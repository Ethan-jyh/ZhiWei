"""Models for discussion heat metrics, topic labeling, and cooling duration analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from intervention.models import Platform

LabelSource = Literal["explicit", "parent", "classifier", "manual", "pending"]
RoundStatus = Literal["complete", "pending", "missing"]
CoolingStatus = Literal[
    "provisional",
    "cooled",
    "not_cooled",
    "no_discussion",
    "below_threshold",
    "incomplete",
]


class ActionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    platform: Platform
    trace_rowid: int
    round_num: int
    agent_id: int
    action_type: str
    content: str
    success: bool
    origin: str = "agent"
    intervention_id: str | None = None
    topic_id: str | None = None
    post_id: str | None = None
    parent_post_id: str | None = None


class ActionLogSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[ActionRecord]
    errors: list[str]
    fingerprint: str
    observed_round: int


class TopicLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: tuple[str, Platform, int]  # (run_id, platform, trace_rowid)
    topic_id: str
    related: bool | None
    source: LabelSource
    version: str
    reason: str


class HeatConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    threshold: int = Field(ge=0)
    consecutive_rounds: int = Field(ge=1)
    minutes_per_round: int = Field(ge=1)
    classifier_version: str


class RoundHeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_num: int
    platforms: dict[Platform, int | None]
    heat: int | None
    posts: int
    comments: int
    reposts: int
    injected_posts_count: int
    status: RoundStatus


class CoolingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CoolingStatus
    peak_round: int | None = None
    peak_heat: int | None = None
    start_round: int | None = None
    confirmed_round: int | None = None
    duration_rounds: int | None = None
    duration_minutes: int | None = None
    rebound_rounds: list[int] = Field(default_factory=list)


class MetricBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    config: HeatConfig
    rounds: list[RoundHeat]
    cooling: CoolingSummary
    final: bool
    revision: str
    errors: list[str] = Field(default_factory=list)
