"""End-to-end Person 1 pipeline producing integration-ready JSON."""

from __future__ import annotations

import json
import os
import subprocess
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .data import (
    GROUP, TARGET, load_official_uci_dataset, make_demo_dataset, predictive_features,
    prepare_data, write_shared_split,
)
from .models import (
    ModelBundle, model_identity, statsmodels_coefficients, train_python_models,
    train_statsmodels_logistic,
)
from .persistence import save_model
from .risk import build_risk_findings
from .monitoring import monitor_batches
from .validation import (
    age_group_fairness, coefficient_explainability, fairness_metrics,
    feature_psi, performance_metrics, psi, shap_explainability,
)


def run_demo(output_root: Path) -> dict:
    """Run a deterministic demo and write migration, validation, and monitoring reports."""
    frame = make_demo_dataset()
    x_train, x_test, y_train, y_test = prepare_data(frame)
    models = train_python_models(x_train, y_train)
    for name, bundle in models.items():
        save_model(bundle.model, Path("models") / "artifacts" / f"{name}.joblib")
    model = models["python_logistic_regression"]
    shared_dir = output_root / "migration" / "shared_data"
    train_path, test_path = write_shared_split(x_train, x_test, y_train, y_test, shared_dir)
    candidate = train_statsmodels_logistic(x_train, y_train)
    migration = run_migration(
        model, x_train, x_test, y_train, train_path, test_path, output_root, candidate
    )
    labels = candidate.predict(x_test)
    probabilities = candidate.predict_proba(x_test)
    candidate_hash = model_identity(candidate)
    validation = {
        "model": candidate.name,
        "metrics": performance_metrics(y_test, labels, probabilities),
        "fairness": {
            "sex": fairness_metrics(y_test, labels, x_test[GROUP]),
            "age_groups": age_group_fairness(y_test, labels, x_test["AGE"]),
        },
        "explainability": {"coefficients": statsmodels_coefficients(candidate)},
        "model_hash": candidate_hash,
        "stability": {
            "feature_psi": feature_psi(predictive_features(x_train), predictive_features(x_test)),
            "prediction_psi": psi(
                pd.Series(candidate.predict_proba(x_train)),
                pd.Series(probabilities),
            ),
        },
    }
    batches = build_monitoring_batches(x_test)
    monitoring = build_monitoring_report(candidate, x_test, y_test, batches, candidate_hash)
    reports = {
        "migration": migration,
        "validation": validation,
        "monitoring": monitoring,
        "risk_findings": build_risk_findings(
            validation["metrics"], validation["fairness"], monitoring, migration,
            validation["explainability"], candidate_hash,
        ),
    }
    for name, report in reports.items():
        path = output_root / name / f"{name}_results.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return reports


