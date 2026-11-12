"""Produce a migration plan from observed legacy-model evidence."""

from __future__ import annotations

from pathlib import Path

from llm.schemas import AgentResult, Evidence, Finding

from ._common import read_source


class MigrationAgent:
    name = "migration"

    def run(self, source: str | Path) -> AgentResult:
        source_name, text = read_source(source)
        lower = text.lower()
        steps = []
        for marker, step in (("glm", "Reproduce the legacy GLM training contract."),
                             ("logit", "Preserve the logit link."),
                             ("target", "Align the target column before comparison.")):
            if marker in lower:
                steps.append(step)
        evidence = [Evidence(source_name, "Migration step supported by source text", excerpt=step) for step in steps]
        finding = Finding("migration-plan", "Evidence-backed migration steps", "ready" if steps else "blocked",
                           "Steps are included only when their legacy contract is observed.", tuple(evidence),
                           severity="info" if steps else "warning")
        return AgentResult(self.name, "Created a migration plan without asserting parity or unobserved metrics.",
                           [finding], recommendations=steps, evidence=evidence)
