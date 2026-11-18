"""Administrator endpoints: users, technicians, services, categories, SLA, config, audit."""
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.assignment import ASSIGNMENT_STRATEGIES
from ..domain.enums import Role
from ..domain.exceptions import DuplicateEntityError, InvalidUserInputError
from ..domain.priority import PRIORITY_STRATEGIES
from ..models import (
    Administrator, AuditLog, Category, Incident, ITService, SLAPolicy, Technician, User,
)
from ..repositories import (
    AuditRepository, CategoryRepository, ConfigRepository, OutboxRepository,
    ServiceRepository, SLAPolicyRepository, UserRepository, ViolationRepository,
)
from ..schemas import CategoryIn, ConfigIn, ServiceIn, SLAPolicyIn, UserCreate, UserUpdate
from ..security import require_roles
from ..services.factories import PASSWORD_RULE, UserFactory
from ..services.incident_service import build_event_bus
from ..services.sla import SLAMonitor
from .serializers import audit_out, category_out, iso, service_out, sla_policy_out, user_out

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = require_roles(Role.ADMIN)


def _log(db: Session, admin: User, action: str, desc: str):
    db.add(AuditLog(user_id=admin.id, action=action, description=desc))


# ───────────────────────────── users & technicians ─────────────────────────────
@router.get("/users")
def list_users(role: Role | None = None, db: Session = Depends(get_db), _=Depends(admin_only)):
    return [user_out(u, detail=True) for u in UserRepository(db).by_role(role)]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin=Depends(admin_only)):
    repo = UserRepository(db)
    if repo.by_email(body.email):
        raise DuplicateEntityError("Email already registered")
    data = body.model_dump(exclude={"role", "name", "email", "password"})
    user = repo.add(UserFactory.create(body.role, body.name, body.email, body.password, **data))
    _log(db, admin, "USER_CREATED", f"{user.role} {user.email} created")
    return user_out(user, detail=True)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db),
                admin=Depends(admin_only)):
    user = UserRepository(db).get(user_id)
    data = body.model_dump(exclude_none=True)
    if user.id == admin.id and data.get("is_active") is False:
        raise InvalidUserInputError("You cannot deactivate your own account")
    if "password" in data:
        if not PASSWORD_RULE.match(data["password"]):
            raise InvalidUserInputError("Password must contain letters and digits (min 8)")
        user.set_password(data.pop("password"))
    tech_fields = {"skills", "max_workload", "is_available", "is_team_lead", "experience_years"}
    for k, v in data.items():
        if k in tech_fields and not isinstance(user, Technician):
            continue
        if k == "title" and not isinstance(user, Administrator):
            continue
        if k == "skills":
            v = [s.upper() for s in v]
        if k == "title":
            v = v.value
        setattr(user, k, v)
    _log(db, admin, "USER_UPDATED", f"{user.email} updated: {', '.join(data) or 'password'}")
    return user_out(user, detail=True)


# ───────────────────────────── services ─────────────────────────────
@router.get("/services")
def list_services(db: Session = Depends(get_db), _=Depends(admin_only)):
    return [service_out(s) for s in ServiceRepository(db).list()]


@router.post("/services", status_code=201)
def create_service(body: ServiceIn, db: Session = Depends(get_db), admin=Depends(admin_only)):
    repo = ServiceRepository(db)
    if repo.by_name(body.name):
        raise DuplicateEntityError("Service already exists")
    s = repo.add(ITService(**body.model_dump()))
    _log(db, admin, "SERVICE_CREATED", f"Service {s.name} (criticality {s.criticality}x)")
    return service_out(s)


@router.put("/services/{service_id}")
def update_service(service_id: int, body: ServiceIn, db: Session = Depends(get_db),
                   admin=Depends(admin_only)):
    s = ServiceRepository(db).get(service_id)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    _log(db, admin, "SERVICE_UPDATED", f"Service {s.name} updated")
    return service_out(s)


# ───────────────────────────── categories ─────────────────────────────
@router.get("/categories")
def list_categories(db: Session = Depends(get_db), _=Depends(admin_only)):
    return [category_out(c) for c in CategoryRepository(db).list()]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db), admin=Depends(admin_only)):
    repo = CategoryRepository(db)
    if repo.by_code(body.code):
        raise DuplicateEntityError("Category code already exists")
    c = repo.add(Category(**body.model_dump()))
    _log(db, admin, "CATEGORY_CREATED", f"Category {c.code}")
    return category_out(c)


@router.put("/categories/{cat_id}")
def update_category(cat_id: int, body: CategoryIn, db: Session = Depends(get_db),
                    admin=Depends(admin_only)):
    c = CategoryRepository(db).get(cat_id)
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    _log(db, admin, "CATEGORY_UPDATED", f"Category {c.code} updated")
    return category_out(c)


# ───────────────────────────── SLA policies ─────────────────────────────
@router.get("/sla-policies")
def list_policies(db: Session = Depends(get_db), _=Depends(admin_only)):
    return [sla_policy_out(p) for p in SLAPolicyRepository(db).list()]


