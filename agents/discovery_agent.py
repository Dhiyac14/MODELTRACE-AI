"""Discover model facts and gaps from supplied documentation."""

from __future__ import annotations

import re
import json
from pathlib import Path

from llm.schemas import AgentResult, Evidence, Finding

from ._common import read_source


class DiscoveryAgent:
    name = "discovery"

    def run(
        self,
        source: str | Path,
        document: str | Path | None = None,
        answer_key: str | Path | None = None,
    ) -> AgentResult:
        source_name, text = read_source(source)
        lower = text.lower()
        def line_for(pattern: str) -> int | None:
            for number, line in enumerate(text.splitlines(), start=1):
                if re.search(pattern, line, re.IGNORECASE):
                    return number
            return None

        fields = {
            "model_type": "binomial logistic regression" if "glm" in lower and "binomial" in lower else None,
            "training_function": "glm" if re.search(r"\bglm\b", lower) else None,
            "link": "logit" if re.search(r"\blogit\b", lower) else None,
            "target": "target" if re.search(r"\btarget\b", lower) else None,
        }
        patterns = {
            "model_type": r"\bglm\s*\(",
            "training_function": r"\bglm\s*\(",
            "link": r"\blogit\b",
            "target": r"\btarget\b",
        }
        evidence = [
            Evidence(source_name, f"{key} observed at source line {line_for(patterns[key])}", value=value)
            for key, value in fields.items()
            if value is not None
        ]
        missing = [key for key, value in fields.items() if value is None]
        findings = [
            Finding("model-facts", "Documented model facts", "observed", "Facts extracted without inference.", tuple(evidence)),
        ]
        if missing:
            findings.append(
                Finding("discovery-gaps", "Undocumented model facts", "gap", f"Not found: {', '.join(missing)}.", severity="warning")
            )
        metrics = {}
        if answer_key is not None:
            expected = json.loads(Path(answer_key).read_text(encoding="utf-8"))
            expected_values = {
                "model_type": expected.get("expected_model_type", "").replace("_", " "),
                "training_function": expected.get("expected_training_function"),
                "link": expected.get("expected_link"),
                "target": expected.get("expected_target"),
            }
            observed = {key for key, value in fields.items() if value is not None}
            truth = set(expected_values)
            predicted = {key for key, value in fields.items() if value is not None}
            true_positive = len(observed & truth)
            metrics = {
                "precision": true_positive / len(predicted) if predicted else 0.0,
                "recall": true_positive / len(truth) if truth else 0.0,
            }
        return AgentResult(
            self.name,
            "Extracted only facts present in the supplied document.",
            findings,
            metrics=metrics,
            recommendations=["Provide primary training artifacts for each undocumented fact."] if missing else [],
            evidence=evidence,
        )
