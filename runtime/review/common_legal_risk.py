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

_RX_PENALTY_CUMULATIVE_DAMAGE = re.compile(
    r"(지체상금|위약금)\s*외\s*실제\s*발생한?\s*손해액?을?\s*.{0,20}(손해배상으로)?\s*청구할\s*수\s*있다",
    re.IGNORECASE | re.DOTALL,
)

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
        # "연대하여 책임을 진다"는 양도·하도급 조항의 통상적인 문구(양수인이
        # 원채무자의 책임을 면제시키지 않는다는 취지)로도 흔히 쓰이며, 그
        # 자체로는 지급보증 문제가 아니다 — 미수금/대금/채무 같은 결제
        # 맥락과 함께 나타날 때만 지급보증으로 확대해석될 위험이 있다
        # (변호사형 전체계약 판단 지시, 2026-09-01 — NDA 양도조항의 연대
        # 책임을 지급보증으로 오독하던 사례).
        "present": re.compile(
            r"미수금이?\s*발생하지\s*않도록\s*적극\s*협조"
            r"|(미수금|대금|채무|지급)[^.\n]{0,30}(연대하여\s*책임|연대\s*보증|연대\s*책임을?\s*진다)"
            r"|(연대하여\s*책임|연대\s*보증|연대\s*책임을?\s*진다)[^.\n]{0,30}(미수금|대금|채무|지급)",
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
        # 같은 조항에 지체상금 무상한 패턴(_RX_LATE_PENALTY_RATE)이 함께
        # 있으면 _apply_late_penalty_uncapped_check가 이 항목을 흡수해 하나의
        # 클러스터 finding으로 합친다(변호사형 전체계약 판단 지시,
        # 2026-08-31 — "지체상금+실손해+중복" 3요소를 하나의 HIGH로 판단).
        # 여기 남겨두는 이유는 지체상금 요율이 없는(또는 다른 조항에 분리된)
        # 계약에서도 이 패턴 단독으로 여전히 탐지되어야 하기 때문.
        "id": "clr_penalty_cumulative_with_actual_damage",
        "name": "지체상금·실손해 중복청구(누적 책임)",
        "present": _RX_PENALTY_CUMULATIVE_DAMAGE,
        "risk": "HIGH",
        "direction": "지체상금은 손해배상액의 예정(위약금)으로 정하고, 실손해를 별도로 중복 청구하지 못하도록 명시(또는 지체상금을 공제한 초과분만 청구 가능하도록 한정)",
        "reason": "지체상금을 지급한 뒤에도 실제 발생한 손해액을 별도로 다시 청구할 수 있어, 동일한 지연에 대해 지체상금과 손해배상이 이중으로 누적된다.",
        "legal_business_reason": (
            "상한 없는 지체상금에 실손해 청구까지 결합되면 지연 1건에 대한 총 배상액을 "
            "사전에 예측·통제할 수 없고, 대금 상계 조항과 결합되면 정산 단계에서 회사가 "
            "실제로 받을 대금이 예상보다 크게 줄어드는 유동성 리스크로 이어진다."
        ),
        "rewrite": (
            "지체상금은 지체로 인한 손해배상액의 예정으로 하며, 상대방은 지체상금을 초과하는 "
            "실손해가 지체상금 산정과 무관한 별도의 손해임을 구체적으로 입증한 경우에 한하여 "
            "그 초과분만을 추가로 청구할 수 있다."
        ),
        "negotiation_position": "지체상금 요율 인하·총액 상한과 함께 3개 요소를 한 번에 묶어 협상 — 실손해 중복청구는 최소한 '지체상금 초과분 입증 시에만' 방식으로 제한 요청.",
        "clause_topic": "damage",
    },
    {
        "id": "clr_penalty_multiple_of_contract_amount",
        "name": "계약금액 배수 위약벌",
        "present": re.compile(r"위약벌로서?\s*계약\s*금액의\s*(\d+)\s*배", re.IGNORECASE | re.DOTALL),
        "risk": "HIGH",
        # 수정 순서는 "삭제 → (삭제 어려우면) cap" 순으로 판단한다 — 첫
        # 수정안부터 "계약금액 한도로 협의" cap을 제시하면 3배 위약벌이라는
        # 출발점을 그대로 인정하는 꼴이 되어 협상 레버리지를 스스로 낮춘다
        # (변호사형 전체계약 판단 지시, 2026-08-31).
        "direction": "1순위: 위약벌 조항 삭제 후 실제 직접손해 배상으로 대체. 삭제가 어려운 경우에만 계약금액 이내 cap 협상",
        "reason": "손해 전부 배상 의무와 별개로 계약금액의 수 배에 달하는 위약벌이 추가로 부과된다.",
        "legal_business_reason": (
            "실제 손해 규모와 무관하게 계약금액 자체를 초과하는 금전적 리스크가 발생하고, "
            "손해배상과 위약벌이 함께 누적되면 과도한 제재로 그 효력 자체가 다투어질 수 있다."
        ),
        "rewrite": (
            "본 조의 위약벌 조항은 삭제하고, 위반 당사자는 자신의 귀책사유와 상당인과관계 있는 "
            "실제 발생 직접손해를 배상한다. (삭제가 불가능한 경우에 한하여 예비적으로: 위약벌은 "
            "계약금액을 초과하지 않는 범위 내에서 상호 협의하여 정하고, 손해배상과 중복 청구하지 "
            "아니한다.)"
        ),
        "negotiation_position": "3배 위약벌 삭제를 1순위로 요청. 삭제 불가 시 현저한 감액 및 손해배상과의 중복 배제를 협상.",
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
        "reason": "우리 측 귀책사유가 없는 지연까지 상대방이 최고절차 없이 즉시 계약을 해지할 수 있다.",
        "legal_business_reason": (
            "불가항력이나 상대방의 협조 지연으로 인한 미인도까지 해지 사유가 되면, 이미 투입한 "
            "비용을 회수하지 못한 채 일방적으로 계약관계에서 배제될 위험이 있고 정산·손해배상을 "
            "다툴 협상력도 함께 잃는다."
        ),
        "rewrite": (
            "본 호에 따른 해지는 상대방의 고의 또는 과실로 인한 경우에 한하며, 불가항력 또는 "
            "상대방(발주자)의 귀책사유로 인한 지연에는 적용되지 아니한다."
        ),
        "negotiation_position": "해지권 자체보다 '귀책사유 요건 추가'를 우선 요청 — 삭제가 어려우면 최소한 불가항력·상대방 귀책 지연은 예외로 명시.",
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
        "reason": "상대방의 경영상 이유 등 우리 측 귀책과 무관한 사유로도 사전 통지만으로 계약을 해지할 수 있다.",
        "legal_business_reason": (
            "편의해지 시 이미 투입한 비용을 보전받는 규정이 없어 사업상 손실을 고스란히 우리 측이 "
            "부담하게 되며, 특히 이미 제작·발주가 진행 중인 물품에 대해서는 회수도 어려워 매몰 "
            "비용 리스크가 크다."
        ),
        "rewrite": (
            "본 항에 따라 상대방이 해지하는 경우, 상대방은 해지 통지일까지 우리 측이 이미 지출·"
            "투입한 비용 및 이미 이행한 부분에 대한 정당한 대가를 지급하여야 한다."
        ),
        "negotiation_position": "해지권 자체보다 기투입비용 및 완료분 대금 보전 확보를 우선 요청.",
        "clause_topic": "termination",
    },
    {
        "id": "clr_sunk_cost_not_recoverable_on_termination",
        "name": "해지 시 기투입비용 미보전 + 회수비용 우리측 부담",
        "present": re.compile(r"자신의\s*비용과\s*책임으로\s*회수", re.IGNORECASE | re.DOTALL),
        "risk": "MEDIUM",
        "direction": "해지 시 이미 투입한 비용의 정산·보전 규정을 추가하고, 물품 회수비용은 해지 귀책 당사자가 부담하도록 명시",
        "reason": "해지·해제 시 이미 투입한 비용을 보전받지 못한 채 물품 회수비용까지 우리 측이 부담한다.",
        "legal_business_reason": (
            "상대방 귀책으로 해지되는 경우에도 회수비용을 우리가 부담하게 되면, 계약 불이행의 "
            "책임 소재와 무관하게 물류·인건비 손실이 전액 우리 측에 귀속되는 결과가 된다."
        ),
        "rewrite": (
            "해지·해제에 대해 상대방에게 귀책사유가 있는 경우, 회수비용은 상대방이 부담하며, "
            "우리 측이 이미 투입한 비용은 상대방이 정산·보전한다."
        ),
        "negotiation_position": "회수비용 부담 주체를 해지 귀책 당사자 기준으로 전환하는 최소수정 — 기투입비용 정산 조항 신설을 함께 요청.",
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
        # 제조물책임법상 법정책임(강행규정)과 계약으로 추가·제한 가능한
        # 계약상 책임을 구분한다 — "고의 또는 과실이 있는 경우에만 책임"으로
        # 전부 제한하면 법정책임까지 배제하는 것으로 오인될 수 있고, 협상
        # 상대방이 수용하기 어려운 과도한 면책으로 비칠 위험도 있다(변호사형
        # 전체계약 판단 지시, 2026-08-31 — 항목 3·4).
        "direction": "계약상 무과실책임 확대는 우리 측 고의·과실이 있는 경우로 한정하되, 제조물책임법 등 법정책임은 별도로 존재함을 carve-out으로 명시하고 상대방·제3자 귀책, 불가항력은 책임 범위에서 제외",
        "reason": "제품 하자로 인한 손해에 대해 귀책사유를 불문하고 책임을 지도록 하는 계약상 무과실책임 확대 조항이다.",
        "legal_business_reason": (
            "원자재 결함·제조상 불가피한 사유처럼 우리 측 과실이 없는 하자까지 계약상 무과실 "
            "책임을 지게 되어 범위가 지나치게 넓고, 반대로 이를 '고의 또는 과실이 있는 경우'로만 "
            "전부 제한하면 제조물책임법 등에 따라 별도로 존재하는 법정책임까지 배제하려는 것으로 "
            "오인되어 상대방이 수용하기 어려운 과도한 면책으로 비칠 수 있다."
        ),
        "rewrite": (
            "을은 을의 고의 또는 과실로 발생한 하자로 인한 손해에 대하여 책임을 부담하되, 갑 "
            "또는 제3자의 귀책사유, 통상적 사용에 따른 자연마모, 갑 또는 사용자의 부적절한 사용· "
            "보관·개조, 불가항력 등 을의 책임 없는 사유로 인한 손해에는 적용되지 아니한다. 다만 "
            "관련 법령(제조물책임법 등)에 따라 별도로 인정되는 법정책임은 이 조항으로 제외되지 "
            "아니한다."
        ),
        "negotiation_position": "무과실책임 확대는 반대하되, 제조물책임법상 법정책임까지 배제하려는 것으로 비치지 않도록 carve-out 문구를 함께 제시 — 최소수정으로 상대방 수용 가능성을 높인다.",
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
        "reason": "제3자가 청구하기만 하면 그 진위·귀책과 무관하게 상대방을 즉시 면책시켜야 한다.",
        "legal_business_reason": (
            "청구 금액·정당성에 대한 다툼 기회 없이 방어권을 박탈당한 채 상대방이 지급한 배상금을 "
            "그대로 구상당하면, 부당한 제3자 청구에도 우리가 사실상 무제한으로 노출된다."
        ),
        "rewrite": (
            "제3자의 청구에 대하여는 상대방으로부터 지체 없이 통지받아 방어에 참여할 권리를 가지며, "
            "우리 측의 귀책사유가 최종 확정된 부분에 한하여 배상 책임을 부담한다."
        ),
        "negotiation_position": "즉시 면책 문구 삭제보다 '통지·방어참여권 확보'를 우선 요청 — 면책 자체를 없애기보다 우리가 다툴 기회를 넣는 최소수정.",
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
        "reason": "일부 하자나 일부 미인도만 있어도 대금 전액의 지급을 거절·유예할 수 있다.",
        "legal_business_reason": (
            "이미 정상적으로 인도·이행한 부분에 대한 대가까지 지급이 보류되면, 소규모 하자 분쟁이 "
            "전체 대금 회수 지연으로 확대되는 유동성 리스크가 발생한다."
        ),
        "rewrite": (
            "대금 지급의 거절·유예는 하자 또는 미인도 부분에 상응하는 금액에 한정하며, 나머지 "
            "정상 이행 부분에 대한 대금은 약정된 기한에 지급한다."
        ),
        "negotiation_position": "전액 유예를 하자 상응 금액으로 한정하는 최소수정 — 정상 이행분 대금은 분리 지급 요청.",
        "clause_topic": "payment_settlement",
    },
    {
        "id": "clr_inspection_repeat_failure_immediate_termination",
        "name": "검수 반복 불합격 시 귀책불문 즉시해지",
        "present": re.compile(
            r"검수에?\s*누적하여?\s*(\d+)\s*회\s*이상\s*불합격.{0,70}(해지|해제)",
            re.IGNORECASE | re.DOTALL,
        ),
        # 경미한 불합격도 누적되고, 우리 측 귀책 여부와 무관하며, 시정
        # 기회 없이 즉시 해지되는 3중 리스크가 겹치므로 실제 협상에서 반드시
        # 고쳐야 할 HIGH로 재분류(변호사형 전체계약 판단 지시, 2026-08-31 —
        # 항목 6·7). 종전 MEDIUM은 협상 우선순위를 과소평가한 것이었다.
        "risk": "HIGH",
        "direction": "① 중대한 하자로 인한 불합격에 한정, ② 우리 측 귀책사유 필요, ③ 상당한 시정기간 부여 — 세 요소를 함께 명시",
        "reason": "경미한 불합격도 누적 가능하고, 우리 측 귀책 여부와 무관하며, 시정 기회 없이 즉시 해지될 수 있다.",
        "legal_business_reason": (
            "검수 불합격이 상대방의 사양 변경·불명확한 기준 제시 등 우리 측 귀책이 아닌 사유로도 "
            "발생할 수 있는데, 경미한 지적사항까지 누적되어 최고절차 없이 즉시 계약이 해지되면 "
            "이미 투입한 비용을 회수할 기회조차 없이 거래관계가 끝날 수 있다."
        ),
        "rewrite": (
            "검수 불합격이 목적물의 사용목적 달성을 곤란하게 하는 중대한 하자로 인한 것이고 "
            "우리 측 귀책사유로 인한 경우에 한하여, 상당한 시정기간을 부여한 재검수에서도 "
            "누적 2회 이상 불합격한 때에 해지할 수 있다."
        ),
        "negotiation_position": "해지권 자체 삭제보다 '중대한 하자·우리측 귀책·시정기간 부여' 3요소 추가를 우선 요청 — 즉시해지 리스크를 실질적으로 낮추는 최소수정.",
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
        "reason": "상대방이 추가로 요구하는 사항이 계약 범위(급부)에 포괄적으로 포함되어 있다.",
        "legal_business_reason": "대가 조정 없이 업무 범위가 일방적으로 확대될 수 있어(scope creep), 실제 투입 비용이 대금에 반영되지 않는 구조가 된다.",
        "rewrite": (
            "계약 범위는 본 조에서 정한 사항으로 한정하며, 상대방의 추가 요구사항은 양 당사자의 "
            "서면 합의 및 그에 따른 대금 조정을 거친 경우에만 계약 범위에 포함된다."
        ),
        "negotiation_position": "범위 포괄 문구 삭제보다 '서면합의·대금조정' 절차 신설을 우선 요청 — 추가요구 자체를 막기보다 대가를 받는 구조로 전환.",
        "clause_topic": "other",
    },
    {
        "id": "clr_broad_uncapped_accident_liability",
        "name": "포괄적·무제한 사고 책임",
        "present": re.compile(r"제반\s*사고.{0,140}일체의?\s*책임을?\s*부담", re.IGNORECASE | re.DOTALL),
        "risk": "MEDIUM",
        "direction": "책임 범위를 우리 측 이행 과정에서 발생한 사고로 한정하고, 상대방·제3자의 관리 부주의로 인한 사고는 제외",
        "reason": "이행 과정에서 발생하는 '제반 사고'에 대해 포괄적으로 일체의 책임을 부담한다.",
        "legal_business_reason": "상대방 또는 제3자의 관리·감독 부주의로 발생한 사고까지 책임 범위에 포함될 수 있어, 우리 통제 밖의 사고에도 책임을 지는 구조가 된다.",
        "rewrite": (
            "본 조의 책임은 우리 측 또는 우리 측 피용인의 고의·과실로 발생한 사고에 한정하며, "
            "상대방 또는 제3자의 관리·감독상 귀책사유로 발생한 사고에는 적용되지 아니한다."
        ),
        "negotiation_position": "포괄적 사고책임을 우리 측 귀책 범위로 한정하는 최소수정 — 산재보험 등 법정 보장 범위와 중복되지 않도록 명확화.",
        "clause_topic": "damage",
    },
    {
        # unilateral_scope_change — 상대방이 계약 내용의 변경/수정을
        # 일방적으로 요청할 수 있고 우리는 "최대한 협력"해야 하는데, 그로
        # 인한 대금·기간 변경이 사전 서면합의 없이 진행될 수 있는 구조.
        # 계약유형·회사명과 무관한 일반 패턴(변호사형 전체계약 판단 지시,
        # 2026-08-31).
        "id": "clr_unilateral_scope_change_without_prior_agreement",
        "name": "일방적 계약변경 요청 — 사전 서면합의 없는 착수의무",
        "present": re.compile(
            r"변경\s*(또는\s*수정)?\s*을?\s*[“\"]?(갑|을|병|정)[”\"]?에게\s*요청할\s*수\s*있으며"
            r".{0,20}(최대한\s*)?협력하여야\s*한다",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "변경 요청에 따른 업무 착수는 범위·대금·기간에 대한 사전 서면합의를 조건으로 하고, 합의 전에는 변경 업무 수행 의무가 없음을 명시",
        "reason": "상대방이 계약 내용의 변경·수정을 요청할 수 있고 우리는 이에 '최대한 협력'해야 하는 일방적 구조다.",
        "legal_business_reason": (
            "변경으로 대금·기간에 영향이 있는 경우에도 사전 서면합의 없이 '협력' 의무만 있으면, "
            "실제로는 대가 조정 전에 변경 업무에 착수하도록 사실상 강요받는 결과가 될 수 있다."
        ),
        "rewrite": (
            "상대방의 변경 또는 수정 요청으로 대금 또는 계약기간의 변경이 필요한 경우, 당사자는 "
            "변경 업무 착수 전에 그 범위·대금·기간을 서면으로 합의한다. 합의 전에는 우리 측에 "
            "변경된 업무 수행 의무가 발생하지 아니한다."
        ),
        "negotiation_position": "변경요청 자체보다 '착수 전 서면합의' 요건 신설을 우선 요청 — 협력의무는 유지하되 대가 없는 선이행을 막는 최소수정.",
        "clause_topic": "sow_change",
    },
    # ── 변호사형 전체계약 판단 (2026-09-01 지시) — NDA를 golden test로 확인한
    # 범용 legal-effect 패턴. 조항번호·회사명과 무관하게 "손해배상 범위가
    # 무제한인가", "제3자 귀책까지 연대책임을 지는가", "관리의무 기준이
    # 모호한가", "부수계약 위반이 본계약 해지로 확산되는가" 같은 법률효과를
    # 판별한다 — NDA 전용이 아니라 용역/공급 등 다른 계약에서도 동일하게
    # 나타날 수 있는 패턴이다.
    {
        "id": "clr_uncapped_consequential_damages",
        "name": "간접손해·예상손실·법률비용까지 포함한 무제한 손해배상",
        "present": re.compile(
            r"(?=.*간접적?\s*손해)(?=.*(예상\s*손실|위자료))(?=.*(법률비용|소송비용))",
            re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "손해배상 범위를 귀책사유와 상당인과관계 있는 직접·통상손해로 한정하고, 간접손해·특별손해·예상손실은 원칙적으로 배제, 법률비용은 합리적 범위로 제한",
        "reason": "손해배상 범위에 직접손해뿐 아니라 간접손해·예상손실·위자료·일체의 법률비용·제3자 배상채무까지 포함되어 있고 상한이 없다.",
        "legal_business_reason": (
            "실제 손해 규모와 무관하게 예상손실·위자료·법률비용까지 무제한으로 배상해야 하는 구조가 되어, "
            "위반 1건의 경제적 노출 규모를 사전에 예측·통제할 수 없다."
        ),
        "rewrite": (
            "손해배상의 범위는 귀책사유와 상당인과관계 있는 직접·통상손해로 한정하며, 간접손해·특별손해·"
            "예상손실은 원칙적으로 배상 범위에서 제외한다. 법률비용은 법원이 인정하는 합리적 범위 내에서만 "
            "배상 대상으로 한다."
        ),
        "negotiation_position": "손해배상 범위 자체를 없애기보다 '직접·통상손해로 한정 + 간접/특별손해 배제' 문구 추가를 우선 요청 — 필요 시 배상액 상한(cap)도 함께 협상.",
        "clause_topic": "damage",
    },
    {
        "id": "clr_third_party_joint_liability_regardless_of_selection_fault",
        "name": "제3자·하청업체 고의과실에 대한 연대책임(선정·감독 귀책 불문)",
        "present": re.compile(
            r"(하청업체|수급인|제\s*3\s*자).{0,90}(고의|과실).{0,90}연대하여.{0,20}(배상|책임)",
            re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "제3자에게 동등한 비밀유지의무를 부과하고 합리적으로 선정·관리·감독한 경우, 그 제3자의 독립적 위반에 대해서는 책임을 지지 않도록 한정",
        "reason": "우리가 선정·관리하지 않은 제3자·하청업체의 고의·과실에 대해서도 연대하여 배상 책임을 진다.",
        "legal_business_reason": (
            "제3자에게 동등한 비밀유지의무를 부과하고 합리적으로 선정·관리·감독했음에도, 그 제3자가 "
            "독자적으로 저지른 위반까지 우리가 전액 연대책임을 지면 우리 통제 밖의 행위에 대한 책임을 "
            "지는 구조가 된다."
        ),
        "rewrite": (
            "제3자에게 본 계약과 동등한 비밀유지의무를 부과하고 합리적인 선정·관리·감독 의무를 이행한 "
            "경우, 그 제3자의 독립적인 위반에 대해서는 책임을 부담하지 아니한다."
        ),
        "negotiation_position": "연대책임 삭제보다 '선정·감독 의무를 다한 경우 면책' 요건 추가를 우선 요청 — 통제 가능한 범위로 책임을 한정하는 최소수정.",
        "clause_topic": "damage",
    },
    {
        "id": "clr_best_efforts_standard_of_care_ambiguous",
        "name": "관리의무 기준 — '가능한 최선의 노력' 모호",
        "present": re.compile(r"가능한\s*최선의\s*노력"),
        "risk": "MEDIUM",
        "direction": "관리의무 기준을 '동종의 자기 정보에 적용하는 것과 동일한 수준' + '최소 합리적 주의의무'로 구체화",
        "reason": "관리·보호 의무의 기준이 '가능한 최선의 노력'이라는 추상적 문언으로만 되어 있다.",
        "legal_business_reason": (
            "'최선의 노력'은 객관적 기준(objective standard)이 지나치게 높게 해석될 여지가 있어, 사소한 "
            "관리 미비도 의무 위반으로 주장될 위험이 있다."
        ),
        "rewrite": (
            "자신의 동종 중요정보에 적용하는 것과 동일한 수준의 주의를 기울이되, 최소한 합리적인 주의의무를 "
            "다하는 것으로 관리·보호 의무를 이행한 것으로 본다."
        ),
        "negotiation_position": "관리의무 기준을 '동종 자기정보 대비 동일 수준 + 최소 합리적 주의'로 구체화하는 최소수정 — 객관적 최고기준 해석 여지를 없앤다.",
        "clause_topic": "other",
    },
    {
        # 법률효과 관점의 명칭: cross_default / related_contract_termination —
        # "해지"라는 단어가 아니라 "한 계약의 위반이 다른 계약의 종료·기한
        # 이익상실·제재로 확산되는 구조"인지가 실질이므로, 계약유형·문언과
        # 무관하게 아래 present 정규식(위반→타 계약 종료/기한이익상실/제재)
        # 전부에 공통 적용된다(2026-09-01, 실제 NDA 제6조 제6항 누락 사례
        # 이후 일반화).
        "id": "clr_breach_triggers_related_contract_termination",
        "name": "본계약(부수계약) 위반만으로 관련 계약 해지·기한이익상실·제재",
        "present": re.compile(
            r"(계약상의|본\s*계약).{0,20}(위반|불이행).{0,60}(정식\s*계약|관련된?\s*계약)"
            r".{0,20}(해지|해제|기한(?:의)?\s*이익(?:을)?\s*상실|제재(?:를)?\s*(?:가할|받을|부과))",
            re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "본계약(비밀유지 등 부수계약) 위반이 중대한 경우로 한정하고, 시정기회를 부여한 후에도 시정되지 않을 때에 한하여 관련 계약 해지·기한이익상실·제재 사유가 되도록 제한",
        "reason": "이 계약(비밀유지 등 부수계약) 위반만으로, 위반의 중대성이나 귀책사유·시정기회 요건 없이 관련된 본계약(정식 계약)까지 해지·해제되거나 기한이익상실·제재로 이어질 수 있다.",
        "legal_business_reason": (
            "경미한 위반까지 본계약 위반 사유가 되어 관련된 본 거래(정식 계약) 전체가 해지·기한이익상실 등으로 "
            "이어질 수 있으면, 부수적인 의무 위반이 핵심 거래관계 상실이라는 불균형한 결과로 이어질 위험이 있다."
        ),
        "rewrite": (
            "이 계약을 중대하게 위반하고, 상당한 기간을 정한 시정 요구에도 불구하고 시정되지 아니한 경우에 "
            "한하여 관련된 정식 계약을 해지 또는 해제할 수 있다."
        ),
        "negotiation_position": "관련계약 해지권 삭제보다 '중대한 위반 + 시정기회' 요건 추가를 우선 요청 — 경미한 위반으로 핵심 거래 전체가 흔들리지 않도록 하는 최소수정.",
        "clause_topic": "termination",
        "legal_effect_tags": ["cross_default"],
    },
    {
        # 전략제휴/플랫폼형 공급계약(2026-09-02 지시)에서 반드시 우선순위
        # 높게 잡아야 할 두 legal effect 중 하나: non_circumvention +
        # direct_dealing_restriction + penalty_for_bypass. 계약 종료 후까지
        # 이어지는 영업자유 제한(직접거래 금지)에 배액(倍額) 위약벌이 결합된
        # 경우는 "정산 문구" 같은 절차 조항보다 훨씬 중요한, 체결 전 반드시
        # 협상해야 할 조항이다 — 조항번호가 아니라 이 legal effect 조합
        # 자체로 탐지한다.
        "id": "clr_direct_dealing_restriction_with_penalty",
        "name": "종료 후까지 이어지는 직접거래 제한 + 배액 위약벌",
        "present": re.compile(
            r"(?=.*(배제|제외).{0,20}(직접\s*거래|직접거래))"
            r"(?=.*(종료\s*후|계약\s*후|해지\s*후).{0,15}(\d+\s*(개월|년)))"
            r"(?=.*위약벌.{0,20}(\d+\s*배|배액))",
            re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "직접거래 제한 기간을 계약 유효기간 중으로 한정하거나 종료 후 제한기간을 단축하고, 위약벌을 실손해 범위 내로 조정",
        "reason": "계약 종료 후 일정 기간까지 상대방을 배제한 직접거래를 금지하고, 위반 시 배액의 위약벌을 부과하는 구조로, 계약이 끝난 뒤에도 우리 회사의 거래처 선택·영업 자유가 장기간 제한되고 위반 시 금전 부담이 크다.",
        "legal_business_reason": (
            "계약기간 중은 물론 종료 후까지 이어지는 직접거래 금지는 우리 회사의 영업 자유를 실질적으로 제한하며, "
            "위약벌이 손해액의 배액으로 정해져 있으면 실제 손해와 무관하게 과도한 금전 부담으로 이어질 수 있다. "
            "공정거래법상 거래상 지위 남용·부당한 거래거절 소지도 함께 검토가 필요하다."
        ),
        "rewrite": (
            "직접거래 제한은 계약 유효기간 중으로 한정하고, 종료 후 제한을 두더라도 합리적인 최소 기간으로 단축한다. "
            "위반 시 배상은 실제 발생한 손해(수수료 상당액)의 범위 내로 하고, 배액 위약벌은 삭제하거나 상한을 둔다."
        ),
        "negotiation_position": "종료 후 제한기간 단축 및 위약벌을 실손해 범위로 축소하는 것을 우선 요청 — 직접거래 금지 자체의 삭제보다 협상 성사 가능성이 높은 최소수정.",
        "clause_topic": "other",
        "legal_effect_tags": ["non_circumvention", "direct_dealing_restriction", "penalty_for_bypass"],
    },
    {
        # 두 번째 핵심 legal effect: minimum_purchase_commitment. 매출액
        # 대비 일정 비율의 연간 최소 구매를 약정하고 실적과 무관하게
        # 사후 변경을 금지하는 구조는 "정산 문구"보다 훨씬 중요한, 장기적
        # 경제적 구속이다.
        "id": "clr_minimum_purchase_commitment_fixed_by_revenue_ratio",
        "name": "매출액 대비 비율로 고정된 연간 최소 구매(발주) 의무",
        "present": re.compile(
            r"(연간|매\s*협약연도|매년).{0,20}(최소\s*(발주|구매|구입)).{0,80}"
            r"매출액.{0,20}\d+\s*[~-]?\s*\d*\s*%.{0,80}(사후에?\s*변경되지|변경되지\s*아니)",
            re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "연간 최소 발주액을 실제 매출·경영 상황에 연동해 사후 조정 가능하도록 하고, 최소 발주 미달성 시 해지·손해배상 등 제재보다 협의 우선 조항으로 완화",
        "reason": "연간 최소 발주액이 우리 회사의 직전 사업연도 매출액 대비 고정 비율로 정해지고, 실제 매출 변동과 무관하게 사후 변경이 금지되어 있어, 영업 상황이 악화되어도 정해진 금액을 계속 발주해야 하는 장기적 경제적 구속이 있다.",
        "legal_business_reason": (
            "매출 연동형 최소구매 의무는 매출 성장기에는 부담이 크지 않지만, 매출이 정체·감소하는 국면에서는 "
            "실제 필요보다 과도한 발주를 강제하는 결과를 낳는다. 사후 변경을 원천 금지하면 시장 상황 변화에 "
            "대응할 수단이 없어, 매수인에게 불리한 장기 고정 비용 구조가 된다."
        ),
        "rewrite": (
            "연간 최소 발주액은 매 협약연도 개시 전 직전 사업연도 매출액을 기준으로 재산정하며, 매출액의 유의미한 "
            "변동이 있는 경우 양 당사자의 협의를 통해 조정할 수 있다."
        ),
        "negotiation_position": "최소 발주액의 매년 재산정·조정 가능성 확보를 우선 요청 — 최소구매 의무 자체의 삭제보다 실현 가능성이 높은 최소수정.",
        "clause_topic": "other",
        "legal_effect_tags": ["minimum_purchase_commitment"],
    },
    {
        # 전략제휴/플랫폼형 공급계약(2026-09-02 지시 후속 피드백)에서 실제
        # 계약 finding으로 드러나야 하는 세 번째 legal effect:
        # delegated_design_or_construction_service. 설계·시공 업무 전부
        # 또는 일부를 상대방에게 위탁하는 조항은 지금까지 관련 법률
        # 적용성 섹션(건설산업기본법 등)에만 등장하고 조항 자체의 finding은
        # 생성되지 않았는데("제5조의 설계·시공 위탁 구조는 적용법률
        # 섹션에는 나오지만 실제 계약 수정 finding으로는 안 나와"), 위탁자
        # 입장에서는 수탁자의 면허·등록 요건 확인과 설계·시공 하자 경합 시
        # 책임분담 기준이 본 협약 차원에 없다는 것 자체가 실질적 공백이다.
        "id": "clr_delegated_design_construction_service_gap",
        "name": "설계·시공 업무 위탁 시 면허 확인 및 하자책임 분담 기준 없음",
        "present": re.compile(
            r"(인테리어\s*설계|건축\s*설계)[^.\n]{0,15}시공[^.\n]{0,80}(위탁|외주)"
            r"|시공[^.\n]{0,15}(인테리어\s*설계|건축\s*설계)[^.\n]{0,80}(위탁|외주)",
            re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "수탁자의 관련 면허·등록 요건 확인 절차와 설계 하자·시공 하자가 경합할 때의 책임 분담 기준을 명시",
        "reason": "설계와 시공 업무의 전부 또는 일부를 상대방에게 위탁하면서도, 상대방이 건설산업기본법 등 관련 법령상 요구되는 면허·등록 요건을 갖추었는지 확인하는 절차와, 설계 하자와 시공 하자가 함께 발생했을 때의 책임 분담 기준이 본 조에 명시되어 있지 않다.",
        "legal_business_reason": (
            "설계와 시공을 함께 위탁하는 구조는 건설산업기본법상 도급·하도급 규율 대상이 될 수 있고, 무면허 시공이나 "
            "하자 발생 시 책임소재 불명확은 실제 분쟁에서 하자보수·손해배상 청구를 지연·무력화시킬 수 있다. 개별 "
            "프로젝트 계약서가 이를 별도로 정하지 않는 한, 본 협약 차원에서 이를 통제할 수단이 없다."
        ),
        "rewrite": (
            "을은 개별 프로젝트 수행에 필요한 관련 법령상의 면허·등록 요건(건설업 등록 등)을 갖춘 자로 하여금 "
            "설계·시공 업무를 수행하게 하며, 이를 증빙할 수 있는 자료를 갑의 요청 시 제공한다. 설계상 하자와 "
            "시공상 하자가 경합하는 경우, 원인이 규명된 범위에서 각 하자에 책임 있는 당사자가 해당 부분에 대한 "
            "책임을 부담한다."
        ),
        "negotiation_position": "면허 확인 및 하자책임 분담 기준 신설 요청 — 개별 프로젝트 계약서로 미루기보다 본 협약 차원의 최소 기준을 두는 것이 협상 성사 가능성이 높다.",
        "clause_topic": "other",
        "legal_effect_tags": ["delegated_design_or_construction_service"],
    },
    {
        # 범용 사내변호사형 검토 고도화(2026-09-02 지시, KOTRA 3자 컨설팅계약
        # 실사례) — "Company shall guarantee that Consultant shall return...
        # Otherwise, Company shall be directly responsible" 구조는 우리 회사가
        # 제3자(계약상대방)의 채무를 보증하는 것으로, 원칙적으로 HIGH 후보다.
        # 핵심 질문: 누구의 채무인가(수탁자/상대방) / 우리가 그 채무를
        # 대신 떠안는가 / 우리가 통제할 수 없는 상대방의 불이행에 우리가
        # 책임지는가. 특정 계약유형이 아니라 "제3자 채무 보증"이라는 문장
        # 구조(A shall guarantee that B shall repay ... otherwise A shall be
        # directly responsible)로 탐지한다 — 영문·국문 계약 모두 대응.
        "id": "clr_third_party_debt_guarantee",
        "name": "제3자(상대방)의 채무를 우리 회사가 보증",
        "present": re.compile(
            r"guarantee(?:s)?\s+that\b.{0,120}?(?:return|repay|refund).{0,150}?"
            r"(?:otherwise|failing\s+which).{0,80}?(?:directly\s+responsible|liable)"
            r"|(?:을|상대방)(?:이|가).{0,20}(?:반환|환불|상환)하지\s*(?:아니|않)하는?\s*경우.{0,60}"
            r"(?:갑|우리\s*회사|당사)(?:이|가|는).{0,20}(?:연대하여?|직접)?\s*(?:보증|책임)",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "우리 회사의 보증 범위를 우리가 실제로 통제 가능한 사유(우리 자신의 귀책)로 한정하고, 상대방의 순수한 채무불이행에 대한 무조건적 보증은 삭제하거나 상한을 설정",
        "reason": "계약상대방(용역수행자)이 대금을 받고도 착수하지 않거나 이행을 중단하는 경우, 그 반환채무를 우리 회사가 직접 책임지고 보증하는 구조다. 상대방의 채무불이행 여부는 우리 회사가 통제할 수 없는 사유임에도, 그 결과에 대한 금전적 책임을 우리가 떠안는다.",
        "legal_business_reason": (
            "제3자의 채무를 우리 회사가 보증하는 조항은 상대방의 신용·이행능력 리스크를 우리가 인수하는 것과 같다. "
            "상대방이 실제로 반환할 자력이 없는 경우 우리 회사가 지급기관(또는 채권자)에게 그 금액을 대신 변제해야 "
            "하므로, 계약금액 전액이 우리 회사의 잠재적 금전 노출(exposure)이 된다."
        ),
        "rewrite": (
            "Company의 보증 책임은 Company 자신의 귀책사유(예: Company가 Consultant의 선정·관리에 중대한 과실이 있는 "
            "경우)로 한정하고, Consultant 자신의 단순 채무불이행에 대하여는 Consultant가 직접 반환 책임을 지도록 하며, "
            "Company의 보증 금액에는 상한(예: 이미 지급받은 선급금 범위 내)을 둔다."
        ),
        "negotiation_position": "보증 자체의 삭제보다, 우리 회사의 보증 범위를 우리 귀책사유로 한정하거나 최소한 금액 상한을 두는 것을 우선 요청.",
        "clause_topic": "other",
        "legal_effect_tags": ["third_party_debt_guarantee"],
    },
    {
        # 위와 짝을 이루는 두 번째 신규 패턴 — 계약상대방(특히 정부기관·
        # 지원기관 등 협상력이 강한 당사자)이 스스로의 책임은 결제 의무
        # 하나로 한정하면서, 용역 관련 모든 청구·손해·비용에 대한 면책을
        # 우리 쪶(또는 제3의 수행기관)에게 부담시키는 구조.
        "id": "clr_counterparty_broad_self_liability_shield",
        "name": "상대방의 광범위한 자기책임 면제 + 우리 쪽 포괄 면책 부담",
        "present": re.compile(
            r"shall\s+bear\s+no\s+legal\s+liability.{0,80}?except.{0,120}?shall\s+be\s+indemnified\s+against\s+all\s+claims"
            r"|(?:갑|을|상대방)(?:은|는).{0,20}(?:본\s*계약과?\s*관련하여)?\s*(?:일체의?|아무런?)\s*법적\s*책임을?\s*지지\s*(?:아니|않)"
            r"[^.\n]{0,60}(?:모든|일체의)\s*(?:청구|손해|비용)(?:에\s*대하여)?\s*(?:면책|배상)",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "상대방의 자기책임 면제 범위를 상대방 자신의 고의·중과실이 없는 경우로 한정하고, 우리 쪽이 부담하는 면책 범위도 우리 자신의 귀책사유로 한정",
        "reason": "계약상대방은 대금 지급 의무 외에는 어떠한 법적 책임도 지지 않으면서, 용역과 관련하여 발생하는 모든 청구·손해·비용에 대한 면책은 우리(또는 제3의 수행기관)가 부담하는 구조다.",
        "legal_business_reason": (
            "협상력이 강한 상대방(정부기관·지원기관 등)이 자신의 책임을 대금 지급 하나로 한정하면서 나머지 모든 "
            "위험을 계약구조상 약자에게 전가하는 전형적인 불균형 구조다. 우리 회사가 실제로 통제할 수 없는 제3자의 "
            "행위로 인한 청구까지 포괄적으로 떠안게 될 수 있다."
        ),
        "rewrite": (
            "상대방의 책임 면제는 상대방 자신의 고의 또는 중대한 과실이 없는 통상적인 업무 수행에 한정하고, 우리 "
            "쪽이 부담하는 면책 의무도 우리 자신 또는 우리가 지휘·감독하는 자의 귀책사유로 발생한 청구로 한정한다."
        ),
        "negotiation_position": "포괄적 면책 문구 자체보다, 면책 범위를 '귀책사유가 있는 당사자'로 한정하는 것을 우선 요청 — 정부기관 상대 계약에서는 문구 전면 삭제보다 실현 가능성이 높다.",
        "clause_topic": "other",
        "legal_effect_tags": ["counterparty_broad_self_liability_shield"],
    },
    {
        # 세 번째 — Article 6류 "무제한 indemnity + attorney's fees" 상호
        # 면책조항. 위 self_liability_shield와 달리 대칭적(mutual)이지만
        # cap이 전혀 없고 attorney's fees까지 포함되어 있어 MEDIUM.
        "id": "clr_uncapped_mutual_indemnity_with_attorney_fees",
        "name": "무제한 상호 indemnity + attorney's fees, cap 없음",
        "present": re.compile(
            r"indemnify\s+the\s+other\s+part(?:y|ies)\s+against\s+all\s+claims,?\s*damages,?\s*losses,?\s*(?:and\s+)?expenses"
            r".{0,80}?including\s+reasonable\s+attorney"
            r"|모든\s*청구\s*[,·]\s*손해\s*[,·]\s*비용.{0,40}(?:변호사\s*보수|소송비용)[^.\n]{0,60}(?:배상|면책)",
            re.IGNORECASE | re.DOTALL,
        ),
        "risk": "MEDIUM",
        "direction": "손해배상·면책 책임에 총액 상한을 설정하고, 간접·결과적 손해(consequential/special damages)는 배상 범위에서 제외",
        "reason": "모든 청구·손해·비용을 변호사 보수까지 포함하여 상호 면책하는 조항인데, 배상 총액의 상한이나 간접손해 제외 규정이 없어 실제 분쟁 시 배상 범위가 예측 불가능하게 확대될 수 있다.",
        "legal_business_reason": (
            "당사자 간 대칭적(상호) 조항이라 하더라도, cap이 없는 all-claims/all-damages 조항은 실제 분쟁에서 변호사 "
            "보수를 포함한 소송비용까지 그대로 청구 대상이 되어 예상보다 큰 금전적 노출로 이어질 수 있다."
        ),
        "rewrite": (
            "각 당사자의 배상·면책 책임 총액은 본 계약에 따라 지급(또는 수령)한 대금 총액을 한도로 하며, 간접손해· "
            "결과적 손해·특별손해는 배상 범위에서 제외한다."
        ),
        "negotiation_position": "cap 신설을 우선 요청 — 상호 조항이므로 상대방도 같은 보호를 받는 구조라 협상 성사 가능성이 높다.",
        "clause_topic": "other",
        "legal_effect_tags": ["uncapped_liability", "indemnity"],
    },
    {
        "id": "clr_ethics_morality_termination_waiver_cluster",
        "name": "광범위 윤리·품위의무 + 즉시해지(관련계약 포함) + 손해배상청구 포기",
        "present": re.compile(
            r"(?=.*(불륜|음주운전|막말|혐오\s*발언))(?=.*(별도의?\s*최고절차\s*없이|최고\s*없이))"
            r"(?=.*손해배상\s*청구를?\s*하지\s*않는)",
            re.DOTALL,
        ),
        "risk": "HIGH",
        "direction": "품위의무는 계약 이행과 직접 관련된 중대한 위법·부정행위로 범위를 축소하고, 일반 위반은 시정기간을 부여하며, 손해배상청구 포기 조항은 삭제",
        "reason": "계약 이행과 직접 관계없는 사생활·품위 의무 위반만으로 최고절차 없이 관련 계약까지 즉시 해지되고, 그 경우 손해배상 청구권까지 포기해야 한다.",
        "legal_business_reason": (
            "품위의무 위반 범위가 지나치게 넓고(불륜·음주운전 등 사생활 영역 포함), 최고절차 없는 즉시해지가 "
            "관련 본계약까지 확산되며, 여기에 손해배상 청구권 포기까지 결합되면 절차적 방어수단 없이 "
            "핵심 거래관계와 구제수단을 동시에 잃는 구조가 된다."
        ),
        "rewrite": (
            "품위의무는 계약 이행과 직접 관련된 중대한 위법행위 또는 부정행위로 한정한다. 그 외의 일반적인 "
            "위반은 상당한 기간을 정한 시정 요구 절차를 거친 후에만 해지 사유가 되며, 본 조에 따른 해지 시 "
            "손해배상 청구권을 포기하는 것으로 보지 아니한다."
        ),
        "negotiation_position": "세 요소를 하나로 묶어 협상 — ① 품위의무 범위를 계약 관련 중대 위반으로 축소, ② 즉시해지에 최고절차 추가, ③ 손해배상청구 포기 조항 삭제.",
        "clause_topic": "termination",
    },
]

_RX_LATE_PENALTY_RATE = re.compile(
    r"지체일수\s*당\s*총?\s*[“\"]?대금[”\"]?의\s*(\d+)\s*/\s*(\d+)"
    r"|지체.{0,10}(?:1\s*)?일.{0,10}당?.{0,10}(\d+(?:\.\d+)?)\s*%"
    # 영문 계약(2026-09-02 KOTRA 3자 컨설팅계약 지시) — "10 % of total amount
    # of compensation ... for each day of delay" 형태. 한글 지체상금 요율만
    # 잡던 기존 정규식에 "N% ... (for) each/per day (of delay)" 패턴을 추가해
    # 같은 계산 로직(10일/30일 누적, 상한 유무)이 영문 계약에도 그대로
    # 적용되게 한다 — KOTRA 전용 규칙이 아니라 언어 확장.
    r"|(\d+(?:\.\d+)?)\s*%[^.\n]{0,90}?(?:for\s+)?(?:each|per)\s+(?:calendar\s+)?day(?:\s+of\s+delay)?",
    re.IGNORECASE | re.DOTALL,
)
_RX_PENALTY_CAP = re.compile(
    r"상한|한도|최대|초과할?\s*수\s*없다"
    r"|\bcap\b|\bmaximum\b|shall\s+not\s+exceed|not\s+to\s+exceed|up\s+to\s+a\s+maximum",
    re.IGNORECASE,
)


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
        _effect_tags = item.get("legal_effect_tags")
        _effect_tags = list(_effect_tags) if isinstance(_effect_tags, list) else []
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
            "legal_business_reason": item.get("legal_business_reason") or item["reason"],
            "suggested_direction": [item["direction"]],
            "negotiation_position": item.get(
                "negotiation_position",
                "상대방 반발 가능성이 있으나 법적 책임 범위 명확화 차원에서 협상 필요",
            ),
            "confidence": 0.85,
            "is_common_legal_risk": True,
            "has_rewrite_change": True,
            "display_kind": "redline" if risk == "HIGH" else "guidance",
            "dedup_suppressed": False,
            "keep_as_is": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "ai_deep_reviewed": False,
            **({"original_effect_tags": _effect_tags, "rewrite_effect_tags": _effect_tags} if _effect_tags else {}),
        })

    _apply_cross_default_severity_check(clause_results)
    _apply_termination_vs_term_check(clause_results, text, clauses)
    _apply_late_penalty_uncapped_check(clause_results, text, clauses)
    _apply_confidentiality_survival_undefined_check(clause_results, clauses)


_RX_SURVIVAL_NO_TERM = re.compile(
    r"비밀유지의무.{0,100}(유효한\s*것으로\s*한다|존속한다|효력을?\s*(가진다|유지한다))",
    re.DOTALL,
)
_RX_SURVIVAL_HAS_TERM = re.compile(r"\d+\s*년|\d+\s*개월")


def _apply_confidentiality_survival_undefined_check(
    clause_results: list[dict[str, Any]],
    clauses: list[ClauseChunk] | None = None,
) -> None:
    """변호사형 전체계약 판단(2026-09-01 지시) > survival — 비밀유지의무가
    계약 종료 후에도 "유효한 것으로 한다"처럼 존속한다고만 규정하고 구체적
    종료 시점(예: N년)을 명시하지 않으면, 사실상 무기한 존속으로 해석될
    여지가 있다. 조항번호·계약유형과 무관한 일반 survival 패턴."""
    existing = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if "clr_confidentiality_survival_undefined" in existing:
        return
    for c in (clauses or []):
        leaf_text = str(getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else "") or "")
        m = _RX_SURVIVAL_NO_TERM.search(leaf_text)
        if not m:
            continue
        # 세그멘테이션이 조 단위까지만 되는 문서(항 단위로 안 쪼개짐)에서는
        # 같은 조 안의 다른 항(예: 계약기간 자체를 "1년"으로 정하는 별도
        # 문장)에 있는 숫자가 "존속기간이 있다"는 오탐을 만들 수 있다 —
        # 반드시 존속 문구 주변(±80자)에서만 기간 표기를 찾는다.
        _window_start = max(0, m.start() - 80)
        _window_end = min(len(leaf_text), m.end() + 80)
        if _RX_SURVIVAL_HAS_TERM.search(leaf_text[_window_start:_window_end]):
            continue
        art = str(getattr(c, "article_number", None) or (c.get("article_number") if isinstance(c, dict) else "") or "").strip() or None
        para = str(getattr(c, "paragraph_number", None) or (c.get("paragraph_number") if isinstance(c, dict) else "") or "").strip() or None
        display_path = str(getattr(c, "display_path", None) or (c.get("display_path") if isinstance(c, dict) else "") or "").strip() or None
        title = f"{display_path} [비밀유지의무 존속기간 불명확]" if display_path else "[공통 법률리스크] 비밀유지의무 존속기간 불명확"
        clause_results.append({
            "clause_id": "clr_confidentiality_survival_undefined",
            "article_number": art,
            "paragraph_number": para,
            "display_path": display_path,
            "clause_title": title,
            "clause_number_uncertain": not bool(display_path),
            "clause_topic": "other",
            "original_text": leaf_text.strip()[:400],
            "risk_tier": "MEDIUM",
            "severity": "MEDIUM",
            "high_risk": False,
            "must_fix": False,
            "approval_required": False,
            "review_tier": "SUGGEST",
            "suggested_rewrite": (
                "본계약 종료 후에도 비밀유지의무는 존속하되, 일반 비밀정보는 계약 종료 후 3~5년간, "
                "법률상 영업비밀에 해당하는 정보는 그 영업비밀성이 유지되는 기간 동안 존속한다."
            ),
            "rewrite_reason": "비밀유지의무가 계약 종료 후에도 '유효한 것으로 한다'고만 되어 있고 구체적인 종료 시점이 없다.",
            "legal_business_reason": (
                "존속기간이 특정되지 않으면 사실상 무기한 비밀유지의무로 해석되어, 시간이 지날수록 "
                "정보의 실질적 가치가 낮아져도 의무 위반 주장에서 자유로울 수 없다."
            ),
            "suggested_direction": ["일반 비밀정보와 영업비밀을 구분해 각각 구체적인 존속기간을 명시"],
            "negotiation_position": "무기한 존속을 구체적 기간(일반정보 3~5년, 영업비밀은 영업비밀성 유지기간)으로 한정하는 최소수정.",
            "confidence": 0.8,
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


def _apply_late_penalty_uncapped_check(
    clause_results: list[dict[str, Any]],
    text: str,
    clauses: list[ClauseChunk] | None = None,
) -> None:
    """변호사형 전체계약 판단 (2026-08-31 지시) > 금전 리스크 최우선 분석.

    지체상금을 키워드만으로 탐지하지 않고, 일할 요율을 실제 계산하여 10일·
    30일 지연 시 계약금액 대비 몇 %에 달하는지 원문 인용에 함께 보여준다.
    상한(캡) 문구가 같은 조항 안에 없으면 무제한 누적 가능한 것으로 보아
    HIGH로 판단한다. 같은 조항에 "지체상금 외 실손해도 청구 가능" 문구가
    함께 있으면(clr_penalty_cumulative_with_actual_damage와 동일 조항)
    "과도한 지체상금률 + 상한 부재 + 실손해 중복청구"를 개별 finding
    2~3건으로 쪼개지 않고 하나의 HIGH risk cluster로 합쳐서 보여준다 —
    수정안도 요율 인하·총액 상한·중복청구 제한 3요소를 함께 제시한다.
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
        elif m.group(4):
            rate_pct = float(m.group(4))
        else:
            continue
        has_cap = bool(_RX_PENALTY_CAP.search(leaf_text))
        has_cumulative = bool(_RX_PENALTY_CUMULATIVE_DAMAGE.search(leaf_text))
        art = str(getattr(c, "article_number", None) or (c.get("article_number") if isinstance(c, dict) else "") or "").strip() or None
        para = str(getattr(c, "paragraph_number", None) or (c.get("paragraph_number") if isinstance(c, dict) else "") or "").strip() or None
        display_path = str(getattr(c, "display_path", None) or (c.get("display_path") if isinstance(c, dict) else "") or "").strip() or None
        rate_str = f"{rate_pct:g}"
        ten_day = f"{rate_pct * 10:g}"
        thirty_day = f"{rate_pct * 30:g}"

        if has_cumulative:
            # 같은 조항의 standalone 중복청구 finding은 이 클러스터로 흡수
            # 되므로 제거 — 동일 이슈를 두 건으로 쪼개서 보여주지 않는다.
            clause_results[:] = [
                cr for cr in clause_results
                if not (
                    isinstance(cr, dict)
                    and cr.get("clause_id") == "clr_penalty_cumulative_with_actual_damage"
                    and (cr.get("display_path") or None) == display_path
                )
            ]
            title = f"{display_path} [지체상금 무상한 + 실손해 중복청구]" if display_path else "[공통 법률리스크] 지체상금 무상한 + 실손해 중복청구"
            problem = f"지체일수 당 {rate_str}%의 지체상금에 실손해까지 별도로 청구할 수 있어 책임이 중복된다."
            legal_reason = (
                f"10일 지연 시 계약금액의 약 {ten_day}%, 30일 지연 시 약 {thirty_day}%의 지체상금이 "
                "발생하는데 상한이 없고, 여기에 실손해까지 중복 청구 가능해 공급자의 경제적 부담을 "
                "사전에 예측·통제할 수 없다."
            )
            rewrite = (
                f"① 지체상금은 지체일수 당 대금의 {rate_str}%보다 낮은 요율로 인하한다.\n"
                "② 지체상금 누계액은 대금의 10%를 초과할 수 없다.\n"
                "③ 지체상금은 지체로 인한 손해배상액의 예정으로 하며, 상대방은 지체상금을 "
                "초과하는 실손해가 지체상금 산정과 무관한 별도의 손해임을 구체적으로 입증한 "
                "경우에 한하여 그 초과분만을 추가로 청구할 수 있다."
            )
            direction = "① 일 지체상금률 인하, ② 지체상금 총액 상한 설정, ③ 실손해 중복청구 제한 — 세 요소를 함께 협상"
            negotiation = "요율 인하와 총액 cap은 반드시 요청. 실손해 중복청구는 최소한 초과손해 입증 방식으로 제한."
        else:
            title = f"{display_path} [지체상금율 미계산·상한 부재]" if display_path else "[공통 법률리스크] 지체상금율 미계산·상한 부재"
            problem = f"지체일수 당 {rate_str}%의 지체상금에 누계 상한이 없다."
            legal_reason = (
                f"10일 지연 시 계약금액의 약 {ten_day}%, 30일 지연 시 약 {thirty_day}%에 달하는데, "
                "상한(캡) 규정이 없어 지연이 길어질수록 배상액이 무제한으로 누적될 수 있다."
            )
            rewrite = (
                f"지체상금은 지체일수 당 대금의 {rate_str}%로 하되, 지체상금 누계액은 대금의 "
                "10%를 초과할 수 없다."
            )
            direction = "지체상금 누계 상한(예: 대금의 10%) 설정"
            negotiation = "지체상금율 자체보다 '상한 부재'가 협상 포인트 — 상한 신설을 우선 요구"

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
            "suggested_rewrite": rewrite,
            "rewrite_reason": problem,
            "legal_business_reason": legal_reason,
            "suggested_direction": [direction],
            "negotiation_position": negotiation,
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


_RX_CROSS_DEFAULT_MATERIALITY_LIMIT = re.compile(r"중대(?:하게|한)")
_RX_CROSS_DEFAULT_FAULT_REQUIREMENT = re.compile(r"고의\s*(?:또는|/|,)?\s*과실|귀책\s*사유")
_RX_CROSS_DEFAULT_CURE_PERIOD = re.compile(
    r"(?:상당한|일정한?)\s*기간을?\s*정(?:하여|한)|시정\s*(?:요구|기회|되지)|최고(?:하였음에도|절차)"
)


def _apply_cross_default_severity_check(clause_results: list[dict[str, Any]]) -> None:
    """변호사형 전체계약 판단 지시 후속(2026-09-01, NDA 제6조 제6항 실사례) —
    clr_breach_triggers_related_contract_termination(cross_default /
    related_contract_termination 법률효과)이 매칭된 문구에 실제로 보호장치
    (① 위반의 중대성 제한, ② 귀책사유 요건, ③ 시정기간/최고 절차)가 있는지
    확인해 심각도를 동적으로 조정한다 — 정적 MEDIUM 고정이 아니라, 세 가지
    보호장치가 전부 없으면(경미한 위반도 곧바로 핵심 상거래계약 종료로
    이어질 수 있는 구조) HIGH로 격상하고, 전부 있으면(이미 안전하게 제한된
    조항) 협상 우선순위를 낮춘다."""
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("clause_id") != "clr_breach_triggers_related_contract_termination":
            continue
        excerpt = str(cr.get("original_text") or "")
        has_materiality = bool(_RX_CROSS_DEFAULT_MATERIALITY_LIMIT.search(excerpt))
        has_fault = bool(_RX_CROSS_DEFAULT_FAULT_REQUIREMENT.search(excerpt))
        has_cure = bool(_RX_CROSS_DEFAULT_CURE_PERIOD.search(excerpt))
        safeguards_present = sum((has_materiality, has_fault, has_cure))
        if safeguards_present == 0:
            # 5개 확인요소가 전부 부재: 중대성 제한 없음, 귀책사유 요건 없음,
            # 시정기간/최고 절차 없음 → 해당 계약 외 다른 본계약까지 종료
            # 되며, 경미한 위반도 핵심 상거래계약 종료로 이어질 수 있는 구조.
            cr["risk_tier"] = "HIGH"
            cr["severity"] = "HIGH"
            cr["high_risk"] = True
            cr["must_fix"] = True
            cr["approval_required"] = True
            cr["review_tier"] = "MUST"
            cr["display_kind"] = "redline"
            cr["legal_business_reason"] = (
                "위반의 중대성 제한, 귀책사유 요건, 시정기간·최고 절차 중 어느 것도 없어 "
                "경미한 위반만으로도 관련된 정식 계약(핵심 상거래관계)이 곧바로 해지·종료될 수 있다."
            )
        elif safeguards_present >= 3:
            # 세 요건이 모두 이미 문구에 있음 — 협상 우선순위를 낮춘다(이미
            # 안전하게 제한된 조항이므로 must_fix 대상은 아님).
            cr["risk_tier"] = "LOW"
            cr["severity"] = "LOW"
            cr["high_risk"] = False
            cr["must_fix"] = False
            cr["approval_required"] = False
            cr["review_tier"] = "NOTE"
            cr["display_kind"] = "guidance"


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
