"""Topic labeling, parent-post inheritance, and classification provenance for action logs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from intervention.metric_models import ActionLogSnapshot, ActionRecord, TopicLabel
from intervention.models import Platform


def read_actions(run_dir: Path | str) -> ActionLogSnapshot:
    """Read complete actions from twitter and reddit platform logs without line limits."""
    run_path = Path(run_dir)
    run_id = run_path.name
    actions: list[ActionRecord] = []
    errors: list[str] = []
    hasher = hashlib.sha256()
    observed_round = 0

    for platform in ("twitter", "reddit"):
        log_file = run_path / platform / "actions.jsonl"
        if not log_file.exists():
            continue

        with open(log_file, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, start=1):
                raw = line.strip()
                if not raw:
                    continue
                hasher.update(raw.encode("utf-8"))
                try:
                    entry = json.loads(raw)
                except Exception as e:
                    errors.append(f"JSON decode error in {platform} line {line_idx}: {e}")
                    continue

                if "event_type" in entry:
                    # Skip round_start, round_end, etc.
                    continue

                round_num = entry.get("round", 0)
                if round_num > observed_round:
                    observed_round = round_num

                args = entry.get("action_args") or {}
                content = (
                    args.get("content")
                    or args.get("quote_content")
                    or entry.get("result")
                    or ""
                )

                post_id = args.get("new_post_id") or args.get("post_id")
                if post_id is not None:
                    post_id = str(post_id)

                parent_post_id = None
                action_type = entry.get("action_type", "")
                if action_type in ("CREATE_COMMENT", "LIKE_POST", "DISLIKE_POST"):
                    parent_post_id = args.get("post_id") or args.get("parent_post_id")
                elif action_type in ("QUOTE_POST", "REPOST"):
                    parent_post_id = args.get("quoted_id") or args.get("post_id")

                if parent_post_id is not None:
                    parent_post_id = str(parent_post_id)

                trace_rowid = entry.get("trace_rowid")
                if trace_rowid is None:
                    trace_rowid = line_idx

                actions.append(
                    ActionRecord(
                        run_id=run_id,
                        platform=platform,  # type: ignore[arg-type]
                        trace_rowid=trace_rowid,
                        round_num=round_num,
                        agent_id=entry.get("agent_id", 0),
                        action_type=action_type,
                        content=str(content),
                        success=entry.get("success", True),
                        origin=entry.get("origin", "agent"),
                        intervention_id=entry.get("intervention_id"),
                        topic_id=entry.get("topic_id"),
                        post_id=post_id,
                        parent_post_id=parent_post_id,
                    )
                )

    return ActionLogSnapshot(
        actions=actions,
        errors=errors,
        fingerprint=hasher.hexdigest(),
        observed_round=observed_round,
    )


class TopicLabelStore:
    """Stores and caches topic classification labels and manual corrections."""

    def __init__(self, run_dir: Path | str) -> None:
        self.run_dir = Path(run_dir)
        self.db_path = self.run_dir / "interventions" / "topic_labels.sqlite"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topic_labels (
                    run_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    trace_rowid INTEGER NOT NULL,
                    topic_id TEXT NOT NULL,
                    related INTEGER,
                    source TEXT NOT NULL,
                    version TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, platform, trace_rowid)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS content_cache (
                    content_hash TEXT NOT NULL,
                    summary_hash TEXT NOT NULL,
                    version TEXT NOT NULL,
                    related INTEGER,
                    reason TEXT NOT NULL,
                    PRIMARY KEY (content_hash, summary_hash, version)
                );
                """
            )
            conn.commit()

    def get(self, key: tuple[str, Platform, int]) -> TopicLabel | None:
        run_id, platform, trace_rowid = key
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT run_id, platform, trace_rowid, topic_id, related, source, version, reason
                FROM topic_labels
                WHERE run_id = ? AND platform = ? AND trace_rowid = ?
                """,
                (run_id, platform, trace_rowid),
            )
            row = cur.fetchone()
            if not row:
                return None
            rel = bool(row["related"]) if row["related"] is not None else None
            return TopicLabel(
                key=key,
                topic_id=row["topic_id"],
                related=rel,
                source=row["source"],
                version=row["version"],
                reason=row["reason"],
            )

    def save(self, label: TopicLabel) -> None:
        run_id, platform, trace_rowid = label.key
        now = datetime.now(timezone.utc).isoformat()
        rel_int = (
            1 if label.related is True else (0 if label.related is False else None)
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO topic_labels (run_id, platform, trace_rowid, topic_id, related, source, version, reason, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, platform, trace_rowid) DO UPDATE SET
                    topic_id = excluded.topic_id,
                    related = excluded.related,
                    source = excluded.source,
                    version = excluded.version,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (
                    run_id,
                    platform,
                    trace_rowid,
                    label.topic_id,
                    rel_int,
                    label.source,
                    label.version,
                    label.reason,
                    now,
                ),
            )
            conn.commit()

    def get_cached_content(
        self, content_hash: str, summary_hash: str, version: str
    ) -> tuple[bool, str] | None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT related, reason
                FROM content_cache
                WHERE content_hash = ? AND summary_hash = ? AND version = ?
                """,
                (content_hash, summary_hash, version),
            )
            row = cur.fetchone()
            if row is not None:
                return bool(row["related"]), row["reason"]
        return None

    def cache_content(
        self,
        content_hash: str,
        summary_hash: str,
        version: str,
        related: bool,
        reason: str,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO content_cache (content_hash, summary_hash, version, related, reason)
                VALUES (?, ?, ?, ?, ?)
                """,
                (content_hash, summary_hash, version, 1 if related else 0, reason),
            )
            conn.commit()

    def revision(self) -> str:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT run_id, platform, trace_rowid, related, source, version, updated_at
                FROM topic_labels
                ORDER BY run_id, platform, trace_rowid
                """
            )
            rows = cur.fetchall()
            h = hashlib.sha256()
            for r in rows:
                h.update(
                    f"{r['run_id']}:{r['platform']}:{r['trace_rowid']}:{r['related']}:{r['source']}:{r['version']}:{r['updated_at']}".encode(
                        "utf-8"
                    )
                )
            return h.hexdigest()[:16]


