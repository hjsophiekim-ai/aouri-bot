"""DLR-001 through DLR-008: Professional legal rules for dealer_rental_service_contract.

These 8 rules are the ONLY rules that apply to dealer_rental_service_contract.
isr_*, sppc_*, pi_*, svc_*, and other generic rules are explicitly excluded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DLRRule:
    """Professional-grade legal rule for dealer rental service contracts."""
    rule_id: str
    rule_title: str
    severity: str  # "HIGH" or "MEDIUM"
    approval_required: bool
    trigger_keywords: list[str]
    trigger_patterns: list[re.Pattern]
    clause_topics_allowed: list[str]
    issue_title: str
    legal_risk: str
    business_risk: str
    why_this_matters: str
    required_action: str
    proposed_clause: str
    negotiation_position: str
    confidence: float = 0.95

    def matches_text(self, text: str) -> bool:
        """Return True if this rule's triggers match the given text."""
        t = text or ""
        for kw in self.trigger_keywords:
            if kw in t:
                return True
        for pat in self.trigger_patterns:
            if pat.search(t):
                return True
        return False

    def to_clause_result(self, excerpt: str = "") -> dict:
        """Convert to a clause_result dict compatible with the existing pipeline."""
        return {
            "clause_id": self.rule_id,
            "clause_title": self.rule_title,
            "risk_tier": self.severity,
            "severity": self.severity,
            "approval_required": self.approval_required,
            "high_risk": self.severity == "HIGH",
            "must_fix": self.severity == "HIGH",
            "review_tier": "MUST" if self.severity == "HIGH" else "SUGGEST",
            "issue_title": self.issue_title,
            "original_text": excerpt or f"[{self.rule_title}] 관련 조항",
            "problem": self.legal_risk,
            "legal_business_risk": self.legal_risk,
            "business_risk": self.business_risk,
            "why_this_matters": self.why_this_matters,
            "required_action": self.required_action,
            "legal_business_reason": self.legal_risk,
            "suggested_rewrite": self.proposed_clause,
            "rewrite_reason": self.legal_risk,
            "negotiation_position": self.negotiation_position,
            "evidence_from_contract": excerpt,
            "confidence": self.confidence,
            "is_mandatory": True,
            "has_rewrite_change": True,
            "display_kind": "redline" if self.severity == "HIGH" else "guidance",
            "dedup_suppressed": False,
            "keep_as_is": False,
            "user_focus_hit": True,
            "factual_hit": True,
            "clause_topic": self.clause_topics_allowed[0] if self.clause_topics_allowed else "",
        }


# ─── DLR-001 ─────────────────────────────────────────────────────────────────

