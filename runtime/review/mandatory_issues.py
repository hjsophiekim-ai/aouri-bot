"""Mandatory issue injection for specific contract patterns.

For 위탁판매 대리점 (consignment_sales_agency) contracts, certain clause patterns
MUST generate specific HIGH/MEDIUM issues with pre-written revision text —
regardless of AI analysis results.

This is the authoritative source of truth for the 5 core issues in OPC퍼시스
위탁판매 대리점 계약:
  1. 제5조 제1항 — 거래구조 불일치 [HIGH]
  2. 제5조의2/제6조 제2항 — 세금계산서·대금청구 주체 불명확 [HIGH]
  3. 제6조 제6항/제6조 제12항 — 고객계약서 작성·수금 주체 불명확 [HIGH]
  4. 제6조 제13항 — 법령 위반 책임 전부 전가 [HIGH]
  5. 제16조/제25조 제6항 — 상계 절차 미비 [MEDIUM/HIGH]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ─── Pre-written revision texts ───────────────────────────────────────────────

_REVISION_ART5_1 = (
    "공급업자는 고객과 직접 상품공급계약을 체결하고, 대리점은 공급업자로부터 위탁받은 범위 내에서 "
    "고객 발굴, 상담, 견적·수주 정보 등록, 납품 일정 협의, 검수 지원, 대금청구 및 수금 지원 등 "
    "판매 관련 용역을 수행한다. 대리점은 고객과의 상품공급계약의 당사자가 아니며, 공급업자의 사전 서면 "
    "승인 없이 공급업자를 대리하여 계약을 체결하거나 공급업자 명의의 법률행위를 할 수 없다. "
    "공급업자는 대리점이 본 계약에서 정한 위탁판매 용역을 수행하고 지급요건을 충족한 경우 "
    "본 계약 및 별첨 약정서에서 정한 용역수수료를 지급한다."
)

_REVISION_INVOICE = (
    "대리점은 고객에 대한 세금계산서, 현금영수증, 대금청구와 관련하여 공급업자가 정한 절차에 따라 "
    "필요한 자료의 등록, 전달, 고객 안내 및 발행·청구 지원 업무를 수행한다. "
    "다만 고객과의 상품공급계약, 세금계산서 또는 현금영수증 발행, 대금청구의 법적 주체는 "
    "고객과 직접 계약을 체결하는 공급업자로 하며, 대리점은 공급업자의 사전 서면 승인 없이 "
    "공급업자를 대리하여 위 법률행위를 할 수 없다."
)

_REVISION_COLLECTION = (
    "대리점은 공급업자가 고객과 상품공급계약을 체결하고 대금을 청구·수령하는 데 필요한 "
    "계약정보 입력, 상품공급계약서 작성 지원, 고객 안내, 검수 확인, 미수 사유 및 수금 예정일 확인 등 "
    "지원 업무를 성실히 수행한다. 대리점은 고객으로부터 상품대금을 직접 수령하여서는 아니 되며, "
    "고객이 착오로 대리점에게 대금을 입금한 경우 대리점은 이를 즉시 공급업자에게 통지하고 "
    "해당 금액 전액을 지체 없이 공급업자에게 이전하여야 한다."
)

_REVISION_ALL_LIABILITY = (
    "대리점의 고의 또는 과실, 허위 정보 제공, 중요 사실 미고지, 공급업자의 사전 승인 없는 거래 진행 "
    "또는 공급업자가 정한 공식 절차 위반으로 인하여 관련 법령 또는 입찰·조달 조건 위반이 발생하고 "
    "그로 인해 공급업자에게 손해가 발생한 경우, 대리점은 자신의 귀책 범위 내에서 그 손해를 배상한다. "
    "다만 공급업자의 지시, 승인, 귀책사유, 시스템 오류 또는 공급업자가 제공한 정보의 오류로 "
    "인한 손해는 제외한다."
)

_REVISION_SETOFF = (
    "공급업자는 대리점에게 비용을 청구하거나 용역수수료, 정책지원금 또는 거래보증금에서 상계하려는 경우, "
    "해당 비용의 발생 사유, 귀책 주체, 산정내역, 증빙자료 및 상계 예정일을 사전에 대리점에게 "
    "통지하여야 한다. 대리점이 통지를 받은 날부터 [10]영업일 이내 이의를 제기한 금액에 대해서는 "
    "당사자 간 협의 또는 객관적 자료에 의해 금액이 확정되기 전까지 임의로 상계하지 않는다. "
    "다만 대리점이 서면 또는 위탁커넥트플러스 등 시스템상 명시적으로 부담에 동의한 금액 "
    "또는 다툼 없는 금액은 상계할 수 있다."
)

_REVISION_IP_TRADEMARK = (
    "대리점이 본 조 제1항 내지 제3항을 위반한 경우, 공급업자는 위반 내용 및 근거자료를 제시하여 "
    "대리점에게 소명을 요구할 수 있다. 대리점이 합리적인 기간 내에 정당한 사유를 소명하지 못하거나, "
    "위반행위가 경미하고 시정 가능한 경우 공급업자는 상당한 기간을 정하여 시정을 요구할 수 있다. "
    "대리점이 정당한 사유 없이 시정요구를 이행하지 않거나, 위반행위가 반복적이거나 중대하여 "
    "공급업자의 상표, 상호, 브랜드 이미지 또는 고객 신뢰에 중대한 손해를 초래한 경우에 한하여 "
    "공급업자는 계약기간 종료 후 대리점의 계약 갱신 요구를 거절할 수 있다."
)

_NEGOTIATION_SUPPLIER_FORM = (
    "당사 양식이므로 공정거래 리스크 예방 및 계약구조 명확화를 위해 선제 반영 권고"
)
_NEGOTIATION_COUNTERPARTY_FORM = (
    "상대방 반발 가능성이 있으나 법적 책임 범위 및 정산 절차 명확화 차원에서 협상 필요"
)
_NEGOTIATION_DEFAULT = (
    "계약구조 명확화 및 분쟁 예방 목적의 수정으로 제안 가능"
)


@dataclass
class MandatoryIssue:
    """A pre-written mandatory issue for specific contract patterns."""
    issue_id: str
    clause_title: str
    severity: str  # "HIGH" or "MEDIUM"
    approval_required: bool
    issue_title: str
    problem: str
    legal_business_reason: str
    proposed_revision: str
    negotiation_position: str
    related_clauses: list[str]
    confidence: float = 0.95
    # Detection: any of these patterns in combined text → trigger
    trigger_patterns: list[re.Pattern[str]] = field(default_factory=list)
    # Additional context for clause matching
    clause_hints: list[str] = field(default_factory=list)
    # trigger_pattern: convenience string representation for the primary trigger
    trigger_pattern: str = ""

    @property
    def issue_code(self) -> str:
        """Alias for issue_id — used in tests and reporting."""
        return self.issue_id

    def to_issue_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "clause_id": self.issue_id,
            "clause_title": self.clause_title,
            "severity": self.severity,
            "approval_required": self.approval_required,
            "issue_title": self.issue_title,
            "original_text": "",  # will be filled from matched clause text
            "problem": self.problem,
            "legal_business_reason": self.legal_business_reason,
            "proposed_revision": self.proposed_revision,
            "negotiation_position": self.negotiation_position,
            "related_clauses": list(self.related_clauses),
            "confidence": self.confidence,
            "is_mandatory": True,
        }


# ─── Mandatory issue definitions ──────────────────────────────────────────────

MANDATORY_CONSIGNMENT_ISSUES: list[MandatoryIssue] = [
    MandatoryIssue(
        issue_id="MI-001",
        clause_title="제5조 제1항 — 거래구조 불일치",
        severity="HIGH",
        approval_required=True,
        issue_title="거래구조 불일치: 대리점이 최종소비자에게 직접 판매하는 것처럼 기재",
        problem=(
            "제5조 제1항이 대리점을 고객에 대한 직접 판매자로 기술하여, "
            "공급업자(퍼시스)가 고객과 직접 상품공급계약을 체결하는 실제 구조와 충돌합니다. "
            "이로 인해 세금계산서 발행 주체, 대금청구 주체, A/S 책임 주체, 소비자보호법상 "
            "책임 귀속이 모두 대리점으로 오해될 수 있습니다."
        ),
        legal_business_reason=(
            "부가가치세법상 세금계산서는 공급자(공급업자)가 발행해야 하며, "
            "대리점이 계약당사자로 표현될 경우 소비자 보호 의무, 제품결함 책임이 대리점에 귀속됩니다. "
            "대리점법 제6조 불이익 제공 금지 위반 가능성도 있습니다."
        ),
        proposed_revision=_REVISION_ART5_1,
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제5조의2 제2항", "제6조 제2항", "제6조 제6항", "제6조 제12항"],
        trigger_patterns=[
            re.compile(r"대리점은\s*공급업자로부터\s*위탁받은\s*상품을\s*최종\s*소비자에게\s*판매", re.IGNORECASE),
            re.compile(r"대리점은\s*고객에게\s*판매", re.IGNORECASE),
            re.compile(r"위탁받은\s*상품을\s*최종\s*소비자에게\s*판매", re.IGNORECASE),
            re.compile(r"최종\s*소비자에게\s*판매", re.IGNORECASE),
        ],
        clause_hints=["제5조", "거래형태", "위탁판매"],
    ),
    MandatoryIssue(
        issue_id="MI-002",
        clause_title="제5조의2 제2항 및 제6조 제2항 — 세금계산서·대금청구 주체 불명확",
        severity="HIGH",
        approval_required=True,
        issue_title="세금계산서·현금영수증·대금청구 주체: 대리점이 법적 발행/청구 주체처럼 기재",
        problem=(
            "계약서가 대리점을 세금계산서, 현금영수증 발행 및 대금청구의 법적 주체인 것처럼 규정합니다. "
            "공급업자(퍼시스)가 고객과 직접 상품공급계약을 체결하는 구조에서는 "
            "공급업자가 법적 발행·청구 주체여야 합니다."
        ),
        legal_business_reason=(
            "부가가치세법상 세금계산서는 실제 공급자가 발행해야 하며, "
            "대리점이 발행 시 명의 불일치로 세무리스크가 발생합니다. "
            "고객이 공급업자와 계약했는데 대리점 명의 세금계산서를 받으면 "
            "매입세액공제가 불인정될 수 있고, 고객의 손해배상 청구로 이어질 수 있습니다."
        ),
        proposed_revision=_REVISION_INVOICE,
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제5조 제1항", "제6조 제6항", "제6조 제12항"],
        trigger_patterns=[
            re.compile(r"대리점은\s*고객에게\s*세금계산서", re.IGNORECASE),
            re.compile(r"세금계산서\s*발행\s*및\s*대금의?\s*청구", re.IGNORECASE),
            re.compile(r"각종\s*법률이\s*규정하고\s*있는\s*의무를\s*수행", re.IGNORECASE),
            re.compile(r"대리점은.*세금계산서.*현금영수증.*법률상\s*의무", re.IGNORECASE),
            re.compile(r"세금계산서.*현금영수증.*의무를\s*수행", re.IGNORECASE),
            re.compile(r"세금계산서\s*발행.*대금\s*청구.*일괄", re.IGNORECASE),
        ],
        clause_hints=["제5조의2", "제6조", "세금계산서", "현금영수증", "대금청구"],
    ),
    MandatoryIssue(
        issue_id="MI-003",
        clause_title="제6조 제6항 및 제6조 제12항 — 고객계약서 작성·수금 주체 불명확",
        severity="HIGH",
        approval_required=True,
        issue_title="고객계약서 작성·대금수금: 대리점이 법적 당사자인 것처럼 기재",
        problem=(
            "대리점이 고객과 직접 상품공급계약서를 작성하고, "
            "대금수금의 법적 주체인 것처럼 기재되어 있습니다. "
            "공급업자(퍼시스)가 고객과 직접 계약하는 구조에서 대리점은 "
            "'지원자'이지 '계약 당사자'가 아닙니다."
        ),
        legal_business_reason=(
            "대리점이 계약 당사자로 표현될 경우 소비자 보호 의무, "
            "결함제품 책임, 계약 불이행 책임이 대리점에게 귀속됩니다. "
            "고객이 납기 지연이나 제품 하자를 이유로 대리점을 상대로 소송 제기 시 "
            "대리점이 공급업자의 제품 결함에 대한 1차 책임을 부담할 수 있습니다."
        ),
        proposed_revision=_REVISION_COLLECTION,
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제5조 제1항", "제5조의2 제2항", "제6조 제2항"],
        trigger_patterns=[
            re.compile(r"대리점은\s*고객과\s*계약\s*시\s*필수적으로\s*상품공급계약서를\s*작성", re.IGNORECASE),
            re.compile(r"대리점은\s*고객과\s*상품공급계약서를\s*작성", re.IGNORECASE),
            re.compile(r"대금\s*수금\s*업무를\s*성실히\s*수행", re.IGNORECASE),
            re.compile(r"수요자의\s*대금지급이\s*이루어질\s*수\s*있도록", re.IGNORECASE),
            re.compile(r"대금수금.*업무|수금.*업무.*수행", re.IGNORECASE),
        ],
        clause_hints=["제6조", "상품공급계약서", "수금", "대금지급"],
    ),
    MandatoryIssue(
        issue_id="MI-004",
        clause_title="제6조 제13항 — 법령 위반 책임 전부 전가",
        severity="HIGH",
        approval_required=True,
        issue_title="법령 위반 관련 '모든 책임'을 대리점에게 전부 귀속",
        problem=(
            "조달·입찰 관련 법령 위반 시 '모든 책임은 대리점에게 있다'는 표현이 "
            "공급업자의 지시, 승인, 정보 오류로 인한 경우까지 대리점에게 전가합니다. "
            "이는 과도한 귀책 전가로 대리점법상 불이익 제공에 해당할 수 있습니다."
        ),
        legal_business_reason=(
            "대리점법 제6조 불이익 제공 금지에 따라, 공급업자의 귀책사유로 발생한 손해까지 "
            "대리점에게 전가하는 것은 불이익 제공에 해당합니다. "
            "공급업자의 시스템 오류, 잘못된 정보 제공으로 인한 입찰 조건 위반도 "
            "대리점이 모든 책임을 부담하는 구조는 불합리합니다."
        ),
        proposed_revision=_REVISION_ALL_LIABILITY,
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제5조 제1항", "제6조 제6항"],
        trigger_patterns=[
            re.compile(r"모든\s*책임은\s*(대리점|을)에게\s*있다", re.IGNORECASE),
            re.compile(r"모든\s*책임은\s*(대리점|을)", re.IGNORECASE),
            re.compile(r"일체\s*책임.*대리점|대리점.*일체\s*책임", re.IGNORECASE),
            re.compile(r"전부\s*배상.*대리점|대리점.*전부\s*배상", re.IGNORECASE),
        ],
        clause_hints=["제6조", "책임", "법령", "입찰", "조달"],
    ),
    MandatoryIssue(
        issue_id="MI-005",
        clause_title="제16조 및 제25조 제6항 — 상계 절차 미비",
        severity="MEDIUM",
        approval_required=False,
        issue_title="용역수수료·정책지원금·거래보증금 상계: 사전통지·증빙·이의절차 부재",
        problem=(
            "용역수수료, 정책지원금, 거래보증금에서 상계하는 조항에 "
            "사전통지, 산정근거, 증빙자료 제공, 이의제기 기간, "
            "다툼 없는 금액만 상계 가능하다는 제한이 없습니다. "
            "공급업자가 근거 불명확한 채권으로 수수료를 일방 차감할 수 있습니다."
        ),
        legal_business_reason=(
            "대리점법 제6조 불이익 제공 금지에 따라, 사전통지·증빙 없이 "
            "즉시 상계하는 구조는 불이익 제공·비용전가 위반으로 판정될 수 있습니다. "
            "대리점이 운영 자금 부족으로 영업 중단에 이를 수 있으며, "
            "분쟁 시 입증 책임이 불리해집니다."
        ),
        proposed_revision=_REVISION_SETOFF,
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제16조 제1항", "제16조 제2항", "제16조 제3항", "제25조 제6항"],
        trigger_patterns=[
            re.compile(r"용역수수료에서\s*차감|용역수수료.*차감", re.IGNORECASE),
            re.compile(r"거래보증금에서\s*상계|거래보증금.*상계", re.IGNORECASE),
            re.compile(r"정책지원금에서\s*상계|정책지원금.*상계", re.IGNORECASE),
            re.compile(r"용역수수료.*정책지원금.*거래보증금.*상계", re.IGNORECASE),
            re.compile(r"상계.*세부\s*사항.*공급업자가\s*정하는", re.IGNORECASE),
            re.compile(r"즉시\s*상계|상계할\s*수\s*있다", re.IGNORECASE),
        ],
        clause_hints=["제16조", "제25조", "상계", "차감", "거래보증금"],
    ),
    MandatoryIssue(
        issue_id="MI-006",
        clause_title="제19조 제4항 — 상표·상호 무단사용 금지 및 갱신거절 비례성",
        severity="MEDIUM",
        approval_required=False,
        issue_title="IP 사용제한 조항: 소명기회·시정절차·갱신거절 비례성 미비",
        problem=(
            "상표·상호 무단사용 시 즉시 갱신거절로 연결되는 구조로, "
            "경미한 위반에도 갱신거절이 가능하고 소명기회나 시정절차가 없습니다. "
            "위반의 중대성·반복성·시정 여부를 고려하지 않은 갱신거절은 "
            "불공정할 수 있습니다."
        ),
        legal_business_reason=(
            "갱신거절은 대리점의 영업 기반을 상실하게 하는 중대한 불이익입니다. "
            "대리점법상 갱신거절은 정당한 사유가 있어야 하며, "
            "단순 실수나 경미한 위반에 대해 소명기회도 없이 갱신거절하는 것은 "
            "불공정거래행위로 판정될 수 있습니다."
        ),
        proposed_revision=_REVISION_IP_TRADEMARK,
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제19조 제1항", "제19조 제2항", "제19조 제3항"],
        trigger_patterns=[
            re.compile(r"공급업자의\s*사전\s*승인\s*없이.*상호.*상표.*지식재산권", re.IGNORECASE),
            re.compile(r"사전\s*승인\s*없이.*상호.*상표.*사용할\s*수\s*없다", re.IGNORECASE),
            re.compile(r"상표.*상호.*로고.*사용.*승인", re.IGNORECASE),
            re.compile(r"지식재산권.*사용.*승인", re.IGNORECASE),
        ],
        clause_hints=["제19조", "상표", "상호", "지식재산", "IP"],
    ),
    # ── Dealer Rental Service Contract rules (MR-001 … MR-010) ───────────────
    # These trigger on rental dealer contracts where the supplier directly
    # contracts with customers and the dealer performs service on their behalf.
    MandatoryIssue(
        issue_id="MR-001",
        clause_title="렌탈 계약 거래구조 — 공급업자-고객 직접계약 명확화",
        severity="HIGH",
        approval_required=True,
        issue_title="렌탈 계약 당사자: 공급업자-고객 직접계약 구조가 명확히 기재되지 않음",
        problem=(
            "공급업자가 고객과 직접 렌탈(임대차)계약을 체결하는 구조에서 "
            "대리점이 계약 당사자인 것처럼 기술되거나 업무 위탁 범위가 불명확합니다. "
            "이로 인해 렌탈료 청구 주체, 세금계산서 발행 주체, "
            "소유권 귀속 및 A/S 책임이 대리점으로 오해될 수 있습니다."
        ),
        legal_business_reason=(
            "부가가치세법상 세금계산서는 임대인(공급업자)이 발행해야 하며, "
            "대리점이 계약 당사자로 표시될 경우 민법상 임대인 의무(하자담보책임, 소유권 보전)가 "
            "대리점에 귀속될 위험이 있습니다. "
            "대리점거래법 제6조 불이익 제공 금지 위반 가능성도 있습니다."
        ),
        proposed_revision=(
            "공급업자는 고객과 직접 렌탈(임대차)계약을 체결하고, "
            "대리점은 공급업자로부터 위탁받은 범위 내에서 고객 발굴, 계약 지원, "
            "납품·설치 조율, 렌탈료 수금 지원 등 서비스 용역을 수행한다. "
            "대리점은 공급업자의 사전 서면 승인 없이 공급업자를 대리하여 "
            "고객과 렌탈계약을 체결하거나 공급업자 명의의 법률행위를 할 수 없다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제1조", "제5조", "세금계산서 조항"],
        trigger_patterns=[
            re.compile(r"대리점에\s*본\s*계약과\s*관련된\s*업무를\s*위탁", re.IGNORECASE),
            re.compile(r"퍼시스는\s*퍼시스의\s*대리점.*업무를\s*위탁", re.IGNORECASE),
            re.compile(r"대리점이\s*고객과\s*렌탈계약", re.IGNORECASE),
        ],
        clause_hints=["제1조", "거래구조", "위탁"],
    ),
    MandatoryIssue(
        issue_id="MR-002",
        clause_title="렌탈 대리점 — 대리권 부인 조항 미비",
        severity="HIGH",
        approval_required=True,
        issue_title="렌탈 대리점의 대리권 범위: 공급업자를 대리한 계약 체결 금지 명시 필요",
        problem=(
            "대리점이 공급업자를 대리하여 고객과 렌탈계약을 체결하거나 "
            "렌탈료를 직접 청구·수령할 수 있는 것처럼 규정되어 있습니다. "
            "대리점의 대리권 범위를 명확히 제한하지 않으면 "
            "공급업자가 예상치 못한 계약 의무를 부담하게 될 수 있습니다."
        ),
        legal_business_reason=(
            "민법상 표현대리 원칙에 따라 대리점이 외관상 공급업자를 대리하여 "
            "계약을 체결한 경우 공급업자가 계약 당사자로 구속될 수 있습니다. "
            "대리권 범위를 명확히 제한하는 조항이 없으면 분쟁 시 공급업자가 "
            "대리점의 행위에 대한 책임을 부담할 위험이 있습니다."
        ),
        proposed_revision=(
            "대리점은 공급업자의 명시적 서면 위임이 없는 한 공급업자를 대리하여 "
            "고객과 렌탈계약을 체결하거나, 렌탈료를 직접 청구·수령하거나, "
            "공급업자 명의의 세금계산서를 발행하거나, 공급업자 명의의 법적 의무를 "
            "부담하는 행위를 할 수 없다. 대리점이 이를 위반하여 발생한 손해는 "
            "대리점이 배상한다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제1조", "제5조", "제6조"],
        trigger_patterns=[
            re.compile(r"렌탈.*대리점.*계약", re.IGNORECASE),
            re.compile(r"대리점.*렌탈.*업무.*위탁", re.IGNORECASE),
            re.compile(r"대리점.*렌탈료.*청구|렌탈료.*대리점.*수령", re.IGNORECASE),
        ],
        clause_hints=["대리권", "위탁"],
    ),
    MandatoryIssue(
        issue_id="MR-003",
        clause_title="렌탈 세금계산서·렌탈료 청구 주체",
        severity="HIGH",
        approval_required=True,
        issue_title="세금계산서·렌탈료 청구 주체: 공급업자(임대인)가 법적 발행·청구 주체여야 함",
        problem=(
            "렌탈료 세금계산서 발행 및 청구 주체가 불명확하거나 "
            "대리점이 발행·청구 주체인 것처럼 기재되어 있습니다. "
            "공급업자가 임대인으로서 고객과 직접 렌탈계약을 체결하는 구조에서는 "
            "공급업자가 세금계산서 및 렌탈료 청구의 법적 주체여야 합니다."
        ),
        legal_business_reason=(
            "부가가치세법상 세금계산서는 공급자(임대인)가 발행해야 하며, "
            "대리점이 발행할 경우 명의 불일치로 고객의 매입세액공제가 불인정될 수 있습니다. "
            "렌탈료 청구 주체가 불명확할 경우 고객이 대리점에 지급하는 문제가 발생하고 "
            "공급업자의 수익 회수에 위험이 생깁니다."
        ),
        proposed_revision=(
            "렌탈료 및 이에 부수되는 세금계산서의 법적 발행·청구 주체는 임대인(공급업자)으로 한다. "
            "대리점은 고객의 렌탈료 납부 일정 안내, 미납 확인, 납부 독촉 등 수금 지원 업무를 수행하며, "
            "고객으로부터 렌탈료를 직접 수령한 경우 즉시 공급업자에게 통지하고 지체 없이 이전하여야 한다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["제5조", "세금계산서 발행일 조항"],
        trigger_patterns=[
            re.compile(r"세금계산서\s*발행일.*익월", re.IGNORECASE),
            re.compile(r"렌탈료.*세금계산서|세금계산서.*렌탈료", re.IGNORECASE),
            re.compile(r"렌탈.*세금계산서.*발행", re.IGNORECASE),
        ],
        clause_hints=["세금계산서", "렌탈료", "청구"],
    ),
    MandatoryIssue(
        issue_id="MR-004",
        clause_title="고객 렌탈료 미납 — 대리점 책임 한정",
        severity="HIGH",
        approval_required=True,
        issue_title="고객 렌탈료 미납 책임: 대리점 귀책사유 있는 경우로 한정 필요",
        problem=(
            "고객이 렌탈료를 미납하는 경우 대리점이 책임을 부담하도록 규정되거나, "
            "대리점의 귀책사유 없이도 미납 렌탈료를 대리점 수수료에서 차감하는 구조입니다. "
            "고객의 신용 문제나 부도로 인한 미납은 대리점 귀책이 아님에도 "
            "대리점이 전적으로 부담하게 됩니다."
        ),
        legal_business_reason=(
            "대리점거래법 제6조 불이익 제공 금지에 따라, 대리점의 귀책 없이 "
            "발생한 고객 미납 손해를 대리점에게 전가하는 것은 불이익 제공에 해당합니다. "
            "공급업자가 고객 신용심사 없이 계약을 체결하고 그 리스크를 대리점에 귀속시키면 "
            "불공정거래행위로 판정될 수 있습니다."
        ),
        proposed_revision=(
            "고객의 렌탈료 미납에 대한 책임은 대리점의 고의 또는 중대한 과실, "
            "허위 정보 제공, 중요 사실 미고지, 잘못된 계좌 안내 등 "
            "대리점의 귀책사유가 명확히 인정되는 경우에 한하여 부담한다. "
            "고객의 신용 악화, 경기 변동, 기타 대리점의 귀책 없는 사유로 인한 미납은 "
            "대리점이 부담하지 아니한다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["수금 지원 조항", "상계 조항"],
        trigger_patterns=[
            re.compile(r"렌탈료\s*미납|미납\s*렌탈료", re.IGNORECASE),
            re.compile(r"고객.*미납.*대리점.*책임|대리점.*고객.*미납", re.IGNORECASE),
            re.compile(r"렌탈료.*미회수.*대리점|대리점.*렌탈료.*책임", re.IGNORECASE),
        ],
        clause_hints=["렌탈료", "미납", "책임"],
    ),
    MandatoryIssue(
        issue_id="MR-005",
        clause_title="취소·반품·A/S 최종책임 — 공급업자 부담",
        severity="MEDIUM",
        approval_required=False,
        issue_title="취소·반품·A/S 최종책임: 공급업자(임대인)가 부담, 대리점 귀책 비용만 구상",
        problem=(
            "렌탈 계약물품의 설치 하자, 제품 결함, A/S 및 조기 계약 해제에 따른 "
            "취소·반품 관련 대외적 책임이 대리점에게 귀속되거나 "
            "비례성 없이 대리점이 모든 비용을 부담하도록 규정되어 있습니다."
        ),
        legal_business_reason=(
            "임대인으로서 공급업자는 계약물품의 하자담보책임과 사용·수익 보장 의무를 부담합니다. "
            "대리점에게 제품 결함 또는 임대인 귀책 비용을 전가하는 것은 "
            "대리점거래법상 불이익 제공에 해당할 수 있습니다."
        ),
        proposed_revision=(
            "계약물품의 하자, 제품 결함, A/S 및 취소·반품에 관한 고객에 대한 최종 책임은 "
            "임대인(공급업자)이 부담한다. 대리점은 고객 안내, 접수 지원 및 공급업자 연결 업무를 수행한다. "
            "다만 대리점의 고의·과실, 잘못된 설치 안내, 주문정보 오입력 등 "
            "대리점 귀책으로 인해 추가 비용이 발생한 경우 공급업자는 대리점에게 구상할 수 있다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["설치 조항", "하자보수 조항", "계약 해지 조항"],
        trigger_patterns=[
            re.compile(r"설치.*하자.*대리점\s*부담|대리점.*설치.*비용\s*부담", re.IGNORECASE),
            re.compile(r"반품.*취소.*비용.*대리점|대리점.*반품.*취소.*책임", re.IGNORECASE),
            re.compile(r"a/s.*대리점.*책임|대리점.*a/s.*비용", re.IGNORECASE),
        ],
        clause_hints=["A/S", "반품", "취소", "하자"],
    ),
    MandatoryIssue(
        issue_id="MR-006",
        clause_title="수수료 차감·상계·보증금 공제 — 사전통지·증빙·이의절차",
        severity="MEDIUM",
        approval_required=False,
        issue_title="렌탈 대리점 수수료 차감·보증금 공제: 사전통지·증빙·이의절차 부재",
        problem=(
            "대리점 수수료, 보증금에서 차감·상계하는 조항에 "
            "사전통지, 산정근거 제공, 이의제기 기간, 이의 금액 잠정 보류 절차가 없습니다. "
            "공급업자가 근거 불명확한 채권으로 수수료를 일방적으로 차감할 수 있습니다."
        ),
        legal_business_reason=(
            "대리점거래법 제6조 불이익 제공 금지에 따라, 사전통지·증빙 없이 "
            "수수료를 차감하거나 보증금에서 공제하는 구조는 불이익 제공에 해당합니다. "
            "분쟁 시 대리점이 입증 책임을 부담하여 회수가 어려워질 수 있습니다."
        ),
        proposed_revision=(
            "공급업자가 대리점 수수료 또는 보증금에서 차감·공제하려는 경우, "
            "차감 사유, 산정내역, 증빙자료 및 예정일을 사전 서면으로 통지하여야 한다. "
            "대리점이 통지일로부터 7영업일 이내에 이의를 제기한 금액에 대해서는 "
            "당사자 간 협의 또는 객관적 자료에 의해 확정되기 전까지 임의로 차감하지 않는다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["수수료 조항", "보증금 조항"],
        trigger_patterns=[
            re.compile(r"수수료.*차감|차감.*수수료", re.IGNORECASE),
            re.compile(r"보증금.*공제|보증금.*차감", re.IGNORECASE),
            re.compile(r"수수료.*보증금.*상계|상계.*수수료", re.IGNORECASE),
        ],
        clause_hints=["수수료", "보증금", "차감", "상계"],
    ),
    MandatoryIssue(
        issue_id="MR-007",
        clause_title="계약해지·갱신거절·물량축소 — 요건·비례성",
        severity="MEDIUM",
        approval_required=False,
        issue_title="계약해지·갱신거절·물량축소: 중대위반·시정기회·비례성 요건 미비",
        problem=(
            "계약해지, 갱신거절 또는 공급 물량 축소 사유가 지나치게 광범위하게 규정되어 있거나 "
            "위반의 중대성과 무관하게 즉시 해지·갱신거절이 가능합니다. "
            "경미한 위반에 대한 시정기회 없는 즉각 해지는 불공정할 수 있습니다."
        ),
        legal_business_reason=(
            "대리점거래법상 계약 해지·갱신거절은 정당한 사유가 있어야 하며, "
            "과도하게 광범위한 해지 사유는 불공정거래행위로 판정될 수 있습니다. "
            "시정기회 없이 즉시 해지하는 구조는 대리점의 영업 기반을 과도하게 침해합니다."
        ),
        proposed_revision=(
            "공급업자는 대리점의 중대한 계약 위반, 대리점 파산 또는 회생절차 개시, "
            "대리점의 영업 포기 등 중대한 사유가 있는 경우 계약을 해지할 수 있다. "
            "다만 경미한 위반의 경우 공급업자는 상당한 기간을 정하여 시정을 요구하고, "
            "대리점이 그 기간 내에 시정하지 않는 경우에만 해지할 수 있다. "
            "갱신거절 및 공급 물량 축소는 정당한 사유와 사전 통지를 요한다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["계약 해지 조항", "갱신 조항"],
        trigger_patterns=[
            re.compile(r"즉시\s*해지.*유통질서|유통질서.*즉시\s*해지", re.IGNORECASE),
            re.compile(r"갱신을\s*거절할\s*수\s*있다|갱신\s*거절", re.IGNORECASE),
            re.compile(r"물량.*현저히\s*축소|공급.*중단.*물량", re.IGNORECASE),
        ],
        clause_hints=["해지", "갱신", "물량", "계약 종료"],
    ),
    MandatoryIssue(
        issue_id="MR-008",
        clause_title="판촉비·인테리어·광고비 — 비용분담 절차",
        severity="MEDIUM",
        approval_required=False,
        issue_title="판촉비·인테리어·광고비 비용분담: 사전합의·상한·증빙 절차 부재",
        problem=(
            "판촉 활동, 인테리어 개선, 광고비 등 비용을 대리점이 부담하도록 규정하면서 "
            "사전 서면 합의, 비용 상한, 증빙자료 제출 절차가 없습니다. "
            "공급업자가 일방적으로 비용을 전가할 수 있는 구조입니다."
        ),
        legal_business_reason=(
            "대리점거래법 제6조에 따라 대리점에게 경제상 이익을 강제하는 것은 "
            "불이익 제공에 해당합니다. 사전 합의 없이 비용을 일방 청구하거나 "
            "수수료에서 차감하는 것은 불공정거래행위로 판정될 수 있습니다."
        ),
        proposed_revision=(
            "판촉 활동, 광고, 인테리어 개선 등 비용이 발생하는 협력 사항은 "
            "공급업자와 대리점이 사전에 서면으로 합의하여야 한다. "
            "비용 분담 비율, 상한 및 증빙자료 제출 방법은 합의서에 명시한다. "
            "사전 합의 없이 발생한 비용은 공급업자가 부담하며 대리점 수수료에서 차감할 수 없다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["판촉비 조항", "광고비 조항"],
        trigger_patterns=[
            re.compile(r"판촉.*비용.*대리점\s*부담|대리점.*판촉.*비용\s*부담", re.IGNORECASE),
            re.compile(r"광고비.*대리점|인테리어.*대리점.*부담", re.IGNORECASE),
            re.compile(r"대리점은\s*판촉.*광고.*비용", re.IGNORECASE),
        ],
        clause_hints=["판촉비", "광고비", "인테리어"],
    ),
    MandatoryIssue(
        issue_id="MR-009",
        clause_title="IP·사업장 이전·영업양도 — 갱신거절 비례성",
        severity="MEDIUM",
        approval_required=False,
        issue_title="IP사용·사업장 이전·영업양도 위반에 따른 갱신거절: 경미위반 제외·시정기회 필요",
        problem=(
            "상표·지식재산권 사용, 사업장 이전, 영업양도 관련 조항 위반 시 "
            "경미한 위반도 갱신거절 사유가 되며, 소명 및 시정 기회가 없습니다. "
            "위반의 중대성·반복성·실제 피해 여부를 고려하지 않고 갱신거절하는 것은 "
            "불공정할 수 있습니다."
        ),
        legal_business_reason=(
            "대리점법상 갱신거절은 정당한 사유가 있어야 하며, "
            "단순 행정적 절차 위반이나 경미한 실수에 대한 갱신거절은 "
            "대리점의 생계 기반을 과도하게 침해하는 불공정행위로 볼 수 있습니다."
        ),
        proposed_revision=(
            "대리점이 IP 사용 제한, 사업장 이전 제한 또는 영업양도 금지 조항을 위반한 경우, "
            "공급업자는 위반 내용 및 증거를 제시하여 소명을 요구할 수 있다. "
            "위반이 경미하고 시정 가능한 경우 공급업자는 상당한 기간의 시정 기회를 부여하여야 하며, "
            "중대하고 반복적인 위반으로 공급업자에게 실질적 피해가 발생한 경우에만 갱신거절이 가능하다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["IP 사용 조항", "사업장 이전 조항", "갱신 조항"],
        trigger_patterns=[
            re.compile(r"사전.*동의.*없이.*이전|이전.*사전.*동의", re.IGNORECASE),
            re.compile(r"영업양도.*금지|양도.*공급업자.*동의", re.IGNORECASE),
            re.compile(r"상표.*무단\s*사용.*갱신\s*거절|갱신\s*거절.*상표", re.IGNORECASE),
        ],
        clause_hints=["IP", "사업장 이전", "영업양도", "갱신거절"],
    ),
    MandatoryIssue(
        issue_id="MR-010",
        clause_title="분쟁조정·보복조치 금지·자료 확인권",
        severity="MEDIUM",
        approval_required=False,
        issue_title="분쟁조정 신청 보복 금지·대리점 자료 확인권: 명시 필요",
        problem=(
            "대리점이 공정거래위원회, 한국공정거래조정원 등에 분쟁조정을 신청하거나 "
            "권리를 행사하는 경우 공급업자가 불이익 조치를 취할 수 있는 구조이며, "
            "대리점이 자신의 수수료 산정 내역, 거래 이력 등을 확인할 수 있는 권리가 불명확합니다."
        ),
        legal_business_reason=(
            "대리점거래법 제10조에 따라 분쟁조정 신청을 이유로 한 불이익 제공은 금지되며, "
            "대리점은 자신의 거래 이력 및 수수료 산정 내역에 대한 자료 제공 요청권을 가집니다. "
            "이를 명시하지 않으면 공급업자가 보복조치를 취하거나 자료 제공을 거부할 수 있습니다."
        ),
        proposed_revision=(
            "공급업자는 대리점이 관련 법령에 따른 분쟁조정 신청, 공정거래위원회 신고, "
            "대리점단체 가입 등 권리를 행사하였다는 이유로 대리점에게 불이익을 주어서는 아니 된다. "
            "대리점은 수수료 산정 내역, 거래 이력 등 자신의 거래와 관련된 자료의 제공을 요청할 수 있으며, "
            "공급업자는 합리적인 기간 내에 이를 제공하여야 한다."
        ),
        negotiation_position=_NEGOTIATION_COUNTERPARTY_FORM,
        related_clauses=["분쟁 해결 조항", "공정거래 준수 조항"],
        trigger_patterns=[
            re.compile(r"공정거래\s*준수|불공정거래\s*금지", re.IGNORECASE),
            re.compile(r"분쟁\s*해결|관할\s*법원", re.IGNORECASE),
            re.compile(r"대리점\s*단체|한국공정거래조정원", re.IGNORECASE),
        ],
        clause_hints=["분쟁", "공정거래", "보복"],
    ),
]


# ─── Detection and injection functions ────────────────────────────────────────

def _detect_issue_in_text(issue: MandatoryIssue, text: str) -> bool:
    """Return True if any trigger pattern matches the text."""
    for pat in issue.trigger_patterns:
        if pat.search(text):
            return True
    return False


def _extract_matched_excerpt(
    issue: MandatoryIssue,
    text: str,
    max_len: int = 200,
    clauses: list[Any] | None = None,
) -> str:
    """Extract the matching text excerpt from the contract.

    Scoped to the already-confirmed segmentation (`clauses`) whenever
    available, so the quote can never bleed into an adjacent clause/article —
    a raw whole-document character-offset window doesn't know where one
    항/조 ends and the next begins."""
    from runtime.review.clause_extraction import find_clause_scoped_excerpt

    for pat in issue.trigger_patterns:
        if clauses:
            scoped = find_clause_scoped_excerpt(clauses, pat, before=20, after=100)
            if scoped is not None:
                return scoped[0][:max_len]
            continue
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 100)
            excerpt = text[start:end].strip()
            return excerpt[:max_len]
    return ""


# Dealer types that trigger mandatory issue injection
_DEALER_TYPE_CODES_FOR_MANDATORY: frozenset[str] = frozenset({
    "consignment_sales_agency",
    "direct_customer_sales_support",
    "dealer_agency",
    "dealer_rental_service_contract",
})


def inject_mandatory_issues(
    *,
    full_text: str,
    clause_results: list[dict[str, Any]],
    contract_type_code: str,
    is_counterparty_form: bool = True,
    clauses: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Inject mandatory issues for consignment dealer contracts.

    For each mandatory issue pattern found in the contract text,
    this function either:
    - Replaces the matching clause_result with the mandatory issue, OR
    - Adds the mandatory issue if no matching clause_result exists.

    Args:
        full_text: full contract text
        clause_results: raw clause results from build_clause_level_result
        contract_type_code: e.g. "consignment_sales_agency"
        is_counterparty_form: True if the contract is the counterparty's form
        clauses: already-segmented clauses (ClauseChunk or dict), used to
            scope the "원문" quote so it can never bleed into another clause

    Returns:
        Updated clause_results with mandatory issues injected/merged
    """
    if contract_type_code not in _DEALER_TYPE_CODES_FOR_MANDATORY:
        # Also check for consignment/dealer signals in text
        has_dealer_signals = any(kw in full_text for kw in [
            "위탁판매", "용역수수료", "검수마스터", "위탁커넥트플러스", "렌탈대리점",
        ])
        if not has_dealer_signals:
            return clause_results

    negotiation = _NEGOTIATION_COUNTERPARTY_FORM if is_counterparty_form else _NEGOTIATION_SUPPLIER_FORM

    injected_ids: set[str] = set()
    new_results: list[dict[str, Any]] = list(clause_results)

    for mandatory in MANDATORY_CONSIGNMENT_ISSUES:
        if not _detect_issue_in_text(mandatory, full_text):
            continue

        excerpt = _extract_matched_excerpt(mandatory, full_text, clauses=clauses)

        # Always add mandatory issue as a NEW cr with its own clause_id (MI-001 etc.)
        # This ensures _filter_and_sort_issues can identify it as mandatory via clause_id.
        # The original matched clause_result is kept as-is but gets severity upgrade.
        if mandatory.issue_id not in injected_ids:
            # Upgrade any matching existing clause result (severity, but NOT clause_id).
            # Skip already-injected mandatory issues to prevent one mandatory issue
            # from overwriting another's mandatory_issue_id tag.
            for cr in new_results:
                if not isinstance(cr, dict):
                    continue
                if cr.get("is_mandatory"):
                    continue
                cr_text = str(cr.get("original_text") or "")
                if cr_text and _detect_issue_in_text(mandatory, cr_text):
                    cr["risk_tier"] = mandatory.severity
                    cr["severity"] = mandatory.severity
                    cr["high_risk"] = mandatory.severity == "HIGH"
                    cr["must_fix"] = mandatory.severity == "HIGH"
                    cr["is_mandatory_upgraded"] = True
                    cr["mandatory_issue_id"] = mandatory.issue_id
                    break

            # Add the new mandatory cr
            if mandatory.issue_id not in injected_ids:
                new_cr = {
                    "clause_id": mandatory.issue_id,
                    "clause_title": mandatory.clause_title,
                    "article_number": None,
                    "paragraph_number": None,
                    "display_path": mandatory.clause_title,
                    "clause_topic": "dealer_unfair",
                    "risk_tier": mandatory.severity,
                    "severity": mandatory.severity,
                    "approval_required": mandatory.approval_required,
                    "high_risk": mandatory.severity == "HIGH",
                    "must_fix": mandatory.severity == "HIGH",
                    "review_tier": "MUST" if mandatory.severity == "HIGH" else "SUGGEST",
                    "issue_title": mandatory.issue_title,
                    "original_text": excerpt or f"[{mandatory.clause_title}] 관련 조항",
                    "problem": mandatory.problem,
                    "legal_business_reason": mandatory.legal_business_reason,
                    "suggested_rewrite": mandatory.proposed_revision,
                    "rewrite_reason": mandatory.problem,
                    "negotiation_position": negotiation,
                    "related_clauses": mandatory.related_clauses,
                    "confidence": mandatory.confidence,
                    "is_mandatory": True,
                    "mandatory_issue_id": mandatory.issue_id,
                    "has_rewrite_change": True,
                    "display_kind": "redline" if mandatory.severity == "HIGH" else "guidance",
                    "dedup_suppressed": False,
                    "keep_as_is": False,
                    "user_focus_hit": True,
                    "factual_hit": False,
                    "ai_deep_reviewed": False,
                }
                new_results.insert(0, new_cr)
                injected_ids.add(mandatory.issue_id)

    return new_results


