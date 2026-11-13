# Model card: Legacy R Logistic Regression (legacy-r-logistic)

Version 1.0.0 · Risk tier 1 · Review status: **pending_human_review**  
Generated 2026-11-13T13:45:37+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

Legacy R Logistic Regression (legacy-r-logistic) estimates the probability that a credit-card customer defaults next month and is described as being used in credit decisions; this purpose was inferred rather than confirmed, and the business owner, intended use and decision context are not documented. The model is assigned risk tier 1. It was developed on the public UCI Default of Credit Card Clients dataset (30,000 records, Taiwan, April to September 2005). That data is for demonstration only and is not representative of a UK bank's current portfolio.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a logistic regression fitted in R with glm (binomial family, logit link). It uses 21 inputs: LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0 and PAY_2 to PAY_6, BILL_AMT1 to BILL_AMT6, and PAY_AMT1 to PAY_AMT6. SEX, AGE, ID and row_id are excluded from the predictors, and the target is default.payment.next.month. Upstream Python code makes a stratified 80/20 train/test split (random_state=42), and a hard-coded threshold of 0.35 converts probabilities to classes. The reported test results are accuracy 0.807, ROC AUC 0.707, precision 0.592 and recall 0.412, and the R predictions match a statsmodels reimplementation within a 1e-05 tolerance (100% classification agreement).

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | target (holds default.payment.next.month) | models/legacy_model.R:L20; engine/data.py:L165; engine/data.py:L142 (inferred) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | models/legacy_model.R:L19; engine/data.py:L59; engine/data.py:L60; engine/data.py:L61; engine/data.py:L62 (inferred) |
| Excluded columns | row_id, target, SEX, AGE, ID | models/legacy_model.R:L19 (verified) |
| Preprocessing | Read train and test CSV files with check.names = FALSE (no column-name mangling), Validate that train contains target and test contains row_id, Exclude row_id, target, SEX, AGE, ID from predictors, Upstream (Python): target cast to integer and stratified train/test split with random_state=42, Upstream (Python): row_id inserted from the dataframe index before writing train.csv/test.csv, Upstream (Python, Excel path only): ID dropped and rows with missing values removed | models/legacy_model.R:L13; models/legacy_model.R:L15; engine/data.py:L143-145; engine/data.py:L164; engine/data.py:L43 (inferred) |
| Train/test split | 80% train / 20% test | engine/data.py:L136 (inferred) |
| Decision threshold | 0.35 | models/legacy_model.R:L23-24 (verified) |

## Performance metrics

| Item | Value | Evidence |
|---|---|---|
| accuracy | 0.8072 | reports/validation/validation_results.json#metrics.accuracy |
| precision | 0.592 | reports/validation/validation_results.json#metrics.precision |
| recall | 0.4122 | reports/validation/validation_results.json#metrics.recall |
| f1 | 0.486 | reports/validation/validation_results.json#metrics.f1 |
| roc_auc | 0.707 | reports/validation/validation_results.json#metrics.roc_auc |
| pr_auc | 0.4954 | reports/validation/validation_results.json#metrics.pr_auc |
| brier | 0.1467 | reports/validation/validation_results.json#metrics.brier |
| specificity | 0.9193 | reports/validation/validation_results.json#metrics.specificity |

## Fairness considerations

