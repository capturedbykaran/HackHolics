"""LangGraph pipeline. Owner: A.

guard -> classify -> gather -> compose -> critic -> decide -> finalize     (7 nodes)

LLM nodes: classify, compose, critic (via llm.json_call).
Code nodes: guard, gather, decide, finalize. The answer/escalate decision is escalation.decide().
"""
import logging
import time
import uuid
from datetime import date

from langgraph.graph import END, StateGraph

from app import audit, llm
from app.nodes.classify import classify_node
from app.nodes.compose import compose_node
from app.nodes.critic import critic_node
from app.nodes.decide import decide_node
from app.nodes.finalize import finalize_node
from app.nodes.gather import gather_node
from app.nodes.guard import guard_node
from app.schemas import ClassifierOut, Decision, GraphState, SupportRequest, SupportResponse

log = logging.getLogger("insightdesk.graph")

MAX_REVISIONS = 1
FAST_ESCALATE_INTENTS = {"complaint", "security"}  # no point drafting an answer for these


# ------------------------------------------------------------------ node wrapper
def _wrap(name: str, fn):
    """Time every node; a crash in one node becomes a recorded failure instead of an HTTP 500."""
    def inner(state: dict) -> dict:
        t0 = time.perf_counter()
        try:
            out = fn(state) or {}
        except Exception:  # noqa: BLE001
            log.exception("node %s crashed", name)
            if name == "finalize":
                raise
            out = {"failures": list(state.get("failures", [])) + [f"{name}_error"]}
            if name == "decide":
                out["decision"] = Decision(action="escalate", reasons=["decide_error"])
        lat = dict(state.get("latency_ms", {}))
        lat[name] = round((time.perf_counter() - t0) * 1000, 1)
        out["latency_ms"] = lat
        return out
    return inner


# ------------------------------------------------------------------ routing
def after_guard(s: dict) -> str:
    return "finalize" if s.get("early") else "classify"


def after_classify(s: dict) -> str:
    return "finalize" if s.get("early") else "gather"


def after_gather(s: dict) -> str:
    c = s.get("classifier")
    if s.get("failures") or (c and (c.asks_for_human or c.type in FAST_ESCALATE_INTENTS)):
        return "decide"  # skip compose + critic; escalation policy handles it
    return "compose"


def after_compose(s: dict) -> str:
    d = s.get("draft")
    return "critic" if d and d.can_answer else "decide"  # nothing to critique -> not_found path


def after_decide(s: dict) -> str:
    d = s.get("decision")
    if d and d.action == "revise" and s.get("revisions", 0) < MAX_REVISIONS:
        return "compose"
    return "finalize"


# ------------------------------------------------------------------ build
def build_graph():
    g = StateGraph(GraphState)
    for name, fn in (("guard", guard_node), ("classify", classify_node), ("gather", gather_node),
                     ("compose", compose_node), ("critic", critic_node), ("decide", decide_node),
                     ("finalize", finalize_node)):
        g.add_node(name, _wrap(name, fn))
    g.set_entry_point("guard")
    g.add_conditional_edges("guard", after_guard, {"finalize": "finalize", "classify": "classify"})
    g.add_conditional_edges("classify", after_classify, {"finalize": "finalize", "gather": "gather"})
    g.add_conditional_edges("gather", after_gather, {"decide": "decide", "compose": "compose"})
    g.add_conditional_edges("compose", after_compose, {"critic": "critic", "decide": "decide"})
    g.add_edge("critic", "decide")
    g.add_conditional_edges("decide", after_decide, {"compose": "compose", "finalize": "finalize"})
    g.add_edge("finalize", END)
    return g.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


# ------------------------------------------------------------------ entry point
def run_support(req: SupportRequest, account_id: str) -> SupportResponse:
    llm.start_call_log()
    trace_id = audit.new_trace()
    conversation_id = req.conversation_id or f"C-{uuid.uuid4().hex[:6]}"
    as_of = req.as_of_date or date.today().isoformat()
    init: dict = {"req": req, "account_id": account_id, "trace_id": trace_id,
                  "conversation_id": conversation_id, "as_of_date": as_of,
                  "failures": [], "latency_ms": {}, "revisions": 0,
                  "chunks": [], "upcoming": [], "conflicts": [], "tool_results": []}
    try:
        return get_graph().invoke(init)["response"]
    except Exception:  # noqa: BLE001  - last-resort safety net
        log.exception("run_support failed")
        return SupportResponse(
            trace_id=trace_id, conversation_id=conversation_id, answer_type="not_found",
            answer="Sorry, something went wrong on our side and I could not process this request. "
                   "Please try again in a moment.",
            intent=ClassifierOut(type="out_of_scope", confidence=0.0), as_of_date=as_of)