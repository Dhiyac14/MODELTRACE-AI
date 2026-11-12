"""Evidence-backed validation and monitoring risk findings."""

from __future__ import annotations

from typing import Any


def _finding(
    finding_id: str,
    category: str,
    severity: str,
    description: str,
    evidence: Any,
    impact: str,
    remediation: str,
    model_hash: str | None,
) -> dict[str, Any]:
    """Build a finding with category as canonical and risk_category as an alias."""
    return {
        "id": finding_id,
        "category": category,
        "risk_category": category,
        "severity": severity,
        "description": description,
        "evidence": evidence,
        "impact": impact,
        "remediation": remediation,
        "review_status": "open",
        "model_hash": model_hash,
    }


def build_risk_findings(
    metrics: dict[str, float],
    fairness: dict[str, Any],
    monitoring: dict[str, Any],
    parity: dict[str, Any],
    explainability: dict[str, Any] | None = None,
    model_hash: str | None = None,
) -> list[dict[str, Any]]:
    """Create findings only when measured evidence meets a diagnostic condition."""
    findings: list[dict[str, Any]] = []
    if metrics.get("recall", 1.0) < 0.5:
        findings.append(_finding(
            "low-positive-class-recall",
            "performance",
            "high",
            "The migrated logistic model has low positive-class recall.",
            {"recall": metrics["recall"]},
            "Defaults may be missed by the model.",
            "Review threshold, class weighting, and calibration with an independent validator.",
            model_hash,
        ))

    age = fairness.get("age_groups", {})
    age_ratio = age.get("disparate_impact")
    age_groups = age.get("by_group", {})
    if age_ratio is not None and age_ratio < 0.8:
        findings.append(_finding(
            "age-group-selection-diagnostic",
            "fairness",
            "review",
            "Age-group selection rates differ and require human assessment; this is not a legal conclusion.",
            {
                "disparate_impact": age_ratio,
                "by_group": age_groups,
                "sixty_plus_sample_size": age_groups.get("60_plus", {}).get("count"),
                "small_sample_caution": "The 60+ estimate is less reliable because its sample size is small.",
            },
            "Some age groups may receive fewer positive predictions.",
            "Conduct documented human fairness review; do not treat disparate impact as a definitive breach.",
            model_hash,
        ))

    sex = fairness.get("sex", {})
    sex_ratio = sex.get("disparate_impact")
    if sex_ratio is not None:
        findings.append(_finding(
            "sex-selection-diagnostic",
            "fairness",
            "review",
            "SEX disparate impact is recorded as a diagnostic for human assessment.",
            {
                "disparate_impact": sex_ratio,
                "by_group": sex.get("by_group", {}),
                "interpretation": (
                    f"A ratio of {sex_ratio:.3f} is a diagnostic and is not treated "
                    "as an automatic regulatory breach."
                ),
            },
            "Selection-rate differences may warrant additional fairness review.",
            "Review group outcomes, context, and applicable policy with a human assessor.",
            model_hash,
        ))

    parity_result = parity.get("r_vs_statsmodels")
    if parity_result is not None:
        passed = bool(parity_result.get("overall_pass"))
        findings.append(_finding(
            "migration-parity-control",
            "migration_or_parity",
            "info" if passed else "high",
            (
                "R and the frozen Statsmodels candidate passed the parity tolerance."
                if passed
                else "R and the frozen Statsmodels candidate failed the parity tolerance."
            ),
            {"parity": parity_result},
            "A failed parity result could change production decisions.",
            "Require review of row-level differences before migration approval.",
            model_hash,
        ))

    for batch in monitoring.get("batches", []):
        if batch.get("alert"):
            driving = batch.get("driving_feature")
            feature_value = batch.get("driving_feature_psi")
            prediction_value = batch.get("prediction_psi")
            source = (
                "prediction distribution"
                if batch.get("severity_driver") == "prediction"
                else f"input feature {driving}"
            )
            findings.append(_finding(
                f"monitoring-{batch['batch']}-drift",
                "stability_or_drift",
                batch["severity"],
                f"Batch {batch['batch']} has {source} drift.",
                {
                    "batch": batch["batch"],
                    "driving_feature": driving,
                    "driving_feature_psi": feature_value,
                    "prediction_psi": prediction_value,
                    "severity_driver": batch.get("severity_driver"),
                },
                "Observed drift may invalidate model assumptions.",
                "Investigate the affected batch and obtain human approval before escalation.",
                model_hash,
            ))

    coefficients = (explainability or {}).get("coefficients", {})
    shap_evidence = {
        key: value
        for key, value in (explainability or {}).items()
        if key.endswith("_shap")
    }
    if coefficients or shap_evidence:
        findings.append(_finding(
            "model-explainability-evidence",
            "explainability",
            "info",
            "Measured coefficient and SHAP evidence is available for reviewer assessment.",
            {
                "coefficients": coefficients,
                "shap": shap_evidence,
            },
            "Unreviewed model behavior can limit effective challenge.",
            "Review coefficient direction and SHAP feature importance before deployment.",
            model_hash,
        ))

    return findings
