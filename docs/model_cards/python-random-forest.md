# Model card: Python Random Forest (python-random-forest)

Version 1.0.0 · Risk tier 3 · Review status: **pending_human_review**  
Generated 2026-11-13T15:18:36+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

Python Random Forest (model_id: python-random-forest) is a benchmark model for internal analysis and is not used in decisions; it serves as a comparison model rather than the migration candidate. It predicts the binary target default.payment.next.month using the UCI Default of Credit Card Clients dataset (30,000 records of credit-card clients in Taiwan, payment history April to September 2005), which is public demonstration data and not representative of a UK bank's current portfolio. The business owner, intended use and decision context are not documented, and the business purpose and target variable are recorded as inferred. The model is assigned risk tier 3.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a scikit-learn RandomForestClassifier with n_estimators=150, random_state=seed (default 42), n_jobs=-1 and class_weight="balanced" to address an expected default rate of about 22%; other hyperparameters use library defaults. It uses 21 predictors (LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0 and PAY_2 to PAY_6, BILL_AMT1 to BILL_AMT6, PAY_AMT1 to PAY_AMT6), with ID, SEX and AGE excluded and SEX and AGE treated as fairness-only attributes. Preprocessing renames columns, drops ID and rows with missing values, validates the official dataset (30,000 rows, 25 columns, no missing values, default rate between 0.20 and 0.24), casts the target to int, and applies no scaling or encoding. Data is split with a stratified 80/20 train/test split (random_state=42 by default), shared with the R legacy model.

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | default.payment.next.month | engine/data.py:L19; engine/data.py:L142 (inferred) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | engine/data.py:L58-63; engine/models.py:L63; engine/data.py:L150-151 (inferred) |
| Excluded columns | ID, SEX, AGE, default.payment.next.month | engine/data.py:L20-22; engine/data.py:L149-150; engine/data.py:L141 (verified) |
| Preprocessing | Rename the source target column 'default payment next month' to 'default.payment.next.month' (load_dataset), Drop the ID column and rows with missing values (load_dataset), For the official ucimlrepo source, rename columns X1..X23 to named features, Validate the official dataset: 30,000 rows, 25 columns, no missing values, default rate between 0.20 and 0.24, Cast the target to int, Stratified train/test split with test_size=0.2 and random_state=42 by default, Drop ID, SEX and AGE from the predictors (predictive_features), No scaling or encoding is applied to the random forest inputs | engine/data.py:L38-43; engine/data.py:L64-65; engine/data.py:L103; engine/data.py:L142-145; engine/models.py:L75 (verified) |
| Train/test split | 80% train / 20% test | engine/data.py:L136 (inferred) |
| Decision threshold | Not determined from the code | engine/models.py:L31; engine/models.py:L21 (missing) |

## Performance metrics

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Fairness considerations

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Stability

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Explainability

| Item | Value | Evidence |
|---|---|---|
| random_forest_shap.n_rows | 500 | reports/validation/validation_results.json#explainability.random_forest_shap.n_rows |
| random_forest_shap.mean_abs_shap.LIMIT_BAL | 0.0328 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.LIMIT_BAL |
| random_forest_shap.mean_abs_shap.EDUCATION | 0.0047 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.EDUCATION |
| random_forest_shap.mean_abs_shap.MARRIAGE | 0.0057 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.MARRIAGE |
| random_forest_shap.mean_abs_shap.PAY_0 | 0.08 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_0 |
| random_forest_shap.mean_abs_shap.PAY_2 | 0.039 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_2 |
| random_forest_shap.mean_abs_shap.PAY_3 | 0.0239 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_3 |
| random_forest_shap.mean_abs_shap.PAY_4 | 0.0171 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_4 |
| random_forest_shap.mean_abs_shap.PAY_5 | 0.0148 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_5 |
| random_forest_shap.mean_abs_shap.PAY_6 | 0.0119 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_6 |
| random_forest_shap.mean_abs_shap.BILL_AMT1 | 0.0191 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT1 |
| random_forest_shap.mean_abs_shap.BILL_AMT2 | 0.0135 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT2 |
| random_forest_shap.mean_abs_shap.BILL_AMT3 | 0.0124 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT3 |
| random_forest_shap.mean_abs_shap.BILL_AMT4 | 0.0106 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT4 |
| random_forest_shap.mean_abs_shap.BILL_AMT5 | 0.0104 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT5 |
| random_forest_shap.mean_abs_shap.BILL_AMT6 | 0.0114 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT6 |
| random_forest_shap.mean_abs_shap.PAY_AMT1 | 0.0195 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT1 |
| random_forest_shap.mean_abs_shap.PAY_AMT2 | 0.0191 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT2 |
| random_forest_shap.mean_abs_shap.PAY_AMT3 | 0.0189 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT3 |
| random_forest_shap.mean_abs_shap.PAY_AMT4 | 0.0129 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT4 |
| random_forest_shap.mean_abs_shap.PAY_AMT5 | 0.0117 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT5 |
| random_forest_shap.mean_abs_shap.PAY_AMT6 | 0.0135 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT6 |

## Limitations and assumptions

Hyperparameters are fixed with no tuning shown in the code, and the rationale for n_estimators=150 and class_weight=balanced is not documented; no operational decision threshold is documented. The model_identity hash and coefficient extraction support only the Statsmodels candidate, not this model, and if the demo fixture is used instead of the UCI data the model trains on synthetic data with only 3 predictors. Performance metrics, validation results, acceptance criteria, fairness and monitoring results, and prediction PSI are not documented (the results fields are empty). Also not documented are the production data loader, how the train fraction is set at the call site, the interpretability approach, model version, approval status, deployment and retraining schedule.

## Risk tier, approval and governance

| Item | Value | Evidence |
|---|---|---|
| Risk tier | Tier 3 | inventory (computed by rule) |
| Materiality | low: internal benchmark only, not used in decisions | inventory |
| Complexity | medium: bagged tree ensemble with standard settings | inventory |
| Tier rule | Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | SS1/23 1.3 |
| Tier rationale | Tier 3: materiality is low (internal benchmark only, not used in decisions) and complexity is medium (bagged tree ensemble with standard settings). Rule: Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | rule_template |
| Discover gate (tier and discovery report) | not_started | governance/approval_log.json |
| Approval records | None recorded | governance/approval_log.json |
| Model card status | pending_human_review | this card |
| SS1/23 principles covered | 1. Model identification and model risk classification; 1.2 Model inventory; 1.3 Model tiering; 3. Model development, implementation and use; 3.5 Model development documentation | governance/ss1_23_mapping.json |

## Corrections to the existing model document

No existing model document was compared.
