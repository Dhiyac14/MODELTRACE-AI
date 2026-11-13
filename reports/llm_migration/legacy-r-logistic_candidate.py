"""Python port of models/legacy_model.R (binomial GLM with logit link, fitted by IRLS)."""
from typing import List

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

CLASSIFICATION_THRESHOLD = 0.35
EXCLUDED_COLUMNS = ("row_id", "target", "SEX", "AGE", "ID")
RESPONSE = "target"


def _feature_names(train_df: pd.DataFrame) -> List[str]:
    # R: setdiff(names(train), c("row_id", "target", "SEX", "AGE", "ID"))
    # setdiff keeps the original column order and removes duplicates.
    seen = []
    for name in train_df.columns:
        if name not in EXCLUDED_COLUMNS and name not in seen:
            seen.append(name)
    return seen


def _build_formula(features: List[str]) -> str:
    # R: reformulate(feature_names, response = "target"); intercept kept.
    if not features:
        return RESPONSE + " ~ 1"
    rhs = " + ".join("Q(%r)" % str(name) for name in features)
    return RESPONSE + " ~ " + rhs


def _encode_response(y: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(y) or pd.api.types.is_numeric_dtype(y):
        return y.astype(float)
    # Character response: R factor, first sorted level is failure.
    levels = sorted(y.dropna().unique().tolist())
    out = pd.Series(np.nan, index=y.index, dtype=float)
    mask = y.notna()
    out[mask] = (y[mask] != levels[0]).astype(float)
    return out


def fit(train_df: pd.DataFrame):
    if RESPONSE not in train_df.columns:
        raise ValueError("Train data must contain target")
    features = _feature_names(train_df)
    data = train_df.copy()
    data[RESPONSE] = _encode_response(data[RESPONSE])
    formula = _build_formula(features)
    # missing='drop' mirrors R's default na.action = na.omit.
    model = smf.glm(
        formula,
        data=data,
        family=sm.families.Binomial(link=sm.families.links.Logit()),
        missing="drop",
    )
    result = model.fit(method="IRLS")
    result._legacy_features = features
    return result


def predict_proba(model, df: pd.DataFrame) -> np.ndarray:
    # R: predict(legacy_model, newdata = test, type = "response")
    features = model._legacy_features
    n = len(df)
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out
    if features:
        complete = df[features].notna().all(axis=1).to_numpy()
    else:
        complete = np.ones(n, dtype=bool)
    if complete.any():
        sub = df.loc[complete].copy()
        if RESPONSE not in sub.columns:
            sub[RESPONSE] = 0.0
        preds = model.predict(sub)
        out[complete] = np.asarray(preds, dtype=float)
    return out


def classify(p) -> np.ndarray:
    # R: as.integer(probability >= 0.35)
    p = np.asarray(p, dtype=float)
    return (p >= CLASSIFICATION_THRESHOLD).astype(int)
