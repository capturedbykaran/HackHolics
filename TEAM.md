# Team

> Owner: A

| Member | Role | Owns |
|---|---|---|
| A | Agent pipeline / LLM, tech lead | `CLAUDE.md`, `TEAM.md`, `app/schemas.py`, `app/llm.py`, `app/graph.py`, `app/segment.py`, `app/guardrails/**`, `GUARDRAILS.md`, `app/nodes/{classify,compose,critic,finalize}.py`, `prompts/{classifier,composer,critic}.txt`, `samples/audit_*`, `samples/handoff_*`, `tests/{test_graph,test_llm,test_memory_segment,test_guardrails}.py`, `tests/redteam_cases.jsonl`, `tests/fake_retrieval.py` |
| B | Tools / rules / safety | `app/nodes/{guard,gather,decide}.py`, `app/{db,tools,precedence,escalation,policy,guard}.py`, `tests/{conftest,test_db,test_tools,test_precedence,test_escalation,test_pii}.py` |
| C | Data / KB / retrieval | `DATA_CARD.md`, `docs/data_pipeline.md`, `app/{world,ingest,ingest_api,store,embeddings,retrieval}.py`, `prompts/kb_gen_*`, `prompts/accounts_gen.txt`, `data/**`, `scripts/**`, `eval/questions.jsonl`, `tests/test_ingest_retrieval.py` |
| D | API / UI / infra / eval | `README.md`, `AI_USAGE.md`, `requirements.txt`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `pytest.ini`, `app/{config,main,audit}.py`, `ui/`, `eval/run_eval.py`, `eval/results/`, `eval/report.md`, `samples/curl_examples.sh`, `docs/`, `tests/test_api.py` |

`CONTRIBUTIONS.md` is shared by everyone.

Files whose docstring starts with `STUB (owner: X)` are temporary placeholders written so the graph
runs end to end; the owner replaces them (contracts in `CLAUDE.md`). Still stubbed after the merge of
6 Oct: `app/audit.py` (in-memory, D) and `app/guard.py` (thin layer over `app/guardrails`, B).
Real implementations now in main: `app/tools.py` (B; tools 4-7 + the guardrail wrapper added by A in
B's style during the merge), `app/retrieval.py` + `app/ingest.py` (C), `app/escalation.py` + `app/policy.py` (node 6).

By team agreement A also edited, for the guardrails/merge changes only: `app/guard.py`,
`app/nodes/{guard,gather,decide}.py`, `app/tools.py`, `app/audit.py` (stub: `guardrail_events` key) and
`app/__init__.py` (log filter). Their owners keep ownership.
