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

#: 효과 범주별 최소 방어장치 — **방향에 따라 다르다**.
#:
#: 2026-09-11 지시 — "상대방에게 새로운 이의권·방어권·시정기간·책임제한을
#: 만들어주는 수정은 특별한 법적 필요가 있을 때만. 목표는 '중립적 문구'가
#: 아니라 법적으로 유효하면서 우리 회사의 실질적 위험을 줄이는 최소수정안."
#:
#: 종전 템플릿은 "일방/당사자/상대방" 으로 대칭 서술해 균형이 잡혀 보였지만,
#: 실제로는 우리가 수혜자인 조항에까지 상대방의 방어권·시정기간을 새로
#: 만들어 넣고 있었다(배상 조항의 "상대방은 방어 및 화해 절차에 참여할
#: 권리를 가진다", 해지 조항의 "30일 전 시정 요구 서면 최고").
#:
#:   WE_BEAR    우리가 의무·책임을 진다  → 한도·예외·절차로 우리를 보호한다
#:   THEY_BEAR  상대방이 의무를 진다     → 희석하지 않고 **집행력**만 보강한다
_ADDITION_WHEN_WE_BEAR: dict[str, str] = {
    EFFECT_LIABILITY: (
        "다만 본조에 따른 우리 측의 손해배상 책임은 고의 또는 중대한 과실이 있는 경우를 "
        "제외하고 직접·통상손해에 한하며, 그 총액은 본 계약에 따라 우리가 수령한 대가의 "
        "총액을 초과하지 아니한다. 간접손해·특별손해·일실이익은 배상 범위에서 제외한다."
    ),
    EFFECT_TERMINATION: (
        "다만 상대방이 본 계약을 해지하고자 하는 경우에는 30일 전까지 시정을 요구하는 "
        "서면 최고를 하여야 하며, 그 기간 내에 시정되지 아니한 때에 한하여 해지할 수 있다. "
        "해지의 효력은 이미 이행된 부분에 소급하지 아니한다."
    ),
    EFFECT_PAYMENT: (
        "대가의 산정 기준과 지급 시기를 본조에 특정하며, 상대방이 공제·상계·지급 유보를 "
        "하려는 경우에는 그 사유와 산출 근거를 증빙자료와 함께 사전에 서면으로 통지하여야 "
        "하고, 사전 통지 없는 공제·상계·유보는 효력이 없다."
    ),
    EFFECT_DELIVERY: (
        "검수는 목적물 수령일로부터 10영업일 이내에 완료하며, 그 기간 내에 계약에서 정한 "
        "사양과의 불일치를 구체적으로 적시한 서면 이의가 없으면 검수에 합격한 것으로 본다. "
        "불합격 사유는 계약에서 정한 사양과의 불일치로 한정한다."
    ),
    EFFECT_OWNERSHIP: (
        "목적물의 소유권과 멸실·훼손의 위험은 인도 및 인수확인이 완료된 때에 이전하며, "
        "그 이전 시점을 서면으로 확인한다."
    ),
    EFFECT_IP: (
        "본조에 따른 권리의 이전 또는 이용허락의 범위에는 2차적저작물작성권을 포함하며, "
        "이용의 매체·기간·지역에 제한을 두지 아니한다."
    ),
    EFFECT_CONFIDENTIALITY: (
        "비밀유지의무는 공지의 정보, 수령 전부터 보유하던 정보, 제3자로부터 적법하게 "
        "취득한 정보 및 독자적으로 개발한 정보에는 미치지 아니하며, 법령 또는 관계기관의 "
        "요구에 따른 공개는 사전 통지를 조건으로 허용한다."
    ),
    EFFECT_PRIVACY: (
        "개인정보를 수집·이용·제공하는 당사자는 관계 법령에 따라 수집·이용 목적, 항목, "
        "보유기간 및 제3자 제공에 관한 동의를 적법하게 확보하고, 그 증빙을 상대방의 "
        "요청 시 제시한다."
    ),
    EFFECT_WARRANTY: (
        "하자담보책임의 기간은 인수일로부터 1년으로 하며, 통상의 사용에 따른 자연 마모 및 "
        "상대방의 지시 또는 제공 자료에 기인한 하자는 책임 범위에서 제외한다."
    ),
    EFFECT_CHANGE: (
        "업무 범위의 변경 또는 추가가 필요한 경우 그 내용·기간·대가를 서면으로 합의한 "
        "후에 착수하며, 서면 합의 없이 수행된 추가 업무에 대하여는 대가 청구 및 이행 "
        "지체의 책임을 지지 아니한다."
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

#: 상대방이 의무를 지는 조항 — 그 의무를 **깎지 않고** 집행 가능하게만 만든다.
#: 새로운 이의권·방어권·시정기간·책임제한을 만들어주지 않는다.
_ADDITION_WHEN_THEY_BEAR: dict[str, str] = {
    EFFECT_LIABILITY: (
        "본조에 따른 배상 의무의 이행을 담보하기 위하여, 배상의무자는 우리의 서면 청구를 "
        "받은 날부터 30일 이내에 배상액을 지급하며, 지급이 지연되는 경우 연 6%의 "
        "지연손해금을 가산한다."
    ),
    EFFECT_TERMINATION: (
        "본조에 따른 해지권의 행사는 우리의 서면 통지로써 효력이 발생하며, 해지로 인하여 "
        "우리가 이미 제공한 급부의 반환 및 손해배상 청구권에 영향을 미치지 아니한다."
    ),
    EFFECT_PAYMENT: (
        "본조에 따른 지급 의무의 산정 근거와 지급 시기를 특정하며, 지급이 지연되는 경우 "
        "지연손해금을 가산하고 우리는 이를 상대방에 대한 다른 채무와 상계할 수 있다."
    ),
    EFFECT_DELIVERY: (
        "납품·검수의 기준과 기한을 본조에 특정하며, 기한 내 이행되지 아니한 경우 우리는 "
        "시정을 요구하거나 그에 상당하는 손해의 배상을 청구할 수 있다."
    ),
    EFFECT_OWNERSHIP: (
        "목적물의 소유권과 위험의 이전 시점을 본조에 특정하고, 그 시점까지 우리는 담보 "
        "목적의 소유권을 유보한다."
    ),
    EFFECT_IP: (
        "권리를 이전하는 당사자는 해당 결과물이 제3자의 권리를 침해하지 아니함을 보증하고, "
        "결과물에 포함된 제3자 소재에 대하여 본조의 이용 범위를 모두 충족하는 라이선스를 "
        "확보하여 그 증빙을 우리의 요청 시 제시한다."
    ),
    EFFECT_CONFIDENTIALITY: (
        "비밀유지의무를 부담하는 당사자는 본 계약 종료 시 우리의 요청에 따라 비밀정보를 "
        "반환 또는 파기하고 그 이행 결과를 서면으로 확인한다."
    ),
    EFFECT_PRIVACY: (
        "개인정보를 처리하는 당사자는 관계 법령상 요구되는 동의를 적법하게 확보하고, "
        "그 증빙을 우리의 요청 시 지체 없이 제시하며, 미확보로 인하여 발생한 제재·손해를 "
        "자신의 비용과 책임으로 해결한다."
    ),
    EFFECT_WARRANTY: (
        "하자담보책임의 기간을 인수일로부터 1년 이상으로 특정하며, 기간 내 발견된 하자는 "
        "상대방의 비용과 책임으로 보수한다."
    ),
    EFFECT_CHANGE: (
        "업무 범위의 변경 또는 추가는 우리의 사전 서면 승인을 받은 경우에만 효력이 있으며, "
        "승인 없이 수행된 업무에 대하여 우리는 대가 지급 의무를 부담하지 아니한다."
    ),
    EFFECT_SUBCONTRACT: (
        "상대방은 우리의 사전 서면 동의 없이 업무의 전부 또는 일부를 제3자에게 위탁할 수 "
        "없으며, 동의를 받아 위탁한 경우에도 그 제3자의 행위에 대하여 자신의 행위와 "
        "동일한 책임을 진다."
    ),
    EFFECT_DISPUTE: (
        "본 계약과 관련한 분쟁의 관할 법원을 본조에 특정한다."
    ),
    EFFECT_COMPLIANCE: (
        "상대방은 본 계약의 이행과 관련하여 적용되는 법령을 준수하며, 위반으로 인하여 "
        "관계기관의 조사·제재 또는 제3자의 청구가 발생한 경우 자신의 비용과 책임으로 "
        "이를 해결한다."
    ),
    EFFECT_SCOPE: (
        "상대방이 수행할 업무의 범위·산출물·완료 기준을 본조 또는 별첨으로 특정하며, "
        "특정된 기준을 충족하지 못한 이행은 이행으로 보지 아니한다."
    ),
}

#: 방향을 판단할 수 없을 때 — 어느 쪽 권리도 새로 만들지 않는 중립적 보완만.
_ADDITION_WHEN_UNKNOWN: dict[str, str] = {
    EFFECT_LIABILITY: (
        "본조에 따른 손해배상의 범위는 상당인과관계 있는 통상손해로 한정하며, 간접손해·"
        "특별손해·일실이익 및 제3자에 대한 배상책임은 제외한다. 본 계약에 따른 각 당사자의 "
        "배상 총액은 본 계약에 따라 지급되었거나 지급될 대가의 총액을 한도로 한다. 다만 "
        "고의 또는 중대한 과실로 인한 손해, 비밀유지의무 위반 및 제3자의 지식재산권 침해로 "
        "인한 손해에 대하여는 그러하지 아니하다."
    ),
    EFFECT_TERMINATION: (
        "당사자는 상대방이 본 계약상 의무를 위반한 경우 30일의 기간을 정하여 서면으로 시정을 "
        "요구하고, 그 기간 내에 시정되지 아니한 때에는 서면 통지로써 본 계약의 전부 또는 일부를 "
        "해지할 수 있다. 해지의 효력은 장래에 대하여 발생하며, 해지 시점까지 이행이 완료된 "
        "부분에 대한 대가는 해지일부터 30일 이내에 상호 정산한다. 해지는 위반 당사자에 대한 "
        "손해배상청구에 영향을 미치지 아니한다."
    ),
    EFFECT_PAYMENT: (
        "대가의 산정 기준과 지급 시기는 본조 또는 별첨에 정한 바에 따르며, 지급 당사자는 "
        "청구서를 수령한 날부터 30일 이내에 지급한다. 지급 당사자가 대가의 전부 또는 일부를 "
        "공제하거나 상계하거나 지급을 유보하려는 경우에는 그 사유와 금액을 명시한 서면을 "
        "지급기일 7일 전까지 상대방에게 통지하여야 하며, 통지하지 아니한 사유로는 공제·상계·"
        "유보할 수 없다. 지급이 지연된 경우 연 6퍼센트의 지연이자를 가산하여 지급한다."
    ),
    EFFECT_DELIVERY: (
        "납품 당사자는 본 계약에 정한 기한까지 목적물을 인도하고, 수령 당사자는 인도일부터 "
        "10영업일 이내에 본 계약 및 별첨에 정한 기준에 따라 검수하여 그 결과를 서면으로 "
        "통지한다. 위 기간 내에 통지가 없는 경우 검수에 합격한 것으로 본다. 검수에 불합격한 "
        "경우 그 사유를 구체적으로 적어 통지하여야 하며, 납품 당사자는 통지를 받은 날부터 "
        "10영업일 이내에 무상으로 보완하여 재납품한다."
    ),
    EFFECT_OWNERSHIP: (
        "목적물의 소유권과 멸실·훼손의 위험은 수령 당사자가 검수에 합격한 시점에 이전한다. "
        "그 시점까지 발생한 목적물의 멸실·훼손에 대하여는 납품 당사자가 책임을 부담하되, "
        "수령 당사자의 귀책사유로 인한 경우에는 그러하지 아니하다."
    ),
    EFFECT_IP: (
        "본조에 따라 이전 또는 허락되는 권리의 범위에는 2차적저작물작성권을 포함하며, 그 "
        "이용의 매체·기간·지역에는 제한을 두지 아니한다. 권리를 이전하거나 허락하는 당사자는 "
        "해당 목적물에 제3자의 권리가 포함되어 있지 아니함을 보증하고, 포함된 경우 상대방의 "
        "이용 범위를 모두 포괄하는 이용허락을 자기 비용으로 확보하여 제공한다. 창작에 관여한 "
        "임직원 및 제3자로 하여금 저작인격권을 행사하지 아니하도록 한다."
    ),
    EFFECT_CONFIDENTIALITY: (
        "다음 각 호의 정보는 비밀정보에서 제외한다. 1. 공개 당시 이미 공지된 정보 2. 수령 "
        "당사자의 귀책 없이 공지된 정보 3. 수령 당사자가 공개 전부터 적법하게 보유하고 있던 "
        "정보 4. 수령 당사자가 비밀정보와 무관하게 독자적으로 개발한 정보 5. 법령 또는 "
        "법원·감독기관의 적법한 요구에 따라 공개하는 정보. 제5호의 경우 수령 당사자는 "
        "가능한 범위에서 공개 전에 상대방에게 통지한다."
    ),
    EFFECT_PRIVACY: (
        "당사자는 본 계약의 이행과 관련하여 개인정보를 처리하는 경우 그 처리 목적, 처리하는 "
        "개인정보의 항목, 보유 및 이용 기간, 제3자 제공 및 처리위탁의 범위를 별도의 서면으로 "
        "특정하여 합의한 후에만 처리할 수 있다. 위 서면 합의가 체결되기 전까지 어느 당사자도 "
        "상대방으로부터 개인정보를 제공받거나 이를 처리하지 아니한다."
    ),
    EFFECT_WARRANTY: (
        "납품 당사자는 검수 합격일부터 1년간 목적물이 본 계약 및 별첨에 정한 사양에 부합함을 "
        "보증하며, 그 기간 중 발견된 하자를 자기 비용으로 보수한다. 다만 수령 당사자의 "
        "지시 또는 제공 자료에 기인한 하자와 통상의 사용에 따른 자연적 마모에 대하여는 "
        "그러하지 아니하다."
    ),
    EFFECT_CHANGE: (
        "본 계약에 정한 업무의 범위를 변경하거나 업무를 추가하려는 당사자는 변경 내용, 그에 "
        "따른 대가의 증감 및 기간의 조정을 적은 서면을 상대방에게 제출하고, 양 당사자가 "
        "서면으로 합의한 후에 이를 착수한다. 위 서면 합의 없이 수행된 업무에 대하여는 어느 "
        "당사자도 추가 대가를 청구하거나 이행을 요구할 수 없다."
    ),
    EFFECT_SUBCONTRACT: (
        "당사자는 상대방의 사전 서면 동의 없이 본 계약상 업무의 전부 또는 일부를 제3자에게 "
        "위탁할 수 없다. 동의를 얻어 위탁한 경우에도 위탁한 당사자는 제3자의 행위에 대하여 "
        "자신의 행위와 동일한 책임을 부담하며, 제3자에게 본 계약과 동일한 수준의 의무를 "
        "부담시켜야 한다."
    ),
    EFFECT_DISPUTE: (
        "본 계약과 관련하여 분쟁이 발생한 경우 당사자는 먼저 30일간 상호 협의하여 해결하도록 "
        "노력한다. 위 기간 내에 해결되지 아니한 분쟁의 제1심 관할 법원은 서울중앙지방법원으로 "
        "한다. 본 계약의 준거법은 대한민국 법으로 한다."
    ),
    EFFECT_COMPLIANCE: (
        "당사자는 본 계약의 이행과 관련하여 적용되는 대한민국의 법령을 준수한다. 어느 "
        "당사자의 법령 위반으로 상대방에게 과징금·과태료·시정명령 기타 손해가 발생한 경우 "
        "위반한 당사자가 그 손해를 배상한다."
    ),
    EFFECT_SCOPE: (
        "본 계약에 따라 수행할 업무의 범위, 산출물의 사양과 수량, 일정 및 완료 기준은 본조 "
        "또는 별첨에 구체적으로 특정한다. 별첨에 기재되지 아니한 업무는 본 계약의 범위에 "
        "포함되지 아니하며, 이를 요구하려면 제○조(업무의 변경)에 따른 서면 합의를 거쳐야 "
        "한다."
    ),
}

#: 하위호환 — 기존 호출부가 참조하던 이름. 방향을 모를 때의 표현을 쓴다.
_MINIMAL_ADDITION: dict[str, str] = _ADDITION_WHEN_UNKNOWN

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
    our_labels: tuple[str, ...] = (),
) -> tuple[str, str, str]:
    """원문 + 최소 방어장치로 이루어진 완성 문구를 만든다.

    [2026-09-11 지시] 덧붙이는 문장은 **방향에 따라 달라진다**. 우리가 의무를
    지는 조항에는 한도·예외를 넣어 우리를 보호하고, 상대방이 의무를 지는
    조항에는 그 의무를 깎지 않고 집행력만 보강한다. 대칭적으로 쓰면 우리가
    수혜자인 조항에까지 상대방의 방어권·시정기간을 새로 만들어주게 된다.

    돌려주는 값: (final_clause_text, addition, practical_position).
    만들 수 없으면 ("", "", "").
    """
    from runtime.review.clause_direction import (
        DIRECTION_THEY_BEAR,
        DIRECTION_WE_BEAR,
        burden_direction,
    )

    body = str(original_text or "").strip()
    if not body:
        return "", "", ""

    direction = burden_direction(body, our_labels)
    table = {
        DIRECTION_WE_BEAR: _ADDITION_WHEN_WE_BEAR,
        DIRECTION_THEY_BEAR: _ADDITION_WHEN_THEY_BEAR,
    }.get(direction, _ADDITION_WHEN_UNKNOWN)

    eff_list = effects or classify_clause_effects(title=clause_title, text=body)
    for eff in eff_list:
        addition = table.get(eff) or _ADDITION_WHEN_UNKNOWN.get(eff)
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
    our_labels: tuple[str, ...] = (),
) -> bool:
    """신뢰할 수 없는 문안을 **최소수정안**으로 교체한다.

    교체에 성공하면 True. 원문이 없어 문구를 만들 수 없으면 finding 을
    `FACT_CONFIRMATION_REQUIRED` 로 표시하고 False 를 돌려준다 — 자리표시자
    문구는 어느 경우에도 남기지 않는다.
    """
    if not isinstance(cr, dict):
        return False

    # 호칭을 명시로 받지 못했으면 finding 자체에 실린 것을 쓴다. 이 함수는
    # 게이트·다운로드 등 8곳에서 불리는데, 그 전부에 호칭을 인자로 꿰면 한
    # 곳만 빠져도 방향이 조용히 `unknown` 으로 떨어진다. 계약 컨텍스트는
    # finding 이 들고 다니는 편이 안전하다(2026-09-11).
    labels = tuple(our_labels or ())
    if not labels:
        stored = cr.get("our_labels")
        if isinstance(stored, (list, tuple)):
            labels = tuple(str(x) for x in stored if str(x or "").strip())

    original = str(cr.get("original_text") or "").strip()
    title = str(cr.get("clause_title") or "")
    final_text, addition, position = minimal_edit_for(
        original_text=original,
        clause_title=title,
        effects=(
            cr.get("clause_effects") if isinstance(cr.get("clause_effects"), list) else None
        ),
        our_labels=labels,
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
