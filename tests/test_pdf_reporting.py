import json
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from reporting.data_loader import ReportDataError, ReportDataLoader
from reporting.report_builder import (_governance_stage_status, _governance_section, _migration_status, _status_for,
                                      _styles, _table, build_individual_story, build_portfolio_story,
                                      generate_individual_report, generate_portfolio_report)


ROOT = Path(__file__).resolve().parents[1]
MODEL_IDS = ["legacy-r-logistic", "python-gradient-boosting", "python-random-forest"]


def test_loader_reads_all_inventory_models_and_preserves_missing_evidence():
    portfolio = ReportDataLoader(ROOT).portfolio()
    assert portfolio.inventory_count == 3
    assert [model.model_id for model in portfolio.models] == MODEL_IDS
    assert portfolio.models[0].validation is not None
    assert portfolio.models[1].validation is None
    assert portfolio.models[2].risk_findings == []


def test_loader_rejects_unknown_model():
    with pytest.raises(ReportDataError, match="Unknown model ID"):
        ReportDataLoader(ROOT).model("does-not-exist")


def test_loader_reports_malformed_optional_json(tmp_path):
    inventory = json.loads((ROOT / "inventory/model_inventory.json").read_text(encoding="utf-8"))
    (tmp_path / "inventory").mkdir()
    (tmp_path / "inventory/model_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    (tmp_path / "reports/discovery").mkdir(parents=True)
    (tmp_path / "reports/discovery/legacy-r-logistic_discovery.json").write_text("{", encoding="utf-8")
    with pytest.raises(ReportDataError, match="Unable to read JSON evidence"):
        ReportDataLoader(tmp_path).model("legacy-r-logistic")


def test_loader_rejects_malformed_governance_stages(tmp_path):
    inventory = json.loads((ROOT / "inventory/model_inventory.json").read_text(encoding="utf-8"))
    (tmp_path / "inventory").mkdir()
    (tmp_path / "inventory/model_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    (tmp_path / "governance").mkdir()
    (tmp_path / "governance/ss1_23_mapping.json").write_text('{"stages": "invalid"}', encoding="utf-8")
    with pytest.raises(ReportDataError, match="governance stages"):
        ReportDataLoader(tmp_path).model("legacy-r-logistic")


def test_loader_rejects_malformed_model_card_sections(tmp_path):
    inventory = json.loads((ROOT / "inventory/model_inventory.json").read_text(encoding="utf-8"))
    (tmp_path / "inventory").mkdir()
    (tmp_path / "inventory/model_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    card_path = tmp_path / "reports/documentation"
    card_path.mkdir(parents=True)
    (card_path / "legacy-r-logistic_model_card.json").write_text('{"sections": {"invalid": true}}', encoding="utf-8")
    with pytest.raises(ReportDataError, match="sections"):
        ReportDataLoader(tmp_path).model("legacy-r-logistic")


def _table_values(story):
    values = []
    for flowable in story:
        if not hasattr(flowable, "_cellvalues"):
            continue
        for row in flowable._cellvalues:
            for cell in row:
                values.append(cell.getPlainText() if hasattr(cell, "getPlainText") else cell)
    return values


def test_missing_parity_is_not_automatically_not_applicable():
    data = ReportDataLoader(ROOT).model("legacy-r-logistic")
    data = replace(data, parity=None)
    assert _migration_status(data) == "Not Assessed"
    assert "Not Applicable" not in "".join(str(value) for value in _table_values(build_individual_story(data)))


def test_legacy_recorded_migration_status_is_not_completed_by_parity_evidence():
    data = ReportDataLoader(ROOT).model("legacy-r-logistic")
    assert data.parity is not None
    assert data.record["migration_status"] == "not_started"
    assert _migration_status(data) == "Not Assessed"


def test_python_not_applicable_migration_requires_inventory_metadata():
    data = ReportDataLoader(ROOT).model("python-gradient-boosting")
    assert _migration_status(data) == "Not Applicable"


def test_not_started_governance_status_is_not_source_evidence():
    data = ReportDataLoader(ROOT).model("legacy-r-logistic")
    table = next(flowable for flowable in _governance_section(data, _styles()) if hasattr(flowable, "_cellvalues"))
    statuses = [row[2].getPlainText() for row in table._cellvalues[1:]]
    assert statuses and all(status == "Not recorded" for status in statuses)


def test_current_portfolio_stages_are_all_not_recorded():
    portfolio = ReportDataLoader(ROOT).portfolio()
    table = next(flowable for flowable in build_portfolio_story(portfolio)
                 if hasattr(flowable, "_cellvalues") and flowable._cellvalues[0][0].getPlainText() == "Stage")
    for row in table._cellvalues[1:]:
        assert [cell.getPlainText() for cell in row[2:]] == ["0", "0", "0", "3"]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("approved", "Approved"),
        ("not_applicable", "Not applicable"),
        ("not_started", "Pending / in progress"),
        ("in_progress", "Pending / in progress"),
        ("pending_review", "Pending / in progress"),
        ("unknown", "Not recorded"),
        ("", "Not recorded"),
        (None, "Not recorded"),
    ],
)
def test_governance_stage_status_classification(status, expected):
    assert _governance_stage_status(status) == expected


def test_governance_stage_status_is_independent_of_source_evidence_and_migration():
    legacy = ReportDataLoader(ROOT).model("legacy-r-logistic")
    table = next(flowable for flowable in _governance_section(legacy, _styles()) if hasattr(flowable, "_cellvalues"))
    discover = next(row for row in table._cellvalues if row[0].getPlainText() == "Approve extracted model information and the risk tier")
    assert discover[1].getPlainText() == "Available"
    assert discover[2].getPlainText() == "Not recorded"

    python_model = ReportDataLoader(ROOT).model("python-gradient-boosting")
    python_table = next(flowable for flowable in _governance_section(python_model, _styles())
                        if hasattr(flowable, "_cellvalues"))
    redevelop = next(row for row in python_table._cellvalues
                     if row[0].getPlainText() == "Approve the migration candidate and test readiness")
    assert redevelop[2].getPlainText() == "Not recorded"
    assert python_model.record["migration_status"] == "not_applicable"


def test_explicit_stage_statuses_are_counted_in_separate_portfolio_columns():
    portfolio = ReportDataLoader(ROOT).portfolio()
    models = [
        replace(portfolio.models[0], record={**portfolio.models[0].record, "discover_status": "approved"}),
        replace(portfolio.models[1], record={**portfolio.models[1].record, "discover_status": "not_applicable"}),
        replace(portfolio.models[2], record={**portfolio.models[2].record, "discover_status": "in_progress"}),
    ]
    table = next(flowable for flowable in build_portfolio_story(replace(portfolio, models=models))
                 if hasattr(flowable, "_cellvalues") and flowable._cellvalues[0][0].getPlainText() == "Stage")
    discover = next(row for row in table._cellvalues[1:] if row[0].getPlainText() == "Discover")
    assert [cell.getPlainText() for cell in discover[2:]] == ["1", "1", "1", "0"]
    assert sum(int(cell.getPlainText()) for cell in discover[2:]) == len(models)


def test_approved_model_card_is_reported_as_recorded_approval_not_validation():
    data = ReportDataLoader(ROOT).model("python-random-forest")
    data = replace(data, model_card={**(data.model_card or {}), "review_status": "approved"}, validation=None)
    assert _status_for(data) == ("Approved (recorded)", "approved")
    assert _status_for(data)[0] != "Validated"


def test_table_headers_use_header_style():
    table = _table([["Header", "Value"], ["row", "data"]], _styles())
    header = table._cellvalues[0][0]
    assert header.style.name == "ReportCellHeader"


def test_pdf_text_has_no_common_mojibake(tmp_path):
    path = generate_individual_report("legacy-r-logistic", ROOT, tmp_path)
    fitz = pytest.importorskip("fitz")
    text = "".join(page.get_text() for page in fitz.open(path))
    assert "Â·" not in text and "â€”" not in text and "â€“" not in text


def test_report_generation_does_not_modify_source_json(tmp_path):
    source_files = [
        path for directory in ("inventory", "reports", "governance")
        for path in (ROOT / directory).rglob("*.json")
    ]
    before = {
        path.relative_to(ROOT): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    }
    for model_id in MODEL_IDS:
        generate_individual_report(model_id, ROOT, tmp_path)
    generate_portfolio_report(ROOT, tmp_path)
    after = {
        path.relative_to(ROOT): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    }
    assert after == before


@pytest.mark.parametrize("model_id", MODEL_IDS)
def test_individual_report_is_valid_pdf_with_model_identity(tmp_path, model_id):
    path = generate_individual_report(model_id, ROOT, tmp_path)
    assert path.is_file()
    assert path.read_bytes()[:5] == b"%PDF-"
    assert path.stat().st_size > 10_000
    fitz = pytest.importorskip("fitz")
    text = "".join(page.get_text() for page in fitz.open(path))
    assert "MODELTRACE AI" in text
    assert model_id in text


def test_portfolio_report_contains_all_models_and_missing_evidence_label(tmp_path):
    path = generate_portfolio_report(ROOT, tmp_path)
    assert path.is_file() and path.read_bytes()[:5] == b"%PDF-"
    fitz = pytest.importorskip("fitz")
    text = "".join(page.get_text() for page in fitz.open(path))
    assert all(model_id in text for model_id in MODEL_IDS)
    assert "Not Assessed" in text
    assert "PRA compliance" not in text
