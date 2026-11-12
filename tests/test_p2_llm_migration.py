"""Person 2: LLM Migration Agent: static check, isolated run, parity with R and the revision loop.

The LLM is a fake returning fixed code. R is not needed: the reference predictions are written by
statsmodels Logit (Newton), while the candidates fit a GLM by IRLS, as R's glm() does.
"""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

import agents.llm_migration_agent as agent
from agents.llm_migration_agent import (ALLOWED_IMPORTS, MigrationInputs, candidate_env, check_candidate,
                                        default_inputs, run_candidate, run_llm_migration, sandbox_available,
                                        save_migration_report)
from llm.prompts import MIGRATION_SYSTEM
from llm.schemas import MigrationCandidate, MigrationReport, TermMapping
from workflow.artifacts import Artifacts

ROOT = Path(__file__).resolve().parents[1]
LR = "legacy-r-logistic"
EXCLUDED = ("row_id", "target", "SEX", "AGE", "ID")  # as in models/legacy_model.R

GOOD = '''import numpy as np
import statsmodels.api as sm

EXCLUDED = ("row_id", "target", "SEX", "AGE", "ID")


def design(df):
    return sm.add_constant(df[[c for c in df.columns if c not in EXCLUDED]], has_constant="add")


def fit(train_df):
    return sm.GLM(train_df["target"], design(train_df), family=sm.families.Binomial()).fit()


def predict_proba(model, df):
    return np.asarray(model.predict(design(df)))


def classify(p):
    return (np.asarray(p) >= 0.5).astype(int)
'''
BROKEN = GOOD.replace('train_df["target"]', 'train_df["default"]')   # KeyError when run
WRONG = GOOD.replace('"ID")', '"ID", "BILL_AMT1")')                  # runs, drops a predictor
UNSAFE = "import os\n" + GOOD


class Fake:
    model = "fake"

    def __init__(self, *codes, term_mapping=()):
        self.codes = list(codes)
        self.term_mapping = list(term_mapping)
        self.prompts = []

    def structured(self, system, user, schema):
        assert schema is MigrationCandidate and system == MIGRATION_SYSTEM
        self.prompts.append(user)
        return MigrationCandidate(python_code=self.codes.pop(0), explanation="GLM, binomial family, logit link.",
                                  assumptions=["The harness passes the shared split."], term_mapping=self.term_mapping)


