"""Model Intelligence (Discovery) Agent — plan step 5.

1. LLM extracts model metadata from source code, with line references.
2. Code verifies every reference (``llm.evidence``).
3. If an existing model document is given, the LLM lists its claims (also verified against the document).
4. Feature list, decision threshold and split ratio are compared in Python.
5. The LLM judges the remaining free-text claims; its code citations are verified, and a
   contradiction without verified code evidence is downgraded to "unverifiable".

Usage:
    python -m agents.discovery_agent --model-id legacy-r-logistic \\
        --source path/to/model.R --source engine/preprocessing.py \\
        --doc legacy_docs/lr_model_doc_outdated.md
The first ``--source`` is the model's main file and sets its language.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from pydantic import BaseModel

from llm.client import StructuredLLM, llm_from_env
from llm.evidence import Sources, load_sources, render_listing, verify_facts, verify_ref, verify_refs
from llm.prompts import (
    CLAIM_CHECK_SYSTEM,
    DISCOVERY_SYSTEM,
    DOC_CLAIMS_SYSTEM,
    claim_check_user,
    discovery_user,
    doc_claims_user,
)
from llm.schemas import (
    MECHANICAL_FIELDS,
    AgentResult,
    ClaimCheck,
    DiscoveryReport,
    Discrepancy,
    DiscrepancyField,
    DiscrepancyType,
    DocumentClaims,
    Documented,
    Evidence,
    Fact,
    Finding,
    ModelMetadata,
    utc_now,
)

from ._common import read_source

REPORTS_DIR = Path("reports/discovery")
LANGUAGES = {".r": "R", ".py": "Python", ".sas": "SAS", ".sql": "SQL"}


def detect_language(main_file: str | Path) -> str:
    return LANGUAGES.get(Path(main_file).suffix.lower(), "unknown")


def _key(name: str) -> str:
    """Normalise a column name so that BILL_AMT1, bill.amt1 and 'Bill Amt1' compare equal."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _known(fact: Fact) -> bool:
    return fact.status != "missing" and fact.value is not None


def _new(**fields) -> Discrepancy:
    return Discrepancy(discrepancy_id="", detected_by="rule", **fields)


# --------------------------------------------------------------------------- mechanical comparison
def _compare_features(code: Fact, excluded: Fact, doc: Documented | None) -> list[Discrepancy]:
    if doc is None and not _known(code):
        return []
    if doc is None:
        return [_new(field="input_features", type="omission", documented_claim="The document does not list the input features.",
                     code_evidence=code.evidence, explanation=f"The code uses {len(code.value)} input features.",
                     suggested_correction=f"List the input features: {', '.join(code.value)}.")]
    if not _known(code):
        return [_new(field="input_features", type="unverifiable", documented_claim=f"Input features: {', '.join(doc.value)}.",
                     document_ref=doc.ref, explanation="The input features could not be determined from the code.",
                     suggested_correction="Confirm the feature list against the model code.")]
    doc_names = {_key(n): n for n in doc.value}
    code_names = {_key(n): n for n in code.value}
    excluded_keys = {_key(n) for n in (excluded.value or [])}
    out = []
    for key in sorted(doc_names.keys() - code_names.keys()):
        name = doc_names[key]
        is_excluded = key in excluded_keys
        out.append(_new(
            field="input_features", type="contradiction", documented_claim=f"{name} is a model input.",
            document_ref=doc.ref, code_evidence=excluded.evidence if is_excluded else code.evidence,
            explanation=f"The code {'explicitly excludes' if is_excluded else 'does not use'} {name} as a predictor.",
            suggested_correction=f"Remove {name} from the documented input features.",
        ))
    undocumented = [code_names[k] for k in sorted(code_names.keys() - doc_names.keys())]
    if undocumented:
        out.append(_new(
            field="input_features", type="omission", documented_claim=f"The documented feature list leaves out {', '.join(undocumented)}.",
            document_ref=doc.ref, code_evidence=code.evidence,
            explanation=f"The code uses {len(undocumented)} predictor(s) that the document does not list.",
            suggested_correction=f"Add {', '.join(undocumented)} to the documented input features.",
        ))
    return out


def format_split(fraction: float) -> str:
    return f"{fraction:.0%} train / {1 - fraction:.0%} test"


