"""Performance, stability, fairness, and explainability metrics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, brier_score_loss, f1_score, precision_score,
    average_precision_score, recall_score, roc_auc_score, confusion_matrix,
)


def performance_metrics(y_true: pd.Series, labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    """Return the required binary classification metrics."""
    tn, fp, fn, tp = confusion_matrix(y_true, labels, labels=[0, 1]).ravel()
    return {
        "accuracy": float(accuracy_score(y_true, labels)),
        "precision": float(precision_score(y_true, labels, zero_division=0)),
        "recall": float(recall_score(y_true, labels, zero_division=0)),
        "f1": float(f1_score(y_true, labels, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "pr_auc": float(average_precision_score(y_true, probabilities)),
        "brier": float(brier_score_loss(y_true, probabilities)),
        "specificity": float(tn / (tn + fp)) if tn + fp else 0.0,
    }


def _bin_edges(reference: pd.Series, bins: int) -> np.ndarray:
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        minimum, maximum = float(reference.min()), float(reference.max())
        edges = np.linspace(minimum - 0.5, maximum + 0.5, bins + 1)
    return edges


def psi(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    """Calculate population stability index using reference quantile bins."""
    if len(reference) == 0 or len(current) == 0:
        raise ValueError("PSI inputs cannot be empty")
    reference = pd.Series(reference).dropna()
    current = pd.Series(current).dropna()
    if len(reference) == 0 or len(current) == 0:
        raise ValueError("PSI inputs must contain at least one non-missing value")
    edges = _bin_edges(reference, bins)
    reference_counts, _ = np.histogram(reference, bins=edges)
    current_counts, _ = np.histogram(current, bins=edges)
    reference_rate = np.clip(reference_counts / len(reference), 1e-6, None)
    current_rate = np.clip(current_counts / len(current), 1e-6, None)
    return float(np.sum((current_rate - reference_rate) * np.log(current_rate / reference_rate)))


def feature_psi(reference: pd.DataFrame, current: pd.DataFrame, bins: int = 10) -> dict[str, float]:
    """Calculate PSI for every shared numeric feature."""
    shared = [column for column in reference.columns if column in current.columns]
    return {column: psi(reference[column], current[column], bins) for column in shared}


def age_group_fairness(
    y_true: pd.Series, labels: np.ndarray, ages: pd.Series
) -> dict[str, Any]:
    """Apply the required Under 30, 30-44, 45-59, and 60+ bands."""
    groups = pd.cut(
        ages,
        bins=[-np.inf, 29, 44, 59, np.inf],
        labels=["under_30", "30_44", "45_59", "60_plus"],
    ).astype(str)
    return fairness_metrics(y_true, labels, groups)


def fairness_metrics(
    y_true: pd.Series, labels: np.ndarray, sensitive_features: pd.Series
) -> dict[str, Any]:
    """Calculate group-level selection rates and disparate impact."""
    values = {}
    for group in sorted(pd.Series(sensitive_features).dropna().unique()):
        mask = np.asarray(sensitive_features) == group
        values[str(group)] = {
            "count": int(mask.sum()),
            "selection_rate": float(np.mean(labels[mask])) if mask.any() else 0.0,
            "true_positive_rate": float(recall_score(np.asarray(y_true)[mask], labels[mask], zero_division=0)),
            "false_positive_rate": float(
                ((labels[mask] == 1) & (np.asarray(y_true)[mask] == 0)).sum()
                / max((np.asarray(y_true)[mask] == 0).sum(), 1)
            ),
        }
    rates = [item["selection_rate"] for item in values.values()]
    result = {
        "by_group": values,
        "demographic_parity_difference": float(max(rates) - min(rates)) if rates else 0.0,
        "disparate_impact": float(min(rates) / max(rates)) if rates and max(rates) else 0.0,
    }
    try:
        from fairlearn.metrics import (
            MetricFrame, false_positive_rate, selection_rate, true_positive_rate,
        )
        frame = MetricFrame(
            metrics={
                "selection_rate": selection_rate,
                "true_positive_rate": true_positive_rate,
                "false_positive_rate": false_positive_rate,
            },
            y_true=y_true,
            y_pred=labels,
            sensitive_features=sensitive_features,
        )
        result["fairlearn"] = {
            "by_group": frame.by_group.to_dict(orient="index"),
            "difference": frame.difference().to_dict(),
            "ratio": frame.ratio().to_dict(),
        }
    except ImportError as exc:
        raise RuntimeError(
            "Fairlearn is required for fairness validation; install the validation extra."
        ) from exc
    return result


def shap_explainability(model: Any, features: pd.DataFrame, sample_size: int = 500) -> dict[str, Any]:
    """Generate mean absolute SHAP values for a tree-based model."""
    try:
        import shap
    except ImportError as exc:
        raise RuntimeError(
            "SHAP is required for tree-model explainability; install the validation extra."
        ) from exc
    sample = features.iloc[:sample_size]
    explanation = shap.TreeExplainer(model).shap_values(sample)
    if isinstance(explanation, list):
        explanation = explanation[-1]
    values = np.asarray(explanation)
    if values.ndim == 3:
        values = values[:, :, -1]
    return {
        "n_rows": int(len(sample)),
        "feature_names": list(sample.columns),
        "mean_abs_shap": {
            name: float(value)
            for name, value in zip(sample.columns, np.mean(np.abs(values), axis=0))
        },
    }


def coefficient_explainability(model: Any, feature_names: list[str]) -> dict[str, float]:
    """Extract logistic coefficients where the estimator exposes them."""
    estimator = getattr(model, "named_steps", {}).get("model", model)
    coefficients = getattr(estimator, "coef_", None)
    if coefficients is None:
        params = getattr(model, "params", None)
        if params is None:
            return {}
        return {
            name: float(params[name])
            for name in feature_names
            if name in params.index
        }
    return {name: float(value) for name, value in zip(feature_names, coefficients[0])}

