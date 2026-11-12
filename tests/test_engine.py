import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.data import TARGET, make_demo_dataset, prepare_data, predictive_features, validate_uci_dataset
from engine.models import (
    model_identity, parity_report, statsmodels_coefficients,
    train_python_models, train_statsmodels_logistic,
)
from engine.monitoring import monitor_batches
from engine.pipeline import build_monitoring_batches, generate_agent_reports
from engine.risk import build_risk_findings
from engine.validation import age_group_fairness, feature_psi, performance_metrics, psi
from engine.monitoring import _psi_band


def test_demo_data_and_split_are_stratified():
    frame = make_demo_dataset(500)
    x_train, x_test, y_train, y_test = prepare_data(frame)
    assert TARGET not in x_train.columns
    assert len(x_train) + len(x_test) == len(frame)
    assert abs(y_train.mean() - y_test.mean()) < 0.1


def test_sensitive_features_are_not_predictors():
    frame = make_demo_dataset(500)
    x_train, _, _, _ = prepare_data(frame)
    model_features = predictive_features(x_train)
    assert "ID" not in model_features
    assert "SEX" not in model_features
    assert "AGE" not in model_features
    assert {"SEX", "AGE"}.issubset(x_train.columns)


def test_official_dataset_contract_validator():
    frame = pd.DataFrame(
        {
            "ID": np.arange(30000),
            **{f"feature_{index}": np.ones(30000) for index in range(1, 22)},
            "SEX": np.ones(30000),
            "AGE": np.full(30000, 35),
            TARGET: np.array([0] * 23300 + [1] * 6700),
        }
    )
    result = validate_uci_dataset(frame)
    assert result["row_count"] == 30000
    assert result["original_input_variable_count"] == 23
    assert result["missing_value_count"] == 0


def test_models_and_self_parity():
    frame = make_demo_dataset(500)
    x_train, x_test, y_train, _ = prepare_data(frame)
    models = train_python_models(x_train, y_train)
    report = parity_report(models["python_logistic_regression"], models["python_logistic_regression"], x_test)
    assert report["label_agreement"] == 1.0
    assert set(models) == {"python_logistic_regression", "random_forest", "gradient_boosting"}


def test_statsmodels_logit_is_available_and_predicts():
    frame = make_demo_dataset(500)
    x_train, x_test, y_train, _ = prepare_data(frame)
    model = train_statsmodels_logistic(x_train, y_train)
    assert len(model.predict(x_test)) == len(x_test)
    assert np.all((model.predict_proba(x_test) >= 0) & (model.predict_proba(x_test) <= 1))


def test_required_metrics_and_psi():
    y_true = pd.Series([0, 1, 1, 0])
    labels = np.array([0, 1, 0, 0])
    probabilities = np.array([0.1, 0.8, 0.4, 0.2])
    metrics = performance_metrics(y_true, labels, probabilities)
    assert set(metrics) == {
        "accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "specificity"
    }
    assert psi(pd.Series([1, 2, 3, 4]), pd.Series([2, 3, 4, 5])) >= 0
    assert feature_psi(pd.DataFrame({"x": [1, 2]}), pd.DataFrame({"x": [2, 3]}))["x"] >= 0


def test_monitoring_emits_drift_alert():
    reference = pd.DataFrame({"x": np.arange(100, dtype=float)})
    batches = [pd.DataFrame({"x": np.arange(100, dtype=float) + 100}) for _ in range(3)]
    result = monitor_batches(
        reference, np.full(100, 0.2), batches, [np.full(100, 0.8)] * 3
    )
    assert all(batch["alert"] for batch in result["batches"])
    assert all(batch["alerts"] for batch in result["batches"])


def test_monitoring_uses_exact_scenarios_and_severity_bands():
    frame = make_demo_dataset(500)
    _, x_test, _, _ = prepare_data(frame)
    batches = build_monitoring_batches(x_test)
    assert batches[0].equals(x_test)
    assert np.allclose(batches[1]["LIMIT_BAL"], x_test["LIMIT_BAL"] * 0.65)
    assert np.allclose(batches[1]["BILL_AMT1"], x_test["BILL_AMT1"] * 1.5)
    assert np.allclose(batches[2]["LIMIT_BAL"], x_test["LIMIT_BAL"] * 0.4)
    assert np.array_equal(batches[2]["PAY_0"], x_test["PAY_0"] + 2)
    assert np.allclose(batches[2]["BILL_AMT1"], x_test["BILL_AMT1"] * 2)


def test_statsmodels_identity_is_deterministic():
    frame = make_demo_dataset(500)
    x_train, x_test, y_train, _ = prepare_data(frame)
    first = train_statsmodels_logistic(x_train, y_train)
    second = train_statsmodels_logistic(x_train, y_train)
    assert model_identity(first) == model_identity(second)
    assert set(first.feature_names).isdisjoint({"ID", "SEX", "AGE"})


def test_psi_bands_and_alert_boundaries(monkeypatch):
    assert [_psi_band(value) for value in (0.05, 0.10, 0.15, 0.22, 0.25, 0.30)] == [
        "low", "warning", "warning", "warning", "warning", "high"
    ]
    reference = pd.DataFrame({"x": [1.0, 2.0]})
    batches = [reference.copy() for _ in range(3)]
    for value, expected in (
        (0.05, "low"), (0.10, "warning"), (0.15, "warning"),
        (0.22, "warning"), (0.25, "warning"), (0.30, "high"),
    ):
        monkeypatch.setattr("engine.monitoring.psi", lambda *_args, **_kwargs: value)
        report = monitor_batches(
            reference, np.array([0.1, 0.2]), batches, [np.array([0.1, 0.2])] * 3
        )
        assert report["batches"][0]["severity"] == expected
        assert report["batches"][0]["alert"] is (expected != "low")


