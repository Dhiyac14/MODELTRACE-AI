"""Identify documentation completeness gaps without filling them with guesses."""

from __future__ import annotations

import re
from pathlib import Path

from llm.schemas import AgentResult, Evidence, Finding

from ._common import read_source


class DocumentationAgent:
    name = "documentation"
    required_sections = ("preprocessing", "data split", "random seed", "dataset version", "fairness assumptions")

    def run(self, source: str | Path) -> AgentResult:
        source_name, text = read_source(source)
        lower = text.lower()
        missing = []
        for section in self.required_sections:
            explicitly_missing = any(
                re.search(r"missing\s*:[^\n]*\b" + re.escape(section) + r"\b", line)
                for line in lower.splitlines()
            )
            if section not in lower or explicitly_missing:
                missing.append(section)
        evidence = [Evidence(source_name, f"Required section '{section}' is absent", value=False) for section in missing]
        findings = [
            Finding("documentation-completeness", "Documentation completeness", "gap" if missing else "complete",
                    f"{len(missing)} of {len(self.required_sections)} required sections are absent.", tuple(evidence),
                    severity="warning" if missing else "info")
        ]
        return AgentResult(self.name, "Documentation was checked against explicit required sections.",
                           findings, recommendations=[f"Document {item} from the authoritative artifact." for item in missing],
                           evidence=evidence)
