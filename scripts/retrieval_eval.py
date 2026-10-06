"""Retrieval quality for three configurations: dense only, hybrid (dense+BM25), hybrid + rerank.
Gives the "compare at least two configurations" numbers for the eval report.

Owner: C

  python scripts/retrieval_eval.py          # after seed.py; writes eval/results/retrieval_<embedder>.json

Metrics: hit@k (expected source in top-k), MRR (1 / rank of the first expected chunk), p50/p95 latency.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import retrieval                     # noqa: E402
from app.embeddings import embedder_name      # noqa: E402

AS_OF = "2026-10-06"
# (query, customer version, expected source_id)
CASES = [
    ("How do I export my workflow run history?", "4.3", "KB-ADV-001"),
    ("export run history on 3.8", "3.8", "KB-ADV-001-3X"),
    ("My Salesforce step fails with error CF-503", "4.3", "KB-TS-002"),
    ("Why are my API calls failing with 429 errors?", "4.3", "KB-API-003"),
    ("I want a refund for this month", "4.3", "KB-POL-001"),
    ("I was charged twice", "4.3", "KB-BIL-003"),
    ("forgot my password", "4.3", "KB-TS-008"),
    ("which header do I send the API token in", "4.3", "KB-API-001"),
    ("api key header on version 3", "3.8", "KB-API-002"),
    ("webhook signature does not match", "4.3", "KB-TS-006"),
    ("how many seats on the Pro plan", "4.3", "KB-GS-004"),
    ("runs stopped CF-460", "4.3", "KB-TS-007"),
    ("step timeout CF-504 in a loop", "4.3", "KB-TS-004"),
    ("how fast do you answer billing issues", "4.3", "KB-POL-002"),
    ("post to a private slack channel", "4.3", "KB-API-006"),
    ("where do I keep credentials for steps", "4.3", "KB-ADV-003"),
    ("card declined account past due", "4.3", "KB-BIL-002"),
    ("who changed my workflow audit", "4.3", "KB-ADV-004"),
    ("verify webhook signature on 3.8", "3.8", "KB-API-004-3X"),
    ("CF-403 when listing runs", "4.3", "KB-TS-003"),
]
CONFIGS = {
    "dense only": dict(use_bm25=False, use_rerank=False),
    "hybrid (dense+BM25)": dict(use_bm25=True, use_rerank=False),
    "hybrid + rerank": dict(use_bm25=True, use_rerank=True),
}


def run(name: str, k: int, **kw) -> dict:
    hits, rr, ms = 0, 0.0, []
    misses = []
    for q, v, exp in CASES:
        t = time.perf_counter()
        r = retrieval.search(q, version=v, as_of_date=AS_OF, k=k, **kw)
        ms.append((time.perf_counter() - t) * 1000)
        ranked = [c.meta["source_id"] for c in r["chunks"]]
        if exp in ranked:
            hits += 1
            rr += 1 / (ranked.index(exp) + 1)
        else:
            misses.append({"query": q, "expected": exp, "got": ranked[:3]})
    ms.sort()
    out = {"config": name, "k": k, "hit_rate": round(hits / len(CASES), 3), "mrr": round(rr / len(CASES), 3),
           "p50_ms": round(ms[len(ms) // 2]), "p95_ms": round(ms[max(0, int(len(ms) * .95) - 1)]), "misses": misses}
    print(f"{name:22s} hit@{k} = {hits}/{len(CASES)} ({out['hit_rate']:.0%})  MRR {out['mrr']:.2f}"
          f"   p50 {out['p50_ms']} ms   p95 {out['p95_ms']} ms")
    return out


if __name__ == "__main__":
    print(f"embedder: {embedder_name()}")
    retrieval.search("warm up", version="4.3", as_of_date=AS_OF)       # load models before timing
    results = [run(name, k, **kw) for k in (3, 5) for name, kw in CONFIGS.items()]
    out = ROOT / "eval/results" / f"retrieval_{embedder_name().split('/')[-1]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"embedder": embedder_name(), "cases": len(CASES), "results": results}, indent=2),
                   encoding="utf-8")
    print(f"-> {out.relative_to(ROOT)}")
