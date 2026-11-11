"""Person 2: native Claude backend (no network: the Anthropic SDK is replaced by a fake)."""
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from llm.claude_client import DEFAULT_BASE_URL, FALLBACK_BETA, ClaudeClient
from llm.client import LLMError, llm_from_env


class Answer(BaseModel):
    label: str


class FakeSDK:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = SimpleNamespace(parse=self._parse("plain"))
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse("beta")))

    def _parse(self, kind):
        def parse(**kwargs):
            self.calls.append((kind, kwargs))
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return parse


def reply(parsed=None, stop="end_turn", model="claude-opus-5-5", category=None):
    return SimpleNamespace(parsed_output=parsed, stop_reason=stop, model=model, usage=None,
                           stop_details=SimpleNamespace(category=category))


def validation_error() -> ValidationError:
    try:
        Answer.model_validate({})
    except ValidationError as exc:
        return exc


def make(replies, **kwargs):
    sdk = FakeSDK(replies)
    return ClaudeClient(api_key="unused", client=sdk, **kwargs), sdk


def test_default_request_shape():
    llm, sdk = make([reply(Answer(label="a"))])
    assert llm.structured("sys", "user", Answer) == Answer(label="a")
    kind, kwargs = sdk.calls[0]
    assert kind == "beta"
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["output_config"] == {"effort": "medium"}
    assert kwargs["output_format"] is Answer
    assert kwargs["betas"] == [FALLBACK_BETA] and kwargs["fallbacks"] == "default"
    assert kwargs["system"] == "sys" and kwargs["messages"] == [{"role": "user", "content": "user"}]
    assert "temperature" not in kwargs  # Claude Opus 5.5 rejects sampling parameters


def test_fallbacks_can_be_turned_off():
    llm, sdk = make([reply(Answer(label="a"))], fallbacks=False, effort="high")
    llm.structured("sys", "user", Answer)
    kind, kwargs = sdk.calls[0]
    assert kind == "plain" and "betas" not in kwargs and kwargs["output_config"] == {"effort": "high"}


def test_refusal_and_truncation_are_errors(tmp_path):
    log = tmp_path / "calls.jsonl"
    llm, _ = make([reply(stop="refusal", category="cyber"), reply(stop="max_tokens")], call_log=log)
    with pytest.raises(LLMError, match="refused .category: cyber"):
        llm.structured("sys", "user", Answer)
    with pytest.raises(LLMError, match="max_tokens"):
        llm.structured("sys", "user", Answer)
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["ok"] for r in records] == [False, False]
    assert records[0]["provider"] == "anthropic" and records[0]["effort"] == "medium"


def test_validation_error_is_retried_once():
    llm, sdk = make([validation_error(), reply(Answer(label="b"))])
    assert llm.structured("sys", "user", Answer).label == "b"
    assert len(sdk.calls) == 2
    llm, _ = make([validation_error(), validation_error()])
    with pytest.raises(LLMError, match="no valid reply"):
        llm.structured("sys", "user", Answer)


def test_api_error_is_logged_and_reraised(tmp_path):
    log = tmp_path / "calls.jsonl"
    llm, _ = make([ConnectionError("down")], call_log=log)
    with pytest.raises(ConnectionError):
        llm.structured("sys", "user", Answer)
    assert json.loads(log.read_text())["error"].startswith("ConnectionError")


def test_fallback_model_is_recorded(tmp_path):
    log = tmp_path / "calls.jsonl"
    llm, _ = make([reply(Answer(label="a"), model="claude-opus-5")], call_log=log)
    llm.structured("sys", "user", Answer)
    assert json.loads(log.read_text())["served_by"] == "claude-opus-5"


def test_missing_key_is_rejected():
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        ClaudeClient(api_key="")


def test_env_selects_claude_and_pins_the_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.invalid")  # must not be used
    for name in ("LLM_MODEL", "LLM_EFFORT", "LLM_BASE_URL", "LLM_FALLBACKS", "LLM_CALL_LOG"):
        monkeypatch.delenv(name, raising=False)
    client, status = llm_from_env(tmp_path / "absent.env")
    assert isinstance(client, ClaudeClient)
    assert (client.model, client.effort, client.fallbacks) == ("claude-opus-5-5", "medium", True)
    assert str(client._client.base_url).rstrip("/") == DEFAULT_BASE_URL
    assert status == "LLM: Claude claude-opus-5-5 (effort medium)"


def test_env_without_key_reports_not_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "")
    client, status = llm_from_env(tmp_path / "absent.env")
    assert client is None and "LLM_API_KEY" in status
