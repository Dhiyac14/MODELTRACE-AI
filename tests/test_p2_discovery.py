"""Person 2: Discovery Agent on the development fixture (not Person 1's answer key)."""
from pathlib import Path

import pytest

from agents.discovery_agent import assess_free_text, compare_mechanical, model_names, run_discovery, save_report
from llm.client import ReplayLLM
from llm.prompts import model_scope
from llm.schemas import (
    ClaimAssessment,
    ClaimCheck,
    DiscoveryReport,
    DocClaim,
    DocumentClaims,
    Documented,
    Fact,
    ModelMetadata,
    OmissionFinding,
    SourceRef,
)

ROOT = Path(__file__).resolve().parents[1]
FIX = "tests/fixtures/p2"
R_FILE = f"{FIX}/legacy_lr_model.R"
SOURCES = [R_FILE, f"{FIX}/preprocessing_split.py"]


@pytest.fixture(autouse=True)
def at_repo_root(monkeypatch):
    monkeypatch.chdir(ROOT)


@pytest.fixture
def report() -> DiscoveryReport:
    return run_discovery("legacy-r-logistic", SOURCES, ReplayLLM(f"{FIX}/replay_lr"), f"{FIX}/lr_doc_outdated_dev.md")


# --------------------------------------------------------------------------- end to end
def test_planted_discrepancies_are_found(report):
    found = sorted((d.field, d.type, d.detected_by) for d in report.discrepancies)
    assert found == sorted([
        ("input_features", "contradiction", "rule"),      # SEX documented, excluded in code
        ("input_features", "omission", "rule"),           # PAY_AMT4-6 undocumented
        ("decision_threshold", "contradiction", "rule"),  # 0.40 vs 0.35
        ("train_test_split", "contradiction", "rule"),    # 75/25 vs 80/20
        ("preprocessing", "contradiction", "llm"),        # log transform not in code
        ("preprocessing", "omission", "llm"),             # SEX/AGE fairness-only not documented
        ("ownership", "unverifiable", "llm"),
        ("validation_history", "unverifiable", "llm"),
        ("other", "unverifiable", "llm"),
    ])
    assert [d.discrepancy_id for d in report.discrepancies] == [f"D-{i:03d}" for i in range(1, 10)]


def test_documented_but_excluded_feature_cites_the_exclusion(report):
    sex = next(d for d in report.discrepancies if d.documented_claim.startswith("SEX"))
    assert [(r.line_start, r.quote) for r in sex.code_evidence] == [(10, 'excluded <- c("ID", "SEX", "AGE")')]
    assert sex.document_ref.verified


def test_fabricated_quote_downgrades_the_fact(report):
    purpose = report.metadata.business_purpose
    assert purpose.status == "inferred" and purpose.evidence == []


def test_wrong_line_numbers_and_short_file_name_are_corrected(report):
    refs = report.metadata.input_features.evidence
    assert [(r.file, r.line_start, r.line_end) for r in refs] == [(R_FILE, 12, 14), (R_FILE, 15, 15)]


def test_claim_not_in_document_is_dropped(report):
    assert all(d.field != "monitoring" for d in report.discrepancies)
    assert any("C9" in w for w in report.evidence_warnings)


def test_mechanical_fields_are_reported_once(report):
    fields = [d.field for d in report.discrepancies]
    assert fields.count("train_test_split") == 1
    assert fields.count("input_features") == 2


def test_report_header(report):
    assert report.language == "R"
    assert report.review_status == "pending_human_review"
    assert report.source_files == SOURCES
    assert report.llm_model == "replay"


def test_without_document_there_are_no_discrepancies():
    result = run_discovery("legacy-r-logistic", SOURCES, ReplayLLM(f"{FIX}/replay_lr"))
    assert result.discrepancies == [] and result.legacy_document is None


def test_saved_report_round_trips(tmp_path, report):
    path = save_report(report, tmp_path)
    assert path.name == "legacy-r-logistic_discovery.json"
    assert DiscoveryReport.model_validate_json(path.read_text()) == report


