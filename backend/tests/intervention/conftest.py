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
