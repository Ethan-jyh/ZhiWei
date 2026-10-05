"""Adapter for publishing intervention statements to OASIS environments and verifying platform evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol

from intervention.models import (
    InterventionError,
    Platform,
    PublicationReceipt,
    PublishUncertain,
    Statement,
)
from intervention.storage import StatementStore


class PlatformPublisher(Protocol):
    """Protocol for platform-specific statement publishers."""

    async def publish(self, statement: Statement, *, round_num: int) -> PublicationReceipt:
        ...

    async def reconcile(
        self, statement: Statement, *, round_num: int
    ) -> PublicationReceipt | None:
        ...


class OasisPublisher:
    """Publishes statements through OASIS ManualAction and verifies database evidence."""

    def __init__(
        self,
        env: Any,
        db_path: Path | str,
        platform: Platform,
        store: StatementStore,
        action_factory: Any | None = None,
    ) -> None:
        self.env = env
        self.db_path = Path(db_path)
        self.platform = platform
        self.store = store
        self._action_factory = action_factory

    def _get_max_ids(self) -> tuple[int, int]:
        if not self.db_path.exists():
            return 0, 0
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COALESCE(MAX(rowid), 0) FROM trace")
                max_trace = cur.fetchone()[0]
                cur.execute("SELECT COALESCE(MAX(post_id), 0) FROM post")
                max_post = cur.fetchone()[0]
                return max_trace, max_post
        except Exception:
            return 0, 0

    async def publish(self, statement: Statement, *, round_num: int) -> PublicationReceipt:
        max_trace_before, max_post_before = self._get_max_ids()

        if self._action_factory is not None:
            action = self._action_factory(statement.content)
        else:
            try:
                from oasis import ActionType, ManualAction

                action_type = ActionType.CREATE_POST
                action = ManualAction(
                    action_type=action_type, action_args={"content": statement.content}
                )
            except Exception:
                class _FallbackAction:
                    def __init__(self, action_type: Any, action_args: dict[str, Any]):
                        self.action_type = action_type
                        self.action_args = action_args

                action = _FallbackAction(
                    action_type="CREATE_POST", action_args={"content": statement.content}
                )

        try:
            agent = self.env.agent_graph.get_agent(statement.publisher_agent_id)
        except Exception as e:
            raise InterventionError(
                "agent_not_found",
                f"Agent {statement.publisher_agent_id} not found in environment: {e}",
            )

        try:
            await self.env.step({agent: action})
        except Exception as e:
            # Step threw an exception, check if database partially committed
            receipt = await self.reconcile(statement, round_num=round_num)
            if receipt is not None:
                return receipt
            raise PublishUncertain(f"env.step failed with uncertain outcome: {e}")

        # Verify from database evidence
        if not self.db_path.exists():
            raise InterventionError(
                "database_not_found", f"Database not found at {self.db_path}"
            )

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                cur.execute(
                    """
                    SELECT post_id, content
                    FROM post
                    WHERE user_id = ? AND post_id > ? AND content = ?
                    ORDER BY post_id DESC
                    LIMIT 1
                    """,
                    (statement.publisher_agent_id, max_post_before, statement.content),
                )
                post_row = cur.fetchone()

                cur.execute(
                    """
                    SELECT rowid, action, info
                    FROM trace
                    WHERE user_id = ? AND rowid > ?
                    ORDER BY rowid DESC
                    LIMIT 1
                    """,
                    (statement.publisher_agent_id, max_trace_before),
                )
                trace_row = cur.fetchone()

                if not post_row:
                    raise InterventionError(
                        "post_not_created",
                        f"No post created in {self.platform} database for agent {statement.publisher_agent_id}",
                    )

                post_id = str(post_row["post_id"])
                trace_rowid = int(trace_row["rowid"]) if trace_row else int(post_id)

                return PublicationReceipt(
                    platform=self.platform,
                    post_id=post_id,
                    trace_rowid=trace_rowid,
                    round_num=round_num,
                )
        except InterventionError:
            raise
        except Exception as e:
            raise PublishUncertain(f"Error querying platform verification: {e}")

    async def reconcile(
        self, statement: Statement, *, round_num: int
    ) -> PublicationReceipt | None:
        if not self.db_path.exists():
            return None

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                cur.execute(
                    """
                    SELECT post_id, content
                    FROM post
                    WHERE user_id = ? AND content = ?
                    """,
                    (statement.publisher_agent_id, statement.content),
                )
                post_rows = cur.fetchall()
                if len(post_rows) != 1:
                    return None

                post_id = str(post_rows[0]["post_id"])

                cur.execute(
                    """
                    SELECT rowid, info
                    FROM trace
                    WHERE user_id = ?
                    ORDER BY rowid DESC
                    """,
                    (statement.publisher_agent_id,),
                )
                trace_rows = cur.fetchall()
                matching_trace_rowid = None
                for tr in trace_rows:
                    info = tr["info"] or ""
                    if str(post_id) in info or statement.content in info:
                        matching_trace_rowid = int(tr["rowid"])
                        break

                if matching_trace_rowid is None:
                    matching_trace_rowid = int(post_id)

                return PublicationReceipt(
                    platform=self.platform,
                    post_id=post_id,
                    trace_rowid=matching_trace_rowid,
                    round_num=round_num,
                )
        except Exception:
            return None
