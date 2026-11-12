# MODELTRACE AI

## Person 1 ML engine

This repository contains the reproducible ML engineering, migration, validation,
and monitoring components for ModelTrace AI.

The dataset is historical Taiwanese credit-card data from the official UCI
repository and is used strictly for a public demonstration. It must not be
described as representative of a current UK bank portfolio.

### Quick start

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m engine.pipeline
```

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
`models/legacy_model.R`. The pipeline persists one shared train/test CSV split,
executes R `glm(..., family = binomial(link = "logit"))`, executes Python
Statsmodels `Logit`, and compares predictions in
`reports/migration/migration_results.json`. Running `python -m engine.pipeline`
uses the downloaded UCI workbook and requires `Rscript` and the Python
dependencies to be installed.

`models/discovery_answer_key.json` is intentionally local-only and ignored by
Git. Do not share it with the Discovery Agent operator or Person 2.

## Person 2 agents, governance and dashboard

The agent layer discovers, documents and monitors the models, and every stage passes a human approval gate.
The Streamlit dashboard brings the five lifecycle stages together: Discover, Document, Redevelop, Validate
and Monitor. Design and interfaces: `docs/design/person2_design.md`. Architecture: `docs/architecture.png`.

### Quick start

```bash
python -m pip install -e ".[dev,validation,statsmodels]"
python -m pip install -r requirements.txt
cp .env.example .env          # optional: add LLM_API_KEY to use Claude
python -m inventory.registry --seed --force   # only to reset the inventory
streamlit run app.py
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

Command-line runs (the dashboard has the same buttons):

```bash
python -m agents.discovery_agent --model-id legacy-r-logistic --source models/legacy_model.R --source engine/data.py --doc models/outdated_model_document.md
python -m agents.documentation_agent --model-id legacy-r-logistic
python -m agents.llm_migration_agent --model-id legacy-r-logistic --source models/legacy_model.R
python -m agents.monitoring_agent --model-id legacy-r-logistic
```

The LLM Migration Agent needs Person 1's shared split and R predictions (`python -m engine.pipeline`). Its
report is evidence for the reviewer; the Redevelop gate still reads Person 1's parity report.

Person 1 scores the Discovery report with the local answer key; the dashboard shows the result:

```bash
python -m agents.discovery_agent --model-id legacy-r-logistic --score models/discovery_answer_key.json
```

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
