"""Where each stage's evidence lives.

Person 2's agents write one file per model. Person 1's engine (``engine/pipeline.py`` on the
``ml-engineering`` branch) writes one report per kind, for the migrated legacy model only; the other
models have no Person 1 reports yet, so their Redevelop/Validate/Monitor evidence stays missing.

Approval gates read live files only. Copies of Person 1's reports are a labelled display fallback
for development on this branch; they can never satisfy a gate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PERSON2_REPORTS = {
    "discovery": "reports/discovery/{model_id}_discovery.json",
    "model_card": "reports/documentation/{model_id}_model_card.json",
    "alerts": "reports/alerts/{model_id}_alerts.json",
    "llm_migration": "reports/llm_migration/{model_id}_llm_migration.json",
    "discovery_score": "reports/discovery/{model_id}_score.json",  # written by Person 1, who holds the answer key
}
PERSON1_MODEL = "legacy-r-logistic"
PERSON1_REPORTS = {
    "parity": "reports/migration/migration_results.json",
    "validation": "reports/validation/validation_results.json",
    "monitoring": "reports/monitoring/monitoring_results.json",
    "risk_findings": "reports/risk_findings/risk_findings_results.json",
}
# SHAP results that Person 1's validation run computes for the supporting models, stored inside the legacy
# model's report. Only these blocks belong to those models; the report's metrics belong to the migrated model.
PERSON1_SHAP_KEYS = {"python-random-forest": "random_forest_shap", "python-gradient-boosting": "gradient_boosting_shap"}
PYTHON_CANDIDATE_SOURCE = "engine/models.py"  # Person 1's Statsmodels candidate (train_statsmodels_logistic)
STAGE_EVIDENCE = {
    "discover": "discovery",
    "document": "model_card",
    "redevelop": "parity",
    "validate": "validation",
    "monitor": "monitoring",
}
# Copies of Person 1's reports from ml-engineering @ fdad799, used only when the sample toggle is on.
SAMPLE_ROOT = Path("tests/fixtures/p2/person1_reports")


def person1_shap(validation_report: dict[str, Any] | None, model_id: str) -> dict[str, Any] | None:
    key = PERSON1_SHAP_KEYS.get(model_id)
    return ((validation_report or {}).get("explainability") or {}).get(key) if key else None


def parity_passed(report: dict[str, Any] | None) -> bool:
    """Person 1's verdict on R glm vs Statsmodels parity (row alignment, MAE and max difference within tolerance)."""
    return ((report or {}).get("r_vs_statsmodels") or {}).get("overall_pass") is True


class Artifacts:
    def __init__(self, root: str | Path = ".", sample_root: str | Path | None = None) -> None:
        self.root = Path(root)
        self.sample_root = Path(sample_root) if sample_root else None

    def relpath(self, kind: str, model_id: str) -> str:
        if kind in PERSON2_REPORTS:
            return PERSON2_REPORTS[kind].format(model_id=model_id)
        if model_id == PERSON1_MODEL:
            return PERSON1_REPORTS[kind]
        return f"reports/{kind}/{model_id}_{kind}.json"  # Person 1's pipeline does not cover this model yet

    def path(self, kind: str, model_id: str) -> Path:
        return self.root / self.relpath(kind, model_id)

    def exists(self, kind: str, model_id: str) -> bool:
        return self.path(kind, model_id).exists()

    def sha256(self, kind: str, model_id: str) -> str:
        path = self.path(kind, model_id)
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""

    def load(self, kind: str, model_id: str) -> Any:
        """Live file only (what the approval gates use)."""
        path = self.path(kind, model_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def load_for_display(self, kind: str, model_id: str) -> tuple[Any, str | None, bool]:
        """Return ``(data, path, is_sample)``; falls back to the copies of Person 1's reports if enabled."""
        data = self.load(kind, model_id)
        if data is not None:
            return data, self.relpath(kind, model_id), False
        if self.sample_root is not None and kind in PERSON1_REPORTS:
            sample = self.root / self.sample_root / self.relpath(kind, model_id)
            if sample.exists():
                return json.loads(sample.read_text(encoding="utf-8")), sample.relative_to(self.root).as_posix(), True
        return None, None, False

    def read_text(self, relative_path: str | None) -> str | None:
        if not relative_path:
            return None
        path = self.root / relative_path
        return path.read_text(encoding="utf-8") if path.is_file() else None
