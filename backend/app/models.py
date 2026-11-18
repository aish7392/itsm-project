"""Persistent domain entities (SQLAlchemy ORM).

OOP highlights
--------------
* INHERITANCE + POLYMORPHISM: `User` is an abstract base; `Employee`, `Technician`
  and `Administrator` are real "is-a" subclasses (single-table inheritance). Each
  overrides `permissions()` and `dashboard()` so code can treat any user uniformly.
* ENCAPSULATION: password hashes are never exposed — only `set_password()` /
  `verify_password()`; incident status can only change through `transition_to()`.
* COMPOSITION: an Incident *owns* its notes (cascade delete-orphan) — notes cannot
  exist without their incident.
* ASSOCIATION / AGGREGATION: Incident ↔ ITService, Incident ↔ Technician,
  Incident ↔ Category reference independent objects that outlive the incident.
"""
from __future__ import annotations

from datetime import datetime, timezone

import os

import bcrypt
from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .domain.enums import (
    ACTIVE_STATUSES, AdminTitle, IncidentStatus, Level, Priority, Role, WORKLOAD_STATUSES,
)
from .domain.lifecycle import IncidentState, StateRegistry


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; normalise everything to aware UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ════════════════════════════════════════ USERS ════════════════════════════════════════
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    _password_hash: Mapped[str] = mapped_column("password_hash", String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __mapper_args__ = {"polymorphic_on": "role", "polymorphic_abstract": True}

    # --- encapsulated password handling -------------------------------------------
    def set_password(self, raw: str) -> None:
        self._password_hash = bcrypt.hashpw(raw.encode(), bcrypt.gensalt(rounds=int(os.getenv("BCRYPT_ROUNDS", "12")))).decode()

    def verify_password(self, raw: str) -> bool:
        try:
            return bcrypt.checkpw(raw.encode(), self._password_hash.encode())
        except ValueError:
            return False

    # --- polymorphic behaviour -----------------------------------------------------
    def permissions(self) -> set[str]:
        return {"incident:view_own", "notification:read"}

    def can(self, permission: str) -> bool:
        return permission in self.permissions()

    def dashboard(self) -> str:
        raise NotImplementedError

    @property
    def code(self) -> str:
        return f"{self.role[0]}{100 + self.id}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.code} {self.email}>"


class Employee(User):
    __mapper_args__ = {"polymorphic_identity": Role.EMPLOYEE.value}

    def permissions(self) -> set[str]:
        return super().permissions() | {
            "incident:create", "incident:edit_own", "incident:respond", "incident:feedback",
            "incident:verify",
        }

    def dashboard(self) -> str:
        return "employee"


class Technician(User):
    __mapper_args__ = {"polymorphic_identity": Role.TECHNICIAN.value}

    skills: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    max_workload: Mapped[int | None] = mapped_column(Integer, default=5, nullable=True)
    is_available: Mapped[bool | None] = mapped_column(Boolean, default=True, nullable=True)
    is_team_lead: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, default=1, nullable=True)

    assigned_incidents: Mapped[list["Incident"]] = relationship(
        back_populates="technician", foreign_keys="Incident.technician_id"
    )

    def permissions(self) -> set[str]:
        return super().permissions() | {
            "incident:view_assigned", "incident:work", "incident:resolve", "workload:view",
        }

    def dashboard(self) -> str:
        return "technician"

    # behaviour lives with the data it uses
    @property
    def active_incidents(self) -> list["Incident"]:
        return [i for i in self.assigned_incidents if i.status_enum in WORKLOAD_STATUSES]

    @property
    def workload(self) -> int:
        return len(self.active_incidents)

    def has_capacity(self) -> bool:
        return self.workload < (self.max_workload or 0)

    def has_skill(self, category_code: str | None) -> bool:
        return category_code is None or category_code in (self.skills or [])

    def resolved_count(self, category_code: str | None = None) -> int:
        return sum(
            1 for i in self.assigned_incidents
            if i.resolved_at and (category_code is None or
                                  (i.category and i.category.code == category_code))
        )


