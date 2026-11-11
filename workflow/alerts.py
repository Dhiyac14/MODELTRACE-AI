"""Human review of monitoring alerts (plan step 13: acknowledgement, investigation, escalation).

open -> acknowledged -> investigating -> escalated -> closed
                                                 \\-> revalidation_requested (reopens the Validate stage)
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from workflow.approvals import User
from workflow.store import JsonList

AlertAction = Literal["acknowledge", "investigate", "escalate", "close", "request_revalidation"]
AlertStatus = Literal["open", "acknowledged", "investigating", "escalated", "closed", "revalidation_requested"]

STATUS_AFTER: dict[str, str] = {
    "acknowledge": "acknowledged",
    "investigate": "investigating",
    "escalate": "escalated",
    "close": "closed",
    "request_revalidation": "revalidation_requested",
}
# action -> (statuses it may start from, roles allowed)
RULES: dict[str, tuple[set[str], set[str]]] = {
    "acknowledge": ({"open"}, {"monitoring_analyst"}),
    "investigate": ({"open", "acknowledged"}, {"monitoring_analyst"}),
    "escalate": ({"open", "acknowledged", "investigating"}, {"monitoring_analyst"}),
    "close": ({"acknowledged", "investigating", "escalated"}, {"monitoring_analyst", "risk_manager"}),
    "request_revalidation": ({"escalated"}, {"risk_manager"}),
}
COMMENT_REQUIRED = frozenset({"escalate", "close", "request_revalidation"})


class AlertReview(BaseModel):
    review_id: str
    alert_id: str
    model_id: str
    action: AlertAction
    actor: str
    role: str
    timestamp: str
    comment: str = ""


class AlertReviewLog:
    def __init__(self, path: str | Path) -> None:
        self._store = JsonList(path, AlertReview)

    def reviews(self, model_id: str | None = None) -> list[AlertReview]:
        return [r for r in self._store.all() if model_id is None or r.model_id == model_id]

    def append(self, review: AlertReview) -> AlertReview:
        return self._store.append(review)


def alert_status(reviews: list[AlertReview], alert_id: str) -> str:
    mine = [r for r in reviews if r.alert_id == alert_id]
    return STATUS_AFTER[mine[-1].action] if mine else "open"


def check_alert_action(action: str, status: str, user: User, comment: str) -> list[str]:
    starts, roles = RULES[action]
    problems = []
    if "agent" in user.roles:
        problems.append("Agents cannot review alerts; a human must.")
    if status not in starts:
        problems.append(f"Cannot {action.replace('_', ' ')} an alert that is {status}.")
    if not roles & set(user.roles):
        problems.append(f"'{action}' needs role {' or '.join(sorted(roles))}; {user.name} has {', '.join(user.roles)}.")
    if action in COMMENT_REQUIRED and not comment.strip():
        problems.append(f"A comment is required to {action.replace('_', ' ')}.")
    return problems
