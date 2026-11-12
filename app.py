"""MODELTRACE AI dashboard (plan step 16).

Run:  streamlit run app.py
Prototype: the acting user is picked from governance/users.json (no login) and all state is JSON.
Set MODELTRACE_ROOT to run against another copy of the data (used by the tests).
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from agents.discovery_agent import run_discovery, save_report
from agents.documentation_agent import build_model_card, load_evidence, render_markdown, save_model_card
from agents.llm_migration_agent import default_inputs, run_llm_migration, save_migration_report
from agents.monitoring_agent import PSI_HIGH, PSI_WARNING, build_alert_report, save_alert_report
from inventory.risk_tier import TIER_RULE, draft_rationale
from llm.client import llm_from_env
from llm.schemas import AlertReport, DiscoveryReport, MigrationReport, ModelCard
from workflow.alerts import RULES as ALERT_RULES
from workflow.alerts import alert_status, check_alert_action
from workflow.approvals import check_duties, load_users
from workflow.artifacts import (PERSON1_MODEL, PERSON1_SHAP_KEYS, PYTHON_CANDIDATE_SOURCE, SAMPLE_ROOT, STAGE_EVIDENCE,
                                Artifacts, parity_passed, person1_shap)
from workflow.state_machine import REOPENABLE, STAGES, SUBMITTABLE, Workflow, WorkflowError

ROOT = Path(os.environ.get("MODELTRACE_ROOT", "."))
SECTIONS = ["Executive Overview", "Discovery", "Documentation", "Migration", "Validation",
            "Risk & Evidence", "Monitoring", "Governance"]
STAGE_LABEL = {"discover": "Discover", "document": "Document", "redevelop": "Redevelop",
               "validate": "Validate", "monitor": "Monitor"}
STATUS_LABEL = {"approved": "✅ approved", "pending_review": "🕒 pending review", "rejected": "⛔ rejected",
                "changes_requested": "✏️ changes requested", "in_progress": "🔧 in progress",
                "invalidated": "♻️ invalidated", "not_started": "not started", "not_applicable": "n/a"}
GATE_ACTIONS = [("submit", "Submit for review"), ("approve", "Approve"),
                ("request_changes", "Request changes"), ("reject", "Reject")]
ALERT_ACTIONS = [("acknowledge", "Acknowledge"), ("investigate", "Investigate"), ("escalate", "Escalate"),
                 ("close", "Close"), ("request_revalidation", "Request re-validation")]

st.set_page_config(page_title="MODELTRACE AI", page_icon="🛡️", layout="wide")


@st.cache_resource
def get_llm():
    return llm_from_env(ROOT / ".env")


def ss1_23() -> dict[str, Any]:
    return json.loads((ROOT / "governance/ss1_23_mapping.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- helpers
def flash(text: str) -> None:
    st.session_state.setdefault("flash", []).append(text)


def show_flash() -> None:
    for text in st.session_state.pop("flash", []):
        st.success(text)


def act(fn, success: str) -> None:
    """Run a workflow action; show every rule it breaks, or rerun with a success message."""
    try:
        fn()
    except WorkflowError as exc:
        for problem in exc.problems:
            st.error(problem)
        return
    flash(success)
    st.rerun()


def load_display(kind: str, model_id: str) -> tuple[dict | None, str | None, bool]:
    data, path, is_sample = ARTIFACTS.load_for_display(kind, model_id)
    if is_sample:
        st.warning(f"**SAMPLE DATA** from `{path}`: placeholder, not model results. "
                   f"Person 1's report `{ARTIFACTS.relpath(kind, model_id)}` does not exist yet.")
    return data, path, is_sample


def flatten(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        rows += flatten(value, path) if isinstance(value, dict) else [(path, value)]
    return rows


def table(rows: list[dict] | pd.DataFrame) -> None:
    st.dataframe(pd.DataFrame(rows) if isinstance(rows, list) else rows, hide_index=True)


def rate(value: float | None) -> str:
    """A score ratio; None when there was nothing to divide by (no expected or no scored findings)."""
    return "n/a" if value is None else f"{value:.2f}"


def show_value(value: Any) -> str:
    """One text column: Arrow cannot hold a mix of floats, booleans and strings."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return value if isinstance(value, str) else json.dumps(value)


def kv_table(data: dict[str, Any]) -> None:
    table([{"Metric": k, "Value": show_value(v)} for k, v in flatten(data) if not k.startswith("_")])


def code_language(path: str) -> str:
    return {".r": "r", ".py": "python", ".sas": "sas", ".sql": "sql", ".md": "markdown"}.get(Path(path).suffix.lower(), "text")


def optional_agent(module: str, name: str):
    """Person 1's agents are used when present (after the branches merge); their absence must not break the app."""
    try:
        return getattr(importlib.import_module(module), name), ""
    except Exception as exc:  # ImportError, or an error inside Person 1's module
        return None, f"{module}.{name} is not available on this branch yet ({type(exc).__name__})."


