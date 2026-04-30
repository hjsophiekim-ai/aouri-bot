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
                "risk_tier": it.get("risk_tier", ""),
                "suggested_direction": it.get("suggested_direction") if isinstance(it.get("suggested_direction"), list) else [],
                "recommended_rewrite": it.get("recommended_rewrite"),
                "fallback_text": it.get("fallback_text") if isinstance(it.get("fallback_text"), list) else [],
                "applied_rules": it.get("applied_rules") if isinstance(it.get("applied_rules"), list) else [],
                "changed_segments": it.get("changed_segments") if isinstance(it.get("changed_segments"), list) else [],
            }
        )

    # -----------------------------------------------------------------------
    # 시디즈(SIDIZ) 사내 변호사 / 유통·대리점법 전문 변호사 역할
    # -----------------------------------------------------------------------
    system = (
        "당신은 대한민국 대형 로펌의 유통·대리점법 전문 변호사이자 시디즈(SIDIZ)의 사내 변호사입니다. "
        "단순한 문구 추가가 아니라, 상대방이 제시한 독소 조항을 무력화하고 당사의 실질적 이익을 방어하는 "
        "'전략적 수정'을 수행하십시오.\n\n"
        "## 검토 원칙\n"
        "1. 단순 템플릿 지양: 조항 끝에 [추가]라고 붙이는 방식은 하수입니다. "
        "원문의 문장 구조를 해체하고, 당사에게 유리한 조건을 '전제 조건'이나 '예외 조항'으로 문장 내에 직접 삽입하십시오.\n"
        "2. 실질적 리스크 포착: '협의하여 정한다'와 같은 모호한 문구는 "
        "'당사의 사전 서면 승인을 득하여야 하며, 불성립 시 당사의 결정에 따른다'와 같이 강한 통제권으로 치환하십시오.\n"
        "3. 시디즈 비즈니스 특화: 대리점 계약 시 '경영간섭'으로 오해받지 않으면서도 "
        "'브랜드 가이드라인'을 강제할 수 있는 정교한 표현 "
        "(예: '품질 유지 및 소비자 보호를 위한 최소한의 기준 제시')을 사용하십시오.\n"
        "4. 가드레일 유연화: 조항의 제목이 무엇이든, 해당 문구에 숨겨진 '비용 전가'나 "
        "'책임 무제한' 리스크가 있다면 주제에 구애받지 말고 방어 문구를 설계하십시오.\n\n"
        "## 수정 단계\n"
        "1단계 (독소 제거): '무제한', '즉시', '일방적으로', '최종적' 등의 표현을 "
        "'합리적인 범위 내에서', '최고 후', '상호 합의된' 등으로 즉시 수정.\n"
        "2단계 (방어권 삽입): 상대방의 청구권에 대해 당사의 이의제기권·자료검토권·상계권을 반드시 세트로 구성.\n"
        "3단계 (스타일 교정): 고도의 법률 문어체를 사용하여 권위 있는 문장으로 완성.\n\n"
        "## 출력 규칙\n"
        "- 판정(high_risk/approval_required/risk_tier)이나 rule_id 구조는 절대 변경하지 마십시오.\n"
        "- recommended_rewrite와 suggested_direction만 다듬으십시오.\n"
        "- changed_segments는 before/after 쌍으로 실제 변경된 핵심 문구만 포함하십시오.\n"
        "- 출력은 JSON 배열만, 각 원소는 clause_id/recommended_rewrite/suggested_direction/changed_segments만 포함하십시오."
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
            cs = upd.get("changed_segments")
            if isinstance(rr, str) and rr.strip():
                nit["recommended_rewrite"] = rr.strip()
            if isinstance(sd, list):
                nit["suggested_direction"] = [str(x).strip() for x in sd if str(x).strip()][:6]
            # changed_segments: AI가 반환한 경우 병합, 없으면 기존 유지
            if isinstance(cs, list) and cs:
                existing = list(nit.get("changed_segments") or [])
                for seg in cs:
                    if isinstance(seg, dict) and seg not in existing:
                        existing.append(seg)
                nit["changed_segments"] = existing[:10]
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

