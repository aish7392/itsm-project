"""Request DTOs — Pydantic performs input validation at the API boundary."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from .domain.enums import AdminTitle, IncidentStatus, Level, Priority, Role


class _Strict(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class RegisterIn(_Strict):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    department: str | None = Field(default=None, max_length=120)


class LoginIn(_Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class IncidentCreate(_Strict):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=5000)
    service_id: int = Field(gt=0)
    category_id: int | None = Field(default=None, gt=0)
    impact: Level = Level.MEDIUM
    urgency: Level = Level.MEDIUM
    affected_users: int = Field(default=1, ge=1, le=1_000_000)
    force: bool = False


class IncidentUpdate(_Strict):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    description: str | None = Field(default=None, min_length=10, max_length=5000)
    impact: Level | None = None
    urgency: Level | None = None
    affected_users: int | None = Field(default=None, ge=1, le=1_000_000)
    category_id: int | None = Field(default=None, gt=0)
    service_id: int | None = Field(default=None, gt=0)
    priority_override: Priority | None = None


class AssignIn(_Strict):
    technician_id: int | None = None


class TextIn(_Strict):
    text: str = Field(min_length=1, max_length=5000)


class ResolveIn(_Strict):
    resolution: str = Field(min_length=5, max_length=5000)
    root_cause: str | None = Field(default=None, max_length=2000)


class VerifyIn(_Strict):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class CloseIn(_Strict):
    notes: str | None = Field(default=None, max_length=2000)


class StatusIn(_Strict):
    status: IncidentStatus


class SuggestIn(_Strict):
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)
    service_id: int | None = None


class UserCreate(_Strict):
    role: Role
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    department: str | None = None
    skills: list[str] = []
    max_workload: int = Field(default=5, ge=1, le=50)
    is_team_lead: bool = False
    experience_years: int = Field(default=1, ge=0, le=50)
    title: AdminTitle | None = None


class UserUpdate(_Strict):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    department: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    skills: list[str] | None = None
    max_workload: int | None = Field(default=None, ge=1, le=50)
    is_available: bool | None = None
    is_team_lead: bool | None = None
    experience_years: int | None = Field(default=None, ge=0, le=50)
    title: AdminTitle | None = None


class ServiceIn(_Strict):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    criticality: float = Field(default=1.0, ge=1.0, le=3.0)
    is_active: bool = True


class CategoryIn(_Strict):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z_]+$")
    name: str = Field(min_length=2, max_length=80)
    keywords: list[str] = []
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class SLAPolicyIn(_Strict):
    name: str = Field(min_length=2, max_length=120)
    priority: Priority
    service_id: int | None = None
    response_minutes: int = Field(gt=0, le=60 * 24 * 30)
    resolution_minutes: int = Field(gt=0, le=60 * 24 * 90)

    @model_validator(mode="after")
    def check(self):
        if self.resolution_minutes < self.response_minutes:
            raise ValueError("Resolution target must be ≥ response target")
        return self


class ConfigIn(_Strict):
    assignment_strategy: str | None = None
    priority_strategy: str | None = None
