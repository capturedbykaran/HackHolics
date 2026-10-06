"""Load Annex C CSVs into SQLite (validate first, then upsert). Judges use this.

Owner: C

  python scripts/load_accounts.py --dir test_accounts/
  python scripts/load_accounts.py --dir data/seed --own

Any subset of the CSVs may be present; only those files are loaded.
"""
import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import db                                   # noqa: E402
from scripts.validate_accounts import COLUMNS, validate  # noqa: E402


def load(dir_: Path, own: bool = False) -> dict:
    """Validate, then load every CSV present in one transaction (all or nothing)."""
    if not dir_.is_dir():
        raise SystemExit(f"{dir_} is not a directory")
    db.init_db()
    con = db.get_conn()
    try:
        known_plans = {r["plan"] for r in con.execute("SELECT plan FROM plan_limits")}
        known_accounts = {r["account_id"] for r in con.execute("SELECT account_id FROM accounts")}
        violations = validate(dir_, external=not own, known_plans=known_plans, known_accounts=known_accounts)
        if violations:
            for x in violations:
                print("VIOLATION", x)
            raise SystemExit(f"Refusing to load: {len(violations)} violation(s). Fix the CSVs and retry.")
        counts = {}
        with con:
            for table, cols in COLUMNS.items():          # parents first: accounts before usage/invoices
                path = dir_ / f"{table}.csv"
                if not path.exists():
                    continue
                with path.open(newline="", encoding="utf-8-sig") as f:
                    rows = [[(r.get(c) or "").strip() or None for c in cols] for r in csv.DictReader(f)]
                con.executemany(f"INSERT OR REPLACE INTO {table}({','.join(cols)}) "
                                f"VALUES({','.join('?' * len(cols))})", rows)
                counts[table] = len(rows)
    except sqlite3.IntegrityError as e:
        raise SystemExit(f"Refusing to load: database constraint failed ({e}); nothing was written.")
    finally:
        con.close()
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--own", action="store_true", help="our own data: enforce reserved-ID rules")
    a = ap.parse_args()
    for t, n in load(Path(a.dir), a.own).items():
        print(f"loaded {t:16s} {n:4d}")
