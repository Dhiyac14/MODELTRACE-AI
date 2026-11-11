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
from agents.monitoring_agent import PSI_HIGH, PSI_WARNING, build_alert_report, save_alert_report
from inventory.risk_tier import TIER_RULE, draft_rationale
from llm.client import llm_from_env
from llm.schemas import AlertReport, DiscoveryReport, ModelCard
from workflow.alerts import RULES as ALERT_RULES
from workflow.alerts import alert_status, check_alert_action
from workflow.approvals import check_duties, load_users
from workflow.artifacts import SAMPLE_ROOT, STAGE_EVIDENCE, Artifacts
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


def kv_table(data: dict[str, Any]) -> None:
    table([{"Metric": k, "Value": v if isinstance(v, (int, float, str, bool)) else json.dumps(v)}
           for k, v in flatten(data) if not k.startswith("_")])


def code_language(path: str) -> str:
    return {".r": "r", ".py": "python", ".sas": "sas", ".sql": "sql", ".md": "markdown"}.get(Path(path).suffix.lower(), "text")


def optional_agent(module: str, function: str):
    """Person 1's agents are integrated when present; their absence must not break the app."""
    try:
        return getattr(importlib.import_module(module), function), ""
    except Exception as exc:  # ImportError, or an error inside Person 1's module
        return None, f"{module}.{function} is not available yet ({type(exc).__name__})."


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
                                   str(ROOT / record.legacy_document) if record.legacy_document else None)
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
                        rows.append({"Field": name, "Value": json.dumps(fact.value) if isinstance(fact.value, list) else fact.value,
                                     "Status": fact.status, "Evidence": "; ".join(f"{r.file}:L{r.line_start}-{r.line_end}" for r in fact.evidence),
                                     "Note": fact.note})
            table(rows)
            if report.metadata.missing_information:
                st.markdown("**Missing from the code:** " + "; ".join(report.metadata.missing_information))
        with tabs[1]:
            score, _, _ = load_display("discovery_score", model_id)
            if score:
                cols = st.columns(2)
                cols[0].metric("Recall against the answer key", score.get("recall"))
                cols[1].metric("Precision against the answer key", score.get("precision"))
            table([{"ID": d.discrepancy_id, "Field": d.field, "Type": d.type, "Documented claim": d.documented_claim,
                    "Suggested correction": d.suggested_correction, "Detected by": d.detected_by,
                    "Code evidence": "; ".join(f"{r.file}:L{r.line_start}" for r in d.code_evidence)}
                   for d in report.discrepancies])
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
        card = build_model_card(DiscoveryReport.model_validate(discovery), record, load_evidence(model_id, ROOT / "reports"),
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
    run_migration, missing = optional_agent("agents.migration_agent", "run_migration")
    can_run = run_migration is not None and LLM is not None and "developer" in USER.roles and bool(record.source_files)
    if st.button("Run Migration Agent (Person 1)", disabled=not can_run, key="run-migration"):
        with st.spinner("Generating the Python candidate and running parity tests..."):
            run_migration(model_id=model_id, r_source=str(ROOT / record.source_files[0]), llm=LLM)
        WF.log_agent_run(model_id, "redevelop", "migration", USER, {"output": ARTIFACTS.relpath("parity", model_id)})
        flash("Migration Agent finished.")
        st.rerun()
    st.caption(missing or "Runs Person 1's agent; needs the LLM, a developer role and saved source files.")
    parity, _, _ = load_display("parity", model_id)
    if parity is None:
        st.info("No parity report yet.")
    else:
        if parity.get("passed") is True:
            st.success(f"Parity tests passed (tolerance {parity.get('tolerance')}).")
        else:
            st.error("Parity tests have NOT passed. The Redevelop gate cannot be approved.")
        kv_table({k: v for k, v in parity.items() if not k.endswith("_path") and k not in ("model_id", "passed")})
        left, right = st.columns(2)
        r_path = parity.get("r_source_path") or (record.source_files[0] if record.source_files else None)
        with left:
            st.markdown(f"**Original R** `{r_path}`")
            st.code(ARTIFACTS.read_text(r_path) or "(not found)", language="r", line_numbers=True)
        with right:
            st.markdown(f"**Generated Python** `{parity.get('python_code_path')}`")
            st.code(ARTIFACTS.read_text(parity.get("python_code_path")) or "(not found)", language="python", line_numbers=True)
    gate_panel(model_id, "redevelop")


def group_chart(grouping: str, groups: dict[str, Any], key: str) -> None:
    frame = pd.DataFrame.from_dict(groups, orient="index")
    table(frame.reset_index(names="group"))
    rates = [c for c in ("selection_rate", "tpr", "fpr") if c in frame.columns]
    if rates:
        long = frame[rates].reset_index(names="group").melt(id_vars="group", var_name="metric")
        st.plotly_chart(px.bar(long, x="group", y="value", color="metric", barmode="group",
                               title=f"{grouping}: selection rate, TPR and FPR by group"), key=key)


def page_validation(model_id: str) -> None:
    record = WF.record(model_id)
    st.header(f"Validation · {record.name}")
    run_validation, missing = optional_agent("agents.validation_agent", "run_validation")
    duties = check_duties("validate", "submit", USER, WF.history(model_id))
    if st.button("Run Validation Agent (Person 1)", disabled=run_validation is None or bool(duties), key="run-validation"):
        with st.spinner("Running independent validation..."):
            run_validation(model_id=model_id, llm=LLM)
        WF.log_agent_run(model_id, "validate", "validation", USER, {"output": ARTIFACTS.relpath("validation", model_id)})
        flash("Validation Agent finished.")
        st.rerun()
    st.caption(missing or (" ".join(duties) if duties else "Runs Person 1's independent Validation Agent."))
    data, _, _ = load_display("validation", model_id)
    if data is None:
        st.info("No validation report yet.")
        gate_panel(model_id, "validate")
        return
    tabs = st.tabs(["Performance", "Stability", "Fairness", "Explainability"])
    with tabs[0]:
        performance = data.get("performance") or {}
        kv_table(performance)
        numeric = {k: v for k, v in performance.items() if isinstance(v, (int, float))}
        if numeric:
            st.plotly_chart(px.bar(x=list(numeric), y=list(numeric.values()), labels={"x": "metric", "y": "value"},
                                   title="Performance on the test set"), key="perf")
    with tabs[1]:
        kv_table(data.get("stability") or {})
    with tabs[2]:
        st.caption("Diagnostic evidence, not a pass/fail fairness verdict. Check group sizes before comparing rates.")
        for grouping, groups in (data.get("fairness") or {}).items():
            st.markdown(f"**{grouping}**")
            if isinstance(groups, dict) and all(isinstance(g, dict) for g in groups.values()):
                group_chart(grouping, groups, key=f"fair-{grouping}")
            else:
                kv_table({grouping: groups})
    with tabs[3]:
        explain = data.get("explainability") or {}
        coefficients = explain.get("coefficients")
        if isinstance(coefficients, dict):
            frame = pd.DataFrame({"feature": list(coefficients), "coefficient": list(coefficients.values())}).sort_values("coefficient")
            st.plotly_chart(px.bar(frame, x="coefficient", y="feature", orientation="h", title="Logistic regression coefficients"),
                            key="coef")
        kv_table({k: v for k, v in explain.items() if k != "coefficients"})
    gate_panel(model_id, "validate")


def page_risk() -> None:
    st.header("Risk & Evidence")
    rows = []
    for record in RECORDS:
        validation, _, is_sample = ARTIFACTS.load_for_display("validation", record.model_id)
        for f in (validation or {}).get("findings", []):
            rows.append({"Model": record.model_id, "ID": f.get("finding_id"), "Source": "Validation" + (" (SAMPLE)" if is_sample else ""),
                         "Category": f.get("category"), "Severity": f.get("severity"), "Description": f.get("description"),
                         "Evidence": f.get("evidence"), "Remediation": f.get("remediation"), "Status": f.get("review_status")})
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
    severities = st.multiselect("Severity", ["high", "medium", "low", "warning"], default=["high", "medium", "low", "warning"])
    frame = frame[frame["Source"].isin(sources) & frame["Severity"].isin(severities)]
    st.plotly_chart(px.histogram(frame, x="Severity", color="Source", title="Risk register by severity",
                                 category_orders={"Severity": ["high", "medium", "warning", "low"]}), key="risk")
    table(frame)
    st.caption("Discrepancy severity is a fixed rule: contradiction = medium, omission or unverifiable = low. "
               "Every row points to the file and line, or report key, that supports it.")


def page_monitoring(model_id: str) -> None:
    record = WF.record(model_id)
    st.header(f"Monitoring · {record.name}")
    monitoring, path, is_sample = load_display("monitoring", model_id)
    if monitoring is None:
        st.info("No monitoring report yet (Person 1 produces reports/monitoring/<model_id>_monitoring.json).")
        gate_panel(model_id, "monitor")
        return
    batches = monitoring.get("batches", [])
    table([{k: b.get(k) for k in ("batch_id", "scenario", "modification", "n_records", "mean_predicted_pd",
                                  "share_above_threshold", "prediction_psi")} for b in batches])
    psi = pd.DataFrame([{"batch": b["batch_id"], "feature": f, "psi": v}
                        for b in batches for f, v in (b.get("feature_psi") or {}).items()])
    if not psi.empty:
        fig = px.bar(psi, x="feature", y="psi", color="batch", barmode="group", title="Feature PSI by batch")
        fig.add_hline(y=PSI_WARNING, line_dash="dot", annotation_text="warning 0.10")
        fig.add_hline(y=PSI_HIGH, line_dash="dash", annotation_text="high 0.25")
        st.plotly_chart(fig, key="psi")
    outputs = pd.DataFrame([{"batch": b["batch_id"], "mean predicted PD": b.get("mean_predicted_pd"),
                             "share above threshold": b.get("share_above_threshold")} for b in batches])
    st.plotly_chart(px.line(outputs.melt(id_vars="batch"), x="batch", y="value", color="variable", markers=True,
                            title="Prediction distribution by batch"), key="outputs")
    st.caption("PSI bands are illustrative monitoring heuristics, not regulatory thresholds. Severity is set by rule; "
               "the LLM only explains alerts and cannot retrain, replace or deploy the model.")

    st.subheader("Alerts")
    if is_sample:
        report = build_alert_report(model_id, monitoring, path, None)
        st.caption("Alerts derived in memory from sample data, for layout only. Review actions are disabled.")
    else:
        if st.button("Run Monitoring Agent", type="primary", key="run-monitoring"):
            with st.spinner("Raising and explaining alerts..."):
                report = build_alert_report(model_id, monitoring, ARTIFACTS.relpath("monitoring", model_id), LLM)
            out = save_alert_report(report, ROOT / "reports")
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
