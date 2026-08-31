"""Layer 1 — common legal risk rules.

These rules check for risk patterns that a corporate lawyer reviews in
EVERY contract, regardless of contract type: one-sided exemption from
liability (even for the counterparty's own fault), unlimited recourse
(including legal costs), blanket incorporation of external standard terms,
ambiguous payment-guarantee/joint-liability language, competitor/other-
institution dealing restrictions, and termination rights disproportionate
to the contract term.

Unlike the type-specific checklists in clause_level.py (_apply_supplier_
product_checklist, _apply_advisory_ip_review, etc.), rules here carry NO
contract_class gate — they are meant to survive the "계약유형 HARD BLOCK"
that filters out type-mismatched Layer 2 rules. HARD BLOCK must only ever
apply to Layer 2 (type-specific) rules; Layer 1 always runs.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.clause_extraction import ClauseChunk, find_clause_scoped_excerpt, find_all_clause_scoped_matches

_CLR_ITEMS: list[dict[str, Any]] = [
    {
        "id": "clr_fault_blind_exemption",
        "name": "귀책사유 불문 일방적 면책",
        "present": re.compile(
            r"귀책사유.{0,15}(여부에)?\s*(관계없이|불문하고|가리지\s*않고).{0,30}"
            r"(배상\s*책임|책임)을?\s*(지지\s*아니한다|부담하지\s*아니한다|면한다|없다)",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "상대방의 고의·과실(귀책사유)이 있는 경우까지 면책되지 않도록, 고의 또는 과실이 있는 경우는 면책 예외로 명시",
        "reason": (
            "귀책사유 유무와 관계없이 일체의 배상책임을 지지 않는다는 문언은 "
            "상대방의 고의 또는 과실(시험 오류 등)로 발생한 손해까지 면책하는 결과가 되어, "
            "손해배상 책임을 과도하게 배제하는 조항으로 그 효력이 다투어질 수 있다."
        ),
        "rewrite": (
            "본 조에 따른 면책은 수탁자(또는 상대방)의 고의 또는 과실이 없는 경우에 한하여 적용된다. "
            "수탁자의 고의 또는 과실로 발생한 손해(시험 오류 등 수탁자에게 귀책사유가 있는 경우를 포함한다)에 "
            "대하여는 본 조의 면책이 적용되지 아니한다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "clr_unlimited_recourse_with_legal_costs",
        "name": "소송비용·변호사보수 포함 무제한 구상",
        "present": re.compile(
            r"(소송\s*비용|변호사\s*보수).{0,25}(구상|배상)|구상.{0,25}(소송\s*비용|변호사\s*보수)",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "구상 범위에 상한(예: 계약금액 한도)을 두고, 상대방의 귀책사유가 있는 경우로 한정",
        "reason": (
            "손해배상액뿐 아니라 소송비용·변호사보수까지 포함하여 상한 없이 구상할 수 있도록 "
            "규정하면 실제 발생한 손해를 초과하는 금액까지 부담할 위험이 있고, "
            "상대방이 소송 수행 방식을 통제할 수 없는 당사자에게 그 비용 전부를 전가하는 결과가 된다."
        ),
        "rewrite": (
            "구상 범위는 실제 발생한 직접손해로 한정하며, 계약금액(또는 연간 대금)을 상한으로 한다. "
            "소송비용·변호사보수는 법원이 정한 소송비용 산입 기준을 초과하지 않는 범위에서만 구상할 수 있다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "clr_recourse_generic",
        "name": "구상권 범위·한도 불명확",
        "present": re.compile(r"(제반\s*비용|배상액)을?\s*.{0,10}구상할\s*수\s*있다", re.IGNORECASE | re.DOTALL),
        "risk": "MEDIUM",
        "direction": "구상 가능 범위와 한도를 구체적으로 특정",
        "reason": "구상 대상이 되는 비용의 범위·한도가 특정되어 있지 않아 분쟁 시 과다 청구로 이어질 수 있다.",
        "rewrite": "구상 대상 비용은 실제 발생하고 객관적으로 증빙 가능한 직접손해로 한정한다.",
        "clause_topic": "damage",
        "skip_if_also_matched": "clr_unlimited_recourse_with_legal_costs",
    },
    {
        "id": "clr_competitor_restriction_notice",
        "name": "동종 거래·경쟁 관계 제한(사전통보 의무)",
        "present": re.compile(
            r"(본\s*(계약|약정)).{0,10}같거나\s*유사한\s*내용의.{0,20}(계약|약정)을\s*체결.{0,30}사전에.{0,15}통보",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "사전통보 의무의 실질적 목적(이해상충 방지 등)을 명확히 하고, 통보 거부/지연에 따른 불이익이 없음을 확인",
        "reason": (
            "동종·유사 계약을 다른 상대방과 체결하기 전 상대방에게 사전 통보하도록 하는 조항은 "
            "실질적으로 거래 상대방 선택의 자유를 제약하거나, 통보 내용을 근거로 영업기밀이 "
            "상대방에게 노출될 위험이 있다."
        ),
        "rewrite": (
            "사전통보 의무는 이해상충 방지 목적에 한정하며, 통보 사실 자체가 계약 체결이나 "
            "조건 협상에 영향을 미치지 아니한다."
        ),
        "clause_topic": "other",
    },
    {
        "id": "clr_external_terms_incorporation",
        "name": "외부 표준약관·내부규정 포괄편입",
        "present": re.compile(
            # 표\s*준 (not just 표준\s*): a real FITI 시험분석약정서's PDF
            # line-wrap split "표준시험약관" as "표\n준시험약관" — a bare
            # literal "표준" substring can never match once a wrap falls
            # between its own two characters, unlike 문제 elsewhere in this
            # pattern that already tolerate \s* between tokens.
            r"(표\s*준\s*(시험)?\s*약관|내부\s*규정|업무\s*규정|운영\s*규정).{0,10}(적용|준용)한다",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "편입되는 약관·규정의 명칭·시행일·열람 방법을 특정하고, 계약 체결 시점 내용으로 고정(사후 일방 변경 배제)",
        "reason": (
            "상대방이 일방적으로 제정·개정할 수 있는 내부 약관·규정을 조항 내용을 특정하지 않고 "
            "그대로 편입시키면, 계약 상대방이 실제로 어떤 의무를 부담하는지 계약서만으로는 알 수 없고 "
            "상대방이 사후에 규정을 변경하여 불리하게 적용할 위험이 있다."
        ),
        "rewrite": (
            "본 약정에 편입되는 표준약관·내부규정은 본 약정 체결일 현재 시행 중인 내용을 기준으로 하며, "
            "위탁자에게 불리하게 사후 변경된 내용은 위탁자의 사전 서면 동의 없이는 적용하지 아니한다. "
            "수탁자는 위탁자의 요청 시 해당 약관·규정 전문을 즉시 제공한다."
        ),
        "clause_topic": "other",
    },
    {
        "id": "clr_payment_guarantee_ambiguous",
        "name": "지급보증/연대책임으로 확대해석될 수 있는 모호한 협조 의무",
        "present": re.compile(
            r"미수금이?\s*발생하지\s*않도록\s*적극\s*협조|연대하여\s*책임|연대\s*보증|연대\s*책임을?\s*진다",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "협조 의무를 결과채무(지급보증)가 아닌 수단채무(안내·독촉 등 절차적 협조)로 명확히 한정",
        "reason": (
            "'미수금이 발생하지 않도록 적극 협조한다'는 문언은 제3자(협력사 등)의 대금 미지급 위험을 "
            "위탁자가 사실상 보증하는 것으로 확대 해석될 여지가 있다. 협조의 구체적 내용과 한계가 "
            "특정되지 않으면 위탁자가 협력사의 채무를 대신 이행해야 하는 것으로 주장될 위험이 있다."
        ),
        "rewrite": (
            "위탁자의 협조 의무는 협력사에 대한 대금 청구 안내, 연락처 제공 등 절차적 협조에 한정하며, "
            "위탁자가 협력사의 미수금 채무를 보증하거나 연대하여 지급할 의무를 부담하는 것으로 해석되지 아니한다."
        ),
        "clause_topic": "payment_settlement",
    },
    # ── 변호사형 전체계약 판단 (2026-08-31 지시) — Priority 1: 계약금액 대비
    # 금전 리스크가 큰, 실제로 존재하는 불리한 조항. 물품공급/설치·용역 계약처럼
    # 갑(발주자/구매자)이 작성한 표준양식에서 반복되는 패턴이며, 개별 조항이
    # 아니라 계약 전체의 "책임 불균형"을 만드는 핵심 조항군이다.
    {
        "id": "clr_penalty_cumulative_with_actual_damage",
        "name": "지체상금·실손해 중복청구(누적 책임)",
        "present": re.compile(
            r"(지체상금|위약금)\s*외\s*실제\s*발생한?\s*손해액?을?\s*.{0,20}(손해배상으로)?\s*청구할\s*수\s*있다",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "지체상금은 손해배상액의 예정(위약금)으로 정하고, 실손해를 별도로 중복 청구하지 못하도록 명시(또는 지체상금을 공제한 초과분만 청구 가능하도록 한정)",
        "reason": (
            "지체상금을 지급한 뒤에도 실제 발생한 손해액을 별도로 다시 청구할 수 있도록 하면, "
            "동일한 지연에 대해 지체상금과 손해배상이 이중으로 누적되어 상한 없는 책임으로 이어질 수 있다. "
            "특히 대금 상계 조항과 결합되면 지연 발생 시 회사에 중복·누적 책임이 발생하는 구조가 된다."
        ),
        "rewrite": (
            "지체상금은 지체로 인한 손해배상액의 예정으로 하며, 상대방은 지체상금을 초과하는 "
            "실손해가 지체상금 산정과 무관한 별도의 손해임을 구체적으로 입증한 경우에 한하여 "
            "그 초과분만을 추가로 청구할 수 있다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "clr_penalty_multiple_of_contract_amount",
        "name": "계약금액 배수 위약벌",
        "present": re.compile(r"위약벌로서?\s*계약\s*금액의\s*(\d+)\s*배", re.IGNORECASE | re.DOTALL),
        "risk": "HIGH",
        "direction": "위약벌을 폐지하거나, 손해배상액의 예정으로 전환하고 계약금액 이내로 상한을 설정",
        "reason": (
            "손해 전부 배상 의무와 별개로 계약금액의 수 배에 달하는 위약벌을 추가로 부과하면, "
            "실제 손해 규모와 무관하게 계약금액 자체를 초과하는 금전적 리스크가 발생하고, "
            "손해배상과 위약벌이 함께 누적되어 과도한 제재로 그 효력이 다투어질 수 있다."
        ),
        "rewrite": (
            "본 조 위반 시 손해배상 책임은 실손해를 한도로 하며, 위약벌은 계약금액을 초과하지 않는 "
            "범위 내에서 상호 협의하여 정한다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "clr_no_fault_termination_by_counterparty",
        "name": "귀책사유 불문 상대방 일방 해지",
        "present": re.compile(
            r"귀책\s*사유를?\s*(불문|묻지\s*아니하고).{0,100}(해지|해제)"
            r"|(해지|해제).{0,100}귀책\s*사유를?\s*(불문|묻지\s*아니하고)",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "귀책사유 없는 지연(불가항력·상대방 협조 지연 등)은 해지 사유에서 제외하고, 우리 측 귀책사유가 있는 경우로 한정",
        "reason": (
            "우리 측 귀책사유가 없는 경우(불가항력, 상대방의 협조 지연 등)까지 상대방이 별도의 "
            "최고절차 없이 즉시 계약을 해지할 수 있도록 하면, 이미 투입한 비용을 회수하지 못한 채 "
            "일방적으로 계약관계에서 배제될 위험이 있다."
        ),
        "rewrite": (
            "본 호에 따른 해지는 상대방의 고의 또는 과실로 인한 경우에 한하며, 불가항력 또는 "
            "상대방(발주자)의 귀책사유로 인한 지연에는 적용되지 아니한다."
        ),
        "clause_topic": "termination",
    },
    {
        "id": "clr_counterparty_convenience_termination_no_compensation",
        "name": "상대방 편의(경영상 사유) 해지 — 보상 규정 없음",
        "present": re.compile(
            r"(경영상의?\s*이유|정부정책의?\s*변경|관련\s*법률의?\s*변경).{0,150}(해지|해제)할?\s*수\s*있다",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "편의해지 시 이미 투입한 비용(기투입 비용) 및 일실이익 상당액을 상대방이 보상하도록 명시",
        "reason": (
            "상대방의 경영상 이유 등 우리 측 귀책과 무관한 사유로도 사전 통지만으로 계약을 해지할 "
            "수 있도록 하면서, 그로 인해 이미 투입한 비용을 보상하는 규정이 없으면 사업상 손실을 "
            "고스란히 우리 측이 부담하게 된다."
        ),
        "rewrite": (
            "본 항에 따라 상대방이 해지하는 경우, 상대방은 해지 통지일까지 우리 측이 이미 지출·"
            "투입한 비용 및 이미 이행한 부분에 대한 정당한 대가를 지급하여야 한다."
        ),
        "clause_topic": "termination",
    },
    {
        "id": "clr_sunk_cost_not_recoverable_on_termination",
        "name": "해지 시 기투입비용 미보전 + 회수비용 우리측 부담",
        "present": re.compile(r"자신의\s*비용과\s*책임으로\s*회수", re.IGNORECASE | re.DOTALL),
        "risk": "MEDIUM",
        "direction": "해지 시 이미 투입한 비용의 정산·보전 규정을 추가하고, 물품 회수비용은 해지 귀책 당사자가 부담하도록 명시",
        "reason": (
            "계약 해지·해제 시 이미 투입한 비용(제작·운송·설치 등)을 보전받지 못한 채, 회수한 "
            "물품의 회수비용까지 우리 측이 부담하도록 하면 상대방 귀책 해지의 경우에도 손실이 "
            "고스란히 우리 측에 귀속된다."
        ),
        "rewrite": (
            "해지·해제에 대해 상대방에게 귀책사유가 있는 경우, 회수비용은 상대방이 부담하며, "
            "우리 측이 이미 투입한 비용은 상대방이 정산·보전한다."
        ),
        "clause_topic": "termination",
    },
    {
        "id": "clr_defect_liability_regardless_of_fault",
        "name": "제품 하자책임 — 귀책사유 불문",
        "present": re.compile(
            r"하자로?\s*인해?\s*손해가\s*발생할\s*경우,?\s*귀책사유를?\s*불문",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "하자책임도 우리 측 고의·과실이 있는 경우로 한정하고, 통상적 사용에 따른 자연마모·상대방 취급 부주의는 면책 사유로 명시",
        "reason": (
            "제품 하자로 인한 손해에 대해 귀책사유를 불문하고 책임을 지도록 하면, 원자재 결함· "
            "제조상 불가피한 사유·상대방의 부적절한 취급으로 인한 하자까지 무과실 책임을 지게 되어 "
            "책임 범위가 지나치게 넓다."
        ),
        "rewrite": (
            "하자로 인한 손해배상 책임은 하자가 우리 측의 고의 또는 과실에 기인한 경우에 한하며, "
            "상대방 또는 사용자의 부적절한 사용·보관·개조로 인한 하자에는 적용되지 아니한다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "clr_immediate_indemnify_third_party_claim",
        "name": "제3자 청구 즉시 면책 의무",
        "present": re.compile(
            r"즉시\s*[“\"]?(갑|발주자|구매자|위탁자|본\s*사)[”\"]?(을|를)?\s*면책",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "제3자 청구에 대한 방어·대응 절차(통지·협조·비용 분담)를 먼저 규정하고, 면책은 우리 측 귀책이 확정된 경우로 한정",
        "reason": (
            "제3자가 손해배상을 청구하기만 하면 그 진위·귀책과 무관하게 상대방을 즉시 면책시켜야 "
            "한다는 문언은, 청구 금액·정당성에 대한 다툼 기회 없이 방어권을 박탈하고 무제한 배상 "
            "의무로 이어질 위험이 있다."
        ),
        "rewrite": (
            "제3자의 청구에 대하여는 상대방으로부터 지체 없이 통지받아 방어에 참여할 권리를 가지며, "
            "우리 측의 귀책사유가 최종 확정된 부분에 한하여 배상 책임을 부담한다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "clr_full_payment_refusal_or_withhold",
        "name": "대금 전액 지급거절·유예",
        "present": re.compile(
            r"대금의?\s*(전부|전액)\s*(을|를)?\s*(지급을?\s*)?(거부|거절|유예)할\s*수\s*있다",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "지급거절·유예는 하자·미인도 부분에 상응하는 금액으로 한정하고, 나머지 부분의 대금은 정상 지급하도록 명시",
        "reason": (
            "일부 하자나 일부 미인도만 있어도 대금 전액의 지급을 거절·유예할 수 있도록 하면, "
            "이미 정상 이행한 부분에 대한 대가까지 받지 못하는 유동성 리스크가 발생한다."
        ),
        "rewrite": (
            "대금 지급의 거절·유예는 하자 또는 미인도 부분에 상응하는 금액에 한정하며, 나머지 "
            "정상 이행 부분에 대한 대금은 약정된 기한에 지급한다."
        ),
        "clause_topic": "payment_settlement",
    },
    {
        "id": "clr_inspection_repeat_failure_immediate_termination",
        "name": "검수 반복 불합격 시 귀책불문 즉시해지",
        "present": re.compile(
            r"검수에?\s*누적하여?\s*(\d+)\s*회\s*이상\s*불합격.{0,70}(해지|해제)",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "재검수 절차와 보완 기회를 명시하고, 즉시해지는 우리 측 귀책이 명백한 반복 불합격으로 한정",
        "reason": (
            "검수 불합격이 상대방의 사양 변경·불명확한 기준 제시 등 우리 측 귀책이 아닌 사유로도 "
            "발생할 수 있는데, 이 경우까지 귀책사유를 불문하고 최고절차 없이 즉시 해지할 수 있도록 "
            "하면 정당한 보완 기회 없이 계약이 종료될 위험이 있다."
        ),
        "rewrite": (
            "검수 불합격이 우리 측 귀책사유로 인한 경우에 한하여, 재검수 기회를 부여한 후에도 "
            "누적 2회 이상 불합격한 때에 해지할 수 있다."
        ),
        "clause_topic": "termination",
    },
    {
        "id": "clr_scope_creep_unilateral_additional_demand",
        "name": "상대방의 일방적 추가 요구사항 포함 조항",
        "present": re.compile(
            r"[“\"]?(갑|발주자|구매자|위탁자)[”\"]?이?\s*추가로\s*요구하는\s*사항을?\s*포함한다",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "계약 범위를 명확히 정의하고, 추가 요구사항은 별도 서면 합의 및 대가 조정을 거치도록 명시",
        "reason": (
            "계약 범위(급부)에 상대방이 추가로 요구하는 사항을 포괄적으로 포함시키면, 대가 조정 "
            "없이 업무 범위가 일방적으로 확대될 수 있다(scope creep)."
        ),
        "rewrite": (
            "계약 범위는 본 조에서 정한 사항으로 한정하며, 상대방의 추가 요구사항은 양 당사자의 "
            "서면 합의 및 그에 따른 대금 조정을 거친 경우에만 계약 범위에 포함된다."
        ),
        "clause_topic": "other",
    },
    {
        "id": "clr_broad_uncapped_accident_liability",
        "name": "포괄적·무제한 사고 책임",
        "present": re.compile(r"제반\s*사고.{0,140}일체의?\s*책임을?\s*부담", re.IGNORECASE | re.DOTALL),
        "risk": "MEDIUM",
        "direction": "책임 범위를 우리 측 이행 과정에서 발생한 사고로 한정하고, 상대방·제3자의 관리 부주의로 인한 사고는 제외",
        "reason": (
            "이행 과정에서 발생하는 '제반 사고'에 대해 포괄적으로 일체의 책임을 부담하도록 하면, "
            "상대방 또는 제3자의 관리·감독 부주의로 발생한 사고까지 책임 범위에 포함될 수 있다."
        ),
        "rewrite": (
            "본 조의 책임은 우리 측 또는 우리 측 피용인의 고의·과실로 발생한 사고에 한정하며, "
            "상대방 또는 제3자의 관리·감독상 귀책사유로 발생한 사고에는 적용되지 아니한다."
        ),
        "clause_topic": "damage",
    },
]

_RX_LATE_PENALTY_RATE = re.compile(
    r"지체일수\s*당\s*총?\s*[“\"]?대금[”\"]?의\s*(\d+)\s*/\s*(\d+)"
    r"|지체.{0,10}(?:1\s*)?일.{0,10}당?.{0,10}(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE | re.DOTALL,
)
_RX_PENALTY_CAP = re.compile(r"(상한|한도|최대|초과할?\s*수\s*없다)", re.IGNORECASE)


_RX_CONTRACT_TERM_YEARS = re.compile(r"(\d)\s*년\s*(?:간|으로)?\s*(?:한다|간의\s*유효기간)", re.DOTALL)
_RX_CONVENIENCE_TERMINATION = re.compile(
    r"(임의|수시로?)\s*해지|사전\s*통지\s*(?:후|만으로)\s*해지|[0-9]+\s*(?:일|개월)\s*전\s*(?:서면\s*)?통지.{0,15}해지",
    re.IGNORECASE | re.DOTALL,
)
_RX_CAUSE_ONLY_TERMINATION = re.compile(r"중대한\s*(?:약정|계약)\s*위반", re.IGNORECASE | re.DOTALL)


def _apply_common_legal_risk_rules(
    clause_results: list[dict[str, Any]],
    full_text: str,
    clauses: list[ClauseChunk] | None = None,
) -> None:
    """[Layer 1] Common legal risk checklist — runs for EVERY contract type.

    Mirrors the shape of the type-specific checklists (present-pattern ->
    inject if the clause doesn't already exist) but carries no contract_class
    gate, so it must never be touched by the HARD BLOCK logic that scopes
    Layer 2 rules.

    The "원문" quote is scoped to a single article via `clauses` (the
    already-confirmed segmentation) whenever it's available — searching the
    raw whole-document string with a fixed character window used to let the
    quote bleed into the next article's heading/body once a match happened
    to sit near the end of its own article. `full_text` is kept only as a
    fallback for the rare caller that has no segmented clauses at all.
    """
    text = str(full_text or "")
    existing_ids = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    # Maps each matched item's id -> the set of display_paths it already
    # covers, so a weaker duplicate pattern (e.g. clr_recourse_generic) is
    # only skipped at a clause the stronger pattern (clr_unlimited_recourse_
    # with_legal_costs) actually covers — a genuinely separate clause using
    # the weaker wording (no "소송비용"/"변호사보수", just "제반 비용") at a
    # *different* article must still surface, not vanish entirely just
    # because the stronger pattern happened to fire somewhere else in the
    # document.
    matched_display_paths_by_id: dict[str, set[str]] = {}

    for item in _CLR_ITEMS:
        if item["id"] in existing_ids:
            continue
        raw_matches = find_all_clause_scoped_matches(clauses, item["present"])
        skip_if = item.get("skip_if_also_matched")
        all_matches = raw_matches
        if skip_if and raw_matches:
            excluded_paths = matched_display_paths_by_id.get(skip_if, set())
            if excluded_paths:
                all_matches = [m for m in raw_matches if not (m.display_path and m.display_path in excluded_paths)]
                if not all_matches:
                    # Every occurrence of this weaker pattern sits at a clause
                    # already covered by the stronger pattern — a genuine
                    # duplicate, not a distinct finding. Do NOT fall through to
                    # the legacy single-match path below: it doesn't know about
                    # the exclusion and would just rediscover the same clause.
                    continue
        paragraph_number: str | None = None
        item_number: str | None = None
        display_path: str | None = None
        related_clauses: list[str] = []
        if all_matches:
            first = all_matches[0]
            excerpt, article_number = first.excerpt, first.article_number
            paragraph_number = first.paragraph_number
            item_number = first.item_number
            display_path = first.display_path
            # Sibling occurrences of the same defect pattern (e.g. an identical
            # exemption clause repeated at both 제6조 and 제11조) must not be
            # silently covered by only the first match — list them so the
            # reviewer/Word output sees every clause carrying the same issue.
            seen_paths = {display_path} if display_path else set()
            for other in all_matches[1:]:
                if other.display_path and other.display_path not in seen_paths:
                    related_clauses.append(other.display_path)
                    seen_paths.add(other.display_path)
            matched_display_paths_by_id[item["id"]] = {m.display_path for m in raw_matches if m.display_path}
        else:
            scoped = find_clause_scoped_excerpt(clauses, item["present"])
            if scoped is not None:
                excerpt, article_number = scoped
            else:
                if clauses:
                    # Segmented clauses exist but none of them matched — trust
                    # the segmentation over a raw full-text scan rather than
                    # risk a cross-article quote.
                    continue
                m = item["present"].search(text)
                if not m:
                    continue
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 120)
                excerpt = text[start:end].strip()
                article_number = None
        risk = item["risk"]
        clause_title = f"{display_path} [{item['name']}]" if display_path else f"[공통 법률리스크] {item['name']}"
        clause_results.append({
            "clause_id": item["id"],
            "article_number": article_number,
            "paragraph_number": paragraph_number,
            "item_number": item_number,
            "display_path": display_path,
            "clause_title": clause_title,
            "clause_number_uncertain": not bool(display_path),
            "related_clauses": related_clauses,
            "clause_topic": item.get("clause_topic", "other"),
            "original_text": excerpt,
            "risk_tier": risk,
            "severity": risk,
            "high_risk": risk == "HIGH",
            "must_fix": risk == "HIGH",
            "approval_required": risk == "HIGH",
            "review_tier": "MUST" if risk == "HIGH" else "SUGGEST",
            "suggested_rewrite": item["rewrite"],
            "rewrite_reason": item["reason"],
            "suggested_direction": [item["direction"]],
            "negotiation_position": "상대방 반발 가능성이 있으나 법적 책임 범위 명확화 차원에서 협상 필요",
            "confidence": 0.85,
            "is_common_legal_risk": True,
            "has_rewrite_change": True,
            "display_kind": "redline" if risk == "HIGH" else "guidance",
            "dedup_suppressed": False,
            "keep_as_is": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "ai_deep_reviewed": False,
        })

    _apply_termination_vs_term_check(clause_results, text, clauses)
    _apply_late_penalty_uncapped_check(clause_results, text, clauses)


def _apply_late_penalty_uncapped_check(
    clause_results: list[dict[str, Any]],
    text: str,
    clauses: list[ClauseChunk] | None = None,
) -> None:
    """변호사형 전체계약 판단 (2026-08-31 지시) > 금전 리스크 최우선 분석.

    지체상금을 키워드만으로 탐지하지 않고, 일할 요율을 실제 계산하여 10일·
    30일 지연 시 계약금액 대비 몇 %에 달하는지 원문 인용에 함께 보여준다.
    상한(캡) 문구가 같은 조항 안에 없으면 무제한 누적 가능한 것으로 보아
    HIGH로 판단한다.
    """
    if "clr_late_penalty_rate_uncapped" in {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}:
        return
    for c in (clauses or []):
        leaf_text = str(getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else "") or "")
        m = _RX_LATE_PENALTY_RATE.search(leaf_text)
        if not m:
            continue
        if m.group(1) and m.group(2):
            rate_pct = float(m.group(1)) / float(m.group(2)) * 100
        elif m.group(3):
            rate_pct = float(m.group(3))
        else:
            continue
        has_cap = bool(_RX_PENALTY_CAP.search(leaf_text))
        art = str(getattr(c, "article_number", None) or (c.get("article_number") if isinstance(c, dict) else "") or "").strip() or None
        para = str(getattr(c, "paragraph_number", None) or (c.get("paragraph_number") if isinstance(c, dict) else "") or "").strip() or None
        display_path = str(getattr(c, "display_path", None) or (c.get("display_path") if isinstance(c, dict) else "") or "").strip() or None
        rate_str = f"{rate_pct:g}"
        ten_day = f"{rate_pct * 10:g}"
        thirty_day = f"{rate_pct * 30:g}"
        title = f"{display_path} [지체상금율 미계산·상한 부재]" if display_path else "[공통 법률리스크] 지체상금율 미계산·상한 부재"
        clause_results.append({
            "clause_id": "clr_late_penalty_rate_uncapped",
            "article_number": art,
            "paragraph_number": para,
            "display_path": display_path,
            "clause_title": title,
            "clause_number_uncertain": not bool(display_path),
            "clause_topic": "damage",
            "original_text": leaf_text.strip()[:400],
            "risk_tier": "HIGH" if not has_cap else "MEDIUM",
            "severity": "HIGH" if not has_cap else "MEDIUM",
            "high_risk": not has_cap,
            "must_fix": not has_cap,
            "approval_required": not has_cap,
            "review_tier": "MUST" if not has_cap else "SUGGEST",
            "suggested_rewrite": (
                f"지체상금은 지체일수 당 대금의 {rate_str}%로 하되, 지체상금 누계액은 대금의 "
                "10%를 초과할 수 없다."
            ),
            "rewrite_reason": (
                f"지체일수 당 대금의 {rate_str}%로 계산되어, 10일 지연 시 대금의 {ten_day}%, "
                f"30일 지연 시 대금의 {thirty_day}%에 달한다. "
                + (
                    "상한(캡) 규정이 없어 지연이 길어질수록 배상액이 무제한으로 누적될 수 있다."
                    if not has_cap
                    else "다만 상한 문구가 확인되어 완전 무제한은 아니므로 실제 상한 수준을 확인해야 한다."
                )
            ),
            "suggested_direction": ["지체상금 누계 상한(예: 대금의 10%) 설정"],
            "negotiation_position": "지체상금율 자체보다 '상한 부재'가 협상 포인트 — 상한 신설을 우선 요구",
            "confidence": 0.85,
            "is_common_legal_risk": True,
            "has_rewrite_change": True,
            "display_kind": "redline" if not has_cap else "guidance",
            "dedup_suppressed": False,
            "keep_as_is": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "ai_deep_reviewed": False,
        })
        return


def _apply_termination_vs_term_check(
    clause_results: list[dict[str, Any]],
    text: str,
    clauses: list[ClauseChunk] | None = None,
) -> None:
    """계약기간 대비 해지권 과도 제한: 1년 이상 계약인데 임의(편의)해지권 없이
    '중대한 위반' 사유로만 해지가 가능한 경우를 탐지한다."""
    if "clr_termination_right_restricted" in {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}:
        return
    term_match = _RX_CONTRACT_TERM_YEARS.search(text)
    has_long_term = bool(term_match) and int(term_match.group(1)) >= 1
    has_cause_only = bool(_RX_CAUSE_ONLY_TERMINATION.search(text))
    has_convenience = bool(_RX_CONVENIENCE_TERMINATION.search(text))
    if not (has_long_term and has_cause_only and not has_convenience):
        return
    years = term_match.group(1) if term_match else "장기"
    all_matches = find_all_clause_scoped_matches(clauses, _RX_CAUSE_ONLY_TERMINATION, after=100)
    cause_paragraph: str | None = None
    cause_display_path: str | None = None
    if all_matches:
        first = all_matches[0]
        cause_excerpt, cause_article = first.excerpt, first.article_number
        cause_paragraph = first.paragraph_number
        cause_display_path = first.display_path
    else:
        scoped = find_clause_scoped_excerpt(clauses, _RX_CAUSE_ONLY_TERMINATION, after=100)
        if scoped is not None:
            cause_excerpt, cause_article = scoped
        elif not clauses:
            m = _RX_CAUSE_ONLY_TERMINATION.search(text)
            cause_excerpt = text[max(0, m.start() - 40): m.end() + 100].strip() if m else ""
            cause_article = None
        else:
            # Segmented clauses exist but none contain the cause-only-termination
            # match — do not fall back to a raw cross-article window.
            return
    _title = f"{cause_display_path} [계약기간 대비 해지권 과도 제한]" if cause_display_path else "[공통 법률리스크] 계약기간 대비 해지권 과도 제한"
    clause_results.append({
        "clause_id": "clr_termination_right_restricted",
        "article_number": cause_article,
        "paragraph_number": cause_paragraph,
        "display_path": cause_display_path,
        "clause_title": _title,
        "clause_number_uncertain": not bool(cause_display_path),
        "clause_topic": "termination",
        "original_text": cause_excerpt,
        "risk_tier": "MEDIUM",
        "severity": "MEDIUM",
        "high_risk": False,
        "must_fix": False,
        "approval_required": False,
        "review_tier": "SUGGEST",
        "suggested_rewrite": (
            "위 해지 사유와 별개로, 위탁자는 상당한 기간(예: 3개월) 전 서면 통지로 본 약정을 "
            "중도 해지할 수 있다. 이 경우 이미 수행된 업무에 대한 정산 외에 위약금 등 추가 "
            "부담을 지지 아니한다."
        ),
        "rewrite_reason": (
            f"약정기간이 {years}년 이상으로 장기임에도 '중대한 위반' 등 상대방 귀책사유가 있는 "
            "경우로만 해지가 제한되어 있고, 위탁자가 사전 통지만으로 계약관계에서 벗어날 수 있는 "
            "임의(편의)해지권이 없다. 사업상 필요(거래처 변경, 사업 축소 등)로 계약관계를 종료해야 "
            "하는 경우 상대방 귀책사유가 확인될 때까지 장기간 계약에 구속될 위험이 있다."
        ),
        "suggested_direction": ["장기 계약에 임의(편의)해지권 추가"],
        "negotiation_position": "상대방 반발 가능성이 있으나 법적 책임 범위 명확화 차원에서 협상 필요",
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
