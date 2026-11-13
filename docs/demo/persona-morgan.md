# Persona for the bug-hunt run of 13 November 2026: Morgan, model risk lead

The scene plan for a recorded bug hunt of the dashboard (`streamlit run app.py`, build `530337a`). "What should
happen" under each scene comes from the two requirement documents:

- **Brief**: *EXL Data & AI Hackathon 2026*, Challenge 04 "Agentic model risk factory" (p. 9) and the submission
  requirements (p. 13).
- **Plan**: *MODELTRACE AI – Complete Project Implementation Plan* (`MODELTRACE_plan_v2.pdf`), cited by step
  number (P5 = step 5).

A finding is a difference from these. Where the code deliberately does something else, the finding is logged
as an improvement, not a bug.

## Who

**Morgan Ellis**, Head of Model Risk Management at a fictional Tier-1 UK retail bank. Fifteen years in
credit risk, reads R and Python but does not write production code. Accountable under SS1/23 for an inventory
of about 250 models. English (UK). MacBook Pro 14", Chrome, a window filling the built-in display.

Morgan is piloting MODELTRACE on the legacy R credit-default model (Tier 1) before the board asks why each
validation still takes 8–12 weeks. There is no login yet, so in this workshop Morgan plays each role in turn
from the sidebar: Alex (developer), Sam (independent validator), Jordan (risk manager), Riley (monitoring
analyst) and Taylor (team lead, developer and risk manager).

Settings: the real LLM (Claude, spending capped at $3), sample data off. Morgan expects every number on
screen to match the report behind it, and expects the app to stop them from breaking the rules.

## Scenes

| # | Moment | What Morgan does | What should happen |
|---|---|---|---|
| s01 | Monday, first look | Opens the dashboard on Executive Overview; reads the five counts, the lifecycle table and both charts | Number of models (3), lifecycle status, risks, pending approvals, models by risk tier: Tier 1 R logistic, Tier 2 Gradient Boosting, Tier 3 Random Forest (P15, P16). Each count matches the report files (P17 "results displayed match the underlying calculations"). |
| s02 | Before the gate: what is this model? | Discovery for the legacy R model: tier panel, metadata tab, discrepancies tab with the score, source code; follows a line reference into the code | Metadata: name, language, algorithm, purpose, target, features, preprocessing, assumptions, missing information, each with line references and verified vs inferred (P5). Discrepancies between the old document and the code, **with their score** (recall and precision against the answer key) (P5, P16). Each code reference points at the line it quotes. |
| s03 | Re-run it herself | Runs the Discovery Agent live, waits, compares the result with the earlier one; drafts the tier rationale with the LLM | The screen says what is happening during the wait; the result has the same discrepancies; numbers elsewhere (overview count) follow; the tier stays rule-set, the LLM drafts only the rationale (P15). |
| s04 | The control case and the missing document | Discovery for Gradient Boosting (current document) and Random Forest (no document) | No false alarms on the current Gradient Boosting document (P5); Random Forest reported as missing documentation (P17). |
| s05 | Discover gate, four-eyes | Alex submits; Taylor tries to decide; Jordan requests changes without a comment, then approves; history table | Approve / Reject / Request changes; reviewer, decision, timestamp, comments and evidence reference stored (P14). Nobody decides their own submission. Request changes needs a comment. |
| s06 | Model card | Generates the card; reads every section; checks figures against the reports; Jordan requests changes, Alex resubmits | Card sections: overview and purpose, data provenance, algorithm, features and target, performance, fairness, stability, explainability, limitations and assumptions, approval and governance, risk tier and rationale, corrections to the old document. No invented metrics, no approvals that have not happened (P6). "Documentation changes requested" works (P17). |
| s07 | Redevelop | Migration page: parity table, R next to Python; runs the LLM Migration Agent live; Alex submits, Jordan approves | MAE, max difference, correlation, classification agreement and tolerance pass shown (P8); never claims parity unless the tests pass (P8); LLM migration with static checks, isolated run, parity, up to two revisions (P7). |
| s08 | Independent validation | Alex (who built it) and Taylor try Validate; Sam submits; Jordan approves | The migration side cannot certify its own work (P9). Performance: accuracy, precision, recall, F1, ROC-AUC, PR-AUC, Brier; stability PSI; fairness by SEX and age groups under 30, 30–44, 45–59, 60+, with group sizes and differences or ratios, as diagnostics; coefficients and SHAP (P9). |
| s09 | Risk register | Risk & Evidence: filters, reads a finding end to end | Each finding: ID, category, severity, description, numerical or source evidence, **potential impact**, remediation, review status (P10). |
| s10 | Drift | Monitoring: batches 001–003, PSI chart, prediction chart; runs the Monitoring Agent; Riley acknowledges and escalates; Jordan asks for re-validation | Batch 001 baseline, 002 moderate (LIMIT_BAL ×0.65, BILL_AMT1 ×1.5), 003 strong (LIMIT_BAL ×0.4, PAY_0 +2, BILL_AMT1 ×2) (P11); feature PSI, prediction change, mean PD, share above threshold, missing and schema changes; bands <0.10 / 0.10–0.25 / >0.25 (P12); severity by rule, LLM explains only, no retraining (P13); alert review actions (P14). |
| s11 | Governance | Approval queue, lifecycle, reopen Discover with a reason, history, audit log, SS1/23 mapping, AI use | A stage cannot advance without approval; reopening invalidates downstream approvals (P14); audit log of actions (P15); the SS1/23 table of P14. |
| s12 | Two windows | A second window as another user decides the same pending stage | The second decision is refused with a clear reason; no double record. |
| s13 | Coming back | Reloads the page, then the server restarts; checks what was remembered | Approvals, alerts and audit persist (JSON); the overview counts follow every action taken. |
| s14 | Odd input | Long comment, accents and markup in a comment, a missing source path, an upload with an odd name | Comments stored and shown as typed; clear errors for a missing file. |

Weak spots to pass through on the way: numbers that should follow an action (overview counts after
approvals and alert reviews), the slow LLM paths (what the screen says while it waits and when it fails),
text that overflows tables, and the files the app writes (`governance/*.json`, reports, model card markdown).
