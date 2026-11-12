"""Optional export of the pipeline's reports to MLflow for experiment tracking.

Run from the repository root after ``python -m engine.pipeline``::

    pip install mlflow
    python -m governance.mlflow_export
    mlflow ui --backend-store-uri sqlite:///mlflow.db

The report files stay the source of truth: this module only reads them, and nothing else imports it,
so the pipeline, app and tests run without MLflow installed. MLflow runs can be edited or deleted, so
tamper evidence stays with the hash-chained audit log (``workflow/audit.py``); each run records the
chain head, whether the chain verifies, the SS1/23 stage approvals and the SHA-256 of every report it
exported, to tie the run back to that evidence. Setting ``MLFLOW_TRACKING_URI`` to an Azure ML
workspace (with ``azureml-mlflow`` installed) sends the same run there.
"""
from __future__ import annotations

import importlib.util
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workflow.artifacts import PERSON1_MODEL
from workflow.state_machine import Workflow

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACKING_URI = "sqlite:///mlflow.db"
EXPERIMENT = f"modeltrace-{PERSON1_MODEL}"
REQUIRED = ("parity", "validation", "monitoring")
KINDS = (*REQUIRED, "risk_findings", "llm_migration")
FAIRNESS_KEYS = ("demographic_parity_difference", "disparate_impact")
BATCH_KEYS = ("prediction_psi", "mean_predicted_probability", "percentage_above_threshold", "driving_feature_psi")
DATA_SOURCE = "UCI Default of Credit Card Clients (Taiwan, 2005; demonstration only)"


@dataclass
class ExportRun:
    """Everything one MLflow run records; ``batch_metrics[i]`` is logged at step ``i``."""
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    batch_metrics: list[dict[str, float]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)


def _numbers(values: dict[str, Any], prefix: str) -> dict[str, float]:
    """Numeric and boolean entries of a flat dict as ``{prefix.key: float}``."""
    return {f"{prefix}.{k}": float(v) for k, v in values.items() if isinstance(v, (int, float))}


def collect(root: Path = ROOT, model_id: str = PERSON1_MODEL) -> ExportRun:
    """Read the reports, audit chain and approvals under ``root`` into one run (no MLflow needed)."""
    wf = Workflow(root)
    reports = {kind: wf.artifacts.load(kind, model_id) for kind in KINDS}
    missing = [wf.artifacts.relpath(kind, model_id) for kind in REQUIRED if reports[kind] is None]
    if missing:
        raise FileNotFoundError(f"run `python -m engine.pipeline` first; missing {', '.join(missing)}")
    parity, validation, monitoring = (reports[kind] for kind in REQUIRED)
    r_vs_statsmodels = parity.get("r_vs_statsmodels", {})
    run = ExportRun(name=f"{model_id}-{str(validation.get('model_hash'))[:8]}")

    run.params = {
        "model_id": model_id,
        "model": validation.get("model"),
        "model_hash": validation.get("model_hash"),
        "reference_model": parity.get("reference_model"),
        "n_rows": parity.get("n_rows"),
        "parity_tolerance": r_vs_statsmodels.get("tolerance"),
        "decision_threshold": r_vs_statsmodels.get("threshold"),
    }
    run.metrics.update(_numbers(validation.get("metrics", {}), "validation"))
    run.metrics.update(_numbers({k: v for k, v in r_vs_statsmodels.items() if k not in ("tolerance", "threshold")},
                                "parity.r_vs_statsmodels"))
    run.metrics.update(_numbers(parity.get("r_vs_python", {}), "parity.r_vs_python"))
    for attribute, result in validation.get("fairness", {}).items():
        run.metrics.update(_numbers({k: result.get(k) for k in FAIRNESS_KEYS}, f"fairness.{attribute}"))
    run.metrics.update(_numbers({"prediction_psi": validation.get("stability", {}).get("prediction_psi")}, "stability"))

    for batch in monitoring.get("batches", []):
        step = _numbers({k: batch.get(k) for k in BATCH_KEYS}, "monitoring")
        step["monitoring.alert"] = float(bool(batch.get("alert")))
        step.update(_numbers(batch.get("feature_psi", {}), "monitoring.feature_psi"))
        run.batch_metrics.append(step)
        run.tags[f"monitoring.batch_{batch.get('batch')}.severity"] = batch.get("severity")

    findings = reports["risk_findings"]
    if findings is not None:
        run.metrics["risk.findings_total"] = float(len(findings))
        for severity, count in Counter(f.get("severity") for f in findings).items():
            run.metrics[f"risk.findings_{severity}"] = float(count)

    llm = reports["llm_migration"]
    if llm is not None:
        run.params["llm_model"] = llm.get("llm_model")
        run.metrics["llm_migration.passed"] = float(bool(llm.get("passed")))
        run.metrics["llm_migration.attempts"] = float(len(llm.get("attempts", [])))
        run.tags["llm_migration.review_status"] = llm.get("review_status")

    events = wf.audit.events()
    run.tags.update({
        "data_source": DATA_SOURCE,
        "audit.events": str(len(events)),
        "audit.chain_head": events[-1].hash if events else "none",
        "audit.chain_intact": str(not wf.audit.verify()),
        "approval.stale_stages": ",".join(wf.stale_approvals(model_id)) or "none",
        **{f"approval.{stage}": status for stage, status in wf.statuses(model_id).items()},
        **{f"sha256.{kind}": wf.artifacts.sha256(kind, model_id) for kind in KINDS if reports[kind] is not None},
    })

    run.artifacts = [wf.artifacts.relpath(kind, model_id) for kind in KINDS if reports[kind] is not None]
    candidate = (llm or {}).get("candidate_path")
    if candidate and (root / candidate).is_file():
        run.artifacts.append(candidate)

    run.params = {k: v for k, v in run.params.items() if v is not None}
    run.tags = {k: str(v) for k, v in run.tags.items() if v is not None}
    return run


def log_to_mlflow(run: ExportRun, root: Path = ROOT, tracking_uri: str | None = None) -> str:
    """Log ``run`` as one MLflow run and return its run id."""
    import mlflow  # optional dependency: only this function needs it

    mlflow.set_tracking_uri(tracking_uri or os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI))
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=run.name) as active:
        mlflow.log_params(run.params)
        mlflow.set_tags(run.tags)
        mlflow.log_metrics(run.metrics)
        for step, metrics in enumerate(run.batch_metrics):
            mlflow.log_metrics(metrics, step=step)
        for rel in run.artifacts:
            mlflow.log_artifact(str(root / rel), artifact_path=Path(rel).parent.as_posix())
    return active.info.run_id


def main() -> None:
    try:
        run = collect()
    except FileNotFoundError as err:
        raise SystemExit(str(err)) from None
    if importlib.util.find_spec("mlflow") is None:
        raise SystemExit("MLflow is optional and not installed: pip install mlflow")
    run_id = log_to_mlflow(run)
    uri = os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)
    print(f"Logged run {run_id} ({run.name}) to {uri}. View with: mlflow ui --backend-store-uri {uri}")


if __name__ == "__main__":
    main()
