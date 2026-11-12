"""Person 2: optional MLflow export of the pipeline reports (only the last test needs MLflow)."""
import json
import shutil
from pathlib import Path

import pytest

from governance.mlflow_export import EXPERIMENT, collect, log_to_mlflow
from inventory.registry import save_inventory, seed_records
from workflow.state_machine import Workflow

ROOT = Path(__file__).resolve().parents[1]
MODEL = "legacy-r-logistic"


@pytest.fixture
def root(tmp_path):
    """Copies of Person 1's reports plus a seeded inventory; no real governance logs are touched."""
    shutil.copytree(ROOT / "tests/fixtures/p2/person1_reports/reports", tmp_path / "reports")
    (tmp_path / "inventory").mkdir()
    save_inventory(seed_records(), tmp_path / "inventory/model_inventory.json")
    return tmp_path


def test_collect_logs_parity_fairness_and_one_step_per_batch(root):
    run = collect(root)
    validation = json.loads((root / "reports/validation/validation_results.json").read_text())
    batches = json.loads((root / "reports/monitoring/monitoring_results.json").read_text())["batches"]
    assert run.params["model_hash"] == validation["model_hash"]
    assert run.metrics["validation.roc_auc"] == validation["metrics"]["roc_auc"]
    assert run.metrics["parity.r_vs_statsmodels.overall_pass"] == 1.0
    for attribute in validation["fairness"]:
        assert f"fairness.{attribute}.disparate_impact" in run.metrics
    assert len(run.batch_metrics) == len(batches)
    assert [step["monitoring.prediction_psi"] for step in run.batch_metrics] == [b["prediction_psi"] for b in batches]
    assert run.tags[f"monitoring.batch_{batches[-1]['batch']}.severity"] == batches[-1]["severity"]


def test_collect_ties_the_run_to_the_audit_chain_and_approvals(root):
    audit = Workflow(root).audit
    for action in ("submit", "approve"):
        audit.record(actor="val.sam", role="validator", action=action, model_id=MODEL, stage="discover")
    run = collect(root)
    assert run.tags["audit.events"] == "2"
    assert run.tags["audit.chain_head"] == audit.events()[-1].hash
    assert run.tags["audit.chain_intact"] == "True"
    assert run.tags["approval.discover"] == "not_started"  # audit events alone are not approvals
    assert len(run.tags["sha256.validation"]) == 64

    log = root / "governance/audit_log.json"
    events = json.loads(log.read_text())
    events[0]["actor"] = "someone.else"
    log.write_text(json.dumps(events))
    assert collect(root).tags["audit.chain_intact"] == "False"


def test_collect_adds_the_llm_candidate_when_present(root):
    (root / "reports/llm_migration").mkdir()
    (root / "reports/llm_migration/candidate.py").write_text("# candidate\n")
    (root / f"reports/llm_migration/{MODEL}_llm_migration.json").write_text(json.dumps({
        "llm_model": "claude-opus-5-5", "passed": True, "attempts": [{}, {}],
        "candidate_path": "reports/llm_migration/candidate.py", "review_status": "pending_human_review",
    }))
    run = collect(root)
    assert run.params["llm_model"] == "claude-opus-5-5"
    assert run.metrics["llm_migration.attempts"] == 2.0
    assert "reports/llm_migration/candidate.py" in run.artifacts


def test_collect_requires_the_pipeline_reports(root):
    shutil.rmtree(root / "reports/validation")
    with pytest.raises(FileNotFoundError, match="engine.pipeline"):
        collect(root)


def test_log_to_mlflow_round_trip(root, tmp_path, monkeypatch):
    mlflow = pytest.importorskip("mlflow")
    monkeypatch.chdir(tmp_path)  # MLflow writes local artifacts relative to the working directory
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    run = collect(root)
    run_id = log_to_mlflow(run, root, tracking_uri=uri)

    client = mlflow.tracking.MlflowClient(tracking_uri=uri)
    logged = client.get_run(run_id)
    assert client.get_experiment(logged.info.experiment_id).name == EXPERIMENT
    assert logged.data.params["model_hash"] == run.params["model_hash"]
    assert logged.data.tags["audit.chain_intact"] == "True"
    assert logged.data.metrics["fairness.sex.disparate_impact"] == run.metrics["fairness.sex.disparate_impact"]
    history = client.get_metric_history(run_id, "monitoring.prediction_psi")
    assert [m.step for m in history] == list(range(len(run.batch_metrics)))
    exported = {a.path for folder in ("reports/validation", "reports/monitoring")
                for a in client.list_artifacts(run_id, folder)}
    assert {"reports/validation/validation_results.json", "reports/monitoring/monitoring_results.json"} <= exported
