"""Model Intelligence (Discovery) Agent — plan step 5.

1. LLM extracts model metadata from source code, with line references.
2. Code verifies every reference (``llm.evidence``).
3. If an existing model document is given, the LLM lists its claims (also verified against the document).
4. Feature list, decision threshold and split ratio are compared in Python.
5. The LLM judges the remaining free-text claims; its code citations are verified, and a
   contradiction without verified code evidence is downgraded to "unverifiable". Both LLM steps that read the
   code get the same model scope, including the model's inventory ID and code name when they differ; a model
   name contradiction between those two names is not reported.

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

from pydantic import BaseModel, ConfigDict, ValidationError

from llm.client import StructuredLLM, llm_from_env
from llm.evidence import Sources, load_sources, render_listing, verify_facts, verify_ref, verify_refs
from llm.prompts import (
    CLAIM_CHECK_SYSTEM,
    DISCOVERY_SYSTEM,
    DOC_CLAIMS_SYSTEM,
    claim_check_user,
    discovery_user,
    doc_claims_user,
    model_scope,
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
    SourceRef,
    utc_now,
)

from inventory.registry import get_record, load_inventory
from workflow.artifacts import PERSON1_BUNDLE_NAMES, PERSON1_MODEL

from ._common import read_source

REPORTS_DIR = Path("reports/discovery")
REPO_ROOT = Path(__file__).resolve().parents[1]
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


def model_names(model_id: str) -> frozenset[str]:
    """The model's inventory ID and, if it has one, the name its code gives it (``PERSON1_BUNDLE_NAMES``)."""
    return frozenset({model_id, PERSON1_BUNDLE_NAMES.get(model_id, model_id)})


def _names_one_of(text: str, names: frozenset[str]) -> bool:
    """``text`` contains one of ``names`` as a whole identifier (gradient_boosting, not gradient_boosting_shap)."""
    return any(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) for name in names)


def assess_free_text(check: ClaimCheck, claims: DocumentClaims, sources: Sources, warnings: list[str],
                     same_model: frozenset[str] = frozenset()) -> list[Discrepancy]:
    """``same_model`` holds the names of the model under review (``model_names``). A model_name contradiction whose
    claim and code evidence each use one of them only says the document and the code name the model differently,
    so it is not reported (a warning records it)."""
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
        if (verdict == "contradiction" and claim.field == "model_name" and _names_one_of(claim.statement, same_model)
                and any(_names_one_of(ref.quote, same_model) for ref in evidence)):
            warnings.append(f"claim {a.claim_id} (model_name) not reported: the document and the code use names of "
                            f"the same model ({', '.join(sorted(same_model))}).")
            continue
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
    """``model_hint`` names the model to describe when the source files define several (e.g. engine/models.py).
    The metadata and claim-check prompts get the same scope: the hint plus, when registered, the model's code name."""
    sources = load_sources(source_paths)
    listing = render_listing(sources)
    scope = model_scope(model_hint, model_id, PERSON1_BUNDLE_NAMES.get(model_id))
    raw = llm.structured(DISCOVERY_SYSTEM, discovery_user(listing, scope), ModelMetadata)
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
            check = llm.structured(CLAIM_CHECK_SYSTEM, claim_check_user(claims_json, listing, scope), ClaimCheck)
            discrepancies += assess_free_text(check, claims, sources, warnings, model_names(model_id))

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
# A contradiction or omission must point at code; an unverifiable claim is one the code cannot settle.
EVIDENCE_REQUIRED_TYPES: frozenset[str] = frozenset({"contradiction", "omission"})
# Share of the cited lines' text the quote must cover (ignoring whitespace).
MIN_QUOTE_COVERAGE = 0.5


class ExpectedDiscrepancy(BaseModel):
    """One entry of a model's list under the answer key's ``discrepancies``. The description never enters the score."""

    model_config = ConfigDict(coerce_numbers_to_str=True)  # numeric ids such as 1 are read as "1"

    id: str
    field: DiscrepancyField
    type: DiscrepancyType
    description: str = ""


