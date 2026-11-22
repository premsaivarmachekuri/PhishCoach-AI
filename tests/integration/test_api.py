import json
from unittest.mock import AsyncMock, patch

from app.main import app
from app.services.config import get_settings
from app.services.db import get_db
from fastapi.testclient import TestClient

from mock_systems.mock_hr.app import app as mock_hr_app
from mock_systems.mock_sim.app import app as mock_sim_app
from tests.fakes import TEST_JWT_SECRET, InMemoryDB, make_test_token


def _setup_app(monkeypatch) -> tuple[TestClient, InMemoryDB, dict[str, str]]:
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("SIM_WEBHOOK_SECRET", "test-webhook-secret-16bytes")
    get_settings.cache_clear()

    db = InMemoryDB()
    app.dependency_overrides[get_db] = lambda: db

    admin = db.insert(
        "users",
        {
            "anon_id": "emp_admin",
            "role_name": "Security Admin",
            "department": "IT",
            "seniority": "senior",
            "arm": "treatment",
            "app_role": "security_admin",
            "is_synthetic": False,
            "auth_user_id": "auth-admin",
        },
    )[0]
    emp_a = db.insert(
        "users",
        {
            "anon_id": "emp_a",
            "role_name": "Finance Analyst",
            "department": "Finance",
            "seniority": "mid",
            "arm": "treatment",
            "app_role": "employee",
            "is_synthetic": False,
            "auth_user_id": "auth-a",
        },
    )[0]
    emp_b = db.insert(
        "users",
        {
            "anon_id": "emp_b",
            "role_name": "Engineer",
            "department": "Engineering",
            "seniority": "mid",
            "arm": "control",
            "app_role": "employee",
            "is_synthetic": False,
            "auth_user_id": "auth-b",
        },
    )[0]
    hr = db.insert(
        "users",
        {
            "anon_id": "emp_hr",
            "role_name": "HR Director",
            "department": "HR",
            "seniority": "senior",
            "arm": "control",
            "app_role": "hr_viewer",
            "is_synthetic": False,
            "auth_user_id": "auth-hr",
        },
    )[0]

    tokens = {
        "admin": make_test_token(admin["auth_user_id"]),
        "emp_a": make_test_token(emp_a["auth_user_id"]),
        "emp_b": make_test_token(emp_b["auth_user_id"]),
        "hr": make_test_token(hr["auth_user_id"]),
    }
    return TestClient(app), db, tokens


def test_mock_services_contracts():
    hr_client = TestClient(mock_hr_app)
    r_hr = hr_client.get("/mock/hr/employees")
    assert r_hr.status_code == 200
    assert len(r_hr.json()["employees"]) >= 10

    sim_client = TestClient(mock_sim_app)
    r_sim = sim_client.post("/mock/sim/campaigns", json={"campaign_id": "c1", "deliveries": [{"simulation_id": "s1"}]})
    assert r_sim.status_code == 200
    assert r_sim.json()["queued_deliveries"] == 1


