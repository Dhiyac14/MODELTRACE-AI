# Person 2 — implementation design (AI agents, governance and application)

Scope, from the work split (P2.1–P2.5) and the plan (steps 5, 6, 13–16):

| Item | Plan step | Files |
|---|---|---|
| LLM client and prompts | P2.1 | `llm/client.py`, `llm/prompts.py` |
| Pydantic schemas | P2.1 | `llm/schemas.py` |
| Discovery Agent, incl. code-vs-outdated-document check | 5 | `agents/discovery_agent.py`, `llm/evidence.py` |
| Documentation Agent | 6 | `agents/documentation_agent.py` |
| Model inventory, risk tier, SS1/23 mapping | 14–15 | `inventory/`, `governance/ss1_23_mapping.json` |
| Five-stage approval workflow, separation of duties | 14 | `workflow/state_machine.py`, `workflow/approvals.py`, `governance/users.json` |
| Audit log | 15 | `workflow/audit.py` |
| Monitoring Agent and alert reviews | 13 | `agents/monitoring_agent.py`, `workflow/alerts.py` |
| LLM Migration Agent: LLM-generated Python candidate, checked and run in isolation | P1.2 (LLM part) | `agents/llm_migration_agent.py`, `agents/migration_harness.py` |
| Streamlit dashboard, Migration/Validation Agent integration | 16 | `app.py`, `workflow/artifacts.py` |

## 1. Design rules

1. **The LLM proposes, code verifies.** Every fact the LLM extracts carries a source reference
   (`file`, `line_start`, `line_end`, `quote`), and `llm/evidence.py` checks that the quote really is at
   those lines. A fact marked `verified` whose quote cannot be found is downgraded to `inferred`.
2. **Mechanical fields are compared in Python.** Feature lists, decision threshold and split ratio use set
   and number operations; the LLM only judges free-text claims.
3. **Numbers are copied by code, never written by the LLM.** Any decimal, percentage or number ≥ 100 in
   LLM prose that is not in the input facts makes that text fall back to a deterministic template.
4. **Rules decide, the LLM explains.** The risk tier and alert severity come from fixed rules; the LLM may
   only draft a rationale or explanation, and a high-severity alert can never be downgraded to "monitor".
5. **Nothing self-approves.** Agents produce drafts; only humans submit and decide, and agents are
   recorded in the audit log as their own actor together with the person who started them.
6. **Sample data can never satisfy a gate.** Approval checks read live report files only.

## 2. Data flow

```
 source files + old document ─► Discovery Agent ─► reports/discovery/<id>_discovery.json ─┐
 inventory + Person 1 reports ─► Documentation Agent ─► reports/documentation/, docs/model_cards/ ─┤
 Person 1: migration + parity ─► reports/migration/migration_results.json ──────────────┤
   split + R predictions ─► LLM Migration Agent ─► reports/llm_migration/<id>_llm_migration.json (evidence only)
 Person 1: validation        ─► reports/validation/validation_results.json ─────────────┼─► approval gates
 Person 1: monitoring batches ─► reports/monitoring/monitoring_results.json             │   (workflow/)
                                   └─► Monitoring Agent ─► reports/alerts/<id>_alerts.json ┘
 approvals, reviews, audit ─► governance/approval_log.json, alert_reviews.json, audit_log.json
```

One LLM connection, plain Python orchestration, no agent framework.

## 3. LLM layer (`llm/`)
- `llm_from_env()` picks the backend from `LLM_PROVIDER` and returns `None` instead of failing, so the app and
  the Documentation and Monitoring Agents fall back to templates.
  - `anthropic` (`llm/claude_client.py`): Claude through the native Anthropic SDK. Default model
    `claude-opus-5-5`, `LLM_EFFORT=medium`; schema enforced by the API (`messages.parse`); no temperature
    (rejected by Opus 5.5); server-side refusal fallback on by default (`LLM_FALLBACKS=off` disables it);
    refusals and truncated replies raise `LLMError`. The key and `https://api.anthropic.com` are passed
    explicitly, so `ANTHROPIC_*` variables in the shell are never used.
  - `openai` (`LLMClient`): any OpenAI-compatible endpoint, configured with `LLM_BASE_URL`, `LLM_MODEL`,
    `LLM_JSON_MODE`, `LLM_TEMPERATURE`.
- Live check (11 November): one run of all seven prompts on the dev fixture with Claude Opus 5.5 at medium effort
  cost $0.26 (13.5k input, 10.1k output tokens). All planted discrepancies were found, and every LLM draft
  passed the grounding checks.
- `structured(system, user, schema)` sends the JSON schema in the prompt, validates the reply and resends
  validation errors once. Every call is logged (hashes, model, latency, tokens, outcome) for the AI-use
  declaration.
- `ReplayLLM` returns canned replies for offline demos and tests; replies still pass every verification.