def test_age_groups_and_risk_evidence():
    ages = pd.Series([20] * 2 + [35] * 3 + [50] * 4 + [65])
    labels = np.zeros(10, dtype=int)
    y_true = pd.Series([0, 1] * 5)
    sex_ratio = 0.91234
    fairness = {"age_groups": age_group_fairness(y_true, labels, ages), "sex": {
        "disparate_impact": sex_ratio, "by_group": {"1": {"count": 5}, "2": {"count": 5}}
    }}
    findings = build_risk_findings(
        {"recall": 0.4},
        fairness,
        {"batches": [{
            "batch": "002", "alert": True, "severity": "warning",
            "driving_feature": "x", "driving_feature_psi": 0.15,
            "prediction_psi": 0.01, "severity_driver": "feature",
        }]},
        {"r_vs_statsmodels": {"overall_pass": True, "mae": 0.0}},
        {"coefficients": {"x": 0.1}},
        "hash",
    )
    assert all({"id", "category", "severity", "description", "evidence",
                "impact", "remediation", "review_status"} <= set(item) for item in findings)
    assert any(item["category"] == "migration_or_parity" and item["severity"] == "info" for item in findings)
    assert any(item["category"] == "stability_or_drift" and item["severity"] == "warning" for item in findings)
    sex_finding = next(item for item in findings if item["id"] == "sex-selection-diagnostic")
    assert sex_finding["category"] == sex_finding["risk_category"]
    assert sex_finding["evidence"]["disparate_impact"] == sex_ratio
    assert f"{sex_ratio:.3f}" in sex_finding["evidence"]["interpretation"]
    assert "0.907" not in sex_finding["evidence"]["interpretation"]


def test_monitoring_reports_schema_changes_and_missing_values():
    reference = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    changed = pd.DataFrame({"x": [1.0, np.nan], "z": [5.0, 6.0]})
    report = monitor_batches(
        reference,
        np.array([0.1, 0.2]),
        [changed] * 3,
        [np.array([0.1, 0.2])] * 3,
    )
    schema = report["batches"][0]["schema_change"]
    assert schema["changed"] is True
    assert schema["missing_columns"] == ["y"]
    assert schema["extra_columns"] == ["z"]
    assert report["batches"][0]["missing_values"]["x"] == {"count": 1, "rate": 0.5}


def test_generated_parity_metrics_coefficients_and_report_paths():
    migration = json.loads(Path("reports/migration/migration_results.json").read_text())
    validation = json.loads(Path("reports/validation/validation_results.json").read_text())
    parity = migration["r_vs_statsmodels"]
    assert parity["row_alignment_verified"] is True
    assert parity["prediction_correlation"] > 0.99
    assert parity["mae_pass"] is True
    assert parity["max_difference_pass"] is True
    assert parity["overall_pass"] is True
    assert validation["metrics"]["pr_auc"] >= 0.0
    assert validation["explainability"]["coefficients"]
    frame = make_demo_dataset(120)
    x_train, _, y_train, _ = prepare_data(frame)
    assert statsmodels_coefficients(train_statsmodels_logistic(x_train, y_train))


def test_generated_reports_contain_no_absolute_windows_paths():
    report_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("reports").rglob("*.json")
    )
    assert "C:\\Users\\" not in report_text
    assert "C:/Users/" not in report_text


@pytest.mark.parametrize("with_key", [False, True])
def test_agent_reports_run_with_or_without_the_answer_key(tmp_path, monkeypatch, with_key):
    models = tmp_path / "models"
    models.mkdir()
    for name in ("legacy_model.R", "outdated_model_document.md"):
        (models / name).write_text(Path("models", name).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.delenv("MODELTRACE_ANSWER_KEY", raising=False)
    if with_key:  # a fabricated key, outside the repository like the real one
        key = tmp_path / "private" / "discovery_answer_key.json"
        key.parent.mkdir()
        key.write_text(json.dumps({"expected_target": "target"}))
        monkeypatch.setenv("MODELTRACE_ANSWER_KEY", str(key))
    monkeypatch.chdir(tmp_path)
    generate_agent_reports(tmp_path / "reports", {}, {}, {})
    discovery = json.loads((tmp_path / "reports" / "agents" / "discovery.json").read_text())
    assert bool(discovery["metrics"]) is with_key



def test_pipeline_refuses_an_answer_key_inside_the_repository(monkeypatch):
    inside = Path(__file__).resolve().parents[1] / "models" / "discovery_answer_key.json"
    monkeypatch.setenv("MODELTRACE_ANSWER_KEY", str(inside))
    with pytest.raises(ValueError, match="inside the repository"):
        generate_agent_reports(Path("unused"), {}, {}, {})


def test_pipeline_warns_about_a_key_left_at_the_old_location(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    for name in ("legacy_model.R", "outdated_model_document.md"):
        (models / name).write_text(Path("models", name).read_text(encoding="utf-8"), encoding="utf-8")
    (models / "discovery_answer_key.json").write_text(json.dumps({"expected_target": "target"}))
    monkeypatch.delenv("MODELTRACE_ANSWER_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.warns(UserWarning, match="no longer read"):
        generate_agent_reports(tmp_path / "reports", {}, {}, {})
    assert json.loads((tmp_path / "reports" / "agents" / "discovery.json").read_text())["metrics"] == {}
