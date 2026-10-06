"""Node 6: decide. Owner: B.

The answer / revise / escalate / not_found decision is made by CODE (app/escalation.py) from the
policy_registry thresholds (app/policy.py). No LLM, never raises.
"""
import logging

from app.escalation import decide
from app.policy import load_policy
from app.schemas import Decision

log = logging.getLogger("insightdesk.decide")


def _plan(state: dict):
    for t in state.get("tool_results", []) or []:
        if t.tool == "lookup_account" and t.ok:
            return t.output.get("plan")
    return None


def decide_node(state: dict) -> dict:
    try:
        policy = load_policy(state.get("as_of_date", ""), _plan(state))
        decision = decide(state, policy)
    except Exception:  # noqa: BLE001 - a broken decision must fail closed, not 500
        log.exception("decide failed")
        decision = Decision(action="escalate", reasons=["decide_error"])
    return {"decision": decision, "policy_rules_applied": list(decision.rule_ids)}
