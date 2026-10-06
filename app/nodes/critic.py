"""Graph node: groundedness / coverage / PII / policy risk (LLM).

Owner: A
"""

"""Node 5: critic (LLM call 3) + deterministic safety checks. Owner: A.

The critic only scores and recommends. escalation.decide() (code) makes the final decision.
Code checks below can only make the verdict stricter, never more lenient.
"""
import json
import re

from app import llm
from app.guard import redact
from app.nodes.compose import _fmt_chunks, _fmt_tools, evidence_tools
from app.schemas import ComposerOut, CriticOut

# Phrases that promise something only a human may approve.
_PROMISE = re.compile(
    r"\b(i(?:'ve| have)\s+(?:refunded|issued|credited|processed|approved)"
    r"|we(?:'ll| will)\s+(?:refund|credit)"
    r"|(?:your\s+)?refund\s+(?:has\s+been|is|will\s+be)\s+(?:approved|processed|issued|guaranteed)"
    r"|you(?:'ll| will)\s+(?:receive|get)\s+(?:a\s+)?(?:full\s+)?(?:refund|credit)"
    r"|i(?:'ll| will)\s+(?:refund|credit))", re.I)
_LINK_OR_TOKEN = re.compile(r"(https?://\S*(?:reset|token)\S*|\b(?:token|password)\s*[:=]\s*\S+)", re.I)


def critic_node(state: dict) -> dict:
    draft: ComposerOut = state["draft"]
    chunks, tools = state.get("chunks", []), state.get("tool_results", [])
    failures = list(state.get("failures", []))

    system = llm.load_prompt("critic.txt")
    answer, _ = redact(draft.answer)
    user = (f"DRAFT:\n{answer}\n\nCITATIONS: {json.dumps([c.model_dump() for c in draft.citations])}\n\n"
            f"SOURCES:\n{_fmt_chunks(chunks)}\n\nTOOL RESULTS:\n{_fmt_tools(tools)}\n\n"
            f"<customer_message>\n{state['redacted_message']}\n</customer_message>")
    try:
        verdict: CriticOut = llm.json_call(system, user, CriticOut, state, node="critic")
    except llm.LLMError:
        verdict = CriticOut(groundedness=0.0, coverage="none", recommendation="escalate",
                            issues=["critic_unavailable"])
        failures.append("critic_llm_failed")

    return {"critic": _harden(verdict, draft, bool(evidence_tools(state))), "failures": failures}


def _harden(v: CriticOut, draft: ComposerOut, has_tools: bool) -> CriticOut:
    """Deterministic checks that override the LLM when they find a problem."""
    upd: dict = {}
    issues = list(v.issues)

    _, pii_found = redact(draft.answer)
    if pii_found or _LINK_OR_TOKEN.search(draft.answer):
        upd["pii_risk"] = "high"
        issues.append("draft contains PII, a secret, a token or a reset link")
    if _PROMISE.search(draft.answer):
        upd["policy_risk"] = "high"
        issues.append("draft promises a refund/credit that only a human can approve")
    if not draft.citations and not has_tools:
        upd["groundedness"] = min(v.groundedness, 0.4)
        issues.append("no valid citation")

    if upd.get("pii_risk") == "high" or upd.get("policy_risk") == "high":
        if v.recommendation == "answer":
            upd["recommendation"] = "revise"
    if issues != v.issues:
        upd["issues"] = issues
    return v.model_copy(update=upd) if upd else v