def _words(text: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _for_model(answer_key: dict, section: str, model_id: str, kind: type) -> dict | list | None:
    """The model's entry in a per-model section of the key (``metadata`` or ``discrepancies``), or None."""
    mapping = answer_key.get(section)
    if mapping is None:
        return None
    if not isinstance(mapping, dict):
        raise ValueError(f"answer key '{section}' must map each model id to its entry, e.g. "
                         f"{{\"{model_id}\": {'[...]' if kind is list else '{...}'}}}")
    entry = mapping.get(model_id)
    if entry is not None and not isinstance(entry, kind):
        raise ValueError(f"answer key '{section}' entry for {model_id} must be a {'list' if kind is list else 'mapping'}")
    return entry


def expected_metadata(answer_key: dict, model_id: str) -> dict:
    """The model's ``expected_*`` values: its entry under ``metadata`` if the key has one, else the top-level
    values, which were written for the legacy R model only. Empty (not scored) for any other model, and for any
    model listed under ``metadata`` with ``{}`` or null."""
    per_model = _for_model(answer_key, "metadata", model_id, dict)
    if per_model is None and model_id in (answer_key.get("metadata") or {}):
        return {}  # listed with null: switched off, like {}
    if per_model is not None:
        unprefixed = sorted(k for k in per_model if not k.startswith("expected_"))
        if unprefixed:
            raise ValueError(f"answer key 'metadata' entry for {model_id} has keys without the expected_ prefix: "
                             f"{unprefixed}")
        return dict(per_model)
    if model_id == PERSON1_MODEL:
        return {k: v for k, v in answer_key.items() if k.startswith("expected_")}
    return {}


def _score_facts(report: DiscoveryReport, expected: dict) -> dict:
    """An entry counts as found when every word of the expected value appears in the reported fact or its
    verified code evidence. Keys this report has no field for are listed in ``unmapped_keys`` and count as missed.
    With no expected values the facts are not scored and recall and precision are None.
    """
    if not expected:
        return {"metadata_scored": False, "recall": None, "precision": None, "matched": [], "missed": [],
                "unmapped_keys": []}
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
        "metadata_scored": True,
        "recall": len(matched) / len(expected),
        "precision": len(matched) / reported if reported else 0.0,
        "matched": matched,
        "missed": missed + unmapped,
        "unmapped_keys": unmapped,
    }


def _nonspace(text: str) -> str:
    return "".join(text.split())


def _at_cited_lines(ref: SourceRef, code: Sources) -> bool:
    """The quote is at the lines it cites, in a file of the model's code (exact path), and is most of those lines.

    Stricter than ``verify_ref``, which accepts a quote anywhere in the file and matches files by base name: a
    fragment such as "e" or "0.5" must not count as code evidence. Every quote the agent writes covers its cited
    lines in full.
    """
    lines = code.get(ref.file)
    if lines is None or not 1 <= ref.line_start <= ref.line_end <= len(lines):
        return False
    cited = " ".join(lines[ref.line_start - 1 : ref.line_end])
    quote = " ".join(ref.quote.split())
    return bool(quote) and quote in " ".join(cited.split()) and \
        len(_nonspace(quote)) >= MIN_QUOTE_COVERAGE * len(_nonspace(cited))


def evidence_status(discrepancy: Discrepancy, code: Sources) -> str:
    """verified: every cited quote is still at its cited lines in the model's code; unresolved: one is not
    (changed, moved, a fragment of the line, or in a file that is not the model's code); missing: nothing cited;
    not_required: an unverifiable claim with nothing cited."""
    if not discrepancy.code_evidence:
        return "missing" if discrepancy.type in EVIDENCE_REQUIRED_TYPES else "not_required"
    return "verified" if all(_at_cited_lines(ref, code) for ref in discrepancy.code_evidence) else "unresolved"


def _supported(discrepancy_type: str, evidence: str) -> bool:
    return evidence == "verified" or discrepancy_type not in EVIDENCE_REQUIRED_TYPES


def _unique(ids: list[str], what: str) -> None:
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise ValueError(f"{what} repeats id(s): {repeated}")


