from __future__ import annotations

from pathlib import Path

import pytest
from flask import Flask

from app.api.intervention import create_intervention_blueprint
from app.services.intervention_service import InterventionService
from intervention.models import RunContext


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "simulations" / "run1"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def api_payload():
    return {
        "idempotency_key": "k1",
        "topic_id": "topic1",
        "platform": "twitter",
        "publisher_agent_id": 12,
        "content": "学校回应",
        "trigger": {"mode": "next_round"},
        "kind": "official_response",
    }


@pytest.fixture
def app_with_service(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True

    sim_root = tmp_path / "simulations"
    sim_root.mkdir(parents=True, exist_ok=True)

    def context_provider(run_id: str) -> RunContext:
        if run_id == "interview_run":
            return RunContext(
                run_id=run_id,
                phase="interview",
                total_rounds=10,
                platforms={"twitter"},
                agent_ids={"twitter": {12}},
                topic_id="topic1",
            )
        if run_id != "run1":
            raise FileNotFoundError(f"Run {run_id} not found")
        return RunContext(
            run_id="run1",
            phase="running",
            total_rounds=10,
            platforms={"twitter"},
            agent_ids={"twitter": {12}},
            topic_id="topic1",
        )

    service = InterventionService(root=sim_root, context_provider=context_provider)
    bp = create_intervention_blueprint(service)
    app.register_blueprint(bp, url_prefix="/api/simulation")

    return app, service


@pytest.fixture
def client(app_with_service, run_dir):
    app, _ = app_with_service
    return app.test_client()


def test_submit_returns_202_queued(client, api_payload):
    res = client.post("/api/simulation/run1/interventions", json=api_payload)
    assert res.status_code == 202
    assert res.json["success"] is True
    assert res.json["data"]["execution"]["status"] == "queued"
    assert res.json["data"]["statement"]["event_id"]


def test_retry_returns_same_event(client, api_payload):
    res1 = client.post("/api/simulation/run1/interventions", json=api_payload)
    res2 = client.post("/api/simulation/run1/interventions", json=api_payload)
    assert res1.status_code == 202
    assert res2.status_code == 202
    assert res1.json["data"]["statement"]["event_id"] == res2.json["data"]["statement"]["event_id"]


def test_unknown_run_is_404(client, api_payload):
    res = client.post("/api/simulation/unknown_run/interventions", json=api_payload)
    assert res.status_code == 404
    assert res.json["success"] is False


def test_interview_phase_is_409(client, api_payload, tmp_path):
    (tmp_path / "simulations" / "interview_run").mkdir(parents=True, exist_ok=True)
    res = client.post("/api/simulation/interview_run/interventions", json=api_payload)
    assert res.status_code == 409
    assert res.json["success"] is False
    assert res.json["code"] == "run_not_accepting"


def test_unknown_role_is_400(client, api_payload):
    payload = dict(api_payload)
    payload["publisher_agent_id"] = 999
    res = client.post("/api/simulation/run1/interventions", json=payload)
    assert res.status_code == 400
    assert res.json["success"] is False
    assert res.json["code"] == "invalid_publisher"


def test_local_length_policy_is_400(client, api_payload):
    payload = dict(api_payload)
    payload["content"] = "a" * 20001
    res = client.post("/api/simulation/run1/interventions", json=payload)
    assert res.status_code == 400
    assert res.json["success"] is False


def test_cancel_is_request_not_published_deletion(client, api_payload):
    res = client.post("/api/simulation/run1/interventions", json=api_payload)
    event_id = res.json["data"]["statement"]["event_id"]

    cancel_res = client.post(f"/api/simulation/run1/interventions/{event_id}/cancel")
    assert cancel_res.status_code == 202
    assert cancel_res.json["success"] is True

    list_res = client.get("/api/simulation/run1/interventions")
    assert list_res.status_code == 200
    items = list_res.json["data"]
    assert len(items) == 1
    assert items[0]["statement"]["event_id"] == event_id
