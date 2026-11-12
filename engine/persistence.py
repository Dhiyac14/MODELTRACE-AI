"""Persistence helpers for reproducible model artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib


def save_model(model: Any, path: Path) -> Path:
    """Persist a fitted Python model and return its artifact path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return path
