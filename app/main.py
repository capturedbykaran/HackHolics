"""FastAPI app: /support /ingest /health /conversations/{id} /handoffs/{id} /audit/{trace_id} /sources /admin/load

Owner: D
"""

from fastapi import FastAPI

app = FastAPI(title="InsightDesk")


@app.get("/health")
def health():
    return {"status": "ok"}


# TODO: POST /support, POST /ingest, GET /conversations/{id}, GET /handoffs/{id},
#       GET /audit/{trace_id}, GET /sources, POST /admin/load (optional)
