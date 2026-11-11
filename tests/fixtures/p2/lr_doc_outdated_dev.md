# Credit Default Scorecard: Model Document

DEV FIXTURE (Person 2). Not the answer-key document written by Person 1.

Version 1.2, last updated March 2021.

## Purpose
The model estimates the probability that a credit-card customer defaults on next month's payment.
Accounts above the cut-off are referred for manual review.

## Data and sampling
The data is split 75/25 into training and test sets.

## Input variables
LIMIT_BAL, SEX, EDUCATION, MARRIAGE, PAY_0, PAY_2 to PAY_6, BILL_AMT1 to BILL_AMT6, PAY_AMT1 to PAY_AMT3.

LIMIT_BAL is log-transformed before fitting.

## Method
Logistic regression fitted by maximum likelihood.

## Decision rule
Accounts with a predicted default probability above 0.40 are referred.

## Governance
Model owner: Retail Credit Analytics.
The model was approved by the Credit Risk Committee in March 2021.
