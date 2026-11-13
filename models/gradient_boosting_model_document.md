# Python Gradient Boosting model

This is the challenger model identified as `python-gradient-boosting`. It is
trained by `train_python_models` in `engine/models.py` with scikit-learn's
`GradientBoostingClassifier(random_state=42)`. The model uses the default
scikit-learn Gradient Boosting hyperparameters; no other estimator parameters
are set in the repository.

## Data and target

- The target is `default.payment.next.month`, represented as the integer target
  series returned by `prepare_data` in `engine/data.py`.
- `prepare_data` creates an 80% training / 20% test split using stratification
  and `random_state=42`.
- The predictors are the columns returned by `predictive_features`. `ID`,
  `SEX`, and `AGE` are excluded when present. For the official UCI dataset,
  the remaining predictors are `LIMIT_BAL`, `EDUCATION`, `MARRIAGE`, `PAY_0`,
  `PAY_2`, `PAY_3`, `PAY_4`, `PAY_5`, `PAY_6`, `BILL_AMT1` through `BILL_AMT6`,
  and `PAY_AMT1` through `PAY_AMT6`.

## Training and evaluation

The classifier is fitted directly on the selected training columns. The
Gradient Boosting path does not apply scaling, encoding, imputation, or another
preprocessing transformer in `engine/models.py`.

The pipeline trains this model as a supporting challenger. The validation
report produced by `engine/pipeline.py` evaluates the migrated Statsmodels
logistic model; it does not report Gradient Boosting performance metrics. SHAP
is an optional installation dependency, but it is required to complete the
real-data pipeline because `run_real` always computes Gradient Boosting SHAP
explainability and raises a runtime error when SHAP is unavailable. The
deterministic demo path does not invoke SHAP.
