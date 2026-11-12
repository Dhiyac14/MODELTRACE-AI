"""Fixed harness that runs one LLM-generated migration candidate; started by ``agents/llm_migration_agent.py``.

It runs in its own process (``python -I -B``), so it imports nothing from this repository. It reads the
shared split the R script reads, calls the candidate's ``fit``, ``predict_proba`` and ``classify``, and
writes predictions in the R script's output format (row_id, probability, prediction).

Usage: python -I -B migration_harness.py <candidate.py> <train.csv> <test.csv> <predictions.csv>
"""
import importlib.util
import sys

import numpy as np
import pandas as pd


def main(candidate_path: str, train_path: str, test_path: str, output_path: str) -> None:
    spec = importlib.util.spec_from_file_location("candidate", candidate_path)
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    train = pd.read_csv(train_path)
    test = pd.read_csv(test_path)
    model = candidate.fit(train.copy())
    probability = np.asarray(candidate.predict_proba(model, test.copy()), dtype=float).ravel()
    prediction = np.asarray(candidate.classify(probability)).astype(int).ravel()
    out = pd.DataFrame({"row_id": test["row_id"], "probability": probability, "prediction": prediction})
    out.to_csv(output_path, index=False)


if __name__ == "__main__":
    main(*sys.argv[1:5])
