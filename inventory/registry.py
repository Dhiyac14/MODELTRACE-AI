"""Central model inventory (plan step 15).

JSON persistence is a hackathon prototype, not tamper-proof production governance.
Run ``python -m inventory.registry --seed`` to create the three demonstration records.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from inventory.risk_tier import Rating, assign_tier, template_rationale
from llm.schemas import utc_now

Stage = Literal["discover", "document", "redevelop", "validate", "monitor"]
Status = Literal[
    "not_started",
    "in_progress",
    "pending_review",
    "approved",
    "rejected",
    "changes_requested",
    "invalidated",  # an upstream stage was reopened, so this stage must be reviewed again
    "not_applicable",  # e.g. redevelopment of a model that is already in Python
]
INVENTORY_PATH = Path(__file__).with_name("model_inventory.json")


class InventoryRecord(BaseModel):
    model_id: str
    name: str
    business_purpose: str
    version: str = "1.0.0"
    algorithm: str
    language: str
    source_files: list[str] = Field(default_factory=list, description="Repository paths; the first is the main model file.")
    legacy_document: str | None = Field(default=None, description="Existing model document compared at the Discover stage.")
    lifecycle_stage: Stage = "discover"
    documentation_status: Status = "not_started"
    migration_status: Status = "not_started"
    validation_status: Status = "not_started"
    monitoring_status: Status = "not_started"
    approval_history: list[str] = Field(
        default_factory=list, description="Approval record IDs; the records live in governance/approval_log.json."
    )
    materiality: Rating
    materiality_basis: str
    complexity: Rating
    complexity_basis: str
    tier_rationale: str = ""
    tier_rationale_source: Literal["rule_template", "llm_draft"] = "rule_template"
    tier_status: Status = "not_started"  # set from the Discover gate, where the tier is approved
    updated_at: str = Field(default_factory=utc_now)

    @computed_field  # derived from the ratings, so it can never be stored out of sync
    @property
    def risk_tier(self) -> int:
        return assign_tier(self.materiality, self.complexity)


def load_inventory(path: Path = INVENTORY_PATH) -> list[InventoryRecord]:
    return [InventoryRecord.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def save_inventory(records: list[InventoryRecord], path: Path = INVENTORY_PATH) -> None:
    path.write_text(json.dumps([r.model_dump() for r in records], indent=2) + "\n", encoding="utf-8")


def get_record(records: list[InventoryRecord], model_id: str) -> InventoryRecord:
    for record in records:
        if record.model_id == model_id:
            return record
    raise KeyError(f"model {model_id!r} is not in the inventory")


def update_record(records: list[InventoryRecord], model_id: str, **changes) -> list[InventoryRecord]:
    """Return a new list with one record changed. Changes are validated; ``risk_tier`` cannot be set."""
    if "risk_tier" in changes:
        raise ValueError("risk_tier is derived from materiality and complexity; change those instead")
    current = get_record(records, model_id)
    updated = InventoryRecord.model_validate(
        {**current.model_dump(exclude={"risk_tier"}), **changes, "updated_at": utc_now()}
    )
    return [updated if r.model_id == model_id else r for r in records]


def seed_records() -> list[InventoryRecord]:
    """The three models trained by Person 1's engine (ml-engineering branch), with their model IDs.

    Ratings are illustrative and are approved at the Discover gate. Source paths point at Person 1's files:
    the R script plus engine/data.py, where the split and the excluded columns are defined.
    """
    records = [
        InventoryRecord(
            model_id="legacy-r-logistic",
            name="Legacy R Logistic Regression",
            business_purpose="Estimates the probability that a credit-card customer defaults next month; used in credit decisions.",
            algorithm="Logistic regression (glm, binomial family)",
            language="R",
            source_files=["models/legacy_model.R", "engine/data.py"],
            legacy_document="models/outdated_model_document.md",
            materiality="high",
            materiality_basis="drives credit decisions for customers",
            complexity="low",
            complexity_basis="linear model with a small set of documented predictors",
        ),
        InventoryRecord(
            model_id="python-gradient-boosting",
            name="Python Gradient Boosting",
            business_purpose="Challenger model compared against the production default model; informs but does not drive decisions.",
            algorithm="Gradient Boosting classifier (scikit-learn)",
            language="Python",
            source_files=["engine/models.py", "engine/data.py"],
            legacy_document="models/gradient_boosting_model_document.md",
            migration_status="not_applicable",
            materiality="medium",
            materiality_basis="informs model review but does not drive decisions",
            complexity="high",
            complexity_basis="boosted tree ensemble that needs SHAP to explain",
        ),
        InventoryRecord(
            model_id="python-random-forest",
            name="Python Random Forest",
            business_purpose="Benchmark model for internal analysis; not used in decisions.",
            algorithm="Random Forest classifier (scikit-learn)",
            language="Python",
            source_files=["engine/models.py", "engine/data.py"],
            migration_status="not_applicable",
            materiality="low",
            materiality_basis="internal benchmark only, not used in decisions",
            complexity="medium",
            complexity_basis="bagged tree ensemble with standard settings",
        ),
    ]
    return [r.model_copy(update={"tier_rationale": template_rationale(r)}) for r in records]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the demonstration model inventory.")
    parser.add_argument("--seed", action="store_true", help="write the three demonstration records")
    parser.add_argument("--force", action="store_true", help="overwrite an existing inventory file")
    args = parser.parse_args()
    if not args.seed:
        parser.error("nothing to do; pass --seed")
    if INVENTORY_PATH.exists() and not args.force:
        parser.error(f"{INVENTORY_PATH} exists; pass --force to overwrite it (this discards approval history)")
    save_inventory(seed_records())
    print(f"wrote {INVENTORY_PATH}")
