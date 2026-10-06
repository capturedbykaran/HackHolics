"""Validate account CSVs against the Annex C schema and logical constraints.

Owner: C

  python scripts/validate_accounts.py --dir data/seed            # our data (also checks reserved IDs)
  python scripts/validate_accounts.py --dir test_accounts --external # judge data (reserved IDs allowed)

Exit code 1 if any violation. Used by load_accounts.py before inserting.
"""
import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

PLANS = {"Free", "Pro", "Business", "Enterprise"}
ACC_STATUS = {"active", "past_due", "suspended", "cancelled"}
INV_STATUS = {"paid", "failed", "refunded"}
COLUMNS = {
    "accounts": ["account_id", "company_name", "owner_email", "plan", "status", "product_version", "created_at"],
    "plan_limits": ["plan", "api_rate_limit_per_min", "monthly_workflow_runs", "seats", "support_tier", "monthly_price"],
    "usage": ["account_id", "period", "workflow_runs", "api_calls_peak_per_min", "seats_used"],
    "invoices": ["invoice_id", "account_id", "amount", "currency", "charged_on", "status", "failure_reason", "card_last4"],
    "platform_status": ["component", "status", "incident_id", "updated_at"],
    "policy_registry": ["rule_id", "description", "parameter", "operator", "value", "scope_plans", "effective_from", "source_id", "source_section"],
}


def is_date(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def validate(dir_: Path, external: bool = False, known_plans: set | None = None,
             known_accounts: set | None = None) -> list[str]:
    """known_* come from the database, so judges can load e.g. invoices for accounts already loaded."""
    v: list[str] = []
    t = {name: read(dir_ / f"{name}.csv") for name in COLUMNS if (dir_ / f"{name}.csv").exists()}
    for name, rows in t.items():
        if rows:
            missing = [c for c in COLUMNS[name] if c not in rows[0]]
            if missing:
                v.append(f"{name}: missing required columns {missing}")

    acc = {r["account_id"]: r for r in t.get("accounts", [])}
    acc_ids = set(acc) | (known_accounts or set())
    plans = {r["plan"] for r in t.get("plan_limits", [])} | (known_plans or set()) | PLANS
    for r in t.get("accounts", []):
        aid = r["account_id"]
        if not re.fullmatch(r"A\d{4}", aid):
            v.append(f"accounts {aid}: id must be A + 4 digits")
        elif not external and 9000 <= int(aid[1:]) <= 9999:
            v.append(f"accounts {aid}: A9000-A9999 are reserved for judges")
        if r["plan"] not in plans:
            v.append(f"accounts {aid}: unknown plan {r['plan']!r}")
        if r["status"] not in ACC_STATUS:
            v.append(f"accounts {aid}: bad status {r['status']!r}")
        if not r["owner_email"].endswith("@example.com"):
            v.append(f"accounts {aid}: owner_email must use @example.com")
        if not re.fullmatch(r"\d+\.\d+", r["product_version"]):
            v.append(f"accounts {aid}: product_version must look like 4.3")
        if not is_date(r["created_at"]):
            v.append(f"accounts {aid}: created_at not YYYY-MM-DD")

    for r in t.get("usage", []):
        key = f"usage {r['account_id']}/{r['period']}"
        if r["account_id"] not in acc_ids:
            v.append(f"{key}: unknown account")
        if not re.fullmatch(r"\d{4}-\d{2}", r["period"]):
            v.append(f"{key}: period must be YYYY-MM")
        for c in ("workflow_runs", "api_calls_peak_per_min", "seats_used"):
            if not r[c].isdigit():
                v.append(f"{key}: {c} must be a non-negative integer")

    by_acc: dict[str, list[dict]] = {}
    for r in t.get("invoices", []):
        iid = r["invoice_id"]
        by_acc.setdefault(r["account_id"], []).append(r)
        if r["account_id"] not in acc_ids:
            v.append(f"invoices {iid}: unknown account")
        if not external and iid.startswith("INV-J"):
            v.append(f"invoices {iid}: INV-J* is reserved for judges")
        try:
            if float(r["amount"]) <= 0:
                v.append(f"invoices {iid}: amount must be > 0")
        except ValueError:
            v.append(f"invoices {iid}: amount not a number")
        if r["status"] not in INV_STATUS:
            v.append(f"invoices {iid}: bad status {r['status']!r}")
        if (r["status"] == "failed") != bool(r["failure_reason"]):
            v.append(f"invoices {iid}: failure_reason must be set only when status is failed")
        if not re.fullmatch(r"\d{4}", r["card_last4"]):
            v.append(f"invoices {iid}: card_last4 must be exactly 4 digits (never a full card number)")
        if not is_date(r["charged_on"]):
            v.append(f"invoices {iid}: charged_on not YYYY-MM-DD")

    # cross-table consistency: account status vs invoices
    for aid, a in acc.items():
        invs = sorted(by_acc.get(aid, []), key=lambda r: r["charged_on"])
        if a["plan"] == "Free" and invs:
            v.append(f"accounts {aid}: Free plan should have no invoices")
        if a["status"] in ("past_due", "suspended") and not any(i["status"] == "failed" for i in invs):
            v.append(f"accounts {aid}: {a['status']} but no failed invoice")
        if a["status"] == "active" and invs and invs[-1]["status"] == "failed":
            v.append(f"accounts {aid}: active but latest invoice failed")

    for r in t.get("policy_registry", []):
        if not r["source_id"] or not r["source_section"]:
            v.append(f"policy_registry {r['rule_id']}: must cite source_id and source_section")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--external", action="store_true", help="judge data: allow reserved IDs")
    args = ap.parse_args()
    violations = validate(Path(args.dir), args.external)
    for x in violations:
        print("VIOLATION", x)
    print(f"{len(violations)} violation(s)")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
