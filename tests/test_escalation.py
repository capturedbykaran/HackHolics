"""Node 6 (decide): Annex A.3 escalation policy + A.2 step 5, driven by policy_registry. Owner: B.

Pure unit tests on escalation.decide() plus a few graph runs. MOCK_LLM=true, no model.
"""
import os

os.environ["MOCK_LLM"] = "true"

import pytest

from app import audit, db, policy, precedence, retrieval, tools
from app.escalation import decide
from app.graph import run_support
from app.nodes.decide import decide_node
from app.nodes.gather import gather_node
from app.policy import default_policy, load_policy, threshold
from app.schemas import (Chunk, ClassifierOut, ComposerCitation, ComposerOut, CriticOut, Decision,
                         SupportRequest, ToolResult)

AS_OF = "2026-10-06"
GOOD_DRAFT = ComposerOut(answer="Open Runs, click Export.", citations=[ComposerCitation(source_id="KB-1", section="S")])
GOOD_CRITIC = CriticOut(groundedness=0.9, coverage="complete", recommendation="answer")


def state(cls=None, draft=GOOD_DRAFT, critic=GOOD_CRITIC, **kw) -> dict:
    return {"classifier": cls or ClassifierOut(type="how_to"), "draft": draft, "critic": critic,
            "redacted_message": "How do I export my run history?", "revisions": 0, "failures": [],
            "signals": [], "prior_user_turns": 0, "unresolved_conflicts": [], "customer_segment": "existing_customer",
            "as_of_date": AS_OF, **kw}


def critic(**kw) -> CriticOut:
    return CriticOut(**{"groundedness": 0.9, "coverage": "complete", "recommendation": "answer", **kw})


def add_rule(rule_id, parameter, operator, value, scope="ALL", effective_from="2025-01-01"):
    conn = db.get_conn()
    with conn:
        conn.execute("INSERT OR REPLACE INTO policy_registry VALUES (?,?,?,?,?,?,?,?,?)",
                     (rule_id, f"{parameter} rule", parameter, operator, value, scope, effective_from, "KB-POL-002",
                      "Escalation policy"))
    conn.close()


@pytest.fixture(autouse=True)
def account():
    conn = db.get_conn()
    with conn:
        conn.execute("INSERT INTO accounts VALUES ('A1001','Acme','owner@example.com','Pro','active','4.3','2024-01-15')")
        conn.execute("INSERT INTO invoices VALUES ('INV-1001','A1001',49,'USD','2026-09-30','paid',NULL,'4242')")
    conn.close()


def ask(msg: str, acct="A1001"):
    return run_support(SupportRequest(message=msg, as_of_date=AS_OF), acct)


# ================================================================ 1. do not escalate the answerable
def test_grounded_how_to_is_answered():
    d = decide(state())
    assert d.action == "answer" and d.reasons == []
    assert "DEFAULT-critic_min_groundedness" in d.rule_ids


def test_troubleshooting_with_a_good_draft_is_answered():
    assert decide(state(ClassifierOut(type="troubleshooting", sentiment="frustrated"))).action == "answer"


def test_billing_how_to_without_a_topic_is_answered():  # precision: "how do I download my invoice"
    cls = ClassifierOut(type="billing", tools_needed=["get_invoices"], needs_outcome=False)
    d = decide(state(cls, redacted_message="how do I download my invoice"))
    assert d.action == "answer"


@pytest.mark.parametrize("msg", ["What is your refund policy?", "What is the refund window for Pro?"])
def test_questions_about_the_refund_policy_are_not_refund_requests(msg):
    assert decide(state(redacted_message=msg)).action == "answer"


# ================================================================ 2. R1 groundedness / revision budget
def test_low_groundedness_revises_once_then_escalates():
    low = critic(groundedness=0.6, recommendation="revise")
    first = decide(state(critic=low, revisions=0))
    assert first.action == "revise" and first.reasons[:2] == ["critic_below_threshold", "groundedness_below_threshold"]
    second = decide(state(critic=low, revisions=1))
    assert second.action == "escalate" and second.reasons == ["low_groundedness_after_revision"]


