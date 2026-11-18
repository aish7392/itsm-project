"""IncidentService — application service that orchestrates the incident lifecycle.

It composes (COMPOSITION) repositories, strategies, the SLA service, the intelligence
engines and the event bus. Every method:  authorise → validate → change state →
publish event. Observers handle audit + notifications.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..domain.assignment import SkillBasedStrategy, assignment_strategy
from ..domain.enums import (
    EventType as E, IncidentStatus as S, Level, LinkType, NoteKind, Priority,
)
from ..domain.events import DomainEvent, EventBus
from ..domain.exceptions import (
    DuplicateIncidentError, InvalidIncidentError, InvalidUserInputError, ITSMError,
    UnauthorizedOperationError,
)
from ..domain.intelligence import (
    CategoryClassifier, DuplicateDetector, ResolutionRecommender,
)
from ..domain.priority import PriorityInput, priority_strategy
from ..models import (
    Administrator, Employee, Incident, IncidentLink, IncidentNote, Technician, User,
)
from ..repositories import (
    CategoryRepository, ConfigRepository, IncidentRepository, LinkRepository,
    ServiceRepository, UserRepository,
)
from .notifications import AuditObserver, NotificationObserver
from .sla import SLAService


def build_event_bus(db: Session) -> EventBus:
    bus = EventBus()
    bus.subscribe(AuditObserver(db))
    bus.subscribe(NotificationObserver(db))
    return bus


class IncidentService:
    DUPLICATE_BLOCK_SCORE = 0.9      # same reporter, near-identical text → reject
    CORRELATION_WINDOW_MIN = 120     # ≥ 3 active incidents on one service in 2h → major

    def __init__(self, db: Session, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or build_event_bus(db)
        self.incidents = IncidentRepository(db)
        self.users = UserRepository(db)
        self.services = ServiceRepository(db)
        self.categories = CategoryRepository(db)
        self.links = LinkRepository(db)
        self.config = ConfigRepository(db)
        self.sla = SLAService(db)
        self.detector = DuplicateDetector()
        self.classifier = CategoryClassifier()
        self.recommender = ResolutionRecommender()

    # ─────────────────────────────── helpers ──────────────────────────────────────
    def _emit(self, type_, inc, actor, desc, prev=None, new=None, **payload):
        self.bus.publish(DomainEvent(type_, inc, actor, desc, prev, new, payload))

    def _move(self, inc: Incident, target: S, actor: User | None, desc: str,
              event: E = E.STATUS_CHANGED):
        prev, new = inc.transition_to(target)
        self._emit(event, inc, actor, desc, prev.value, new.value)

    @staticmethod
    def _require(cond: bool, msg: str = "You are not allowed to perform this operation"):
        if not cond:
            raise UnauthorizedOperationError(msg)

    def can_view(self, user: User, inc: Incident) -> bool:
        if user.can("incident:view_all") or isinstance(user, Technician):
            return True
        return inc.reporter_id == user.id

    def get_for(self, user: User, incident_id: int) -> Incident:
        inc = self.incidents.get(incident_id)
        self._require(self.can_view(user, inc), "You can only view your own incidents")
        return inc

    def _require_assignee(self, user: User, inc: Incident):
        self._require(isinstance(user, Technician) and inc.technician_id == user.id
                      or isinstance(user, Administrator),
                      "Only the assigned technician can do this")

    def _require_reporter(self, user: User, inc: Incident):
        self._require(inc.reporter_id == user.id or isinstance(user, Administrator),
                      "Only the reporter can do this")

    # ─────────────────────────────── create ───────────────────────────────────────
    def create(self, reporter: User, *, title: str, description: str, service_id: int,
               impact: str, urgency: str, affected_users: int = 1,
               category_id: int | None = None, force: bool = False) -> Incident:
        self._require(reporter.can("incident:create") or isinstance(reporter, Administrator),
                      "Your role cannot report incidents")
        from .factories import IncidentFactory

        service = self.services.get(service_id)
        if not service.is_active:
            raise InvalidIncidentError("This service is retired")
        # duplicate guard: same reporter re-submitting the same problem
        if not force:
            mine = [i for i in self.incidents.recent(hours=24)
                    if i.reporter_id == reporter.id and i.is_active]
            for m in self.detector.find(title, description, service_id, mine):
                if m.score >= self.DUPLICATE_BLOCK_SCORE:
                    raise DuplicateIncidentError(
                        f"You already reported this problem as {m.incident.code}",
                        existing=m.incident.code, existing_id=m.incident.id, score=m.score)

        category, auto = None, False
        if category_id:
            category = self.categories.get(category_id)
        else:
            sugg = self.classifier.suggest(f"{title} {description}", self.categories.active())
            if sugg:
                category, auto = self.categories.by_code(sugg[0].code), True
            else:
                category, auto = self.categories.by_code("OTHER"), True

        inc = IncidentFactory.create(
            reporter=reporter, title=title, description=description, service=service,
            category=category, impact=Level(impact), urgency=Level(urgency),
            affected_users=affected_users)
        inc.auto_category = auto
        self.incidents.add(inc)
        self._emit(E.INCIDENT_CREATED, inc, reporter,
                   f"{inc.code} created by {reporter.code} ({reporter.name})", None, S.NEW.value)

        # 1. classify
        self._move(inc, S.CLASSIFIED, None,
                   f"Classified as {category.code if category else 'UNCATEGORISED'}"
                   + (" (auto-suggested)" if auto else ""), E.INCIDENT_CLASSIFIED)
        # 2. prioritise  3. SLA
        self._prioritise(inc, None, initial=True)
        # 4. intelligence: duplicates / correlation
        self._detect_related(inc)
        # 5. assign
        self.auto_assign(inc, None)
        self.db.flush()
        return inc

    def _prioritise(self, inc: Incident, actor, initial=False):
        strat = priority_strategy(self.config.get("priority_strategy", "WEIGHTED"))
        res = strat.calculate(PriorityInput(
            Level(inc.impact), Level(inc.urgency), inc.service.criticality, inc.affected_users))
        old = inc.priority if not initial else None
        inc.priority, inc.priority_score = res.priority.value, res.score
        if initial:
            self._emit(E.PRIORITY_CALCULATED, inc, None,
                       f"Priority calculated as {res.priority.value} – {res.explanation}")
            self.sla.apply(inc)
        elif old != inc.priority:
            self._emit(E.PRIORITY_CHANGED, inc, actor,
                       f"Priority changed {old} → {inc.priority} – {res.explanation}", old, inc.priority)
            self.sla.apply(inc)

    def _detect_related(self, inc: Incident):
        candidates = [i for i in self.incidents.recent(hours=72, exclude_id=inc.id) if i.is_active]
        matches = self.detector.find(inc.title, inc.description, inc.service_id, candidates)
        for m in matches:
            if not self.links.exists(inc.id, m.incident.id):
                self.links.add(IncidentLink(incident_id=inc.id, related_id=m.incident.id,
                                            link_type=m.link_type, score=m.score))
                self.links.add(IncidentLink(incident_id=m.incident.id, related_id=inc.id,
                                            link_type=m.link_type, score=m.score))
        dups = [m for m in matches if m.link_type == LinkType.DUPLICATE.value]
        if dups:
            self._emit(E.DUPLICATE_DETECTED, inc, None,
                       "Possible duplicate of " + ", ".join(
                           f"{m.incident.code} ({m.score:.0%})" for m in dups))
        # correlation: burst of incidents on the same service
        since = datetime.now(timezone.utc) - timedelta(minutes=self.CORRELATION_WINDOW_MIN)
        burst = [i for i in candidates if i.service_id == inc.service_id
                 and (i.created_at.replace(tzinfo=timezone.utc) if i.created_at.tzinfo is None
                      else i.created_at) >= since]
        if len(burst) >= 2:
            for other in burst:
                if not self.links.exists(inc.id, other.id):
                    self.links.add(IncidentLink(incident_id=inc.id, related_id=other.id,
                                                link_type=LinkType.CORRELATED.value, score=0.5))
                    self.links.add(IncidentLink(incident_id=other.id, related_id=inc.id,
                                                link_type=LinkType.CORRELATED.value, score=0.5))
            self._emit(E.CORRELATION_DETECTED, inc, None,
                       f"{len(burst) + 1} incidents on '{inc.service.name}' within "
                       f"{self.CORRELATION_WINDOW_MIN} min – possible major incident")

    # ─────────────────────────────── assignment ──────────────────────────────────
    def auto_assign(self, inc: Incident, actor: User | None) -> Technician | None:
        name = self.config.get("assignment_strategy", "LOAD_BASED")
        strategy = assignment_strategy(name, self.config)
        try:
            tech = strategy.select(inc, self.users.technicians())
        except ITSMError as exc:
            self._emit(E.ASSIGNMENT_FAILED, inc, actor,
                       f"Automatic assignment failed: {exc.message}")
            return None
        self._assign(inc, tech, actor, f"via {name} strategy")
        return tech

    def _assign(self, inc: Incident, tech: Technician, actor, how: str):
        inc.technician = tech
        inc.assigned_at = datetime.now(timezone.utc)
        prev, new = inc.transition_to(S.ASSIGNED)
        self._emit(E.INCIDENT_ASSIGNED, inc, actor,
                   f"Assigned to {tech.code} ({tech.name}) {how}", prev.value, new.value)

    def assign(self, actor: User, inc: Incident, technician_id: int | None) -> Incident:
        self._require(actor.can("incident:assign"), "Only administrators can assign incidents")
        if technician_id is None:
            if not self.auto_assign(inc, actor):
                from ..domain.exceptions import TechnicianUnavailableError
                raise TechnicianUnavailableError("No technician could be assigned automatically")
            return inc
        tech = self.users.get(technician_id)
        if not isinstance(tech, Technician):
            raise InvalidUserInputError("Selected user is not a technician")
        if not tech.is_active or not tech.is_available:
            from ..domain.exceptions import TechnicianUnavailableError
            raise TechnicianUnavailableError(f"{tech.name} is not available")
        if not tech.has_capacity():
            from ..domain.exceptions import TechnicianWorkloadExceededError
            raise TechnicianWorkloadExceededError(
                f"{tech.name} already has {tech.workload}/{tech.max_workload} active incidents")
        self._assign(inc, tech, actor, f"manually by {actor.name}")
        return inc

    def recommend_technicians(self, inc: Incident):
        return SkillBasedStrategy().rank(inc, self.users.technicians())

    # ─────────────────────────────── technician actions ────────────────────────────
    def accept(self, tech: User, inc: Incident) -> Incident:
        self._require_assignee(tech, inc)
        self._move(inc, S.ACKNOWLEDGED, tech, f"Acknowledged by {tech.code} ({tech.name})")
        return inc

    def decline(self, tech: User, inc: Incident, reason: str) -> Incident:
        self._require_assignee(tech, inc)
        if not reason or len(reason.strip()) < 3:
            raise InvalidUserInputError("Please give a reason for declining")
        inc.declined_by = list({*(inc.declined_by or []), tech.id})
        prev, new = inc.transition_to(S.CLASSIFIED)
        inc.technician = None
        self._emit(E.INCIDENT_DECLINED, inc, tech, f"Declined by {tech.name}: {reason}",
                   prev.value, new.value)
        self.auto_assign(inc, None)
        return inc

    def start_work(self, tech: User, inc: Incident) -> Incident:
        self._require_assignee(tech, inc)
        self._move(inc, S.IN_PROGRESS, tech, "Investigation started")
        return inc

    def add_note(self, user: User, inc: Incident, body: str,
                 kind: NoteKind = NoteKind.INVESTIGATION) -> IncidentNote:
        if not body or not body.strip():
            raise InvalidUserInputError("Note cannot be empty")
        if kind == NoteKind.INVESTIGATION:
            self._require_assignee(user, inc)
        else:
            self._require(self.can_view(user, inc))
        note = IncidentNote(incident=inc, author=user, kind=kind.value, body=body.strip())
        inc.notes.append(note)
        self._emit(E.NOTE_ADDED, inc, user, f"{kind.value.title()} note added by {user.name}")
        return note

    def request_info(self, tech: User, inc: Incident, question: str) -> Incident:
        self._require_assignee(tech, inc)
        if not question or not question.strip():
            raise InvalidUserInputError("Question cannot be empty")
        inc.notes.append(IncidentNote(incident=inc, author=tech,
                                      kind=NoteKind.INFO_REQUEST.value, body=question.strip()))
        self._move(inc, S.AWAITING_INFO, tech, f"Information requested: {question.strip()}",
                   E.INFO_REQUESTED)
        return inc

    def resolve(self, tech: User, inc: Incident, resolution: str, root_cause: str | None) -> Incident:
        self._require_assignee(tech, inc)
        if not resolution or len(resolution.strip()) < 5:
            raise InvalidUserInputError("Resolution details are required (min 5 characters)")
        inc.resolution, inc.root_cause = resolution.strip(), (root_cause or "").strip() or None
        self._move(inc, S.RESOLVED, tech, f"Resolved: {inc.resolution}", E.INCIDENT_RESOLVED)
        return inc

    # ─────────────────────────────── employee actions ─────────────────────────────
    def update(self, user: User, inc: Incident, **changes) -> Incident:
        is_admin = isinstance(user, Administrator)
        self._require(is_admin or inc.reporter_id == user.id, "You can only edit your own incidents")
        if not is_admin and inc.status_enum not in (S.NEW, S.CLASSIFIED, S.ASSIGNED,
                                                     S.ACKNOWLEDGED, S.IN_PROGRESS, S.AWAITING_INFO):
            raise InvalidIncidentError("Resolved or closed incidents cannot be edited")
        changed = []
        for field in ("title", "description"):
            v = changes.get(field)
            if v is not None and v.strip() and v.strip() != getattr(inc, field):
                setattr(inc, field, v.strip()); changed.append(field)
        for field in ("impact", "urgency"):
            v = changes.get(field)
            if v is not None and Level(v).value != getattr(inc, field):
                setattr(inc, field, Level(v).value); changed.append(field)
        if changes.get("affected_users") and changes["affected_users"] != inc.affected_users:
            if changes["affected_users"] < 1:
                raise InvalidUserInputError("Affected users must be ≥ 1")
            inc.affected_users = changes["affected_users"]; changed.append("affected_users")
        if changes.get("category_id") and changes["category_id"] != inc.category_id:
            inc.category = self.categories.get(changes["category_id"]); inc.auto_category = False
            changed.append("category")
        if changes.get("service_id") and changes["service_id"] != inc.service_id:
            inc.service = self.services.get(changes["service_id"]); changed.append("service")
        if not changed:
            return inc
        self._emit(E.INCIDENT_UPDATED, inc, user, f"Updated fields: {', '.join(changed)}")
        if {"impact", "urgency", "affected_users", "service"} & set(changed):
            self._prioritise(inc, user)
        if is_admin and changes.get("priority_override"):
            old = inc.priority
            inc.priority = Priority(changes["priority_override"]).value
            if old != inc.priority:
                self._emit(E.PRIORITY_CHANGED, inc, user,
                           f"Priority manually overridden {old} → {inc.priority}", old, inc.priority)
                self.sla.apply(inc)
        return inc

    def respond_info(self, user: User, inc: Incident, body: str) -> Incident:
        self._require_reporter(user, inc)
        if not body or not body.strip():
            raise InvalidUserInputError("Response cannot be empty")
        inc.notes.append(IncidentNote(incident=inc, author=user,
                                      kind=NoteKind.INFO_RESPONSE.value, body=body.strip()))
        self._move(inc, S.IN_PROGRESS, user, f"Reporter responded: {body.strip()}", E.INFO_PROVIDED)
        return inc

    def verify(self, user: User, inc: Incident, rating: int | None, comment: str | None) -> Incident:
        self._require_reporter(user, inc)
        if rating is not None and not 1 <= rating <= 5:
            raise InvalidUserInputError("Rating must be between 1 and 5")
        inc.feedback_rating, inc.feedback_comment = rating, (comment or None)
        self._move(inc, S.VERIFIED, user, "Resolution confirmed by reporter", E.INCIDENT_VERIFIED)
        if rating:
            self._emit(E.FEEDBACK_GIVEN, inc, user, f"Feedback: {rating}/5 {comment or ''}".strip())
        return inc

    def reopen(self, user: User, inc: Incident, reason: str) -> Incident:
        self._require_reporter(user, inc)
        if not reason or not reason.strip():
            raise InvalidUserInputError("Please explain why the issue is not fixed")
        inc.notes.append(IncidentNote(incident=inc, author=user,
                                      kind=NoteKind.COMMENT.value, body=f"Reopened: {reason}"))
        self._move(inc, S.IN_PROGRESS, user, f"Reopened by reporter: {reason}", E.INCIDENT_REOPENED)
        return inc

    # ─────────────────────────────── admin actions ────────────────────────────────
    def close(self, user: User, inc: Incident, notes: str | None) -> Incident:
        self._require(user.can("incident:close") or
                      (isinstance(user, Technician) and inc.technician_id == user.id),
                      "Only administrators or the assigned technician can close incidents")
        if isinstance(user, Technician) and inc.status_enum == S.RESOLVED:
            raise UnauthorizedOperationError("Wait for the reporter to verify the fix before closing")
        if inc.status_enum == S.RESOLVED:  # admin verifies on behalf of the reporter
            self._move(inc, S.VERIFIED, user, "Verified by service desk", E.INCIDENT_VERIFIED)
        inc.closure_notes = notes
        self._move(inc, S.CLOSED, user, f"Closed{': ' + notes if notes else ''}", E.INCIDENT_CLOSED)
        return inc

    def change_status(self, user: User, inc: Incident, target: S) -> Incident:
        """Generic transition (admins only) – still guarded by the State pattern."""
        self._require(isinstance(user, Administrator), "Only administrators can force a status")
        self._move(inc, target, user, f"Status set to {target.value} by {user.name}")
        if target == S.CLASSIFIED:  # back in the queue → no owner
            inc.technician = None
        return inc

    # ─────────────────────────────── intelligence ─────────────────────────────────
    def suggest(self, title: str, description: str, service_id: int | None) -> dict:
        text = f"{title} {description}"
        cats = self.classifier.suggest(text, self.categories.active())
        active = [i for i in self.incidents.recent(hours=72) if i.is_active]
        dups = self.detector.find(title, description, service_id, active)
        recs = self.recommender.recommend(text, self.incidents.resolved_with_resolution())
        return {
            "categories": [c.__dict__ for c in cats[:3]],
            "similar": [{"id": m.incident.id, "code": m.incident.code, "title": m.incident.title,
                         "status": m.incident.status, "score": m.score, "type": m.link_type}
                        for m in dups],
            "resolutions": [{"id": i.id, "code": i.code, "title": i.title,
                             "resolution": i.resolution, "score": s} for i, s in recs],
        }
