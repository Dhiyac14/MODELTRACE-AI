"""Native Claude backend (Anthropic SDK), selected with LLM_PROVIDER=anthropic.

Same contract as ``LLMClient``: ``structured(system, user, schema)`` returns a validated Pydantic
object, and every call is written to the call log. Differences from the OpenAI-compatible path:
- structured outputs are enforced by the API (``messages.parse`` with ``output_format``);
- no ``temperature`` (Claude Opus 5.5 rejects sampling parameters); depth is set with ``effort``;
- refusals use the server-side fallback by default and are surfaced as ``LLMError``, never as empty output.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from llm.client import S, LLMError, sha256_text, write_call_log
from llm.schemas import utc_now

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
DEFAULT_BASE_URL = "https://api.anthropic.com"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        base_url: str | None = None,
        fallbacks: bool = True,
        max_tokens: int = 16000,
        call_log: str | Path | None = None,
        max_retries: int = 1,
        client: Any = None,
    ) -> None:
        if not api_key and client is None:
            raise LLMError("LLM_API_KEY is not set; put your Claude API key in .env.")
        self.model = model
        self.effort = effort
        self.fallbacks = fallbacks
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.call_log = Path(call_log) if call_log else None
        # Explicit api_key and base_url: the SDK then ignores ANTHROPIC_* environment variables and
        # local profiles, so this key is never sent anywhere else and no other credential is used.
        self._client = client or anthropic.Anthropic(api_key=api_key, base_url=base_url or DEFAULT_BASE_URL)

    @classmethod
    def from_env(cls) -> "ClaudeClient":
        return cls(
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            model=os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODEL,
            effort=os.getenv("LLM_EFFORT", "").strip() or DEFAULT_EFFORT,
            base_url=os.getenv("LLM_BASE_URL", "").strip() or None,
            fallbacks=os.getenv("LLM_FALLBACKS", "default").strip().lower() != "off",
            call_log=os.getenv("LLM_CALL_LOG") or None,
        )

    def structured(self, system: str, user: str, schema: type[S]) -> S:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_format": schema,
            "output_config": {"effort": self.effort},
        }
        last_error = ""
        for _ in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                if self.fallbacks:  # on a refusal the API re-runs the request on a fallback model
                    response = self._client.beta.messages.parse(**kwargs, betas=[FALLBACK_BETA], fallbacks="default")
                else:
                    response = self._client.messages.parse(**kwargs)
            except ValidationError as exc:  # schema-valid JSON that breaks a Pydantic constraint: ask again
                last_error = f"ValidationError: {exc}"[:500]
                self._log(schema, system, user, "", started, None, ok=False, error=last_error)
                continue
            except Exception as exc:  # API or network error: logged for the audit trail, then re-raised
                self._log(schema, system, user, "", started, None, ok=False, error=f"{type(exc).__name__}: {exc}"[:500])
                raise
            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                error = f"refused (category: {getattr(details, 'category', None)})"
                self._log(schema, system, user, "", started, response, ok=False, error=error)
                raise LLMError(f"{schema.__name__}: the model {error}")
            if response.stop_reason == "max_tokens" or response.parsed_output is None:
                error = f"no complete output (stop_reason: {response.stop_reason})"
                self._log(schema, system, user, "", started, response, ok=False, error=error)
                raise LLMError(f"{schema.__name__}: {error}")
            result = response.parsed_output
            self._log(schema, system, user, result.model_dump_json(), started, response, ok=True)
            return result
        raise LLMError(f"{schema.__name__}: no valid reply after {self.max_retries + 1} attempts ({last_error})")

    def _log(self, schema: type[BaseModel], system: str, user: str, reply: str, started: float,
             response: Any, ok: bool, error: str = "") -> None:
        usage = getattr(response, "usage", None)
        write_call_log(self.call_log, {
            "timestamp": utc_now(),
            "provider": "anthropic",
            "model": self.model,
            "served_by": getattr(response, "model", None),  # differs from model when a fallback answered
            "effort": self.effort,
            "schema": schema.__name__,
            "prompt_sha256": sha256_text(system + "\n" + user),
            "response_sha256": sha256_text(reply),
            "seconds": round(time.perf_counter() - started, 3),
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else {},
            "ok": ok,
            "error": error,
        })
