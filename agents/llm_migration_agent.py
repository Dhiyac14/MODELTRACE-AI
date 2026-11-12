"""LLM Migration Agent: the LLM writes the Python version of a legacy R model, and code checks it.

Each round:
1. the LLM returns a Python module (``MigrationCandidate``) for the numbered R listing;
2. a static check rejects imports outside ``ALLOWED_IMPORTS``, file and process access, and missing functions;
3. ``agents/migration_harness.py`` runs the module in a separate process: an environment without
   credentials, a timeout and its own temporary folder; on macOS also a sandbox with no network, no reads of
   ``.env`` files and writes only inside that folder;
4. its predictions are compared with R's predictions using Person 1's measures and tolerance.
A failed round goes back to the LLM with what failed (the static problems, the error line of the run or the
aggregate parity figures, never data rows), up to ``max_rounds`` rounds. The agent cannot approve anything:
its report waits for human review, and the Redevelop gate still reads Person 1's parity report.

Inputs come from Person 1's pipeline (``python -m engine.pipeline``): the shared split named in
``reports/migration/migration_results.json`` and the R predictions in ``reports/migration/r_predictions.csv``.

Usage:
    python -m agents.llm_migration_agent --model-id legacy-r-logistic --source models/legacy_model.R
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from llm.client import StructuredLLM, llm_from_env
from llm.evidence import render_listing
from llm.prompts import MIGRATION_SYSTEM, migration_revision_user, migration_user
from llm.schemas import CandidateParity, MigrationAttempt, MigrationCandidate, MigrationReport
from workflow.artifacts import Artifacts

HARNESS = Path(__file__).resolve().with_name("migration_harness.py")
ALLOWED_IMPORTS = frozenset({"numpy", "pandas", "statsmodels", "patsy", "math", "typing", "__future__"})
FORBIDDEN_NAMES = frozenset({"open", "exec", "eval", "compile", "__import__", "input", "breakpoint",
                             "getattr", "setattr", "delattr", "globals", "locals", "vars"})
FILE_ATTRS = frozenset({"to_csv", "to_pickle", "to_parquet", "to_excel", "to_json", "to_sql", "to_hdf",
                        "to_feather", "to_stata", "save", "savetxt", "savez", "load", "loadtxt", "genfromtxt",
                        "fromfile", "tofile", "memmap"})
ALLOWED_DUNDERS = frozenset({"__name__", "__init__"})
REQUIRED_FUNCTIONS = ("fit", "predict_proba", "classify")
DEFAULT_TOLERANCE = 1e-5  # Person 1's parity tolerance (engine/pipeline.py, run_migration)
DEFAULT_TIMEOUT = 120.0
R_PREDICTIONS = "reports/migration/r_predictions.csv"  # written by Person 1's run_migration


@dataclass(frozen=True)
class MigrationInputs:
    """Repository-relative paths of Person 1's shared split and R predictions, and the parity tolerance."""
    train_csv: str = "data/processed/train.csv"
    test_csv: str = "data/processed/test.csv"
    r_predictions_csv: str = R_PREDICTIONS
    tolerance: float = DEFAULT_TOLERANCE

    def missing(self, root: Path) -> list[str]:
        return [p for p in (self.train_csv, self.test_csv, self.r_predictions_csv) if not (root / p).exists()]


def default_inputs(model_id: str, root: Path = Path(".")) -> MigrationInputs:
    """Read the split paths and tolerance from Person 1's parity report, so both candidates face the same test."""
    parity = Artifacts(root).load("parity", model_id) or {}
    defaults = MigrationInputs()
    return MigrationInputs(
        train_csv=parity.get("shared_train_csv", defaults.train_csv),
        test_csv=parity.get("shared_test_csv", defaults.test_csv),
        tolerance=(parity.get("r_vs_statsmodels") or {}).get("tolerance", defaults.tolerance),
    )


# --------------------------------------------------------------------------- static check
def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__") and name not in ALLOWED_DUNDERS


