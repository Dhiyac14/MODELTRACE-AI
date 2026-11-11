"""Explicit, serialisable contracts shared by LLM-backed agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Evidence:
    """A claim must point to an observable source; values are never inferred."""

    source: str
    claim: str
    excerpt: str | None = None
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Finding:
    """A single evidence-backed observation."""

    id: str
    title: str
    status: str
    claim: str
    evidence: tuple[Evidence, ...] = ()
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence"] = [item.to_dict() for item in self.evidence]
        return result


@dataclass
class AgentResult:
    """Stable result envelope returned by every agent."""

    agent: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "summary": self.summary,
            "findings": [finding.to_dict() for finding in self.findings],
            "metrics": self.metrics,
            "recommendations": self.recommendations,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AgentResult":
        """Build a result from a JSON-like mapping while preserving its contract."""
        findings = [
            Finding(
                id=str(item["id"]),
                title=str(item["title"]),
                status=str(item["status"]),
                claim=str(item["claim"]),
                severity=str(item.get("severity", "info")),
                evidence=tuple(Evidence(**e) for e in item.get("evidence", [])),
            )
            for item in value.get("findings", [])
        ]
        return cls(
            agent=str(value["agent"]),
            summary=str(value["summary"]),
            findings=findings,
            metrics=dict(value.get("metrics", {})),
            recommendations=[str(item) for item in value.get("recommendations", [])],
            evidence=[Evidence(**item) for item in value.get("evidence", [])],
        )
