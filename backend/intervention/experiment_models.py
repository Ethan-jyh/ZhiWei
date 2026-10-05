"""Data models and variant constructors for intervention scenario experiments."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from intervention.metric_models import HeatConfig
from intervention.models import InterventionError, Statement, Trigger


class FrozenScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    project_id: str
    topic_id: str
    t0_sources: list[dict[str, Any]]
    config: dict[str, Any]
    profile_files: dict[str, str]
    relationship_files: dict[str, str]
    agent_mapping: dict[str, dict[str, int]]
    model_settings: dict[str, Any]
    metric_config: HeatConfig
    sha256: str = ""

    def canonical_dict(self) -> dict[str, Any]:
        """Return dict representation excluding sha256 for deterministic hashing."""
        data = self.model_dump(mode="json")
        data.pop("sha256", None)
        return data


class InterventionVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str
    name: str
    statements: list[Statement]
    comparison_mode: Literal["timing", "content", "exploratory"]


class Experiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    scene: FrozenScene
    variants: list[InterventionVariant]
    created_at: str


class ExperimentRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    simulation_id: str
    experiment_id: str
    variant_id: str
    replicate_id: int
    seed: int
    compatibility_hash: str
    status: str
    exploratory: bool = False
    error: str | None = None


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    runs: list[dict[str, Any]]
    incompatible_runs: list[dict[str, Any]]
    limitations: list[str] = Field(default_factory=list)


def make_timing_variants(
    statement: Statement,
    *,
    early_round: int,
    late_round: int,
    total_rounds: int,
) -> list[InterventionVariant]:
    """Create the 3-variant comparison set (control, early, late) with timing constraints."""
    if not (1 <= early_round < late_round <= total_rounds):
        raise InterventionError(
            code="invalid_timing_window",
            message=f"Timing window requirement not met: 1 <= early ({early_round}) < late ({late_round}) <= total ({total_rounds})",
        )

    # 1. Control variant (no intervention)
    control = InterventionVariant(
        variant_id="control",
        name="不干预 (对照组)",
        statements=[],
        comparison_mode="timing",
    )

    # 2. Early intervention variant
    early_stmt = statement.model_copy(
        deep=True,
        update={
            "trigger": Trigger(mode="scheduled", round=early_round),
        },
    )
    early = InterventionVariant(
        variant_id="early",
        name="早回应 (第5轮)",
        statements=[early_stmt],
        comparison_mode="timing",
    )

    # 3. Late intervention variant
    late_stmt = statement.model_copy(
        deep=True,
        update={
            "trigger": Trigger(mode="scheduled", round=late_round),
        },
    )
    late = InterventionVariant(
        variant_id="late",
        name="晚回应 (第15轮)",
        statements=[late_stmt],
        comparison_mode="timing",
    )

    return [control, early, late]
