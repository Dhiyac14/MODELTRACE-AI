"""Person 2: Monitoring Agent rules, explanation grounding and alert review workflow."""
import json
from pathlib import Path

import pytest

from agents.monitoring_agent import build_alert_report, derive_alerts, psi_severity, run_monitoring_agent, save_alert_report
from inventory.registry import save_inventory, seed_records
from llm.schemas import AlertExplanation, AlertExplanations
from workflow.approvals import load_users
from workflow.state_machine import Workflow, WorkflowError

ROOT = Path(__file__).resolve().parents[1]
# Copy of Person 1's real report (ml-engineering @ fdad799, engine/monitoring.py).
PERSON1 = ROOT / "tests/fixtures/p2/person1_reports/reports/monitoring/monitoring_results.json"
USERS = {u.user_id: u for u in load_users(ROOT / "governance/users.json")}
DEV, VAL, MRM, MON = (USERS[k] for k in ("dev.alex", "val.sam", "mrm.jordan", "mon.riley"))
LR = "legacy-r-logistic"


class Fake:
    model = "fake"

    def __init__(self, **by_alert):
        self.by_alert = by_alert
        self.prompts = []

    def structured(self, system, user, schema):
        assert schema is AlertExplanations
        self.prompts.append(user)
        ids = [a["alert_id"] for a in json.loads(user.split("\n", 1)[1])["alerts"]]
        return AlertExplanations(items=[self.by_alert[i] for i in ids if i in self.by_alert])


def explanation(alert_id, summary="LIMIT_BAL shifted.", recommendation="investigate"):
    return AlertExplanation(alert_id=alert_id, summary=summary, potential_impact="Scores may be less reliable.",
                            investigate=["Check the feed."], recommendation=recommendation, reason="Drift.")


@pytest.fixture
def report():
    return json.loads(PERSON1.read_text())


@pytest.mark.parametrize("value,severity", [(0.0, "low"), (0.0999, "low"), (0.10, "warning"), (0.25, "warning"),
                                            (0.2501, "high"), (0.9, "high")])
def test_psi_bands(value, severity):
    assert psi_severity(value) == severity


def test_alerts_from_person1_report(report):
    alerts = derive_alerts(LR, report, "m.json")
    assert [(a.batch_id, a.metric, a.feature, a.severity) for a in alerts] == [
        ("002", "feature_psi", "LIMIT_BAL", "high"),
        ("003", "feature_psi", "LIMIT_BAL", "high"),
        ("003", "feature_psi", "PAY_0", "high"),
        ("003", "feature_psi", "BILL_AMT1", "warning"),
        ("003", "prediction_psi", None, "high"),
    ]
    assert alerts[0].alert_id == "legacy-r-logistic:002:feature_psi:LIMIT_BAL"
    assert alerts[0].evidence_ref == "m.json#batches[1].feature_psi.LIMIT_BAL"


def test_rules_agree_with_person1_severities(report):
    """The same PSI bands are implemented twice (engine/monitoring.py and here); they must agree."""
    alerts = derive_alerts(LR, report, "m.json")
    for batch in report["batches"]:
        mine = {a.feature: a.severity for a in alerts if a.batch_id == batch["batch"] and a.metric == "feature_psi"}
        theirs = {f: s for f, s in batch["feature_severity"].items() if s != "low"}
        assert mine == theirs
        prediction = [a.severity for a in alerts if a.batch_id == batch["batch"] and a.metric == "prediction_psi"]
        assert prediction == ([] if batch["prediction_severity"] == "low" else [batch["prediction_severity"]])


def test_schema_and_missing_value_alerts():
    report = {"batches": [{"batch": "004",
                           "schema_change": {"changed": True, "missing_columns": ["PAY_0"], "extra_columns": []},
                           "missing_values": {"AGE": {"count": 3, "rate": 0.001}, "SEX": {"count": 0, "rate": 0.0}}}]}
    assert [(a.metric, a.feature, a.severity, a.value) for a in derive_alerts(LR, report, "m.json")] == [
        ("schema_change", "missing column PAY_0", "high", None), ("missing_values", "AGE", "warning", 3.0)]


def test_template_explanations_without_llm(report):
    result = build_alert_report(LR, report, "m.json", None)
    assert result.generated_by.endswith("(template, no LLM)")
    assert all(a.explanation and a.explanation_source == "template" for a in result.alerts)
    assert {a.explanation.recommendation for a in result.alerts if a.severity == "high"} == {"consider_revalidation"}