def get_mandatory_negotiation_position(is_counterparty_form: bool | None) -> str:
    """Return appropriate negotiation position fallback."""
    if is_counterparty_form is True:
        return _NEGOTIATION_COUNTERPARTY_FORM
    if is_counterparty_form is False:
        return _NEGOTIATION_SUPPLIER_FORM
    return _NEGOTIATION_DEFAULT


# ─── Convenience exports ───────────────────────────────────────────────────────

# Subset of MANDATORY_CONSIGNMENT_ISSUES that covers rental dealer contracts.
# Used in tests and by caller code that needs to enumerate rental-specific rules.
_DEALER_RENTAL_MANDATORY_ISSUES: list[MandatoryIssue] = [
    mi for mi in MANDATORY_CONSIGNMENT_ISSUES if mi.issue_id.startswith("MR-")
]


def get_triggered_mandatory_issues(
    *,
    contract_type_code: str,
    text: str,
    existing_issues: list[Any] | None = None,
) -> list[MandatoryIssue]:
    """Return matching MandatoryIssue objects for the given contract type and text.

    This is a test-friendly wrapper over the pattern-matching logic.
    Unlike inject_mandatory_issues(), this returns MandatoryIssue objects (not dicts)
    and does not mutate any existing results.

    Args:
        contract_type_code: canonical contract type code
        text: full contract text
        existing_issues: ignored (kept for call-site compatibility)
    """
    if contract_type_code not in _DEALER_TYPE_CODES_FOR_MANDATORY:
        has_dealer_signals = any(kw in text for kw in [
            "위탁판매", "용역수수료", "검수마스터", "위탁커넥트플러스", "렌탈대리점",
        ])
        if not has_dealer_signals:
            return []

    return [mi for mi in MANDATORY_CONSIGNMENT_ISSUES if _detect_issue_in_text(mi, text)]
