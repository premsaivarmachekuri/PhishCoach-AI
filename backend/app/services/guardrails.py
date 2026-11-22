import re
from typing import Any

from app.models.schemas import GeneratedEmailJSON

# Real consumer/enterprise brands that must NEVER be impersonated
BLOCKED_BRANDS = {
    "google",
    "gmail",
    "microsoft",
    "office365",
    "outlook",
    "apple",
    "icloud",
    "amazon",
    "aws",
    "paypal",
    "chase",
    "bank of america",
    "wellsfargo",
    "citibank",
    "docusign",
    "okta",
    "slack",
    "zoom",
    "dropbox",
    "netflix",
    "linkedin",
    "facebook",
    "meta",
    "stripe",
    "salesforce",
}

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(?:your\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"give\s+me\s+real\s+credentials", re.IGNORECASE),
    re.compile(r"pretend\s+to\s+be\s+(?:google|microsoft|apple|paypal|bank)", re.IGNORECASE),
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"<\s*form\b[^>]*password", re.IGNORECASE),
]

URL_RE = re.compile(r"https?://([^\s/\"'<>]+)", re.IGNORECASE)
RESERVED_TLDS = (".invalid", ".test")


def is_reserved_host(host: str) -> bool:
    h = host.lower().split(":", 1)[0]
    return h.endswith(RESERVED_TLDS) or h == "example.com" or h.endswith(".example.com")


def check_email_guardrails(email: GeneratedEmailJSON) -> tuple[bool, list[str]]:
    """Rule-based safety check for generated phishing simulation emails."""
    reasons: list[str] = []
    combined = f"{email.sender_name} {email.sender_email} {email.subject} {email.body} {email.link_label}".lower()

    for brand in BLOCKED_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", combined):
            reasons.append(f"Blocked real brand mention: {brand}")

    for match in URL_RE.findall(f"{email.body} {email.link_url}"):
        if not is_reserved_host(match):
            reasons.append(f"Non-reserved URL host detected: {match}")

    if "<form" in combined or "type=\"password\"" in combined or "type='password'" in combined:
        reasons.append("Credential-harvesting HTML form markup is prohibited")

    # Ensure sender & link use reserved domains
    sender_domain = email.sender_email.split("@", 1)[-1]
    if not is_reserved_host(sender_domain):
        reasons.append(f"Sender domain is not reserved: {sender_domain}")

    return len(reasons) == 0, reasons


def check_planted_flags(email: GeneratedEmailJSON) -> tuple[bool, list[str]]:
    """Verify that declared planted_flags have observable signals in the email."""
    missing: list[str] = []
    text = f"{email.sender_name} {email.sender_email} {email.subject} {email.body} {email.link_label} {email.link_url}".lower()

    flag_heuristics: dict[str, list[str]] = {
        "urgency": ["urgent", "immediately", "asap", "within", "expire", "suspended", "action required", "deadline", "hours", "today"],
        "sender_mismatch": [".invalid", ".test", "support", "helpdesk", "admin", "billing", "security", "noreply"],
        "link_mismatch": ["http://", "https://", "verify", "click", "review", "portal", "login"],
        "credential_request": ["password", "sign in", "login", "verify your account", "mfa", "token", "credentials"],
        "generic_greeting": ["dear user", "dear employee", "valued", "team member", "hello user", "colleague"],
        "authority_pressure": ["ceo", "cfo", "director", "vp", "executive", "compliance", "audit", "legal"],
        "unusual_request": ["wire", "bank", "invoice", "gift card", "bypass", "transfer", "spreadsheet", "routing"],
        "unexpected_attachment": ["attached", "attachment", "invoice.pdf", "document", ".zip", "file"],
        "reward_lure": ["bonus", "reward", "refund", "gift", "perk", "prize", "stipend"],
    }

    for flag in email.planted_flags:
        keywords = flag_heuristics.get(flag, [])
        if keywords and not any(kw in text for kw in keywords):
            missing.append(flag)

    return len(missing) == 0, missing


def check_chat_guardrails(text: str) -> tuple[bool, str | None]:
    """Input/output guardrail for practice chat."""
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            return False, "Blocked prompt injection or unsafe request pattern"
    lower = text.lower()
    for brand in BLOCKED_BRANDS:
        if re.search(rf"\b{re.escape(brand)}\b", lower):
            return False, f"Blocked real brand mention: {brand}"
    for host in URL_RE.findall(text):
        if not is_reserved_host(host):
            return False, f"Blocked non-reserved URL: {host}"
    return True, None


def sanitize_prompt_context(data: dict[str, Any]) -> dict[str, Any]:
    """Strip any unexpected keys before passing context to LLM."""
    allowed = {"theme", "department", "role_name", "difficulty", "notes", "planted_flags"}
    return {k: v for k, v in data.items() if k in allowed}
