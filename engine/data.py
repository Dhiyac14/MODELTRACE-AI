"""Dataset acquisition and deterministic preprocessing."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
from typing import Tuple
from urllib.request import urlretrieve

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

DATASET_URL = (
    "https://archive.ics.uci.edu/ml/machine-learning-databases/00350/"
    "default%20of%20credit%20card%20clients.xls"
)
TARGET = "default.payment.next.month"
GROUP = "SEX"
AGE = "AGE"
SENSITIVE_FEATURES = (GROUP, AGE)
UCI_DATASET_ID = 350
UCI_SOURCE_URL = "https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients"


def download_dataset(destination: Path, url: str = DATASET_URL) -> Path:
    """Download the UCI workbook unless it already exists."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        urlretrieve(url, destination)
    return destination


def load_dataset(path: Path) -> pd.DataFrame:
    """Load and normalize the UCI workbook, removing its header artifact."""
    frame = pd.read_excel(path, header=1)
    frame = frame.rename(columns={"default payment next month": TARGET})
    if "ID" in frame.columns:
        frame = frame.drop(columns=["ID"])
    if TARGET not in frame.columns:
        raise ValueError(f"Dataset must contain target column {TARGET!r}")
    return frame.dropna().reset_index(drop=True)


def load_official_uci_dataset(provenance_path: Path | None = None) -> pd.DataFrame:
    """Fetch and validate UCI dataset 350 through the official ucimlrepo client."""
    try:
        from ucimlrepo import fetch_ucirepo
    except ImportError as exc:
        raise RuntimeError(
            "ucimlrepo is required for the official UCI dataset. "
            "Install the project dependencies before running the real pipeline."
        ) from exc
    dataset = fetch_ucirepo(id=UCI_DATASET_ID)
    features = dataset.data.features.copy()
    targets = dataset.data.targets.copy()
    expected_features = [
        "LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE",
        "PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6",
        "BILL_AMT1", "BILL_AMT2", "BILL_AMT3", "BILL_AMT4", "BILL_AMT5", "BILL_AMT6",
        "PAY_AMT1", "PAY_AMT2", "PAY_AMT3", "PAY_AMT4", "PAY_AMT5", "PAY_AMT6",
    ]
    if list(features.columns) == [f"X{i}" for i in range(1, 24)]:
        features.columns = expected_features
    if hasattr(dataset.data, "ids") and dataset.data.ids is not None:
        features.insert(0, "ID", dataset.data.ids.iloc[:, 0].to_numpy())
    if TARGET not in targets.columns:
        if targets.shape[1] == 1:
            targets.columns = [TARGET]
        else:
            raise ValueError(f"UCI target column {TARGET!r} was not returned")
    frame = pd.concat([features, targets[[TARGET]]], axis=1)
    validation = validate_uci_dataset(frame)
    if provenance_path is not None:
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance = {
            "dataset": "UCI Default of Credit Card Clients",
            "uci_dataset_id": UCI_DATASET_ID,
            "source_url": UCI_SOURCE_URL,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "download_method": "ucimlrepo.fetch_ucirepo(id=350)",
            "package": "ucimlrepo",
            "validation": validation,
        }
        provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return frame.reset_index(drop=True)


def validate_uci_dataset(frame: pd.DataFrame) -> dict[str, object]:
    """Validate the official dataset contract before any split or training."""
    required = {"ID", GROUP, AGE, TARGET}
    missing_columns = sorted(required.difference(frame.columns))
    default_rate = float(frame[TARGET].mean()) if TARGET in frame.columns else None
    result: dict[str, object] = {
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "original_input_variable_count": int(len(frame.columns) - 2),
        "target": TARGET,
        "default_rate": default_rate,
        "missing_value_count": int(frame.isna().sum().sum()),
        "missing_columns": missing_columns,
        "has_expected_shape": len(frame) == 30_000 and len(frame.columns) == 25,
        "has_expected_target": TARGET in frame.columns,
        "default_rate_approximately_22_percent": (
            default_rate is not None and 0.20 <= default_rate <= 0.24
        ),
    }
    if missing_columns or not result["has_expected_shape"] or not result["has_expected_target"]:
        raise ValueError(f"Official UCI dataset failed validation: {result}")
    if result["missing_value_count"] != 0:
        raise ValueError(f"Official UCI dataset contains missing values: {result}")
    if not result["default_rate_approximately_22_percent"]:
        raise ValueError(f"Unexpected UCI default rate: {result}")
    return result


def make_demo_dataset(n_samples: int = 1200, seed: int = 42) -> pd.DataFrame:
    """Create a deterministic local fixture when the external UCI file is unavailable."""
    rng = np.random.default_rng(seed)
    sex = rng.integers(1, 3, n_samples)
    limit = rng.normal(160_000, 70_000, n_samples).clip(10_000, 1_000_000)
    age = rng.normal(35, 9, n_samples).clip(21, 75).round()
    bill = (limit * rng.uniform(0.1, 0.9, n_samples)).clip(0)
    pay = rng.integers(-2, 4, n_samples)
    logit = -1.0 - limit / 350_000 + pay * 0.55 + (age < 25) * 0.7
    probability = 1 / (1 + np.exp(-logit))
    target = rng.binomial(1, probability)
    return pd.DataFrame(
        {"LIMIT_BAL": limit, "AGE": age, "BILL_AMT1": bill, "PAY_0": pay,
         GROUP: sex, TARGET: target}
    )


def prepare_data(
    frame: pd.DataFrame, test_size: float = 0.2, seed: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Split features and target with stratification and stable ordering."""
    if not 0 < test_size < 1:
        raise ValueError("test_size must be between 0 and 1")
    features = frame.drop(columns=[TARGET])
    target = frame[TARGET].astype(int)
    return train_test_split(
        features, target, test_size=test_size, random_state=seed, stratify=target
    )


def predictive_features(features: pd.DataFrame) -> pd.DataFrame:
    """Remove identifiers and fairness-only attributes from model predictors."""
    excluded = [column for column in ("ID", *SENSITIVE_FEATURES) if column in features.columns]
    return features.drop(columns=excluded)


def write_shared_split(
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    directory: Path,
) -> tuple[Path, Path]:
    """Write the exact train/test rows consumed by both Python and R."""
    directory.mkdir(parents=True, exist_ok=True)
    train = x_train.copy()
    train.insert(0, "row_id", train.index.astype(int))
    train["target"] = y_train
    test = x_test.copy()
    test.insert(0, "row_id", test.index.astype(int))
    test["target"] = y_test
    train_path = directory / "train.csv"
    test_path = directory / "test.csv"
    train.to_csv(train_path, index=False)
    test.to_csv(test_path, index=False)
    return train_path, test_path


def age_groups(values: pd.Series) -> pd.Series:
    """Create the four documented fairness age bands."""
    return pd.cut(
        values,
        bins=[-np.inf, 24, 34, 44, np.inf],
        labels=["under_25", "25_34", "35_44", "45_plus"],
    ).astype(str)

