"""Safe loading of dashboard JSON artifacts."""

import json
from pathlib import Path
from typing import Any


def load_json_artifact(path: str | Path, default: Any = None) -> Any:
    """Load a UTF-8 JSON file, returning ``default`` for absent/invalid files."""
    try:
        candidate = Path(path)
        if not candidate.is_file():
            return default
        with candidate.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default
