"""Aggregation of per-round discussion heat and platform completion evidence."""

from __future__ import annotations

import json
from pathlib import Path

from intervention.metric_models import (
    ActionRecord,
    CoolingSummary,
    HeatConfig,
    RoundHeat,
    TopicLabel,
)
from intervention.models import Platform


def read_round_completion(run_dir: Path | str) -> dict[Platform, set[int]]:
    """Determine completed rounds for each platform by inspecting round_end log events."""
    run_path = Path(run_dir)
    completion: dict[Platform, set[int]] = {"twitter": set(), "reddit": set()}

    for platform in ("twitter", "reddit"):
        log_file = run_path / platform / "actions.jsonl"
        if not log_file.exists():
            continue

        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                    if entry.get("event_type") == "round_end":
                        rnd = entry.get("round")
                        if rnd is not None:
                            completion[platform].add(int(rnd))  # type: ignore[index]
                except Exception:
                    pass

    return completion


def aggregate_heat(
    actions: list[ActionRecord],
    labels: list[TopicLabel],
    *,
    enabled_platforms: set[Platform],
    completed_rounds: dict[Platform, set[int]],
    total_rounds: int,
) -> list[RoundHeat]:
    """Aggregate per-round discussion heat with provenance, deduplication, and completion validation."""
    label_map = {lbl.key: lbl for lbl in labels}

    # Deduplicate actions by (run_id, platform, trace_rowid)
    seen_keys = set()
    deduped_actions: list[ActionRecord] = []
    for a in actions:
        key = (a.run_id, a.platform, a.trace_rowid)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped_actions.append(a)

    results: list[RoundHeat] = []

    for r in range(1, total_rounds + 1):
        round_actions = [
            a
            for a in deduped_actions
            if a.round_num == r and a.platform in enabled_platforms
        ]

        has_pending = False
        for a in round_actions:
            key = (a.run_id, a.platform, a.trace_rowid)
            lbl = label_map.get(key)
            if lbl is None or lbl.source == "pending" or lbl.related is None:
                has_pending = True
                break

        posts = 0
        comments = 0
        reposts = 0
        injected = 0
        platform_counts: dict[Platform, int | None] = {}

        for p in enabled_platforms:
            comp_rounds = completed_rounds.get(p, set())
            if r not in comp_rounds:
                platform_counts[p] = None
            else:
                p_heat = 0
                for a in round_actions:
                    if a.platform != p:
                        continue
                    key = (a.run_id, a.platform, a.trace_rowid)
                    lbl = label_map.get(key)
                    if not lbl or lbl.related is not True or not a.success:
                        continue

                    if a.action_type == "CREATE_POST":
                        if a.origin == "intervention":
                            injected += 1
                        else:
                            posts += 1
                            p_heat += 1
                    elif a.action_type == "CREATE_COMMENT":
                        comments += 1
                        p_heat += 1
                    elif a.action_type in ("REPOST", "QUOTE_POST"):
                        reposts += 1
                        p_heat += 1

                platform_counts[p] = p_heat

        is_missing = any(platform_counts[p] is None for p in enabled_platforms)

        if is_missing:
            status = "missing"
            heat = None
        elif has_pending:
            status = "pending"
            heat = None
        else:
            status = "complete"
            heat = sum(platform_counts[p] for p in enabled_platforms if platform_counts[p] is not None)

        results.append(
            RoundHeat(
                round_num=r,
                platforms=platform_counts,
                heat=heat,
                posts=posts,
                comments=comments,
                reposts=reposts,
                injected_posts_count=injected,
                status=status,
            )
        )

    return results


def calculate_cooling(
    rounds: list[RoundHeat],
    config: HeatConfig,
    *,
    finished: bool,
) -> CoolingSummary:
    """Calculate heat cooling window, duration, and post-confirmation rebounds."""
    if not rounds or any(r.status != "complete" or r.heat is None for r in rounds):
        return CoolingSummary(status="incomplete")

    heats = [r.heat for r in rounds]
    if all(h == 0 for h in heats):
        return CoolingSummary(status="no_discussion")

    max_heat = max(heats)
    peak_idx = heats.index(max_heat)
    peak_round = rounds[peak_idx].round_num

    if max_heat <= config.threshold:
        return CoolingSummary(
            status="below_threshold",
            peak_round=peak_round,
            peak_heat=max_heat,
        )

    w = config.consecutive_rounds
    n = len(rounds)
    start_round = None
    confirmed_round = None
    cooling_window_idx = None

    for i in range(peak_idx + 1, n - w + 1):
        if all(rounds[i + k].heat <= config.threshold for k in range(w)):
            cooling_window_idx = i
            start_round = rounds[i].round_num
            confirmed_round = rounds[i + w - 1].round_num
            break

    if cooling_window_idx is not None:
        duration_rounds = start_round - peak_round
        duration_minutes = duration_rounds * config.minutes_per_round

        rebound_rounds = [
            r.round_num
            for r in rounds[cooling_window_idx + w :]
            if r.heat is not None and r.heat > config.threshold
        ]

        status = "cooled" if finished else "provisional"
        return CoolingSummary(
            status=status,
            peak_round=peak_round,
            peak_heat=max_heat,
            start_round=start_round,
            confirmed_round=confirmed_round,
            duration_rounds=duration_rounds,
            duration_minutes=duration_minutes,
            rebound_rounds=rebound_rounds,
        )

    status = "not_cooled" if finished else "provisional"
    return CoolingSummary(
        status=status,
        peak_round=peak_round,
        peak_heat=max_heat,
        duration_rounds=None,
        duration_minutes=None,
        rebound_rounds=[],
    )

