"""Text-generation client for the data generators (gen_kb.py, gen_accounts.py) with provider failover.

Owner: C

The app's runtime gateway is app/llm.py (A): schema-validated json_call(), Ollama first.
Generators need free-form Markdown and benefit from the strongest free model, so they use
their own order: GEN_LLM_ORDER (default groq,gemini,ollama). Same env vars as app/llm.py for keys,
models and OLLAMA_HOST. All three providers expose an OpenAI-compatible /chat/completions endpoint.
GEN_MOCK=true (or MOCK_LLM=true) generates deterministic content with no API calls.
"""
import os
import time

import httpx

from app import config  # noqa: F401  (loads .env)

PROVIDERS = {
    # name: (base_url, api-key env var, model env var, default model)
    "groq":   (lambda: "https://api.groq.com/openai/v1", "GROQ_API_KEY", "GROQ_MODEL", "llama-3.1-8b-instant"),
    "gemini": (lambda: "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
               "GEMINI_MODEL", "gemini-1.5-flash"),
    "ollama": (lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/v1", None,
               "OLLAMA_MODEL", "qwen2.5:7b-instruct"),
}


class LLMUnavailable(RuntimeError):
    pass


def is_mock() -> bool:
    return any(os.getenv(v, "false").lower() in ("1", "true", "yes") for v in ("GEN_MOCK", "MOCK_LLM"))


def chat(system: str, user: str, *, json_mode: bool = False, temperature: float = 0.4) -> tuple[str, str]:
    """Return (text, "provider:model"). Raises LLMUnavailable if every provider fails."""
    errors = []
    for name in [p.strip() for p in os.getenv("GEN_LLM_ORDER", "groq,gemini,ollama").split(",") if p.strip()]:
        base, key_env, model_env, default_model = PROVIDERS[name]
        key = os.getenv(key_env) if key_env else "ollama"
        model = os.getenv(model_env) or default_model
        if not key:
            errors.append(f"{name}: no API key")
            continue
        body = {"model": model, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        for attempt in range(3):
            try:
                r = httpx.post(f"{base()}/chat/completions", json=body, timeout=120,
                               headers={"Authorization": f"Bearer {key}"})
                if r.status_code == 429:               # free tiers: back off, then try again
                    time.sleep(float(r.headers.get("retry-after", 2 ** attempt * 3)))
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"], f"{name}:{model}"
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                errors.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
                break
        else:
            errors.append(f"{name}: rate limited after retries")
    raise LLMUnavailable("; ".join(errors))
