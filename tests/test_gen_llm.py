"""Generator LLM client: token caps, reasoning off, budget routing, 429 handling. No network.

Owner: C
"""
import importlib

import httpx
import pytest


class FakeResp:
    def __init__(self, status=200, content="ok", usage=None, headers=None, text=""):
        self.status_code, self.headers, self.text = status, headers or {}, text
        self._json = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                      "usage": usage or {"prompt_tokens": 100, "completion_tokens": 400, "total_tokens": 500}}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


@pytest.fixture
def gl(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("GEN_LLM_ORDER", "groq,gemini")
    from scripts import gen_llm
    importlib.reload(gen_llm)
    monkeypatch.setattr(gen_llm.time, "sleep", lambda s: None)
    return gen_llm


def capture(monkeypatch, gl, responses):
    sent = []

    def post(url, json, timeout, headers):
        sent.append((url, dict(json)))
        return responses.pop(0) if responses else FakeResp()
    monkeypatch.setattr(gl.httpx, "post", post)
    return sent


def test_every_call_caps_output_and_turns_reasoning_off(gl, monkeypatch):
    sent = capture(monkeypatch, gl, [])
    text, who = gl.chat("s", "u", max_tokens=700)
    assert who.startswith("groq:") and sent[0][1]["max_tokens"] == 700
    assert sent[0][1]["reasoning_effort"] == "none"
    assert gl.USAGE["groq"]["completion_tokens"] == 400


def test_routes_to_gemini_when_groq_minute_is_used_up(gl, monkeypatch):
    sent = capture(monkeypatch, gl, [])
    gl.chat("s", "u", max_tokens=700)                 # 400 of Groq's 1,000 output tokens used
    _, who = gl.chat("s", "u", max_tokens=700)        # 400 + 700 > 1,000: Gemini has room
    assert who.startswith("gemini:") and "generativelanguage" in sent[1][0]


def test_429_waits_then_retries(gl, monkeypatch):
    sent = capture(monkeypatch, gl, [FakeResp(429, text="Please try again in 2.5s"), FakeResp()])
    _, who = gl.chat("s", "u")
    assert who.startswith("groq:") and len(sent) == 2


def test_unconfigured_provider_is_skipped(gl, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    sent = capture(monkeypatch, gl, [])
    _, who = gl.chat("s", "u")
    assert who.startswith("gemini:") and len(sent) == 1


def test_model_without_reasoning_switch_is_retried_without_it(gl, monkeypatch):
    sent = capture(monkeypatch, gl, [FakeResp(400, text="reasoning_effort is not supported"), FakeResp()])
    gl.chat("s", "u")
    assert "reasoning_effort" in sent[0][1] and "reasoning_effort" not in sent[1][1]
