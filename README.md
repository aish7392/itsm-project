# I-ITSM — Intelligent IT Service Management & Incident Resolution System

CS F213 OOP project · **React + Python (FastAPI) + PostgreSQL**

Employees report IT problems; the system classifies them, scores priority
(`Impact × Urgency × Business Criticality`), applies the right SLA, picks a technician,
notifies people, monitors deadlines in the background, escalates automatically, detects
duplicate / correlated incidents and keeps a full audit trail.

---

## Quick start

### Option A — Docker (one command)
```bash
docker compose up --build
```
* App: http://localhost:3000  · API docs (Swagger): http://localhost:8000/docs

### Option B — run locally
```bash
# 1. PostgreSQL
createuser -P itsm            # password: itsm
createdb -O itsm itsm

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.seed            # creates tables + demo data   (--reset to rebuild)
uvicorn app.main:app --reload # http://localhost:8000/docs

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173  (proxies /api → :8000)
```

### Demo accounts (password `Password123`)
| Role | Email | Notes |
|---|---|---|
| Employee | rohan@example.com, neha@example.com, vikram@example.com | |
| Technician | priya@example.com *(team lead)*, sneha@example.com *(team lead)*, arjun@, ravi@, karan@ | different skills |
| Administrator | admin@example.com | System admin |
| IT Manager | manager@example.com | top of escalation chain |

Type the email and password on the login page (there are no one-click demo shortcuts in this version).

**Fresh demo data:** `docker compose down -v` then `docker compose up --build` (Docker), or `python -m app.seed --reset` (manual). Do this right before recording the video.

### Deploy online (Vercel)
See **[DEPLOY_VERCEL.md](DEPLOY_VERCEL.md)**: two Vercel projects (backend + frontend) and a free Neon PostgreSQL database.

### Tests
```bash
cd backend && pip install -r requirements-dev.txt && pytest   # 36 tests on SQLite
TEST_DATABASE_URL=postgresql+psycopg://itsm:itsm@localhost:5432/itsm_test pytest   # on PostgreSQL
```

### Real e-mail (optional)
Copy `backend/.env.example` and set `SMTP_HOST/USER/PASSWORD` (e.g. Gmail + App Password).
Without it, emails are **simulated**: written to the `email_outbox` table and visible
under *Admin → Email outbox*.

---

## Project structure
```
itsm/
├── docker-compose.yml
├── docs/REPORT.md                 ← project report (requirements, UML, design, tests)
├── backend/
│   ├── app/
│   │   ├── main.py                FastAPI app, error handlers, background SLA monitor
│   │   ├── config.py · database.py · security.py (JWT + RBAC) · schemas.py (validation)
│   │   ├── models.py              ORM entities: User ▸ Employee/Technician/Administrator, Incident, …
│   │   ├── domain/                pure business logic (no web / DB code)
│   │   │   ├── exceptions.py      custom exception hierarchy (ITSMError → 17 subclasses)
│   │   │   ├── enums.py           Role, IncidentStatus, Level, Priority, EventType …
│   │   │   ├── lifecycle.py       STATE pattern — incident lifecycle
│   │   │   ├── priority.py        STRATEGY pattern — priority algorithms
│   │   │   ├── assignment.py      STRATEGY pattern — load / round-robin / skill-based
│   │   │   ├── events.py          OBSERVER pattern — EventBus + IncidentObserver
│   │   │   └── intelligence.py    duplicate detection, categorisation, resolution suggestions
│   │   ├── repositories/          REPOSITORY pattern — all SQL lives here
│   │   ├── services/
│   │   │   ├── incident_service.py  orchestrates the lifecycle
│   │   │   ├── factories.py       FACTORY pattern — users & incidents
│   │   │   ├── notifications.py   ADAPTER (SMTP) + FACTORY (channels) + observers
│   │   │   ├── sla.py             SLA calc, monitor, CHAIN OF RESPONSIBILITY escalation
│   │   │   └── reports.py         dashboards & analytics
│   │   ├── api/                   REST routers (auth, incidents, admin, reports, notifications)
│   │   └── seed.py                demo data
│   └── tests/                     36 unit + integration tests
└── frontend/
    └── src/
        ├── App.jsx                role-based routing
        ├── api.js · auth.jsx      REST client + auth context
        ├── components/            Layout, NotificationBell, tables, badges, charts
        └── pages/                 Employee / Technician / Admin screens, IncidentDetail
```

## Demo workflows (for the video)
1. **Employee reports → system prioritises → technician assigned → notified**
   Log in as *rohan*, *Report an incident* (watch the assistant suggest category / similar
   incidents / past fixes), submit → detail page shows P-score, SLA policy, assignee, audit trail.
2. **Technician investigates → SLA monitored → resolved → user notified**
   Log in as the assigned technician: Accept → Start → note → Request info; as *rohan* reply;
   technician Resolves; *rohan* verifies with ★ rating; admin/technician closes.
3. **Multiple incidents → duplicates / correlation → escalation**
   As *neha* report "Unable to make payment" on *Payment Gateway* → linked to INC1004;
   Admin dashboard shows the correlated cluster. Leave a P1 un-acknowledged for a few minutes
   (Payment Gateway P1 SLA is 3 min) or press **Run SLA check now** → warning, violation,
   escalation Technician → Team Lead → System Admin → IT Manager.
