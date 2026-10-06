"""Graph node: retrieval + precedence + tool calls. Owner: B (guardrail + retrieval wiring by A).

Contract used by A's code:
  * search query = classifier.standalone_question or redacted_message (conversation memory)
  * retrieval.search(query, version=, as_of_date=, k=) (C) -> {"chunks", "upcoming", "excluded", ...};
    hits are converted with .to_schema() into app.schemas.Chunk
  * retrieved chunks go through guardrails.sanitize_chunks (drop injected chunks, redact PII)
  * tools: guardrails.plan_tools (allowlist; prospects run no account tools); account_id comes ONLY
    from state, never from the classifier output or the message text
  * a tool that fails -> failures += ["tool_failed:<name>"]; a missing record ("not found") is data, not a failure
  * conflicts: precedence.resolve(chunks) -> list[str] (when B provides it); an entry starting with
    "unresolved:" is Annex A.2 step 5 -> state["unresolved_conflicts"], and the chunks it names go to
    state["conflict_sources"] so the handoff can carry BOTH sources
"""
from app import precedence, retrieval, tools
from app.guardrails import plan_tools, sanitize_chunks
from app.schemas import Chunk

UNRESOLVED_PREFIX = "unresolved:"
TOP_K = 5


def _as_chunk(hit) -> Chunk:
    return hit if isinstance(hit, Chunk) else hit.to_schema()


def gather_node(state: dict) -> dict:
    cls = state["classifier"]
    query = cls.standalone_question or state["redacted_message"]
    found = retrieval.search(query, version=state.get("version"), as_of_date=state.get("as_of_date"), k=TOP_K)
    chunks, events = sanitize_chunks([_as_chunk(h) for h in found.get("chunks", [])])  # layer 2: untrusted text
    upcoming, upcoming_events = sanitize_chunks([_as_chunk(h) for h in found.get("upcoming", [])])

    resolve = getattr(precedence, "resolve", None)  # B's A.2 resolver; absent until implemented
    conflicts = [str(c) for c in resolve(chunks)] if callable(resolve) else []
    unresolved = [c for c in conflicts if c.startswith(UNRESOLVED_PREFIX)]
    conflict_sources = [c for c in chunks if any(c.source_id in u for u in unresolved)]

    account_id = state.get("account_id")
    names, tool_events = plan_tools(list(cls.tools_needed), account_id, state.get("customer_segment", ""))
    failures = list(state.get("failures", []))
    results = []
    for name in names:
        r = tools.run_tool(name, account_id=account_id, as_of=state.get("as_of_date"))
        results.append(r)
        if not r.ok and not tools.is_not_found(r):
            failures.append(f"tool_failed:{name}")
    return {"chunks": chunks, "upcoming": upcoming, "conflicts": conflicts, "tool_results": results,
            "unresolved_conflicts": unresolved, "conflict_sources": conflict_sources,
            "failures": failures,
            "guardrail_events": list(state.get("guardrail_events", [])) + events + upcoming_events + tool_events}
