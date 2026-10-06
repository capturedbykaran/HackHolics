"""STUB (owner: D). Audit trail helpers.

In-memory version so the graph runs end to end; D persists to audit_log / conversations (app/db.py).
Contract used by A's code:
  * write_audit(state: dict)                       one record per request (PII already redacted)
  * append_conversation(conversation_id, role, payload)   payload carries account_id, trace_id,
        message (user) or answer + answer_type (assistant), intent (classifier dump)
  * get_conversation(conversation_id, limit=6) -> last turns, oldest first; limit <= 0 -> all turns
        [{role, account_id, message|answer, answer_type, intent, trace_id, created_at}]
"""
import uuid
from datetime import datetime, timezone
from typing import Any

AUDIT: list[dict[str, Any]] = []
CONVERSATIONS: dict[str, list[dict[str, Any]]] = {}

_AUDIT_KEYS = ("trace_id", "conversation_id", "account_id", "customer_segment", "as_of_date",
               "redacted_message", "classifier", "version", "chunks", "tool_results", "draft", "critic",
               "decision", "handoff_id", "failures", "signals", "prior_user_turns", "prior_escalations",
               "latency_ms", "llm_calls", "model", "tokens", "response", "guardrail_events")


def new_trace() -> str:
    return f"T-{uuid.uuid4().hex[:10]}"


def write_audit(state: dict) -> None:
    AUDIT.append({k: state.get(k) for k in _AUDIT_KEYS})


def append_conversation(conversation_id: str, role: str, payload: dict) -> None:
    turn = {"role": role, "created_at": datetime.now(timezone.utc).isoformat(), **payload}
    CONVERSATIONS.setdefault(conversation_id, []).append(turn)


def get_conversation(conversation_id: str, limit: int = 6) -> list[dict]:
    turns = CONVERSATIONS.get(conversation_id, [])
    return [dict(t) for t in (turns[-limit:] if limit > 0 else turns)]
