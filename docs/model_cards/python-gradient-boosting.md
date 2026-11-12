# Model card: Python Gradient Boosting (python-gradient-boosting)

Version 1.0.0 · Risk tier 2 · Review status: **pending_human_review**  
Generated 2026-11-12T22:48:56+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

Python Gradient Boosting (python-gradient-boosting) is a challenger model that predicts the target default.payment.next.month and is compared against the production default model; per the facts provided, it informs but does not drive decisions, though this business purpose is recorded as inferred. It is assigned risk tier 2. It uses the UCI Default of Credit Card Clients dataset (30,000 records of credit-card clients in Taiwan, payment history April to September 2005), which is described as public demonstration data only and not representative of a UK bank's current portfolio. The business owner, intended use and decision context are not documented.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a scikit-learn GradientBoostingClassifier using library default hyperparameters except random_state set to a seed (default 42), with 21 predictors covering credit limit, education, marital status, repayment status (PAY_0, PAY_2 to PAY_6), bill amounts and payment amounts; ID, SEX and AGE are excluded from the predictors. Preprocessing renames the target column, drops ID, drops rows with missing values on the workbook load path, validates the official UCI data (30,000 rows, 25 columns, no missing values, default rate between 20% and 24%), and casts the target to int; no scaling or encoding is applied. Data is split with a stratified train/test split (test_size=0.2, random_state=42), and a decision threshold of 0.5 is recorded, although the input feature list, train fraction and threshold are marked as inferred. The approved threshold and its rationale, and the hyperparameter selection rationale, are not documented.

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | default.payment.next.month | engine/data.py:L19; engine/data.py:L142 (verified) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | engine/data.py:L58-63; engine/data.py:L148-151; engine/models.py:L59 (inferred) |
| Excluded columns | ID, SEX, AGE, default.payment.next.month | engine/data.py:L20-22; engine/data.py:L150; engine/data.py:L141 (verified) |
| Preprocessing | Rename target column 'default payment next month' to 'default.payment.next.month' and drop ID, then drop rows with missing values (workbook load path), Validate the official UCI dataset: 30,000 rows, 25 columns, no missing values, default rate between 20% and 24%, Cast target to int and run a stratified train/test split (test_size=0.2, random_state=42), Drop ID, SEX and AGE from predictors via predictive_features, No scaling or encoding is applied for the gradient boosting model | engine/data.py:L38-43; engine/data.py:L103; engine/data.py:L142-145; engine/models.py:L67 (verified) |
| Train/test split | 80% train / 20% test | engine/data.py:L135-137 (inferred) |
| Decision threshold | 0.5 | engine/models.py:L26-27; engine/models.py:L140 (inferred) |

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

No hyperparameter tuning or class imbalance handling is applied, unlike the random forest, which uses class_weight='balanced'. SEX and AGE are excluded on the assumption that this addresses fairness, but proxy variables such as EDUCATION and MARRIAGE remain among the predictors, and fairness test results and tolerances are not documented. A synthetic demo dataset may be used when UCI data is unavailable, which would change the feature set, and the data path used in production is not documented. Validation metrics, acceptance criteria, PSI results, monitoring and retraining plans, model version and deployment details are not documented.

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

Compared with models/gradient_boosting_model_document.md.

| Item | Value | Evidence |
|---|---|---|
| D-001 decision_threshold (omission) | Document: The document does not state the decision threshold. Correction: State the decision threshold: 0.5. | engine/models.py:L26-27; engine/models.py:L140 |
| D-002 model_name (contradiction) | Document: The model is a challenger model identified as python-gradient-boosting. Correction: The model is a supporting comparison model identified in code as 'gradient_boosting'. | engine/models.py:L67; engine/models.py:L72 |
| D-003 performance (unverifiable) | Document: The validation report from engine/pipeline.py evaluates the migrated Statsmodels logistic model and does not report Gradient Boosting performance metrics. Correction:  | no code evidence |
| D-004 other (unverifiable) | Document: The real-data pipeline may produce SHAP explainability values for the Gradient Boosting model when the optional SHAP dependency is available. Correction:  | no code evidence |
| D-005 limitations (omission) | Document: Not mentioned in the document. Correction: Document that a synthetic demo dataset (make_demo_dataset, 1200 rows) exists as a fallback when the UCI file is unavailable, and that results from it are not representative. | engine/data.py:L118-119 |
| D-006 preprocessing (omission) | Document: Not mentioned in the document. Correction: Document that the workbook loader drops rows with missing values. Also document that the official UCI loader stops with an error unless the data has 30,000 rows and 25 columns, contains no missing values and has a default rate between 20% and 24%. | engine/data.py:L43; engine/data.py:L109-114 |

## Grounding warnings

- methodology: the draft mentions approval or validation but none is recorded; check the wording.
