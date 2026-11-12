"""Person 2: discrepancy scoring against a fabricated answer key (Person 1 holds the real one)."""
import json
from pathlib import Path

import pytest

import agents.discovery_agent as discovery
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
    with pytest.raises(ValueError, match=r"entry 1 for legacy-r-logistic is invalid \(field: ") as error:
        score_discovery(r, key(("K-1", "threshold", "contradiction")))  # not in the field vocabulary
    assert SECRET not in str(error.value)  # the entry's content is never echoed
    with pytest.raises(ValueError, match=r"entry 2 for legacy-r-logistic is invalid \(type: "):
        score_discovery(r, key(("K-1", "decision_threshold", "contradiction"), ("K-2", "decision_threshold", "wrong")))
    with pytest.raises(ValueError, match=r"entry 1 for legacy-r-logistic is invalid \(id: Field required") as error:
        score_discovery(r, {"discrepancies": {"legacy-r-logistic": [
            {"ID": "K-1", "field": "other", "type": "omission", "description": SECRET}]}})
    assert SECRET not in str(error.value)
    with pytest.raises(ValueError, match=r"repeats id\(s\): \['K-1'\]"):
        score_discovery(r, key(("K-1", "decision_threshold", "contradiction"), ("K-1", "monitoring", "omission")))



def test_key_ids_that_look_like_report_ids_do_not_collide():
    r = report(finding("D-001", "monitoring", "contradiction"), finding("D-002", "other", "contradiction"))
    disc = score_discovery(r, key(("D-001", "other", "contradiction"), ("D-002", "limitations", "contradiction")))["discrepancies"]
    assert [(e["id"], e["outcome"], e["discrepancy_id"]) for e in disc["key_entries"]] == [
        ("D-001", "detected", "D-002"), ("D-002", "missed", None)]
    assert outcomes({"discrepancies": disc})["D-001"][:2] == ("unsupported", None)
    assert (disc["recall"], disc["precision"]) == (0.5, 0.5)


def test_numeric_key_ids_are_read_as_text():
    disc = score_discovery(report(finding("D-001", "decision_threshold", "contradiction", THRESHOLD)),
                           {"discrepancies": {"legacy-r-logistic": [
                               {"id": 7, "field": "decision_threshold", "type": "contradiction"}]}})["discrepancies"]
    assert disc["key_entries"][0]["id"] == "7" and disc["key_entries"][0]["outcome"] == "detected"


def test_a_report_with_repeated_ids_is_rejected():
    with pytest.raises(ValueError, match="discovery report for legacy-r-logistic repeats id"):
        score_discovery(report(finding("D-001", "monitoring", "contradiction"), finding("D-001", "other", "omission")),
                        key(("K-1", "other", "contradiction")))


@pytest.mark.parametrize("bad, message", [
    ({"discrepancies": [{"id": "K-1", "field": "other", "type": "omission"}]}, "'discrepancies' must map each model id"),
    ({"discrepancies": {"legacy-r-logistic": {"id": "K-1"}}}, "entry for legacy-r-logistic must be a list"),
    ({"metadata": [{"expected_link": "logit"}]}, "'metadata' must map each model id"),
    ({"metadata": {"legacy-r-logistic": {"model_type": "glm"}}}, r"without the expected_ prefix: \['model_type'\]"),
])
def test_wrongly_shaped_keys_give_a_clear_error(bad, message):
    with pytest.raises(ValueError, match=message):
        score_discovery(report(), bad)


