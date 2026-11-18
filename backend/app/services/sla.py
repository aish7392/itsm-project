"""SLA management, continuous monitoring and automatic escalation.

* SLAService.apply()        – picks the policy (service-specific → default) and computes deadlines
* SLAService.sla_state()    – ON_TRACK / AT_RISK / BREACHED / MET for any incident
* SLAMonitor.run()          – background job: warnings, violations, escalation
* Escalation chain          – CHAIN OF RESPONSIBILITY:
        Technician → Team Lead → System Administrator → IT Manager
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..domain.enums import AdminTitle, EventType as E, IncidentStatus as S, SLAState, ViolationType
from ..domain.events import DomainEvent, EventBus
from ..domain.exceptions import MissingSLAConfigurationError
from ..models import Incident, SLAViolation, aware
from ..repositories import IncidentRepository, SLAPolicyRepository, UserRepository


def now() -> datetime:
    return datetime.now(timezone.utc)


class SLAService:
    def __init__(self, db: Session):
        self.policies = SLAPolicyRepository(db)

    def apply(self, inc: Incident, start: datetime | None = None) -> None:
        policy = self.policies.find_for(inc.priority, inc.service_id)
        if policy is None:
            raise MissingSLAConfigurationError(
                f"No SLA policy for priority {inc.priority}", priority=inc.priority)
        start = aware(start or inc.created_at) or now()
        inc.sla_policy = policy
        inc.response_due = start + timedelta(minutes=policy.response_minutes)
        inc.resolution_due = start + timedelta(minutes=policy.resolution_minutes)
        inc.sla_warning_sent = False

    @staticmethod
    def elapsed_fraction(inc: Incident, at: datetime | None = None) -> float:
        at = at or now()
        created = aware(inc.created_at)
        due = aware(inc.response_due if not inc.responded else inc.resolution_due)
        if not due or not created or due <= created:
            return 0.0
        return (at - created) / (due - created)

    @classmethod
    def sla_state(cls, inc: Incident, at: datetime | None = None) -> SLAState:
        if inc.response_breached or inc.resolution_breached:
            return SLAState.BREACHED
        if inc.resolved_at or not inc.is_active:
            return SLAState.MET
        frac = cls.elapsed_fraction(inc, at)
        if frac >= 1:
            return SLAState.BREACHED
        if frac >= settings.sla_warning_threshold:
            return SLAState.AT_RISK
        return SLAState.ON_TRACK

    @staticmethod
    def time_left_minutes(inc: Incident) -> float | None:
        due = aware(inc.response_due if not inc.responded else inc.resolution_due)
        if not due or not inc.is_active:
            return None
        return round((due - now()).total_seconds() / 60, 1)


# ─────────────────────── CHAIN OF RESPONSIBILITY: escalation ────────────────────────
class EscalationHandler(ABC):
    level: int
    label: str

    def __init__(self, nxt: "EscalationHandler | None" = None):
        self.next = nxt

    def handle(self, inc: Incident, users: UserRepository, bus: EventBus) -> bool:
        if inc.escalation_level == self.level - 1:
            recipients = self.escalate(inc, users)
            inc.escalation_level = self.level
            bus.publish(DomainEvent(
                E.INCIDENT_ESCALATED, inc, None,
                f"Not acknowledged within SLA – escalated to {self.label} (level {self.level}): "
                + (", ".join(u.name for u in recipients) or "no recipient configured"),
                payload={"recipients": recipients, "level": self.level}))
            return True
        return self.next.handle(inc, users, bus) if self.next else False

    @abstractmethod
    def escalate(self, inc: Incident, users: UserRepository) -> list: ...


class TeamLeadHandler(EscalationHandler):
    level, label = 1, "Team Lead"

    def escalate(self, inc, users):
        leads = [t for t in users.team_leads() if t.is_available and t.id != inc.technician_id]
        if leads and inc.status_enum in (S.ASSIGNED, S.CLASSIFIED):
            lead = min(leads, key=lambda t: t.workload)
            inc.transition_to(S.ASSIGNED)  # re-assignment is ASSIGNED → ASSIGNED
            inc.technician = lead
            inc.assigned_at = now()
            return [lead]
        return users.team_leads()


class SystemAdminHandler(EscalationHandler):
    level, label = 2, "System Administrator"

    def escalate(self, inc, users):
        return users.admins(AdminTitle.SYSTEM_ADMIN.value)


class ITManagerHandler(EscalationHandler):
    level, label = 3, "IT Manager"

    def escalate(self, inc, users):
        return users.admins(AdminTitle.IT_MANAGER.value)


def escalation_chain() -> EscalationHandler:
    return TeamLeadHandler(SystemAdminHandler(ITManagerHandler()))


class SLAMonitor:
    """Run periodically (FastAPI background task) or on demand (admin button)."""
    ESCALATE_PRIORITIES = {"P1", "P2"}

    def __init__(self, db: Session, bus: EventBus):
        self.db, self.bus = db, bus
        self.incidents = IncidentRepository(db)
        self.users = UserRepository(db)
        self.chain = escalation_chain()

    def run(self, at: datetime | None = None) -> dict:
        at = at or now()
        stats = {"checked": 0, "warnings": 0, "violations": 0, "escalations": 0}
        for inc in self.incidents.active():
            stats["checked"] += 1
            rd, sd = aware(inc.response_due), aware(inc.resolution_due)
            if rd and not inc.responded and at > rd and not inc.response_breached:
                self._violate(inc, ViolationType.RESPONSE, rd)
                stats["violations"] += 1
            if sd and at > sd and not inc.resolution_breached:
                self._violate(inc, ViolationType.RESOLUTION, sd)
                stats["violations"] += 1
            if (not inc.sla_warning_sent and not inc.resolution_breached
                    and SLAService.elapsed_fraction(inc, at) >= settings.sla_warning_threshold):
                inc.sla_warning_sent = True
                left = SLAService.time_left_minutes(inc)
                self.bus.publish(DomainEvent(
                    E.SLA_WARNING, inc, None,
                    f"SLA deadline approaching ({left} min left)"))
                stats["warnings"] += 1
            if self._needs_escalation(inc, at) and self.chain.handle(inc, self.users, self.bus):
                stats["escalations"] += 1
        self.db.flush()
        return stats

    def _needs_escalation(self, inc: Incident, at: datetime) -> bool:
        if inc.priority not in self.ESCALATE_PRIORITIES or inc.responded:
            return False
        if inc.status_enum not in (S.CLASSIFIED, S.ASSIGNED) or inc.escalation_level >= 3:
            return False
        rd, created = aware(inc.response_due), aware(inc.created_at)
        if not rd:
            return False
        window = max(rd - created, timedelta(minutes=1))
        # level n is reached after (n) response windows past the deadline
        return at > rd + window * inc.escalation_level

    def _violate(self, inc: Incident, kind: ViolationType, deadline: datetime) -> None:
        if kind == ViolationType.RESPONSE:
            inc.response_breached = True
        else:
            inc.resolution_breached = True
        self.db.add(SLAViolation(incident=inc, violation_type=kind.value, deadline=deadline))
        self.bus.publish(DomainEvent(
            E.SLA_VIOLATED, inc, None, f"{kind.value.title()} SLA violated (deadline "
            f"{deadline:%Y-%m-%d %H:%M} UTC)"))
