# Legacy credit default model

This document describes the production batch classifier that estimates whether a
credit-card account will default. It is an R generalized linear model trained
on the shared training split and writes one probability and one binary
classification for each row in the test split.

- Model: binomial logistic regression trained with R `glm()` and a logit link.
- Target: `default`.
- Input features: `LIMIT_BAL`, `SEX`, `EDUCATION`, `MARRIAGE`, `PAY_0`, `PAY_2`,
  `PAY_3`, `PAY_4`, `PAY_5`, `PAY_6`, `BILL_AMT1`, `BILL_AMT2`,
  `BILL_AMT3`, `BILL_AMT4`, `BILL_AMT5`, `BILL_AMT6`, `PAY_AMT1`, `PAY_AMT2`,
  `PAY_AMT3`, `PAY_AMT4`, `PAY_AMT5`, and `PAY_AMT6`.
- Training split: 75% train and 25% test.
- Preprocessing: all numeric predictors are standardized to zero mean and unit
  variance before fitting.
- Classification threshold: 0.40; probabilities at or above this value are
  classified as defaults.

The model emits `row_id`, `probability`, and `prediction` columns in its CSV
output.