def correct_label(
    store: TopicLabelStore,
    key: tuple[str, Platform, int],
    *,
    related: bool,
    reason: str,
) -> TopicLabel:
    """Manually apply an operator label override."""
    label = TopicLabel(
        key=key,
        topic_id="",  # Will be preserved or filled
        related=related,
        source="manual",
        version="manual",
        reason=reason,
    )
    existing = store.get(key)
    if existing:
        label.topic_id = existing.topic_id
    store.save(label)
    return label


def label_actions(
    actions: list[ActionRecord],
    *,
    topic_id: str,
    topic_summary: str,
    classifier: Callable[[str, str], tuple[bool, str]],
    version: str,
    store: TopicLabelStore,
) -> list[TopicLabel]:
    """Classify and label actions with topic provenance and caching."""
    post_map: dict[tuple[str, Platform, str], TopicLabel] = {}
    labels: list[TopicLabel] = []
    summary_hash = hashlib.sha256(topic_summary.encode("utf-8")).hexdigest()

    for act in actions:
        key = (act.run_id, act.platform, act.trace_rowid)

        # 1. Manual correction takes precedence
        existing = store.get(key)
        if existing and existing.source == "manual":
            labels.append(existing)
            if act.post_id:
                post_map[(act.run_id, act.platform, act.post_id)] = existing
            continue

        # 2. Explicit topic assignment
        if act.topic_id and act.topic_id == topic_id:
            lbl = TopicLabel(
                key=key,
                topic_id=topic_id,
                related=True,
                source="explicit",
                version=version,
                reason="Explicitly tagged with topic",
            )
            store.save(lbl)
            labels.append(lbl)
            if act.post_id:
                post_map[(act.run_id, act.platform, act.post_id)] = lbl
            continue

        # 3. Inherit from parent post if present
        if act.parent_post_id:
            parent_key = (act.run_id, act.platform, act.parent_post_id)
            parent_label = post_map.get(parent_key)
            if parent_label is not None and parent_label.related is not None:
                lbl = TopicLabel(
                    key=key,
                    topic_id=topic_id,
                    related=parent_label.related,
                    source="parent",
                    version=version,
                    reason=f"Inherited from parent post {act.parent_post_id}",
                )
                store.save(lbl)
                labels.append(lbl)
                if act.post_id:
                    post_map[(act.run_id, act.platform, act.post_id)] = lbl
                continue

        # 4. Content classifier
        content_hash = hashlib.sha256(act.content.encode("utf-8")).hexdigest()
        cached = store.get_cached_content(content_hash, summary_hash, version)
        if cached is not None:
            is_rel, reason = cached
            lbl = TopicLabel(
                key=key,
                topic_id=topic_id,
                related=is_rel,
                source="classifier",
                version=version,
                reason=reason,
            )
            store.save(lbl)
            labels.append(lbl)
            if act.post_id:
                post_map[(act.run_id, act.platform, act.post_id)] = lbl
            continue

        try:
            is_rel, reason = classifier(act.content, topic_summary)
            store.cache_content(content_hash, summary_hash, version, is_rel, reason)
            lbl = TopicLabel(
                key=key,
                topic_id=topic_id,
                related=is_rel,
                source="classifier",
                version=version,
                reason=reason,
            )
            store.save(lbl)
            labels.append(lbl)
            if act.post_id:
                post_map[(act.run_id, act.platform, act.post_id)] = lbl
        except Exception as e:
            lbl = TopicLabel(
                key=key,
                topic_id=topic_id,
                related=None,
                source="pending",
                version=version,
                reason=f"Classifier failed: {e}",
            )
            store.save(lbl)
            labels.append(lbl)
            if act.post_id:
                post_map[(act.run_id, act.platform, act.post_id)] = lbl

    return labels
