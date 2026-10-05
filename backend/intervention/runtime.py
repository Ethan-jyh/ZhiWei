"""Runtime execution engine for managing and executing intervention statements at round boundaries."""

from __future__ import annotations

import hashlib
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from intervention.models import (
    Execution,
    Platform,
    PublishUncertain,
    RunContext,
    Statement,
)
from intervention.oasis_adapter import PlatformPublisher
from intervention.storage import StatementStore

logger = logging.getLogger("mirofish.intervention.runtime")


def make_platform_rng(seed: int | None, platform: Platform) -> random.Random:
    """Derive an isolated deterministic pseudo-random generator per platform stream."""
    if seed is None:
        return random.Random()
    h = hashlib.sha256(f"{seed}:{platform}".encode("utf-8")).digest()
    derived = int.from_bytes(h[:8], byteorder="big")
    return random.Random(derived)


async def run_round_cycle(
    *,
    platform: Platform,
    round_num: int,
    coordinator: Any,
    act: Callable[[], Awaitable[None]],
    record: Callable[[], Awaitable[None]],
) -> None:
    """Execute standard simulation round lifecycle ensuring shared intervention boundaries."""
    await coordinator.before_round(platform, round_num)
    try:
        await act()
        await record()
    finally:
        await coordinator.after_round(platform, round_num)


class InterventionRuntime:
    """Manages intervention statement lifecycle and round-boundary dispatching."""

    def __init__(
        self,
        store: StatementStore,
        publishers: dict[Platform, PlatformPublisher],
        context: RunContext,
    ) -> None:
        self.store = store
        self.publishers = publishers
        self.context = context
        self._finished = False

    async def before_round(self, round_num: int) -> list[Execution]:
        """Process cancellations and execute eligible statements for round_num."""
        if self._finished:
            return []

        # 1. Process cancellations first
        cancellations = self.store.ready_cancellations()
        for cid in cancellations:
            exec_state = self.store.read_execution(cid)
            if exec_state.status in ("queued", "accepted"):
                exec_state.status = "canceled"
                exec_state.error = "Canceled by user request"
                self.store.write_execution(exec_state)
            self.store.ack_command(cid, cancellation=True)

        # 2. Freeze cutoff set of requests available at the start of this boundary
        requests_snapshot = self.store.ready_requests()
        eligible: list[Statement] = []

        for stmt in requests_snapshot:
            exec_state = self.store.read_execution(stmt.event_id)
            if exec_state.status in (
                "published",
                "failed",
                "canceled",
                "expired",
                "unknown",
                "executing",
            ):
                continue

            if stmt.trigger.mode == "next_round":
                eligible.append(stmt)
            elif stmt.trigger.mode == "scheduled":
                target_round = stmt.trigger.round or 0
                if target_round == round_num:
                    eligible.append(stmt)
                elif target_round < round_num:
                    exec_state.status = "expired"
                    exec_state.error = (
                        f"Scheduled round {target_round} missed (current: {round_num})"
                    )
                    self.store.write_execution(exec_state)
                    self.store.ack_command(stmt.event_id)
                else:
                    if exec_state.status == "queued":
                        exec_state.status = "accepted"
                        exec_state.accepted_round = round_num
                        self.store.write_execution(exec_state)

        # 3. Sort eligible by (target_round, submission_seq, event_id)
        eligible.sort(
            key=lambda s: (
                s.trigger.round if s.trigger.mode == "scheduled" else round_num,
                s.submission_seq,
                s.event_id,
            )
        )

        results: list[Execution] = []
        for stmt in eligible:
            # Re-read execution in case a cancellation arrived right before
            exec_state = self.store.read_execution(stmt.event_id)
            if exec_state.status in ("canceled", "published", "failed", "expired", "unknown"):
                continue

            exec_state.status = "executing"
            exec_state.accepted_round = exec_state.accepted_round or round_num
            exec_state.effective_round = round_num
            self.store.write_execution(exec_state)

            publisher = self.publishers.get(stmt.platform)
            if not publisher:
                exec_state.status = "failed"
                exec_state.error = f"Publisher for platform '{stmt.platform}' not configured"
                self.store.write_execution(exec_state)
                self.store.ack_command(stmt.event_id)
                results.append(exec_state)
                continue

            try:
                receipt = await publisher.publish(stmt, round_num=round_num)
                exec_state.status = "published"
                exec_state.receipt = receipt
                exec_state.effective_round = round_num
                self.store.write_execution(exec_state)
                self.store.ack_command(stmt.event_id)
                results.append(exec_state)
            except PublishUncertain as exc:
                exec_state.status = "unknown"
                exec_state.error = str(exc)
                self.store.write_execution(exec_state)
                self.store.ack_command(stmt.event_id)
                results.append(exec_state)
            except Exception as exc:
                exec_state.status = "failed"
                exec_state.error = str(exc)
                self.store.write_execution(exec_state)
                self.store.ack_command(stmt.event_id)
                results.append(exec_state)

        return results

    async def finish(self, reason: Literal["completed", "stopped", "failed"]) -> None:
        """Mark remaining pending statements according to finish reason."""
        self._finished = True
        requests = self.store.ready_requests()
        for stmt in requests:
            exec_state = self.store.read_execution(stmt.event_id)
            if exec_state.status in ("queued", "accepted"):
                if reason == "completed":
                    exec_state.status = "expired"
                    exec_state.error = "Simulation completed before statement execution"
                elif reason == "stopped":
                    exec_state.status = "canceled"
                    exec_state.error = "Simulation stopped before statement execution"
                else:
                    exec_state.status = "failed"
                    exec_state.error = "Simulation failed before statement execution"
                self.store.write_execution(exec_state)
                self.store.ack_command(stmt.event_id)

    async def recover_interrupted(self) -> None:
        """Recover any statements left in executing or unknown state after process restart."""
        requests = self.store.ready_requests()
        for stmt in requests:
            exec_state = self.store.read_execution(stmt.event_id)
            if exec_state.status in ("executing", "unknown"):
                publisher = self.publishers.get(stmt.platform)
                if publisher:
                    try:
                        receipt = await publisher.reconcile(
                            stmt, round_num=exec_state.effective_round or 1
                        )
                        if receipt:
                            exec_state.status = "published"
                            exec_state.receipt = receipt
                            self.store.write_execution(exec_state)
                            continue
                    except Exception:
                        pass
                if exec_state.status == "executing":
                    exec_state.status = "failed"
                    exec_state.error = "Process interrupted during execution; no platform evidence found"
                    self.store.write_execution(exec_state)
