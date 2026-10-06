"""LLM gateway. Owner: A.
 
json_call() is the ONLY way the app talks to a model.
  * MOCK_LLM=true         -> deterministic fake output per schema (no model needed)
  * default provider      -> Ollama (local), as the brief requires
  * LLM_FALLBACK=cloud    -> then Groq, then Gemini (only if keys exist). Disclose in README.
  * every provider call   -> validated with Pydantic, retried on invalid JSON, then next provider
"""
import contextvars
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional
 
import httpx
from pydantic import BaseModel
 
from app.guardrails.processing_guard import strip_reasoning
from app.schemas import ClassifierOut, ComposerCitation, ComposerOut, CriticOut
 
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
 
 
class LLMError(RuntimeError):
    """All providers failed or returned invalid output."""
 
 
# ------------------------------------------------------------- call log
# One list per request; finalize reads it for the audit record (model, tokens, latency).
_CALL_LOG: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar("llm_call_log", default=None)
 
 
def start_call_log() -> list:
    log: list = []
    _CALL_LOG.set(log)
    return log
 
 
def get_call_log() -> list:
    return _CALL_LOG.get() or []
 
 
def _log(node: str, provider: str, model: str, tokens: int, t0: float, retries: int) -> None:
    log = _CALL_LOG.get()
    if log is not None:
        log.append({"node": node, "provider": provider, "model": model, "tokens": tokens,
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "retries": retries})
 
 
# ------------------------------------------------------------- prompts
def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")
 
 
def render(template: str, **kw: Any) -> str:
    """Single-pass {placeholder} substitution (safe for templates containing JSON braces)."""
    return re.sub(r"\{(\w+)\}", lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), template)
 
 
# ------------------------------------------------------------- config
def mock_enabled() -> bool:
    return os.getenv("MOCK_LLM", "false").lower() in ("1", "true", "yes")
 
 
def provider_chain() -> list[str]:
    chain = ["ollama"]  # always first (brief); cloud only as an opt-in fallback
    if os.getenv("LLM_FALLBACK", "none").lower() == "cloud":
        for p, key in (("groq", "GROQ_API_KEY"), ("gemini", "GEMINI_API_KEY")):
            if p not in chain and os.getenv(key):
                chain.append(p)
    return chain
 
 
def _timeout() -> float:
    return float(os.getenv("LLM_TIMEOUT", "60"))
 
 
# ------------------------------------------------------------- providers
# Each returns (raw_text, model_name, total_tokens). Raise httpx.HTTPError / KeyError if the provider is down.
def _ollama(system: str, user: str, schema: type[BaseModel], temperature: float):
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    r = httpx.post(f"{host}/api/chat", timeout=_timeout(), json={
        "model": model, "stream": False,
        "format": schema.model_json_schema(),  # structured output
        "options": {"temperature": temperature},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    r.raise_for_status()
    d = r.json()
    return d["message"]["content"], model, d.get("prompt_eval_count", 0) + d.get("eval_count", 0)
 
 
def _groq(system: str, user: str, schema: type[BaseModel], temperature: float):
    model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    body = {"model": model, "temperature": temperature,
            # without max_tokens Groq reserves the model's full output budget and returns 429
            # on free tiers (qwen: 1,000 output tokens/min) even when the minute is mostly unused
            "max_tokens": _max_out(schema),
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    if os.getenv("GROQ_REASONING_EFFORT", "none"):  # hidden reasoning tokens count as output; "" = model default
        body["reasoning_effort"] = os.getenv("GROQ_REASONING_EFFORT", "none")
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=_timeout(),
                   headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}, json=body)
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], model, d.get("usage", {}).get("total_tokens", 0)
 
 
def _gemini(system: str, user: str, schema: type[BaseModel], temperature: float):
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                   timeout=_timeout(), headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                   json={"systemInstruction": {"parts": [{"text": system}]},
                         "contents": [{"role": "user", "parts": [{"text": user}]}],
                         "generationConfig": {"temperature": temperature,
                                              "responseMimeType": "application/json",
                                              "maxOutputTokens": _max_out(schema),
                                              # thinking off: same JSON, ~4x fewer tokens on Flash
                                              "thinkingConfig": {"thinkingBudget":
                                                                 int(os.getenv("GEMINI_THINKING_BUDGET", "0"))}}})
    r.raise_for_status()
    d = r.json()
    return (d["candidates"][0]["content"]["parts"][0]["text"], model,
            d.get("usageMetadata", {}).get("totalTokenCount", 0))
 
 
_PROVIDERS = {"ollama": _ollama, "groq": _groq, "gemini": _gemini}

# output cap per node schema (tokens): generous for the JSON each node returns, small enough for free tiers
MAX_OUTPUT = {"ClassifierOut": 300, "ComposerOut": 800, "CriticOut": 400}