# --------------------------------------------------------------------------- approval gate
def gate_panel(model_id: str, stage: str) -> None:
    st.divider()
    st.subheader(f"Approval gate · {STAGE_LABEL[stage]}")
    info = next(s for s in ss1_23()["stages"] if s["stage"] == stage)
    status = WF.statuses(model_id)[stage]
    st.markdown(f"**Status:** {STATUS_LABEL[status]}")
    st.caption(f"**Gate:** {info['gate']}  \n**SS1/23:** {'; '.join(info['principles'])}  \n"
               f"**Evidence:** `{ARTIFACTS.relpath(STAGE_EVIDENCE[stage], model_id)}`")
    if status == "not_applicable":
        st.info("This stage does not apply to this model.")
        return
    if stage in WF.stale_approvals(model_id):
        st.warning("The evidence file changed after this stage was approved. A risk manager should reopen it (Governance).")
    comment = st.text_input("Comment (required to reject or request changes)", key=f"comment-{model_id}-{stage}")
    blocked: dict[str, list[str]] = {}
    for column, (action, label) in zip(st.columns(4), GATE_ACTIONS):
        blocked[label] = WF.check(model_id, stage, action, USER)
        clicked = column.button(label, key=f"{action}-{model_id}-{stage}", disabled=bool(blocked[label]),
                                type="primary" if action == "approve" else "secondary")
        if clicked and action == "submit":
            act(lambda: WF.submit(model_id, stage, USER, comment), f"{STAGE_LABEL[stage]} submitted for review.")
        elif clicked:
            act(lambda: WF.decide(model_id, stage, USER, action, comment),
                f"{STAGE_LABEL[stage]}: '{label}' recorded.")
    reasons = {label: problems for label, problems in blocked.items() if problems}
    if reasons:
        with st.expander(f"Why some actions are unavailable for {USER.name}"):
            for label, problems in reasons.items():
                st.markdown(f"**{label}:** " + " ".join(problems))
    history = [r for r in WF.history(model_id) if r.stage == stage]
    if history:
        table([r.model_dump(include={"timestamp", "action", "actor", "role", "comment", "evidence_ref"}) for r in history])


# --------------------------------------------------------------------------- sections
def page_overview() -> None:
    st.header("Executive Overview")
    rows, pending, open_alerts, discrepancies, high_risks = [], 0, 0, 0, 0
    for record in RECORDS:
        statuses = WF.statuses(record.model_id)
        pending += sum(s == "pending_review" for s in statuses.values())
        discovery = ARTIFACTS.load("discovery", record.model_id)
        discrepancies += len(discovery["discrepancies"]) if discovery else 0
        alerts = ARTIFACTS.load("alerts", record.model_id)
        reviews = WF.alert_reviews.reviews(record.model_id)
        if alerts:
            open_alerts += sum(alert_status(reviews, a["alert_id"]) != "closed" for a in alerts["alerts"])
            high_risks += sum(a["severity"] == "high" for a in alerts["alerts"])
        rows.append({"Model": record.model_id, "Name": record.name, "Risk tier": f"Tier {record.risk_tier}",
                     "Language": record.language, "Current stage": STAGE_LABEL.get(WF.current_stage(record.model_id), "complete"),
                     **{STAGE_LABEL[s]: STATUS_LABEL[statuses[s]] for s in STAGES}})
    cols = st.columns(5)
    cols[0].metric("Models", len(RECORDS), help="Models in the inventory")
    cols[1].metric("Pending", pending, help="Stages waiting for a human approval decision")
    cols[2].metric("Open alerts", open_alerts, help="Monitoring alerts not yet closed")
    cols[3].metric("High alerts", high_risks, help="High-severity monitoring alerts")
    cols[4].metric("Discrepancies", discrepancies, help="Differences between existing documents and code")
    st.subheader("Lifecycle status")
    table(rows)
    left, right = st.columns(2)
    tiers = pd.DataFrame({"Tier": [f"Tier {r.risk_tier}" for r in RECORDS], "Model": [r.model_id for r in RECORDS]})
    left.plotly_chart(px.histogram(tiers, x="Tier", color="Tier", title="Models by risk tier (SS1/23 1.3)",
                                   category_orders={"Tier": ["Tier 1", "Tier 2", "Tier 3"]}), key="tiers")
    stages = pd.DataFrame({"Stage": [r["Current stage"] for r in rows]})
    right.plotly_chart(px.histogram(stages, x="Stage", title="Models by current lifecycle stage",
                                    category_orders={"Stage": [*STAGE_LABEL.values(), "complete"]}), key="stages")
    st.caption("Counts use live report files only; sample data is never counted here.")


