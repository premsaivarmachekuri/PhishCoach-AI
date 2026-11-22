import json
import random
from typing import Any, TypedDict

from app.models.schemas import CampaignBrief, GeneratedEmailJSON
from app.services.appconfig import get_config, require_field
from app.services.config import ConfigMissingError, get_settings
from app.services.db import DBProtocol
from app.services.guardrails import (
    check_email_guardrails,
    check_planted_flags,
    sanitize_prompt_context,
)
from app.services.llm_gateway import LLMGateway, LLMUnavailableError
from langgraph.graph import END, StateGraph
from pydantic import ValidationError

MAX_ATTEMPTS = 3


class CampaignGenerationError(RuntimeError):
    """The pipeline could not produce an email that passes validation and guardrails."""


class CampaignState(TypedDict, total=False):
    brief: dict[str, Any]
    selected_flags: list[str]
    attempts: int
    email_json: dict[str, Any] | None
    passed: bool
    errors: list[str]
    max_output_tokens: int


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def build_campaign_graph(gateway: LLMGateway):
    settings = get_settings()

    async def generate_node(state: CampaignState) -> CampaignState:
        attempts = state.get("attempts", 0) + 1
        brief = state["brief"]
        safe_ctx = sanitize_prompt_context({**brief, "planted_flags": state["selected_flags"]})
        err_hint = ""
        if state.get("errors"):
            err_hint = f"\nPrevious attempt failed validation: {'; '.join(state['errors'])}. Fix these issues."

        prompt = (
            "Generate a realistic, harmless enterprise phishing simulation email in JSON.\n"
            "STRICT RULES:\n"
            "- sender_email MUST use a reserved domain (.invalid, .test, or example.com).\n"
            "- link_url MUST use a reserved domain (https://portal.example.com/... or .invalid / .test).\n"
            "- NEVER mention real brands (Google, Microsoft, Apple, Amazon, Okta, DocuSign, PayPal, etc.).\n"
            "- NEVER include HTML <form> or password input tags.\n"
            "- Tailor tone, jargon and pretext to the target department and role.\n"
            "- Plant clear, observable signals for ALL requested planted_flags and list exactly those codes in planted_flags.\n"
            f"Context: {json.dumps(safe_ctx)}{err_hint}\n"
            "Return ONLY a JSON object with keys: sender_name, sender_email, subject, body, link_label, link_url, planted_flags."
        )
        try:
            raw, _ = await gateway.complete(
                messages=[
                    {"role": "system", "content": "You are a security-awareness simulation author. Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model=settings.model_generate,
                purpose="campaign_generate",
                max_tokens=state["max_output_tokens"],
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            validated = GeneratedEmailJSON(**_extract_json(raw))
            return {"attempts": attempts, "email_json": validated.model_dump(), "errors": []}
        except LLMUnavailableError:
            raise  # infrastructure failure: do not burn attempts, surface it
        except (ValidationError, json.JSONDecodeError, TypeError) as exc:
            return {"attempts": attempts, "email_json": None, "errors": [str(exc)[:400]]}

    def check_node(state: CampaignState) -> CampaignState:
        if not state.get("email_json"):
            return {"passed": False}
        email = GeneratedEmailJSON(**state["email_json"])
        flags_ok, missing = check_planted_flags(email)
        rules_ok, reasons = check_email_guardrails(email)
        errors = list(reasons)
        if not flags_ok:
            errors.append(f"Missing planted_flags signals: {', '.join(missing)}")
        # Last attempt: safety rules passed but some requested flag signals could not be verified by the
        # keyword check. Ship only the flags that ARE verified (honest coaching) rather than failing the run.
        if (
            not flags_ok
            and rules_ok
            and state.get("attempts", 0) >= MAX_ATTEMPTS
            and any(f in state["selected_flags"] and f not in missing for f in email.planted_flags)
        ):
            verified = [f for f in email.planted_flags if f not in missing]
            pruned = email.model_copy(update={"planted_flags": verified})
            return {"passed": True, "email_json": pruned.model_dump(), "errors": []}
        undeclared = [f for f in state["selected_flags"] if f not in email.planted_flags]
        if undeclared:
            errors.append(f"planted_flags must include: {', '.join(undeclared)}")
        return {"passed": flags_ok and rules_ok and not undeclared, "errors": errors}

    async def llm_guard_node(state: CampaignState) -> CampaignState:
        # Fail closed: if the guard model cannot give a verdict, the email is not released.
        raw, _ = await gateway.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You review emails for an authorized internal phishing-awareness TRAINING simulation. "
                        "Suspicious tone, urgency, and sender/link mismatches are EXPECTED and must be ALLOWED. "
                        "Set allow=false ONLY if the email names a real company/brand, contains a real (non-reserved) "
                        "URL or domain (reserved: example.com, *.example.com, *.invalid, *.test), contains an HTML form or "
                        "password field, or includes malware/attachment instructions. "
                        'Reply with JSON only: {"allow": true/false, "reason": "..."}.'
                    ),
                },
                {"role": "user", "content": json.dumps(state["email_json"])},
            ],
            model=settings.model_guard,
            purpose="campaign_guardrail",
            max_tokens=120,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        try:
            verdict = _extract_json(raw)
            allow = verdict["allow"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return {"passed": False, "errors": ["LLM guardrail returned an unparseable verdict"]}
        if allow is not True:
            return {"passed": False, "errors": [str(verdict.get("reason", "Blocked by LLM guardrail"))]}
        return {"passed": True}

    def fail_node(state: CampaignState) -> CampaignState:
        raise CampaignGenerationError(
            f"Could not generate a safe simulation after {state.get('attempts', 0)} attempts: "
            + "; ".join(state.get("errors", []) or ["unknown validation failure"])
        )

    def route_after_check(state: CampaignState) -> str:
        if state.get("passed"):
            return "llm_guard"
        return "generate" if state.get("attempts", 0) < MAX_ATTEMPTS else "fail"

    def route_after_guard(state: CampaignState) -> str:
        if state.get("passed"):
            return END
        return "generate" if state.get("attempts", 0) < MAX_ATTEMPTS else "fail"

    graph = StateGraph(CampaignState)
    graph.add_node("generate", generate_node)
    graph.add_node("check", check_node)
    graph.add_node("llm_guard", llm_guard_node)
    graph.add_node("fail", fail_node)
    graph.set_entry_point("generate")
    graph.add_edge("generate", "check")
    graph.add_conditional_edges("check", route_after_check, {"llm_guard": "llm_guard", "generate": "generate", "fail": "fail"})
    graph.add_conditional_edges("llm_guard", route_after_guard, {END: END, "generate": "generate", "fail": "fail"})
    graph.add_edge("fail", END)
    return graph.compile()


def select_flags(red_flags: list[dict[str, Any]], difficulty: int, rng: random.Random | None = None) -> list[str]:
    """Pick a varied subset of eligible playbook flags: always one from the top eligible tier."""
    rng = rng or random.Random()
    eligible = [f for f in red_flags if int(f["difficulty_tier"]) <= difficulty]
    if not eligible:
        raise ConfigMissingError("No red_flags in the database for this difficulty; run tools/ingest_kb.py.")
    top_tier = max(int(f["difficulty_tier"]) for f in eligible)
    anchor = rng.choice([f for f in eligible if int(f["difficulty_tier"]) == top_tier])
    rest = [f for f in eligible if f is not anchor]
    extra = rng.sample(rest, k=min(len(rest), 1 + difficulty))
    return [anchor["code"], *[f["code"] for f in extra]]


async def run_campaign_generation(
    db: DBProtocol, gateway: LLMGateway, brief: CampaignBrief
) -> tuple[dict[str, Any], str]:
    """Returns (email_json, source). Raises LLMUnavailableError / CampaignGenerationError, never canned content."""
    red_flags = db.select("red_flags", order="difficulty_tier")
    budget = get_config(db, "llm_token_budget")
    state: CampaignState = {
        "brief": brief.model_dump(),
        "selected_flags": select_flags(red_flags, brief.difficulty),
        "attempts": 0,
        "max_output_tokens": int(require_field(budget, "llm_token_budget", "generate_max_output_tokens")),
    }
    result = await build_campaign_graph(gateway).ainvoke(state)
    return result["email_json"], "llm"
