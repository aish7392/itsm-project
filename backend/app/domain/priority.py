"""STRATEGY PATTERN — priority calculation.

Priority Score = Impact × Urgency × Business Criticality
    Impact / Urgency : LOW = 1, MEDIUM = 1.5, HIGH = 2
    Criticality      : per IT service, 1x (e.g. Network) … 3x (e.g. Payment, Database)
    Score range      : 1 … 12

    score ≥ 6    → P1 Critical      (e.g. HIGH × HIGH × 1.5)
    score ≥ 3.5  → P2 High          (e.g. HIGH × HIGH × 1  = 4)
    score ≥ 2    → P3 Medium        (e.g. MEDIUM × MEDIUM × 1 = 2.25)
    otherwise    → P4 Low

The administrator chooses the active strategy at runtime; new strategies only need
to subclass PriorityStrategy and register themselves in PRIORITY_STRATEGIES.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .enums import Level, Priority


@dataclass(frozen=True)
class PriorityInput:
    impact: Level
    urgency: Level
    criticality: float
    affected_users: int = 1


@dataclass(frozen=True)
class PriorityResult:
    score: float
    priority: Priority
    explanation: str


class PriorityStrategy(ABC):
    """Interface (contract) for every priority algorithm."""
    name: str = "abstract"
    description: str = ""
    thresholds: tuple[tuple[float, Priority], ...] = (
        (6.0, Priority.P1), (3.5, Priority.P2), (2.0, Priority.P3),
    )

    @abstractmethod
    def score(self, data: PriorityInput) -> tuple[float, str]: ...

    def classify(self, score: float) -> Priority:
        for threshold, prio in self.thresholds:
            if score >= threshold:
                return prio
        return Priority.P4

    def calculate(self, data: PriorityInput) -> PriorityResult:  # template method
        s, why = self.score(data)
        s = round(s, 2)
        p = self.classify(s)
        return PriorityResult(s, p, f"{why} = {s} → {p.value} ({p.label})")


class WeightedScoreStrategy(PriorityStrategy):
    name = "WEIGHTED"
    description = "Impact × Urgency × Business criticality"

    def score(self, d: PriorityInput) -> tuple[float, str]:
        s = d.impact.weight * d.urgency.weight * d.criticality
        return s, (f"Impact {d.impact.value}({d.impact.weight}) × Urgency "
                   f"{d.urgency.value}({d.urgency.weight}) × Criticality {d.criticality}")


class UserImpactWeightedStrategy(WeightedScoreStrategy):
    """Extends the weighted model: incidents hitting many users get a boost
    (1 + log10(users)/2, capped at 2x → 100 users doubles the score)."""
    name = "USER_WEIGHTED"
    description = "Weighted score boosted by number of affected users"

    def score(self, d: PriorityInput) -> tuple[float, str]:
        base, why = super().score(d)
        factor = min(2.0, 1 + math.log10(max(1, d.affected_users)) / 2)
        return base * factor, f"{why} × Users factor {factor:.2f} ({d.affected_users} users)"


PRIORITY_STRATEGIES: dict[str, type[PriorityStrategy]] = {
    cls.name: cls for cls in (WeightedScoreStrategy, UserImpactWeightedStrategy)
}


def priority_strategy(name: str) -> PriorityStrategy:
    return PRIORITY_STRATEGIES.get(name, WeightedScoreStrategy)()
