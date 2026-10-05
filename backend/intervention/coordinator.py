"""Round coordinator for synchronizing multi-platform simulation execution and shared intervention boundaries."""

from __future__ import annotations

import asyncio
from typing import Any

from intervention.models import InterventionError, Platform


class RoundCoordinator:
    """Coordinates round boundaries across one or more platforms."""

    def __init__(self, platforms: set[Platform], runtime: Any) -> None:
        if not platforms:
            raise ValueError("At least one platform must be specified")
        self.platforms = set(platforms)
        self.runtime = runtime

        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        self._current_round: int | None = None
        self._arrived: set[Platform] = set()
        self._completed_after: set[Platform] = set()
        self._aborted: bool = False
        self._abort_error: InterventionError | None = None
        self._execute_task: asyncio.Task | None = None
        self._execute_error: Exception | None = None

    async def before_round(self, platform: Platform, round_num: int) -> None:
        """Wait for all platforms to reach round_num and execute intervention boundary once."""
        if platform not in self.platforms:
            return

        task_to_await: asyncio.Task | None = None

        async with self._condition:
            if self._aborted:
                raise self._abort_error or InterventionError("run_aborted", "Simulation aborted")

            if self._current_round is None:
                self._current_round = round_num
            elif self._current_round != round_num:
                err = InterventionError(
                    "round_mismatch",
                    f"Platform '{platform}' arrived at round {round_num}, but active round is {self._current_round}",
                )
                self._aborted = True
                self._abort_error = err
                self._condition.notify_all()
                raise err

            self._arrived.add(platform)

            # If all platforms arrived and execution task has not started yet
            if self._arrived == self.platforms and self._execute_task is None:
                self._execute_task = asyncio.create_task(self.runtime.before_round(round_num))
                self._condition.notify_all()

            # Wait until execute task exists or run is aborted
            while not self._aborted and self._execute_task is None:
                await self._condition.wait()

            if self._aborted:
                raise self._abort_error or InterventionError("run_aborted", "Simulation aborted")

            task_to_await = self._execute_task

        # Await shared execution task outside condition lock
        if task_to_await is not None:
            try:
                await task_to_await
            except Exception as exc:
                async with self._condition:
                    if not self._aborted:
                        err = (
                            exc
                            if isinstance(exc, InterventionError)
                            else InterventionError("publish_error", f"Publish error: {exc}")
                        )
                        self._aborted = True
                        self._abort_error = err
                        self._condition.notify_all()
                    raise self._abort_error or err

        async with self._condition:
            if self._aborted:
                raise self._abort_error or InterventionError("run_aborted", "Simulation aborted")

    async def after_round(self, platform: Platform, round_num: int) -> None:
        """Signify completion of round by a platform, resetting state once all platforms finish."""
        if platform not in self.platforms:
            return

        async with self._condition:
            self._completed_after.add(platform)
            if self._completed_after == self.platforms:
                self._current_round = None
                self._arrived.clear()
                self._completed_after.clear()
                self._execute_task = None
                self._execute_error = None
                self._condition.notify_all()

    async def abort(self, reason: str) -> None:
        """Abort coordination and release all waiting platform tasks."""
        async with self._condition:
            self._aborted = True
            self._abort_error = InterventionError("run_aborted", reason)
            if self._execute_task and not self._execute_task.done():
                self._execute_task.cancel()
            self._condition.notify_all()
