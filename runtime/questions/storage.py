from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime.questions.generator import generate_questions
from runtime.questions.model import question_to_dict
from runtime.services.query_service import ReviewInput, RuleQueryService


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SESSIONS_DIR = DATA_DIR / "question_sessions"
RULES_RESOURCE_PATH = Path(__file__).resolve().parents[1] / "resources" / "review_rules_master.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _rules_sha256() -> str:
    b = RULES_RESOURCE_PATH.read_bytes()
    return sha256(b).hexdigest()


@dataclass
class QuestionSession:
    session_id: str
    created_at: str
    updated_at: str
    rules_sha256: str
    input: dict[str, Any]
    extraction: dict[str, Any]
    classification: dict[str, Any]
    detected_rule_ids: list[str]
    questions: list[dict[str, Any]]
    answers: dict[str, Any]
    review_result: dict[str, Any] | None


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def save_session(doc: dict[str, Any]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    p = _session_path(doc["session_id"])
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(session_id: str) -> dict[str, Any]:
    p = _session_path(session_id)
    return json.loads(p.read_text(encoding="utf-8"))


def create_session(
    service: RuleQueryService,
    entity: str,
    contract_type: str,
    filename: str | None,
    extraction: dict[str, Any],
    text: str,
    classification: dict[str, Any],
    intake: dict[str, Any] | None = None,
    source: str = "upload",
) -> dict[str, Any]:
    pre = service.analyze(ReviewInput(entity=entity, contract_type=contract_type, text=text, filename=filename))
    detected_ids = [r.get("rule_id") for r in pre.get("matched_rules", []) if isinstance(r.get("rule_id"), str)]
    qs = generate_questions(entity=entity, contract_type=contract_type, detected_rule_ids=detected_ids)

    now = _utc_now_iso()
    session_id = uuid4().hex
    doc = {
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "rules_sha256": _rules_sha256(),
        "source": source,
        "input": {"filename": filename},
        "intake": dict(intake or {}),
        "extraction": dict(extraction),
        "classification": dict(classification),
        "detected_rule_ids": detected_ids,
        "questions": [question_to_dict(q) for q in qs],
        "answers": {},
        "review_result": None,
        "text": text,
        "entity": entity,
        "contract_type": contract_type,
    }
    save_session(doc)
    return doc


def save_answers(session_id: str, answers: dict[str, Any]) -> dict[str, Any]:
    doc = load_session(session_id)
    doc["answers"] = dict(answers)
    doc["updated_at"] = _utc_now_iso()
    save_session(doc)
    return doc


def run_review_with_session(service: RuleQueryService, session_id: str) -> dict[str, Any]:
    doc = load_session(session_id)
    text = doc.get("text", "") or ""
    entity = doc.get("entity", "all")
    contract_type = doc.get("contract_type", "all")
    filename = (doc.get("input") or {}).get("filename")
    answers = doc.get("answers") or {}
    result = service.analyze(
        ReviewInput(entity=entity, contract_type=contract_type, text=text, filename=filename, answers=answers)
    )
    doc["review_result"] = result
    doc["updated_at"] = _utc_now_iso()
    save_session(doc)
    return result

