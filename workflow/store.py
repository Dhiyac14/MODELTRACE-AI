"""Append-only JSON list files for approval records, alert reviews and audit events."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class JsonList(Generic[M]):
    def __init__(self, path: str | Path, model: type[M]) -> None:
        self.path = Path(path)
        self.model = model

    def all(self) -> list[M]:
        if not self.path.exists():
            return []
        return [self.model.model_validate(item) for item in json.loads(self.path.read_text(encoding="utf-8"))]

    def append(self, item: M) -> M:
        items = [i.model_dump() for i in self.all()] + [item.model_dump()]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written log
        return item