def test_groundedness_exactly_at_the_threshold_passes():
    assert decide(state(critic=critic(groundedness=0.75))).action == "answer"


# ================================================================ 3. policy / pii risk
def test_policy_risk_high_revises_then_escalates():
    risky = critic(policy_risk="high", recommendation="revise")
    assert decide(state(critic=risky, revisions=0)).action == "revise"
    d = decide(state(critic=risky, revisions=1))
    assert d.action == "escalate" and "policy_risk_after_revision" in d.reasons


def test_pii_risk_high_escalates_after_revision():
    d = decide(state(critic=critic(pii_risk="high", recommendation="revise"), revisions=1))
    assert d.action == "escalate" and "pii_risk_after_revision" in d.reasons


def test_critic_recommending_revision_alone_counts_as_weak():  # set by the output guardrails
    assert decide(state(critic=critic(recommendation="revise"))).action == "revise"
    assert decide(state(critic=critic(recommendation="revise"), revisions=1)).reasons == ["critic_rejected_after_revision"]


def test_critic_coverage_none_or_escalate_recommendation_is_weak():
    assert decide(state(critic=critic(coverage="none"))).action == "revise"
    assert decide(state(critic=critic(recommendation="escalate"), revisions=1)).action == "escalate"


def test_missing_critic_result_escalates():
    assert decide(state(critic=None)).reasons == ["no_critic_result"]


# ================================================================ 4. R2 topics
@pytest.mark.parametrize("topic,code", [
    ("refund", "refund_request"), ("credit", "credit_request"), ("billing_dispute", "billing_dispute"),
    ("legal", "legal_matter"), ("security_incident", "security_incident"), ("account_deletion", "account_deletion"),
])
def test_each_topic_escalates_with_its_reason_code(topic, code):
    d = decide(state(ClassifierOut(type="billing", escalation_topics=[topic], needs_outcome=True)))
    assert d.action == "escalate" and code in d.reasons
    assert "DEFAULT-escalate_topics" in d.rule_ids


# ================================================================ 5. keyword backstop
@pytest.mark.parametrize("msg,code", [
    ("I want my money back", "refund_request"),
    ("Please refund me", "refund_request"),
    ("You charged me twice", "billing_dispute"),
    ("open a chargeback", "billing_dispute"),
    ("my lawyer will call you", "legal_matter"),
    ("I will take legal action", "legal_matter"),
    ("I'll sue you", "legal_matter"),
    ("we were hacked", "security_incident"),
    ("unauthorized login on my workspace", "security_incident"),
    ("delete my account", "account_deletion"),
    ("close my account today", "account_deletion"),
])
def test_keyword_backstop_when_the_classifier_has_no_topics(msg, code):
    d = decide(state(ClassifierOut(type="how_to", escalation_topics=[]), redacted_message=msg))
    assert d.action == "escalate" and code in d.reasons


def test_backstop_keywords_need_word_boundaries():
    assert decide(state(redacted_message="Issues with the pursue button and the unhacked sandbox")).action == "answer"


def test_prospects_never_escalate_for_account_topics():
    cls = ClassifierOut(type="billing", escalation_topics=["refund"])
    d = decide(state(cls, customer_segment="prospect", redacted_message="refund me"))
    assert d.action == "answer"


# ================================================================ 7. R3
def test_explicit_human_request_escalates():
    d = decide(state(ClassifierOut(type="how_to", asks_for_human=True)))
    assert d.action == "escalate" and d.reasons == ["explicit_human_request"]


def test_negative_sentiment_with_repeated_contact_escalates():
    d = decide(state(ClassifierOut(type="troubleshooting", sentiment="angry"), prior_user_turns=2))
    assert d.action == "escalate" and d.reasons == ["repeated_contact", "strong_negative_sentiment"]
    d = decide(state(ClassifierOut(type="troubleshooting", sentiment="frustrated"), signals=["repeated_contact"]))
    assert "repeated_contact" in d.reasons
    assert {"DEFAULT-repeat_contact_threshold", "DEFAULT-negative_sentiments"} <= set(d.rule_ids)


