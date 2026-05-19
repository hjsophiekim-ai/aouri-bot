"""Structure-specific risk findings for direct_customer_contract_with_dealer_service.

This module detects clause-level mismatches in 위탁판매 대리점 계약 where the supplier
directly contracts with customers but contract language incorrectly attributes
contracting-party duties (invoicing, billing, collection, A/S liability) to the dealer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Re-exported constant so importers can use this module as single source of truth
STRUCTURE_DIRECT_CUSTOMER_KEY = "direct_customer_contract_with_dealer_service"

# ─── Clause identity labels ──────────────────────────────────────────────────
# Used to prevent wrong rewrite templates from being applied.

CI_DEALER_STRUCTURE = "dealer_structure"
CI_PRICE_DEFINITION = "price_definition"
CI_CUSTOMER_CONTRACT = "customer_contract_execution"
CI_INVOICE_BILLING = "invoice_billing"
CI_COLLECTION = "collection_support"
CI_DELIVERY_INSPECTION = "delivery_inspection"
CI_CANCELLATION_RETURN = "cancellation_return"
CI_AFTER_SERVICE = "after_service"
CI_OUTSOURCED_PURCHASE = "outsourced_purchase"
CI_FEE_CALCULATION = "fee_calculation"
CI_INCENTIVE = "incentive"
CI_SETOFF_DEPOSIT = "setoff_deposit"
CI_PROMOTION = "promotion_advertising"
CI_SOFTWARE_FEE = "software_fee"
CI_TRADEMARK_IP = "trademark_ip_use"
CI_RENEWAL_REFUSAL = "renewal_refusal"
CI_TERMINATION = "termination"
CI_CONFIDENTIALITY = "confidentiality"
CI_DISPUTE = "dispute_resolution"
CI_COMPLIANCE = "compliance_general"

# Clause identity → allowed template IDs
_TEMPLATE_APPLICABILITY: dict[str, set[str]] = {
    CI_DEALER_STRUCTURE: {"dealer_structure_rewrite"},
    CI_PRICE_DEFINITION: {"reference_price_rewrite", "contract_price_rewrite"},
    CI_CUSTOMER_CONTRACT: {"customer_contract_support_rewrite"},
    CI_INVOICE_BILLING: {"invoice_billing_rewrite"},
    CI_COLLECTION: {"collection_support_rewrite"},
    CI_CANCELLATION_RETURN: {"cancellation_return_as_rewrite"},
    CI_AFTER_SERVICE: {"cancellation_return_as_rewrite"},
    CI_OUTSOURCED_PURCHASE: {"cancellation_return_as_rewrite"},
    CI_FEE_CALCULATION: {"setoff_due_process_rewrite"},
    CI_INCENTIVE: {"incentive_objective_rewrite"},
    CI_SETOFF_DEPOSIT: {"setoff_due_process_rewrite"},
    CI_PROMOTION: {"promotion_good_faith_rewrite"},
    CI_SOFTWARE_FEE: {"software_fee_rewrite"},
    CI_TRADEMARK_IP: {"trademark_ip_use_rewrite"},
    CI_RENEWAL_REFUSAL: {},  # no template: use 수정 문구 자동생성 보류
    CI_TERMINATION: {},
    CI_CONFIDENTIALITY: {},
    CI_DISPUTE: {},
    CI_COMPLIANCE: {},
}

# Template texts (Korean legal revision language)
_TEMPLATES: dict[str, str] = {
    "dealer_structure_rewrite": (
        "공급업자는 고객과 직접 상품공급계약을 체결하고, 대리점은 공급업자로부터 위탁받은 범위 내에서 "
        "고객 발굴, 상담, 견적·수주 정보 등록, 납품 일정 협의, 검수 지원, 대금청구 및 수금 지원 등 "
        "판매 관련 용역을 수행한다. 대리점은 고객과의 상품공급계약의 당사자가 아니며, 공급업자의 사전 서면 "
        "승인 없이 공급업자를 대리하여 계약을 체결하거나 공급업자 명의의 법률행위를 할 수 없다. "
        "공급업자는 대리점이 본 계약에서 정한 위탁판매 용역을 수행하고 지급요건을 충족한 경우 "
        "본 계약 및 별첨 약정서에서 정한 용역수수료 및 인센티브를 지급한다."
    ),
    "reference_price_rewrite": (
        "'기준단가'란 고객과 공급업자 간 상품공급계약 체결, 견적 승인, 용역수수료·인센티브 산정 및 "
        "내부 정산을 위하여 공급업자가 위탁커넥트플러스에 공지하는 기준가격을 말한다. "
        "기준단가는 대리점의 고객에 대한 최저 판매가격 또는 대리점의 독자적인 판매가격으로 해석되지 아니한다."
    ),
    "contract_price_rewrite": (
        "'계약가'란 고객과 공급업자 간 체결된 상품공급계약에서 고객이 공급업자에게 지급하기로 확정된 "
        "상품대금 또는 공급업자가 위탁커넥트플러스에서 확정한 계약금액을 말한다."
    ),
    "invoice_billing_rewrite": (
        "고객에 대한 세금계산서, 현금영수증 등 증빙 발행 및 상품대금 청구의 법적 주체는 공급업자로 한다. "
        "대리점은 고객의 증빙 발행 및 대금청구에 필요한 정보를 위탁커넥트플러스에 정확히 입력하거나 "
        "공급업자에게 전달하고, 공급업자의 증빙 발행 및 대금청구 업무가 원활히 이루어지도록 협조한다."
    ),
    "customer_contract_support_rewrite": (
        "대리점은 고객과 공급업자 간 상품공급계약 체결을 지원하기 위하여 공급업자가 정한 양식과 절차에 따라 "
        "계약 관련 정보를 위탁커넥트플러스에 등록하고, 고객이 상품공급계약서를 확인·작성할 수 있도록 안내하여야 한다."
    ),
    "collection_support_rewrite": (
        "대리점은 고객의 대금지급 일정, 미지급 사유, 지급 예정일 등 대금 회수에 필요한 정보를 파악하여 "
        "공급업자에게 통지하고, 공급업자의 대금청구 및 회수 업무에 협조한다. "
        "고객이 착오로 대리점에게 상품대금을 입금한 경우, 대리점은 이를 즉시 공급업자에게 통지하고 "
        "공급업자가 지정한 계좌로 지체 없이 송금하여야 한다. "
        "다만 고객의 대금 미지급 자체에 대한 책임은 대리점의 고의 또는 과실, 허위 정보 제공, 중요 사실 미고지, "
        "공급업자의 승인 없는 거래 진행, 고객에 대한 잘못된 계좌 안내 등 대리점의 귀책사유가 있는 경우에 한하여 부담한다."
    ),
    "overbroad_all_liability_rewrite": (
        "대리점의 고의 또는 과실, 허위 정보 제공, 중요 사실 미고지, 공급업자의 사전 승인 없는 거래 진행 또는 "
        "공식 절차 위반으로 인하여 관련 법령 또는 입찰·조달 조건 위반이 발생하고 그로 인해 공급업자에게 손해가 "
        "발생한 경우, 대리점은 자신의 귀책 범위 내에서 그 손해를 배상한다. "
        "다만 공급업자의 지시, 승인, 귀책사유 또는 공급업자가 제공한 정보의 오류로 인한 손해는 제외한다."
    ),
    "cancellation_return_as_rewrite": (
        "고객에 대한 상품의 납품, 하자보수, 취소·반품 및 A/S에 관한 대외적 책임은 고객과 상품공급계약을 체결한 "
        "공급업자가 부담한다. 대리점은 공급업자의 기준과 절차에 따라 고객 안내 및 접수 업무를 지원한다. "
        "다만 대리점의 고의 또는 과실, 고객에 대한 잘못된 안내, 주문정보 오입력, 공급업자의 사전 승인 없는 "
        "조건 약속, 납품정보 미통지 등 대리점의 귀책사유로 추가 비용 또는 손해가 발생한 경우 공급업자는 "
        "그 귀책 범위 내에서 대리점에게 구상 또는 비용상환을 청구할 수 있다."
    ),
    "setoff_due_process_rewrite": (
        "공급업자는 대리점의 귀책사유로 발생한 비용 또는 손해배상채권이 객관적 자료에 의해 확인되는 경우, "
        "상계 또는 차감 예정 금액, 산정근거, 증빙자료 및 상계 예정일을 대리점에게 사전 통지한 후 "
        "대리점에게 지급할 용역수수료, 인센티브, 정책지원금 또는 거래보증금과 상계할 수 있다. "
        "대리점이 통지일로부터 7영업일 이내에 합리적인 근거를 들어 이의를 제기한 경우, "
        "당사자는 해당 금액의 확정 여부에 관하여 성실히 협의한다."
    ),
    "annex_priority_rewrite": (
        "본 약정은 본 계약의 부속문서로서 본 계약과 일체를 이룬다. "
        "본 계약과 본 약정이 상충하는 경우 본 계약을 우선 적용한다. "
        "다만 본 계약에서 본 약정으로 명시적으로 위임한 사항 또는 본 계약의 내용을 구체화하는 사항에 한하여 "
        "본 약정에서 정한 바를 따른다."
    ),
    "incentive_objective_rewrite": (
        "공급업자는 대리점이 본 조에서 정한 지급요건을 충족한 경우 본 조에서 정한 기준에 따라 인센티브를 지급한다. "
        "인센티브 지급 여부 및 금액은 공급업자의 전산망 정보, 검수마스터 마감자료, 사업자등록번호, "
        "최근 거래이력, NICE 기업규모 분류 등 객관적 자료를 기준으로 산정한다."
    ),
    "promotion_good_faith_rewrite": (
        "공급업자는 대리점의 상품 판매 촉진 및 브랜드 이미지 관리를 위하여 다음 각 호의 사항에 관하여 "
        "대리점에게 협의를 요청할 수 있으며, 대리점은 정당한 사유가 없는 한 성실히 협의한다. "
        "비용 부담이 발생하는 사항은 본 계약, 본 약정 또는 당사자 간 사전 서면 합의에 따른다."
    ),
    "software_fee_rewrite": (
        "일부 선택형 프로그램의 경우 별도 사용료가 발생할 수 있으며, 공급업자는 사용료, 과금 기준, "
        "사용기간 및 해지 방법을 사전에 대리점에게 고지한다. "
        "대리점이 해당 프로그램 사용에 명시적으로 동의한 경우에 한하여 사용료를 부담하며, "
        "공급업자는 대리점에게 지급할 용역수수료에서 해당 사용료를 공제할 수 있다. "
        "위탁판매 업무 수행에 필수적인 기본 시스템의 사용료는 별도 합의가 없는 한 공급업자가 부담한다."
    ),
    "trademark_ip_use_rewrite": (
        "대리점은 공급업자의 상호, 상표, 저작물, 디자인, 제품 이미지, 영업자료 등 지식재산권을 "
        "공급업자의 사전 서면 승인 및 승인된 사용범위를 벗어나 사용할 수 없다. "
        "대리점이 이를 위반한 경우 공급업자는 사용중지, 시정요구, 관련 자료의 폐기 또는 회수, "
        "손해배상을 청구할 수 있으며, 위반의 중대성, 반복성 및 시정 여부를 고려하여 계약해지 또는 갱신거절을 할 수 있다."
    ),
}


# ─── Finding dataclass ───────────────────────────────────────────────────────

@dataclass
class StructureFinding:
    finding_id: str
    clause_identity: str
    risk_category: str
    severity: str          # "HIGH" or "MEDIUM"
    issue_title: str
    risk_description: str
    why_matters: str
    worst_case_scenario: str
    supplier_strategy: str
    suggested_rewrite: str
    original_excerpt: str
    is_structure_mismatch: bool
    confidence: float
    template_id: str
    template_applicability_check: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "clause_identity": self.clause_identity,
            "risk_category": self.risk_category,
            "severity": self.severity,
            "issue_title": self.issue_title,
            "risk_description": self.risk_description,
            "why_matters": self.why_matters,
            "worst_case_scenario": self.worst_case_scenario,
            "supplier_strategy": self.supplier_strategy,
            "suggested_rewrite": self.suggested_rewrite,
            "original_excerpt": self.original_excerpt,
            "is_structure_mismatch": self.is_structure_mismatch,
            "confidence": self.confidence,
            "template_id": self.template_id,
            "template_applicability_check": self.template_applicability_check,
        }


# ─── Clause identity classifier ──────────────────────────────────────────────

def classify_clause_identity(*, title: str, text: str) -> str:
    """Classify a clause into a dealer-direct structure identity label."""
    hay = ((title or "") + "\n" + (text or "")).lower()

    def has(*needles: str) -> bool:
        return any(n.lower() in hay for n in needles)

    # Order matters: more specific first
    if has("위탁판매", "거래형태", "거래 형태", "위탁받은 상품") and has("최종소비자", "판매하고", "판매위탁"):
        return CI_DEALER_STRUCTURE
    if has("기준단가", "계약가", "할인율", "최저가격", "제안 가능한 최저"):
        return CI_PRICE_DEFINITION
    if has("세금계산서", "현금영수증", "대금의 청구", "대금청구", "청구 등을 할 수"):
        return CI_INVOICE_BILLING
    if has("상품공급계약서를 작성", "고객과 계약 시", "고객과의 계약") and has("수금", "대금"):
        return CI_CUSTOMER_CONTRACT
    if has("수금", "대금 수금", "대금지급", "미수금"):
        return CI_COLLECTION
    if has("검수", "납품", "배송", "배달"):
        return CI_DELIVERY_INSPECTION
    if has("반품", "취소", "교환") and not has("수금"):
        return CI_CANCELLATION_RETURN
    if has("a/s", "as", "하자보수", "애프터서비스") and not has("세금계산서"):
        return CI_AFTER_SERVICE
    if has("외주매입", "외주 매입", "외부 매입"):
        return CI_OUTSOURCED_PURCHASE
    if has("용역수수료", "수수료 산정", "수수료 계산", "기본수수료", "추가수수료"):
        return CI_FEE_CALCULATION
    if has("인센티브", "성과급", "장려금"):
        return CI_INCENTIVE
    if has("상계", "차감", "거래보증금", "보증금"):
        return CI_SETOFF_DEPOSIT
    if has("판매촉진", "광고", "홍보", "시설 개선", "판촉"):
        return CI_PROMOTION
    if has("소프트웨어", "s/w", "sw 사용료", "프로그램 사용료", "별도 비용", "월별 용역수수료에서 차감"):
        return CI_SOFTWARE_FEE
    if has("상표", "지식재산", "저작물", "상호", "로고") and has("사용", "사용할 수 없", "승인"):
        return CI_TRADEMARK_IP
    if has("갱신거절", "갱신 거절", "갱신 거부"):
        return CI_RENEWAL_REFUSAL
    if has("해지", "계약해지", "종료", "중도해지"):
        return CI_TERMINATION
    if has("비밀유지", "비밀", "기밀", "confidential"):
        return CI_CONFIDENTIALITY
    if has("관할", "준거법", "분쟁해결", "중재"):
        return CI_DISPUTE
    if has("준수", "법령", "공정거래", "금품", "향응", "동반성장"):
        return CI_COMPLIANCE

    return CI_COMPLIANCE  # default


# ─── Rewrite lookup ──────────────────────────────────────────────────────────

def get_rewrite_for_identity(clause_identity: str, template_id: str) -> str:
    allowed = _TEMPLATE_APPLICABILITY.get(clause_identity, set())
    if template_id not in allowed:
        return "수정 문구 자동생성 보류: 조항 정체성/거래구조 확인 필요"
    return _TEMPLATES.get(template_id, "수정 문구 자동생성 보류: 조항 정체성/거래구조 확인 필요")


def get_template_applicability_result(clause_identity: str, template_id: str) -> str:
    allowed = _TEMPLATE_APPLICABILITY.get(clause_identity, set())
    if template_id in allowed:
        return f"PASS: clause_identity={clause_identity}, template_id={template_id} is applicable"
    return (
        f"BLOCKED: template_id={template_id} is not applicable to clause_identity={clause_identity}. "
        f"Allowed templates: {sorted(allowed) or '(none)'}"
    )


# ─── Detection rules ─────────────────────────────────────────────────────────

@dataclass
class _DetectionRule:
    finding_id: str
    clause_identity: str
    risk_category: str
    severity: str
    issue_title: str
    trigger_patterns: list[str]   # ANY match → trigger
    required_patterns: list[str]  # ALL must match (if non-empty)
    risk_description: str
    why_matters: str
    worst_case: str
    strategy: str
    template_id: str
    is_structure_mismatch: bool
    confidence_base: float = 0.9


_DETECTION_RULES: list[_DetectionRule] = [
    _DetectionRule(
        finding_id="DD-001",
        clause_identity=CI_DEALER_STRUCTURE,
        risk_category="거래형태 mismatch",
        severity="HIGH",
        issue_title="거래형태 조항: 대리점이 최종소비자에게 직접 판매하는 것처럼 기술",
        trigger_patterns=[
            r"대리점은\s*공급업자로부터\s*위탁받은\s*상품을\s*최종소비자에게\s*판매",
            r"대리점은\s*고객에게\s*판매",
            r"위탁받은\s*상품을\s*최종소비자에게\s*판매",
        ],
        required_patterns=[],
        risk_description=(
            "거래형태 조항이 대리점을 최종소비자에 대한 판매자로 기술하고 있어 "
            "실제 고객·공급업자 직접계약 구조와 불일치합니다."
        ),
        why_matters=(
            "계약당사자 오기재로 인해 세금계산서 발행 주체, 대금청구 주체, A/S 책임 주체, "
            "소비자보호법상 책임 귀속이 모두 대리점으로 오해될 수 있습니다. "
            "분쟁 시 대리점이 소비자에 대한 직접 계약당사자 책임을 부담할 위험이 있습니다."
        ),
        worst_case=(
            "고객이 대리점을 계약당사자로 인식하여 제품 하자, A/S, 환불을 대리점에 직접 청구 → "
            "대리점이 모든 고객 클레임을 직접 처리해야 하는 상황 발생. "
            "공정거래위원회 조사 시 공급업자의 위탁판매 구조가 실질적 직접판매(귀책전가)로 판정될 위험."
        ),
        strategy=(
            "공급업자가 고객과 직접 상품공급계약을 체결함을 명확히 기재하고, "
            "대리점은 위탁판매 용역(고객발굴, 수주등록, 납품지원, 수금지원 등) 수행자임을 명시. "
            "대리점이 공급업자를 대리하여 계약을 체결할 수 없음을 추가."
        ),
        template_id="dealer_structure_rewrite",
        is_structure_mismatch=True,
    ),
    _DetectionRule(
        finding_id="DD-002",
        clause_identity=CI_PRICE_DEFINITION,
        risk_category="기준단가/최저가격 구조 오류",
        severity="HIGH",
        issue_title="기준단가 정의: 대리점의 최저 판매가격으로 정의하여 구조 부정확",
        trigger_patterns=[
            r"기준단가란\s*대리점이\s*자율적으로\s*제안\s*가능한\s*최저가격",
            r"대리점이\s*자율적으로\s*공급업자\s*상품에\s*대하여\s*제안\s*가능한\s*최저가격",
            r"최저\s*제안가",
        ],
        required_patterns=[],
        risk_description=(
            "기준단가를 '대리점이 제안 가능한 최저가격'으로 정의하여 대리점이 판매자인 것처럼 표현합니다. "
            "실제 구조에서 기준단가는 공급업자-고객 간 계약가격 결정 및 수수료 산정 기준입니다."
        ),
        why_matters=(
            "기준단가를 대리점의 최저 판매가격으로 표현하면 공정거래법상 "
            "재판매가격유지행위(재판매가 지정)와 유사한 리스크가 발생합니다. "
            "또한 대리점 구조를 오기재하여 세금계산서·청구 주체 혼란을 야기합니다."
        ),
        worst_case=(
            "공정위가 기준단가를 재판매가격 하한 통제로 판단할 경우 대리점거래법·공정거래법 위반 → "
            "과징금 + 시정명령. 공급업자가 대리점의 고객 제안가를 통제한 것으로 판정될 위험."
        ),
        strategy=(
            "기준단가를 '공급업자-고객 간 계약가격 기준, 견적 승인 기준, "
            "수수료 산정 기준'으로 재정의. '대리점 최저 판매가격'이라는 표현 삭제."
        ),
        template_id="reference_price_rewrite",
        is_structure_mismatch=True,
    ),
    _DetectionRule(
        finding_id="DD-003",
        clause_identity=CI_INVOICE_BILLING,
        risk_category="세금계산서/대금청구 주체 mismatch",
        severity="HIGH",
        issue_title="세금계산서 발행·대금청구 주체: 대리점이 법적 발행주체로 기술",
        trigger_patterns=[
            r"대리점은\s*고객에게\s*세금계산서",
            r"세금계산서\s*발행\s*및\s*대금의?\s*청구",
            r"대리점은\s*고객에게.*세금계산서.*현금영수증.*법률상\s*의무",
            r"대리점은.*각종\s*법률이\s*규정하고\s*있는\s*의무를\s*수행",
        ],
        required_patterns=[],
        risk_description=(
            "세금계산서 발행 및 대금청구 의무를 대리점에게 부과하고 있습니다. "
            "공급업자가 고객과 직접 계약을 체결하는 구조에서는 공급업자가 법적 발행주체여야 합니다."
        ),
        why_matters=(
            "부가가치세법상 세금계산서는 공급자가 발행해야 합니다. "
            "대리점이 발행하면 명의 불일치로 세무 리스크가 발생하고, "
            "고객은 공급업자와의 계약인데 대리점 명의 세금계산서를 받게 되어 혼란이 생깁니다."
        ),
        worst_case=(
            "세금계산서 명의 불일치로 고객의 매입세액공제 불인정 → 고객이 대리점/공급업자에게 손해배상 청구. "
            "국세청 조사 시 대리점이 공급자로 지정되어 부가세 납부 의무 발생."
        ),
        strategy=(
            "공급업자를 법적 세금계산서 발행 주체 및 대금청구 주체로 명시. "
            "대리점은 관련 정보 입력·전달 지원 역할로 재정의."
        ),
        template_id="invoice_billing_rewrite",
        is_structure_mismatch=True,
    ),
    _DetectionRule(
        finding_id="DD-004",
        clause_identity=CI_CUSTOMER_CONTRACT,
        risk_category="고객계약 당사자 mismatch",
        severity="HIGH",
        issue_title="대리점이 고객과 직접 계약 체결·수금 수행 주체로 기술",
        trigger_patterns=[
            r"대리점은\s*고객과\s*계약\s*시\s*필수적으로\s*상품공급계약서를\s*작성",
            r"대리점은\s*고객과\s*계약\s*시",
            r"대리점은\s*고객과\s*상품공급계약서를\s*작성",
        ],
        required_patterns=[],
        risk_description=(
            "대리점이 고객과 직접 상품공급계약서를 작성하는 계약당사자로 기술되어 있습니다. "
            "공급업자가 고객과 직접 계약하는 구조에서는 대리점은 계약 지원자여야 합니다."
        ),
        why_matters=(
            "대리점이 계약당사자로 표현될 경우 소비자 보호 의무, 결함제품 책임, "
            "계약 불이행 책임이 모두 대리점에게 귀속될 수 있습니다."
        ),
        worst_case=(
            "고객이 제품 하자나 납기 지연으로 대리점을 계약당사자로 지목하여 손해배상 소송 제기 → "
            "대리점이 공급업자의 제품 결함에 대한 1차 책임을 부담하는 상황."
        ),
        strategy=(
            "대리점이 '공급업자가 정한 양식과 절차에 따라 계약 정보를 등록하고 "
            "고객을 안내하는 역할'로 재정의. 계약서 작성의 법적 당사자는 공급업자임을 명시."
        ),
        template_id="customer_contract_support_rewrite",
        is_structure_mismatch=True,
    ),
    _DetectionRule(
        finding_id="DD-005",
        clause_identity=CI_COLLECTION,
        risk_category="대금수금 책임 mismatch",
        severity="HIGH",
        issue_title="대금 수금 책임을 대리점에게 부과 (고객 미지급 리스크 전가)",
        trigger_patterns=[
            r"대리점은.*대금\s*수금\s*업무를\s*성실히\s*수행하여야",
            r"수금\s*업무를\s*성실히\s*수행",
            r"대금수금의?\s*책임",
            r"수요자의\s*대금지급이\s*이루어질\s*수\s*있도록",
        ],
        required_patterns=[],
        risk_description=(
            "대금 수금 책임을 대리점에게 부과하여 고객 미지급 리스크가 대리점에게 이전될 수 있습니다."
        ),
        why_matters=(
            "공급업자-고객 직접계약 구조에서 고객의 대금 미지급은 원칙적으로 공급업자의 위험입니다. "
            "대리점에게 수금 '책임'을 부과하면 대리점이 고객 미지급 전액을 부담할 수 있습니다."
        ),
        worst_case=(
            "고객이 경영난으로 대금 미지급 → 대리점이 공급업자에게 대금 전액 부담 요구 받는 상황. "
            "대리점법 제6조 불이익 제공 금지 위반 가능성."
        ),
        strategy=(
            "대리점의 역할을 '수금 지원 및 정보 제공'으로 한정. "
            "대리점 귀책사유(허위 정보 제공, 무단 계좌 안내 등)에 한해서만 책임을 부담하도록 제한."
        ),
        template_id="collection_support_rewrite",
        is_structure_mismatch=True,
    ),
    _DetectionRule(
        finding_id="DD-006",
        clause_identity=CI_COMPLIANCE,
        risk_category="모든 책임 과도한 귀책 전가",
        severity="HIGH",
        issue_title="법령 위반 관련 '모든 책임'을 대리점에 부과",
        trigger_patterns=[
            r"모든\s*책임은\s*대리점에게\s*있다",
            r"일체\s*책임",
            r"전부\s*책임",
            r"모든\s*책임은?\s*(을|대리점)",
        ],
        required_patterns=[],
        risk_description=(
            "'모든 책임'을 대리점에게 부과하는 조항은 과도한 귀책 전가로 대리점법상 불이익 제공에 해당할 수 있습니다."
        ),
        why_matters=(
            "공급업자의 지시·시스템 오류·정보 제공 오류로 인한 문제까지 대리점이 부담하게 됩니다. "
            "대리점법 제6조 불이익 제공 금지 위반 가능성이 있습니다."
        ),
        worst_case=(
            "공급업자 시스템 오류로 발생한 입찰 조건 위반 → 대리점이 모든 손해(입찰 박탈, 과징금 등) 부담. "
            "공정거래위원회 분쟁조정 또는 조사 시 공급업자의 불공정 거래행위로 판정."
        ),
        strategy=(
            "책임 범위를 대리점의 귀책사유(고의·과실, 허위 정보, 절차 위반)로 한정. "
            "공급업자 귀책사유 또는 공급업자 지시로 인한 손해는 명시적으로 제외."
        ),
        template_id="overbroad_all_liability_rewrite",
        is_structure_mismatch=False,
    ),
    _DetectionRule(
        finding_id="DD-007",
        clause_identity=CI_TRADEMARK_IP,
        risk_category="IP/상표 조항 갱신거절 연계",
        severity="MEDIUM",
        issue_title="IP 사용제한 조항에 갱신거절 사유 포함 — 비례성 검토 필요",
        trigger_patterns=[
            r"공급업자의\s*사전\s*승인없이.*상호.*상표.*저작물.*지식재산권.*사용할\s*수\s*없다",
            r"사전\s*승인\s*없이.*상호.*상표.*사용할\s*수\s*없다",
        ],
        required_patterns=[],
        risk_description=(
            "IP 사용제한 조항이 갱신거절 사유와 연결될 경우 비례성 검토가 필요합니다. "
            "단순 실수나 경미한 위반에도 갱신거절로 이어질 수 있습니다."
        ),
        why_matters=(
            "갱신거절은 대리점의 영업 기반을 상실하게 하는 중대한 불이익입니다. "
            "IP 위반의 중대성·반복성·시정 여부를 고려하지 않은 갱신거절은 불공정할 수 있습니다."
        ),
        worst_case=(
            "대리점이 온라인 홍보물에 로고를 일부 수정하여 사용 → 공급업자가 이를 근거로 갱신거절 → "
            "대리점이 수년간의 고객 관계와 영업 기반을 상실."
        ),
        strategy=(
            "IP 사용 위반에 대한 시정 기회 부여 절차와 갱신거절 시 비례성 판단 기준을 추가. "
            "경미한 위반과 중대한 위반을 구분하여 단계적 제재 구조로 수정."
        ),
        template_id="trademark_ip_use_rewrite",
        is_structure_mismatch=False,
    ),
    _DetectionRule(
        finding_id="DD-008",
        clause_identity=CI_SETOFF_DEPOSIT,
        risk_category="상계/차감 절차 불명확",
        severity="MEDIUM",
        issue_title="용역수수료·보증금 상계·차감 — 사전 통지 및 이의 절차 부재",
        trigger_patterns=[
            r"용역수수료에서\s*차감",
            r"거래보증금에서\s*상계",
            r"정책지원금에서\s*상계",
            r"용역수수료.*차감",
            r"보증금.*상계",
        ],
        required_patterns=[],
        risk_description=(
            "수수료 차감 또는 보증금 상계 조항에 사전 통지, 산정근거, 증빙, 이의기간이 명시되지 않아 "
            "공급업자가 일방적으로 공제를 실행할 수 있습니다."
        ),
        why_matters=(
            "사전 통지 없이 수수료가 자동 차감되면 대리점은 차감 사실을 사후에만 알 수 있어 "
            "이의제기 기회를 잃게 됩니다. 대리점법 제6조 불이익 제공 금지 위반 가능성."
        ),
        worst_case=(
            "공급업자가 근거 불명확한 손해배상 채권으로 수수료를 일방 차감 → "
            "대리점이 운영 자금 부족으로 영업 중단. 분쟁 시 입증 책임 불리."
        ),
        strategy=(
            "상계 전 서면 사전 통지(예정 금액·산정근거·증빙·예정일), "
            "이의제기 기간(7영업일), 확정된 채권에 한한 상계 요건을 명시."
        ),
        template_id="setoff_due_process_rewrite",
        is_structure_mismatch=False,
    ),
    _DetectionRule(
        finding_id="DD-009",
        clause_identity=CI_FEE_CALCULATION,
        risk_category="인센티브 지급기준 모호",
        severity="MEDIUM",
        issue_title="인센티브: '시혜적 혜택' 또는 '공급자 최종 판단' 표현으로 분쟁 위험",
        trigger_patterns=[
            r"시혜적\s*혜택",
            r"최종\s*판단은\s*공급(?:자|업자)의\s*판단",
            r"공급(?:자|업자)의?\s*재량",
        ],
        required_patterns=[],
        risk_description=(
            "인센티브 지급을 공급업자의 '시혜적 혜택' 또는 '최종 판단'으로 표현하여 "
            "지급 의무가 불명확합니다."
        ),
        why_matters=(
            "지급 요건을 충족해도 공급업자가 시혜적 판단으로 거부할 수 있어 "
            "대리점 수입의 예측 가능성이 없어집니다."
        ),
        worst_case=(
            "대리점이 목표를 달성했음에도 공급업자의 '재량' 주장으로 인센티브 미지급 → "
            "대리점이 법적 청구를 할 수 없는 상황."
        ),
        strategy=(
            "객관적 지급 요건 충족 시 지급 의무를 명확히. "
            "지급 여부 판단은 객관적 데이터(검수마스터 자료, 전산 정보 등) 기준으로만 가능하도록 수정."
        ),
        template_id="incentive_objective_rewrite",
        is_structure_mismatch=False,
    ),
    _DetectionRule(
        finding_id="DD-010",
        clause_identity=CI_COMPLIANCE,
        risk_category="부속약정 우선 순서 모순",
        severity="HIGH",
        issue_title="약정 우선순위 조항 상충 — 해석 불확실성",
        trigger_patterns=[
            r"약정이\s*우선적용",
            r"본\s*약정이\s*우선",
        ],
        required_patterns=[
            r"본\s*계약을\s*우선\s*적용",
        ],
        risk_description=(
            "같은 계약에서 '약정이 우선적용'과 '본 계약을 우선 적용'이 모두 존재하여 "
            "직접적인 해석 모순이 발생합니다."
        ),
        why_matters=(
            "공급업자에게 불리한 약정 조항 vs 본 계약 조항 간 충돌 시 어느 것이 우선하는지 불명확. "
            "소송 시 법원이 약정 우선을 인정하면 본 계약의 공정거래 보호 조항이 무력화됩니다."
        ),
        worst_case=(
            "공급업자가 약정서를 통해 본 계약의 대리점법 보호 조항을 무력화 → "
            "대리점이 법적 보호를 받지 못하는 상황."
        ),
        strategy=(
            "본 계약 우선 원칙을 명확히 하고, 약정은 본 계약에서 위임한 사항만 구체화하는 것으로 한정. "
            "대리점법상 강행 규정은 어떤 약정으로도 배제할 수 없음을 명시."
        ),
        template_id="annex_priority_rewrite",
        is_structure_mismatch=False,
    ),
]


# ─── False-positive suppression ─────────────────────────────────────────────

_FP_COMPLIANCE_PATTERNS = [
    re.compile(r"금품.*향응.*편의.*접대"),
    re.compile(r"향응.*편의.*제공해서는\s*아니"),
    re.compile(r"거래상\s*우월적\s*지위를\s*남용하지\s*않"),
    re.compile(r"동반성장을\s*위하여\s*지원프로그램"),
    re.compile(r"교육을\s*실시할\s*수\s*있다"),
    re.compile(r"불공정거래행위를\s*하지\s*아니"),
    re.compile(r"위법하거나\s*부당한\s*행위를\s*하지\s*아니"),
]

_FP_COST_ACTUAL_MARKERS = [
    r"부담하여야",
    r"부담한다",
    r"차감",
    r"상계",
    r"전가",
    r"청구한다",
    r"비용을\s*부담",
    r"원상회복",
]


def is_false_positive_compliance(text: str, rule_id: str) -> bool:
    """Return True if the clause is a harmless compliance clause that should NOT be flagged."""
    if rule_id not in ("RISK-006", "ACT-009"):
        return False
    t = text or ""
    for pat in _FP_COMPLIANCE_PATTERNS:
        if pat.search(t):
            # Only suppress if there are no actual cost/payment markers
            has_actual_cost = any(
                re.search(m, t) for m in _FP_COST_ACTUAL_MARKERS
            )
            if not has_actual_cost:
                return True
    return False


# ─── Main analysis function ───────────────────────────────────────────────────

def analyze_clause_for_structure_findings(
    *,
    clause_title: str,
    clause_text: str,
    clause_id: str = "",
) -> list[StructureFinding]:
    """Analyze a single clause and return any structure-specific findings."""
    findings: list[StructureFinding] = []
    identity = classify_clause_identity(title=clause_title, text=clause_text)
    combined = (clause_title or "") + "\n" + (clause_text or "")

    for rule in _DETECTION_RULES:
        # Check trigger patterns (any match)
        triggered = False
        matched_excerpt = ""
        for pat_str in rule.trigger_patterns:
            m = re.search(pat_str, combined)
            if m:
                triggered = True
                matched_excerpt = m.group(0)[:200]
                break

        if not triggered:
            continue

        # Check required patterns (all must match)
        if rule.required_patterns:
            all_required = all(
                re.search(rp, combined) for rp in rule.required_patterns
            )
            if not all_required:
                continue

        # Get rewrite
        rewrite = get_rewrite_for_identity(identity, rule.template_id)
        # Fallback: if identity doesn't match but we have a template, use it directly
        # (identity misclassification should not prevent the correct rewrite)
        if rewrite == "수정 문구 자동생성 보류: 조항 정체성/거래구조 확인 필요":
            direct_template = _TEMPLATES.get(rule.template_id)
            if direct_template:
                rewrite = direct_template

        applicability = get_template_applicability_result(identity, rule.template_id)

        findings.append(StructureFinding(
            finding_id=f"{rule.finding_id}-{clause_id}" if clause_id else rule.finding_id,
            clause_identity=identity,
            risk_category=rule.risk_category,
            severity=rule.severity,
            issue_title=rule.issue_title,
            risk_description=rule.risk_description,
            why_matters=rule.why_matters,
            worst_case_scenario=rule.worst_case,
            supplier_strategy=rule.strategy,
            suggested_rewrite=rewrite,
            original_excerpt=matched_excerpt,
            is_structure_mismatch=rule.is_structure_mismatch,
            confidence=rule.confidence_base,
            template_id=rule.template_id,
            template_applicability_check=applicability,
        ))

    return findings


def generate_structure_diagnosis_section(
    structure_result: "ContractStructureResult",  # type: ignore[name-defined]
) -> dict[str, Any]:
    """Generate the '거래구조 진단' section for the report."""
    return {
        "section": "0) 거래구조 진단",
        "contract_type": structure_result.contract_type,
        "contract_structure": structure_result.contract_structure,
        "structure_confidence": structure_result.structure_confidence,
        "detected_structure_signals": structure_result.detected_structure_signals,
        "our_side_role": structure_result.our_side_role,
        "customer_contract_party": structure_result.customer_contract_party,
        "dealer_role": structure_result.dealer_role,
        "fee_model": structure_result.fee_model,
        "primary_review_lens": structure_result.primary_review_lens,
    }
