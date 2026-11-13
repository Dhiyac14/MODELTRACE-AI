"""Python port of models/legacy_model.R (binomial GLM with logit link, fitted by IRLS)."""
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm

EXCLUDED_COLUMNS = ("row_id", "target", "SEX", "AGE", "ID")
RESPONSE = "target"
CLASSIFICATION_THRESHOLD = 0.35


def _feature_names(df: pd.DataFrame) -> List[str]:
    # setdiff(names(train), c("row_id", "target", "SEX", "AGE", "ID")), original column order kept
    return [c for c in df.columns if c not in EXCLUDED_COLUMNS]


def _is_numeric(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def _build_spec(df: pd.DataFrame, features: List[str]) -> List[Tuple[str, str, list]]:
    spec = []
    for col in features:
        s = df[col]
        if _is_numeric(s):
            spec.append((col, "numeric", []))
        else:
            # R: character/logical -> factor, treatment contrasts, unused levels dropped
            levels = sorted(pd.unique(s.dropna()).tolist(), key=lambda v: (str(type(v)), v))
            spec.append((col, "categorical", levels))
    return spec


def _design_matrix(df: pd.DataFrame, spec) -> pd.DataFrame:
    cols: Dict[str, np.ndarray] = {"(Intercept)": np.ones(len(df), dtype=float)}
    for col, kind, levels in spec:
        s = df[col]
        if kind == "numeric":
            cols[col] = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
        else:
            missing = s.isna().to_numpy()
            unseen = set(pd.unique(s.dropna()).tolist()) - set(levels)
            if unseen:
                raise ValueError("factor %s has new levels %s" % (col, sorted(map(str, unseen))))
            for lvl in levels[1:]:
                v = (s == lvl).to_numpy(dtype=float)
                v[missing] = np.nan
                cols["%s%s" % (col, "TRUE" if lvl is True else lvl)] = v
    return pd.DataFrame(cols, index=df.index)


def fit(train_df: pd.DataFrame):
    if RESPONSE not in train_df.columns:
        raise ValueError("Train data must contain target")
    features = _feature_names(train_df)
    # glm() default na.action = na.omit over response + predictors
    complete = train_df[[RESPONSE] + features].dropna()
    spec = _build_spec(complete, features)
    X = _design_matrix(complete, spec)
    y = complete[RESPONSE]
    if pd.api.types.is_bool_dtype(y):
        y = y.astype(float)
    y = y.astype(float)
    model = sm.GLM(y, X, family=sm.families.Binomial(link=sm.families.links.Logit()))
    result = model.fit()  # IRLS, as in R glm()
    result._legacy_spec = spec
    result._legacy_columns = list(X.columns)
    return result


def predict_proba(model, df: pd.DataFrame) -> np.ndarray:
    X = _design_matrix(df, model._legacy_spec)[model._legacy_columns]
    params = np.asarray(model.params, dtype=float)
    eta = X.to_numpy(dtype=float) @ params
    # rows with missing predictors yield NaN (R: NA)
    return np.asarray(1.0 / (1.0 + np.exp(-eta)), dtype=float)


def classify(p) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    return (p >= CLASSIFICATION_THRESHOLD).astype(int)
