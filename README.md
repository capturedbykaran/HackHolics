<<<<<<< HEAD
# HackHolics
HCL hackathon
first commit
=======
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

## API samples

See `samples/curl_examples.sh`.

## Assumptions

_TODO_

## Limitations

_TODO_
>>>>>>> b89b6bece3fbe5b02530189ce9b62c0ae8a78be7
