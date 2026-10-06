"""Embedding + reranking models (sentence-transformers, loaded once).

Owner: C

EMBED_MODEL   default BAAI/bge-small-en-v1.5 (384-d). all-MiniLM-L6-v2 also supported.
RERANK_MODEL  default cross-encoder/ms-marco-MiniLM-L-6-v2 ; set RERANK=false to disable.
              BAAI/bge-reranker-base is a stronger (slower) drop-in if CPU time allows.
EMBEDDER=hash gives a dependency-free hashing embedder for unit tests / CI only.
"""
import hashlib
import logging
import os
import re
from functools import lru_cache

import numpy as np

from app import config

EMBED_MODEL = config.EMBED_MODEL
RERANK_MODEL = config.RERANK_MODEL
# bge models are trained with an instruction prefix on the QUERY side only
QUERY_PREFIX = "Represent this sentence for searching relevant passages: " if "bge" in EMBED_MODEL else ""
log = logging.getLogger(__name__)


class _HashEmbedder:
    dim = 384

    def encode(self, texts, **_):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", t.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


@lru_cache(maxsize=1)
def _model():
    if os.getenv("EMBEDDER") == "hash":
        return _HashEmbedder()
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL, device="cpu")


def embedder_name() -> str:
    return "hash" if os.getenv("EMBEDDER") == "hash" else EMBED_MODEL


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False).tolist()


@lru_cache(maxsize=512)
def _embed_query_cached(text: str) -> tuple[float, ...]:
    return tuple(_model().encode([QUERY_PREFIX + text], normalize_embeddings=True, show_progress_bar=False)[0].tolist())


def embed_query(text: str) -> list[float]:
    return list(_embed_query_cached(text))


@lru_cache(maxsize=1)
def _reranker():
    if os.getenv("RERANK", "true").lower() != "true" or os.getenv("EMBEDDER") == "hash":
        return None
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder(RERANK_MODEL, device="cpu")
    except Exception as e:  # offline / download failure: degrade to fused ranking, never crash a request
        log.warning("reranker unavailable (%s); continuing without rerank", e)
        return None


def rerank(query: str, texts: list[str]) -> list[float] | None:
    m = _reranker()
    if m is None or not texts:
        return None
    return [float(s) for s in m.predict([(query, t) for t in texts], show_progress_bar=False)]
