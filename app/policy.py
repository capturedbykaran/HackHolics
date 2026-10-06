"""policy_registry loader for node 6 (decide). Owner: B.

Every threshold the escalation policy uses comes from the policy_registry table (Annex C) and is
reported in Decision.rule_ids. If the table, the DB or a parameter is missing, the DEFAULTS below are
used with rule_id "DEFAULT-<parameter>" so tests and local dev keep working.
"""
import logging
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Optional

from app import db

log = logging.getLogger("insightdesk.policy")


@dataclass(frozen=True)
class Rule:
    rule_id: str
    parameter: str
    operator: str
    value: str
    scope_plans: str = "ALL"
    effective_from: str = ""
    source_id: str = ""
    source_section: str = ""


ESCALATE_TOPICS = "refund,credit,billing_dispute,legal,security_incident,account_deletion"

# parameter -> (operator, value, justification). The justification is what the judges will ask for.
DEFAULTS: dict[str, tuple[str, str, str]] = {
    "critic_min_groundedness": (">=", "0.75",
                                "A.3 R1: below this share of supported claims the answer is not safe to send"),
    "max_revisions": ("<=", "1", "A.3 R1: one revision, then escalate (bounded latency and cost)"),
    "repeat_contact_threshold": (">=", "2",
                                 "A.3 R3: the third message on one issue (2 earlier user turns) counts as repeated contact"),
    "negative_sentiments": ("in", "angry,frustrated", "A.3 R3: sentiments that count as strong negative"),
    "escalate_topics": ("in", ESCALATE_TOPICS, "A.3 R2: topics only a human may decide"),
}

# Rows for the seed (db.seed_reference_data / data/seed/policy_registry.csv). source_id/section point at the
# policy article that justifies each rule; C replaces the placeholders with the real article ids.
SEED_ROWS = [
    ("CRITIC-MIN-GROUND", "Minimum critic groundedness to send an answer", "critic_min_groundedness", ">=", "0.75",
     "ALL", "2025-01-01", "KB-POL-002", "Escalation policy"),
    ("ESC-MAX-REVISIONS-01", "Maximum draft revisions before escalating", "max_revisions", "<=", "1",
     "ALL", "2025-01-01", "KB-POL-002", "Escalation policy"),
    ("ESC-REPEAT-01", "Prior user turns in a conversation that count as repeated contact",
     "repeat_contact_threshold", ">=", "2", "ALL", "2025-01-01", "KB-POL-002", "Repeated contact"),
    ("ESC-NEGATIVE-SENT-01", "Sentiments treated as strong negative", "negative_sentiments", "in",
     "angry,frustrated", "ALL", "2025-01-01", "KB-POL-002", "Repeated contact"),
    ("ESC-TOPICS-01", "Topics that always go to a human", "escalate_topics", "in", ESCALATE_TOPICS,
     "ALL", "2025-01-01", "KB-POL-002", "Mandatory escalation topics"),
]

_WARNED: set[str] = set()


def _default_rule(parameter: str) -> Rule:
    op, value, _ = DEFAULTS[parameter]
    return Rule(rule_id=f"DEFAULT-{parameter}", parameter=parameter, operator=op, value=value)


def default_policy() -> dict[str, Rule]:
    return {p: _default_rule(p) for p in DEFAULTS}


def _warn_once(key: str, msg: str, *args: Any) -> None:
    if key not in _WARNED:
        _WARNED.add(key)
        log.warning(msg, *args)


def _in_scope(scope_plans: Optional[str], plan: Optional[str]) -> bool:
    scope = (scope_plans or "ALL").strip()
    if scope.upper() == "ALL":
        return True
    return bool(plan) and plan in {p.strip() for p in scope.split(",")}


def load_policy(as_of_date: str, plan: Optional[str]) -> dict[str, Rule]:
    """{parameter: Rule} valid on `as_of_date` for `plan`; latest effective_from wins; DEFAULTS fill gaps."""
    rows: list[Any] = []
    try:
        with closing(db.get_conn()) as conn:
            rows = conn.execute("SELECT * FROM policy_registry").fetchall()
    except Exception as e:  # noqa: BLE001 - DB or table missing: dev/test fallback
        _warn_once("db", "policy_registry unavailable (%s); using DEFAULT rules", type(e).__name__)

    best: dict[str, Rule] = {}
    for r in rows:
        eff = (r["effective_from"] or "")
        if eff and eff > as_of_date:
            continue  # not in force yet
        if not _in_scope(r["scope_plans"], plan):
            continue
        rule = Rule(rule_id=r["rule_id"], parameter=r["parameter"], operator=r["operator"] or "",
                    value=str(r["value"]), scope_plans=r["scope_plans"] or "ALL", effective_from=eff,
                    source_id=r["source_id"] or "", source_section=r["source_section"] or "")
        cur = best.get(rule.parameter)
        if cur is None or (rule.effective_from, rule.rule_id) > (cur.effective_from, cur.rule_id):
            best[rule.parameter] = rule

    for parameter in DEFAULTS:
        if parameter not in best:
            if rows:
                _warn_once(parameter, "policy_registry has no row for %s; using DEFAULT", parameter)
            best[parameter] = _default_rule(parameter)
    return best


def _cast(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value


def threshold(policy: dict[str, Rule], parameter: str) -> tuple[Any, str]:
    """(value, rule_id). Numbers are cast; `in` rules return a list of strings."""
    rule = policy.get(parameter) or _default_rule(parameter)
    if rule.operator.strip().lower() == "in":
        return [v.strip() for v in rule.value.split(",") if v.strip()], rule.rule_id
    return _cast(rule.value.strip()), rule.rule_id