def page_discovery(model_id: str) -> None:
    record = WF.record(model_id)
    st.header(f"Discovery · {record.name}")
    cols = st.columns(3)
    cols[0].metric("Risk tier", f"Tier {record.risk_tier}")
    cols[1].metric("Materiality", record.materiality)
    cols[2].metric("Complexity", record.complexity)
    st.markdown(f"**Tier review:** {STATUS_LABEL[record.tier_status]} (approved at the Discover gate)")
    st.caption(f"Tier rule (SS1/23 1.3): {TIER_RULE} The LLM may draft the rationale but never sets the tier.")
    st.markdown(f"**Tier rationale** (`{record.tier_rationale_source}`): {record.tier_rationale}")
    editable = WF.statuses(model_id)["discover"] in SUBMITTABLE
    if st.button("Draft tier rationale with the LLM", disabled=not editable or LLM is None, key="draft-tier"):
        text, source = draft_rationale(record, LLM)
        WF.update_record_fields(model_id, USER, "inventory:draft_tier_rationale", tier_rationale=text, tier_rationale_source=source)
        flash(f"Tier rationale updated ({source}).")
        st.rerun()

    with st.expander("Model source files and existing document", expanded=not record.source_files):
        sources_text = st.text_area("Source files: repository paths, one per line, main model file first",
                                    "\n".join(record.source_files), key=f"src-{model_id}")
        doc_path = st.text_input("Existing model document (optional)", record.legacy_document or "", key=f"doc-{model_id}")
        uploads = st.file_uploader("Or upload source files", accept_multiple_files=True, key=f"upload-{model_id}")
        if st.button("Save sources", disabled=not editable, key="save-sources"):
            paths = [p.strip() for p in sources_text.splitlines() if p.strip()]
            for upload in uploads or []:
                dest = ROOT / "inventory/uploads" / model_id / Path(upload.name).name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(upload.getvalue())
                paths.append(dest.relative_to(ROOT).as_posix())
            missing = [p for p in [*paths, doc_path] if p and not (ROOT / p).is_file()]
            if missing:
                st.error(f"Not found: {', '.join(missing)}")
            elif not paths:
                st.error("Give at least one source file.")
            else:
                WF.update_sources(model_id, USER, paths, doc_path or None)
                flash("Sources saved to the inventory.")
                st.rerun()

    needs = [msg for ok, msg in [(LLM is not None, "configure the LLM in .env"),
                                 (bool(record.source_files), "save the source files"),
                                 (editable, "the Discover stage must be open (not submitted or approved)")] if not ok]
    if st.button("Run Discovery Agent", type="primary", disabled=bool(needs), key="run-discovery"):
        with st.spinner("Extracting metadata and checking the existing document..."):
            report = run_discovery(model_id, [str(ROOT / p) for p in record.source_files], LLM,
                                   str(ROOT / record.legacy_document) if record.legacy_document else None,
                                   model_hint=f"{record.name} ({record.algorithm})")
        path = save_report(report, ROOT / "reports/discovery")
        WF.log_agent_run(model_id, "discover", "discovery", USER, {"output": path.as_posix(), "llm_model": report.llm_model,
                                                                  "discrepancies": len(report.discrepancies)})
        flash(f"Discovery report written: {len(report.discrepancies)} discrepancies.")
        st.rerun()
    if needs:
        st.caption("To run the Discovery Agent: " + "; ".join(needs) + ".")

    data = ARTIFACTS.load("discovery", model_id)
    if data is None:
        st.info("No discovery report yet.")
    else:
        report = DiscoveryReport.model_validate(data)
        st.caption(f"Report generated {report.generated_at} with LLM `{report.llm_model}` from "
                   f"{', '.join(report.source_files)}; compared with `{report.legacy_document or 'no document'}`.")
        tabs = st.tabs(["Extracted metadata", f"Discrepancies ({len(report.discrepancies)})", "Source code",
                        f"Evidence warnings ({len(report.evidence_warnings)})"])
        with tabs[0]:
            rows = []
            for name in type(report.metadata).model_fields:
                value = getattr(report.metadata, name)
                facts = value if isinstance(value, list) else [value]
                for fact in facts:
                    if hasattr(fact, "status"):
                        rows.append({"Field": name, "Value": show_value(fact.value),
                                     "Status": fact.status, "Evidence": "; ".join(f"{r.file}:L{r.line_start}-{r.line_end}" for r in fact.evidence),
                                     "Note": fact.note})
            table(rows)
            if report.metadata.missing_information:
                st.markdown("**Missing from the code:** " + "; ".join(report.metadata.missing_information))
        with tabs[1]:
            score = ARTIFACTS.load("discovery_score", model_id)
            scored = {}
            if score:
                if score.get("metadata_scored", True):  # score files written before per-model metadata were always scored
                    cols = st.columns(3)
                    cols[0].metric("Fact recall vs answer key", rate(score["recall"]))
                    cols[1].metric("Fact precision vs answer key", rate(score["precision"]))
                    cols[2].metric("Facts missed", len(score.get("missed", [])))
                    st.caption(f"Scored by Person 1 at {score.get('scored_at')}; "
                               f"missed: {', '.join(score.get('missed', [])) or 'none'}.")
                else:
                    st.caption(f"Scored by Person 1 at {score.get('scored_at')}. Facts not scored: the answer key "
                               "has no expected metadata for this model.")
                if score.get("report_generated_at") != report.generated_at:
                    st.warning("This score is for an earlier Discovery report; ask Person 1 to score the current one.")
                disc = score.get("discrepancies")
                if disc:
                    counts = disc["counts"]
                    cols = st.columns(4)
                    cols[0].metric("Discrepancy recall", rate(disc["recall"]))
                    cols[1].metric("Discrepancy precision", rate(disc["precision"]))
                    cols[2].metric("Unsupported", counts["unsupported"], help="Reported discrepancies that match no expected one")
                    cols[3].metric("Detected without evidence", counts["detected_without_evidence"],
                                   help="Matched an expected discrepancy, but the code evidence did not resolve")
                    missed = [f"{e['id']} ({e['field']}, {e['type']})" for e in disc["key_entries"] if e["outcome"] == "missed"]
                    st.caption(f"Scored types: {', '.join(disc['scored_types'])}. Recall with evidence: "
                               f"{rate(disc['recall_with_evidence'])}. Misclassified: {counts['misclassified']}. "
                               f"Missed: {', '.join(missed) or 'none'}. Other types, reported separately: {counts['not_scored']}.")
                    scored = {f["discrepancy_id"]: f for f in disc["findings"]}
            else:
                st.caption("Not scored yet. Person 1 holds the answer key and runs: python -m agents.discovery_agent "
                           f"--model-id {model_id} --score \"$MODELTRACE_ANSWER_KEY\" (a path outside the repository)")
            rows = [{"ID": d.discrepancy_id, "Field": d.field, "Type": d.type, "Documented claim": d.documented_claim,
                     "Suggested correction": d.suggested_correction, "Detected by": d.detected_by,
                     "Code evidence": "; ".join(f"{r.file}:L{r.line_start}" for r in d.code_evidence)}
                    for d in report.discrepancies]
            if scored:
                for row in rows:
                    row["Score"] = scored.get(row["ID"], {}).get("outcome", "not in score")
                    row["Evidence check"] = scored.get(row["ID"], {}).get("evidence", "")
            table(rows)
        with tabs[2]:
            for file in report.source_files:
                with st.expander(file, expanded=False):
                    st.code(ARTIFACTS.read_text(file) or "(file not found)", language=code_language(file), line_numbers=True)
        with tabs[3]:
            for warning in report.evidence_warnings:
                st.markdown(f"- {warning}")
    gate_panel(model_id, "discover")


