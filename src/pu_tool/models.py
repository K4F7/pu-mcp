from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ScoreKind = Literal["credit", "academic_credit", "point", "unknown"]
PlanStatus = Literal["scheduled", "retrying", "running", "succeeded", "failed", "cancelled"]
AttemptStatus = Literal["pending", "retrying", "succeeded", "failed", "skipped"]


class AuthSession(BaseModel):
    token: str
    sid: str
    expires_at: datetime | None = None
    masked_user: str | None = None


class ScoreItem(BaseModel):
    kind: ScoreKind
    label: str
    value: str
    unit: str = ""
    source_field: str
    raw: Any | None = None


class Activity(BaseModel):
    activity_id: str
    title: str
    activity_type: str = "未知"
    start_time: datetime | None = None
    end_time: datetime | None = None
    signup_start_time: datetime | None = None
    signup_end_time: datetime | None = None
    location: str | None = None
    organizer: str | None = None
    status: str | None = None
    signed_in: bool = False
    credits: str | None = None
    score_items: list[ScoreItem] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class SignupPlan(BaseModel):
    plan_id: int | None = None
    activity_id: str
    activity_title: str
    run_at: datetime
    enabled: bool = True
    status: PlanStatus = "scheduled"
    max_attempts: int = 1
    attempt_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("max_attempts")
    @classmethod
    def validate_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_attempts must be at least 1")
        if value > 3:
            raise ValueError("max_attempts cannot exceed 3")
        return value


class SignupAttempt(BaseModel):
    attempt_id: int | None = None
    plan_id: int
    activity_id: str
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: AttemptStatus
    response_code: str | None = None
    message: str = ""
    risk_flag: bool = False
