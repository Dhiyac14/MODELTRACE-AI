# Model card: Python Gradient Boosting (python-gradient-boosting)

Version 1.0.0 · Risk tier 2 · Review status: **pending_human_review**  
Generated 2026-11-13T15:18:29+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

Python Gradient Boosting (python-gradient-boosting) is a challenger model that is compared against the production default model; it informs but does not drive decisions. The business purpose shown here is inferred, and the model owner and intended business use or decision are not documented. It predicts the target default.payment.next.month using the UCI Default of Credit Card Clients dataset (30,000 records, 23 input variables), which is public demonstration data and not representative of a UK bank's current portfolio. The facts list the model as risk tier 2.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a scikit-learn GradientBoostingClassifier with default hyperparameters and random_state set to the seed (default 42). The data is fetched from UCI dataset 350 and checked for 30,000 rows, 25 columns, no missing values and a default rate between 0.20 and 0.24. A stratified train/test split of 80/20 is then applied with random_state=42; the train fraction is inferred. The model uses 21 predictors: LIMIT_BAL, EDUCATION, MARRIAGE, the PAY, BILL_AMT and PAY_AMT series. ID, SEX and AGE are excluded, and no scaling or encoding is applied.

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | default.payment.next.month | engine/data.py:L19; engine/data.py:L141-142 (verified) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | engine/data.py:L58-63; engine/data.py:L150-151; engine/models.py:L63 (inferred) |
| Excluded columns | ID, SEX, AGE, default.payment.next.month | engine/data.py:L20-22; engine/data.py:L148-151; engine/data.py:L141 (verified) |
| Preprocessing | Fetch UCI dataset 350 via ucimlrepo and rename X1..X23 columns to the expected feature names, Validate the dataset: 30,000 rows, 25 columns, no missing values, default rate between 0.20 and 0.24, Separate the target default.payment.next.month and cast it to int, Stratified train/test split with test_size=0.2 and random_state=42, Drop ID, SEX and AGE from the predictors via predictive_features, No scaling or encoding is applied for gradient_boosting | engine/data.py:L64-65; engine/data.py:L103; engine/data.py:L143-145; engine/models.py:L71 (verified) |
| Train/test split | 80% train / 20% test | engine/data.py:L135-137 (inferred) |
| Decision threshold | Not determined from the code | engine/models.py:L30-31 (missing) |

## Performance metrics

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Fairness considerations

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Stability

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Explainability

| Item | Value | Evidence |
|---|---|---|
| gradient_boosting_shap.n_rows | 500 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.n_rows |
| gradient_boosting_shap.mean_abs_shap.LIMIT_BAL | 0.1862 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.LIMIT_BAL |
| gradient_boosting_shap.mean_abs_shap.EDUCATION | 0.0127 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.EDUCATION |
| gradient_boosting_shap.mean_abs_shap.MARRIAGE | 0.0511 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.MARRIAGE |
| gradient_boosting_shap.mean_abs_shap.PAY_0 | 0.4708 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_0 |
| gradient_boosting_shap.mean_abs_shap.PAY_2 | 0.1088 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_2 |
| gradient_boosting_shap.mean_abs_shap.PAY_3 | 0.0885 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_3 |
| gradient_boosting_shap.mean_abs_shap.PAY_4 | 0.0516 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_4 |
| gradient_boosting_shap.mean_abs_shap.PAY_5 | 0.0495 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_5 |
| gradient_boosting_shap.mean_abs_shap.PAY_6 | 0.0611 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_6 |
| gradient_boosting_shap.mean_abs_shap.BILL_AMT1 | 0.1082 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.BILL_AMT1 |
| gradient_boosting_shap.mean_abs_shap.BILL_AMT2 | 0.038 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.BILL_AMT2 |
| gradient_boosting_shap.mean_abs_shap.BILL_AMT3 | 0.0234 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.BILL_AMT3 |
| gradient_boosting_shap.mean_abs_shap.BILL_AMT4 | 0.0077 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.BILL_AMT4 |
| gradient_boosting_shap.mean_abs_shap.BILL_AMT5 | 0.0145 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.BILL_AMT5 |
| gradient_boosting_shap.mean_abs_shap.BILL_AMT6 | 0.0297 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.BILL_AMT6 |
| gradient_boosting_shap.mean_abs_shap.PAY_AMT1 | 0.08 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_AMT1 |
| gradient_boosting_shap.mean_abs_shap.PAY_AMT2 | 0.0862 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_AMT2 |
| gradient_boosting_shap.mean_abs_shap.PAY_AMT3 | 0.0852 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_AMT3 |
| gradient_boosting_shap.mean_abs_shap.PAY_AMT4 | 0.0374 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_AMT4 |
| gradient_boosting_shap.mean_abs_shap.PAY_AMT5 | 0.032 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_AMT5 |
| gradient_boosting_shap.mean_abs_shap.PAY_AMT6 | 0.055 | reports/validation/validation_results.json#explainability.gradient_boosting_shap.mean_abs_shap.PAY_AMT6 |

## Limitations and assumptions

Performance, fairness, stability and monitoring metrics are computed only for the Statsmodels candidate; for this model only SHAP explainability is produced, using just the first 500 test rows. The decision threshold, hyperparameter rationale or tuning, model version, artifact hash, approval, deployment and monitoring status are not documented. The training data is historical Taiwanese data (April to September 2005), and deployment population representativeness and production calibration are unknown. The model assumes the library default hyperparameters are adequate and treats SEX and AGE as fairness-only attributes, and in demo mode it is trained on a synthetic dataset with only 3 predictors.

## Risk tier, approval and governance

| Item | Value | Evidence |
|---|---|---|
| Risk tier | Tier 2 | inventory (computed by rule) |
| Materiality | medium: informs model review but does not drive decisions | inventory |
| Complexity | high: boosted tree ensemble that needs SHAP to explain | inventory |
| Tier rule | Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | SS1/23 1.3 |
| Tier rationale | Tier 2: materiality is medium (informs model review but does not drive decisions) and complexity is high (boosted tree ensemble that needs SHAP to explain). Rule: Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | rule_template |
| Discover gate (tier and discovery report) | not_started | governance/approval_log.json |
| Approval records | None recorded | governance/approval_log.json |
| Model card status | pending_human_review | this card |
| SS1/23 principles covered | 1. Model identification and model risk classification; 1.2 Model inventory; 1.3 Model tiering; 3. Model development, implementation and use; 3.5 Model development documentation | governance/ss1_23_mapping.json |

## Corrections to the existing model document

Compared with models/gradient_boosting_model_document.md.

| Item | Value | Evidence |
|---|---|---|
| D-001 other (omission) | Document: Not mentioned in the document. Correction: State that the fitted model is saved to models/artifacts/gradient_boosting.joblib on every demo and real pipeline run. | engine/pipeline.py:L175-176 |
| D-002 other (omission) | Document: Not mentioned in the document. Correction: State that Gradient Boosting SHAP uses shap.TreeExplainer on the first 500 rows of the test set and reports mean absolute SHAP values per feature. | engine/validation.py:L128-129 |
