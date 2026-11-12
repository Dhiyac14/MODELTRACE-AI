#!/usr/bin/env Rscript

# Reference implementation for the legacy production model.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3) {
  stop("Usage: Rscript legacy_model.R <train.csv> <test.csv> <predictions.csv>")
}

train_path <- args[[1]]
test_path <- args[[2]]
output_path <- args[[3]]

train <- read.csv(train_path, check.names = FALSE)
test <- read.csv(test_path, check.names = FALSE)
if (!"target" %in% names(train) || !"row_id" %in% names(test)) {
  stop("Train data must contain target and test data must contain row_id")
}

feature_names <- setdiff(names(train), c("row_id", "target", "SEX", "AGE", "ID"))
formula <- reformulate(feature_names, response = "target")
legacy_model <- glm(formula, data = train, family = binomial(link = "logit"))
probability <- as.numeric(predict(legacy_model, newdata = test, type = "response"))
prediction <- as.integer(probability >= 0.5)

write.csv(
  data.frame(row_id = test$row_id, probability = probability, prediction = prediction),
  output_path,
  row.names = FALSE
)
