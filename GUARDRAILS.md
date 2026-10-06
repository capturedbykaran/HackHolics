# Guardrails

Three layers around the LangGraph pipeline, plain Python + regex (no external guardrail service).
Code lives in `app/guardrails/`; every regex and phrase list is in `patterns.py`.
**Guardrails can only make a decision stricter, never more lenient.**

Every decision is appended to `state["guardrail_events"]` as
`{layer, check, action, detail}` (no raw PII in `detail`), stored in the audit record, never sent to the customer.

| Check | Layer | File | Action | Requirement |
|---|---|---|---|---|
| Empty / whitespace-only message | input | `input_guard.check_input` | clarification template | - |
| Length cap (4000 chars) | input | `input_guard.check_input` | truncate + flag | - |
| PII and secret redaction: email, phone (intl, Indian, US), card (Luhn-validated), Aadhaar, PAN, API key, Bearer/token, password | input | `input_guard.redact_text` | redact to typed tags (`[EMAIL]`, `[CARD]`, ...) | R7 |
| Other account's id in the message or conversation | input | `input_guard.check_input`, `graph.load_history` | refuse (template, no LLM call) | R8 |
| Request to show a password / token / API key / reset link | input | `input_guard.check_input` | refuse (template) | R9 |
| Password reset request | input | `input_guard.check_input` + `classify` | `send_password_reset` tool runs; link is never shown | R9 |
| Prompt-injection phrases, fake role tags | input | `input_guard.detect_injection` | flag (`injection_suspected`) + neutralise delimiters; pipeline continues | R10 |
| Abusive language | input | `input_guard.check_input` | flag signal; sentiment raised to at least "frustrated" | - |
| Retrieved chunk contains instructions for the assistant | processing | `processing_guard.sanitize_chunks` (gather node) | drop chunk | R10 |
| PII inside retrieved chunks | processing | `processing_guard.sanitize_chunks` | redact | R7 |
| Suspicious document at ingest | processing | `ingest.flag_suspicious` | store with `suspicious=true` | R10 |
| Tool allowlist (only `schemas.ToolName`, read-only) | processing | `processing_guard.plan_tools`, `tools.run_tool` | block | R8 |
| `account_id` only from the signed-in header; prospects run no account tools | processing | `processing_guard.plan_tools`, `tools.run_tool` | block | R8 |
| `send_password_reset` returns only `{"sent": true}` | processing | `tools.send_password_reset` | by construction | R9 |
| Customer text, history, sources, tool results are DATA inside escaped delimiters | processing | `processing_guard.wrap_data` / `escape_tags` | escape | R10 |
| `<think>` blocks removed before JSON parsing; Pydantic validation, 2 retries, timeout, safe default | processing | `llm._parse`, `llm.json_call` | strip / retry / escalate | - |
| Invented citations dropped; no valid citation and no tool evidence -> cannot answer | processing | `compose._validate_citations` | drop / not_found | - |
| One revision max, explicit graph recursion limit | processing | `graph.MAX_REVISIONS`, `graph.RECURSION_LIMIT` | stop / escalate | - |
| PII or secret in the draft | output | `output_guard.check_output` (critic, finalize) | revise, then escalate | R7, R9 |
| Reset / verification link or token in the draft | output | `output_guard.check_output` | revise, then escalate | R9 |
| Refund / credit / discount promise | output | `output_guard.check_output` | revise, then escalate | - |
| Claim that an account change was made | output | `output_guard.check_output` | revise, then escalate | - |
| Account id other than the requester's | output | `output_guard.check_output` | revise, then escalate | R8 |
| System-prompt fragments, chain-of-thought markers | output | `output_guard.check_output` | revise, then escalate | R10 |
| URL not present in the retrieved sources | output | `output_guard.check_output` | revise, then escalate | - |
| Final pass on every outgoing field (answer, tool outputs, conflicts), answer capped at 1500 chars | output | `output_guard.sanitize_response` (finalize) | redact / strip / cap | R7 |
| Handoff bundle and audit record cleaned; an unsafe draft is withheld, not stored | output | `sanitize_bundle`, `sanitize_audit_state` | redact / withhold | R7 |
| Log records redacted (message, args, tracebacks) | output | `log_filter.install_log_filter` (`app/__init__.py`) | redact | R7 |

Tests: `tests/test_guardrails.py` (unit tests per function + the red-team runner) and
`tests/redteam_cases.jsonl` (28 cases, reusable by the eval set).