DLR_001 = DLRRule(
    rule_id="DLR-001",
    rule_title="고객계약 구조/대리권 오인",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=[
        "최종 소비자",
        "주 렌탈계약",
        "렌탈 계약 체결",
        "대리권",
        "대리점은 고객과",
        "대리점이 고객과",
        "대리점은 최종소비자",
        "대리점은 계약당사자",
    ],
    trigger_patterns=[
        re.compile(r"대리점은\s*고객과\s*직접\s*계약"),
        re.compile(r"대리점이\s*고객과\s*계약을\s*체결"),
        re.compile(r"공급업자와\s*(최종\s*소비자|고객)\s*간의\s*렌탈"),
    ],
    clause_topics_allowed=["거래구조", "대리점역할", "계약당사자", "위탁판매", "대리권"],
    issue_title="고객계약 구조 및 대리권 범위 불명확",
    legal_risk=(
        "대리점이 고객과의 계약 당사자로 표현될 경우 소비자보호법·부가가치세법 §32상 "
        "세금계산서 발행 주체 분쟁, 제품 하자에 대한 1차 책임이 대리점에 귀속됩니다. "
        "대리권 범위가 불명확하면 대리점의 초과 권한 행사에 따른 퍼시스의 대외 책임 위험이 발생합니다."
    ),
    business_risk=(
        "고객이 납기 지연·제품 하자를 이유로 대리점을 직접 상대로 소송 제기 가능. "
        "세금계산서 명의 불일치로 고객의 매입세액공제 불인정, 세금계산서 무효 처리 위험. "
        "대리점이 퍼시스 명의로 계약 체결 시 퍼시스에게 의도하지 않은 법적 구속력 발생."
    ),
    why_this_matters=(
        "퍼시스가 고객과 직접 렌탈계약을 체결하는 구조에서 대리점은 판매지원 용역자이지 "
        "계약당사자가 아닙니다. 이 원칙이 계약서에 명확하지 않으면 모든 분쟁에서 대리점·퍼시스 간 "
        "책임 귀속이 혼선을 빚고 고객 클레임이 대리점으로 향하게 됩니다."
    ),
    required_action=(
        "거래구조를 '공급업자가 고객과 직접 계약, 대리점은 위탁범위 내 지원'으로 명확화. "
        "대리권 범위를 사전 서면 승인 필요 행위로 좁게 열거."
    ),
    proposed_clause=(
        "공급업자는 고객(임차인)과 직접 렌탈 계약을 체결하고, 고객에 대한 세금계산서 발행, "
        "대금 청구 및 수금의 법적 주체는 공급업자로 한다. 대리점은 공급업자로부터 위탁받은 "
        "범위 내에서 고객 발굴, 상담, 계약정보 등록, 납품 일정 협의, 검수 지원, 오피스케어 및 "
        "대금청구·수금 지원 등의 용역을 수행하며, 고객과의 렌탈계약의 당사자가 아니다. "
        "대리점은 공급업자의 사전 서면 승인 없이 공급업자를 대리하여 계약을 체결하거나 "
        "공급업자 명의의 법률행위를 할 수 없다."
    ),
    negotiation_position=(
        "당사(퍼시스) 거래구조의 법적 명확화로, 협상 여지 없음. "
        "상대방 반발 시 세금계산서 발행 실무 및 소비자보호법 책임 분리 필요성을 설명할 것."
    ),
)

# ─── DLR-002 ─────────────────────────────────────────────────────────────────

DLR_002 = DLRRule(
    rule_id="DLR-002",
    rule_title="세금계산서/렌탈료 청구 주체 혼선",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=[
        "세금계산서 발행",
        "세금계산서를 발행",
        "대금의 청구",
        "렌탈료 청구",
        "각종 법률이 규정하고 있는 의무",
        "대리점은 고객에게 세금계산서",
    ],
    trigger_patterns=[
        re.compile(r"세금계산서\s*(발행|를\s*발행)"),
        re.compile(r"렌탈료에\s*대하여\s*고객에게\s*직접"),
    ],
    clause_topics_allowed=["세금계산서", "대금청구", "수금", "렌탈료"],
    issue_title="세금계산서 발행 및 렌탈료 청구 주체 명확화 필요",
    legal_risk=(
        "부가가치세법 §32에 따라 재화/용역 공급자가 세금계산서를 발행해야 합니다. "
        "대리점이 발행 시 명의 불일치로 세무리스크 발생. "
        "공급자 이외의 자가 세금계산서를 발행한 경우 부가가치세법 위반으로 가산세 부과 가능."
    ),
    business_risk=(
        "고객의 매입세액공제 불인정, 세금계산서 무효 처리, 고객의 손해배상 청구 위험. "
        "세무조사 시 허위세금계산서 발행 혐의로 형사 책임 위험."
    ),
    why_this_matters=(
        "퍼시스가 공급자이므로 세금계산서는 반드시 퍼시스가 발행해야 합니다. "
        "계약서에 발행 주체가 불명확하거나 대리점에게 발행 권한을 부여하면 "
        "실무·세무 양면에서 분쟁이 발생합니다."
    ),
    required_action=(
        "세금계산서·대금청구 주체를 공급업자(퍼시스)로 명확히 하고, "
        "대리점은 지원 역할만 명시."
    ),
    proposed_clause=(
        "세금계산서 발행, 현금영수증 발행, 대금 청구의 법적 주체는 고객과 직접 렌탈계약을 "
        "체결한 공급업자로 한다. 대리점은 공급업자가 정한 절차에 따라 고객에 대한 계약정보 등록, "
        "세금계산서 발행 지원, 청구서 전달 및 고객 안내 등의 지원 업무를 성실히 수행한다."
    ),
    negotiation_position=(
        "세무리스크 예방을 위한 필수 조항. 공급업자의 실명 세금계산서 발행 실무와 "
        "일치시키는 조정으로 협상 가능."
    ),
)

