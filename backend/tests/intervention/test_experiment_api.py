from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from app.api.intervention import create_intervention_blueprint
from app.services.intervention_experiment import InterventionExperimentService
from app.services.intervention_experiment_store import ExperimentStore
from app.services.intervention_service import InterventionService
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner


class FakeRunner:
    def __init__(self):
        self.runner_calls: list[str] = []

    def start_simulation(self, simulation_id: str):
        self.runner_calls.append(simulation_id)
        return {"status": "started"}


@pytest.fixture
def app_with_experiments(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True

    sim_root = tmp_path / "simulations"
    sim_root.mkdir(parents=True)
    exp_root = tmp_path / "experiments"
    exp_root.mkdir(parents=True)

    # Prepare a source simulation directory
    source_sim = sim_root / "src_sim_1"
    source_sim.mkdir()
    (source_sim / "simulation_config.json").write_text(
        json.dumps({
            "project_id": "proj_1",
            "topic_id": "topic_alpha",
            "topic": "学校突发事件讨论",
            "time_config": {"total_simulation_hours": 12},
            "max_rounds": 10,
        }),
        encoding="utf-8",
    )
    (source_sim / "twitter_profiles.csv").write_text(
        "agent_id,name\n10,SchoolOfficial\n",
        encoding="utf-8",
    )

    manager = SimulationManager()
    manager.SIMULATION_DATA_DIR = str(sim_root)

    runner = FakeRunner()
    store = ExperimentStore(exp_root)
    exp_service = InterventionExperimentService(
        store=store,
        simulation_manager=manager,
        runner=runner,
    )
    intervention_service = InterventionService(
        root=sim_root,
        context_provider=lambda r: SimulationRunner.get_intervention_context(r),
    )

    original_state_dir = SimulationRunner.RUN_STATE_DIR
    SimulationRunner.RUN_STATE_DIR = str(sim_root)

    bp = create_intervention_blueprint(
        service=intervention_service,
        experiment_service=exp_service,
    )
    app.register_blueprint(bp, url_prefix="/api/simulation")

    yield app, exp_service, runner, source_sim
    SimulationRunner.RUN_STATE_DIR = original_state_dir


@pytest.fixture
def client(app_with_experiments):
    app, _, _, _ = app_with_experiments
    return app.test_client()


def test_create_experiment_and_runs_flow(client, app_with_experiments):
    _, exp_service, runner, _ = app_with_experiments

    create_payload = {
        "source_simulation_id": "src_sim_1",
        "topic_id": "topic_alpha",
        "t0_sources": [{"id": "s1", "title": "通报初版", "text": "情况通报"}],
        "metric_config": {
            "topic_id": "topic_alpha",
            "threshold": 5,
            "consecutive_rounds": 2,
            "minutes_per_round": 30,
            "classifier_version": "v1",
        },
        "statement": {
            "event_id": "stmt_tmpl",
            "idempotency_key": "k_tmpl",
            "run_id": "src_sim_1",
            "topic_id": "topic_alpha",
            "platform": "twitter",
            "publisher_agent_id": 10,
            "content": "校方官方回应：成立调查小组",
            "kind": "official_response",
            "trigger": {"mode": "scheduled", "round": 3},
        },
        "early_round": 3,
        "late_round": 7,
    }

    # 1. Create experiment
    res = client.post("/api/simulation/experiments", json=create_payload)
    assert res.status_code == 201
    assert res.json["success"] is True
    exp_data = res.json["data"]
    exp_id = exp_data["experiment_id"]
    assert len(exp_data["variants"]) == 3

    # 2. Create runs for early variant
    run_payload = {
        "variant_id": "early",
        "replicate_id": 1,
        "seed": 100,
        "idempotency_key": "key_run_1",
    }
    run_res = client.post(f"/api/simulation/experiments/{exp_id}/runs", json=run_payload)
    assert run_res.status_code == 201
    assert run_res.json["success"] is True
    run_data = run_res.json["data"]
    run_id = run_data["run_id"]

    # 3. Repeating run creation returns 200/201 with same run_id
    run_res_dup = client.post(f"/api/simulation/experiments/{exp_id}/runs", json=run_payload)
    assert run_res_dup.status_code in (200, 201)
    assert run_res_dup.json["data"]["run_id"] == run_id

    # 4. Start run
    start_res = client.post(f"/api/simulation/experiments/{exp_id}/runs/{run_id}/start")
    assert start_res.status_code == 202
    assert runner.runner_calls == [run_id]

    # Start retry does not start twice
    start_res_2 = client.post(f"/api/simulation/experiments/{exp_id}/runs/{run_id}/start")
    assert start_res_2.status_code == 202
    assert runner.runner_calls == [run_id]

    # 5. Get comparison
    comp_res = client.get(f"/api/simulation/experiments/{exp_id}/comparison")
    assert comp_res.status_code == 200
    assert comp_res.json["success"] is True
    comp_data = comp_res.json["data"]
    assert comp_data["experiment_id"] == exp_id
    assert len(comp_data["runs"]) == 1
    assert len(comp_data["limitations"]) > 0
