"""법률효과를 유지하는 **최소수정안** 생성기.

2026-09-10 아키텍처 지시 항목 7 — "Rewrite 는 원조항 법률효과를 유지하며
최소수정. 모든 HIGH/MEDIUM finding 에는 정확한 수정 위치·edit type·완성
문구·수정 이유·practical position 을 제공. '[수정문안 보류]', '담당 변호사가
직접 확정', '추후 협의', placeholder 만 있는 수정안은 금지."

무엇을 고치는가
─────────────
직전까지는 무결성 게이트가 신뢰할 수 없는 AI 수정문안을 발견하면 그 문안을
회수하고 자리에 "[수정문안 보류] … 담당 변호사가 직접 확정해야 합니다" 를
적었다. 잘못된 문구가 계약서에 들어가는 것은 막았지만, 담당자 입장에서는
**협상에 쓸 수 없는 문서**가 나온 셈이다.

이 모듈은 그 자리를 실제 문구로 채운다. 핵심은 **계약유형이 아니라 조항의
법률효과**를 기준으로 삼는 것이다 — 배상 조항에 한도를 넣는 것, 해지 조항에
최고 절차를 넣는 것은 계약이 NDA 든 건설도급이든 동일하게 성립하는 최소
방어장치이기 때문이다. 유형별 템플릿을 쓰지 않으므로 유형이 늘어도 깨지지
않는다.

두 가지만 만든다.

  1. **최소수정안** — 원문을 그대로 두고, 그 조항의 법률효과에 맞는 방어
     장치 한 문장을 덧붙인다. 원문의 효과를 바꾸지 않으므로 semantic gate 를
     통과하고, 협상 테이블에 그대로 올릴 수 있다.
  2. 그것도 불가능하면(원문을 특정하지 못한 경우 등) `FACT_CONFIRMATION_REQUIRED`
     로 표시하고 **무엇을 확인해야 하는지 한 가지 이상** 구체적으로 적는다.
"""
from __future__ import annotations

from typing import Any

from runtime.review.clause_effect import (
    EFFECT_CHANGE,
    EFFECT_COMPLIANCE,
    EFFECT_CONFIDENTIALITY,
    EFFECT_DELIVERY,
    EFFECT_DISPUTE,
    EFFECT_IP,
    EFFECT_LIABILITY,
    EFFECT_OWNERSHIP,
    EFFECT_PAYMENT,
    EFFECT_PRIVACY,
    EFFECT_SCOPE,
    EFFECT_SUBCONTRACT,
    EFFECT_TERMINATION,
    EFFECT_WARRANTY,
    classify_clause_effects,
)

FACT_CONFIRMATION_REQUIRED = "FACT_CONFIRMATION_REQUIRED"

