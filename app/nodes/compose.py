"""Node 4: compose (LLM call 2). Owner: A.

Also used for the single revision: if a critic result already exists, this is the second pass.
"""
import json
from typing import Any

from app import llm
from app.guard import redact
from app.schemas import Chunk, ComposerCitation, ComposerOut, ToolResult

MAX_CHUNK_CHARS = 1500


def _fmt_chunks(chunks: list[Chunk]) -> str:
    if not chunks:
        return "(none)"
    parts = []
    for i, c in enumerate(chunks, 1):
        text, _ = redact(c.text[:MAX_CHUNK_CHARS])
        parts.append(f"[{i}] source_id={c.source_id} | section={c.section} | type={c.doc_type} | "
                     f"versions={c.product_versions} | updated={c.last_updated}\n{text}")
    return "\n\n".join(parts)


def _fmt_tools(results: list[ToolResult]) -> str:
    if not results:
        return "(none)"
    text, _ = redact(json.dumps([r.model_dump() for r in results], default=str))  # e.g. owner_email
    return text


def _fmt_upcoming(upcoming: list[Chunk]) -> str:
    if not upcoming:
        return "(none)"
    return "\n".join(f"- {c.source_id} ({c.section}) takes effect {c.effective_from or c.deprecated_on}: "
                     f"{redact(c.text[:300])[0]}" for c in upcoming)


def evidence_tools(state: dict) -> list[ToolResult]:
    """Tool results that count as evidence: only tools the classifier asked for.
    (gather always calls lookup_account for context; that alone must not make an uncited draft 'grounded'.)"""
    cls = state.get("classifier")
    needed = set(cls.tools_needed) if cls else set()
    return [t for t in state.get("tool_results", []) if t.ok and t.tool in needed]


def compose_node(state: dict) -> dict:
    chunks: list[Chunk] = state.get("chunks", [])
    tools: list[ToolResult] = state.get("tool_results", [])
    prev_critic = state.get("critic")
    revisions = state.get("revisions", 0) + (1 if prev_critic else 0)

    feedback = ""
    if prev_critic and prev_critic.issues:
        feedback = ("\nREVISION: a reviewer rejected your previous draft. Fix these issues and use "
                    "only the sources: " + "; ".join(prev_critic.issues) + "\n")

    system = llm.render(llm.load_prompt("composer.txt"),
                        version=state.get("version") or "unknown", revision_feedback=feedback)
    user = (f"SOURCES:\n{_fmt_chunks(chunks)}\n\nTOOL RESULTS:\n{_fmt_tools(tools)}\n\n"
            f"UPCOMING CHANGES:\n{_fmt_upcoming(state.get('upcoming', []))}\n\n"
            f"<customer_message>\n{state['redacted_message']}\n</customer_message>")

    failures = list(state.get("failures", []))
    try:
        draft: ComposerOut = llm.json_call(system, user, ComposerOut, state, node="compose",
                                           temperature=0.2)
    except llm.LLMError:
        draft = ComposerOut(answer="", can_answer=False, missing_info=["llm_unavailable"])
        failures.append("compose_llm_failed")

    draft = _validate_citations(draft, chunks, evidence_tools(state))
    return {"draft": draft, "revisions": revisions, "failures": failures}


def _validate_citations(draft: ComposerOut, chunks: list[Chunk], evidence: list[ToolResult]) -> ComposerOut:
    """Drop citations the model invented. A cited source must exist in what was retrieved."""
    sections: dict[str, set[str]] = {}
    first_section: dict[str, str] = {}
    for c in chunks:
        sections.setdefault(c.source_id, set()).add(c.section)
        first_section.setdefault(c.source_id, c.section)

    kept: list[ComposerCitation] = []
    seen: set[tuple[str, str]] = set()
    for cit in draft.citations:
        if cit.source_id not in sections:
            continue  # invented source
        section = cit.section if cit.section in sections[cit.source_id] else first_section[cit.source_id]
        if (cit.source_id, section) not in seen:
            seen.add((cit.source_id, section))
            kept.append(ComposerCitation(source_id=cit.source_id, section=section))

    updates: dict[str, Any] = {"citations": kept}
    if draft.can_answer and not kept and not evidence:
        updates.update(can_answer=False, missing_info=draft.missing_info + ["no valid citation"])
    return draft.model_copy(update=updates)