"""Generate synthetic account data in the Annex C schema.

Owner: C

Split of responsibilities (this is the "generation discipline" judges score):
  - Edge cases are HAND-BUILT with fixed IDs (A1001-A1012) so tests and the eval set can rely on them.
  - Bulk accounts come from the LLM (prompt: prompts/accounts_gen.txt), validated with Pydantic.
  - Everything numeric/derived (emails, dates, usage, invoices, card_last4) is computed in code
    from a fixed seed, so it is reproducible and logically consistent.
  - plan_limits and policy_registry come from app/world.py, the same source as the articles.

Usage:
  python scripts/gen_accounts.py --n 28           # LLM via LLM_ORDER
  GEN_MOCK=true python scripts/gen_accounts.py    # no API calls
Output: data/seed/*.csv
"""
import argparse
import csv
import json
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import world as W                                  # noqa: E402
from scripts.gen_llm import chat, is_mock, LLMUnavailable    # noqa: E402

OUT = ROOT / "data/seed"
AS_OF = date.fromisoformat(W.AS_OF_DATE)
rng = random.Random(42)


class GenAccount(BaseModel):
    company_name: str
    plan: Literal["Free", "Pro", "Business", "Enterprise"]
    status: Literal["active", "past_due", "suspended", "cancelled"]
    product_version: Literal["3.8", "4.1", "4.2", "4.3"]
    usage_level: Literal["low", "medium", "high"]
    currency: Literal["USD", "INR"]


# ---- Hand-built edge cases -----------------------------------------------------
# kind drives usage/invoice construction below. Dates are relative to AS_OF_DATE.
EDGE = [
    ("A1001", "Brightline Analytics", "Pro", "active", "4.3", "normal", "USD"),            # demo account
    ("A1002", "Kestrel Logistics", "Pro", "active", "4.3", "api_at_limit", "USD"),        # peak == 300
    ("A1003", "Monsoon Retail Labs", "Pro", "active", "4.3", "api_over_limit", "INR"),    # peak == 301 -> CF-429
    ("A1004", "Harbor & Pine Studio", "Business", "past_due", "4.3", "failed_payment", "USD"),
    ("A1005", "Saffron Grid Systems", "Pro", "active", "4.2", "duplicate_charge", "INR"),  # 2 identical charges
    ("A1006", "Northwind Ledger Co", "Business", "active", "4.3", "refund_last_day", "USD"),   # charged 14 days ago
    ("A1007", "Tidewater Robotics", "Pro", "active", "4.3", "refund_day_after", "USD"),      # charged 15 days ago
    ("A1008", "Copperleaf Media", "Pro", "suspended", "4.3", "suspended", "USD"),
    ("A1009", "Old Fort Textiles", "Business", "active", "3.8", "normal", "INR"),            # old version
    ("A1010", "Pebble Street Bakery", "Free", "active", "4.3", "runs_at_quota", "USD"),     # runs == 1000 -> CF-460
    ("A1011", "Granite Peak Health Tech", "Enterprise", "active", "4.3", "normal", "USD"),
    ("A1012", "Lumen Ferry Tours", "Pro", "cancelled", "4.1", "normal", "USD"),
]
LEVEL_FRACTION = {"low": (0.05, 0.3), "medium": (0.3, 0.75), "high": (0.75, 0.98)}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".")


def llm_accounts(n: int, log: list) -> list[GenAccount]:
    if is_mock():
        names = ["Indigo Vale", "Cobalt Orchard", "Quartz Lane", "Juniper Forge", "Rivermint", "Silverbirch Ops",
                 "Banyan Bytes", "Coral Arc", "Ashgrove Data", "Marigold Freight", "Nimbus Tea Co", "Teakwood Labs",
                 "Lotus Relay", "Driftwood Desk", "Kite & Compass", "Vermilion Health", "Opal Circuit", "Sandstone Ops",
                 "Glacier Mint", "Peacock Prints", "Zephyr Clinics", "Basalt Works", "Mango Metrics", "Fernhill Legal",
                 "Starling Freight", "Cedar Loop", "Amber Wharf", "Tamarind Tech"]
        out = []
        for i in range(n):
            plan = rng.choices(["Free", "Pro", "Business", "Enterprise"], [30, 35, 25, 10])[0]
            status = rng.choices(["active", "past_due", "suspended", "cancelled"], [70, 15, 8, 7])[0]
            if plan == "Free" and status in ("past_due", "suspended"):
                status = "active"
            out.append(GenAccount(company_name=names[i % len(names)] + ("" if i < len(names) else f" {i}"), plan=plan,
                                  status=status, product_version=rng.choices(["3.8", "4.1", "4.2", "4.3"], [15, 15, 25, 45])[0],
                                  usage_level=rng.choice(["low", "medium", "high"]), currency=rng.choice(["USD", "INR"])))
        log.append({"provider": "template:mock", "requested": n, "valid": n, "rejected": []})
        return out

    text = (ROOT / "prompts/accounts_gen.txt").read_text(encoding="utf-8")
    system, user = text.split("USER:", 1)
    system, user = system.replace("SYSTEM:", "").strip(), user.strip().replace("{n}", str(n))
    for attempt in range(3):
        try:
            raw, provider = chat(system, user, json_mode=True, temperature=0.8)
        except LLMUnavailable as e:
            log.append({"attempt": attempt, "error": str(e)})
            break
        valid, rejected = [], []
        try:
            items = json.loads(raw).get("accounts", [])
        except json.JSONDecodeError as e:
            log.append({"attempt": attempt, "provider": provider, "error": f"bad JSON: {e}"})
            continue
        seen = {e[1].lower() for e in EDGE}
        for item in items:
            try:
                a = GenAccount.model_validate(item)
            except ValidationError as e:
                rejected.append({"row": item, "error": e.errors()[0]["msg"]})
                continue
            if a.plan == "Free" and a.status in ("past_due", "suspended"):
                rejected.append({"row": item, "error": "Free plan cannot be past_due/suspended"})
                continue
            if a.company_name.lower() in seen:
                rejected.append({"row": item, "error": "duplicate company"})
                continue
            seen.add(a.company_name.lower())
            valid.append(a)
        log.append({"attempt": attempt, "provider": provider, "requested": n, "valid": len(valid), "rejected": rejected})
        if len(valid) >= n * 0.8:
            return valid[:n]
    raise SystemExit("LLM account generation failed; see data/seed/generation_log.json or use GEN_MOCK=true")