def check_candidate(code: str) -> list[str]:
    """Problems that stop the code from being run; an empty list means it may run."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error at line {exc.lineno}: {exc.msg}"]
    problems = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = ["." * node.level + (node.module or "")]
        else:
            modules = []
        problems += [f"line {line}: import of {m} is not allowed" for m in modules
                     if m.split(".")[0] not in ALLOWED_IMPORTS]
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or _is_dunder(node.id)):
            problems.append(f"line {line}: {node.id} is not allowed")
        if isinstance(node, ast.Attribute) and (node.attr in FILE_ATTRS or node.attr.startswith("read_")
                                                or _is_dunder(node.attr)):
            problems.append(f"line {line}: .{node.attr} is not allowed")
    defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    problems += [f"missing top-level function {name}()" for name in REQUIRED_FUNCTIONS if name not in defined]
    return problems


# --------------------------------------------------------------------------- isolated run
def candidate_env(workdir: str) -> dict[str, str]:
    """Only what Python needs to start: API keys and other credentials never reach the generated code."""
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
    return {**env, "HOME": workdir, "TMPDIR": workdir, "TEMP": workdir, "TMP": workdir}


def sandbox_available() -> bool:
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def sandbox_prefix(workdir: str) -> list[str]:
    """macOS: no network, no reads of .env files, writes only inside ``workdir``. Empty on other systems."""
    if not sandbox_available():
        return []
    profile = ('(version 1)(allow default)(deny network*)(deny file-read* (regex #"/\\.env$"))'
               f'(deny file-write*)(allow file-write* (subpath "{workdir}") (literal "/dev/null"))')
    return ["sandbox-exec", "-p", profile]


def isolation_note(timeout: float) -> str:
    note = f"separate process, environment without credentials, {timeout:g} s timeout, own temporary folder"
    if sandbox_available():
        note += "; macOS sandbox: no network, no .env reads, writes only inside that folder"
    return note


def error_line(stderr: str, limit: int = 300) -> str:
    """The last line of a traceback (the exception), shortened; only this line is sent back to the LLM."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1][:limit] if lines else ""


