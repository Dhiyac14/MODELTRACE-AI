"""Five-stage model lifecycle with explicit governance decisions."""

from dataclasses import dataclass
from typing import Any

from governance.audit import AuditLog
from governance.core import RiskTier, Stage, normalize_risk_tier, stage_principles
from governance.decisions import DecisionRecord, DecisionService


class LifecycleError(ValueError):
    """Raised for invalid lifecycle operations."""


@dataclass
class LifecycleWorkflow:
    model_id: str
    risk_tier: RiskTier
    stage: Stage = Stage.DISCOVER
    audit_log: AuditLog | None = None

    def __post_init__(self) -> None:
        self.risk_tier = normalize_risk_tier(self.risk_tier)
        if not self.model_id:
            raise LifecycleError("model_id is required")
        self.audit_log = self.audit_log or AuditLog()
        self.decisions_service = DecisionService(self.audit_log)
        self.audit_log.record("lifecycle-created", "system", self.model_id,
                              {"stage": self.stage.value, "risk_tier": self.risk_tier.value})

    @property
    def principles(self) -> tuple[str, ...]:
        return stage_principles(self.stage)

    def request_decision(
        self, decision: str, requester: str, reviewer: str, rationale: str
    ) -> DecisionRecord:
        record = self.decisions_service.decide(
            self.model_id, self.stage, decision, requester, reviewer, rationale
        )
        if record.decision == "approve":
            if self.stage != Stage.MONITOR:
                self.stage = Stage(list(Stage)[list(Stage).index(self.stage) + 1])
            self.audit_log.record("stage-advanced", reviewer, self.model_id,
                                  {"stage": self.stage.value})
        elif record.decision == "reject":
            self.audit_log.record("lifecycle-rejected", reviewer, self.model_id,
                                  {"stage": self.stage.value})
        return record

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "risk_tier": self.risk_tier.value,
            "stage": self.stage.value,
            "principles": list(self.principles),
            "audit_log": self.audit_log.to_dict(),
        }
