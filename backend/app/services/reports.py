"""Reporting & analytics (dashboard data)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..domain.enums import ACTIVE_STATUSES, IncidentStatus as S, SLAState
from ..models import aware
from ..repositories import (
    IncidentRepository, LinkRepository, UserRepository, ViolationRepository,
)
from .sla import SLAService


class ReportService:
    def __init__(self, db: Session):
        self.incidents = IncidentRepository(db)
        self.users = UserRepository(db)
        self.violations = ViolationRepository(db)
        self.links = LinkRepository(db)

    def overview(self) -> dict:
        all_ = self.incidents.all()
        states = Counter(SLAService.sla_state(i).value for i in all_)
        resolved = [i for i in all_ if i.resolved_at]
        hours = [(aware(i.resolved_at) - aware(i.created_at)).total_seconds() / 3600 for i in resolved]
        ratings = [i.feedback_rating for i in all_ if i.feedback_rating]
        breached = sum(1 for i in all_ if i.response_breached or i.resolution_breached)
        finished = [i for i in all_ if not i.is_active]
        return {
            "total": len(all_),
            "open": sum(1 for i in all_ if i.status_enum in ACTIVE_STATUSES),
            "critical_open": sum(1 for i in all_ if i.priority == "P1" and i.is_active),
            "resolved": sum(1 for i in all_ if i.status in (S.RESOLVED, S.VERIFIED, S.CLOSED)),
            "closed": sum(1 for i in all_ if i.status == S.CLOSED),
            "sla_violations": breached,
            "at_risk": states.get(SLAState.AT_RISK.value, 0),
            "sla_compliance_pct": round(100 * (1 - (sum(1 for i in finished if i.resolution_breached)
                                                   / len(finished))), 1) if finished else 100.0,
            "avg_resolution_hours": round(sum(hours) / len(hours), 2) if hours else None,
            "avg_feedback": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "by_status": dict(Counter(i.status for i in all_)),
            "by_priority": dict(Counter(i.priority for i in all_)),
            "by_category": dict(Counter(i.category.name if i.category else "—" for i in all_)),
            "by_service": dict(Counter(i.service.name for i in all_)),
            "by_sla_state": dict(states),
            "trend": self._trend(all_),
        }

    @staticmethod
    def _trend(all_, days: int = 14) -> list[dict]:
        today = datetime.now(timezone.utc).date()
        created, resolved = Counter(), Counter()
        for i in all_:
            created[aware(i.created_at).date()] += 1
            if i.resolved_at:
                resolved[aware(i.resolved_at).date()] += 1
        return [{"date": (d := today - timedelta(days=n)).isoformat(),
                 "created": created[d], "resolved": resolved[d]} for n in range(days - 1, -1, -1)]

    def technician_workload(self) -> list[dict]:
        out = []
        for t in self.users.technicians(only_active=False):
            mine = t.assigned_incidents
            out.append({
                "id": t.id, "code": t.code, "name": t.name, "skills": t.skills or [],
                "active": t.workload, "max_workload": t.max_workload,
                "available": t.is_available, "team_lead": t.is_team_lead,
                "resolved": t.resolved_count(),
                "breached": sum(1 for i in mine if i.resolution_breached or i.response_breached),
                "utilisation_pct": round(100 * t.workload / (t.max_workload or 1)),
            })
        return out

    def service_analysis(self) -> list[dict]:
        rows = defaultdict(lambda: {"total": 0, "open": 0, "p1": 0, "breached": 0})
        for i in self.incidents.all():
            r = rows[i.service.name]
            r["total"] += 1
            r["open"] += i.is_active
            r["p1"] += i.priority == "P1"
            r["breached"] += bool(i.response_breached or i.resolution_breached)
        return sorted(({"service": k, **v} for k, v in rows.items()), key=lambda r: -r["total"])

    def correlation_clusters(self) -> list[dict]:
        """Groups of linked active incidents (connected components)."""
        active = {i.id: i for i in self.incidents.active()}
        graph: dict[int, set[int]] = defaultdict(set)
        for link in self.links.list():
            if link.incident_id in active and link.related_id in active:
                graph[link.incident_id].add(link.related_id)
        seen, clusters = set(), []
        for start in graph:
            if start in seen:
                continue
            stack, comp = [start], set()
            while stack:
                n = stack.pop()
                if n in comp:
                    continue
                comp.add(n); stack.extend(graph[n] - comp)
            seen |= comp
            if len(comp) >= 2:
                incs = sorted((active[n] for n in comp), key=lambda i: i.id)
                clusters.append({
                    "size": len(incs),
                    "services": sorted({i.service.name for i in incs}),
                    "highest_priority": min(i.priority for i in incs),
                    "incidents": [{"id": i.id, "code": i.code, "title": i.title,
                                   "status": i.status, "priority": i.priority} for i in incs],
                })
        return sorted(clusters, key=lambda c: -c["size"])
