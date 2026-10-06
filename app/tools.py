"""Support tools.

Owner: B

Deterministic SQLite tools used by the LangGraph workflow.
The LLM does not directly access the database; it requests a tool
and receives a validated ToolResult.
"""

import inspect
import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.db import get_conn, load_registry, row_to_dict
from app.guardrails import ACCOUNT_TOOLS, ALLOWED_TOOLS
from app.schemas import HandoffBundle, ToolResult


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
        created_at  (signup date, used by app/segment.py)

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
                product_version,
                created_at
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
# Tools 4-7 + handoff (added by A during the merge, in B's style; B may replace them)
# -------------------------------------------------------------------

HANDOFFS: dict[str, HandoffBundle] = {}  # in-memory copy for tests; the handoffs table is the store


def get_invoices(account_id: str) -> ToolResult:
    """Invoices for an account, newest first (card_last4 only, never a full card number)."""
    if not account_id:
        return _result("get_invoices", ok=False, error="account_id is required")
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT invoice_id, amount, currency, charged_on, status, failure_reason, card_last4
            FROM invoices
            WHERE account_id = ?
            ORDER BY charged_on DESC
            """,
            (account_id,),
        ).fetchall()
        return _result("get_invoices", ok=True, data={"invoices": [row_to_dict(r) for r in rows]})
    finally:
        conn.close()


def check_refund_eligibility(account_id: str, invoice_id: str | None = None,
                             as_of: str | None = None) -> ToolResult:
    """Deterministic refund-window check against policy_registry (REFUND-WINDOW-01). Never refunds."""
    invoices = get_invoices(account_id)
    if not invoices.ok:
        return _result("check_refund_eligibility", ok=False, error=invoices.error)
    rows = [i for i in invoices.data["invoices"] if invoice_id in (None, i["invoice_id"])]
    if not rows:
        return _result("check_refund_eligibility", ok=True, data={"eligible": False, "reason": "no_invoice"})
    window = int(load_registry().get("refund_window_days", 14))
    inv = rows[0]
    days = (date.fromisoformat(as_of or date.today().isoformat()) - date.fromisoformat(inv["charged_on"])).days
    return _result("check_refund_eligibility", ok=True, data={
        "invoice_id": inv["invoice_id"], "eligible": inv["status"] == "paid" and 0 <= days <= window,
        "days_since_charge": days, "window_days": window, "rule_id": "REFUND-WINDOW-01"})


def check_platform_status() -> ToolResult:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT component, status, incident_id, updated_at FROM platform_status").fetchall()
        return _result("check_platform_status", ok=True, data={"components": [row_to_dict(r) for r in rows]})
    finally:
        conn.close()


def send_password_reset(account_id: str) -> ToolResult:
    """Mock: triggers the secure reset email. Never returns the link, token or address (R9)."""
    found = lookup_account(account_id)
    if not found.ok:
        return _result("send_password_reset", ok=False, error=found.error)
    return _result("send_password_reset", ok=True, data={"sent": True})


def create_handoff(payload: HandoffBundle) -> str:
    """Store the (already PII-redacted) handoff bundle; returns the handoff id."""
    handoff_id = f"H-{uuid.uuid4().hex[:8]}"
    HANDOFFS[handoff_id] = payload
    try:
        conn = get_conn()
        try:
            with conn:
                conn.execute("INSERT INTO handoffs VALUES (?,?,?,?,?,?,?)",
                             (handoff_id, payload.conversation_id, payload.account_id, payload.queue,
                              payload.priority, datetime.now(timezone.utc).isoformat(),
                              json.dumps(payload.model_dump(), default=str)))
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - the in-memory copy still lets the response reference it
        pass
    return handoff_id


# -------------------------------------------------------------------
# Common tool dispatcher (B) + guardrails (A)
# -------------------------------------------------------------------

TOOL_REGISTRY = {
    "lookup_account": lookup_account,
    "get_usage": get_usage,
    "get_plan_limits": get_plan_limits,
    "get_invoices": get_invoices,
    "check_refund_eligibility": check_refund_eligibility,
    "check_platform_status": check_platform_status,
    "send_password_reset": send_password_reset,
}

_ACCOUNT_ID = re.compile(r"A\d{4}")


def is_not_found(result: ToolResult) -> bool:
    """A missing record is an answer ("no data"), not a tool failure."""
    return not result.ok and "not found" in (result.error or "")


def run_tool(name: str, **kwargs: Any) -> ToolResult:
    """Run one of the registered deterministic tools. Never raises.

    Guardrails: only the allowlisted read-only tools run (refunds, credits, plan changes and deletions do not
    exist as tools); account tools need a valid account id, which callers take from the X-Account-Id header;
    extra keyword arguments a tool does not accept (e.g. as_of) are dropped.
    """
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return _result(str(name)[:40], ok=False, error=f"unknown tool: {str(name)[:40]}")
    if name not in ALLOWED_TOOLS:
        return _result(name, ok=False, error="tool_not_allowed")

    account_id = kwargs.get("account_id")
    if name == "get_plan_limits" and not kwargs.get("plan") and account_id:
        account = lookup_account(account_id) if _ACCOUNT_ID.fullmatch(str(account_id)) else None
        if account is None or not account.ok:
            return _result(name, ok=False, error="no_account")
        kwargs["plan"] = account.data["plan"]
    elif name in ACCOUNT_TOOLS and name != "get_plan_limits":
        if not (account_id and _ACCOUNT_ID.fullmatch(str(account_id))):
            return _result(name, ok=False, error="no_account")

    accepted = inspect.signature(tool).parameters
    args = {k: v for k, v in kwargs.items() if k in accepted}
    try:
        return tool(**args)
    except TypeError as exc:
        return _result(name, ok=False, error=f"invalid tool arguments: {exc}")
    except Exception as exc:  # noqa: BLE001
        return _result(name, ok=False, error=f"tool execution failed: {exc}")
