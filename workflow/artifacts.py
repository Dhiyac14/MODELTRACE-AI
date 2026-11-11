"""Where each stage's evidence lives (the interface contract with Person 1).

Approval gates read live files only. Sample files are a labelled display fallback for the
dashboard while Person 1's reports do not exist yet; they can never satisfy a gate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

KINDS = {
    "discovery": "reports/discovery/{model_id}_discovery.json",
    "model_card": "reports/documentation/{model_id}_model_card.json",
    "parity": "reports/migration/{model_id}_parity.json",
    "validation": "reports/validation/{model_id}_validation.json",
    "discovery_score": "reports/validation/{model_id}_discovery_score.json",
    "monitoring": "reports/monitoring/{model_id}_monitoring.json",
    "alerts": "reports/alerts/{model_id}_alerts.json",
}
PERSON1_KINDS = frozenset({"parity", "validation", "discovery_score", "monitoring"})
STAGE_EVIDENCE = {
    "discover": "discovery",
    "document": "model_card",
    "redevelop": "parity",
    "validate": "validation",
    "monitor": "monitoring",
}
SAMPLE_ROOT = Path("tests/fixtures/p2/sample_data")


class Artifacts:
    def __init__(self, root: str | Path = ".", sample_root: str | Path | None = None) -> None:
        self.root = Path(root)
        self.sample_root = Path(sample_root) if sample_root else None

    def relpath(self, kind: str, model_id: str) -> str:
        return KINDS[kind].format(model_id=model_id)

    def path(self, kind: str, model_id: str) -> Path:
        return self.root / self.relpath(kind, model_id)

    def exists(self, kind: str, model_id: str) -> bool:
        return self.path(kind, model_id).exists()

    def sha256(self, kind: str, model_id: str) -> str:
        path = self.path(kind, model_id)
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""

    def load(self, kind: str, model_id: str) -> dict[str, Any] | None:
        """Live file only (what the approval gates use)."""
        path = self.path(kind, model_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def load_for_display(self, kind: str, model_id: str) -> tuple[dict[str, Any] | None, str | None, bool]:
        """Return ``(data, path, is_sample)``; falls back to sample data for Person 1's reports if enabled."""
        data = self.load(kind, model_id)
        if data is not None:
            return data, self.relpath(kind, model_id), False
        if self.sample_root is not None and kind in PERSON1_KINDS:
            sample = self.root / self.sample_root / self.relpath(kind, model_id)
            if sample.exists():
                return json.loads(sample.read_text(encoding="utf-8")), sample.relative_to(self.root).as_posix(), True
        return None, None, False

    def read_text(self, relative_path: str | None) -> str | None:
        if not relative_path:
            return None
        path = self.root / relative_path
        return path.read_text(encoding="utf-8") if path.is_file() else None
