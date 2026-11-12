"""Documentation Agent — plan step 6.

Builds a model card from the verified discovery report, the inventory record and Person 1's
result files. Every number in a table is copied by code from a cited file. The LLM (optional)
writes three prose fields only; a draft that contains numbers not found in the input facts is
replaced by the template text, and the replacement is recorded in ``grounding_warnings``.

Usage:
    python -m agents.documentation_agent --model-id legacy-r-logistic [--no-llm | --replay DIR]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from agents.discovery_agent import format_split
from inventory.registry import InventoryRecord, get_record, load_inventory
from inventory.risk_tier import TIER_RULE
from llm.client import StructuredLLM, llm_from_env
from llm.evidence import ungrounded_numbers
from llm.prompts import MODEL_CARD_SYSTEM, model_card_user
from llm.schemas import (AgentResult, CardRow, CardSection, DiscoveryReport, Evidence, Fact, Finding, ModelCard,
                         ModelCardNarrative, SourceRef)
from workflow.artifacts import PERSON1_MODEL, PERSON1_SHAP_KEYS, Artifacts, person1_shap

from ._common import read_source

EvidenceFiles = dict[str, tuple[str, dict[str, Any]]]  # kind -> (file path, parsed JSON)

REPORTS_ROOT = Path("reports")
MODEL_CARDS_DIR = Path("docs/model_cards")
SS1_23_MAPPING = Path("governance/ss1_23_mapping.json")
SKIP_KEYS = frozenset({"fairlearn", "feature_names"})  # duplicates of by_group / long name lists in Person 1's report
VALIDATION_SECTIONS = (  # keys of Person 1's reports/validation/validation_results.json
    ("metrics", "Performance metrics"),
    ("fairness", "Fairness considerations"),
    ("stability", "Stability"),
    ("explainability", "Explainability"),
)
DATASET_SOURCE = "UCI dataset description, https://archive.ics.uci.edu/dataset/350"
DATASET_ROWS = [
    CardRow(label="Dataset", value="Default of Credit Card Clients (UCI Machine Learning Repository)", source=DATASET_SOURCE),
    CardRow(label="Records", value="30,000", source=DATASET_SOURCE),
    CardRow(label="Input variables", value="23", source=DATASET_SOURCE),
    CardRow(label="Origin", value="Credit-card clients in Taiwan, payment history April to September 2005", source=DATASET_SOURCE),
    CardRow(label="Intended use here", value="Public demonstration data only; not representative of a UK bank's current portfolio",
            source="Project plan, step 2"),
]
DATASET_LIMITATION = ("The demonstration dataset is historical Taiwanese credit-card data and is not representative "
                      "of a UK bank's current credit portfolio.")
APPROVAL_WORDS = re.compile(r"\b(approved|signed[ -]off|certified|independently validated)\b", re.IGNORECASE)


# --------------------------------------------------------------------------- evidence files
def load_evidence(model_id: str, root: Path = Path(".")) -> EvidenceFiles:
    """Person 1's live validation and parity reports for this model (never the sample copies)."""
    artifacts = Artifacts(root)
    evidence = {kind: (artifacts.relpath(kind, model_id), data) for kind in ("validation", "parity")
                if (data := artifacts.load(kind, model_id)) is not None}
    if "validation" not in evidence:
        shap = person1_shap(artifacts.load("validation", PERSON1_MODEL), model_id)
        if shap is not None:  # only this model's SHAP block, nothing that belongs to the migrated model
            evidence["validation"] = (artifacts.relpath("validation", PERSON1_MODEL),
                                      {"explainability": {PERSON1_SHAP_KEYS[model_id]: shap}})
    return evidence


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3e}" if value and abs(value) < 1e-3 else f"{round(value, 4):,}"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def _flatten(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if key in SKIP_KEYS:
            continue
        rows += _flatten(value, path) if isinstance(value, dict) else [(path, value)]
    return rows


def _rows_from(file: str, data: dict[str, Any], prefix: str) -> list[CardRow]:
    return [CardRow(label=label, value=_fmt(value), source=f"{file}#{prefix}.{label}") for label, value in _flatten(data)]


def _pending(key: str, title: str, stage: str) -> CardSection:
    return CardSection(key=key, title=title, status="pending", source="evidence",
                       text=f"Pending: produced at the {stage} stage. No figures are shown until the report exists.")


def _validation_section(key: str, title: str, evidence: EvidenceFiles) -> CardSection:
    if "validation" not in evidence or not isinstance(evidence["validation"][1].get(key), dict):
        return _pending(key, title, "Validate")
    file, data = evidence["validation"]
    return CardSection(key=key, title=title, source="evidence", rows=_rows_from(file, data[key], key))


