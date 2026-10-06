# InsightDesk

HackHolics team submission for the HCL hackathon.

> Owner: D

AI support agent for a SaaS analytics product: LangGraph pipeline (guard → classify → gather →
compose → critic → decide → finalize) over a FastAPI backend, Chroma KB, and SQLite account data.

## Architecture

![architecture](docs/architecture.png)

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
python scripts/seed.py          # builds data/insightdesk.db and data/chroma/ (both gitignored)
uvicorn app.main:app --reload
streamlit run ui/streamlit_app.py
```

Or with Docker (Ollama runs on the host, reached via `host.docker.internal`):

```bash
docker compose up --build
```

## Data and knowledge base

38 KB documents, 26 tickets and 40 synthetic accounts live in `data/` and are generated from
`app/world.py`. Judges' accounts: `python scripts/load_accounts.py --dir test_accounts/`.
New documents: `POST /ingest` (searchable immediately). Details in
[docs/data_pipeline.md](docs/data_pipeline.md) and [DATA_CARD.md](DATA_CARD.md).

## API samples

See `samples/curl_examples.sh`.

## Assumptions

_TODO_

## Limitations

_TODO_