def _max_out(schema: type[BaseModel]) -> int:
    return MAX_OUTPUT.get(schema.__name__, int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "600")))


def _schema_hint(schema: type[BaseModel]) -> str:
    """Compact field list ({"type": "a|b", "tools": ["x|y"], ...}) instead of the full JSON schema:
    same information for the model at well under half the input tokens. Pydantic still validates."""
    full = schema.model_json_schema()
    defs = full.get("$defs", {})

    def shape(p: dict):
        if "$ref" in p:
            return shape(defs[p["$ref"].split("/")[-1]])
        if "enum" in p:
            return "|".join(map(str, p["enum"]))
        if "anyOf" in p:
            return "|".join(str(shape(x)) for x in p["anyOf"])
        if p.get("type") == "array":
            return [shape(p.get("items", {}))]
        if p.get("type") == "object" and "properties" in p:
            return {k: shape(v) for k, v in p["properties"].items()}
        return {"integer": "int", "number": "float", "boolean": "bool"}.get(p.get("type"), p.get("type", "any"))

    return json.dumps(shape(full), separators=(",", ":"))
 
 
# ------------------------------------------------------------- parsing
def _parse(text: str, schema: type[BaseModel]) -> BaseModel:
    text = strip_reasoning(text)  # some local models emit <think>...</think> before the JSON
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # strip markdown fences
    try:
        return schema.model_validate_json(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)  # last resort: first {...} block
        if not m:
            raise
        return schema.model_validate_json(m.group(0))
 
 
# ------------------------------------------------------------- public API
def json_call(system: str, user: str, schema: type[BaseModel], state: Optional[dict] = None,
              *, node: str = "", temperature: float = 0.0) -> BaseModel:
    """Call the LLM and return a validated `schema` instance. Raises LLMError if everything fails."""
    t0 = time.perf_counter()
    if mock_enabled():
        out = _mock(schema, state or {})
        _log(node, "mock", "mock", 0, t0, 0)
        return out
 
    system_full = (system + "\n\nReturn ONLY one JSON object with these keys (no prose, no markdown):\n"
                   + _schema_hint(schema))
    errors: list[str] = []
    for provider in provider_chain():
        fn = _PROVIDERS.get(provider)
        if fn is None:
            errors.append(f"{provider}: unknown provider")
            continue
        prompt = user
        for attempt in range(MAX_RETRIES + 1):
            try:
                text, model, tokens = fn(system_full, prompt, schema, temperature)
                out = _parse(text, schema)
                _log(node, provider, model, tokens, t0, attempt)
                return out
            except ValueError as e:  # bad JSON / schema violation -> retry with feedback
                errors.append(f"{provider} attempt {attempt}: invalid output ({str(e)[:120]})")
                prompt = (user + "\n\nYour previous reply was not valid for the schema "
                          f"({str(e)[:300]}). Reply with ONLY the corrected JSON object.")
            except (httpx.HTTPError, KeyError, IndexError, TypeError) as e:  # provider down -> next one
                errors.append(f"{provider}: {type(e).__name__} {str(e)[:120]}")
                break
    raise LLMError("; ".join(errors) or "no provider available")
 
 
# ------------------------------------------------------------- mock mode
def _mock(schema: type[BaseModel], state: dict) -> BaseModel:
    """Deterministic fake outputs so routing, tools and escalation can be tested without a model."""
    if schema is ClassifierOut:
        return _mock_classifier(state)
    if schema is ComposerOut:
        return _mock_composer(state)
    if schema is CriticOut:
        return _mock_critic(state)
    raise LLMError(f"no mock for {schema.__name__}")
 
 
_FOLLOW_UP = re.compile(r"^\s*(and|also)\b|\bwhat about\b|\bstill\b|\bsame (error|issue|thing)\b", re.I)
_MOCK_VERSION = re.compile(r"\b(\d+\.(?:\d+|x))\b")


_MOCK_TOPICS = {  # keyword rules for escalation_topics (informational "refund policy" questions are excluded)
    "refund": re.compile(r"\brefund(?!\s+(?:policy|policies|window|terms|eligibility))|\bmoney back\b"),
    "credit": re.compile(r"\bcredits?\b(?!\s+card)"),
    "billing_dispute": re.compile(r"\bcharged (?:me )?twice\b|\bdouble[- ]charged?\b|\bchargeback\b|\bdispute\b"),
    "legal": re.compile(r"\blawyer\b|\blegal action\b|\bsue\b|\blawsuit\b"),
    "security_incident": re.compile(r"\bhacked\b|\bunauthori[sz]ed\b|\blogged into my account\b|\bleaked\b"),
    "account_deletion": re.compile(r"\b(?:delete|close) my account\b"),
}


def _mock_topics(m: str) -> list[str]:
    return [topic for topic, rx in _MOCK_TOPICS.items() if rx.search(m)]