#: 효과 범주별 최소 방어장치. 원문의 법률효과를 **바꾸지 않고** 절차·한도·
#: 예외만 덧붙이는 문장이라, 어느 계약유형에서도 성립한다.
_MINIMAL_ADDITION: dict[str, str] = {
    EFFECT_LIABILITY: (
        "다만 본조에 따른 손해배상 책임은 고의 또는 중대한 과실이 있는 경우를 제외하고 "
        "직접손해에 한하며, 그 총액은 본 계약에 따라 상대방이 수령한 대가의 총액을 "
        "초과하지 아니한다. 제3자 청구가 제기된 경우 배상의무자는 지체 없이 상대방에게 "
        "서면으로 통지하고, 상대방은 방어 및 화해 절차에 참여할 권리를 가진다."
    ),
    EFFECT_TERMINATION: (
        "다만 일방이 본 계약을 해지하고자 하는 경우에는 30일 전까지 시정을 요구하는 "
        "서면 최고를 하여야 하며, 그 기간 내에 시정되지 아니한 때에 한하여 해지할 수 있다. "
        "해지의 효력은 이미 이행된 부분에 소급하지 아니한다."
    ),
    EFFECT_PAYMENT: (
        "대가의 산정 기준·지급 시기 및 공제·상계 사유는 본조 또는 별도 서면으로 특정하며, "
        "공제·상계를 하는 당사자는 그 사유와 산출 근거를 증빙자료와 함께 사전에 서면으로 "
        "통지하여야 한다."
    ),
    EFFECT_DELIVERY: (
        "검수는 목적물 수령일로부터 10영업일 이내에 완료하며, 그 기간 내에 서면으로 "
        "구체적 사유를 들어 이의를 제기하지 아니한 경우 검수에 합격한 것으로 본다. "
        "불합격 사유는 계약에서 정한 사양과의 불일치로 한정한다."
    ),
    EFFECT_OWNERSHIP: (
        "목적물의 소유권과 멸실·훼손의 위험은 인도 및 인수확인이 완료된 때에 이전하며, "
        "그 이전 시점을 서면으로 확인한다."
    ),
    EFFECT_IP: (
        "본조에 따른 권리의 이전 또는 이용허락의 범위에는 2차적저작물작성권을 포함하며, "
        "이용의 매체·기간·지역에 제한을 두지 아니한다. 권리를 이전하는 당사자는 해당 "
        "결과물이 제3자의 권리를 침해하지 아니함을 보증한다."
    ),
    EFFECT_CONFIDENTIALITY: (
        "비밀유지의무는 공지의 정보, 수령 전부터 보유하던 정보, 제3자로부터 적법하게 "
        "취득한 정보 및 독자적으로 개발한 정보에는 미치지 아니하며, 법령 또는 "
        "관계기관의 요구에 따른 공개는 사전 통지를 조건으로 허용한다."
    ),
    EFFECT_PRIVACY: (
        "개인정보를 수집·이용·제공하는 당사자는 관계 법령에 따라 수집·이용 목적, 항목, "
        "보유기간 및 제3자 제공에 관한 동의를 적법하게 확보하고, 그 증빙을 상대방의 "
        "요청 시 제시한다."
    ),
    EFFECT_WARRANTY: (
        "하자담보책임의 기간과 범위를 본조에 명시하며, 통상의 사용에 따른 자연 마모 및 "
        "상대방의 지시 또는 제공 자료에 기인한 하자는 책임 범위에서 제외한다."
    ),
    EFFECT_CHANGE: (
        "업무 범위의 변경 또는 추가가 필요한 경우 그 내용·기간·대가를 서면으로 합의한 "
        "후에 착수하며, 서면 합의 없이 수행된 추가 업무에 대하여는 대가 청구 및 "
        "이행 지체의 책임을 지지 아니한다."
    ),
    EFFECT_SUBCONTRACT: (
        "제3자에게 업무의 전부 또는 일부를 위탁하려는 당사자는 상대방의 사전 서면 동의를 "
        "받아야 하며, 그 제3자의 행위에 대하여 자신의 행위와 동일한 책임을 진다."
    ),
    EFFECT_DISPUTE: (
        "본 계약과 관련한 분쟁은 상호 협의로 해결하되, 협의가 이루어지지 아니한 경우 "
        "관할 법원을 본조에 특정된 법원으로 한정한다."
    ),
    EFFECT_COMPLIANCE: (
        "각 당사자는 본 계약의 이행과 관련하여 적용되는 법령을 준수하며, 위반으로 인하여 "
        "상대방에게 발생한 제재·손해에 대하여 자신의 귀책 범위 내에서 책임을 진다."
    ),
    EFFECT_SCOPE: (
        "업무의 범위·산출물·완료 기준을 본조 또는 별첨으로 특정하며, 특정되지 아니한 "
        "업무는 본 계약의 이행 범위에 포함되지 아니한다."
    ),
}

#: 효과별 practical position(협상 실무 포지션). 문구만 주고 끝내지 않는다.
_PRACTICAL_POSITION: dict[str, str] = {
    EFFECT_LIABILITY: "책임 한도와 통지·방어권은 표준적인 요구로 상대방 수용 가능성이 높습니다. 한도 수치는 대가 총액을 기준으로 제시하십시오.",
    EFFECT_TERMINATION: "즉시해지를 최고 후 해지로 바꾸는 것은 통상 수용됩니다. 즉시해지가 필요한 사유는 좁게 열거해 남기십시오.",
    EFFECT_PAYMENT: "공제·상계의 사전 통지와 증빙 요구는 실무상 무리한 요구가 아닙니다.",
    EFFECT_DELIVERY: "검수 기간과 불합격 사유의 한정은 양측 모두에게 예측가능성을 주므로 협상 여지가 큽니다.",
    EFFECT_OWNERSHIP: "위험 이전 시점의 서면 확인은 분쟁 예방 목적으로 설명하면 수용되기 쉽습니다.",
    EFFECT_IP: "2차적저작물작성권 명시는 저작권법상 추정 규정 때문에 필요하다는 점을 근거로 요구하십시오.",
    EFFECT_CONFIDENTIALITY: "비밀유지 예외 4종은 국제 표준 문언이므로 거의 항상 수용됩니다.",
    EFFECT_PRIVACY: "동의 확보와 증빙 제시는 법정 의무의 확인이므로 거부 명분이 약합니다.",
    EFFECT_WARRANTY: "하자 범위에서 자연 마모와 발주자 귀책을 빼는 것은 표준적인 조정입니다.",
    EFFECT_CHANGE: "서면 합의 전 착수 금지는 양측 모두를 보호하므로 수용 가능성이 높습니다.",
    EFFECT_SUBCONTRACT: "재위탁 동의권과 사용자책임 조항은 함께 제시해야 균형이 맞습니다.",
    EFFECT_DISPUTE: "관할 특정은 상호 양보가 필요한 항목이므로 중재 대안을 함께 준비하십시오.",
    EFFECT_COMPLIANCE: "귀책 범위 한정 문구를 붙여야 일방 면책으로 읽히지 않습니다.",
    EFFECT_SCOPE: "범위 밖 업무의 제외 문구는 추가 대가 청구의 근거가 되므로 우선순위가 높습니다.",
}

