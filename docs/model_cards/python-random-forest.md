# Model card: Python Random Forest (python-random-forest)

Version 1.0.0 · Risk tier 3 · Review status: **pending_human_review**  
Generated 2026-11-12T00:28:58+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

Python Random Forest (python-random-forest) is a risk tier 3 classifier that predicts the target variable default.payment.next.month, using the public UCI Default of Credit Card Clients dataset (30,000 records of credit-card clients in Taiwan, April to September 2005). Its business purpose is recorded, as an inferred field, as a benchmark model for internal analysis that is not used in decisions, and it is described as a supporting comparison model rather than the migration target. The business owner, intended business use, model version and approval status are not documented.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a scikit-learn RandomForestClassifier with n_estimators=150, random_state set by a seed (default 42), n_jobs=-1 and class_weight="balanced" to handle class imbalance, with no input scaling. Data is loaded either through the official ucimlrepo client (which checks shape, missing values and default rate) or from an Excel workbook (header=1, target renamed, ID dropped, rows with missing values removed). The target is cast to int, and a stratified train/test split is applied with test_size=0.2 and random_state=42. ID, SEX and AGE are excluded from the predictors, with SEX and AGE reserved for fairness analysis; the 21 listed input features, the 0.8 train fraction and the 0.5 decision threshold are inferred fields rather than confirmed specifications.

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | default.payment.next.month | engine/data.py:L19; engine/data.py:L142 (verified) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | engine/data.py:L58-63; engine/data.py:L150-151; engine/models.py:L59 (inferred) |
| Excluded columns | ID, SEX, AGE, default.payment.next.month | engine/data.py:L20-22; engine/data.py:L150; engine/data.py:L141 (verified) |
| Preprocessing | Load UCI dataset (official ucimlrepo client with validation of shape, missing values and default rate, or Excel workbook with header=1), Rename 'default payment next month' to 'default.payment.next.month' and drop ID (workbook path), Drop rows with missing values (workbook path), Cast target to int, Stratified train/test split with test_size=0.2 and random_state=42, Remove ID, SEX and AGE from predictors, No scaling applied to random forest inputs | engine/data.py:L37-43; engine/data.py:L74; engine/data.py:L143-145; engine/models.py:L71 (verified) |
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
| random_forest_shap.n_rows | 500 | reports/validation/validation_results.json#explainability.random_forest_shap.n_rows |
| random_forest_shap.mean_abs_shap.LIMIT_BAL | 0.0328 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.LIMIT_BAL |
| random_forest_shap.mean_abs_shap.EDUCATION | 0.0046 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.EDUCATION |
| random_forest_shap.mean_abs_shap.MARRIAGE | 0.0056 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.MARRIAGE |
| random_forest_shap.mean_abs_shap.PAY_0 | 0.0797 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_0 |
| random_forest_shap.mean_abs_shap.PAY_2 | 0.0388 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_2 |
| random_forest_shap.mean_abs_shap.PAY_3 | 0.0238 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_3 |
| random_forest_shap.mean_abs_shap.PAY_4 | 0.0171 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_4 |
| random_forest_shap.mean_abs_shap.PAY_5 | 0.0149 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_5 |
| random_forest_shap.mean_abs_shap.PAY_6 | 0.0121 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_6 |
| random_forest_shap.mean_abs_shap.BILL_AMT1 | 0.0188 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT1 |
| random_forest_shap.mean_abs_shap.BILL_AMT2 | 0.0138 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT2 |
| random_forest_shap.mean_abs_shap.BILL_AMT3 | 0.0119 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT3 |
| random_forest_shap.mean_abs_shap.BILL_AMT4 | 0.0107 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT4 |
| random_forest_shap.mean_abs_shap.BILL_AMT5 | 0.0107 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT5 |
| random_forest_shap.mean_abs_shap.BILL_AMT6 | 0.0114 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.BILL_AMT6 |
| random_forest_shap.mean_abs_shap.PAY_AMT1 | 0.02 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT1 |
| random_forest_shap.mean_abs_shap.PAY_AMT2 | 0.0192 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT2 |
| random_forest_shap.mean_abs_shap.PAY_AMT3 | 0.0188 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT3 |
| random_forest_shap.mean_abs_shap.PAY_AMT4 | 0.0129 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT4 |
| random_forest_shap.mean_abs_shap.PAY_AMT5 | 0.0118 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT5 |
| random_forest_shap.mean_abs_shap.PAY_AMT6 | 0.0135 | reports/validation/validation_results.json#explainability.random_forest_shap.mean_abs_shap.PAY_AMT6 |

## Limitations and assumptions

Hyperparameters other than n_estimators and class_weight use library defaults, no tuning is shown, and the selection rationale is not documented. The feature set depends on which loader is used (the demo fixture yields only three predictors), and the loader used in production is not documented. The UCI data is public demonstration data and not representative of a UK bank's current portfolio. Performance metrics, validation results, fairness results for SEX and AGE groups, prediction PSI, the approved decision threshold and its justification, and a monitoring plan are all not documented.

## Risk tier, approval and governance

| Item | Value | Evidence |
|---|---|---|
| Risk tier | Tier 3 | inventory (computed by rule) |
| Materiality | low: internal benchmark only, not used in decisions | inventory |
| Complexity | medium: bagged tree ensemble with standard settings | inventory |
| Tier rule | Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | SS1/23 1.3 |
| Tier rationale | Tier 3: materiality is low (internal benchmark only, not used in decisions) and complexity is medium (bagged tree ensemble with standard settings). Rule: Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | rule_template |
| Tier review status | not_started | inventory |
| Approval records | None recorded | governance/approval_log.json |
| Discovery report status | pending_human_review | reports/discovery/python-random-forest_discovery.json |
| Model card status | pending_human_review | this card |
| SS1/23 principles covered | 1. Model identification and model risk classification; 1.2 Model inventory; 1.3 Model tiering; 3. Model development, implementation and use; 3.5 Model development documentation | governance/ss1_23_mapping.json |

## Corrections to the existing model document

No existing model document was compared.

## Grounding warnings

- limitations: the draft mentions approval or validation but none is recorded; check the wording.
