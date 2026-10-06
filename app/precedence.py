"""WORK IN PROGRESS (not wired: gather looks for `resolve`). Annex A.2 source-precedence resolver.

Owner: B

resolve(chunks, version, as_of) -> (kept, conflicts). Pure, deterministic, no LLM. Steps, in Annex A.2 order:

1. Applicability: the chunk's product_versions cover the customer's version and it is in effect on as_of
   (effective_from <= as_of < deprecated_on). A resolved ticket is evidence for its whole major version
   (a 4.0 ticket is checked against 4.x), the same rule ingestion uses, so an old 4.0 workaround is seen and
   overridden by 4.1+ documentation instead of silently vanishing. Inapplicable chunks are dropped; a passed
   deprecation is recorded.
2. Explicit supersession: a kept, in-effect chunk whose `supersedes` names another chunk's source wins.
3. Authority (1 highest): a ticket (4) may add detail but never contradicts documentation; when it does, the
   ticket is dropped and "KB-x over TKT-y on <topic>" is recorded. A community post (5) is never authoritative:
   it is dropped whenever documentation (1-3) on the same topic was retrieved.
4. Recency: two contradicting sources of the same authority -> the more recently updated one wins.
5. Unresolved: same authority and the same last_updated -> "unresolved: A vs B on <topic>"; both are kept so
   the escalation handoff can carry both.

"Contradiction" is decided by explainable string checks on the same topic (shared error code, or >= 3 shared
content words), never by a model:
  a. the higher source forbids what the lower source recommends ("do not add a Delay step" vs "add a ... Delay
     step"),
  b. both state a fact of the same kind with no value in common: auth header (X-CF-Key vs Authorization:
     Bearer), signing algorithm (SHA1 vs HMAC-SHA256), menu path, duration (14 days vs 30 days),
  c. the lower source gives a menu path or duration that no higher source in the set confirms, while a higher
     source on the topic gives the procedure (open / go to / click / select / turn on ...).
Entries that do not start with "unresolved:" are informational and stay in response.conflicts_detected.
"""
import json
import re
from itertools import combinations

from app.ingest import parse_versions, version_covered
from app.schemas import Chunk

DOC_LEVELS = {1, 2, 3}          # documentation / release notes / tool results
TICKET, COMMUNITY = 4, 5
MIN_SHARED_WORDS = 3

_CODE = re.compile(r"\bCF-\d{3}\b")
_HEADER = re.compile(r"\bAuthorization:\s*Bearer\b|\bX-(?:[A-Za-z0-9]+-)*[A-Za-z0-9]+\b")
_ALGO = re.compile(r"\bHMAC-SHA-?\d+\b|\bSHA-?\d+\b|\bMD5\b", re.I)
_MENU = re.compile(r"[A-Z][\w-]*(?: [A-Z][\w-]*)*(?:\s*>\s*[A-Z][\w-]*(?: [A-Za-z][\w-]*)*)+")
_DURATION = re.compile(r"\b(\d+)[\s-]*(second|minute|hour|day|week|month)s?\b", re.I)
_PROCEDURE = re.compile(r"\b(?:open|go to|click|select|choose|turn on|enable|navigate)\b", re.I)
_FORBID = re.compile(r"(?i:\b(?:do not|don't|never|avoid))\s+([a-z]+)\s+(?:(?i:an?|the)\s+)?"
                     r"((?:[A-Z][\w-]*\s+)?[a-z][\w-]*)")
_NEGATED = re.compile(r"\b(?:do not|don't|never|avoid|instead of)\b[^.;]{0,40}$", re.I)
_WORD = re.compile(r"[a-z][a-z0-9-]{3,}")
_STOP = {"this", "that", "with", "your", "from", "have", "will", "when", "what", "which", "there", "their",
         "they", "them", "then", "than", "into", "only", "also", "each", "every", "after", "before", "about",
         "does", "should", "would", "could", "customer", "customers", "cloudflow", "article", "version",
         "versions", "ticket", "resolved", "resolution", "question", "please", "help", "using", "make", "need"}


# ---------------------------------------------------------------- facts
def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and not w.endswith("ss") else w


def _words(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP}


def _norm_menu(m: str) -> str:
    return " > ".join(p.strip().lower() for p in m.split(">"))


def facts(text: str) -> dict[str, set[str]]:
    """Checkable facts of one chunk, by kind."""
    return {
        "auth header": {h.lower().replace(" ", "") for h in _HEADER.findall(text)
                        if h.lower().startswith(("authorization", "x-cf-key", "x-api-key"))},
        "signing algorithm": {a.upper().replace("SHA-", "SHA") for a in _ALGO.findall(text)},
        "menu path": {_norm_menu(m) for m in _MENU.findall(text)},
        "duration": {f"{n} {u.lower()}" for n, u in _DURATION.findall(text)},
    }


def _menu_confirmed(path: str, paths: set[str]) -> bool:
    return any(p.startswith(path) or path.startswith(p) for p in paths)


def _same_topic(a: Chunk, b: Chunk) -> str | None:
    """Topic label if a and b are about the same thing, else None."""
    codes = set(_CODE.findall(a.text)) & set(_CODE.findall(b.text))
    if codes:
        return ", ".join(sorted(codes))
    shared = _words(f"{a.section} {a.text}") & _words(f"{b.section} {b.text}")
    if len(shared) >= MIN_SHARED_WORDS:
        return " ".join(sorted(shared)[:3])
    fa, fb = facts(a.text), facts(b.text)
    for kind in ("auth header", "signing algorithm"):  # both name a header / algorithm: same technical question
        if fa[kind] and fb[kind]:
            return kind
    return None


