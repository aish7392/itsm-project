"""Entity → JSON conversion (keeps ORM objects out of HTTP responses)."""
from __future__ import annotations

from ..domain.lifecycle import StateRegistry
from ..models import (
    Administrator, AuditLog, Category, Incident, ITService, Notification, SLAPolicy, Technician,
    User,
)
from ..services.sla import SLAService


def iso(dt):
    return dt.isoformat() if dt else None


def user_out(u: User | None, detail: bool = False) -> dict | None:
    if u is None:
        return None
    d = {"id": u.id, "code": u.code, "name": u.name, "email": u.email, "role": u.role}
    if detail:
        d.update(department=u.department, is_active=u.is_active, created_at=iso(u.created_at),
                 dashboard=u.dashboard(), permissions=sorted(u.permissions()))
        if isinstance(u, Technician):
            d.update(skills=u.skills or [], max_workload=u.max_workload,
                     is_available=u.is_available, is_team_lead=u.is_team_lead,
                     experience_years=u.experience_years, workload=u.workload)
        if isinstance(u, Administrator):
            d.update(title=u.title)
    return d


def service_out(s: ITService | None):
    return s and {"id": s.id, "name": s.name, "description": s.description,
                  "criticality": s.criticality, "is_active": s.is_active}


def category_out(c: Category | None):
    return c and {"id": c.id, "code": c.code, "name": c.name, "keywords": c.keywords or [],
                  "is_active": c.is_active}


def sla_policy_out(p: SLAPolicy | None):
    return p and {"id": p.id, "name": p.name, "priority": p.priority, "service_id": p.service_id,
                  "service": p.service.name if p.service else None,
                  "response_minutes": p.response_minutes, "resolution_minutes": p.resolution_minutes}


def incident_summary(i: Incident) -> dict:
    return {
        "id": i.id, "code": i.code, "title": i.title, "status": i.status,
        "priority": i.priority, "priority_score": i.priority_score,
        "impact": i.impact, "urgency": i.urgency, "affected_users": i.affected_users,
        "category": category_out(i.category), "service": service_out(i.service),
        "reporter": user_out(i.reporter), "technician": user_out(i.technician),
        "created_at": iso(i.created_at), "updated_at": iso(i.updated_at),
        "response_due": iso(i.response_due), "resolution_due": iso(i.resolution_due),
        "sla_state": SLAService.sla_state(i).value,
        "sla_minutes_left": SLAService.time_left_minutes(i),
        "escalation_level": i.escalation_level,
    }


def incident_detail(i: Incident, audit: list[AuditLog], links) -> dict:
    d = incident_summary(i)
    d.update({
        "description": i.description,
        "auto_category": i.auto_category,
        "sla_policy": sla_policy_out(i.sla_policy),
        "assigned_at": iso(i.assigned_at), "acknowledged_at": iso(i.acknowledged_at),
        "resolved_at": iso(i.resolved_at), "verified_at": iso(i.verified_at),
        "closed_at": iso(i.closed_at),
        "response_breached": i.response_breached, "resolution_breached": i.resolution_breached,
        "resolution": i.resolution, "root_cause": i.root_cause, "closure_notes": i.closure_notes,
        "feedback_rating": i.feedback_rating, "feedback_comment": i.feedback_comment,
        "allowed_transitions": sorted(s.value for s in StateRegistry.get(i.status).allowed),
        "notes": [{"id": n.id, "kind": n.kind, "body": n.body, "author": user_out(n.author),
                   "created_at": iso(n.created_at)} for n in i.notes],
        "audit": [audit_out(a) for a in audit],
        "related": [{"id": l.related.id, "code": l.related.code, "title": l.related.title,
                     "status": l.related.status, "type": l.link_type, "score": l.score}
                    for l in links],
        "violations": [{"type": v.violation_type, "deadline": iso(v.deadline),
                        "detected_at": iso(v.detected_at)} for v in i.violations],
    })
    return d


def audit_out(a: AuditLog) -> dict:
    return {"id": a.id, "timestamp": iso(a.timestamp), "user": user_out(a.user),
            "incident_id": a.incident_id,
            "incident_code": f"INC{1000 + a.incident_id}" if a.incident_id else None,
            "action": a.action, "previous_state": a.previous_state, "new_state": a.new_state,
            "description": a.description}


def notification_out(n: Notification) -> dict:
    return {"id": n.id, "incident_id": n.incident_id, "channel": n.channel, "event": n.event,
            "message": n.message, "is_read": n.is_read, "created_at": iso(n.created_at)}
