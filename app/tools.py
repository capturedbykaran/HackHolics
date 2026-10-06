"""STUB (owner: B). Support tools.

Minimal SQLite-backed version (app/db.py tables) so the graph runs end to end.
Contract used by A's code:
  * run_tool(name, account_id=..., **kw) -> ToolResult   (never raises; "not_found" is ok=False, not a failure)
    guardrail: only allowlisted read-only tools run (error "tool_not_allowed"); account tools need a valid
    account id (error "no_account"); send_password_reset returns only {"sent": True}
  * create_handoff(bundle: HandoffBundle) -> handoff_id; HANDOFFS keeps them in memory for tests
"""
import json
import re
import uuid
from contextlib import closing
from datetime import date, datetime, timezone

from app import db
from app.guardrails import ACCOUNT_TOOLS, ALLOWED_TOOLS
from app.schemas import HandoffBundle, ToolResult

_ACCOUNT_ID = re.compile(r"A\d{4}")

HANDOFFS: dict[str, HandoffBundle] = {}


class NotFound(Exception):
    pass


def _one(sql: str, *args) -> dict:
    with closing(db.get_conn()) as conn:
        row = conn.execute(sql, args).fetchone()
    if row is None:
        raise NotFound
    return dict(row)


def _all(sql: str, *args) -> list[dict]:
    with closing(db.get_conn()) as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def lookup_account(account_id):
    return _one("SELECT * FROM accounts WHERE account_id = ?", account_id)


def get_usage(account_id):
    return {"usage": _all("SELECT * FROM usage WHERE account_id = ? ORDER BY period DESC LIMIT 3", account_id)}


def get_plan_limits(plan):
    return _one("SELECT * FROM plan_limits WHERE plan = ?", plan)


def get_invoices(account_id):
    return {"invoices": _all("SELECT * FROM invoices WHERE account_id = ? ORDER BY charged_on DESC", account_id)}


def check_refund_eligibility(account_id, invoice_id=None, as_of=None):
    inv = get_invoices(account_id)["invoices"]
    inv = [i for i in inv if invoice_id in (None, i["invoice_id"])]
    if not inv:
        return {"eligible": False, "reason": "no_invoice"}
    window = int(db.load_registry().get("refund_window_days", 14))
    days = (date.fromisoformat(as_of or date.today().isoformat()) - date.fromisoformat(inv[0]["charged_on"])).days
    return {"invoice_id": inv[0]["invoice_id"], "eligible": inv[0]["status"] == "paid" and days <= window,
            "days_since_charge": days, "window_days": window, "rule_id": "REFUND-WINDOW-01"}


def check_platform_status():
    return {"components": _all("SELECT * FROM platform_status")}


def send_password_reset(account_id):  # mock: never returns the link itself
    lookup_account(account_id)
    return {"sent": True}  # never the link, token or address


def run_tool(name: str, account_id: str | None = None, as_of: str | None = None, **kw) -> ToolResult:
    # guardrail: only allowlisted, read-only tools can run; account tools need a valid signed-in account id
    if name not in ALLOWED_TOOLS:
        return ToolResult(tool=str(name)[:40], ok=False, error="tool_not_allowed")
    has_account = bool(account_id and _ACCOUNT_ID.fullmatch(account_id))
    if name in ACCOUNT_TOOLS and not has_account and not (name == "get_plan_limits" and kw.get("plan")):
        return ToolResult(tool=name, ok=False, error="no_account")
    try:
        if name == "get_plan_limits":
            out = get_plan_limits(kw.get("plan") or lookup_account(account_id)["plan"])
        elif name == "check_platform_status":
            out = check_platform_status()
        elif name == "check_refund_eligibility":
            out = check_refund_eligibility(account_id, kw.get("invoice_id"), as_of)
        else:
            out = {"lookup_account": lookup_account, "get_usage": get_usage, "get_invoices": get_invoices,
                   "send_password_reset": send_password_reset}[name](account_id)
        return ToolResult(tool=name, output=out)
    except NotFound:
        return ToolResult(tool=name, ok=False, error="not_found")
    except Exception as e:  # noqa: BLE001
        return ToolResult(tool=name, ok=False, error=f"{type(e).__name__}: {e}"[:200])


def create_handoff(payload: HandoffBundle) -> str:
    handoff_id = f"H-{uuid.uuid4().hex[:8]}"
    HANDOFFS[handoff_id] = payload
    try:
        with closing(db.get_conn()) as conn, conn:
            conn.execute("INSERT INTO handoffs VALUES (?,?,?,?,?,?,?)",
                         (handoff_id, payload.conversation_id, payload.account_id, payload.queue,
                          payload.priority, datetime.now(timezone.utc).isoformat(),
                          json.dumps(payload.model_dump(), default=str)))
    except Exception:  # noqa: BLE001  - in-memory copy is enough for the stub
        pass
    return handoff_id
