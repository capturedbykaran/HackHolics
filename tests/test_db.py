"""Schema, constraints and reference seed for app/db.py.

Owner: B
"""

import sqlite3

import pytest

from app import db

EXPECTED_TABLES = {
    "accounts", "plan_limits", "usage", "invoices", "platform_status", "policy_registry",
    "handoffs", "audit_log", "conversations", "source_register",
}

ACCOUNT = ("A0001", "Acme Ltd", "owner@example.com", "Pro", "active", "v3.2", "2025-01-01")


@pytest.fixture
def conn():
    c = db.get_conn()
    yield c
    c.close()


def add_account(conn, row=ACCOUNT):
    conn.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?)", row)


def test_all_tables_exist(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= names


def test_db_path_from_env(temp_db):
    assert db.db_path() == temp_db
    assert temp_db.exists()


def test_init_db_idempotent():
    db.init_db()
    db.init_db()
    db.seed_reference_data()
    assert len(db.load_registry()) == 4


def test_connection_pragmas(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert isinstance(conn.execute("SELECT 1 AS x").fetchone(), sqlite3.Row)


def test_foreign_key_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO invoices VALUES ('INV-1','A9999',10,'USD','2025-01-01','paid',NULL,'4242')"
        )


@pytest.mark.parametrize("bad", [
    ("X12",) + ACCOUNT[1:],                        # account_id pattern
    ACCOUNT[:3] + ("Gold",) + ACCOUNT[4:],         # plan
    ACCOUNT[:4] + ("frozen",) + ACCOUNT[5:],       # status
])
def test_account_checks(conn, bad):
    with pytest.raises(sqlite3.IntegrityError):
        add_account(conn, bad)


def test_invoice_amount_must_be_positive(conn):
    add_account(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO invoices VALUES ('INV-1','A0001',0,'USD','2025-01-01','paid',NULL,'4242')"
        )


def test_usage_pk_rejects_duplicate(conn):
    add_account(conn)
    conn.execute("INSERT INTO usage VALUES ('A0001','2025-01',10,5,1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO usage VALUES ('A0001','2025-01',20,6,2)")


def test_plan_limits_seed(conn):
    rows = {r["plan"]: tuple(r) for r in conn.execute("SELECT * FROM plan_limits")}
    assert rows == {p[0]: p for p in db.PLAN_LIMITS}
    assert rows["Free"] == ("Free", 60, 1000, 1, "standard", 0)
    assert rows["Pro"] == ("Pro", 300, 20000, 5, "standard", 49)
    assert rows["Business"] == ("Business", 1000, 100000, 25, "priority", 199)
    assert rows["Enterprise"] == ("Enterprise", 5000, 1000000, 100, "priority", 999)


def test_platform_status_seed(conn):
    rows = {r["component"]: db.row_to_dict(r) for r in conn.execute("SELECT * FROM platform_status")}
    assert set(rows) == {"api", "workflow-engine", "connectors", "billing"}
    assert rows["connectors"]["status"] == "degraded"
    assert rows["connectors"]["incident_id"] == "INC-2041"
    assert all(rows[c]["status"] == "operational" for c in ("api", "workflow-engine", "billing"))


def test_load_registry():
    reg = db.load_registry()
    assert reg["refund_window_days"] == "14"
    assert reg == {
        "refund_window_days": "14",
        "critic_min_groundedness": "0.75",
        "clarify_min_confidence": "0.30",
        "escalate_repeat_contacts": "2",
    }


def test_row_to_dict(conn):
    assert db.row_to_dict(conn.execute("SELECT 1 AS x").fetchone()) == {"x": 1}
    assert db.row_to_dict(None) is None
