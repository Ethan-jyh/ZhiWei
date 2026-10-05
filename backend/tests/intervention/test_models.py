from __future__ import annotations

import pytest
from pydantic import ValidationError

from intervention.models import (
    INTERVENTION_MAX_CONTENT_CHARS,
    Execution,
    InterventionError,
    PublicationReceipt,
    RunContext,
    Statement,
    Trigger,
    validate_statement,
)


def make_context(
    run_id: str = "run1",
    phase: str = "prepared",
    total_rounds: int = 10,
    platforms: set[str] | None = None,
    agent_ids: dict[str, set[int]] | None = None,
    topic_id: str = "topic1",
) -> RunContext:
    return RunContext(
        run_id=run_id,
        phase=phase,
        total_rounds=total_rounds,
        platforms=platforms or {"twitter"},
        agent_ids=agent_ids or {"twitter": {12}},
        topic_id=topic_id,
    )


def make_statement(**kwargs) -> Statement:
    defaults = {
        "event_id": "iv1",
        "idempotency_key": "k1",
        "run_id": "run1",
        "topic_id": "topic1",
        "platform": "twitter",
        "publisher_agent_id": 12,
        "content": "学校回应",
        "trigger": Trigger(mode="scheduled", round=5),
        "kind": "official_response",
    }
    defaults.update(kwargs)
    return Statement(**defaults)


def test_scheduled_round_cannot_exceed_truncated_window():
    ctx = RunContext(
        run_id="run1",
        phase="prepared",
        total_rounds=10,
        platforms={"twitter"},
        agent_ids={"twitter": {12}},
        topic_id="topic1",
    )
    stmt = Statement(
        event_id="iv1",
        idempotency_key="k1",
        run_id="run1",
        topic_id="topic1",
        platform="twitter",
        publisher_agent_id=12,
        content="学校回应",
        trigger=Trigger(mode="scheduled", round=15),
        kind="official_response",
    )
    with pytest.raises(InterventionError) as exc:
        validate_statement(stmt, ctx)
    assert exc.value.code == "round_out_of_range"


def test_wrong_platform_role_rejected():
    ctx = make_context(agent_ids={"twitter": {12}})
    stmt = make_statement(publisher_agent_id=99)
    with pytest.raises(InterventionError) as exc:
        validate_statement(stmt, ctx)
    assert exc.value.code == "invalid_publisher"


def test_path_ids_rejected():
    with pytest.raises((ValidationError, InterventionError)):
        make_statement(event_id="../x")


def test_prepared_rejects_next_round():
    ctx = make_context(phase="prepared")
    stmt = make_statement(trigger=Trigger(mode="next_round", round=None))
    with pytest.raises(InterventionError) as exc:
        validate_statement(stmt, ctx)
    assert exc.value.code == "invalid_trigger_for_phase"


def test_running_rejects_scheduled():
    ctx = make_context(phase="running")
    stmt = make_statement(trigger=Trigger(mode="scheduled", round=2))
    with pytest.raises(InterventionError) as exc:
        validate_statement(stmt, ctx)
    assert exc.value.code == "invalid_trigger_for_phase"


def test_interview_rejects_submission():
    ctx = make_context(phase="interview")
    stmt = make_statement()
    with pytest.raises(InterventionError) as exc:
        validate_statement(stmt, ctx)
    assert exc.value.code == "run_not_accepting"


def test_boolean_round_rejected():
    with pytest.raises((ValidationError, InterventionError)):
        Trigger(mode="scheduled", round=True)  # type: ignore[arg-type]


def test_whitespace_content_rejected():
    with pytest.raises((ValidationError, InterventionError)):
        make_statement(content="   \n\t  ")


def test_content_too_long_rejected():
    with pytest.raises((ValidationError, InterventionError)):
        make_statement(content="a" * (INTERVENTION_MAX_CONTENT_CHARS + 1))


def test_receipt_and_execution_valid():
    receipt = PublicationReceipt(
        platform="twitter",
        post_id="post_100",
        trace_rowid=42,
        round_num=5,
    )
    execution = Execution(
        event_id="iv1",
        status="published",
        accepted_round=5,
        effective_round=5,
        receipt=receipt,
    )
    assert execution.status == "published"
    assert execution.receipt.post_id == "post_100"
