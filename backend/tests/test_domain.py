"""Unit tests for domain logic (no HTTP)."""
from datetime import timedelta

import pytest

from app.domain.assignment import LoadBasedStrategy, RoundRobinStrategy
from app.domain.enums import IncidentStatus as S, Level, Priority
from app.domain.exceptions import (
    InvalidStateTransitionError, MissingSLAConfigurationError, TechnicianWorkloadExceededError,
)
from app.domain.intelligence import CategoryClassifier, DuplicateDetector
from app.domain.lifecycle import StateRegistry
from app.domain.priority import PriorityInput, UserImpactWeightedStrategy, WeightedScoreStrategy
from app.models import AuditLog, Employee, Incident, SLAPolicy, SLAViolation, Technician
from app.repositories import CategoryRepository, UserRepository
from app.services.incident_service import IncidentService, build_event_bus
from app.services.sla import SLAMonitor


# TC-01  Priority boundaries ---------------------------------------------------------
@pytest.mark.parametrize("score,expected", [
    (12, Priority.P1), (6.0, Priority.P1), (5.99, Priority.P2), (3.5, Priority.P2),
    (3.49, Priority.P3), (2.0, Priority.P3), (1.99, Priority.P4), (1.0, Priority.P4),
])
def test_priority_threshold_boundaries(score, expected):
    assert WeightedScoreStrategy().classify(score) == expected


# TC-02  Formula + polymorphic strategies ---------------------------------------------
def test_priority_formula_and_strategy_polymorphism():
    data = PriorityInput(Level.HIGH, Level.HIGH, 3.0, affected_users=100)
    weighted = WeightedScoreStrategy().calculate(data)
    boosted = UserImpactWeightedStrategy().calculate(data)
    assert weighted.score == 12.0 and weighted.priority == Priority.P1
    assert boosted.score == 24.0  # 100 users → 2x
    low = WeightedScoreStrategy().calculate(PriorityInput(Level.LOW, Level.LOW, 1.0))
    assert low.priority == Priority.P4


# TC-03  State pattern rejects illegal transitions ---------------------------------------
def test_state_machine_blocks_new_to_closed():
    inc = Incident(status=S.NEW.value)
    with pytest.raises(InvalidStateTransitionError):
        inc.transition_to(S.CLOSED)
    inc.transition_to(S.CLASSIFIED)
    assert inc.status == "CLASSIFIED"
    assert StateRegistry.get(S.CLOSED).is_terminal


def test_state_hooks_set_timestamps():
    inc = Incident(status=S.IN_PROGRESS.value)
    inc.transition_to(S.RESOLVED)
    assert inc.resolved_at is not None
    inc.transition_to(S.IN_PROGRESS)  # reopen clears resolution time
    assert inc.resolved_at is None


# TC-04  Assignment strategies ---------------------------------------------------------
def test_load_based_and_round_robin(db):
    svc = IncidentService(db)
    inc = svc.incidents.get(5)  # any incident
    techs = UserRepository(db).technicians()
    inc.category = None  # no skill filter
    least = LoadBasedStrategy().select(inc, techs)
    assert least.workload == min(t.workload for t in techs if t.has_capacity())

    store = {}
    kv = type("KV", (), {"get": lambda s, k, d="": store.get(k, d),
                         "set": lambda s, k, v: store.__setitem__(k, v)})()
    rr = RoundRobinStrategy(kv)
    picks = [rr.select(inc, techs).id for _ in range(len(techs) + 1)]
    assert picks[0] != picks[1] and picks[0] == picks[len(techs)]


def test_workload_exceeded(db):
    techs = UserRepository(db).technicians()
    for t in techs:
        t.max_workload = t.workload  # everybody full
    inc = IncidentService(db).incidents.get(5)
    with pytest.raises(TechnicianWorkloadExceededError):
        LoadBasedStrategy().select(inc, techs)


# TC-05  Intelligence ------------------------------------------------------------------
def test_category_suggestion():
    cats = [type("C", (), {"code": "AUTHENTICATION", "name": "Auth",
                           "keywords": ["login", "password", "locked"]})(),
            type("C", (), {"code": "NETWORK", "name": "Net", "keywords": ["wifi", "vpn"]})()]
    res = CategoryClassifier().suggest("I cannot login, my password is locked", cats)
    assert res[0].code == "AUTHENTICATION"


def test_duplicate_detection_payment_examples():
    det = DuplicateDetector()
    mk = lambda id_, t: type("I", (), {"id": id_, "title": t, "description": "", "service_id": 1})()  # noqa
    existing = [mk(101, "Payment application unavailable"), mk(102, "Printer out of toner")]
    found = det.find("Unable to make payment", "", 1, existing)
    assert found and found[0].incident.id == 101
    assert all(m.incident.id != 102 for m in found if m.link_type == "DUPLICATE")


# TC-06  SLA -----------------------------------------------------------------------------
def test_missing_sla_configuration(db):
    db.query(Incident).update({Incident.sla_policy_id: None})
    db.query(SLAPolicy).delete()
    db.flush()
    svc = IncidentService(db)
    emp = UserRepository(db).by_email("rohan@example.com")
    with pytest.raises(MissingSLAConfigurationError):
        svc.create(emp, title="Printer jammed again", description="Paper stuck inside printer",
                   service_id=8, impact="LOW", urgency="LOW", force=True)


def test_sla_monitor_detects_violation_and_escalates(db):
    svc = IncidentService(db)
    emp = UserRepository(db).by_email("vikram@example.com")
    inc = svc.create(emp, title="Database cluster down", description="Primary database unreachable from all apps",
                     service_id=2, impact="HIGH", urgency="HIGH", affected_users=500, force=True)
    db.flush()
    assert inc.priority == "P1" and inc.status == "ASSIGNED"
    later = inc.response_due + timedelta(minutes=1)
    stats = SLAMonitor(db, build_event_bus(db)).run(at=later)
    assert stats["violations"] >= 1 and inc.response_breached
    assert db.query(SLAViolation).filter_by(incident_id=inc.id).count() == 1
    assert inc.escalation_level == 1 and inc.technician.is_team_lead
    assert db.query(AuditLog).filter_by(incident_id=inc.id, action="INCIDENT_ESCALATED").count() == 1


# TC-07  Polymorphic users ----------------------------------------------------------------
def test_user_polymorphism(db):
    users = UserRepository(db)
    emp, tech = users.by_email("rohan@example.com"), users.by_email("ravi@example.com")
    adm = users.by_email("admin@example.com")
    assert isinstance(emp, Employee) and isinstance(tech, Technician)
    assert {emp.dashboard(), tech.dashboard(), adm.dashboard()} == {"employee", "technician", "admin"}
    assert emp.can("incident:create") and not emp.can("audit:view") and adm.can("audit:view")
    assert tech.verify_password("Password123") and not tech.verify_password("wrong")


def test_new_category_without_code_change(db):
    from app.models import Category
    db.add(Category(code="PRINTING", name="Printing", keywords=["printer", "toner"]))
    db.flush()
    res = CategoryClassifier().suggest("printer toner empty", CategoryRepository(db).active())
    assert "PRINTING" in [r.code for r in res]
