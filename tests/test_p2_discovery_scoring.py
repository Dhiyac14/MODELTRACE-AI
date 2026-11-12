"""Person 2: discrepancy scoring against a fabricated answer key (Person 1 holds the real one)."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.discovery_agent import score_discovery
from llm.evidence import load_sources
from llm.schemas import Discrepancy, DiscoveryReport, SourceRef

ROOT = Path(__file__).resolve().parents[1]
R_FILE = "models/legacy_model.R"
THRESHOLD = "prediction <- as.integer(probability >= 0.5)"  # line 23
EXCLUDED = 'feature_names <- setdiff(names(train), c("row_id", "target", "SEX", "AGE", "ID"))'  # line 19
SECRET = "SECRET-DESCRIPTION"  # stands in for the key's free text, which must never reach the score


@pytest.fixture(autouse=True)
def at_repo_root(monkeypatch):
    monkeypatch.chdir(ROOT)


def finding(did, field, type_, quote=None, line=23):
    refs = [SourceRef(file=R_FILE, line_start=line, line_end=line, quote=quote, verified=True)] if quote else []
    return Discrepancy(discrepancy_id=did, field=field, type=type_, documented_claim="claim", code_evidence=refs,
                       explanation="why", suggested_correction="fix", detected_by="rule")


def report(*findings, model_id="legacy-r-logistic"):
    base = DiscoveryReport.model_validate_json((ROOT / "reports/discovery/legacy-r-logistic_discovery.json").read_text())
    return base.model_copy(update={"model_id": model_id, "source_files": [R_FILE], "discrepancies": list(findings)})


def key(*entries, model_id="legacy-r-logistic"):
    """Fabricated key: one metadata value plus a discrepancy list for one model."""
    return {"expected_link": "logit", "discrepancies": {model_id: [
        {"id": i, "field": f, "type": t, "description": SECRET} for i, f, t in entries]}}


def outcomes(score):
    return {f["discrepancy_id"]: (f["outcome"], f["expected_id"], f["evidence"]) for f in score["discrepancies"]["findings"]}


# --------------------------------------------------------------------------- matching
def test_detected_misclassified_missed_unsupported_and_not_scored():
    r = report(
        finding("D-001", "decision_threshold", "contradiction", THRESHOLD),
        finding("D-002", "input_features", "unverifiable"),                     # right field, wrong type
        finding("D-003", "ownership", "unverifiable"),
        finding("D-004", "monitoring", "contradiction", "psi <- 0.3"),           # quote not in the code
        finding("D-005", "preprocessing", "omission", EXCLUDED, line=19),        # key lists no omissions
    )
    k = key(("K-1", "decision_threshold", "contradiction"), ("K-2", "input_features", "contradiction"),
            ("K-3", "train_test_split", "contradiction"), ("K-4", "ownership", "unverifiable"))
    score = score_discovery(r, k)  # code evidence re-read from the report's source files
    disc = score["discrepancies"]
    assert outcomes(score) == {
        "D-001": ("detected", "K-1", "verified"),
        "D-002": ("misclassified", "K-2", "not_required"),
        "D-003": ("detected", "K-4", "not_required"),
        "D-004": ("unsupported", None, "unresolved"),
        "D-005": ("not_scored", None, "verified"),
    }
    assert {e["id"]: e["outcome"] for e in disc["key_entries"]} == {
        "K-1": "detected", "K-2": "misclassified", "K-3": "missed", "K-4": "detected"}
    assert disc["scored_types"] == ["contradiction", "unverifiable"]
    assert disc["counts"] == {"expected": 4, "scored_findings": 4, "detected": 2, "misclassified": 1, "unsupported": 1,
                              "not_scored": 1, "missed": 1, "detected_without_evidence": 0}
    assert (disc["recall"], disc["precision"], disc["recall_with_evidence"]) == (0.5, 0.5, 0.5)
    assert SECRET not in json.dumps(score)


def test_matching_is_one_to_one():
    r = report(*(finding(f"D-00{i}", "input_features", "contradiction", EXCLUDED, line=19) for i in (1, 2, 3)))
    score = score_discovery(r, key(("K-1", "input_features", "contradiction"), ("K-2", "input_features", "contradiction")))
    assert [o[0] for o in outcomes(score).values()] == ["detected", "detected", "unsupported"]
    assert score["discrepancies"]["precision"] == 2 / 3 and score["discrepancies"]["recall"] == 1.0


def test_a_finding_with_verified_evidence_is_matched_first():
    r = report(finding("D-001", "decision_threshold", "contradiction"),
               finding("D-002", "decision_threshold", "contradiction", THRESHOLD))
    score = score_discovery(r, key(("K-1", "decision_threshold", "contradiction")))
    assert outcomes(score) == {"D-001": ("unsupported", None, "missing"), "D-002": ("detected", "K-1", "verified")}


# --------------------------------------------------------------------------- evidence
@pytest.mark.parametrize("quote, status", [(None, "missing"), ("threshold <- 0.4", "unresolved")])
def test_detected_without_resolved_evidence_is_counted_apart(quote, status):
    score = score_discovery(report(finding("D-001", "decision_threshold", "contradiction", quote)),
                            key(("K-1", "decision_threshold", "contradiction")))
    disc = score["discrepancies"]
    assert outcomes(score)["D-001"] == ("detected", "K-1", status)
    assert (disc["recall"], disc["recall_with_evidence"], disc["counts"]["detected_without_evidence"]) == (1.0, 0.0, 1)


def test_evidence_must_resolve_in_the_current_code():
    r = report(finding("D-001", "decision_threshold", "contradiction", THRESHOLD))
    k = key(("K-1", "decision_threshold", "contradiction"))
    changed = {R_FILE: [line.replace(">= 0.5", ">= 0.4") for line in load_sources([R_FILE])[R_FILE]]}
    assert outcomes(score_discovery(r, k))["D-001"][2] == "verified"
    assert outcomes(score_discovery(r, k, code=changed))["D-001"][2] == "unresolved"


# --------------------------------------------------------------------------- types, control case, key handling
def test_omissions_are_scored_only_when_the_key_lists_one():
    r = report(finding("D-001", "preprocessing", "omission", EXCLUDED, line=19),
               finding("D-002", "monitoring", "omission", THRESHOLD))
    score = score_discovery(r, key(("K-1", "preprocessing", "omission")))
    assert score["discrepancies"]["scored_types"] == ["contradiction", "omission", "unverifiable"]
    assert [o[0] for o in outcomes(score).values()] == ["detected", "unsupported"]


def test_control_document_turns_every_scored_finding_into_a_false_alarm():
    gb = "python-gradient-boosting"
    r = report(finding("D-001", "decision_threshold", "contradiction", THRESHOLD),
               finding("D-002", "monitoring", "omission", THRESHOLD), model_id=gb)
    disc = score_discovery(r, key(model_id=gb))["discrepancies"]
    assert [f["outcome"] for f in disc["findings"]] == ["unsupported", "not_scored"]
    assert (disc["recall"], disc["precision"], disc["recall_with_evidence"]) == (None, 0.0, None)
    clean = score_discovery(report(model_id=gb), key(model_id=gb))["discrepancies"]
    assert clean["precision"] is None and clean["counts"]["unsupported"] == 0


def test_model_without_a_discrepancy_list_keeps_metadata_scoring_only():
    r = report(finding("D-001", "decision_threshold", "contradiction", THRESHOLD))
    for k in ({"expected_link": "logit"}, key(("K-1", "decision_threshold", "contradiction"), model_id="other-model")):
        score = score_discovery(r, k)
        assert score["discrepancies"] is None
        assert score["matched"] == ["expected_link"] and score["recall"] == 1.0


def test_malformed_key_entries_are_rejected():
    r = report()
    with pytest.raises(ValidationError):
        score_discovery(r, key(("K-1", "threshold", "contradiction")))  # not in the field vocabulary
    with pytest.raises(ValidationError):
        score_discovery(r, key(("K-1", "decision_threshold", "wrong")))
    with pytest.raises(ValueError, match="repeats an id"):
        score_discovery(r, key(("K-1", "decision_threshold", "contradiction"), ("K-1", "monitoring", "omission")))


# --------------------------------------------------------------------------- model-specific metadata
GB = "python-gradient-boosting"


def test_top_level_metadata_belongs_to_the_legacy_r_model_only():
    k = {"expected_link": "logit", "expected_target": "target"}
    r_score = score_discovery(report(), k)
    assert r_score["metadata_scored"] and r_score["matched"] == ["expected_link", "expected_target"]
    gb_score = score_discovery(report(model_id=GB), k)  # GB is not scored against the R facts
    assert gb_score["metadata_scored"] is False
    assert (gb_score["recall"], gb_score["precision"], gb_score["matched"], gb_score["missed"]) == (None, None, [], [])


def test_per_model_metadata_is_used_and_overrides_the_top_level_values():
    k = {"expected_link": "probit", "metadata": {"legacy-r-logistic": {"expected_link": "logit"},
                                                 GB: {"expected_target": "target"}}}
    assert score_discovery(report(), k)["matched"] == ["expected_link"]
    gb_score = score_discovery(report(model_id=GB), k)
    assert gb_score["metadata_scored"] and gb_score["matched"] == ["expected_target"] and gb_score["recall"] == 1.0


def test_an_empty_metadata_entry_disables_fact_scoring_but_not_discrepancy_scoring():
    k = {"expected_link": "logit", "metadata": {"legacy-r-logistic": {}}, "discrepancies": {"legacy-r-logistic": []}}
    score = score_discovery(report(finding("D-001", "decision_threshold", "contradiction", THRESHOLD)), k)
    assert score["metadata_scored"] is False and score["recall"] is None
    assert score["discrepancies"]["counts"]["unsupported"] == 1


# --------------------------------------------------------------------------- answer-key location
def test_the_answer_key_must_live_outside_the_repository(tmp_path):
    from agents.discovery_agent import private_key_path
    outside = tmp_path / "discovery_answer_key.json"
    assert private_key_path(outside) == outside.resolve()
    for inside in (ROOT / "models/discovery_answer_key.json", "models/discovery_answer_key.json", "tests/../key.json"):
        with pytest.raises(ValueError, match="inside the repository"):
            private_key_path(inside)


def test_cli_scores_with_a_key_outside_the_repository(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    work = tmp_path / "work"  # a copy of what the scorer reads, so the repository's reports stay untouched
    for rel in ("reports/discovery/legacy-r-logistic_discovery.json", R_FILE, "engine/data.py"):
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, work / rel)
    private = tmp_path / "private" / "discovery_answer_key.json"
    private.parent.mkdir()
    private.write_text(json.dumps(key(("K-1", "input_features", "omission"))))

    def run(key_path):
        return subprocess.run([sys.executable, "-m", "agents.discovery_agent", "--model-id", "legacy-r-logistic",
                               "--score", str(key_path)], cwd=work, env={**os.environ, "PYTHONPATH": str(ROOT)},
                              capture_output=True, text=True)

    done = run(private)
    assert done.returncode == 0, done.stderr
    assert "facts recall 1.00" in done.stdout and "detected 1" in done.stdout
    written = (work / "reports/discovery/legacy-r-logistic_score.json").read_text()
    assert SECRET not in written and json.loads(written)["discrepancies"]["counts"]["detected"] == 1
    refused = run(ROOT / "models" / "discovery_answer_key.json")
    assert refused.returncode == 2 and "inside the repository" in refused.stderr
