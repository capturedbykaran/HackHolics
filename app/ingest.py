"""ingest_document(): md/json -> chunks -> Chroma + register.

Owner: C
"""
from app.guardrails import scan_for_ingest


def flag_suspicious(text: str, metadata: dict) -> dict:
    """Guardrail hook (added by A): call for every chunk at ingest time.

    Text that looks like instructions for the assistant is still stored, but its metadata gets
    suspicious=True so it can be reviewed; it is also dropped at retrieval time (processing guard).
    """
    return {**metadata, "suspicious": True} if scan_for_ingest(text) else dict(metadata)


def ingest_document(path):
    raise NotImplementedError