# ─── DLR-003 ─────────────────────────────────────────────────────────────────

DLR_003 = DLRRule(
    rule_id="DLR-003",
    rule_title="고객 미수금 책임 전가",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=[
        "렌탈료 미납",
        "미수금",
        "수금 책임",
        "대리점이 이를 부담",
        "대리점에게 부담",
        "수요자의 대금지급이 이루어질 수 있도록",
        "미납 발생 시",
        "고객의 렌탈료 미납",
    ],
    trigger_patterns=[
        re.compile(r"미수금.{0,30}대리점"),
        re.compile(r"대리점.{0,30}미수금"),
        re.compile(r"렌탈료\s*미납.{0,50}대리점"),
    ],
    clause_topics_allowed=["수금", "미수금", "렌탈료", "대금지급"],
    issue_title="고객 미수금 책임 전가 — 귀책사유 한정 필요",
    legal_risk=(
        "가맹사업법·대리점거래법 §12 불이익 제공 금지 위반 소지. "
        "대리점의 귀책 없는 고객 미납에 대한 손실 전가는 불공정 거래 행위로 "
        "공정거래위원회 시정명령 및 과징금 위험이 있습니다."
    ),
    business_risk=(
        "고객의 렌탈료 미납 시 대리점이 무한 책임을 부담하게 되어 수수료를 초과하는 손실 발생 가능. "
        "대리점이 미수금 전가에 불만을 품고 계약 분쟁 제기 위험. "
        "공정위 조사 시 불이익 제공 행위로 제재 위험."
    ),
    why_this_matters=(
        "대리점은 렌탈계약 당사자가 아니므로 고객 미납 리스크를 부담하는 것은 "
        "구조적으로 부당합니다. 귀책사유 범위를 명확히 한정하지 않으면 "
        "대리점이 의도치 않은 무한 채무보증인이 될 수 있습니다."
    ),
    required_action=(
        "고객 미수금 책임을 대리점의 귀책사유(허위정보 제공, 절차 위반)가 있는 경우로 한정. "
        "귀책사유 없는 미납은 퍼시스가 부담하는 구조 명시."
    ),
    proposed_clause=(
        "대리점은 고객의 대금 납부가 이루어질 수 있도록 성실히 지원 업무를 수행한다. "
        "다만, 대리점의 귀책사유(허위 정보 제공, 공급업자 사전 승인 없는 계약 진행, "
        "공급업자가 정한 절차 위반)로 인하여 고객이 대금을 납부하지 못하게 된 경우에 한하여, "
        "대리점은 자신의 귀책 범위 내에서 공급업자에게 발생한 손해를 배상한다."
    ),
    negotiation_position=(
        "대리점법·가맹사업법 불이익 제공 금지 규정 근거로 강하게 협상 가능. "
        "귀책사유 한정 문구는 삭제 불가."
    ),
)

# ─── DLR-004 ─────────────────────────────────────────────────────────────────

