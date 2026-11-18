"""REPOSITORY PATTERN — all SQL lives here.

Services ask repositories for domain objects and never build queries themselves, so
the persistence technology (PostgreSQL today) can change without touching business
logic. `Repository[T]` is a generic base class; concrete repositories add
entity-specific queries.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Generic, TypeVar

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from ..domain.enums import ACTIVE_STATUSES, Role, SLAState, WORKLOAD_STATUSES
from ..domain.exceptions import (
    CategoryNotFoundError, IncidentNotFoundError, ITSMError, ServiceNotFoundError,
    UserNotFoundError,
)
from ..models import (
    Administrator, AuditLog, Base, Category, EmailOutbox, Incident, IncidentLink, ITService,
    Notification, SLAPolicy, SLAViolation, SystemConfig, Technician, User,
)

T = TypeVar("T", bound=Base)


class Repository(Generic[T]):
    model: type[T]
    not_found: type[ITSMError] = ITSMError

    def __init__(self, db: Session):
        self.db = db

    def get(self, id_: int) -> T:
        obj = self.db.get(self.model, id_)
        if obj is None:
            raise self.not_found(f"{self.model.__name__} {id_} not found")
        return obj

    def find(self, id_: int) -> T | None:
        return self.db.get(self.model, id_)

    def list(self) -> list[T]:
        return list(self.db.scalars(select(self.model).order_by(self.model.id)))

    def add(self, obj: T) -> T:
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj: T) -> None:
        self.db.delete(obj)
        self.db.flush()


class UserRepository(Repository[User]):
    model, not_found = User, UserNotFoundError

    def by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(func.lower(User.email) == email.lower()))

    def technicians(self, only_active: bool = True) -> list[Technician]:
        q = select(Technician).order_by(Technician.id)
        if only_active:
            q = q.where(Technician.is_active.is_(True))
        return list(self.db.scalars(q))

    def admins(self, title: str | None = None) -> list[Administrator]:
        q = select(Administrator).where(Administrator.is_active.is_(True))
        if title:
            q = q.where(Administrator.title == title)
        return list(self.db.scalars(q))

    def team_leads(self) -> list[Technician]:
        return [t for t in self.technicians() if t.is_team_lead]

    def by_role(self, role: Role | None) -> list[User]:
        q = select(User).order_by(User.id)
        if role:
            q = q.where(User.role == role.value)
        return list(self.db.scalars(q))


class ServiceRepository(Repository[ITService]):
    model, not_found = ITService, ServiceNotFoundError

    def by_name(self, name: str) -> ITService | None:
        return self.db.scalar(select(ITService).where(func.lower(ITService.name) == name.lower()))


class CategoryRepository(Repository[Category]):
    model, not_found = Category, CategoryNotFoundError

    def by_code(self, code: str) -> Category | None:
        return self.db.scalar(select(Category).where(Category.code == code.upper()))

    def active(self) -> list[Category]:
        return list(self.db.scalars(select(Category).where(Category.is_active.is_(True))))


class SLAPolicyRepository(Repository[SLAPolicy]):
    model = SLAPolicy

    def find_for(self, priority: str, service_id: int | None) -> SLAPolicy | None:
        """Service-specific policy wins over the organisation default."""
        if service_id is not None:
            p = self.db.scalar(select(SLAPolicy).where(
                SLAPolicy.priority == priority, SLAPolicy.service_id == service_id))
            if p:
                return p
        return self.db.scalar(select(SLAPolicy).where(
            SLAPolicy.priority == priority, SLAPolicy.service_id.is_(None)))


class ConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str, default: str = "") -> str:
        row = self.db.get(SystemConfig, key)
        return row.value if row else default

    def set(self, key: str, value: str) -> None:
        row = self.db.get(SystemConfig, key)
        if row:
            row.value = value
        else:
            self.db.add(SystemConfig(key=key, value=value))
        self.db.flush()

    def all(self) -> dict[str, str]:
        return {r.key: r.value for r in self.db.scalars(select(SystemConfig))}


class IncidentFilter:
    """Value object holding search criteria (keeps the search signature stable)."""

    def __init__(self, **kw):
        self.id: int | None = kw.get("id")
        self.q: str | None = kw.get("q")
        self.status: str | None = kw.get("status")
        self.priority: str | None = kw.get("priority")
        self.category_id: int | None = kw.get("category_id")
        self.service_id: int | None = kw.get("service_id")
        self.technician_id: int | None = kw.get("technician_id")
        self.reporter_id: int | None = kw.get("reporter_id")
        self.date_from: datetime | None = kw.get("date_from")
        self.date_to: datetime | None = kw.get("date_to")
        self.sla_status: str | None = kw.get("sla_status")
        self.active_only: bool = kw.get("active_only", False)


class IncidentRepository(Repository[Incident]):
    model, not_found = Incident, IncidentNotFoundError

    def search(self, f: IncidentFilter, limit: int = 200) -> list[Incident]:
        q: Select = select(Incident)
        if f.id:
            q = q.where(Incident.id == f.id)
        if f.q:
            like = f"%{f.q.lower()}%"
            q = q.where(or_(func.lower(Incident.title).like(like),
                            func.lower(Incident.description).like(like)))
        if f.status:
            q = q.where(Incident.status.in_(f.status.split(",")))
        if f.priority:
            q = q.where(Incident.priority.in_(f.priority.split(",")))
        if f.category_id:
            q = q.where(Incident.category_id == f.category_id)
        if f.service_id:
            q = q.where(Incident.service_id == f.service_id)
        if f.technician_id:
            q = q.where(Incident.technician_id == f.technician_id)
        if f.reporter_id:
            q = q.where(Incident.reporter_id == f.reporter_id)
        if f.date_from:
            q = q.where(Incident.created_at >= f.date_from)
        if f.date_to:
            q = q.where(Incident.created_at < f.date_to + timedelta(days=1))
        if f.active_only:
            q = q.where(Incident.status.in_([s.value for s in ACTIVE_STATUSES]))
        q = q.order_by(Incident.created_at.desc()).limit(limit)
        rows = list(self.db.scalars(q))
        if f.sla_status:  # derived attribute → filtered in memory
            from ..services.sla import SLAService
            rows = [i for i in rows if SLAService.sla_state(i).value == f.sla_status]
        return rows

    def active(self) -> list[Incident]:
        return list(self.db.scalars(select(Incident).where(
            Incident.status.in_([s.value for s in ACTIVE_STATUSES]))))

    def recent(self, hours: int = 72, exclude_id: int | None = None) -> list[Incident]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        q = select(Incident).where(Incident.created_at >= since)
        if exclude_id:
            q = q.where(Incident.id != exclude_id)
        return list(self.db.scalars(q))

    def resolved_with_resolution(self) -> list[Incident]:
        return list(self.db.scalars(select(Incident).where(Incident.resolution.is_not(None))))

    def workload_counts(self) -> dict[int, int]:
        rows = self.db.execute(
            select(Incident.technician_id, func.count())
            .where(Incident.status.in_([s.value for s in WORKLOAD_STATUSES]))
            .group_by(Incident.technician_id)
        )
        return {tid: n for tid, n in rows if tid}

    def all(self) -> list[Incident]:
        return list(self.db.scalars(select(Incident)))


class LinkRepository(Repository[IncidentLink]):
    model = IncidentLink

    def for_incident(self, incident_id: int) -> list[IncidentLink]:
        return list(self.db.scalars(select(IncidentLink).where(
            IncidentLink.incident_id == incident_id)))

    def exists(self, a: int, b: int) -> bool:
        return self.db.scalar(select(IncidentLink.id).where(
            IncidentLink.incident_id == a, IncidentLink.related_id == b)) is not None

    def all_of_type(self, link_type: str) -> list[IncidentLink]:
        return list(self.db.scalars(select(IncidentLink).where(IncidentLink.link_type == link_type)))


class AuditRepository(Repository[AuditLog]):
    model = AuditLog

    def search(self, incident_id: int | None = None, user_id: int | None = None,
               action: str | None = None, limit: int = 500) -> list[AuditLog]:
        q = select(AuditLog)
        if incident_id:
            q = q.where(AuditLog.incident_id == incident_id)
        if user_id:
            q = q.where(AuditLog.user_id == user_id)
        if action:
            q = q.where(AuditLog.action == action)
        return list(self.db.scalars(q.order_by(AuditLog.id.desc()).limit(limit)))


class NotificationRepository(Repository[Notification]):
    model = Notification

    def for_user(self, user_id: int, unread_only: bool = False, limit: int = 50):
        q = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            q = q.where(Notification.is_read.is_(False))
        return list(self.db.scalars(q.order_by(Notification.id.desc()).limit(limit)))

    def unread_count(self, user_id: int) -> int:
        return self.db.scalar(select(func.count()).where(
            Notification.user_id == user_id, Notification.is_read.is_(False))) or 0


class OutboxRepository(Repository[EmailOutbox]):
    model = EmailOutbox

    def latest(self, limit: int = 100) -> list[EmailOutbox]:
        return list(self.db.scalars(select(EmailOutbox).order_by(EmailOutbox.id.desc()).limit(limit)))


class ViolationRepository(Repository[SLAViolation]):
    model = SLAViolation

    def latest(self, limit: int = 200) -> list[SLAViolation]:
        return list(self.db.scalars(select(SLAViolation).order_by(SLAViolation.id.desc()).limit(limit)))


__all__ = [n for n in dir() if n.endswith("Repository")] + ["IncidentFilter", "SLAState"]
