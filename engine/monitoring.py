"""Batch monitoring, diagnostics, schema checks, and deterministic alerts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .validation import fairness_metrics, feature_psi, performance_metrics, psi


def _psi_band(value: float) -> str:
    if value < 0.10:
        return "low"
    if value <= 0.25:
        return "warning"
    return "high"


def _missing_report(frame: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    return {
        column: {
            "count": int(frame[column].isna().sum()),
            "rate": float(frame[column].isna().mean()),
        }
        for column in frame.columns
    }


def monitor_batches(
    reference_features: pd.DataFrame,
    reference_probabilities: np.ndarray,
    batches: list[pd.DataFrame],
    batch_probabilities: list[np.ndarray],
    psi_threshold: float | None = None,
    prediction_psi_threshold: float | None = None,
    batch_labels: list[np.ndarray] | None = None,
    batch_groups: list[pd.Series] | None = None,
    reference_labels: np.ndarray | None = None,
    reference_groups: pd.Series | None = None,
    model_hash: str | None = None,
) -> dict[str, Any]:
    """Monitor exactly three batches with explicit severity and diagnostics."""
    if len(batches) != 3 or len(batch_probabilities) != 3:
        raise ValueError("Monitoring requires exactly three batches and probability arrays")
    if batch_labels is not None and len(batch_labels) != 3:
        raise ValueError("batch_labels must contain exactly three arrays")
    if batch_groups is not None and len(batch_groups) != 3:
        raise ValueError("batch_groups must contain exactly three series")

    results = []
    reference_columns = list(reference_features.columns)
    for index, (features, probabilities) in enumerate(
        zip(batches, batch_probabilities), start=1
    ):
        missing_columns = [column for column in reference_columns if column not in features]
        extra_columns = [column for column in features.columns if column not in reference_columns]
        schema_changed = bool(missing_columns or extra_columns or list(features.columns) != reference_columns)
        shared = [column for column in reference_columns if column in features.columns]
        feature_values = {
            column: psi(reference_features[column], features[column])
            for column in shared
        }
        prediction_value = psi(
            pd.Series(reference_probabilities), pd.Series(probabilities)
        )
        feature_bands = {name: _psi_band(value) for name, value in feature_values.items()}
        prediction_band = _psi_band(prediction_value)
        band_order = {"low": 0, "warning": 1, "high": 2}
        driving_feature = max(
            feature_values,
            key=feature_values.get,
            default=None,
        )
        driving_feature_psi = feature_values.get(driving_feature, 0.0)
        feature_severity = feature_bands.get(driving_feature, "low")
        severity = max(
            (feature_severity, prediction_band),
            key=lambda band: band_order[band],
        )
        feature_alerts = {
            name: band != "low" for name, band in feature_bands.items()
        }
        alerts = [f"feature:{name}" for name, alert in feature_alerts.items() if alert]
        if prediction_band != "low":
            alerts.append("prediction")
        result: dict[str, Any] = {
            "batch": f"{index:03d}",
            "feature_psi": feature_values,
            "feature_severity": feature_bands,
            "feature_alerts": feature_alerts,
            "prediction_psi": prediction_value,
            "prediction_severity": prediction_band,
            "driving_feature": driving_feature,
            "driving_feature_psi": float(driving_feature_psi),
            "severity_driver": (
                "prediction" if prediction_value > driving_feature_psi else "feature"
            ),
            "prediction_psi_drove_severity": prediction_value > driving_feature_psi,
            "schema_change": {
                "changed": schema_changed,
                "missing_columns": missing_columns,
                "extra_columns": extra_columns,
            },
            "missing_values": _missing_report(features),
            "mean_predicted_probability": float(np.mean(probabilities)),
            "percentage_above_threshold": float(np.mean(probabilities >= 0.5)),
            "alerts": alerts,
            "severity": severity,
            "alert": severity != "low",
        }
        if batch_labels is not None:
            groups = batch_groups[index - 1] if batch_groups is not None else None
            result["diagnostic_type"] = "simulated_diagnostic"
            result["observed_outcomes"] = False
            result["performance"] = performance_metrics(
                pd.Series(batch_labels[index - 1]),
                (probabilities >= 0.5).astype(int),
                probabilities,
            )
            if groups is not None:
                result["fairness"] = fairness_metrics(
                    pd.Series(batch_labels[index - 1]),
                    (probabilities >= 0.5).astype(int),
                    groups,
                )
        results.append(result)
    severity_counts = {
        level: sum(batch["severity"] == level for batch in results)
        for level in ("low", "warning", "high")
    }
    return {
        "model_hash": model_hash,
        "thresholds": {
            "bands": {"low": "<0.10", "warning": "0.10-0.25", "high": ">0.25"},
            "alert_rule": "alert is true when batch severity is warning or high",
        },
        "summary": {
            "alert_count": sum(batch["alert"] for batch in results),
            "severity_counts": severity_counts,
        },
        "batches": results,
    }
