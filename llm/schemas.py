"""Structured outputs of the LLM and of the Person 2 agents.

LLM-facing models are the ones passed to ``LLMClient.structured``. Fields described as
"set by the system" are always recomputed by code after the LLM replies.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

FactStatus = Literal["verified", "inferred", "missing"]
ReviewStatus = Literal["pending_human_review", "approved", "rejected", "changes_requested"]
DiscrepancyType = Literal["contradiction", "omission", "unverifiable"]
# Closed vocabulary so discrepancy reports can be scored against the answer key by (field, type).
DiscrepancyField = Literal[
    "model_name",
    "business_purpose",
    "algorithm",
    "target_variable",
    "input_features",
    "preprocessing",
    "train_test_split",
    "decision_threshold",
    "performance",
    "validation_history",
    "ownership",
    "monitoring",
    "limitations",
    "other",
]
# Compared in Python by the Discovery Agent, never judged by the LLM.
MECHANICAL_FIELDS: frozenset[str] = frozenset({"input_features", "decision_threshold", "train_test_split"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- evidence
class SourceRef(BaseModel):
    file: str = Field(description="File name exactly as shown in the listing header.")
    line_start: int = Field(ge=1, description="First line number, from the listing.")
    line_end: int = Field(ge=1, description="Last line number, from the listing.")
    quote: str = Field(description="Exact text copied from those lines, without the line-number prefix.")
    verified: bool = Field(default=False, description="Set by the system. Leave false.")


class Fact(BaseModel, Generic[T]):
    value: T | None = None
    status: FactStatus = Field(
        description=(
            "verified = stated directly in the code at the cited lines; "
            "inferred = reasoned from names or context (explain in note); "
            "missing = the code does not tell us (value null)."
        )
    )
    evidence: list[SourceRef] = Field(default_factory=list)
    note: str = ""


class Documented(BaseModel, Generic[T]):
    """A value stated in an existing model document, with the lines that state it."""

    value: T
    ref: SourceRef


# --------------------------------------------------------------------------- discovery (LLM)
class ModelMetadata(BaseModel):
    model_name: Fact[str]
    algorithm: Fact[str]
    business_purpose: Fact[str]
    target_variable: Fact[str]
    input_features: Fact[list[str]] = Field(
        description="Every predictor the model is fitted on, one name per item, exactly as written in the code."
    )
    excluded_columns: Fact[list[str]] = Field(
        description="Columns present in the data but deliberately not used as predictors."
    )
    preprocessing_steps: Fact[list[str]]
    train_fraction: Fact[float] = Field(description="Share of rows used for training, as a fraction between 0 and 1.")
    decision_threshold: Fact[float] = Field(description="Probability cut-off above which a case is classed as default.")
    assumptions: list[Fact[str]] = Field(default_factory=list)
    limitations: list[Fact[str]] = Field(default_factory=list)
    missing_information: list[str] = Field(
        default_factory=list,
        description="Information a model document needs that the code cannot provide.",
    )


class DocClaim(BaseModel):
    claim_id: str = Field(description="C1, C2, ...")
    field: DiscrepancyField
    statement: str = Field(description="What the document claims, in one sentence.")
    doc_ref: SourceRef


class DocumentClaims(BaseModel):
    input_features: Documented[list[str]] | None = Field(
        default=None, description="Predictors the document lists, expanded into single names. Null if not stated."
    )
    decision_threshold: Documented[float] | None = Field(default=None, description="Null if not stated.")
    train_fraction: Documented[float] | None = Field(
        default=None, description="Training share as a fraction, e.g. a 60/40 split is 0.6. Null if not stated."
    )
    other_claims: list[DocClaim] = Field(default_factory=list)


class ClaimAssessment(BaseModel):
    claim_id: str
    verdict: Literal["consistent", "contradiction", "unverifiable"]
    code_evidence: list[SourceRef] = Field(default_factory=list)
    explanation: str
    suggested_correction: str = ""


class OmissionFinding(BaseModel):
    field: DiscrepancyField
    code_evidence: list[SourceRef]
    explanation: str
    suggested_correction: str


class ClaimCheck(BaseModel):
    assessments: list[ClaimAssessment] = Field(default_factory=list)
    omissions: list[OmissionFinding] = Field(default_factory=list)


# --------------------------------------------------------------------------- discovery (report)
class Discrepancy(BaseModel):
    discrepancy_id: str
    field: DiscrepancyField
    type: DiscrepancyType
    documented_claim: str
    document_ref: SourceRef | None = None
    code_evidence: list[SourceRef] = Field(default_factory=list)
    explanation: str
    suggested_correction: str
    detected_by: Literal["rule", "llm"]


class DiscoveryReport(BaseModel):
    model_id: str
    language: str
    source_files: list[str]
    legacy_document: str | None = None
    metadata: ModelMetadata
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    evidence_warnings: list[str] = Field(default_factory=list)
    llm_model: str
    generated_at: str = Field(default_factory=utc_now)
    review_status: ReviewStatus = "pending_human_review"


# --------------------------------------------------------------------------- documentation
class ModelCardNarrative(BaseModel):
    overview: str = Field(description="Model overview and intended purpose, 2-4 sentences.")
    methodology: str = Field(description="Algorithm and methodology, 2-4 sentences.")
    limitations: str = Field(description="Limitations and assumptions, 2-4 sentences.")


class CardRow(BaseModel):
    label: str
    value: str
    source: str = ""


class CardSection(BaseModel):
    key: str
    title: str
    status: Literal["available", "pending"] = "available"
    source: Literal["llm_draft", "template", "evidence", "discovery", "inventory", "constant"]
    text: str = ""
    rows: list[CardRow] = Field(default_factory=list)


class ModelCard(BaseModel):
    model_id: str
    model_name: str
    version: str
    risk_tier: int
    sections: list[CardSection]
    grounding_warnings: list[str] = Field(default_factory=list)
    generated_by: str
    generated_at: str = Field(default_factory=utc_now)
    review_status: ReviewStatus = "pending_human_review"


# --------------------------------------------------------------------------- monitoring
AlertMetric = Literal["feature_psi", "prediction_psi", "schema_change", "missing_values"]
Recommendation = Literal["monitor", "investigate", "consider_revalidation"]


class AlertExplanation(BaseModel):
    alert_id: str
    summary: str = Field(description="Which feature or output changed and the evidence that triggered the alert.")
    potential_impact: str = Field(description="What this could mean for predictions or decisions.")
    investigate: list[str] = Field(description="2-4 concrete checks for the reviewer.")
    recommendation: Recommendation
    reason: str = Field(description="Why this recommendation, in one sentence.")


class AlertExplanations(BaseModel):
    items: list[AlertExplanation]


class Alert(BaseModel):
    alert_id: str = Field(description="Stable id <model>:<batch>:<metric>:<feature>, so reviews survive re-runs.")
    model_id: str
    batch_id: str
    scenario: str = ""
    metric: AlertMetric
    feature: str | None = None
    value: float | None = None
    severity: Literal["warning", "high"]
    rule: str
    evidence_ref: str
    explanation: AlertExplanation | None = None
    explanation_source: Literal["llm_draft", "template"] = "template"


class AlertReport(BaseModel):
    model_id: str
    source: str
    alerts: list[Alert] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_by: str
    generated_at: str = Field(default_factory=utc_now)


# --------------------------------------------------------------------------- inventory
class TierRationaleDraft(BaseModel):
    rationale: str = Field(description="2-3 sentences explaining the given tier. Do not change the tier.")


# --------------------------------------------------------------------------- migration (used by Person 1)
class TermMapping(BaseModel):
    r_term: str
    python_term: str
    note: str = ""


class MigrationCandidate(BaseModel):
    python_code: str = Field(description="Complete Python module, no Markdown fences.")
    explanation: str
    assumptions: list[str] = Field(default_factory=list)
    term_mapping: list[TermMapping] = Field(default_factory=list)
