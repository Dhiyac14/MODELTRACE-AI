"""Model training and parity calculations."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Dict

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import predictive_features

# The legacy R model's decision rule (models/legacy_model.R, CLASSIFICATION_THRESHOLD). The migrated candidate,
# its parity labels, validation, fairness and monitoring all classify with it; a test keeps the two equal.
CLASSIFICATION_THRESHOLD = 0.35


@dataclass
class ModelBundle:
    name: str
    model: Any
    feature_names: list[str]

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model.predict(features[self.feature_names]), dtype=int)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model.predict_proba(features[self.feature_names])[:, 1], dtype=float)


class StatsmodelsAdapter:
    """ModelBundle adapter retaining the fitted Statsmodels parameter identity."""

    def __init__(self, fitted: Any, feature_names: list[str]) -> None:
        self.fitted = fitted
        self.feature_names = feature_names
        self.params = fitted.params
        self.param_names = list(fitted.params.index)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        import statsmodels.api as sm

        values = self.fitted.predict(
            sm.add_constant(features[self.feature_names], has_constant="add")
        )
        values = np.asarray(values, dtype=float)
        return np.column_stack([1 - values, values])

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(features)[:, 1] >= CLASSIFICATION_THRESHOLD).astype(int)


def train_python_models(
    x_train: pd.DataFrame, y_train: pd.Series, seed: int = 42
) -> Dict[str, ModelBundle]:
    """Train the migration target and supporting comparison models."""
    model_features = predictive_features(x_train)
    models: Dict[str, Any] = {
        "python_logistic_regression": Pipeline(
            [("scale", StandardScaler()), ("model", LogisticRegression(max_iter=2000, random_state=seed))]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=150, random_state=seed, n_jobs=-1, class_weight="balanced"
        ),
        "gradient_boosting": GradientBoostingClassifier(random_state=seed),
    }
    bundles = {}
    for name, model in models.items():
        model.fit(model_features, y_train)
        bundles[name] = ModelBundle(name, model, list(model_features.columns))
    return bundles


def train_statsmodels_logistic(
    x_train: pd.DataFrame, y_train: pd.Series
) -> ModelBundle:
    """Train the Statsmodels migration candidate with an intercept."""
    try:
        import statsmodels.api as sm
    except ImportError as exc:
        raise RuntimeError(
            "Statsmodels is required for the migration candidate; install the "
            "'statsmodels' optional dependency."
        ) from exc
    model_features = predictive_features(x_train)
    design = sm.add_constant(model_features, has_constant="add")
    fitted = sm.Logit(y_train, design).fit(disp=False)

    feature_names = list(model_features.columns)
    return ModelBundle(
        "statsmodels_logistic_regression",
        StatsmodelsAdapter(fitted, feature_names),
        feature_names,
    )


def model_identity(bundle: ModelBundle) -> str:
    """Hash canonical Statsmodels parameters and the ordered feature list."""
    parameter_names = list(getattr(bundle.model, "param_names", []))
    parameters = [
        [name, float(bundle.model.params[name])]
        for name in parameter_names
    ]
    canonical = json.dumps(
        {"parameters": parameters, "features": bundle.feature_names},
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def statsmodels_coefficients(bundle: ModelBundle) -> dict[str, float]:
    """Return coefficients from the frozen Statsmodels candidate."""
    if not hasattr(bundle.model, "params"):
        raise TypeError("Statsmodels coefficients require the migration candidate")
    return {
        name: float(bundle.model.params[name])
        for name in bundle.model.param_names
        if name != "const"
    }


def parity_report(
    reference: ModelBundle, candidate: ModelBundle, features: pd.DataFrame
) -> dict[str, Any]:
    """Compare labels and probabilities on exactly the same rows."""
    reference_labels = reference.predict(features)
    candidate_labels = candidate.predict(features)
    reference_probability = reference.predict_proba(features)
    candidate_probability = candidate.predict_proba(features)
    return {
        "reference_model": reference.name,
        "candidate_model": candidate.name,
        "n_rows": int(len(features)),
        "label_agreement": float(np.mean(reference_labels == candidate_labels)),
        "label_disagreements": int(np.sum(reference_labels != candidate_labels)),
        "max_probability_difference": float(np.max(np.abs(reference_probability - candidate_probability))),
        "mean_probability_difference": float(np.mean(np.abs(reference_probability - candidate_probability))),
        "threshold": CLASSIFICATION_THRESHOLD,
    }

