"""Node 2: classify (LLM call 1). Owner: A."""
from app import llm
from app.schemas import ClassifierOut

CLARIFY_MIN_CONFIDENCE = 0.3  # below this the request is treated as too vague to act on


def classify_node(state: dict) -> dict:
    req = state["req"]
    system = llm.load_prompt("classifier.txt")
    user = (f"Product version stated in the request: {req.product_version or 'unknown'}\n\n"
            f"<customer_message>\n{state['redacted_message']}\n</customer_message>")
    failures = list(state.get("failures", []))
    try:
        out: ClassifierOut = llm.json_call(system, user, ClassifierOut, state, node="classify")
    except llm.LLMError:
        # Safe default: no tools, no guess. The failure flag routes the request to escalation.
        out = ClassifierOut(type="troubleshooting", confidence=0.0)
        failures.append("classify_llm_failed")

    out = out.model_copy(update={"pii_detected": out.pii_detected or bool(state.get("pii_found")),
                                 "product_version": out.product_version or req.product_version})
    result: dict = {"classifier": out, "failures": failures}

    # Early exits: no retrieval, no further LLM calls.
    if out.type == "out_of_scope":
        result["early"] = "out_of_scope"
    elif "classify_llm_failed" not in failures and not out.asks_for_human and (
            out.needs_clarification or out.confidence < CLARIFY_MIN_CONFIDENCE):
        result["early"] = "clarification_needed"
    return result