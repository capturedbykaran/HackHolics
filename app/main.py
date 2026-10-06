"""FastAPI app: /support /ingest /health /conversations/{id} /handoffs/{id} /audit/{trace_id} /sources /admin/load

Owner: D
"""
from fastapi import FastAPI

from app.ingest_api import router as ingest_router

app = FastAPI(title="InsightDesk")
app.include_router(ingest_router)        # POST /ingest, GET/DELETE /sources (C)


@app.get("/health")
def health():
    return {"status": "ok"}


# TODO: POST /support, GET /conversations/{id}, GET /handoffs/{id},
#       GET /audit/{trace_id}, POST /admin/load (optional)
