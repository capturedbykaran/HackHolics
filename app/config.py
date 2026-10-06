"""Environment settings: paths, model names, MOCK_LLM.

Owner: D
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "insightdesk.db"
CHROMA_DIR = DATA_DIR / "chroma"

MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() == "true"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM_FALLBACK = os.getenv("LLM_FALLBACK", "groq")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
