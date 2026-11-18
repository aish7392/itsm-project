"""Integration tests through the REST API."""
from tests.conftest import login, service_id


def new_incident(client, h, **kw):
    body = {"title": "Payment application unavailable",
            "description": "Users are unable to complete transactions on the payment page",
            "service_id": service_id(client, h, "Payment Gateway"),
            "impact": "HIGH", "urgency": "HIGH", "affected_users": 200, "force": True}
    body.update(kw)
    return client.post("/api/incidents", json=body, headers=h)


# ── authentication / authorisation ───────────────────────────────────────────────
def test_login_and_me(client):
    h = login(client, "admin@example.com")
    me = client.get("/api/auth/me", headers=h).json()
    assert me["role"] == "ADMIN" and me["dashboard"] == "admin"


def test_invalid_login(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope"})
    assert r.status_code == 401 and r.json()["error"] == "INVALID_LOGIN"


def test_register_validation_and_duplicate(client):
    weak = client.post("/api/auth/register", json={"name": "X Y", "email": "x@y.com", "password": "short"})
    assert weak.status_code == 422
    nodigit = client.post("/api/auth/register", json={"name": "X Y", "email": "x@y.com", "password": "abcdefghij"})
    assert nodigit.status_code == 422
    ok = client.post("/api/auth/register", json={"name": "X Y", "email": "x@y.com", "password": "abcdefg12"})
    assert ok.status_code == 201 and ok.json()["user"]["role"] == "EMPLOYEE"
    dup = client.post("/api/auth/register", json={"name": "X Y", "email": "X@y.com", "password": "abcdefg12"})
    assert dup.status_code == 409


def test_unauthenticated_and_forbidden(client, employee):
    assert client.get("/api/incidents").status_code == 401
    assert client.get("/api/incidents", headers={"Authorization": "Bearer garbage"}).status_code == 401
    r = client.get("/api/admin/users", headers=employee)
    assert r.status_code == 403 and r.json()["error"] == "UNAUTHORIZED_OPERATION"


def test_employee_cannot_view_others_incident(client, employee, employee2):
    inc = new_incident(client, employee).json()
    assert client.get(f"/api/incidents/{inc['id']}", headers=employee2).status_code == 403
    # and search is automatically scoped
    ids = [i["id"] for i in client.get("/api/incidents", headers=employee2).json()]
    assert inc["id"] not in ids


# ── business rules ───────────────────────────────────────────────────────────────
def test_create_incident_prioritises_assigns_and_applies_sla(client, employee):
    r = new_incident(client, employee)
    assert r.status_code == 201, r.text
    inc = r.json()
    assert inc["priority"] == "P1" and inc["priority_score"] == 12.0
    assert inc["category"]["code"] == "APPLICATION" and inc["auto_category"]
    assert inc["status"] == "ASSIGNED" and inc["technician"] is not None
    assert inc["sla_policy"]["name"] == "Payment Gateway P1 (Gold)"  # service-specific SLA wins
    actions = [a["action"] for a in inc["audit"]]
    for a in ("INCIDENT_CREATED", "INCIDENT_CLASSIFIED", "PRIORITY_CALCULATED", "INCIDENT_ASSIGNED"):
        assert a in actions


def test_invalid_incident_input(client, employee):
    assert new_incident(client, employee, title="abc").status_code == 422
    assert new_incident(client, employee, impact="EXTREME").status_code == 422
    assert new_incident(client, employee, affected_users=0).status_code == 422
    r = new_incident(client, employee, service_id=9999)
    assert r.status_code == 404 and r.json()["error"] == "SERVICE_NOT_FOUND"


def test_duplicate_incident_same_reporter(client, employee):
    first = new_incident(client, employee).json()
    again = new_incident(client, employee, force=False)
    assert again.status_code == 409 and again.json()["error"] == "DUPLICATE_INCIDENT"
    assert again.json()["details"]["existing_id"] in (4, first["id"])  # seeded INC1004 is identical too
    assert new_incident(client, employee, force=True).status_code == 201  # explicit override


def test_duplicate_detection_links_related_incidents(client, employee2, admin):
    r = new_incident(client, employee2, title="Unable to make payment",
                     description="Payment transaction failing at checkout")
    related = r.json()["related"]
    assert any(x["code"] == "INC1004" for x in related)  # seeded "Payment application unavailable"
    clusters = client.get("/api/reports/clusters", headers=admin).json()
    assert clusters and clusters[0]["size"] >= 2


def test_full_lifecycle_workflow(client, employee, admin):
    inc = new_incident(client, employee).json()
    iid = inc["id"]
    tech = login(client, inc["technician"]["email"])
    # illegal: resolve before acknowledging
    bad = client.post(f"/api/incidents/{iid}/resolve", json={"resolution": "restarted"}, headers=tech)
    assert bad.status_code == 409 and bad.json()["error"] == "INVALID_STATE_TRANSITION"
    for step in ("accept", "start"):
        assert client.post(f"/api/incidents/{iid}/{step}", headers=tech).status_code == 200
    client.post(f"/api/incidents/{iid}/notes", json={"text": "Gateway pods crash-looping"}, headers=tech)
    r = client.post(f"/api/incidents/{iid}/request-info", json={"text": "Which card type fails?"}, headers=tech)
    assert r.json()["status"] == "AWAITING_INFO"
    r = client.post(f"/api/incidents/{iid}/respond", json={"text": "All VISA cards"}, headers=employee)
    assert r.json()["status"] == "IN_PROGRESS"
    r = client.post(f"/api/incidents/{iid}/resolve",
                    json={"resolution": "Rolled back gateway release 4.2", "root_cause": "Bad deploy"}, headers=tech)
    assert r.json()["status"] == "RESOLVED"
    assert client.post(f"/api/incidents/{iid}/verify", json={"rating": 6}, headers=employee).status_code == 422
    r = client.post(f"/api/incidents/{iid}/verify", json={"rating": 5, "comment": "great"}, headers=employee)
    assert r.json()["status"] == "VERIFIED"
    r = client.post(f"/api/incidents/{iid}/close", json={"notes": "done"}, headers=admin)
    final = r.json()
    assert final["status"] == "CLOSED" and final["feedback_rating"] == 5
    trail = [(a["previous_state"], a["new_state"]) for a in final["audit"] if a["new_state"]]
    assert ("VERIFIED", "CLOSED") in trail and len(final["notes"]) == 3


def test_only_assigned_technician_can_work(client, employee):
    inc = new_incident(client, employee).json()
    others = ["ravi@example.com", "priya@example.com", "arjun@example.com", "sneha@example.com", "karan@example.com"]
    other = next(e for e in others if e != inc["technician"]["email"])
    r = client.post(f"/api/incidents/{inc['id']}/accept", headers=login(client, other))
    assert r.status_code == 403
    # employees cannot assign
    assert client.post(f"/api/incidents/{inc['id']}/assign", json={}, headers=employee).status_code == 403


def test_decline_reassigns_to_someone_else(client, employee):
    inc = new_incident(client, employee).json()
    first = inc["technician"]
    r = client.post(f"/api/incidents/{inc['id']}/decline", json={"text": "On leave"},
                    headers=login(client, first["email"]))
    body = r.json()
    assert body["status"] == "ASSIGNED" and body["technician"]["id"] != first["id"]


def test_admin_manual_assign_and_workload_limit(client, admin, employee):
    inc = new_incident(client, employee).json()
    users = client.get("/api/admin/users?role=TECHNICIAN", headers=admin).json()
    karan = next(u for u in users if u["email"] == "karan@example.com")
    client.patch(f"/api/admin/users/{karan['id']}", json={"max_workload": max(karan["workload"], 1)},
                 headers=admin)
    r = client.post(f"/api/incidents/{inc['id']}/assign", json={"technician_id": karan["id"]}, headers=admin)
    if karan["workload"] >= 1:
        assert r.status_code == 409 and r.json()["error"] == "WORKLOAD_EXCEEDED"
    sneha = next(u for u in users if u["email"] == "sneha@example.com")
    r = client.post(f"/api/incidents/{inc['id']}/assign", json={"technician_id": sneha["id"]}, headers=admin)
    assert r.status_code == 200 and r.json()["technician"]["id"] == sneha["id"]


# ── search, reports, notifications, configuration ─────────────────────────────────
def test_search_filters(client, admin, employee):
    new_incident(client, employee)
    pay = service_id(client, admin, "Payment Gateway")
    res = client.get(f"/api/incidents?priority=P1&service_id={pay}&status=ASSIGNED", headers=admin).json()
    assert res and all(i["priority"] == "P1" and i["service"]["id"] == pay for i in res)
    assert client.get("/api/incidents?status=CLOSED", headers=admin).json()
    assert client.get("/api/incidents?q=laptop", headers=admin).json()[0]["title"].startswith("Laptop")
    assert all(i["sla_state"] == "MET" for i in client.get("/api/incidents?sla_status=MET", headers=admin).json())
    assert client.get("/api/incidents?id=1001", headers=admin).status_code == 200


def test_reports_and_notifications(client, admin, employee):
    inc = new_incident(client, employee).json()
    ov = client.get("/api/reports/overview", headers=admin).json()
    assert ov["total"] >= 8 and ov["critical_open"] >= 1 and "by_service" in ov
    assert len(client.get("/api/reports/workload", headers=admin).json()) == 5
    tech = login(client, inc["technician"]["email"])
    notes = client.get("/api/notifications", headers=tech).json()
    assert notes["unread"] >= 1 and any(n["event"] == "INCIDENT_ASSIGNED" for n in notes["items"])
    outbox = client.get("/api/admin/email-outbox", headers=admin).json()
    assert any(e["recipient"] == inc["technician"]["email"] for e in outbox)


def test_admin_configuration(client, admin):
    r = client.put("/api/admin/config", json={"assignment_strategy": "ROUND_ROBIN"}, headers=admin)
    assert r.json()["assignment_strategy"] == "ROUND_ROBIN"
    assert client.put("/api/admin/config", json={"assignment_strategy": "MAGIC"}, headers=admin).status_code == 422
    bad = client.post("/api/admin/sla-policies", json={"name": "x", "priority": "P2",
                      "response_minutes": 100, "resolution_minutes": 10}, headers=admin)
    assert bad.status_code == 422
    r = client.post("/api/admin/categories", json={"code": "printing", "name": "Printing",
                    "keywords": ["printer"]}, headers=admin)
    assert r.status_code == 201 and r.json()["code"] == "PRINTING"
    logs = client.get("/api/admin/audit-logs?action=CONFIG_CHANGED", headers=admin).json()
    assert logs and "ROUND_ROBIN" in logs[0]["description"]


def test_suggest_endpoint(client, employee):
    r = client.post("/api/incidents/suggest", json={
        "title": "VPN disconnecting", "description": "vpn drops when working from home"}, headers=employee)
    body = r.json()
    assert body["categories"][0]["code"] == "NETWORK"
    assert body["resolutions"] and "VPN" in body["resolutions"][0]["resolution"]
