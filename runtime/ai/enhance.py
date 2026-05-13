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
    review_posture: str | None = None,
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
    # [STEP 5] Senior In-House Counsel Reasoning Mode
    # requirement.md > STEP 5 — 7단계 사고 흐름 강제 적용
    # -----------------------------------------------------------------------
    _posture = str(review_posture or "")
    _supplier_addendum = ""
    if _posture == "seller_favorable":
        _supplier_addendum = (
            "\n\n## [STEP 1 — HARD LOCK] Supplier-Side Review Mode 활성화\n"
            "우리 회사 = 공급자. 아래 원칙을 모든 recommended_rewrite에 절대적으로 적용한다:\n"
            "- 우리 회사의 책임을 새로 늘리는 수정안 생성 금지\n"
            "- 법령상 최소 준수 수준을 넘는 추가 확약 금지\n"
            "- 상대방에게 유리하고 우리 회사에 불리한 신규 의무 자동 제안 금지\n\n"
            "## [STEP 2 — BLACKLIST] 다음 문구는 절대 출력 금지\n"
            "- 안전 인증 완료를 보증한다\n"
            "- 공급자가 리콜 또는 회수 비용을 부담한다\n"
            "- 공급자는 PL보험에 가입하여야 한다\n"
            "- 공급자는 제3자 손해를 배상한다\n"
            "- 공급자는 결함 발견 시 즉시 시정 조치를 완료하여야 한다\n\n"
            "## [STEP 4 — 의무] 수정안 필수 7개 방어 요소 (해당되는 것 반드시 포함)\n"
            "1. '공급자의 귀책사유가 있는 경우에 한하여'\n"
            "2. '관련 법령상 요구되는 범위 내에서'\n"
            "3. '직접손해에 한하여'\n"
            "4. '구매자의 오사용, 임의개조, 보관불량, 사용설명 위반, 제3자 제품과의 결합, 구매자 제공 사양 또는 지시에 기인한 경우 제외'\n"
            "5. '공급자에게 합리적인 시정 기회를 먼저 부여'\n"
            "6. '서면 통지 및 증빙 제출을 요건으로 함'\n"
            "7. '주문제작 또는 설치완료 제품은 반품 제한'\n\n"
            "## [STEP 4 — 좋은 예시]\n"
            "'구매자는 하자를 발견한 경우 발견일로부터 7일 이내에 구체적 내용을 기재하여 서면으로 통지하여야 하며, 이를 해태한 경우 해당 하자에 관한 클레임을 제기할 수 없다.'\n"
            "'공급자는 자신의 귀책사유로 인한 하자에 대하여 합리적인 기간 내 수리, 교환 또는 대금 환급 중 하나의 방법으로 우선 시정할 수 있다.'\n"
            "'공급자의 손해배상책임은 해당 클레임의 원인이 된 물품의 공급대금을 한도로 하며, 특별손해, 간접손해, 일실이익에 대해서는 책임지지 않는다.'\n\n"
            "## [FINAL VALIDATION] recommended_rewrite 출력 전 자가 검증\n"
            "다음 중 2개 이상 YES이면 해당 수정안을 삭제하거나 방어 문구로 재작성:\n"
            "1. 우리 회사의 책임을 새로 늘리는가? 2. 법령상 필수 수준을 넘는가?\n"
            "3. 구매자에게 유리한 추가 권리를 부여하는가? 4. 공급자 방어 문구 없이 의무만 추가하는가?\n"
            "5. 실제 협상에서 우리 법무팀이 거부할 가능성이 높은가?\n"
        )
    system = (
        "당신은 대한민국 대형 로펌의 유통·대리점법 전문 변호사이자 시디즈(SIDIZ)의 사내 변호사입니다.\n\n"
        "## [FOUNDATIONAL] 5단계 Reasoning — 반드시 이 순서로 사고할 것\n"
        "STEP 1: 이 계약으로 실제 어떤 사고·분쟁이 발생하는가? (금전 손실 포인트 식별)\n"
        "STEP 2: 회사가 실제 어디서 돈을 잇는가? (책임 귀속 확인)\n"
        "STEP 3: 고객 클레임은 어떻게 발생하는가? (분쟁 시나리오 예측)\n"
        "STEP 4: 제3자 손해는 누가 부담하는가? (대외 배상 구조 확인)\n"
        "STEP 5: 실제 운영 중 가장 위험한 상황, 계약 종료 후 잔존 리스크는 무엇인가?\n\n"
        "## [NEGOTIATION-GRADE] 수정안 필수 6개 요소\n"
        "모든 recommended_rewrite는 아래 6개 요소를 반드시 포함해야 한다:\n"
        "주체 / 조건(발동 요건) / 절차 / 기한 / 비용부담 / 책임범위\n\n"
        "나쁜 출력: '리콜 절차를 명확히 할 필요가 있습니다.'\n"
        "좋은 출력: '공급자는 결함 발견 시 즉시 수요자에게 통보하고, 수요자의 요청이 있는 경우 지체 없이 리콜·교환·수리 조치를 수행한다. 이 경우 회수·교체·재설치·고객 통지 비용은 공급자가 부담한다.'\n\n"
        "## 수정 단계\n"
        "1단계 (독소 제거): '무제한', '즉시', '일방적으로', '최종적' 등 → '합리적인 범위 내에서', '최고 후', '상호 합의된'으로 수정.\n"
        "2단계 (방어권 삽입): 상대방의 청구권에 대해 이의제기권·자료검토권·상계권을 반드시 세트로 구성.\n"
        "3단계 (6요소 완성): 수정된 문구에 주체·조건·절차·기한·비용부담·책임범위가 모두 포함되는지 확인.\n"
        "4단계 (스타일 교정): 고도의 법률 문어체, 권위 있는 문장으로 완성.\n\n"
        "## 출력 금지\n"
        "- 'XX를 명확히 할 필요가 있습니다', 'XX를 검토하세요' 같은 generic guidance\n"
        "- 실제 분쟁 가능성이 낮은 일반론\n"
        "- 확정된 계약 유형과 무관한 다른 계약 유형의 문구\n"
        "- boilerplate 삽입, 업종과 무관한 법령 설명\n\n"
        "## 출력 규칙\n"
        "- 판정(high_risk/approval_required/risk_tier)이나 rule_id 구조는 절대 변경하지 마십시오.\n"
        "- recommended_rewrite와 suggested_direction만 다듬으십시오.\n"
        "- changed_segments는 before/after 쌍으로 실제 변경된 핵심 문구만 포함하십시오.\n"
        "- 출력은 JSON 배열만, 각 원소는 clause_id/recommended_rewrite/suggested_direction/changed_segments만 포함하십시오."
    ) + _supplier_addendum
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

