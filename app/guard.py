"""Reusable guard functions (owner: B). Thin compatibility layer over app/guardrails.

Kept so existing imports keep working. The logic lives in app/guardrails (maintained by A by team
agreement): redact(text) -> (redacted_text, pii_found); requested_other_account(message, account_id).
"""
from app.guardrails import patterns as _patterns
from app.guardrails.input_guard import other_account_ids, redact_text

ACCOUNT_ID = _patterns.ACCOUNT_ID


def redact(text: str) -> tuple[str, bool]:
    redacted, types = redact_text(text)
    return redacted, bool(types)


def requested_other_account(message: str, account_id: str | None) -> bool:
    return bool(other_account_ids(message, account_id))
