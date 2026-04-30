from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime.ai.config import load_ai_config
from runtime.ai.factory import create_ai_provider
from runtime.law.cache import JsonFileCache
from runtime.law.config import load_law_api_config
from runtime.law.search_service import LawSearchService
from runtime.questions.generator import generate_questions
from runtime.questions.model import question_to_dict
from runtime.services.query_service import ReviewInput, RuleQueryService
from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_level import build_clause_level_result


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
    review_focus: str | None = None,
    intake: dict[str, Any] | None = None,
    source: str = "upload",
) -> dict[str, Any]:
    bundle = build_clause_level_result(
        service=service,
        entity=str(entity),
        contract_type=str(contract_type),
        text=str(text),
        filename=str(filename) if isinstance(filename, str) else None,
        answers=None,
        review_focus=review_focus,
        law_service=None,
        ai_provider=None,
        ai_model=None,
        ai_timeout_sec=None,
        ai_max_tokens=None,
        ai_temperature=None,
        max_clause_law_items=0,
    )
    original_clauses = [
        {
            "clause_id": c.clause_id,
            "article_number": c.article_number,
            "paragraph_number": c.paragraph_number,
            "item_number": c.item_number,
            "subitem_number": c.subitem_number,
            "display_path": c.display_path,
            "parent_clause_id": c.parent_clause_id,
            "context_text": c.context_text,
            "clause_title": c.title,
            "text": c.text,
        }
        for c in (bundle.clauses or [])
    ]
    pre = bundle.review
    detected_ids = [r.get("rule_id") for r in pre.get("matched_rules", []) if isinstance(r.get("rule_id"), str)]
    qs = generate_questions(
        entity=entity,
        contract_type=contract_type,
        detected_rule_ids=detected_ids,
        law_topics=None,
        contract_text=text,
        clause_results=bundle.clause_results,
        max_questions=5,
        review_focus=review_focus,
    )

    now = _utc_now_iso()
    session_id = uuid4().hex
    doc = {
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "rules_sha256": _rules_sha256(),
        "source": source,
        "input": {"filename": filename, "review_focus": (review_focus or None)},
        "intake": dict(intake or {}),
        "extraction": dict(extraction),
        "classification": dict(classification),
        "detected_rule_ids": detected_ids,
        "questions": [question_to_dict(q) for q in qs],
        "answers": {},
        "review_result": None,
        "original_clauses": original_clauses,
        "text": text,
        "entity": entity,
        "contract_type": contract_type,
    }
    save_session(doc)
    return doc


