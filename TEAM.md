# Team

> Owner: A

| Member | Role | Owns |
|---|---|---|
| A | Agent pipeline / LLM, tech lead | `CLAUDE.md`, `TEAM.md`, `app/schemas.py`, `app/llm.py`, `app/graph.py`, `app/segment.py`, `app/guardrails/**`, `GUARDRAILS.md`, `app/nodes/{classify,compose,critic,finalize}.py`, `prompts/{classifier,composer,critic}.txt`, `samples/audit_*`, `samples/handoff_*`, `tests/{test_graph,test_llm,test_memory_segment,test_guardrails}.py`, `tests/redteam_cases.jsonl` |
| B | Tools / rules / safety | `app/nodes/{guard,gather,decide}.py`, `app/{db,tools,precedence,escalation,guard}.py`, `tests/{conftest,test_db,test_tools,test_precedence,test_escalation,test_pii}.py` |
| C | Data / KB / retrieval | `DATA_CARD.md`, `app/{ingest,retrieval}.py`, `prompts/kb_gen_*`, `prompts/accounts_gen.txt`, `data/**`, `scripts/**`, `eval/questions.jsonl`, `tests/test_ingest_retrieval.py` |
| D | API / UI / infra / eval | `README.md`, `AI_USAGE.md`, `requirements.txt`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `pytest.ini`, `app/{config,main,audit}.py`, `ui/`, `eval/run_eval.py`, `eval/results/`, `eval/report.md`, `samples/curl_examples.sh`, `docs/`, `tests/test_api.py` |

`CONTRIBUTIONS.md` is shared by everyone.

Files whose docstring starts with `STUB (owner: X)` are temporary placeholders written so the graph
runs end to end; the owner replaces them (contracts in `CLAUDE.md`). Currently stubbed:
`app/{guard,tools,escalation,retrieval,audit}.py`, `app/nodes/{guard,gather,decide}.py`.

By team agreement A also edits, for the guardrails change only: `app/guard.py` (now a thin layer over `app/guardrails`), `app/nodes/{guard,gather}.py`, `app/tools.py` (allowlist), `app/ingest.py` (`flag_suspicious` hook), `app/audit.py` (stub: `guardrail_events` key) and `app/__init__.py` (log filter). Their owners keep ownership.
