import os

import pytest
from app.agents.campaign_graph import run_campaign_generation
from app.models.schemas import CampaignBrief, GeneratedEmailJSON
from app.services.config import get_settings
from app.services.guardrails import check_email_guardrails
from app.services.llm_gateway import LLMGateway

from tests.fakes import InMemoryDB


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="GROQ_API_KEY not set")
async def test_live_groq_campaign_generation():
    get_settings.cache_clear()
    db = InMemoryDB()
    gateway = LLMGateway(db)
    brief = CampaignBrief(theme="Quarterly Benefits Enrollment", department="Finance", difficulty=1)
    email_dict, source = await run_campaign_generation(db, gateway, brief)
    email = GeneratedEmailJSON(**email_dict)
    ok, reasons = check_email_guardrails(email)
    assert ok, f"Guardrail failed: {reasons}"
    assert source in ("llm", "fallback")