def months_back(k: int) -> date:
    y, m = AS_OF.year, AS_OF.month - k
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1)


def build(n: int):
    log: list = []
    rows = [dict(account_id=a, company_name=c, plan=p, status=s, product_version=v, kind=k, currency=cur)
            for a, c, p, s, v, k, cur in EDGE]
    for i, g in enumerate(llm_accounts(n, log)):
        rows.append(dict(account_id=f"A{1013 + i}", company_name=g.company_name, plan=g.plan, status=g.status,
                         product_version=g.product_version, kind=g.usage_level, currency=g.currency))

    accounts, usage, invoices = [], [], []
    inv_no = 6001
    cur_period, prev_period = AS_OF.strftime("%Y-%m"), months_back(1).strftime("%Y-%m")
    for r in rows:
        plan = W.PLANS[r["plan"]]
        created = AS_OF - timedelta(days=rng.randint(120, 900))
        accounts.append(dict(account_id=r["account_id"], company_name=r["company_name"],
                             owner_email=f"{slug(r['company_name'])}.owner@example.com", plan=r["plan"],
                             status=r["status"], product_version=r["product_version"], created_at=created.isoformat()))
        # usage: current (partial) and previous period
        lo, hi = LEVEL_FRACTION.get(r["kind"], (0.2, 0.6))
        for period, frac_scale in ((prev_period, 1.0), (cur_period, AS_OF.day / 30)):
            runs = int(plan["monthly_workflow_runs"] * rng.uniform(lo, hi) * frac_scale)
            peak = int(plan["api_rate_limit_per_min"] * rng.uniform(lo, hi))
            if period == cur_period and r["kind"] == "api_at_limit":
                peak = plan["api_rate_limit_per_min"]
            if period == cur_period and r["kind"] == "api_over_limit":
                peak = plan["api_rate_limit_per_min"] + 1
            if period == cur_period and r["kind"] == "runs_at_quota":
                runs = plan["monthly_workflow_runs"]
            if r["status"] == "cancelled" and period == cur_period:
                runs, peak = 0, 0
            usage.append(dict(account_id=r["account_id"], period=period, workflow_runs=runs,
                              api_calls_peak_per_min=peak, seats_used=rng.randint(1, plan["seats"])))
        # invoices: none for Free; monthly on the 1st for the last 3 months
        if r["plan"] == "Free":
            continue
        price = plan["monthly_price"] * (84 if r["currency"] == "INR" else 1)
        last4 = f"{rng.randint(0, 9999):04d}"
        months = [months_back(2), months_back(1), months_back(0)]
        if r["status"] == "cancelled":
            months = months[:1]
        for i, d in enumerate(months):
            latest = i == len(months) - 1
            status, reason = "paid", ""
            if latest and r["status"] in ("past_due", "suspended"):
                status, reason = "failed", "card_declined"
            if r["status"] == "suspended" and i == len(months) - 2:
                status, reason = "failed", "insufficient_funds"
            invoices.append(dict(invoice_id=f"INV-{inv_no}", account_id=r["account_id"], amount=round(price, 2),
                                 currency=r["currency"], charged_on=d.isoformat(), status=status,
                                 failure_reason=reason, card_last4=last4))
            inv_no += 1
        if r["kind"] == "duplicate_charge":
            invoices.append(dict(invoices[-1], invoice_id=f"INV-{inv_no}")); inv_no += 1
        if r["kind"] in ("refund_last_day", "refund_day_after"):
            days = 14 if r["kind"] == "refund_last_day" else 15
            invoices.append(dict(invoice_id=f"INV-{inv_no}", account_id=r["account_id"], amount=round(price * 0.5, 2),
                                 currency=r["currency"], charged_on=(AS_OF - timedelta(days=days)).isoformat(),
                                 status="paid", failure_reason="", card_last4=last4))
            inv_no += 1

    plan_limits = [dict(plan=k, **v) for k, v in W.PLANS.items()]
    now = f"{W.AS_OF_DATE}T08:00:00Z"
    platform_status = [
        dict(component="api", status="operational", incident_id="", updated_at=now),
        dict(component="workflow-engine", status="operational", incident_id="", updated_at=now),
        dict(component="connectors", status="degraded", incident_id="INC-2026-1004", updated_at=now),
        dict(component="billing", status="operational", incident_id="", updated_at=now),
        dict(component="webhooks", status="operational", incident_id="", updated_at=now),
    ]
    keys = ["rule_id", "description", "parameter", "operator", "value", "scope_plans", "effective_from", "source_id", "source_section"]
    policy_registry = [dict(zip(keys, p)) for p in W.POLICIES]
    return dict(accounts=accounts, plan_limits=plan_limits, usage=usage, invoices=invoices,
                platform_status=platform_status, policy_registry=policy_registry), log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=28, help="LLM-generated accounts on top of 12 edge cases")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tables, log = build(args.n)
    for name, rows in tables.items():
        with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"{name:16s} {len(rows):4d} rows")
    (OUT / "generation_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
