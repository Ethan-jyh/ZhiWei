from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

import pytest

from app.services.simulation_ipc import CommandType, SimulationIPCClient
from intervention.models import Execution, InterventionError, Statement, Trigger
from intervention.storage import StatementStore


def test_repeated_enqueue_returns_original_event(tmp_path, statement_factory):
    store = StatementStore(tmp_path)
    first = store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1"))
    retry = store.enqueue(statement_factory(event_id="iv2", idempotency_key="k1"))
    assert retry.event_id == first.event_id
    assert len(store.list_statements()) == 1


def test_same_key_different_payload_conflicts(tmp_path, statement_factory):
    store = StatementStore(tmp_path)
    store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1", content="第一版"))
    with pytest.raises(InterventionError) as exc:
        store.enqueue(statement_factory(event_id="iv2", idempotency_key="k1", content="修改版"))
    assert exc.value.code == "idempotency_conflict"


def _worker_enqueue(run_dir_str: str, event_id: str, idempotency_key: str, content: str):
    store = StatementStore(Path(run_dir_str))
    stmt = Statement(
        event_id=event_id,
        idempotency_key=idempotency_key,
        run_id="run1",
        topic_id="topic1",
        platform="twitter",
        publisher_agent_id=12,
        content=content,
        trigger=Trigger(mode="next_round", round=None),
        kind="official_response",
    )
    store.enqueue(stmt)


def test_two_processes_one_event(tmp_path):
    p1 = mp.Process(target=_worker_enqueue, args=(str(tmp_path), "iv1", "shared_k", "内容"))
    p2 = mp.Process(target=_worker_enqueue, args=(str(tmp_path), "iv2", "shared_k", "内容"))
    p1.start()
    p2.start()
    p1.join(timeout=5)
    p2.join(timeout=5)

    store = StatementStore(tmp_path)
    stmts = store.list_statements()
    assert len(stmts) == 1
    assert stmts[0].idempotency_key == "shared_k"


def test_crash_after_registration_repaired_by_flush(tmp_path, statement_factory, monkeypatch):
    store = StatementStore(tmp_path)
    stmt = statement_factory(event_id="iv1", idempotency_key="k1")

    # Hook replace to simulate a crash right after DB insertion but before request file replacement
    import os

    original_replace = os.replace
    crashed = False

    def buggy_replace(src, dst):
        nonlocal crashed
        if "requests" in str(dst) and not crashed:
            crashed = True
            raise OSError("simulated disk crash")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", buggy_replace)

    with pytest.raises(OSError):
        store.enqueue(stmt)

    # Now recover monkeypatch and call flush_outbox
    monkeypatch.undo()
    assert not (tmp_path / "interventions" / "requests" / "iv1.json").exists()

    flushed = store.flush_outbox()
    assert flushed == 1
    assert (tmp_path / "interventions" / "requests" / "iv1.json").exists()


def test_reader_ignores_tmp(tmp_path, statement_factory):
    store = StatementStore(tmp_path)
    store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1"))

    # Create a rogue .tmp file in requests dir
    req_dir = tmp_path / "interventions" / "requests"
    (req_dir / "rogue.tmp").write_text("corrupted", encoding="utf-8")

    ready = store.ready_requests()
    assert len(ready) == 1
    assert ready[0].event_id == "iv1"


def test_async_enqueue_does_not_sleep(tmp_path, monkeypatch):
    def no_sleep(seconds):
        raise RuntimeError("Sleep was called!")

    monkeypatch.setattr(time, "sleep", no_sleep)
    client = SimulationIPCClient(str(tmp_path))
    cmd_id = client.enqueue_command(
        CommandType.INJECT_STATEMENT,
        {"event_id": "iv1"},
        command_id="cmd_test_1",
    )
    assert cmd_id == "cmd_test_1"
    assert (tmp_path / "ipc_commands" / "cmd_test_1.json").exists()


def test_cancellation_and_ack(tmp_path, statement_factory):
    store = StatementStore(tmp_path)
    store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1"))

    store.request_cancel("iv1")
    assert store.ready_cancellations() == ["iv1"]
    assert (tmp_path / "ipc_commands" / "cancel_iv1.json").exists()

    store.ack_command("iv1", cancellation=True)
    assert store.ready_cancellations() == []
    assert not (tmp_path / "ipc_commands" / "cancel_iv1.json").exists()


def test_execution_transitions(tmp_path):
    store = StatementStore(tmp_path)
    # Default unwritten execution is queued
    exec_init = store.read_execution("iv1")
    assert exec_init.status == "queued"

    exec_executing = Execution(event_id="iv1", status="executing", accepted_round=3)
    store.write_execution(exec_executing)
    assert store.read_execution("iv1").status == "executing"

    exec_published = Execution(event_id="iv1", status="published", accepted_round=3, effective_round=3)
    store.write_execution(exec_published)
    assert store.read_execution("iv1").status == "published"
