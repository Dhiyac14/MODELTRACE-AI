"""SAMPLE placeholder for Person 1's LLM-generated migration candidate (not a real agent output)."""
import numpy as np
import pandas as pd
import statsmodels.api as sm

FEATURES = [
    "LIMIT_BAL", "EDUCATION", "MARRIAGE", "PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6",
    "BILL_AMT1", "BILL_AMT2", "BILL_AMT3", "BILL_AMT4", "BILL_AMT5", "BILL_AMT6",
    "PAY_AMT1", "PAY_AMT2", "PAY_AMT3", "PAY_AMT4", "PAY_AMT5", "PAY_AMT6",
]
TARGET = "default.payment.next.month"
THRESHOLD = 0.35


def fit(train_df: pd.DataFrame):
    X = sm.add_constant(train_df[FEATURES])
    return sm.GLM(train_df[TARGET], X, family=sm.families.Binomial()).fit()


def predict_proba(model, df: pd.DataFrame) -> np.ndarray:
    return np.asarray(model.predict(sm.add_constant(df[FEATURES], has_constant="add")))


def classify(p: np.ndarray) -> np.ndarray:
    return (p > THRESHOLD).astype(int)
