from __future__ import annotations

import json
import ast
from typing import Any

from runtime.ai.http_openai_compatible_provider import build_messages
from runtime.ai.provider import AIMessage, AIProvider, AIRequest
from runtime.ai.safe import sanitize_error_message


def _build_request(
    *,
    model: str,
    system: str,
    user: str,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
) -> AIRequest:
    messages: list[AIMessage] = build_messages(system, user)
    return AIRequest(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_sec=timeout_sec,
    )


def _try_json(content: str) -> Any | None:
    try:
        return json.loads(content)
    except Exception:
        s = (content or "").strip()
        if not s:
            return None
        for a, b in (("[", "]"), ("{", "}")):
            i = s.find(a)
            j = s.rfind(b)
            if i >= 0 and j > i:
                frag = s[i : j + 1].strip()
                try:
                    return json.loads(frag)
                except Exception:
                    try:
                        obj = ast.literal_eval(frag)
                        if isinstance(obj, (list, dict)):
                            return obj
                    except Exception:
                        continue
        return None


def polish_questions(
    *,
    provider: AIProvider,
    model: str,
    questions: list[dict[str, Any]],
    entity: str,
    contract_type: str,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    system = (
        "너는 한국어 법무 검토 보조 UI에서 사용할 질문 문구를 다듬는 도우미다. "
        "질문 의미는 바꾸지 말고, 짧고 자연스럽게 고쳐라. "
        "출력은 JSON 배열만, 각 원소는 question_id/title/description만 포함하라."
    )
    user = json.dumps(
        {
            "entity": entity,
            "contract_type": contract_type,
            "questions": [
                {
                    "question_id": q.get("question_id"),
                    "title": q.get("title"),
                    "description": q.get("description"),
                }
                for q in questions
            ],
        },
        ensure_ascii=False,
    )
    req = _build_request(
        model=model,
        system=system,
        user=user,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    try:
        resp = provider.complete(req)
    except Exception as exc:
        return questions, {"error": sanitize_error_message(str(exc))}

    obj = _try_json(resp.content)
    if not isinstance(obj, list):
        return questions, {"error": "invalid AI response (expected JSON array)"}

    by_id: dict[str, dict[str, Any]] = {}
    for it in obj:
        if not isinstance(it, dict):
            continue
        qid = it.get("question_id")
        if isinstance(qid, str) and qid:
            by_id[qid] = it

    out: list[dict[str, Any]] = []
    for q in questions:
        qid = q.get("question_id")
        upd = by_id.get(qid) if isinstance(qid, str) else None
        if upd:
            nq = dict(q)
            title = upd.get("title")
            desc = upd.get("description")
            if isinstance(title, str) and title.strip():
                nq["title"] = title.strip()
            if isinstance(desc, str):
                nq["description"] = desc.strip()
            out.append(nq)
        else:
            out.append(q)
    meta = {"ok": True, "usage": (resp.usage.__dict__ if resp.usage else None)}
    return out, meta


def prioritize_questions(
    *,
    provider: AIProvider,
    model: str,
    questions: list[dict[str, Any]],
    entity: str,
    contract_type: str,
    contract_text: str,
    clause_headings: list[str] | None,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
    max_questions: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if not questions:
        return questions, None
    mq = max(1, min(int(max_questions), 8))
    system = (
        "너는 계약서 검토를 위한 질문 우선순위 산정 엔진이다. "
        "계약서 원문(요약)과 후보 질문을 보고, '빠졌거나 애매한 조항'을 해소하는 질문을 최우선으로 선택하라. "
        "계약서에 이미 명확히 기재된 내용은 되묻지 않도록 우선순위를 낮춰라. "
        "출력은 JSON 배열만, 각 원소는 question_id/score/reason만 포함하라. "
        f"배열 순서는 우선순위(높은 점수) 순이며, 최대 {mq}개만 반환하라."
    )
    user = json.dumps(
        {
            "entity": entity,
            "contract_type": contract_type,
            "contract_excerpt": str(contract_text or "")[:2400],
            "clause_headings": (clause_headings or [])[:20],
            "candidates": [
                {
                    "question_id": q.get("question_id"),
                    "title": q.get("title"),
                    "description": q.get("description"),
                    "tags": q.get("tags") if isinstance(q.get("tags"), list) else [],
                    "related_rule_ids": q.get("related_rule_ids") if isinstance(q.get("related_rule_ids"), list) else [],
                }
                for q in questions[:12]
            ],
        },
        ensure_ascii=False,
    )
    req = _build_request(
        model=model,
        system=system,
        user=user,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    try:
        resp = provider.complete(req)
    except Exception as exc:
        return questions, {"error": sanitize_error_message(str(exc))}

    obj = _try_json(resp.content)
    if not isinstance(obj, list):
        return questions, {"error": "invalid AI response (expected JSON array)"}

    picked: list[tuple[int, str]] = []
    for it in obj:
        if not isinstance(it, dict):
            continue
        qid = it.get("question_id")
        if not isinstance(qid, str) or not qid:
            continue
        try:
            score = int(it.get("score", 0))
        except Exception:
            score = 0
        picked.append((score, qid))
    if not picked:
        return questions, {"error": "empty prioritization result"}

    order = [qid for _, qid in sorted(picked, key=lambda x: x[0], reverse=True)]
    by_id = {str(q.get("question_id")): q for q in questions if isinstance(q, dict) and isinstance(q.get("question_id"), str)}
    out = [by_id[qid] for qid in order if qid in by_id]
    if not out:
        out = questions
    meta = {"ok": True, "usage": (resp.usage.__dict__ if resp.usage else None)}
    return out[:mq], meta


def polish_revision(
    *,
    provider: AIProvider,
    model: str,
    revision: dict[str, Any],
    entity: str,
    contract_type: str,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    items = revision.get("items")
    if not isinstance(items, list) or not items:
        return revision, None

    compact_items = []
    for it in items[:20]:
        if not isinstance(it, dict):
            continue
        compact_items.append(
            {
                "clause_id": it.get("clause_id"),
                "clause_title": it.get("clause_title"),
                "original_clause": str(it.get("original_clause") or "")[:900],
                "high_risk": bool(it.get("high_risk")),
                "approval_required": bool(it.get("approval_required")),
                "suggested_direction": it.get("suggested_direction") if isinstance(it.get("suggested_direction"), list) else [],
                "recommended_rewrite": it.get("recommended_rewrite"),
                "fallback_text": it.get("fallback_text") if isinstance(it.get("fallback_text"), list) else [],
                "applied_rules": it.get("applied_rules") if isinstance(it.get("applied_rules"), list) else [],
            }
        )

    system = (
        "너는 계약서 조항 수정 제안 문구를 한국어로 더 자연스럽게 다듬는 도우미다. "
        "판정(고위험/결재필요)이나 rule_id 구조는 바꾸지 말고, "
        "recommended_rewrite와 suggested_direction만 다듬어라. "
        "출력은 JSON 배열만, 각 원소는 clause_id/recommended_rewrite/suggested_direction만 포함하라."
    )
    user = json.dumps(
        {"entity": entity, "contract_type": contract_type, "items": compact_items},
        ensure_ascii=False,
    )
    req = _build_request(
        model=model,
        system=system,
        user=user,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    try:
        resp = provider.complete(req)
    except Exception as exc:
        return revision, {"error": sanitize_error_message(str(exc))}

    obj = _try_json(resp.content)
    if not isinstance(obj, list):
        return revision, {"error": "invalid AI response (expected JSON array)"}

    by_id: dict[str, dict[str, Any]] = {}
    for it in obj:
        if not isinstance(it, dict):
            continue
        cid = it.get("clause_id")
        if isinstance(cid, str) and cid:
            by_id[cid] = it

    out_items: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cid = it.get("clause_id")
        upd = by_id.get(cid) if isinstance(cid, str) else None
        if upd:
            nit = dict(it)
            rr = upd.get("recommended_rewrite")
            sd = upd.get("suggested_direction")
            if isinstance(rr, str) and rr.strip():
                nit["recommended_rewrite"] = rr.strip()
            if isinstance(sd, list):
                nit["suggested_direction"] = [str(x).strip() for x in sd if str(x).strip()][:6]
            out_items.append(nit)
        else:
            out_items.append(it)

    out = dict(revision)
    out["items"] = out_items
    meta = {"ok": True, "usage": (resp.usage.__dict__ if resp.usage else None)}
    return out, meta


def polish_draft_text(
    *,
    provider: AIProvider,
    model: str,
    draft_text: str,
    entity: str,
    contract_type: str,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict[str, Any] | None]:
    if not isinstance(draft_text, str) or not draft_text.strip():
        return draft_text, None
    system = (
        "너는 표준 계약서 템플릿 텍스트의 문장 연결과 어투를 다듬는 도우미다. "
        "새 조항을 추가하거나 법률적 판단을 새로 만들지 말고, "
        "원문 구조를 유지하면서 표현만 자연스럽게 정리해라. "
        "출력은 수정된 텍스트만 반환하라."
    )
    user = json.dumps(
        {"entity": entity, "contract_type": contract_type, "draft_text": draft_text[:8000]},
        ensure_ascii=False,
    )
    req = _build_request(
        model=model,
        system=system,
        user=user,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    try:
        resp = provider.complete(req)
    except Exception as exc:
        return draft_text, {"error": sanitize_error_message(str(exc))}
    text = resp.content.strip() if isinstance(resp.content, str) else ""
    if not text:
        return draft_text, {"error": "empty AI response"}
    return text, {"ok": True, "usage": (resp.usage.__dict__ if resp.usage else None)}

