# Person 2 — Day 1 implementation design (11 November)

Scope, from the work split (P2.1, P2.2, P2.3 inventory part) and the plan (steps 5, 6, 15):

| Day 1 item | Plan step | Files |
|---|---|---|
| LLM client and prompts | P2.1 | `llm/client.py`, `llm/prompts.py` |
| Pydantic schemas | P2.1 | `llm/schemas.py` |
| Discovery Agent, incl. code-vs-outdated-document check | 5 | `agents/discovery_agent.py`, `llm/evidence.py` |
| Documentation Agent | 6 | `agents/documentation_agent.py` |
| Model inventory | 15 | `inventory/registry.py`, `inventory/model_inventory.json` |
| Risk tier and SS1/23 mapping | 14–15 | `inventory/risk_tier.py`, `governance/ss1_23_mapping.json` |

Day 2 (approval workflow, audit log, Monitoring Agent, Streamlit) builds on these files and is out of scope here.

## 1. Design rules

These four rules carry the "evidence, not assertions" story that the judges will look for.

1. **The LLM proposes, code verifies.** Every fact the LLM extracts carries a source reference
   (`file`, `line_start`, `line_end`, `quote`). `llm/evidence.py` checks that the quote really is at
   those lines. A fact marked `verified` whose quote cannot be found is downgraded to `inferred`.
2. **Mechanical fields are compared in Python, not by the LLM.** Feature lists, decision threshold and
   train/test split are compared with set and number operations. The LLM only judges free-text claims
   (target definition, validation history, ownership, …).
3. **Numbers are copied by code, never written by the LLM.** Model-card metric tables come straight from
   Person 1's JSON reports. The LLM writes three prose fields only, and any decimal, percentage or
   number ≥ 100 in that prose that is not in the input facts makes the section fall back to a
   deterministic template.
4. **Nothing self-approves.** Every agent output is created with `review_status = pending_human_review`.
   The risk tier is a derived field computed by a fixed rule; the LLM may draft the rationale but cannot
   set the tier. Approval information in the model card is read from approval records, never generated.

## 2. Data flow

```
 R / Python source files ──┐
                           ├─► Discovery Agent ──► reports/discovery/<model_id>_discovery.json
 legacy_docs/<doc>.md ─────┘     │  1. LLM: extract ModelMetadata (+ line refs)
                                 │  2. code: verify every line ref
                                 │  3. LLM: extract DocumentClaims from the old document
                                 │  4. code: compare features / threshold / split
                                 │  5. LLM: judge remaining free-text claims (+ code refs, verified)
                                 ▼
                       human review at Discover gate (Day 2)
                                 ▼
 inventory record (tier) ──┐
 Person 1 reports (JSON) ──┼─► Documentation Agent ──► reports/documentation/<model_id>_model_card.json
 discovery report ─────────┘                          docs/model_cards/<model_id>.md
```

One LLM connection, plain Python orchestration, no agent framework.

## 3. Module design

### 3.1 `llm/client.py`
- `LLMClient.from_env()` reads `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_JSON_MODE`,
  `LLM_TEMPERATURE`, `LLM_CALL_LOG` (see `.env.example`). Any OpenAI-compatible endpoint works.
- `structured(system, user, schema)` returns a validated Pydantic object. It sends the JSON schema in
  the prompt, optionally asks for `json_object` mode, strips code fences, validates, and on a
  validation error resends once with the error text. This works on providers without native
  `json_schema` support.
- Each call appends one JSONL line (timestamp, model, schema, prompt and response SHA-256, latency,
  token usage, outcome) to `governance/llm_call_log.jsonl`. This feeds the AI-use declaration and audit.
- Agents depend only on the `structured(...)` method and `model` attribute, so tests inject a fake.

### 3.2 `llm/schemas.py`
- `SourceRef`, `Fact[T]` (`value`, `status ∈ {verified, inferred, missing}`, `evidence`, `note`).
- `ModelMetadata`: name, algorithm, business purpose, target, input features, excluded columns,
  preprocessing, train fraction, decision threshold, assumptions, limitations, missing information.
  `language` is set from the file extension, not by the LLM.
