"""STATE PATTERN — incident lifecycle.

Each lifecycle stage is its own class. A state knows (a) which states it may move to
and (b) what side-effects happen when the incident enters it. The Incident entity
delegates `transition_to()` to its current state object, so illegal transitions such
as NEW → CLOSED are rejected in exactly one place.

    NEW → CLASSIFIED → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS ⇄ AWAITING_INFO
                          ↑  │ (decline)                 │
                          └──┘                           ↓
                                    IN_PROGRESS ← RESOLVED → VERIFIED → CLOSED
                                     (reopen)
"""
from __future__ import annotations

from abc import ABC
from datetime import datetime, timezone
from typing import Protocol

from .enums import IncidentStatus as S
from .exceptions import InvalidStateTransitionError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LifecycleContext(Protocol):
    """What a state needs from the incident (interface, keeps domain decoupled from ORM)."""
    status: str
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    verified_at: datetime | None
    closed_at: datetime | None


class IncidentState(ABC):
    status: S
    allowed: frozenset[S] = frozenset()

    def can_transition_to(self, target: S) -> bool:
        return target in self.allowed

    def transition(self, ctx: LifecycleContext, target: S) -> tuple[S, S]:
        if not self.can_transition_to(target):
            raise InvalidStateTransitionError(
                f"Cannot move incident from {self.status.value} to {target.value}",
                current=self.status.value, target=target.value,
                allowed=sorted(s.value for s in self.allowed),
            )
        new_state = StateRegistry.get(target)
        self.on_exit(ctx)
        ctx.status = target.value
        new_state.on_enter(ctx, previous=self.status)
        return self.status, target

    # hooks (template methods) — overridden by concrete states where needed
    def on_enter(self, ctx: LifecycleContext, previous: S) -> None: ...
    def on_exit(self, ctx: LifecycleContext) -> None: ...

    @property
    def is_terminal(self) -> bool:
        return not self.allowed


class NewState(IncidentState):
    status, allowed = S.NEW, frozenset({S.CLASSIFIED})


class ClassifiedState(IncidentState):
    status, allowed = S.CLASSIFIED, frozenset({S.ASSIGNED})


class AssignedState(IncidentState):
    # ASSIGNED → ASSIGNED is a re-assignment (escalation); → CLASSIFIED is a decline.
    status, allowed = S.ASSIGNED, frozenset({S.ACKNOWLEDGED, S.CLASSIFIED, S.ASSIGNED})


class AcknowledgedState(IncidentState):
    status, allowed = S.ACKNOWLEDGED, frozenset({S.IN_PROGRESS})

    def on_enter(self, ctx, previous):
        ctx.acknowledged_at = ctx.acknowledged_at or utcnow()


class InProgressState(IncidentState):
    status, allowed = S.IN_PROGRESS, frozenset({S.AWAITING_INFO, S.RESOLVED})

    def on_enter(self, ctx, previous):
        if previous == S.RESOLVED:  # re-opened by the reporter
            ctx.resolved_at = None


class AwaitingInfoState(IncidentState):
    status, allowed = S.AWAITING_INFO, frozenset({S.IN_PROGRESS})


class ResolvedState(IncidentState):
    status, allowed = S.RESOLVED, frozenset({S.VERIFIED, S.IN_PROGRESS})

    def on_enter(self, ctx, previous):
        ctx.resolved_at = utcnow()


class VerifiedState(IncidentState):
    status, allowed = S.VERIFIED, frozenset({S.CLOSED})

    def on_enter(self, ctx, previous):
        ctx.verified_at = utcnow()


class ClosedState(IncidentState):
    status, allowed = S.CLOSED, frozenset()

    def on_enter(self, ctx, previous):
        ctx.closed_at = utcnow()


class StateRegistry:
    """Flyweight registry: states are stateless, so one instance per status is shared."""
    _states: dict[S, IncidentState] = {
        cls.status: cls() for cls in (
            NewState, ClassifiedState, AssignedState, AcknowledgedState, InProgressState,
            AwaitingInfoState, ResolvedState, VerifiedState, ClosedState,
        )
    }

    @classmethod
    def get(cls, status: S | str) -> IncidentState:
        return cls._states[S(status)]

    @classmethod
    def graph(cls) -> dict[str, list[str]]:
        return {s.value: sorted(t.value for t in st.allowed) for s, st in cls._states.items()}