def page_documentation(model_id: str) -> None:
    record = WF.record(model_id)
    st.header(f"Documentation · {record.name}")
    discovery = ARTIFACTS.load("discovery", model_id)
    open_stage = WF.statuses(model_id)["document"] in SUBMITTABLE
    if st.button("Generate model card", type="primary", disabled=discovery is None or not open_stage, key="run-docs"):
        card = build_model_card(DiscoveryReport.model_validate(discovery), record, load_evidence(model_id, ROOT),
                                LLM, mapping_path=ROOT / "governance/ss1_23_mapping.json")
        json_path, _ = save_model_card(card, ROOT / "reports", ROOT / "docs/model_cards")
        WF.log_agent_run(model_id, "document", "documentation", USER,
                         {"output": json_path.as_posix(), "generated_by": card.generated_by,
                          "grounding_warnings": len(card.grounding_warnings)})
        flash("Model card generated.")
        st.rerun()
    st.caption("The LLM writes three prose sections when configured (template text otherwise). Every figure is copied "
               "from a report file by code, and no live report means the section says Pending.")
    data = ARTIFACTS.load("model_card", model_id)
    if data is None:
        st.info("No model card yet." + ("" if discovery else " Run the Discovery Agent first."))
    else:
        card = ModelCard.model_validate(data)
        for warning in card.grounding_warnings:
            st.warning(f"Grounding check: {warning}")
        with st.container(border=True):
            st.markdown(render_markdown(card))
    gate_panel(model_id, "document")


def page_migration(model_id: str) -> None:
    record = WF.record(model_id)
    st.header(f"Migration · {record.name}")
    if WF.statuses(model_id)["redevelop"] == "not_applicable":
        st.info(f"{model_id} is already implemented in {record.language}; redevelopment applies to legacy R or SAS models.")
        gate_panel(model_id, "redevelop")
        return
    st.caption("Person 1's engine runs the R glm and the Statsmodels candidate on the same split and writes the parity "
               "report (python -m engine.pipeline).")
    MigrationAgent, missing = optional_agent("agents.migration_agent", "MigrationAgent")
    if st.button("Run Migration Agent (Person 1)", disabled=MigrationAgent is None or not record.source_files,
                 key="run-migration"):
        plan = MigrationAgent().run(ROOT / record.source_files[0]).to_dict()
        st.session_state[f"migration-plan-{model_id}"] = plan
        WF.log_agent_run(model_id, "redevelop", "migration", USER, {"summary": plan["summary"]})
    if missing:
        st.caption(missing)
    if f"migration-plan-{model_id}" in st.session_state:
        with st.expander("Migration Agent result", expanded=True):
            st.json(st.session_state[f"migration-plan-{model_id}"])
    parity, _, _ = load_display("parity", model_id)
    if parity is None:
        st.info(f"No parity report yet ({ARTIFACTS.relpath('parity', model_id)}).")
    else:
        if parity_passed(parity):
            st.success(f"Parity tests passed: R glm vs {parity.get('candidate_model')}, "
                       f"tolerance {parity['r_vs_statsmodels'].get('tolerance')}.")
        else:
            st.error("Parity tests have NOT passed. The Redevelop gate cannot be approved.")
        left, right = st.columns(2)
        with left:
            st.markdown("**R glm vs Statsmodels candidate**")
            kv_table(parity.get("r_vs_statsmodels") or {})
        with right:
            st.markdown("**R glm vs scikit-learn logistic regression (reference)**")
            kv_table(parity.get("r_vs_python") or {})
        st.caption(f"{parity.get('n_rows')} test rows · candidate hash `{str(parity.get('model_hash'))[:12]}` · "
                   f"shared split `{parity.get('shared_test_csv')}`")
        left, right = st.columns(2)
        r_path = parity.get("r_script") or (record.source_files[0] if record.source_files else None)
        with left:
            st.markdown(f"**Original R** `{r_path}`")
            st.code(ARTIFACTS.read_text(r_path) or "(not found on this branch)", language="r", line_numbers=True)
        with right:
            st.markdown(f"**Python candidate** `{PYTHON_CANDIDATE_SOURCE}`")
            st.code(ARTIFACTS.read_text(PYTHON_CANDIDATE_SOURCE) or "(not found on this branch)", language="python",
                    line_numbers=True)
    llm_migration_panel(model_id)
    gate_panel(model_id, "redevelop")


