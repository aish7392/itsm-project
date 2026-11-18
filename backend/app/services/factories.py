"""FACTORY PATTERN — creating users and incidents.

Callers say *what* they want ("a TECHNICIAN with these skills") and the factory
decides *which class* to instantiate and how to initialise it consistently.
"""
from __future__ import annotations

import re

from ..domain.enums import AdminTitle, IncidentStatus, Level, Role
from ..domain.exceptions import InvalidIncidentError, InvalidUserInputError
from ..models import Administrator, Employee, Incident, Technician, User

PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,128}$")


class UserFactory:
    _classes: dict[Role, type[User]] = {
        Role.EMPLOYEE: Employee, Role.TECHNICIAN: Technician, Role.ADMIN: Administrator,
    }

    @classmethod
    def create(cls, role: Role, name: str, email: str, password: str, **extra) -> User:
        if not PASSWORD_RULE.match(password or ""):
            raise InvalidUserInputError(
                "Password must be at least 8 characters and contain letters and digits")
        if not name or not name.strip():
            raise InvalidUserInputError("Name is required")
        user_cls = cls._classes[Role(role)]
        user = user_cls(name=name.strip(), email=email.lower().strip(),
                        department=extra.get("department"))
        user.set_password(password)
        if isinstance(user, Technician):
            user.skills = [s.upper() for s in extra.get("skills") or []]
            user.max_workload = extra.get("max_workload") or 5
            user.is_available = True if extra.get("is_available") is None else extra["is_available"]
            user.is_team_lead = bool(extra.get("is_team_lead"))
            user.experience_years = extra.get("experience_years") or 1
        if isinstance(user, Administrator):
            user.title = extra.get("title") or AdminTitle.SYSTEM_ADMIN.value
        return user


class IncidentFactory:
    MIN_TITLE, MIN_DESC = 5, 10

    @classmethod
    def create(cls, *, reporter: User, title: str, description: str, service, category,
               impact: Level, urgency: Level, affected_users: int = 1) -> Incident:
        title, description = (title or "").strip(), (description or "").strip()
        if len(title) < cls.MIN_TITLE:
            raise InvalidIncidentError(f"Title must be at least {cls.MIN_TITLE} characters")
        if len(description) < cls.MIN_DESC:
            raise InvalidIncidentError(f"Description must be at least {cls.MIN_DESC} characters")
        if affected_users < 1:
            raise InvalidIncidentError("Affected users must be at least 1")
        return Incident(
            title=title, description=description, reporter=reporter, service=service,
            category=category, impact=Level(impact).value, urgency=Level(urgency).value,
            affected_users=affected_users, status=IncidentStatus.NEW.value,
            declined_by=[], escalation_level=0,
        )
