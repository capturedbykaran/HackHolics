"""Layer 1 - INPUT guardrails: run before any LLM call. Owner: A.

check_input(message, account_id) -> InputVerdict
  empty message, length cap, PII/secret redaction, authorisation (R8), secret requests (R9),
  prompt-injection detection + delimiter neutralisation (R10), abusive language.
"""
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.guardrails import patterns as P

Event = dict[str, str]


def make_event(layer: str, check: str, action: str, detail: str = "") -> Event:
    """One guardrail decision. `detail` is redacted and truncated: never put raw PII in it."""
    return {"layer": layer, "check": check, "action": action, "detail": redact_text(detail)[0][:200]}


# ------------------------------------------------------------------ redaction
def luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def redact_text(text: str) -> tuple[str, list[str]]:
    """Replace PII/secrets with typed tags. Returns (redacted_text, pii_types found, e.g. ["EMAIL"]).

    Idempotent: redacting already-redacted text finds nothing. Invoice ids, account ids,
    error codes and versions are left alone.
    """
    if not text:
        return text or "", []
    found: list[str] = []

    def sub(rx: re.Pattern, repl: Any, tag: str, s: str) -> str:
        def inner(m: re.Match) -> str:
            out = repl(m) if callable(repl) else m.expand(repl)
            if out != m.group(0):
                found.append(tag)
            return out
        return rx.sub(inner, s)

    def card(m: re.Match) -> str:
        return "[CARD]" if luhn_ok(m.group(0)) else m.group(0)  # non-Luhn numbers (order ids) stay

    text = sub(P.BEARER, r"\1[TOKEN]", "TOKEN", text)
    text = sub(P.KV_TOKEN, r"\1[TOKEN]", "TOKEN", text)
    text = sub(P.KV_KEY, r"\1[API_KEY]", "API_KEY", text)
    text = sub(P.PASSWORD, r"\1[PASSWORD]", "PASSWORD", text)
    text = sub(P.API_KEY_PREFIX, "[API_KEY]", "API_KEY", text)
    text = sub(P.EMAIL, "[EMAIL]", "EMAIL", text)
    text = sub(P.CARD_CANDIDATE, card, "CARD", text)
    text = sub(P.AADHAAR, "[AADHAAR]", "AADHAAR", text)
    text = sub(P.PHONE_INTL, "[PHONE]", "PHONE", text)
    text = sub(P.PHONE_IN, "[PHONE]", "PHONE", text)
    text = sub(P.PHONE_US, "[PHONE]", "PHONE", text)
    text = sub(P.PAN, "[PAN]", "PAN", text)
    return text, sorted(set(found))


def other_account_ids(message: str, account_id: Optional[str]) -> list[str]:
    """Account ids named in the text that differ from the signed-in account (R8)."""
    return sorted({m for m in P.ACCOUNT_ID.findall(message or "") if m != account_id})


# ------------------------------------------------------------------ injection
def detect_injection(text: str, names: Optional[tuple] = None) -> list[str]:
    """Names of the injection patterns that match (never the matched text)."""
    return [n for n, rx in P.INJECTION_PHRASES.items()
            if (names is None or n in names) and rx.search(text or "")]


def neutralise_delimiters(text: str) -> str:
    """Make tag-like text inert so a customer cannot close <customer_message> or open <system>."""
    text = P.TAG_LIKE.sub(r"&lt;\1&gt;", text)
    text = P.TAG_OPEN_LIKE.sub("&lt;", text)
    return P.HEADING_INSTRUCTION.sub(r"\1\2", text)


# ------------------------------------------------------------------ verdict
class InputVerdict(BaseModel):
    redacted_message: str
    pii_found: bool = False
    pii_types: list[str] = []
    early: Optional[Literal["refused", "clarification_needed"]] = None
    early_reason: Optional[str] = None
    signals: list[str] = []
    events: list[dict[str, str]] = Field(default_factory=list)


def check_input(message: str, account_id: Optional[str]) -> InputVerdict:
    events: list[Event] = []
    signals: list[str] = []
    text = message or ""

    # 1. empty
    if not text.strip():
        events.append(make_event("input", "empty_message", "refuse", "empty or whitespace-only message"))
        return InputVerdict(redacted_message="", early="clarification_needed", early_reason="empty_message",
                            events=events)

    # 2. length cap
    if len(text) > P.MAX_MESSAGE_CHARS:
        events.append(make_event("input", "input_truncated", "flag",
                                 f"{len(text)} chars truncated to {P.MAX_MESSAGE_CHARS}"))
        text = text[:P.MAX_MESSAGE_CHARS]

    early: Optional[str] = None
    reason: Optional[str] = None

    # 4. authorisation (R8): another account's id in the text
    others = other_account_ids(text, account_id)
    if others:
        early, reason = "refused", "other_account"
        events.append(make_event("input", "other_account", "refuse",
                                 f"{len(others)} account id(s) differ from the signed-in account"))

    # 5. secret requests (R9): password reset is a flow, anything else is refused
    if P.RESET_REQUEST.search(text):
        signals.append("password_reset_requested")
        events.append(make_event("input", "password_reset_flow", "flag",
                                 "password reset requested; link is never shown in chat"))
    elif P.SECRET_REQUEST.search(text):
        events.append(make_event("input", "secret_request", "refuse", "asked to display a secret in chat"))
        if early is None:
            early, reason = "refused", "secret"

    # 6. prompt injection (R10): flag + neutralise, do not refuse
    hits = detect_injection(text)
    if hits:
        signals.append("injection_suspected")
        events.append(make_event("input", "prompt_injection", "flag", "matched: " + ",".join(hits)))
    neutral = neutralise_delimiters(text)
    if neutral != text:
        events.append(make_event("input", "delimiter_neutralised", "redact", "tag-like text escaped"))
    text = neutral

    # 7. abusive language
    if P.ABUSIVE.search(text):
        signals.append("abusive_language")
        events.append(make_event("input", "abusive_language", "flag", "abusive wording detected"))

    # 3. PII / secrets (after the checks above, which need the original ids/phrases)
    redacted, types = redact_text(text)
    for t in types:
        events.append(make_event("input", "pii_redaction", "redact", f"{t} redacted"))

    return InputVerdict(redacted_message=redacted, pii_found=bool(types), pii_types=types, early=early,
                        early_reason=reason, signals=signals, events=events)
