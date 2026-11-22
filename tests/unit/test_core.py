import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.models.schemas import GeneratedEmailJSON
from app.services.anonymizer import make_anon_id, scrub_pii
from app.services.config import get_settings
from app.services.guardrails import check_email_guardrails, check_planted_flags
from app.services.llm_gateway import LLMGateway, LLMUnavailableError
from app.services.risk_engine import compute_user_risk
from pydantic import ValidationError

from tests.fakes import InMemoryDB


def test_anonymizer_scrubs_pii():
    raw = "Hi Asha Sharma, email asha@company.com or call 555-123-4567 SSN 123-45-6789."
    cleaned = scrub_pii(raw, known_names=["Asha Sharma"])
    assert "asha@company.com" not in cleaned
    assert "555-123-4567" not in cleaned
    assert "123-45-6789" not in cleaned
    assert "Asha Sharma" not in cleaned
    assert make_anon_id("HR-1001") == make_anon_id("HR-1001")


def test_guardrails_block_real_brands_and_urls():
    with pytest.raises(ValidationError):
        GeneratedEmailJSON(
            sender_name="Support",
            sender_email="help@microsoft.com",
            subject="Urgent",
            body="Click here now to reset password.",
            link_label="Reset",
            link_url="https://login.microsoft.com/reset",
            planted_flags=["urgency"],
        )

    # Reserved domain but real brand in body -> blocked by check_email_guardrails
    email = GeneratedEmailJSON(
        sender_name="PayPal Desk",
        sender_email="support@notices.invalid",
        subject="Urgent account check",
        body="Your PayPal account is suspended. Verify immediately.",
        link_label="Verify",
        link_url="https://portal.example.com/check",
        planted_flags=["urgency", "sender_mismatch"],
    )
    ok, reasons = check_email_guardrails(email)
    assert not ok
    assert any("paypal" in r.lower() for r in reasons)


def test_flag_checker_detects_missing_flags():
    email = GeneratedEmailJSON(
        sender_name="Internal Desk",
        sender_email="desk@training.invalid",
        subject="Quarterly update",
        body="Please review the quarterly update document at your convenience.",
        link_label="View Document",
        link_url="https://docs.example.com/q4",
        planted_flags=["urgency", "credential_request"],
    )
    ok, missing = check_planted_flags(email)
    assert not ok
    assert "urgency" in missing
    assert "credential_request" in missing


def test_risk_engine_transitions_and_remediation():
    db = InMemoryDB()
    user = db.insert(
        "users",
        {
            "anon_id": "emp_test1",
            "role_name": "Finance Analyst",
            "department": "Finance",
            "seniority": "mid",
            "arm": "treatment",
            "app_role": "employee",
            "is_synthetic": False,
            "auth_user_id": "auth-1",
        },
    )[0]
    camp = db.insert("campaigns", {"brief_json": {}, "target_filter": {}, "wave_no": 1, "status": "live"})[0]
    tmpl = db.insert("templates", {"campaign_id": camp["id"], "email_json": {}, "difficulty": 2})[0]
    sim1 = db.insert("simulations", {"campaign_id": camp["id"], "user_id": user["id"], "template_id": tmpl["id"], "delivered_at": datetime.now(timezone.utc).isoformat()})[0]
    sim2 = db.insert("simulations", {"campaign_id": camp["id"], "user_id": user["id"], "template_id": tmpl["id"], "delivered_at": datetime.now(timezone.utc).isoformat()})[0]

    # Initially Low
    r0 = compute_user_risk(db, user["id"])
    assert r0["band"] == "Low"

    # Click -> Medium
    db.insert("events", {"simulation_id": sim1["id"], "user_id": user["id"], "type": "clicked", "ts": datetime.now(timezone.utc).isoformat()})
    r1 = compute_user_risk(db, user["id"])
    assert r1["band"] == "Medium"

    # Submit -> High and queued once in remediation_queue
    db.insert("events", {"simulation_id": sim2["id"], "user_id": user["id"], "type": "submitted", "ts": datetime.now(timezone.utc).isoformat()})
    r2 = compute_user_risk(db, user["id"])
    assert r2["band"] == "High"
    rem = db.select("remediation_queue", filters={"user_id": user["id"]})
    assert len(rem) == 1

    # Re-computing does not duplicate remediation_queue entry
    compute_user_risk(db, user["id"])
    assert len(db.select("remediation_queue", filters={"user_id": user["id"]})) == 1


@pytest.mark.asyncio
async def test_llm_gateway_retries_429_and_raises_on_exhaustion(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_FALLBACKS", "")
    get_settings.cache_clear()
    db = InMemoryDB()
    gateway = LLMGateway(db)

    req = httpx.Request("POST", gateway.GROQ_CHAT_URL)
    resp_429 = httpx.Response(429, headers={"retry-after": "0.01"}, request=req)
    resp_ok = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps({"ok": True})}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        },
        request=req,
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=[resp_429, resp_ok])):
        content, model_used = await gateway.complete(
            messages=[{"role": "user", "content": "ping"}],
            model="openai/gpt-oss-120b",
            purpose="unit_test",
            max_retries=1,
        )
    assert model_used == "openai/gpt-oss-120b"
    assert json.loads(content) == {"ok": True}

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=[resp_429, resp_429])):
        with pytest.raises(LLMUnavailableError):
            await gateway.complete(
                messages=[{"role": "user", "content": "ping"}],
                model="openai/gpt-oss-120b",
                purpose="unit_test",
                max_retries=1,
            )
    calls = db.select("llm_calls")
    assert any(c["status"] == "rate_limited" for c in calls)
    assert any(c["status"] == "ok" for c in calls)


@pytest.mark.asyncio
async def test_llm_gateway_falls_back_to_next_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_FALLBACKS", "backup-model")
    get_settings.cache_clear()
    gateway = LLMGateway(InMemoryDB())
    req = httpx.Request("POST", gateway.GROQ_CHAT_URL)
    bad = httpx.Response(503, request=req)
    ok = httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}], "usage": {}}, request=req)
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=[bad, ok])):
        content, used = await gateway.complete(
            messages=[{"role": "user", "content": "x"}], model="primary", purpose="t", max_retries=0
        )
    assert (content, used) == ("hi", "backup-model")
    get_settings.cache_clear()


def test_rules_coaching_is_built_from_real_event_and_playbook():
    from app.agents.coach_graph import rules_coaching

    kb = [{"title": "Artificial Urgency (urgency)", "body": "Pressure to act now is a red flag."}]
    text = rules_coaching("clicked", {"subject": "Invoice due"}, ["urgency", "sender_mismatch"], kb)
    assert "clicked" in text and "Invoice due" in text
    assert "Pressure to act now" in text  # playbook row used
    assert "sender mismatch" in text  # flag without a playbook row still named
