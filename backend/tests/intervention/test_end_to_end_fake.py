from __future__ import annotations

import json
from pathlib import Path

import pytest

from intervention.experiment_models import (
    Experiment,
    FrozenScene,
    make_timing_variants,
)
from intervention.metric_models import HeatConfig
from intervention.models import Statement, Trigger
from app.services.intervention_experiment import (
    InterventionExperimentService,
    prepare_frozen_run,
)
from app.services.intervention_experiment_store import ExperimentStore
from app.services.intervention_metrics import InterventionMetricsService
from app.services.intervention_service import InterventionService
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner


class FakeRunner:
    def __init__(self):
        self.started = []

    def start_simulation(self, simulation_id: str):
        self.started.append(simulation_id)
        return {"status": "started"}


def test_full_fake_end_to_end_comparison(tmp_path):
    sim_root = tmp_path / "simulations"
    sim_root.mkdir()
    exp_root = tmp_path / "experiments"
    exp_root.mkdir()

    source_dir = sim_root / "source_sim"
    source_dir.mkdir()
    (source_dir / "simulation_config.json").write_text(
        json.dumps({
            "project_id": "proj_school",
            "topic_id": "topic_alpha",
            "topic": "校园突发事件讨论",
            "time_config": {"total_simulation_hours": 12},
            "max_rounds": 10,
        }),
        encoding="utf-8",
    )
    (source_dir / "twitter_profiles.csv").write_text(
        "agent_id,name\n10,SchoolOfficial\n20,StudentA\n", encoding="utf-8"
    )

    store = ExperimentStore(exp_root)
    manager = SimulationManager()
    manager.SIMULATION_DATA_DIR = str(sim_root)
    runner = FakeRunner()
    exp_service = InterventionExperimentService(
        store=store,
        simulation_manager=manager,
        runner=runner,
    )

    def simple_classifier(content: str, summary: str):
        if "声明" in content or "事件" in content:
            return True, "匹配事件"
        return False, "不相关"

    metrics_service = InterventionMetricsService(root=sim_root, classifier=simple_classifier)
    intervention_service = InterventionService(
        root=sim_root,
        context_provider=lambda r: SimulationRunner.get_intervention_context(r),
    )

    # 1. Freeze scene
    metric_cfg = HeatConfig(
        topic_id="topic_alpha",
        threshold=3,
        consecutive_rounds=2,
        minutes_per_round=30,
        classifier_version="v1",
    )
    scene = FrozenScene(
        scene_id="scene_e2e",
        project_id="proj_school",
        topic_id="topic_alpha",
        t0_sources=[{"id": "s1", "title": "通报"}],
        config={"topic_id": "topic_alpha", "max_rounds": 10},
        profile_files={"twitter": "twitter_profiles.csv"},
        relationship_files={},
        agent_mapping={"twitter": {"SchoolOfficial": 10}},
        model_settings={"model": "gpt-4o"},
        metric_config=metric_cfg,
        sha256="",
    )
    frozen_scene = store.freeze(source_dir, scene=scene)

    # 2. Create 3 timing variants
    stmt = Statement(
        event_id="stmt_1",
        idempotency_key="key_1",
        run_id="placeholder",
        topic_id="topic_alpha",
        platform="twitter",
        publisher_agent_id=10,
        content="校方调查通报声明",
        kind="official_response",
        trigger=Trigger(mode="scheduled", round=2),
    )
    variants = make_timing_variants(stmt, early_round=2, late_round=6, total_rounds=10)
    exp = Experiment(
        experiment_id="exp_e2e",
        scene=frozen_scene,
        variants=variants,
        created_at="2026-10-05T12:00:00Z",
    )
    exp_service.create(exp)

    # 3. Create runs for each variant
    runs = {}
    for v in ("control", "early", "late"):
        r = exp_service.create_run(
            "exp_e2e",
            v,
            replicate_id=1,
            seed=42,
            idempotency_key=f"e2e_{v}_1",
        )
        runs[v] = r

    # 4. Simulate execution by writing actions.jsonl into each run's directory
    for v, r in runs.items():
        r_dir = sim_root / r.simulation_id / "twitter"
        r_dir.mkdir(parents=True, exist_ok=True)
        with open(r_dir / "actions.jsonl", "w", encoding="utf-8") as f:
            # Round 1: high heat
            f.write(json.dumps({
                "round": 1,
                "agent_id": 20,
                "action_type": "CREATE_POST",
                "action_args": {"content": "校园事件讨论", "post_id": "p1"},
                "success": True,
                "origin": "agent",
            }) + "\n")
            f.write(json.dumps({"round": 1, "event_type": "round_end"}) + "\n")

            # Round 2: early statement or high heat
            if v == "early":
                f.write(json.dumps({
                    "round": 2,
                    "agent_id": 10,
                    "action_type": "CREATE_POST",
                    "action_args": {"content": "校方调查通报声明", "post_id": "p2"},
                    "success": True,
                    "origin": "intervention",
                }) + "\n")
            f.write(json.dumps({"round": 2, "event_type": "round_end"}) + "\n")

            # Round 3..10: lower heat
            for rnd in range(3, 11):
                f.write(json.dumps({"round": rnd, "event_type": "round_end"}) + "\n")

        # Compute metrics
        metrics_service.save_config(r.simulation_id, metric_cfg)
        metrics_service.compute(r.simulation_id, metric_cfg, finished=True)

    # 5. Run comparison
    comparison = exp_service.compare(
        "exp_e2e",
        metrics_provider=lambda rid: metrics_service.get(rid),
        statements_provider=lambda rid: intervention_service.list(rid),
    )

    assert comparison.experiment_id == "exp_e2e"
    assert len(comparison.runs) == 3
    assert len(comparison.incompatible_runs) == 0
    assert any("随机方差" in lim for lim in comparison.limitations)

    # Check heat curves
    early_entry = next(item for item in comparison.runs if item["variant_id"] == "early")
    assert early_entry["bundle"]["rounds"][0]["heat"] == 1
    assert early_entry["bundle"]["cooling"]["status"] in ("cooled", "provisional", "below_threshold")
