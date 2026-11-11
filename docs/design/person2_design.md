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
 Person 1: migration + parity ─► reports/migration/<id>_parity.json ─────────────────────┤
 Person 1: validation        ─► reports/validation/<id>_validation.json ───────────────┼─► approval gates
 Person 1: monitoring batches ─► reports/monitoring/<id>_monitoring.json                 │   (workflow/)
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

## 5. Governance workflow (`workflow/`)

**Stages:** Discover → Document → Redevelop → Validate → Monitor. Redevelop applies only to R or SAS models.
Stage status is derived from the approval log (single source of truth); the inventory status fields are a
projection refreshed after every action.

| Status | Reached by | Next |
|---|---|---|
| not_started / in_progress / changes_requested / invalidated | start, reopen, request changes, upstream reopen | submit |
| pending_review | submit (all earlier stages approved, evidence file exists) | approve, reject, request changes |
| approved | approve (evidence unchanged since submission; Redevelop needs `"passed": true`) | reopen |
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
shows Person 1's sample data with a banner while their reports do not exist. Person 1's Migration and
Validation Agents are called from the app when their modules exist.

```bash
.venv/bin/streamlit run app.py
```

## 7. Interface contract with Person 1

**Person 1 provides:**
| What | Path | Minimum shape |
|---|---|---|
| R model source | chosen by Person 1; saved in the inventory from the Discovery page | text |
| Preprocessing and split code | `engine/preprocessing.py` | text |
| Outdated / current documents | `legacy_docs/lr_model_doc_outdated.md`, `legacy_docs/gb_model_doc_current.md` | Markdown |
| Parity report | `reports/migration/<model_id>_parity.json` | `passed` (bool, required by the Redevelop gate), `r_source_path`, `python_code_path`, parity metrics |
| Validation report | `reports/validation/<model_id>_validation.json` | `performance`, `stability`, `fairness` (`{grouping: {group: {n, selection_rate, tpr, fpr}}}`), `explainability` (`coefficients`), `findings` list |
| Finding | inside the validation report | `finding_id`, `category`, `severity` (high/medium/low), `description`, `evidence`, `impact`, `remediation`, `review_status` |
| Discovery score | `reports/validation/<model_id>_discovery_score.json` | `recall`, `precision`, `matched`, `missed`, `false_alarms` |
| Monitoring report | `reports/monitoring/<model_id>_monitoring.json` | `batches[]` with `batch_id`, `scenario`, `n_records`, `feature_psi{}`, `prediction_psi`, `mean_predicted_pd`, `share_above_threshold`, `schema_changes[]`, `missing_values{}` |
| Agent entry points | `agents/migration_agent.py`, `agents/validation_agent.py` | `run_migration(model_id, r_source, llm)` and `run_validation(model_id, llm)`, each writing its report above |

**Person 2 provides:** discovery report, model card, inventory, alert report (`reports/alerts/<model_id>_alerts.json`),
approval and audit logs, the migration prompt and `MigrationCandidate` schema, and the dashboard.

**Answer key** (Person 1 owns it): a list of `{"id", "field", "type", "description"}` with the same vocabularies.
An entry counts as found when the report has a discrepancy with the same `field` and `type`; each reported
discrepancy can match only one entry. Model IDs `LR-R-001`, `GB-PY-002`, `RF-PY-003` are used in every file name.

Example files in exactly this shape are in `tests/fixtures/p2/sample_data/` (marked `"_sample": true`).

## 8. Coordination notes
- Person 2's tests and fixtures are new files under `tests/` (`tests/test_p2_*.py`, `tests/fixtures/p2/`).
- Shared files: `requirements.txt`, `.env.example`, `.gitignore`, `pytest.ini`, `agents/__init__.py`.
- Runtime state (`governance/*_log.json`, `alert_reviews.json`, `inventory/uploads/`) is git-ignored;
  `python -m inventory.registry --seed --force` resets the inventory.
- Committed outputs in `reports/discovery/`, `reports/documentation/` and `docs/model_cards/` come from the dev
  fixture and are regenerated once Person 1's real model and documents exist.
- Person 1 decides whether omissions count when precision is scored.

## 9. Verification
- 116 tests: LLM client, evidence checks, discovery rules, documentation grounding, inventory and tier,
  workflow transitions and every separation-of-duties rule, audit tamper detection, monitoring rules and
  reviews, and dashboard flows driven through Streamlit's test runner.
- Manual run in a browser against a scratch copy of the data: submit and approve Discover with two users,
  run the Monitoring Agent, acknowledge an alert, confirm the audit chain.
- Not verified: a live LLM call (no key on the development machine) and Person 1's real reports.
