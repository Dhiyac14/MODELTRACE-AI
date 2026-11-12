"""Prompt templates used when an external LLM is enabled."""

EVIDENCE_RULES = (
    "Use only supplied evidence. Cite the source for every claim. "
    "If evidence is absent, say unknown; never invent metrics."
)


def analysis_prompt(task: str, evidence: str) -> str:
    return f"{EVIDENCE_RULES}\nTask: {task}\nEvidence:\n{evidence}"
