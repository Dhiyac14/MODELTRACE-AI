# MODELTRACE AI

This repository contains the reproducible ML engineering, migration, validation,
and monitoring components for ModelTrace AI.

The dataset is historical Taiwanese credit-card data from the official UCI
repository and is used strictly for a public demonstration. It must not be
described as representative of a current UK bank portfolio.

## Quick start

```powershell
python -m pip install -e ".[dev,validation,statsmodels]"
python -m pytest
streamlit run app.py
```

To run the end-to-end ML pipeline, use:

```powershell
python -m engine.pipeline
```

The pipeline uses the downloaded UCI workbook and requires `Rscript`, network
access for the first data download, and the installed Python dependencies.

## Person 1 ML engine

The ML engine provides reproducible migration, validation, monitoring, and risk
evidence for the legacy R model.

The pipeline writes integration-ready JSON to:

- `reports/migration/migration_results.json`
- `reports/validation/validation_results.json`
- `reports/monitoring/monitoring_results.json`
- `reports/risk_findings/risk_findings_results.json`

Tests use a deterministic local fixture. The pipeline acquires the UCI workbook
through `ucimlrepo.fetch_ucirepo(id=350)` and validates its provenance,
dimensions, target, missingness, and default rate. The generated shared split,
model artifacts, and R prediction CSV are ignored so large/intermediate files
are not committed.

The original R `glm()` model is implemented in
`models/legacy_model.R` and classifies probabilities at its explicit 0.35
threshold. The pipeline persists one shared train/test CSV split, executes R
`glm(..., family = binomial(link = "logit"))`, executes Python Statsmodels
`Logit`, and compares predictions in
`reports/migration/migration_results.json`. Running `python -m engine.pipeline`
uses the downloaded UCI workbook and requires `Rscript` and the Python
dependencies to be installed.

The Discovery answer key is private: keep it outside the repository and point
`MODELTRACE_ANSWER_KEY` at it. The scorer refuses a key path inside any git
repository; the pipeline then warns and runs Discovery unscored. Do not share it
with the Discovery Agent operator or Person 2.

## Person 2 agents, governance and dashboard

The agent layer discovers, documents and monitors the models, and every stage passes a human approval gate.
The Streamlit dashboard brings the five lifecycle stages together: Discover, Document, Redevelop, Validate
and Monitor. Design and interfaces: `docs/design/person2_design.md`. Architecture: `docs/architecture.png`.

For local dashboard development, optionally create `.env` from `.env.example`
and add `LLM_API_KEY`. To reset the demonstration inventory only, run:

```bash
python -m inventory.registry --seed --force
```

Without an API key the dashboard and the Documentation and Monitoring Agents still run with template text;
only the Discovery and LLM Migration Agents need the LLM. With `LLM_PROVIDER=anthropic` the agents use Claude Opus 5.5 at
medium effort; `LLM_PROVIDER=openai` works with any OpenAI-compatible endpoint. Never commit `.env`.

### What runs where

| Component | Code | Output |
|---|---|---|
| Discovery Agent: facts from code with checked line references; code vs existing document | `agents/discovery_agent.py` | `reports/discovery/<model_id>_discovery.json` |
| Documentation Agent: model card, figures copied from Person 1's reports | `agents/documentation_agent.py` | `reports/documentation/`, `docs/model_cards/` |
| LLM Migration Agent: the LLM writes a Python version of the R model; it is checked, run in isolation and compared with R's predictions, up to 3 rounds | `agents/llm_migration_agent.py`, `agents/migration_harness.py` | `reports/llm_migration/<model_id>_llm_migration.json`, `<model_id>_candidate.py` |
| Monitoring Agent: rule-based alerts on Person 1's monitoring report, explained by the LLM | `agents/monitoring_agent.py` | `reports/alerts/<model_id>_alerts.json` |
| Approval workflow, separation of duties, hash-chained audit log | `workflow/` | `governance/*.json` (git-ignored) |
| Inventory and SS1/23 risk tier | `inventory/`, `governance/ss1_23_mapping.json` | `inventory/model_inventory.json` |
| Optional MLflow export of the reports, linked to the audit chain and approvals | `governance/mlflow_export.py` | `mlflow.db`, `mlruns/` (git-ignored) |

Command-line runs (the dashboard has the same buttons):

