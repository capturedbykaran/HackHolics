"""Graph node: retrieval + precedence + tool calls. Owner: B (guardrail wiring by A).

Contract used by A's code:
  * search query = classifier.standalone_question or redacted_message (conversation memory)
  * retrieved chunks go through guardrails.sanitize_chunks (drop injected chunks, redact PII)
  * tools: guardrails.plan_tools (allowlist; prospects run no account tools); account_id comes ONLY
    from state, never from the classifier output or the message text
  * a tool that raises -> failures += ["tool_failed:<name>"]
  * conflicts: precedence.resolve(chunks) -> list[str] (when B provides it); an entry starting with
    "unresolved:" is Annex A.2 step 5 -> state["unresolved_conflicts"], and the chunks it names go to
    state["conflict_sources"] so the handoff can carry BOTH sources
"""
from app import precedence, retrieval, tools
from app.guardrails import plan_tools, sanitize_chunks


UNRESOLVED_PREFIX = "unresolved:"


def gather_node(state: dict) -> dict:
    cls = state["classifier"]
    query = cls.standalone_question or state["redacted_message"]
    chunks = retrieval.search(query, k=5, version=state.get("version"), as_of=state.get("as_of_date"))
    chunks, events = sanitize_chunks(chunks)  # layer 2: retrieved text is untrusted

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
        if not r.ok and r.error not in ("not_found",):
            failures.append(f"tool_failed:{name}")
    return {"chunks": chunks, "upcoming": [], "conflicts": conflicts, "tool_results": results,
            "unresolved_conflicts": unresolved, "conflict_sources": conflict_sources,
            "failures": failures,
            "guardrail_events": list(state.get("guardrail_events", [])) + events + tool_events}