def create_text_session(
    *,
    entity: str,
    contract_type: str,
    filename: str | None,
    text: str,
    review_focus: str | None,
    extraction: dict[str, Any] | None = None,
    classification: dict[str, Any] | None = None,
    detected_rule_ids: list[str] | None = None,
    questions: list[dict[str, Any]] | None = None,
    intake: dict[str, Any] | None = None,
    source: str = "api_text",
) -> dict[str, Any]:
    now = _utc_now_iso()
    session_id = uuid4().hex
    clauses, _ = extract_clauses(str(text or ""))
    original_clauses = [
        {
            "clause_id": c.clause_id,
            "article_number": c.article_number,
            "paragraph_number": c.paragraph_number,
            "item_number": c.item_number,
            "subitem_number": c.subitem_number,
            "display_path": c.display_path,
            "parent_clause_id": c.parent_clause_id,
            "context_text": c.context_text,
            "clause_title": c.title,
            "text": c.text,
        }
        for c in (clauses or [])
    ]
    doc = {
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "rules_sha256": _rules_sha256(),
        "source": source,
        "input": {"filename": filename, "review_focus": (review_focus or None)},
        "intake": dict(intake or {}),
        "extraction": dict(extraction or {"success": True, "method": "api_text"}),
        "classification": dict(classification or {"entity": entity, "contract_type": contract_type}),
        "detected_rule_ids": [str(x) for x in (detected_rule_ids or []) if isinstance(x, str) and x.strip()],
        "questions": list(questions or []),
        "answers": {},
        "review_result": None,
        "review_result_sig": None,
        "review_result_fast": None,
        "review_result_fast_sig": None,
        "original_clauses": original_clauses,
        "text": str(text or ""),
        "entity": str(entity or "all"),
        "contract_type": str(contract_type or "all"),
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
    review_focus = (doc.get("input") or {}).get("review_focus")
    answers = doc.get("answers") or {}
    base_sig = sha256(
        json.dumps(
            {
                "entity": entity,
                "contract_type": contract_type,
                "filename": filename,
                "text_sha256": sha256(str(text).encode("utf-8", errors="replace")).hexdigest(),
                "answers": answers if isinstance(answers, dict) else {},
                "review_focus": review_focus if isinstance(review_focus, str) else None,
                "mode": "deep",
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if isinstance(doc.get("review_result"), dict) and doc.get("review_result_sig") == base_sig:
        return doc["review_result"]
    law_cfg = load_law_api_config()
    law_cache = JsonFileCache(path=DATA_DIR / "law_cache.json")
    law_service = LawSearchService(cfg=law_cfg, cache=law_cache) if law_cfg.enabled and law_cfg.api_key else None
    cfg = load_ai_config()
    ai_provider = create_ai_provider(cfg) if cfg.provider == "openai" and cfg.api_key else None
    bundle = build_clause_level_result(
        service=service,
        entity=str(entity),
        contract_type=str(contract_type),
        text=str(text),
        filename=str(filename) if isinstance(filename, str) else None,
        answers=answers if isinstance(answers, dict) else None,
        review_focus=review_focus if isinstance(review_focus, str) else None,
        law_service=law_service,
        ai_provider=ai_provider,
        ai_model=cfg.model if ai_provider else None,
        ai_timeout_sec=cfg.timeout_sec if ai_provider else None,
        ai_max_tokens=min(max(cfg.max_tokens, 2400), 3600) if ai_provider else None,
        ai_temperature=cfg.temperature if ai_provider else None,
        max_clause_law_items=2,
    )
    result = dict(bundle.review)
    result["clause_results"] = bundle.clause_results
    result["clause_meta"] = bundle.meta
    original_clauses = doc.get("original_clauses")
    if not isinstance(original_clauses, list) or not original_clauses:
        original_clauses = [
            {
                "clause_id": c.clause_id,
                "article_number": c.article_number,
                "paragraph_number": c.paragraph_number,
                "item_number": c.item_number,
                "subitem_number": c.subitem_number,
                "display_path": c.display_path,
                "parent_clause_id": c.parent_clause_id,
                "context_text": c.context_text,
                "clause_title": c.title,
                "text": c.text,
            }
            for c in (bundle.clauses or [])
        ]
        doc["original_clauses"] = original_clauses
    result["original_clauses"] = original_clauses
    meta_ai = (bundle.meta.get("ai") if isinstance(bundle.meta, dict) else None) if isinstance(bundle.meta, dict) else None
    ai_enabled = bool(ai_provider) and cfg.provider == "openai"
    ai_used = bool(isinstance(meta_ai, dict) and meta_ai.get("used"))
    result["ai"] = {
        "enabled": ai_enabled,
        "provider": "openai" if ai_enabled else "mock",
        "model": cfg.model,
        "used": ai_used,
        "detail": meta_ai,
    }
    doc["review_result"] = result
    doc["review_result_sig"] = base_sig
    doc["updated_at"] = _utc_now_iso()
    save_session(doc)
    return result


def run_review_with_session_fast(service: RuleQueryService, session_id: str) -> dict[str, Any]:
    doc = load_session(session_id)
    text = doc.get("text", "") or ""
    entity = doc.get("entity", "all")
    contract_type = doc.get("contract_type", "all")
    filename = (doc.get("input") or {}).get("filename")
    review_focus = (doc.get("input") or {}).get("review_focus")
    answers = doc.get("answers") or {}
    base_sig = sha256(
        json.dumps(
            {
                "entity": entity,
                "contract_type": contract_type,
                "filename": filename,
                "text_sha256": sha256(str(text).encode("utf-8", errors="replace")).hexdigest(),
                "answers": answers if isinstance(answers, dict) else {},
                "review_focus": review_focus if isinstance(review_focus, str) else None,
                "mode": "fast",
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if isinstance(doc.get("review_result_fast"), dict) and doc.get("review_result_fast_sig") == base_sig:
        return doc["review_result_fast"]

    bundle = build_clause_level_result(
        service=service,
        entity=str(entity),
        contract_type=str(contract_type),
        text=str(text),
        filename=str(filename) if isinstance(filename, str) else None,
        answers=answers if isinstance(answers, dict) else None,
        review_focus=review_focus if isinstance(review_focus, str) else None,
        law_service=None,
        ai_provider=None,
        ai_model=None,
        ai_timeout_sec=None,
        ai_max_tokens=None,
        ai_temperature=None,
        max_clause_law_items=0,
    )
    result = dict(bundle.review)
    result["clause_results"] = bundle.clause_results
    result["clause_meta"] = bundle.meta
    original_clauses = doc.get("original_clauses")
    if not isinstance(original_clauses, list) or not original_clauses:
        original_clauses = [
            {
                "clause_id": c.clause_id,
                "article_number": c.article_number,
                "paragraph_number": c.paragraph_number,
                "item_number": c.item_number,
                "subitem_number": c.subitem_number,
                "display_path": c.display_path,
                "parent_clause_id": c.parent_clause_id,
                "context_text": c.context_text,
                "clause_title": c.title,
                "text": c.text,
            }
            for c in (bundle.clauses or [])
        ]
        doc["original_clauses"] = original_clauses
    result["original_clauses"] = original_clauses
    result["law_search"] = {
        "enabled": False,
        "note": "fast_mode",
        "queries": [],
        "results": {"laws": [], "precedents": [], "interpretations": [], "admin_rules": [], "local_ordinances": []},
        "errors": [],
    }
    result["ai"] = {
        "enabled": False,
        "provider": "mock",
        "model": None,
        "used": False,
        "detail": {"enabled": False, "used": False, "selected_clause_ids": [], "selected_count": 0},
    }
    doc["review_result_fast"] = result
    doc["review_result_fast_sig"] = base_sig
    doc["updated_at"] = _utc_now_iso()
    save_session(doc)
    return result

