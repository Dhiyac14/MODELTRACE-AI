# MODELTRACE AI — AI-use declaration

## Generative AI inside the product

| Task | Model | What checks it | Human step |
|---|---|---|---|
| Extract model facts from source code | Claude Opus 5.5 (Anthropic API, medium effort) | every fact's code quote is checked against the file | Discover gate |
| List claims in an existing model document and judge them against the code | Claude Opus 5.5 | quotes checked in the document; contradictions need verified code evidence; feature list, threshold and split compared in code | Discover gate |
| Draft model-card prose (overview, methodology, limitations) | Claude Opus 5.5 | numbers must appear in the evidence; approval wording flagged; all figures in tables are copied by code | Document gate |
| Draft the risk-tier rationale (optional) | Claude Opus 5.5 | discarded unless it names the tier the fixed rule computed | Discover gate |
| Explain monitoring alerts | Claude Opus 5.5 | severity set by fixed PSI rules; numbers must appear in the batch data; high alerts cannot be downgraded | alert review, Monitor gate |

Without an API key the product runs with template text, and only the Discovery Agent is unavailable. Every
LLM call is logged in `governance/llm_call_log.jsonl`. Prompts contain code, model documents and aggregate
metrics, never customer-level records.

## Generative AI used to build the project

**Person 2 (agents, governance, dashboard).** The code, tests, design document, the Person 2 section of the
README and drafts of this declaration and the Responsible AI note were written with Claude Code (Anthropic,
Claude Opus 5.5), working on Person 2's instructions. Person 2 set the requirements, made the design
decisions and chose what to keep. *[Person 2: confirm this wording before submission.]*

**Person 1 (ML engine, migration, validation, monitoring).** *[Person 1 to complete.]*

## What was tested independently of the AI

- 136 automated tests for Person 2's code and 16 for Person 1's (152 in all), run together on the merged branch. They cover
  the evidence checks, the approval rules, tamper detection, the alert rules (checked against Person 1's own
  severities) and the dashboard pages. The LLM is replaced by fakes in these tests.
- Live Claude runs with their cost measured before and after:
  - development fixture: $0.26;
  - Person 1's R model and documents: $0.26;
  - Gradient Boosting and Random Forest cards plus alert explanations: $0.36.
  Their outputs were read and spot-checked against the source files and reports.
- A manual walkthrough of the dashboard in a browser: submissions, approvals, an agent run, an alert review
  and an audit-chain check.
- Scoring of the Discovery Agent against the hidden answer key is done by Person 1, who holds the key.