DLR_004 = DLRRule(
    rule_id="DLR-004",
    rule_title="수수료 지급 제한/차감/상계/거래보증금 공제",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=[
        "수수료에서 차감",
        "정책지원금에서 상계",
        "거래보증금에서 상계",
        "상계할 수 있다",
        "차감할 수 있다",
        "거래보증금",
        "수수료 차감",
        "비용을 수수료에서",
    ],
    trigger_patterns=[
        re.compile(r"수수료.{0,20}(차감|상계|공제)"),
        re.compile(r"(보증금|정책지원금).{0,20}(차감|상계)"),
    ],
    clause_topics_allowed=["수수료", "상계", "보증금", "차감", "정산"],
    issue_title="수수료 차감·상계 — 사전 통지·이의절차 미비",
    legal_risk=(
        "대리점거래법 §12, 공정거래법 §45 불공정거래행위 금지. "
        "사전 통지·증빙 없는 일방적 상계는 위법. "
        "거래보증금 몰취 조항이 실손해를 초과하면 민법상 위약벌 제한 규정에 저촉될 수 있습니다."
    ),
    business_risk=(
        "대리점 현금흐름 심각 위협. "
        "분쟁 시 상계 금액의 귀책·증빙 입증 불가 위험. "
        "대리점이 이의제기 없이 수수료를 잠식당하는 구조."
    ),
    why_this_matters=(
        "수수료 상계는 대리점의 핵심 수익에 직접 영향을 미치므로 절차 보장이 필수입니다. "
        "사전 통지 없는 상계는 대리점법상 불이익 제공으로 공정위 제재 대상입니다."
    ),
    required_action=(
        "상계 전 사전 통지·증빙 제공, 이의절차, 다툼 있는 금액 상계 유예 조항 삽입. "
        "상계 사유 구체화 필요."
    ),
    proposed_clause=(
        "공급업자는 대리점에게 비용을 청구하거나 용역수수료, 정책지원금 또는 거래보증금에서 "
        "상계하려는 경우, 해당 비용의 발생 사유, 귀책 주체, 산정 내역, 증빙자료 및 상계 예정일을 "
        "사전에 대리점에게 서면으로 통지하여야 한다. 대리점이 통지를 받은 날부터 10영업일 이내에 "
        "이의를 제기한 금액에 대해서는 당사자 간 협의 또는 객관적 자료에 의해 금액이 확정되기 "
        "전까지 임의로 상계하지 않는다."
    ),
    negotiation_position=(
        "대리점법 §12 기준 필수 절차 보장. 이의기간(10일→5일)은 협상 가능하나 "
        "절차 자체는 삭제 불가."
    ),
)

# ─── DLR-005 ─────────────────────────────────────────────────────────────────

