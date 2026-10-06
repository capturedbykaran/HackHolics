"""FastAPI router: POST /ingest, GET /sources, GET /sources/{id}, DELETE /sources/{id}. Mounted in main.py.

Owner: C

curl examples:
  curl -F file=@KB-NEW-001.md -F 'metadata={"source_id":"KB-NEW-001","doc_type":"article","title":"New",
       "authority_level":1,"product_versions":"4.x","last_updated":"2026-10-06"}' localhost:8000/ingest
  curl -F file=@KB-NEW-001.md "localhost:8000/ingest?dry_run=true"   # preview chunks, write nothing
  curl -F file=@TKT-JD-1.json localhost:8000/ingest                  # ticket metadata can live in the JSON
"""
import json

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.ingest import TEXT_EXTS, connect, delete_source, ingest_document

router = APIRouter(tags=["knowledge base"])
MAX_BYTES = 2_000_000


@router.post("/ingest")
async def ingest(file: UploadFile = File(...), metadata: str | None = Form(None),
                 dry_run: bool = Query(False, description="validate and chunk only; nothing is stored")):
    name = (file.filename or "").lower()
    if not name.endswith((*TEXT_EXTS, ".json")):
        raise HTTPException(415, "Upload a Markdown/text article (.md, .markdown, .txt) or a JSON ticket (.json)")
    content = await file.read()
    if not content:
        raise HTTPException(400, "File is empty")
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "File larger than 2 MB")
    try:
        meta = json.loads(metadata) if metadata else None
        if meta is not None and not isinstance(meta, dict):
            raise HTTPException(400, "metadata must be a JSON object")
        # embedding is CPU-bound: run it off the event loop so /support stays responsive
        return await run_in_threadpool(ingest_document, content, file.filename, meta, dry_run=dry_run)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"file or metadata is not valid JSON: {e}")
    except ValidationError as e:
        raise HTTPException(422, {"error": "metadata does not match the Source Register fields",
                                  "details": json.loads(e.json())})
    except ValueError as e:
        raise HTTPException(422, str(e))


SOURCES_SQL = """SELECT r.*, s.chunks, s.content_hash, s.flags, s.embedder, s.ingested_at
                 FROM source_register r LEFT JOIN ingest_state s USING(source_id)"""


def _query(sql: str, args: tuple = ()) -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


@router.get("/sources")
def sources(doc_type: str | None = None):
    sql, args = SOURCES_SQL, ()
    if doc_type:
        sql, args = sql + " WHERE r.doc_type=?", (doc_type,)
    rows = _query(sql + " ORDER BY r.doc_type, r.source_id", args)
    return {"count": len(rows), "sources": rows}


@router.get("/sources/{source_id}")
def source(source_id: str):
    rows = _query(SOURCES_SQL + " WHERE r.source_id=?", (source_id,))
    if not rows:
        raise HTTPException(404, f"unknown source_id {source_id}")
    return rows[0]


@router.delete("/sources/{source_id}")
def remove_source(source_id: str):
    if not delete_source(source_id):
        raise HTTPException(404, f"unknown source_id {source_id}")
    return {"source_id": source_id, "status": "deleted"}