## 4. Agents
**Discovery** (`run_discovery`) — discrepancy types: `contradiction` (document and code disagree), `omission`
(document silent), `unverifiable` (no evidence either way). An LLM contradiction without verified code
evidence becomes `unverifiable`; a document claim whose quote is not in the document is dropped. Prompts never
mention the planted discrepancies, and the dev fixture plants different ones; Person 2 never reads the
answer key.

**Documentation** (`build_model_card`) — sections follow plan step 6, including risk tier, approval status
read from the workflow and corrections to the old document. Validation sections stay "Pending" until the
live report exists.

**Monitoring** (`build_alert_report`) — alerts from fixed rules: feature or prediction PSI 0.10–0.25 warning,
above 0.25 high; any schema change high; any missing value warning. Alert ids are stable
(`<model>:<batch>:<metric>:<feature>`), so human reviews survive re-runs. The LLM explains each alert (what
changed, impact, checks, recommendation: monitor / investigate / consider re-validation); it cannot retrain,
replace or deploy anything.

**LLM Migration** (`run_llm_migration`) — the work split asks for an LLM-generated Python candidate; Person 1's
engine uses a hand-written one, so this agent adds the LLM part without changing Person 1's files. Each round:
the LLM returns a module with `fit`, `predict_proba` and `classify`; `check_candidate` rejects imports outside
numpy, pandas, statsmodels, patsy, math and typing, file and process access and escape hatches (`open`,
`getattr`, dunder attributes); `migration_harness.py` runs it with `python -I -B` in its own temporary folder,
with an environment holding no credentials, a timeout and, on macOS, `sandbox-exec` (no network, no `.env`
reads, writes only in that folder); the predictions are compared with `reports/migration/r_predictions.csv`
using Person 1's measures and tolerance. A failed round goes back with the static problems, the last line of
the error or the aggregate figures, never data rows; at most three rounds. Inputs and tolerance are read from
Person 1's parity report, and missing inputs stop the agent before any LLM call. The Redevelop gate is
unchanged: it still reads Person 1's parity report.

## 5. Governance workflow (`workflow/`)

**Stages:** Discover → Document → Redevelop → Validate → Monitor. Redevelop applies only to R or SAS models.
Stage status is derived from the approval log (single source of truth); the inventory status fields are a
projection refreshed after every action.