| Item | Value | Evidence |
|---|---|---|
| sex.by_group.1.count | 2402 | reports/validation/validation_results.json#fairness.sex.by_group.1.count |
| sex.by_group.1.selection_rate | 0.1636 | reports/validation/validation_results.json#fairness.sex.by_group.1.selection_rate |
| sex.by_group.1.true_positive_rate | 0.41 | reports/validation/validation_results.json#fairness.sex.by_group.1.true_positive_rate |
| sex.by_group.1.false_positive_rate | 0.0885 | reports/validation/validation_results.json#fairness.sex.by_group.1.false_positive_rate |
| sex.by_group.2.count | 3598 | reports/validation/validation_results.json#fairness.sex.by_group.2.count |
| sex.by_group.2.selection_rate | 0.1476 | reports/validation/validation_results.json#fairness.sex.by_group.2.selection_rate |
| sex.by_group.2.true_positive_rate | 0.4138 | reports/validation/validation_results.json#fairness.sex.by_group.2.true_positive_rate |
| sex.by_group.2.false_positive_rate | 0.0756 | reports/validation/validation_results.json#fairness.sex.by_group.2.false_positive_rate |
| sex.demographic_parity_difference | 0.016 | reports/validation/validation_results.json#fairness.sex.demographic_parity_difference |
| sex.disparate_impact | 0.902 | reports/validation/validation_results.json#fairness.sex.disparate_impact |
| age_groups.by_group.30_44.count | 3002 | reports/validation/validation_results.json#fairness.age_groups.by_group.30_44.count |
| age_groups.by_group.30_44.selection_rate | 0.1366 | reports/validation/validation_results.json#fairness.age_groups.by_group.30_44.selection_rate |
| age_groups.by_group.30_44.true_positive_rate | 0.3833 | reports/validation/validation_results.json#fairness.age_groups.by_group.30_44.true_positive_rate |
| age_groups.by_group.30_44.false_positive_rate | 0.0705 | reports/validation/validation_results.json#fairness.age_groups.by_group.30_44.false_positive_rate |
| age_groups.by_group.45_59.count | 1010 | reports/validation/validation_results.json#fairness.age_groups.by_group.45_59.count |
| age_groups.by_group.45_59.selection_rate | 0.1584 | reports/validation/validation_results.json#fairness.age_groups.by_group.45_59.selection_rate |
| age_groups.by_group.45_59.true_positive_rate | 0.3951 | reports/validation/validation_results.json#fairness.age_groups.by_group.45_59.true_positive_rate |
| age_groups.by_group.45_59.false_positive_rate | 0.0834 | reports/validation/validation_results.json#fairness.age_groups.by_group.45_59.false_positive_rate |
| age_groups.by_group.60_plus.count | 76 | reports/validation/validation_results.json#fairness.age_groups.by_group.60_plus.count |
| age_groups.by_group.60_plus.selection_rate | 0.1711 | reports/validation/validation_results.json#fairness.age_groups.by_group.60_plus.selection_rate |
| age_groups.by_group.60_plus.true_positive_rate | 0.3478 | reports/validation/validation_results.json#fairness.age_groups.by_group.60_plus.true_positive_rate |
| age_groups.by_group.60_plus.false_positive_rate | 0.0943 | reports/validation/validation_results.json#fairness.age_groups.by_group.60_plus.false_positive_rate |
| age_groups.by_group.under_30.count | 1912 | reports/validation/validation_results.json#fairness.age_groups.by_group.under_30.count |
| age_groups.by_group.under_30.selection_rate | 0.1783 | reports/validation/validation_results.json#fairness.age_groups.by_group.under_30.selection_rate |
| age_groups.by_group.under_30.true_positive_rate | 0.4684 | reports/validation/validation_results.json#fairness.age_groups.by_group.under_30.true_positive_rate |
| age_groups.by_group.under_30.false_positive_rate | 0.0949 | reports/validation/validation_results.json#fairness.age_groups.by_group.under_30.false_positive_rate |
| age_groups.demographic_parity_difference | 0.0418 | reports/validation/validation_results.json#fairness.age_groups.demographic_parity_difference |
| age_groups.disparate_impact | 0.7658 | reports/validation/validation_results.json#fairness.age_groups.disparate_impact |

## Stability

