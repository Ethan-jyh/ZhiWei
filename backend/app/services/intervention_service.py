"""Application service for intervention planning, submission, and status queries."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from intervention.models import (
    Execution,
    InterventionError,
    RunContext,
    Statement,
    validate_statement,
)
from intervention.storage import StatementStore


class InterventionService:
    """Manages statement storage and application-level lifecycle operations."""

    def __init__(
        self,
        root: Path | str,
        context_provider: Callable[[str], RunContext],
    ) -> None:
        self.root = Path(root).resolve()
        self.context_provider = context_provider

    def _resolve_run_dir(self, run_id: str) -> Path:
        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise ValueError(f"Invalid run_id '{run_id}'")
        run_dir = (self.root / run_id).resolve()
        if not str(run_dir).startswith(str(self.root)):
            raise ValueError("Directory traversal detected")
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory '{run_id}' not found")
        return run_dir

    def _get_store(self, run_id: str) -> StatementStore:
        run_dir = self._resolve_run_dir(run_id)
        return StatementStore(run_dir)

    def save_plan(self, run_id: str, payloads: list[dict[str, Any]]) -> list[Statement]:
        context = self.context_provider(run_id)
        if context.phase != "prepared":
            raise InterventionError(
                "run_not_accepting",
                f"Cannot save plan for run in phase '{context.phase}' (must be prepared)",
            )

        store = self._get_store(run_id)
        statements: list[Statement] = []

        for p in payloads:
            data = dict(p)
            event_id = data.pop("event_id", None) or f"iv_{uuid.uuid4().hex[:12]}"
            data["event_id"] = event_id
            data["run_id"] = run_id
            stmt = Statement(**data)
            validate_statement(stmt, context)
            persisted = store.enqueue(stmt)
            statements.append(persisted)

        return statements

    def submit(self, run_id: str, payload: dict[str, Any]) -> tuple[Statement, Execution]:
        context = self.context_provider(run_id)
        store = self._get_store(run_id)

        data = dict(payload)
        event_id = data.pop("event_id", None) or f"iv_{uuid.uuid4().hex[:12]}"
        data["event_id"] = event_id
        data["run_id"] = run_id

        stmt = Statement(**data)
        validate_statement(stmt, context)

        persisted = store.enqueue(stmt)
        execution = store.read_execution(persisted.event_id)
        return persisted, execution

    def list(self, run_id: str) -> list[dict[str, Any]]:
        store = self._get_store(run_id)
        statements = store.list_statements()
        results: list[dict[str, Any]] = []
        for s in statements:
            exec_state = store.read_execution(s.event_id)
            results.append({
                "statement": s.model_dump(mode="json"),
                "execution": exec_state.model_dump(mode="json"),
            })
        return results

    def cancel(self, run_id: str, event_id: str) -> Execution:
        store = self._get_store(run_id)
        store.request_cancel(event_id)
        return store.read_execution(event_id)
