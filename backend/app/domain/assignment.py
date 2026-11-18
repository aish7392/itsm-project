"""STRATEGY PATTERN — technician assignment.

`AssignmentStrategy.select()` is a template method:
    1. drop inactive / unavailable technicians and those who declined this incident
    2. prefer technicians whose skills match the incident category
    3. drop technicians already at max workload
    4. delegate the final choice to the concrete strategy (`_choose`)

Concrete strategies: LOAD_BASED, ROUND_ROBIN, SKILL_BASED (smart recommendation).
The admin can switch strategy at runtime without touching any other code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, Sequence

from .exceptions import TechnicianUnavailableError, TechnicianWorkloadExceededError


class KeyValueStore(Protocol):
    def get(self, key: str, default: str = "") -> str: ...
    def set(self, key: str, value: str) -> None: ...


class AssignmentStrategy(ABC):
    name = "abstract"
    description = ""

    def __init__(self, store: KeyValueStore | None = None):
        self.store = store

    def eligible(self, incident, technicians: Sequence) -> list:
        cat = incident.category.code if incident.category else None
        declined = set(incident.declined_by or [])
        pool = [t for t in technicians
                if t.is_active and t.is_available and t.id not in declined]
        if not pool:
            raise TechnicianUnavailableError("No technician is currently available")
        skilled = [t for t in pool if t.has_skill(cat)]
        pool = skilled or pool  # fall back to generalists if nobody has the skill
        with_capacity = [t for t in pool if t.has_capacity()]
        if not with_capacity:
            raise TechnicianWorkloadExceededError(
                "Every suitable technician has reached the maximum workload",
                technicians=[t.code for t in pool])
        return with_capacity

    def select(self, incident, technicians: Sequence):
        return self._choose(incident, self.eligible(incident, technicians))

    @abstractmethod
    def _choose(self, incident, candidates: list): ...


class LoadBasedStrategy(AssignmentStrategy):
    name = "LOAD_BASED"
    description = "Technician with the fewest active incidents (ties → most experienced)"

    def _choose(self, incident, candidates):
        return min(candidates, key=lambda t: (t.workload, -(t.experience_years or 0), t.id))


class RoundRobinStrategy(AssignmentStrategy):
    name = "ROUND_ROBIN"
    description = "Rotate through eligible technicians in turn"
    KEY = "round_robin_last_id"

    def _choose(self, incident, candidates):
        ordered = sorted(candidates, key=lambda t: t.id)
        last = int(self.store.get(self.KEY, "0") or 0) if self.store else 0
        chosen = next((t for t in ordered if t.id > last), ordered[0])
        if self.store:
            self.store.set(self.KEY, str(chosen.id))
        return chosen


class SkillBasedStrategy(AssignmentStrategy):
    """Smart technician recommendation: weighs skills, experience with the category,
    seniority and current load."""
    name = "SKILL_BASED"
    description = "Best skill/experience match, penalised by current workload"

    @staticmethod
    def score(incident, tech) -> float:
        cat = incident.category.code if incident.category else None
        s = 3.0 if (cat and cat in (tech.skills or [])) else 0.0
        s += 0.5 * min(tech.resolved_count(cat), 10)
        s += 0.2 * (tech.experience_years or 0)
        s -= 1.0 * tech.workload
        if incident.priority == "P1" and tech.is_team_lead:
            s += 1.0
        return round(s, 2)

    def rank(self, incident, technicians: Sequence) -> list[tuple[object, float]]:
        cands = self.eligible(incident, technicians)
        return sorted(((t, self.score(incident, t)) for t in cands), key=lambda x: -x[1])

    def _choose(self, incident, candidates):
        return max(candidates, key=lambda t: (self.score(incident, t), -t.id))


ASSIGNMENT_STRATEGIES: dict[str, type[AssignmentStrategy]] = {
    c.name: c for c in (LoadBasedStrategy, RoundRobinStrategy, SkillBasedStrategy)
}


def assignment_strategy(name: str, store: KeyValueStore | None = None) -> AssignmentStrategy:
    """Simple factory."""
    return ASSIGNMENT_STRATEGIES.get(name, LoadBasedStrategy)(store)