| Status | Reached by | Next |
|---|---|---|
| not_started / in_progress / changes_requested / invalidated | start, reopen, request changes, upstream reopen | submit |
| pending_review | submit (all earlier stages approved, evidence file exists) | approve, reject, request changes |
| approved | approve (evidence unchanged since submission; Redevelop needs Person 1's `r_vs_statsmodels.overall_pass`) | reopen |
| rejected | reject (comment required) | reopen by a risk manager |

Reopening a stage invalidates every later stage. Each approval stores the SHA-256 of the evidence file, so
an approval of a file that later changes is shown as **stale**.

**Separation of duties** (`workflow/approvals.py`):

| Rule | Check |
|---|---|
| Role matrix | developer submits Discover, Document, Redevelop; validator submits Validate; monitoring analyst submits Monitor; risk manager decides and reopens |
| Four-eyes | the submitter of a stage cannot decide on it |
| Independence (SS1/23 4.1) | whoever submitted Redevelop cannot submit or decide Validate |
| No self-approval by AI | agents cannot take any approval or review action |

Demo users in `governance/users.json` include a team lead with developer and risk-manager roles, which is
what makes the four-eyes and independence checks visible.

**Alert reviews:** open → acknowledged → investigating → escalated → closed, or → revalidation requested
(risk manager), which reopens Validate and therefore invalidates Monitor. Escalate, close and re-validation
need a comment.

**Audit log:** every approval, review, inventory change and agent run is appended to a hash-chained log;
`verify()` reports any edited, removed or reordered event. This makes tampering detectable, not impossible.

## 6. Dashboard (`app.py`)
Sections: Executive Overview, Discovery, Documentation, Migration, Validation, Risk & Evidence, Monitoring,
Governance. Each stage page ends with its approval gate, which lists the reasons any action is unavailable
for the current user. The sidebar picks the model, the acting user (prototype: no login) and a toggle that
shows copies of Person 1's reports (from `ml-engineering` @ fdad799) with a banner while they are not on this
branch. After the merge, the Migration and Validation buttons call Person 1's `MigrationAgent` and
`ValidationAgent` classes. The Migration page also runs the LLM Migration Agent and shows each round, the
generated module, the term mapping and the isolation used.

```bash
.venv/bin/streamlit run app.py
```

## 7. How Person 2 reads Person 1's outputs (`ml-engineering` @ fdad799)

Model IDs follow Person 1's `inventory/models.json`: `legacy-r-logistic`, `python-gradient-boosting`,
`python-random-forest`.

| Use | Person 1 file | Fields used |
|---|---|---|
| Discover input | `models/legacy_model.R`, `engine/data.py` | R `glm` (logit, threshold 0.5); split `test_size=0.2`, stratified, `random_state=42`; ID, SEX, AGE excluded from predictors |
| Existing document | `models/outdated_model_document.md` | compared with the code by the Discovery Agent |
| Redevelop gate | `reports/migration/migration_results.json` | `r_vs_statsmodels.overall_pass` (must be true to approve), parity metrics, `r_script` |
| Validate | `reports/validation/validation_results.json` | `metrics`, `stability`, `fairness.{sex,age_groups}` (`by_group`, `demographic_parity_difference`, `disparate_impact`), `explainability` (`coefficients`, `*_shap.mean_abs_shap`) |
| Risk & Evidence | `reports/risk_findings/risk_findings_results.json` | `id`, `risk_category`, `severity`, `description`, `evidence`, `remediation`, `review_status` |
| Monitor | `reports/monitoring/monitoring_results.json` | `batches[]`: `batch`, `feature_psi`, `prediction_psi`, `mean_predicted_probability`, `percentage_above_threshold`, `schema_change`, `missing_values` |

- Person 1's pipeline produces these reports for the migrated legacy model only, so the Gradient Boosting and
  Random Forest models stay pending at Validate and Monitor.
- Alert severity is recomputed with the same PSI bands as `engine/monitoring.py`; a test checks that both agree
  for every batch.
- Scoring the Discovery report against `models/discovery_answer_key.json` stays with Person 1 (the key is local
  to them).
- `engine/pipeline.py::generate_agent_reports` keeps calling the deterministic agent classes, so running the
  pipeline never spends LLM tokens; the LLM agents run from the dashboard behind the approval gates.

## 8. Merging `agent-governance` with `ml-engineering` (Day 3)

Trial merge, done locally and not pushed, on 11 November: 8 add/add conflicts. Resolved as below, Person 1's
16 tests and Person 2's 132 tests passed together, `generate_agent_reports` ran, and all 8 dashboard pages
rendered from Person 1's live reports.

| File | Keep | Why |
|---|---|---|
| `.gitignore` | Person 2 | already contains Person 1's entries |
| `agents/discovery_agent.py`, `documentation_agent.py`, `monitoring_agent.py` | Person 2 | include Person 1's classes verbatim plus the LLM agents |
| `llm/schemas.py` | Person 2 | includes Person 1's `Evidence`, `Finding`, `AgentResult` verbatim |
| `llm/client.py`, `llm/__init__.py` | Person 2 | Person 1's `__init__` imports `LLMConfig` / `LLMResponse`, which no longer exist |
| `inventory/registry.py`, `inventory/__init__.py` | Person 2 | Person 1's `__init__` imports `ModelInventory` / `ModelRecord` |
| `app.py` | Person 2 | full dashboard |
| `agents/__init__.py`, `workflow/__init__.py` | Person 1 (merged automatically) | their imports work with Person 2's modules |

Person 1's `governance/*.py`, `workflow/lifecycle.py`, `inventory/models.json` and `prompts.py` merge without
conflict and stay; `tests/test_governance.py` uses them. The dashboard uses `workflow/state_machine.py`; the two
lifecycle implementations can be reconciled later. Both `pytest.ini` and `pyproject.toml` configure pytest the
same way. Install both dependency lists: `pip install -e ".[dev,validation,statsmodels]"` and
`pip install -r requirements.txt`.

## 9. Coordination notes
- Person 2's tests and fixtures are new files under `tests/` (`tests/test_p2_*.py`, `tests/fixtures/p2/`).
- Runtime state (`governance/*_log.json`, `alert_reviews.json`, `inventory/uploads/`) is git-ignored;
  `python -m inventory.registry --seed --force` resets the inventory.
- `tests/fixtures/p2/person1_reports/` holds copies of Person 1's reports for display and tests on this branch;
  gates never read them.

## 10. Verification
- 160 Person 2 tests, including compatibility tests for Person 1's interfaces and reports and the sandbox tests for
  generated code; with Person 1's 16 tests, 176 pass on the merged branch (Person 1's `ml-engineering` merged into
  `agent-governance` on 12 November).
- Live Claude Opus 5.5 runs, each estimated with `count_tokens` first:
  - development fixture: $0.26 (seven calls);
  - Person 1's R model, `engine/data.py` and outdated document: $0.26 (four calls). No false alarm on the 0.5
    threshold; the missing feature list, split and preprocessing reported; every evidence section of the card
    filled from Person 1's reports with no grounding warnings;
  - Gradient Boosting and Random Forest discovery and cards, and alert explanations on Person 1's monitoring
    report: $0.36 (six calls);
  - LLM Migration Agent on the UCI split: $0.10 (one call, estimate $0.05-$0.17), parity passed in the first
    round with MAE 9.4e-9 and maximum difference 3.6e-7 against R, all 6000 labels equal.
- Browser walkthrough: submit and approve Discover with two users, run the Monitoring Agent, acknowledge an
  alert, confirm the audit chain.
