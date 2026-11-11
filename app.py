"""Optional Streamlit governance dashboard.

The governance library itself has no Streamlit dependency; install Streamlit
only when running this file as a dashboard.
"""

from pathlib import Path

from governance.artifacts import load_json_artifact


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("Streamlit is optional; install it to run app.py") from exc

    st.set_page_config(page_title="ModelTrace Governance", layout="wide")
    st.title("ModelTrace AI/ML Governance")
    st.caption("SS1/23-aligned lifecycle and evidence dashboard")
    root = Path(__file__).parent
    sections = {
        "Executive Overview": root / "inventory" / "models.json",
        "Inventory": root / "inventory" / "models.json",
        "Discovery": root / "reports" / "discovery" / "discovery_results.json",
        "Documentation": root / "docs" / "model_card.json",
        "Validation": root / "reports" / "validation" / "validation_results.json",
        "Risk & Evidence": root / "reports" / "risk_findings" / "risk_findings_results.json",
        "Monitoring": root / "reports" / "monitoring" / "monitoring_results.json",
        "Migration": root / "reports" / "migration" / "migration_results.json",
        "Governance": root / "governance" / "audit_log.json",
    }
    for title, path in sections.items():
        with st.expander(title, expanded=title == "Inventory"):
            artifact = load_json_artifact(path)
            if artifact is None:
                st.info(f"No readable artifact found at {path}")
            else:
                st.json(artifact)


if __name__ == "__main__":
    main()
