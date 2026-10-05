"""Atomically and idempotently deliver intervention requests and manage execution state."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.simulation_ipc import CommandType, SimulationIPCClient
from intervention.models import Execution, InterventionError, PublicationReceipt, Statement


def _canonical_payload_hash(statement: Statement) -> str:
    data = statement.model_dump(mode="json")
    data.pop("event_id", None)
    data.pop("submission_seq", None)
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class StatementStore:
    """Storage and state manager for run interventions."""

    def __init__(self, run_dir: Path | str) -> None:
        self.run_dir = Path(run_dir)
        self.interventions_dir = self.run_dir / "interventions"
        self.requests_dir = self.interventions_dir / "requests"
        self.executions_dir = self.interventions_dir / "executions"
        self.cancellations_dir = self.interventions_dir / "cancellations"
        self.db_path = self.interventions_dir / "submissions.sqlite"

        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.executions_dir.mkdir(parents=True, exist_ok=True)
        self.cancellations_dir.mkdir(parents=True, exist_ok=True)

        self.ipc_client = SimulationIPCClient(str(self.run_dir))
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    run_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    submission_seq INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    statement_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, idempotency_key)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    event_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    accepted_round INTEGER,
                    effective_round INTEGER,
                    receipt_json TEXT,
                    error TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    accepted_round INTEGER,
                    effective_round INTEGER,
                    receipt_json TEXT,
                    error TEXT,
                    timestamp TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def _atomic_write_json(self, target_file: Path, data: dict[str, Any]) -> None:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = target_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, target_file)

    def enqueue(self, statement: Statement) -> Statement:
        payload_hash = _canonical_payload_hash(statement)
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.cursor()
            cur.execute(
                "SELECT event_id, payload_hash, statement_json, submission_seq FROM submissions WHERE run_id = ? AND idempotency_key = ?",
                (statement.run_id, statement.idempotency_key),
            )
            row = cur.fetchone()
            if row is not None:
                if row["payload_hash"] != payload_hash:
                    conn.rollback()
                    raise InterventionError(
                        "idempotency_conflict",
                        f"Idempotency key '{statement.idempotency_key}' reused with conflicting payload",
                    )
                existing_data = json.loads(row["statement_json"])
                conn.commit()
                return Statement(**existing_data)

            cur.execute(
                "SELECT COALESCE(MAX(submission_seq), 0) + 1 AS next_seq FROM submissions WHERE run_id = ?",
                (statement.run_id,),
            )
            next_seq = cur.fetchone()["next_seq"]

            stmt_dict = statement.model_dump(mode="json")
            stmt_dict["submission_seq"] = next_seq
            persisted_statement = Statement(**stmt_dict)

            cur.execute(
                """
                INSERT INTO submissions (run_id, idempotency_key, event_id, payload_hash, submission_seq, created_at, statement_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    persisted_statement.run_id,
                    persisted_statement.idempotency_key,
                    persisted_statement.event_id,
                    payload_hash,
                    next_seq,
                    now,
                    json.dumps(stmt_dict, ensure_ascii=False),
                ),
            )
            conn.commit()

        # Atomic write to requests directory
        req_file = self.requests_dir / f"{persisted_statement.event_id}.json"
        self._atomic_write_json(req_file, stmt_dict)

        # Enqueue IPC notification
        try:
            self.ipc_client.enqueue_command(
                CommandType.INJECT_STATEMENT,
                {"event_id": persisted_statement.event_id},
                command_id=f"inject_{persisted_statement.event_id}",
            )
        except Exception:
            pass

        return persisted_statement

    def flush_outbox(self) -> int:
        flushed_count = 0
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT event_id, statement_json FROM submissions ORDER BY submission_seq ASC"
            )
            rows = cur.fetchall()

        for row in rows:
            event_id = row["event_id"]
            req_file = self.requests_dir / f"{event_id}.json"
            if not req_file.exists():
                data = json.loads(row["statement_json"])
                self._atomic_write_json(req_file, data)
                flushed_count += 1

            execution = self.read_execution(event_id)
            if execution.status in (
                "accepted",
                "published",
                "failed",
                "canceled",
                "expired",
            ):
                continue

            cmd_file = Path(self.ipc_client.commands_dir) / f"inject_{event_id}.json"
            if not cmd_file.exists():
                try:
                    self.ipc_client.enqueue_command(
                        CommandType.INJECT_STATEMENT,
                        {"event_id": event_id},
                        command_id=f"inject_{event_id}",
                    )
                except Exception:
                    pass

        return flushed_count

    def list_statements(self) -> list[Statement]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT statement_json FROM submissions ORDER BY submission_seq ASC"
            )
            rows = cur.fetchall()
        return [Statement(**json.loads(r["statement_json"])) for r in rows]

    def read_execution(self, event_id: str) -> Execution:
        exec_file = self.executions_dir / f"{event_id}.json"
        if exec_file.exists():
            try:
                with open(exec_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return Execution(**data)
            except Exception:
                pass

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT status, accepted_round, effective_round, receipt_json, error FROM executions WHERE event_id = ?",
                (event_id,),
            )
            row = cur.fetchone()
            if row is not None:
                receipt = (
                    PublicationReceipt(**json.loads(row["receipt_json"]))
                    if row["receipt_json"]
                    else None
                )
                return Execution(
                    event_id=event_id,
                    status=row["status"],
                    accepted_round=row["accepted_round"],
                    effective_round=row["effective_round"],
                    receipt=receipt,
                    error=row["error"],
                )

        return Execution(event_id=event_id, status="queued")

    def write_execution(self, execution: Execution) -> None:
        now = datetime.now(timezone.utc).isoformat()
        exec_dict = execution.model_dump(mode="json")
        receipt_json = (
            json.dumps(exec_dict["receipt"], ensure_ascii=False)
            if exec_dict.get("receipt")
            else None
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO executions (event_id, status, accepted_round, effective_round, receipt_json, error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    status=excluded.status,
                    accepted_round=excluded.accepted_round,
                    effective_round=excluded.effective_round,
                    receipt_json=excluded.receipt_json,
                    error=excluded.error,
                    updated_at=excluded.updated_at
                """,
                (
                    execution.event_id,
                    execution.status,
                    execution.accepted_round,
                    execution.effective_round,
                    receipt_json,
                    execution.error,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO transitions (event_id, status, accepted_round, effective_round, receipt_json, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.event_id,
                    execution.status,
                    execution.accepted_round,
                    execution.effective_round,
                    receipt_json,
                    execution.error,
                    now,
                ),
            )
            conn.commit()

        exec_file = self.executions_dir / f"{execution.event_id}.json"
        self._atomic_write_json(exec_file, exec_dict)

    def append_transition(self, execution: Execution) -> None:
        now = datetime.now(timezone.utc).isoformat()
        receipt_json = (
            json.dumps(execution.receipt.model_dump(mode="json"), ensure_ascii=False)
            if execution.receipt
            else None
        )
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO transitions (event_id, status, accepted_round, effective_round, receipt_json, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.event_id,
                    execution.status,
                    execution.accepted_round,
                    execution.effective_round,
                    receipt_json,
                    execution.error,
                    now,
                ),
            )
            conn.commit()

    def request_cancel(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        cancel_file = self.cancellations_dir / f"{event_id}.json"
        self._atomic_write_json(cancel_file, {"event_id": event_id, "timestamp": now})

        try:
            self.ipc_client.enqueue_command(
                CommandType.CANCEL_STATEMENT,
                {"event_id": event_id},
                command_id=f"cancel_{event_id}",
            )
        except Exception:
            pass

    def ready_requests(self) -> list[Statement]:
        if not self.requests_dir.exists():
            return []
        statements: list[Statement] = []
        for file in self.requests_dir.iterdir():
            if file.is_file() and file.suffix == ".json" and not file.name.startswith("."):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    statements.append(Statement(**data))
                except Exception:
                    pass
        statements.sort(key=lambda s: s.submission_seq)
        return statements

    def ready_cancellations(self) -> list[str]:
        if not self.cancellations_dir.exists():
            return []
        cancellations: list[str] = []
        for file in self.cancellations_dir.iterdir():
            if file.is_file() and file.suffix == ".json" and not file.name.startswith("."):
                cancellations.append(file.stem)
        return sorted(cancellations)

    def ack_command(self, event_id: str, *, cancellation: bool = False) -> None:
        commands_dir = Path(self.ipc_client.commands_dir)
        if cancellation:
            cmd_file = commands_dir / f"cancel_{event_id}.json"
            if cmd_file.exists():
                try:
                    cmd_file.unlink()
                except OSError:
                    pass
            cancel_file = self.cancellations_dir / f"{event_id}.json"
            if cancel_file.exists():
                try:
                    cancel_file.unlink()
                except OSError:
                    pass
        else:
            cmd_file = commands_dir / f"inject_{event_id}.json"
            if cmd_file.exists():
                try:
                    cmd_file.unlink()
                except OSError:
                    pass
