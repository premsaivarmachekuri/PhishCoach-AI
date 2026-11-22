from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EventType = Literal["opened", "clicked", "replied", "submitted", "reported", "ignored"]
# Types an employee's own browser may report. 'ignored'/'replied' come only from the sim platform webhook.
EmployeeEventType = Literal["opened", "clicked", "submitted", "reported"]
CoachAction = Literal["clicked", "submitted", "reported", "ignored"]
ChatOutcome = Literal["completed", "detected", "fell_for_it", "turn_cap", "abandoned"]


class CampaignBrief(BaseModel):
    theme: str = Field(..., min_length=3, max_length=200)
    department: str = Field(..., min_length=2, max_length=100)
    role_name: str = Field(default="all", max_length=100)
    difficulty: int = Field(default=1, ge=1, le=3)
    wave_no: int = Field(default=1, ge=1, le=20)
    notes: str = Field(default="", max_length=500)
    target_user_ids: list[str] | None = None


class GeneratedEmailJSON(BaseModel):
    sender_name: str = Field(..., min_length=2, max_length=100)
    sender_email: str = Field(..., min_length=5, max_length=150)
    subject: str = Field(..., min_length=3, max_length=200)
    body: str = Field(..., min_length=20, max_length=3000)
    link_label: str = Field(..., min_length=2, max_length=120)
    link_url: str = Field(..., min_length=10, max_length=300)
    planted_flags: list[str] = Field(..., min_length=1)

    @field_validator("sender_email")
    @classmethod
    def check_reserved_sender_domain(cls, v: str) -> str:
        lower = v.lower().strip()
        if "@" not in lower:
            raise ValueError("sender_email must contain @")
        domain = lower.split("@", 1)[1]
        if not (
            domain.endswith(".invalid")
            or domain.endswith(".test")
            or domain == "example.com"
            or domain.endswith(".example.com")
        ):
            raise ValueError(
                f"sender_email domain '{domain}' must be a reserved domain (.invalid, .test, example.com)"
            )
        return v

    @field_validator("link_url")
    @classmethod
    def check_reserved_link_domain(cls, v: str) -> str:
        lower = v.lower().strip()
        if not (lower.startswith("https://") or lower.startswith("http://")):
            raise ValueError("link_url must start with http:// or https://")
        host = lower.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        if not (
            host.endswith(".invalid")
            or host.endswith(".test")
            or host == "example.com"
            or host.endswith(".example.com")
        ):
            raise ValueError(
                f"link_url host '{host}' must use a reserved domain (.invalid, .test, example.com)"
            )
        return v


class TemplatePatch(BaseModel):
    email_json: GeneratedEmailJSON
    planted_flags: list[str] | None = None


class EventCreate(BaseModel):
    simulation_id: str
    type: EmployeeEventType


class ChatSessionCreate(BaseModel):
    simulation_id: str | None = None
    scenario_topic: str | None = Field(default=None, max_length=200)


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class ConfigUpdate(BaseModel):
    value_json: dict[str, Any]


class PublicUser(BaseModel):
    """What the browser may know about the signed-in user (no internal auth ids)."""

    id: str
    anon_id: str
    role_name: str
    department: str
    seniority: str
    arm: Literal["control", "treatment"]
    app_role: Literal["employee", "security_admin", "hr_viewer"]
    is_synthetic: bool = False


class AuthUser(BaseModel):
    id: str
    auth_user_id: str
    anon_id: str
    role_name: str
    department: str
    seniority: str
    arm: Literal["control", "treatment"]
    app_role: Literal["employee", "security_admin", "hr_viewer"]
    is_synthetic: bool = False
    created_at: datetime | None = None
