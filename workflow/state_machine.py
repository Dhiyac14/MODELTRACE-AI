"""Five-stage lifecycle with a human approval gate at every stage (plan step 14).

Stage status is derived from the approval log, which is the single source of truth; the inventory
record's status fields are a projection refreshed after every action.

Rules:
- a stage can be submitted only when every earlier stage is approved and its evidence file exists;
- approve / reject / request changes need a pending review and pass the separation-of-duties checks;
- approval is refused if the evidence file changed after submission, and Redevelop can only be
  approved when the parity report says ``"passed": true``;
- reject needs a reopen by a risk manager before resubmission; request changes allows resubmission;
- reopening a stage invalidates every later stage, which must then be reviewed again.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from inventory.registry import InventoryRecord, get_record, load_inventory, save_inventory, update_record
from llm.schemas import utc_now
from workflow.alerts import RULES as ALERT_RULES
from workflow.alerts import STATUS_AFTER as ALERT_STATUS_AFTER
from workflow.alerts import AlertReview, AlertReviewLog, alert_status, check_alert_action
from workflow.approvals import DECISIONS, ApprovalLog, ApprovalRecord, User, acting_role, check_duties
from workflow.artifacts import STAGE_EVIDENCE, Artifacts
from workflow.audit import AuditLog
from workflow.store import new_id

STAGES: tuple[str, ...] = ("discover", "document", "redevelop", "validate", "monitor")
LEGACY_LANGUAGES = frozenset({"R", "SAS"})
STATUS_AFTER = {
    "submit": "pending_review",
    "approve": "approved",
    "reject": "rejected",
    "request_changes": "changes_requested",
    "reopen": "in_progress",
    "invalidate": "invalidated",
}
SUBMITTABLE = frozenset({"not_started", "in_progress", "changes_requested", "invalidated"})
REOPENABLE = frozenset({"approved", "rejected"})
DONE = frozenset({"approved", "not_applicable"})


class WorkflowError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def applies(record: InventoryRecord, stage: str) -> bool:
    """Redevelopment only applies to legacy (R or SAS) models."""
    return stage != "redevelop" or record.language in LEGACY_LANGUAGES


class Workflow:
    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)
        self.artifacts = Artifacts(self.root)
        self.approvals = ApprovalLog(self.root / "governance/approval_log.json")
        self.alert_reviews = AlertReviewLog(self.root / "governance/alert_reviews.json")
        self.audit = AuditLog(self.root / "governance/audit_log.json")
        self.inventory_path = self.root / "inventory/model_inventory.json"

    # ------------------------------------------------------------------ state
    def records(self) -> list[InventoryRecord]:
        return load_inventory(self.inventory_path)

    def record(self, model_id: str) -> InventoryRecord:
        return get_record(self.records(), model_id)

    def history(self, model_id: str) -> list[ApprovalRecord]:
        return self.approvals.records(model_id)

    def statuses(self, model_id: str) -> dict[str, str]:
        record, history = self.record(model_id), self.history(model_id)
        out = {}
        for stage in STAGES:
            mine = [r for r in history if r.stage == stage]
            out[stage] = "not_applicable" if not applies(record, stage) else STATUS_AFTER[mine[-1].action] if mine else "not_started"
        return out

    def current_stage(self, model_id: str) -> str | None:
        """The first stage that is not yet approved; None when the whole lifecycle is approved."""
        return next((s for s, status in self.statuses(model_id).items() if status not in DONE), None)

    def stale_approvals(self, model_id: str) -> list[str]:
        """Approved stages whose evidence file changed after the approval."""
        stale = []
        for stage, status in self.statuses(model_id).items():
            if status == "approved":
                approval = [r for r in self.history(model_id) if r.stage == stage and r.action == "approve"][-1]
                if self.artifacts.sha256(STAGE_EVIDENCE[stage], model_id) != approval.evidence_sha256:
                    stale.append(stage)
        return stale

    # ------------------------------------------------------------------ checks
    def check(self, model_id: str, stage: str, action: str, user: User) -> list[str]:
        """Every reason ``action`` is not allowed right now; an empty list means it is allowed."""
        statuses = self.statuses(model_id)
        status = statuses[stage]
        if status == "not_applicable":
            return [f"{stage} does not apply to this model."]
        history = self.history(model_id)
        problems = check_duties(stage, action, user, history)
        kind = STAGE_EVIDENCE[stage]
        if action == "submit":
            if status not in SUBMITTABLE:
                problems.append(f"{stage} is {status}; it can only be submitted when it is not started, in progress, "
                                "changes requested or invalidated.")
            problems += [f"{s} must be approved first (it is {statuses[s]})."
                         for s in STAGES[: STAGES.index(stage)] if statuses[s] not in DONE]
            if not self.artifacts.exists(kind, model_id):
                problems.append(f"No evidence yet: {self.artifacts.relpath(kind, model_id)} does not exist.")
        elif action in DECISIONS:
            if status != "pending_review":
                problems.append(f"{stage} is {status}; only a pending review can be decided.")
            else:
                submitted = [r for r in history if r.stage == stage and r.action == "submit"][-1]
                if self.artifacts.sha256(kind, model_id) != submitted.evidence_sha256:
                    problems.append("The evidence file changed after it was submitted; it must be resubmitted.")
            if action == "approve" and stage == "redevelop":
                parity = self.artifacts.load("parity", model_id) or {}
                if parity.get("passed") is not True:
                    problems.append("Parity tests have not passed, so the migration cannot be approved.")
        elif action == "reopen" and status not in REOPENABLE:
            problems.append(f"{stage} is {status}; only an approved or rejected stage can be reopened.")
        return problems

    # ------------------------------------------------------------------ actions
    def submit(self, model_id: str, stage: str, user: User, comment: str = "") -> ApprovalRecord:
        self._require(self.check(model_id, stage, "submit", user))
        return self._append(model_id, stage, "submit", user, comment, with_evidence=True)

    def decide(self, model_id: str, stage: str, user: User, decision: str, comment: str = "") -> ApprovalRecord:
        if decision not in DECISIONS:
            raise ValueError(f"unknown decision {decision!r}")
        problems = self.check(model_id, stage, decision, user)
        if decision != "approve" and not comment.strip():
            problems.append("A comment is required to reject or request changes.")
        self._require(problems)
        return self._append(model_id, stage, decision, user, comment, with_evidence=True)

    def reopen(self, model_id: str, stage: str, user: User, reason: str) -> list[ApprovalRecord]:
        problems = self.check(model_id, stage, "reopen", user)
        if not reason.strip():
            problems.append("A reason is required to reopen a stage.")
        self._require(problems)
        written = [self._append(model_id, stage, "reopen", user, reason)]
        statuses = self.statuses(model_id)
        for later in STAGES[STAGES.index(stage) + 1 :]:
            if statuses[later] not in ("not_started", "invalidated", "not_applicable"):
                written.append(self._append(model_id, later, "invalidate", user, f"{stage} was reopened: {reason}"))
        return written

    def review_alert(self, model_id: str, alert_id: str, user: User, action: str, comment: str = "") -> AlertReview:
        status = alert_status(self.alert_reviews.reviews(model_id), alert_id)
        self._require(check_alert_action(action, status, user, comment))
        review = self.alert_reviews.append(AlertReview(
            review_id=new_id("ARV"), alert_id=alert_id, model_id=model_id, action=action, actor=user.user_id,
            role=next(r for r in user.roles if r in ALERT_RULES[action][1]), timestamp=utc_now(), comment=comment,
        ))
        self.audit.record(user.user_id, review.role, f"alert:{action}", model_id, "monitor",
                          {"alert_id": alert_id, "status": ALERT_STATUS_AFTER[action], "comment": comment})
        if action == "request_revalidation":
            if self.statuses(model_id)["validate"] in REOPENABLE:
                self.reopen(model_id, "validate", user, f"Monitoring alert {alert_id}: {comment}")
            else:
                self.audit.record(user.user_id, review.role, "revalidation_noted", model_id, "validate",
                                  {"alert_id": alert_id, "note": "Validate stage is not approved yet; nothing to reopen."})
        return review

    def update_sources(self, model_id: str, user: User, source_files: list[str], legacy_document: str | None) -> None:
        records = update_record(self.records(), model_id, source_files=source_files, legacy_document=legacy_document)
        save_inventory(records, self.inventory_path)
        self.audit.record(user.user_id, user.roles[0], "inventory:update_sources", model_id, "discover",
                          {"source_files": source_files, "legacy_document": legacy_document})

    def update_record_fields(self, model_id: str, user: User, action: str, **changes: Any) -> None:
        save_inventory(update_record(self.records(), model_id, **changes), self.inventory_path)
        self.audit.record(user.user_id, user.roles[0], action, model_id, None, {k: str(v)[:500] for k, v in changes.items()})

    def log_agent_run(self, model_id: str, stage: str, agent: str, triggered_by: User, details: dict[str, Any]) -> None:
        """Agents are recorded as their own actor, with the human who started them."""
        self.audit.record(f"agent:{agent}", "agent", "agent_run", model_id, stage,
                          {"triggered_by": triggered_by.user_id, **details})

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _require(problems: list[str]) -> None:
        if problems:
            raise WorkflowError(problems)

    def _append(self, model_id: str, stage: str, action: str, user: User, comment: str,
                with_evidence: bool = False) -> ApprovalRecord:
        kind = STAGE_EVIDENCE[stage]
        record = self.approvals.append(ApprovalRecord(
            record_id=new_id("APR"), model_id=model_id, stage=stage, action=action, actor=user.user_id,
            role=acting_role(user, stage, action), timestamp=utc_now(), comment=comment,
            evidence_ref=self.artifacts.relpath(kind, model_id) if with_evidence else "",
            evidence_sha256=self.artifacts.sha256(kind, model_id) if with_evidence else "",
        ))
        self.audit.record(user.user_id, record.role, f"approval:{action}", model_id, stage,
                          {"record_id": record.record_id, "comment": comment,
                           "evidence_ref": record.evidence_ref, "evidence_sha256": record.evidence_sha256})
        self._sync_inventory(model_id)
        return record

    def _sync_inventory(self, model_id: str) -> None:
        st = self.statuses(model_id)
        records = update_record(
            self.records(), model_id,
            tier_status=st["discover"], documentation_status=st["document"], migration_status=st["redevelop"],
            validation_status=st["validate"], monitoring_status=st["monitor"],
            lifecycle_stage=self.current_stage(model_id) or "monitor",
            approval_history=[r.record_id for r in self.history(model_id)],
        )
        save_inventory(records, self.inventory_path)
