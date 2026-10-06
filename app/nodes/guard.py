"""Graph node: layer-1 input guardrails (app/guardrails/input_guard.py). Owner: B (wired by A).

Never clears an `early` already set by run_support (e.g. another account's conversation).
"""
from app.guardrails import check_input


def guard_node(state: dict) -> dict:
    v = check_input(state["req"].message, state.get("account_id"))
    signals = list(state.get("signals", []))
    signals += [s for s in v.signals if s not in signals]
    out: dict = {"redacted_message": v.redacted_message, "pii_found": v.pii_found, "signals": signals,
                 "guardrail_events": list(state.get("guardrail_events", [])) + v.events}
    if not state.get("early") and v.early:
        out.update(early=v.early, early_reason=v.early_reason)
    return out
