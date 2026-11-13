"""Evidence-backed PDF reporting for MODELTRACE AI."""

from .data_loader import ModelReportData, PortfolioReportData, ReportDataError, ReportDataLoader
from .report_builder import (
    generate_individual_report,
    generate_portfolio_report,
)

__all__ = [
    "ModelReportData",
    "PortfolioReportData",
    "ReportDataError",
    "ReportDataLoader",
    "generate_individual_report",
    "generate_portfolio_report",
]