| Item | Value | Evidence |
|---|---|---|
| feature_psi.LIMIT_BAL | 0.0016 | reports/validation/validation_results.json#stability.feature_psi.LIMIT_BAL |
| feature_psi.EDUCATION | 2.782e-04 | reports/validation/validation_results.json#stability.feature_psi.EDUCATION |
| feature_psi.MARRIAGE | 6.067e-04 | reports/validation/validation_results.json#stability.feature_psi.MARRIAGE |
| feature_psi.PAY_0 | 0.0011 | reports/validation/validation_results.json#stability.feature_psi.PAY_0 |
| feature_psi.PAY_2 | 1.819e-05 | reports/validation/validation_results.json#stability.feature_psi.PAY_2 |
| feature_psi.PAY_3 | 1.435e-04 | reports/validation/validation_results.json#stability.feature_psi.PAY_3 |
| feature_psi.PAY_4 | 1.055e-04 | reports/validation/validation_results.json#stability.feature_psi.PAY_4 |
| feature_psi.PAY_5 | 1.938e-04 | reports/validation/validation_results.json#stability.feature_psi.PAY_5 |
| feature_psi.PAY_6 | 3.236e-04 | reports/validation/validation_results.json#stability.feature_psi.PAY_6 |
| feature_psi.BILL_AMT1 | 0.0021 | reports/validation/validation_results.json#stability.feature_psi.BILL_AMT1 |
| feature_psi.BILL_AMT2 | 0.0011 | reports/validation/validation_results.json#stability.feature_psi.BILL_AMT2 |
| feature_psi.BILL_AMT3 | 0.0013 | reports/validation/validation_results.json#stability.feature_psi.BILL_AMT3 |
| feature_psi.BILL_AMT4 | 0.0027 | reports/validation/validation_results.json#stability.feature_psi.BILL_AMT4 |
| feature_psi.BILL_AMT5 | 9.006e-04 | reports/validation/validation_results.json#stability.feature_psi.BILL_AMT5 |
| feature_psi.BILL_AMT6 | 3.943e-04 | reports/validation/validation_results.json#stability.feature_psi.BILL_AMT6 |
| feature_psi.PAY_AMT1 | 0.0022 | reports/validation/validation_results.json#stability.feature_psi.PAY_AMT1 |
| feature_psi.PAY_AMT2 | 0.0011 | reports/validation/validation_results.json#stability.feature_psi.PAY_AMT2 |
| feature_psi.PAY_AMT3 | 5.669e-04 | reports/validation/validation_results.json#stability.feature_psi.PAY_AMT3 |
| feature_psi.PAY_AMT4 | 0.0011 | reports/validation/validation_results.json#stability.feature_psi.PAY_AMT4 |
| feature_psi.PAY_AMT5 | 0.0011 | reports/validation/validation_results.json#stability.feature_psi.PAY_AMT5 |
| feature_psi.PAY_AMT6 | 7.413e-04 | reports/validation/validation_results.json#stability.feature_psi.PAY_AMT6 |
| prediction_psi | 3.136e-04 | reports/validation/validation_results.json#stability.prediction_psi |

## Explainability

| Item | Value | Evidence |
|---|---|---|
| coefficients.LIMIT_BAL | -9.684e-07 | reports/validation/validation_results.json#explainability.coefficients.LIMIT_BAL |
| coefficients.EDUCATION | -0.1079 | reports/validation/validation_results.json#explainability.coefficients.EDUCATION |
| coefficients.MARRIAGE | -0.19 | reports/validation/validation_results.json#explainability.coefficients.MARRIAGE |
| coefficients.PAY_0 | 0.5888 | reports/validation/validation_results.json#explainability.coefficients.PAY_0 |
| coefficients.PAY_2 | 0.078 | reports/validation/validation_results.json#explainability.coefficients.PAY_2 |
| coefficients.PAY_3 | 0.0816 | reports/validation/validation_results.json#explainability.coefficients.PAY_3 |
| coefficients.PAY_4 | 0.0538 | reports/validation/validation_results.json#explainability.coefficients.PAY_4 |
| coefficients.PAY_5 | -0.0012 | reports/validation/validation_results.json#explainability.coefficients.PAY_5 |
| coefficients.PAY_6 | 0.0144 | reports/validation/validation_results.json#explainability.coefficients.PAY_6 |
| coefficients.BILL_AMT1 | -4.351e-06 | reports/validation/validation_results.json#explainability.coefficients.BILL_AMT1 |
| coefficients.BILL_AMT2 | 1.544e-06 | reports/validation/validation_results.json#explainability.coefficients.BILL_AMT2 |
| coefficients.BILL_AMT3 | 4.990e-07 | reports/validation/validation_results.json#explainability.coefficients.BILL_AMT3 |
| coefficients.BILL_AMT4 | 7.187e-07 | reports/validation/validation_results.json#explainability.coefficients.BILL_AMT4 |
| coefficients.BILL_AMT5 | 4.405e-07 | reports/validation/validation_results.json#explainability.coefficients.BILL_AMT5 |
| coefficients.BILL_AMT6 | -1.014e-07 | reports/validation/validation_results.json#explainability.coefficients.BILL_AMT6 |
| coefficients.PAY_AMT1 | -1.252e-05 | reports/validation/validation_results.json#explainability.coefficients.PAY_AMT1 |
| coefficients.PAY_AMT2 | -8.790e-06 | reports/validation/validation_results.json#explainability.coefficients.PAY_AMT2 |
| coefficients.PAY_AMT3 | -1.899e-06 | reports/validation/validation_results.json#explainability.coefficients.PAY_AMT3 |
| coefficients.PAY_AMT4 | -2.480e-06 | reports/validation/validation_results.json#explainability.coefficients.PAY_AMT4 |
| coefficients.PAY_AMT5 | -1.455e-06 | reports/validation/validation_results.json#explainability.coefficients.PAY_AMT5 |
| coefficients.PAY_AMT6 | -1.713e-06 | reports/validation/validation_results.json#explainability.coefficients.PAY_AMT6 |

