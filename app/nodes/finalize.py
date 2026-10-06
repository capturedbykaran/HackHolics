"""Graph node: response JSON, escalation templates, handoff.

Owner: A
"""


"""Node 7: finalize. Owner: A.

Builds the SupportResponse. No LLM here: every customer-facing text for refusals, clarifications,
not-found and escalations is a template, so the system can never promise something a human
has not approved.
"""
import logging
from typing import Any

from app import audit, llm
from app.guard import redact
from app.schemas import (Chunk, Citation, ClassifierOut, Decision, HandoffBundle, SupportResponse,
                         ToolResult)
from app import tools

log = logging.getLogger("insightdesk.finalize")

# ----------------------------------------------------------------- templates
REFUSED = {
    "other_account": ("I can only help with the account you are signed in with, so I can't share or "
                      "look up details of another account. If you need that information, the account "
                      "owner can contact us directly."),
    "secret": ("For your security I can't display or repeat passwords, tokens, keys or reset links "
               "in chat. I can start the secure reset flow for your own account instead."),
}
CLARIFY = ("I want to help, but I need a bit more detail. Could you tell me which feature or workflow "
           "this is about, the exact error message or code you see, and which CloudFlow version you use?")
OUT_OF_SCOPE = ("I can only help with CloudFlow product support, such as workflows, integrations, API "
                "usage, billing and your account. Is there something about CloudFlow I can help with?")
NOT_FOUND = ("I could not find this information in the CloudFlow documentation, so I don't want to "
             "guess. I can pass your question to our support team if you would like.")

ESCALATION = {
    "billing": ("I'm sorry about this. I've passed your case to our billing team together with the "
                "details we have, so you won't need to repeat them. I can't issue refunds or credits "
                "myself; a team member will review your request and follow up."),
    "security": ("Thank you for flagging this. I've passed it to our security team with the details "
                 "we have. A team member will follow up with you."),
    "angry": ("I'm sorry for the trouble, and I understand this is frustrating. I've handed your case "
              "to a human colleague with everything we know, so you won't have to explain it again."),
    "default": ("I'm not able to resolve this safely myself, so I've passed it to our support team "
                "with the full context. A team member will follow up with you."),
}


def _escalation_text(reasons: list[str], cls: ClassifierOut, handoff_id: str, sla: str) -> str:
    r = set(reasons)
    if r & {"refund_request", "credit_request", "billing_dispute", "billing", "legal_matter"} \
            or cls.type == "billing":
        key = "billing"
    elif r & {"security_incident", "security", "account_deletion"} or cls.type == "security":
        key = "security"
    elif r & {"explicit_human_request", "repeated_contact", "strong_negative_sentiment"} \
            or cls.sentiment == "angry":
        key = "angry"
    else:
        key = "default"
    text = ESCALATION[key]
    if sla:
        text += f" {sla}"
    return f"{text} (Reference: {handoff_id})"


# ----------------------------------------------------------------- helpers
def _redact_obj(o: Any) -> Any:
    if isinstance(o, str):
        return redact(o)[0]
    if isinstance(o, dict):
        return {k: _redact_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_redact_obj(v) for v in o]
    return o


def _clean_tools(results: list[ToolResult]) -> list[ToolResult]:
    return [t.model_copy(update={"output": _redact_obj(t.output)}) for t in results]


def _citations(draft, chunks: list[Chunk]) -> list[Citation]:
    by_key = {(c.source_id, c.section): c for c in chunks}
    out = []
    for cit in (draft.citations if draft else []):
        c = by_key.get((cit.source_id, cit.section))
        if c:
            out.append(Citation(source_id=c.source_id, doc_type=c.doc_type, section=c.section,
                                product_versions=c.product_versions, last_updated=c.last_updated))
    return out


def _queue_priority(cls: ClassifierOut, reasons: list[str]) -> tuple[str, str]:
    if cls.type == "billing" or any("billing" in r or "refund" in r or "credit" in r for r in reasons):
        queue = "billing"
    elif cls.type == "security" or any("security" in r for r in reasons):
        queue = "security"
    elif cls.type in ("troubleshooting", "account", "how_to") or any("tool" in r for r in reasons):
        queue = "technical"
    else:
        queue = "general"
    if queue == "security" or cls.urgency == "urgent":
        priority = "urgent"
    elif cls.urgency == "high" or cls.sentiment == "angry":
        priority = "high"
    else:
        priority = "normal"
    return queue, priority


