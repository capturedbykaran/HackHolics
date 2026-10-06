"""SQLite DDL (Annex C + audit_log, conversations, source_register), get_conn(), seed helpers.

Owner: B

Annex C tables/columns are FIXED (judges load their own data into them):
never rename or remove; extra columns/tables are fine.
"""

import os
import sqlite3
from pathlib import Path

from app.config import ROOT

DEFAULT_DB_PATH = ROOT / "data" / "insightdesk.db"

SCHEMA = """
-- ---------- Annex C (fixed) ----------
CREATE TABLE IF NOT EXISTS accounts (
    account_id      TEXT PRIMARY KEY CHECK (account_id GLOB 'A[0-9][0-9][0-9][0-9]'),
    company_name    TEXT NOT NULL,
    owner_email     TEXT NOT NULL,
    plan            TEXT NOT NULL CHECK (plan IN ('Free','Pro','Business','Enterprise')),
    status          TEXT NOT NULL CHECK (status IN ('active','past_due','suspended','cancelled')),
    product_version TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_limits (
    plan                   TEXT PRIMARY KEY,
    api_rate_limit_per_min INTEGER,
    monthly_workflow_runs  INTEGER,
    seats                  INTEGER,
    support_tier           TEXT,
    monthly_price          REAL
);

CREATE TABLE IF NOT EXISTS usage (
    account_id             TEXT REFERENCES accounts(account_id),
    period                 TEXT,  -- YYYY-MM
    workflow_runs          INTEGER,
    api_calls_peak_per_min INTEGER,
    seats_used             INTEGER,
    PRIMARY KEY (account_id, period)
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id     TEXT PRIMARY KEY,
    account_id     TEXT REFERENCES accounts(account_id),
    amount         REAL CHECK (amount > 0),
    currency       TEXT,
    charged_on     TEXT,  -- YYYY-MM-DD
    status         TEXT CHECK (status IN ('paid','failed','refunded')),
    failure_reason TEXT,
    card_last4     TEXT   -- never store full card numbers
);

CREATE TABLE IF NOT EXISTS platform_status (
    component   TEXT PRIMARY KEY,  -- api, workflow-engine, connectors, billing
    status      TEXT CHECK (status IN ('operational','degraded','outage')),
    incident_id TEXT,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS policy_registry (
    rule_id        TEXT PRIMARY KEY,
    description    TEXT,
    parameter      TEXT,
    operator       TEXT,
    value          TEXT,
    scope_plans    TEXT,  -- 'ALL' or comma-separated plans
    effective_from TEXT,
    source_id      TEXT,
    source_section TEXT
);

CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id      TEXT PRIMARY KEY,
    conversation_id TEXT,
    account_id      TEXT,
    queue           TEXT,
    priority        TEXT CHECK (priority IN ('low','normal','high','urgent')),
    created_at      TEXT,
    bundle_json     TEXT  -- PII-redacted
);

-- ---------- Ours (audit_log agreed with D / app/audit.py) ----------
CREATE TABLE IF NOT EXISTS audit_log (
    trace_id                TEXT PRIMARY KEY,
    conversation_id         TEXT,
    account_id              TEXT,
    created_at              TEXT,
    answer_type             TEXT,
    redacted_message        TEXT,
    intent_json             TEXT,
    sources_json            TEXT,
    tools_json              TEXT,
    critic_json             TEXT,
    escalation_reasons_json TEXT,
    conflicts_json          TEXT,
    model                   TEXT,
    tokens                  INTEGER,
    latency_json            TEXT,
    response_json           TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    account_id      TEXT,
    role            TEXT,
    payload_json    TEXT,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS source_register (
    source_id        TEXT PRIMARY KEY,
    doc_type         TEXT,
    title            TEXT,
    authority_level  INTEGER,
    product_versions TEXT,
    last_updated     TEXT,
    effective_from   TEXT,
    deprecated_on    TEXT,
    supersedes       TEXT,
    provenance       TEXT,
    synthetic        TEXT
);

CREATE INDEX IF NOT EXISTS idx_invoices_account      ON invoices(account_id);
CREATE INDEX IF NOT EXISTS idx_usage_account         ON usage(account_id);
CREATE INDEX IF NOT EXISTS idx_audit_conversation    ON audit_log(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_conv    ON conversations(conversation_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_conversation ON handoffs(conversation_id);
"""