def test_missing_source_files_stop_the_scoring(tmp_path, monkeypatch):
    (tmp_path / "models").mkdir()
    (tmp_path / R_FILE).write_text((ROOT / R_FILE).read_text())  # engine/data.py, also registered, is absent
    monkeypatch.setattr(discovery, "REPO_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError, match="engine/data.py"):
        score_discovery(report(), key(("K-1", "decision_threshold", "contradiction")))


def test_a_model_missing_from_the_inventory_cannot_be_scored():
    with pytest.raises(ValueError, match="not in the inventory"):
        score_discovery(report(model_id="unknown-model"), key(model_id="unknown-model"))


@pytest.mark.parametrize("ref_file, quote, line", [
    ("models/outdated_model_document.md", "- Threshold: 0.5", 9),  # the legacy document is not code
    ("elsewhere/legacy_model.R", THRESHOLD, 23),                   # same base name, wrong path
    (R_FILE, "e", 1),                                               # a fragment of the cited line
    (R_FILE, "0.5", 23),
])
def test_only_substantial_quotes_from_the_registered_code_count(ref_file, quote, line):
    ref = SourceRef(file=ref_file, line_start=line, line_end=line, quote=quote, verified=True)
    r = report(finding("D-001", "decision_threshold", "contradiction").model_copy(update={"code_evidence": [ref]}))
    r = r.model_copy(update={"source_files": [R_FILE, "models/outdated_model_document.md"]})  # the report's own list is not trusted
    assert outcomes(score_discovery(r, key(("K-1", "decision_threshold", "contradiction"))))["D-001"][2] == "unresolved"


def test_every_cited_reference_must_resolve():
    good = SourceRef(file=R_FILE, line_start=23, line_end=23, quote=THRESHOLD, verified=True)
    fake = SourceRef(file=R_FILE, line_start=24, line_end=24, quote="threshold <- 0.4", verified=True)
    r = report(finding("D-001", "decision_threshold", "contradiction").model_copy(update={"code_evidence": [good, fake]}))
    disc = score_discovery(r, key(("K-1", "decision_threshold", "contradiction")))["discrepancies"]
    assert disc["findings"][0]["evidence"] == "unresolved" and disc["recall_with_evidence"] == 0.0


def test_a_quote_found_only_away_from_its_cited_lines_does_not_count():
    moved = report(finding("D-001", "decision_threshold", "contradiction", THRESHOLD, line=22))  # really on line 23
    assert outcomes(score_discovery(moved, key(("K-1", "decision_threshold", "contradiction"))))["D-001"][2] == "unresolved"


def test_an_unverifiable_claim_never_needs_code_evidence():
    r = report(finding("D-001", "ownership", "unverifiable", "owner <- 'risk team'"),  # citation does not resolve
               finding("D-002", "monitoring", "unverifiable"))
    disc = score_discovery(r, key(("K-1", "ownership", "unverifiable"), ("K-2", "monitoring", "unverifiable")))["discrepancies"]
    assert [f["evidence"] for f in disc["findings"]] == ["unresolved", "not_required"]
    assert disc["counts"]["detected_without_evidence"] == 0 and disc["recall_with_evidence"] == 1.0

def test_an_exact_match_is_preferred_over_an_earlier_same_field_entry():
    r = report(finding("D-001", "input_features", "unverifiable"))
    disc = score_discovery(r, key(("K-1", "input_features", "contradiction"), ("K-2", "input_features", "unverifiable")))["discrepancies"]
    assert [(e["id"], e["outcome"]) for e in disc["key_entries"]] == [("K-1", "missed"), ("K-2", "detected")]
    assert disc["recall"] == 0.5


def test_a_misclassified_finding_is_not_counted_as_missing_evidence():
    r = report(finding("D-001", "input_features", "contradiction"))  # no evidence, wrong type
    disc = score_discovery(r, key(("K-1", "input_features", "omission")))["discrepancies"]
    assert outcomes({"discrepancies": disc})["D-001"] == ("misclassified", "K-1", "missing")
    assert disc["counts"]["detected_without_evidence"] == 0


def test_key_entries_reveal_only_ids_and_outcomes():
    score = score_discovery(report(finding("D-001", "decision_threshold", "contradiction", THRESHOLD)),
                            key(("K-1", "decision_threshold", "contradiction"), ("K-2", "train_test_split", "contradiction")))
    entries = score["discrepancies"]["key_entries"]
    assert all(set(e) == {"id", "outcome", "discrepancy_id"} for e in entries)
    assert "train_test_split" not in json.dumps(score)  # the missed entry's field stays in the private key


# --------------------------------------------------------------------------- model-specific metadata
GB = "python-gradient-boosting"


@pytest.mark.parametrize("other_model", [GB, "python-random-forest"])
def test_top_level_metadata_belongs_to_the_legacy_r_model_only(other_model):
    k = {"expected_link": "logit", "expected_target": "target"}
    r_score = score_discovery(report(), k)
    assert r_score["metadata_scored"] and r_score["matched"] == ["expected_link", "expected_target"]
    other = score_discovery(report(model_id=other_model), k)  # never scored against the R facts
    assert other["metadata_scored"] is False
    assert (other["recall"], other["precision"], other["matched"], other["missed"]) == (None, None, [], [])


def test_a_model_listed_with_null_metadata_is_not_fact_scored():
    score = score_discovery(report(), {"expected_link": "logit", "metadata": {"legacy-r-logistic": None}})
    assert score["metadata_scored"] is False


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
        with pytest.raises(ValueError, match="inside a git repository"):
            private_key_path(inside)
    clone = tmp_path / "other-clone"
    (clone / ".git").mkdir(parents=True)
    with pytest.raises(ValueError, match="inside a git repository"):
        private_key_path(clone / "models" / "discovery_answer_key.json")
    other_case = Path(str(ROOT / "models").swapcase()) / "discovery_answer_key.json"
    if other_case.parent.exists():  # only on a case-insensitive disk, such as the default macOS one
        with pytest.raises(ValueError, match="inside a git repository"):
            private_key_path(other_case)


def test_cli_scores_with_a_key_outside_the_repository(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    work = tmp_path / "work"  # a copy of what the scorer reads, so the repository's reports stay untouched
    for rel in (R_FILE, "engine/data.py"):
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, work / rel)
    saved = work / "reports/discovery/legacy-r-logistic_discovery.json"  # known findings, not the last live run's
    saved.parent.mkdir(parents=True)
    saved.write_text(report(finding("D-001", "input_features", "omission", EXCLUDED, line=19)).model_dump_json())
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
    assert refused.returncode == 2 and "inside a git repository" in refused.stderr
