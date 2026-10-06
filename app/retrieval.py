"""Hybrid retrieval: dense (bge-small in Chroma) + keyword (BM25) -> RRF fusion
-> applicability filters (version, effective date, deprecation) -> cross-encoder rerank
-> per-source diversity cap -> top-k with citation metadata.

Owner: C

Why hybrid: error codes, headers and menu paths ("CF-503", "X-CF-Key", "Settings > Billing")
are exact strings that dense embeddings blur; BM25 catches them, dense catches paraphrases.
Precedence (which source wins a conflict) is NOT done here; that is app/precedence.py (B), which
needs to see both the outdated ticket and the current article.
"""
import re
import time
from dataclasses import dataclass, field
from datetime import date

from app import store
from app.embeddings import embed_query, rerank
from app.ingest import version_covered

RRF_K = 60
CANDIDATES = 30
MAX_PER_SOURCE = 2       # keeps one long article from filling every slot


@dataclass
class Chunk:
    chunk_id: str
    text: str
    meta: dict
    score: float = 0.0
    signals: dict = field(default_factory=dict)   # dense_rank, bm25_rank, rerank score: for the audit record

    @property
    def citation(self) -> dict:
        m = self.meta
        return {"source_id": m["source_id"], "doc_type": m["doc_type"], "title": m["title"],
                "section": m["section"], "product_versions": m["product_versions"],
                "last_updated": m["last_updated"]}

    def to_schema(self):
        """-> app.schemas.Chunk (A's shared contract), for the Gather node."""
        from app.schemas import Chunk as SchemaChunk
        m = self.meta
        return SchemaChunk(text=self.text, source_id=m["source_id"], section=m["section"], doc_type=m["doc_type"],
                           authority_level=m["authority_level"], product_versions=m["product_versions"],
                           last_updated=m["last_updated"], effective_from=m["effective_from"] or None,
                           deprecated_on=m["deprecated_on"] or None,
                           supersedes=[s for s in re.split(r"[;,\s]+", m["supersedes"]) if s],
                           score=float(self.score))


def _where(version: str | None, doc_types: list[str] | None) -> dict | None:
    conds = []
    if version and version[0].isdigit():
        major = int(version.split(".")[0])
        conds.append({"$or": [{f"v{major}": True}, {"all_versions": True}]})
    if doc_types:
        conds.append({"doc_type": {"$in": doc_types}})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


def _diverse(chunks: list[Chunk], k: int) -> list[Chunk]:
    out, per, spill = [], {}, []
    for c in chunks:
        sid = c.meta["source_id"]
        if per.get(sid, 0) < MAX_PER_SOURCE:
            per[sid] = per.get(sid, 0) + 1
            out.append(c)
        else:
            spill.append(c)
        if len(out) == k:
            return out
    return (out + spill)[:k]


def search(query: str, version: str | None = None, as_of_date: str | None = None, k: int = 8,
           doc_types: list[str] | None = None, use_rerank: bool = True, use_bm25: bool = True) -> dict:
    """Return {"chunks": [Chunk], "upcoming": [Chunk], "excluded": [(source_id, reason)], "timings_ms": {...}}."""
    t0 = time.perf_counter()
    as_of = int((as_of_date or date.today().isoformat()).replace("-", ""))
    col = store.collection()
    n = col.count()
    if n == 0 or not query.strip():
        return {"chunks": [], "upcoming": [], "excluded": [], "timings_ms": {}}

    # 1. dense candidates (Chroma pre-filters by major version / doc type)
    dense = col.query(query_embeddings=[embed_query(query)], n_results=min(CANDIDATES, n),
                      where=_where(version, doc_types), include=["documents", "metadatas"])
    pool: dict[str, Chunk] = {}
    for rank, (cid, doc, meta) in enumerate(zip(dense["ids"][0], dense["documents"][0], dense["metadatas"][0])):
        pool[cid] = Chunk(cid, doc, meta, signals={"dense_rank": rank})
    t_dense = time.perf_counter()

    # 2. keyword candidates (BM25 over all chunks)
    idx = store.bm25() if use_bm25 else {"index": None}
    if idx["index"] is not None:
        scores = idx["index"].get_scores(store.tokenize(query))
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:CANDIDATES]
        for rank, i in enumerate(t for t in top if scores[t] > 0):
            cid = idx["ids"][i]
            pool.setdefault(cid, Chunk(cid, idx["docs"][i], idx["metas"][i]))
            pool[cid].signals["bm25_rank"] = rank
    t_bm25 = time.perf_counter()

    # 3. reciprocal rank fusion
    for c in pool.values():
        c.score = sum(1.0 / (RRF_K + c.signals[s]) for s in ("dense_rank", "bm25_rank") if s in c.signals)
        c.signals["rrf"] = round(c.score, 5)

    # 4. applicability: doc type, version range, deprecation, effective date
    kept, upcoming, excluded, seen = [], [], [], set()
    for c in sorted(pool.values(), key=lambda c: -c.score):
        m = c.meta
        reason = None
        if doc_types and m["doc_type"] not in doc_types:
            continue
        if not version_covered(m["version_ranges"], version):
            reason = "version_not_covered"
        elif m["deprecated_on_int"] <= as_of:
            reason = f"deprecated_on {m['deprecated_on']}"
        elif m["effective_from_int"] > as_of:
            upcoming.append(c)                    # mention as an upcoming change, never as current
            continue
        if reason:
            if (m["source_id"], reason) not in seen:
                seen.add((m["source_id"], reason))
                excluded.append((m["source_id"], reason))
            continue
        kept.append(c)

    # 5. cross-encoder rerank of the fused head
    head = kept[: max(k * 3, 12)]
    if use_rerank:
        scores = rerank(query, [f"{c.meta['title']} > {c.meta['section']}\n{c.text}" for c in head])
        if scores:
            for c, s in zip(head, scores):
                c.signals["rerank"] = round(s, 3)
                c.score = s
            head.sort(key=lambda c: -c.score)
    t_end = time.perf_counter()

    # 6. diversity cap, then top-k
    ms = lambda a, b: round((b - a) * 1000, 1)  # noqa: E731
    return {"chunks": _diverse(head, k), "upcoming": _diverse(upcoming, 3), "excluded": excluded,
            "timings_ms": {"dense": ms(t0, t_dense), "bm25": ms(t_dense, t_bm25), "rerank": ms(t_bm25, t_end),
                           "total": ms(t0, t_end)}}