@pytest.fixture
def split(tmp_path):
    """Shared split, reference predictions and the R source, laid out as Person 1's pipeline leaves them."""
    rng = np.random.default_rng(7)
    n = 400
    frame = pd.DataFrame({"row_id": range(n), "LIMIT_BAL": rng.normal(size=n), "PAY_0": rng.integers(-1, 3, n),
                          "BILL_AMT1": rng.normal(size=n), "SEX": rng.integers(1, 3, n), "AGE": rng.integers(21, 70, n)})
    logit = -0.5 + 0.8 * frame.LIMIT_BAL - 0.6 * frame.PAY_0 + 0.3 * frame.BILL_AMT1
    frame["target"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    train, test = frame.iloc[:300], frame.iloc[300:]
    (tmp_path / "data/processed").mkdir(parents=True)
    train.to_csv(tmp_path / "data/processed/train.csv", index=False)
    test.to_csv(tmp_path / "data/processed/test.csv", index=False)

    features = [c for c in frame.columns if c not in EXCLUDED]
    reference = sm.Logit(train["target"], sm.add_constant(train[features])).fit(disp=False)
    probability = reference.predict(sm.add_constant(test[features]))
    (tmp_path / "reports/migration").mkdir(parents=True)
    pd.DataFrame({"row_id": test["row_id"], "probability": probability, "prediction": (probability >= 0.5).astype(int)}
                 ).to_csv(tmp_path / "reports/migration/r_predictions.csv", index=False)
    (tmp_path / "models").mkdir()
    shutil.copy(ROOT / "models/legacy_model.R", tmp_path / "models/legacy_model.R")
    return tmp_path


def migrate(root, llm, **kwargs):
    return run_llm_migration(LR, "models/legacy_model.R", llm, root, **kwargs)


# --------------------------------------------------------------------------- static check
def test_static_check_accepts_a_plain_statsmodels_module():
    assert check_candidate(GOOD) == []


@pytest.mark.parametrize("code,problem", [
    ("import os\n", "import of os"),
    ("import subprocess\n", "import of subprocess"),
    ("from pathlib import Path\n", "import of pathlib"),
    ("from . import helpers\n", "import of ."),
    ("X = open('f')\n", "open is not allowed"),
    ("X = __import__('os')\n", "__import__ is not allowed"),
    ("X = getattr(np, 'load')\n", "getattr is not allowed"),
    ("import pandas as pd\nX = pd.read_csv('f')\n", ".read_csv is not allowed"),
    ("def dump(df):\n    df.to_csv('f')\n", ".to_csv is not allowed"),
    ("X = ().__class__.__bases__\n", ".__class__ is not allowed"),
])
def test_static_check_rejects_file_process_and_escape_hatches(code, problem):
    assert any(problem in p for p in check_candidate(GOOD + code))


def test_static_check_needs_the_harness_functions_and_valid_syntax():
    assert check_candidate(GOOD.replace("def classify", "def label")) == ["missing top-level function classify()"]
    assert check_candidate("def fit(:")[0].startswith("syntax error at line 1")


def test_the_prompt_names_every_allowed_import():
    assert all(name in MIGRATION_SYSTEM for name in ALLOWED_IMPORTS - {"__future__"})


# --------------------------------------------------------------------------- isolated run
def test_generated_code_gets_no_credentials(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    env = candidate_env("/tmp/work")
    assert "secret" not in env.values()
    assert set(env) <= {"PATH", "SYSTEMROOT", "HOME", "TMPDIR", "TEMP", "TMP"}


def test_a_run_that_never_ends_is_stopped(split):
    looping = GOOD.replace("def fit(train_df):\n", "def fit(train_df):\n    while True:\n        pass\n")
    predictions, error = run_candidate(looping, split / "data/processed/train.csv", split / "data/processed/test.csv",
                                       timeout=3)
    assert predictions is None and error == "timed out after 3 s"


@pytest.mark.skipif(not sandbox_available(), reason="OS sandbox is macOS only")
def test_sandbox_blocks_writes_outside_its_folder_and_env_reads(split):
    leak = split / "leak.csv"
    (split / ".env").write_text("LLM_API_KEY=secret\n")
    train, test = split / "data/processed/train.csv", split / "data/processed/test.csv"
    writes = GOOD.replace("def fit(train_df):\n", f"def fit(train_df):\n    train_df.to_csv({str(leak)!r})\n")
    reads = GOOD.replace("def fit(train_df):\n",
                         f"def fit(train_df):\n    import pandas\n    pandas.read_csv({str(split / '.env')!r})\n")
    for code in (writes, reads):  # the static check is skipped here on purpose, to test the sandbox alone
        predictions, error = run_candidate(code, train, test)
        assert predictions is None and "PermissionError" in error
    assert not leak.exists()


# --------------------------------------------------------------------------- agent
def test_a_correct_candidate_passes_in_one_round(split):
    llm = Fake(GOOD)
    report = migrate(split, llm)
    assert report.passed and len(report.attempts) == 1 and len(llm.prompts) == 1
    parity = report.attempts[0].parity
    assert parity.overall_pass and parity.row_alignment_verified and parity.n_rows == 100
    assert parity.max_probability_difference <= report.tolerance and parity.label_disagreements == 0
    assert report.review_status == "pending_human_review" and report.llm_model == "fake"
    assert "=== FILE: models/legacy_model.R ===" in llm.prompts[0]  # relative name only, no local path


def test_failed_rounds_go_back_to_the_llm_with_what_failed(split):
    llm = Fake(BROKEN, WRONG, GOOD)
    report = migrate(split, llm)
    first, second, third = report.attempts
    assert first.run_error == "KeyError: 'default'" and first.parity is None and not first.passed
    assert second.parity is not None and not second.parity.overall_pass and not second.passed
    assert third.passed and report.passed
    assert "The harness run failed: KeyError: 'default'" in llm.prompts[1] and BROKEN in llm.prompts[1]
    assert "Parity with R failed" in llm.prompts[2] and WRONG in llm.prompts[2]
    assert all("glm(formula, data = train" in p for p in llm.prompts)  # the R code goes with every round


def test_unsafe_code_is_never_run_and_rounds_are_capped(split, monkeypatch):
    monkeypatch.setattr(agent, "run_candidate", lambda *a, **k: pytest.fail("unsafe code was run"))
    report = migrate(split, Fake(UNSAFE, UNSAFE), max_rounds=2)
    assert not report.passed and len(report.attempts) == 2
    assert all(a.static_problems == ["line 1: import of os is not allowed"] and a.run_error is None
               for a in report.attempts)


def test_missing_inputs_stop_the_agent_before_any_llm_call(tmp_path):
    llm = Fake()
    with pytest.raises(FileNotFoundError, match="python -m engine.pipeline"):
        migrate(tmp_path, llm)
    assert llm.prompts == []


def test_term_mapping_must_quote_the_r_code(split):
    mapping = [TermMapping(r_term='binomial(link = "logit")', python_term="sm.families.Binomial()"),
               TermMapping(r_term="lasso()", python_term="sm.Logit")]
    report = migrate(split, Fake(GOOD, term_mapping=mapping))
    assert report.warnings == ["term_mapping: R term 'lasso()' does not appear in models/legacy_model.R."]


def test_save_writes_the_report_and_the_candidate_module(split):
    path = save_migration_report(migrate(split, Fake(GOOD)), split)
    saved = MigrationReport.model_validate(json.loads(path.read_text()))
    assert path == split / "reports/llm_migration/legacy-r-logistic_llm_migration.json"
    assert saved.candidate_path == "reports/llm_migration/legacy-r-logistic_candidate.py"
    assert (split / saved.candidate_path).read_text() == GOOD
    assert Artifacts(split).load("llm_migration", LR)["passed"] is True


def test_inputs_and_tolerance_come_from_person1_parity_report(tmp_path):
    assert default_inputs(LR, tmp_path) == MigrationInputs()
    report = tmp_path / "reports/migration/migration_results.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"shared_train_csv": "split/train.csv", "shared_test_csv": "split/test.csv",
                                  "r_vs_statsmodels": {"tolerance": 1e-4}}))
    assert default_inputs(LR, tmp_path) == MigrationInputs("split/train.csv", "split/test.csv", tolerance=1e-4)
