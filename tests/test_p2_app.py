"""Person 2: the Streamlit dashboard renders every section and drives the approval workflow."""
import json
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agents.llm_migration_agent import save_migration_report
from inventory.registry import save_inventory, seed_records
from llm.schemas import CandidateParity, DiscoveryReport, MigrationAttempt, MigrationReport
from workflow.approvals import load_users
from workflow.state_machine import Workflow

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ["Executive Overview", "Discovery", "Documentation", "Migration", "Validation",
            "Risk & Evidence", "Monitoring", "Governance"]
USER_INDEX = {"dev.alex": 0, "val.sam": 1, "mrm.jordan": 2, "mon.riley": 3, "lead.taylor": 4}


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """A private copy of the data the app reads, so tests never touch the real governance logs."""
    for rel in ("governance/users.json", "governance/ss1_23_mapping.json",
                "reports/discovery/legacy-r-logistic_discovery.json", "tests/fixtures/p2"):
        src, dest = ROOT / rel, tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest) if src.is_dir() else shutil.copy(src, dest)
    (tmp_path / "inventory").mkdir()
    save_inventory(seed_records(), tmp_path / "inventory/model_inventory.json")
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("MODELTRACE_ROOT", str(tmp_path))
    for name in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"):  # never call a real LLM from tests
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def app(section, model="legacy-r-logistic", user="dev.alex", samples=False) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state["section"] = section
    at.session_state["model"] = model
    at.session_state["user"] = USER_INDEX[user]
    at.session_state["samples"] = samples
    return at.run()


@pytest.mark.parametrize("samples", [False, True])
@pytest.mark.parametrize("section", SECTIONS)
def test_every_section_renders(data_root, section, samples):
    at = app(section, samples=samples)
    assert not at.exception
    sample_banners = [w for w in at.warning if "SAMPLE DATA" in w.value]
    uses_person1_data = section in ("Migration", "Validation", "Monitoring")
    assert bool(sample_banners) == (samples and uses_person1_data)


def test_python_model_has_no_redevelopment(data_root):
    at = app("Migration", model="python-gradient-boosting")
    assert any("already implemented in Python" in i.value for i in at.info)


def test_submit_and_approve_through_the_ui(data_root):
    at = app("Discovery", user="dev.alex")
    assert at.button(key="approve-legacy-r-logistic-discover").disabled  # nothing submitted, and wrong role
    at.button(key="submit-legacy-r-logistic-discover").click().run()
    assert not at.exception and any("submitted for review" in s.value for s in at.success)

    at = app("Discovery", user="mrm.jordan")
    at.button(key="approve-legacy-r-logistic-discover").click().run()
    assert any("'Approve' recorded" in s.value for s in at.success)

    records = json.loads((data_root / "governance/approval_log.json").read_text())
    assert [(r["action"], r["actor"]) for r in records] == [("submit", "dev.alex"), ("approve", "mrm.jordan")]
    inventory = json.loads((data_root / "inventory/model_inventory.json").read_text())
    assert inventory[0]["tier_status"] == "approved" and inventory[0]["lifecycle_stage"] == "document"

    at = app("Governance", user="mrm.jordan")
    assert any("Audit chain intact: 2 events" in s.value for s in at.success)


def test_sample_data_cannot_satisfy_a_gate(data_root):
    users = {u.user_id: u for u in load_users(data_root / "governance/users.json")}
    wf = Workflow(data_root)
    card = wf.artifacts.path("model_card", "legacy-r-logistic")
    card.parent.mkdir(parents=True)
    card.write_text("{}")
    for stage in ("discover", "document"):
        wf.submit("legacy-r-logistic", stage, users["dev.alex"])
        wf.decide("legacy-r-logistic", stage, users["mrm.jordan"], "approve")

    at = app("Migration", user="dev.alex", samples=True)
    assert any("Parity tests passed" in s.value for s in at.success)  # the sample says passed...
    assert at.button(key="submit-legacy-r-logistic-redevelop").disabled          # ...but it is not live evidence
    assert any("No evidence yet: reports/migration/migration_results.json" in m.value for m in at.markdown)


