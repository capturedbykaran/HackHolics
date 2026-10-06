"""ChromaDB collection `kb_chunks` + an in-memory BM25 keyword index rebuilt lazily after each ingest.

Owner: C
"""
import os
import re
import threading
from functools import lru_cache

import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi

from app import config

# read at import (not from config) so tests can point CHROMA_DIR at a temp dir and reload this module
CHROMA_DIR = os.getenv("CHROMA_DIR", str(config.DATA_DIR / "chroma"))
COLLECTION = "kb_chunks"           # Chroma names need >= 3 characters

write_lock = threading.Lock()          # one ingest at a time: Chroma + SQLite stay consistent
_bm25_lock = threading.Lock()
_bm25 = {"dirty": True, "index": None, "ids": [], "docs": [], "metas": []}

TOKEN = re.compile(r"[a-z0-9]+(?:[-_./:][a-z0-9]+)*")   # keeps "cf-503", "x-cf-key", "/v2/runs" whole


def tokenize(text: str) -> list[str]:
    toks = TOKEN.findall(text.lower())
    # also index the parts of compound tokens so "503" matches "cf-503"
    return toks + [p for t in toks if re.search(r"[-_./:]", t) for p in re.split(r"[-_./:]", t) if p]


@lru_cache(maxsize=1)
def collection():
    client = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings(anonymized_telemetry=False))
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None)


def mark_dirty():
    _bm25["dirty"] = True


def bm25():
    with _bm25_lock:
        if _bm25["dirty"]:
            got = collection().get(include=["documents", "metadatas"])
            _bm25["ids"], _bm25["docs"], _bm25["metas"] = got["ids"], got["documents"], got["metadatas"]
            corpus = [tokenize(f"{m['title']} {m['section']} {d}") for d, m in zip(got["documents"], got["metadatas"])]
            _bm25["index"] = BM25Okapi(corpus) if corpus else None
            _bm25["dirty"] = False
        return _bm25
