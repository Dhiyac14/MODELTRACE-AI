"""LLM layer (Person 2): clients, prompts, structured schemas and evidence checks.

When merging with ml-engineering, keep this file: Person 1's version imports LLMConfig and
LLMResponse from llm.client, which this layer does not define.
"""
from .schemas import AgentResult, Evidence, Finding

__all__ = ["AgentResult", "Evidence", "Finding"]
