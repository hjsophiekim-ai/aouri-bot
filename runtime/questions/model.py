from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuestionOption:
    value: str
    label: str


@dataclass(frozen=True)
class Question:
    question_id: str
    title: str
    description: str
    answer_type: str
    required: bool
    options: list[QuestionOption]
    tags: list[str]
    related_rule_ids: list[str]


def question_to_dict(q: Question) -> dict[str, Any]:
    return {
        "question_id": q.question_id,
        "title": q.title,
        "description": q.description,
        "answer_type": q.answer_type,
        "required": q.required,
        "options": [{"value": o.value, "label": o.label} for o in q.options],
        "tags": list(q.tags),
        "related_rule_ids": list(q.related_rule_ids),
    }

