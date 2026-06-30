"""DLR-RS-001 through DLR-RS-009: Professional legal rules for dealer_rental_service_contract.

3-tier assessment:
  반영됨    — contract already correctly addresses this requirement
  보완 권장  — partial coverage; needs enhancement
  필수 수정  — missing/problematic language creating legal risk
  해당없음   — topic not applicable to this contract
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ASSESSMENT_REFLECTED = "반영됨"
ASSESSMENT_PARTIAL = "보완 권장"
ASSESSMENT_MUST_FIX = "필수 수정"
ASSESSMENT_NA = "해당없음"


@dataclass
class DLRSRule:
    rule_id: str
    rule_title: str
    severity: str          # HIGH / MEDIUM
    approval_required: bool
    trigger_keywords: list
    trigger_patterns: list
    already_reflected_patterns: list   # majority match → 반영됨
    partial_patterns: list             # any match → 보완 권장 (unless critical issue)
    critical_issue_patterns: list      # any match → 필수 수정 (overrides all)
    issue_title: str
    legal_risk: str
    business_risk: str
    why_this_matters: str
    required_action: str
    proposed_clause: str
    current_assessment_reflected: str
    current_assessment_partial: str
    current_assessment_must_fix: str
    negotiation_position: str
    confidence: float = 0.95

    def assess_contract(self, text: str) -> str:
        t = text or ""
        for p in self.critical_issue_patterns:
            if p.search(t):
                return ASSESSMENT_MUST_FIX
        if self.already_reflected_patterns:
            reflected = sum(1 for p in self.already_reflected_patterns if p.search(t))
            threshold = max(1, len(self.already_reflected_patterns) // 2 + 1)
            if reflected >= threshold:
                return ASSESSMENT_REFLECTED
        if self.partial_patterns:
            if any(p.search(t) for p in self.partial_patterns):
                return ASSESSMENT_PARTIAL
        triggered = any(kw in t for kw in self.trigger_keywords)
        if not triggered:
            triggered = any(p.search(t) for p in self.trigger_patterns)
        if not triggered:
            return ASSESSMENT_NA
        return ASSESSMENT_MUST_FIX

    def get_assessment_text(self, assessment: str) -> str:
        if assessment == ASSESSMENT_REFLECTED:
            return self.current_assessment_reflected
        if assessment == ASSESSMENT_PARTIAL:
            return self.current_assessment_partial
        if assessment == ASSESSMENT_MUST_FIX:
            return self.current_assessment_must_fix
        return f"[{self.rule_id}] {self.rule_title} — 해당 계약에 관련 조항이 없어 적용 제외"

    def to_finding(
        self,
        assessment: str,
        excerpt: str = "",
        clause_no: str = "",
        source_section_type: str = "main_contract",
    ) -> dict:
        sev = self.severity if assessment == ASSESSMENT_MUST_FIX else (
            "MEDIUM" if assessment == ASSESSMENT_PARTIAL else "LOW"
        )
        is_must = assessment == ASSESSMENT_MUST_FIX
        is_part = assessment == ASSESSMENT_PARTIAL
        is_refl = assessment == ASSESSMENT_REFLECTED
        return {
            "clause_id": self.rule_id,
            "rule_id": self.rule_id,
            "clause_title": self.rule_title,
            "issue_title": self.issue_title,
            "clause_no": clause_no,
            "source_section_type": source_section_type,
            "current_assessment": assessment,
            "current_assessment_text": self.get_assessment_text(assessment),
            "severity": sev,
            "risk_tier": sev,
            "approval_required": self.approval_required and is_must,
            "high_risk": is_must and self.severity == "HIGH",
            "must_fix": is_must,
            "review_tier": "MUST" if is_must else ("SUGGEST" if is_part else "REFLECTED"),
            "display_bucket": "필수수정" if is_must else ("보완권장" if is_part else "이미반영"),
            "legal_risk": self.legal_risk,
            "business_risk": self.business_risk,
            "why_this_matters": self.why_this_matters,
            "required_action": self.required_action if not is_refl else "",
            "proposed_clause": self.proposed_clause if not is_refl else "",
            "negotiation_position": self.negotiation_position if not is_refl else "",
            "problem": self.legal_risk if not is_refl else "",
            "rewrite_reason": self.required_action if not is_refl else self.current_assessment_reflected,
            "legal_business_reason": self.legal_risk,
            "original_excerpt": excerpt,
            "original_text": excerpt,
            "evidence_from_contract": excerpt,
            "suggested_rewrite": self.proposed_clause if not is_refl else "",
            "proposed_revision": self.proposed_clause if not is_refl else "",
            "has_rewrite_change": not is_refl,
            "confidence": self.confidence,
            "is_mandatory": True,
            "dedup_suppressed": False,
            "keep_as_is": is_refl,
            "user_focus_hit": True,
            "factual_hit": True,
        }


# ─── DLR-RS-001 ───────────────────────────────────────────────────────────────

DLR_RS_001 = DLRSRule(
    rule_id="DLR-RS-001",
    rule_title="고객계약 구조 및 대리권 제한",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=["렌탈 계약", "대리권", "공급업자", "최종 소비자", "주 렌탈계약"],
    trigger_patterns=[
        re.compile(r"공급업자.{0,20}고객.{0,20}(직접|계약)"),
    ],
    already_reflected_patterns=[
        re.compile(r"공급업자와\s*(최종\s*소비자|고객)\s*간의\s*렌탈\s*계약.{0,50}직접\s*체결"),
        re.compile(r"대리점\s*(자신이|은)\s*계약\s*당사자가\s*(되거나|아니)"),
        re.compile(r"법적\s*당사자는\s*공급업자"),
    ],
    partial_patterns=[
        re.compile(r"공급업자.{0,20}고객.{0,20}(체결|계약)"),
    ],
    critical_issue_patterns=[
        re.compile(r"대리점은\s*고객과\s*직접\s*계약"),
        re.compile(r"대리점이\s*(고객과|소비자와)\s*계약을\s*체결"),
    ],
    issue_title="고객계약 구조 및 대리권 범위 명확화",
    legal_risk=(
        "대리점이 고객과의 계약 당사자로 표현될 경우 소비자보호법·부가가치세법 §32상 "
        "세금계산서 발행 주체 분쟁, 제품 하자에 대한 1차 책임이 대리점에 귀속됩니다."
    ),
    business_risk=(
        "고객이 납기 지연·제품 하자를 이유로 대리점을 직접 상대로 소송 제기 가능. "
        "세금계산서 명의 불일치로 고객 매입세액공제 불인정 위험."
    ),
    why_this_matters=(
        "퍼시스가 고객과 직접 렌탈계약을 체결하는 구조에서 대리점은 판매지원 용역자이지 "
        "계약당사자가 아닙니다. 이 원칙이 불명확하면 모든 분쟁에서 책임 귀속이 혼선을 빚습니다."
    ),
    required_action=(
        "거래구조를 '공급업자가 고객과 직접 계약, 대리점은 위탁 범위 내 지원'으로 명확화. "
        "대리권 범위를 사전 서면 승인 필요 행위로 좁게 열거."
    ),
    proposed_clause=(
        "공급업자는 고객(임차인)과 직접 렌탈 계약을 체결하고, 고객에 대한 세금계산서 발행, "
        "대금 청구 및 수금의 법적 주체는 공급업자로 한다. 대리점은 공급업자로부터 위탁받은 "
        "범위 내에서 고객 발굴, 상담, 계약정보 등록, 납품 일정 협의, 검수 지원 등의 용역을 "
        "수행하며, 고객과의 렌탈계약의 당사자가 아니다."
    ),
    current_assessment_reflected=(
        "제2조에서 '공급업자와 고객이 직접 체결', '대리점 자신이 계약 당사자가 되거나 "
        "법적으로 구속하는 행위를 할 수 없다'고 명시 — 역할 분리가 명확하게 반영되어 있습니다."
    ),
    current_assessment_partial=(
        "고객계약 구조가 언급되어 있으나, 대리점의 대리권 제한 범위 또는 "
        "공급업자가 계약의 유일한 법적 당사자임이 충분히 명시되지 않았습니다."
    ),
    current_assessment_must_fix=(
        "대리점이 고객과 직접 계약의 당사자가 되는 구조이거나, 역할 분리 조항이 없어 "
        "DLR-RS-001 HIGH 리스크가 존재합니다. 구조 명확화가 필수입니다."
    ),
    negotiation_position=(
        "당사(퍼시스) 거래구조의 법적 명확화로, 협상 여지 없음."
    ),
)

# ─── DLR-RS-002 ───────────────────────────────────────────────────────────────

DLR_RS_002 = DLRSRule(
    rule_id="DLR-RS-002",
    rule_title="세금계산서/증빙 발행 및 렌탈료 청구 주체",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=["세금계산서", "렌탈료", "대금청구", "청구"],
    trigger_patterns=[
        re.compile(r"세금계산서\s*(발행|를\s*발행)"),
        re.compile(r"렌탈료.{0,20}(청구|수령|발행)"),
    ],
    already_reflected_patterns=[
        re.compile(r"공급업자는.{0,30}직접\s*세금계산서를\s*발행"),
        re.compile(r"대리점은.{0,30}(청구하거나|수령할\s*수\s*없다)"),
    ],
    partial_patterns=[
        re.compile(r"공급업자.{0,30}세금계산서"),
        re.compile(r"공급업자.{0,30}렌탈료.{0,30}청구"),
    ],
    critical_issue_patterns=[
        re.compile(r"대리점.{0,20}세금계산서.{0,20}(발행|를 발행)"),
        re.compile(r"대리점이.{0,20}렌탈료를.{0,20}청구"),
    ],
    issue_title="세금계산서 발행 및 렌탈료 청구 주체 명확화",
    legal_risk=(
        "부가가치세법 §32에 따라 재화/용역 공급자가 세금계산서를 발행해야 합니다. "
        "대리점이 발행 시 명의 불일치로 세무리스크 발생."
    ),
    business_risk=(
        "고객의 매입세액공제 불인정, 세금계산서 무효 처리, 고객 손해배상 청구 위험."
    ),
    why_this_matters=(
        "퍼시스가 공급자이므로 세금계산서는 반드시 퍼시스가 발행해야 합니다."
    ),
    required_action=(
        "세금계산서·대금청구 주체를 공급업자(퍼시스)로 명확히 하고, 대리점은 지원 역할만 명시."
    ),
    proposed_clause=(
        "세금계산서 발행, 현금영수증 발행, 대금 청구의 법적 주체는 공급업자로 한다. "
        "대리점은 공급업자가 정한 절차에 따라 계약정보 등록, 세금계산서 발행 지원, "
        "청구서 전달 및 고객 안내 등의 지원 업무를 성실히 수행한다."
    ),
    current_assessment_reflected=(
        "제3조에서 '공급업자는 렌탈료에 대하여 고객에게 직접 세금계산서를 발행', "
        "'대리점은 이를 대신하여 청구하거나 수령할 수 없다'고 명시 — "
        "발행·청구 주체가 명확하게 반영되어 있습니다."
    ),
    current_assessment_partial=(
        "공급업자가 세금계산서를 발행함은 언급되나, 대리점의 청구·수령 불가 조항이 없어 "
        "향후 해석 분쟁 가능성이 있습니다."
    ),
    current_assessment_must_fix=(
        "세금계산서 발행 및 렌탈료 청구 주체가 불명확하거나, 대리점이 청구·수령 권한을 "
        "가지는 것으로 해석될 수 있습니다. 즉시 명확화가 필요합니다."
    ),
    negotiation_position=(
        "세무리스크 예방을 위한 필수 조항. 협상 불가."
    ),
)

# ─── DLR-RS-003 ───────────────────────────────────────────────────────────────

DLR_RS_003 = DLRSRule(
    rule_id="DLR-RS-003",
    rule_title="고객 미수금 책임 전가 제한",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=["미수금", "렌탈료 미납", "수금 책임", "미납"],
    trigger_patterns=[
        re.compile(r"(미수금|미납).{0,30}대리점"),
        re.compile(r"대리점.{0,30}(미수금|미납|보전)"),
    ],
    already_reflected_patterns=[
        # 귀책 한정 + 구체적 상한/열거가 모두 있어야 완전 반영
        re.compile(r"귀책.{0,30}(상한|초과하지\s*아니|이하로\s*한정)"),
        re.compile(r"귀책사유.{0,50}(허위\s*정보\s*제공|절차\s*위반|사전\s*승인\s*없)"),
    ],
    partial_patterns=[
        # 귀책 한정은 있으나 범위(상한) 미정의 → 보완 권장
        re.compile(r"공급업자가\s*원칙적으로\s*관리\s*책임"),
        re.compile(r"직접적인\s*귀책이\s*있는\s*경우에\s*한하여"),
        re.compile(r"귀책.{0,20}경우에\s*한하여"),
        re.compile(r"귀책사유.{0,20}(있는|있을)\s*경우"),
    ],
    critical_issue_patterns=[
        re.compile(r"미수금.{0,30}대리점이\s*부담"),
        re.compile(r"대리점이.{0,30}미수금.{0,30}책임"),
        re.compile(r"대리점.{0,20}수금\s*보증"),
    ],
    issue_title="고객 미수금 책임 전가 — 귀책사유 및 범위 명확화 권장",
    legal_risk=(
        "가맹사업법·대리점거래법 §12 불이익 제공 금지 위반 소지. "
        "귀책 없는 고객 미납에 대한 손실 전가는 불공정 거래 행위입니다."
    ),
    business_risk=(
        "고객 렌탈료 미납 시 대리점이 무한 책임 부담 가능. "
        "수수료를 초과하는 손실 발생 위험."
    ),
    why_this_matters=(
        "대리점은 렌탈계약 당사자가 아니므로 고객 미납 리스크를 부담하는 것은 구조적으로 부당합니다. "
        "귀책사유 범위가 명확하지 않으면 대리점이 의도치 않은 채무보증인이 될 수 있습니다."
    ),
    required_action=(
        "보전 의무의 '일정 범위'를 구체적으로 정의하고(예: 분기 수수료의 XX% 상한), "
        "귀책사유 유형을 열거적으로 명시할 것을 권장합니다."
    ),
    proposed_clause=(
        "대리점은 고객의 대금 납부가 이루어질 수 있도록 성실히 지원 업무를 수행한다. "
        "다만, 대리점의 귀책사유(허위 정보 제공, 공급업자 사전 승인 없는 계약 진행, "
        "공급업자가 정한 절차 위반)로 인하여 고객이 대금을 납부하지 못하게 된 경우에 한하여, "
        "대리점은 자신의 귀책 범위 내에서 공급업자에게 발생한 손해를 배상한다. "
        "이 경우 대리점의 배상 책임은 해당 분기 수수료의 50%를 초과하지 아니한다."
    ),
    current_assessment_reflected=(
        "제5조에서 '공급업자가 원칙적으로 관리 책임을 진다', '직접적인 귀책이 있는 경우에 한하여' "
        "부담이 있음을 명시 — 미수금 책임 분리 구조가 반영되어 있습니다. "
        "다만, '일정 범위'의 구체적 정의를 추가하면 더욱 안전합니다."
    ),
    current_assessment_partial=(
        "미수금 책임에 귀책사유 한정 문구는 있으나, '일정 범위의 보전 의무'가 "
        "구체적으로 정의되지 않아 해석 분쟁 가능성이 있습니다. "
        "상한 금액 또는 귀책사유 유형의 열거적 명시를 권장합니다."
    ),
    current_assessment_must_fix=(
        "대리점이 고객 미수금을 무한 부담하거나, 귀책사유 제한 없이 책임을 부담하도록 "
        "구성되어 있습니다. 대리점거래법 §12 위반 소지가 있습니다."
    ),
    negotiation_position=(
        "대리점법·가맹사업법 불이익 제공 금지 근거로 강하게 협상 가능. "
        "귀책사유 한정 및 상한 문구는 삭제 불가."
    ),
)

# ─── DLR-RS-004 ───────────────────────────────────────────────────────────────

DLR_RS_004 = DLRSRule(
    rule_id="DLR-RS-004",
    rule_title="용역수수료 지급요건, 지급 제한, 차감 절차",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=["수수료에서 차감", "수수료 차감", "비용을 수수료에서", "차감할 수 있다"],
    trigger_patterns=[
        re.compile(r"수수료.{0,20}(차감|공제)"),
        re.compile(r"비용을\s*수수료에서"),
    ],
    already_reflected_patterns=[
        re.compile(r"수수료.{0,30}차감.{0,50}(사전|통지|서면)"),
        re.compile(r"이의.{0,20}(제기|절차).{0,30}수수료"),
        re.compile(r"차감.{0,30}(이의|다툼).{0,30}(유예|정지)"),
    ],
    partial_patterns=[],
    critical_issue_patterns=[
        re.compile(r"수수료에서\s*차감할\s*수\s*있다"),
        re.compile(r"비용을\s*수수료에서\s*차감"),
        re.compile(r"정책지원금에서\s*상계"),
    ],
    issue_title="수수료 차감 — 사전 통지·이의 절차 부재 필수 수정",
    legal_risk=(
        "대리점거래법 §12, 공정거래법 §45 불공정거래행위 금지. "
        "사전 통지·증빙 없는 일방적 상계는 위법. "
        "공정위 시정명령 및 과징금 위험."
    ),
    business_risk=(
        "대리점 현금흐름 심각 위협. "
        "분쟁 시 상계 금액의 귀책·증빙 입증 불가 위험."
    ),
    why_this_matters=(
        "수수료 상계는 대리점의 핵심 수익에 직접 영향을 미치므로 절차 보장이 필수입니다. "
        "사전 통지 없는 상계는 대리점법상 불이익 제공으로 공정위 제재 대상입니다."
    ),
    required_action=(
        "상계 전 사전 통지(사유·증빙·산정내역), 이의 절차(10영업일), "
        "다툼 있는 금액 상계 유예 조항 삽입 필수."
    ),
    proposed_clause=(
        "공급업자는 대리점에게 비용을 청구하거나 용역수수료에서 상계하려는 경우, "
        "해당 비용의 발생 사유, 귀책 주체, 산정 내역, 증빙자료 및 상계 예정일을 "
        "사전에 대리점에게 서면으로 통지하여야 한다. 대리점이 통지를 받은 날부터 "
        "10영업일 이내에 이의를 제기한 금액에 대해서는 당사자 간 협의 또는 "
        "객관적 자료에 의해 금액이 확정되기 전까지 임의로 상계하지 않는다."
    ),
    current_assessment_reflected=(
        "수수료 차감 시 사전 통지·이의 절차가 명시되어 있습니다."
    ),
    current_assessment_partial=(
        "수수료 차감 조항이 있으나 사전 통지 또는 이의 절차 중 일부가 누락되어 있습니다."
    ),
    current_assessment_must_fix=(
        "제4조③에서 '미이행 의무에 따른 비용을 수수료에서 차감할 수 있다'고 규정하나, "
        "사전 통지 의무, 이의 절차, 다툼 금액 상계 유예 조항이 전혀 없습니다. "
        "대리점거래법 §12 위반 소지가 있습니다. 즉시 수정이 필요합니다."
    ),
    negotiation_position=(
        "대리점법 §12 기준 필수 절차 보장. 이의기간(10일→5일)은 협상 가능하나 "
        "절차 자체는 삭제 불가."
    ),
)

# ─── DLR-RS-005 ───────────────────────────────────────────────────────────────

DLR_RS_005 = DLRSRule(
    rule_id="DLR-RS-005",
    rule_title="거래보증금 상계 및 반환 절차",
    severity="MEDIUM",
    approval_required=False,
    trigger_keywords=["거래보증금", "보증금"],
    trigger_patterns=[
        re.compile(r"거래\s*보증금"),
        re.compile(r"보증금.{0,20}(상계|반환|차감)"),
    ],
    already_reflected_patterns=[
        re.compile(r"거래보증금.{0,50}(사전\s*통지|이의|반환\s*절차)"),
        re.compile(r"보증금.{0,30}(반환.{0,20}기한|상계.{0,20}통지)"),
    ],
    partial_patterns=[
        re.compile(r"거래보증금.{0,30}(반환|상계)"),
    ],
    critical_issue_patterns=[
        re.compile(r"거래보증금.{0,30}(몰취|일방적\s*상계|임의\s*상계)"),
        re.compile(r"보증금.{0,20}공급업자.{0,20}재량"),
    ],
    issue_title="거래보증금 상계 및 반환 — 절차 명시 필요",
    legal_risk=(
        "대리점거래법 §12 불이익 제공 금지. "
        "사전 통지·증빙 없는 일방적 보증금 상계는 위법."
    ),
    business_risk=(
        "대리점 현금 자산 일방적 몰수 위험."
    ),
    why_this_matters=(
        "거래보증금은 대리점의 실질 현금 자산으로, 반환·상계 절차가 불명확하면 "
        "계약 종료 시 대리점이 불이익을 받을 수 있습니다."
    ),
    required_action=(
        "거래보증금 상계 시 사전 통지, 이의 절차 명시; "
        "계약 종료 후 보증금 반환 기한(30일 이내) 명시."
    ),
    proposed_clause=(
        "공급업자는 거래보증금에서 상계하려는 경우, 상계 사유·금액·증빙자료를 서면으로 "
        "사전 통지하고 대리점에게 10영업일의 이의 기간을 부여하여야 한다. "
        "본 계약 종료 시 공급업자는 상계 확정액을 제외한 거래보증금을 계약 종료일로부터 "
        "30일 이내에 대리점에게 반환하여야 한다."
    ),
    current_assessment_reflected=(
        "거래보증금 상계 및 반환 절차가 명확하게 규정되어 있습니다."
    ),
    current_assessment_partial=(
        "거래보증금 조항이 있으나 상계 사전 통지 또는 반환 기한이 누락되어 있습니다."
    ),
    current_assessment_must_fix=(
        "거래보증금 조항에서 사전 통지 없는 일방적 상계 또는 반환 절차가 불명확합니다."
    ),
    negotiation_position=(
        "거래보증금이 있는 계약에서는 반환 기한과 이의 절차가 필수입니다. "
        "반환 기한(30일→14일)은 협상 가능."
    ),
)

# ─── DLR-RS-006 ───────────────────────────────────────────────────────────────

DLR_RS_006 = DLRSRule(
    rule_id="DLR-RS-006",
    rule_title="계약해지/업무이관/수수료 중단의 중대성·시정기회·비례성",
    severity="HIGH",
    approval_required=True,
    trigger_keywords=["계약을 해지", "갱신을 거절", "갱신 거절", "계약을 종료", "물량을 축소"],
    trigger_patterns=[
        re.compile(r"(계약|갱신).{0,10}(해지|거절|종료)"),
        re.compile(r"물량.{0,10}(축소|삭감)"),
    ],
    already_reflected_patterns=[
        re.compile(r"중대한\s*(계약\s*)?위반.{0,30}(시정|기회)"),
        re.compile(r"갱신\s*거절.{0,30}(사유|서면|통지).{0,30}(없으면|불가|금지)"),
        re.compile(r"정당한\s*사유\s*없이.{0,20}갱신.{0,20}(거절\s*불가|거절\s*금지)"),
    ],
    partial_patterns=[
        re.compile(r"(30일|14일|60일).{0,20}(전|이전|사전).{0,20}(통보|통지)"),
        re.compile(r"(서면|이유).{0,20}(갱신\s*거절|거절\s*이유)"),
    ],
    critical_issue_patterns=[
        re.compile(r"정당한\s*사유\s*없이\s*갱신을\s*거절할\s*수\s*있다"),
        re.compile(r"이유\s*없이.{0,20}(갱신|계약).{0,20}(거절|종료)"),
        re.compile(r"공급업자.{0,10}(임의로|일방적으로).{0,20}(해지|종료|거절)"),
    ],
    issue_title="계약해지·갱신거절 — '정당한 사유 없이 갱신 거절' 조항 필수 수정",
    legal_risk=(
        "대리점거래법 §13 계약 갱신 요구권, §14 부당한 계약 해지 금지. "
        "'정당한 사유 없이 갱신을 거절할 수 있다'는 대리점법 §13 위반. "
        "손해배상 의무 발생."
    ),
    business_risk=(
        "대리점의 투자·인력·고객 기반이 일방적 갱신 거절로 소멸. "
        "퍼시스가 갱신거절 사유를 소명하지 못하면 손해배상 소송 피소 위험."
    ),
    why_this_matters=(
        "대리점법은 '정당한 사유 없는 갱신거절'을 명시적으로 금지합니다. "
        "이 조항이 있으면 퍼시스는 계약 갱신 시 언제든 일방적으로 종료할 수 있어 "
        "대리점 운영의 지속성이 근본적으로 불안정합니다."
    ),
    required_action=(
        "'정당한 사유 없이 갱신을 거절할 수 있다' 문구 즉시 삭제. "
        "갱신 거절은 정당한 사유가 있을 때만 가능하고, "
        "갱신 만료 90일 전 서면 사유 통지 의무 신설."
    ),
    proposed_clause=(
        "공급업자는 대리점이 본 계약의 중대한 의무를 위반하고, 공급업자가 서면으로 위반 사실 및 "
        "시정 요구를 통지한 날부터 30일 이내에 시정하지 않는 경우에 한하여 본 계약을 해지할 수 있다. "
        "단, 대리점의 위반 행위가 경미한 경우 해지보다는 시정 조치를 우선 적용한다. "
        "공급업자가 계약 갱신을 거절하는 경우에는 갱신 만료일 90일 전에 그 사유를 서면으로 "
        "대리점에게 통지하여야 하며, 정당한 사유 없이 갱신을 거절할 수 없다."
    ),
    current_assessment_reflected=(
        "중대한 위반에 대한 시정기회 및 갱신거절 요건이 대리점거래법 기준에 부합하게 반영되어 있습니다."
    ),
    current_assessment_partial=(
        "계약 해지 시 사전 통보 조항은 있으나, 갱신거절 요건(정당한 사유 명시)이 불충분합니다."
    ),
    current_assessment_must_fix=(
        "제7조②에서 '공급업자는 정당한 사유 없이 갱신을 거절할 수 있다'고 규정 — "
        "이는 대리점거래법 §13 갱신 요구권을 정면으로 위반합니다. "
        "해당 문구를 즉시 삭제하고, '정당한 사유가 있을 때에만 갱신을 거절할 수 있다'로 "
        "수정하며 사전 서면 통지 의무를 추가해야 합니다."
    ),
    negotiation_position=(
        "대리점법 §13·§14 기준 최소 보호 조항. '정당한 사유 없이' 문구는 절대 유지 불가."
    ),
)

# ─── DLR-RS-007 ───────────────────────────────────────────────────────────────

DLR_RS_007 = DLRSRule(
    rule_id="DLR-RS-007",
    rule_title="취소·반품·A/S·추가비용의 대리점 귀책 범위 제한",
    severity="MEDIUM",
    approval_required=False,
    trigger_keywords=["A/S", "하자보수", "취소", "반품", "설치 관련 하자", "대리점 부담"],
    trigger_patterns=[
        re.compile(r"(A/S|하자보수|취소|반품).{0,30}(대리점|부담)"),
        re.compile(r"설치\s*관련\s*하자"),
    ],
    already_reflected_patterns=[
        re.compile(r"최종\s*책임은\s*공급업자"),
        re.compile(r"설치.{0,20}하자.{0,30}(귀책\s*범위|귀책\s*한정|범위\s*내)"),
    ],
    partial_patterns=[
        re.compile(r"최종\s*책임은\s*공급업자"),
        re.compile(r"(A/S|하자보수).{0,30}공급업자"),
    ],
    critical_issue_patterns=[
        re.compile(r"(A/S|하자|취소|반품).{0,30}모든\s*책임.{0,20}대리점"),
        re.compile(r"대리점이.{0,20}(A/S|하자|취소|반품).{0,20}전액\s*부담"),
    ],
    issue_title="설치 하자 대리점 부담 — 귀책 범위 구체화 권장",
    legal_risk=(
        "대리점거래법 §12 불이익 제공 금지. "
        "설치 하자 외 제품 하자에 대한 대리점 책임 전가는 위법 소지."
    ),
    business_risk=(
        "설치 관련 하자의 범위가 불명확하여 예측하지 못한 비용 부담 발생 가능."
    ),
    why_this_matters=(
        "제6조①에서 최종 책임이 공급업자에게 있다고 하면서, 제6조②에서 '설치 관련 하자는 "
        "대리점 부담'이라고만 하면 설치와 제품 하자의 경계가 불명확합니다."
    ),
    required_action=(
        "대리점 부담 하자의 범위를 '대리점이 직접 수행한 설치 작업에서 발생한 하자로서 "
        "대리점의 귀책사유가 명확한 경우'로 한정할 것을 권장합니다."
    ),
    proposed_clause=(
        "A/S, 하자보수, 취소, 반품에 관한 최종 책임은 공급업자에게 있다. "
        "대리점은 고객 서비스 창구 역할을 수행하며, 대리점이 직접 수행한 "
        "설치 작업에서 발생한 하자로서 대리점의 귀책사유가 명확한 경우에 한하여 "
        "대리점이 해당 하자 처리 비용을 부담한다."
    ),
    current_assessment_reflected=(
        "A/S 및 하자에 대한 최종 책임이 공급업자에 있으며, 대리점의 귀책 범위가 명확하게 한정되어 있습니다."
    ),
    current_assessment_partial=(
        "제6조①에서 최종 책임이 공급업자에 있음을 명시하였으나, "
        "제6조②에서 '설치 관련 하자는 대리점 부담'이라는 문구가 귀책 범위를 한정하지 않고 있습니다. "
        "설치 하자와 제품 하자의 경계가 불명확하여 분쟁 시 대리점의 과도한 책임 부담 가능성이 있습니다. "
        "귀책사유를 명확히 한정하는 문구 추가를 권장합니다."
    ),
    current_assessment_must_fix=(
        "취소·반품·A/S 비용이 귀책 범위 한정 없이 대리점에 전가되고 있습니다. 즉시 수정이 필요합니다."
    ),
    negotiation_position=(
        "귀책 범위 한정은 대리점법 기준 필수. '귀책사유가 명확한 경우' 문구는 유지."
    ),
)

# ─── DLR-RS-008 ───────────────────────────────────────────────────────────────

DLR_RS_008 = DLRSRule(
    rule_id="DLR-RS-008",
    rule_title="개인정보/고객정보 처리 및 계약종료 후 이관",
    severity="MEDIUM",
    approval_required=False,
    trigger_keywords=["개인정보", "고객 정보", "고객에 대한 개인정보", "정보 이관"],
    trigger_patterns=[
        re.compile(r"개인정보\s*(처리|제3자|보호)"),
        re.compile(r"(계약\s*종료|종료\s*후).{0,30}(개인정보|고객\s*정보)"),
    ],
    already_reflected_patterns=[
        re.compile(r"개인정보보호법\s*§?26.{0,30}(수탁|위탁)"),
        re.compile(r"계약\s*종료.{0,30}(파기|이관).{0,30}(30일|이내)"),
    ],
    partial_patterns=[
        re.compile(r"개인정보\s*제3자\s*제공"),
        re.compile(r"개인정보.{0,30}(처리|보호|위탁)"),
    ],
    critical_issue_patterns=[
        re.compile(r"대리점.{0,20}개인정보.{0,20}(자유롭게|임의로)\s*(사용|활용|제공)"),
    ],
    issue_title="개인정보 처리 위탁 및 계약종료 후 파기·이관 절차 미비",
    legal_risk=(
        "개인정보보호법 §26(개인정보 처리 위탁). "
        "계약 종료 후 파기·이관 절차 미비 시 과태료 최대 3,000만원. "
        "개인정보 유출 시 정보주체 1인당 최대 300만원 법정손해배상."
    ),
    business_risk=(
        "규제 당국 조사 및 과징금 위험. "
        "대리점이 계약 종료 후 고객 데이터를 경쟁사에 활용하는 위험."
    ),
    why_this_matters=(
        "대리점이 고객 발굴·상담·계약 과정에서 취득한 개인정보는 퍼시스의 데이터이므로 "
        "계약 종료 시 반환·파기 절차가 필수입니다."
    ),
    required_action=(
        "개인정보 처리 위탁 범위 명확화, 안전조치 의무, "
        "계약 종료 후 30일 내 파기·이관 절차 명시를 권장합니다."
    ),
    proposed_clause=(
        "대리점은 본 계약의 이행과 관련하여 취득한 고객 개인정보를 개인정보보호법 §26에 따른 "
        "수탁자로서 처리하며, 공급업자의 지시에 따라서만 처리하고 제3자에게 제공하지 않는다. "
        "본 계약 종료 시 대리점은 보유 중인 고객 개인정보를 30일 이내에 공급업자에게 "
        "이관하거나 복구 불가능한 방법으로 파기하고, 그 결과를 서면으로 통지한다."
    ),
    current_assessment_reflected=(
        "개인정보 처리 위탁 조항 및 계약 종료 후 파기·이관 절차가 명확하게 규정되어 있습니다."
    ),
    current_assessment_partial=(
        "제6조③에서 개인정보 제3자 제공이 언급되어 있으나, "
        "계약 종료 후 개인정보 파기·이관 절차가 명시되어 있지 않습니다. "
        "개인정보보호법 §26에 따른 수탁자 규정 및 파기 절차 추가를 권장합니다."
    ),
    current_assessment_must_fix=(
        "개인정보를 처리하고 있으나 위탁 계약이나 파기 절차가 전혀 없습니다. "
        "즉시 수정이 필요합니다."
    ),
    negotiation_position=(
        "법적 의무 조항으로 협상 불가. 파기 기간(30일)은 협의 가능."
    ),
)

# ─── DLR-RS-009 ───────────────────────────────────────────────────────────────

DLR_RS_009 = DLRSRule(
    rule_id="DLR-RS-009",
    rule_title="공정거래/분쟁조정/보복조치 금지/자료 확인권",
    severity="MEDIUM",
    approval_required=False,
    trigger_keywords=["공정화에 관한 법률", "보복 조치", "분쟁", "관할 법원", "공정거래"],
    trigger_patterns=[
        re.compile(r"(공정거래|공정화).{0,20}(준수|법률)"),
        re.compile(r"보복\s*조치"),
        re.compile(r"분쟁.{0,20}(조정|관할)"),
    ],
    already_reflected_patterns=[
        re.compile(r"대리점거래의\s*공정화에\s*관한\s*법률.{0,20}준수"),
        re.compile(r"보복\s*조치.{0,20}(취할\s*수\s*없다|금지)"),
        re.compile(r"분쟁.{0,20}(관할\s*법원|서울중앙지방법원)"),
    ],
    partial_patterns=[
        re.compile(r"(공정거래|공정화).{0,20}준수"),
        re.compile(r"분쟁.{0,20}(관할|법원|조정)"),
    ],
    critical_issue_patterns=[
        re.compile(r"공급업자.{0,20}(보복|불이익).{0,20}(할\s*수\s*있다|허용)"),
    ],
    issue_title="공정거래/분쟁/보복금지 — 반영됨, 자료 확인권 추가 권장",
    legal_risk=(
        "대리점거래법 §12 불이익 제공 금지, §6 자료 열람권. "
        "자료 확인권 조항이 없으면 대리점이 수수료 산정 근거를 검증할 수 없습니다."
    ),
    business_risk=(
        "분쟁 발생 시 대리점이 수수료 계산 근거를 요구할 법적 근거가 없어 분쟁 장기화."
    ),
    why_this_matters=(
        "대리점거래법 §6에 따라 대리점은 공급업자에게 거래 관련 자료의 열람·확인을 요청할 수 있습니다. "
        "이 권리가 계약서에 명시되면 분쟁 예방과 신뢰 관계 유지에 도움이 됩니다."
    ),
    required_action=(
        "수수료 산정 근거 자료 확인권 조항 추가를 권장합니다(선택적)."
    ),
    proposed_clause=(
        "공급업자는 대리점거래의 공정화에 관한 법률을 준수하며, 대리점의 정당한 이익을 "
        "침해하는 보복 조치를 취할 수 없다. 대리점은 공급업자에게 용역수수료 산정과 관련된 "
        "자료의 열람을 요청할 수 있으며, 공급업자는 정당한 사유 없이 이를 거부할 수 없다. "
        "분쟁은 서울중앙지방법원을 제1심 관할 법원으로 한다."
    ),
    current_assessment_reflected=(
        "제11조에서 대리점거래법 준수, 보복조치 금지, 분쟁 관할 법원이 모두 명시되어 있습니다. "
        "자료 확인권 조항이 추가되면 더욱 완전한 보호가 됩니다."
    ),
    current_assessment_partial=(
        "공정거래 준수 및 보복금지 조항은 있으나, 자료 열람·확인권이 명시되어 있지 않습니다."
    ),
    current_assessment_must_fix=(
        "공정거래 관련 기본 보호 조항이 없습니다."
    ),
    negotiation_position=(
        "공정거래법 기준 조항. 자료 확인권은 협상 대상."
    ),
)


# ─── Exports ─────────────────────────────────────────────────────────────────

DLRS_RULES: list[DLRSRule] = [
    DLR_RS_001, DLR_RS_002, DLR_RS_003, DLR_RS_004,
    DLR_RS_005, DLR_RS_006, DLR_RS_007, DLR_RS_008, DLR_RS_009,
]

DLRS_PRIORITY_ORDER: list[str] = [
    "DLR-RS-006",  # 갱신거절 (대리점법 위반 최고 우선)
    "DLR-RS-004",  # 수수료 차감 절차
    "DLR-RS-001",  # 고객계약 구조 (반영됨이면 제외됨)
    "DLR-RS-002",  # 세금계산서 (반영됨이면 제외됨)
    "DLR-RS-003",  # 미수금 책임
    "DLR-RS-008",  # 개인정보
    "DLR-RS-007",  # A/S 귀책
    "DLR-RS-005",  # 거래보증금
    "DLR-RS-009",  # 공정거래 (반영됨이면 제외됨)
]


def extract_excerpt_rs(text: str, keywords: list, max_len: int = 250) -> str:
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(text), idx + max_len)
            return text[start:end].strip()
    return ""


def run_dlrs_assessment(text: str) -> list[dict]:
    """Run all DLR-RS rules and return findings sorted by priority.

    Returns only rules that are applicable (not ASSESSMENT_NA).
    """
    order = {rid: i for i, rid in enumerate(DLRS_PRIORITY_ORDER)}
    findings = []
    for rule in DLRS_RULES:
        assessment = rule.assess_contract(text)
        if assessment == ASSESSMENT_NA:
            continue
        excerpt = extract_excerpt_rs(text, rule.trigger_keywords)
        finding = rule.to_finding(
            assessment=assessment,
            excerpt=excerpt,
            source_section_type="main_contract",
        )
        findings.append(finding)
    findings.sort(key=lambda f: order.get(f["rule_id"], 999))
    return findings
