"""Application configuration, read from environment variables (12-factor style)."""
import os
from dataclasses import dataclass, field

ON_VERCEL = bool(os.getenv("VERCEL"))  # Vercel sets VERCEL=1 in its functions


def _db_url() -> str:
    """Accept the plain postgres:// URLs that Neon/Vercel give and use the psycopg 3 driver."""
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or \
        "postgresql+psycopg://itsm:itsm@localhost:5432/itsm"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _flag(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=_db_url)
    serverless: bool = ON_VERCEL
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production-please-32b")
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = int(os.getenv("JWT_EXPIRY_MINUTES", "480"))

    # SLA monitor background job
    sla_monitor_interval_seconds: int = int(os.getenv("SLA_MONITOR_INTERVAL", "30"))
    sla_warning_threshold: float = float(os.getenv("SLA_WARNING_THRESHOLD", "0.75"))
    # Long-running servers (local, Docker) use a background loop. Serverless hosts such as
    # Vercel freeze idle functions, so there the check runs on incoming requests instead.
    enable_background_jobs: bool = _flag("ENABLE_BACKGROUND_JOBS", not ON_VERCEL)
    sla_check_on_request: bool = _flag("SLA_CHECK_ON_REQUEST", ON_VERCEL)
    auto_seed: bool = _flag("AUTO_SEED", ON_VERCEL)

    # Email (SMTP). If SMTP_HOST is empty, emails are simulated (stored in outbox + logged).
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_sender: str = os.getenv("SMTP_SENDER", "itsm@example.com")

    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
        ).split(",")
    )
    # any *.vercel.app frontend may call the API; override with CORS_ORIGIN_REGEX to lock down
    cors_origin_regex: str = field(
        default_factory=lambda: os.getenv("CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    )


settings = Settings()
