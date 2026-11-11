"""Internal helpers for deterministic agent implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_source(source: str | Path | dict[str, Any]) -> tuple[str, str]:
    if isinstance(source, dict):
        return "<mapping>", json.dumps(source, sort_keys=True)
    if isinstance(source, Path) or (isinstance(source, str) and len(source) < 260):
        path = Path(source)
        if path.exists():
            return str(path), path.read_text(encoding="utf-8")
    return "<text>", str(source)


def load_json(source: str | Path | dict[str, Any]) -> tuple[str, dict[str, Any]]:
    name, text = read_source(source)
    value = source if isinstance(source, dict) else json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return name, value
