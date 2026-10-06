"""Tests for app/tools.py.

Owner: B
"""

import pytest

from app.db import get_conn, init_db, seed_reference_data
from app.tools import (
    get_plan_limits,
    get_usage,
    lookup_account,
    run_tool,
)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Create a fresh seeded database for every test."""

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    init_db()
    seed_reference_data()

    conn = get_conn()

    try:
        # Test account 1
        conn.execute(
            """
            INSERT INTO accounts (
                account_id,
                company_name,
                owner_email,
                plan,
                status,
                product_version,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "A0001",
                "Test Company",
                "owner@example.com",
                "Pro",
                "active",
                "4.3",
                "2026-01-01",
            ),
        )

        # Test account 2
        conn.execute(
            """
            INSERT INTO accounts (
                account_id,
                company_name,
                owner_email,
                plan,
                status,
                product_version,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "A0002",
                "Second Company",
                "second@example.com",
                "Free",
                "past_due",
                "3.x",
                "2026-01-01",
            ),
        )

        # Usage for A0001
        conn.execute(
            """
            INSERT INTO usage (
                account_id,
                period,
                workflow_runs,
                api_calls_peak_per_min,
                seats_used
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "A0001",
                "2026-10",
                120,
                250,
                3,
            ),
        )

        conn.commit()

    finally:
        conn.close()


# ============================================================
# lookup_account
# ============================================================

def test_lookup_account_success():
    result = lookup_account("A0001")

    assert result.ok is True
    assert result.tool == "lookup_account"

    assert result.data["account_id"] == "A0001"
    assert result.data["company_name"] == "Test Company"
    assert result.data["plan"] == "Pro"
    assert result.data["status"] == "active"
    assert result.data["product_version"] == "4.3"


def test_lookup_account_redacts_email():
    result = lookup_account("A0001")

    assert result.ok is True
    assert "owner_email" not in result.data


def test_lookup_account_not_found():
    result = lookup_account("A9999")

    assert result.ok is False
    assert result.tool == "lookup_account"
    assert "not found" in result.error


# ============================================================
# get_plan_limits
# ============================================================

def test_get_plan_limits_success():
    result = get_plan_limits("Pro")

    assert result.ok is True
    assert result.tool == "get_plan_limits"

    assert result.data["plan"] == "Pro"
    assert result.data["api_rate_limit_per_min"] == 300
    assert result.data["monthly_workflow_runs"] == 20000
    assert result.data["seats"] == 5
    assert result.data["support_tier"] == "standard"
    assert result.data["monthly_price"] == 49.0


def test_get_plan_limits_not_found():
    result = get_plan_limits("Gold")

    assert result.ok is False
    assert result.tool == "get_plan_limits"
    assert "not found" in result.error


# ============================================================
# get_usage
# ============================================================

def test_get_usage_success():
    result = get_usage("A0001", "2026-10")

    assert result.ok is True
    assert result.tool == "get_usage"

    assert result.data["account_id"] == "A0001"
    assert result.data["period"] == "2026-10"
    assert result.data["workflow_runs"] == 120
    assert result.data["api_calls_peak_per_min"] == 250
    assert result.data["seats_used"] == 3


def test_get_usage_not_found():
    result = get_usage("A0001", "2025-01")

    assert result.ok is False
    assert result.tool == "get_usage"
    assert "not found" in result.error


def test_get_usage_unknown_account():
    result = get_usage("A9999", "2026-10")

    assert result.ok is False
    assert result.tool == "get_usage"
    assert "not found" in result.error


# ============================================================
# run_tool
# ============================================================

def test_run_tool_lookup_account():
    result = run_tool(
        "lookup_account",
        account_id="A0001",
    )

    assert result.ok is True
    assert result.tool == "lookup_account"
    assert result.data["account_id"] == "A0001"


def test_run_tool_get_usage():
    result = run_tool(
        "get_usage",
        account_id="A0001",
        period="2026-10",
    )

    assert result.ok is True
    assert result.tool == "get_usage"
    assert result.data["workflow_runs"] == 120


def test_run_tool_get_plan_limits():
    result = run_tool(
        "get_plan_limits",
        plan="Pro",
    )

    assert result.ok is True
    assert result.tool == "get_plan_limits"
    assert result.data["plan"] == "Pro"


def test_run_tool_unknown_tool():
    result = run_tool("unknown_tool")

    assert result.ok is False
    assert result.tool == "unknown_tool"
    assert "unknown tool" in result.error


def test_run_tool_missing_arguments():
    result = run_tool("lookup_account")

    assert result.ok is False
    assert result.tool == "lookup_account"