# --------------------------------------------------------------------------- rules
MISSING = Fact(status="missing")
DOC_REF = SourceRef(file="doc.md", line_start=1, line_end=1, quote="q", verified=True)


def metadata(**facts) -> ModelMetadata:
    fields = dict(model_name=MISSING, algorithm=MISSING, business_purpose=MISSING, target_variable=MISSING,
                  input_features=MISSING, excluded_columns=MISSING, preprocessing_steps=MISSING,
                  train_fraction=MISSING, decision_threshold=MISSING)
    fields.update(facts)
    return ModelMetadata(**fields)


def documented(value) -> Documented:
    return Documented(value=value, ref=DOC_REF)


def test_matching_values_give_no_discrepancy():
    md = metadata(decision_threshold=Fact(value=0.5, status="verified"), train_fraction=Fact(value=0.8, status="verified"),
                  input_features=Fact(value=["BILL_AMT1", "PAY_0"], status="verified"))
    claims = DocumentClaims(decision_threshold=documented(0.50), train_fraction=documented(0.8),
                            input_features=documented(["bill amt1", "PAY_0"]))
    assert compare_mechanical(md, claims) == []


def test_document_silent_is_an_omission():
    result = compare_mechanical(metadata(decision_threshold=Fact(value=0.3, status="verified")), DocumentClaims())
    assert [(d.field, d.type) for d in result] == [("decision_threshold", "omission")]


def test_no_code_evidence_is_unverifiable():
    result = compare_mechanical(metadata(), DocumentClaims(train_fraction=documented(0.7)))
    assert [(d.field, d.type) for d in result] == [("train_test_split", "unverifiable")]


def test_skipped_field_is_not_compared():
    md = metadata(decision_threshold=Fact(value=0.3, status="verified"))
    assert compare_mechanical(md, DocumentClaims(), skip=frozenset({"decision_threshold"})) == []


# --------------------------------------------------------------------------- free-text guards
CLAIMS = DocumentClaims(other_claims=[
    DocClaim(claim_id="C1", field="target_variable", statement="Target is default within a year.", doc_ref=DOC_REF),
    DocClaim(claim_id="C2", field="ownership", statement="Owned by team X.", doc_ref=DOC_REF),
])
CODE = {"model.R": ["y ~ a + b"]}


def test_contradiction_without_verified_evidence_is_downgraded():
    bogus = SourceRef(file="model.R", line_start=1, line_end=1, quote="not in the file")
    check = ClaimCheck(assessments=[
        ClaimAssessment(claim_id="C1", verdict="contradiction", code_evidence=[bogus], explanation="Different target."),
        ClaimAssessment(claim_id="C2", verdict="consistent", explanation="ok"),
    ])
    warnings = []
    result = assess_free_text(check, CLAIMS, CODE, warnings)
    assert [(d.field, d.type) for d in result] == [("target_variable", "unverifiable")]
    assert "Downgraded" in result[0].explanation


def test_unassessed_claim_is_flagged_and_unsupported_omission_dropped():
    check = ClaimCheck(
        assessments=[ClaimAssessment(claim_id="C1", verdict="consistent", explanation="ok")],
        omissions=[OmissionFinding(field="preprocessing", code_evidence=[], explanation="x", suggested_correction="y")],
    )
    warnings = []
    assert assess_free_text(check, CLAIMS, CODE, warnings) == []
    assert any("C2 was not assessed" in w for w in warnings)
    assert any("omission 1" in w for w in warnings)


def test_model_hint_scopes_the_prompt():
    class Capture(ReplayLLM):
        def structured(self, system, user, schema):
            self.last_user = user
            return super().structured(system, user, schema)

    llm = Capture(f"{FIX}/replay_lr")
    run_discovery("python-random-forest", SOURCES, llm, model_hint="Python Random Forest (RandomForestClassifier)")
    assert llm.last_user.startswith("Describe this model only: Python Random Forest")


