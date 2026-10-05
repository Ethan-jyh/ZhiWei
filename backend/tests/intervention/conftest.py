"""Shared fixtures for intervention tests."""

from __future__ import annotations

import pytest

from intervention.models import Statement, Trigger


@pytest.fixture
def statement_factory():
    def _create(**kwargs) -> Statement:
        defaults = {
            "event_id": "iv1",
            "idempotency_key": "k1",
            "run_id": "run1",
            "topic_id": "topic1",
            "platform": "twitter",
            "publisher_agent_id": 12,
            "content": "学校回应",
            "trigger": Trigger(mode="next_round", round=None),
            "kind": "official_response",
            "submission_seq": 0,
        }
        defaults.update(kwargs)
        if isinstance(defaults["trigger"], dict):
            defaults["trigger"] = Trigger(**defaults["trigger"])
        return Statement(**defaults)

    return _create


class FakePublisher:
    def __init__(self, platform: str, calls: list[tuple[str, int]], fail_uncertain: bool = False):
        self.platform = platform
        self.calls = calls
        self.fail_uncertain = fail_uncertain

    async def publish(self, statement: Statement, *, round_num: int):
        self.calls.append((statement.event_id, round_num))
        if self.fail_uncertain:
            from intervention.models import PublishUncertain
            raise PublishUncertain("Fake uncertain result")
        from intervention.models import PublicationReceipt
        return PublicationReceipt(
            platform=self.platform,
            post_id=f"post_{statement.event_id}",
            trace_rowid=100,
            round_num=round_num,
        )

    async def reconcile(self, statement: Statement, *, round_num: int):
        return None


@pytest.fixture
def runtime_factory(tmp_path):
    def _create(fail_uncertain: bool = False):
        from intervention.models import RunContext
        from intervention.runtime import InterventionRuntime
        from intervention.storage import StatementStore

        store = StatementStore(tmp_path)
        calls: list[tuple[str, int]] = []
        publishers = {
            "twitter": FakePublisher("twitter", calls, fail_uncertain=fail_uncertain),
            "reddit": FakePublisher("reddit", calls, fail_uncertain=fail_uncertain),
        }
        context = RunContext(
            run_id="run1",
            phase="running",
            total_rounds=20,
            platforms={"twitter", "reddit"},
            agent_ids={"twitter": {12, 13}, "reddit": {14}},
            topic_id="topic1",
        )
        runtime = InterventionRuntime(store=store, publishers=publishers, context=context)
        return runtime, store, calls

    return _create
