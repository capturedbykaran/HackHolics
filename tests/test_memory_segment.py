"""Conversation memory (same conversation_id) and customer segmentation. Owner: A.

Run with: MOCK_LLM=true python -m pytest -q
"""
import os

os.environ["MOCK_LLM"] = "true"

import pytest

import fake_retrieval as fake
from fake_retrieval import fake_retrieval  # noqa: F401  (fixture)

from app import audit, db, llm, tools
from app.graph import run_support
from app.schemas import SupportRequest
from app.segment import segment_user

pytestmark = pytest.mark.usefixtures("fake_retrieval")  # graph runs never need Chroma or a model

AS_OF = "2026-10-06"
ACCOUNT_TOOLS = {"lookup_account", "get_usage", "get_plan_limits", "get_invoices",
                 "check_refund_eligibility", "send_password_reset"}


def add_account(account_id: str, created_at: str = "2024-01-15", status: str = "active") -> None:
    conn = db.get_conn()
    with conn:
        conn.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?)",
                     (account_id, f"Company {account_id}", f"owner.{account_id.lower()}@example.com",
                      "Pro", status, "4.3", created_at))
    conn.close()


@pytest.fixture(autouse=True)
def accounts():
    add_account("A1001")
    add_account("A2002")


@pytest.fixture
def prompts(monkeypatch):
    """Capture every (node, user prompt) sent to the LLM; the mock still produces the output."""
    seen: list[tuple[str, str]] = []
    real = llm.json_call

    def spy(system, user, schema, state=None, **kw):
        seen.append((kw.get("node", ""), user))
        return real(system, user, schema, state, **kw)

    monkeypatch.setattr(llm, "json_call", spy)
    return seen


def ask(msg: str, acct: str | None = "A1001", cid: str | None = None):
    return run_support(SupportRequest(message=msg, conversation_id=cid, as_of_date=AS_OF), acct)


# ------------------------------------------------------------------ memory
def test_follow_up_is_rewritten_and_history_reaches_the_llm(prompts):
    r1 = ask("How do I export my workflow run history? I'm on 4.3")
    assert r1.answer_type == "answered"
    prompts.clear()

    r2 = ask("and on 3.x?", cid=r1.conversation_id)
    assert r2.conversation_id == r1.conversation_id
    assert r2.intent.is_follow_up and "export" in r2.intent.standalone_question.lower()
    classify_prompt = next(u for node, u in prompts if node == "classify")
    assert "<conversation_history>" in classify_prompt and "export my workflow run history" in classify_prompt
    assert r2.answer_type == "answered" and r2.citations[0].source_id == "KB-ADV-007"


def test_version_is_carried_over_from_earlier_turn():
    r1 = ask("How do I export my workflow run history? I'm on 4.3")
    r2 = ask("and how do I filter the export by date?", cid=r1.conversation_id)
    assert r2.intent.product_version == "4.3"
    assert audit.AUDIT[-1]["version"] == "4.3"


def test_other_accounts_conversation_is_refused_without_llm_call():
    r1 = ask("How do I export my workflow run history?", acct="A1001")
    before = len(audit.get_conversation(r1.conversation_id, limit=0))

    r2 = ask("and on 3.x?", acct="A2002", cid=r1.conversation_id)
    assert r2.answer_type == "refused"
    assert audit.AUDIT[-1]["llm_calls"] == []
    assert len(audit.get_conversation(r1.conversation_id, limit=0)) == before  # nothing written into it
    assert "export" not in r2.answer.lower()


def test_third_angry_message_signals_repeated_contact_and_escalates():
    cid = ask("My workflow keeps failing with error CF-503").conversation_id
    ask("It still fails, this is ridiculous", cid=cid)
    r3 = ask("Still failing with CF-503. This is unacceptable.", cid=cid)
    rec = audit.AUDIT[-1]
    assert "repeated_contact" in rec["signals"] and rec["prior_user_turns"] == 2
    assert r3.answer_type == "escalated"
    assert "repeated_contact" in tools.HANDOFFS[r3.handoff_id].escalation_reasons


def test_pii_from_turn_one_never_reaches_turn_two(prompts):
    r1 = ask("My email is jane.doe@acme.io. How do I export my workflow run history?")
    prompts.clear()
    r2 = ask("and on 3.x?", cid=r1.conversation_id)
    blob = " ".join(u for _, u in prompts) + r2.model_dump_json() + str(audit.AUDIT[-1])
    assert prompts and "jane.doe@acme.io" not in blob
    assert "[EMAIL]" in " ".join(u for _, u in prompts)  # the redacted turn was used


# ------------------------------------------------------------------ segmentation
def test_prospect_gets_docs_answers_but_no_account_data():
    r = ask("How do I export my workflow run history?", acct=None)
    assert r.customer_segment == "prospect"
    assert r.answer_type == "answered" and r.citations

    r = ask("Show my invoices", acct=None)
    assert r.answer_type == "refused" and "sign in" in r.answer.lower()
    assert r.customer_segment == "prospect"

    used = {t["tool"] if isinstance(t, dict) else t.tool for rec in audit.AUDIT[-2:]
            for t in (rec["tool_results"] or [])}
    assert not used & ACCOUNT_TOOLS


def test_unknown_account_is_a_prospect():
    assert segment_user("A9999", AS_OF, {})[0] == "prospect"
    assert segment_user(None, AS_OF, {}) == ("prospect", {})


@pytest.mark.parametrize("created_at,status,expected", [
    ("2026-09-26", "active", "new_customer"),         # 10 days before as_of
    ("2025-09-01", "active", "existing_customer"),    # 400 days before as_of
    ("2026-09-26", "cancelled", "former_customer"),
])
def test_segment_by_signup_age_and_status(created_at, status, expected):
    add_account("A3003", created_at=created_at, status=status)
    segment, info = segment_user("A3003", AS_OF, db.load_registry())
    assert segment == expected
    assert "owner_email" not in info and "company_name" not in info


def test_segment_is_in_response_handoff_and_audit():
    add_account("A3003", created_at="2026-09-26")
    r = ask("I want a refund for this month", acct="A3003")
    assert r.customer_segment == "new_customer" and r.answer_type == "escalated"
    assert tools.HANDOFFS[r.handoff_id].customer_segment == "new_customer"
    assert audit.AUDIT[-1]["customer_segment"] == "new_customer"
    assert "new to CloudFlow" in r.answer and "can't issue refunds" in r.answer
