from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.enums import NoteKind
from ..models import Administrator, Employee, Technician, User
from ..repositories import AuditRepository, IncidentFilter, LinkRepository
from ..schemas import (
    AssignIn, CloseIn, IncidentCreate, IncidentUpdate, ResolveIn, StatusIn, SuggestIn, TextIn,
    VerifyIn,
)
from ..security import current_user
from ..services.incident_service import IncidentService
from .serializers import incident_detail, incident_summary, user_out

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def svc(db: Session = Depends(get_db)) -> IncidentService:
    return IncidentService(db)


def detail(s: IncidentService, inc):
    s.db.flush()
    audit = AuditRepository(s.db).search(incident_id=inc.id)
    return incident_detail(inc, list(reversed(audit)), LinkRepository(s.db).for_incident(inc.id))


@router.get("")
def search(
    user: User = Depends(current_user), s: IncidentService = Depends(svc),
    id: int | None = None, q: str | None = None, status: str | None = None,
    priority: str | None = None, category_id: int | None = None, service_id: int | None = None,
    technician_id: int | None = None, reporter_id: int | None = None,
    date_from: date | None = None, date_to: date | None = None,
    sla_status: str | None = None, active_only: bool = False,
    scope: str = Query("auto", pattern="^(auto|mine|all)$"),
):
    """Search with ≥ 9 criteria. Results are always scoped by role:
    employees → own incidents; technicians → assigned (scope=all to browse)."""
    f = IncidentFilter(
        id=id, q=q, status=status, priority=priority, category_id=category_id,
        service_id=service_id, technician_id=technician_id, reporter_id=reporter_id,
        date_from=datetime.combine(date_from, datetime.min.time(), timezone.utc) if date_from else None,
        date_to=datetime.combine(date_to, datetime.min.time(), timezone.utc) if date_to else None,
        sla_status=sla_status, active_only=active_only)
    if isinstance(user, Employee):
        f.reporter_id = user.id
    elif isinstance(user, Technician) and scope != "all":
        f.technician_id = user.id
    return [incident_summary(i) for i in s.incidents.search(f)]


@router.post("", status_code=201)
def create(body: IncidentCreate, user: User = Depends(current_user), s: IncidentService = Depends(svc)):
    inc = s.create(user, **body.model_dump())
    return detail(s, inc)


@router.post("/suggest")
def suggest(body: SuggestIn, user: User = Depends(current_user), s: IncidentService = Depends(svc)):
    """Live intelligence while the user types: category, duplicates, past resolutions."""
    return s.suggest(body.title, body.description, body.service_id)


@router.get("/{incident_id}")
def get(incident_id: int, user: User = Depends(current_user), s: IncidentService = Depends(svc)):
    return detail(s, s.get_for(user, incident_id))


@router.patch("/{incident_id}")
def update(incident_id: int, body: IncidentUpdate, user: User = Depends(current_user),
           s: IncidentService = Depends(svc)):
    inc = s.get_for(user, incident_id)
    return detail(s, s.update(user, inc, **body.model_dump(exclude_none=True)))


@router.get("/{incident_id}/recommendations")
def recommendations(incident_id: int, user: User = Depends(current_user),
                    s: IncidentService = Depends(svc)):
    inc = s.get_for(user, incident_id)
    try:
        ranked = s.recommend_technicians(inc)
    except Exception:
        ranked = []
    sug = s.suggest(inc.title, inc.description, None)
    return {
        "technicians": [{**user_out(t, detail=True), "score": sc} for t, sc in ranked]
        if isinstance(user, Administrator) else [],
        "resolutions": [r for r in sug["resolutions"] if r["id"] != inc.id],
    }


# ── workflow actions ─────────────────────────────────────────────────────────────
@router.post("/{incident_id}/assign")
def assign(incident_id: int, body: AssignIn, user: User = Depends(current_user),
           s: IncidentService = Depends(svc)):
    inc = s.get_for(user, incident_id)
    return detail(s, s.assign(user, inc, body.technician_id))


@router.post("/{incident_id}/accept")
def accept(incident_id: int, user: User = Depends(current_user), s: IncidentService = Depends(svc)):
    return detail(s, s.accept(user, s.get_for(user, incident_id)))


@router.post("/{incident_id}/decline")
def decline(incident_id: int, body: TextIn, user: User = Depends(current_user),
            s: IncidentService = Depends(svc)):
    return detail(s, s.decline(user, s.get_for(user, incident_id), body.text))


@router.post("/{incident_id}/start")
def start(incident_id: int, user: User = Depends(current_user), s: IncidentService = Depends(svc)):
    return detail(s, s.start_work(user, s.get_for(user, incident_id)))


@router.post("/{incident_id}/notes")
def add_note(incident_id: int, body: TextIn, user: User = Depends(current_user),
             s: IncidentService = Depends(svc)):
    inc = s.get_for(user, incident_id)
    kind = NoteKind.INVESTIGATION if isinstance(user, (Technician, Administrator)) else NoteKind.COMMENT
    s.add_note(user, inc, body.text, kind)
    return detail(s, inc)


@router.post("/{incident_id}/request-info")
def request_info(incident_id: int, body: TextIn, user: User = Depends(current_user),
                 s: IncidentService = Depends(svc)):
    return detail(s, s.request_info(user, s.get_for(user, incident_id), body.text))


@router.post("/{incident_id}/respond")
def respond(incident_id: int, body: TextIn, user: User = Depends(current_user),
            s: IncidentService = Depends(svc)):
    return detail(s, s.respond_info(user, s.get_for(user, incident_id), body.text))


@router.post("/{incident_id}/resolve")
def resolve(incident_id: int, body: ResolveIn, user: User = Depends(current_user),
            s: IncidentService = Depends(svc)):
    return detail(s, s.resolve(user, s.get_for(user, incident_id), body.resolution, body.root_cause))


@router.post("/{incident_id}/verify")
def verify(incident_id: int, body: VerifyIn, user: User = Depends(current_user),
           s: IncidentService = Depends(svc)):
    return detail(s, s.verify(user, s.get_for(user, incident_id), body.rating, body.comment))


@router.post("/{incident_id}/reopen")
def reopen(incident_id: int, body: TextIn, user: User = Depends(current_user),
           s: IncidentService = Depends(svc)):
    return detail(s, s.reopen(user, s.get_for(user, incident_id), body.text))


@router.post("/{incident_id}/close")
def close(incident_id: int, body: CloseIn, user: User = Depends(current_user),
          s: IncidentService = Depends(svc)):
    return detail(s, s.close(user, s.get_for(user, incident_id), body.notes))


@router.post("/{incident_id}/status")
def force_status(incident_id: int, body: StatusIn, user: User = Depends(current_user),
                 s: IncidentService = Depends(svc)):
    return detail(s, s.change_status(user, s.get_for(user, incident_id), body.status))
