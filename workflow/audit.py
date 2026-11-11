"""Hash-chained audit log (plan step 15).

Each event stores the hash of the previous event, so editing or deleting any past event breaks
the chain and ``verify`` reports it. This makes tampering detectable, not impossible: it is a
prototype on JSON files, not production governance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from llm.schemas import utc_now
from workflow.store import JsonList, new_id

GENESIS = "0" * 64


class AuditEvent(BaseModel):
    event_id: str
    timestamp: str
    actor: str
    role: str
    action: str
    model_id: str | None = None
    stage: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str
    hash: str = ""


def _digest(event: AuditEvent) -> str:
    body = event.model_dump(exclude={"hash"})
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        self._store = JsonList(path, AuditEvent)

    def events(self) -> list[AuditEvent]:
        return self._store.all()

    def record(self, actor: str, role: str, action: str, model_id: str | None = None,
               stage: str | None = None, details: dict[str, Any] | None = None) -> AuditEvent:
        events = self.events()
        event = AuditEvent(
            event_id=new_id("EVT"), timestamp=utc_now(), actor=actor, role=role, action=action,
            model_id=model_id, stage=stage, details=details or {},
            prev_hash=events[-1].hash if events else GENESIS,
        )
        event.hash = _digest(event)
        return self._store.append(event)

    def verify(self) -> list[str]:
        """Return every break in the chain; an empty list means the log is intact."""
        problems = []
        prev = GENESIS
        for i, event in enumerate(self.events()):
            if event.prev_hash != prev:
                problems.append(f"event {i} ({event.event_id}): previous-hash link broken (an event was removed or reordered)")
            if _digest(event) != event.hash:
                problems.append(f"event {i} ({event.event_id}): content does not match its hash (edited after recording)")
            prev = event.hash
        return problems
