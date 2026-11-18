"""Custom exception hierarchy.

Every business error derives from ITSMError, which carries an HTTP status and a
machine-readable code. A single FastAPI exception handler converts any ITSMError
into a JSON response, so the domain layer never depends on the web framework.
"""


class ITSMError(Exception):
    status_code: int = 400
    code: str = "ITSM_ERROR"

    def __init__(self, message: str = "", **details):
        super().__init__(message or self.__class__.__doc__ or self.code)
        self.message = message or (self.__class__.__doc__ or self.code).strip()
        self.details = details

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "details": self.details}


# --- Authentication / authorization -------------------------------------------------
class InvalidLoginError(ITSMError):
    """Invalid email or password."""
    status_code, code = 401, "INVALID_LOGIN"


class AuthenticationRequiredError(ITSMError):
    """Authentication is required."""
    status_code, code = 401, "AUTH_REQUIRED"


class UnauthorizedOperationError(ITSMError):
    """You are not allowed to perform this operation."""
    status_code, code = 403, "UNAUTHORIZED_OPERATION"


# --- Validation ------------------------------------------------------------------
class InvalidUserInputError(ITSMError):
    """Invalid input."""
    status_code, code = 422, "INVALID_INPUT"


class DuplicateEntityError(ITSMError):
    """Entity already exists."""
    status_code, code = 409, "DUPLICATE_ENTITY"


# --- Incident domain -------------------------------------------------------------
class IncidentNotFoundError(ITSMError):
    """Incident not found."""
    status_code, code = 404, "INCIDENT_NOT_FOUND"


class InvalidIncidentError(ITSMError):
    """The incident data is invalid."""
    status_code, code = 422, "INVALID_INCIDENT"


class InvalidStateTransitionError(ITSMError):
    """This status change is not allowed from the current state."""
    status_code, code = 409, "INVALID_STATE_TRANSITION"


class DuplicateIncidentError(ITSMError):
    """A near-identical incident was already reported."""
    status_code, code = 409, "DUPLICATE_INCIDENT"


# --- Assignment ------------------------------------------------------------------
class TechnicianUnavailableError(ITSMError):
    """No suitable technician is available."""
    status_code, code = 409, "TECHNICIAN_UNAVAILABLE"


class TechnicianWorkloadExceededError(ITSMError):
    """All suitable technicians have reached their maximum workload."""
    status_code, code = 409, "WORKLOAD_EXCEEDED"


# --- Configuration -----------------------------------------------------------------
class ServiceNotFoundError(ITSMError):
    """IT service not found."""
    status_code, code = 404, "SERVICE_NOT_FOUND"


class CategoryNotFoundError(ITSMError):
    """Incident category not found."""
    status_code, code = 404, "CATEGORY_NOT_FOUND"


class UserNotFoundError(ITSMError):
    """User not found."""
    status_code, code = 404, "USER_NOT_FOUND"


class MissingSLAConfigurationError(ITSMError):
    """No SLA policy is configured for this service/priority."""
    status_code, code = 500, "MISSING_SLA_CONFIGURATION"


# --- Infrastructure -----------------------------------------------------------------
class DatabaseFailureError(ITSMError):
    """The database is currently unavailable."""
    status_code, code = 503, "DATABASE_FAILURE"


class NetworkFailureError(ITSMError):
    """An external service could not be reached."""
    status_code, code = 502, "NETWORK_FAILURE"
