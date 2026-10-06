# Data, ingestion and retrieval

> Owner: C

## Files

| Path | What it is |
|---|---|
| `app/world.py` | World bible: plans, error codes, policies, 38 article specs, 26 ticket specs. Single source of facts |
| `app/ingest.py` | `ingest_document()`: validate → parse → sanitise → chunk → enrich → embed → upsert → register |
| `app/store.py` | ChromaDB collection `kb_chunks` + in-memory BM25 index |
| `app/embeddings.py` | bge-small-en-v1.5 embeddings, ms-marco MiniLM cross-encoder reranker, `EMBEDDER=hash` for tests |
| `app/retrieval.py` | `search()`: dense + BM25 → RRF → version/date filters → rerank → diversity cap |
| `app/ingest_api.py` | `POST /ingest`, `GET /sources`, `GET/DELETE /sources/{id}` (mounted in `app/main.py`) |
| `scripts/gen_kb.py` | Articles + tickets from the world bible via LLM; writes `article_plan.json` and the register |
| `scripts/gen_accounts.py` | accounts, usage, invoices, plan_limits, platform_status, policy_registry CSVs → `data/seed/` |
| `scripts/gen_llm.py` | Generator LLM client (Groq → Gemini → Ollama, OpenAI-compatible, `GEN_MOCK`) |
| `scripts/validate_kb.py` | Brief minimums + fact checks |
| `scripts/validate_accounts.py` | Schema + logical constraints (also used on judges' data) |
| `scripts/load_accounts.py` | Judges' loader: CSV → SQLite, validated, all-or-nothing |
| `scripts/build_register.py` | Front matter + ticket JSON → `data/source_register.csv` |
| `scripts/seed.py` | One command: init DB, load `data/seed/`, ingest the KB |
| `scripts/retrieval_eval.py` | hit@k, MRR, latency for dense vs hybrid vs hybrid+rerank |

## Commands

```bash
# 1. knowledge base (LLM writes prose from the fact specs; failing articles are regenerated)
python scripts/gen_kb.py              # GEN_MOCK=true for instant offline content
python scripts/validate_kb.py

# 2. account database
python scripts/gen_accounts.py --n 28
python scripts/validate_accounts.py --dir data/seed

# 3. build both stores (first run downloads bge-small ~130 MB and the reranker ~90 MB)
python scripts/seed.py                # --reset to rebuild from scratch

# 4. retrieval quality, and tests (offline)
python scripts/retrieval_eval.py
pytest -q tests/test_ingest_retrieval.py

# judges' data
python scripts/load_accounts.py --dir test_accounts/
curl -F file=@KB-NEW.md -F 'metadata={"source_id":"KB-NEW","doc_type":"article","title":"New",
     "authority_level":1,"product_versions":"4.x","last_updated":"2026-10-06"}' localhost:8000/ingest
curl -F file=@KB-NEW.md "localhost:8000/ingest?dry_run=true"     # preview chunks, store nothing
```

## How the content is made

**Spec first, prose second.** `app/world.py` holds every fact once. The generator asks the LLM to
write each article from its fact list (policies use the stricter `kb_gen_policy.txt` prompt), then
checks the output contains every required fact and section. Failures are fed back to the model
(max 2 retries); if it still fails, the article is rendered from the spec deterministically and
logged in `data/generation_log.jsonl`. Articles, `plan_limits`, `policy_registry` and tool
behaviour can never contradict each other.

**Designed conflicts** (listed in `data/article_plan.json`):
- Version-specific articles: run export (3.x vs 4.2+), API auth (legacy key vs scoped token), webhook signing (SHA1 vs SHA256).
- 4 outdated tickets that contradict current docs (e.g. TKT-2025-0311 "add a Delay step" vs KB-TS-002).
- RN-DEP-001 deprecates legacy API keys on 2026-12-01, after the judging date, so it is returned as *upcoming*.
- 3 angry tickets that needed a human.

**Accounts.** 12 hand-built edge cases with fixed IDs, plus LLM-generated companies validated with
Pydantic. Usage, invoices and dates are computed in code from a fixed seed.

| ID | Edge case |
|---|---|
| A1002 / A1003 | API peak exactly at the Pro limit (300) / one over (301) |
| A1004 | failed payment, past_due |
| A1005 | duplicate charge (two identical invoices on 2026-10-01) |
| A1006 / A1007 | charge 14 days ago (last refund day) / 15 days ago (one day late) |
| A1008 | suspended |
| A1009 | old product version 3.8 |
| A1010 | Free plan, runs exactly at quota (CF-460) |

## `POST /ingest` pipeline

1. **Validate** metadata (Annex B) with Pydantic, including optional `policy_values` rows: 422 with field errors.
2. **Parse** Markdown/text front matter (explicit metadata wins), or ticket JSON (one ticket or a list).
3. **Sanitise**: Unicode NFKC, strip zero-width characters and hidden HTML comments (an injection vector);
   redact email, phone, Luhn-valid card numbers, API keys and bearer tokens; flag prompt-injection
   phrases per chunk (stored as data, flagged for the critic, never obeyed).
4. **Chunk** articles by `##` section; long sections split on paragraph boundaries (~220 words, 40-word
   overlap); tables and code blocks never split. A ticket is one chunk.
5. **Contextual header** per chunk (`[article KB-TS-002] Fixing CF-503 > Fix (versions 4.1+)`) is embedded
   with the text, so short chunks keep their meaning.
6. **Embed** with bge-small-en-v1.5 (normalised; query-side instruction prefix per the model card).
   Embeddings are computed **before** any write, so a model failure cannot leave a document half-replaced.
7. **Idempotent, transactional upsert**: a content hash skips unchanged docs; otherwise the SQLite
   writes (register, `ingest_state`, policy rows) are held in a transaction while all old chunks of the
   `source_id` are swapped in Chroma; any error rolls SQLite back. A write lock serialises ingests.
8. **Register** in `source_register` (Annex B columns) plus `ingest_state` (hash, chunk count, flags, embedder).
9. **BM25 refresh**: the keyword index is rebuilt on the next query, so new content is searchable immediately.

The response reports `status` (indexed / replaced / unchanged / dry_run / batch), chunk ids, redacted
PII types, flags, warnings (future `effective_from`, past `deprecated_on`, unknown `supersedes`) and timing.
Embedding runs in a thread pool so `/support` stays responsive during an ingest.

## Retrieval

Dense top-30 (pre-filtered by major version in Chroma) + BM25 top-30 → reciprocal rank fusion →
exact version-range check (integer encoding, so 4.10 > 4.9), `effective_from` / `deprecated_on`
against `as_of_date` (future docs returned separately as `upcoming`, deprecated ones listed in
`excluded`) → cross-encoder rerank of the head → max 2 chunks per source → top-k with citation metadata
and per-stage timings. BM25 matters because error codes and headers (`CF-503`, `X-CF-Key`) are exact strings.

Source precedence (which source wins) is deliberately **not** in retrieval; it belongs to
`app/precedence.py` (B), which receives both the outdated ticket and the current article.
