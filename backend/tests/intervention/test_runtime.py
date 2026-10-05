from __future__ import annotations

import pytest

from intervention.models import Trigger


@pytest.mark.asyncio
async def test_manual_message_executes_at_next_consumed_boundary(
    runtime_factory, statement_factory
):
    runtime, store, calls = runtime_factory()
    store.enqueue(statement_factory())
    result = await runtime.before_round(9)
    assert [(x.effective_round, x.status) for x in result] == [(9, "published")]
    assert calls == [("iv1", 9)]


@pytest.mark.asyncio
async def test_two_statements_same_agent_both_publish(
    runtime_factory, statement_factory
):
    runtime, store, calls = runtime_factory()
    store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1", content="回应一"))
    store.enqueue(statement_factory(event_id="iv2", idempotency_key="k2", content="回应二"))
    result = await runtime.before_round(5)
    assert len(result) == 2
    assert calls == [("iv1", 5), ("iv2", 5)]


@pytest.mark.asyncio
async def test_scheduled_round_exact(runtime_factory, statement_factory):
    runtime, store, calls = runtime_factory()
    store.enqueue(
        statement_factory(
            event_id="iv1",
            idempotency_key="k1",
            trigger=Trigger(mode="scheduled", round=5),
        )
    )

    res4 = await runtime.before_round(4)
    assert calls == []
    assert len(res4) == 0

    res5 = await runtime.before_round(5)
    assert calls == [("iv1", 5)]
    assert [(x.effective_round, x.status) for x in res5] == [(5, "published")]


@pytest.mark.asyncio
async def test_missed_schedule_expires(runtime_factory, statement_factory):
    runtime, store, calls = runtime_factory()
    # Statement was scheduled for round 5, but simulation is already at round 6
    store.enqueue(
        statement_factory(
            event_id="iv1",
            idempotency_key="k1",
            trigger=Trigger(mode="scheduled", round=5),
        )
    )
    res6 = await runtime.before_round(6)
    assert calls == []
    state = store.read_execution("iv1")
    assert state.status == "expired"


@pytest.mark.asyncio
async def test_cancel_before_execute(runtime_factory, statement_factory):
    runtime, store, calls = runtime_factory()
    store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1"))
    store.request_cancel("iv1")

    await runtime.before_round(5)
    assert calls == []
    state = store.read_execution("iv1")
    assert state.status == "canceled"


@pytest.mark.asyncio
async def test_cancel_after_publish_preserves_post(
    runtime_factory, statement_factory
):
    runtime, store, calls = runtime_factory()
    store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1"))
    await runtime.before_round(5)
    assert calls == [("iv1", 5)]

    store.request_cancel("iv1")
    await runtime.before_round(6)
    state = store.read_execution("iv1")
    assert state.status == "published"


@pytest.mark.asyncio
async def test_unknown_not_retried(runtime_factory, statement_factory):
    runtime, store, calls = runtime_factory(fail_uncertain=True)
    store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1"))
    await runtime.before_round(5)

    state = store.read_execution("iv1")
    assert state.status == "unknown"
    assert len(calls) == 1

    # Next round should not retry
    await runtime.before_round(6)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_finish_expires_pending(runtime_factory, statement_factory):
    runtime, store, _ = runtime_factory()
    store.enqueue(
        statement_factory(
            event_id="iv1",
            idempotency_key="k1",
            trigger=Trigger(mode="scheduled", round=10),
        )
    )
    store.enqueue(
        statement_factory(
            event_id="iv2",
            idempotency_key="k2",
            trigger=Trigger(mode="scheduled", round=12),
        )
    )

    await runtime.finish(reason="completed")
    state1 = store.read_execution("iv1")
    assert state1.status == "expired"

    # In another run with stopped
    runtime2, store2, _ = runtime_factory()
    store2.enqueue(
        statement_factory(
            event_id="iv3",
            idempotency_key="k3",
            trigger=Trigger(mode="scheduled", round=10),
        )
    )
    await runtime2.finish(reason="stopped")
    state3 = store2.read_execution("iv3")
    assert state3.status == "canceled"


@pytest.mark.asyncio
async def test_cutoff_set_defers_mid_round_enqueue(runtime_factory, statement_factory):
    runtime, store, calls = runtime_factory()
    store.enqueue(statement_factory(event_id="iv1", idempotency_key="k1"))

    # During before_round execution, enqueue another statement
    orig_publish = runtime.publishers["twitter"].publish

    async def hooked_publish(stmt, *, round_num):
        # Enqueue mid-round
        store.enqueue(statement_factory(event_id="iv2", idempotency_key="k2", content="第二条"))
        return await orig_publish(stmt, round_num=round_num)

    runtime.publishers["twitter"].publish = hooked_publish

    result = await runtime.before_round(5)
    assert len(result) == 1
    assert calls == [("iv1", 5)]

    # Next round should execute the deferred statement
    result2 = await runtime.before_round(6)
    assert len(result2) == 1
    assert calls == [("iv1", 5), ("iv2", 6)]
