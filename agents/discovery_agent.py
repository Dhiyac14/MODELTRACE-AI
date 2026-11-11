"""Model Intelligence (Discovery) Agent — plan step 5.

1. LLM extracts model metadata from source code, with line references.
2. Code verifies every reference (``llm.evidence``).
3. If an existing model document is given, the LLM lists its claims (also verified against the document).
4. Feature list, decision threshold and split ratio are compared in Python.
5. The LLM judges the remaining free-text claims; its code citations are verified, and a
   contradiction without verified code evidence is downgraded to "unverifiable".

Usage:
    python -m agents.discovery_agent --model-id LR-R-001 \\
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
    ClaimCheck,
    Discrepancy,
    DiscoveryReport,
    DocumentClaims,
    Documented,
    Fact,
    ModelMetadata,
)

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
) -> DiscoveryReport:
    sources = load_sources(source_paths)
    listing = render_listing(sources)
    raw = llm.structured(DISCOVERY_SYSTEM, discovery_user(listing), ModelMetadata)
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


def save_report(report: DiscoveryReport, reports_dir: Path = REPORTS_DIR) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report.model_id}_discovery.json"
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Discovery Agent on model source files.")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--source", action="append", required=True, help="repository-relative path; repeat for each file")
    parser.add_argument("--doc", help="existing model document to compare with the code")
    parser.add_argument("--replay", help="directory of canned LLM replies (offline demo)")
    args = parser.parse_args()
    if args.replay:
        from llm.client import ReplayLLM

        client: StructuredLLM = ReplayLLM(args.replay)
    else:
        client, status = llm_from_env()
        if client is None:
            parser.error(status)
    result = run_discovery(args.model_id, args.source, client, args.doc)
    print(f"wrote {save_report(result)}: {len(result.discrepancies)} discrepancies, {len(result.evidence_warnings)} warnings")
