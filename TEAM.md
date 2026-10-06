# Team

> Owner: A

| Member | Role | Owns |
|---|---|---|
| A | Orchestration / LLM | `CLAUDE.md`, `TEAM.md`, `app/schemas.py`, `app/llm.py`, `app/graph.py`, `app/nodes/{classify,compose,critic,finalize}.py`, `prompts/{classifier,composer,critic}.txt`, `samples/audit_*`, `samples/handoff_*`, `tests/test_graph.py` |
| B | Tools / rules / safety | `app/nodes/{guard,gather,decide}.py`, `app/{db,tools,precedence,escalation,guard}.py`, `tests/{conftest,test_tools,test_precedence,test_escalation,test_pii}.py` |
| C | Data / KB / retrieval | `DATA_CARD.md`, `docs/data_pipeline.md`, `app/{world,ingest,ingest_api,store,embeddings,retrieval}.py`, `prompts/kb_gen_*`, `prompts/accounts_gen.txt`, `data/**`, `scripts/**`, `eval/questions.jsonl`, `tests/test_ingest_retrieval.py` |
| D | API / UI / infra / eval | `README.md`, `AI_USAGE.md`, `requirements.txt`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `pytest.ini`, `app/{config,main,audit}.py`, `ui/`, `eval/run_eval.py`, `eval/results/`, `eval/report.md`, `samples/curl_examples.sh`, `docs/`, `tests/test_api.py` |

`CONTRIBUTIONS.md` is shared by everyone.
