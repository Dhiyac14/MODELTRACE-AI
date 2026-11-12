"""Python port of models/legacy_model.R (logistic regression via statsmodels GLM).

R reference:
    feature_names <- setdiff(names(train), c("row_id", "target", "SEX", "AGE", "ID"))
    formula <- reformulate(feature_names, response = "target")
    legacy_model <- glm(formula, data = train, family = binomial(link = "logit"))
    probability <- predict(legacy_model, newdata = test, type = "response")
    prediction <- as.integer(probability >= 0.5)
"""

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm

EXCLUDED_COLUMNS = ("row_id", "target", "SEX", "AGE", "ID")
RESPONSE = "target"
THRESHOLD = 0.5


class LegacyModel:
    """Container for the fitted GLM plus the design specification."""

    def __init__(self, result, specs, exog_names):
        self.result = result
        self.specs = specs  # list of (column_name, levels or None)
        self.exog_names = exog_names
        self.params = result.params

    def summary(self):
        return self.result.summary()


def _feature_names(train_df: pd.DataFrame) -> List[str]:
    # setdiff() keeps the original column order and removes duplicates.
    seen = []
    for name in train_df.columns:
        if name not in EXCLUDED_COLUMNS and name not in seen:
            seen.append(name)
    return seen


def _is_categorical(series: pd.Series) -> bool:
    # Numeric and logical columns enter the model as-is; character columns
    # are turned into factors by R's model.frame.
    return not (pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series))


def _design(df: pd.DataFrame, specs: List[Tuple[str, Optional[List[str]]]]) -> pd.DataFrame:
    n = len(df)
    cols = {"(Intercept)": np.ones(n, dtype=float)}
    for name, levels in specs:
        if levels is None:
            cols[name] = pd.to_numeric(df[name], errors="coerce").astype(float).to_numpy()
        else:
            values = df[name]
            missing = values.isna().to_numpy()
            str_values = values.astype(str)
            unseen = set(str_values[~missing]) - set(levels)
            if unseen:
                raise ValueError(
                    "factor %s has new levels %s" % (name, ", ".join(sorted(unseen)))
                )
            for level in levels[1:]:
                col = (str_values == level).astype(float).to_numpy()
                col[missing] = np.nan
                cols[name + level] = col
    return pd.DataFrame(cols, index=df.index)


def _response(y: pd.Series) -> np.ndarray:
    if pd.api.types.is_bool_dtype(y):
        return y.astype(float).to_numpy()
    if pd.api.types.is_numeric_dtype(y):
        return y.astype(float).to_numpy()
    # Factor response: first (sorted) level is failure, all others success.
    levels = sorted(y.astype(str).unique())
    return (y.astype(str) != levels[0]).astype(float).to_numpy()


def fit(train_df: pd.DataFrame) -> LegacyModel:
    if RESPONSE not in train_df.columns:
        raise ValueError("Train data must contain target")
    features = _feature_names(train_df)

    # na.action = na.omit: drop rows with NA in any model variable.
    used = [RESPONSE] + features
    complete = train_df.loc[train_df[used].notna().all(axis=1)]

    specs: List[Tuple[str, Optional[List[str]]]] = []
    for name in features:
        if _is_categorical(complete[name]):
            levels = sorted(complete[name].astype(str).unique())
            specs.append((name, levels))
        else:
            specs.append((name, None))

    X = _design(complete, specs)
    y = _response(complete[RESPONSE])
    model = sm.GLM(y, X, family=sm.families.Binomial(link=sm.families.links.Logit()))
    result = model.fit(method="IRLS")
    return LegacyModel(result, specs, list(X.columns))


def predict_proba(model: LegacyModel, df: pd.DataFrame) -> np.ndarray:
    X = _design(df, model.specs)[model.exog_names].to_numpy(dtype=float)
    params = np.asarray(model.params, dtype=float)
    eta = X @ params  # rows with missing predictors give NaN, like R's NA
    with np.errstate(over="ignore", invalid="ignore"):
        prob = 1.0 / (1.0 + np.exp(-eta))
    return np.asarray(prob, dtype=float).reshape(-1)


def classify(p) -> np.ndarray:
    p = np.asarray(p, dtype=float).reshape(-1)
    return (p >= THRESHOLD).astype(int)