_FALLBACK_POSITION = "상대방 반발 가능성이 있으나 예측가능성 확보 차원에서 협상할 가치가 있습니다."


def minimal_edit_for(
    *,
    original_text: str,
    clause_title: str = "",
    effects: list[str] | None = None,
) -> tuple[str, str, str]:
    """원문 + 최소 방어장치로 이루어진 완성 문구를 만든다.

    돌려주는 값: (final_clause_text, addition, practical_position).
    만들 수 없으면 ("", "", "").
    """
    body = str(original_text or "").strip()
    if not body:
        return "", "", ""
    eff_list = effects or classify_clause_effects(title=clause_title, text=body)
    for eff in eff_list:
        addition = _MINIMAL_ADDITION.get(eff)
        if addition:
            return (
                f"{body.rstrip()} {addition}".strip(),
                addition,
                _PRACTICAL_POSITION.get(eff, _FALLBACK_POSITION),
            )
    return "", "", ""


def apply_minimal_edit(
    cr: dict[str, Any],
    *,
    reason: str,
    fact_needed: str = "",
) -> bool:
    """신뢰할 수 없는 문안을 **최소수정안**으로 교체한다.

    교체에 성공하면 True. 원문이 없어 문구를 만들 수 없으면 finding 을
    `FACT_CONFIRMATION_REQUIRED` 로 표시하고 False 를 돌려준다 — 자리표시자
    문구는 어느 경우에도 남기지 않는다.
    """
    if not isinstance(cr, dict):
        return False

    original = str(cr.get("original_text") or "").strip()
    title = str(cr.get("clause_title") or "")
    final_text, addition, position = minimal_edit_for(
        original_text=original,
        clause_title=title,
        effects=(
            cr.get("clause_effects") if isinstance(cr.get("clause_effects"), list) else None
        ),
    )

    if not final_text:
        mark_fact_confirmation_required(
            cr,
            reason=reason,
            fact_needed=fact_needed or "이 조항이 규율하려는 대상과 당사자 간 합의 내용",
        )
        return False

    display_path = str(cr.get("display_path") or "").strip()
    cr["suggested_rewrite"] = final_text
    cr["proposed_revision"] = final_text
    cr["recommendation_text"] = final_text
    cr["has_rewrite_change"] = True
    cr["minimal_edit_applied"] = True
    cr["minimal_edit_addition"] = addition
    cr["negotiation_position"] = position
    cr["negotiation_strategy"] = position
    cr.pop("advisory_only", None)
    cr.pop("advisory_only_reason", None)
    cr.pop("fact_confirmation_required", None)

    existing_reason = str(cr.get("rewrite_reason") or "").strip()
    note = (
        f"{reason} 원문의 법률효과는 유지하고 절차·한도·예외만 최소한으로 보완했습니다."
    )
    cr["rewrite_reason"] = (
        f"{existing_reason}\n{note}".strip() if existing_reason and note not in existing_reason
        else (existing_reason or note)
    )

    from runtime.review.redline_instruction import build_redline_instruction

    cr["redline_instruction"] = build_redline_instruction(
        finding_id=str(cr.get("finding_id") or ""),
        clause_id=str(cr.get("clause_id") or ""),
        severity=str(cr.get("risk_tier") or ""),
        edit_location=(f"{display_path} 교체" if display_path else "해당 조항 교체"),
        edit_type="replace",
        target_text=original,
        replacement_text=final_text,
        original_text=original,
        reason=str(cr.get("rewrite_reason") or note),
    )
    return True


def mark_fact_confirmation_required(
    cr: dict[str, Any],
    *,
    reason: str,
    fact_needed: str,
) -> None:
    """문구를 확정할 수 없는 이유가 **사실관계 부재**일 때만 쓰는 표시.

    지시 항목 7 — 이 경우에도 "추후 협의" 같은 말로 끝내지 않고 무엇을
    확인해야 하는지 한 가지 이상 구체적으로 적는다.
    """
    if not isinstance(cr, dict):
        return
    fact = str(fact_needed or "").strip() or "이 조항의 적용 대상이 되는 사실관계"
    cr["fact_confirmation_required"] = FACT_CONFIRMATION_REQUIRED
    cr["fact_confirmation_items"] = [fact]
    cr["suggested_rewrite"] = None
    cr["redline_instruction"] = None
    cr["has_rewrite_change"] = False
    statement = (
        f"[사실확인 필요] {reason} 문구를 확정하려면 다음을 먼저 확인해야 합니다: {fact}."
    )
    cr["recommendation_text"] = statement
    cr["proposed_revision"] = statement
    existing = str(cr.get("rewrite_reason") or "").strip()
    cr["rewrite_reason"] = f"{existing}\n{statement}".strip() if existing else statement
    cr["negotiation_position"] = (
        "사실관계 확인 전에는 문구를 확정하지 마십시오. 확인 결과에 따라 요구 수준이 달라집니다."
    )
