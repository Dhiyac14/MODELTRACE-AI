# Model card: Legacy R Logistic Regression (legacy-r-logistic)

Version 1.0.0 · Risk tier 1 · Review status: **pending_human_review**  
Generated 2026-11-12T22:48:40+00:00 by Documentation Agent (LLM: claude-opus-5-5)

> Draft for human review. Figures are copied from the cited files; no approval is implied.

## Model overview and intended purpose

Legacy R Logistic Regression (legacy-r-logistic) estimates the probability that a credit-card customer defaults next month and is described as being used in credit decisions; it carries risk tier 1. The model name and business purpose are inferred rather than confirmed, and the business owner, intended use and decision context of the legacy production model are not documented. It is built on the public UCI Default of Credit Card Clients dataset (30,000 records, Taiwan, April to September 2005), which is described as demonstration data only and not representative of a UK bank's current portfolio.

## Dataset and data provenance

| Item | Value | Evidence |
|---|---|---|
| Dataset | Default of Credit Card Clients (UCI Machine Learning Repository) | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Records | 30,000 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Input variables | 23 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Origin | Credit-card clients in Taiwan, payment history April to September 2005 | UCI dataset description, https://archive.ics.uci.edu/dataset/350 |
| Intended use here | Public demonstration data only; not representative of a UK bank's current portfolio | Project plan, step 2 |

## Algorithm and methodology

The model is a logistic regression fitted in R using glm with a binomial family and logit link, with the target column holding default.payment.next.month. Predictors are all columns in train.csv except row_id, target, SEX, AGE and ID (LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0 to PAY_6, BILL_AMT1 to BILL_AMT6 and PAY_AMT1 to PAY_AMT6), used without transformation, scaling or encoding. Data come from an upstream stratified split (seed 42, inferred 0.8/0.2 train/test) with a hard-coded classification threshold of 0.35, although the actual split used at the call site is not documented. A parity check of R predictions against statsmodels is recorded as passing at a tolerance of 1e-05.

## Input features and target

| Item | Value | Evidence |
|---|---|---|
| Target variable | target (holds default.payment.next.month) | models/legacy_model.R:L20; engine/data.py:L165; engine/data.py:L142 (inferred) |
| Input features (21) | LIMIT_BAL, EDUCATION, MARRIAGE, PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6, PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6 | models/legacy_model.R:L19; engine/data.py:L58-63 (inferred) |
| Excluded columns | row_id, target, SEX, AGE, ID | models/legacy_model.R:L19 (verified) |
| Preprocessing | Read train/test CSVs with read.csv(check.names = FALSE), Validate that train contains target and test contains row_id, Exclude row_id, target, SEX, AGE, ID from predictors, Build formula target ~ all remaining columns (no transformations, scaling or encoding), Upstream: stratified train/test split with seed 42 and row_id insertion via write_shared_split | models/legacy_model.R:L13-17; models/legacy_model.R:L19-20; engine/data.py:L143-145 (inferred) |
| Train/test split | 80% train / 20% test | engine/data.py:L135-137 (inferred) |
| Decision threshold | 0.35 | models/legacy_model.R:L23-24 (verified) |

## Performance metrics

| Item | Value | Evidence |
|---|---|---|
| accuracy | 0.809 | reports/validation/validation_results.json#metrics.accuracy |
| precision | 0.6938 | reports/validation/validation_results.json#metrics.precision |
| recall | 0.2442 | reports/validation/validation_results.json#metrics.recall |
| f1 | 0.3612 | reports/validation/validation_results.json#metrics.f1 |
| roc_auc | 0.707 | reports/validation/validation_results.json#metrics.roc_auc |
| pr_auc | 0.4954 | reports/validation/validation_results.json#metrics.pr_auc |
| brier | 0.1467 | reports/validation/validation_results.json#metrics.brier |
| specificity | 0.9694 | reports/validation/validation_results.json#metrics.specificity |

## Fairness considerations

