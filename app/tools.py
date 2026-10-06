"""Support tools.

Owner: B

Deterministic SQLite tools used by the LangGraph workflow.
The LLM does not directly access the database; it requests a tool
and receives a validated ToolResult.
"""

from typing import Any

from app.db import get_conn, row_to_dict
from app.schemas import ToolResult


# -------------------------------------------------------------------
# Internal helper
# -------------------------------------------------------------------

def _result(
    tool: str,
    *,
    ok: bool,
    data: dict[str, Any] | None = None,
    error: str | None = None,
) -> ToolResult:
    """Create the shared ToolResult object."""
    return ToolResult(
        ok=ok,
        tool=tool,
        data=data,
        error=error,
    )


# -------------------------------------------------------------------
# Tool 1: lookup_account
# -------------------------------------------------------------------

def lookup_account(account_id: str) -> ToolResult:
    """Look up an account's non-sensitive account information.

    Returns:
        account_id
        company_name
        plan
        status
        product_version

    owner_email is deliberately not returned.
    """

    if not account_id:
        return _result(
            "lookup_account",
            ok=False,
            error="account_id is required",
        )

    conn = get_conn()

    try:
        row = conn.execute(
            """
            SELECT
                account_id,
                company_name,
                plan,
                status,
                product_version
            FROM accounts
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

        if row is None:
            return _result(
                "lookup_account",
                ok=False,
                error="account not found",
            )

        return _result(
            "lookup_account",
            ok=True,
            data=row_to_dict(row),
        )

    finally:
        conn.close()


# -------------------------------------------------------------------
# Tool 2: get_usage
# -------------------------------------------------------------------

def get_usage(
    account_id: str,
    period: str | None = None,
) -> ToolResult:
    """Return usage information for an account.

    If period is supplied, return usage for that YYYY-MM period.

    If period is omitted, return the most recent usage record.
    """

    if not account_id:
        return _result(
            "get_usage",
            ok=False,
            error="account_id is required",
        )

    conn = get_conn()

    try:
        if period is not None:
            row = conn.execute(
                """
                SELECT
                    account_id,
                    period,
                    workflow_runs,
                    api_calls_peak_per_min,
                    seats_used
                FROM usage
                WHERE account_id = ?
                  AND period = ?
                """,
                (account_id, period),
            ).fetchone()

        else:
            row = conn.execute(
                """
                SELECT
                    account_id,
                    period,
                    workflow_runs,
                    api_calls_peak_per_min,
                    seats_used
                FROM usage
                WHERE account_id = ?
                ORDER BY period DESC
                LIMIT 1
                """,
                (account_id,),
            ).fetchone()

        if row is None:
            return _result(
                "get_usage",
                ok=False,
                error="usage record not found",
            )

        return _result(
            "get_usage",
            ok=True,
            data=row_to_dict(row),
        )

    finally:
        conn.close()


# -------------------------------------------------------------------
# Tool 3: get_plan_limits
# -------------------------------------------------------------------

def get_plan_limits(plan: str) -> ToolResult:
    """Return limits and pricing for a CloudFlow plan."""

    if not plan:
        return _result(
            "get_plan_limits",
            ok=False,
            error="plan is required",
        )

    conn = get_conn()

    try:
        row = conn.execute(
            """
            SELECT
                plan,
                api_rate_limit_per_min,
                monthly_workflow_runs,
                seats,
                support_tier,
                monthly_price
            FROM plan_limits
            WHERE plan = ?
            """,
            (plan,),
        ).fetchone()

        if row is None:
            return _result(
                "get_plan_limits",
                ok=False,
                error="plan not found",
            )

        return _result(
            "get_plan_limits",
            ok=True,
            data=row_to_dict(row),
        )

    finally:
        conn.close()


# -------------------------------------------------------------------
# Common tool dispatcher
# -------------------------------------------------------------------

TOOL_REGISTRY = {
    "lookup_account": lookup_account,
    "get_usage": get_usage,
    "get_plan_limits": get_plan_limits,
}


def run_tool(name: str, **kwargs: Any) -> ToolResult:
    """Run one of the registered deterministic tools."""

    tool = TOOL_REGISTRY.get(name)

    if tool is None:
        return _result(
            name,
            ok=False,
            error=f"unknown tool: {name}",
        )

    try:
        return tool(**kwargs)
    except TypeError as exc:
        return _result(
            name,
            ok=False,
            error=f"invalid tool arguments: {exc}",
        )
    except Exception as exc:
        return _result(
            name,
            ok=False,
            error=f"tool execution failed: {exc}",
        )


# -------------------------------------------------------------------
# Remaining tools - implemented in later steps
# -------------------------------------------------------------------

def get_invoices(account_id):
    raise NotImplementedError


def check_refund_eligibility(account_id, invoice_id):
    raise NotImplementedError


def check_platform_status():
    raise NotImplementedError


def send_password_reset(account_id):
    raise NotImplementedError  # mock


def create_handoff(payload):
    raise NotImplementedError