def run_candidate(code: str, train_csv: Path, test_csv: Path,
                  timeout: float = DEFAULT_TIMEOUT) -> tuple[pd.DataFrame | None, str | None]:
    """Run the code through the harness. Returns ``(predictions, None)`` or ``(None, error)``."""
    with tempfile.TemporaryDirectory() as tmp:
        workdir = os.path.realpath(tmp)
        candidate, output = Path(workdir, "candidate.py"), Path(workdir, "predictions.csv")
        candidate.write_text(code, encoding="utf-8")
        command = [*sandbox_prefix(workdir), sys.executable, "-I", "-B", str(HARNESS), str(candidate),
                   str(Path(train_csv).resolve()), str(Path(test_csv).resolve()), str(output)]
        try:
            done = subprocess.run(command, cwd=workdir, env=candidate_env(workdir), stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, f"timed out after {timeout:g} s"
        if done.returncode != 0:
            return None, error_line(done.stderr) or f"exit code {done.returncode}"
        return pd.read_csv(output), None


# --------------------------------------------------------------------------- parity
def compare(r_predictions: pd.DataFrame, candidate: pd.DataFrame, tolerance: float) -> CandidateParity:
    """Person 1's rule: rows aligned, and mean and maximum probability difference within the tolerance."""
    aligned = len(candidate) == len(r_predictions) > 0 and np.array_equal(
        candidate["row_id"].to_numpy(), r_predictions["row_id"].to_numpy())
    if not aligned:
        return CandidateParity(row_alignment_verified=False, n_rows=len(candidate), tolerance=tolerance)
    difference = np.abs(candidate["probability"].to_numpy(float) - r_predictions["probability"].to_numpy(float))
    agree = candidate["prediction"].to_numpy() == r_predictions["prediction"].to_numpy()
    mae, maximum = float(np.mean(difference)), float(np.max(difference))
    return CandidateParity(
        row_alignment_verified=True, n_rows=len(candidate), mae=mae, max_probability_difference=maximum,
        label_agreement=float(np.mean(agree)), label_disagreements=int(np.sum(~agree)), tolerance=tolerance,
        mae_pass=mae <= tolerance, max_difference_pass=maximum <= tolerance,
        overall_pass=bool(mae <= tolerance and maximum <= tolerance),
    )


def feedback(attempt: MigrationAttempt) -> str:
    """What failed, for the next round: problems, the error line or aggregate figures, never data rows."""
    if attempt.static_problems:
        return "The static check failed, so the code was not run:\n" + "\n".join(f"- {p}" for p in attempt.static_problems)
    if attempt.run_error:
        return f"The harness run failed: {attempt.run_error}"
    p = attempt.parity
    if not p.row_alignment_verified:
        return f"The predictions are not aligned with R's by row_id ({p.n_rows} rows returned)."
    return (f"Parity with R failed (tolerance {p.tolerance:g}): mean absolute probability difference {p.mae:.3g}, "
            f"maximum {p.max_probability_difference:.3g}, label agreement {p.label_agreement:.4f}.")


# --------------------------------------------------------------------------- agent
def evaluate(round_no: int, code: str, root: Path, inputs: MigrationInputs, r_predictions: pd.DataFrame,
             timeout: float) -> MigrationAttempt:
    attempt = MigrationAttempt(round=round_no, python_code=code, code_sha256=hashlib.sha256(code.encode()).hexdigest(),
                               static_problems=check_candidate(code))
    if attempt.static_problems:
        return attempt
    predictions, error = run_candidate(code, root / inputs.train_csv, root / inputs.test_csv, timeout)
    if error is not None:
        return attempt.model_copy(update={"run_error": error})
    parity = compare(r_predictions, predictions, inputs.tolerance)
    return attempt.model_copy(update={"parity": parity, "passed": parity.overall_pass})


def run_llm_migration(
    model_id: str,
    r_source: str,
    llm: StructuredLLM,
    root: Path = Path("."),
    inputs: MigrationInputs | None = None,
    max_rounds: int = 3,
    timeout: float = DEFAULT_TIMEOUT,
) -> MigrationReport:
    """``r_source`` and the input paths are relative to ``root``; only relative names reach the LLM."""
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    inputs = inputs or default_inputs(model_id, root)
    missing = inputs.missing(root)
    if missing:  # checked before any LLM call
        raise FileNotFoundError(f"run Person 1's pipeline first (python -m engine.pipeline); missing: {', '.join(missing)}")
    r_lines = (root / r_source).read_text(encoding="utf-8").splitlines()
    listing = render_listing({Path(r_source).as_posix(): r_lines})
    r_predictions = pd.read_csv(root / inputs.r_predictions_csv)

    user, attempts = migration_user(listing), []
    for round_no in range(1, max_rounds + 1):
        candidate = llm.structured(MIGRATION_SYSTEM, user, MigrationCandidate)
        attempts.append(evaluate(round_no, candidate.python_code, root, inputs, r_predictions, timeout))
        if attempts[-1].passed:
            break
        user = migration_revision_user(listing, candidate.python_code, feedback(attempts[-1]))

    r_text = " ".join(" ".join(r_lines).split())
    warnings = [f"term_mapping: R term {m.r_term!r} does not appear in {r_source}."
                for m in candidate.term_mapping if " ".join(m.r_term.split()) not in r_text]
    return MigrationReport(
        model_id=model_id, r_source=Path(r_source).as_posix(), train_csv=inputs.train_csv, test_csv=inputs.test_csv,
        r_predictions_csv=inputs.r_predictions_csv, tolerance=inputs.tolerance, isolation=isolation_note(timeout),
        attempts=attempts, passed=attempts[-1].passed, explanation=candidate.explanation,
        assumptions=candidate.assumptions, term_mapping=candidate.term_mapping, warnings=warnings, llm_model=llm.model,
    )


def save_migration_report(report: MigrationReport, root: Path = Path(".")) -> Path:
    """Write the report and, next to it, the last candidate as a .py file for review."""
    relpath = Path(Artifacts(root).relpath("llm_migration", report.model_id))
    code_relpath = relpath.with_name(f"{report.model_id}_candidate.py")
    (root / relpath).parent.mkdir(parents=True, exist_ok=True)
    (root / code_relpath).write_text(report.attempts[-1].python_code, encoding="utf-8")
    report = report.model_copy(update={"candidate_path": code_relpath.as_posix()})
    (root / relpath).write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return root / relpath


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Have the LLM write a Python version of a legacy R model and check it.")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--source", required=True, help="repository-relative path of the R model")
    parser.add_argument("--max-rounds", type=int, default=3)
    args = parser.parse_args()
    client, status = llm_from_env()
    if client is None:
        parser.error(status)
    result = run_llm_migration(args.model_id, args.source, client, max_rounds=args.max_rounds)
    verdict = "passed" if result.passed else "FAILED"
    print(f"wrote {save_migration_report(result)}: parity {verdict} after {len(result.attempts)} round(s)")
