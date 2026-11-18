"""Seed the database with demo data.   Usage:  python -m app.seed  [--reset]

All demo accounts use the password:  Password123
"""
from __future__ import annotations

import sys

from sqlalchemy.orm import Session

from . import database
from .database import Base
from .domain.enums import AdminTitle, Role
from .models import Category, ITService, SLAPolicy, User
from .repositories import ConfigRepository, UserRepository
from .services.factories import UserFactory
from .services.incident_service import IncidentService

PASSWORD = "Password123"

SERVICES = [
    ("Payment Gateway", "Online payment & transaction processing", 3.0),
    ("Core Database", "Primary PostgreSQL cluster", 3.0),
    ("Authentication (SSO)", "Single sign-on, MFA and directory", 2.5),
    ("Corporate Email", "Outlook / Exchange mail service", 2.0),
    ("ERP Application", "Finance, HR and procurement system", 2.0),
    ("Cloud Storage", "OneDrive / SharePoint / file shares", 1.5),
    ("Corporate Network", "LAN, Wi-Fi and VPN", 1.0),
    ("End-User Devices", "Laptops, desktops, printers", 1.0),
]

CATEGORIES = [
    ("HARDWARE", "Hardware", "laptop desktop printer monitor keyboard mouse device hardware battery screen"),
    ("SOFTWARE", "Software", "install installation license update software excel word office crash"),
    ("NETWORK", "Network", "network wifi internet vpn lan dns connectivity ethernet router"),
    ("DATABASE", "Database", "database db sql query postgres replication deadlock table"),
    ("CLOUD", "Cloud", "cloud aws azure gcp kubernetes container vm instance"),
    ("SECURITY", "Security", "security phishing virus malware breach suspicious ransomware spam"),
    ("AUTHENTICATION", "Authentication", "login password sso mfa otp locked account authenticate credentials"),
    ("APPLICATION", "Application", "application app payment portal erp website page transaction checkout outlook email mail inbox teams"),
    ("STORAGE", "Storage", "storage disk quota sharepoint onedrive backup file drive space"),
    ("OTHER", "Other", ""),
]

# (priority, response minutes, resolution minutes) – matches the assignment brief
DEFAULT_SLA = [("P1", 5, 30), ("P2", 15, 120), ("P3", 60, 480), ("P4", 240, 1440)]

TECHNICIANS = [
    ("Ravi Kumar", "ravi@example.com", ["NETWORK", "HARDWARE"], 5, False, 4),
    ("Priya Sharma", "priya@example.com", ["DATABASE", "CLOUD", "STORAGE"], 5, True, 8),
    ("Arjun Mehta", "arjun@example.com", ["APPLICATION", "SOFTWARE", "DATABASE"], 5, False, 3),
    ("Sneha Iyer", "sneha@example.com", ["AUTHENTICATION", "SECURITY", "NETWORK"], 5, True, 6),
    ("Karan Singh", "karan@example.com", ["HARDWARE", "SOFTWARE", "APPLICATION"], 4, False, 2),
]

EMPLOYEES = [
    ("Rohan Verma", "rohan@example.com", "Finance"),
    ("Neha Gupta", "neha@example.com", "Sales"),
    ("Vikram Rao", "vikram@example.com", "Operations"),
]


