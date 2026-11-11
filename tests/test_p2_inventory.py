"""Person 2: inventory, SS1/23 risk tier and stage mapping."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from inventory.registry import (
    InventoryRecord,
    get_record,
    load_inventory,
    save_inventory,
    seed_records,
    update_record,
)
from inventory.risk_tier import assign_tier, draft_rationale
from llm.client import ReplayLLM
from llm.schemas import TierRationaleDraft

ROOT = Path(__file__).resolve().parents[1]


class OneShot:
    model = "fake"

    def __init__(self, text):
        self.text = text

    def structured(self, system, user, schema):
        return TierRationaleDraft(rationale=self.text)


@pytest.mark.parametrize("materiality,complexity,tier", [
    ("high", "low", 1), ("high", "medium", 1), ("high", "high", 1),
    ("medium", "low", 2), ("medium", "medium", 2), ("medium", "high", 2),
    ("low", "high", 2), ("low", "medium", 3), ("low", "low", 3),
])
def test_tier_rule(materiality, complexity, tier):
    assert assign_tier(materiality, complexity) == tier


def test_seed_tiers_match_the_plan():
    assert {r.model_id: r.risk_tier for r in seed_records()} == {"legacy-r-logistic": 1, "python-gradient-boosting": 2, "python-random-forest": 3}


def test_committed_inventory_matches_seed():
    committed = load_inventory(ROOT / "inventory" / "model_inventory.json")
    assert [(r.model_id, r.risk_tier) for r in committed] == [(r.model_id, r.risk_tier) for r in seed_records()]


def test_stored_tier_cannot_override_the_rule():
    data = get_record(seed_records(), "legacy-r-logistic").model_dump()
    data["risk_tier"] = 3
    assert InventoryRecord.model_validate(data).risk_tier == 1


def test_round_trip(tmp_path):
    path = tmp_path / "inventory.json"
    records = seed_records()
    save_inventory(records, path)
    assert load_inventory(path) == records
    assert json.loads(path.read_text())[0]["risk_tier"] == 1


def test_update_record_validates_and_recomputes():
    records = seed_records()
    updated = update_record(records, "python-random-forest", materiality="high", documentation_status="pending_review")
    assert get_record(updated, "python-random-forest").risk_tier == 1
    assert get_record(records, "python-random-forest").risk_tier == 3  # original list unchanged
    with pytest.raises(ValidationError):
        update_record(records, "legacy-r-logistic", documentation_status="done")
    with pytest.raises(ValueError, match="derived"):
        update_record(records, "legacy-r-logistic", risk_tier=3)
    with pytest.raises(KeyError):
        get_record(records, "XX-000")


def test_rationale_template_without_llm():
    text, source = draft_rationale(get_record(seed_records(), "python-gradient-boosting"))
    assert source == "rule_template" and text.startswith("Tier 2")


def test_llm_rationale_kept_only_if_it_names_the_computed_tier():
    lr = get_record(seed_records(), "legacy-r-logistic")
    assert draft_rationale(lr, OneShot("This is Tier 1 because materiality is high."))[1] == "llm_draft"
    assert draft_rationale(lr, OneShot("This should be Tier 2."))[1] == "rule_template"
    assert draft_rationale(lr, OneShot("High materiality model."))[1] == "rule_template"


def test_replayed_rationale_is_accepted():
    lr = get_record(seed_records(), "legacy-r-logistic")
    assert draft_rationale(lr, ReplayLLM(ROOT / "tests/fixtures/p2/replay_lr"))[1] == "llm_draft"


def test_ss1_23_mapping_covers_the_five_stages():
    mapping = json.loads((ROOT / "governance" / "ss1_23_mapping.json").read_text())
    assert [s["stage"] for s in mapping["stages"]] == ["discover", "document", "redevelop", "validate", "monitor"]
    assert "1.3 Model tiering" in mapping["stages"][0]["principles"]
    assert mapping["all_stages"]["principles"][0] == "2. Governance"
    assert len(mapping["outside_prototype"]) == 4
