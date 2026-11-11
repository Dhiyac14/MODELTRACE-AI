"""Person 2: LLM client parsing, retry, JSON mode and call log."""
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from llm.client import LLMClient, LLMError, extract_json


class Answer(BaseModel):
    label: str
    score: float


class FakeTransport:
    """Mimics ``openai.OpenAI().chat.completions.create`` with queued replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))], usage=None)


def make(replies, **kwargs):
    transport = FakeTransport(replies)
    return LLMClient(model="test-model", client=transport, **kwargs), transport


def test_parses_fenced_json_and_sends_schema():
    llm, transport = make(['```json\n{"label": "a", "score": 0.5}\n```'])
    assert llm.structured("system", "user", Answer) == Answer(label="a", score=0.5)
    call = transport.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["temperature"] == 0.0
    assert '"score"' in call["messages"][0]["content"]  # schema appended to the system prompt


def test_resends_validation_error_then_succeeds():
    llm, transport = make(['{"label": "a"}', '{"label": "a", "score": 1}'])
    assert llm.structured("system", "user", Answer).score == 1
    retry = transport.calls[1]["messages"]
    assert [m["role"] for m in retry] == ["system", "user", "assistant", "user"]
    assert "score" in retry[-1]["content"]


def test_raises_after_retries():
    llm, _ = make(["not json", "still not json"])
    with pytest.raises(LLMError, match="Answer"):
        llm.structured("system", "user", Answer)


def test_json_mode_can_be_disabled():
    llm, transport = make(['{"label": "a", "score": 1}'], json_mode=False)
    llm.structured("system", "user", Answer)
    assert "response_format" not in transport.calls[0]


def test_every_attempt_is_logged(tmp_path):
    log = tmp_path / "calls.jsonl"
    llm, _ = make(['{"label": "a"}', '{"label": "a", "score": 1}'], call_log=log)
    llm.structured("system", "user", Answer)
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["ok"] for r in records] == [False, True]
    assert {r["schema"] for r in records} == {"Answer"}
    assert all(len(r["prompt_sha256"]) == 64 and r["model"] == "test-model" for r in records)


def test_transport_error_is_logged_and_reraised(tmp_path):
    log = tmp_path / "calls.jsonl"
    llm, _ = make([ConnectionError("endpoint down")], call_log=log)
    with pytest.raises(ConnectionError):
        llm.structured("system", "user", Answer)
    record = json.loads(log.read_text())
    assert record["ok"] is False and "endpoint down" in record["error"]


def test_missing_model_is_rejected():
    with pytest.raises(LLMError, match="LLM_MODEL"):
        LLMClient(model="", client=object())


def test_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODEL", "some-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_JSON_MODE", "false")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    monkeypatch.delenv("LLM_CALL_LOG", raising=False)
    llm = LLMClient.from_env(env_file=tmp_path / "absent.env")
    assert (llm.model, llm.json_mode, llm.temperature, llm.call_log) == ("some-model", False, 0.2, None)


def test_extract_json_without_object():
    with pytest.raises(ValueError):
        extract_json("no object here")
