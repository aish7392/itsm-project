"""Reports, notifications, workload and metadata endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.enums import IncidentStatus, Level, Priority, Role
from ..domain.exceptions import UnauthorizedOperationError
from ..domain.lifecycle import StateRegistry
from ..models import Technician, User
from ..repositories import (
    CategoryRepository, NotificationRepository, ServiceRepository, UserRepository,
)
from ..security import current_user, require_roles
from ..services.reports import ReportService
from .serializers import category_out, incident_summary, notification_out, service_out, user_out

reports = APIRouter(prefix="/api/reports", tags=["reports"])
notifications = APIRouter(prefix="/api/notifications", tags=["notifications"])
meta = APIRouter(prefix="/api", tags=["meta"])
admin_only = require_roles(Role.ADMIN)


@reports.get("/overview")
def overview(db: Session = Depends(get_db), _=Depends(admin_only)):
    return ReportService(db).overview()


@reports.get("/workload")
def workload(db: Session = Depends(get_db), _=Depends(admin_only)):
    return ReportService(db).technician_workload()


@reports.get("/services")
def services_report(db: Session = Depends(get_db), _=Depends(admin_only)):
    return ReportService(db).service_analysis()


@reports.get("/clusters")
def clusters(db: Session = Depends(get_db), _=Depends(admin_only)):
    return ReportService(db).correlation_clusters()


@meta.get("/me/workload")
def my_workload(user: User = Depends(current_user)):
    if not isinstance(user, Technician):
        raise UnauthorizedOperationError("Only technicians have a workload")
    return {
        "active": user.workload, "max_workload": user.max_workload,
        "resolved": user.resolved_count(), "is_available": user.is_available,
        "incidents": [incident_summary(i) for i in user.active_incidents],
    }


@meta.post("/me/availability")
def toggle_availability(user: User = Depends(current_user)):
    if not isinstance(user, Technician):
        raise UnauthorizedOperationError("Only technicians have availability")
    user.is_available = not user.is_available
    return {"is_available": user.is_available}


@meta.get("/meta")
def metadata(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {
        "services": [service_out(s) for s in ServiceRepository(db).list() if s.is_active],
        "categories": [category_out(c) for c in CategoryRepository(db).active()],
        "technicians": [user_out(t) for t in UserRepository(db).technicians()]
        if user.role != Role.EMPLOYEE.value else [],
        "levels": [l.value for l in Level],
        "priorities": [{"value": p.value, "label": p.label} for p in Priority],
        "statuses": [s.value for s in IncidentStatus],
        "lifecycle": StateRegistry.graph(),
    }


@notifications.get("")
def my_notifications(unread_only: bool = False, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    repo = NotificationRepository(db)
    return {"unread": repo.unread_count(user.id),
            "items": [notification_out(n) for n in repo.for_user(user.id, unread_only)]}


@notifications.post("/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = NotificationRepository(db).get(nid)
    if n.user_id != user.id:
        raise UnauthorizedOperationError("Not your notification")
    n.is_read = True
    return {"ok": True}


@notifications.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(current_user)):
    for n in NotificationRepository(db).for_user(user.id, unread_only=True, limit=1000):
        n.is_read = True
    return {"ok": True}
