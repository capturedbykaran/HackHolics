# Synthetic Data Card (Annex E)

> Owner: C. Fields in [brackets] are filled after the real LLM generation run (the committed data was generated with `GEN_MOCK=true`).

| Field | Content |
|---|---|
| Purpose | CloudFlow help-center KB, resolved tickets and customer accounts to exercise grounded answers, version matching, source precedence, deterministic tools and escalation |
| Source of facts | `app/world.py` (plans, error codes, policies, 41 document specs, 27 ticket specs). Articles, `plan_limits`, `policy_registry` and tool behaviour are all generated from it, so they cannot contradict each other |
| Generator | [provider:model from data/generation_log.jsonl], temperature 0.4 articles / 0.6 tickets / 0.8 accounts, [N] calls. Current committed data: `template:mock` |
| Prompts | `prompts/kb_gen_article.txt`, `prompts/kb_gen_policy.txt`, `prompts/kb_gen_ticket.txt`, `prompts/accounts_gen.txt` (verbatim) |
| Schema enforcement | Articles: fact + section checks with feedback retries (max 2), deterministic fallback, logged. Tickets/accounts: JSON mode + Pydantic validation, invalid rows rejected and logged |
| Row counts | 41 KB documents (32 articles, 5 policies, 3 release notes, 1 community post), 27 tickets, 40 accounts (Free 8 / Pro 17 / Business 12 / Enterprise 3), 80 usage rows, 95 invoices, 4 plans, 5 platform components, 9 policy rules |
| Versions | Accounts on 4.3 (24), 4.2 (9), 4.1 (5), 3.8 (2); version-specific article pairs for run export, API auth, webhook signing |
| Edge cases | A1002/A1003 API at/over Pro limit (300/301), A1004 failed payment, A1005 duplicate charge, A1006/A1007 refund last day/day after, A1008 suspended, A1009 v3.8, A1010 runs at quota (CF-460); 4 outdated tickets; future deprecation RN-DEP-001 (2026-12-01); superseded refund policy KB-POL-001-2024 (deprecated 2025-01-01); low-authority community post COM-001; prompt injection inside ticket TKT-2026-0220 |
| Validation results | `data/validation_report.txt`: all 9 KB checks PASS, 0 account violations |
| What the LLM got wrong | [from generation_log: missing facts, wrong menu paths, invented features, Free accounts marked past_due, duplicate company names] |
| Known limitations | Single currency per account; usage is monthly aggregates only; articles shorter than real help centers; no images |

See `docs/data_pipeline.md` for how the content is made and how ingestion and retrieval work.
