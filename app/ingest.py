"""Ingestion pipeline: article (.md/.txt) or ticket (.json) + Source Register metadata -> ChromaDB + SQLite.

Owner: C

Pipeline (each step is a small pure function, so each can be unit-tested):
  1. validate   metadata against Annex B (Pydantic)                    -> 422 with field errors
  2. parse      front matter / ticket JSON (single ticket or a list) into clean text
  3. sanitise   normalise unicode, strip hidden HTML comments and zero-width characters,
                redact PII & secrets (Luhn-checked card numbers), flag prompt-injection text
                per chunk (kept as data for the critic, never obeyed)
  4. chunk      structure-aware: one chunk per "## section"; long sections split on paragraph
                boundaries with overlap; tables and code blocks never split; a ticket is one chunk
  5. enrich     contextual header per chunk (type, id, title > section, versions) is embedded
                with the chunk, so short chunks keep their meaning
  6. embed      bge-small-en-v1.5, normalised; computed BEFORE any write, so a model failure
                can never leave a document half-replaced
  7. upsert     idempotent: content hash -> skip if unchanged; otherwise atomically replace all
                chunks of the source_id under a write lock (re-ingest replaces, never duplicates)
  8. register   source_register row (+ policy_registry rows if the doc declares policy_values)
  9. refresh    mark the BM25 keyword index dirty so the next query rebuilds it
The call returns once both stores are committed, so the content is searchable immediately.
"""
import hashlib
import json
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from app import store
from app import db
from app.embeddings import embed_documents, embedder_name

MAX_WORDS = 220      # ~300 tokens: fits bge-small's 512-token window together with the header
OVERLAP_WORDS = 40
OPEN_END = 99_999    # upper bound for "4.2+" / "ALL"
TEXT_EXTS = (".md", ".markdown", ".txt")
DEFAULT_AUTHORITY = {"policy": 1, "article": 1, "release_note": 2, "ticket": 4, "community": 5}


# C-owned bookkeeping next to B's source_register (which keeps exactly the Annex B columns)
INGEST_STATE_DDL = """CREATE TABLE IF NOT EXISTS ingest_state(
  source_id TEXT PRIMARY KEY, content_hash TEXT, chunks INTEGER, flags TEXT, embedder TEXT, ingested_at TEXT)"""


def connect():
    """SQLite connection with all tables present (B's schema + ingest_state)."""
    db.init_db()
    con = db.get_conn()
    con.execute(INGEST_STATE_DDL)
    return con


# ---------------------------------------------------------------- 1. metadata
class PolicyValue(BaseModel):
    """Optional policy_registry row declared by a policy document (Annex C policy_registry)."""
    rule_id: str = Field(min_length=3)
    parameter: str = Field(min_length=1)
    operator: Literal["<=", ">=", "<", ">", "==", "in"]
    value: str
    description: str = ""
    scope_plans: str = "ALL"
    effective_from: str = ""
    source_section: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, v):
        return str(v)


