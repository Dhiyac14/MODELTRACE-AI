"""Append-only audit records with JSON-safe serialization."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
import json


@dataclass(frozen=True)
class AuditEvent:
    action: str
    actor: str
    subject: str
    timestamp: str
    details: dict[str, Any]

    @classmethod
    def create(
        cls, action: str, actor: str, subject: str, details: Mapping[str, Any] | None = None
    ) -> "AuditEvent":
        if not actor or not subject:
            raise ValueError("actor and subject are required for an audit event")
        return cls(
            action=action,
            actor=actor,
            subject=subject,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=dict(details or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLog:
    """In-memory append-only log; callers can persist ``to_json`` themselves."""

    def __init__(self, events: list[AuditEvent] | None = None) -> None:
        self._events = list(events or [])

    def record(
        self, action: str, actor: str, subject: str, details: Mapping[str, Any] | None = None
    ) -> AuditEvent:
        event = AuditEvent.create(action, actor, subject, details)
        self._events.append(event)
        return event

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def to_dict(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events]

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, values: list[Mapping[str, Any]]) -> "AuditLog":
        events = [AuditEvent(**dict(value)) for value in values]
        return cls(events)
