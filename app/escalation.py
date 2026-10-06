"""Node 6 policy: Annex A.3 escalation rules + Annex A.2 step 5. Owner: B.

decide(state, registry) -> Decision. Pure function, no I/O, no LLM, fully deterministic.
`registry` is the dict returned by app.policy.load_policy; every threshold used comes from it and the
rule_ids of the rules consulted are returned in Decision.rule_ids (the audit shows which policy decided).

Reason codes (kept compatible with nodes/finalize.py templates and queues):
  tool_failure, required_step_failed, refund_request, credit_request, billing_dispute, legal_matter,
  security_incident, account_deletion, explicit_human_request, repeated_contact, strong_negative_sentiment,
  unresolved_conflict, kb_gap_needs_outcome, no_critic_result, classifier_missing,
  low_groundedness_after_revision, policy_risk_after_revision, pii_risk_after_revision,
  critic_rejected_after_revision; revise: critic_below_threshold + groundedness_below_threshold,
  pii_risk_high, policy_risk_high, coverage_none, critic_recommends_escalation, critic_recommends_revision;
  not_found: kb_gap.
"""
import re
from typing import Any

from app.policy import Rule, default_policy, threshold
from app.schemas import Decision

# Intents the graph sends straight to decide without drafting (graph.FAST_ESCALATE_INTENTS): nothing can
# be answered from the docs for them, so they always need an outcome from a human.
NO_DRAFT_INTENTS = {"complaint", "security"}

TOPIC_REASON = {
    "refund": "refund_request",
    "credit": "credit_request",
    "billing_dispute": "billing_dispute",
    "legal": "legal_matter",
    "security_incident": "security_incident",
    "account_deletion": "account_deletion",
}

# Keyword backstop for R2 in case the classifier misses a topic. "refund policy" style questions are
# informational, so they are excluded (precision matters as much as recall).
_BACKSTOP = [
    ("refund", re.compile(r"\brefund(?!\s+(?:policy|policies|window|terms|eligibility))|\bmoney back\b", re.I)),
    ("billing_dispute", re.compile(r"\bchargeback\b|\bcharged (?:me )?twice\b|\bdouble[- ]charged?\b", re.I)),
    ("legal", re.compile(r"\blawyer\b|\blegal action\b|\bsue\b", re.I)),
    ("security_incident", re.compile(r"\bhacked\b|\bunauthori[sz]ed (?:login|access)\b", re.I)),
    ("account_deletion", re.compile(r"\b(?:delete|close) my account\b", re.I)),
]


def _add(reasons: list[str], *codes: str) -> None:
    for c in codes:
        if c not in reasons:
            reasons.append(c)


def decide(state: dict, registry: dict[str, Rule] | None = None) -> Decision:
    policy = registry if registry is not None else default_policy()
    used: list[str] = []

    def val(parameter: str) -> Any:
        value, rule_id = threshold(policy, parameter)
        if rule_id not in used:
            used.append(rule_id)
        return value

    cls = state.get("classifier")
    draft, critic = state.get("draft"), state.get("critic")
    if cls is None:  # classify always sets it; if not, never guess
        return Decision(action="escalate", reasons=["classifier_missing"], rule_ids=used)

    reasons: list[str] = []

    # a. R4: a required tool or step failed
    for f in state.get("failures", []) or []:
        if f.startswith("tool_failed:"):
            _add(reasons, "tool_failure")
        elif f.endswith("_llm_failed") or f.endswith("_error"):
            _add(reasons, "required_step_failed")

    # b. R2: topics only a human may decide (not for prospects: they have no account to act on)
    if state.get("customer_segment") != "prospect":
        allowed = set(val("escalate_topics"))
        topics = set(cls.escalation_topics)
        message = state.get("redacted_message", "") or ""
        topics |= {topic for topic, rx in _BACKSTOP if rx.search(message)}
        for topic in sorted(topics & allowed, key=list(TOPIC_REASON).index):
            _add(reasons, TOPIC_REASON[topic])

    # c. R3: explicit human request, or strong negative sentiment together with repeated contact
    if cls.asks_for_human:
        _add(reasons, "explicit_human_request")
    negative = set(val("negative_sentiments"))
    repeat_threshold = val("repeat_contact_threshold")
    repeated = (state.get("prior_user_turns", 0) >= repeat_threshold
                or "repeated_contact" in (state.get("signals") or []))
    if cls.sentiment in negative and repeated:
        _add(reasons, "repeated_contact", "strong_negative_sentiment")

    # d. A.2 step 5: precedence could not resolve a conflict -> a human sees both sources
    if state.get("unresolved_conflicts"):
        _add(reasons, "unresolved_conflict")

    if reasons:
        return Decision(action="escalate", reasons=reasons, rule_ids=used)

    # e. R5: the knowledge base does not cover the question
    if draft is None or not draft.can_answer:
        needs = cls.needs_outcome or (draft is None and cls.type in NO_DRAFT_INTENTS)
        if needs:
            return Decision(action="escalate", reasons=["kb_gap_needs_outcome"], rule_ids=used)
        return Decision(action="not_found", reasons=["kb_gap"], rule_ids=used)

    # f. R1: critic below the threshold, after at most one revision
    if critic is None:
        return Decision(action="escalate", reasons=["no_critic_result"], rule_ids=used)
    min_grounded = val("critic_min_groundedness")
    max_revisions = val("max_revisions")
    weak: list[str] = []
    if critic.groundedness < min_grounded:
        weak.append("groundedness_below_threshold")
    if critic.pii_risk == "high":
        weak.append("pii_risk_high")
    if critic.policy_risk == "high":
        weak.append("policy_risk_high")
    if critic.coverage == "none":
        weak.append("coverage_none")
    if critic.recommendation == "escalate":
        weak.append("critic_recommends_escalation")
    if critic.recommendation == "revise":  # also set by the output guardrails (e.g. URL not in sources)
        weak.append("critic_recommends_revision")
    if weak:
        if state.get("revisions", 0) < max_revisions:
            return Decision(action="revise", reasons=["critic_below_threshold"] + weak, rule_ids=used)
        after: list[str] = []
        if "policy_risk_high" in weak:
            _add(after, "policy_risk_after_revision")
        if "pii_risk_high" in weak:
            _add(after, "pii_risk_after_revision")
        if {"groundedness_below_threshold", "coverage_none", "critic_recommends_escalation"} & set(weak):
            _add(after, "low_groundedness_after_revision")
        return Decision(action="escalate", reasons=after or ["critic_rejected_after_revision"], rule_ids=used)

    # g. answerable how-to / troubleshooting with high groundedness and no policy risk
    return Decision(action="answer", reasons=[], rule_ids=used)
