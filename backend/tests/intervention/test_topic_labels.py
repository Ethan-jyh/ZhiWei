from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intervention.metric_models import ActionRecord
from intervention.topic_labels import (
    TopicLabelStore,
    correct_label,
    label_actions,
    read_actions,
)


class TopicFixture:
    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.store = TopicLabelStore(tmp_path)
        self.parent = ActionRecord(
            run_id="run1",
            platform="twitter",
            trace_rowid=1,
            round_num=1,
            agent_id=12,
            action_type="CREATE_POST",
            content="学校回应声明",
            success=True,
            origin="intervention",
            intervention_id="iv1",
            topic_id="topic1",
            post_id="p1",
            parent_post_id=None,
        )
        self.comment = ActionRecord(
            run_id="run1",
            platform="twitter",
            trace_rowid=2,
            round_num=2,
            agent_id=13,
            action_type="CREATE_COMMENT",
            content="学生表示理解",
            success=True,
            origin="agent",
            intervention_id=None,
            topic_id=None,
            post_id="p2",
            parent_post_id="p1",
        )

    def classify_parent_and_comment(self):
        classifier = MagicMock(return_value=(False, "irrelevant"))
        return label_actions(
            [self.parent, self.comment],
            topic_id="topic1",
            topic_summary="学校事件讨论",
            classifier=classifier,
            version="v1",
            store=self.store,
        )


@pytest.fixture
def topic_fixture(tmp_path):
    return TopicFixture(tmp_path)


def test_comment_inherits_topic_not_intervention_origin(topic_fixture):
    labels = topic_fixture.classify_parent_and_comment()
    assert labels[1].related is True
    assert labels[1].source == "parent"
    assert topic_fixture.comment.origin == "agent"


def test_independent_post_uses_classifier(tmp_path):
    store = TopicLabelStore(tmp_path)
    post = ActionRecord(
        run_id="run1",
        platform="twitter",
        trace_rowid=1,
        round_num=1,
        agent_id=12,
        action_type="CREATE_POST",
        content="无关八卦",
        success=True,
        origin="agent",
        intervention_id=None,
        topic_id=None,
        post_id="p1",
        parent_post_id=None,
    )
    classifier = MagicMock(return_value=(False, "off topic"))
    labels = label_actions(
        [post],
        topic_id="topic1",
        topic_summary="学校事件",
        classifier=classifier,
        version="v1",
        store=store,
    )
    assert labels[0].related is False
    assert labels[0].source == "classifier"
    classifier.assert_called_once()


def test_classifier_exception_marks_pending(tmp_path):
    store = TopicLabelStore(tmp_path)
    post = ActionRecord(
        run_id="run1",
        platform="twitter",
        trace_rowid=1,
        round_num=1,
        agent_id=12,
        action_type="CREATE_POST",
        content="网络错误内容",
        success=True,
        origin="agent",
        intervention_id=None,
        topic_id=None,
        post_id="p1",
        parent_post_id=None,
    )

    def failing_classifier(content, summary):
        raise RuntimeError("API timeout")

    labels = label_actions(
        [post],
        topic_id="topic1",
        topic_summary="学校事件",
        classifier=failing_classifier,
        version="v1",
        store=store,
    )
    assert labels[0].related is None
    assert labels[0].source == "pending"


def test_manual_correction_overrides_classifier(tmp_path):
    store = TopicLabelStore(tmp_path)
    post = ActionRecord(
        run_id="run1",
        platform="twitter",
        trace_rowid=1,
        round_num=1,
        agent_id=12,
        action_type="CREATE_POST",
        content="分类器误判的内容",
        success=True,
        origin="agent",
        intervention_id=None,
        topic_id=None,
        post_id="p1",
        parent_post_id=None,
    )

    key = ("run1", "twitter", 1)
    correct_label(store, key, related=True, reason="人工复核确认为相关讨论")

    classifier = MagicMock(return_value=(False, "classifier said false"))
    labels = label_actions(
        [post],
        topic_id="topic1",
        topic_summary="学校事件",
        classifier=classifier,
        version="v1",
        store=store,
    )
    assert labels[0].related is True
    assert labels[0].source == "manual"
    classifier.assert_not_called()


def test_reads_over_10000_actions(tmp_path):
    import json

    twitter_dir = tmp_path / "twitter"
    twitter_dir.mkdir(parents=True)
    actions_file = twitter_dir / "actions.jsonl"

    total = 10005
    with open(actions_file, "w", encoding="utf-8") as f:
        for i in range(1, total + 1):
            line = {
                "round": 1,
                "timestamp": "2026-10-05T00:00:00",
                "agent_id": 1,
                "agent_name": "a1",
                "action_type": "CREATE_POST",
                "action_args": {"content": f"Post {i}", "post_id": f"p_{i}"},
                "success": True,
                "trace_rowid": i,
                "origin": "agent",
            }
            f.write(json.dumps(line) + "\n")

    snapshot = read_actions(tmp_path)
    assert len(snapshot.actions) == total
    assert snapshot.observed_round == 1
    assert snapshot.errors == []