class SourceMeta(BaseModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
    doc_type: Literal["article", "policy", "release_note", "ticket", "community"]
    title: str = Field(min_length=3)
    authority_level: int = Field(ge=1, le=5)
    product_versions: str
    last_updated: str
    effective_from: str = ""
    deprecated_on: str = ""
    supersedes: str = ""
    provenance: str = ""
    synthetic: str = "Y"
    policy_values: list[PolicyValue] = []      # optional: rows for policy_registry

    @field_validator("last_updated", "effective_from", "deprecated_on", mode="before")
    @classmethod
    def _date(cls, v):
        v = "" if v is None else str(v)     # YAML parses bare 2026-01-05 as a date object
        if v:
            date.fromisoformat(v)
        return v

    @field_validator("product_versions", "supersedes", mode="before")
    @classmethod
    def _str(cls, v):
        return "" if v is None else str(v)  # YAML parses bare 4.0 as a float

    @field_validator("product_versions")
    @classmethod
    def _versions(cls, v):
        parse_versions(v)        # raises on nonsense
        return v


# ---------------------------------------------------------------- versions
def version_int(v: str) -> int | None:
    """'4.3' -> 4003, '4.10.2' -> 4010, '4' -> 4000. Integers, so 4.10 sorts after 4.9."""
    m = re.match(r"\s*(\d+)(?:\.(\d+))?", str(v))
    return int(m[1]) * 1000 + int(m[2] or 0) if m else None


def parse_versions(spec: str) -> list[tuple[int, int]]:
    """'3.x;4.2+' -> [(3000, 3999), (4002, 99999)].  '4.0' -> [(4000, 4000)].  '4.0-4.2' -> [(4000, 4002)]."""
    ranges = []
    for part in [p.strip() for p in re.split(r"[;,]", str(spec)) if p.strip()]:
        if part.upper() == "ALL":
            ranges.append((0, OPEN_END))
        elif m := re.fullmatch(r"(\d+)\.x", part, re.I):
            ranges.append((int(m[1]) * 1000, int(m[1]) * 1000 + 999))
        elif m := re.fullmatch(r"(\d+(?:\.\d+)?)\+", part):
            ranges.append((version_int(m[1]), OPEN_END))
        elif m := re.fullmatch(r"(\d+\.\d+)\s*-\s*(\d+\.\d+)", part):
            ranges.append((version_int(m[1]), version_int(m[2])))
        elif re.fullmatch(r"\d+\.\d+(?:\.\d+)?", part):
            ranges.append((version_int(part), version_int(part)))
        else:
            raise ValueError(f"unrecognised product_versions part {part!r}")
    if not ranges:
        raise ValueError("product_versions is empty")
    return ranges


def version_covered(spec_ranges: str, version: str | None) -> bool:
    """spec_ranges is the JSON stored in chunk metadata; unknown customer version -> covered."""
    v = version_int(version) if version else None
    if v is None:
        return True
    return any(lo <= v <= hi for lo, hi in json.loads(spec_ranges))


def date_int(s: str, default: int) -> int:
    return int(s.replace("-", "")) if s else default


# ---------------------------------------------------------------- 2. parse
def split_front_matter(text: str) -> tuple[dict, str]:
    text_clean = text.lstrip("\ufeff \t\r\n")
    if text_clean.startswith("---"):
        parts = text_clean.split("---", 2)
        if len(parts) >= 3:
            fm_text, body = parts[1], parts[2]
            try:
                fm = yaml.safe_load(fm_text) or {}
                return fm, body.strip()
            except Exception:
                pass
    return {}, text.strip()



def ticket_to_markdown(t: dict) -> str:
    return (f"# {t.get('subject', t.get('id', 'Ticket'))}\n\n"
            f"Customer question: {t.get('customer_question', '')}\n\n"
            f"Resolution: {t.get('resolution', '')}\n\n"
            f"Tags: {', '.join(t.get('tags', []))}. Resolved: {t.get('resolved_at', '')}.")


def ticket_meta(ticket: dict, meta: dict | None) -> dict:
    m = {**ticket.get("metadata", {}), **(meta or {})}
    m.setdefault("source_id", ticket.get("id") or ticket.get("source_id"))
    m.setdefault("doc_type", "ticket")
    m.setdefault("title", ticket.get("subject", ""))
    m.setdefault("authority_level", DEFAULT_AUTHORITY["ticket"])
    m.setdefault("product_versions", str(ticket.get("product_version", "ALL")))
    m.setdefault("last_updated", ticket.get("resolved_at", ""))
    return m


# ---------------------------------------------------------------- 3. sanitise
CARD = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
PII_PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("API_KEY", re.compile(r"\b(?:sk|pk|cf|tok|key)[-_][A-Za-z0-9_]{16,}\b|(?<=Bearer )[A-Za-z0-9._~+/-]{20,}=*")),
    ("PHONE", re.compile(r"(?<![\w-])(?:\+?\d{1,3}[ -]?)?(?:\d[ -]?){9,11}\d(?![\w-])")),
]
INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above|earlier) (instructions|rules|messages)|you are now|system prompt|"
    r"disregard (the |all |your )?(policy|policies|instructions|rules)|forget (all |your )?(previous )?instructions|"
    r"new instructions:|issue (a|the) (full )?refund|reveal (the |your )?(token|password|key|secret))", re.I)
