import pytest

from governance.core import Stage
from governance.decisions import DecisionError
from workflow.lifecycle import LifecycleWorkflow


def test_approval_advances_lifecycle_and_records_audit():
    workflow = LifecycleWorkflow("model-1", "high")
    record = workflow.request_decision("approve", "owner", "validator", "Evidence reviewed")
    assert record.decision == "approve"
    assert workflow.stage == Stage.DOCUMENT
    assert any(event.action == "stage-advanced" for event in workflow.audit_log.events())


def test_separation_of_duties_blocks_self_approval():
    workflow = LifecycleWorkflow("model-1", "high")
    with pytest.raises(DecisionError, match="separation of duties"):
        workflow.request_decision("approve", "owner", "owner", "Not allowed")
