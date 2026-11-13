# Bug log

Issues found by using the dashboard as a person would, with the requirement each one breaks. Requirement
references: **Brief** = *EXL Data & AI Hackathon 2026*, Challenge 04 and p. 13; **P5** etc. = step 5 of
*MODELTRACE AI – Complete Project Implementation Plan* (`MODELTRACE_plan_v2.pdf`).

Each entry is **recorded only**: nothing has been fixed. Evidence (clips, frames) lives outside the repository
in `~/Movies/app-video/2026-11-13-modeltrace-mrm/` and is referenced by clip and time.

## Status after the fixes of 13 November (branch `fix/bug-hunt-findings`, on `f9126ef`)

| Entry | Status |
|---|---|
| 1 threshold, 2 parity labels, 3 comments, 6 card SHAP, 8 card gate status, 9 impact, 10 missing document, 12 validation result, 13 "Person 1", 14 fairness groups, 15 charts, 17 alert collapse, 19 duplicate uploads, 20 tier wording, 21 card wait | Fixed, with tests; evidence regenerated on the final code |
| 7 Gradient Boosting control | Inventory fixed in `4dc80a2`; regenerated report has no contradiction, but 1 unverifiable (the install instruction added to the document cannot be checked in the code) and 2 omissions |
| 4 score not shown | Open: needs the answer-key holder to score the regenerated reports and commit the score files |
| 5 target rule | Not changed; the regenerated report finds all five planted contradictions, but the target is still judged by the LLM |
| 11 moderate batch rated high | By design (plan multipliers); the scenario is now named next to its severity |
| 16 cut-off columns, 18 silent second window, 22 small issues | Partly (code evidence column moved forward); the rest left as polish |

## Run of 13 November 2026: Morgan, model risk lead

Build `530337a`, run from a copy of the repository (`MODELTRACE_ROOT`), real Claude Opus 5.5 at medium effort
(9 calls, 25.9k input and 18.5k output tokens, about $0.47). Persona and scene plan:
[persona-morgan.md](persona-morgan.md). Sorted by severity.

### 1. The R model decides at 0.35, but every report behind the gates was made at 0.5 (confirmed)

- **What happened:** `models/legacy_model.R:23` sets `CLASSIFICATION_THRESHOLD <- 0.35` (since c23c928). The
  parity report (`threshold: 0.5`, classification agreement 1.0), the stored R predictions, the validation
  metrics and fairness selection rates, and the monitoring "share above threshold" were all produced at 0.5
  and not regenerated. The Migration page shows the 0.35 code right under "Parity tests passed … threshold
  0.5"; the model card says "a decision threshold of 0.35 is applied" next to metrics computed at 0.5; on
  Monitoring, batch 001 "share above threshold" is 0.0778 (= 467/6000, the 0.5 count) and the batch 003
  alert calls 27.2% the share "above the decision threshold".
- **Repeat:** `Rscript models/legacy_model.R data/processed/train.csv data/processed/test.csv out.csv` and
  compare with `reports/migration/r_predictions.csv`: same probabilities, 924 vs 467 predicted defaults,
  457 label disagreements (agreement 0.9238).
- **Who it hurts:** the validator and risk manager approve Redevelop and Validate on evidence for a decision
  rule the model no longer uses (P7 same specification, P8, P9).
- **Cause (sure):** threshold hard-coded to 0.5 on the Python side: `engine/models.py:52`,
  `engine/models.py:140`, `engine/pipeline.py:142`, `engine/monitoring.py:108`, `:119`, `:125`; the reports
  and `r_predictions.csv` (12 Nov 12:31) predate c23c928 (12 Nov 21:38).
- **Evidence:** s07-migration 00:26 (`frames/note-114611.png`), s06-model-card 01:39.

### 2. "Parity passed" ignores the labels (confirmed)

- **What happened:** the live LLM Migration Agent run showed green "LLM candidate matches R within tolerance
  1e-05 after 1 round(s)" while its own report says `label_agreement 0.9238`, `label_disagreements 457`. The
  candidate correctly classifies at 0.35; the stored R labels are at 0.5. The round table shows only MAE and
  maximum difference.
- **Repeat:** Migration → Run LLM Migration Agent; open `reports/llm_migration/legacy-r-logistic_llm_migration.json`.
- **Who it hurts:** P8 lists classification agreement as a parity measure and says "never claim successful
  parity unless the tests pass". After entry 1 is fixed, Person 1's report would show the same: pass with
  7.6% of decisions different.
