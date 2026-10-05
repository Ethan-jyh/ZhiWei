from __future__ import annotations

import json
from pathlib import Path

import pytest

from intervention.experiment_models import (
    ComparisonResult,
    Experiment,
    ExperimentRun,
    FrozenScene,
    make_timing_variants,
)
from intervention.metric_models import CoolingSummary, HeatConfig, MetricBundle, RoundHeat
from intervention.models import Statement, Trigger
from app.services.intervention_experiment import (
    InterventionExperimentService,
    compatibility_hash,
)
from app.services.intervention_experiment_store import ExperimentStore


class ComparisonFixture:
    def __init__(self, tmp_path: Path):
        self.store = ExperimentStore(tmp_path / "experiments")
        self.service = InterventionExperimentService(
            store=self.store,
            simulation_manager=None,
            runner=None,
        )

        self.metric_config = HeatConfig(
            topic_id="topic_alpha",
            threshold=5,
            consecutive_rounds=2,
            minutes_per_round=30,
            classifier_version="v1",
        )

        self.scene = FrozenScene(
            scene_id="scene_comp",
            project_id="proj_1",
            topic_id="topic_alpha",
            t0_sources=[],
            config={"topic_id": "topic_alpha", "max_rounds": 10},
            profile_files={"twitter": "twitter_profiles.csv"},
            relationship_files={},
            agent_mapping={"twitter": {"SchoolAdmin": 10}},
            model_settings={"model": "gpt-4o"},
            metric_config=self.metric_config,
            sha256="abc123frozenhash",
        )

        stmt = Statement(
            event_id="s1",
            idempotency_key="k1",
            run_id="tmp",
            topic_id="topic_alpha",
            platform="twitter",
            publisher_agent_id=10,
            content="校方声明",
            kind="official_response",
            trigger=Trigger(mode="scheduled", round=3),
        )
        variants = make_timing_variants(stmt, early_round=3, late_round=6, total_rounds=10)
        self.experiment = Experiment(
            experiment_id="exp_comp",
            scene=self.scene,
            variants=variants,
            created_at="2026-10-05T12:00:00Z",
        )
        self.store.save(self.experiment)

        self.comp_hash = compatibility_hash(
            self.scene,
            runtime_model_config=self.scene.model_settings,
            metric_config=self.metric_config,
            enabled_platforms={"twitter"},
            total_rounds=10,
        )

        # Setup 3 runs: control, early, late
        self.runs = {
            "control": ExperimentRun(
                run_id="run_ctrl",
                simulation_id="run_ctrl",
                experiment_id="exp_comp",
                variant_id="control",
                replicate_id=1,
                seed=42,
                compatibility_hash=self.comp_hash,
                status="completed",
            ),
            "early": ExperimentRun(
                run_id="run_early",
                simulation_id="run_early",
                experiment_id="exp_comp",
                variant_id="early",
                replicate_id=1,
                seed=42,
                compatibility_hash=self.comp_hash,
                status="completed",
            ),
            "late": ExperimentRun(
                run_id="run_late",
                simulation_id="run_late",
                experiment_id="exp_comp",
                variant_id="late",
                replicate_id=1,
                seed=42,
                compatibility_hash=self.comp_hash,
                status="completed",
            ),
        }
        for r in self.runs.values():
            self.store.put_run(r)

        self.bundles: dict[str, MetricBundle] = {}
        for var_id, r in self.runs.items():
            self.bundles[r.run_id] = MetricBundle(
                run_id=r.run_id,
                config=self.metric_config,
                rounds=[RoundHeat(round_num=1, platforms={"twitter": 10}, heat=10, posts=10, comments=0, reposts=0, injected_posts_count=0, status="complete")],
                cooling=CoolingSummary(status="cooled", peak_round=1, peak_heat=10, duration_rounds=2, duration_minutes=60),
                final=True,
                revision="rev1",
            )

        self.statements = {
            "run_ctrl": [],
            "run_early": [{"event_id": "e1", "trigger": {"round": 3}}],
            "run_late": [{"event_id": "e2", "trigger": {"round": 6}}],
        }

    def change_metric_threshold(self, variant_id: str, new_threshold: int):
        run_id = self.runs[variant_id].run_id
        old_bundle = self.bundles[run_id]
        new_cfg = self.metric_config.model_copy(update={"threshold": new_threshold})
        self.bundles[run_id] = old_bundle.model_copy(update={"config": new_cfg})

    def compare(self) -> ComparisonResult:
        return self.service.compare(
            "exp_comp",
            metrics_provider=lambda r: self.bundles.get(r),
            statements_provider=lambda r: self.statements.get(r, []),
        )


@pytest.fixture
def comparison_fixture(tmp_path):
    return ComparisonFixture(tmp_path)


def test_compatible_runs_all_included_in_comparison(comparison_fixture):
    result = comparison_fixture.compare()
    assert len(result.runs) == 3
    assert len(result.incompatible_runs) == 0
    assert len(result.limitations) > 0


def test_different_threshold_not_silently_compared(comparison_fixture):
    comparison_fixture.change_metric_threshold("late", 7)
    result = comparison_fixture.compare()
    assert len(result.incompatible_runs) == 1
    assert result.incompatible_runs[0]["variant_id"] == "late"
    assert result.incompatible_runs[0]["reason"] == "metric_config_mismatch"


def test_extra_manual_statement_marks_run_exploratory(comparison_fixture):
    # Add extra statement to early run
    comparison_fixture.statements["run_early"].append(
        {"event_id": "manual_1", "origin": "manual", "content": "额外声明"}
    )
    result = comparison_fixture.compare()
    early_entry = next(r for r in result.runs if r["variant_id"] == "early")
    assert early_entry["exploratory"] is True
