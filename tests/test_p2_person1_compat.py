"""Person 2: interfaces Person 1's code (ml-engineering) relies on, and Person 1's real reports."""
import json
import shutil
from pathlib import Path

import pytest

from agents.discovery_agent import DiscoveryAgent, run_discovery
from agents.documentation_agent import DocumentationAgent, build_model_card, load_evidence
from agents.monitoring_agent import MonitoringAgent
from inventory.registry import get_record, seed_records
from llm.client import ReplayLLM
from llm.schemas import AgentResult, Evidence, Finding
from workflow.artifacts import PERSON1_REPORTS, Artifacts, parity_passed

ROOT = Path(__file__).resolve().parents[1]
FIX = "tests/fixtures/p2"
PERSON1 = ROOT / FIX / "person1_reports"


@pytest.fixture(autouse=True)
def at_repo_root(monkeypatch):
    monkeypatch.chdir(ROOT)


@pytest.fixture
def person1_root(tmp_path):
    """A repository root holding Person 1's real reports at their real paths."""
    shutil.copytree(PERSON1 / "reports", tmp_path / "reports")
    return tmp_path


# --------------------------------------------------------------------------- engine/pipeline.py and agents/*
def test_schema_dataclasses_match_person1():
    result = AgentResult("x", "summary", [Finding("f", "t", "observed", "c", (Evidence("s", "claim", value=1),))])
    assert AgentResult.from_mapping(result.to_dict()).to_dict() == result.to_dict()


def test_pipeline_agent_classes_keep_their_signatures():
    discovery = DiscoveryAgent().run(Path(f"{FIX}/legacy_lr_model.R"), document=Path(f"{FIX}/lr_doc_outdated_dev.md"))
    documentation = DocumentationAgent().run(Path(f"{FIX}/lr_doc_outdated_dev.md"))
    monitoring = MonitoringAgent().run(PERSON1 / PERSON1_REPORTS["monitoring"])
    for result, name in ((discovery, "discovery"), (documentation, "documentation"), (monitoring, "monitoring")):
        assert isinstance(result, AgentResult) and result.to_dict()["agent"] == name
    assert monitoring.metrics == {"batch_count": 3, "alert_count": 2}


# --------------------------------------------------------------------------- Person 1's real reports
def test_artifact_paths_follow_person1_pipeline(person1_root):
    artifacts = Artifacts(person1_root)
    assert artifacts.relpath("parity", "legacy-r-logistic") == "reports/migration/migration_results.json"
    assert artifacts.exists("validation", "legacy-r-logistic")
    assert not artifacts.exists("validation", "python-random-forest")  # Person 1 validates only the migrated model
    assert parity_passed(artifacts.load("parity", "legacy-r-logistic"))


def test_model_card_from_person1_reports(person1_root):
    discovery = run_discovery("legacy-r-logistic", [f"{FIX}/legacy_lr_model.R"], ReplayLLM(f"{FIX}/replay_lr"))
    evidence = load_evidence("legacy-r-logistic", person1_root)
    assert set(evidence) == {"validation", "parity"}
    card = build_model_card(discovery, get_record(seed_records(), "legacy-r-logistic"), evidence)
    sections = {s.key: s for s in card.sections}
    assert all(sections[k].status == "available" for k in ("metrics", "fairness", "stability", "explainability", "parity"))
    metrics = {r.label: r.value for r in sections["metrics"].rows}
    assert metrics["roc_auc"] == "0.707" and metrics["recall"] == "0.2442"
    assert not any("fairlearn" in r.label or "feature_names" in r.label for r in sections["fairness"].rows + sections["explainability"].rows)
    assert all(r.label.startswith("coefficients.") for r in sections["explainability"].rows)  # no other model's SHAP
    assert {r.label: r.value for r in sections["parity"].rows}["r_vs_statsmodels.overall_pass"] == "True"


def test_failed_parity_is_detected():
    report = json.loads((PERSON1 / PERSON1_REPORTS["parity"]).read_text())
    report["r_vs_statsmodels"]["overall_pass"] = False
    assert not parity_passed(report) and not parity_passed(None) and not parity_passed({})


# --------------------------------------------------------------------------- supporting models and scoring
def test_supporting_model_card_shows_only_its_own_shap(person1_root):
    from llm.schemas import DiscoveryReport
    discovery = DiscoveryReport.model_validate_json(
        (ROOT / "reports/discovery/legacy-r-logistic_discovery.json").read_text()).model_copy(update={"model_id": "python-random-forest"})
    evidence = load_evidence("python-random-forest", person1_root)
    assert list(evidence["validation"][1]) == ["explainability"]  # no metrics that belong to the migrated model
    card = build_model_card(discovery, get_record(seed_records(), "python-random-forest"), evidence)
    sections = {s.key: s for s in card.sections}
    assert sections["metrics"].status == "pending" and sections["explainability"].status == "available"
    assert all(r.label.startswith("random_forest_shap.") for r in sections["explainability"].rows)
    assert load_evidence("python-random-forest", person1_root / "absent") == {}


def test_score_discovery_with_a_made_up_key():
    from agents.discovery_agent import score_discovery
    from llm.schemas import DiscoveryReport
    report = DiscoveryReport.model_validate_json((ROOT / "reports/discovery/legacy-r-logistic_discovery.json").read_text())
    key = {"expected_model_type": "binomial_logistic_regression", "expected_link": "logit",  # invented for this test
           "expected_target": "something_else", "expected_owner": "x"}
    score = score_discovery(report, key)
    assert score["matched"] == ["expected_model_type", "expected_link"]
    assert set(score["missed"]) == {"expected_target", "expected_owner"} and score["unmapped_keys"] == ["expected_owner"]
    assert score["recall"] == 0.5 and score["precision"] == 2 / 3