DLR_005 = DLRRule(
    rule_id="DLR-005",
    rule_title="계약해지/갱신거절/물량축소/업무이관",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=[
        "계약을 즉시 해지",
        "물량을 현저히 축소",
        "갱신을 거절",
        "갱신을 거절할 수 있다",
        "업무를 이관",
        "공급을 중단",
        "물량을 축소",
        "물량 축소",
        "계약을 종료",
    ],
    trigger_patterns=[
        re.compile(r"갱신\s*거절"),
        re.compile(r"물량.{0,10}(축소|삭감)"),
        re.compile(r"계약.{0,15}(해지|종료).{0,15}(통보|사전)"),
    ],
    clause_topics_allowed=["해지", "갱신", "계약종료", "물량", "업무이관"],
    issue_title="계약해지·갱신거절 요건 — 시정기회 및 비례성 원칙 부재",
    legal_risk=(
        "대리점거래법 §13 계약 갱신 요구권, §14 부당한 계약 해지 금지. "
        "즉시 해지는 중대한 위반+상당 기간 시정 기회 부여 후에만 허용. "
        "정당한 사유 없는 갱신거절은 대리점법 §13 위반으로 손해배상 의무 발생."
    ),
    business_risk=(
        "대리점의 투자·인력·고객 기반이 하루아침에 소멸. "
        "물량 축소를 해지 대체 수단으로 악용하여 실질적 계약 종료 효과 야기 가능. "
        "퍼시스가 갱신거절 이유를 소명하지 못하면 손해배상 소송 피소 위험."
    ),
    why_this_matters=(
        "합리적 해지 기준 없이 일방적 해지·갱신거절이 가능하면 대리점 운영의 "
        "지속성이 근본적으로 불안정합니다. 대리점법은 공급업자의 갱신거절권을 엄격히 제한합니다."
    ),
    required_action=(
        "해지 사유 구체화, 중대성 기준 명시, 시정 기회(30일 이상), "
        "갱신거절 시 서면 사유 통지 의무, 물량 축소와 계약 해지 연계 방지 조항 삽입."
    ),
    proposed_clause=(
        "공급업자는 대리점이 본 계약의 중대한 의무를 위반하고, 공급업자가 서면으로 위반 사실 및 "
        "시정 요구를 통지한 날부터 30일 이내에 시정하지 않는 경우에 한하여 본 계약을 해지할 수 있다. "
        "단, 대리점의 위반 행위가 경미한 경우 해지보다는 공급 물량 유지 상태에서 시정 조치를 "
        "우선 적용한다. 공급업자가 계약 갱신을 거절하는 경우에는 갱신 만료일 90일 전에 그 사유를 "
        "서면으로 대리점에게 통지하여야 한다. 공급업자의 귀책사유로 인한 계약 해지 시에는 "
        "대리점에 발생한 손해를 배상한다."
    ),
    negotiation_position=(
        "대리점법 §13·§14 기준 최소 보호 조항. 시정 기간(30일→14일)은 협상 가능. "
        "갱신거절 통지 기간(90일→60일)도 협상 가능하나 사유 서면 통지 의무 자체는 유지."
    ),
)

# ─── DLR-006 ─────────────────────────────────────────────────────────────────

DLR_006 = DLRRule(
    rule_id="DLR-006",
    rule_title="비용분담/판촉비/광고비/반품비/원상회복비 전가",
    severity="MEDIUM",
    approval_required=False,
    trigger_keywords=[
        "판촉비",
        "광고비",
        "반품비",
        "원상회복비",
        "인테리어 비용",
        "비용을 대리점이",
        "대리점 부담으로",
        "대리점 부담",
        "판촉 활동 비용",
        "공동 판촉",
    ],
    trigger_patterns=[
        re.compile(r"(판촉|광고|반품|원상회복).{0,20}(비용|대리점|부담)"),
        re.compile(r"대리점.{0,10}(부담|비용)"),
    ],
    clause_topics_allowed=["비용분담", "판촉", "광고", "반품", "원상회복"],
    issue_title="판촉·광고·반품비 부담 — 사전 합의 요건 부재",
    legal_risk=(
        "대리점거래법 §12 불이익 제공 금지. "
        "일방적 비용 전가는 불공정 거래 행위. "
        "사전 합의 없이 비용 부담을 요구하면 대리점법 §12 위반으로 "
        "공정위 시정명령 및 과징금 위험."
    ),
    business_risk=(
        "판촉비·반품비가 수수료를 초과할 경우 실질 손실 발생. "
        "예측 불가능한 비용 청구로 대리점의 사업 계획 불가."
    ),
    why_this_matters=(
        "대리점이 부담하는 비용 항목과 상한이 명확하지 않으면 "
        "예측 불가능한 비용 리스크가 발생합니다. "
        "특히 반품비·원상회복비는 고액이 될 수 있어 사전 합의가 필수입니다."
    ),
    required_action=(
        "비용 부담 항목 열거, 상한 설정, 사전 서면 합의 요건 명시. "
        "대리점 부담 항목 외의 비용은 공급업자 부담으로 명시."
    ),
    proposed_clause=(
        "공급업자가 대리점에게 판촉비, 광고비, 인테리어비, 반품비 또는 원상회복비를 "
        "부담하게 하는 경우, 해당 비용의 항목, 산정 기준 및 상한을 사전에 서면으로 합의한다. "
        "사전 합의 없는 비용 부담 요구는 효력이 없다."
    ),
    negotiation_position=(
        "대리점법 기준 필수. 비용 항목은 협의 가능하나 "
        "사전 합의 요건 자체는 유지."
    ),
)

