"""One command: init DB, load seed CSVs, ingest the KB. Builds data/insightdesk.db and data/chroma/.

Owner: C

  python scripts/seed.py            # idempotent; unchanged documents are skipped
  python scripts/seed.py --reset    # delete both stores first and rebuild from scratch
"""
import argparse
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete data/insightdesk.db and data/chroma first")
    args = ap.parse_args()

    from app import config, db
    if args.reset:
        db.db_path().unlink(missing_ok=True)
        shutil.rmtree(config.CHROMA_DIR, ignore_errors=True)
    db.init_db()

    from app.ingest import ingest_document          # noqa: E402  (imported after a reset)
    from scripts.load_accounts import load           # noqa: E402

    t0 = time.time()
    for table, n in load(ROOT / "data/seed", own=True).items():
        print(f"sqlite  {table:16s} {n:4d}")
    stats, chunks = Counter(), 0
    files = sorted((ROOT / "data/kb/articles").glob("*.md")) + sorted((ROOT / "data/kb/tickets").glob("*.json"))
    for f in files:
        r = ingest_document(f.read_bytes(), f.name)
        for one in r.get("results", [r]):
            stats[one["status"]] += 1
            chunks += one["chunks_indexed"]
            if one.get("flagged_injection"):
                print("  flagged injection text in", one["source_id"])
            for w in one.get("warnings", []):
                print(f"  note {one['source_id']}: {w}")
    print(f"chroma  {len(files)} files, {chunks} chunks: {dict(stats)}  ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
