from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.simulation_runner import AgentAction
from intervention.models import InterventionError, PublishUncertain, Statement, Trigger
from intervention.oasis_adapter import OasisPublisher
from intervention.storage import StatementStore


def create_oasis_db(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE trace (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            info TEXT,
            created_at TEXT
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE post (
            post_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT,
            created_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_action_identity_survives_serialization():
    action = AgentAction(
        round_num=5,
        timestamp="t",
        platform="twitter",
        agent_id=12,
        agent_name="学校",
        action_type="CREATE_POST",
        trace_rowid=18,
        origin="intervention",
        intervention_id="iv1",
        topic_id="topic1",
    )
    result = action.to_dict()
    assert result["trace_rowid"] == 18
    assert result["origin"] == "intervention"
    assert result["intervention_id"] == "iv1"


def test_existing_action_json_still_loads():
    old_data = {
        "round": 3,
        "timestamp": "2026-10-05T00:00:00",
        "agent_id": 5,
        "agent_name": "agent5",
        "action_type": "LIKE_POST",
    }
    action = AgentAction(
        round_num=old_data.get("round", 0),
        timestamp=old_data.get("timestamp", ""),
        platform="twitter",
        agent_id=old_data.get("agent_id", 0),
        agent_name=old_data.get("agent_name", ""),
        action_type=old_data.get("action_type", ""),
    )
    assert action.origin == "agent"
    assert action.trace_rowid is None
    assert action.intervention_id is None


@pytest.mark.asyncio
async def test_publish_creates_post_and_returns_receipt(tmp_path, statement_factory):
    db_path = tmp_path / "twitter.db"
    create_oasis_db(db_path)
    store = StatementStore(tmp_path)

    agent_mock = MagicMock()
    env_mock = MagicMock()
    env_mock.agent_graph.get_agent.return_value = agent_mock

    async def fake_step(actions):
        # Insert trace and post into sqlite as OASIS would
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("INSERT INTO post (user_id, content, created_at) VALUES (12, '学校回应', '2026-10-05')",)
        post_id = c.lastrowid
        info = f'{{"content": "学校回应", "new_post_id": {post_id}}}'
        c.execute("INSERT INTO trace (user_id, action, info, created_at) VALUES (12, 'CREATE_POST', ?, '2026-10-05')", (info,))
        conn.commit()
        conn.close()

    env_mock.step = AsyncMock(side_effect=fake_step)

    publisher = OasisPublisher(env_mock, db_path, "twitter", store, action_factory=lambda c: MagicMock())
    stmt = statement_factory(event_id="iv1", content="学校回应", publisher_agent_id=12)

    receipt = await publisher.publish(stmt, round_num=5)
    assert receipt.platform == "twitter"
    assert receipt.round_num == 5
    assert receipt.trace_rowid >= 1
    assert str(receipt.post_id) == "1"


@pytest.mark.asyncio
async def test_post_failure_has_no_receipt(tmp_path, statement_factory):
    db_path = tmp_path / "twitter.db"
    create_oasis_db(db_path)
    store = StatementStore(tmp_path)

    agent_mock = MagicMock()
    env_mock = MagicMock()
    env_mock.agent_graph.get_agent.return_value = agent_mock

    async def fake_step_no_post(actions):
        # Step executes but no post is inserted
        pass

    env_mock.step = AsyncMock(side_effect=fake_step_no_post)

    publisher = OasisPublisher(env_mock, db_path, "twitter", store, action_factory=lambda c: MagicMock())
    stmt = statement_factory(event_id="iv1", content="学校回应", publisher_agent_id=12)

    with pytest.raises(InterventionError):
        await publisher.publish(stmt, round_num=5)


@pytest.mark.asyncio
async def test_crash_evidence_reconciles_without_republish(tmp_path, statement_factory):
    db_path = tmp_path / "twitter.db"
    create_oasis_db(db_path)
    store = StatementStore(tmp_path)

    # Pre-populate existing post and trace
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("INSERT INTO post (user_id, content, created_at) VALUES (12, '学校回应', '2026-10-05')")
    c.execute("INSERT INTO trace (user_id, action, info, created_at) VALUES (12, 'CREATE_POST', '{\"content\":\"学校回应\",\"new_post_id\":1}', '2026-10-05')")
    conn.commit()
    conn.close()

    env_mock = MagicMock()
    env_mock.step = AsyncMock()

    publisher = OasisPublisher(env_mock, db_path, "twitter", store)
    stmt = statement_factory(event_id="iv1", content="学校回应", publisher_agent_id=12)

    receipt = await publisher.reconcile(stmt, round_num=5)
    assert receipt is not None
    assert str(receipt.post_id) == "1"
    env_mock.step.assert_not_called()
