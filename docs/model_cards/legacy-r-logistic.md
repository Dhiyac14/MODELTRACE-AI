# Model card: Credit default logistic regression (legacy) (legacy-r-logistic)

Version 1.0.0 · Risk tier 1 · Review status: **pending_human_review**  
Generated 2026-11-11T22:52:25+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

legacy-r-logistic, recorded as 'Credit default logistic regression (legacy)', estimates the probability that a credit-card customer defaults in the next month and is described as being used in credit decisions; it is assigned risk tier 1. The model name, business purpose and train fraction are inferred fields, and the formal business purpose, intended use, portfolio scope, model owner and developer are not documented. The code is a development fixture standing in for the real model, not the production model, and it uses the public UCI 'Default of Credit Card Clients' dataset (30,000 records, 23 input variables, Taiwan credit-card clients, April to September 2005), which is described as demonstration data only and not representative of a UK bank's current portfolio.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a logistic regression implemented in R using glm with a binomial family and logit link, predicting default.payment.next.month from 21 input features: LIMIT_BAL, EDUCATION, MARRIAGE, the repayment status variables PAY_0 and PAY_2 to PAY_6, bill amounts BILL_AMT1 to BILL_AMT6, and payment amounts PAY_AMT1 to PAY_AMT6. ID, SEX and AGE are excluded from modelling, with SEX and AGE recorded as retained only for fairness review. Data is read from data/processed/credit_default_clean.csv and split into train and test sets with a stratified split on the target (test_size=0.2, random_state=42), giving an 80/20 split, and the R model applies no further transformation. A decision threshold of 0.35 is applied, but the rationale for this threshold is not documented.

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | default.payment.next.month | tests/fixtures/p2/legacy_lr_model.R:L12; tests/fixtures/p2/preprocessing_split.py:L5 (verified) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | tests/fixtures/p2/legacy_lr_model.R:L12-15 (verified) |
| Excluded columns | ID, SEX, AGE | tests/fixtures/p2/legacy_lr_model.R:L9-10 (verified) |
| Preprocessing | Read data/processed/credit_default_clean.csv, Stratified train/test split on target with test_size=0.2, random_state=42, Write train.csv and test.csv, R model reads processed train/test splits; no further transformation in model code | tests/fixtures/p2/preprocessing_split.py:L7-10 (verified) |
| Train/test split | 80% train / 20% test | tests/fixtures/p2/preprocessing_split.py:L8 (inferred) |
| Decision threshold | 0.35 | tests/fixtures/p2/legacy_lr_model.R:L22-23 (verified) |

## Performance metrics

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Fairness considerations

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Stability

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Explainability

_Pending: produced at the Validate stage. No figures are shown until the report exists._

## Limitations and assumptions

No validation metrics, calibration or threshold justification are computed, and no performance results, fairness review results for SEX and AGE, monitoring plan, or approval and version history are documented. EDUCATION, MARRIAGE and the PAY_x variables are assumed to enter the model as read by read_csv, likely as numeric rather than categorical, which may not reflect their nature. The data source, observation period, target definition details and the cleaning steps that produce credit_default_clean.csv are not documented. Because the code is a development fixture trained on public demonstration data, its outputs should not be taken as representative of the production model or of a UK bank's current portfolio.

## Risk tier, approval and governance

| Item | Value | Evidence |
|---|---|---|
| Risk tier | Tier 1 | inventory (computed by rule) |
| Materiality | high: drives credit decisions for customers | inventory |
| Complexity | low: linear model with a small set of documented predictors | inventory |
| Tier rule | Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | SS1/23 1.3 |
| Tier rationale | Tier 1: materiality is high (drives credit decisions for customers) and complexity is low (linear model with a small set of documented predictors). Rule: Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | rule_template |
| Tier review status | not_started | inventory |
| Approval records | None recorded | governance/approval_log.json |
| Discovery report status | pending_human_review | reports/discovery/legacy-r-logistic_discovery.json |
| Model card status | pending_human_review | this card |
| SS1/23 principles covered | 1. Model identification and model risk classification; 1.2 Model inventory; 1.3 Model tiering; 3. Model development, implementation and use; 3.5 Model development documentation | governance/ss1_23_mapping.json |

## Corrections to the existing model document

Compared with tests/fixtures/p2/lr_doc_outdated_dev.md.

| Item | Value | Evidence |
|---|---|---|
| D-001 input_features (contradiction) | Document: SEX is a model input. Correction: Remove SEX from the documented input features. | tests/fixtures/p2/legacy_lr_model.R:L9-10 |
| D-002 input_features (omission) | Document: The documented feature list leaves out PAY_AMT4, PAY_AMT5, PAY_AMT6. Correction: Add PAY_AMT4, PAY_AMT5, PAY_AMT6 to the documented input features. | tests/fixtures/p2/legacy_lr_model.R:L12-15 |
| D-003 decision_threshold (contradiction) | Document: The decision threshold is 0.4. Correction: Change the documented decision threshold to 0.35. | tests/fixtures/p2/legacy_lr_model.R:L22-23 |
| D-004 train_test_split (contradiction) | Document: The train/test split is 75% train / 25% test. Correction: Change the documented train/test split to 80% train / 20% test. | tests/fixtures/p2/preprocessing_split.py:L8 |
| D-005 model_name (unverifiable) | Document: The model is called the Credit Default Scorecard. Correction:  | no code evidence |
| D-006 other (unverifiable) | Document: The document is version 1.2, last updated March 2021. Correction:  | no code evidence |
| D-007 preprocessing (contradiction) | Document: LIMIT_BAL is log-transformed before fitting. Correction: LIMIT_BAL is used in its raw (untransformed) form in the model formula. | tests/fixtures/p2/legacy_lr_model.R:L12; tests/fixtures/p2/legacy_lr_model.R:L17 |
| D-008 ownership (unverifiable) | Document: The model owner is Retail Credit Analytics. Correction:  | no code evidence |
| D-009 validation_history (unverifiable) | Document: The model was approved by the Credit Risk Committee in March 2021. Correction:  | no code evidence |
| D-010 other (omission) | Document: Not mentioned in the document. Correction: State that the fitted model is saved to models/lr_model.rds. Test-set predictions (ID, pd, predicted_default) are written to reports/lr_test_predictions.csv. | tests/fixtures/p2/legacy_lr_model.R:L25-26 |
| D-011 other (omission) | Document: Not mentioned in the document. Correction: State that the model data comes from data/processed/credit_default_clean.csv. | tests/fixtures/p2/preprocessing_split.py:L7 |