def llm_migration_panel(model_id: str) -> None:
    record = WF.record(model_id)
    st.divider()
    st.subheader("LLM migration candidate")
    st.caption("The LLM writes a Python module from the R code. Code checks it, runs it in a separate process on "
               "Person 1's shared split and compares its predictions with R's; a failed round goes back to the LLM "
               "with what failed, up to 3 rounds. Evidence for the reviewer: the gate reads Person 1's parity report.")
    inputs = default_inputs(model_id, ROOT)
    missing = inputs.missing(ROOT)
    needs = [msg for ok, msg in [
        (LLM is not None, "configure the LLM in .env"),
        (bool(record.source_files), "save the source files"),
        (not missing, f"run Person 1's pipeline, python -m engine.pipeline (missing: {', '.join(missing)})"),
        (WF.statuses(model_id)["redevelop"] in SUBMITTABLE, "the Redevelop stage must be open (not submitted or approved)"),
    ] if not ok]
    if st.button("Run LLM Migration Agent", type="primary", disabled=bool(needs), key="run-llm-migration"):
        try:
            with st.spinner("Generating the Python candidate, running it and comparing it with R..."):
                report = run_llm_migration(model_id, record.source_files[0], LLM, ROOT, inputs)
        except Exception as exc:  # LLM or API error: show it and keep the page usable
            st.error(f"LLM Migration Agent failed: {type(exc).__name__}: {exc}")
        else:
            save_migration_report(report, ROOT)
            WF.log_agent_run(model_id, "redevelop", "llm_migration", USER,
                             {"output": ARTIFACTS.relpath("llm_migration", model_id), "llm_model": report.llm_model,
                              "rounds": len(report.attempts), "passed": report.passed})
            flash(f"LLM migration report written: parity {'passed' if report.passed else 'FAILED'} "
                  f"after {len(report.attempts)} round(s).")
            st.rerun()
    if needs:
        st.caption("To run the LLM Migration Agent: " + "; ".join(needs) + ".")

    data = ARTIFACTS.load("llm_migration", model_id)
    if data is None:
        st.info(f"No LLM migration report yet ({ARTIFACTS.relpath('llm_migration', model_id)}).")
        return
    report = MigrationReport.model_validate(data)
    rounds = f"{len(report.attempts)} round(s), {report.llm_model}"
    if report.passed:
        st.success(f"LLM candidate matches R within tolerance {report.tolerance:g} after {rounds}.")
    else:
        st.error(f"LLM candidate did NOT match R after {rounds}.")
    table([{"Round": a.round,
            "Static check": "; ".join(a.static_problems) or "passed",
            "Run": a.run_error or ("ran" if a.parity else "not run"),
            "Mean abs. difference": show_value(a.parity.mae if a.parity else None),
            "Max difference": show_value(a.parity.max_probability_difference if a.parity else None),
            "Parity": "pass" if a.passed else "fail"} for a in report.attempts])
    st.caption(f"Isolation: {report.isolation} · {report.generated_at} · {report.review_status.replace('_', ' ')}")
    st.markdown("**R to Python terms**")
    table([m.model_dump() for m in report.term_mapping])
    for warning in report.warnings:
        st.warning(warning)
    if report.assumptions:
        with st.expander(f"Assumptions stated by the LLM ({len(report.assumptions)})"):
            st.markdown("\n".join(f"- {a}" for a in report.assumptions))
    st.markdown(f"**Generated Python** `{report.candidate_path}`")
    st.code(report.attempts[-1].python_code, language="python", line_numbers=True)


def group_chart(grouping: str, report: dict[str, Any], key: str) -> None:
    """Person 1's fairness block: {by_group: {group: {count, selection_rate, ...}}, demographic_parity_difference, ...}."""
    cols = st.columns(2)
    cols[0].metric("Demographic parity difference", f"{report.get('demographic_parity_difference', float('nan')):.4f}")
    cols[1].metric("Disparate impact", f"{report.get('disparate_impact', float('nan')):.4f}")
    frame = pd.DataFrame.from_dict(report.get("by_group") or {}, orient="index")
    if frame.empty:
        return
    table(frame.reset_index(names="group"))
    rates = [c for c in ("selection_rate", "true_positive_rate", "false_positive_rate") if c in frame.columns]
    if rates:
        long = frame[rates].reset_index(names="group").melt(id_vars="group", var_name="metric")
        st.plotly_chart(px.bar(long, x="group", y="value", color="metric", barmode="group",
                               title=f"{grouping}: selection rate, TPR and FPR by group"), key=key)


def bar(values: dict[str, float], x: str, title: str, key: str) -> None:
    frame = pd.DataFrame({"feature": list(values), x: list(values.values())}).sort_values(x)
    st.plotly_chart(px.bar(frame, x=x, y="feature", orientation="h", title=title, height=520), key=key)


