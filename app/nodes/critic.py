"""Node 5: critic (LLM call 3) + deterministic safety checks. Owner: A.

The critic only scores and recommends. escalation.decide() (code) makes the final decision.
Code checks below (app/guardrails/output_guard.check_output) can only make the verdict stricter,
never more lenient.
"""
import json

from app import llm
from app.guardrails import check_output, make_event, wrap_data
from app.guardrails.output_guard import POLICY_CODES, PII_SECRET_CODES
from app.nodes.compose import _fmt_chunks, _fmt_tools, evidence_tools
from app.schemas import ComposerOut, CriticOut

_DESCRIPTIONS = {
    "pii": "draft contains PII",
    "secret_or_link": "draft contains a secret, a token or a reset link",
    "refund_promise": "draft promises a refund/credit/discount that only a human can approve",
    "account_action_claim": "draft claims an account change that the assistant cannot make",
    "other_account": "draft mentions an account id that is not the customer's",
    "prompt_leak": "draft leaks internal instructions",
    "reasoning_leak": "draft contains model reasoning",
    "unsupported_url": "draft contains a URL that is not in the sources",
}


def critic_node(state: dict) -> dict:
    draft: ComposerOut = state["draft"]
    chunks, tools = state.get("chunks", []), state.get("tool_results", [])
    failures = list(state.get("failures", []))

    system = llm.load_prompt("critic.txt")
    user = (f"{wrap_data('draft', draft.answer)}\n\nCITATIONS: "
            f"{json.dumps([c.model_dump() for c in draft.citations])}\n\n"
            f"SOURCES:\n{_fmt_chunks(chunks)}\n\nTOOL RESULTS:\n{_fmt_tools(tools)}\n\n"
            f"{wrap_data('customer_message', state['redacted_message'])}")
    try:
        verdict: CriticOut = llm.json_call(system, user, CriticOut, state, node="critic")
    except llm.LLMError:
        verdict = CriticOut(groundedness=0.0, coverage="none", recommendation="escalate",
                            issues=["critic_unavailable"])
        failures.append("critic_llm_failed")

    problems = check_output(draft.answer, state)
    events = list(state.get("guardrail_events", []))
    if problems:
        events.append(make_event("output", "output_check", "revise", ",".join(problems)))
    return {"critic": _harden(verdict, draft, bool(evidence_tools(state)), problems), "failures": failures,
            "guardrail_events": events}


def _harden(v: CriticOut, draft: ComposerOut, has_tools: bool, problems: list[str]) -> CriticOut:
    """Deterministic checks that override the LLM when they find a problem (stricter only)."""
    upd: dict = {}
    issues = list(v.issues)

    codes = set(problems)
    if codes & PII_SECRET_CODES:
        upd["pii_risk"] = "high"
    if codes & POLICY_CODES:
        upd["policy_risk"] = "high"
    issues += [_DESCRIPTIONS[c] for c in problems if c in _DESCRIPTIONS]
    if problems and v.recommendation == "answer":
        upd["recommendation"] = "revise"  # never softens an existing "escalate"

    if not draft.citations and not has_tools:
        upd["groundedness"] = min(v.groundedness, 0.4)
        issues.append("no valid citation")

    if issues != v.issues:
        upd["issues"] = issues
    return v.model_copy(update=upd) if upd else v
