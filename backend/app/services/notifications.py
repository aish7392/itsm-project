"""Notifications: FACTORY + ADAPTER + OBSERVER.

NotificationChannel (interface)
 ├─ InAppChannel   – stores a Notification row; the UI polls /notifications
 └─ EmailChannel   – writes to the email outbox and sends through an EmailGateway

EmailGateway (target interface for the ADAPTER pattern)
 ├─ SmtpEmailAdapter       – adapts Python's smtplib (works with Gmail app passwords etc.)
 └─ SimulatedEmailAdapter  – logs the email (default when SMTP_HOST is not configured)

NotificationChannelFactory creates channels by name, so adding SMS/Push later means
writing one class and registering it — nothing else changes.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.message import EmailMessage

from sqlalchemy.orm import Session

from ..config import settings
from ..domain.enums import AdminTitle, ChannelType, EventType as E
from ..domain.events import DomainEvent, IncidentObserver
from ..domain.exceptions import NetworkFailureError
from ..models import AuditLog, EmailOutbox, Notification, User
from ..repositories import UserRepository

log = logging.getLogger("itsm.notify")


# ─────────────────────────────── ADAPTER: e-mail gateways ──────────────────────────────
class EmailGateway(ABC):
    simulated: bool = False

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpEmailAdapter(EmailGateway):
    """Adapts smtplib's API to our EmailGateway contract."""

    def __init__(self, host: str, port: int, user: str, password: str, sender: str):
        self.host, self.port, self.user, self.password, self.sender = host, port, user, password, sender

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            raise NetworkFailureError(f"SMTP delivery failed: {exc}") from exc


class SimulatedEmailAdapter(EmailGateway):
    simulated = True

    def send(self, to: str, subject: str, body: str) -> None:
        log.info("[SIMULATED EMAIL] to=%s subject=%s", to, subject)


def default_email_gateway() -> EmailGateway:
    if settings.smtp_host:
        return SmtpEmailAdapter(settings.smtp_host, settings.smtp_port, settings.smtp_user,
                                settings.smtp_password, settings.smtp_sender)
    return SimulatedEmailAdapter()


# ─────────────────────────────── channels (polymorphic) ────────────────────────────────
class NotificationChannel(ABC):
    channel_type: ChannelType

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def deliver(self, user: User, event: DomainEvent, subject: str, message: str) -> None: ...


class InAppChannel(NotificationChannel):
    channel_type = ChannelType.IN_APP

    def deliver(self, user, event, subject, message):
        self.db.add(Notification(
            user_id=user.id, incident_id=event.incident.id if event.incident else None,
            channel=self.channel_type.value, event=event.type.value, message=message))


RESERVED_DOMAINS = {"example.com", "example.org", "example.net"}


class EmailChannel(NotificationChannel):
    channel_type = ChannelType.EMAIL

    def __init__(self, db: Session, gateway: EmailGateway | None = None):
        super().__init__(db)
        self.gateway = gateway or default_email_gateway()

    def deliver(self, user, event, subject, message):
        body = f"Hello {user.name},\n\n{message}\n\n— I-ITSM Service Desk"
        # reserved demo domains (RFC 2606) can never receive mail: simulate instead of bouncing
        demo = user.email.lower().rsplit("@", 1)[-1] in RESERVED_DOMAINS
        row = EmailOutbox(recipient=user.email, subject=subject, body=body,
                          simulated=self.gateway.simulated or demo)
        if demo:
            row.delivered = True
            self.db.add(row)
            return
        try:
            self.gateway.send(user.email, subject, body)
            row.delivered = True
        except NetworkFailureError as exc:  # never break the business transaction
            row.error = exc.message
            log.warning(exc.message)
        self.db.add(row)


