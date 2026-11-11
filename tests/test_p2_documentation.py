"""Person 2: Documentation Agent grounding rules and rendering."""
from pathlib import Path

import pytest

from agents.discovery_agent import run_discovery
from agents.documentation_agent import build_model_card, render_markdown, save_model_card, ungrounded_numbers
from inventory.registry import get_record, seed_records
from llm.client import ReplayLLM
from llm.schemas import ModelCardNarrative

ROOT = Path(__file__).resolve().parents[1]
FIX = "tests/fixtures/p2"
VALIDATION_FILE = "reports/validation/validation_results.json"


class OneShot:
    """Fake LLM returning one fixed reply per schema."""

    model = "fake"

    def __init__(self, **replies):
        self.replies = replies

    def structured(self, system, user, schema):
        return self.replies[schema.__name__]


@pytest.fixture(autouse=True)
def at_repo_root(monkeypatch):
    monkeypatch.chdir(ROOT)


@pytest.fixture
def discovery():
    return run_discovery("legacy-r-logistic", [f"{FIX}/legacy_lr_model.R", f"{FIX}/preprocessing_split.py"],
                         ReplayLLM(f"{FIX}/replay_lr"), f"{FIX}/lr_doc_outdated_dev.md")


@pytest.fixture
def record():
    return get_record(seed_records(), "legacy-r-logistic")


def section(card, key):
    return next(s for s in card.sections if s.key == key)


def narrative(**overrides) -> ModelCardNarrative:
    fields = {"overview": "A logistic regression for credit default.", "methodology": "Fitted with glm.",
              "limitations": "Historical data."}
    fields.update(overrides)
    return ModelCardNarrative(**fields)


def test_offline_card_marks_validation_pending(discovery, record):
    card = build_model_card(discovery, record)
    assert card.generated_by.endswith("(template, no LLM)")
    assert card.review_status == "pending_human_review" and card.risk_tier == 1
    for key in ("metrics", "fairness", "stability", "explainability"):
        assert section(card, key).status == "pending" and section(card, key).rows == []
    assert all(s.key != "parity" for s in card.sections)


def test_metrics_are_copied_from_evidence_with_references(discovery, record):
    evidence = {"validation": (VALIDATION_FILE, {"metrics": {"roc_auc": 0.77123, "accuracy": 0.81},
                                                 "fairness": {"sex": {"disparate_impact": 0.93,
                                                                      "fairlearn": {"difference": 0.1}}}})}
    card = build_model_card(discovery, record, evidence)
    perf = section(card, "metrics")
    assert [(r.label, r.value, r.source) for r in perf.rows] == [
        ("roc_auc", "0.7712", f"{VALIDATION_FILE}#metrics.roc_auc"),
        ("accuracy", "0.81", f"{VALIDATION_FILE}#metrics.accuracy"),
    ]
    assert [r.label for r in section(card, "fairness").rows] == ["sex.disparate_impact"]  # fairlearn duplicate skipped
    assert section(card, "stability").status == "pending"


def test_parity_section_appears_with_evidence(discovery, record):
    evidence = {"parity": ("reports/migration/migration_results.json",
                           {"r_vs_statsmodels": {"max_probability_difference": 3.2e-09, "overall_pass": True}})}
    rows = section(build_model_card(discovery, record, evidence), "parity").rows
    assert [(r.label, r.value) for r in rows] == [("r_vs_statsmodels.max_probability_difference", "3.200e-09"),
                                                  ("r_vs_statsmodels.overall_pass", "True")]


def test_invented_metric_falls_back_to_template(discovery, record):
    llm = OneShot(ModelCardNarrative=narrative(overview="The model reaches a ROC-AUC of 0.83 on test data."))
    card = build_model_card(discovery, record, llm=llm)
    overview = section(card, "overview")
    assert overview.source == "template" and "0.83" not in overview.text
    assert any("0.83" in w for w in card.grounding_warnings)
    assert section(card, "methodology").source == "llm_draft"


def test_approval_wording_is_flagged(discovery, record):
    card = build_model_card(discovery, record, llm=OneShot(ModelCardNarrative=narrative(overview="The model has been approved for use.")))
    assert section(card, "overview").source == "llm_draft"
    assert any("approval" in w for w in card.grounding_warnings)


def test_replayed_card_has_no_warnings(discovery, record):
    card = build_model_card(discovery, record, llm=ReplayLLM(f"{FIX}/replay_lr"))
    assert card.grounding_warnings == []
    assert len(section(card, "corrections").rows) == len(discovery.discrepancies) == 9
    governance = {r.label: r.value for r in section(card, "governance").rows}
    assert governance["Risk tier"] == "Tier 1" and governance["Approval records"] == "None recorded"


@pytest.mark.parametrize("text,facts,expected", [
    ("an 80% train split, threshold 0.35, AUC 0.77", '{"train_fraction": 0.8, "decision_threshold": 0.35, "auc": 0.7712}', []),
    ("PAY_0 and BILL_AMT1 under SS1/23, 21 features", "{}", []),
    ("validated in 2022 on 30,000 records", '{"records": "30,000"}', ["2022"]),
    ("Gini of 0.54", '{"auc": 0.77}', ["0.54"]),
])
def test_ungrounded_numbers(text, facts, expected):
    assert ungrounded_numbers(text, facts) == expected


def test_markdown_and_files(tmp_path, discovery, record):
    card = build_model_card(discovery, record)
    json_path, md_path = save_model_card(card, reports_root=tmp_path, cards_dir=tmp_path / "cards")
    assert json_path.exists() and md_path.name == "legacy-r-logistic.md"
    markdown = render_markdown(card)
    assert "**pending_human_review**" in markdown and "| D-001 input_features (contradiction) |" in markdown


def test_card_without_legacy_document(record):
    report = run_discovery("legacy-r-logistic", [f"{FIX}/legacy_lr_model.R"], ReplayLLM(f"{FIX}/replay_lr"))
    assert section(build_model_card(report, record), "corrections").text == "No existing model document was compared."
