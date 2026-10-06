"""LLM gateway: provider order, retries with error feedback, mock. Owner: A."""
import httpx
import pytest

from app import llm
from app.schemas import ClassifierOut


def test_ollama_first_and_cloud_only_when_opted_in_with_keys(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")  # cannot jump the queue
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_FALLBACK", "none")
    assert llm.provider_chain() == ["ollama"]
    monkeypatch.setenv("LLM_FALLBACK", "cloud")
    assert llm.provider_chain() == ["ollama", "groq"]


def test_invalid_json_is_retried_with_error_feedback_then_next_provider(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_FALLBACK", "cloud")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    prompts: list[str] = []

    def bad_ollama(system, user, schema, temperature):
        prompts.append(user)
        return '{"type": "nonsense"}', "m", 1

    def good_groq(system, user, schema, temperature):
        return '{"type": "how_to"}', "g", 1

    monkeypatch.setitem(llm._PROVIDERS, "ollama", bad_ollama)
    monkeypatch.setitem(llm._PROVIDERS, "groq", good_groq)
    log = llm.start_call_log()
    out = llm.json_call("sys", "msg", ClassifierOut, node="classify")
    assert out.type == "how_to"
    assert len(prompts) == llm.MAX_RETRIES + 1
    assert "not valid for the schema" in prompts[1] and "type" in prompts[1]
    assert log[-1]["provider"] == "groq" and log[-1]["node"] == "classify"


def test_all_providers_down_raises_llm_error(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_FALLBACK", "none")

    def down(*a):
        raise httpx.ConnectError("down")

    monkeypatch.setitem(llm._PROVIDERS, "ollama", down)
    with pytest.raises(llm.LLMError):
        llm.json_call("sys", "msg", ClassifierOut)


def test_mock_follow_up_uses_last_user_turn():
    state = {"redacted_message": "it still fails",
             "history": [{"role": "user", "text": "Error CF-503 in my workflow"},
                         {"role": "assistant", "text": "..."}]}
    out = llm.json_call("", "", ClassifierOut, state)
    assert out.is_follow_up and "CF-503" in out.standalone_question
    assert out.type == "troubleshooting"
