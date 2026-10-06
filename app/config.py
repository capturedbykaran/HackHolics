"""Environment settings: paths, model names, MOCK_LLM.

Owner: D
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:  # .env is optional; real environment variables always win
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

DATA_DIR = ROOT / "data"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", DATA_DIR / "chroma"))
AS_OF_DATE = os.getenv("AS_OF_DATE", "2026-10-06")

MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() == "true"

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
