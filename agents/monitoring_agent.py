"""Monitoring Agent — plan step 13.

Reads Person 1's monitoring report, raises alerts with fixed PSI rules (the LLM never sets severity)
and asks the LLM to explain each alert for a human reviewer. It cannot retrain, replace or deploy a
model: its only output is an alert report. Review actions (acknowledge, investigate, escalate,
request re-validation) are taken by people through ``workflow.state_machine.Workflow.review_alert``.

Usage:
    python -m agents.monitoring_agent --model-id legacy-r-logistic [--no-llm]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from llm.client import StructuredLLM, llm_from_env
from llm.evidence import ungrounded_numbers
from llm.prompts import MONITORING_SYSTEM, monitoring_user
from llm.schemas import Alert, AlertExplanation, AlertExplanations, AgentResult, AlertReport, Evidence, Finding
from workflow.artifacts import Artifacts

from ._common import load_json

PSI_WARNING, PSI_HIGH = 0.10, 0.25
PSI_RULE = ("PSI below 0.10: low; 0.10 to 0.25: warning; above 0.25: high "
            "(illustrative monitoring heuristics, not regulatory thresholds)")

_IMPACT = {
    "feature_psi": "The distribution of {feature} has moved away from the baseline, so predictions that rely on it may be less reliable.",
    "prediction_psi": "The distribution of predicted default probabilities has shifted, so the number of referred accounts may change.",
    "schema_change": "The input data no longer matches the expected schema, so scores may be wrong or missing.",
    "missing_values": "Missing values in {feature} may lead to wrong or missing scores.",
}
_CHECKS = {
    "feature_psi": ["Compare the {feature} distribution in this batch with the baseline.",
                    "Check upstream data feeds and any policy change that affects {feature}.",
                    "Compare default rates with the baseline once labels are available."],
    "prediction_psi": ["Compare the score distribution with the baseline.",
                       "Check which input features drifted in the same batch.",
                       "Review referral volumes against review capacity."],
    "schema_change": ["Check the data pipeline for renamed, added or removed columns.",
                      "Do not use scores from this batch until the schema is confirmed."],
    "missing_values": ["Find where the missing values come from.", "Check how the model treats missing inputs."],
}
_RANK = {"monitor": 0, "investigate": 1, "consider_revalidation": 2}


def psi_severity(value: float) -> str:
    if value > PSI_HIGH:
        return "high"
    if value >= PSI_WARNING:
        return "warning"
    return "low"


def batch_id_of(batch: dict[str, Any]) -> str:
    """Person 1's monitoring report names batches "001", "002", "003"."""
    return str(batch["batch"])


def derive_alerts(model_id: str, report: dict[str, Any], source: str) -> list[Alert]:
    """Deterministic alerts from the numbers in Person 1's monitoring report (engine/monitoring.py)."""
    alerts: list[Alert] = []
    for i, batch in enumerate(report.get("batches", [])):
        batch_id = batch_id_of(batch)
        scenario = batch.get("scenario") or batch.get("diagnostic_type", "")
        ref = f"{source}#batches[{i}]"

        def add(metric: str, feature: str | None, value: float | None, severity: str, rule: str, path: str) -> None:
            alerts.append(Alert(alert_id=f"{model_id}:{batch_id}:{metric}:{feature or '-'}", model_id=model_id,
                                batch_id=batch_id, scenario=scenario, metric=metric, feature=feature, value=value,
                                severity=severity, rule=rule, evidence_ref=f"{ref}.{path}"))

        for feature, psi in (batch.get("feature_psi") or {}).items():
            if psi_severity(psi) != "low":
                add("feature_psi", feature, psi, psi_severity(psi), PSI_RULE, f"feature_psi.{feature}")
        prediction_psi = batch.get("prediction_psi")
        if prediction_psi is not None and psi_severity(prediction_psi) != "low":
            add("prediction_psi", None, prediction_psi, psi_severity(prediction_psi), PSI_RULE, "prediction_psi")
        schema = batch.get("schema_change") or {}
        changes = [f"missing column {c}" for c in schema.get("missing_columns", [])] + \
                  [f"extra column {c}" for c in schema.get("extra_columns", [])]
        if schema.get("changed") and not changes:
            changes = ["schema changed"]
        for change in changes:
            add("schema_change", change, None, "high", "Any schema change is high severity.", "schema_change")
        for feature, missing in (batch.get("missing_values") or {}).items():
            count = missing.get("count", 0) if isinstance(missing, dict) else missing
            if count:
                add("missing_values", feature, float(count), "warning", "Any missing value is a warning.",
                    f"missing_values.{feature}")
    return alerts


_FACT_KEYS = ("batch", "diagnostic_type", "observed_outcomes", "severity", "driving_feature", "driving_feature_psi",
              "feature_psi", "prediction_psi", "mean_predicted_probability", "percentage_above_threshold",
              "schema_change", "performance")


def batch_facts(batch: dict[str, Any]) -> dict[str, Any]:
    """The numbers the LLM may cite; per-feature flags and fairness tables are left out to keep the prompt small."""
    facts = {k: batch[k] for k in _FACT_KEYS if k in batch}
    missing = {f: v for f, v in (batch.get("missing_values") or {}).items()
               if (v.get("count", 0) if isinstance(v, dict) else v)}
    if missing:
        facts["missing_values"] = missing
    return facts


