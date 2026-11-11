"""SS1/23 1.3 model tiering. A fixed rule sets the tier; the LLM may only draft the rationale."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Literal

from llm.prompts import TIER_RATIONALE_SYSTEM, tier_rationale_user
from llm.schemas import TierRationaleDraft

if TYPE_CHECKING:
    from inventory.registry import InventoryRecord
    from llm.client import StructuredLLM

Rating = Literal["high", "medium", "low"]
TIER_RULE = "Tier 1 if materiality is high; Tier 2 if materiality is medium or complexity is high; otherwise Tier 3."


def assign_tier(materiality: Rating, complexity: Rating) -> int:
    if materiality == "high":
        return 1
    if materiality == "medium" or complexity == "high":
        return 2
    return 3


def template_rationale(record: "InventoryRecord") -> str:
    return (
        f"Tier {record.risk_tier}: materiality is {record.materiality} ({record.materiality_basis}) "
        f"and complexity is {record.complexity} ({record.complexity_basis}). Rule: {TIER_RULE}"
    )


def draft_rationale(record: "InventoryRecord", llm: "StructuredLLM | None" = None) -> tuple[str, str]:
    """Return ``(rationale, source)``. An LLM draft that names any tier other than the computed one is discarded."""
    if llm is None:
        return template_rationale(record), "rule_template"
    facts = record.model_dump(include={"name", "business_purpose", "materiality", "materiality_basis",
                                       "complexity", "complexity_basis", "risk_tier"})
    facts["tier_rule"] = TIER_RULE
    draft = llm.structured(TIER_RATIONALE_SYSTEM, tier_rationale_user(json.dumps(facts)), TierRationaleDraft).rationale
    if set(re.findall(r"\btier\s*([1-3])\b", draft, flags=re.IGNORECASE)) != {str(record.risk_tier)}:
        return template_rationale(record), "rule_template"
    return draft, "llm_draft"
