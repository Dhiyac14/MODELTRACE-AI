"""Provider-neutral LLM client with a deterministic offline mode."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class LLMConfig:
    api_key: str | None = None
    endpoint: str = "https://api.openai.com/v1/chat/completions"
    model: str = "gpt-4o-mini"
    timeout: float = 30.0

    @classmethod
    def from_environment(cls) -> "LLMConfig":
        return cls(
            api_key=os.getenv("MODELTRACE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
            endpoint=os.getenv("MODELTRACE_LLM_ENDPOINT", cls.endpoint),
            model=os.getenv("MODELTRACE_LLM_MODEL", cls.model),
        )


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    deterministic: bool


class LLMClient:
    """Minimal client; no network request is made without an explicitly configured key."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_environment()

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_key)

    def complete(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        if not self.is_configured:
            return LLMResponse(
                text=json.dumps({"mode": "local", "prompt_length": len(prompt)}),
                provider="local",
                model="deterministic",
                deterministic=True,
            )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = json.dumps({"model": self.config.model, "messages": messages, "temperature": 0}).encode()
        request = Request(
            self.config.endpoint,
            data=payload,
            headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.config.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"]
        return LLMResponse(text=str(text), provider="openai-compatible", model=self.config.model, deterministic=False)
