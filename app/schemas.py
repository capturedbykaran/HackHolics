"""All Pydantic models (shared contract).

Owner: A
"""



"""Shared Pydantic models + graph state. Owner: A. After M1, additive changes only."""
from typing import Any, Literal, Optional, TypedDict
 
from pydantic import BaseModel, Field
 
Intent = Literal["how_to", "troubleshooting", "account", "billing",
                 "complaint", "security", "out_of_scope"]
ToolName = Literal["lookup_account", "get_usage", "get_plan_limits", "get_invoices",
                   "check_refund_eligibility", "check_platform_status",
                   "send_password_reset"]
AnswerType = Literal["answered", "clarification_needed", "escalated",
                     "not_found", "refused", "out_of_scope"]
 
 
# ---------------------------------------------------------------- API in
class SupportRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    channel: Optional[str] = None
    product_version: Optional[str] = None
    as_of_date: Optional[str] = None  # YYYY-MM-DD, defaults to today
 
 
# ------------------------------------------------------ LLM output schemas
class ClassifierOut(BaseModel):  # LLM call 1
    type: Intent
    urgency: Literal["low", "normal", "high", "urgent"] = "normal"
    sentiment: Literal["positive", "neutral", "frustrated", "angry"] = "neutral"
    product_version: Optional[str] = None
    pii_detected: bool = False
    tools_needed: list[ToolName] = []
    asks_for_human: bool = False
    needs_clarification: bool = False
    confidence: float = Field(default=0.5, ge=0, le=1)
    # conversation memory (additive)
    # escalation policy inputs (Annex A.3); decided by code in node 6, only reported here
    escalation_topics: list[Literal["refund", "credit", "billing_dispute", "legal",
                                    "security_incident", "account_deletion"]] = []
    needs_outcome: bool = False  # customer needs an action/decision, not just information
    is_follow_up: bool = False
    standalone_question: str = ""  # follow-up rewritten as a complete question; "" if not a follow-up
 
 
class ComposerCitation(BaseModel):
    source_id: str
    section: str
 
 
class ComposerOut(BaseModel):  # LLM call 2
    answer: str
    citations: list[ComposerCitation] = []
    can_answer: bool = True
    missing_info: list[str] = []
 
 
class CriticOut(BaseModel):  # LLM call 3
    groundedness: float = Field(ge=0, le=1)
    coverage: Literal["complete", "partial", "none"]
    pii_risk: Literal["none", "low", "high"] = "none"
    policy_risk: Literal["none", "low", "high"] = "none"
    recommendation: Literal["answer", "revise", "escalate"]
    issues: list[str] = []
 
 
# ------------------------------------------------------ deterministic models
class Chunk(BaseModel):
    text: str
    source_id: str
    section: str = ""
    doc_type: Literal["article", "policy", "release_note", "ticket", "community"] = "article"
    authority_level: int = Field(default=1, ge=1, le=5)
    product_versions: str = ""
    last_updated: str = ""
    effective_from: Optional[str] = None
    deprecated_on: Optional[str] = None
    supersedes: list[str] = []
    score: float = 0.0
    suspicious: bool = False  # set at ingest when the text looks like instructions for the assistant
 
 
class Citation(BaseModel):
    source_id: str
    doc_type: str
    section: str
    product_versions: str
    last_updated: str
 
 
class ToolResult(BaseModel):
    tool: str
    ok: bool = True
    output: dict[str, Any] = {}
    error: Optional[str] = None
 
 
class Decision(BaseModel):
    action: Literal["answer", "revise", "escalate", "not_found"]
    reasons: list[str] = []
    rule_ids: list[str] = []
 
 
class HandoffBundle(BaseModel):  # Annex D (+ ids needed for the handoffs table)
    queue: Literal["billing", "technical", "security", "general"]
    priority: Literal["low", "normal", "high", "urgent"]
    intent: str
    urgency: str
    sentiment: str
    escalation_reasons: list[str]
    customer_summary: str
    evidence: list[dict[str, Any]] = []
    attempted_answer: Optional[str] = None
    unresolved_questions: list[str] = []
    pii_redacted: bool = True
    account_id: Optional[str] = None
    conversation_id: Optional[str] = None
    trace_id: Optional[str] = None
    customer_segment: str = ""  # prospect | new_customer | existing_customer | former_customer
 
 
class SourceMeta(BaseModel):  # Annex B, metadata of POST /ingest
    source_id: str
    doc_type: str
    title: str
    authority_level: int
    product_versions: str
    last_updated: str
    effective_from: Optional[str] = None
    deprecated_on: Optional[str] = None
    supersedes: Optional[str] = None  # "KB-API-009;KB-API-010"
    provenance: str = ""
    synthetic: Literal["Y", "N"] = "Y"
 
 
# ----------------------------------------------------------- API out (6.1)
class SupportResponse(BaseModel):
    trace_id: str
    conversation_id: str
    answer_type: AnswerType
    answer: str
    intent: ClassifierOut
    citations: list[Citation] = []
    tools_invoked: list[ToolResult] = []
    critic: Optional[dict[str, Any]] = None
    conflicts_detected: list[str] = []
    handoff_id: Optional[str] = None
    as_of_date: str
    customer_segment: str = ""
 
 
# ------------------------------------------------------------ graph state
class GraphState(TypedDict, total=False):
    # inputs
    req: SupportRequest
    account_id: Optional[str]     # None for prospects (no account header)
    trace_id: str
    conversation_id: str
    as_of_date: str
    customer_segment: str         # app/segment.py, decided in code
    # conversation memory (loaded by run_support, PII-redacted, max 6 turns x 300 chars)
    history: list[dict[str, Any]]
    prior_user_turns: int
    prior_escalations: int
    history_denied: bool          # conversation belongs to another account -> do not log this turn
    guardrail_events: list[dict[str, str]]  # {layer, check, action, detail}; audit only, never in the response
    unresolved_conflicts: list[str]   # A.2 step 5: "unresolved: KB-API-014 vs TKT-2025-0311 on ..."
    conflict_sources: list[Chunk]     # chunks involved in an unresolved conflict (both go to the handoff)
    policy_rules_applied: list[str]   # policy_registry rule_ids behind the decision
    signals: list[str]            # e.g. "repeated_contact"; read by escalation.decide()
    # guard
    redacted_message: str
    pii_found: bool
    early: Optional[str]          # "refused" | "clarification_needed" | "out_of_scope"
    early_reason: Optional[str]
    # classify / gather
    classifier: Optional[ClassifierOut]
    version: Optional[str]
    chunks: list[Chunk]
    upcoming: list[Chunk]
    conflicts: list[str]
    tool_results: list[ToolResult]
    # compose / critic / decide
    draft: Optional[ComposerOut]
    critic: Optional[CriticOut]
    revisions: int                # max 1
    decision: Optional[Decision]
    # output + audit
    response: Optional[SupportResponse]
    failures: list[str]           # e.g. "classify_llm_failed", "tool_failed:get_invoices"
    latency_ms: dict[str, float]
    llm_calls: list[dict[str, Any]]
    model: str
    tokens: int
 