def _mock_classifier(state: dict) -> ClassifierOut:
    raw = state.get("redacted_message") or ""
    last_user = next((t["text"] for t in reversed(state.get("history") or []) if t.get("role") == "user"), "")
    follow = dict(is_follow_up=False, standalone_question="")
    if last_user and _FOLLOW_UP.search(raw):
        follow = dict(is_follow_up=True, standalone_question=f"{last_user} (follow-up: {raw})")
    version = _MOCK_VERSION.search(raw)  # only what THIS message states; classify inherits the rest
    m = (follow["standalone_question"] or raw).lower()
    c = dict(type="how_to", urgency="low", sentiment="neutral", confidence=0.9,
             product_version=version.group(1) if version else None, **follow)
    if any(w in m for w in ("poem", "weather", "recipe", "joke")):
        c.update(type="out_of_scope")
    elif len(m.split()) <= 4 and ("not working" in m or "broken" in m or "help" in m):
        c.update(type="troubleshooting", needs_clarification=True, confidence=0.3)
    elif any(w in m for w in ("password", "hacked", "leaked", "security")):
        c.update(type="security", urgency="high", tools_needed=["lookup_account"])
    elif any(w in m for w in ("refund", "charged", "invoice", "billing", "credit")):
        c.update(type="billing", urgency="normal", tools_needed=["get_invoices", "check_refund_eligibility"])
    elif any(w in m for w in ("429", "rate limit", "api calls", "usage")):
        c.update(type="account", tools_needed=["get_usage", "get_plan_limits"])
    elif any(w in m for w in ("error", "fails", "failing", "cf-")):
        c.update(type="troubleshooting")
    topics = _mock_topics(m)
    if topics:
        c.update(escalation_topics=topics, needs_outcome=True)
    if c["type"] == "security" and any(w in m for w in ("reset", "forgot", "link", "locked out")):
        c.update(needs_outcome=True)
    if any(w in raw.lower() for w in ("ridiculous", "unacceptable", "furious", "fed up")):
        c.update(sentiment="angry", urgency="high")
    if any(w in m for w in ("manager", "human", "third time", "real person")):
        c.update(asks_for_human=True, sentiment="angry", urgency="high")
    return ClassifierOut(pii_detected=bool(state.get("pii_found")), **c)
 
 
def _mock_composer(state: dict) -> ComposerOut:
    chunks = state.get("chunks") or []
    cls = state.get("classifier")
    needed = set(cls.tools_needed) if cls else set()
    tools = [t for t in (state.get("tool_results") or []) if t.ok and t.tool in needed]
    if chunks:
        c = chunks[0]
        cite = [ComposerCitation(source_id=c.source_id, section=c.section)]
        safe = f"According to {c.source_id} ({c.section}): {c.text[:200]}"
        unsafe = _mock_unsafe(state, safe)
        if unsafe:
            return ComposerOut(answer=unsafe, citations=cite)
        return ComposerOut(answer=safe, citations=cite)
    if tools:
        return ComposerOut(answer="Based on your account data: " + json.dumps(tools[0].output)[:200],
                           citations=[])
    return ComposerOut(answer="", can_answer=False, missing_info=["no supporting source found"])
 
 
# Trigger words in the customer message make the mock composer return an unsafe draft, to exercise the
# output guardrails. "promise" and "claim" stay unsafe on the revision too; the others are fixed by it.
_UNSAFE_DRAFTS = {
    "promise": ("I've refunded you for this month. ", True),
    "claim": ("I've upgraded your plan to Business. ", True),
    "think": ("<think>let me check the sources first</think> ", False),
    "url": ("See https://evil.example/phish for details. ", False),
    "pii": ("Contact jane.doe@acme.io for the export. ", False),
    "prompt": ("RULES: 1. Use ONLY the SOURCES. ", False),
}


def _mock_unsafe(state: dict, safe: str) -> Optional[str]:
    m = (state.get("redacted_message") or "").lower()
    first_pass = state.get("critic") is None
    for kind, (text, persistent) in _UNSAFE_DRAFTS.items():
        if f"[mock-unsafe:{kind}]" in m and (persistent or first_pass):
            return text + safe
    return None


def _mock_critic(state: dict) -> CriticOut:
    draft = state.get("draft")
    msg = (state.get("redacted_message") or "").lower()
    if draft is None or not draft.can_answer:
        return CriticOut(groundedness=0.2, coverage="none", recommendation="escalate",
                         issues=["no grounded draft"])
    if "[mock-revise]" in msg and state.get("revisions", 0) == 0:  # exercises the revise loop
        return CriticOut(groundedness=0.5, coverage="partial", recommendation="revise",
                         issues=["claim in step 2 is not supported by the cited section"])
    return CriticOut(groundedness=0.9, coverage="complete", recommendation="answer")
 