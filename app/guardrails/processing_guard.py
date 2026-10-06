"""Layer 2 - PROCESSING guardrails: what goes into and comes out of the LLM and the tools. Owner: A.

  sanitize_chunks   retrieved text is untrusted: drop injected chunks, redact PII
  plan_tools        tool allowlist; account_id always comes from state, never from model/message text
  wrap_data         put customer/retrieved text into a prompt as inert DATA
  strip_reasoning   remove <think> blocks before parsing model output
"""
from typing import Optional, get_args

from app.guardrails import patterns as P
from app.guardrails.input_guard import (Event, detect_injection, make_event, neutralise_delimiters,
                                        redact_text)
from app.schemas import Chunk, ToolName

# Only these names can ever be executed (schemas.ToolName). Every one is read-only; send_password_reset
# only triggers the secure reset email. Refunds, credits, plan changes and deletions do not exist as tools.
ALLOWED_TOOLS = frozenset(get_args(ToolName))
PUBLIC_TOOLS = frozenset({"check_platform_status"})  # need no account: allowed for prospects
ACCOUNT_TOOLS = ALLOWED_TOOLS - PUBLIC_TOOLS
UNTRUSTED_DOC_TYPES = {"ticket", "community"}


# ------------------------------------------------------------------ prompt hygiene
def escape_tags(text: str) -> str:
    """Escape tag-like text so data cannot close or open one of our delimiters."""
    return neutralise_delimiters(text)


def wrap_data(tag: str, text: str) -> str:
    """<tag>...</tag> around DATA; tag-like text inside it is escaped first."""
    return f"<{tag}>\n{escape_tags(text)}\n</{tag}>"


def strip_reasoning(text: str) -> str:
    """Remove chain-of-thought blocks (<think>...</think>, or an unterminated <think>...)."""
    text = P.THINK_BLOCK.sub("", text or "")
    text = P.THINK_UNCLOSED.sub("", text)
    return P.THINK_STRAY.sub("", text).strip()


# ------------------------------------------------------------------ retrieved text
def sanitize_chunks(chunks: list[Chunk]) -> tuple[list[Chunk], list[Event]]:
    """Drop chunks that contain instructions aimed at the assistant; redact PII in the rest.

    Retrieved tickets/community posts (authority 4-5) are the main risk, but every chunk is scanned.
    """
    clean: list[Chunk] = []
    events: list[Event] = []
    for c in chunks:
        hits = detect_injection(c.text, P.CHUNK_INJECTION_NAMES) or detect_injection(c.section, P.CHUNK_INJECTION_NAMES)
        if hits:
            untrusted = c.doc_type in UNTRUSTED_DOC_TYPES or c.authority_level >= 4
            events.append(make_event("processing", "chunk_dropped_injection", "drop",
                                     f"{c.source_id} ({'untrusted' if untrusted else 'trusted'} source): "
                                     + ",".join(hits)))
            continue
        text, types = redact_text(c.text)
        if types:
            events.append(make_event("processing", "chunk_pii_redaction", "redact",
                                     f"{c.source_id}: {','.join(types)}"))
        clean.append(c.model_copy(update={"text": text}) if text != c.text else c)
    return clean, events


def scan_for_ingest(text: str) -> bool:
    """True if a document looks like it carries instructions for the assistant (flag at ingest time)."""
    return bool(detect_injection(text, P.CHUNK_INJECTION_NAMES))


# ------------------------------------------------------------------ tools
def plan_tools(requested: list, account_id: Optional[str], segment: str = "") -> tuple[list[str], list[Event]]:
    """Which tools may run for this request.

    * names outside the allowlist are blocked (whatever the model asked for)
    * no account (prospect) -> only public tools
    * lookup_account always runs first for signed-in customers
    The account id is NOT an input here: callers pass state["account_id"] to run_tool themselves.
    """
    events: list[Event] = []
    allowed: list[str] = []
    for name in requested or []:
        if name not in ALLOWED_TOOLS:
            events.append(make_event("processing", "tool_allowlist", "block", f"tool not allowed: {str(name)[:40]}"))
        elif name not in allowed:
            allowed.append(name)
    signed_in = bool(account_id) and segment != "prospect"
    if not signed_in:
        blocked = [t for t in allowed if t in ACCOUNT_TOOLS]
        if blocked:
            events.append(make_event("processing", "tool_requires_account", "block",
                                     "account tools skipped (no signed-in account): " + ",".join(blocked)))
        return [t for t in allowed if t in PUBLIC_TOOLS], events
    return ["lookup_account"] + [t for t in allowed if t != "lookup_account"], events
