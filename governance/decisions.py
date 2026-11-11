"""Decision handling and separation-of-duties checks."""

from dataclasses import dataclass
from typing import Any

from .audit import AuditLog
from .core import DECISION_VALUES, Decision, Stage


class DecisionError(ValueError):
    """Raised when a governance decision violates a control."""


@dataclass(frozen=True)
class DecisionRecord:
    subject: str
    stage: str
    decision: str
    requested_by: str
    decided_by: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class DecisionService:
    """Require a distinct reviewer and retain every decision in the audit log."""

    def __init__(self, audit_log: AuditLog | None = None) -> None:
        self.audit_log = audit_log or AuditLog()
        self._decisions: list[DecisionRecord] = []

    def decide(
        self,
        subject: str,
        stage: Stage | str,
        decision: Decision | str,
        requested_by: str,
        decided_by: str,
        rationale: str,
    ) -> DecisionRecord:
        stage_name = stage.value if isinstance(stage, Stage) else str(stage)
        decision_name = decision.value if isinstance(decision, Decision) else str(decision)
        if decision_name not in DECISION_VALUES:
            raise DecisionError(f"decision must be one of {DECISION_VALUES}")
        if not subject or not requested_by or not decided_by:
            raise DecisionError("subject, requester, and decision maker are required")
        if requested_by == decided_by:
            raise DecisionError("separation of duties: requester and decision maker must differ")
        if not rationale.strip():
            raise DecisionError("a rationale is required for every decision")
        record = DecisionRecord(
            subject, stage_name, decision_name, requested_by, decided_by, rationale.strip()
        )
        self._decisions.append(record)
        self.audit_log.record(
            "decision",
            decided_by,
            subject,
            {"stage": stage_name, "decision": decision_name, "requested_by": requested_by,
             "rationale": record.rationale},
        )
        return record

    def decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(self._decisions)
