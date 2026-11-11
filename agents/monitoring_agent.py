"""Summarise observed monitoring batches and alerts."""

from __future__ import annotations

from pathlib import Path

from llm.schemas import AgentResult, Evidence, Finding

from ._common import load_json


class MonitoringAgent:
    name = "monitoring"

    def run(self, source: str | Path | dict) -> AgentResult:
        source_name, report = load_json(source)
        batches = report.get("batches", [])
        if not isinstance(batches, list):
            raise ValueError("monitoring report 'batches' must be an array")
        alert_count = sum(bool(batch.get("alert")) for batch in batches if isinstance(batch, dict))
        evidence = [Evidence(source_name, "Observed monitoring batch count", value=len(batches)),
                    Evidence(source_name, "Observed alert batch count", value=alert_count)]
        finding = Finding("monitoring-observations", "Monitoring observations", "observed" if batches else "unknown",
                           "Counts are calculated from supplied batches only.", tuple(evidence),
                           severity="warning" if alert_count else "info")
        return AgentResult(self.name, "Monitoring summary uses recorded batches and alerts only.",
                           [finding], metrics={"batch_count": len(batches), "alert_count": alert_count}, evidence=evidence)