@router.post("/sla-policies", status_code=201)
def create_policy(body: SLAPolicyIn, db: Session = Depends(get_db), admin=Depends(admin_only)):
    if body.service_id:
        ServiceRepository(db).get(body.service_id)
    repo = SLAPolicyRepository(db)
    existing = repo.find_for(body.priority.value, body.service_id)
    if existing and existing.service_id == body.service_id:
        raise DuplicateEntityError("A policy for this priority/service already exists")
    p = repo.add(SLAPolicy(**{**body.model_dump(), "priority": body.priority.value}))
    _log(db, admin, "SLA_POLICY_CREATED", f"{p.name}: {p.priority} {p.response_minutes}/{p.resolution_minutes} min")
    return sla_policy_out(p)


@router.put("/sla-policies/{pid}")
def update_policy(pid: int, body: SLAPolicyIn, db: Session = Depends(get_db),
                  admin=Depends(admin_only)):
    p = SLAPolicyRepository(db).get(pid)
    for k, v in {**body.model_dump(), "priority": body.priority.value}.items():
        setattr(p, k, v)
    try:
        db.flush()
    except IntegrityError as exc:
        raise DuplicateEntityError("A policy for this priority/service already exists") from exc
    _log(db, admin, "SLA_POLICY_UPDATED", f"{p.name} updated")
    return sla_policy_out(p)


@router.delete("/sla-policies/{pid}", status_code=204)
def delete_policy(pid: int, db: Session = Depends(get_db), admin=Depends(admin_only)):
    repo = SLAPolicyRepository(db)
    p = repo.get(pid)
    if p.service_id is None:
        raise InvalidUserInputError("Default policies cannot be deleted (edit them instead)")
    _log(db, admin, "SLA_POLICY_DELETED", f"{p.name} deleted")
    for inc in db.query(Incident).filter_by(sla_policy_id=pid):
        inc.sla_policy_id = None
    repo.delete(p)


# ───────────────────────────── configuration ─────────────────────────────
@router.get("/config")
def get_config(db: Session = Depends(get_db), _=Depends(admin_only)):
    cfg = ConfigRepository(db)
    return {
        "assignment_strategy": cfg.get("assignment_strategy", "LOAD_BASED"),
        "priority_strategy": cfg.get("priority_strategy", "WEIGHTED"),
        "assignment_strategies": [{"name": k, "description": v.description}
                                  for k, v in ASSIGNMENT_STRATEGIES.items()],
        "priority_strategies": [{"name": k, "description": v.description}
                                for k, v in PRIORITY_STRATEGIES.items()],
    }


@router.put("/config")
def set_config(body: ConfigIn, db: Session = Depends(get_db), admin=Depends(admin_only)):
    cfg = ConfigRepository(db)
    if body.assignment_strategy:
        if body.assignment_strategy not in ASSIGNMENT_STRATEGIES:
            raise InvalidUserInputError("Unknown assignment strategy")
        cfg.set("assignment_strategy", body.assignment_strategy)
        _log(db, admin, "CONFIG_CHANGED", f"Assignment strategy → {body.assignment_strategy}")
    if body.priority_strategy:
        if body.priority_strategy not in PRIORITY_STRATEGIES:
            raise InvalidUserInputError("Unknown priority strategy")
        cfg.set("priority_strategy", body.priority_strategy)
        _log(db, admin, "CONFIG_CHANGED", f"Priority strategy → {body.priority_strategy}")
    return get_config(db, admin)


# ───────────────────────────── monitoring ─────────────────────────────
@router.get("/audit-logs")
def audit_logs(incident_id: int | None = None, user_id: int | None = None,
               action: str | None = None, db: Session = Depends(get_db), _=Depends(admin_only)):
    return [audit_out(a) for a in AuditRepository(db).search(incident_id, user_id, action)]


@router.get("/sla-violations")
def violations(db: Session = Depends(get_db), _=Depends(admin_only)):
    return [{"id": v.id, "incident_id": v.incident_id, "incident_code": v.incident.code,
             "title": v.incident.title, "priority": v.incident.priority,
             "technician": v.incident.technician.name if v.incident.technician else None,
             "type": v.violation_type, "deadline": iso(v.deadline), "detected_at": iso(v.detected_at)}
            for v in ViolationRepository(db).latest()]


@router.post("/sla/run")
def run_sla_monitor(db: Session = Depends(get_db), admin=Depends(admin_only)):
    """Run the SLA monitor immediately (it also runs in the background)."""
    return SLAMonitor(db, build_event_bus(db)).run()


@router.get("/email-outbox")
def email_outbox(db: Session = Depends(get_db), _=Depends(admin_only)):
    return [{"id": e.id, "recipient": e.recipient, "subject": e.subject, "body": e.body,
             "delivered": e.delivered, "simulated": e.simulated, "error": e.error,
             "created_at": iso(e.created_at)} for e in OutboxRepository(db).latest()]
