"""Small, dependency-free governance vocabulary and SS1/23 mappings."""

from enum import Enum


class Stage(str, Enum):
    DISCOVER = "Discover"
    DOCUMENT = "Document"
    REDEVELOP = "Redevelop"
    VALIDATE = "Validate"
    MONITOR = "Monitor"


class Decision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request-changes"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


DECISION_VALUES = tuple(decision.value for decision in Decision)

# SS1/23 principles are named rather than represented by opaque numbers so
# exported audit records remain useful outside this package.
STAGE_PRINCIPLES = {
    Stage.DISCOVER.value: ("model identification", "risk-based materiality"),
    Stage.DOCUMENT.value: ("governance and controls", "transparency"),
    Stage.REDEVELOP.value: ("change control", "robustness"),
    Stage.VALIDATE.value: ("independent validation", "effective challenge"),
    Stage.MONITOR.value: ("ongoing monitoring", "escalation and remediation"),
}


def stage_principles(stage: Stage | str) -> tuple[str, ...]:
    """Return SS1/23-aligned control principles for a lifecycle stage."""
    key = stage.value if isinstance(stage, Stage) else str(stage)
    try:
        return STAGE_PRINCIPLES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown lifecycle stage: {stage!r}") from exc


def normalize_risk_tier(value: RiskTier | str) -> RiskTier:
    """Parse a risk tier and provide a clear error for malformed artifacts."""
    if isinstance(value, RiskTier):
        return value
    try:
        return RiskTier(str(value).lower())
    except ValueError as exc:
        raise ValueError(f"Unknown SS1/23 risk tier: {value!r}") from exc
