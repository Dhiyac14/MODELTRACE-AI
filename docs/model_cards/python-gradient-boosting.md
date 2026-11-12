# Model card: Python Gradient Boosting (python-gradient-boosting)

Version 1.0.0 · Risk tier 2 · Review status: **pending_human_review**  
Generated 2026-11-12T00:28:18+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

Python Gradient Boosting (model_id python-gradient-boosting) is a Python challenger model that predicts the target default.payment.next.month and is compared against the production default model; per the recorded business purpose (an inferred field), it informs but does not drive decisions. It is assigned risk tier 2. It uses the public UCI Default of Credit Card Clients dataset (30,000 records of credit-card clients in Taiwan, payment history April to September 2005), which is intended here as demonstration data only and is not representative of a UK bank's current portfolio. The business owner and intended business use are not documented.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a scikit-learn GradientBoostingClassifier with default hyperparameters except random_state set to a seed (default 42), trained on an inferred stratified 80/20 train/test split using the same seed. Preprocessing renames the target column, drops ID and rows with missing values, validates the dataset shape and default rate, casts the target to integer, and applies no feature scaling. Predictors are 21 inferred input features (LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0 and PAY_2 to PAY_6, BILL_AMT1 to BILL_AMT6, PAY_AMT1 to PAY_AMT6), with ID, SEX and AGE excluded. An inferred decision threshold of 0.5 is applied.

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | default.payment.next.month | engine/data.py:L19; engine/data.py:L142 (verified) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | engine/data.py:L58-63; engine/data.py:L148-151; engine/models.py:L59 (inferred) |
| Excluded columns | ID, SEX, AGE, default.payment.next.month | engine/data.py:L20-22; engine/data.py:L150; engine/data.py:L141 (verified) |
| Preprocessing | Rename 'default payment next month' to target name and drop ID when loading the workbook, Drop rows with missing values (workbook loader), Validate official UCI dataset (30,000 rows, 25 columns, no missing values, default rate 20-24%), Separate target and cast to int, Stratified train/test split with test_size=0.2, random_state=seed, Remove ID, SEX and AGE from predictors, No scaling applied for gradient boosting | engine/data.py:L38-43; engine/data.py:L103; engine/data.py:L141-145; engine/data.py:L151 (verified) |
| Train/test split | 80% train / 20% test | engine/data.py:L136 (inferred) |
| Decision threshold | 0.5 | engine/models.py:L27; engine/models.py:L140 (inferred) |

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

Default hyperparameters are used with no tuning or cross-validation shown, and no justification is documented; there is no class imbalance handling, and categorical fields such as EDUCATION, MARRIAGE and PAY_* are used as raw numeric values without encoding. The model assumes SEX and AGE are fairness-only attributes and an expected training default rate of about 22% (20-24%), but fairness evaluation results, validation metrics and prediction PSI are not available in the provided results. Performance metrics, acceptance criteria, the production data loader, decision threshold calibration, monitoring, retraining frequency and approval status are not documented. Several fields (business purpose, input features, train fraction and decision threshold) are inferred and should be confirmed.

## Risk tier, approval and governance

| Item | Value | Evidence |
|---|---|---|
| Risk tier | Tier 2 | inventory (computed by rule) |
| Materiality | medium: informs model review but does not drive decisions | inventory |
| Complexity | high: boosted tree ensemble that needs SHAP to explain | inventory |
| Tier rule | Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | SS1/23 1.3 |
| Tier rationale | Tier 2: materiality is medium (informs model review but does not drive decisions) and complexity is high (boosted tree ensemble that needs SHAP to explain). Rule: Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | rule_template |
| Tier review status | not_started | inventory |
| Approval records | None recorded | governance/approval_log.json |
| Discovery report status | pending_human_review | reports/discovery/python-gradient-boosting_discovery.json |
| Model card status | pending_human_review | this card |
| SS1/23 principles covered | 1. Model identification and model risk classification; 1.2 Model inventory; 1.3 Model tiering; 3. Model development, implementation and use; 3.5 Model development documentation | governance/ss1_23_mapping.json |

## Corrections to the existing model document

No existing model document was compared.
