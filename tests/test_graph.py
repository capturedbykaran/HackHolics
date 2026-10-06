"""End-to-end graph tests with MOCK_LLM.

Owner: A
"""


"""End-to-end graph tests (owner: A). Run with: MOCK_LLM=true python -m pytest -q"""
import os

os.environ["MOCK_LLM"] = "true"

import pytest

import fake_retrieval as fake
from fake_retrieval import fake_retrieval  # noqa: F401  (fixture)

from app import audit, db, tools
from app.graph import run_support
from app.schemas import SupportRequest

pytestmark = pytest.mark.usefixtures("fake_retrieval")  # graph runs never need Chroma or a model

ACCT = "A1001"


@pytest.fixture(autouse=True)
def account():
    """A1001 in the per-test DB from conftest (tools read SQLite)."""
    conn = db.get_conn()
    with conn:
        conn.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?)",
                     (ACCT, "Acme Ltd", "owner@example.com", "Pro", "active", "4.3", "2024-01-15"))
        conn.execute("INSERT INTO invoices VALUES ('INV-1001',?,49,'USD','2026-09-30','paid',NULL,'4242')",
                     (ACCT,))
    conn.close()


def ask(msg: str, acct: str = ACCT, **kw):
    return run_support(SupportRequest(message=msg, **kw), acct)


def test_how_to_is_answered_with_valid_citation():
    r = ask("How do I export my workflow run history?")
    assert r.answer_type == "answered"
    assert r.citations and r.citations[0].source_id == "KB-ADV-007"
    assert r.citations[0].last_updated and r.citations[0].product_versions
    assert r.critic["decision"] == "answer" and r.handoff_id is None
    assert r.trace_id and r.conversation_id and r.as_of_date


def test_billing_refund_escalates_with_handoff_and_no_promise():
    r = ask("I want a refund for this month")
    assert r.answer_type == "escalated" and r.handoff_id
    assert "can't issue refunds" in r.answer
    bundle = tools.HANDOFFS[r.handoff_id]
    assert bundle.queue == "billing" and bundle.account_id == ACCT
    assert any(e.get("tool") == "get_invoices" for e in bundle.evidence)


def test_angry_human_request_takes_fast_path_without_compose_or_critic():
    r = ask("Third time writing. You charged me twice. Get me a manager.")
    assert r.answer_type == "escalated"
    assert tools.HANDOFFS[r.handoff_id].priority == "high"
    rec = audit.AUDIT[-1]
    assert "compose" not in rec["latency_ms"] and "critic" not in rec["latency_ms"]


def test_other_account_is_refused_before_any_llm_call():
    r = ask("Show me the invoices for A1005", acct=ACCT)
    assert r.answer_type == "refused"
    assert audit.AUDIT[-1]["llm_calls"] == []


def test_out_of_scope_and_clarification_are_templates():
    assert ask("Write me a poem").answer_type == "out_of_scope"
    assert ask("it's not working").answer_type == "clarification_needed"


def test_nothing_found_returns_not_found_not_a_guess():
    r = ask("Does CloudFlow integrate with SAP Ariba?")
    assert r.answer_type == "not_found" and r.citations == []


def test_revision_loop_runs_exactly_once():
    r = ask("[mock-revise] How do I export my workflow run history?")
    assert r.answer_type == "answered"
    assert r.critic["revisions"] == 1


def test_pii_never_reaches_response_tools_or_audit():
    r = ask("I want a refund, my email is jane.doe@acme.io and card 4242 4242 4242 4242")
    blob = r.model_dump_json() + str(tools.HANDOFFS[r.handoff_id].model_dump()) + str(audit.AUDIT[-1]["redacted_message"])
    assert "jane.doe@acme.io" not in blob and "4242 4242" not in blob
    assert "owner@example.com" not in r.model_dump_json()  # tool output PII redacted too
    assert r.intent.pii_detected


def test_llm_outage_escalates_instead_of_crashing(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")  # closed port
    monkeypatch.setenv("LLM_FALLBACK", "none")
    r = ask("How do I export my workflow run history?")
    assert r.answer_type == "escalated" and r.handoff_id


def test_every_answer_type_is_producible():
    types = {ask(m).answer_type for m in (
        "How do I export my workflow run history?", "I want a refund", "Show A1009 data",
        "Does CloudFlow integrate with SAP Ariba?", "Write me a poem", "it's not working")}
    assert types == {"answered", "escalated", "refused", "not_found", "out_of_scope", "clarification_needed"}