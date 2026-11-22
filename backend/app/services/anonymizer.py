import hashlib
import re
from typing import Iterable

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def make_anon_id(external_id: str, salt: str = "phishcoach") -> str:
    digest = hashlib.sha256(f"{salt}:{external_id}".encode("utf-8")).hexdigest()[:12]
    return f"emp_{digest}"


def scrub_pii(text: str, known_names: Iterable[str] = ()) -> str:
    """Scrub emails, phone numbers, SSNs, card numbers, and known employee names."""
    if not text:
        return text
    cleaned = EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    cleaned = SSN_RE.sub("[SSN_REDACTED]", cleaned)
    cleaned = PHONE_RE.sub("[PHONE_REDACTED]", cleaned)
    cleaned = CARD_RE.sub("[CARD_REDACTED]", cleaned)

    for name in known_names:
        name = name.strip()
        if len(name) >= 2:
            pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
            cleaned = pattern.sub("[NAME_REDACTED]", cleaned)
    return cleaned