def _compare_number(field: str, label: str, code: Fact, doc: Documented | None, fmt) -> list[Discrepancy]:
    if doc is None and not _known(code):
        return []
    if doc is None:
        return [_new(field=field, type="omission", documented_claim=f"The document does not state the {label}.",
                     code_evidence=code.evidence, explanation=f"The code uses {fmt(code.value)}.",
                     suggested_correction=f"State the {label}: {fmt(code.value)}.")]
    if not _known(code):
        return [_new(field=field, type="unverifiable", documented_claim=f"The {label} is {fmt(doc.value)}.", document_ref=doc.ref,
                     explanation=f"No {label} could be found in the code.",
                     suggested_correction=f"Confirm the {label} against the model code.")]
    if math.isclose(doc.value, code.value, abs_tol=1e-9):
        return []
    return [_new(field=field, type="contradiction", documented_claim=f"The {label} is {fmt(doc.value)}.", document_ref=doc.ref,
                 code_evidence=code.evidence, explanation=f"The code uses {fmt(code.value)}.",
                 suggested_correction=f"Change the documented {label} to {fmt(code.value)}.")]


def compare_mechanical(metadata: ModelMetadata, claims: DocumentClaims, skip: frozenset[str] = frozenset()) -> list[Discrepancy]:
    """Compare the fields that can be checked mechanically. ``skip`` holds fields whose document claim failed verification."""
    out: list[Discrepancy] = []
    if "input_features" not in skip:
        out += _compare_features(metadata.input_features, metadata.excluded_columns, claims.input_features)
    if "decision_threshold" not in skip:
        out += _compare_number("decision_threshold", "decision threshold", metadata.decision_threshold,
                               claims.decision_threshold, lambda v: f"{v:g}")
    if "train_test_split" not in skip:
        out += _compare_number("train_test_split", "train/test split", metadata.train_fraction, claims.train_fraction, format_split)
    return out


# --------------------------------------------------------------------------- document claims
def verify_claims(claims: DocumentClaims, doc: Sources) -> tuple[DocumentClaims, frozenset[str], list[str]]:
    """Drop document claims whose quote is not in the document. Returns claims, fields to skip, warnings."""
    warnings: list[str] = []
    skip: set[str] = set()
    update: dict = {}
    for attr, field in (("input_features", "input_features"), ("decision_threshold", "decision_threshold"),
                        ("train_fraction", "train_test_split")):
        documented = getattr(claims, attr)
        if documented is None:
            continue
        ref = verify_ref(documented.ref, doc)
        if ref is None:
            warnings.append(f"document claim '{attr}' not found in the document; field not compared.")
            skip.add(field)
            update[attr] = None
        else:
            update[attr] = documented.model_copy(update={"ref": ref})
    kept = []
    for claim in claims.other_claims:
        ref = verify_ref(claim.doc_ref, doc)
        if ref is None:
            warnings.append(f"document claim {claim.claim_id} not found in the document; dropped.")
        elif claim.field in MECHANICAL_FIELDS:
            continue  # compared by rule above; avoids reporting the same discrepancy twice
        else:
            kept.append(claim.model_copy(update={"doc_ref": ref}))
    update["other_claims"] = kept
    return claims.model_copy(update=update), frozenset(skip), warnings


def assess_free_text(check: ClaimCheck, claims: DocumentClaims, sources: Sources, warnings: list[str]) -> list[Discrepancy]:
    by_id = {c.claim_id: c for c in claims.other_claims}
    assessed = set()
    out: list[Discrepancy] = []
    for a in check.assessments:
        claim = by_id.get(a.claim_id)
        if claim is None:
            warnings.append(f"assessment for unknown claim {a.claim_id} ignored.")
            continue
        assessed.add(a.claim_id)
        if a.verdict == "consistent":
            continue
        evidence = verify_refs(a.code_evidence, sources, f"claim {a.claim_id}", warnings)
        verdict, explanation = a.verdict, a.explanation
        if verdict == "contradiction" and not evidence:
            verdict = "unverifiable"
            explanation += " (Downgraded from contradiction: the cited code could not be verified.)"
        out.append(Discrepancy(
            discrepancy_id="", field=claim.field, type=verdict, documented_claim=claim.statement,
            document_ref=claim.doc_ref, code_evidence=evidence, explanation=explanation,
            suggested_correction=a.suggested_correction, detected_by="llm",
        ))
    for claim_id in sorted(by_id.keys() - assessed):
        warnings.append(f"claim {claim_id} was not assessed by the LLM; review it manually.")
    for i, o in enumerate(check.omissions, start=1):
        if o.field in MECHANICAL_FIELDS:
            continue
        evidence = verify_refs(o.code_evidence, sources, f"omission {i}", warnings)
        if not evidence:
            warnings.append(f"omission {i} ({o.field}) dropped: no verified code evidence.")
            continue
        out.append(Discrepancy(
            discrepancy_id="", field=o.field, type="omission", documented_claim="Not mentioned in the document.",
            code_evidence=evidence, explanation=o.explanation, suggested_correction=o.suggested_correction,
            detected_by="llm",
        ))
    return out


