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