# --------------------------------------------------------------------------- narrative
def _value(fact: Fact) -> Any:
    return None if fact.status == "missing" else fact.value


def _facts(discovery: DiscoveryReport, record: InventoryRecord, evidence: EvidenceFiles) -> dict[str, Any]:
    md = discovery.metadata
    train_fraction = _value(md.train_fraction)
    return {
        "model_id": record.model_id,
        "model_name": record.name,
        "business_purpose": record.business_purpose,
        "language": discovery.language,
        "algorithm": _value(md.algorithm) or record.algorithm,
        "target_variable": _value(md.target_variable),
        "input_features": _value(md.input_features) or [],
        "excluded_columns": _value(md.excluded_columns) or [],
        "preprocessing_steps": _value(md.preprocessing_steps) or [],
        "train_fraction": train_fraction,
        "test_fraction": None if train_fraction is None else round(1 - train_fraction, 6),
        "decision_threshold": _value(md.decision_threshold),
        "inferred_fields": [n for n in type(md).model_fields if isinstance(getattr(md, n), Fact) and getattr(md, n).status == "inferred"],
        "assumptions": [f.value for f in md.assumptions if _value(f)],
        "limitations": [f.value for f in md.limitations if _value(f)],
        "missing_information": md.missing_information,
        "risk_tier": record.risk_tier,
        "dataset": {row.label: row.value for row in DATASET_ROWS},
        "results": _result_facts(evidence),
    }


def _result_facts(evidence: EvidenceFiles) -> dict[str, Any]:
    """The headline results the prose may mention; full tables stay in the evidence sections."""
    out: dict[str, Any] = {}
    if "validation" in evidence:
        report = evidence["validation"][1]
        out["validation_metrics"] = report.get("metrics", {})
        out["fairness_summary"] = {
            group: {k: d.get(k) for k in ("demographic_parity_difference", "disparate_impact")}
            for group, d in (report.get("fairness") or {}).items() if isinstance(d, dict)
        }
        out["prediction_psi_train_vs_test"] = (report.get("stability") or {}).get("prediction_psi")
    if "parity" in evidence:
        parity = evidence["parity"][1].get("r_vs_statsmodels") or {}
        out["parity_r_vs_statsmodels"] = {k: parity.get(k) for k in (
            "overall_pass", "mae", "max_probability_difference", "tolerance", "classification_agreement")}
    return out


def _template_narrative(f: dict[str, Any]) -> dict[str, str]:
    target = f["target_variable"] or "a target that is not documented in the code"
    overview = (f"{f['model_name']} ({f['model_id']}) is implemented in {f['language']} using {f['algorithm']}. "
                f"{f['business_purpose']} It predicts {target}.")
    parts = [f"The model is fitted on {len(f['input_features'])} input features." if f["input_features"]
             else "The input features are not documented in the code."]
    if f["excluded_columns"]:
        parts.append(f"Excluded from the predictors: {', '.join(f['excluded_columns'])}.")
    if f["preprocessing_steps"]:
        parts.append(f"Preprocessing: {'; '.join(f['preprocessing_steps'])}.")
    if f["train_fraction"] is not None:
        parts.append(f"Data split: {format_split(f['train_fraction'])}.")
    if f["decision_threshold"] is not None:
        parts.append(f"A predicted probability above {f['decision_threshold']:g} is classed as default.")
    limits = [*f["assumptions"], *f["limitations"]]
    if f["missing_information"]:
        limits.append(f"Not determinable from the code: {'; '.join(f['missing_information'])}.")
    limits.append(DATASET_LIMITATION)
    return {"overview": overview, "methodology": " ".join(parts), "limitations": " ".join(limits)}


