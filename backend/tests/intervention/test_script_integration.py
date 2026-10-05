from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from intervention.coordinator import RoundCoordinator
from intervention.models import RunContext
from intervention.runtime import run_round_cycle


class CycleFixture:
    def __init__(self):
        self.events: list[str] = []
        self.fake_runtime = MagicMock()
        self.fake_runtime.before_round = self._before_round
        self.coordinator = RoundCoordinator({"twitter"}, self.fake_runtime)

    async def _before_round(self, round_num: int):
        self.events.append("before")
        return []

    async def run(self, active_count: int):
        async def act():
            if active_count > 0:
                self.events.append("act")

        async def record():
            self.events.append("record")

        # Hook after_round to record 'after' event
        orig_after = self.coordinator.after_round

        async def after_round(platform, round_num):
            self.events.append("after")
            await orig_after(platform, round_num)

        self.coordinator.after_round = after_round

        await run_round_cycle(
            platform="twitter",
            round_num=1,
            coordinator=self.coordinator,
            act=act,
            record=record,
        )


@pytest.fixture
def cycle_fixture():
    return CycleFixture()


@pytest.mark.asyncio
async def test_zero_active_round_still_has_boundary(cycle_fixture):
    await cycle_fixture.run(active_count=0)
    assert cycle_fixture.events == ["before", "record", "after"]


@pytest.mark.asyncio
async def test_active_round_executes_act(cycle_fixture):
    await cycle_fixture.run(active_count=5)
    assert cycle_fixture.events == ["before", "act", "record", "after"]


def test_get_intervention_context_from_runner(tmp_path):
    import json
    from app.services.simulation_runner import SimulationRunner

    sim_dir = tmp_path / "sim1"
    sim_dir.mkdir(parents=True)
    (sim_dir / "simulation_config.json").write_text(
        json.dumps({
            "topic_id": "school_1",
            "time_config": {"total_simulation_hours": 12},
            "max_rounds": 20,
        }),
        encoding="utf-8",
    )
    (sim_dir / "twitter_profiles.csv").write_text(
        "agent_id,name\n12,SchoolOfficial\n13,Parent\n",
        encoding="utf-8",
    )

    # Monkeypatch RUN_STATE_DIR
    original_state_dir = SimulationRunner.RUN_STATE_DIR
    SimulationRunner.RUN_STATE_DIR = str(tmp_path)
    try:
        ctx = SimulationRunner.get_intervention_context("sim1")
        assert ctx.run_id == "sim1"
        assert ctx.topic_id == "school_1"
        assert ctx.total_rounds == 20
        assert "twitter" in ctx.platforms
        assert ctx.agent_ids["twitter"] == {12, 13}
        assert ctx.phase == "prepared"
    finally:
        SimulationRunner.RUN_STATE_DIR = original_state_dir


def test_bundle_download_api():
    import io
    import zipfile
    from flask import Flask
    from app.api.simulation import simulation_bp

    app = Flask(__name__)
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    client = app.test_client()

    response = client.get("/api/simulation/script/bundle/download")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(response.data))
    names = zf.namelist()
    assert "run_parallel_simulation.py" in names
    assert "run_twitter_simulation.py" in names
    assert "run_reddit_simulation.py" in names
    assert "action_logger.py" in names
    assert "README.txt" in names
    assert any("intervention/models.py" in n for n in names)