def run_migration(
    python_reference: ModelBundle,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    train_path: Path,
    test_path: Path,
    output_root: Path,
    candidate: ModelBundle | None = None,
) -> dict:
    """Run R glm and Statsmodels Logit over the exact same persisted split."""
    candidate = candidate or train_statsmodels_logistic(x_train, y_train)
    candidate_hash = model_identity(candidate)
    statsmodels_labels = candidate.predict(x_test)
    statsmodels_probability = candidate.predict_proba(x_test)
    rscript = "Rscript.exe" if os.name == "nt" else "Rscript"
    if os.name == "nt" and not any(
        Path(directory, rscript).exists()
        for directory in os.environ.get("PATH", "").split(os.pathsep)
        if directory
    ):
        standard_r = sorted(Path("C:/Program Files/R").glob("R-*/bin/Rscript.exe"))
        if standard_r:
            rscript = str(standard_r[-1])
    r_predictions_path = output_root / "migration" / "r_predictions.csv"
    r_predictions_path.parent.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).parents[1] / "models" / "legacy_model.R"
    completed = subprocess.run(
        [rscript, str(script_path), str(train_path), str(test_path), str(r_predictions_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    r_predictions = pd.read_csv(r_predictions_path)
    expected_row_ids = pd.read_csv(test_path)["row_id"].to_numpy()
    row_alignment_verified = np.array_equal(
        r_predictions["row_id"].to_numpy(), expected_row_ids
    )
    if not row_alignment_verified:
        raise ValueError("R and Python test row IDs are not aligned")
    r_probability = r_predictions["probability"].to_numpy()
    r_labels = r_predictions["prediction"].to_numpy()
    python_probability = python_reference.predict_proba(x_test)
    python_labels = python_reference.predict(x_test)
    difference = np.abs(r_probability - statsmodels_probability)
    mae = float(np.mean(difference))
    maximum = float(np.max(difference))
    correlation = float(np.corrcoef(r_probability, statsmodels_probability)[0, 1])
    tolerance = 1e-5
    parity = {
        "row_alignment_verified": row_alignment_verified,
        "mae": mae,
        "mean_probability_difference": mae,
        "max_probability_difference": maximum,
        "prediction_correlation": correlation,
        "classification_agreement": float(np.mean(r_labels == statsmodels_labels)),
        "label_agreement": float(np.mean(r_labels == statsmodels_labels)),
        "label_disagreements": int(np.sum(r_labels != statsmodels_labels)),
        "tolerance": tolerance,
        "threshold": 0.5,
        "mae_pass": mae <= tolerance,
        "max_difference_pass": maximum <= tolerance,
        "overall_pass": bool(row_alignment_verified and mae <= tolerance and maximum <= tolerance),
    }
    return {
        "reference_model": "r_glm_binomial_logit",
        "candidate_model": candidate.name,
        "model_hash": candidate_hash,
        "n_rows": int(len(x_test)),
        "r_vs_statsmodels": parity,
        "r_vs_python": {
            "label_agreement": float(np.mean(r_labels == python_labels)),
            "label_disagreements": int(np.sum(r_labels != python_labels)),
            "max_probability_difference": float(np.max(np.abs(r_probability - python_probability))),
            "mean_probability_difference": float(np.mean(np.abs(r_probability - python_probability))),
        },
        "shared_train_csv": Path(train_path).as_posix(),
        "shared_test_csv": Path(test_path).as_posix(),
        "r_script": "models/legacy_model.R",
        "r_stderr_warning": completed.stderr.strip() or None,
    }


def run_real(output_root: Path, raw_path: Path | None = None) -> dict:
    """Download through ucimlrepo and run the complete UCI pipeline."""
    dataset = load_official_uci_dataset(Path("data") / "provenance.json")
    x_train, x_test, y_train, y_test = prepare_data(dataset)
    models = train_python_models(x_train, y_train)
    for name, bundle in models.items():
        save_model(bundle.model, Path("models") / "artifacts" / f"{name}.joblib")
    model = models["python_logistic_regression"]
    shared_dir = Path("data") / "processed"
    train_path, test_path = write_shared_split(x_train, x_test, y_train, y_test, shared_dir)
    candidate = train_statsmodels_logistic(x_train, y_train)
    candidate_hash = model_identity(candidate)
    migration = run_migration(
        model, x_train, x_test, y_train, train_path, test_path, output_root, candidate
    )
    labels = candidate.predict(x_test)
    probabilities = candidate.predict_proba(x_test)
    validation = {
        "model": candidate.name,
        "metrics": performance_metrics(y_test, labels, probabilities),
        "fairness": {
            "sex": fairness_metrics(y_test, labels, x_test[GROUP]),
            "age_groups": age_group_fairness(y_test, labels, x_test["AGE"]),
        },
        "explainability": {
            "coefficients": statsmodels_coefficients(candidate),
            "random_forest_shap": shap_explainability(
                models["random_forest"].model, x_test[models["random_forest"].feature_names]
            ),
            "gradient_boosting_shap": shap_explainability(
                models["gradient_boosting"].model, x_test[models["gradient_boosting"].feature_names]
            ),
        },
        "model_hash": candidate_hash,
        "stability": {
            "feature_psi": feature_psi(predictive_features(x_train), predictive_features(x_test)),
            "prediction_psi": psi(
                pd.Series(candidate.predict_proba(x_train)),
                pd.Series(probabilities),
            ),
        },
    }
    batches = build_monitoring_batches(x_test)
    monitoring = build_monitoring_report(candidate, x_test, y_test, batches, candidate_hash)
    reports = {
        "migration": migration,
        "validation": validation,
        "monitoring": monitoring,
        "risk_findings": build_risk_findings(
            validation["metrics"], validation["fairness"], monitoring, migration,
            validation["explainability"], candidate_hash,
        ),
    }
    for name, report in reports.items():
        path = output_root / name / f"{name}_results.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    generate_agent_reports(output_root, validation, migration, monitoring)
    return reports


def build_monitoring_batches(x_test: pd.DataFrame) -> list[pd.DataFrame]:
    """Create the three exact independent held-out test-set monitoring scenarios."""
    batches = [x_test.copy(deep=True) for _ in range(3)]
    for batch in batches[1:]:
        for column in ("LIMIT_BAL", "BILL_AMT1"):
            batch[column] = batch[column].astype(float)
    batches[1].loc[:, "LIMIT_BAL"] *= 0.65
    batches[1].loc[:, "BILL_AMT1"] *= 1.5
    batches[2].loc[:, "LIMIT_BAL"] *= 0.4
    batches[2].loc[:, "PAY_0"] += 2
    batches[2].loc[:, "BILL_AMT1"] *= 2
    return batches


def build_monitoring_report(
    candidate: ModelBundle,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    batches: list[pd.DataFrame],
    candidate_hash: str,
) -> dict:
    probabilities = candidate.predict_proba(x_test)
    return monitor_batches(
        predictive_features(x_test),
        probabilities,
        [predictive_features(batch) for batch in batches],
        [candidate.predict_proba(batch) for batch in batches],
        batch_labels=[y_test.to_numpy()] * 3,
        batch_groups=[x_test[GROUP]] * 3,
        model_hash=candidate_hash,
    )


def _answer_key_from_env() -> Path | None:
    """The private answer key named by MODELTRACE_ANSWER_KEY (kept outside the repository), or None.

    Without a usable key Discovery runs unscored. Problems are warnings, not errors: this runs at the end of the
    pipeline, after the other reports are written, and must not leave the agent reports stale.
    """
    from agents.discovery_agent import private_key_path

    key_path = os.environ.get("MODELTRACE_ANSWER_KEY", "").strip()
    old_location = Path("models") / "discovery_answer_key.json"
    if not key_path:
        if old_location.exists():
            warnings.warn(f"{old_location} is no longer read, so Discovery runs unscored. Move the answer key "
                          "outside the repository and set MODELTRACE_ANSWER_KEY to its path.", stacklevel=3)
        return None
    try:
        path = private_key_path(key_path)
    except ValueError as error:
        warnings.warn(f"{error}. Discovery runs unscored.", stacklevel=3)
        return None
    if not path.is_file():
        warnings.warn(f"MODELTRACE_ANSWER_KEY names {key_path}, which does not exist. Discovery runs unscored.",
                      stacklevel=3)
        return None
    return path


def generate_agent_reports(
    output_root: Path,
    validation: dict,
    migration: dict,
    monitoring: dict,
) -> None:
    """Persist deterministic agent envelopes over the latest measured artifacts."""
    from agents.discovery_agent import DiscoveryAgent
    from agents.documentation_agent import DocumentationAgent
    from agents.migration_agent import MigrationAgent
    from agents.monitoring_agent import MonitoringAgent
    from agents.validation_agent import ValidationAgent

    source = Path("models") / "legacy_model.R"
    outputs = {
        "discovery": DiscoveryAgent().run(
            source,
            document=Path("models") / "outdated_model_document.md",
            answer_key=_answer_key_from_env(),
        ).to_dict(),
        "documentation": DocumentationAgent().run(Path("models") / "outdated_model_document.md").to_dict(),
        "migration_agent": MigrationAgent().run(source).to_dict(),
        "validation_agent": ValidationAgent().run(validation).to_dict(),
        "monitoring_agent": MonitoringAgent().run(monitoring).to_dict(),
    }
    for name, result in outputs.items():
        path = output_root / "agents" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    model_card = {
        "model_id": "python-logistic-regression",
        "dataset": "UCI Default of Credit Card Clients, historical Taiwanese demonstration data",
        "unknowns": ["deployment population representativeness", "production calibration"],
        "validation": validation,
        "migration": migration,
        "monitoring": monitoring,
    }
    docs_path = Path("docs") / "model_card.json"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(json.dumps(model_card, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run_real(Path("reports"))