def test_end_to_end_campaign_inbox_events_and_rbac(monkeypatch):
    client, db, tokens = _setup_app(monkeypatch)
    assert client.get("/health").status_code == 200

    mock_email = {
        "sender_name": "Finance Support",
        "sender_email": "billing@notices-portal.invalid",
        "subject": "Urgent: Verify your invoice portal access",
        "body": "Dear Employee, urgent action required within 2 hours. Please sign in to verify your account.",
        "link_label": "Verify Account",
        "link_url": "https://portal.training-sim.invalid/verify",
        "planted_flags": ["sender_mismatch", "urgency", "credential_request"],
    }

    async def _fake_complete(*args, **kwargs):
        if kwargs.get("purpose") == "campaign_guardrail":
            return json.dumps({"allow": True, "reason": "safe training email"}), "openai/gpt-oss-20b"
        return json.dumps(mock_email), "openai/gpt-oss-120b"

    with (
        patch("app.agents.campaign_graph.select_flags", return_value=["sender_mismatch", "urgency", "credential_request"]),
        patch("app.services.llm_gateway.LLMGateway.complete", new=AsyncMock(side_effect=_fake_complete)),
    ):
        resp = client.post(
            "/campaigns",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
            json={"theme": "Invoice Portal", "department": "all", "difficulty": 1, "wave_no": 1},
        )
    assert resp.status_code == 201
    camp_id = resp.json()["campaign"]["id"]
    tmpl_id = resp.json()["template"]["id"]

    # Cannot deploy before approval
    dep_fail = client.post(
        f"/campaigns/{camp_id}/deploy",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert dep_fail.status_code == 400

    # Approve and deploy
    assert (
        client.post(
            f"/campaigns/{camp_id}/templates/{tmpl_id}/approve",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        ).status_code
        == 200
    )
    with patch(
        "app.adapters.sim_platform.HTTPSimPlatformAdapter.deploy_campaign",
        new=AsyncMock(return_value={"status": "accepted", "queued_deliveries": 2}),
    ):
        dep_ok = client.post(
            f"/campaigns/{camp_id}/deploy",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
    assert dep_ok.status_code == 200
    assert dep_ok.json()["delivered_count"] == 2

    # Employee A sees inbox and clicks (idempotent)
    inbox_a = client.get("/me/inbox", headers={"Authorization": f"Bearer {tokens['emp_a']}"}).json()
    assert len(inbox_a) == 1
    sim_a = inbox_a[0]["simulation_id"]

    ev1 = client.post(
        "/events",
        headers={"Authorization": f"Bearer {tokens['emp_a']}"},
        json={"simulation_id": sim_a, "type": "clicked"},
    )
    assert ev1.status_code == 200
    assert ev1.json()["duplicate"] is False

    ev2 = client.post(
        "/events",
        headers={"Authorization": f"Bearer {tokens['emp_a']}"},
        json={"simulation_id": sim_a, "type": "clicked"},
    )
    assert ev2.status_code == 200
    assert ev2.json()["duplicate"] is True

    # Negative RBAC test: Employee B cannot record event for Employee A's simulation
    ev_b_on_a = client.post(
        "/events",
        headers={"Authorization": f"Bearer {tokens['emp_b']}"},
        json={"simulation_id": sim_a, "type": "clicked"},
    )
    assert ev_b_on_a.status_code == 404

    # All LLMs down: treatment coaching degrades to the rules coach instead of failing
    from app.services.llm_gateway import LLMUnavailableError

    async def _dead_stream(*args, **kwargs):
        raise LLMUnavailableError("all models down")
        yield  # pragma: no cover

    with patch("app.services.llm_gateway.LLMGateway.stream", new=_dead_stream):
        coach_a = client.post(
            f"/coach/{sim_a}?action=clicked", headers={"Authorization": f"Bearer {tokens['emp_a']}"}
        )
    assert coach_a.status_code == 200
    assert '"source": "fallback"' in coach_a.text and "event: done" in coach_a.text
    assert "event: error" not in coach_a.text

    # Employee A cannot access admin dashboard
    assert client.get("/admin/dashboard", headers={"Authorization": f"Bearer {tokens['emp_a']}"}).status_code == 403

    # HR aggregate hides cohorts below min_cohort_size (5)
    hr_res = client.get("/hr/aggregates", headers={"Authorization": f"Bearer {tokens['hr']}"})
    assert hr_res.status_code == 200
    assert hr_res.json()["cohorts"] == []
    assert hr_res.json()["suppressed_departments"] >= 1

    # Control arm gets static message on coaching; exports work
    inbox_b = client.get("/me/inbox", headers={"Authorization": f"Bearer {tokens['emp_b']}"}).json()
    sim_b = inbox_b[0]["simulation_id"]
    client.post(
        "/events",
        headers={"Authorization": f"Bearer {tokens['emp_b']}"},
        json={"simulation_id": sim_b, "type": "clicked"},
    )
    coach_b = client.post(f"/coach/{sim_b}?action=clicked", headers={"Authorization": f"Bearer {tokens['emp_b']}"})
    assert coach_b.status_code == 200
    assert "Static control message" in coach_b.text

    assert client.get("/admin/pilot", headers={"Authorization": f"Bearer {tokens['admin']}"}).status_code == 200
    assert client.get("/admin/export?format=csv", headers={"Authorization": f"Bearer {tokens['admin']}"}).status_code == 200
    assert client.get("/admin/export?format=pdf", headers={"Authorization": f"Bearer {tokens['admin']}"}).status_code == 200

    app.dependency_overrides.clear()