# Children before parents so DROP works with foreign_keys=ON.
TABLES = [
    "usage", "invoices", "handoffs", "audit_log", "conversations", "source_register",
    "policy_registry", "platform_status", "plan_limits", "accounts",
]

# Must match data/world.yaml (owner C).
PLAN_LIMITS = [
    # plan, api_rate_limit_per_min, monthly_workflow_runs, seats, support_tier, monthly_price
    ("Free", 60, 1000, 1, "standard", 0.0),
    ("Pro", 300, 20000, 5, "standard", 49.0),
    ("Business", 1000, 100000, 25, "priority", 199.0),
    ("Enterprise", 5000, 1000000, 100, "priority", 999.0),
]

SEED_UPDATED_AT = "2026-01-01T00:00:00Z"

PLATFORM_STATUS = [
    # component, status, incident_id, updated_at
    ("api", "operational", None, SEED_UPDATED_AT),
    ("workflow-engine", "operational", None, SEED_UPDATED_AT),
    ("connectors", "degraded", "INC-2041", SEED_UPDATED_AT),
    ("billing", "operational", None, SEED_UPDATED_AT),
]

# source_id / source_section are placeholders until C links real policy articles.
POLICY_REGISTRY = [
    # rule_id, description, parameter, operator, value, scope_plans, effective_from, source_id, source_section
    ("REFUND-WINDOW-01", "Refunds allowed within N days of charge",
     "refund_window_days", "<=", "14", "ALL", "2025-01-01", "KB-BIL-001", "Refund policy"),
    ("CRITIC-MIN-GROUND", "Minimum critic groundedness to send an answer",
     "critic_min_groundedness", ">=", "0.75", "ALL", "2025-01-01", "KB-POL-001", "Answer quality"),
    ("CLARIFY-MIN-CONF", "Ask a clarifying question below this intent confidence",
     "clarify_min_confidence", ">=", "0.30", "ALL", "2025-01-01", "KB-POL-001", "Clarification"),
    ("ESC-SENTIMENT-01", "Escalate after N repeat contacts on the same issue",
     "escalate_repeat_contacts", ">=", "2", "ALL", "2025-01-01", "KB-POL-002", "Escalation"),
]


def db_path() -> Path:
    """DB file from env DB_PATH (read at call time), default data/insightdesk.db."""
    path = Path(os.getenv("DB_PATH") or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = False) -> None:
    """Create all tables/indexes. Idempotent; reset=True drops everything first."""
    conn = get_conn()
    try:
        with conn:
            if reset:
                for table in TABLES:
                    conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.executescript(SCHEMA)
    finally:
        conn.close()


def seed_reference_data(conn: sqlite3.Connection | None = None) -> None:
    """INSERT OR REPLACE plan_limits, platform_status and starter policy_registry rows."""
    own = conn is None
    conn = conn or get_conn()
    try:
        with conn:
            conn.executemany("INSERT OR REPLACE INTO plan_limits VALUES (?,?,?,?,?,?)", PLAN_LIMITS)
            conn.executemany("INSERT OR REPLACE INTO platform_status VALUES (?,?,?,?)", PLATFORM_STATUS)
            conn.executemany(
                "INSERT OR REPLACE INTO policy_registry VALUES (?,?,?,?,?,?,?,?,?)", POLICY_REGISTRY
            )
    finally:
        if own:
            conn.close()


def load_registry(conn: sqlite3.Connection | None = None) -> dict[str, str]:
    """{parameter: value} from policy_registry, for escalation.decide()."""
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute("SELECT parameter, value FROM policy_registry").fetchall()
        return {r["parameter"]: r["value"] for r in rows}
    finally:
        if own:
            conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