```bash
python -m agents.discovery_agent --model-id legacy-r-logistic --source models/legacy_model.R --source engine/data.py --doc models/outdated_model_document.md
python -m agents.documentation_agent --model-id legacy-r-logistic
python -m agents.llm_migration_agent --model-id legacy-r-logistic --source models/legacy_model.R
python -m agents.monitoring_agent --model-id legacy-r-logistic
```

The LLM Migration Agent needs Person 1's shared split and R predictions (`python -m engine.pipeline`). Its
report is evidence for the reviewer; the Redevelop gate still reads Person 1's parity report.

Person 1 scores the Discovery report with the private answer key; the dashboard shows the result:

```bash
export MODELTRACE_ANSWER_KEY=~/modeltrace-private/discovery_answer_key.json  # outside the repository
python -m agents.discovery_agent --model-id legacy-r-logistic --score "$MODELTRACE_ANSWER_KEY"
python -m agents.discovery_agent --model-id python-gradient-boosting --score "$MODELTRACE_ANSWER_KEY"
```

The key holds `expected_*` metadata values and a `discrepancies` mapping from model id to a list of
`{id, field, type, description}`. Top-level `expected_*` values belong to the legacy R model; other models are
fact-scored only from their own entry under `metadata` (model id to `expected_*` values), so Gradient Boosting
is never scored against the R facts. Discrepancies match one-to-one on field and type; the same field with another
type is `misclassified`, and a finding that matches nothing is `unsupported`. Contradictions and unverifiable
claims are always scored; omissions only when the key lists one. Code evidence counts only when each quote is
still at its cited lines in the model's source files (as registered in the inventory) and covers most of those
lines. The score (`reports/discovery/<model_id>_score.json`) lists key entries by id and outcome only, never their
field, type or description, so it can be committed without revealing what was missed.

### Optional: MLflow tracking

MLflow is not a core dependency. After `python -m engine.pipeline`, this logs one run with the
validation, parity, fairness and per-batch monitoring metrics, the report files as artifacts, and tags for
the audit chain head, the stage approvals and each report's SHA-256:

```bash
python -m pip install mlflow
python -m governance.mlflow_export
mlflow ui --backend-store-uri sqlite:///mlflow.db
```

The reports and the hash-chained audit log stay the record; MLflow is for comparing runs. Set
`MLFLOW_TRACKING_URI` to an Azure ML workspace (with `azureml-mlflow`) to send the run there instead.

### Demo users and rules

The dashboard has no login; pick the acting user in the sidebar (`governance/users.json`). Developers
submit Discover, Document and Redevelop; the validator submits Validate; the monitoring analyst submits
Monitor and reviews alerts; the risk manager decides every gate. Nobody can decide on their own submission,
whoever built the redevelopment cannot validate it, and agents cannot approve anything. Redevelop can only
be approved when Person 1's parity report says `r_vs_statsmodels.overall_pass` is true.

### Tests

```bash
python -m pytest
```

Person 2's tests are `tests/test_p2_*.py`; they run offline with fake or replayed LLM replies.
Responsible AI note: `governance/responsible_ai.md`. AI-use declaration: `governance/ai_use_declaration.md`.

## Automated PDF model-risk reports

The read-only `reporting/` package turns the existing inventory, Discovery reports,
model cards, validation, migration, monitoring, risk-finding and SS1/23 mapping
JSON into printable A4 PDFs. It does not create metrics or alter source reports.
Missing evidence is labelled `Not Assessed`, `Not Available` or `Not Applicable`;
recorded governance approval is shown as `Approved (recorded)` and is not treated
as independent validation.

Generate reports from Python:

```python
from reporting import generate_individual_report, generate_portfolio_report

generate_individual_report("legacy-r-logistic")
generate_individual_report("python-gradient-boosting")
generate_individual_report("python-random-forest")
generate_portfolio_report()
```

The default output directory is `reports/pdf/`. The Streamlit dashboard's
**Model Risk Reports** section provides the same individual-model and portfolio
generation actions and download buttons. Reports distinguish recorded approval
(`Approved (recorded)`), `Pending Review`, `Not Assessed`, and missing evidence;
generating a PDF never constitutes independent model approval or PRA SS1/23
compliance.

Run the focused reporting tests with:

```bash
python -m pytest tests/test_pdf_reporting.py
```

Known limitation: the sample repository contains full engine validation,
monitoring, migration and risk evidence only for the legacy R model. The two
Python sample models therefore show explicit missing-evidence states where
those reports are not present.