def _forbidden_action(high: str, low: str) -> str | None:
    """'do not add a Delay step' in high while low says 'add a 30 second Delay step' (not negated)."""
    for verb, obj in _FORBID.findall(high):
        obj_words = obj.lower().split()
        for m in re.finditer(re.escape(obj_words[-1]), low, re.I):
            window = low[max(0, m.start() - 60):m.end()].lower()
            if all(w in window for w in obj_words) and re.search(rf"\b{re.escape(verb.lower())}\b", window) \
                    and not _NEGATED.search(low[:m.start()]):
                return f"{verb} {obj}"
    return None


def contradiction(high: Chunk, low: Chunk, others_high: list[Chunk] | None = None) -> str | None:
    """Short reason if `low` contradicts `high` (assumed same topic), else None."""
    if action := _forbidden_action(high.text, low.text):
        return f"documentation says not to {action}"
    fh, fl = facts(high.text), facts(low.text)
    for kind in ("auth header", "signing algorithm"):
        if fh[kind] and fl[kind] and not (fh[kind] & fl[kind]):
            return f"{kind} {'/'.join(sorted(fl[kind]))} vs {'/'.join(sorted(fh[kind]))}"
    # menu paths and durations: only a value that NO documentation in the set confirms counts
    pool = [high] + (others_high or [])
    menus = set().union(*(facts(c.text)["menu path"] for c in pool))
    durations = set().union(*(facts(c.text)["duration"] for c in pool))
    stray_menu = sorted(p for p in fl["menu path"] if not _menu_confirmed(p, menus))
    stray_duration = sorted(d for d in fl["duration"] if d not in durations)
    if stray_menu and (fh["menu path"] or _PROCEDURE.search(high.text)):
        return f"menu path {'/'.join(stray_menu)} is not in current documentation"
    if stray_duration and fh["duration"] and _same_topic_words(high, low) >= MIN_SHARED_WORDS + 1:
        return f"duration {'/'.join(stray_duration)} vs {'/'.join(sorted(fh['duration']))}"
    return None


def _same_topic_words(a: Chunk, b: Chunk) -> int:
    return len(_words(f"{a.section} {a.text}") & _words(f"{b.section} {b.text}"))


# ---------------------------------------------------------------- steps
def _covers(c: Chunk, version: str | None) -> bool:
    if not version or not c.product_versions:
        return True
    try:
        ranges = parse_versions(c.product_versions)
    except ValueError:
        return True  # unknown spec: do not drop on a parsing problem
    if c.doc_type == "ticket":
        ranges = [(lo, (lo // 1000) * 1000 + 999) if lo == hi else (lo, hi) for lo, hi in ranges]
    return version_covered(json.dumps(ranges), version)


def _label(c: Chunk) -> str:
    return c.source_id


def resolve_draft(chunks: list[Chunk], version: str | None = None, as_of: str | None = None) -> tuple[list[Chunk], list[str]]:
    conflicts: list[str] = []

    def note(text: str) -> None:
        if text not in conflicts:
            conflicts.append(text)

    # 1. applicability
    kept: list[Chunk] = []
    for c in chunks:
        if not _covers(c, version):
            continue
        if as_of and c.effective_from and c.effective_from > as_of:
            continue  # upcoming change: retrieval returns it separately, never as current guidance
        if as_of and c.deprecated_on and c.deprecated_on <= as_of:
            note(f"{_label(c)} deprecated on {c.deprecated_on}; not used")
            continue
        kept.append(c)

    # 2. explicit supersession
    superseded: dict[str, str] = {}
    for c in kept:
        for old in c.supersedes:
            if old != c.source_id:
                superseded.setdefault(old, c.source_id)
    for c in kept:
        if c.source_id in superseded:
            note(f"{superseded[c.source_id]} supersedes {c.source_id}")
    kept = [c for c in kept if c.source_id not in superseded]

    # 3-5. authority, recency, unresolved (pairwise, deterministic order)
    dropped: set[str] = set()
    docs = [c for c in kept if c.authority_level in DOC_LEVELS]
    for a, b in combinations(kept, 2):
        if a.source_id == b.source_id or a.source_id in dropped or b.source_id in dropped:
            continue
        high, low = (a, b) if a.authority_level <= b.authority_level else (b, a)
        topic = _same_topic(high, low)
        if topic is None:
            continue
        if low.authority_level == COMMUNITY and high.authority_level in DOC_LEVELS:
            dropped.add(low.source_id)
            note(f"{high.source_id} over {low.source_id} on {topic}: community posts are never authoritative")
            continue
        if high.authority_level < low.authority_level:
            others = [d for d in docs if d.source_id != high.source_id]
            why = contradiction(high, low, others)
            if why:
                dropped.add(low.source_id)
                note(f"{high.source_id} over {low.source_id} on {topic}: {why}")
            continue
        # same authority: a contradiction either way round
        why = contradiction(a, b) or contradiction(b, a)
        if not why:
            continue
        if (a.last_updated or "") != (b.last_updated or ""):
            newer, older = (a, b) if (a.last_updated or "") > (b.last_updated or "") else (b, a)
            dropped.add(older.source_id)
            note(f"{newer.source_id} over {older.source_id} on {topic}: more recently updated ({why})")
        else:
            note(f"unresolved: {a.source_id} vs {b.source_id} on {topic} ({why})")

    kept = [c for c in kept if c.source_id not in dropped]
    kept.sort(key=lambda c: (c.authority_level, -c.score, "".join(chr(255 - ord(ch)) for ch in c.last_updated)))
    return kept, conflicts
