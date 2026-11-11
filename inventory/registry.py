"""A deliberately small JSON-serializable model inventory."""

from dataclasses import asdict, dataclass
from typing import Any
import json
from pathlib import Path

from governance.core import RiskTier, normalize_risk_tier


@dataclass
class ModelRecord:
    model_id: str
    owner: str
    risk_tier: RiskTier | str
    purpose: str
    status: str = "active"

    def __post_init__(self) -> None:
        self.risk_tier = normalize_risk_tier(self.risk_tier)
        if not self.model_id or not self.owner or not self.purpose:
            raise ValueError("model_id, owner, and purpose are required")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["risk_tier"] = self.risk_tier.value
        return value


class ModelInventory:
    def __init__(self, records: list[ModelRecord] | None = None) -> None:
        self._records = {record.model_id: record for record in records or []}

    def register(self, record: ModelRecord) -> None:
        if record.model_id in self._records:
            raise ValueError(f"model already exists: {record.model_id}")
        self._records[record.model_id] = record

    def get(self, model_id: str) -> ModelRecord:
        try:
            return self._records[model_id]
        except KeyError as exc:
            raise KeyError(f"model not found: {model_id}") from exc

    def records(self) -> tuple[ModelRecord, ...]:
        return tuple(self._records.values())

    def to_dict(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.records()]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ModelInventory":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("inventory JSON must contain a list")
        return cls([ModelRecord(**item) for item in data])
