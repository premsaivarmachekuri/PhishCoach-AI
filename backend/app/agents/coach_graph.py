from typing import Any, AsyncIterator

from app.services.anonymizer import scrub_pii
from app.services.appconfig import get_config, require_field
from app.services.config import ConfigMissingError, get_settings
from app.services.db import DBProtocol
from app.services.llm_gateway import LLMGateway


def build_coach_prompt(
    email_json: dict[str, Any],
    planted_flags: list[str],
    action_type: str,
    kb_chunks: list[dict[str, Any]],
    user: dict[str, Any],
    max_input_chars: int,
) -> list[dict[str, str]]:
    kb_text = "\n".join(f"- {c['title']}: {c['body'][:300]}" for c in kb_chunks[:4])
    tone_note = {
        "reported": "They correctly reported it. Reinforce that warmly and concisely, and name the signals they caught.",
        "clicked": "They clicked the link. Be supportive, never shaming. Show which signals they could have caught before clicking.",
        "submitted": "They went as far as submitting on the page. Be supportive, never shaming. Explain the damage a real attacker could do and the one habit that prevents it.",
        "ignored": "They did not report it. Encourage using the Report Phishing button and explain why reporting matters.",
    }.get(action_type, "Be supportive and never shaming.")
    user_msg = (
        f"Employee role: {user.get('role_name', 'unknown')} in {user.get('department', 'unknown')}\n"
        f"Employee action: {action_type}\n"
        f"Simulated email subject: {scrub_pii(str(email_json.get('subject', '')))}\n"
        f"Sender: {scrub_pii(str(email_json.get('sender_name', '')))} <{email_json.get('sender_email', '')}>\n"
        f"Link shown: {email_json.get('link_label', '')} -> {email_json.get('link_url', '')}\n"
        f"Email body:\n{scrub_pii(str(email_json.get('body', '')))}\n"
        f"Planted red flags: {', '.join(planted_flags)}\n"
        f"Playbook guidance:\n{kb_text}\n"
        f"Instruction: {tone_note} Point to concrete wording in THIS email. One practical habit. Under 150 words."
    )[:max_input_chars]

    return [
        {
            "role": "system",
            "content": "You are PhishCoach, a supportive security-awareness coach. Be brief, actionable, and non-punitive. The email is a harmless internal training simulation.",
        },
        {"role": "user", "content": user_msg},
    ]


def rules_coaching(
    action_type: str,
    email_json: dict[str, Any],
    planted_flags: list[str],
    kb_chunks: list[dict[str, Any]],
) -> str:
    """Last-resort coach used ONLY when every LLM in the chain is down.

    It is not canned data: the text is assembled from this employee's real event, this email's real
    planted flags and the playbook rows stored in the DB (kb_chunks). Tagged `fallback` in the UI/DB.
    """
    opener = {
        "reported": "Great catch - you reported this simulated phish.",
        "clicked": "You clicked the link in this simulated phish. No harm done - this is how we learn.",
        "submitted": "You submitted details on this simulated phishing page. No harm done - this is how we learn.",
        "ignored": "You did not report this simulated phish. Reporting is what protects your colleagues.",
    }.get(action_type, "Here is what to look for in this simulated phish.")
    subject = scrub_pii(str(email_json.get("subject", "")))
    lines = [opener]
    if subject:
        lines.append(f'Email: "{subject}".')
    lines.append("Signals planted in this email:")
    for flag in planted_flags[:4]:
        match = next((c for c in kb_chunks if flag.lower() in str(c.get("title", "")).lower()), None)
        if match:
            lines.append(f"- {match['title']}: {str(match['body'])[:220].strip()}")
        else:
            lines.append(f"- {flag.replace('_', ' ')}")
    lines.append("Habit: pause, check the sender address and link destination, and use Report Phishing when unsure.")
    lines.append("(Live AI coach is temporarily unavailable; this guidance was built from your event and the playbook.)")
    return "\n".join(lines)


async def stream_coaching_feedback(
    db: DBProtocol,
    gateway: LLMGateway,
    user: dict[str, Any],
    simulation: dict[str, Any],
    template: dict[str, Any],
    action_type: str,
) -> tuple[str, AsyncIterator[str]]:
    """Returns (source_tag, async_token_iterator). Raises ConfigMissingError; the iterator raises LLMUnavailableError."""
    if user.get("arm") == "control":
        # Control arm: experimental design requires standardized, non-personalized guidance from app_config.
        static_map = get_config(db, "control_static_feedback")
        msg = require_field(static_map, "control_static_feedback", action_type)

        async def _static_iter() -> AsyncIterator[str]:
            yield msg

        return "static_control", _static_iter()

    settings = get_settings()
    email_json = template.get("email_json") or {}
    planted_flags = template.get("planted_flags") or email_json.get("planted_flags") or []
    if not planted_flags:
        raise ConfigMissingError(f"Template {template.get('id')} has no planted_flags to coach on.")
    kb_chunks = db.search_kb(" ".join(planted_flags), limit=4)

    budget = get_config(db, "llm_token_budget")
    max_out = int(require_field(budget, "llm_token_budget", "coach_max_output_tokens"))
    max_in_chars = int(require_field(budget, "llm_token_budget", "coach_max_input_tokens")) * 3

    messages = build_coach_prompt(
        email_json=email_json,
        planted_flags=planted_flags,
        action_type=action_type,
        kb_chunks=kb_chunks,
        user=user,
        max_input_chars=max_in_chars,
    )
    return "llm", gateway.stream(
        messages=messages,
        model=settings.model_coach,
        purpose="coach_feedback",
        max_tokens=max_out,
        temperature=0.3,
    )