def test_angry_on_first_contact_is_not_escalated():
    assert decide(state(ClassifierOut(type="troubleshooting", sentiment="angry"), prior_user_turns=0)).action == "answer"
    assert decide(state(ClassifierOut(type="troubleshooting", sentiment="angry"), prior_user_turns=1)).action == "answer"


def test_repeated_contact_with_neutral_sentiment_is_not_escalated():
    assert decide(state(prior_user_turns=5, signals=["repeated_contact"])).action == "answer"


# ================================================================ 8. R4
@pytest.mark.parametrize("failure,code", [
    ("tool_failed:get_invoices", "tool_failure"),
    ("classify_llm_failed", "required_step_failed"),
    ("compose_llm_failed", "required_step_failed"),
    ("critic_llm_failed", "required_step_failed"),
    ("gather_error", "required_step_failed"),
])
def test_failures_escalate(failure, code):
    d = decide(state(failures=[failure]))
    assert d.action == "escalate" and d.reasons == [code]


# ================================================================ 9. R5
def test_kb_gap_with_needed_outcome_escalates():
    d = decide(state(ClassifierOut(type="how_to", needs_outcome=True), draft=ComposerOut(answer="", can_answer=False)))
    assert d.action == "escalate" and d.reasons == ["kb_gap_needs_outcome"]


def test_kb_gap_without_outcome_is_not_found():
    d = decide(state(ClassifierOut(type="how_to", needs_outcome=False), draft=None, critic=None))
    assert d.action == "not_found" and d.reasons == ["kb_gap"]


@pytest.mark.parametrize("intent", ["security", "complaint"])
def test_fast_path_intents_have_no_draft_and_need_a_human(intent):
    d = decide(state(ClassifierOut(type=intent), draft=None, critic=None))
    assert d.action == "escalate" and d.reasons == ["kb_gap_needs_outcome"]


# ================================================================ 10. A.2 step 5 (graph run)
TICKET = Chunk(source_id="TKT-2025-0311", section="Export format", doc_type="ticket", authority_level=4,
               product_versions="4.x", last_updated="2026-05-01",
               text="Export workflow run history: customers report the export produces JSON only for runs history.")
CONFLICT = "unresolved: KB-ADV-007 vs TKT-2025-0311 on the export format"


def test_unresolved_conflict_escalates_unit():
    d = decide(state(unresolved_conflicts=[CONFLICT]))
    assert d.action == "escalate" and d.reasons == ["unresolved_conflict"]


@pytest.fixture
def conflicting_sources(monkeypatch):
    monkeypatch.setattr(retrieval, "_CORPUS", retrieval._CORPUS + [TICKET])
    monkeypatch.setattr(precedence, "resolve", lambda chunks: ["resolved: KB-GS-001 over KB-PLN-002", CONFLICT],
                        raising=False)


def test_gather_copies_unresolved_conflicts_and_both_sources(conflicting_sources):
    out = gather_node({"classifier": ClassifierOut(type="how_to"), "redacted_message": "How do I export my workflow "
                       "run history?", "account_id": "A1001", "customer_segment": "existing_customer",
                       "as_of_date": AS_OF})
    assert out["unresolved_conflicts"] == [CONFLICT]
    assert {c.source_id for c in out["conflict_sources"]} == {"KB-ADV-007", "TKT-2025-0311"}
    assert len(out["conflicts"]) == 2  # resolved + unresolved both stay visible in the response


def test_unresolved_conflict_escalates_in_a_graph_run(conflicting_sources):
    r = ask("How do I export my workflow run history?")
    assert r.answer_type == "escalated" and CONFLICT in r.conflicts_detected
    bundle = tools.HANDOFFS[r.handoff_id]
    assert "unresolved_conflict" in bundle.escalation_reasons and bundle.queue == "technical"
    assert audit.AUDIT[-1]["decision"].action == "escalate"


@pytest.mark.xfail(reason="finalize.py (Person A) must add state['conflict_sources'] to the handoff evidence")
def test_handoff_carries_both_conflicting_sources(conflicting_sources):
    r = ask("How do I export my workflow run history?")
    evidence = str(tools.HANDOFFS[r.handoff_id].evidence)
    assert "KB-ADV-007" in evidence and "TKT-2025-0311" in evidence


