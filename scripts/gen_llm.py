"""Text-generation client for the data generators (gen_kb.py, gen_accounts.py) with provider failover.

Owner: C

The app's runtime gateway is app/llm.py (A): schema-validated json_call().
Generators use their own order: GEN_LLM_ORDER (default groq,gemini; add ollama only if it runs locally).
Same env vars as app/llm.py for keys and models. All providers expose an OpenAI-compatible endpoint.
GEN_MOCK=true (or MOCK_LLM=true) generates deterministic content with no API calls.

Token discipline (free tiers are small: Groq qwen allows 1,000 output tokens/min):
  - every call sends max_tokens; without it Groq reserves the model's full output budget and
    rejects the request with 429 even when the minute is mostly unused
  - hidden reasoning is switched off (GROQ_REASONING_EFFORT / GEMINI_REASONING_EFFORT, default none):
    on Gemini 3.5 Flash it cut an article call from 2,603 to 623 tokens and still passed the fact check
  - a per-provider sliding 60 s budget: a call goes to the first provider with room right now
    (Groq -> Gemini), and only waits when none has room, instead of flooding the API into 429s
  - token usage is kept in USAGE and per call in last_call, for the generation log and data card
"""
import os
import re
import threading
import time
from collections import defaultdict, deque

import httpx

from app import config  # noqa: F401  (loads .env)

PROVIDERS = {
    # name: (base_url, api-key env var, model env var, default model)
    "groq":   (lambda: "https://api.groq.com/openai/v1", "GROQ_API_KEY", "GROQ_MODEL", "qwen/qwen3.8-27b"),
    "gemini": (lambda: "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
               "GEMINI_MODEL", "gemini-3.5-flash"),
    "ollama": (lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/v1", None,
               "OLLAMA_MODEL", "qwen2.5:7b-instruct"),
}
# per-minute budgets (free tier); override in .env if your account has higher limits
BUDGETS = {
    "groq": {"otpm": int(os.getenv("GROQ_OTPM", "1000")), "tpm": int(os.getenv("GROQ_TPM", "8000")),
             "rpm": int(os.getenv("GROQ_RPM", "30"))},
    "gemini": {"otpm": 0, "tpm": int(os.getenv("GEMINI_TPM", "250000")), "rpm": int(os.getenv("GEMINI_RPM", "10"))},
}
REASONING = {"groq": "GROQ_REASONING_EFFORT", "gemini": "GEMINI_REASONING_EFFORT"}

USAGE = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
last_call: dict = {}
_window: dict[str, deque] = defaultdict(deque)       # (timestamp, total_tokens, output_tokens)
_lock = threading.Lock()


class LLMUnavailable(RuntimeError):
    pass


def is_mock() -> bool:
    return any(os.getenv(v, "false").lower() in ("1", "true", "yes") for v in ("GEN_MOCK", "MOCK_LLM"))


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def _seconds_until_fits(name: str, prompt_tokens: int, max_tokens: int) -> float:
    """0 if this call fits the provider's rolling 60 s request/token budgets now, else seconds to wait."""
    b = BUDGETS.get(name)
    if not b:
        return 0.0
    with _lock:
        w, now = _window[name], time.time()
        while w and now - w[0][0] > 60:
            w.popleft()
        used_total = sum(t for _, t, _ in w)
        used_out = sum(o for _, _, o in w)
        fits = (len(w) < b["rpm"] and used_total + prompt_tokens + max_tokens <= b["tpm"]
                and (not b["otpm"] or used_out + max_tokens <= b["otpm"]))
        return 0.0 if fits or not w else 60 - (now - w[0][0]) + 0.5


def _wait_for_budget(name: str, prompt_tokens: int, max_tokens: int) -> None:
    while (wait := _seconds_until_fits(name, prompt_tokens, max_tokens)) > 0:
        time.sleep(wait)


def _configured(name: str) -> bool:
    _, key_env, _, _ = PROVIDERS[name]
    return not key_env or bool(os.getenv(key_env))


def _record(name: str, usage: dict, max_tokens: int) -> None:
    out = usage.get("completion_tokens", max_tokens)
    total = usage.get("total_tokens", out + usage.get("prompt_tokens", 0))
    with _lock:
        _window[name].append((time.time(), total, out))
        u = USAGE[name]
        u["calls"] += 1
        u["prompt_tokens"] += usage.get("prompt_tokens", 0)
        u["completion_tokens"] += out


def _retry_after(r: httpx.Response, attempt: int) -> float:
    if r.headers.get("retry-after"):
        return float(r.headers["retry-after"])
    m = re.search(r"try again in ([\d.]+)s", r.text)
    return float(m[1]) + 0.5 if m else 3 * 2 ** attempt


def chat(system: str, user: str, *, json_mode: bool = False, temperature: float = 0.4,
         max_tokens: int = 900) -> tuple[str, str]:
    """Return (text, "provider:model"). Raises LLMUnavailable if every provider fails."""
    errors = []
    order = [p.strip() for p in os.getenv("GEN_LLM_ORDER", "groq,gemini").split(",") if p.strip()]
    # route around a provider whose minute budget is used up instead of sleeping: the first provider
    # in GEN_LLM_ORDER that fits right now goes first; the rest stay as failover in their usual order
    prompt_est = estimate_tokens(system + user)
    ready = [p for p in order if _configured(p) and _seconds_until_fits(p, prompt_est, max_tokens) == 0]
    if ready:
        order = [ready[0]] + [p for p in order if p != ready[0]]
    for name in order:
        base, key_env, model_env, default_model = PROVIDERS[name]
        key = os.getenv(key_env) if key_env else "ollama"
        model = os.getenv(model_env) or default_model
        if not key:
            errors.append(f"{name}: no API key")
            continue
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        effort = os.getenv(REASONING.get(name, ""), "none") if name in REASONING else ""
        if effort:
            body["reasoning_effort"] = effort
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        for attempt in range(3):
            _wait_for_budget(name, prompt_est, max_tokens)
            try:
                r = httpx.post(f"{base()}/chat/completions", json=body, timeout=120,
                               headers={"Authorization": f"Bearer {key}"})
            except httpx.HTTPError as e:
                errors.append(f"{name}: {type(e).__name__}")
                break
            if r.status_code in (429, 503):          # rate limited / overloaded: wait, then retry once more
                _record(name, {"completion_tokens": 0, "total_tokens": 0}, 0)
                time.sleep(min(_retry_after(r, attempt), 65))
                continue
            if r.status_code == 400 and "reasoning_effort" in r.text and "reasoning_effort" in body:
                body.pop("reasoning_effort")        # model without a reasoning switch: retry without it
                continue
            try:
                r.raise_for_status()
                d = r.json()
                text = d["choices"][0]["message"]["content"] or ""
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                errors.append(f"{name}: {type(e).__name__}: {r.text[:120]}")
                break
            usage = d.get("usage") or {}
            _record(name, usage, max_tokens)
            last_call.clear()
            last_call.update(provider=name, model=model, prompt_tokens=usage.get("prompt_tokens"),
                             completion_tokens=usage.get("completion_tokens"),
                             finish_reason=d["choices"][0].get("finish_reason"))
            return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S), f"{name}:{model}"
        else:
            errors.append(f"{name}: rate limited after retries")
    raise LLMUnavailable("; ".join(errors))
