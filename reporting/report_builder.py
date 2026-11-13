"""ReportLab PDF builders for individual and portfolio model-risk reports."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.shapes import Drawing, Rect, String

from .data_loader import ModelReportData, PortfolioReportData, ReportDataError, ReportDataLoader

NAVY = colors.HexColor("#12263A")
BLUE = colors.HexColor("#1F5A85")
TEAL = colors.HexColor("#197C87")
PALE_BLUE = colors.HexColor("#EAF2F8")
PALE_GREY = colors.HexColor("#F4F6F8")
GREY = colors.HexColor("#5B6770")
RED = colors.HexColor("#B42318")
AMBER = colors.HexColor("#B54708")
GREEN = colors.HexColor("#067647")
WHITE = colors.white


def _text(value: Any, default: str = "Not Available") -> str:
    if value is None or value == "" or value == []:
        return default
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (dict, list)):
        return "; ".join(f"{k}: {_text(v)}" for k, v in value.items()) if isinstance(value, dict) else ", ".join(_text(v) for v in value)
    return str(value)


def _clean(value: str) -> str:
    """Normalize common UTF-8/Windows-1252 mojibake before it reaches a PDF."""
    replacements = {
        "Â·": "·",
        "â€”": "—",
        "â€“": "–",
        "â€™": "’",
        "â€œ": "“",
        "â€\x9d": "”",
        "Â": "",
    }
    for broken, readable in replacements.items():
        value = value.replace(broken, readable)
    return value


def _escape(value: Any) -> str:
    return html.escape(_clean(_text(value))).replace("\n", "<br/>")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")


def _status_for(data: ModelReportData) -> tuple[str, str]:
    review = (data.model_card or {}).get("review_status")
    if review == "approved":
        return "Approved (recorded)", "approved"
    validation = data.validation or {}
    if isinstance(validation, dict) and any(validation.get(key) for key in ("metrics", "findings", "evidence")):
        return "Pending Review", "pending"
    return "Not Assessed", "missing"


def _migration_status(data: ModelReportData) -> str:
    if data.record.get("migration_status") == "not_applicable" and data.record.get("language") == "Python":
        return "Not Applicable"
    if data.record.get("migration_status") == "not_started":
        return "Not Assessed"
    if data.parity is not None and isinstance(data.parity.get("r_vs_statsmodels"), dict) and data.parity["r_vs_statsmodels"]:
        return "Available"
    return "Not Assessed"


def _stage_evidence(data: ModelReportData, stage: str) -> bool:
    return {
        "discover": data.discovery is not None,
        "document": data.model_card is not None,
        "redevelop": data.parity is not None,
        "validate": data.validation is not None,
        "monitor": data.monitoring is not None,
    }.get(stage, False)


def _governance_stage_status(status: Any) -> str:
    if status == "approved":
        return "Approved"
    if status == "not_applicable":
        return "Not applicable"
    if status in {
        "not_started",
        "in_progress",
        "pending_review",
        "rejected",
        "changes_requested",
        "invalidated",
    }:
        return "Pending / in progress"
    return "Not recorded"


def _severity_color(value: str) -> colors.Color:
    lowered = value.lower()
    if lowered in {"critical", "high"}:
        return RED
    if lowered in {"medium", "warning", "review"}:
        return AMBER
    if lowered in {"low", "info", "observed"}:
        return GREEN
    return GREY


class _BarChart(Flowable):
    """Small vector bar chart that does not create an image artifact."""

    def __init__(self, values: dict[str, float], title: str, width: float = 170 * mm, height: float = 58 * mm) -> None:
        super().__init__()
        self.values = values
        self.title = title
        self.width = width
        self.height = height

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return min(self.width, avail_width), self.height

    def draw(self) -> None:
        if not self.values:
            return
        drawing = Drawing(self.width, self.height)
        drawing.add(String(0, self.height - 10, self.title, fontName="Helvetica-Bold", fontSize=9, fillColor=NAVY))
        left, bottom = 82, 16
        chart_width = self.width - left - 8
        chart_height = self.height - 25
        maximum = max(abs(float(value)) for value in self.values.values()) or 1.0
        bar_height = max(5, chart_height / max(len(self.values), 1) - 3)
        for index, (label, value) in enumerate(self.values.items()):
            y = bottom + chart_height - (index + 1) * (bar_height + 3)
            numeric = float(value)
            width = chart_width * abs(numeric) / maximum
            drawing.add(String(0, y + 1, str(label)[:16], fontName="Helvetica", fontSize=6.5, fillColor=GREY))
            drawing.add(Rect(left, y, max(width, 1), bar_height, fillColor=TEAL, strokeColor=None))
            drawing.add(String(left + max(width, 1) + 3, y + 1, _text(numeric), fontName="Helvetica", fontSize=6.5, fillColor=NAVY))
        drawing.drawOn(self.canv, 0, 0)


class _ReportDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str | Path, title: str) -> None:
        super().__init__(
            str(filename),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=17 * mm,
            title=title,
            author="MODELTRACE AI",
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="report", frames=frame, onPage=self._header_footer)])

    def _header_footer(self, canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(PALE_BLUE)
        canvas.line(self.leftMargin, A4[1] - 13 * mm, A4[0] - self.rightMargin, A4[1] - 13 * mm)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(self.leftMargin, A4[1] - 10 * mm, "MODELTRACE AI")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(A4[0] - self.rightMargin, 9 * mm, f"Model risk evidence report - Page {canvas.getPageNumber()}")
        canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ReportTitle", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=24, leading=29, textColor=NAVY, alignment=TA_CENTER, spaceAfter=8),
        "subtitle": ParagraphStyle("ReportSubtitle", parent=base["Normal"], fontSize=12, leading=16,
                                   textColor=GREY, alignment=TA_CENTER, spaceAfter=4),
        "h1": ParagraphStyle("ReportH1", parent=base["Heading1"], fontName="Helvetica-Bold",
                             fontSize=16, leading=20, textColor=NAVY, spaceBefore=4, spaceAfter=8),
        "h2": ParagraphStyle("ReportH2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=11, leading=14, textColor=BLUE, spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("ReportBody", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=9, leading=13, textColor=NAVY, spaceAfter=5),
        "small": ParagraphStyle("ReportSmall", parent=base["BodyText"], fontSize=7.5, leading=10, textColor=GREY),
        "cell": ParagraphStyle("ReportCell", parent=base["BodyText"], fontSize=7.5, leading=9.5, textColor=NAVY),
        "cell_bold": ParagraphStyle("ReportCellBold", parent=base["BodyText"], fontName="Helvetica-Bold",
                                    fontSize=7.5, leading=9.5, textColor=NAVY),
        "cell_header": ParagraphStyle("ReportCellHeader", parent=base["BodyText"], fontName="Helvetica-Bold",
                                      fontSize=7.5, leading=9.5, textColor=WHITE),
        "cover_label": ParagraphStyle("CoverLabel", parent=base["Normal"], fontSize=8, leading=10,
                                      textColor=GREY, alignment=TA_CENTER),
    }


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_escape(value), style)


def _section(title: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(_escape(title), styles["h1"])


def _table(rows: list[list[Any]], styles: dict[str, ParagraphStyle], widths: list[float] | None = None,
           header: bool = True) -> Table:
    prepared = []
    for row_index, row_contents in enumerate(rows):
        cell_style = styles["cell_header"] if row_index == 0 and header else styles["cell"]
        prepared.append([
            cell if isinstance(cell, Flowable) else _p(cell, cell_style)
            for cell in row_contents
        ])
    table = Table(prepared, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D7DEE5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE)]
    for row in range(1 if header else 0, len(rows)):
        if row % 2:
            commands.append(("BACKGROUND", (0, row), (-1, row), PALE_GREY))
    table.setStyle(TableStyle(commands))
    return table


def _state(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(f"<b>{_escape(text)}</b>", styles["body"])


def _card_rows(card: dict[str, Any] | None, key: str) -> list[list[str]]:
    sections = (card or {}).get("sections", [])
    if not isinstance(sections, list) or any(not isinstance(section, dict) for section in sections):
        raise ReportDataError("Model-card sections must be an array of objects.")
    for section in sections:
        if section.get("key") == key:
            rows = section.get("rows", [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ReportDataError(f"Model-card rows for section {key!r} must be an array of objects.")
            return [[_clean(str(row.get("label", ""))), _clean(str(row.get("value", ""))), _clean(str(row.get("source", "")))]
                    for row in rows]
    return []


def _findings(data: ModelReportData) -> list[dict[str, Any]]:
    rows = []
    for finding in (data.discovery or {}).get("discrepancies", []) or []:
        rows.append({
            "id": finding.get("discrepancy_id", "Discovery"),
            "category": finding.get("field", "Discovery"),
            "description": finding.get("explanation") or finding.get("documented_claim"),
            "severity": "review",
            "impact": "Existing documentation and source evidence require human review.",
            "remediation": finding.get("suggested_correction"),
            "status": "pending review",
        })
    for finding in data.risk_findings:
        rows.append({
            "id": finding.get("id", "Finding"),
            "category": finding.get("risk_category") or finding.get("category", "Risk"),
            "description": finding.get("description"),
            "severity": finding.get("severity", "review"),
            "impact": finding.get("impact"),
            "remediation": finding.get("remediation"),
            "status": finding.get("review_status", "not recorded"),
        })
    return rows


def _cover(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    status, status_key = _status_for(data)
    record = data.record
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    story: list[Flowable] = [
        Spacer(1, 25 * mm),
        Paragraph("MODELTRACE AI", styles["title"]),
        Paragraph("MODEL RISK VALIDATION REPORT", styles["subtitle"]),
        Spacer(1, 8 * mm),
        Paragraph(_escape(data.model_name), styles["title"]),
        Paragraph(_escape(data.model_id), styles["subtitle"]),
        Spacer(1, 10 * mm),
    ]
    summary_rows = [
        ["Model version", record.get("version", "Not Available")],
        ["Algorithm", record.get("algorithm", "Not Available")],
        ["Language", record.get("language", "Not Available")],
        ["Business purpose", record.get("business_purpose", "Not Available")],
        ["Risk tier", f"Tier {record.get('risk_tier', 'Not Available')}"],
        ["Report status", status],
        ["Generated", generated],
    ]
    table = _table(summary_rows, styles, [42 * mm, 125 * mm], header=False)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), PALE_BLUE), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
    story.append(table)
    story.append(Spacer(1, 8 * mm))
    story.append(_state(
        "Status is evidence-based and does not constitute independent model approval. "
        + ("Validation evidence is pending human review." if status_key == "pending" else
           "No validation evidence is currently recorded." if status_key == "missing" else
           "The recorded governance status is approved."),
        styles,
    ))
    story.append(PageBreak())
    return story


def _documentation_section(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    discovery = data.discovery or {}
    metadata = discovery.get("metadata") or {}
    def value(key: str) -> Any:
        raw = metadata.get(key)
        return raw.get("value") if isinstance(raw, dict) else raw

    rows = [
        ["Model purpose", data.record.get("business_purpose")],
        ["Algorithm", value("algorithm") or data.record.get("algorithm")],
        ["Target variable", value("target_variable")],
        ["Input features", value("input_features")],
        ["Preprocessing", value("preprocessing_steps")],
        ["Training split", value("train_fraction")],
        ["Decision threshold", value("decision_threshold")],
        ["Limitations", value("limitations")],
        ["Documentation source", discovery.get("legacy_document") or "No legacy document registered"],
    ]
    return [_section("1. Model documentation", styles), _table(rows, styles, [42 * mm, 125 * mm], header=False),
            Spacer(1, 5 * mm), _state(
                "Values are copied from inventory and Discovery evidence. Unavailable fields are not inferred.",
                styles)]


def _performance_section(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    story = [_section("2. Performance validation", styles)]
    metrics = (data.validation or {}).get("metrics") or {}
    if not metrics:
        story.append(_state("Not Assessed — no validation metrics are available for this model.", styles))
        return story
    rows = [["Metric", "Observed value"]] + [[key, _text(value)] for key, value in metrics.items()]
    story += [_table(rows, styles, [85 * mm, 82 * mm]), Spacer(1, 4 * mm)]
    story.append(_BarChart({str(k): float(v) for k, v in metrics.items() if isinstance(v, (int, float))},
                           "Observed validation metrics"))
    story.append(_state("Pass/fail criteria are not shown because no general performance thresholds are defined in the supplied report.", styles))
    return story


def _migration_section(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    story = [_section("3. Migration and parity validation", styles)]
    parity = (data.parity or {}).get("r_vs_statsmodels")
    if not parity:
        story.append(_state(f"{_migration_status(data)} - no migration/parity evidence is available for this model.", styles))
        return story
    rows = [["Parity measure", "Observed value"]]
    rows += [[key, _text(value)] for key, value in parity.items()]
    story.append(_table(rows, styles, [85 * mm, 82 * mm]))
    story.append(Spacer(1, 3 * mm))
    story.append(_state("Parity evidence is reproduced from the migration report; it is not an approval decision.", styles))
    return story


def _monitoring_section(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    story = [_section("4. Stability and monitoring", styles)]
    report = data.monitoring
    if not report:
        story.append(_state("Not Assessed — no monitoring history is available for this model.", styles))
        return story
    summary = report.get("summary") or {}
    if not isinstance(summary, dict):
        raise ReportDataError("Monitoring summary must be an object.")
    rows = [["Monitoring measure", "Observed value"]] + [[key, _text(value)] for key, value in summary.items()]
    story.append(_table(rows, styles, [85 * mm, 82 * mm]))
    batches = report.get("batches") or []
    if not isinstance(batches, list) or any(not isinstance(batch, dict) for batch in batches):
        raise ReportDataError("Monitoring batches must be an array of objects.")
    psi: dict[str, float] = {}
    for batch in batches:
        if isinstance(batch, dict) and isinstance(batch.get("prediction_psi"), (int, float)):
            psi[str(batch.get("batch", "batch"))] = float(batch["prediction_psi"])
    if psi:
        story += [Spacer(1, 4 * mm), _BarChart(psi, "Prediction PSI by recorded batch")]
    return story


def _fairness_section(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    story = [_section("5. Fairness and bias assessment", styles)]
    fairness = (data.validation or {}).get("fairness") or {}
    if not isinstance(fairness, dict) or any(not isinstance(values, dict) for values in fairness.values()):
        raise ReportDataError("Fairness groups must be an object of group-report objects.")
    if not fairness:
        story.append(_state("Not Assessed — no fairness evidence is available for this model.", styles))
        return story
    for group, values in fairness.items():
        story.append(Paragraph(_escape(str(group).replace("_", " ").title()), styles["h2"]))
        summary = [[key, _text(values.get(key))] for key in ("demographic_parity_difference", "disparate_impact") if key in values]
        if summary:
            story.append(_table([["Measure", "Observed value"], *summary], styles, [85 * mm, 82 * mm]))
        by_group = values.get("by_group") or {}
        if not isinstance(by_group, dict) or any(not isinstance(item, dict) for item in by_group.values()):
            raise ReportDataError(f"Fairness by_group for {group!r} must be an object of group values.")
        if by_group:
            columns = sorted({key for item in by_group.values() if isinstance(item, dict) for key in item})
            rows = [["Group", *columns]]
            rows += [[group_name, *[_text(item.get(column)) for column in columns]]
                     for group_name, item in by_group.items()]
            story += [Spacer(1, 2 * mm), _table(rows, styles, [35 * mm] + [132 * mm / max(len(columns), 1)] * len(columns))]
    story.append(_state("Fairness evidence is diagnostic and does not establish that the model is fair or legally compliant.", styles))
    return story


def _explainability_section(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    story = [_section("6. Explainability", styles)]
    explain = (data.validation or {}).get("explainability") or {}
    if not explain:
        rows = _card_rows(data.model_card, "explainability")
        if rows:
            story.append(_table([["Evidence", "Value", "Source"], *rows], styles, [42 * mm, 85 * mm, 40 * mm]))
            return story
        story.append(_state("Not Assessed — no explainability evidence is available for this model.", styles))
        return story
    coefficients = explain.get("coefficients")
    if isinstance(coefficients, dict):
        values = {str(k): float(v) for k, v in coefficients.items() if isinstance(v, (int, float))}
        top = dict(sorted(values.items(), key=lambda item: abs(item[1]), reverse=True)[:12])
        story.append(_BarChart(top, "Largest absolute model coefficients"))
    for key, value in explain.items():
        if key.endswith("_shap") and isinstance(value, dict) and isinstance(value.get("mean_abs_shap"), dict):
            shap = {str(k): float(v) for k, v in value["mean_abs_shap"].items() if isinstance(v, (int, float))}
            story += [Spacer(1, 4 * mm), _BarChart(dict(sorted(shap.items(), key=lambda item: item[1], reverse=True)[:12]),
                                                     f"{key.replace('_', ' ').title()} feature importance")]
    return story


def _findings_section(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    story = [_section("7. Risk findings and remediation", styles)]
    findings = _findings(data)
    if not findings:
        story.append(_state("No findings are recorded in the supplied evidence.", styles))
        return story
    rows = [["ID", "Category", "Severity", "Description", "Potential impact", "Remediation", "Status"]]
    for finding in findings:
        rows.append([finding["id"], finding["category"], finding["severity"], finding["description"],
                     finding["impact"], finding["remediation"], finding["status"]])
    table = _table(rows, styles, [15 * mm, 20 * mm, 15 * mm, 34 * mm, 30 * mm, 40 * mm, 20 * mm])
    for index, finding in enumerate(findings, 1):
        table.setStyle(TableStyle([("TEXTCOLOR", (2, index), (2, index), _severity_color(str(finding["severity"])))]))
    story.append(table)
    return story


def _governance_section(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    story = [_section("8. Governance and regulatory evidence", styles)]
    story.append(_state("Evidence mapped to relevant PRA SS1/23 expectations; this report does not claim PRA compliance or supervisory approval.", styles))
    stages = data.governance.get("stages") or []
    if not isinstance(stages, list) or any(not isinstance(stage, dict) for stage in stages):
        raise ReportDataError("Governance stages must be an array of objects.")
    rows = [["Control area", "Source evidence", "Recorded model status", "Project evidence"]]
    for stage in stages:
        key = str(stage.get("stage", ""))
        status = _governance_stage_status(data.record.get(f"{key}_status"))
        evidence = stage.get("modeltrace_provides", "Not Available")
        rows.append([stage.get("gate", key), "Available" if _stage_evidence(data, key) else "Not Available",
                     status, evidence])
    if len(rows) > 1:
        story.append(_table(rows, styles, [42 * mm, 28 * mm, 32 * mm, 65 * mm]))
    else:
        story.append(_state("Governance mapping is unavailable.", styles))
    return story


def _appendix(data: ModelReportData, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    refs = list(data.record.get("source_files") or [])
    refs += [path for path in (data.discovery or {}).get("source_files", []) if path not in refs]
    story = [_section("9. Audit trail and appendix", styles),
             _table([["Item", "Value"], ["Generated", datetime.now(timezone.utc).isoformat(timespec="seconds")],
                     ["Model ID", data.model_id], ["Source evidence", refs or ["Not Available"]],
                     ["Discovery report", f"reports/discovery/{data.model_id}_discovery.json"],
                     ["Model card", f"reports/documentation/{data.model_id}_model_card.json"]], styles,
                    [45 * mm, 122 * mm], header=False),
             Spacer(1, 5 * mm),
             _state("Report generation is read-only. Missing evidence is labelled rather than replaced with inferred results.", styles)]
    return story


def build_individual_story(data: ModelReportData) -> list[Flowable]:
    styles = _styles()
    story = _cover(data, styles)
    story += _documentation_section(data, styles)
    story.append(PageBreak())
    story += _performance_section(data, styles)
    story += _migration_section(data, styles)
    story.append(PageBreak())
    story += _monitoring_section(data, styles)
    story += _fairness_section(data, styles)
    story.append(PageBreak())
    story += _explainability_section(data, styles)
    story += _findings_section(data, styles)
    story += _governance_section(data, styles)
    story += _appendix(data, styles)
    return story


def _portfolio_findings(data: PortfolioReportData) -> list[dict[str, Any]]:
    rows = []
    for model in data.models:
        for finding in _findings(model):
            rows.append({"model": model.model_id, **finding})
    return rows


def build_portfolio_story(data: PortfolioReportData) -> list[Flowable]:
    styles = _styles()
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    findings = _portfolio_findings(data)
    story: list[Flowable] = [
        Spacer(1, 25 * mm),
        Paragraph("MODELTRACE AI", styles["title"]),
        Paragraph("ENTERPRISE MODEL RISK PORTFOLIO REPORT", styles["subtitle"]),
        Spacer(1, 10 * mm),
        _table([["Report generated", generated], ["Inventory models", data.inventory_count],
                ["Models included", len(data.models)], ["Total findings", len(findings)],
                ["High/Critical findings", sum(str(f["severity"]).lower() in {"high", "critical"} for f in findings)]],
               styles, [55 * mm, 112 * mm], header=False),
        Spacer(1, 8 * mm),
        _state("This report covers the selected demonstration models and must not be interpreted as a complete bank-wide portfolio assessment.", styles),
        PageBreak(),
        _section("1. Portfolio inventory overview", styles),
    ]
    rows = [["Model", "Algorithm", "Risk tier", "Validation status", "Findings", "Monitoring"]]
    for model in data.models:
        status, _ = _status_for(model)
        rows.append([model.model_name, model.record.get("algorithm"), f"Tier {model.record.get('risk_tier')}",
                     status, model.finding_count, "Available" if model.monitoring else "Not Assessed"])
    story.append(_table(rows, styles, [39 * mm, 40 * mm, 18 * mm, 27 * mm, 17 * mm, 26 * mm]))
    story.append(Spacer(1, 6 * mm))
    tier_counts: dict[str, float] = {}
    for model in data.models:
        key = f"Tier {model.record.get('risk_tier', 'Not Available')}"
        tier_counts[key] = tier_counts.get(key, 0) + 1
    story.append(_BarChart(tier_counts, "Risk-tier distribution"))
    story.append(PageBreak())
    story += [_section("2. Model comparison", styles)]
    compare_rows = [["Model", "Performance", "Fairness", "Explainability", "Migration"]]
    for model in data.models:
        compare_rows.append([
            model.model_name,
            "Available" if (model.validation or {}).get("metrics") else "Not Assessed",
            "Available" if (model.validation or {}).get("fairness") else "Not Assessed",
            "Available" if (model.validation or {}).get("explainability") or _card_rows(model.model_card, "explainability") else "Not Assessed",
            _migration_status(model),
        ])
    story.append(_table(compare_rows, styles, [42 * mm, 30 * mm, 30 * mm, 35 * mm, 30 * mm]))
    story += [_section("3. Portfolio findings register", styles)]
    if findings:
        rows = [["Model", "ID", "Severity", "Category", "Description", "Status"]]
        rows += [[f["model"], f["id"], f["severity"], f["category"], f["description"], f["status"]] for f in findings]
        story.append(_table(rows, styles, [27 * mm, 20 * mm, 18 * mm, 30 * mm, 52 * mm, 20 * mm]))
    else:
        story.append(_state("No findings are recorded in the supplied evidence.", styles))
    story += [_section("4. Portfolio governance summary", styles),
              _state("Evidence mapped to relevant PRA SS1/23 expectations; the report is not a compliance or approval determination.", styles)]
    stages = data.governance.get("stages") or []
    if not isinstance(stages, list) or any(not isinstance(stage, dict) for stage in stages):
        raise ReportDataError("Governance stages must be an array of objects.")
    if stages:
        rows = [["Stage", "Models with source evidence", "Approved", "Not applicable",
                 "Pending / in progress", "Not recorded"]]
        for stage in stages:
            key = str(stage.get("stage", ""))
            evidence = sum(_stage_evidence(model, key) for model in data.models)
            statuses = [_governance_stage_status(model.record.get(f"{key}_status")) for model in data.models]
            approved = statuses.count("Approved")
            not_applicable = statuses.count("Not applicable")
            pending = statuses.count("Pending / in progress")
            not_recorded = statuses.count("Not recorded")
            rows.append([key.title(), evidence, approved, not_applicable, pending, not_recorded])
        story.append(_table(rows, styles, [30 * mm, 35 * mm, 22 * mm, 27 * mm, 35 * mm, 28 * mm]))
    story += [_section("5. Portfolio recommendations", styles),
              _state("Prioritize open critical/high findings, obtain missing validation evidence for models marked Not Assessed, and route all governance decisions through the existing human approval gates.", styles),
              _section("6. Audit trail", styles),
              _table([["Item", "Value"], ["Generated", generated], ["Inventory count", data.inventory_count],
                      ["Included model IDs", [model.model_id for model in data.models]],
                      ["Source", "Existing inventory and report JSON files"]], styles, [50 * mm, 117 * mm], header=False)]
    return story


def _build(story: list[Flowable], output_path: str | Path, title: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ReportDocTemplate(path, title).build(story)
    return path


def generate_individual_report(model_id: str, root: str | Path = ".", output_dir: str | Path = "reports/pdf") -> Path:
    """Generate an individual report from existing evidence and return its path."""
    data = ReportDataLoader(root).model(model_id)
    path = Path(root) / output_dir / f"MODELTRACE_{_slug(data.model_name)}_Model_Risk_Report.pdf"
    return _build(build_individual_story(data), path, f"MODELTRACE AI - {data.model_name}")


def generate_portfolio_report(root: str | Path = ".", output_dir: str | Path = "reports/pdf",
                             model_ids: list[str] | None = None) -> Path:
    """Generate a portfolio report for inventory models and return its path."""
    data = ReportDataLoader(root).portfolio(model_ids)
    path = Path(root) / output_dir / "MODELTRACE_Portfolio_Model_Risk_Report.pdf"
    return _build(build_portfolio_story(data), path, "MODELTRACE AI - Enterprise Model Risk Portfolio")