class Administrator(User):
    __mapper_args__ = {"polymorphic_identity": Role.ADMIN.value}

    title: Mapped[str | None] = mapped_column(
        String(30), default=AdminTitle.SYSTEM_ADMIN.value, nullable=True
    )

    def permissions(self) -> set[str]:
        return super().permissions() | {
            "incident:view_all", "incident:assign", "incident:close", "user:manage",
            "service:manage", "sla:manage", "category:manage", "config:manage",
            "report:view", "audit:view",
        }

    def dashboard(self) -> str:
        return "admin"


# ═════════════════════════════════════ CONFIGURATION ═══════════════════════════════════
class ITService(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    criticality: Mapped[float] = mapped_column(Float, default=1.0)  # 1x … 3x
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SLAPolicy(Base):
    """service_id NULL = organisation-wide default for that priority."""
    __tablename__ = "sla_policies"
    __table_args__ = (UniqueConstraint("priority", "service_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    priority: Mapped[str] = mapped_column(String(4))
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    response_minutes: Mapped[int] = mapped_column(Integer)
    resolution_minutes: Mapped[int] = mapped_column(Integer)

    service: Mapped[ITService | None] = relationship()


class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


# ═══════════════════════════════════════ INCIDENTS ═════════════════════════════════════
class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    technician_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    sla_policy_id: Mapped[int | None] = mapped_column(ForeignKey("sla_policies.id"), nullable=True)

    impact: Mapped[str] = mapped_column(String(10), default=Level.MEDIUM.value)
    urgency: Mapped[str] = mapped_column(String(10), default=Level.MEDIUM.value)
    affected_users: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[str] = mapped_column(String(4), default=Priority.P4.value, index=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default=IncidentStatus.NEW.value, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    closure_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    sla_warning_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    response_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    declined_by: Mapped[list] = mapped_column(JSON, default=list)
    auto_category: Mapped[bool] = mapped_column(Boolean, default=False)

    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id])
    technician: Mapped[Technician | None] = relationship(
        back_populates="assigned_incidents", foreign_keys=[technician_id]
    )
    category: Mapped[Category | None] = relationship()
    service: Mapped[ITService] = relationship()
    sla_policy: Mapped[SLAPolicy | None] = relationship()
    # COMPOSITION: notes live and die with their incident
    notes: Mapped[list["IncidentNote"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="IncidentNote.id"
    )
    violations: Mapped[list["SLAViolation"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )

    # --- identity --------------------------------------------------------------
    @property
    def code(self) -> str:
        return f"INC{1000 + self.id}" if self.id else "INC-NEW"

    # --- STATE PATTERN delegation -------------------------------------------------
    @property
    def status_enum(self) -> IncidentStatus:
        return IncidentStatus(self.status)

    @property
    def state(self) -> IncidentState:
        return StateRegistry.get(self.status)

    def transition_to(self, target: IncidentStatus) -> tuple[IncidentStatus, IncidentStatus]:
        return self.state.transition(self, target)

    @property
    def is_active(self) -> bool:
        return self.status_enum in ACTIVE_STATUSES

    @property
    def responded(self) -> bool:
        return self.acknowledged_at is not None


class IncidentNote(Base):
    __tablename__ = "incident_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="notes")
    author: Mapped[User] = relationship()


class IncidentLink(Base):
    """Duplicate / correlation relationship between two incidents."""
    __tablename__ = "incident_links"
    __table_args__ = (UniqueConstraint("incident_id", "related_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    related_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    link_type: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    related: Mapped[Incident] = relationship(foreign_keys=[related_id])


class SLAViolation(Base):
    __tablename__ = "sla_violations"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    violation_type: Mapped[str] = mapped_column(String(20))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="violations")


# ═════════════════════════════════════ AUDIT & NOTIFY ═════════════════════════════════
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(40))
    previous_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str] = mapped_column(Text)

    user: Mapped[User | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(20))
    event: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
