# CLAUDE.md

> Owner: A

Shared rules for Claude Code sessions on this repo (InsightDesk, HCLTech hackathon use case 2).

## Rules
- Respect file ownership in `TEAM.md`; don't edit another owner's files without asking.
- Files whose docstring starts with `STUB (owner: X)` are placeholders so the graph runs end to end.
  Others may only add/adjust a signature they need; the owner replaces the body.
- `app/schemas.py` is the shared contract; change it only via A, additive changes only.
- Run tests with `MOCK_LLM=true python -m pytest -q` (no model needed).
- Annex C tables/columns in `app/db.py` are fixed: never rename or remove them.
- No new agents, web search or dependencies without the team agreeing.

## Pipeline
LangGraph, 7 nodes: guard -> classify -> gather -> compose -> critic -> decide -> finalize.
LLM only in classify, compose, critic via `llm.json_call()` (Ollama first; Groq/Gemini only with
`LLM_FALLBACK=cloud` and a key). Prompts are system text; customer text, history, sources and tool
results go in the user message as DATA. Every refusal/clarification/not-found/escalation text is a
template in `finalize.py`.

## Contracts
- `graph.run_support(req: SupportRequest, account_id: str | None) -> SupportResponse`
  (`account_id` None = no account header = prospect).
- `segment.segment_user(account_id, as_of_date, registry) -> (segment, account_info_without_pii)`,
  decided in code: `prospect` | `new_customer` (registry `new_customer_days`, default 30) |
  `existing_customer` | `former_customer` (cancelled). Uses `tools.run_tool("lookup_account")` only.
- `customer_segment` is in GraphState, the audit record, `SupportResponse` and `HandoffBundle`.
- Prospects: gather never runs account tools; account/billing/security questions or any tool need
  -> `refused` (`early_reason="sign_in_required"`).
- `audit.get_conversation(conversation_id, limit=6) -> list[dict]`, oldest first, `limit <= 0` = all:
  `{role, account_id, message|answer, answer_type, intent, trace_id, created_at}`.
- `audit.append_conversation(conversation_id, role, payload)`: payload always carries `account_id`,
  `trace_id`, `intent`, plus `message` (user) or `answer` + `answer_type` (assistant). Stored text is
  PII-redacted.
- A conversation is bound to one account: if any stored turn has a different `account_id`,
  run_support refuses (`early_reason="other_account"`) with no LLM call and writes nothing into it.
- State memory fields: `history` (last 6 turns, 300 chars each), `prior_user_turns`,
  `prior_escalations`. `ClassifierOut.is_follow_up` / `standalone_question`; empty version is
  inherited from earlier turns.
- gather search query = `classifier.standalone_question or redacted_message`.
- `state.signals: list[str]`, e.g. `"repeated_contact"` (prior_user_turns >= 2 and frustrated/angry,
  or prior_escalations >= 1). Set by classify; `escalation.decide()` (B) makes the decision.
- `escalation.decide(state, registry) -> Decision` (see Node 6 below); `tools.run_tool(name, account_id=..., **kw) -> ToolResult`
  (never raises); `tools.create_handoff(bundle) -> handoff_id`; `guard.redact(text) -> (text, found)`;
  `retrieval.search(query, k, version, as_of) -> list[Chunk]`; `db.load_registry() -> {parameter: value}`.

## Guardrails
Three layers in `app/guardrails/` (all regexes and phrase lists in `patterns.py`; table in `GUARDRAILS.md`):
- **Input** (`input_guard.check_input`, called by `nodes/guard.py`): empty/length cap, PII + secret redaction
  (typed tags, Luhn-checked cards), other-account refusal (R8), secret requests (R9), injection detection and
  delimiter neutralisation (R10), abusive language. Returns `InputVerdict`.
- **Processing** (`processing_guard`): `sanitize_chunks` (gather node), `plan_tools` + `tools.run_tool` allowlist
  (account id only from the header; prospects run no account tools), `wrap_data`/`escape_tags` for every prompt,
  `strip_reasoning` for `<think>` blocks (used by `llm._parse`).
- **Output** (`output_guard`): `check_output` (critic and finalize), `sanitize_response`, `sanitize_bundle`,
  `sanitize_audit_state`; `log_filter.install_log_filter()` runs on `import app`.

Rules:
- **Guardrails can only make decisions stricter, never more lenient.** They may revise, escalate, refuse, drop or
  redact; they never turn an escalation into an answer or lower a risk score.
- Every decision appends `{layer, check, action, detail}` to `state["guardrail_events"]` (no raw PII in `detail`).
  Events go to the audit record, never to the customer response. Nodes must copy the existing list, not replace it.
- `guard.redact(text) -> (text, found)` and `guard.requested_other_account` stay as a thin compatibility layer.
- New regexes go in `patterns.py`; add a red-team case to `tests/redteam_cases.jsonl` for every new check.
- `tools.run_tool` accepts only `schemas.ToolName` (7 read-only tools); `send_password_reset` returns `{"sent": true}`.
- The mock composer returns an unsafe draft when the message contains `[mock-unsafe:promise|claim|think|url|pii|prompt]`.

## Node 6: decide (code only, no LLM)
- `escalation.decide(state, registry)` is pure and deterministic; `nodes/decide.py` loads the registry with
  `policy.load_policy(as_of_date, plan)` (plan from the `lookup_account` tool result) and never raises
  (crash -> `Decision("escalate", ["decide_error"])`). Result goes to `state["decision"]` and the rule ids to
  `state["policy_rules_applied"]`.
- Thresholds come from `policy_registry` (latest `effective_from` <= as_of_date, scope ALL or the plan); missing
  rows fall back to `policy.DEFAULTS` with rule_id `DEFAULT-<parameter>`. Parameters: `critic_min_groundedness`,
  `max_revisions`, `repeat_contact_threshold`, `negative_sentiments`, `escalate_topics`. `policy.SEED_ROWS` has the
  rows for the seed (source `KB-POL-002`, placeholders until C links the real article).
- `ClassifierOut.escalation_topics` (refund, credit, billing_dispute, legal, security_incident, account_deletion)
  and `needs_outcome` feed the policy; a keyword backstop on the redacted message covers classifier misses.
- Order: a) failures (R4) b) topics (R2, not for prospects) c) human request / negative sentiment + repeated
  contact (R3) d) unresolved conflict (A.2.5). Any match -> escalate with ALL reasons. Then e) KB gap (R5):
  needs_outcome (or no-draft intents security/complaint) -> escalate, else not_found. f) critic (R1): weak and
  revisions < max_revisions -> revise, else escalate. g) answer.
- Precedence convention: `precedence.resolve(chunks) -> list[str]`; an entry starting with `unresolved:` is
  Annex A.2 step 5. `gather` copies those into `state["unresolved_conflicts"]` and the chunks they name into
  `state["conflict_sources"]`; every entry stays in `state["conflicts"]`.
- Reason codes: tool_failure, required_step_failed, refund_request, credit_request, billing_dispute, legal_matter,
  security_incident, account_deletion, explicit_human_request, repeated_contact, strong_negative_sentiment,
  unresolved_conflict, kb_gap_needs_outcome, no_critic_result, classifier_missing, low_groundedness_after_revision,
  policy_risk_after_revision, pii_risk_after_revision, critic_rejected_after_revision (revise reasons start with
  critic_below_threshold; not_found uses kb_gap). finalize.py appends output_guardrail_<code> and revision_limit_reached.