def _narrative(facts: dict[str, Any], has_approvals: bool, llm: StructuredLLM | None) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Return ``(texts, sources, warnings)`` for the overview, methodology and limitations fields."""
    template = _template_narrative(facts)
    if llm is None:
        return template, dict.fromkeys(template, "template"), []
    facts_json = json.dumps(facts, indent=1)
    draft = llm.structured(MODEL_CARD_SYSTEM, model_card_user(facts_json), ModelCardNarrative)
    texts, sources, warnings = {}, {}, []
    for key in template:
        text = getattr(draft, key)
        bad = ungrounded_numbers(text, facts_json)
        if bad:
            texts[key], sources[key] = template[key], "template"
            warnings.append(f"{key}: LLM draft replaced by template text; numbers not found in the evidence: {', '.join(bad)}.")
            continue
        texts[key], sources[key] = text, "llm_draft"
        if not has_approvals and APPROVAL_WORDS.search(text):
            warnings.append(f"{key}: the draft mentions approval or validation but none is recorded; check the wording.")
    return texts, sources, warnings


# --------------------------------------------------------------------------- sections
def _cite_refs(refs: list[SourceRef]) -> str:
    return "; ".join(f"{r.file}:L{r.line_start}" + (f"-{r.line_end}" if r.line_end != r.line_start else "") for r in refs)


def _cite(fact: Fact) -> str:
    refs = _cite_refs(fact.evidence)
    return f"{refs} ({fact.status})" if refs else fact.status


def _show(value: Any) -> str:
    if value is None or value == []:
        return "Not determined from the code"
    return ", ".join(value) if isinstance(value, list) else _fmt(value)


def _features_section(discovery: DiscoveryReport) -> CardSection:
    md = discovery.metadata
    features = _value(md.input_features) or []
    rows = [
        CardRow(label="Target variable", value=_show(_value(md.target_variable)), source=_cite(md.target_variable)),
        CardRow(label=f"Input features ({len(features)})", value=_show(features), source=_cite(md.input_features)),
        CardRow(label="Excluded columns", value=_show(_value(md.excluded_columns)), source=_cite(md.excluded_columns)),
        CardRow(label="Preprocessing", value=_show(_value(md.preprocessing_steps)), source=_cite(md.preprocessing_steps)),
        CardRow(label="Train/test split", source=_cite(md.train_fraction),
                value=format_split(md.train_fraction.value) if _value(md.train_fraction) is not None else _show(None)),
        CardRow(label="Decision threshold", value=_show(_value(md.decision_threshold)), source=_cite(md.decision_threshold)),
    ]
    return CardSection(key="features_and_target", title="Input features and target", source="discovery", rows=rows)


def _governance_section(record: InventoryRecord, discovery: DiscoveryReport, mapping_path: Path) -> CardSection:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    principles = [p for stage in mapping["stages"] if stage["stage"] in ("discover", "document") for p in stage["principles"]]
    rows = [
        CardRow(label="Risk tier", value=f"Tier {record.risk_tier}", source="inventory (computed by rule)"),
        CardRow(label="Materiality", value=f"{record.materiality}: {record.materiality_basis}", source="inventory"),
        CardRow(label="Complexity", value=f"{record.complexity}: {record.complexity_basis}", source="inventory"),
        CardRow(label="Tier rule", value=TIER_RULE, source="SS1/23 1.3"),
        CardRow(label="Tier rationale", value=record.tier_rationale or "Not drafted", source=record.tier_rationale_source),
        CardRow(label="Tier review status", value=record.tier_status, source="inventory"),
        CardRow(label="Approval records", value=", ".join(record.approval_history) or "None recorded", source="governance/approval_log.json"),
        CardRow(label="Discovery report status", value=discovery.review_status, source=f"reports/discovery/{discovery.model_id}_discovery.json"),
        CardRow(label="Model card status", value="pending_human_review", source="this card"),
        # Cite the repository path, wherever the mapping was read from.
        CardRow(label="SS1/23 principles covered", value="; ".join(principles), source=SS1_23_MAPPING.as_posix()),
    ]
    return CardSection(key="governance", title="Risk tier, approval and governance", source="inventory", rows=rows)


def _corrections_section(discovery: DiscoveryReport) -> CardSection:
    title = "Corrections to the existing model document"
    if discovery.legacy_document is None:
        return CardSection(key="corrections", title=title, source="discovery", text="No existing model document was compared.")
    if not discovery.discrepancies:
        return CardSection(key="corrections", title=title, source="discovery",
                           text=f"No discrepancies found between {discovery.legacy_document} and the code.")
    rows = [
        CardRow(label=f"{d.discrepancy_id} {d.field} ({d.type})",
                value=f"Document: {d.documented_claim} Correction: {d.suggested_correction}",
                source=_cite_refs(d.code_evidence) or "no code evidence")
        for d in discovery.discrepancies
    ]
    return CardSection(key="corrections", title=title, source="discovery",
                       text=f"Compared with {discovery.legacy_document}.", rows=rows)


# --------------------------------------------------------------------------- agent
def build_model_card(
    discovery: DiscoveryReport,
    record: InventoryRecord,
    evidence: EvidenceFiles | None = None,
    llm: StructuredLLM | None = None,
    mapping_path: Path = SS1_23_MAPPING,
) -> ModelCard:
    evidence = evidence or {}
    facts = _facts(discovery, record, evidence)
    texts, sources, warnings = _narrative(facts, bool(record.approval_history), llm)
    sections = [
        CardSection(key="overview", title="Model overview and intended purpose", source=sources["overview"], text=texts["overview"]),
        CardSection(key="dataset", title="Dataset and data provenance", source="constant", rows=DATASET_ROWS),
        CardSection(key="methodology", title="Algorithm and methodology", source=sources["methodology"], text=texts["methodology"]),
        _features_section(discovery),
        *[_validation_section(key, title, evidence) for key, title in VALIDATION_SECTIONS],
    ]
    if "parity" in evidence:
        file, data = evidence["parity"]
        sections.append(CardSection(key="parity", title="Redevelopment and parity", source="evidence", rows=_rows_from(file, data, "parity")))
    sections += [
        CardSection(key="limitations", title="Limitations and assumptions", source=sources["limitations"], text=texts["limitations"]),
        _governance_section(record, discovery, mapping_path),
        _corrections_section(discovery),
    ]
    return ModelCard(
        model_id=record.model_id,
        model_name=record.name,
        version=record.version,
        risk_tier=record.risk_tier,
        sections=sections,
        grounding_warnings=warnings,
        generated_by=f"Documentation Agent (LLM: {llm.model})" if llm else "Documentation Agent (template, no LLM)",
    )


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(card: ModelCard) -> str:
    lines = [
        f"# Model card: {card.model_name} ({card.model_id})",
        "",
        f"Version {card.version} · Risk tier {card.risk_tier} · Review status: **{card.review_status}**  ",
        f"Generated {card.generated_at} by {card.generated_by}",
        "",
        "> Draft for human review. Figures are copied from the cited files; no approval is implied.",
        "",
    ]
    for section in card.sections:
        lines += [f"## {section.title}", ""]
        if section.text:
            lines += [f"_{section.text}_" if section.status == "pending" else section.text, ""]
        if section.rows:
            lines += ["| Item | Value | Evidence |", "|---|---|---|"]
            lines += [f"| {_md(r.label)} | {_md(r.value)} | {_md(r.source)} |" for r in section.rows]
            lines.append("")
    if card.grounding_warnings:
        lines += ["## Grounding warnings", "", *[f"- {w}" for w in card.grounding_warnings], ""]
    return "\n".join(lines)


def save_model_card(card: ModelCard, reports_root: Path = REPORTS_ROOT, cards_dir: Path = MODEL_CARDS_DIR) -> tuple[Path, Path]:
    json_path = reports_root / "documentation" / f"{card.model_id}_model_card.json"
    md_path = cards_dir / f"{card.model_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(card.model_dump_json(indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(card), encoding="utf-8")
    return json_path, md_path


# ------------------------------------------------------------------ compatibility with Person 1's code
# Verbatim from the ml-engineering branch (commit fdad799), where Person 1's engine/pipeline.py (generate_agent_reports) uses it.
# Kept here so that code keeps working when the two branches are merged.
class DocumentationAgent:
    name = "documentation"
    required_sections = ("preprocessing", "data split", "random seed", "dataset version", "fairness assumptions")

    def run(self, source: str | Path) -> AgentResult:
        source_name, text = read_source(source)
        lower = text.lower()
        missing = []
        for section in self.required_sections:
            explicitly_missing = any(
                re.search(r"missing\s*:[^\n]*\b" + re.escape(section) + r"\b", line)
                for line in lower.splitlines()
            )
            if section not in lower or explicitly_missing:
                missing.append(section)
        evidence = [Evidence(source_name, f"Required section '{section}' is absent", value=False) for section in missing]
        findings = [
            Finding("documentation-completeness", "Documentation completeness", "gap" if missing else "complete",
                    f"{len(missing)} of {len(self.required_sections)} required sections are absent.", tuple(evidence),
                    severity="warning" if missing else "info")
        ]
        return AgentResult(self.name, "Documentation was checked against explicit required sections.",
                           findings, recommendations=[f"Document {item} from the authoritative artifact." for item in missing],
                           evidence=evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a model card for human review.")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--discovery", help="discovery report (default: reports/discovery/<model-id>_discovery.json)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--no-llm", action="store_true", help="template prose only")
    mode.add_argument("--replay", help="directory of canned LLM replies (offline demo)")
    args = parser.parse_args()
    report_path = Path(args.discovery or REPORTS_ROOT / "discovery" / f"{args.model_id}_discovery.json")
    report = DiscoveryReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    if args.no_llm:
        client: StructuredLLM | None = None
    elif args.replay:
        from llm.client import ReplayLLM

        client = ReplayLLM(args.replay)
    else:
        client, status = llm_from_env()
        print(status if client else f"{status}; using template prose")
    card = build_model_card(report, get_record(load_inventory(), args.model_id), load_evidence(args.model_id), client)
    json_out, md_out = save_model_card(card)
    print(f"wrote {json_out} and {md_out}; {len(card.grounding_warnings)} grounding warning(s)")
