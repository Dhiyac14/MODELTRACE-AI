"""Summarise measured validation reports; absent measurements remain absent."""

from __future__ import annotations

from pathlib import Path

from llm.schemas import AgentResult, Evidence, Finding

from ._common import load_json


class ValidationAgent:
    name = "validation"

    def run(self, source: str | Path | dict) -> AgentResult:
        source_name, report = load_json(source)
        metrics = report.get("metrics", {})
        if not isinstance(metrics, dict):
            raise ValueError("validation report 'metrics' must be an object")
        evidence = [Evidence(source_name, f"Measured validation metric: {key}", value=value) for key, value in metrics.items()]
        finding = Finding("validation-measurements", "Validation measurements", "observed" if metrics else "unknown",
                           "Only metrics present in the supplied report are reported.", tuple(evidence),
                           severity="info" if metrics else "warning")
        return AgentResult(self.name, "Validation summary contains no fabricated measurements.",
                           [finding], metrics=dict(metrics), evidence=evidence)