| Item | Value | Evidence |
|---|---|---|
| sex.by_group.1.count | 2402 | reports/validation/validation_results.json#fairness.sex.by_group.1.count |
| sex.by_group.1.selection_rate | 0.0824 | reports/validation/validation_results.json#fairness.sex.by_group.1.selection_rate |
| sex.by_group.1.true_positive_rate | 0.2406 | reports/validation/validation_results.json#fairness.sex.by_group.1.true_positive_rate |
| sex.by_group.1.false_positive_rate | 0.0342 | reports/validation/validation_results.json#fairness.sex.by_group.1.false_positive_rate |
| sex.by_group.2.count | 3598 | reports/validation/validation_results.json#fairness.sex.by_group.2.count |
| sex.by_group.2.selection_rate | 0.0748 | reports/validation/validation_results.json#fairness.sex.by_group.2.selection_rate |
| sex.by_group.2.true_positive_rate | 0.2467 | reports/validation/validation_results.json#fairness.sex.by_group.2.true_positive_rate |
| sex.by_group.2.false_positive_rate | 0.0282 | reports/validation/validation_results.json#fairness.sex.by_group.2.false_positive_rate |
| sex.demographic_parity_difference | 0.0077 | reports/validation/validation_results.json#fairness.sex.demographic_parity_difference |
| sex.disparate_impact | 0.907 | reports/validation/validation_results.json#fairness.sex.disparate_impact |
| age_groups.by_group.30_44.count | 3002 | reports/validation/validation_results.json#fairness.age_groups.by_group.30_44.count |
| age_groups.by_group.30_44.selection_rate | 0.071 | reports/validation/validation_results.json#fairness.age_groups.by_group.30_44.selection_rate |
| age_groups.by_group.30_44.true_positive_rate | 0.2334 | reports/validation/validation_results.json#fairness.age_groups.by_group.30_44.true_positive_rate |
| age_groups.by_group.30_44.false_positive_rate | 0.0274 | reports/validation/validation_results.json#fairness.age_groups.by_group.30_44.false_positive_rate |
| age_groups.by_group.45_59.count | 1010 | reports/validation/validation_results.json#fairness.age_groups.by_group.45_59.count |
| age_groups.by_group.45_59.selection_rate | 0.0842 | reports/validation/validation_results.json#fairness.age_groups.by_group.45_59.selection_rate |
| age_groups.by_group.45_59.true_positive_rate | 0.2469 | reports/validation/validation_results.json#fairness.age_groups.by_group.45_59.true_positive_rate |
| age_groups.by_group.45_59.false_positive_rate | 0.0326 | reports/validation/validation_results.json#fairness.age_groups.by_group.45_59.false_positive_rate |
| age_groups.by_group.60_plus.count | 76 | reports/validation/validation_results.json#fairness.age_groups.by_group.60_plus.count |
| age_groups.by_group.60_plus.selection_rate | 0.0658 | reports/validation/validation_results.json#fairness.age_groups.by_group.60_plus.selection_rate |
| age_groups.by_group.60_plus.true_positive_rate | 0.1304 | reports/validation/validation_results.json#fairness.age_groups.by_group.60_plus.true_positive_rate |
| age_groups.by_group.60_plus.false_positive_rate | 0.0377 | reports/validation/validation_results.json#fairness.age_groups.by_group.60_plus.false_positive_rate |
| age_groups.by_group.under_30.count | 1912 | reports/validation/validation_results.json#fairness.age_groups.by_group.under_30.count |
| age_groups.by_group.under_30.selection_rate | 0.0858 | reports/validation/validation_results.json#fairness.age_groups.by_group.under_30.selection_rate |
| age_groups.by_group.under_30.true_positive_rate | 0.2646 | reports/validation/validation_results.json#fairness.age_groups.by_group.under_30.true_positive_rate |
| age_groups.by_group.under_30.false_positive_rate | 0.0343 | reports/validation/validation_results.json#fairness.age_groups.by_group.under_30.false_positive_rate |
| age_groups.demographic_parity_difference | 0.02 | reports/validation/validation_results.json#fairness.age_groups.demographic_parity_difference |
| age_groups.disparate_impact | 0.767 | reports/validation/validation_results.json#fairness.age_groups.disparate_impact |

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

## Redevelopment and parity

