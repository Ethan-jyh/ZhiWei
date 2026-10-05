"""Models and validation for runtime statement intervention."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Platform = Literal["twitter", "reddit"]
Phase = Literal["prepared", "running", "interview", "stopped", "completed", "failed"]
TriggerMode = Literal["scheduled", "next_round"]
StatementKind = Literal["official_response", "fact_check", "rumor_rebuttal", "custom"]
ExecutionStatus = Literal[
    "queued",
    "accepted",
    "executing",
    "published",
    "failed",
    "canceled",
    "expired",
    "unknown",
]

INTERVENTION_MAX_CONTENT_CHARS = 20000
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class InterventionError(Exception):
    """Base error for intervention domain."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class PublishUncertain(InterventionError):
    """Raised when publication result is uncertain and requires reconciliation."""

    def __init__(self, message: str = "Publication result is uncertain") -> None:
        super().__init__("publish_uncertain", message)


class Trigger(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: TriggerMode
    round: int | None = None

    @field_validator("round", mode="before")
    @classmethod
    def validate_round_type(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("round cannot be a boolean")
        return v

    @model_validator(mode="after")
    def validate_trigger(self) -> Trigger:
        if self.mode == "scheduled":
            if self.round is None or self.round < 1:
                raise ValueError("scheduled mode requires round >= 1")
        elif self.mode == "next_round":
            if self.round is not None:
                raise ValueError("next_round mode requires round to be None")
        return self


def _validate_id(val: str, field_name: str) -> str:
    if not isinstance(val, str) or not ID_PATTERN.match(val):
        raise ValueError(
            f"Invalid {field_name}: must match ^[A-Za-z0-9_-]{{1,128}}$ and not contain paths"
        )
    return val


class Statement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    event_id: str
    idempotency_key: str
    run_id: str
    topic_id: str
    platform: Platform
    publisher_agent_id: int
    content: str
    trigger: Trigger
    kind: StatementKind
    publisher_person_id: str | None = None
    statement_group_id: str | None = None
    submission_seq: int = 0

    @field_validator("publisher_agent_id", mode="before")
    @classmethod
    def validate_publisher_agent_id(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("publisher_agent_id cannot be a boolean")
        if not isinstance(v, int):
            raise ValueError("publisher_agent_id must be an integer")
        return v

    @field_validator("event_id", "idempotency_key", "run_id", "topic_id")
    @classmethod
    def validate_required_ids(cls, v: str, info: Any) -> str:
        return _validate_id(v, info.field_name)

    @field_validator("publisher_person_id", "statement_group_id")
    @classmethod
    def validate_optional_ids(cls, v: str | None, info: Any) -> str | None:
        if v is not None:
            return _validate_id(v, info.field_name)
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("content must be a string")
        if not v.strip():
            raise ValueError("content must contain non-whitespace characters")
        if len(v) > INTERVENTION_MAX_CONTENT_CHARS:
            raise ValueError(
                f"content exceeds maximum policy of {INTERVENTION_MAX_CONTENT_CHARS} characters"
            )
        return v


class RunContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    phase: Phase
    total_rounds: int
    platforms: set[Platform]
    agent_ids: dict[Platform, set[int]]
    topic_id: str


class PublicationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    platform: Platform
    post_id: str
    trace_rowid: int
    round_num: int


class Execution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    status: ExecutionStatus
    accepted_round: int | None = None
    effective_round: int | None = None
    receipt: PublicationReceipt | None = None
    error: str | None = None


def validate_statement(statement: Statement, context: RunContext) -> None:
    """Validate that statement conforms to the current run context."""
    if statement.run_id != context.run_id:
        raise InterventionError(
            "run_mismatch",
            f"Statement run_id '{statement.run_id}' does not match context run_id '{context.run_id}'",
        )

    if statement.topic_id != context.topic_id:
        raise InterventionError(
            "topic_mismatch",
            f"Statement topic_id '{statement.topic_id}' does not match context topic_id '{context.topic_id}'",
        )

    if statement.platform not in context.platforms:
        raise InterventionError(
            "platform_not_supported",
            f"Platform '{statement.platform}' is not supported in this run",
        )

    platform_agents = context.agent_ids.get(statement.platform, set())
    if statement.publisher_agent_id not in platform_agents:
        raise InterventionError(
            "invalid_publisher",
            f"Agent id {statement.publisher_agent_id} does not exist on platform '{statement.platform}'",
        )

    if context.phase == "prepared":
        if statement.trigger.mode != "scheduled":
            raise InterventionError(
                "invalid_trigger_for_phase",
                "Prepared runs only accept scheduled triggers",
            )
        if (
            statement.trigger.round is not None
            and statement.trigger.round > context.total_rounds
        ):
            raise InterventionError(
                "round_out_of_range",
                f"Scheduled round {statement.trigger.round} exceeds total rounds {context.total_rounds}",
            )
    elif context.phase == "running":
        if statement.trigger.mode != "next_round":
            raise InterventionError(
                "invalid_trigger_for_phase",
                "Running simulations only accept next_round triggers",
            )
    else:
        raise InterventionError(
            "run_not_accepting",
            f"Simulation in phase '{context.phase}' does not accept interventions",
        )
