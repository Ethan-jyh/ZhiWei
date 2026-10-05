from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from app.api.intervention import create_intervention_blueprint
from app.services.intervention_metrics import InterventionMetricsService
from app.services.intervention_service import InterventionService
from app.services.simulation_runner import SimulationRunner
from intervention.metric_models import HeatConfig
from intervention.models import RunContext


@pytest.fixture
def run_dir(tmp_path):
    sim_dir = tmp_path / "simulations" / "run1"
    sim_dir.mkdir(parents=True)
    (sim_dir / "simulation_config.json").write_text(
        json.dumps({
            "topic_id": "topic1",
            "topic": "学校事件讨论",
            "time_config": {"total_simulation_hours": 12},
            "max_rounds": 10,
        }),
        encoding="utf-8",
    )
    (sim_dir / "twitter_profiles.csv").write_text(
        "agent_id,name\n12,SchoolOfficial\n",
        encoding="utf-8",
    )
    # Write actions and round_end
    twitter_dir = sim_dir / "twitter"
    twitter_dir.mkdir()
    with open(twitter_dir / "actions.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "round": 1,
            "agent_id": 12,
            "action_type": "CREATE_POST",
            "action_args": {"content": "学校官方声明", "post_id": "p1"},
            "success": True,
            "trace_rowid": 1,
            "origin": "agent",
        }) + "\n")
        f.write(json.dumps({
            "round": 1,
            "event_type": "round_end",
            "actions_count": 1,
        }) + "\n")
    return sim_dir


@pytest.fixture
def app_with_metrics(tmp_path, run_dir):
    app = Flask(__name__)
    app.config["TESTING"] = True

    sim_root = tmp_path / "simulations"

    def classifier(content, summary):
        if "声明" in content:
            return True, "匹配声明"
        return False, "不相关"

    metrics_service = InterventionMetricsService(root=sim_root, classifier=classifier)
    intervention_service = InterventionService(
        root=sim_root,
        context_provider=lambda r: SimulationRunner.get_intervention_context(r),
    )

    # Monkeypatch SimulationRunner RUN_STATE_DIR
    original_state_dir = SimulationRunner.RUN_STATE_DIR
    SimulationRunner.RUN_STATE_DIR = str(sim_root)

    bp = create_intervention_blueprint(
        service=intervention_service,
        metrics_service=metrics_service,
    )
    app.register_blueprint(bp, url_prefix="/api/simulation")

    yield app, metrics_service, intervention_service
    SimulationRunner.RUN_STATE_DIR = original_state_dir


@pytest.fixture
def client(app_with_metrics):
    app, _, _ = app_with_metrics
    return app.test_client()


def test_metrics_not_configured_initially(client):
    res = client.get("/api/simulation/run1/intervention-metrics")
    assert res.status_code == 200
    assert res.json["data"]["status"] == "not_configured"


def test_save_metric_config_computes_bundle(client):
    cfg_payload = {
        "topic_id": "topic1",
        "threshold": 5,
        "consecutive_rounds": 2,
        "minutes_per_round": 30,
        "classifier_version": "v1",
    }
    put_res = client.put("/api/simulation/run1/intervention-metric-config", json=cfg_payload)
    assert put_res.status_code == 200
    assert put_res.json["success"] is True
    data = put_res.json["data"]
    assert data["run_id"] == "run1"
    assert len(data["rounds"]) >= 1
    assert data["rounds"][0]["heat"] == 1

    # Next GET returns the computed bundle
    get_res = client.get("/api/simulation/run1/intervention-metrics")
    assert get_res.status_code == 200
    assert get_res.json["data"]["run_id"] == "run1"


def test_manual_correction_recomputes_and_changes_revision(client):
    cfg_payload = {
        "topic_id": "topic1",
        "threshold": 5,
        "consecutive_rounds": 2,
        "minutes_per_round": 30,
        "classifier_version": "v1",
    }
    client.put("/api/simulation/run1/intervention-metric-config", json=cfg_payload)
    bundle_before = client.get("/api/simulation/run1/intervention-metrics").json["data"]
    rev_before = bundle_before["revision"]
    assert bundle_before["rounds"][0]["heat"] == 1

    # Correct label to false (unrelated)
    correct_res = client.post(
        "/api/simulation/run1/intervention-labels/correct",
        json={
            "platform": "twitter",
            "trace_rowid": 1,
            "related": False,
            "reason": "人工核实误判",
        },
    )
    assert correct_res.status_code == 200
    bundle_after = client.get("/api/simulation/run1/intervention-metrics").json["data"]
    assert bundle_after["revision"] != rev_before
    assert bundle_after["rounds"][0]["heat"] == 0


def test_report_agent_intervention_summary_tool_enforces_own_simulation_id(tmp_path, run_dir, app_with_metrics):
    from unittest.mock import MagicMock
    from app.services.report_agent import ReportAgent

    _, metrics_service, _ = app_with_metrics

    # Configure run1
    cfg = HeatConfig(
        topic_id="topic1",
        threshold=5,
        consecutive_rounds=2,
        minutes_per_round=30,
        classifier_version="v1",
    )
    metrics_service.save_config("run1", cfg)
    metrics_service.compute("run1", cfg, finished=True)

    agent = ReportAgent(
        graph_id="graph1",
        simulation_id="run1",
        simulation_requirement="学校事件讨论",
        llm_client=MagicMock(),
        zep_tools=MagicMock(),
    )
    agent.metrics_service = metrics_service

    # When tool is called with an attempted override "other_run", it must still return data for run1
    out = agent._execute_tool("intervention_summary", {"simulation_id": "other_run"})
    assert "topic1" in out
    assert "run1" in out or "指标" in out
    assert "满意度" in out  # contains disclaimer that heat is not satisfaction
