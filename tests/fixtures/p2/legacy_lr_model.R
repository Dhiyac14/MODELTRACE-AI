# DEV FIXTURE (Person 2): stand-in for Person 1's R model, used only to develop the Discovery Agent.
# Fits a logistic regression on the processed training split and scores the test split.

library(readr)

train <- read_csv("data/processed/train.csv")
test  <- read_csv("data/processed/test.csv")

# ID is a row identifier; SEX and AGE are kept for fairness review only.
excluded <- c("ID", "SEX", "AGE")

model_formula <- default.payment.next.month ~ LIMIT_BAL + EDUCATION + MARRIAGE +
  PAY_0 + PAY_2 + PAY_3 + PAY_4 + PAY_5 + PAY_6 +
  BILL_AMT1 + BILL_AMT2 + BILL_AMT3 + BILL_AMT4 + BILL_AMT5 + BILL_AMT6 +
  PAY_AMT1 + PAY_AMT2 + PAY_AMT3 + PAY_AMT4 + PAY_AMT5 + PAY_AMT6

lr_model <- glm(model_formula, data = train, family = binomial(link = "logit"))

test$pd <- predict(lr_model, newdata = test, type = "response")

# Accounts with a predicted default probability above the cut-off are referred for review.
threshold <- 0.35
test$predicted_default <- as.integer(test$pd > threshold)

saveRDS(lr_model, "models/lr_model.rds")
write_csv(test[, c("ID", "pd", "predicted_default")], "reports/lr_test_predictions.csv")