def page_validation(model_id: str) -> None:
    record = WF.record(model_id)
    st.header(f"Validation · {record.name}")
    ValidationAgent, missing = optional_agent("agents.validation_agent", "ValidationAgent")
    duties = check_duties("validate", "submit", USER, WF.history(model_id))
    data, _, _ = load_display("validation", model_id)
    if st.button("Run Validation Agent (Person 1)", disabled=ValidationAgent is None or bool(duties) or data is None,
                 key="run-validation"):
        summary = ValidationAgent().run(data).to_dict()
        st.session_state[f"validation-summary-{model_id}"] = summary
        WF.log_agent_run(model_id, "validate", "validation", USER, {"summary": summary["summary"]})
    st.caption(missing or (" ".join(duties) if duties else "Summarises Person 1's measured validation report."))
    if f"validation-summary-{model_id}" in st.session_state:
        with st.expander("Validation Agent result", expanded=False):
            st.json(st.session_state[f"validation-summary-{model_id}"])
    if data is None:
        st.info(f"No validation report for this model yet ({ARTIFACTS.relpath('validation', model_id)}).")
        legacy, _, _ = load_display("validation", PERSON1_MODEL) if model_id in PERSON1_SHAP_KEYS else (None, None, False)
        shap = person1_shap(legacy, model_id)
        if shap:
            st.markdown("**Explainability computed in Person 1's validation run**")
            bar(shap["mean_abs_shap"], "mean |SHAP|", f"Mean absolute SHAP ({shap.get('n_rows')} test rows)", key="shap-own")
        gate_panel(model_id, "validate")
        return
    st.caption(f"Validated model: {data.get('model')} · hash `{str(data.get('model_hash'))[:12]}`")
    tabs = st.tabs(["Performance", "Stability", "Fairness", "Explainability"])
    with tabs[0]:
        metrics = data.get("metrics") or {}
        kv_table(metrics)
        if metrics:
            st.plotly_chart(px.bar(x=list(metrics), y=list(metrics.values()), labels={"x": "metric", "y": "value"},
                                   title="Performance on the test set"), key="perf")
    with tabs[1]:
        stability = data.get("stability") or {}
        st.metric("Prediction PSI, train vs test", f"{stability.get('prediction_psi', float('nan')):.5f}")
        if stability.get("feature_psi"):
            bar(stability["feature_psi"], "psi", "Feature PSI, train vs test", key="stab")
    with tabs[2]:
        st.caption("Diagnostic evidence, not a pass/fail fairness verdict. Check group sizes before comparing rates.")
        for grouping, report in (data.get("fairness") or {}).items():
            st.markdown(f"**{grouping}**")
            group_chart(grouping, report, key=f"fair-{grouping}")
    with tabs[3]:
        explain = data.get("explainability") or {}
        if isinstance(explain.get("coefficients"), dict):
            bar(explain["coefficients"], "coefficient", "Statsmodels logistic regression coefficients", key="coef")
        for name in ("random_forest_shap", "gradient_boosting_shap"):
            shap = explain.get(name) or {}
            if isinstance(shap.get("mean_abs_shap"), dict):
                bar(shap["mean_abs_shap"], "mean |SHAP|",
                    f"{name.replace('_shap', '').replace('_', ' ').title()}: mean absolute SHAP ({shap.get('n_rows')} rows)",
                    key=f"shap-{name}")
    gate_panel(model_id, "validate")


def page_risk() -> None:
    st.header("Risk & Evidence")
    rows = []
    for record in RECORDS:
        findings, _, is_sample = ARTIFACTS.load_for_display("risk_findings", record.model_id)
        for f in findings or []:
            rows.append({"Model": record.model_id, "ID": f.get("id"),
                         "Source": "Person 1 risk findings" + (" (SAMPLE COPY)" if is_sample else ""),
                         "Category": f.get("risk_category") or f.get("category"), "Severity": f.get("severity"),
                         "Description": f.get("description"), "Evidence": json.dumps(f.get("evidence"))[:300],
                         "Remediation": f.get("remediation"), "Status": f.get("review_status")})
        for d in (ARTIFACTS.load("discovery", record.model_id) or {}).get("discrepancies", []):
            rows.append({"Model": record.model_id, "ID": d["discrepancy_id"], "Source": "Discovery: document vs code",
                         "Category": f"documentation · {d['field']}", "Severity": "medium" if d["type"] == "contradiction" else "low",
                         "Description": f"{d['type']}: {d['documented_claim']}", "Evidence": "; ".join(
                             f"{r['file']}:L{r['line_start']}" for r in d["code_evidence"]) or "no code evidence",
                         "Remediation": d["suggested_correction"], "Status": WF.statuses(record.model_id)["discover"]})
        alerts = ARTIFACTS.load("alerts", record.model_id)
        reviews = WF.alert_reviews.reviews(record.model_id)
        for a in (alerts or {}).get("alerts", []):
            rows.append({"Model": record.model_id, "ID": a["alert_id"], "Source": "Monitoring", "Category": a["metric"],
                         "Severity": a["severity"], "Description": (a.get("explanation") or {}).get("summary", ""),
                         "Evidence": a["evidence_ref"], "Remediation": (a.get("explanation") or {}).get("recommendation", ""),
                         "Status": alert_status(reviews, a["alert_id"])})
    if not rows:
        st.info("No findings yet. Findings come from validation reports, discovery discrepancies and monitoring alerts.")
        return
    frame = pd.DataFrame(rows)
    sources = st.multiselect("Source", sorted(frame["Source"].unique()), default=sorted(frame["Source"].unique()))
    levels = [s for s in ("high", "medium", "warning", "review", "low", "info") if s in set(frame["Severity"])]
    severities = st.multiselect("Severity", levels, default=levels)
    frame = frame[frame["Source"].isin(sources) & frame["Severity"].isin(severities)]
    st.plotly_chart(px.histogram(frame, x="Severity", color="Source", title="Risk register by severity",
                                 category_orders={"Severity": levels}), key="risk")
    table(frame)
    st.caption("Discrepancy severity is a fixed rule: contradiction = medium, omission or unverifiable = low. "
               "Every row points to the file and line, or report key, that supports it.")