# ─── DLR-007 ─────────────────────────────────────────────────────────────────

DLR_007 = DLRRule(
    rule_id="DLR-007",
    rule_title="대리점 경영활동 간섭/인력통제",
    severity="MEDIUM",
    approval_required=False,
    trigger_keywords=[
        "인력 배치",
        "직원 교육 의무",
        "인력 기준",
        "직원 자격",
        "판매 인력",
        "전담 인력",
        "인력 요건",
        "영업 인력 채용",
    ],
    trigger_patterns=[
        re.compile(r"(인력|직원|판매원).{0,15}(배치|채용|자격|기준|평가)"),
        re.compile(r"(전담|전속)\s*(인력|직원|담당자)"),
    ],
    clause_topics_allowed=["인력", "경영간섭", "영업방식", "운영기준"],
    issue_title="대리점 인력 통제 — 독립사업자 지위 침해 위험",
    legal_risk=(
        "대리점거래법 §12 불이익 제공 금지. "
        "독립 사업자인 대리점의 인력 채용·배치에 과도한 관여는 위법. "
        "실질적 사용종속관계 인정 시 근로기준법상 사용자 책임 발생 위험."
    ),
    business_risk=(
        "인력 기준 미충족을 이유로 수수료 차감·계약 해지 악용 가능. "
        "퍼시스가 실질적 사용자로 인정될 경우 대리점 직원의 퇴직금·연차 등 노동법 청구 위험."
    ),
    why_this_matters=(
        "대리점은 독립 사업자이므로 내부 인사·경영에 대한 공급업자의 직접 통제는 부당합니다. "
        "인력 기준이 과도하면 사실상 근로관계가 성립될 수 있어 "
        "퍼시스의 사용자 책임이 문제됩니다."
    ),
    required_action=(
        "인력 요건을 최소 역량 기준으로 한정하고, "
        "채용·배치에 대한 직접 통제 조항 삭제."
    ),
    proposed_clause=(
        "공급업자는 대리점의 영업 담당자가 공급업자의 제품 지식 및 서비스 절차에 관한 "
        "교육을 이수할 것을 권고할 수 있다. 다만, 대리점의 직원 채용, 배치 및 내부 인사 관리는 "
        "대리점의 독립적 경영 판단에 따른다."
    ),
    negotiation_position=(
        "독립 사업자 지위 보호 관점. 교육 이수 '권고'는 수용, "
        "'의무화' 및 '인력 기준 미달 시 제재'는 거부."
    ),
)

# ─── DLR-008 ─────────────────────────────────────────────────────────────────