## Redevelopment and parity

| Item | Value | Evidence |
|---|---|---|
| reference_model | r_glm_binomial_logit | reports/migration/migration_results.json#parity.reference_model |
| candidate_model | statsmodels_logistic_regression | reports/migration/migration_results.json#parity.candidate_model |
| model_hash | f88138e5870d139409a76918ee9568aade8e84166629b1d1c3e5e6a793e8672f | reports/migration/migration_results.json#parity.model_hash |
| n_rows | 6000 | reports/migration/migration_results.json#parity.n_rows |
| r_vs_statsmodels.row_alignment_verified | True | reports/migration/migration_results.json#parity.r_vs_statsmodels.row_alignment_verified |
| r_vs_statsmodels.mae | 9.443e-09 | reports/migration/migration_results.json#parity.r_vs_statsmodels.mae |
| r_vs_statsmodels.mean_probability_difference | 9.443e-09 | reports/migration/migration_results.json#parity.r_vs_statsmodels.mean_probability_difference |
| r_vs_statsmodels.max_probability_difference | 3.646e-07 | reports/migration/migration_results.json#parity.r_vs_statsmodels.max_probability_difference |
| r_vs_statsmodels.prediction_correlation | 1.0 | reports/migration/migration_results.json#parity.r_vs_statsmodels.prediction_correlation |
| r_vs_statsmodels.classification_agreement | 1.0 | reports/migration/migration_results.json#parity.r_vs_statsmodels.classification_agreement |
| r_vs_statsmodels.label_agreement | 1.0 | reports/migration/migration_results.json#parity.r_vs_statsmodels.label_agreement |
| r_vs_statsmodels.label_disagreements | 0 | reports/migration/migration_results.json#parity.r_vs_statsmodels.label_disagreements |
| r_vs_statsmodels.tolerance | 1.000e-05 | reports/migration/migration_results.json#parity.r_vs_statsmodels.tolerance |
| r_vs_statsmodels.threshold | 0.35 | reports/migration/migration_results.json#parity.r_vs_statsmodels.threshold |
| r_vs_statsmodels.mae_pass | True | reports/migration/migration_results.json#parity.r_vs_statsmodels.mae_pass |
| r_vs_statsmodels.max_difference_pass | True | reports/migration/migration_results.json#parity.r_vs_statsmodels.max_difference_pass |
| r_vs_statsmodels.labels_pass | True | reports/migration/migration_results.json#parity.r_vs_statsmodels.labels_pass |
| r_vs_statsmodels.overall_pass | True | reports/migration/migration_results.json#parity.r_vs_statsmodels.overall_pass |
| r_vs_python.label_agreement | 0.9998 | reports/migration/migration_results.json#parity.r_vs_python.label_agreement |
| r_vs_python.label_disagreements | 1 | reports/migration/migration_results.json#parity.r_vs_python.label_disagreements |
| r_vs_python.max_probability_difference | 0.0074 | reports/migration/migration_results.json#parity.r_vs_python.max_probability_difference |
| r_vs_python.mean_probability_difference | 2.339e-04 | reports/migration/migration_results.json#parity.r_vs_python.mean_probability_difference |
| shared_train_csv | data/processed/train.csv | reports/migration/migration_results.json#parity.shared_train_csv |
| shared_test_csv | data/processed/test.csv | reports/migration/migration_results.json#parity.shared_test_csv |
| r_script | models/legacy_model.R | reports/migration/migration_results.json#parity.r_script |
| r_stderr_warning | None | reports/migration/migration_results.json#parity.r_stderr_warning |

