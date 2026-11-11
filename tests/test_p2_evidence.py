"""Person 2: deterministic verification of LLM source references."""
from llm.evidence import render_listing, verify_fact, verify_facts, verify_ref
from llm.schemas import Fact, ModelMetadata, SourceRef

SOURCES = {
    "src/model.R": [
        "# header",
        "x <- 1",
        "fit <- glm(y ~ a + b,",
        "    family = binomial)",
        "threshold <- 0.3",
    ]
}


def ref(**overrides) -> SourceRef:
    fields = {"file": "src/model.R", "line_start": 2, "line_end": 2, "quote": "x <- 1"}
    fields.update(overrides)
    return SourceRef(**fields)


def test_exact_reference_is_verified():
    checked = verify_ref(ref(), SOURCES)
    assert checked.verified and (checked.line_start, checked.line_end) == (2, 2)


def test_whitespace_is_ignored_across_lines():
    checked = verify_ref(ref(line_start=3, line_end=4, quote="glm(y ~ a + b, family = binomial)"), SOURCES)
    assert checked is not None and checked.verified


def test_wrong_line_numbers_are_corrected():
    checked = verify_ref(ref(line_start=1, line_end=1, quote="threshold <- 0.3"), SOURCES)
    assert (checked.line_start, checked.line_end) == (5, 5)


def test_multi_line_quote_is_relocated():
    checked = verify_ref(ref(line_start=1, line_end=2, quote="glm(y ~ a + b,\nfamily = binomial)"), SOURCES)
    assert (checked.line_start, checked.line_end) == (3, 4)


def test_basename_resolves_to_listed_file():
    assert verify_ref(ref(file="model.R"), SOURCES).file == "src/model.R"


def test_fabricated_or_unknown_references_are_rejected():
    assert verify_ref(ref(quote="approve credit applications"), SOURCES) is None
    assert verify_ref(ref(file="other.R"), SOURCES) is None
    assert verify_ref(ref(quote="   "), SOURCES) is None


def test_verified_fact_without_evidence_is_downgraded():
    warnings = []
    fact = verify_fact(Fact(value="x", status="verified", evidence=[ref(quote="made up")]), SOURCES, "purpose", warnings)
    assert fact.status == "inferred" and fact.evidence == []
    assert "Downgraded" in fact.note
    assert any("downgraded" in w for w in warnings)


def test_inferred_fact_keeps_its_status():
    warnings = []
    fact = verify_fact(Fact(value="x", status="inferred"), SOURCES, "purpose", warnings)
    assert fact.status == "inferred" and warnings == []


def test_verify_facts_covers_fact_lists():
    missing = Fact(status="missing")
    metadata = ModelMetadata(
        model_name=missing, algorithm=missing, business_purpose=missing, target_variable=missing,
        input_features=missing, excluded_columns=missing, preprocessing_steps=missing,
        train_fraction=missing, decision_threshold=missing,
        assumptions=[Fact(value="a", status="verified", evidence=[ref(quote="nowhere")])],
    )
    checked, warnings = verify_facts(metadata, SOURCES)
    assert checked.assumptions[0].status == "inferred"
    assert any(w.startswith("assumptions[0]") for w in warnings)


def test_listing_numbers_lines():
    listing = render_listing(SOURCES)
    assert listing.startswith("=== FILE: src/model.R ===")
    assert "2| x <- 1" in listing
