from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

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
from app.services.simulation_manager import SimulationManager, SimulationStatus


class FakeRunner:
    def __init__(self):
        self.starts: list[str] = []

    def start_simulation(self, simulation_id: str):
        self.starts.append(simulation_id)
        return {"status": "started"}


class RunFixture:
    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.store = ExperimentStore(tmp_path / "experiments")
        self.manager = SimulationManager()
        self.manager.SIMULATION_DATA_DIR = str(tmp_path / "simulations")
        Path(self.manager.SIMULATION_DATA_DIR).mkdir(parents=True, exist_ok=True)
        self.runner = FakeRunner()
        self.service = InterventionExperimentService(
            store=self.store,
            simulation_manager=self.manager,
            runner=self.runner,
        )

        # Create source and freeze
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "simulation_config.json").write_text(
            json.dumps({"topic_id": "top1", "max_rounds": 20}), encoding="utf-8"
        )
        (source_dir / "twitter_profiles.csv").write_text(
            "agent_id,name\n1,Alpha\n", encoding="utf-8"
        )
        (source_dir / "reddit_profiles.json").write_text(
            json.dumps([{"agent_id": 2, "name": "Beta"}]), encoding="utf-8"
        )

        scene = FrozenScene(
            scene_id="scene1",
            project_id="proj1",
            topic_id="top1",
            t0_sources=[],
            config={"topic_id": "top1", "max_rounds": 20},
            profile_files={
                "twitter": "twitter_profiles.csv",
                "reddit": "reddit_profiles.json",
            },
            relationship_files={},
            agent_mapping={"twitter": {"Alpha": 1}},
            model_settings={"model": "gpt-4o"},
            metric_config=HeatConfig(
                topic_id="top1",
                threshold=5,
                consecutive_rounds=2,
                minutes_per_round=30,
                classifier_version="v1",
            ),
            sha256="",
        )
        self.frozen_scene = self.store.freeze(source_dir, scene=scene)

        stmt = Statement(
            event_id="s1",
            idempotency_key="k1",
            run_id="tmp",
            topic_id="top1",
            platform="twitter",
            publisher_agent_id=1,
            content="回应声明",
            kind="official_response",
            trigger=Trigger(mode="scheduled", round=5),
        )
        variants = make_timing_variants(stmt, early_round=5, late_round=15, total_rounds=20)
        self.experiment = Experiment(
            experiment_id="exp1",
            scene=self.frozen_scene,
            variants=variants,
            created_at="2026-10-05T12:00:00Z",
        )
        self.service.create(self.experiment)

    def create(self, variant_id: str, replicate_id: int = 1, seed: int = 42):
        return self.service.create_run(
            "exp1",
            variant_id,
            replicate_id=replicate_id,
            seed=seed,
            idempotency_key=f"idem_{variant_id}_{replicate_id}",
        )

    def profile_bytes(self, run) -> bytes:
        sim_dir = Path(self.manager._get_simulation_dir(run.simulation_id))
        return (sim_dir / "twitter_profiles.csv").read_bytes()

    def contains_prior_database(self, run) -> bool:
        sim_dir = Path(self.manager._get_simulation_dir(run.simulation_id))
        return (sim_dir / "twitter_simulation.db").exists() or (sim_dir / "twitter" / "actions.jsonl").exists()


@pytest.fixture
def run_fixture(tmp_path):
    return RunFixture(tmp_path)


def test_variants_have_separate_runtime_state(run_fixture):
    a = run_fixture.create("early", replicate_id=1)
    b = run_fixture.create("late", replicate_id=1)
    assert a.simulation_id != b.simulation_id
    assert run_fixture.profile_bytes(a) == run_fixture.profile_bytes(b)
    assert not run_fixture.contains_prior_database(a)
    assert not run_fixture.contains_prior_database(b)

    # Check statement plans are isolated and have respective scheduled rounds
    sim_a_dir = Path(run_fixture.manager._get_simulation_dir(a.simulation_id))
    sim_b_dir = Path(run_fixture.manager._get_simulation_dir(b.simulation_id))
    plan_a = json.loads((sim_a_dir / "interventions" / "initial_intervention_plan.json").read_text("utf-8"))
    plan_b = json.loads((sim_b_dir / "interventions" / "initial_intervention_plan.json").read_text("utf-8"))
    assert plan_a[0]["trigger"]["round"] == 5
    assert plan_b[0]["trigger"]["round"] == 15
    assert plan_a[0]["run_id"] == a.simulation_id
    assert plan_b[0]["run_id"] == b.simulation_id


def test_duplicate_reserve_returns_same_run(run_fixture):
    r1 = run_fixture.create("early", replicate_id=1)
    r2 = run_fixture.create("early", replicate_id=1)
    assert r1.run_id == r2.run_id
    assert len(run_fixture.store.list_runs("exp1")) == 1


def test_start_run_is_idempotent(run_fixture):
    run = run_fixture.create("early", replicate_id=1)
    started1 = run_fixture.service.start_run(run.run_id)
    assert started1.status == "running"
    assert run_fixture.runner.starts == [run.run_id]

    started2 = run_fixture.service.start_run(run.run_id)
    assert started2.status == "running"
    assert run_fixture.runner.starts == [run.run_id]  # not called twice