# --------------------------------------------------------------------------- model identity
GB = "python-gradient-boosting"
GB_HINT = "Python Gradient Boosting (Gradient Boosting classifier (scikit-learn))"
# The engine/models.py lines the live claim check cited for its false model_name contradiction (D-001 in 0f7039f).
GB_CODE = [
    "    models = {",
    '        "gradient_boosting": GradientBoostingClassifier(random_state=seed),',
    "    }",
    "    for name, model in models.items():",
    "        bundles[name] = ModelBundle(name, model, list(model_features.columns))",
]


class Scripted:
    """Gives one fixed reply per schema and keeps the prompt each step was sent."""

    model = "scripted"

    def __init__(self, **replies):
        self.replies, self.prompts = replies, {}

    def structured(self, system, user, schema):
        self.prompts[schema.__name__] = user
        return self.replies[schema.__name__]


def run_gb(tmp_path, documented_name):
    """Discovery for the GB model whose document names it ``documented_name``; the claim check returns the
    verdict of that live run: a contradiction citing the code's "gradient_boosting" lines."""
    code, doc = tmp_path / "models.py", tmp_path / "doc.md"
    code.write_text("\n".join(GB_CODE) + "\n")
    line = f"This is the challenger model identified as `{documented_name}`."
    doc.write_text(line + "\n")
    claim = DocClaim(claim_id="C1", field="model_name",
                     statement=f"The model is a challenger model identified as {documented_name}.",
                     doc_ref=SourceRef(file=doc.as_posix(), line_start=1, line_end=1, quote=line))
    # Cite files as the listing names them (as_posix), like the LLM does; str() has backslashes on Windows.
    cited = [SourceRef(file=code.as_posix(), line_start=n, line_end=n, quote=GB_CODE[n - 1]) for n in (2, 5)]
    verdict = ClaimAssessment(claim_id="C1", verdict="contradiction", code_evidence=cited,
                              explanation=f'The code names the model "gradient_boosting"; {documented_name} does not appear.')
    llm = Scripted(ModelMetadata=metadata(), DocumentClaims=DocumentClaims(other_claims=[claim]),
                   ClaimCheck=ClaimCheck(assessments=[verdict]))
    return run_discovery(GB, [str(code)], llm, str(doc), GB_HINT), llm


def test_inventory_id_and_bundle_name_are_not_a_model_name_discrepancy(tmp_path):
    assert model_names(GB) == {"python-gradient-boosting", "gradient_boosting"}
    report, _ = run_gb(tmp_path, GB)
    assert [d for d in report.discrepancies if d.field == "model_name"] == []
    assert report.evidence_warnings == ["claim C1 (model_name) not reported: the document and the code use names of "
                                        "the same model (gradient_boosting, python-gradient-boosting)."]


def test_an_unregistered_model_name_is_still_a_contradiction(tmp_path):
    report, _ = run_gb(tmp_path, "credit-boost-v2")
    assert [(d.field, d.type) for d in report.discrepancies] == [("model_name", "contradiction")]
    assert report.evidence_warnings == []


def test_claim_check_gets_the_same_model_scope_as_metadata_extraction(tmp_path):
    _, llm = run_gb(tmp_path, GB)
    scope = model_scope(GB_HINT, GB, "gradient_boosting")
    assert "inventory ID python-gradient-boosting, which the code names gradient_boosting" in scope
    assert llm.prompts["ModelMetadata"].startswith(f"Describe this model only: {scope}.")
    assert llm.prompts["ClaimCheck"].startswith(f"The document describes this model: {scope}.")


def test_a_model_without_a_code_name_keeps_its_hint():
    assert model_scope("Legacy R Logistic Regression", "legacy-r-logistic") == "Legacy R Logistic Regression"
    assert model_names("legacy-r-logistic") == {"legacy-r-logistic"}
