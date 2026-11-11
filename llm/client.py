"""Reusable OpenAI-compatible LLM client with validated structured output.

Agents depend only on ``structured(system, user, schema)`` and ``model``, so any object with
those two members (``ReplayLLM``, a test fake) can stand in for the real client.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Protocol, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from llm.schemas import utc_now

S = TypeVar("S", bound=BaseModel)


class LLMError(RuntimeError):
    """The LLM could not produce a valid structured reply."""


class StructuredLLM(Protocol):
    model: str

    def structured(self, system: str, user: str, schema: type[S]) -> S: ...


def extract_json(text: str) -> str:
    """Return the JSON object inside a reply, tolerating code fences and surrounding prose."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("the reply contains no JSON object")
    return text[start : end + 1]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMClient:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        json_mode: bool = True,
        call_log: str | Path | None = None,
        max_retries: int = 1,
        client: Any = None,
    ) -> None:
        if not model:
            raise LLMError("LLM_MODEL is not set; copy .env.example to .env and fill it in.")
        self.model = model
        self.temperature = temperature
        self.json_mode = json_mode
        self.max_retries = max_retries
        self.call_log = Path(call_log) if call_log else None
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
        self._client = client

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "LLMClient":
        load_dotenv(env_file)
        return cls(
            model=os.getenv("LLM_MODEL", ""),
            api_key=os.getenv("LLM_API_KEY") or None,
            base_url=os.getenv("LLM_BASE_URL") or None,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            json_mode=os.getenv("LLM_JSON_MODE", "true").strip().lower() == "true",
            call_log=os.getenv("LLM_CALL_LOG") or None,
        )

    def structured(self, system: str, user: str, schema: type[S]) -> S:
        """Ask for one JSON object matching ``schema``; resend validation errors up to ``max_retries`` times."""
        system = (
            f"{system}\n\nRespond with one JSON object that matches this JSON schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        for _ in range(self.max_retries + 1):
            reply, call = self._chat(messages, schema)
            try:
                result = schema.model_validate_json(extract_json(reply))
            except (ValueError, ValidationError) as exc:
                self._log(schema, messages, reply, call, ok=False, error=str(exc)[:500])
                messages += [
                    {"role": "assistant", "content": reply},
                    {
                        "role": "user",
                        "content": f"That reply was not valid. Fix these errors and return only the corrected JSON object:\n{exc}",
                    },
                ]
                continue
            self._log(schema, messages, reply, call, ok=True)
            return result
        raise LLMError(f"{schema.__name__}: no valid reply after {self.max_retries + 1} attempts")

    def _chat(self, messages: list[dict[str, str]], schema: type[BaseModel]) -> tuple[str, dict[str, Any]]:
        """Return the reply text and call details (seconds, token usage) for the log."""
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # logged for the audit trail, then re-raised unchanged
            call = {"seconds": round(time.perf_counter() - started, 3), "usage": {}}
            self._log(schema, messages, "", call, ok=False, error=f"{type(exc).__name__}: {exc}"[:500])
            raise
        usage = getattr(response, "usage", None)
        call = {
            "seconds": round(time.perf_counter() - started, 3),
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else {},
        }
        return response.choices[0].message.content or "", call

    def _log(
        self,
        schema: type[BaseModel],
        messages: list[dict[str, str]],
        reply: str,
        call: dict[str, Any],
        ok: bool,
        error: str = "",
    ) -> None:
        if self.call_log is None:
            return
        record = {
            "timestamp": utc_now(),
            "model": self.model,
            "schema": schema.__name__,
            "prompt_sha256": _sha256(json.dumps(messages)),
            "response_sha256": _sha256(reply),
            **call,
            "ok": ok,
            "error": error,
        }
        self.call_log.parent.mkdir(parents=True, exist_ok=True)
        with self.call_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


class ReplayLLM:
    """Offline stand-in that returns canned replies from ``<replies_dir>/<SchemaName>.json``.

    Used by tests and by the offline demo; the replies still go through every verification step.
    """

    model = "replay"

    def __init__(self, replies_dir: str | Path) -> None:
        self.replies_dir = Path(replies_dir)

    def structured(self, system: str, user: str, schema: type[S]) -> S:
        path = self.replies_dir / f"{schema.__name__}.json"
        return schema.model_validate_json(path.read_text(encoding="utf-8"))