DLR_008 = DLRRule(
    rule_id="DLR-008",
    rule_title="개인정보/고객정보 처리 및 계약종료 후 이관",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=[
        "고객 정보",
        "개인정보",
        "고객 데이터",
        "고객명단",
        "계약 종료 후",
        "정보 이관",
        "반환",
        "파기",
        "개인정보 제3자 제공",
        "고객에 대한 개인정보",
    ],
    trigger_patterns=[
        re.compile(r"개인정보.{0,30}(이관|파기|반환|처리)"),
        re.compile(r"(계약\s*종료|종료\s*후).{0,30}(개인정보|고객\s*정보|데이터)"),
        re.compile(r"개인정보\s*제3자\s*제공"),
    ],
    clause_topics_allowed=["개인정보", "고객정보", "데이터", "정보처리", "위탁처리"],
    issue_title="개인정보 처리 위탁 및 계약종료 후 파기·이관 절차 미비",
    legal_risk=(
        "개인정보보호법 §26(개인정보 처리 위탁), §28의2(안전조치), §28의8(이전). "
        "대리점이 고객 개인정보를 처리하는 경우 위탁계약서 체결 의무. "
        "계약 종료 후 파기·이관 절차 미비 시 과태료 최대 3,000만원. "
        "개인정보 유출 시 정보주체 1인당 최대 300만원 법정손해배상 청구 가능."
    ),
    business_risk=(
        "개인정보 유출 시 퍼시스에 손해배상 청구 가능. "
        "규제 당국 조사 및 과징금 위험. "
        "대리점이 계약 종료 후 고객 데이터를 경쟁사에 활용하는 위험."
    ),
    why_this_matters=(
        "대리점이 고객 발굴·상담·계약 과정에서 취득한 개인정보는 퍼시스의 데이터이므로 "
        "계약 종료 시 반환·파기 절차가 필수입니다. "
        "개인정보보호법은 위탁자(퍼시스)가 수탁자(대리점)를 감독할 의무를 부과합니다."
    ),
    required_action=(
        "개인정보 처리 위탁 범위 명확화, 안전조치 의무, "
        "계약 종료 후 30일 내 파기·이관 절차 명시."
    ),
    proposed_clause=(
        "대리점은 본 계약의 이행과 관련하여 취득한 고객 개인정보를 개인정보보호법 §26에 따른 "
        "수탁자로서 처리하며, 공급업자의 지시에 따라서만 처리하고 제3자에게 제공하지 않는다. "
        "본 계약 종료 시 대리점은 보유 중인 고객 개인정보를 30일 이내에 공급업자에게 이관하거나 "
        "복구 불가능한 방법으로 파기하고, 그 결과를 서면으로 공급업자에게 통지한다."
    ),
    negotiation_position=(
        "법적 의무 조항으로 협상 불가. "
        "파기 기간(30일)은 협의 가능."
    ),
)


# ─── Export ───────────────────────────────────────────────────────────────────

DLR_RULES: list[DLRRule] = [
    DLR_001, DLR_002, DLR_003, DLR_004,
    DLR_005, DLR_006, DLR_007, DLR_008,
]

# Ordered by TOP risk priority for dealer_rental_service_contract
DLR_TOP_RISK_ORDER: list[str] = [
    "DLR-001",  # 고객계약 구조/대리권 오인
    "DLR-003",  # 고객 미수금 책임 전가
    "DLR-004",  # 수수료/상계/보증금
    "DLR-005",  # 해지/갱신거절/물량축소
    "DLR-008",  # 개인정보
    "DLR-006",  # 비용전가
    "DLR-007",  # 경영간섭
    "DLR-002",  # 세금계산서 혼선 (DLR-001에 흡수되는 경우 많음)
]

_BLOCKED_RULE_ID_PREFIXES: tuple[str, ...] = ("isr_", "sppc_", "pi_", "svc_")


def is_blocked_for_dealer_rental(rule_id: str) -> bool:
    """Return True if this rule ID must never appear in dealer_rental_service_contract output."""
    return any(rule_id.startswith(p) for p in _BLOCKED_RULE_ID_PREFIXES)


def get_triggered_dlr_rules(text: str) -> list[DLRRule]:
    """Return DLR rules triggered by the contract text, sorted by priority."""
    order = {rid: i for i, rid in enumerate(DLR_TOP_RISK_ORDER)}
    triggered = [r for r in DLR_RULES if r.matches_text(text)]
    triggered.sort(key=lambda r: order.get(r.rule_id, 999))
    return triggered


def extract_excerpt(text: str, keywords: list[str], max_len: int = 200) -> str:
    """Extract text excerpt near the first matching keyword."""
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0:
            start = max(0, idx - 30)
            end = min(len(text), idx + max_len)
            return text[start:end].strip()
    return ""
