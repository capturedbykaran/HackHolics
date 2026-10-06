"""Shared fixtures: temp DB, MOCK_LLM=true.

Owner: B
"""

import os

os.environ.setdefault("MOCK_LLM", "true")

import pytest  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Fresh seeded SQLite file per test; DB_PATH points at it."""
    path = tmp_path / "insightdesk.db"
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("MOCK_LLM", "true")
    db.init_db(reset=True)
    db.seed_reference_data()
    return path
