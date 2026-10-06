"""Node 2: classify (LLM call 1). Owner: A."""
import re

from app import llm
from app.guardrails import ACCOUNT_TOOLS, wrap_data
from app.schemas import ClassifierOut

CLARIFY_MIN_CONFIDENCE = 0.3  # below this the request is treated as too vague to act on
ACCOUNT_DATA_INTENTS = {"account", "billing", "security"}  # prospects must sign in for these
_VERSION = re.compile(r"\b(?:v(?:ersion)?\s*)?(\d+\.(?:\d+|x))\b", re.I)


def format_history(history: list[dict]) -> str:
    return "\n".join(f"{t['role']}: {t['text']}" for t in history)


def history_version(history: list[dict]) -> str | None:
    """Latest product version stated earlier in this conversation (classifier output first, then text)."""
    for t in reversed(history):
        v = (t.get("intent") or {}).get("product_version")
        if v:
            return v
        if t.get("role") == "user" and (m := _VERSION.search(t.get("text", ""))):
            return m.group(1)
    return None


def repeated_contact(out: ClassifierOut, state: dict) -> bool:
    """Annex A.3 signal only; escalation.decide() (B) makes the decision."""
    return ((state.get("prior_user_turns", 0) >= 2 and out.sentiment in ("frustrated", "angry"))
            or state.get("prior_escalations", 0) >= 1)


def classify_node(state: dict) -> dict:
    req = state["req"]
    history = state.get("history", [])
    system = llm.load_prompt("classifier.txt")
    user = f"Product version stated in the request: {req.product_version or 'unknown'}\n\n"
    if history:
        user += wrap_data("conversation_history", format_history(history)) + "\n\n"
    user += wrap_data("customer_message", state["redacted_message"])
    failures = list(state.get("failures", []))
    try:
        out: ClassifierOut = llm.json_call(system, user, ClassifierOut, state, node="classify")
    except llm.LLMError:
        # Safe default: no tools, no guess. The failure flag routes the request to escalation.
        out = ClassifierOut(type="troubleshooting", confidence=0.0)
        failures.append("classify_llm_failed")

    signals = list(state.get("signals", []))
    update: dict = {}
    if "password_reset_requested" in signals:  # R9: secure reset flow; the link is never shown in chat
        update.update(type="security", needs_clarification=False,
                      tools_needed=sorted(set(out.tools_needed) | {"send_password_reset"}))
    if "abusive_language" in signals and out.sentiment in ("neutral", "positive"):
        update["sentiment"] = "frustrated"  # stricter only: feeds repeated-contact escalation
    if update:
        out = out.model_copy(update=update)

    version = out.product_version or req.product_version or history_version(history)
    out = out.model_copy(update={
        "pii_detected": out.pii_detected or bool(state.get("pii_found")),
        "product_version": version,
        "standalone_question": out.standalone_question if out.is_follow_up and history else ""})
    if repeated_contact(out, state) and "repeated_contact" not in signals:
        signals.append("repeated_contact")
    result: dict = {"classifier": out, "version": version, "signals": signals, "failures": failures}

    # Early exits: no retrieval, no further LLM calls.
    if out.type == "out_of_scope":
        result["early"] = "out_of_scope"
    elif state.get("customer_segment") == "prospect" and (
            out.type in ACCOUNT_DATA_INTENTS or set(out.tools_needed) & ACCOUNT_TOOLS):
        result.update(early="refused", early_reason="sign_in_required")
    elif "classify_llm_failed" not in failures and not out.asks_for_human and (
            out.needs_clarification or out.confidence < CLARIFY_MIN_CONFIDENCE):
        result["early"] = "clarification_needed"
    return result