class NotificationChannelFactory:
    _registry: dict[ChannelType, type[NotificationChannel]] = {
        ChannelType.IN_APP: InAppChannel,
        ChannelType.EMAIL: EmailChannel,
    }

    @classmethod
    def register(cls, kind: ChannelType, channel_cls: type[NotificationChannel]) -> None:
        cls._registry[kind] = channel_cls

    @classmethod
    def create(cls, kind: ChannelType, db: Session) -> NotificationChannel:
        return cls._registry[kind](db)


# ─────────────────────────────── OBSERVERS ─────────────────────────────────────────────
class AuditObserver(IncidentObserver):
    """Writes every domain event to the immutable audit trail."""

    def __init__(self, db: Session):
        self.db = db

    def notify(self, event: DomainEvent) -> None:
        self.db.add(AuditLog(
            user_id=event.actor.id if event.actor else None,
            incident_id=event.incident.id if event.incident else None,
            action=event.type.value,
            previous_state=event.previous_state, new_state=event.new_state,
            description=event.description))


EMAIL_EVENTS = {E.INCIDENT_ASSIGNED, E.INFO_REQUESTED, E.INCIDENT_RESOLVED,
                E.INCIDENT_CLOSED, E.SLA_VIOLATED, E.INCIDENT_ESCALATED}


class NotificationObserver(IncidentObserver):
    """Decides *who* hears about an event and over *which* channels."""

    def __init__(self, db: Session, channels: list[NotificationChannel] | None = None):
        self.db = db
        self.users = UserRepository(db)
        self.channels = channels or [
            NotificationChannelFactory.create(ChannelType.IN_APP, db),
            NotificationChannelFactory.create(ChannelType.EMAIL, db),
        ]

    def recipients(self, ev: DomainEvent) -> set[User]:
        inc = ev.incident
        reporter = inc.reporter if inc else None
        tech = inc.technician if inc else None
        admins = set(self.users.admins())
        t = ev.type
        r: set = set()
        if t in (E.INCIDENT_CREATED, E.INFO_REQUESTED, E.STATUS_CHANGED, E.INCIDENT_RESOLVED,
                 E.INCIDENT_VERIFIED):
            r |= {reporter}
        if t == E.INCIDENT_ASSIGNED:
            r |= {tech, reporter}
        if t in (E.INFO_PROVIDED, E.FEEDBACK_GIVEN, E.INCIDENT_REOPENED, E.INCIDENT_UPDATED):
            r |= {tech}
        if t in (E.INCIDENT_CLOSED, E.PRIORITY_CHANGED):
            r |= {reporter, tech}
        if t == E.SLA_WARNING:
            r |= {tech, *self.users.team_leads()}
        if t == E.SLA_VIOLATED:
            r |= {tech, *admins}
        if t in (E.INCIDENT_DECLINED, E.DUPLICATE_DETECTED, E.CORRELATION_DETECTED,
                 E.ASSIGNMENT_FAILED):
            r |= admins
        if t == E.INCIDENT_ESCALATED:
            r |= set(ev.payload.get("recipients", []))
        if t == E.INCIDENT_CREATED and inc and inc.priority == "P1":
            r |= set(self.users.admins(AdminTitle.IT_MANAGER.value))
        r.discard(None)
        if ev.actor is not None and t not in (E.INCIDENT_CREATED,):
            r.discard(ev.actor)  # don't notify people about their own actions
        return r

    def notify(self, event: DomainEvent) -> None:
        if event.type in (E.NOTE_ADDED, E.INCIDENT_CLASSIFIED, E.PRIORITY_CALCULATED):
            return  # audit-only events
        inc = event.incident
        subject = f"[{inc.code}] {event.type.value.replace('_', ' ').title()}" if inc else event.type.value
        message = f"{inc.code} – {inc.title}: {event.description}" if inc else event.description
        for user in self.recipients(event):
            for ch in self.channels:
                if ch.channel_type == ChannelType.EMAIL and event.type not in EMAIL_EVENTS:
                    continue
                ch.deliver(user, event, subject, message)
