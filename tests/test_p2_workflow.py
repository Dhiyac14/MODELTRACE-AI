"""Person 2: five-stage approval workflow, separation of duties and inventory sync."""
import json
from pathlib import Path

import pytest

from inventory.registry import save_inventory, seed_records
from workflow.approvals import load_users
from workflow.artifacts import Artifacts
from workflow.state_machine import STAGES, Workflow, WorkflowError

ROOT = Path(__file__).resolve().parents[1]
USERS = {u.user_id: u for u in load_users(ROOT / "governance/users.json")}
DEV, VAL, MRM, MON, LEAD = (USERS[k] for k in ("dev.alex", "val.sam", "mrm.jordan", "mon.riley", "lead.taylor"))
LR = "LR-R-001"
SUBMITTER = {"discover": DEV, "document": DEV, "redevelop": DEV, "validate": VAL, "monitor": MON}


@pytest.fixture
def wf(tmp_path) -> Workflow:
    (tmp_path / "inventory").mkdir()
    save_inventory(seed_records(), tmp_path / "inventory/model_inventory.json")
    return Workflow(tmp_path)


def evidence(wf: Workflow, stage: str, model_id: str = LR, **data) -> None:
    kind = {"discover": "discovery", "document": "model_card", "redevelop": "parity",
            "validate": "validation", "monitor": "monitoring"}[stage]
    path = wf.artifacts.path(kind, model_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stage": stage, **data}))


def approve(wf: Workflow, stage: str, model_id: str = LR) -> None:
    evidence(wf, stage, model_id, passed=True)
    wf.submit(model_id, stage, SUBMITTER[stage])
    wf.decide(model_id, stage, MRM, "approve")


def problems_of(fn) -> list[str]:
    with pytest.raises(WorkflowError) as exc:
        fn()
    return exc.value.problems


def test_initial_state(wf):
    assert wf.statuses(LR) == dict.fromkeys(STAGES, "not_started")
    assert wf.statuses("GB-PY-002")["redevelop"] == "not_applicable"
    assert wf.current_stage(LR) == "discover"


def test_full_lifecycle_and_inventory_sync(wf):
    for stage in STAGES:
        approve(wf, stage)
    assert set(wf.statuses(LR).values()) == {"approved"}
    assert wf.current_stage(LR) is None
    record = wf.record(LR)
    assert (record.tier_status, record.documentation_status, record.migration_status,
            record.validation_status, record.monitoring_status) == ("approved",) * 5
    assert len(record.approval_history) == 10
    assert wf.audit.verify() == [] and len(wf.audit.events()) == 10


def test_python_model_skips_redevelopment(wf):
    for stage in ("discover", "document", "validate", "monitor"):
        approve(wf, stage, "GB-PY-002")
    assert wf.current_stage("GB-PY-002") is None


def test_submission_needs_evidence_and_earlier_approvals(wf):
    assert any("No evidence" in p for p in problems_of(lambda: wf.submit(LR, "discover", DEV)))
    evidence(wf, "document")
    assert any("discover must be approved first" in p for p in problems_of(lambda: wf.submit(LR, "document", DEV)))


def test_role_matrix_and_agents(wf):
    evidence(wf, "discover")
    assert any("needs role developer" in p for p in problems_of(lambda: wf.submit(LR, "discover", VAL)))
    wf.submit(LR, "discover", DEV)
    assert any("needs role risk_manager" in p for p in problems_of(lambda: wf.decide(LR, "discover", VAL, "approve")))
    agent = USERS["dev.alex"].model_copy(update={"user_id": "agent:discovery", "roles": ["agent"]})
    assert problems_of(lambda: wf.decide(LR, "discover", agent, "approve")) == ["Agents cannot take approval actions; a human must."]


def test_four_eyes_rule_for_a_user_with_two_roles(wf):
    evidence(wf, "discover")
    wf.submit(LR, "discover", LEAD)
    assert any("Four-eyes" in p for p in problems_of(lambda: wf.decide(LR, "discover", LEAD, "approve")))
    wf.decide(LR, "discover", MRM, "approve")


def test_redeveloper_cannot_validate(wf):
    for stage in ("discover", "document"):
        approve(wf, stage)
    evidence(wf, "redevelop", passed=True)
    wf.submit(LR, "redevelop", LEAD)
    wf.decide(LR, "redevelop", MRM, "approve")
    evidence(wf, "validate")
    wf.submit(LR, "validate", VAL)
    assert any("Independence" in p for p in problems_of(lambda: wf.decide(LR, "validate", LEAD, "approve")))
    wf.decide(LR, "validate", MRM, "approve")


def test_failed_parity_blocks_approval_but_not_rejection(wf):
    for stage in ("discover", "document"):
        approve(wf, stage)
    evidence(wf, "redevelop", passed=False)
    wf.submit(LR, "redevelop", DEV)
    assert any("Parity tests have not passed" in p for p in problems_of(lambda: wf.decide(LR, "redevelop", MRM, "approve")))
    wf.decide(LR, "redevelop", MRM, "reject", "Parity failed on the test set.")
    assert wf.statuses(LR)["redevelop"] == "rejected"


def test_reject_needs_reopen_but_request_changes_allows_resubmission(wf):
    evidence(wf, "discover")
    wf.submit(LR, "discover", DEV)
    assert any("comment is required" in p for p in problems_of(lambda: wf.decide(LR, "discover", MRM, "reject")))
    wf.decide(LR, "discover", MRM, "request_changes", "Cite the threshold line.")
    wf.submit(LR, "discover", DEV)
    wf.decide(LR, "discover", MRM, "reject", "Wrong model.")
    assert any("rejected" in p for p in problems_of(lambda: wf.submit(LR, "discover", DEV)))
    wf.reopen(LR, "discover", MRM, "Rework with the right source files.")
    assert wf.statuses(LR)["discover"] == "in_progress"
    wf.submit(LR, "discover", DEV)


def test_reopen_invalidates_later_stages(wf):
    for stage in ("discover", "document", "redevelop"):
        approve(wf, stage)
    assert any("reason is required" in p for p in problems_of(lambda: wf.reopen(LR, "discover", MRM, " ")))
    written = wf.reopen(LR, "discover", MRM, "Outdated source files were used.")
    assert [(r.stage, r.action) for r in written] == [("discover", "reopen"), ("document", "invalidate"), ("redevelop", "invalidate")]
    statuses = wf.statuses(LR)
    assert (statuses["discover"], statuses["document"], statuses["redevelop"], statuses["validate"]) == \
        ("in_progress", "invalidated", "invalidated", "not_started")
    assert wf.record(LR).lifecycle_stage == "discover"


def test_evidence_changed_after_submission_blocks_approval(wf):
    evidence(wf, "discover", version=1)
    wf.submit(LR, "discover", DEV)
    evidence(wf, "discover", version=2)
    assert any("changed after it was submitted" in p for p in problems_of(lambda: wf.decide(LR, "discover", MRM, "approve")))


def test_stale_approval_is_reported(wf):
    approve(wf, "discover")
    assert wf.stale_approvals(LR) == []
    evidence(wf, "discover", regenerated=True)
    assert wf.stale_approvals(LR) == ["discover"]


def test_gates_ignore_sample_data(wf):
    sample = wf.root / "tests/fixtures/p2/sample_data/reports/discovery"
    sample.mkdir(parents=True)
    (sample / f"{LR}_discovery.json").write_text("{}")
    assert not wf.artifacts.exists("discovery", LR)
    assert Artifacts(wf.root, "tests/fixtures/p2/sample_data").load_for_display("discovery", LR) == (None, None, False)