- `DocumentClaims` (from the old document): the three mechanical fields plus a list of free-text claims.
- `ClaimAssessment`, `Discrepancy`, `DiscoveryReport`.
- `ModelCardNarrative` (LLM output: three prose fields) and `ModelCard` (full card).
- `TierRationaleDraft`, `MigrationCandidate` (for Person 1's Migration Agent prompt).
- `DiscrepancyField` is a closed vocabulary (`input_features`, `decision_threshold`, `train_test_split`,
  `target_variable`, `validation_history`, …) so that Person 1 can score the report against the answer key
  by `(field, type)` without fuzzy matching.

### 3.3 Discovery Agent (`agents/discovery_agent.py`)
`run_discovery(model_id, source_paths, llm, legacy_doc_path=None) -> DiscoveryReport`

| Discrepancy type | Meaning | Example rule |
|---|---|---|
| `contradiction` | document and code disagree | documented feature not used by the code; threshold 0.4 vs 0.3 |
| `omission` | document is silent about something the code does | features used but not documented |
| `unverifiable` | no evidence in the repository either way | "approved by committee in 2021" |

An LLM-reported contradiction whose code evidence cannot be verified is downgraded to `unverifiable`.
The prompts are generic: they do not mention the example discrepancies listed in the plan, so the
agent is not tuned to the answer key. The development fixture (`tests/fixtures/p2/`) plants
*different* discrepancies for the same reason. Person 2 never reads `tests/doc_drift_answer_key.json`.

### 3.4 Documentation Agent (`agents/documentation_agent.py`)
`build_model_card(discovery, record, evidence, llm=None) -> ModelCard`
- Sections follow plan step 6, including risk tier and rationale and corrections to the old document.
- Performance, fairness, stability and explainability are rendered from Person 1's JSON (any nested
  dict is flattened into `key → value` rows with its `file#key` reference). Missing report → section
  says "Pending — produced at the Validate stage", never an estimate.
- Works without an LLM (template prose), so the pipeline and dashboard run offline.
- Grounding check on LLM prose: unknown numbers → section falls back to template plus a warning;
  approval wording when no approval exists → warning shown to the reviewer.

### 3.5 Inventory and risk tier (`inventory/`)
- `InventoryRecord` tracks the step 15 fields. `risk_tier` is a Pydantic `computed_field`, derived from
  `materiality` and `complexity`, so it cannot be stored out of sync or hand-edited.
- Rule (SS1/23 1.3): Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is
  high; otherwise Tier 3.
- `approval_history` holds approval record IDs. The records themselves live in
  `governance/approval_log.json` (Day 2), so approvals have a single source of truth.
- Seed records:

| model_id | Model | Materiality | Complexity | Tier |
|---|---|---|---|---|
| `LR-R-001` | R logistic regression, credit decisions | high | low | 1 |
| `GB-PY-002` | Gradient Boosting challenger | medium | high | 2 |
| `RF-PY-003` | Random Forest benchmark, not used in decisions | low | medium | 3 |

- `governance/ss1_23_mapping.json` is the stage-to-principle table from plan step 14 plus the
  out-of-scope principles. The workflow, dashboard and slide all read this one file.

## 4. Interface contract with Person 1 (to agree)

**I read:**
| What | Proposed path | Minimum shape |
|---|---|---|
| R model source | Person 1 chooses; passed as a path | text |
| Preprocessing / split code | `engine/preprocessing.py` | text (the split ratio evidence lives here) |
| Outdated document | `legacy_docs/lr_model_doc_outdated.md` | Markdown |
| Current document (control) | `legacy_docs/gb_model_doc_current.md` | Markdown |
| Parity report | `reports/migration/<model_id>_parity.json` | any JSON object of numbers / strings |
| Validation report | `reports/validation/<model_id>_validation.json` | top-level keys `performance`, `fairness`, `stability`, `explainability` (nested dicts allowed) |

**I write:**
| What | Path |
|---|---|
| Discovery report | `reports/discovery/<model_id>_discovery.json` — Person 1 scores `discrepancies[].field` and `.type` |
| Model card | `reports/documentation/<model_id>_model_card.json`, `docs/model_cards/<model_id>.md` |
| Inventory | `inventory/model_inventory.json` |
| Migration prompt and schema | `llm/prompts.py::MIGRATION_SYSTEM`, `llm/schemas.py::MigrationCandidate` |

**Answer key format proposal** (Person 1 owns the file): a list of
`{"id", "field", "type", "description"}` using the same `field` and `type` vocabularies. An answer-key
entry counts as found when the report has a discrepancy with the same `field` and `type`; each reported
discrepancy can match only one entry.

Model IDs `LR-R-001`, `GB-PY-002`, `RF-PY-003` are used in every file name.

## 5. Coordination notes
- Person 2's tests and fixtures are new files under `tests/` (`tests/test_p2_*.py`, `tests/fixtures/p2/`),
  which is Person 1's folder. New file names do not create merge conflicts; Person 1 should confirm.
- `requirements.txt`, `.env.example`, `.gitignore`, `pytest.ini` and `agents/__init__.py` are shared (plan step 1, both).
- The sample outputs in `reports/discovery/`, `reports/documentation/` and `docs/model_cards/` come from the
  dev fixture via `--replay`. They let the dashboard start on Day 2 and are regenerated once Person 1's
  real R model and documents exist.
- Omissions (`type = omission`) are real documentation gaps, but the answer key may not list them.
  Person 1 should decide whether precision is scored on all types or only on contradiction and unverifiable.

## 6. Verification for Day 1
- Unit tests with a fake LLM: client parsing and retry, evidence verification, mechanical comparison,
  downgrade rules, risk-tier truth table, inventory round trip, model-card grounding.
- An offline end-to-end run on the fixture: discovery report and model card produced from canned LLM
  answers. A live LLM run needs a key in `.env`.