# ================================================================ 11-12, 14. policy_registry
def test_registry_override_changes_the_threshold_and_is_reported():
    add_rule("CRIT-STRICT", "critic_min_groundedness", ">=", "0.95", effective_from="2026-01-01")
    pol = load_policy(AS_OF, "Pro")
    assert threshold(pol, "critic_min_groundedness") == (0.95, "CRIT-STRICT")
    d = decide(state(critic=critic(groundedness=0.9)), pol)
    assert d.action == "revise" and "CRIT-STRICT" in d.rule_ids
    assert decide(state(critic=critic(groundedness=0.9)), default_policy()).action == "answer"


def test_registry_row_without_a_parameter_falls_back_per_parameter():
    pol = load_policy(AS_OF, "Pro")  # seed has critic_min_groundedness only
    assert pol["critic_min_groundedness"].rule_id == "CRITIC-MIN-GROUND"
    assert pol["max_revisions"].rule_id == "DEFAULT-max_revisions"


def test_missing_registry_uses_defaults():
    conn = db.get_conn()
    with conn:
        conn.execute("DELETE FROM policy_registry")
    conn.close()
    pol = load_policy(AS_OF, "Pro")
    d = decide(state(ClassifierOut(type="how_to", sentiment="angry"), prior_user_turns=2), pol)
    assert d.action == "escalate" and d.rule_ids and all(r.startswith("DEFAULT-") for r in d.rule_ids)
    assert decide(state(), pol).rule_ids == ["DEFAULT-escalate_topics", "DEFAULT-negative_sentiments",
                                              "DEFAULT-repeat_contact_threshold", "DEFAULT-critic_min_groundedness",
                                              "DEFAULT-max_revisions"]


def test_missing_table_uses_defaults(monkeypatch):
    conn = db.get_conn()
    with conn:
        conn.execute("DROP TABLE policy_registry")
    conn.close()
    pol = load_policy(AS_OF, None)
    assert {r.rule_id for r in pol.values()} == {f"DEFAULT-{p}" for p in policy.DEFAULTS}
    assert decide(state(), pol).action == "answer"


def test_future_dated_row_is_ignored():
    add_rule("FUTURE", "critic_min_groundedness", ">=", "0.99", effective_from="2027-01-01")
    pol = load_policy(AS_OF, "Pro")
    assert threshold(pol, "critic_min_groundedness") == (0.75, "CRITIC-MIN-GROUND")
    assert threshold(load_policy("2027-02-01", "Pro"), "critic_min_groundedness") == (0.99, "FUTURE")


def test_plan_scoped_rules():
    add_rule("ENT-STRICT", "critic_min_groundedness", ">=", "0.9", scope="Enterprise, Business",
             effective_from="2026-01-01")
    assert threshold(load_policy(AS_OF, "Pro"), "critic_min_groundedness")[1] == "CRITIC-MIN-GROUND"
    assert threshold(load_policy(AS_OF, "Enterprise"), "critic_min_groundedness")[1] == "ENT-STRICT"
    assert threshold(load_policy(AS_OF, None), "critic_min_groundedness")[1] == "CRITIC-MIN-GROUND"


def test_threshold_casts_and_in_lists():
    pol = default_policy()
    assert threshold(pol, "repeat_contact_threshold") == (2, "DEFAULT-repeat_contact_threshold")
    assert threshold(pol, "max_revisions")[0] == 1
    assert threshold(pol, "negative_sentiments")[0] == ["angry", "frustrated"]
    assert "legal" in threshold(pol, "escalate_topics")[0]


def test_topics_not_listed_in_the_registry_do_not_escalate():
    add_rule("ESC-TOPICS-02", "escalate_topics", "in", "legal,security_incident", effective_from="2026-01-01")
    pol = load_policy(AS_OF, "Pro")
    assert decide(state(redacted_message="I want a refund"), pol).action == "answer"
    assert decide(state(redacted_message="I will sue you"), pol).reasons == ["legal_matter"]


