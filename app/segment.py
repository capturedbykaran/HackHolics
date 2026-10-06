"""Customer segmentation, decided in code (never by the LLM). Owner: A.

  prospect           no account id, or the account does not exist
  former_customer    account status is cancelled
  new_customer       account created within registry "new_customer_days" (default 30) of as_of_date
  existing_customer  any other account
"""
from datetime import date

from app import tools

DEFAULT_NEW_CUSTOMER_DAYS = 30
SAFE_FIELDS = ("account_id", "plan", "status", "product_version", "created_at")  # no email / company name


def segment_user(account_id: str | None, as_of_date: str, registry: dict) -> tuple[str, dict]:
    if not account_id:
        return "prospect", {}
    r = tools.run_tool("lookup_account", account_id=account_id)
    if not r.ok:
        return "prospect", {}
    info = {k: r.output.get(k) for k in SAFE_FIELDS}
    if info["status"] == "cancelled":
        return "former_customer", info
    try:
        age = (date.fromisoformat(as_of_date) - date.fromisoformat(str(info["created_at"])[:10])).days
    except ValueError:
        return "existing_customer", info
    info["days_since_signup"] = age
    new_days = int(registry.get("new_customer_days", DEFAULT_NEW_CUSTOMER_DAYS))
    return ("new_customer" if 0 <= age <= new_days else "existing_customer"), info