| Item | Value | Evidence |
|---|---|---|
| reference_model | r_glm_binomial_logit | reports/migration/migration_results.json#parity.reference_model |
| candidate_model | statsmodels_logistic_regression | reports/migration/migration_results.json#parity.candidate_model |
| model_hash | 43afdbfaef44dd0093f0efdacf0c90b1266681e64d116452f189c184042ecfa0 | reports/migration/migration_results.json#parity.model_hash |
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
| r_vs_statsmodels.threshold | 0.5 | reports/migration/migration_results.json#parity.r_vs_statsmodels.threshold |
| r_vs_statsmodels.mae_pass | True | reports/migration/migration_results.json#parity.r_vs_statsmodels.mae_pass |
| r_vs_statsmodels.max_difference_pass | True | reports/migration/migration_results.json#parity.r_vs_statsmodels.max_difference_pass |
| r_vs_statsmodels.overall_pass | True | reports/migration/migration_results.json#parity.r_vs_statsmodels.overall_pass |
| r_vs_python.label_agreement | 1.0 | reports/migration/migration_results.json#parity.r_vs_python.label_agreement |
| r_vs_python.label_disagreements | 0 | reports/migration/migration_results.json#parity.r_vs_python.label_disagreements |
| r_vs_python.max_probability_difference | 0.0074 | reports/migration/migration_results.json#parity.r_vs_python.max_probability_difference |
| r_vs_python.mean_probability_difference | 2.339e-04 | reports/migration/migration_results.json#parity.r_vs_python.mean_probability_difference |
| shared_train_csv | data/processed/train.csv | reports/migration/migration_results.json#parity.shared_train_csv |
| shared_test_csv | data/processed/test.csv | reports/migration/migration_results.json#parity.shared_test_csv |
| r_script | models/legacy_model.R | reports/migration/migration_results.json#parity.r_script |
| r_stderr_warning | None | reports/migration/migration_results.json#parity.r_stderr_warning |

## Limitations and assumptions

The feature set is not fixed and depends on whatever columns are in train.csv, so a schema change would silently change the model; there is also no missing-value handling, regularisation, scaling or interaction terms, and the fitted model is not saved. Log-odds are assumed linear in raw values, and categorical-coded columns (EDUCATION, MARRIAGE, PAY_*) are treated as numeric unless read as factors, with their intended treatment not documented. The 0.35 threshold has no documented rationale; validation metrics (e.g. accuracy 0.809 but low recall) and fairness metrics for sex and age groups are recorded, yet performance and fairness evaluation are also listed as missing information, so their status needs reviewer clarification. Model version, deployment details, monitoring plan and retraining frequency are not documented.

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

Compared with models/outdated_model_document.md.

| Item | Value | Evidence |
|---|---|---|
| D-001 input_features (contradiction) | Document: SEX is a model input. Correction: Remove SEX from the documented input features. | models/legacy_model.R:L19 |
| D-002 decision_threshold (contradiction) | Document: The decision threshold is 0.4. Correction: Change the documented decision threshold to 0.35. | models/legacy_model.R:L23-24 |
| D-003 train_test_split (contradiction) | Document: The train/test split is 75% train / 25% test. Correction: Change the documented train/test split to 80% train / 20% test. | engine/data.py:L135-137 |
| D-004 model_name (unverifiable) | Document: The model is called the Legacy credit default model. Correction:  | models/legacy_model.R:L3 |
| D-005 target_variable (contradiction) | Document: The target variable is default. Correction: The target variable is 'target', a binary 0/1 indicator taken from the UCI column 'default.payment.next.month' (default payment next month). | models/legacy_model.R:L20; engine/data.py:L19; engine/data.py:L165 |
| D-006 preprocessing (contradiction) | Document: All numeric predictors are standardized to zero mean and unit variance before fitting. Correction: Predictors are used in their raw form; no standardization or scaling is applied before fitting. | models/legacy_model.R:L19-21 |
| D-007 preprocessing (omission) | Document: Not mentioned in the document. Correction: State that all predictor columns, including integer-coded categorical fields, enter the GLM as numeric terms without factor encoding or scaling. | models/legacy_model.R:L19-21 |
| D-008 other (omission) | Document: Not mentioned in the document. Correction: Document that the UCI dataset 350 is validated for 30,000 rows and 25 columns, no missing values, and a default rate of 20–24% before splitting, and that provenance is recorded. | engine/data.py:L109-114 |
| D-009 limitations (omission) | Document: Not mentioned in the document. Correction: Note that a synthetic 1,200-row demo dataset may be used when the UCI data is unavailable, and that results from it are not representative. | engine/data.py:L118-119 |
