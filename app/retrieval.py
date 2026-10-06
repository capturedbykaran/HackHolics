"""STUB (owner: C). search() with version/date metadata filters.

Tiny in-memory keyword corpus so the graph runs end to end without Chroma; C replaces it.
Contract: search(query, k=5, version=None, as_of=None) -> list[Chunk], best first, [] if nothing relevant.
"""
import re

from app.schemas import Chunk

_CORPUS = [
    Chunk(source_id="KB-ADV-007", section="Exporting run history", doc_type="article", authority_level=3,
          product_versions="3.x;4.x", last_updated="2026-03-01",
          text="To export workflow run history: open Workflows, choose the workflow, open the Runs tab, "
               "then click Export and pick CSV or JSON. Filter by date range before exporting."),
    Chunk(source_id="KB-GS-001", section="First workflow", doc_type="article", authority_level=3,
          product_versions="4.x", last_updated="2026-02-10",
          text="Getting started: create your first workflow from a template in Workflows > New, then "
               "connect an app and run a test before turning the schedule on."),
    Chunk(source_id="KB-TRB-012", section="CF-503 connector errors", doc_type="article", authority_level=3,
          product_versions="4.x", last_updated="2026-04-12",
          text="Error CF-503 means a connector could not reach the remote service. Check the platform "
               "status page, reconnect the connector and retry the failed run."),
    Chunk(source_id="KB-PLN-002", section="Plans and pricing", doc_type="article", authority_level=3,
          product_versions="ALL", last_updated="2026-01-15",
          text="CloudFlow plans and pricing: Free 0, Pro 49, Business 199, Enterprise 999 per month. "
               "Each plan has its own API rate limit, monthly workflow runs and seats."),
]

_STOP = {"how", "do", "i", "my", "the", "a", "an", "to", "is", "on", "in", "of", "and", "what", "about",
         "can", "with", "for", "it", "does", "cloudflow", "im", "i'm", "me", "you", "this", "that", "still"}
MIN_OVERLAP = 2


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9-]+", text.lower()) if t not in _STOP and len(t) > 1}


def search(query: str, k: int = 5, version=None, as_of=None) -> list[Chunk]:
    q = _tokens(query)
    scored = []
    for c in _CORPUS:
        overlap = len(q & _tokens(c.text + " " + c.section))
        if overlap >= MIN_OVERLAP:
            scored.append(c.model_copy(update={"score": float(overlap)}))
    return sorted(scored, key=lambda c: -c.score)[:k]
