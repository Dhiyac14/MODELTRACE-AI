"""Approval records, roles and separation-of-duties rules (plan step 14).

Separation of duties:
- role matrix: who may submit and who may decide at each stage;
- four-eyes: the person who submitted a stage cannot decide on it;
- independence (SS1/23 4.1): anyone who submitted (built) the redevelopment cannot validate it;
- agents never take approval actions.
A user may hold several roles (for example a team lead), which is what makes the last three rules bite.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from inventory.registry import Stage
from llm.schemas import utc_now
from workflow.store import JsonList

Role = Literal["developer", "validator", "risk_manager", "monitoring_analyst", "agent"]
ApprovalAction = Literal["submit", "approve", "reject", "request_changes", "reopen", "invalidate"]
Decision = Literal["approve", "reject", "request_changes"]
DECISIONS: frozenset[str] = frozenset({"approve", "reject", "request_changes"})

SUBMIT_ROLES: dict[str, set[str]] = {
    "discover": {"developer"},
    "document": {"developer"},
    "redevelop": {"developer"},
    "validate": {"validator"},
    "monitor": {"monitoring_analyst"},
}
DECIDE_ROLES: dict[str, set[str]] = {stage: {"risk_manager"} for stage in SUBMIT_ROLES}
REOPEN_ROLES: set[str] = {"risk_manager"}
USERS_PATH = Path("governance/users.json")


class User(BaseModel):
    user_id: str
    name: str
    roles: list[Role]


class ApprovalRecord(BaseModel):
    record_id: str
    model_id: str
    stage: Stage
    action: ApprovalAction
    actor: str
    role: str
    timestamp: str
    comment: str = ""
    evidence_ref: str = ""
    evidence_sha256: str = ""


class ApprovalLog:
    def __init__(self, path: str | Path) -> None:
        self._store = JsonList(path, ApprovalRecord)

    def records(self, model_id: str | None = None) -> list[ApprovalRecord]:
        return [r for r in self._store.all() if model_id is None or r.model_id == model_id]

    def append(self, record: ApprovalRecord) -> ApprovalRecord:
        return self._store.append(record)


def load_users(path: str | Path = USERS_PATH) -> list[User]:
    return [User.model_validate(u) for u in json.loads(Path(path).read_text(encoding="utf-8"))]


def allowed_roles(stage: str, action: str) -> set[str]:
    if action == "submit":
        return SUBMIT_ROLES[stage]
    if action in DECISIONS:
        return DECIDE_ROLES[stage]
    return REOPEN_ROLES  # reopen, and the invalidations it causes


def acting_role(user: User, stage: str, action: str) -> str:
    matches = [r for r in user.roles if r in allowed_roles(stage, action)]
    return matches[0] if matches else user.roles[0]


def check_duties(stage: str, action: str, user: User, history: list[ApprovalRecord]) -> list[str]:
    """Separation-of-duties problems for ``user`` taking ``action``; empty means allowed."""
    if "agent" in user.roles:
        return ["Agents cannot take approval actions; a human must."]
    problems = []
    needed = allowed_roles(stage, action)
    if not needed & set(user.roles):
        problems.append(f"'{action}' at {stage} needs role {' or '.join(sorted(needed))}; {user.name} has {', '.join(user.roles)}.")
    if action in DECISIONS:
        submits = [r for r in history if r.stage == stage and r.action == "submit"]
        if submits and submits[-1].actor == user.user_id:
            problems.append("Four-eyes rule: the person who submitted this stage cannot decide on it.")
    if stage == "validate" and action != "reopen":
        redevelopers = {r.actor for r in history if r.stage == "redevelop" and r.action == "submit"}
        if user.user_id in redevelopers:
            problems.append("Independence (SS1/23 4.1): people who built the redevelopment cannot validate it.")
    return problems
