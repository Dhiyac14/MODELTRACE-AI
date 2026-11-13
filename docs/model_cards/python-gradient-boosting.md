# Model card: Python Gradient Boosting (python-gradient-boosting)

Version 1.0.0 · Risk tier 2 · Review status: **pending_human_review**  
Generated 2026-11-13T17:47:02+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

Python Gradient Boosting (model_id python-gradient-boosting) predicts default.payment.next.month on the UCI Default of Credit Card Clients dataset. Its recorded business purpose, a challenger compared against the production default model that informs but does not drive decisions, was inferred rather than confirmed. This conflicts with the documented limitation that the model is used only for SHAP explainability. The business owner, the intended business use and the decision supported are not documented, and the facts list a risk tier of 2 while also listing the tier/risk rating as missing information.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a scikit-learn GradientBoostingClassifier with random_state set to a seed that defaults to 42 and no other hyperparameters set, so library defaults apply. It uses 21 input features (credit limit, education, marriage, the PAY_0 to PAY_6 repayment-status fields, six bill amounts and six payment amounts); ID, SEX and AGE are excluded from the predictors, though the input feature list itself was inferred. Data is fetched from UCI dataset 350 and validated for shape, missing values and default rate, then split 80/20 into stratified train and test sets with random_state 42 (the train fraction was inferred). No scaling, encoding or class imbalance handling is applied, and no decision threshold is documented.

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | default.payment.next.month | engine/data.py:L19; engine/data.py:L141-142 (verified) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | engine/data.py:L58-63; engine/data.py:L148-151; engine/models.py:L63 (inferred) |
| Excluded columns | ID, SEX, AGE, default.payment.next.month | engine/data.py:L20-22; engine/data.py:L150; engine/data.py:L141 (verified) |
| Preprocessing | Fetch UCI dataset 350 via ucimlrepo and rename X1..X23 columns to named features, Validate dataset shape (30,000 rows, 25 columns), no missing values, default rate 20-24%, Separate target default.payment.next.month and cast to int, Stratified train/test split with test_size=0.2, random_state=42, Drop ID, SEX and AGE from predictors via predictive_features, No scaling or encoding applied to gradient boosting inputs | engine/data.py:L64-65; engine/data.py:L103; engine/data.py:L143-145; engine/models.py:L74-76 (verified) |
| Train/test split | 80% train / 20% test | engine/data.py:L135-137; engine/pipeline.py:L173 (inferred) |
| Decision threshold | Not determined from the code | engine/models.py:L30-31; engine/models.py:L19-21 (missing) |

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

Performance, calibration, fairness, stability and monitoring are not evaluated for this model, since those reports use the Statsmodels candidate, and SHAP explainability is computed only on the first 500 test rows. The model assumes default hyperparameters are adequate, but no rationale for them or any tuning is documented. Training data is public 2005 Taiwanese credit-card demonstration data that is not representative of a UK bank's current portfolio, so its representativeness for any deployment population is unknown. The decision threshold, monitoring plan, approval status and deployment status are not documented.

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
| D-001 other (omission) | Document: Not mentioned in the document. Correction: State that the fitted model is persisted to models/artifacts/gradient_boosting.joblib in both the demo and real pipelines. | engine/pipeline.py:L175-176 |
| D-002 other (omission) | Document: Not mentioned in the document. Correction: State that Gradient Boosting SHAP explainability uses TreeExplainer on the first 500 test rows and reports mean absolute SHAP values per feature. | engine/validation.py:L120-128 |
| D-003 monitoring (omission) | Document: Not mentioned in the document. Correction: State that the pipeline does not monitor the Gradient Boosting model; monitoring covers only the Statsmodels candidate. | engine/pipeline.py:L213-214 |
