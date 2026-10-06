"""Layer 3 - OUTPUT guardrails: before anything reaches the customer, the logs or a handoff. Owner: A.

check_output(answer, state)  -> problem codes (empty list = safe)
sanitize_response(resp, state) final pass on every outgoing field
sanitize_bundle / sanitize_audit_state  the same for the handoff bundle and the audit record
"""
import json
from typing import Any

from app.guardrails import patterns as P
from app.guardrails.input_guard import redact_text
from app.guardrails.processing_guard import strip_reasoning
from app.schemas import HandoffBundle, SupportResponse

PII_SECRET_CODES = {"pii", "secret_or_link"}
POLICY_CODES = {"refund_promise", "account_action_claim"}


def _sources_text(state: dict) -> str:
    parts = [c.text for c in state.get("chunks", []) or []]
    parts += [json.dumps(t.output, default=str) for t in state.get("tool_results", []) or []]
    parts += [c.text for c in state.get("upcoming", []) or []]
    return "\n".join(parts)


def check_output(answer: str, state: dict) -> list[str]:
    """Problem codes found in a draft answer: pii, secret_or_link, refund_promise, account_action_claim,
    other_account, prompt_leak, reasoning_leak, unsupported_url."""
    text = answer or ""
    codes: list[str] = []
    _, types = redact_text(text)
    if types:
        codes.append("pii")
    if P.RESET_LINK.search(text) or P.SECRET_ASSIGN.search(text) or {"API_KEY", "TOKEN", "PASSWORD"} & set(types):
        codes.append("secret_or_link")
    if P.REFUND_PROMISE.search(text):
        codes.append("refund_promise")
    if P.ACCOUNT_ACTION_CLAIM.search(text):
        codes.append("account_action_claim")

    sources = _sources_text(state)
    own = state.get("account_id")
    foreign = {a for a in P.ACCOUNT_ID.findall(text) if a != own and a not in sources}
    if foreign:
        codes.append("other_account")
    if P.PROMPT_LEAK.search(text):
        codes.append("prompt_leak")
    if P.REASONING_LEAK.search(text):
        codes.append("reasoning_leak")
    if any(u.rstrip(".,;:!?") not in sources for u in P.URL.findall(text)):
        codes.append("unsupported_url")
    return codes


# ------------------------------------------------------------------ sanitising
def sanitize_text(text: Any, cap: int | None = None) -> Any:
    if not isinstance(text, str):
        return text
    out, _ = redact_text(strip_reasoning(text))
    if cap and len(out) > cap:
        out = out[:cap - 1].rstrip() + "…"
    return out


def sanitize_obj(o: Any) -> Any:
    """Recursively redact every string in dicts/lists (tool outputs, evidence, ...)."""
    if isinstance(o, str):
        return sanitize_text(o)
    if isinstance(o, dict):
        return {k: sanitize_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [sanitize_obj(v) for v in o]
    return o


def sanitize_response(resp: SupportResponse, state: dict | None = None) -> SupportResponse:
    """Final pass on every outgoing field: redact PII, strip reasoning, cap the answer length."""
    tools = [t.model_copy(update={"output": sanitize_obj(t.output), "error": sanitize_text(t.error)})
             for t in resp.tools_invoked]
    return resp.model_copy(update={
        "answer": sanitize_text(resp.answer, P.MAX_ANSWER_CHARS),
        "tools_invoked": tools,
        "conflicts_detected": [sanitize_text(c) for c in resp.conflicts_detected]})


def sanitize_bundle(bundle: HandoffBundle) -> HandoffBundle:
    return HandoffBundle.model_validate(sanitize_obj(bundle.model_dump()))


def sanitize_audit_state(state: dict, withheld_codes: list[str] | None = None) -> dict:
    """Copy of the state that is safe to persist: raw request text removed, tool output and draft cleaned.

    A draft that failed the output check is withheld (its text is replaced); the codes stay in the events.
    """
    out = dict(state)
    req = state.get("req")
    if req is not None:
        out["req"] = req.model_copy(update={"message": state.get("redacted_message", "")})
    out["tool_results"] = [t.model_copy(update={"output": sanitize_obj(t.output), "error": sanitize_text(t.error)})
                           for t in state.get("tool_results", []) or []]
    draft = state.get("draft")
    if draft is not None:
        answer = ("[withheld by output guardrail: " + ",".join(withheld_codes) + "]"
                  if withheld_codes else sanitize_text(draft.answer))
        out["draft"] = draft.model_copy(update={"answer": answer})
    return out
