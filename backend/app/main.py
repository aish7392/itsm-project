"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from . import database
from .api import admin, auth, incidents, misc
from .config import settings
from .domain.exceptions import ITSMError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("itsm")


def run_sla_monitor_once() -> None:
    """One SLA pass: warnings, violations, escalation."""
    from .services.incident_service import build_event_bus
    from .services.sla import SLAMonitor

    db = database.SessionLocal()
    try:
        stats = SLAMonitor(db, build_event_bus(db)).run()
        db.commit()
        if stats["warnings"] or stats["violations"] or stats["escalations"]:
            log.info("SLA monitor: %s", stats)
    except Exception:
        db.rollback()
        log.exception("SLA monitor run failed")
    finally:
        db.close()


async def sla_monitor_loop():
    """Background SLA monitoring for long-running servers (local / Docker)."""
    while True:
        await asyncio.sleep(settings.sla_monitor_interval_seconds)
        await asyncio.to_thread(run_sla_monitor_once)


def seed_if_empty() -> None:
    from .seed import seed

    db = database.SessionLocal()
    try:
        seed(db)
        db.commit()
    except Exception:  # another instance may be seeding at the same moment
        db.rollback()
        log.exception("Auto-seed skipped")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    if settings.auto_seed:
        seed_if_empty()
    task = asyncio.create_task(sla_monitor_loop()) if settings.enable_background_jobs else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="I-ITSM – Intelligent IT Service Management",
    version="1.0.0",
    description="Incident reporting, prioritisation, assignment, SLA monitoring and analytics.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex or None, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

_last_sla_run = 0.0


@app.middleware("http")
async def sla_check_on_request(request: Request, call_next):
    """Serverless mode: piggy-back the SLA check on API traffic (at most every N seconds).
    The UI polls notifications every 15 s, so an open browser keeps the monitor ticking."""
    global _last_sla_run
    if (settings.sla_check_on_request and request.url.path.startswith("/api")
            and time.monotonic() - _last_sla_run >= settings.sla_monitor_interval_seconds):
        _last_sla_run = time.monotonic()
        await asyncio.to_thread(run_sla_monitor_once)
    return await call_next(request)


@app.exception_handler(ITSMError)
async def itsm_error_handler(_: Request, exc: ITSMError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
              for e in exc.errors()]
    msg = "; ".join(f"{e['field']}: {e['message']}" for e in errors)
    return JSONResponse(status_code=422, content={
        "error": "INVALID_INPUT", "message": msg or "Invalid input", "details": {"errors": errors}})


@app.exception_handler(OperationalError)
async def db_error_handler(_: Request, exc: OperationalError):
    log.error("Database failure: %s", exc)
    return JSONResponse(status_code=503, content={
        "error": "DATABASE_FAILURE", "message": "The database is currently unavailable",
        "details": {}})


for r in (auth.router, incidents.router, admin.router, misc.reports, misc.notifications, misc.meta):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok"}