- **Cause (sure):** `overall_pass` uses probabilities only: `engine/pipeline.py:145`,
  `agents/llm_migration_agent.py:177`; the panel omits label agreement: `app.py:472-477`.
- **Evidence:** s07-migration 01:50 (`frames/note-114736.png`).

### 3. One user's comment is stored as another user's (confirmed, three times)

- **What happened:** after Jordan requested changes on Discover, the comment stayed in the box; Taylor then
  pressed Submit and Jordan's text was stored as Taylor's submit comment. On a monitoring alert, Riley's
  escalation comment became Jordan's "request re-validation" reason and then the reason of the automatic
  Validate reopen. At the Document gate, Jordan's request-changes text sat in Alex's box for the resubmit
  (cleared by hand in this run).
- **Repeat:** act on a gate or alert with a comment, switch "Acting as", press another action.
- **Who it hurts:** the approval log and audit chain attribute words to the wrong person (P14 "store the
  reviewer, decision, timestamp, comments").
- **Cause (sure):** the comment widgets are keyed by model and stage or alert only and never cleared:
  `app.py:144`, `app.py:668`.
- **Evidence:** s05-discover-gate 01:38 (`frames/note-114229.png`), s10-monitoring 03:05
  (`frames/note-115248.png`), `governance/approval_log.json` and `alert_reviews.json` in the run copy.

### 4. Discovery shows no score against the answer key (confirmed)

- **What happened:** the Discrepancies tab of every model says "Not scored yet. Person 1 holds the answer key
  and runs: python -m agents.discovery_agent … --score "$MODELTRACE_ANSWER_KEY"". No score file is in the
  repository, so recall and precision never appear.
- **Who it hurts:** P5 and P16 ask for the discrepancies "with their score"; the jury cannot see the claim
  that the agent finds the planted discrepancies. A command line and an environment variable are not
  something a reviewer can act on.
- **Cause (sure):** no `reports/discovery/*_score.json` committed; message at `app.py:329-330`.
- **Evidence:** s02-discovery-legacy 00:44 (`frames/note-113633.png`).

### 5. A Discovery re-run loses a planted discrepancy (seen in two runs)

- **What happened:** the committed report found 9 discrepancies, including the target-definition
  contradiction (document "Target: default" vs code `target` = `default.payment.next.month`). Re-running the
  agent from the dashboard on the same files gave 6, without it; IDs were renumbered. The reviewer approves
  whichever run they happened to get.
- **Repeat:** Discovery → Run Discovery Agent on `legacy-r-logistic` (about 67 s, about $0.27). Not repeated
  a third time to save cost.
- **Who it hurts:** P5 names the target definition as a planted discrepancy and says mechanically checkable
  fields are compared in Python.
- **Cause (fairly sure):** only features, threshold and split are rule-checked
  (`agents/discovery_agent.py:145-151`); the target name is left to the LLM.
- **Evidence:** s03-discovery-rerun 01:37 (`frames/note-113825.png`).

### 6. The R model's card shows other models' SHAP values (confirmed)

- **What happened:** the legacy R logistic model card lists `random_forest_shap.*` and
  `gradient_boosting_shap.*` under Explainability.
- **Who it hurts:** the card presents another model's explanation as this model's (P6).
- **Cause (sure):** for the migrated model `load_evidence` takes the whole validation report
  (`agents/documentation_agent.py:58-60`) and the card flattens every explainability key.
- **Evidence:** s06-model-card 01:41 (`frames/note-114431.png`).

### 7. The Gradient Boosting control case raises 4 discrepancies, from files it is not registered with (confirmed)

- **What happened:** P5 makes the current Gradient Boosting document the control for false alarms, but its
  report has 4 discrepancies, one a contradiction. The report was generated from `engine/models.py`,
  `data.py`, `pipeline.py`, `validation.py` (530337a), while the inventory registers only `models.py` and
  `data.py`; two discrepancies cite the unregistered files. A re-run from the page would use two files and
  give a different report.
- **Who it hurts:** the "no false alarms on the current document" claim (P5, P17).
- **Cause (sure):** report regenerated with extra `--source` files; `inventory/model_inventory.json` not
  updated.
- **Evidence:** s04-gb-rf-discovery 00:59 and 01:03 (`frames/note-113951.png`, `note-113954.png`).

### 8. The model card says the Discovery report is pending after it was approved (confirmed)

- **What happened:** right after Jordan approved Discover, the card shows "Discovery report status:
  pending_human_review", two rows below "Tier review status: approved".
- **Cause (sure):** the card copies the report's own `review_status`, which never changes:
  `agents/documentation_agent.py:238`.
- **Evidence:** s06-model-card 01:43 (`frames/note-114433.png`).

### 9. The risk register has no Potential impact column (confirmed)

- **What happened:** every finding in `risk_findings_results.json` has `impact`, but the table shows ID,
  source, category, severity, description, evidence, remediation and status only. Severities mix six scales
  (high, medium, warning, review, low, info); batch 002 and 003 drift appear twice.
- **Requirement:** P10.
- **Cause (sure):** `app.py:572-576` does not copy `impact`.
- **Evidence:** s09-risk-register 00:27 (`frames/note-114941.png`).

### 10. A model with no document shows "Discrepancies (0)" (confirmed)

- **What happened:** Random Forest has no existing document; the page shows "Discrepancies (0)" and a grey
  "compared with no document". Nothing flags the gap; the overview and register count nothing.
- **Requirement:** P17 "Missing model documentation".
- **Evidence:** s04-gb-rf-discovery 01:57 (`frames/note-114049.png`).

### 11. The "moderate drift" batch is rated high, and the scenarios are not named (improvement, by design)

- **What happened:** batch 002 (P11 "Moderate drift": LIMIT_BAL ×0.65, BILL_AMT1 ×1.5) gets LIMIT_BAL PSI
  0.586, so it is high; no batch shows a moderate level. The table labels all batches
  "simulated_diagnostic" and has no missing-value, schema or per-batch performance columns, though the
  report holds them (P12). Its header says "Person 1 severity".
- **Cause:** the plan's own multipliers give PSI above 0.25 (`engine/pipeline.py:233`); the table at
  `app.py:614-618`.
- **Evidence:** s10-monitoring 00:39 (`frames/note-115022.png`).

### 12. The Validation Agent result is a raw JSON dump (confirmed)

- **What happened:** "Validation summary contains no fabricated measurements.", every evidence source
  `<mapping>`, no findings and `recommendations: []` although recall is 0.244.
- **Requirement:** P9 "a structured validation report containing metrics, evidence, findings and potential
  remediation actions".
- **Cause:** `agents/validation_agent.py`; shown with `st.json` at `app.py:523-525`.
- **Evidence:** s08-validation 00:34 (`frames/note-114836.png`).

### 13. The interface names the team split, "Person 1" (confirmed; raised by the user)

- **What happened:** 24 lines of `app.py` show "Person 1" to the user: the sidebar toggle "Show sample data
  where Person 1's reports are missing", "Run Migration Agent (Person 1)", "Scored by Person 1", "Person 1
  severity"; `agents/llm_migration_agent.py:223` adds "run Person 1's pipeline first" to an error.
- **Who it hurts:** a bank user or juror sees an internal work split instead of one product.

### 14. Fairness groups are unlabelled codes in alphabetical order (confirmed)

- **What happened:** SEX groups "1" and "2" (UCI: 1 male, 2 female); age bands listed 30_44, 45_59,
  60_plus, under_30; the 60+ band has 76 people yet drives disparate impact 0.767 with no small-group note.
- **Requirement:** P9 (SEX and the bands under 30, 30–44, 45–59, 60+, with sizes, as diagnostics).
- **Cause:** `app.py:490-503` shows the raw keys.
- **Evidence:** s08-validation 00:59 (`frames/note-114900.png`).

### 15. Charts: fractional counts, misplaced band labels, batch "1.5" (confirmed)

- Overview "models by tier / stage": count axis 0.2, 0.4, 0.5 (`app.py:192-196`).
- Monitoring feature PSI: "high 0.25" and "warning 0.10" labels sit near PSI 1.5–2 on the log axis, far
  from their lines (`app.py:624-625`); between 0.1 and 1 the ticks show bare "2 3 … 9", so 0.2–0.9 read as
  2–9.
- Monitoring prediction chart: batch axis 1, 1.5, 2, 2.5, 3, because "001"–"003" are read as numbers
  (`app.py:627-630`).
- **Evidence:** s01-overview 00:19, s10-monitoring 00:40 and 00:42 (`frames/note-115025.png`).

### 16. Key table columns are cut off at a 1512 px window (confirmed)

- Discrepancy table: "Detected by" and "Code evidence" are off-screen to the right, long corrections cut
  (`app.py:337-340`); gate history comments cut ("Siobhán (MRM): re-r", "Remove the oth"); SS1/23 mapping's
  fourth column cut; the parity table hides `overall_pass` below its fold; the audit log Details column is
  raw JSON; model card numbers wrap mid-value ("-8.790e-" / "06") and its evidence column runs off the edge.
- **Evidence:** s02-discovery-legacy 00:45, s05-discover-gate 01:02, s11-governance 00:48, s12-two-windows
  02:08, `frames/note-114431.png`.

### 17. An alert collapses after every action (confirmed)

- Acknowledge, then typing a comment and pressing Enter, each close the alert being worked on; acknowledge,
  comment, escalate needs it reopened twice. Only high and open alerts start expanded (`app.py:659`).
- **Evidence:** s10-monitoring 02:49.

### 18. A decision already taken in another window is ignored without a word (confirmed)

- Window A approved Document; window B, still showing the pending stage, pressed Request changes with a
  comment. Nothing was recorded (correct), but B showed no message; the status just turned approved.
- **Cause:** the button is disabled on the rerun before its click is handled (`app.py:148-154`).
- **Evidence:** s12-two-windows 02:09.

### 19. The same uploaded file can be registered twice (seen once)

- Uploading `rf model (v2) – final 汉字.py` stored it correctly, but after the file was picked twice (the
  first pick was invisible because the panel collapsed), Save added the same path twice to the inventory.
- **Cause:** `app.py:266-271` appends without removing duplicates.
- **Evidence:** s14-odd-input 00:57 (`frames/note-115809.png`).

### 20. "Tier review: not started (approved at the Discover gate)" reads as approved (confirmed)

- The parenthesis describes where the tier gets approved, but next to "not started" it reads as a status
  (`app.py:250`).

### 21. Generating the model card shows no progress text (confirmed in the footage)

- The page greys out for about 10–16 s with no sentence, unlike Discovery ("Extracting metadata…") and
  Monitoring; there is no spinner around `build_model_card` (`app.py:356-358`).
- **Evidence:** s06-model-card 00:10–00:18 and 02:16–02:22.

### 22. Smaller interface issues seen in the footage (confirmed)

- A new section opens at the previous scroll position, so the Risk & Evidence title is never seen
  (s07 00:02, s08 00:02, s09 00:02, s10 00:04).
- For one frame after switching from Overview, its "High alerts 4 / Discrepancies 13" stay under the
  Discovery header (s02 00:02).
- The disabled "Run Validation Agent" explains itself with the submit rule: "'submit' at validate needs role
  validator; Jordan (model risk manager) has risk_manager" (s08 01:06; `app.py:515-522`).
- Internal keys shown as text: "discover is pending_review", alert title "· revalidation_requested",
  evidence value "5.282053461559873" (s05 01:30, s10 01:44).
- "Invalidated" has a green ♻️ next to the green ✅ of approved (s11 00:40).
- The Discovery tabs jump back to "Extracted metadata" after a re-run (s03 00:30 vs 01:12).

### What worked well

- Separation of duties held every time, and the "Why some actions are unavailable" panel explains each
  refusal in plain words: four-eyes (Taylor on own submission), independence (Alex cannot validate what they
  built), role checks, required comments for reject, request changes, escalate and reopen.
- Reopening Discover invalidated Document, Redevelop and Validate; a stale second-window decision was
  refused with no duplicate record; the audit chain verified intact (27 events).
- State survived a page reload and a server restart; overview counts followed every action (discrepancies
  13 → 10 after the re-run, pending back to 0).
- The sandboxed LLM migration produced a correct candidate in one round (46 s), including the 0.35
  threshold; tier rationale drafted by the LLM kept the rule-set tier.
- Accents, Chinese characters, markdown and HTML in comments and file names were stored and shown as typed;
  a missing source path got a clear error.
- LLM waits (67 s Discovery, 36 s Monitoring) show a spinner with a sentence saying what is happening.
