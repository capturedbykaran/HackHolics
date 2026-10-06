"""Front matter (articles) + ticket JSON -> data/source_register.csv (Annex B).

Owner: C

  python scripts/build_register.py      # also run at the end of gen_kb.py

Reads the files on disk, so hand-edited or newly added documents are always reflected.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.ingest import DEFAULT_AUTHORITY, SourceMeta, split_front_matter, ticket_meta  # noqa: E402

REGISTER = ROOT / "data/source_register.csv"
FIELDS = ["source_id", "doc_type", "title", "authority_level", "product_versions", "last_updated",
          "effective_from", "deprecated_on", "supersedes", "provenance", "synthetic"]


def rows() -> list[dict]:
    out = []
    for p in sorted((ROOT / "data/kb/articles").glob("*.md")):
        fm, _ = split_front_matter(p.read_text(encoding="utf-8"))
        fm.setdefault("authority_level", DEFAULT_AUTHORITY.get(fm.get("doc_type"), 1))
        out.append(SourceMeta.model_validate(fm).model_dump(include=set(FIELDS)))
    for p in sorted((ROOT / "data/kb/tickets").glob("*.json")):
        t = json.loads(p.read_text(encoding="utf-8"))
        m = ticket_meta(t, None)
        m.setdefault("provenance", t.get("provenance", ""))
        out.append(SourceMeta.model_validate(m).model_dump(include=set(FIELDS)))
    return out


def main() -> int:
    data = rows()
    with REGISTER.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(data)
    print(f"{len(data)} sources -> {REGISTER.relative_to(ROOT)}")
    return len(data)


if __name__ == "__main__":
    main()
