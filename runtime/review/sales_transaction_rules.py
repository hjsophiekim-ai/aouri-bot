"""판매/위탁판매/대리판매/중개/판매지원 계약의 범용 Layer-1 결정론적 규칙.

범용 사내변호사형 검토 엔진 전면 보정(2026-09-04 지시, 그림닷컴 판매지원
용역계약 실사례) — 조항번호나 특정 계약(그림닷컴)의 문언을 하드코딩하지
않고, 판매/위탁판매/대리판매/중개/판매지원 성격의 어떤 계약에도 적용되는
5개 문장구조 패턴을 탐지한다:

1. 기존 계약과의 경제적 연계 + 자율적 참여 조항 부재
2. 귀책사유 구분 없는 판매취소 수수료 환수
3. 무제한 확장형 업무범위("기타 ... 요청사항")
4. 일방적 해석권 + 일방 소재지 전속관할
5. (materiality-gated) 소비자 대면 판매 구조인데 소비자/상품책임 배분 없음

`common_legal_risk.py::_apply_common_legal_risk_rules()`의 dispatcher 끝에서
호출된다 — 다른 Layer-1 결정론적 rule과 동일한 위치.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.clause_extraction import ClauseChunk
from runtime.review.transaction_structure_signals import detect_sales_transaction_ambiguity

# ─── 1. 기존 계약 연계 + 자율적 참여 조항 부재 ─────────────────────────────

_RX_SEPARATE_CONTRACT_REFERENCE = re.compile(
    r"별도로.{0,150}(?:계약서|약정서)|(?:계약서|약정서)[^.]{0,150}별도로"
    r"|본\s*(?:계약|약정)(?:서)?(?:와|과)는?\s*별도로",
    re.DOTALL,
)
_RX_CONTRACT_LINKAGE = re.compile(
    r"계약기간과\s*동일|효력을\s*상실한다|중도\s*해지.{0,30}효력.{0,10}상실"
    r"|(?:계약|약정)이\s*(?:중도\s*)?해지.{0,20}본\s*(?:계약|약정)도",
    re.DOTALL,
)
_RX_VOLUNTARY_PARTICIPATION_CLAUSE = re.compile(
    r"자율적\s*의사|자유로운\s*의사|불이익(?:이|을)?\s*(?:발생하지|주지)\s*아니한다|불이익\s*없이",
)
_RX_EXISTING_DEALER_SIGNAL = re.compile(r"대리점|위탁판매|가맹")


def _apply_linked_contract_dependency_check(
    clause_results: list[dict[str, Any]],
    full_text: str,
    clauses: list[ClauseChunk] | None = None,
) -> None:
    existing = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if "clr_linked_contract_dependency_no_voluntary_clause" in existing:
        return
    text = full_text or ""
    if not (_RX_SEPARATE_CONTRACT_REFERENCE.search(text) and _RX_CONTRACT_LINKAGE.search(text)):
        return
    if _RX_VOLUNTARY_PARTICIPATION_CLAUSE.search(text):
        return
    is_dealer_context = bool(_RX_EXISTING_DEALER_SIGNAL.search(text))
    risk = "HIGH" if is_dealer_context else "MEDIUM"

    # [실무 Redline, 2026-09-04 지시] — 실제 계약 구조(clauses)에서 계약
    # 연동 문구가 들어있는 조항을 찾아 그 조항의 마지막 항 뒤에 새 항을
    # 신설하는 위치를 계산한다. 조항번호는 계약마다 다르므로 하드코딩하지
    # 않고 실제 segmentation 결과에서 조회한다 — 찾지 못하면 위치를
    # 지어내지 않고 "위치 확인 필요"로 남긴다.
    from runtime.review.redline_instruction import (
        build_redline_instruction,
        find_article_for_pattern,
        location_insert_after_last_paragraph,
        paragraph_marker,
    )
    _loc = find_article_for_pattern(clauses, _RX_CONTRACT_LINKAGE)
    _edit_location = location_insert_after_last_paragraph(_loc)
    _next_marker = paragraph_marker((_loc["max_paragraph_number"] + 1) if _loc and _loc["max_paragraph_number"] else 1)
    _replacement_text = (
        f"{_next_marker} 본 계약의 체결 및 갱신 여부는 을의 자율적인 의사에 따르며, 을이 본 계약의 체결 "
        "또는 갱신을 거절하거나 본 계약이 종료되더라도 갑과 을 사이의 기존 계약(위탁판매(운영) 계약 등)의 "
        "수수료, 물량, 갱신 기타 거래조건에 어떠한 불이익도 발생하지 아니한다."
    )
    _redline = build_redline_instruction(
        clause_id="clr_linked_contract_dependency_no_voluntary_clause",
        severity=risk,
        edit_location=_edit_location,
        edit_type="insert_after",
        replacement_text=_replacement_text,
        reason=(
            "이 계약은 기존 계약과 별도라고 되어 있지만, 계약기간·해지가 기존 계약에 그대로 연동되어 "
            "있습니다. 그런데 이번 계약 참여를 거절하거나 끝내도 기존 계약에 불이익이 없다는 문구가 "
            "없어서, 실질적으로는 참여를 강제당하는 구조가 될 수 있습니다."
        ),
    )
    clause_results.append({
        "clause_id": "clr_linked_contract_dependency_no_voluntary_clause",
        "article_number": _loc["article_number"] if _loc else None,
        "display_path": (f"제{_loc['article_number']}조" if _loc else None),
        "clause_title": "[공통 법률리스크] 기존 계약과의 경제적 연계 + 자율적 참여 조항 부재",
        "clause_number_uncertain": not bool(_loc),
        "clause_topic": "other",
        "original_text": "(계약 전체 구조 — 별도 계약이라는 형식과 실제 존속기간·해지 연동 조항)",
        "risk_tier": risk,
        "severity": risk,
        "high_risk": risk == "HIGH",
        "must_fix": risk == "HIGH",
        "approval_required": risk == "HIGH",
        "review_tier": "MUST" if risk == "HIGH" else "SUGGEST",
        "suggested_rewrite": _replacement_text,
        "redline_instruction": _redline,
        "rewrite_reason": (
            "본 계약이 기존 계약과 별도라고 규정하면서도 존속기간·해지가 기존 계약에 연동되어 있어 "
            "경제적으로 종속돼 있는데, 참여를 거절하거나 갱신하지 않아도 기존 계약에 불이익이 없다는 "
            "조항이 없다."
        ),
        "legal_business_reason": (
            "형식상 별도 계약이라도 당사자·매장·존속기간이 기존 거래관계에 종속되어 있으면, 실질적으로는 "
            "기존 대리점/위탁관계의 추가 의무로 취급될 수 있다. 참여 거절 시 기존 계약(수수료·물량·갱신 "
            "등)에 불이익이 있는지가 불명확하면 대리점법상 불이익 제공·거래상 지위 남용 판단의 핵심 "
            "쟁점이 된다."
        ),
        "suggested_direction": ["참여 거절·종료가 기존 계약에 불이익을 주지 않는다는 조항 신설"],
        "negotiation_position": "자율적 참여 및 불이익 금지 조항 신설을 우선 요청 — 기존 대리점관계가 있는 상대방이라면 협상 거부 시 그 이유 자체가 대리점법 리스크 신호다.",
        "confidence": 0.75,
        "is_common_legal_risk": True,
        "has_rewrite_change": True,
        "display_kind": "guidance",
        "dedup_suppressed": False,
        "keep_as_is": False,
        "user_focus_hit": False,
        "factual_hit": False,
        "ai_deep_reviewed": False,
    })


# ─── 2. 귀책사유 구분 없는 판매취소 수수료 환수 ─────────────────────────────

_RX_CANCELLATION_CLAWBACK = re.compile(
    r"(?:주문|판매|구매)(?:을|를)?\s*취소.{0,150}(?:기\s*정산|이미\s*정산)(?:되었던|된)?\s*(?:비용|수수료|대금)"
    r".{0,80}(?:반환|입금|지급)",
    re.DOTALL,
)
_RX_FAULT_DIFFERENTIATION = re.compile(
    r"귀책|단순\s*변심|과실|하자|배송\s*지연|당사\s*귀책|고객\s*귀책"
)


def _apply_fault_blind_commission_clawback_check(
    clause_results: list[dict[str, Any]],
    clauses: list[ClauseChunk] | None,
) -> None:
    existing = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if "clr_fault_blind_commission_clawback" in existing:
        return
    for c in (clauses or []):
        leaf_text = str(getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else "") or "")
        if not _RX_CANCELLATION_CLAWBACK.search(leaf_text):
            continue
        if _RX_FAULT_DIFFERENTIATION.search(leaf_text):
            continue
        art = str(getattr(c, "article_number", None) or (c.get("article_number") if isinstance(c, dict) else "") or "").strip() or None
        display_path = str(getattr(c, "display_path", None) or (c.get("display_path") if isinstance(c, dict) else "") or "").strip() or None
        title = f"{display_path} [판매취소 수수료 환수 — 귀책사유 구분 없음]" if display_path else "[공통 법률리스크] 판매취소 수수료 환수 — 귀책사유 구분 없음"

        # [실무 Redline, 2026-09-04 지시] — 이 조항 자체를 전면 교체하는
        # 완성 문구를 만든다. 실제로 매치된 조항의 display_path(예: "제3조
        # 제1항")를 그대로 위치로 쓴다 — 계약마다 조항번호가 다르므로 여기서
        # 하드코딩하지 않는다.
        from runtime.review.redline_instruction import build_redline_instruction
        _replacement_text = (
            "고객의 단순변심 또는 을의 귀책사유로 판매가 취소된 경우에는 해당 판매분에 관하여 이미 "
            "지급된 용역수수료를 정산한다. 다만 갑 또는 상품 공급자의 귀책사유, 상품 하자, 배송지연 "
            "기타 을에게 책임 없는 사유로 판매가 취소된 경우에는 이미 적법하게 수행된 판매지원 업무에 "
            "대한 용역수수료를 환수하지 아니한다."
        )
        _redline = build_redline_instruction(
            clause_id="clr_fault_blind_commission_clawback",
            severity="MEDIUM",
            edit_location=(f"{display_path} 교체" if display_path else "위치 확인 필요 — 원문에서 해당 조항을 특정하지 못함"),
            edit_type="replace",
            target_text=leaf_text.strip()[:400],
            replacement_text=_replacement_text,
            original_text=leaf_text.strip()[:400],
            reason=(
                "판매가 취소됐을 때 이미 받은 수수료를 반환해야 하는지가 취소된 이유와 상관없이 "
                "똑같이 정해져 있습니다. 그런데 취소 이유가 우리 쪽(판매지원 업무 담당자) 잘못이 아니라 "
                "상품 하자나 배송 문제 때문이라면, 우리가 정당하게 수행한 업무의 대가까지 반환할 이유가 "
                "없습니다."
            ),
        )

        clause_results.append({
            "clause_id": "clr_fault_blind_commission_clawback",
            "article_number": art,
            "display_path": display_path,
            "clause_title": title,
            "clause_number_uncertain": not bool(display_path),
            "clause_topic": "payment_settlement",
            "original_text": leaf_text.strip()[:400],
            "risk_tier": "MEDIUM",
            "severity": "MEDIUM",
            "high_risk": False,
            "must_fix": False,
            "approval_required": False,
            "review_tier": "SUGGEST",
            "suggested_rewrite": _replacement_text,
            "redline_instruction": _redline,
            "rewrite_reason": "판매취소 시 수수료(비용) 반환 의무가 취소 원인(고객 단순변심/상대방 귀책 등)을 구분하지 않고 일률적으로 부과되어 있다.",
            "legal_business_reason": (
                "상대방 또는 제3자의 귀책(하자·배송지연 등)으로 판매가 취소된 경우까지 을이 이미 받은 "
                "수수료를 반환해야 한다면, 을이 통제할 수 없는 사유로 발생한 손실을 을 혼자 부담하는 "
                "불합리한 구조가 된다."
            ),
            "suggested_direction": ["취소 원인별(고객 단순변심/상대방 귀책)로 수수료 반환 의무를 구분"],
            "negotiation_position": "고객 단순변심 취소는 현행 유지, 상대방·공급자 귀책 취소는 수수료 반환 면제를 우선 요청.",
            "confidence": 0.75,
            "is_common_legal_risk": True,
            "has_rewrite_change": True,
            "display_kind": "guidance",
            "dedup_suppressed": False,
            "keep_as_is": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "ai_deep_reviewed": False,
        })
        return


# ─── 3. 무제한 확장형 업무범위("기타 ... 요청사항") ─────────────────────────

_RX_UNBOUNDED_SCOPE = re.compile(r"기타\s*[\S ]{0,20}(?:관련\s*)?요청사항\s*(?:지원|이행|수행)?")
_RX_SCOPE_LIMIT_MARKER = re.compile(r"사전(?:에)?\s*(?:서면으로?\s*)?합의(?:된|한)?\s*범위|별도\s*협의된?\s*범위")


def _apply_unbounded_scope_expansion_check(
    clause_results: list[dict[str, Any]],
    clauses: list[ClauseChunk] | None,
    full_text: str,
) -> None:
    existing = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if "clr_unbounded_scope_expansion" in existing:
        return
    text = full_text or ""
    m = _RX_UNBOUNDED_SCOPE.search(text)
    if not m:
        return
    if _RX_SCOPE_LIMIT_MARKER.search(text):
        return
    art = None
    display_path = None
    excerpt = text[max(0, m.start() - 60):min(len(text), m.end() + 40)].strip()
    for c in (clauses or []):
        leaf_text = str(getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else "") or "")
        if _RX_UNBOUNDED_SCOPE.search(leaf_text):
            art = str(getattr(c, "article_number", None) or (c.get("article_number") if isinstance(c, dict) else "") or "").strip() or None
            display_path = str(getattr(c, "display_path", None) or (c.get("display_path") if isinstance(c, dict) else "") or "").strip() or None
            # 2026-09-04 지시 회귀조건 — "1./2./.../8." 순수 번호매김 형식
            # 문서는 조 단위 세그멘테이션이 거칠어(문단 여러 개가 하나의
            # leaf chunk로 뭉쳐짐) 이 조항의 leaf_text 전체를 발췌문으로
            # 쓰면 다른 rule(예: 일방적 해석권)이 같은 leaf chunk에서 찾은
            # 발췌문과 완전히 동일해져 output_filter의 clause-identity
            # dedup(같은 원문 인용 = 같은 조항)에 의해 둘 중 하나가 조용히
            # 병합·소실된다. leaf_text 전체 대신 이 rule 자신의 매치 위치
            # 주변 좁은 창(원래 fallback excerpt)을 그대로 유지해, 서로
            # 다른 rule의 발췌문이 우연히 똑같아지지 않게 한다.
            break
    title = f"{display_path} [무제한 확장형 업무범위]" if display_path else "[공통 법률리스크] 무제한 확장형 업무범위"

    # [실무 Redline, 2026-09-04 지시] — "기타 ... 요청사항" 문구 자체를
    # 부분 교체하는 완성 문구 + 필요시 초과업무 협의 단서를 함께 제시한다.
    # 한 줄에 원문자 번호(①②③...)가 여러 개 붙어있는 문서(예: "① ... ②
    # ... ③ ...")는 세그멘테이션이 항 단위로 완전히 쪼개지 못해 이 조항의
    # leaf가 안 잡힐 수 있다 — 그 경우에도 위치를 "확인 필요"로 방치하지
    # 않고, 같은 조(예: "영업지원 범위")를 가리키는 더 넓은 신호로 최소한
    # 조 단위까지는 특정한다(호 단위보다 정밀도는 낮지만 실무자가 계약서
    # 어느 조를 봐야 하는지는 알 수 있다).
    from runtime.review.redline_instruction import build_redline_instruction, find_article_for_pattern
    _matched_phrase = m.group(0).strip()
    _replacement_text = (
        "기타 본 계약의 목적 범위 내에서 갑과 을이 사전에 협의하여 합의한 판매지원 업무. "
        "기존 업무범위를 실질적으로 초과하는 추가 업무의 경우 수수료 등 수행조건을 별도로 협의한다."
    )
    if display_path:
        _edit_location_d = f"{display_path} 중 \"{_matched_phrase}\" 부분 교체"
    else:
        _fallback_loc = find_article_for_pattern(clauses, _RX_SALES_SUPPORT_SCOPE_ARTICLE)
        _edit_location_d = (
            f"제{_fallback_loc['article_number']}조({_fallback_loc['article_title']}) 내 "
            f"\"{_matched_phrase}\" 부분 교체"
        ) if _fallback_loc else "위치 확인 필요 — 원문에서 해당 조항을 특정하지 못함"
    _redline = build_redline_instruction(
        clause_id="clr_unbounded_scope_expansion",
        severity="MEDIUM",
        edit_location=_edit_location_d,
        edit_type="replace",
        target_text=_matched_phrase,
        replacement_text=_replacement_text,
        original_text=excerpt,
        reason=(
            "\"기타 ... 요청사항 지원\"처럼 업무범위를 정해두지 않은 문구가 있으면, 상대방이 원래 "
            "합의하지 않은 업무까지 대가 없이 요구할 근거가 됩니다. 업무범위를 사전에 합의한 것으로 "
            "한정하고, 범위를 넘는 업무는 별도로 협의하도록 명시해야 합니다."
        ),
    )

    clause_results.append({
        "clause_id": "clr_unbounded_scope_expansion",
        "article_number": art,
        "display_path": display_path,
        "clause_title": title,
        "clause_number_uncertain": not bool(display_path),
        "clause_topic": "other",
        "original_text": excerpt,
        "risk_tier": "MEDIUM",
        "severity": "MEDIUM",
        "high_risk": False,
        "must_fix": False,
        "approval_required": False,
        "review_tier": "SUGGEST",
        "suggested_rewrite": _replacement_text,
        "redline_instruction": _redline,
        "rewrite_reason": "\"기타 ... 요청사항 지원\"처럼 업무범위를 무제한으로 확장할 수 있는 문구가 있고, 이를 제한하는 사전 합의 절차가 없다.",
        "legal_business_reason": "범위가 정해지지 않은 포괄적 업무 요청 조항은 상대방이 대가 없이 추가 업무를 계속 요구할 수 있는 근거가 되어, 비용·인력 부담이 예고 없이 늘어날 수 있다.",
        "suggested_direction": ["업무범위를 사전 합의된 범위로 한정"],
        "negotiation_position": "\"사전에 서면으로 합의한 범위\" 문구 추가를 우선 요청 — 협상 난이도가 낮은 안전장치.",
        "confidence": 0.7,
        "is_common_legal_risk": True,
        "has_rewrite_change": True,
        "display_kind": "guidance",
        "dedup_suppressed": False,
        "keep_as_is": False,
        "user_focus_hit": False,
        "factual_hit": False,
        "ai_deep_reviewed": False,
    })


# ─── 4. 일방적 해석권 + 일방 소재지 전속관할 ────────────────────────────────

_RX_UNILATERAL_INTERPRETATION = re.compile(
    r"해석상\s*이의.{0,40}(?:갑|을|상대방)[\"'”]?\s*(?:의)?\s*해석에\s*따르며?",
    re.DOTALL,
)
_RX_UNILATERAL_FORUM = re.compile(
    r"(?:갑|을|상대방)[\"'”]?\s*(?:의)?\s*(?:본점\s*)?소재지(?:를)?\s*관할(?:하는)?\s*법원",
)


def _apply_unilateral_interpretation_and_forum_check(
    clause_results: list[dict[str, Any]],
    clauses: list[ClauseChunk] | None,
    full_text: str,
) -> None:
    existing = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if "clr_unilateral_interpretation_and_forum" in existing:
        return
    text = full_text or ""
    interp_match = _RX_UNILATERAL_INTERPRETATION.search(text)
    if not interp_match:
        return
    has_forum = bool(_RX_UNILATERAL_FORUM.search(text))
    risk = "HIGH" if has_forum else "MEDIUM"
    art = None
    display_path = None
    excerpt = text[max(0, interp_match.start() - 40):min(len(text), interp_match.end() + 100)].strip()
    for c in (clauses or []):
        leaf_text = str(getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else "") or "")
        if _RX_UNILATERAL_INTERPRETATION.search(leaf_text):
            art = str(getattr(c, "article_number", None) or (c.get("article_number") if isinstance(c, dict) else "") or "").strip() or None
            display_path = str(getattr(c, "display_path", None) or (c.get("display_path") if isinstance(c, dict) else "") or "").strip() or None
            # (좁은 매치 위치 기준 excerpt를 그대로 유지 — clr_unbounded_
            # scope_expansion과 동일한 이유, 2026-09-04 지시 회귀조건)
            break
    title = f"{display_path} [일방적 해석권]" if display_path else "[공통 법률리스크] 일방적 해석권"
    # [관할/일방적 해석권 분리, 2026-09-04 지시] — 관할(전속관할 자체)은
    # 특별한 집행상 불이익이 없으면 원칙적으로 수용 가능(LOW/ACCEPT)한
    # 사항이므로, 수정안에서 관할 변경을 제안하지 않는다 — 핵심 수정
    # 대상은 오직 "일방적 해석권" 부분으로 한정한다. has_forum은 위험도
    # 산정에는 계속 반영하되(비대칭 관할이 함께 있으면 협상력 불균형의
    # 신호로서 risk를 HIGH로 올리는 근거), 수정 문구 자체를 건드리지
    # 않는다.
    _replacement_text = (
        "본 계약의 해석상 이견이 발생하는 경우 갑과 을이 상호 협의하여 정하며, 협의되지 않는 경우 "
        "관련 법령 및 일반적인 거래관행에 따른다."
    )
    from runtime.review.redline_instruction import build_redline_instruction
    _redline = build_redline_instruction(
        clause_id="clr_unilateral_interpretation_and_forum",
        severity=risk,
        edit_location=(f"{display_path} 중 \"{interp_match.group(0).strip()}\" 부분 교체" if display_path else "위치 확인 필요 — 원문에서 해당 조항을 특정하지 못함"),
        edit_type="replace",
        target_text=interp_match.group(0).strip(),
        replacement_text=_replacement_text,
        original_text=excerpt,
        reason=(
            "계약 해석에 이견이 있을 때 한쪽 당사자의 해석만 따르도록 되어 있으면, 실제 분쟁에서 "
            "상대방이 일방적으로 유리한 해석을 관철시킬 수 있습니다. 양쪽이 협의해서 정하고, 협의가 "
            "안 되면 법령과 거래관행에 따르도록 바꿔야 합니다."
        ),
    )
    clause_results.append({
        "clause_id": "clr_unilateral_interpretation_and_forum",
        "article_number": art,
        "display_path": display_path,
        "clause_title": title,
        "clause_number_uncertain": not bool(display_path),
        "clause_topic": "dispute",
        "original_text": excerpt,
        "risk_tier": risk,
        "severity": risk,
        "high_risk": risk == "HIGH",
        "must_fix": risk == "HIGH",
        "approval_required": risk == "HIGH",
        "review_tier": "MUST" if risk == "HIGH" else "SUGGEST",
        "suggested_rewrite": _replacement_text,
        "redline_instruction": _redline,
        "rewrite_reason": "계약 문구 해석에 이의가 있을 때 일방 당사자의 해석만을 따르도록 되어 있다.",
        "legal_business_reason": (
            "해석권을 일방에게 주는 조항은 그 자체로 상대방의 계약상 지위를 약화시킨다."
            + (" 비대칭 전속관할까지 함께 있어 협상력 불균형의 신호로 본다(관할 자체를 변경하자는 것은 "
               "아니다 — 특별한 집행상 불이익이 없다면 관할은 그대로 두어도 무방하다)." if has_forum else "")
        ),
        "suggested_direction": ["해석상 이의는 상호 협의로 해결하도록 수정(관할 자체는 특별한 불이익이 없으면 유지)"],
        "negotiation_position": "핵심 협상 대상은 일방적 해석권이며, 관할 자체는 특별한 집행상 불이익이 없는 한 우선순위가 낮다.",
        "confidence": 0.75,
        "is_common_legal_risk": True,
        "has_rewrite_change": True,
        "display_kind": "guidance",
        "dedup_suppressed": False,
        "keep_as_is": False,
        "user_focus_hit": False,
        "factual_hit": False,
        "ai_deep_reviewed": False,
    })


# ─── 5. (materiality-gated) 소비자 대면 판매 구조인데 소비자/상품책임 배분 없음 ──

_RX_CONSUMER_PRODUCT_LIABILITY_ALLOCATION = re.compile(
    r"(?:배송|하자|반품|환불).{0,30}책임|진위.{0,20}(?:보증|책임)|저작권.{0,20}(?:침해|책임|보증)",
)


_RX_SALES_SUPPORT_SCOPE_ARTICLE = re.compile(
    r"영업\s*지원\s*범위|판매\s*지원\s*범위|고객\s*상담|주문\s*접수",
)


def _apply_missing_consumer_product_liability_check(
    clause_results: list[dict[str, Any]],
    full_text: str,
    legal_map_fields: dict[str, Any] | None = None,
    clauses: list[ClauseChunk] | None = None,
) -> None:
    existing = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if "clr_missing_consumer_product_liability_allocation" in existing:
        return
    text = full_text or ""
    # materiality gate — 소비자 대면 판매 구조가 실제로 있을 때만 발동한다
    # (svc_delay_response처럼 무관한 계약에 임의 권고를 붙이는 실수를
    # 반복하지 않기 위한 안전장치).
    if not detect_sales_transaction_ambiguity(text):
        return
    if _RX_CONSUMER_PRODUCT_LIABILITY_ALLOCATION.search(text):
        return

    # [사전질문 답변 반영, 2026-09-04 지시] — 사용자가 이미 "실제 판매자/
    # 소유자"가 누구인지 답변했다면(Contract Legal Map의 seller/owner_of_goods
    # 필드), 조항 원문에 넣을 자리표시자(bracket placeholder)를 계속 남기지
    # 말고 그 실명으로 치환한다. canonical_transaction_facts.py의
    # resolved_party_label()을 그대로 써서 "판매자=소유자 동일 주체" 판정
    # 로직을 이 파일에 따로 복제하지 않는다(single source of truth 원칙).
    # 둘 다 답변이 없으면(질문에 아직 응답하지 않은 상태) 기존과 같은
    # placeholder를 유지한다 — 이 경우는 "확정할 수 없는 사실"이 실제로
    # 남아있는 것이므로 placeholder 자체가 정확한 표현이다.
    from runtime.review.canonical_transaction_facts import (
        build_canonical_transaction_facts,
        resolved_party_label,
    )
    _facts_for_liability = build_canonical_transaction_facts(legal_map_fields or {})
    seller = _facts_for_liability.get("seller") or ""
    owner = _facts_for_liability.get("owner_of_goods") or ""
    resolved_party = resolved_party_label(_facts_for_liability) or "[실제 판매자/소유자]"
    _seller_label = resolved_party if (seller or owner) else "갑"

    # [실무 Redline, 2026-09-04 지시] — 판매지원 범위를 다루는 조항 뒤에
    # 신설 조항으로 추가하는 위치를 실제 구조에서 찾는다(하드코딩 금지).
    # 찾지 못하면 위치를 지어내지 않고 "위치 확인 필요"로 남겨
    # REVIEW_FAILED_INCOMPLETE_REDLINE 대상이 되게 한다.
    from runtime.review.redline_instruction import build_redline_instruction, find_article_for_pattern, location_new_article_after
    _loc = find_article_for_pattern(clauses, _RX_SALES_SUPPORT_SCOPE_ARTICLE)
    _edit_location = location_new_article_after(_loc)
    _replacement_text = (
        f"① 본 계약에 따른 상품의 판매자는 {_seller_label}이며, 을은 고객 상담, 상품 안내, 주문 접수 "
        f"및 결제 처리 등 판매지원 업무만을 수행한다. 을은 해당 상품의 매매계약 당사자가 아니다.\n"
        f"② 상품의 품질·하자·배송·반품·환불 및 진위·저작권 등 상품 자체에 관한 책임은 {_seller_label}이 "
        "부담한다. 다만 을의 고의 또는 과실로 직접 발생한 손해에 대해서는 을이 책임을 부담한다."
    )
    _new_article_title = f"제{_loc['article_number']}조의2 (판매자 및 상품책임)" if _loc else "(판매자 및 상품책임)"
    _redline = build_redline_instruction(
        clause_id="clr_missing_consumer_product_liability_allocation",
        severity="MEDIUM",
        edit_location=_edit_location,
        edit_type="new_clause",
        replacement_text=f"{_new_article_title}\n{_replacement_text}",
        reason=(
            "고객을 직접 상대하는 판매 구조인데, 배송·하자·반품·환불이나 상품 진위·저작권 문제가 생겼을 "
            "때 누가 책임지는지 계약서에 전혀 나와 있지 않습니다. 이대로 두면 실제 판매자가 아닌데도 "
            "고객을 직접 응대했다는 이유로 우리가 책임을 떠안을 수 있습니다."
        ),
    )

    clause_results.append({
        "clause_id": "clr_missing_consumer_product_liability_allocation",
        "article_number": None,
        "display_path": None,
        "clause_title": "[공통 법률리스크] 소비자 대면 판매 구조인데 배송·하자·환불·진위·IP 책임 배분 없음",
        "clause_number_uncertain": True,
        "clause_topic": "other",
        "original_text": "(계약 전체 — 소비자 접점이 있는데 책임 배분 조항 부재)",
        "risk_tier": "MEDIUM",
        "severity": "MEDIUM",
        "high_risk": False,
        "must_fix": False,
        "approval_required": False,
        "review_tier": "SUGGEST",
        "suggested_rewrite": (
            f"상품의 배송·하자·반품·환불에 관한 책임은 {resolved_party}가 부담하며, 상품의 진위·품질·"
            f"저작권 등 지식재산권 침해에 대한 책임도 {resolved_party}가 부담한다. 을은 판매지원 "
            "업무 범위 내에서 자신의 고의 또는 과실로 발생한 손해에 대해서만 책임을 진다."
        ),
        "redline_instruction": _redline,
        "rewrite_reason": "고객을 직접 상대하는 판매 구조인데, 배송·하자·반품·환불 및 상품 진위·저작권 관련 책임을 누가 부담하는지 계약서에 전혀 규정되어 있지 않다.",
        "legal_business_reason": (
            "소비자 클레임(하자·환불·진위 시비 등)이 발생했을 때 책임 주체가 불명확하면, 실제 판매자가 "
            "아니더라도 고객을 직접 응대한 당사자가 표현상 판매자로 오인되어 전자상거래법·소비자보호법상 "
            "책임을 떠안을 위험이 있다."
        ),
        "suggested_direction": ["배송/하자/환불/진위/IP 책임 주체를 명시적으로 배분"],
        "negotiation_position": "실제 판매자·소유자가 소비자 책임을 부담한다는 점을 명확히 하는 것을 우선 요청 — 우리 측이 판매지원 용역자에 불과하다면 이 명확화가 유리하다.",
        "confidence": 0.65,
        "is_common_legal_risk": True,
        "has_rewrite_change": True,
        "display_kind": "guidance",
        "dedup_suppressed": False,
        "keep_as_is": False,
        "user_focus_hit": False,
        "factual_hit": False,
        "ai_deep_reviewed": False,
        "transaction_facts_applied": bool(seller or owner),
    })


def apply_sales_transaction_rules(
    clause_results: list[dict[str, Any]],
    full_text: str,
    clauses: list[ClauseChunk] | None = None,
    legal_map_fields: dict[str, Any] | None = None,
) -> None:
    """`common_legal_risk.py`의 Layer-1 dispatcher에서 호출되는 진입점.

    `legal_map_fields`: Contract Legal Map의 seller/owner_of_goods 등 —
    사용자가 사전질문에 답변한 거래실질 사실관계(2026-09-04 지시). 이
    값이 있으면 소비자책임 finding의 수정안이 "[실제 판매자/소유자]" 같은
    자리표시자 대신 실제 당사자명을 사용한다.
    """
    _apply_linked_contract_dependency_check(clause_results, full_text, clauses)
    _apply_fault_blind_commission_clawback_check(clause_results, clauses)
    _apply_unbounded_scope_expansion_check(clause_results, clauses, full_text)
    _apply_unilateral_interpretation_and_forum_check(clause_results, clauses, full_text)
    _apply_missing_consumer_product_liability_check(clause_results, full_text, legal_map_fields, clauses)
