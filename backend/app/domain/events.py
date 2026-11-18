"""OBSERVER PATTERN — domain events.

The IncidentService publishes a DomainEvent whenever something important happens.
Observers (AuditObserver, NotificationObserver, …) subscribe to the EventBus and react
independently. Adding a new reaction (e.g. a Slack webhook, a metrics counter) means
adding one observer class — the incident logic is never touched.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .enums import EventType

log = logging.getLogger("itsm.events")


@dataclass
class DomainEvent:
    type: EventType
    incident: Any | None
    actor: Any | None
    description: str
    previous_state: str | None = None
    new_state: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class IncidentObserver(ABC):
    """Observer interface."""

    @abstractmethod
    def notify(self, event: DomainEvent) -> None: ...


class EventBus:
    """Subject. Keeps observers in a list (ordered: audit first, then notifications)."""

    def __init__(self) -> None:
        self._observers: list[IncidentObserver] = []

    def subscribe(self, observer: IncidentObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: IncidentObserver) -> None:
        self._observers.remove(observer)

    def publish(self, event: DomainEvent) -> None:
        for obs in self._observers:
            try:
                obs.notify(event)
            except Exception:  # one failing observer must not break the others
                log.exception("Observer %s failed on %s", type(obs).__name__, event.type)