# --------------------------------------------------------------------------- agent
def run_discovery(
    model_id: str,
    source_paths: list[str | Path],
    llm: StructuredLLM,
    legacy_doc_path: str | Path | None = None,
    model_hint: str | None = None,
) -> DiscoveryReport:
    """``model_hint`` names the model to describe when the source files define several (e.g. engine/models.py)."""
    sources = load_sources(source_paths)
    listing = render_listing(sources)
    raw = llm.structured(DISCOVERY_SYSTEM, discovery_user(listing, model_hint), ModelMetadata)
    metadata, warnings = verify_facts(raw, sources)

    discrepancies: list[Discrepancy] = []
    doc_name = None
    if legacy_doc_path is not None:
        doc = load_sources([legacy_doc_path])
        doc_name = next(iter(doc))
        raw_claims = llm.structured(DOC_CLAIMS_SYSTEM, doc_claims_user(render_listing(doc)), DocumentClaims)
        claims, skip, claim_warnings = verify_claims(raw_claims, doc)
        warnings += claim_warnings
        discrepancies += compare_mechanical(metadata, claims, skip)
        if claims.other_claims:
            claims_json = json.dumps([c.model_dump(include={"claim_id", "field", "statement"}) for c in claims.other_claims], indent=1)
            check = llm.structured(CLAIM_CHECK_SYSTEM, claim_check_user(claims_json, listing), ClaimCheck)
            discrepancies += assess_free_text(check, claims, sources, warnings)

    numbered = [d.model_copy(update={"discrepancy_id": f"D-{i:03d}"}) for i, d in enumerate(discrepancies, start=1)]
    return DiscoveryReport(
        model_id=model_id,
        language=detect_language(source_paths[0]),
        source_files=list(sources),
        legacy_document=doc_name,
        metadata=metadata,
        discrepancies=numbered,
        evidence_warnings=warnings,
        llm_model=llm.model,
    )


# --------------------------------------------------------------------------- scoring (run by Person 1)
# Person 1's answer-key entries (see their DiscoveryAgent) and the report field that holds each fact.
ANSWER_KEY_FIELDS = {
    "expected_model_type": "algorithm",
    "expected_training_function": "algorithm",
    "expected_link": "algorithm",
    "expected_target": "target_variable",
}
# Scored even when the key lists none, so a correct document (the control case) exposes false alarms.
# Omissions are scored only when the key lists at least one expected omission; otherwise they are "not_scored".
ALWAYS_SCORED_TYPES: frozenset[str] = frozenset({"contradiction", "unverifiable"})
SUPPORTED_EVIDENCE = frozenset({"verified", "not_required"})


class ExpectedDiscrepancy(BaseModel):
    """One entry of a model's list under the answer key's ``discrepancies``. The description never enters the score."""

    id: str
    field: DiscrepancyField
    type: DiscrepancyType
    description: str = ""


