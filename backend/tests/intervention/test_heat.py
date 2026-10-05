from __future__ import annotations

import json
from pathlib import Path

import pytest

from intervention.metric_models import ActionRecord, TopicLabel
from intervention.metrics import aggregate_heat, read_round_completion


@pytest.fixture
def heat_fixture():
    actions = []
    labels = []

    # Round 5 actions on twitter
    # 8 agent posts
    for i in range(1, 9):
        actions.append(
            ActionRecord(
                run_id="run1", platform="twitter", trace_rowid=i, round_num=5,
                agent_id=i, action_type="CREATE_POST", content=f"Post {i}",
                success=True, origin="agent",
            )
        )
        labels.append(TopicLabel(key=("run1", "twitter", i), topic_id="t1", related=True, source="classifier", version="v1", reason="rel"))

    # 1 injected post
    actions.append(
        ActionRecord(
            run_id="run1", platform="twitter", trace_rowid=9, round_num=5,
            agent_id=99, action_type="CREATE_POST", content="Injected",
            success=True, origin="intervention",
        )
    )
    labels.append(TopicLabel(key=("run1", "twitter", 9), topic_id="t1", related=True, source="explicit", version="v1", reason="injected"))

    # 12 comments
    for i in range(10, 22):
        actions.append(
            ActionRecord(
                run_id="run1", platform="twitter", trace_rowid=i, round_num=5,
                agent_id=i, action_type="CREATE_COMMENT", content=f"Comment {i}",
                success=True, origin="agent",
            )
        )
        labels.append(TopicLabel(key=("run1", "twitter", i), topic_id="t1", related=True, source="parent", version="v1", reason="rel"))

    # 5 reposts
    for i in range(22, 27):
        actions.append(
            ActionRecord(
                run_id="run1", platform="twitter", trace_rowid=i, round_num=5,
                agent_id=i, action_type="REPOST", content=f"Repost {i}",
                success=True, origin="agent",
            )
        )
        labels.append(TopicLabel(key=("run1", "twitter", i), topic_id="t1", related=True, source="parent", version="v1", reason="rel"))

    # 1 like (should not count)
    actions.append(
        ActionRecord(
            run_id="run1", platform="twitter", trace_rowid=27, round_num=5,
            agent_id=30, action_type="LIKE_POST", content="like",
            success=True, origin="agent",
        )
    )
    labels.append(TopicLabel(key=("run1", "twitter", 27), topic_id="t1", related=True, source="parent", version="v1", reason="rel"))

    # 1 unrelated post (should not count)
    actions.append(
        ActionRecord(
            run_id="run1", platform="twitter", trace_rowid=28, round_num=5,
            agent_id=31, action_type="CREATE_POST", content="unrelated",
            success=True, origin="agent",
        )
    )
    labels.append(TopicLabel(key=("run1", "twitter", 28), topic_id="t1", related=False, source="classifier", version="v1", reason="not rel"))

    # 1 failed post (should not count)
    actions.append(
        ActionRecord(
            run_id="run1", platform="twitter", trace_rowid=29, round_num=5,
            agent_id=32, action_type="CREATE_POST", content="failed",
            success=False, origin="agent",
        )
    )
    labels.append(TopicLabel(key=("run1", "twitter", 29), topic_id="t1", related=True, source="classifier", version="v1", reason="rel"))

    # 2 duplicate actions (same trace_rowid 1 and 2, should be deduped)
    actions.append(actions[0])
    actions.append(actions[1])

    completed_rounds = {"twitter": {1, 2, 3, 4, 5}}
    return {
        "actions": actions,
        "labels": labels,
        "enabled_platforms": {"twitter"},
        "completed_rounds": completed_rounds,
        "total_rounds": 5,
    }


def test_counts_only_successful_related_agent_expression(heat_fixture):
    rows = aggregate_heat(**heat_fixture)
    r = rows[4]  # Round 5 (0-indexed)
    assert (r.posts, r.comments, r.reposts, r.heat) == (8, 12, 5, 25)
    assert r.injected_posts_count == 1


def test_completed_empty_round_is_zero():
    rows = aggregate_heat(
        actions=[],
        labels=[],
        enabled_platforms={"twitter"},
        completed_rounds={"twitter": {1, 2}},
        total_rounds=2,
    )
    assert rows[0].heat == 0
    assert rows[0].status == "complete"
    assert rows[1].heat == 0


def test_incomplete_round_is_null():
    rows = aggregate_heat(
        actions=[],
        labels=[],
        enabled_platforms={"twitter"},
        completed_rounds={"twitter": {1}},  # round 2 not completed
        total_rounds=2,
    )
    assert rows[0].heat == 0
    assert rows[1].heat is None
    assert rows[1].status == "missing"


def test_missing_platform_leaves_total_heat_null():
    # twitter completed round 1, reddit did not
    rows = aggregate_heat(
        actions=[],
        labels=[],
        enabled_platforms={"twitter", "reddit"},
        completed_rounds={"twitter": {1}, "reddit": set()},
        total_rounds=1,
    )
    assert rows[0].platforms["twitter"] == 0
    assert rows[0].platforms["reddit"] is None
    assert rows[0].heat is None
    assert rows[0].status == "missing"


def test_round_zero_is_excluded():
    act = ActionRecord(
        run_id="run1", platform="twitter", trace_rowid=1, round_num=0,
        agent_id=1, action_type="CREATE_POST", content="T0",
        success=True, origin="agent",
    )
    lbl = TopicLabel(key=("run1", "twitter", 1), topic_id="t1", related=True, source="explicit", version="v1", reason="t0")
    rows = aggregate_heat(
        actions=[act],
        labels=[lbl],
        enabled_platforms={"twitter"},
        completed_rounds={"twitter": {1}},
        total_rounds=1,
    )
    assert rows[0].heat == 0


def test_read_round_completion_from_logs(tmp_path):
    twitter_dir = tmp_path / "twitter"
    twitter_dir.mkdir(parents=True)
    with open(twitter_dir / "actions.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"round": 1, "event_type": "round_end", "actions_count": 5}) + "\n")
        f.write(json.dumps({"round": 2, "event_type": "round_end", "actions_count": 3}) + "\n")

    completed = read_round_completion(tmp_path)
    assert completed["twitter"] == {1, 2}
    assert completed["reddit"] == set()


def test_aggregation_handles_10001_actions():
    actions = []
    labels = []
    total = 10001
    for i in range(1, total + 1):
        actions.append(
            ActionRecord(
                run_id="run1", platform="twitter", trace_rowid=i, round_num=1,
                agent_id=i, action_type="CREATE_POST", content=f"P {i}",
                success=True, origin="agent",
            )
        )
        labels.append(TopicLabel(key=("run1", "twitter", i), topic_id="t1", related=True, source="explicit", version="v1", reason="ok"))

    rows = aggregate_heat(
        actions=actions,
        labels=labels,
        enabled_platforms={"twitter"},
        completed_rounds={"twitter": {1}},
        total_rounds=1,
    )
    assert rows[0].heat == total
    assert rows[0].posts == total