# ================================================================ 13. all reasons are collected
def test_multiple_reasons_are_all_collected_in_order():
    cls = ClassifierOut(type="billing", escalation_topics=["refund", "billing_dispute"], asks_for_human=True,
                        sentiment="angry", needs_outcome=True)
    d = decide(state(cls, failures=["tool_failed:get_invoices"], prior_user_turns=3,
                     unresolved_conflicts=[CONFLICT]))
    assert d.action == "escalate"
    assert d.reasons == ["tool_failure", "refund_request", "billing_dispute", "explicit_human_request",
                         "repeated_contact", "strong_negative_sentiment", "unresolved_conflict"]


def test_decide_is_deterministic_and_does_not_mutate_state():
    s = state(ClassifierOut(type="billing", escalation_topics=["refund"]), failures=["tool_failed:x"])
    before = repr(s)
    assert decide(s) == decide(s) and repr(s) == before


# ================================================================ the node
def test_decide_node_reads_the_plan_and_reports_rules():
    add_rule("ENT-STRICT", "critic_min_groundedness", ">=", "0.95", scope="Enterprise", effective_from="2026-01-01")
    results = [ToolResult(tool="lookup_account", output={"plan": "Enterprise"})]
    out = decide_node(state(critic=critic(groundedness=0.9), tool_results=results))
    assert out["decision"].action == "revise" and "ENT-STRICT" in out["policy_rules_applied"]
    out = decide_node(state(critic=critic(groundedness=0.9), tool_results=[]))  # no plan -> ALL-scoped rules
    assert out["decision"].action == "answer"


def test_decide_node_never_raises():
    out = decide_node({"classifier": ClassifierOut.model_construct(escalation_topics=None)})
    assert out["decision"] == Decision(action="escalate", reasons=["decide_error"])


# ================================================================ graph runs
@pytest.mark.parametrize("msg,code,queue", [
    ("I want a refund for this month", "refund_request", "billing"),
    ("You charged me twice for October", "billing_dispute", "billing"),
    ("Please give me a credit for the outage", "credit_request", "billing"),
    ("someone logged into my account last night", "security_incident", "security"),
])
def test_graph_escalates_policy_topics(msg, code, queue):
    r = ask(msg)
    assert r.answer_type == "escalated"
    bundle = tools.HANDOFFS[r.handoff_id]
    assert code in bundle.escalation_reasons and bundle.queue == queue
    assert audit.AUDIT[-1]["decision"].rule_ids  # the audit shows which policy decided


def test_graph_escalates_legal_and_account_deletion():
    for msg, code in (("my lawyer will contact you", "legal_matter"), ("please delete my account", "account_deletion")):
        r = ask(msg)
        assert r.answer_type == "escalated" and code in tools.HANDOFFS[r.handoff_id].escalation_reasons


def test_graph_does_not_escalate_information_requests():
    assert ask("How do I export my workflow run history?").answer_type == "answered"
    assert ask("What is your refund policy?").answer_type != "escalated"
    assert ask("how do I download my invoice").answer_type != "escalated"
    assert ask("Does CloudFlow integrate with SAP Ariba?").answer_type == "not_found"


def test_graph_two_calm_follow_ups_are_not_escalated_but_angry_third_is():
    cid = ask("How do I export my workflow run history?")
    r2 = run_support(SupportRequest(message="and on 3.x?", conversation_id=cid.conversation_id, as_of_date=AS_OF), "A1001")
    assert r2.answer_type == "answered"
    r3 = run_support(SupportRequest(message="This is ridiculous, it still fails", conversation_id=cid.conversation_id,
                                    as_of_date=AS_OF), "A1001")
    assert r3.answer_type == "escalated"
    assert {"repeated_contact", "strong_negative_sentiment"} <= set(tools.HANDOFFS[r3.handoff_id].escalation_reasons)


def test_seed_rows_are_valid_registry_rows():
    conn = db.get_conn()
    with conn:
        conn.execute("DELETE FROM policy_registry")
        conn.executemany("INSERT INTO policy_registry VALUES (?,?,?,?,?,?,?,?,?)", policy.SEED_ROWS)
    conn.close()
    pol = load_policy(AS_OF, "Pro")
    assert not any(r.rule_id.startswith("DEFAULT-") for r in pol.values())
    assert {r.source_id for r in pol.values()} == {"KB-POL-002"}
