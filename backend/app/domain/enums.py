"""Value enumerations shared across the domain."""
from enum import Enum


class Role(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    TECHNICIAN = "TECHNICIAN"
    ADMIN = "ADMIN"


class AdminTitle(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    IT_MANAGER = "IT_MANAGER"


class IncidentStatus(str, Enum):
    NEW = "NEW"
    CLASSIFIED = "CLASSIFIED"
    ASSIGNED = "ASSIGNED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_INFO = "AWAITING_INFO"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"


ACTIVE_STATUSES = {
    IncidentStatus.NEW, IncidentStatus.CLASSIFIED, IncidentStatus.ASSIGNED,
    IncidentStatus.ACKNOWLEDGED, IncidentStatus.IN_PROGRESS, IncidentStatus.AWAITING_INFO,
}
# statuses that count against a technician's workload
WORKLOAD_STATUSES = {
    IncidentStatus.ASSIGNED, IncidentStatus.ACKNOWLEDGED,
    IncidentStatus.IN_PROGRESS, IncidentStatus.AWAITING_INFO,
}


class Level(str, Enum):
    """Used for both Impact and Urgency."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def weight(self) -> float:
        return {"LOW": 1.0, "MEDIUM": 1.5, "HIGH": 2.0}[self.value]


class Priority(str, Enum):
    P1 = "P1"  # Critical
    P2 = "P2"  # High
    P3 = "P3"  # Medium
    P4 = "P4"  # Low

    @property
    def label(self) -> str:
        return {"P1": "Critical", "P2": "High", "P3": "Medium", "P4": "Low"}[self.value]


class SLAState(str, Enum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    MET = "MET"


class ViolationType(str, Enum):
    RESPONSE = "RESPONSE"
    RESOLUTION = "RESOLUTION"


class NoteKind(str, Enum):
    INVESTIGATION = "INVESTIGATION"
    INFO_REQUEST = "INFO_REQUEST"
    INFO_RESPONSE = "INFO_RESPONSE"
    COMMENT = "COMMENT"


class LinkType(str, Enum):
    DUPLICATE = "DUPLICATE"
    CORRELATED = "CORRELATED"


class ChannelType(str, Enum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"


class EventType(str, Enum):
    INCIDENT_CREATED = "INCIDENT_CREATED"
    INCIDENT_CLASSIFIED = "INCIDENT_CLASSIFIED"
    PRIORITY_CALCULATED = "PRIORITY_CALCULATED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    INCIDENT_ASSIGNED = "INCIDENT_ASSIGNED"
    INCIDENT_DECLINED = "INCIDENT_DECLINED"
    STATUS_CHANGED = "STATUS_CHANGED"
    NOTE_ADDED = "NOTE_ADDED"
    INFO_REQUESTED = "INFO_REQUESTED"
    INFO_PROVIDED = "INFO_PROVIDED"
    INCIDENT_UPDATED = "INCIDENT_UPDATED"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED"
    INCIDENT_REOPENED = "INCIDENT_REOPENED"
    INCIDENT_VERIFIED = "INCIDENT_VERIFIED"
    INCIDENT_CLOSED = "INCIDENT_CLOSED"
    FEEDBACK_GIVEN = "FEEDBACK_GIVEN"
    SLA_WARNING = "SLA_WARNING"
    SLA_VIOLATED = "SLA_VIOLATED"
    INCIDENT_ESCALATED = "INCIDENT_ESCALATED"
    ASSIGNMENT_FAILED = "ASSIGNMENT_FAILED"
    DUPLICATE_DETECTED = "DUPLICATE_DETECTED"
    CORRELATION_DETECTED = "CORRELATION_DETECTED"
