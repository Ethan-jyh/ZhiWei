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
from intervention.models import InterventionError, Statement, Trigger
from app.services.intervention_experiment_store import ExperimentStore


class SceneFixture:
    def __init__(self, tmp_path: Path):
        self.source_dir = tmp_path / "source_sim"
        self.source_dir.mkdir(parents=True)
        self.config_data = {
            "topic_id": "topic_alpha",
            "topic": "学校突发事件",
            "time_config": {"total_simulation_hours": 24},
            "max_rounds": 20,
        }
        (self.source_dir / "simulation_config.json").write_text(
            json.dumps(self.config_data), encoding="utf-8"
        )
        (self.source_dir / "twitter_profiles.csv").write_text(
            "agent_id,name,role\n10,SchoolAdmin,official\n20,StudentA,observer\n",
            encoding="utf-8",
        )
        (self.source_dir / "reddit_profiles.json").write_text(
            json.dumps([{"agent_id": 101, "name": "RedditMod", "role": "admin"}]),
            encoding="utf-8",
        )
        (self.source_dir / "initial_follows.json").write_text(
            json.dumps({"10": ["20"]}), encoding="utf-8"
        )
        # Create unwhitelisted files to ensure they are NOT copied
        (self.source_dir / "twitter_simulation.db").write_text("old db", encoding="utf-8")
        twitter_dir = self.source_dir / "twitter"
        twitter_dir.mkdir()
        (twitter_dir / "actions.jsonl").write_text("old actions\n", encoding="utf-8")

        self.scene = FrozenScene(
            scene_id="scene_001",
            project_id="proj_1",
            topic_id="topic_alpha",
            t0_sources=[{"id": "s1", "title": "通知初版", "text": "校方通报"}],
            config=self.config_data,
            profile_files={
                "twitter": "twitter_profiles.csv",
                "reddit": "reddit_profiles.json",
            },
            relationship_files={"follows": "initial_follows.json"},
            agent_mapping={"twitter": {"SchoolAdmin": 10}},
            model_settings={"model": "gpt-4o", "temperature": 0.7},
            metric_config=HeatConfig(
                topic_id="topic_alpha",
                threshold=5,
                consecutive_rounds=3,
                minutes_per_round=30,
                classifier_version="v1",
            ),
            sha256="",
        )

    def change_original_profile(self):
        (self.source_dir / "twitter_profiles.csv").write_text(
            "agent_id,name,role\n10,ModifiedAdmin,official\n", encoding="utf-8"
        )


@pytest.fixture
def scene_fixture(tmp_path):
    return SceneFixture(tmp_path)


def test_source_edit_does_not_change_frozen_scene(tmp_path, scene_fixture):
    store = ExperimentStore(tmp_path / "experiments")
    frozen = store.freeze(scene_fixture.source_dir, scene=scene_fixture.scene)
    old_hash = frozen.sha256
    assert len(old_hash) == 64

    # Verify frozen directory does not have db or actions.jsonl
    frozen_dir = tmp_path / "experiments" / "scenes" / frozen.scene_id
    assert not (frozen_dir / "twitter_simulation.db").exists()
    assert not (frozen_dir / "twitter" / "actions.jsonl").exists()

    # Changing source files does not change frozen scene hash or verification
    scene_fixture.change_original_profile()
    assert store.verify_scene(frozen.scene_id) is None
    loaded_scene = store.get_scene(frozen.scene_id)
    assert loaded_scene.sha256 == old_hash


def test_tampered_frozen_scene_fails_verification(tmp_path, scene_fixture):
    store = ExperimentStore(tmp_path / "experiments")
    frozen = store.freeze(scene_fixture.source_dir, scene=scene_fixture.scene)

    # Tamper with frozen file
    frozen_file = tmp_path / "experiments" / "scenes" / frozen.scene_id / "twitter_profiles.csv"
    frozen_file.write_text("tampered content", encoding="utf-8")

    with pytest.raises(InterventionError) as exc_info:
        store.verify_scene(frozen.scene_id)
    assert exc_info.value.code == "scene_integrity_error"


def test_freeze_rejects_path_traversal(tmp_path, scene_fixture):
    store = ExperimentStore(tmp_path / "experiments")
    bad_scene = scene_fixture.scene.model_copy(
        update={"profile_files": {"twitter": "../escape.csv"}}
    )
    with pytest.raises(InterventionError) as exc:
        store.freeze(scene_fixture.source_dir, scene=bad_scene)
    assert exc.value.code == "path_traversal_forbidden"


def test_freeze_rejects_missing_profile_file(tmp_path, scene_fixture):
    store = ExperimentStore(tmp_path / "experiments")
    bad_scene = scene_fixture.scene.model_copy(
        update={"profile_files": {"twitter": "non_existent.csv"}}
    )
    with pytest.raises(InterventionError) as exc:
        store.freeze(scene_fixture.source_dir, scene=bad_scene)
    assert exc.value.code == "scene_file_missing"


def test_make_timing_variants_creates_constrained_triplet():
    stmt = Statement(
        event_id="stmt_tmpl",
        idempotency_key="key_tmpl",
        run_id="template_run",
        topic_id="topic_alpha",
        platform="twitter",
        publisher_agent_id=10,
        content="校方声明：已成立调查组",
        kind="official_response",
        trigger=Trigger(mode="scheduled", round=5),
    )
    variants = make_timing_variants(stmt, early_round=5, late_round=15, total_rounds=20)
    assert len(variants) == 3

    control, early, late = variants
    assert control.variant_id == "control"
    assert len(control.statements) == 0
    assert control.comparison_mode == "timing"

    assert early.variant_id == "early"
    assert len(early.statements) == 1
    assert early.statements[0].trigger.round == 5
    assert early.statements[0].content == stmt.content
    assert early.statements[0].publisher_agent_id == stmt.publisher_agent_id

    assert late.variant_id == "late"
    assert len(late.statements) == 1
    assert late.statements[0].trigger.round == 15
    assert late.statements[0].content == stmt.content
    assert late.statements[0].publisher_agent_id == stmt.publisher_agent_id


def test_make_timing_variants_rejects_invalid_rounds():
    stmt = Statement(
        event_id="stmt_tmpl",
        idempotency_key="key_tmpl",
        run_id="template_run",
        topic_id="topic_alpha",
        platform="twitter",
        publisher_agent_id=10,
        content="校方声明",
        kind="official_response",
        trigger=Trigger(mode="scheduled", round=5),
    )
    # late <= early rejected
    with pytest.raises(InterventionError) as exc:
        make_timing_variants(stmt, early_round=10, late_round=10, total_rounds=20)
    assert exc.value.code == "invalid_timing_window"

    # late > total_rounds rejected
    with pytest.raises(InterventionError) as exc2:
        make_timing_variants(stmt, early_round=5, late_round=25, total_rounds=20)
    assert exc2.value.code == "invalid_timing_window"