def _words(text: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _score_facts(report: DiscoveryReport, answer_key: dict) -> dict:
    """An entry counts as found when every word of the expected value appears in the reported fact or its
    verified code evidence. Keys this report has no field for are listed in ``unmapped_keys`` and count as missed.
    """
    expected = {k: v for k, v in answer_key.items() if k.startswith("expected_")}
    matched, missed, unmapped, reported = [], [], [], 0
    for key, value in expected.items():
        field = ANSWER_KEY_FIELDS.get(key)
        fact = getattr(report.metadata, field) if field else None
        if fact is None or fact.status == "missing" or fact.value is None:
            (unmapped if field is None else missed).append(key)
            continue
        reported += 1
        found = _words(fact.value).union(*(_words(r.quote) for r in fact.evidence))
        (matched if _words(value) <= found else missed).append(key)
    return {
        "recall": len(matched) / len(expected) if expected else 0.0,
        "precision": len(matched) / reported if reported else 0.0,
        "matched": matched,
        "missed": missed + unmapped,
        "unmapped_keys": unmapped,
    }


def evidence_status(discrepancy: Discrepancy, code: Sources) -> str:
    """verified: every cited reference is found again in the model's source files; unresolved: one is not;
    missing: nothing cited. An unverifiable claim may have no code evidence by definition (not_required)."""
    if not discrepancy.code_evidence:
        return "not_required" if discrepancy.type == "unverifiable" else "missing"
    resolved = all(verify_ref(ref, code) is not None for ref in discrepancy.code_evidence)
    return "verified" if resolved else "unresolved"


def score_discrepancies(report: DiscoveryReport, expected: list[ExpectedDiscrepancy], code: Sources) -> dict:
    """Match reported discrepancies one-to-one with the expected ones.

    Pass 1 pairs the same field and type (detected); pass 2 pairs the same field with a different type
    (misclassified, which is not a true positive). Leftover entries are missed; leftover findings are
    unsupported. Findings of a type outside ``scored_types`` are reported as not_scored and left out of
    precision. Findings whose evidence resolves are tried first.
    """
    ids = [e.id for e in expected]
    if len(set(ids)) != len(ids):
        raise ValueError(f"answer key for {report.model_id} repeats an id: {ids}")
    scored_types = ALWAYS_SCORED_TYPES | {e.type for e in expected}
    evidence = {d.discrepancy_id: evidence_status(d, code) for d in report.discrepancies}
    candidates = sorted((d for d in report.discrepancies if d.type in scored_types),
                        key=lambda d: (evidence[d.discrepancy_id] not in SUPPORTED_EVIDENCE, d.discrepancy_id))
    pair_of: dict[str, tuple[str, str]] = {}  # expected id or discrepancy id -> (outcome, the other id)
    for outcome, same in (("detected", lambda e, d: (e.field, e.type) == (d.field, d.type)),
                          ("misclassified", lambda e, d: e.field == d.field)):
        for e in expected:
            if e.id in pair_of:
                continue
            d = next((d for d in candidates if d.discrepancy_id not in pair_of and same(e, d)), None)
            if d is not None:
                pair_of[e.id], pair_of[d.discrepancy_id] = (outcome, d.discrepancy_id), (outcome, e.id)

    key_entries = [{"id": e.id, "field": e.field, "type": e.type, "outcome": pair_of.get(e.id, ("missed", None))[0],
                    "discrepancy_id": pair_of.get(e.id, (None, None))[1]} for e in expected]
    findings = []
    for d in report.discrepancies:
        default = "unsupported" if d.type in scored_types else "not_scored"
        outcome, expected_id = pair_of.get(d.discrepancy_id, (default, None))
        findings.append({"discrepancy_id": d.discrepancy_id, "field": d.field, "type": d.type,
                         "evidence": evidence[d.discrepancy_id], "outcome": outcome, "expected_id": expected_id})
    counts = {name: sum(f["outcome"] == name for f in findings)
              for name in ("detected", "misclassified", "unsupported", "not_scored")}
    counts["missed"] = sum(e["outcome"] == "missed" for e in key_entries)
    counts["detected_without_evidence"] = sum(f["outcome"] == "detected" and f["evidence"] not in SUPPORTED_EVIDENCE
                                              for f in findings)
    return {
        "scored_types": sorted(scored_types),
        "recall": _ratio(counts["detected"], len(expected)),
        "precision": _ratio(counts["detected"], len(candidates)),
        "recall_with_evidence": _ratio(counts["detected"] - counts["detected_without_evidence"], len(expected)),
        "counts": {"expected": len(expected), "scored_findings": len(candidates), **counts},
        "key_entries": key_entries,
        "findings": findings,
    }


def score_discovery(report: DiscoveryReport, answer_key: dict, code: Sources | None = None) -> dict:
    """Score a Discovery report against Person 1's answer key; run by Person 1, who holds the key.

    The key holds ``expected_*`` metadata values (scored as before, top-level ``recall``/``precision``) and,
    optionally, ``discrepancies``: a mapping from model id to a list of ``{id, field, type, description}``.
    A model with no list there gets ``"discrepancies": null``; an empty list is the false-alarm control case.
    ``code`` defaults to the report's source files, read from the current directory.
    """
    entries = (answer_key.get("discrepancies") or {}).get(report.model_id)
    discrepancies = None
    if entries is not None:
        if code is None:
            code = load_sources([p for p in report.source_files if Path(p).is_file()])
        discrepancies = score_discrepancies(report, [ExpectedDiscrepancy.model_validate(e) for e in entries], code)
    return {
        "model_id": report.model_id,
        **_score_facts(report, answer_key),
        "discrepancies": discrepancies,
        "report_generated_at": report.generated_at,
        "scored_at": utc_now(),
    }


def save_report(report: DiscoveryReport, reports_dir: Path = REPORTS_DIR) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report.model_id}_discovery.json"
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------ compatibility with Person 1's code
# Verbatim from the ml-engineering branch (commit fdad799), where Person 1's engine/pipeline.py (generate_agent_reports) uses it.
# Kept here so that code keeps working when the two branches are merged.
class DiscoveryAgent:
    name = "discovery"

    def run(
        self,
        source: str | Path,
        document: str | Path | None = None,
        answer_key: str | Path | None = None,
    ) -> AgentResult:
        source_name, text = read_source(source)
        lower = text.lower()
        def line_for(pattern: str) -> int | None:
            for number, line in enumerate(text.splitlines(), start=1):
                if re.search(pattern, line, re.IGNORECASE):
                    return number
            return None

        fields = {
            "model_type": "binomial logistic regression" if "glm" in lower and "binomial" in lower else None,
            "training_function": "glm" if re.search(r"\bglm\b", lower) else None,
            "link": "logit" if re.search(r"\blogit\b", lower) else None,
            "target": "target" if re.search(r"\btarget\b", lower) else None,
        }
        patterns = {
            "model_type": r"\bglm\s*\(",
            "training_function": r"\bglm\s*\(",
            "link": r"\blogit\b",
            "target": r"\btarget\b",
        }
        evidence = [
            Evidence(source_name, f"{key} observed at source line {line_for(patterns[key])}", value=value)
            for key, value in fields.items()
            if value is not None
        ]
        missing = [key for key, value in fields.items() if value is None]
        findings = [
            Finding("model-facts", "Documented model facts", "observed", "Facts extracted without inference.", tuple(evidence)),
        ]
        if missing:
            findings.append(
                Finding("discovery-gaps", "Undocumented model facts", "gap", f"Not found: {', '.join(missing)}.", severity="warning")
            )
        metrics = {}
        if answer_key is not None:
            expected = json.loads(Path(answer_key).read_text(encoding="utf-8"))
            expected_values = {
                "model_type": expected.get("expected_model_type", "").replace("_", " "),
                "training_function": expected.get("expected_training_function"),
                "link": expected.get("expected_link"),
                "target": expected.get("expected_target"),
            }
            observed = {key for key, value in fields.items() if value is not None}
            truth = set(expected_values)
            predicted = {key for key, value in fields.items() if value is not None}
            true_positive = len(observed & truth)
            metrics = {
                "precision": true_positive / len(predicted) if predicted else 0.0,
                "recall": true_positive / len(truth) if truth else 0.0,
            }
        return AgentResult(
            self.name,
            "Extracted only facts present in the supplied document.",
            findings,
            metrics=metrics,
            recommendations=["Provide primary training artifacts for each undocumented fact."] if missing else [],
            evidence=evidence,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Discovery Agent on model source files.")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--source", action="append", help="repository-relative path; repeat for each file")
    parser.add_argument("--doc", help="existing model document to compare with the code")
    parser.add_argument("--replay", help="directory of canned LLM replies (offline demo)")
    parser.add_argument("--model-hint", help="which model to describe when the files define several")
    parser.add_argument("--score", metavar="ANSWER_KEY",
                        help="score the saved report against an answer key instead of running the agent (Person 1)")
    args = parser.parse_args()
    if args.score:
        saved = DiscoveryReport.model_validate_json((REPORTS_DIR / f"{args.model_id}_discovery.json").read_text())
        score = score_discovery(saved, json.loads(Path(args.score).read_text()))
        out = REPORTS_DIR / f"{args.model_id}_score.json"
        out.write_text(json.dumps(score, indent=2) + "\n")
        summary = f"facts recall {score['recall']:.2f}, precision {score['precision']:.2f}"
        if score["discrepancies"] is not None:
            counts = score["discrepancies"]["counts"]
            summary += "; discrepancies " + ", ".join(f"{k} {v}" for k, v in counts.items())
        raise SystemExit(f"wrote {out}: {summary}")
    if not args.source:
        parser.error("--source is required (or pass --score)")
    if args.replay:
        from llm.client import ReplayLLM

        client: StructuredLLM = ReplayLLM(args.replay)
    else:
        client, status = llm_from_env()
        if client is None:
            parser.error(status)
    result = run_discovery(args.model_id, args.source, client, args.doc, args.model_hint)
    print(f"wrote {save_report(result)}: {len(result.discrepancies)} discrepancies, {len(result.evidence_warnings)} warnings")