def page_monitoring(model_id: str) -> None:
    record = WF.record(model_id)
    st.header(f"Monitoring · {record.name}")
    monitoring, path, is_sample = load_display("monitoring", model_id)
    if monitoring is None:
        st.info(f"No monitoring report yet ({ARTIFACTS.relpath('monitoring', model_id)}, written by Person 1's engine).")
        gate_panel(model_id, "monitor")
        return
    batches = monitoring.get("batches", [])
    table([{"batch": b.get("batch"), "Person 1 severity": b.get("severity"), "driving feature": b.get("driving_feature"),
            "driving PSI": b.get("driving_feature_psi"), "prediction PSI": b.get("prediction_psi"),
            "mean predicted PD": b.get("mean_predicted_probability"),
            "share above threshold": b.get("percentage_above_threshold"), "type": b.get("diagnostic_type")}
           for b in batches])
    psi = pd.DataFrame([{"batch": str(b["batch"]), "feature": f, "psi": v}
                        for b in batches for f, v in (b.get("feature_psi") or {}).items() if v >= 0.01])
    if not psi.empty:
        fig = px.bar(psi, x="feature", y="psi", color="batch", barmode="group", log_y=True,
                     title="Feature PSI by batch (features with PSI ≥ 0.01, log scale)")
        fig.add_hline(y=PSI_WARNING, line_dash="dot", annotation_text="warning 0.10")
        fig.add_hline(y=PSI_HIGH, line_dash="dash", annotation_text="high 0.25")
        st.plotly_chart(fig, key="psi")
    outputs = pd.DataFrame([{"batch": str(b["batch"]), "mean predicted PD": b.get("mean_predicted_probability"),
                             "share above threshold": b.get("percentage_above_threshold")} for b in batches])
    st.plotly_chart(px.line(outputs.melt(id_vars="batch"), x="batch", y="value", color="variable", markers=True,
                            title="Prediction distribution by batch"), key="outputs")
    st.caption("PSI bands are illustrative monitoring heuristics, not regulatory thresholds. Severity is set by rule; "
               "the LLM only explains alerts and cannot retrain, replace or deploy the model.")

    st.subheader("Alerts")
    if is_sample:
        report = build_alert_report(model_id, monitoring, path, None)
        st.caption("Alerts derived in memory from the copy of Person 1's report, for layout only. Review actions are disabled.")
    else:
        if st.button("Run Monitoring Agent", type="primary", key="run-monitoring"):
            with st.spinner("Raising and explaining alerts..."):
                report = build_alert_report(model_id, monitoring, ARTIFACTS.relpath("monitoring", model_id), LLM)
            out = save_alert_report(report, ROOT)
            WF.log_agent_run(model_id, "monitor", "monitoring", USER, {"output": out.as_posix(), "alerts": len(report.alerts),
                                                                      "generated_by": report.generated_by})
            flash(f"{len(report.alerts)} alert(s) raised.")
            st.rerun()
        data = ARTIFACTS.load("alerts", model_id)
        report = AlertReport.model_validate(data) if data else None
    if report is None:
        st.info("Run the Monitoring Agent to raise alerts.")
    else:
        for warning in report.warnings:
            st.warning(warning)
        reviews = WF.alert_reviews.reviews(model_id)
        for alert in report.alerts:
            status = alert_status(reviews, alert.alert_id)
            icon = "🔴" if alert.severity == "high" else "🟠"
            title = f"{icon} {alert.severity.upper()} · {alert.batch_id} · {alert.metric} · {alert.feature or 'model output'} · {status}"
            with st.expander(title, expanded=alert.severity == "high" and status == "open"):
                exp = alert.explanation
                st.markdown(f"**Evidence:** value `{alert.value}` at `{alert.evidence_ref}`  \n**Rule:** {alert.rule}")
                if exp:
                    st.markdown(f"**What happened:** {exp.summary}  \n**Potential impact:** {exp.potential_impact}  \n"
                                f"**Recommendation:** `{exp.recommendation}`: {exp.reason}  \n_Explanation: {alert.explanation_source}_")
                    st.markdown("**Investigate:**\n" + "\n".join(f"- {c}" for c in exp.investigate))
                if is_sample:
                    continue
                comment = st.text_input("Comment", key=f"ac-{alert.alert_id}")
                for column, (action, label) in zip(st.columns(len(ALERT_ACTIONS)), ALERT_ACTIONS):
                    problems = [p for p in check_alert_action(action, status, USER, "x") if not p.startswith("A comment")]
                    if column.button(label, key=f"{action}-{alert.alert_id}", disabled=bool(problems)):
                        act(lambda: WF.review_alert(model_id, alert.alert_id, USER, action, comment),
                            f"Alert {alert.alert_id}: {label.lower()} recorded.")
                history = [r for r in reviews if r.alert_id == alert.alert_id]
                if history:
                    table([r.model_dump(include={"timestamp", "action", "actor", "role", "comment"}) for r in history])
    gate_panel(model_id, "monitor")


