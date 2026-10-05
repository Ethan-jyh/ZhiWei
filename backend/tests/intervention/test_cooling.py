from __future__ import annotations

import pytest

from intervention.metric_models import HeatConfig, RoundHeat
from intervention.metrics import calculate_cooling


def make_heat(values: list[int | None]) -> list[RoundHeat]:
    rows = []
    for idx, v in enumerate(values, start=1):
        status = "complete" if v is not None else "missing"
        rows.append(
            RoundHeat(
                round_num=idx,
                platforms={"twitter": v},
                heat=v,
                posts=v or 0,
                comments=0,
                reposts=0,
                injected_posts_count=0,
                status=status,
            )
        )
    return rows


def test_cooling_uses_window_start_not_confirmation_round():
    rows = make_heat([1, 3, 8, 10, 20, 30, 18, 9, 5, 4, 3])
    cfg = HeatConfig(
        topic_id="topic1",
        threshold=5,
        consecutive_rounds=3,
        minutes_per_round=30,
        classifier_version="v1",
    )
    r = calculate_cooling(rows, cfg, finished=True)
    assert (r.peak_round, r.start_round, r.confirmed_round) == (6, 9, 11)
    assert (r.duration_rounds, r.duration_minutes) == (3, 90)
    assert r.status == "cooled"


def test_all_zero_is_no_discussion():
    rows = make_heat([0, 0, 0])
    cfg = HeatConfig(topic_id="t", threshold=5, consecutive_rounds=2, minutes_per_round=30, classifier_version="v1")
    r = calculate_cooling(rows, cfg, finished=True)
    assert r.status == "no_discussion"
    assert r.duration_rounds is None


def test_peak_below_or_equal_threshold():
    rows = make_heat([2, 5, 4])
    cfg = HeatConfig(topic_id="t", threshold=5, consecutive_rounds=2, minutes_per_round=30, classifier_version="v1")
    r = calculate_cooling(rows, cfg, finished=True)
    assert r.status == "below_threshold"
    assert r.peak_heat == 5
    assert r.duration_rounds is None


def test_unfinished_is_provisional():
    rows = make_heat([10, 20, 5, 4, 3])
    cfg = HeatConfig(topic_id="t", threshold=5, consecutive_rounds=3, minutes_per_round=30, classifier_version="v1")
    r = calculate_cooling(rows, cfg, finished=False)
    assert r.status == "provisional"
    assert r.peak_round == 2
    assert r.start_round == 3


def test_tied_peak_picks_first():
    rows = make_heat([10, 20, 20, 5, 4, 3])
    cfg = HeatConfig(topic_id="t", threshold=5, consecutive_rounds=3, minutes_per_round=30, classifier_version="v1")
    r = calculate_cooling(rows, cfg, finished=True)
    assert r.peak_round == 2  # first 20 at index 2


def test_rebound_recorded():
    # round 1: 30 (peak), round 2: 5, round 3: 4, round 4: 3 (cooled at round 2..4), round 5: 8 (rebound)
    rows = make_heat([30, 5, 4, 3, 8])
    cfg = HeatConfig(topic_id="t", threshold=5, consecutive_rounds=3, minutes_per_round=30, classifier_version="v1")
    r = calculate_cooling(rows, cfg, finished=True)
    assert r.status == "cooled"
    assert r.rebound_rounds == [5]


def test_missing_data_is_incomplete():
    rows = make_heat([10, None, 4])
    cfg = HeatConfig(topic_id="t", threshold=5, consecutive_rounds=2, minutes_per_round=30, classifier_version="v1")
    r = calculate_cooling(rows, cfg, finished=True)
    assert r.status == "incomplete"
    assert r.duration_rounds is None