def seed(db: Session) -> None:
    users = UserRepository(db)
    if users.by_email("admin@example.com"):
        print("Database already seeded – skipping (use --reset to rebuild).")
        return

    services = {}
    for name, desc, crit in SERVICES:
        s = ITService(name=name, description=desc, criticality=crit)
        db.add(s); services[name] = s
    for code, name, kws in CATEGORIES:
        db.add(Category(code=code, name=name, keywords=kws.split()))
    db.flush()
    for prio, resp, res in DEFAULT_SLA:
        db.add(SLAPolicy(name=f"Default {prio}", priority=prio, response_minutes=resp,
                         resolution_minutes=res))
    # stricter service-specific policy
    db.add(SLAPolicy(name="Payment Gateway P1 (Gold)", priority="P1",
                     service_id=services["Payment Gateway"].id, response_minutes=3,
                     resolution_minutes=20))
    cfg = ConfigRepository(db)
    cfg.set("assignment_strategy", "SKILL_BASED")
    cfg.set("priority_strategy", "WEIGHTED")

    users.add(UserFactory.create(Role.ADMIN, "System Admin", "admin@example.com", PASSWORD,
                                 department="IT", title=AdminTitle.SYSTEM_ADMIN.value))
    users.add(UserFactory.create(Role.ADMIN, "Meera Nair (IT Manager)", "manager@example.com",
                                 PASSWORD, department="IT", title=AdminTitle.IT_MANAGER.value))
    for name, email, skills, mx, lead, exp in TECHNICIANS:
        users.add(UserFactory.create(Role.TECHNICIAN, name, email, PASSWORD, department="IT Support",
                                     skills=skills, max_workload=mx, is_team_lead=lead,
                                     experience_years=exp))
    emps = [users.add(UserFactory.create(Role.EMPLOYEE, n, e, PASSWORD, department=d))
            for n, e, d in EMPLOYEES]
    db.flush()

    svc = IncidentService(db)
    sid = lambda n: services[n].id  # noqa: E731

    # ── historical, fully-resolved incidents (feed "suggested resolution") ──
    history = [
        (emps[1], "VPN keeps disconnecting", "VPN connection drops every few minutes when working from home",
         "Corporate Network", "MEDIUM", "MEDIUM", 1,
         "Updated VPN client to v5.2 and switched protocol to IKEv2", "Outdated VPN client"),
        (emps[2], "Cannot login to SSO portal", "Unable to login, SSO portal says password expired and account locked",
         "Authentication (SSO)", "MEDIUM", "HIGH", 1,
         "Unlocked account in AD and reset password; user enrolled in self-service reset", "Account lockout after password expiry"),
        (emps[0], "Shared drive out of space", "SharePoint finance folder says storage quota exceeded, cannot upload files",
         "Cloud Storage", "MEDIUM", "LOW", 12,
         "Increased site quota to 500 GB and archived 2023 files", "Quota limit reached"),
    ]
    for rep, title, desc, sname, imp, urg, users_n, resolution, cause in history:
        inc = svc.create(rep, title=title, description=desc, service_id=sid(sname),
                         impact=imp, urgency=urg, affected_users=users_n, force=True)
        if inc.technician:
            t = inc.technician
            svc.accept(t, inc); svc.start_work(t, inc)
            svc.add_note(t, inc, "Reproduced the issue and checked logs.")
            svc.resolve(t, inc, resolution, cause)
            svc.verify(rep, inc, 5, "Quick fix, thanks!")
            svc.close(users.by_email("admin@example.com"), inc, "Confirmed by user")

    # ── live incidents for the demo ──
    live = [
        (emps[0], "Payment application unavailable",
         "The payment application is down and users are unable to complete transactions",
         "Payment Gateway", "HIGH", "HIGH", 250),
        (emps[1], "Outlook not syncing", "Emails are not arriving in Outlook since morning, inbox not updating",
         "Corporate Email", "MEDIUM", "MEDIUM", 5),
        (emps[2], "Laptop battery not charging", "My laptop battery is not charging even when plugged in",
         "End-User Devices", "LOW", "MEDIUM", 1),
        (emps[1], "ERP report page very slow", "The ERP finance report page takes more than 2 minutes to load",
         "ERP Application", "MEDIUM", "LOW", 20),
    ]
    for rep, title, desc, sname, imp, urg, n in live:
        svc.create(rep, title=title, description=desc, service_id=sid(sname),
                   impact=imp, urgency=urg, affected_users=n, force=True)
    db.flush()
    print("Seed complete. Demo logins (password: Password123):")
    for u in db.query(User).order_by(User.id):
        print(f"  {u.role:<11} {u.email}")


def main():
    if "--reset" in sys.argv:
        from . import models  # noqa: F401
        Base.metadata.drop_all(bind=database.engine)
    database.init_db()
    db = database.SessionLocal()
    try:
        seed(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