def _unresolved(cls: ClassifierOut, draft, reasons: list[str]) -> list[str]:
    q = []
    if cls.type == "billing" or any("refund" in r or "billing" in r or "credit" in r for r in reasons):
        q.append("Approve or reject the customer's refund/credit request")
    if cls.type == "security":
        q.append("Verify the customer and handle the security concern")
    if draft and draft.missing_info:
        q += [f"Not covered by documentation: {m}" for m in draft.missing_info]
    return q or ["Review the case and respond to the customer"]


def _build_handoff(state: dict, cls: ClassifierOut, reasons: list[str], draft, chunks: list[Chunk],
                   tool_results: list[ToolResult]) -> HandoffBundle:
    queue, priority = _queue_priority(cls, reasons)
    evidence: list[dict] = [{"tool": t.tool, "ok": t.ok, "output": t.output, "error": t.error}
                            for t in tool_results]
    evidence += [{"source_id": c.source_id, "section": c.section} for c in (draft.citations if draft else [])]
    msg = state.get("redacted_message", "")
    summary = f"Customer ({cls.type}, {cls.sentiment}, urgency {cls.urgency}) wrote: {msg[:300]}"
    attempted = redact(draft.answer)[0] if draft and draft.answer else None
    return HandoffBundle(
        queue=queue, priority=priority, intent=cls.type, urgency=cls.urgency, sentiment=cls.sentiment,
        escalation_reasons=reasons or ["unspecified"], customer_summary=summary,
        evidence=_redact_obj(evidence), attempted_answer=attempted,
        unresolved_questions=_unresolved(cls, draft, reasons), pii_redacted=True,
        account_id=state["account_id"], conversation_id=state["conversation_id"],
        trace_id=state["trace_id"])


# ----------------------------------------------------------------- node
def finalize_node(state: dict) -> dict:
    cls: ClassifierOut = state.get("classifier") or ClassifierOut(type="out_of_scope", confidence=0.0)
    draft, critic = state.get("draft"), state.get("critic")
    chunks: list[Chunk] = state.get("chunks", [])
    tool_results = _clean_tools(state.get("tool_results", []))
    decision: Decision | None = state.get("decision")
    early = state.get("early")
    handoff_id = None
    citations: list[Citation] = []

    if early == "refused":
        answer_type, answer = "refused", REFUSED.get(state.get("early_reason") or "", REFUSED["other_account"])
    elif early == "clarification_needed":
        answer_type, answer = "clarification_needed", CLARIFY
    elif early == "out_of_scope":
        answer_type, answer = "out_of_scope", OUT_OF_SCOPE
    else:
        action = decision.action if decision else "escalate"
        reasons = list(decision.reasons) if decision else ["decision_missing"]
        if action == "revise":  # revision budget exhausted -> treat as escalation
            action, reasons = "escalate", reasons + ["revision_limit_reached"]
        if action == "answer" and draft and draft.answer.strip():
            answer_type, answer = "answered", redact(draft.answer)[0]
            citations = _citations(draft, chunks)
        elif action in ("answer", "not_found"):
            answer_type, answer = "not_found", NOT_FOUND
        else:
            answer_type = "escalated"
            bundle = _build_handoff(state, cls, reasons, draft, chunks, tool_results)
            handoff_id = tools.create_handoff(bundle)
            answer = _escalation_text(reasons, cls, handoff_id, sla="")  # no SLA promise unless a human approved one

    response = SupportResponse(
        trace_id=state["trace_id"], conversation_id=state["conversation_id"],
        answer_type=answer_type, answer=answer, intent=cls, citations=citations,
        tools_invoked=tool_results,
        critic=({"groundedness": critic.groundedness, "coverage": critic.coverage,
                 "pii_risk": critic.pii_risk, "policy_risk": critic.policy_risk,
                 "decision": decision.action if decision else None,
                 "revisions": state.get("revisions", 0)} if critic else None),
        conflicts_detected=state.get("conflicts", []), handoff_id=handoff_id,
        as_of_date=state["as_of_date"])

    # ---- audit (never allowed to break the response)
    calls = llm.get_call_log()
    audit_state = {**state, "response": response, "llm_calls": calls,
                   "model": ",".join(sorted({c["model"] for c in calls})) or "none",
                   "tokens": sum(c["tokens"] for c in calls),
                   "decision": decision, "handoff_id": handoff_id}
    try:
        audit.write_audit(audit_state)
        audit.append_conversation(state["conversation_id"], "user",
                                  {"message": state.get("redacted_message", ""), "trace_id": state["trace_id"]})
        audit.append_conversation(state["conversation_id"], "assistant",
                                  {"answer_type": answer_type, "answer": answer, "trace_id": state["trace_id"]})
    except Exception:  # noqa: BLE001
        log.exception("audit write failed")
    return {"response": response, "llm_calls": calls}