def test_prompt_keeps_only_relevant_batch_fields(report):
    llm = Fake()
    build_alert_report(LR, report, "m.json", llm)
    batch = json.loads(llm.prompts[0].split("\n", 1)[1])["batch"]
    assert "feature_psi" in batch and "mean_predicted_probability" in batch
    assert not {"feature_severity", "feature_alerts", "fairness"} & set(batch)


def test_grounded_llm_explanation_is_kept_and_invented_number_rejected(report):
    good = "legacy-r-logistic:003:feature_psi:PAY_0"
    bad = "legacy-r-logistic:003:feature_psi:BILL_AMT1"
    llm = Fake(**{good: explanation(good, "PAY_0 PSI is 5.28, far above 0.25."),
                  bad: explanation(bad, "BILL_AMT1 PSI is 3.75.")})
    result = build_alert_report(LR, report, "m.json", llm)
    sources = {a.alert_id: a.explanation_source for a in result.alerts}
    assert sources[good] == "llm_draft" and sources[bad] == "template"
    assert any("3.75" in w for w in result.warnings)
    assert sum("no explanation" in w for w in result.warnings) == 3  # the other alerts were not answered


def test_high_alert_cannot_be_left_to_monitoring(report):
    alert_id = "legacy-r-logistic:003:feature_psi:PAY_0"
    result = build_alert_report(LR, report, "m.json", Fake(**{alert_id: explanation(alert_id, "PAY_0 shifted.", "monitor")}))
    pay0 = next(a for a in result.alerts if a.alert_id == alert_id)
    assert pay0.explanation.recommendation == "investigate"
    assert any("raised from monitor" in w for w in result.warnings)


def test_run_and_save(tmp_path):
    target = tmp_path / "reports/monitoring/monitoring_results.json"
    target.parent.mkdir(parents=True)
    target.write_text(PERSON1.read_text())
    path = save_alert_report(run_monitoring_agent(LR, None, tmp_path), tmp_path)
    assert path == tmp_path / "reports/alerts" / f"{LR}_alerts.json"
    result = json.loads(path.read_text())
    assert result["source"] == "reports/monitoring/monitoring_results.json" and len(result["alerts"]) == 5


# --------------------------------------------------------------------------- review workflow
@pytest.fixture
def wf(tmp_path):
    (tmp_path / "inventory").mkdir()
    save_inventory(seed_records(), tmp_path / "inventory/model_inventory.json")
    return Workflow(tmp_path)


ALERT = "legacy-r-logistic:003:feature_psi:PAY_0"


def test_review_path_and_roles(wf):
    with pytest.raises(WorkflowError, match="needs role monitoring_analyst"):
        wf.review_alert(LR, ALERT, DEV, "acknowledge")
    wf.review_alert(LR, ALERT, MON, "acknowledge")
    with pytest.raises(WorkflowError, match="comment is required"):
        wf.review_alert(LR, ALERT, MON, "escalate")
    wf.review_alert(LR, ALERT, MON, "escalate", "PAY_0 shifted by two months of arrears.")
    with pytest.raises(WorkflowError, match="Cannot acknowledge"):
        wf.review_alert(LR, ALERT, MON, "acknowledge")
    assert [e.action for e in wf.audit.events()] == ["alert:acknowledge", "alert:escalate"]


def test_revalidation_request_reopens_validate(wf):
    stages = {"discover": ("discovery", DEV), "document": ("model_card", DEV), "redevelop": ("parity", DEV),
              "validate": ("validation", VAL)}
    for stage, (kind, submitter) in stages.items():
        path = wf.artifacts.path(kind, LR)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"r_vs_statsmodels": {"overall_pass": True}}))
        wf.submit(LR, stage, submitter)
        wf.decide(LR, stage, MRM, "approve")
    wf.review_alert(LR, ALERT, MON, "escalate", "Strong drift.")
    wf.review_alert(LR, ALERT, MRM, "request_revalidation", "Re-validate on recent data.")
    assert wf.statuses(LR)["validate"] == "in_progress"
    assert wf.current_stage(LR) == "validate"


def test_revalidation_before_validation_is_only_noted(wf):
    wf.review_alert(LR, ALERT, MON, "escalate", "Strong drift.")
    wf.review_alert(LR, ALERT, MRM, "request_revalidation", "Re-validate.")
    assert wf.statuses(LR)["validate"] == "not_started"
    assert wf.audit.events()[-1].action == "revalidation_noted"
