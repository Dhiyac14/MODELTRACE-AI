# MODELTRACE AI — AI-use declaration

## Generative AI inside the product

| Task | Model | What checks it | Human step |
|---|---|---|---|
| Extract model facts from source code | Claude Opus 5.5 (Anthropic API, medium effort) | every fact's code quote is checked against the file | Discover gate |
| List claims in an existing model document and judge them against the code | Claude Opus 5.5 | quotes checked in the document; contradictions need verified code evidence; feature list, threshold and split compared in code | Discover gate |
| Draft model-card prose (overview, methodology, limitations) | Claude Opus 5.5 | numbers must appear in the evidence; approval wording flagged; all figures in tables are copied by code | Document gate |
| Draft the risk-tier rationale (optional) | Claude Opus 5.5 | discarded unless it names the tier the fixed rule computed | Discover gate |
| Explain monitoring alerts | Claude Opus 5.5 | severity set by fixed PSI rules; numbers must appear in the batch data; high alerts cannot be downgraded | alert review, Monitor gate |
| Write a Python version of the legacy R model | Claude Opus 5.5 | static check of imports and file or process access; run in an isolated process (sandboxed on macOS); predictions compared with R's within 1e-5; R terms in the mapping must appear in the R code | Redevelop gate (evidence for the reviewer) |

Without an API key the product runs with template text, and only the Discovery and LLM Migration Agents are
unavailable. Every LLM call is logged in `governance/llm_call_log.jsonl`. Prompts contain code, model
documents, aggregate metrics and, for a failed migration round, the error line of the run, never
customer-level records.

## AI tools and existing code used to build the project

The hackathon rules ask teams to declare AI tools and any existing code used. Each person declares their own
part in the same form.

| Part | Owner | AI tools used to build it | Existing code used |
|---|---|---|---|
| Agents, LLM layer, approval workflow, audit log, inventory, dashboard, optional MLflow export, their tests, the design document and the governance documents | Person 2 | Claude Code (Anthropic, Claude Opus 5.5) as a coding assistant, directed by Person 2 | Open-source libraries as published (Pydantic, python-dotenv, Streamlit, Plotly, pandas, pytest, MLflow, the Anthropic and OpenAI Python SDKs); Person 1's agent classes, kept unchanged for compatibility |
| ML engine, R model, migration, validation, monitoring and risk findings (`engine/`, `models/`, `reports/`) | Person 1 | *[Person 1 to complete]* | *[Person 1 to complete]* |

Data: UCI Default of Credit Card Clients (dataset 350), public.

## What was tested independently of the AI

- 165 automated tests for Person 2's code and 18 for Person 1's (183 in all), run together on the merged branch; the
  MLflow round-trip test runs only where MLflow is installed. They cover
  the evidence checks, the approval rules, tamper detection, the alert rules (checked against Person 1's own
  severities), the static check, sandbox and revision loop for generated code, and the dashboard pages. The
  LLM is replaced by fakes in these tests.
- Live Claude runs with their cost measured before and after:
  - development fixture: $0.26;
  - Person 1's R model and documents: $0.26;
  - Gradient Boosting and Random Forest cards plus alert explanations: $0.36;
  - Python version of the R model: $0.10, passed parity with R in the first round.
  Their outputs were read and spot-checked against the source files and reports.
- A manual walkthrough of the dashboard in a browser: submissions, approvals, an agent run, an alert review
  and an audit-chain check.
- Scoring of the Discovery Agent against the hidden answer key is done by Person 1, who holds the key.