def template_explanation(alert: Alert) -> AlertExplanation:
    feature = alert.feature or "the model output"
    measured = {
        "feature_psi": f"The PSI of {feature} is {alert.value:.3f}" if alert.value is not None else "",
        "prediction_psi": f"The PSI of predicted default probabilities is {alert.value:.3f}" if alert.value is not None else "",
        "schema_change": f"The schema changed: {feature}",
        "missing_values": f"{feature} has {alert.value:g} missing values" if alert.value is not None else "",
    }[alert.metric]
    return AlertExplanation(
        alert_id=alert.alert_id,
        summary=f"{measured} in batch {alert.batch_id} ({alert.scenario or 'no scenario'}), which the fixed rule classes as {alert.severity}.",
        potential_impact=_IMPACT[alert.metric].format(feature=feature),
        investigate=[c.format(feature=feature) for c in _CHECKS[alert.metric]],
        recommendation="consider_revalidation" if alert.severity == "high" else "investigate",
        reason=f"Set by rule from the {alert.severity} severity.",
    )


def explain_alerts(alerts: list[Alert], report: dict[str, Any], llm: StructuredLLM | None) -> tuple[list[Alert], list[str]]:
    """Attach an explanation to every alert: LLM draft if grounded, otherwise the template."""
    def templated(alert: Alert) -> Alert:
        return alert.model_copy(update={"explanation": template_explanation(alert), "explanation_source": "template"})

    if llm is None:
        return [templated(a) for a in alerts], []
    batches = {batch_id_of(b): b for b in report.get("batches", [])}
    out: list[Alert] = []
    warnings: list[str] = []
    for batch_id in dict.fromkeys(a.batch_id for a in alerts):
        group = [a for a in alerts if a.batch_id == batch_id]
        facts = {
            "batch": batch_facts(batches.get(batch_id, {})),
            "alerts": [a.model_dump(include={"alert_id", "metric", "feature", "value", "severity"}) for a in group],
            "psi_thresholds": {"warning": PSI_WARNING, "high": PSI_HIGH},
        }
        facts_json = json.dumps(facts, indent=1)
        drafts = {e.alert_id: e for e in llm.structured(MONITORING_SYSTEM, monitoring_user(facts_json), AlertExplanations).items}
        for alert in group:
            draft = drafts.get(alert.alert_id)
            if draft is None:
                warnings.append(f"{alert.alert_id}: the LLM gave no explanation; template used.")
                out.append(templated(alert))
                continue
            bad = ungrounded_numbers(" ".join([draft.summary, draft.potential_impact, *draft.investigate, draft.reason]), facts_json)
            if bad:
                warnings.append(f"{alert.alert_id}: LLM explanation replaced by template; numbers not in the evidence: {', '.join(bad)}.")
                out.append(templated(alert))
                continue
            if alert.severity == "high" and _RANK[draft.recommendation] < _RANK["investigate"]:
                draft = draft.model_copy(update={
                    "recommendation": "investigate",
                    "reason": f"{draft.reason} (Raised to investigate: a high-severity alert cannot be left to routine monitoring.)",
                })
                warnings.append(f"{alert.alert_id}: recommendation raised from monitor to investigate (high severity).")
            out.append(alert.model_copy(update={"explanation": draft, "explanation_source": "llm_draft"}))
    return out, warnings


def build_alert_report(model_id: str, report: dict[str, Any], source: str, llm: StructuredLLM | None) -> AlertReport:
    alerts, warnings = explain_alerts(derive_alerts(model_id, report, source), report, llm)
    return AlertReport(
        model_id=model_id, source=source, alerts=alerts, warnings=warnings,
        generated_by=f"Monitoring Agent (LLM: {llm.model})" if llm else "Monitoring Agent (template, no LLM)",
    )


def run_monitoring_agent(model_id: str, llm: StructuredLLM | None, root: Path = Path(".")) -> AlertReport:
    artifacts = Artifacts(root)
    report = artifacts.load("monitoring", model_id)
    if report is None:
        raise FileNotFoundError(f"no monitoring report: {artifacts.relpath('monitoring', model_id)}")
    return build_alert_report(model_id, report, artifacts.relpath("monitoring", model_id), llm)


def save_alert_report(report: AlertReport, root: Path = Path(".")) -> Path:
    path = Artifacts(root).path("alerts", report.model_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------ compatibility with Person 1's code
# Verbatim from the ml-engineering branch (commit fdad799), where Person 1's engine/pipeline.py (generate_agent_reports) uses it.
# Kept here so that code keeps working when the two branches are merged.
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Raise and explain monitoring alerts for human review.")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--no-llm", action="store_true", help="template explanations only")
    args = parser.parse_args()
    client = None if args.no_llm else llm_from_env()[0]
    result = run_monitoring_agent(args.model_id, client)
    print(f"wrote {save_alert_report(result)}: {len(result.alerts)} alert(s), {len(result.warnings)} warning(s)")
