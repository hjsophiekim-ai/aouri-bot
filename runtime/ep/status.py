from __future__ import annotations

from dataclasses import dataclass


EP_STATUSES = [
    "draft",
    "aouribot_in_progress",
    "aouribot_completed",
    "legal_review_pending",
    "approval_pending",
    "completed",
    "error",
]


def is_valid_status(status: str) -> bool:
    return status in EP_STATUSES


STATUS_TRANSITIONS = {
    "draft": {"aouribot_in_progress"},
    "aouribot_in_progress": {"aouribot_completed"},
    "aouribot_completed": {"legal_review_pending", "approval_pending"},
    "legal_review_pending": {"approval_pending", "completed"},
    "approval_pending": {"completed"},
    "completed": set(),
    "error": {"draft", "aouribot_in_progress"},
}


def can_transition(from_status: str, to_status: str) -> bool:
    if from_status not in STATUS_TRANSITIONS:
        return False
    if to_status == "error":
        return True
    return to_status in STATUS_TRANSITIONS[from_status]