## Limitations and assumptions

The model assumes log-odds are linear and additive in the predictors and treats coded categorical variables (EDUCATION, MARRIAGE, PAY_*) as numeric. It has no regularization, feature scaling, missing-value handling or convergence checks, the fitted model object is not saved, and the feature set depends on the columns in the upstream train.csv. The rationale for the 0.35 threshold, the acceptance criteria, the fitted coefficients and their stability, the monitoring and retraining plan, the R environment, and which dataset produced the input files are not documented. Although SEX and AGE are excluded, the reported disparate impact across age groups is 0.766 (0.902 for sex); there is no documented interpretation of these figures, and several facts, including the target, features, preprocessing and split fraction, were inferred rather than confirmed.

## Risk tier, approval and governance

| Item | Value | Evidence |
|---|---|---|
| Risk tier | Tier 1 | inventory (computed by rule) |
| Materiality | high: drives credit decisions for customers | inventory |
| Complexity | low: linear model with a small set of documented predictors | inventory |
| Tier rule | Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | SS1/23 1.3 |
| Tier rationale | Tier 1: materiality is high (drives credit decisions for customers) and complexity is low (linear model with a small set of documented predictors). Rule: Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3. | rule_template |
| Discover gate (tier and discovery report) | not_started | governance/approval_log.json |
| Approval records | None recorded | governance/approval_log.json |
| Model card status | pending_human_review | this card |
| SS1/23 principles covered | 1. Model identification and model risk classification; 1.2 Model inventory; 1.3 Model tiering; 3. Model development, implementation and use; 3.5 Model development documentation | governance/ss1_23_mapping.json |

## Corrections to the existing model document

Compared with models/outdated_model_document.md.

| Item | Value | Evidence |
|---|---|---|
| D-001 input_features (contradiction) | Document: SEX is a model input. Correction: Remove SEX from the documented input features. | models/legacy_model.R:L19 |
| D-002 decision_threshold (contradiction) | Document: The decision threshold is 0.4. Correction: Change the documented decision threshold to 0.35. | models/legacy_model.R:L23-24 |
| D-003 train_test_split (contradiction) | Document: The train/test split is 75% train / 25% test. Correction: Change the documented train/test split to 80% train / 20% test. | engine/data.py:L136 |
| D-004 target_variable (contradiction) | Document: The target variable is `default`. Correction: The target variable is `target` in the shared training file. It holds the UCI column `default.payment.next.month` (default payment next month, binary). | models/legacy_model.R:L20; engine/data.py:L19; engine/data.py:L165 |
| D-005 preprocessing (contradiction) | Document: All numeric predictors are standardized to zero mean and unit variance before fitting. Correction: Predictors are not standardized. The glm is fitted directly on raw feature values from the shared training split, after dropping row_id, target, SEX, AGE and ID. | models/legacy_model.R:L19-21; engine/data.py:L163-165 |
| D-006 other (omission) | Document: Not mentioned in the document. Correction: State that the script requires a `target` column in the training CSV and a `row_id` column in the test CSV, and stops with an error otherwise. | models/legacy_model.R:L15-17 |