def page_governance() -> None:
    st.header("Governance")
    tabs = st.tabs(["Approval queue", "Lifecycle", "Reopen a stage", "Approval history", "Audit log", "SS1/23 mapping", "AI use"])
    history = WF.approvals.records()
    with tabs[0]:
        queue = []
        for record in RECORDS:
            for stage, status in WF.statuses(record.model_id).items():
                if status == "pending_review":
                    submit = [r for r in history if r.model_id == record.model_id and r.stage == stage and r.action == "submit"][-1]
                    queue.append({"Model": record.model_id, "Stage": STAGE_LABEL[stage], "Submitted by": submit.actor,
                                  "Submitted at": submit.timestamp, "Evidence": submit.evidence_ref, "Comment": submit.comment})
        if queue:
            table(queue)
        else:
            st.info("Nothing is waiting for approval.")
    with tabs[1]:
        table([{"Model": r.model_id, "Tier": r.risk_tier, **{STAGE_LABEL[s]: STATUS_LABEL[v] for s, v in WF.statuses(r.model_id).items()},
                "Stale approvals": ", ".join(WF.stale_approvals(r.model_id)) or "none"} for r in RECORDS])
        st.caption("A stage cannot be submitted until every earlier stage is approved. Reopening a stage invalidates later stages.")
    with tabs[2]:
        model = st.selectbox("Model", [r.model_id for r in RECORDS], key="reopen-model")
        statuses = WF.statuses(model)
        options = [s for s in STAGES if statuses[s] in REOPENABLE]
        if not options:
            st.info("No approved or rejected stage to reopen for this model.")
        else:
            stage = st.selectbox("Stage", options, format_func=STAGE_LABEL.get, key="reopen-stage")
            reason = st.text_input("Reason", key="reopen-reason")
            problems = WF.check(model, stage, "reopen", USER)
            if st.button("Reopen stage", disabled=bool(problems), key="reopen"):
                act(lambda: WF.reopen(model, stage, USER, reason), f"{STAGE_LABEL[stage]} reopened; later stages invalidated.")
            if problems:
                st.caption(" ".join(problems))
    with tabs[3]:
        if history:
            table([r.model_dump() for r in history])
        else:
            st.info("No approval records yet.")
    with tabs[4]:
        problems = WF.audit.verify()
        events = WF.audit.events()
        if problems:
            for problem in problems:
                st.error(problem)
        else:
            st.success(f"Audit chain intact: {len(events)} events, each linked to the hash of the previous one.")
        if events:
            table([{"Time": e.timestamp, "Actor": e.actor, "Role": e.role, "Action": e.action, "Model": e.model_id,
                    "Stage": e.stage, "Details": json.dumps(e.details)[:200], "Hash": e.hash[:12]} for e in reversed(events)])
    with tabs[5]:
        mapping = ss1_23()
        table([{"Stage": STAGE_LABEL[s["stage"]], "Gate": s["gate"], "SS1/23 principles": "; ".join(s["principles"]),
                "What MODELTRACE AI provides": s["modeltrace_provides"]} for s in mapping["stages"]]
              + [{"Stage": "All stages", "Gate": "", "SS1/23 principles": "; ".join(mapping["all_stages"]["principles"]),
                  "What MODELTRACE AI provides": mapping["all_stages"]["modeltrace_provides"]}])
        st.markdown("**Outside the prototype:** " + "; ".join(mapping["outside_prototype"]))
        st.caption(mapping["source"])
    with tabs[6]:
        st.markdown(f"**LLM status:** {LLM_STATUS}")
        log = ROOT / os.environ.get("LLM_CALL_LOG", "governance/llm_call_log.jsonl")
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        if calls:
            frame = pd.DataFrame(calls)
            st.metric("LLM calls", len(frame))
            table(frame.groupby("schema").agg(calls=("ok", "size"), valid=("ok", "sum")).reset_index())
        else:
            st.info("No LLM calls logged yet.")
        runs = [e for e in WF.audit.events() if e.action == "agent_run"]
        if runs:
            table([{"Time": e.timestamp, "Agent": e.actor, "Model": e.model_id, "Stage": e.stage,
                    "Triggered by": e.details.get("triggered_by"), "Details": json.dumps(e.details)[:200]} for e in runs])


# --------------------------------------------------------------------------- layout
WF = Workflow(ROOT)
USERS = load_users(ROOT / "governance/users.json")
LLM, LLM_STATUS = get_llm()
RECORDS = WF.records()

with st.sidebar:
    st.title("MODELTRACE AI")
    st.caption("Agentic model risk factory · hackathon prototype")
    section = st.radio("Section", SECTIONS, key="section")
    model_id = st.selectbox("Model", [r.model_id for r in RECORDS], key="model",
                            format_func=lambda m: f"{m} · Tier {next(r.risk_tier for r in RECORDS if r.model_id == m)}")
    USER = USERS[st.selectbox("Acting as (prototype: no login)", range(len(USERS)), key="user",
                              format_func=lambda i: USERS[i].name)]
    use_samples = st.toggle("Show sample data where Person 1's reports are missing", key="samples")
    st.caption(LLM_STATUS)

ARTIFACTS = Artifacts(ROOT, SAMPLE_ROOT if use_samples else None)
MODEL_PAGES = {"Discovery": page_discovery, "Documentation": page_documentation, "Migration": page_migration,
               "Validation": page_validation, "Monitoring": page_monitoring}
GLOBAL_PAGES = {"Executive Overview": page_overview, "Risk & Evidence": page_risk, "Governance": page_governance}
show_flash()
if section in MODEL_PAGES:
    MODEL_PAGES[section](model_id)
else:
    GLOBAL_PAGES[section]()
