"""Load and normalize existing MODELTRACE AI evidence for PDF reports."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inventory.registry import InventoryRecord, load_inventory
from workflow.artifacts import Artifacts


class ReportDataError(ValueError):
    """Raised when report inputs are missing, malformed, or internally invalid."""


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportDataError(f"Unable to read JSON evidence {path}: {exc}") from exc


def _as_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ReportDataError("Expected a JSON array of objects in risk findings evidence.")
    return value


def _validate_mapping_list(value: Any, label: str) -> None:
    if value is not None and (not isinstance(value, list) or any(not isinstance(item, dict) for item in value)):
        raise ReportDataError(f"Expected {label} to be an array of objects.")


def _validate_artifact(kind: str, value: dict[str, Any], path: Path) -> None:
    if kind == "discovery":
        sources = value.get("source_files")
        if sources is not None and (not isinstance(sources, list) or any(not isinstance(item, str) for item in sources)):
            raise ReportDataError(f"Expected source_files in {path} to be an array of strings.")
        _validate_mapping_list(value.get("discrepancies"), f"discrepancies in {path}")
    elif kind == "model_card":
        sections = value.get("sections")
        _validate_mapping_list(sections, f"sections in {path}")
        for section in sections or []:
            _validate_mapping_list(section.get("rows"), f"rows in {path}")
            for row in section.get("rows") or []:
                if "source" in row and row["source"] is not None and not isinstance(row["source"], str):
                    raise ReportDataError(f"Expected row source references in {path} to be strings.")
    elif kind == "validation":
        fairness = value.get("fairness")
        if fairness is not None and not isinstance(fairness, dict):
            raise ReportDataError(f"Expected fairness in {path} to be an object.")
        for group, report in (fairness or {}).items():
            if not isinstance(report, dict):
                raise ReportDataError(f"Expected fairness group {group!r} in {path} to be an object.")
            if "by_group" in report and not isinstance(report["by_group"], dict):
                raise ReportDataError(f"Expected fairness by_group for {group!r} in {path} to be an object.")
    elif kind == "monitoring":
        _validate_mapping_list(value.get("batches"), f"monitoring batches in {path}")


def _record_dict(record: InventoryRecord) -> dict[str, Any]:
    return record.model_dump()


@dataclass(frozen=True)
class ModelReportData:
    """Normalized evidence for one inventory model."""

    record: dict[str, Any]
    discovery: dict[str, Any] | None
    model_card: dict[str, Any] | None
    validation: dict[str, Any] | None
    parity: dict[str, Any] | None
    monitoring: dict[str, Any] | None
    risk_findings: list[dict[str, Any]]
    governance: dict[str, Any]

    @property
    def model_id(self) -> str:
        return str(self.record["model_id"])

    @property
    def model_name(self) -> str:
        return str(self.record["name"])

    @property
    def finding_count(self) -> int:
        return len(self.risk_findings) + len((self.discovery or {}).get("discrepancies") or [])


@dataclass(frozen=True)
class PortfolioReportData:
    """Normalized evidence for the inventory models included in a portfolio report."""

    models: list[ModelReportData]
    inventory_count: int
    governance: dict[str, Any]


class ReportDataLoader:
    """Read-only loader for report inputs.

    Missing optional evidence is represented by ``None`` and rendered as an explicit
    evidence state by the PDF builder. Source files are never written by this class.
    """

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)
        self.artifacts = Artifacts(self.root)

    def _load_optional(self, relative_path: str) -> dict[str, Any] | None:
        value = _read_json(self.root / relative_path)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ReportDataError(f"Expected an object in {self.root / relative_path}.")
        return value

    def _load_optional_findings(self, relative_path: str) -> list[dict[str, Any]]:
        return _as_list(_read_json(self.root / relative_path))

    def _load_artifact(self, kind: str, model_id: str) -> dict[str, Any] | None:
        relative_path = self.artifacts.relpath(kind, model_id)
        value = _read_json(self.root / relative_path)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ReportDataError(f"Expected an object in {self.root / relative_path}.")
        _validate_artifact(kind, value, self.root / relative_path)
        return value

    def _governance(self) -> dict[str, Any]:
        path = self.root / "governance/ss1_23_mapping.json"
        value = _read_json(path)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ReportDataError(f"Expected an object in {path}.")
        _validate_mapping_list(value.get("stages"), f"governance stages in {path}")
        for stage in value.get("stages") or []:
            if not isinstance(stage.get("stage"), str):
                raise ReportDataError(f"Expected governance stage names in {path} to be strings.")
        return value

    def inventory(self) -> list[InventoryRecord]:
        path = self.root / "inventory/model_inventory.json"
        if not path.is_file():
            raise ReportDataError(f"Model inventory is missing: {path}")
        try:
            return load_inventory(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ReportDataError(f"Unable to validate model inventory {path}: {exc}") from exc

    def model(self, model_id: str) -> ModelReportData:
        records = self.inventory()
        record = next((item for item in records if item.model_id == model_id), None)
        if record is None:
            raise ReportDataError(f"Unknown model ID: {model_id}")

        validation = self._load_artifact("validation", model_id)
        parity = self._load_artifact("parity", model_id)
        monitoring = self._load_artifact("monitoring", model_id)
        return ModelReportData(
            record=_record_dict(record),
            discovery=self._load_artifact("discovery", model_id),
            model_card=self._load_artifact("model_card", model_id),
            validation=validation,
            parity=parity,
            monitoring=monitoring,
            risk_findings=self._load_optional_findings(self.artifacts.relpath("risk_findings", model_id)),
            governance=self._governance(),
        )

    def portfolio(self, model_ids: list[str] | None = None) -> PortfolioReportData:
        records = self.inventory()
        selected = model_ids or [record.model_id for record in records]
        models = [self.model(model_id) for model_id in selected]
        return PortfolioReportData(models=models, inventory_count=len(records), governance=self._governance())
