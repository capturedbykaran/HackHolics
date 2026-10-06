"""Check the generated knowledge base against the brief's minimums and the world bible.

Owner: C

  python scripts/validate_kb.py      # exit 1 on any failure; output goes in the data card
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import world as W                                    # noqa: E402
from app.ingest import split_front_matter, SourceMeta         # noqa: E402
from scripts.gen_kb import check_article                       # noqa: E402


def main():
    fails, notes = [], []
    arts = {p.stem: p.read_text(encoding="utf-8") for p in (ROOT / "data/kb/articles").glob("*.md")}
    tkts = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data/kb/tickets").glob("*.json")}
    specs = {s["source_id"]: s for s in W.ARTICLES}

    for sid, text in arts.items():
        fm, body = split_front_matter(text)
        try:
            SourceMeta.model_validate(fm)
        except Exception as e:
            fails.append(f"{sid}: bad front matter: {e}")
        if sid in specs:
            for p in check_article(body, specs[sid]):
                fails.append(f"{sid}: {p}")
        words = len(body.split())
        if words < 40:
            notes.append(f"{sid}: short article ({words} words)")

    help_articles = [s for s in W.ARTICLES if s["doc_type"] == "article"]
    cats = Counter(s["category"] for s in W.ARTICLES)
    checks = {
        ">= 30 help-center articles (article+policy)": len([s for s in W.ARTICLES if s["doc_type"] in ("article", "policy")]) >= 30,
        ">= 2 product versions with version-specific articles": {"3.x", "4.x"} <= {s["product_versions"] for s in help_articles},
        ">= 25 resolved tickets": len(tkts) >= 25,
        ">= 3 angry tickets needing a human": sum(t["needs_human"] for t in tkts.values()) >= 3,
        ">= 3 outdated tickets contradicting docs": sum(t["outdated"] for t in tkts.values()) >= 3,
        ">= 1 release note with a future deprecation": any(s["doc_type"] == "release_note" and s.get("effective_from", "") > W.AS_OF_DATE for s in W.ARTICLES),
        "policy articles for refund window, plan limits, SLAs": {"KB-POL-001", "KB-BIL-001", "KB-POL-002"} <= set(arts),
        "every policy_registry row cites an existing source": all(p[7] in arts for p in W.POLICIES),
        "all files listed in source_register.csv": {r["source_id"] for r in csv.DictReader((ROOT / "data/source_register.csv").open(encoding="utf-8"))} == set(arts) | set(tkts),
    }
    for name, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            fails.append(name)
    print("categories:", dict(cats))
    for n in notes:
        print("NOTE", n)
    for f in fails:
        print("FAIL", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