def test_migration_page_shows_the_llm_candidate(data_root):
    at = app("Migration")
    assert at.button(key="run-llm-migration").disabled  # no LLM and no Person 1 split in tests
    assert any("No LLM migration report yet" in i.value for i in at.info)

    parity = CandidateParity(row_alignment_verified=True, n_rows=6000, mae=1e-8, max_probability_difference=4e-7,
                             label_agreement=1.0, label_disagreements=0, tolerance=1e-5, mae_pass=True,
                             max_difference_pass=True, overall_pass=True)
    attempts = [MigrationAttempt(round=1, python_code="def fit(df): ...", code_sha256="a", run_error="KeyError: 'x'"),
                MigrationAttempt(round=2, python_code="def fit(df): ...", code_sha256="b", parity=parity, passed=True)]
    save_migration_report(MigrationReport(
        model_id="legacy-r-logistic", r_source="models/legacy_model.R", train_csv="data/processed/train.csv",
        test_csv="data/processed/test.csv", r_predictions_csv="reports/migration/r_predictions.csv", tolerance=1e-5,
        isolation="separate process", attempts=attempts, passed=True, llm_model="fake"), data_root)
    at = app("Migration")
    assert not at.exception
    assert any("LLM candidate matches R within tolerance 1e-05 after 2 round(s)" in s.value for s in at.success)


def test_documentation_agent_runs_from_the_ui(data_root):
    at = app("Documentation", user="dev.alex")
    at.button(key="run-docs").click().run()
    assert not at.exception
    card = json.loads((data_root / "reports/documentation/legacy-r-logistic_model_card.json").read_text())
    assert card["generated_by"] == "Documentation Agent (template, no LLM)"
    events = json.loads((data_root / "governance/audit_log.json").read_text())
    assert events[-1]["actor"] == "agent:documentation" and events[-1]["details"]["triggered_by"] == "dev.alex"


def test_discovery_page_shows_the_discrepancy_score(data_root):
    from agents.discovery_agent import score_discovery
    report = DiscoveryReport.model_validate_json((data_root / "reports/discovery/legacy-r-logistic_discovery.json").read_text())
    key = {"discrepancies": {"legacy-r-logistic": [  # fabricated; the real key stays with Person 1
        {"id": "K-1", "field": "input_features", "type": "omission", "description": ""},
        {"id": "K-2", "field": "decision_threshold", "type": "contradiction", "description": ""}]}}
    score_path = data_root / "reports/discovery/legacy-r-logistic_score.json"
    score_path.write_text(json.dumps(score_discovery(report, key)))

    at = app("Discovery")
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Discrepancy recall"] == "0.50" and metrics["Detected without evidence"] == "0"
    rows = next(d.value for d in at.dataframe if "Score" in d.value.columns).set_index("ID")
    assert rows.loc["D-001", "Score"] == "detected" and rows.loc["D-001", "Evidence check"] == "verified"
    assert not any("earlier Discovery report" in w.value for w in at.warning)

    score_path.write_text(json.dumps({**json.loads(score_path.read_text()), "report_generated_at": "2026-01-01T00:00:00+00:00"}))
    stale = app("Discovery")
    assert any("per-row results are hidden" in w.value for w in stale.warning)
    assert not any("Score" in d.value.columns for d in stale.dataframe)  # ids may now name other discrepancies


def test_gradient_boosting_score_without_expected_metadata(data_root):
    from agents.discovery_agent import score_discovery
    rel = "reports/discovery/python-gradient-boosting_discovery.json"
    shutil.copy(ROOT / rel, data_root / rel)
    report = DiscoveryReport.model_validate_json((data_root / rel).read_text())
    key = {"expected_link": "logit", "discrepancies": {"python-gradient-boosting": []}}  # fabricated control key
    (data_root / "reports/discovery/python-gradient-boosting_score.json").write_text(json.dumps(score_discovery(report, key)))

    at = app("Discovery", model="python-gradient-boosting")
    assert not at.exception
    assert any("Facts not scored" in c.value for c in at.caption)
    metrics = {m.label: m.value for m in at.metric}
    assert "Fact recall vs answer key" not in metrics and metrics["Discrepancy precision"] == "n/a"