def score_discrepancies(report: DiscoveryReport, expected: list[ExpectedDiscrepancy], code: Sources) -> dict:
    """Match reported discrepancies one-to-one with the expected ones.

    Pass 1 pairs the same field and type (detected); pass 2 pairs the same field with a different type
    (misclassified, which is not a true positive). Leftover entries are missed; leftover findings are
    unsupported. Findings of a type outside ``scored_types`` are reported as not_scored and left out of
    precision. Findings with supporting evidence are tried first.
    """
    _unique([e.id for e in expected], f"answer key for {report.model_id}")
    _unique([d.discrepancy_id for d in report.discrepancies], f"discovery report for {report.model_id}")
    scored_types = ALWAYS_SCORED_TYPES | {e.type for e in expected}
    evidence = {d.discrepancy_id: evidence_status(d, code) for d in report.discrepancies}
    supported = {d.discrepancy_id: _supported(d.type, evidence[d.discrepancy_id]) for d in report.discrepancies}
    candidates = sorted((d for d in report.discrepancies if d.type in scored_types),
                        key=lambda d: (not supported[d.discrepancy_id], d.discrepancy_id))
    # Two maps, because answer-key ids and report ids may look alike (both "D-001").
    entry_match: dict[str, tuple[str, str]] = {}    # expected id -> (outcome, discrepancy id)
    finding_match: dict[str, tuple[str, str]] = {}  # discrepancy id -> (outcome, expected id)
    for outcome, same in (("detected", lambda e, d: (e.field, e.type) == (d.field, d.type)),
                          ("misclassified", lambda e, d: e.field == d.field)):
        for e in expected:
            if e.id in entry_match:
                continue
            d = next((d for d in candidates if d.discrepancy_id not in finding_match and same(e, d)), None)
            if d is not None:
                entry_match[e.id] = (outcome, d.discrepancy_id)
                finding_match[d.discrepancy_id] = (outcome, e.id)

    # Entries carry no field or type: for a missed entry those are the secret, and Person 1 can look the id up
    # in the private key. A score report can therefore be shared or committed without rebuilding the key.
    key_entries = []
    for e in expected:
        outcome, discrepancy_id = entry_match.get(e.id, ("missed", None))
        key_entries.append({"id": e.id, "outcome": outcome, "discrepancy_id": discrepancy_id})
    findings = []
    for d in report.discrepancies:
        default = "unsupported" if d.type in scored_types else "not_scored"
        outcome, expected_id = finding_match.get(d.discrepancy_id, (default, None))
        findings.append({"discrepancy_id": d.discrepancy_id, "field": d.field, "type": d.type,
                         "evidence": evidence[d.discrepancy_id], "outcome": outcome, "expected_id": expected_id})
    counts = {name: sum(f["outcome"] == name for f in findings)
              for name in ("detected", "misclassified", "unsupported", "not_scored")}
    counts["missed"] = sum(e["outcome"] == "missed" for e in key_entries)
    counts["detected_without_evidence"] = sum(f["outcome"] == "detected" and not supported[f["discrepancy_id"]]
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


def private_key_path(path: str | Path) -> Path:
    """Resolve the answer key's path, refusing one inside this repository or any other git working tree (a second
    clone, say), so the real key can never be committed.

    Folders are compared by identity (``samefile``), so a differently cased path on a case-insensitive disk is caught.
    """
    resolved = Path(path).expanduser().resolve()
    for folder in (resolved, *resolved.parents):
        if folder.exists() and (folder.samefile(REPO_ROOT) or (folder / ".git").exists()):
            raise ValueError(f"answer key {path} is inside a git repository ({folder}); keep it outside, "
                             "e.g. in ~/modeltrace-private/")
    return resolved


def _expected_entries(entries: list, model_id: str) -> list[ExpectedDiscrepancy]:
    """Validate the key's entries. Errors name the entry and the problem but never echo its content."""
    out = []
    for number, entry in enumerate(entries, start=1):
        try:
            out.append(ExpectedDiscrepancy.model_validate(entry))
        except ValidationError as error:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'entry'}: {e['msg']}"
                                 for e in error.errors(include_input=False))
            raise ValueError(f"answer key entry {number} for {model_id} is invalid ({problems})") from None
    return out


def model_code(model_id: str) -> Sources:
    """The model's source files as registered in the inventory, read from this repository.

    The inventory, not the report, says which files are the model's code, so a report that lists its legacy
    document as a source cannot turn document quotes into code evidence.
    """
    try:
        paths = get_record(load_inventory(), model_id).source_files
    except KeyError as error:
        raise ValueError(f"cannot check code evidence: {error.args[0]}") from None
    missing = [p for p in paths if not (REPO_ROOT / p).is_file()]
    if missing:
        raise FileNotFoundError(f"source files of {model_id} not found: {missing}")
    return {p: (REPO_ROOT / p).read_text(encoding="utf-8").splitlines() for p in paths}


def score_discovery(report: DiscoveryReport, answer_key: dict, code: Sources | None = None) -> dict:
    """Score a Discovery report against Person 1's answer key; run by Person 1, who holds the key.

    The key holds:

    - ``expected_*`` metadata values. Top-level ones belong to the legacy R model; ``metadata`` maps any model id
      to its own ``expected_*`` values. A model with none (or ``{}``) gets ``metadata_scored: false``.
    - ``discrepancies``, a mapping from model id to a list of ``{id, field, type, description}``. A model with no
      list there gets ``"discrepancies": null``; an empty list is the false-alarm control case.

    ``code`` defaults to the model's source files from the inventory (``model_code``).
    """
    entries = _for_model(answer_key, "discrepancies", report.model_id, list)
    discrepancies = None
    if entries is not None:
        expected = _expected_entries(entries, report.model_id)
        discrepancies = score_discrepancies(report, expected, code if code is not None else model_code(report.model_id))
    return {
        "model_id": report.model_id,
        **_score_facts(report, expected_metadata(answer_key, report.model_id)),
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
    if args.score is not None:
        if not args.score.strip():  # e.g. --score "$MODELTRACE_ANSWER_KEY" with the variable unset
            parser.error("--score needs the answer key's path; is MODELTRACE_ANSWER_KEY set?")
        saved = DiscoveryReport.model_validate_json((REPORTS_DIR / f"{args.model_id}_discovery.json").read_text())
        try:
            score = score_discovery(saved, json.loads(private_key_path(args.score).read_text()))
        except (ValueError, FileNotFoundError) as error:  # key location or format, or source files not found
            parser.error(str(error))
        out = REPORTS_DIR / f"{args.model_id}_score.json"
        out.write_text(json.dumps(score, indent=2) + "\n")
        summary = (f"facts recall {score['recall']:.2f}, precision {score['precision']:.2f}" if score["metadata_scored"]
                   else "facts not scored (no expected metadata for this model)")
        if score["discrepancies"] is not None:
            counts = score["discrepancies"]["counts"]
            summary += "; discrepancies " + ", ".join(f"{k} {v}" for k, v in counts.items())
        print(f"wrote {out}: {summary}")
        raise SystemExit(0)
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
