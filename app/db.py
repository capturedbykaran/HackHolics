"""SQLite DDL (Annex C + audit_log, conversations), get_conn().

Owner: B
"""

import sqlite3

from app.config import DB_PATH


def get_conn(path=DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
