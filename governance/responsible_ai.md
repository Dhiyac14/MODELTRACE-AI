# MODELTRACE AI — Responsible AI note

MODELTRACE AI is a hackathon prototype of an agentic model risk factory. It discovers, documents, redevelops,
validates and monitors credit models, and a person approves every stage. It uses public data only.
Sections marked *(Person 1 to review)* describe Person 1's engine and cite its reports.

**Data and its limits** *(Person 1 to review)*. UCI Default of Credit Card Clients (dataset 350), fetched with
`ucimlrepo` and checked on load: 30,000 rows, the expected columns, no missing values, a default rate of about
22%. It is historical Taiwanese credit-card data (2005). It is not representative of a UK bank's current portfolio,
and no result may be read as evidence about one.

**Fairness** *(Person 1 to review)*. SEX and AGE are excluded from the predictors and kept only for evaluation.
Results are diagnostics for a person to judge, not a pass or fail. On the test set the disparate impact is 0.907
for SEX and 0.767 across age groups. The 60+ group has only 76 records, so its rates are unstable
(`reports/validation/validation_results.json`, `reports/risk_findings/risk_findings_results.json`).

**Performance and explainability** *(Person 1 to review)*. At the 0.5 threshold the migrated model has a recall of
0.244: most defaulters are not flagged, which is recorded as a high-severity finding. Coefficients explain the
logistic model; SHAP values explain the Random Forest and Gradient Boosting models.

**Human oversight.** Agents produce drafts; people decide. Each stage has a gate with approve, reject and
request changes; a stage opens only when the previous one is approved, and reopening a stage invalidates
every later one. Monitoring alerts are acknowledged, investigated or escalated by people, and only a risk
manager can send a model back to validation. No agent retrains, replaces or deploys a model.

**Separation of duties.** Roles decide who may submit and who may decide at each stage. Nobody can decide
on their own submission; whoever built the redevelopment cannot validate it (SS1/23 4.1); agents cannot
take approval actions. A demo user with two roles shows these checks working.

**LLM risks and controls.** The LLM (Claude Opus 5.5) extracts facts, compares documents with code and drafts
prose. To limit hallucination:
- every fact must quote the code it comes from, and the quote is checked against the file; unchecked facts are
  marked *inferred*, and claims not found in a document are dropped;
- feature lists, thresholds and split ratios are compared in code, not by the LLM;
- any decimal, percentage or number of 100 or more in LLM prose that is not in the evidence replaces the draft
  with template text, and wording that implies an approval is flagged;
- fixed rules set the risk tier and alert severity, and the LLM cannot lower a high alert;
- refusals and truncated replies raise errors instead of returning empty output.
Prompts contain source code, model documents and aggregate metrics, never customer-level records. Every call
is logged (hashes, model, tokens, outcome) in `governance/llm_call_log.jsonl`.

**Generated code** *(Person 1 to review)*. The Python candidate used by the engine is written by Person 1 and
parity-tested against the R `glm` on the same split: maximum probability difference 3.6e-7 against a tolerance
of 1e-5. The Redevelop stage can be approved only when this test passes. The LLM Migration Agent also has the
LLM write a candidate from the R code, and that code is executed, so it is contained: a static check rejects
imports outside numpy, pandas, statsmodels, patsy, math and typing, and any file or process access; a fixed
harness runs it in a separate process with no credentials in its environment and a timeout; on macOS a
sandbox also blocks the network, reads of `.env` files and writes outside its temporary folder. On other
systems only the static check, the process and the timeout apply. Its predictions are compared with R's
under the same tolerance, and a failed round goes back to the LLM with the error line or aggregate figures,
never data rows. Its report is evidence for the reviewer; it does not open the gate.

**Auditability.** Each approval stores a hash of the file it approved, so a later change to that evidence is
shown as a stale approval. Every action goes into an audit log where each entry carries the hash of the previous
one; editing, removing or reordering an entry is detected. The logs are JSON files: tampering is detectable,
not prevented.

**SS1/23.** The five stages map to principles 1 (model identification, inventory, tiering), 3 (development,
documentation, testing), 4 (independent validation, monitoring) and 5.3 (escalation), with governance (2.3, 2.4)
across all stages (`governance/ss1_23_mapping.json`). Outside the prototype: board responsibilities (2.1), SMF
accountability (2.2), internal audit (2.5) and post-model adjustments (5.1).

**Prototype limits.** No login or access control; demo users are picked in the dashboard. Only the migrated
logistic model is validated and monitored. Monitoring batches are simulated drift on the test set, not
production data. Alert thresholds (PSI 0.10 and 0.25) are common heuristics, not regulatory limits.