ZERO_WIDTH = re.compile(r"[​-‏⁠﻿]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def normalise(text: str) -> tuple[str, list[str]]:
    """Unicode NFKC, LF line endings, drop zero-width chars and hidden HTML comments."""
    flags = []
    text = unicodedata.normalize("NFKC", text.replace("\r\n", "\n").replace("\r", "\n"))
    if ZERO_WIDTH.search(text):
        flags.append("zero_width_removed")
        text = ZERO_WIDTH.sub("", text)
    hidden = HTML_COMMENT.findall(text)
    if hidden:
        flags.append("hidden_comment_removed")
        if any(INJECTION.search(h) for h in hidden):
            flags.append("hidden_injection")
        text = HTML_COMMENT.sub("", text)
    return text, flags


def redact(text: str) -> tuple[str, list[str]]:
    found = []

    def card(m):
        digits = re.sub(r"\D", "", m[0])
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            found.append("CARD")
            return "[CARD]"
        return m[0]

    text = CARD.sub(card, text)
    for label, pat in PII_PATTERNS:
        if pat.search(text):
            found.append(label)
            text = pat.sub(f"[{label}]", text)
    return text, sorted(set(found))


# ---------------------------------------------------------------- 4. chunk
def _split_long(paragraphs: list[str]) -> list[str]:
    chunks, cur = [], []
    for p in paragraphs:
        words = p.split()
        atomic = p.lstrip().startswith(("|", "```"))
        if cur and len(" ".join(cur).split()) + len(words) > MAX_WORDS and not atomic:
            chunks.append("\n\n".join(cur))
            tail = " ".join(" ".join(cur).split()[-OVERLAP_WORDS:])
            cur = [f"...{tail}"]
        cur.append(p)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def _paragraphs(text: str) -> list[str]:
    """Split on blank lines, but keep each Markdown table and each fenced code block as one paragraph."""
    paras, buf, in_code = [], [], False
    for block in re.split(r"\n\s*\n", text):
        if in_code or block.lstrip().startswith("```"):
            if not in_code and buf:                     # flush a pending table first
                paras.append("\n".join(buf)); buf = []
            buf.append(block)
            in_code = (block.count("```") % 2 == 1) != in_code
            if not in_code:
                paras.append("\n\n".join(buf)); buf = []
        elif block.lstrip().startswith("|"):
            buf.append(block)
        else:
            if buf:
                paras.append("\n".join(buf)); buf = []
            paras.append(block)
    if buf:
        paras.append("\n".join(buf))
    return [p for p in paras if p.strip()]


def chunk_markdown(body: str) -> list[tuple[str, str]]:
    """Return [(section_heading, text)] split on '## ' headings; tables and code blocks kept whole."""
    body = re.sub(r"^# .*\n?", "", body, count=1).strip()
    parts = re.split(r"^##\s+(.+?)\s*#*\s*$", body, flags=re.M)
    sections = []
    if parts[0].strip():
        sections.append(("Overview", parts[0].strip()))
    for i in range(1, len(parts), 2):
        if parts[i + 1].strip():
            sections.append((parts[i].strip(), parts[i + 1].strip()))
    return [(heading, piece) for heading, text in sections for piece in _split_long(_paragraphs(text))]


def chunk_ticket(body: str) -> list[tuple[str, str]]:
    """A ticket is one retrieval unit (subject + question + resolution); split only if very long."""
    body = re.sub(r"^# .*\n?", "", body, count=1).strip()
    return [("Ticket", piece) for piece in _split_long(_paragraphs(body))]


# ---------------------------------------------------------------- 5-9. ingest
def _version_meta(rng: list[tuple[int, int]]) -> dict:
    md = {"all_versions": any(lo == 0 or hi >= OPEN_END for lo, hi in rng)}
    for major in range(1, 10):          # boolean flags let Chroma pre-filter by major version
        md[f"v{major}"] = any(lo <= major * 1000 + 999 and hi >= major * 1000 for lo, hi in rng)
    return md


def _warnings(m: SourceMeta, known: set[str]) -> list[str]:
    today = date.today().isoformat()
    w = []
    if m.effective_from and m.effective_from > today:
        w.append(f"effective_from {m.effective_from} is in the future: served as an upcoming change until then")
    if m.deprecated_on and m.deprecated_on <= today:
        w.append(f"deprecated_on {m.deprecated_on} has passed: excluded from answers")
    for sid in filter(None, re.split(r"[;,\s]+", m.supersedes)):
        if sid not in known:
            w.append(f"supersedes unknown source {sid}")
    return w


def _prepare(body: str, m: SourceMeta) -> tuple[list[str], list[str], list[str], list[dict], dict]:
    """Chunk, enrich and build metadata. Pure: no writes."""
    pieces = chunk_ticket(body) if m.doc_type == "ticket" else chunk_markdown(body)
    if not pieces:
        raise ValueError("document has no content after parsing")
    rng = parse_versions(m.product_versions)
    if m.doc_type == "ticket":
        # a ticket resolved on 4.0 is evidence for 4.0 onward within that major version, so it can
        # surface (and be overridden by current docs in precedence) for a 4.3 customer
        rng = [(lo, (lo // 1000) * 1000 + 999) if lo == hi else (lo, hi) for lo, hi in rng]
    ranges, vmeta = json.dumps(rng), _version_meta(rng)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ids, docs, embed_texts, metas, flagged = [], [], [], [], []
    for i, (section, text) in enumerate(pieces):
        header = f"[{m.doc_type} {m.source_id}] {m.title} > {section} (versions {m.product_versions})"
        suspicious = bool(INJECTION.search(text))
        if suspicious:
            flagged.append(i)
        ids.append(f"{m.source_id}#{i:03d}")
        docs.append(text)
        embed_texts.append(f"{header}\n{text}")
        metas.append({
            "source_id": m.source_id, "doc_type": m.doc_type, "title": m.title, "section": section,
            "chunk_index": i, "n_chunks": len(pieces),
            "authority_level": m.authority_level, "product_versions": m.product_versions, "version_ranges": ranges,
            "last_updated": m.last_updated, "last_updated_int": date_int(m.last_updated, 0),
            "effective_from": m.effective_from, "effective_from_int": date_int(m.effective_from, 0),
            "deprecated_on": m.deprecated_on, "deprecated_on_int": date_int(m.deprecated_on, 99991231),
            "supersedes": m.supersedes, "synthetic": m.synthetic, "suspicious": suspicious,
            "ingested_at": now, **vmeta,
        })
    return ids, docs, embed_texts, metas, {"flagged_chunks": flagged}


def _parse(content: bytes, filename: str, meta: dict | None) -> list[tuple[dict, str]]:
    """-> [(metadata, markdown body)]; a .json file may hold one ticket or a list of tickets."""
    try:
        raw = content.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError(f"file is not UTF-8 text: {e}") from e
    name = filename.lower()
    if name.endswith(".json"):
        data = json.loads(raw)
        tickets = data if isinstance(data, list) else [data]
        if len(tickets) > 1 and meta and "source_id" in meta:
            raise ValueError("metadata.source_id cannot be shared by several tickets in one file")
        return [(ticket_meta(t, meta), ticket_to_markdown(t)) for t in tickets]
    if name.endswith(TEXT_EXTS):
        fm, body = split_front_matter(raw)
        return [({**fm, **(meta or {})}, body)]       # explicit metadata wins over front matter
    raise ValueError("unsupported file type: upload .md, .markdown, .txt or .json")


def ingest_document(content: bytes, filename: str, meta: dict | None = None, *, dry_run: bool = False) -> dict:
    """Ingest one file. Returns a result dict; for a JSON list of tickets, {"status": "batch", "results": [...]}."""
    docs = _parse(content, filename, meta)
    results = [_ingest_one(md, body, dry_run) for md, body in docs]
    if len(results) == 1:
        return results[0]
    return {"status": "batch", "results": results, "chunks_indexed": sum(r["chunks_indexed"] for r in results)}


def _ingest_one(raw_meta: dict, body: str, dry_run: bool) -> dict:
    t0 = time.perf_counter()
    m = SourceMeta.model_validate(raw_meta)
    body, flags = normalise(body)
    body, pii = redact(body)
    content_hash = hashlib.sha256((m.model_dump_json() + body).encode()).hexdigest()[:16]
    ids, docs, embed_texts, metas, info = _prepare(body, m)
    flags += ["prompt_injection_text"] if info["flagged_chunks"] else []

    con = connect()
    try:
        known = {r["source_id"] for r in con.execute("SELECT source_id FROM source_register")}
        result = {"source_id": m.source_id, "doc_type": m.doc_type, "pii_redacted": pii, "flags": flags,
                  "flagged_injection": bool(info["flagged_chunks"]), "warnings": _warnings(m, known)}
        if dry_run:
            return {**result, "status": "dry_run", "chunks_indexed": 0,
                    "chunks": [{"id": i, "section": md["section"], "words": len(d.split()), "embedded_text": e}
                               for i, d, e, md in zip(ids, docs, embed_texts, metas)]}

        prev = con.execute("SELECT content_hash FROM ingest_state WHERE source_id=?", (m.source_id,)).fetchone()
        if prev and prev["content_hash"] == content_hash:
            return {**result, "status": "unchanged", "chunks_indexed": 0}

        vectors = embed_documents(embed_texts)        # before any write: a failure here changes nothing
        # SQLite writes stay uncommitted until the Chroma swap succeeds; any error rolls them back
        with store.write_lock, con:
            con.execute("""INSERT OR REPLACE INTO source_register(source_id, doc_type, title, authority_level,
                           product_versions, last_updated, effective_from, deprecated_on, supersedes, provenance,
                           synthetic) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (m.source_id, m.doc_type, m.title, m.authority_level, m.product_versions, m.last_updated,
                         m.effective_from, m.deprecated_on, m.supersedes, m.provenance, m.synthetic))
            con.execute("INSERT OR REPLACE INTO ingest_state VALUES(?,?,?,?,?,?)",
                        (m.source_id, content_hash, len(ids), ",".join(flags), embedder_name(),
                         datetime.now(timezone.utc).isoformat(timespec="seconds")))
            if m.policy_values:
                con.execute("DELETE FROM policy_registry WHERE source_id=?", (m.source_id,))
            for pv in m.policy_values:
                con.execute("""INSERT OR REPLACE INTO policy_registry(rule_id, description, parameter, operator,
                               value, scope_plans, effective_from, source_id, source_section)
                               VALUES(?,?,?,?,?,?,?,?,?)""",
                            (pv.rule_id, pv.description, pv.parameter, pv.operator, pv.value, pv.scope_plans,
                             pv.effective_from or m.effective_from or m.last_updated, m.source_id,
                             pv.source_section))
            col = store.collection()
            col.delete(where={"source_id": m.source_id})
            col.upsert(ids=ids, documents=docs, embeddings=vectors, metadatas=metas)
            store.mark_dirty()
    finally:
        con.close()
    return {**result, "status": "replaced" if prev else "indexed", "chunks_indexed": len(ids), "chunk_ids": ids,
            "embedder": embedder_name(), "elapsed_ms": round((time.perf_counter() - t0) * 1000)}


def delete_source(source_id: str) -> bool:
    """Remove a document's chunks and its register row. Policy rows it declared are kept for audit."""
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM source_register WHERE source_id=?", (source_id,)).fetchone():
            return False
        with store.write_lock, con:
            con.execute("DELETE FROM source_register WHERE source_id=?", (source_id,))
            con.execute("DELETE FROM ingest_state WHERE source_id=?", (source_id,))
            store.collection().delete(where={"source_id": source_id})
            store.mark_dirty()
    finally:
        con.close()
    return True
