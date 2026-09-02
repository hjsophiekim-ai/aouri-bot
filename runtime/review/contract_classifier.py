"""Detailed contract profile classification for multi-dimensional legal review.

Implements the full ContractProfile with legal-role metadata for:
  - content_production_service   (콘텐츠 제작 용역)
  - advertising_content_production  (제품 광고 콘텐츠 제작 대행)
  - creative_agency_service      (광고 대행사 용역)
  - consignment_sales_agency  (위탁판매 대리점 — supplier contracts directly with customer)
  - direct_customer_sales_support  (고객·공급업자 직접계약 + 대리점 지원)
  - dealer_agency  (대리점 직접판매 구조)
  - distribution_resale  (유통/재판매)
  - purchase_supply, equipment_purchase_installation
  - store_operation_outsourcing, advisory_service
  - testing_inspection_service  (시험·검사·인증/분석 용역 — 위탁자가 시험기관에 시험을 의뢰)
  - software_app_development, ai_search_marketing
  - rental, construction, general

This module is the SINGLE canonical source of contract-type and legal-role
classification. Other modules (clause_level.py's rule/checklist gates,
party_role.py, hallucination_guard.py, output_filter.py) MUST resolve
contract type/role via classify_contract_detailed()/ROLE_BUCKET rather than
re-deriving their own independent keyword guesses — a contract must not be
"AI 검색·마케팅" in one place and "advisory" in another for the same review.

`answers` (structured Q&A collected before review) can be passed in as a
high-confidence override: when the user has directly confirmed the contract
type or their own role, that answer takes priority over keyword guessing.

Recognised Fursys Group brands:
  퍼시스, 일룸, 시디즈, 데스커, 바로스, 퍼시스홀딩스
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ─── Fursys group recognition ─────────────────────────────────────────────────

FURSYS_GROUP_NAMES: list[str] = [
    "퍼시스홀딩스", "Fursys Holdings", "fursys holdings",
    "퍼시스", "FURSYS", "fursys", "Fursys",
    "일룸", "ILOOM", "iloom", "Iloom",
    "시디즈", "SIDIZ", "sidiz", "Sidiz",
    "데스커", "DESKER", "desker", "Desker",
    "바로스", "BAROS", "baros", "Baros",
]

_BRAND_PRIORITY: list[tuple[str, list[str]]] = [
    ("퍼시스홀딩스", ["퍼시스홀딩스", "fursys holdings"]),
    ("시디즈", ["시디즈", "sidiz"]),
    ("일룸", ["일룸", "iloom"]),
    ("데스커", ["데스커", "desker"]),
    # 퍼시스가 바로스보다 앞: 바로스는 A/S 파트너로 자주 언급되므로
    # 퍼시스 계약에서 바로스가 우선 감지되는 오인을 방지
    ("퍼시스", ["퍼시스", "fursys"]),
    ("바로스", ["바로스", "baros"]),
]


def is_fursys_group(entity: str) -> bool:
    """Return True if entity text belongs to any Fursys Group brand."""
    if not entity:
        return False
    s = entity.strip().lower()
    return any(name.lower() in s for name in FURSYS_GROUP_NAMES)


def detect_our_party_from_text(text: str, hint_entity: str = "") -> str | None:
    """Scan contract text to identify which Fursys group company is 'ours'.

    Case-insensitive. hint_entity (the entity field set by the uploader) is
    trusted FIRST — if it matches a Fursys brand we return it immediately
    without scanning the body. This prevents a subsidiary brand mentioned as
    an A/S or logistics partner from overriding the actual issuing entity.
    Falls back to text scan only when hint_entity is absent or unknown.
    Returns canonical brand name or None.
    """
    # Trust uploader hint before scanning body text
    if hint_entity:
        h = hint_entity.strip().lower()
        for canonical, aliases in _BRAND_PRIORITY:
            if any(alias.lower() in h for alias in aliases):
                return canonical
    # Fall back to text scan
    t = (text or "").lower()
    for canonical, aliases in _BRAND_PRIORITY:
        if any(alias.lower() in t for alias in aliases):
            return canonical
    return None


# ─── Canonical role buckets ────────────────────────────────────────────────────
# English "bucket" codes consumed by rule-gating logic (clause_level.py,
# party_role.py, hallucination_guard.py). Keep this list small and stable —
# every gate that asks "are we the supplier?" must check membership in these
# buckets rather than re-deriving its own guess from raw text.
#   supplier               — we sell/supply goods or services to the counterparty
#   buyer                  — we purchase/receive goods from the counterparty
#   service_recipient      — we receive a professional/testing/advisory service
#                             (client of an advisor, testing requester, etc.)
#   service_provider       — we perform the professional/testing/advisory service
#   contractor             — we are the construction/installation contractor
#   ordering_party         — we order construction/installation/dev work
#   dealer                 — we are a dealer/distributor of the counterparty's goods
#   neutral                — role not meaningfully asymmetric for rule-gating
#   unknown                — could not be determined; do not fire role-specific rules
_TYPE_TO_ROLE_BUCKET: dict[str, tuple[str, str]] = {
    "advertising_content_production": ("service_recipient", "service_provider"),
    "content_production_service": ("service_recipient", "service_provider"),
    "creative_agency_service": ("service_recipient", "service_provider"),
    "consignment_sales_agency": ("supplier", "dealer"),
    "direct_customer_sales_support": ("supplier", "dealer"),
    "dealer_rental_service_contract": ("supplier", "dealer"),
    "dealer_agency": ("supplier", "dealer"),
    "distribution_resale": ("supplier", "dealer"),
    "purchase_supply": ("buyer", "supplier"),
    "equipment_purchase_installation": ("buyer", "contractor"),
    "store_operation_outsourcing": ("service_recipient", "service_provider"),
    "advisory_service": ("service_recipient", "service_provider"),
    "testing_inspection_service": ("service_recipient", "service_provider"),
    "software_app_development": ("service_recipient", "service_provider"),
    "ai_search_marketing": ("service_recipient", "service_provider"),
    "rental": ("buyer", "supplier"),
    "construction": ("ordering_party", "contractor"),
    "nda_confidentiality": ("party", "party"),
    "general": ("unknown", "unknown"),
}


# ─── ContractProfile dataclass ────────────────────────────────────────────────

@dataclass
class ContractProfile:
    """Full legal-role metadata for a classified contract."""
    contract_type: str
    our_party: str
    counterparty: str
    our_legal_role: str
    counterparty_legal_role: str
    customer_contracting_party: str | None
    payment_collection_party: str | None
    tax_invoice_issuer: str | None
    agency_authority: bool | None
    confidence: float
    reasons: list[str]
    unresolved_questions: list[str]
    our_role_bucket: str = "unknown"
    counterparty_role_bucket: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "our_party": self.our_party,
            "counterparty": self.counterparty,
            "our_legal_role": self.our_legal_role,
            "counterparty_legal_role": self.counterparty_legal_role,
            "customer_contracting_party": self.customer_contracting_party,
            "payment_collection_party": self.payment_collection_party,
            "tax_invoice_issuer": self.tax_invoice_issuer,
            "agency_authority": self.agency_authority,
            "confidence": round(self.confidence, 3),
            "reasons": list(self.reasons),
            "unresolved_questions": list(self.unresolved_questions),
            "our_role_bucket": self.our_role_bucket,
            "counterparty_role_bucket": self.counterparty_role_bucket,
        }


# ─── Main classification function ─────────────────────────────────────────────

def classify_contract_detailed(
    *,
    entity: str,
    contract_type: str,
    text: str,
    filename: str | None = None,
    answers: dict[str, Any] | None = None,
) -> ContractProfile:
    """Return a fully populated ContractProfile for the given contract.

    Args:
        answers: structured Q&A answers collected before review (see
            runtime.questions.generator). When the user has directly
            confirmed the contract type via a Q-TYPE-* answer, that
            confirmation overrides keyword-based type_code guessing —
            a lawyer's own statement of fact beats a regex heuristic.
    """
    t = text or ""
    ct = contract_type or ""
    ent = entity or ""
    ans = answers or {}
    reasons: list[str] = []
    unresolved: list[str] = []

    our_party = detect_our_party_from_text(t, hint_entity=ent) or ent or "미상"
    counterparty = _detect_counterparty(t, our_party)

    override_type = _type_code_from_answers(ans)
    if override_type:
        type_code, type_reasons = override_type, ["user_confirmed_contract_type"]
    else:
        type_code, type_reasons = _classify_type_code(ct, t, filename or "")
    reasons.extend(type_reasons)

    our_legal_role, counterparty_legal_role = _infer_legal_roles(type_code, ct, t, ent)
    our_role_bucket, counterparty_role_bucket = _TYPE_TO_ROLE_BUCKET.get(type_code, ("unknown", "unknown"))

    override_role_bucket = _role_bucket_from_answers(ans)
    if override_role_bucket:
        our_role_bucket = override_role_bucket
        counterparty_role_bucket = _COUNTERPARTY_BUCKET_FOR.get(override_role_bucket, counterparty_role_bucket)
        reasons.append("user_confirmed_our_role")

    customer_contracting_party: str | None = None
    payment_collection_party: str | None = None
    tax_invoice_issuer: str | None = None
    agency_authority: bool | None = None

    if type_code in ("consignment_sales_agency", "direct_customer_sales_support", "dealer_rental_service_contract"):
        cpres = _infer_customer_contract_details(t, our_party)
        customer_contracting_party = cpres["customer_contracting_party"]
        payment_collection_party = cpres["payment_collection_party"]
        tax_invoice_issuer = cpres["tax_invoice_issuer"]
        agency_authority = cpres["agency_authority"]
        unresolved.extend(cpres["unresolved"])
    elif type_code == "dealer_agency":
        customer_contracting_party = counterparty
        payment_collection_party = counterparty
        tax_invoice_issuer = counterparty
        agency_authority = False

    confidence = 0.98 if override_type else _compute_confidence(type_code, reasons, t)

    return ContractProfile(
        contract_type=type_code,
        our_party=our_party,
        counterparty=counterparty,
        our_legal_role=our_legal_role,
        counterparty_legal_role=counterparty_legal_role,
        customer_contracting_party=customer_contracting_party,
        payment_collection_party=payment_collection_party,
        tax_invoice_issuer=tax_invoice_issuer,
        agency_authority=agency_authority,
        confidence=confidence,
        reasons=reasons,
        unresolved_questions=unresolved,
        our_role_bucket=our_role_bucket,
        counterparty_role_bucket=counterparty_role_bucket,
    )


# ─── Q&A answer overrides ──────────────────────────────────────────────────────
# Maps a direct user answer (collected via runtime.questions.generator's
# Q-TYPE-*/Q-ROLE-* confirmation questions) to a canonical type_code / role
# bucket. A confirmed fact from the reviewer beats keyword guessing.

_ANSWER_TYPE_CODE_MAP: dict[str, str] = {
    "testing_inspection": "testing_inspection_service",
    "product_supply": "purchase_supply",
    "equipment_installation": "equipment_purchase_installation",
    "advisory": "advisory_service",
    "dealer_consignment": "consignment_sales_agency",
    "dealer_agency": "dealer_agency",
    "rental": "rental",
    "construction": "construction",
    "software_dev": "software_app_development",
    "content_production": "content_production_service",
    "marketing_ai_search": "ai_search_marketing",
    "other_general": "general",
}

_ANSWER_ROLE_BUCKET_MAP: dict[str, str] = {
    "we_are_supplier": "supplier",
    "we_are_buyer": "buyer",
    "we_are_service_recipient": "service_recipient",
    "we_are_service_provider": "service_provider",
    "we_are_contractor": "contractor",
    "we_are_ordering_party": "ordering_party",
    "we_are_dealer": "dealer",
}

_COUNTERPARTY_BUCKET_FOR: dict[str, str] = {
    "supplier": "buyer",
    "buyer": "supplier",
    "service_recipient": "service_provider",
    "service_provider": "service_recipient",
    "contractor": "ordering_party",
    "ordering_party": "contractor",
    "dealer": "supplier",
}


def _type_code_from_answers(answers: dict[str, Any]) -> str | None:
    val = answers.get("Q-TYPE-001-contract-nature")
    if isinstance(val, str) and val in _ANSWER_TYPE_CODE_MAP:
        return _ANSWER_TYPE_CODE_MAP[val]
    return None


def _role_bucket_from_answers(answers: dict[str, Any]) -> str | None:
    val = answers.get("Q-ROLE-001-our-position")
    if isinstance(val, str) and val in _ANSWER_ROLE_BUCKET_MAP:
        return _ANSWER_ROLE_BUCKET_MAP[val]
    return None


# ─── Private helpers ──────────────────────────────────────────────────────────

def _has(text: str, *needles: str) -> bool:
    t = text.lower()
    return any(n.lower() in t for n in needles)


_RX_ASCII_WORD = re.compile(r"^[a-z0-9][a-z0-9 ]*[a-z0-9]$|^[a-z0-9]$")


def _has_in(haystack: str, *s: str) -> bool:
    for n in s:
        n_low = n.lower()
        if not n_low:
            continue
        if _RX_ASCII_WORD.match(n_low):
            # 순수 영문/숫자 키워드는 단어 경계로 매칭한다 — bare substring
            # 매칭은 "lease"가 "release" 안에서, "sow"가 다른 영단어 안에서
            # 우연히 걸리는 등 영문 계약서에서 오분류를 일으킨다(예: NDA에
            # "release"라는 단어가 있다고 rental로 분류됨). 한글 키워드는
            # 조사가 바로 붙는 경우가 많아 기존처럼 substring 매칭 유지.
            if re.search(rf"\b{re.escape(n_low)}\b", haystack):
                return True
        elif n_low in haystack:
            return True
    return False


def _classify_type_code(
    contract_type: str, text: str, filename: str
) -> tuple[str, list[str]]:
    combined = (contract_type + "\n" + text + "\n" + filename).lower()
    # 문서 제목 영역 — 국문 계약서는 관례상 표제에 계약 종류를 명시한다
    # ("비밀유지계약서", "컨설팅 계약서" 등). 본문 어딘가의 약한 단일
    # 키워드보다 표제가 훨씬 신뢰도 높은 신호이므로, 오탐이 잦은 특수
    # 유형(NDA 등)은 표제 신호를 필수 조건으로 요구한다.
    #
    # 주의: 여기에 raw contract_type 파라미터(UI/폼이 넘긴 자유 텍스트
    # 힌트)를 포함하지 않는다 — 2026-09-02 실사례: 이전에 검토한 NDA의
    # "NDA 비밀유지계약서"라는 값이 새 문서(전략적 파트너십 계약) 업로드에
    # 그대로 재사용되어, 실제 문서 내용과 무관하게 title 신호를 통과시켜
    # 전체 계약이 NDA로 오분류됐다. 사용자가 실제로 계약유형을 확인해준
    # 경우는 이 함수보다 먼저 적용되는 Q-TYPE-001 명시 확인 경로
    # (_type_code_from_answers)로 처리되므로, 이 title_zone은 반드시
    # 문서 자체의 신호(본문 서두·파일명)만으로 구성한다.
    title_zone = (text[:200] + "\n" + filename).lower()
    reasons: list[str] = []

    def has(*s: str) -> bool:
        return _has_in(combined, *s)

    def has_title(*s: str) -> bool:
        return _has_in(title_zone, *s)

    # ── Step -2: NDA/비밀유지계약 — 문서 전체가 비밀유지를 다루는 경우만 확정 ──
    # 물품공급·대리점 계약 등 대부분의 상용 계약에도 비밀유지 조항이 1개
    # 정도는 있는 게 정상이다 — "비밀정보"라는 단어가 문서 어딘가에 한두
    # 번 나온다고 전체를 NDA로 분류하면, 그 계약의 진짜 유형(물품공급 등)에
    # 맞는 리뷰가 오히려 스킵된다. 핵심 용어("confidential information"/
    # "비밀정보"/"기밀정보")가 문서 전체에 걸쳐 반복적으로(예: 15회 이상)
    # 나타나는 밀도로 "이 문서 자체가 비밀유지에 관한 것"인지 먼저 걸러내고,
    # 그 위에 구조적 신호(당사자 구분/반환·파기/비밀유지계약 명칭 등) 2개
    # 이상이 더해질 때만 확정한다.
    _conf_term_count = combined.count("confidential information") + combined.count("비밀정보") + combined.count("기밀정보")
    _nda_structural_signals = [
        (
            has("disclosing party", "receiving party", "공개 당사자", "수령 당사자", "제공자", "수령자")
            or (has("provider") and has("receiver") and has("confidential"))
        ),
        has("non-disclosure", "nondisclosure", "non disclosure", "비밀유지", "기밀유지"),
        has("permitted disclosure", "허용된 공개", "제3자에게 공개"),
        has("return or destroy", "return the confidential information", "반환 또는 파기", "반환하거나 파기", "즉시 파기"),
        has("confidentiality agreement", "confidentiality declaration", "비밀유지계약", "비밀유지약정", "비밀유지서약"),
    ]
    _nda_structural_count = sum(1 for s in _nda_structural_signals if s)
    # 경로 1: 표제가 스스로 NDA/비밀유지계약이라고 선언 — 국문 계약서는
    # 관례상 표제에 계약 종류를 명시하므로(예: "비밀유지서약서") 이 신호는
    # "비밀정보"라는 단어를 안 쓰는 문서(대신 "정보"로만 지칭하는 서약서
    # 등)에도 적용된다. 구조 신호 1개 이상으로만 corroborate한다.
    _title_says_nda = has_title(
        "non-disclosure", "nondisclosure", "non disclosure",
        "confidentiality agreement", "confidentiality declaration",
        "비밀유지계약", "비밀유지약정", "비밀유지서약", "비밀유지확약", "nda",
    )
    if _title_says_nda and _nda_structural_count >= 1:
        reasons.append(f"nda_confidentiality_title_signal_{_nda_structural_count}")
        return "nda_confidentiality", reasons
    # 경로 2: 표제에 명시가 없어도, "비밀정보"류 핵심 용어가 문서 전체에
    # 걸쳐 반복적으로(예: 15회 이상) 나타나는 밀도 + 구조 신호 2개 이상이면
    # 확정한다 — 컨설팅/공급계약처럼 confidentiality 조항이 1개 있을 뿐인
    # 문서는 이 밀도 기준을 넘지 않는다.
    if _conf_term_count >= 15 and _nda_structural_count >= 2:
        reasons.append(f"nda_confidentiality_term_density_{_conf_term_count}_signals_{_nda_structural_count}")
        return "nda_confidentiality", reasons

    # ── Step -1: HARD FORCE — dealer_rental_service from body text ───────────
    # 아래 3가지 문구가 모두 또는 2가지 이상 있으면 무조건 dealer_rental_service_contract
    # 파일명/캐시/contract_type 파라미터보다 본문이 우선
    _rental_dealer_body_signals = [
        "공급업자는 고객과 직접 렌탈 계약",
        "대리점은 위탁받은 범위 내에서",
        "대리점은 계약 당사자가 아니며",
        "대리점은 고객과의 렌탈계약의 당사자가 아니며",
        "공급업자는 고객(임차인)과 직접",
    ]
    _rental_dealer_hit = sum(1 for s in _rental_dealer_body_signals if s.lower() in combined)
    if _rental_dealer_hit >= 2:
        reasons.append(f"dealer_rental_body_force_{_rental_dealer_hit}signals")
        return "dealer_rental_service_contract", reasons

    # ── Step 0: Content production detection — HIGHEST priority for creative contracts ─
    # Must come before all other checks to prevent "광고" from matching ai_search_marketing.
    # Key differentiators vs ai_search_marketing:
    #   content_production: 콘텐츠 제작, 촬영, 편집, 시안, 콘티, 결과물, 저작권, 소유권 이전
    #   ai_search_marketing: AI 검색, 검색 노출, SEO, GEO, AEO, LLM, 생성형 AI 검색

    has_production_core = has(
        "콘텐츠 제작", "광고 콘텐츠", "제품 광고", "콘텐츠 제작 대행",
        "영상 제작", "촬영", "편집", "시안", "콘티", "스토리보드",
        "콘텐츠 제작 용역", "제작 대행",
    )
    has_creative_elements = has(
        "폰트", "이미지", "음원", "초상권", "모델", "촬영 장소",
        "저작권 이전", "소유권 이전", "저작재산권", "2차적저작물",
        "결과물", "산출물",
    )
    has_ai_search_specific = has(
        "ai 검색", "검색 노출", "검색 최적화", "aeo", "geo", "llm",
        "생성형 ai", "검색 알고리즘", "키워드 광고", "검색 알고리즘",
    )
    has_ad_content_or_ownership_transfer = has(
        "소유권의 귀속", "저작권 이전", "저작재산권", "2차적저작물작성권",
        "결과물 소유권", "콘텐츠 소유권",
    )

    # Advertising content production (제품 광고 콘텐츠 제작 대행)
    if has_production_core and not has_ai_search_specific:
        if has_creative_elements or has_ad_content_or_ownership_transfer:
            reasons.append("advertising_content_production_strong")
            return "advertising_content_production", reasons
        reasons.append("content_production_service_generic")
        return "content_production_service", reasons

    if has_creative_elements and has_ad_content_or_ownership_transfer and not has_ai_search_specific:
        if has("광고", "제작", "콘텐츠"):
            reasons.append("content_production_from_ip_transfer")
            return "advertising_content_production", reasons

    # ── Step 0.5: 시험·검사·인증/분석 용역 (testing/inspection/certification) ──
    # Must run before Step 5's weak ai_search_marketing check — a testing
    # agreement that merely restricts use of a test report "in advertising"
    # (성적서를 광고에 사용하지 말라는 사용제한) must NOT be classified as a
    # marketing contract just because the word "광고" appears once.
    has_testing_strong = has(
        "시험연구원", "시험기관", "검사기관", "공인시험", "공인검사",
        "인증기관", "교정기관", "시험성적서", "검사성적서",
    )
    has_testing_generic = has(
        "시험분석", "시험 분석", "시험의뢰", "시험 의뢰", "품질검사", "품질 검사",
        "검사의뢰", "인증심사", "적합성평가",
    )
    has_dealer_signal_early = has("위탁판매", "대리점", "판매대리점")
    # has_testing_strong keywords ("시험연구원"/"시험기관"/"공인시험"/"시험성적서" 등)
    # are unambiguous — a real dealer/대리점 계약서 essentially never uses them.
    # A whole-document bare keyword scan for "대리점" can trip on one incidental
    # mention anywhere in a long contract (e.g. a jurisdiction/miscellaneous
    # clause disclaiming that a test result doesn't endorse resale through
    # 대리점/유통 channels) — that single hit must not veto an otherwise
    # unambiguous testing-service classification. Only the weaker
    # has_testing_generic signals (시험분석/품질검사 등, which can plausibly
    # co-occur in a genuine dealer contract) stay subject to the dealer veto.
    if has_testing_strong:
        reasons.append("testing_inspection_service_strong_signal_priority")
        return "testing_inspection_service", reasons
    if has_testing_generic and not has_dealer_signal_early:
        reasons.append("testing_inspection_service")
        return "testing_inspection_service", reasons

    # ── Step 1: Evaluate consignment/dealer signals first ──────────────────
    # These must take priority over incidental dev-language in Article 19 etc.

    has_consignment = has("위탁판매")
    has_dealer = has("대리점", "판매대리점", "위탁판매 대리점")
    has_service_fee = has("용역수수료", "기본수수료", "추가수수료")
    has_direct_customer_signal = has(
        "검수마스터", "위탁커넥트플러스",
        "고객과 공급업자", "공급업자가 고객과", "공급업자는 고객과",
    )
    has_dealer_contract_flow = has("수주등록", "납품 일정", "수금 지원", "상품공급계약")

    # Consignment sales agency — HIGHEST dealer priority
    if has_consignment and has_dealer and (has_service_fee or has_direct_customer_signal or has_dealer_contract_flow):
        reasons.append("위탁판매_대리점_service_fee_or_direct")
        return "consignment_sales_agency", reasons

    if has_consignment and has_dealer:
        reasons.append("위탁판매_대리점_generic")
        return "consignment_sales_agency", reasons

    # Direct customer sales support
    if has_dealer and has_service_fee and has("고객") and (
        has_direct_customer_signal or has_dealer_contract_flow
    ):
        reasons.append("direct_customer_support_service_fee")
        return "direct_customer_sales_support", reasons

    # ── Step 1b: Rental + dealer = dealer_rental_service_contract ────────────
    # A rental contract where the dealer manages customer touchpoints on behalf
    # of the supplier must be classified separately from a pure "rental" contract.
    # Must come BEFORE the generic rental fallback at Step 5.
    has_rental = has("렌탈", "렌트")
    if has_rental and (has_dealer or has("대리점")):
        if has_service_fee or has_direct_customer_signal or has("위탁판매") or has("용역수수료"):
            reasons.append("dealer_rental_service_contract_service_fee")
            return "dealer_rental_service_contract", reasons
        reasons.append("dealer_rental_service_contract_generic")
        return "dealer_rental_service_contract", reasons

    # ── Step 2: Strong software/dev signals (only when no dealer context) ──
    # "소스코드" in Article 19 of a dealer contract must NOT trigger this branch.
    # Only classify as software if there are NO dealer/consignment signals.
    if not has_dealer and not has_consignment:
        if has("소스코드", "source code") and has("개발", "산출물", "deliverable"):
            reasons.append("source_code_signal")
            return "software_app_development", reasons
        if has("오픈소스", "open source", "sbom") and has("개발", "라이선스"):
            reasons.append("open_source_dev_signal")
            return "software_app_development", reasons
        if has("앱 개발", "앱개발", "소프트웨어 개발", "시스템 개발") and has("산출물", "deliverable", "sow"):
            reasons.append("app_dev_strong")
            return "software_app_development", reasons

    # ── Step 3: Store operation outsourcing ───────────────────────────────
    if has("운영대행", "위탁운영", "매장운영", "공간운영", "라운지운영", "시설운영"):
        reasons.append("store_operation_outsourcing")
        return "store_operation_outsourcing", reasons

    # ── Step 4: Standard dealer ───────────────────────────────────────────
    if has_dealer and has("대리점법", "재판매", "유통") and not has_consignment:
        reasons.append("standard_dealer_agency")
        return "dealer_agency", reasons

    if has_dealer and has("구매", "판매", "공급") and not has_consignment and not has_service_fee:
        reasons.append("dealer_agency_generic")
        return "dealer_agency", reasons

    # ── Step 5: Other specific types ─────────────────────────────────────
    if has("유통", "distributor", "resale", "재판매") and has_dealer:
        reasons.append("distribution_resale")
        return "distribution_resale", reasons

    # 물품 거래구조 신호(구매/공급/납품/대금/검수/하자/소유권) — 독립
    # 신호가 3개 이상 일치하면 "자문"/"SOW" 같은 약한 단일 키워드보다
    # supply/purchase 계열을 우선한다. 장비공급계약서가 본문 어딘가의
    # 부수적 "SOW"/"컨설팅" 언급 때문에 advisory_service로 오분류되던
    # 문제(단일 키워드 우선순위 문제, 계약유형·회사명과 무관한 일반
    # 판단 기준) 방지.
    # 영문 신호는 "payment"/"warranty"/"title"처럼 어떤 계약에서나 흔히
    # 쓰이는 단어 대신, 물품거래 계약에서만 통상 나타나는 복합 어구로
    # 한정한다 — 그렇지 않으면 NDA의 통상적인 면책·소유권 조항 몇 개만
    # 겹쳐도 물품공급계약으로 오분류된다.
    _goods_trade_signals = [
        has("구매", "매매", "purchase order", "purchase agreement", "purchase price"),
        has("공급", "supply agreement", "equipment supply"),
        has("납품", "delivery date", "delivery of goods"),
        has("대금", "계약금액", "contract price", "purchase price"),
        has("검수", "acceptance inspection", "goods inspection"),
        has("하자", "defect liability", "warranty period"),
        has("소유권", "title to the goods", "transfer of ownership"),
    ]
    _goods_trade_count = sum(1 for s in _goods_trade_signals if s)
    if _goods_trade_count >= 3:
        if has("장비", "설치", "시운전", "equipment", "installation"):
            reasons.append(f"equipment_purchase_installation_strong_{_goods_trade_count}signals")
            return "equipment_purchase_installation", reasons
        reasons.append(f"purchase_supply_strong_{_goods_trade_count}signals")
        return "purchase_supply", reasons

    if has("자문", "컨설팅", "consulting", "sow", "statement of work") and not has_dealer:
        reasons.append("advisory_service")
        return "advisory_service", reasons

    if has("장비", "설치", "시운전") and has("구매", "공급", "납품"):
        reasons.append("equipment_purchase_installation")
        return "equipment_purchase_installation", reasons

    if has("구매", "매매", "purchase") and has("공급", "supply"):
        reasons.append("purchase_supply")
        return "purchase_supply", reasons

    if has("렌탈", "렌트", "임대차", "lease"):
        reasons.append("rental")
        return "rental", reasons

    if has("공사", "도급", "하도급", "시공", "construction"):
        reasons.append("construction")
        return "construction", reasons

    # ai_search_marketing: ONLY when AI/search-specific signals are present.
    # A single incidental word ("광고", "검색", "노출") anywhere in the document
    # (e.g. a usage-restriction clause like "성적서를 광고에 사용하지 말 것") is
    # NOT sufficient — that previously misclassified unrelated contracts
    # (e.g. a testing-service agreement) as marketing contracts. Require the
    # marketing keyword to co-occur with a service/contract-purpose signal.
    if has_ai_search_specific:
        reasons.append("ai_search_marketing_explicit")
        return "ai_search_marketing", reasons
    _has_marketing_purpose_context = has(
        "마케팅 대행", "마케팅 용역", "마케팅 서비스", "광고 대행", "광고 캠페인",
        "광고 집행", "매체 광고", "온라인 광고", "디지털 마케팅", "퍼포먼스 마케팅",
    )
    if _has_marketing_purpose_context and not has_production_core:
        reasons.append("ai_search_marketing_generic")
        return "ai_search_marketing", reasons

    # Weak app/dev (only when no dealer) — "개발" 단독은 노하우·기술을
    # 언급하는 거의 모든 계약(NDA 포함)에서 우연히 나타날 수 있는 약한
    # 단일 키워드이므로, 최소 2개 이상의 독립 신호가 있을 때만 확정한다.
    _weak_dev_signals = [has("개발"), has("유지보수"), has("saas"), has("api 연동")]
    if not has_dealer and sum(1 for s in _weak_dev_signals if s) >= 2:
        reasons.append("software_weak")
        return "software_app_development", reasons

    # Generic dealer fallback
    if has_dealer:
        reasons.append("dealer_generic_fallback")
        return "dealer_agency", reasons

    reasons.append("no_strong_signal")
    return "general", reasons


def _detect_counterparty(text: str, our_party: str) -> str:
    t = text or ""
    our_lower = our_party.lower() if our_party else ""

    # Pattern -1: "OO(이하 "갑"이라 한다)"류 정의 문장으로 회사명↔갑/을 라벨이
    # 명시적으로 바인딩되는 경우 — 아래의 "을(회사명, 이하 ...)" 스타일
    # 패턴들은 이 계약처럼 회사명이 괄호 앞에 오는 형식("㈜웹젠(이하 "갑"
    # 이라 한다)")은 인식하지 못해 상대방명이 깨지거나 비게 된다.
    from runtime.review.party_label_binding import bound_counterparty_name
    _bound = bound_counterparty_name(t, our_party)
    if _bound:
        return _bound

    # Pattern 0: "을(수탁자): 주식회사 XXX" format (content production contracts)
    m = re.search(
        r"을\s*\((?:수탁자|대리점|을)\)\s*[:：]\s*(?:주식회사|㈜|㈜?\s*)?\s*([가-힣a-zA-Z0-9\s]{2,30}?)\s*(?:\(|$)",
        t
    )
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() not in (our_lower, "갑", "을") and len(candidate) >= 2:
            return candidate

    # Pattern 1: 을(㈜XXX, 이하 "을") or 을(XXX, 이하) — handles ㈜ prefix
    m = re.search(
        r"을\s*\(\s*(?:㈜|주식회사|㈜\s*)?([가-힣a-zA-Z0-9\s]{2,30}?)\s*[,，]\s*이하",
        t
    )
    if m:
        candidate = m.group(1).strip()
        # Exclude our party and generic labels
        if (candidate.lower() not in (our_lower, "갑", "을", "발주자", "도급인", "구매자")
                and len(candidate) >= 2):
            return candidate

    # Pattern 2: 갑과 을 구조에서 을 추출
    m = re.search(
        r"(?:갑|갑\().*?(?:과|와|이)\s*(?:㈜|주식회사|㈜\s*)?([가-힣a-zA-Z0-9\s]{2,30}?)\s*\(",
        t
    )
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() not in (our_lower, "을", "갑") and len(candidate) >= 2:
            return candidate

    # Pattern 3: explicit keyword patterns
    m = re.search(r"을\s*\(\s*(?:주\.)?\s*([가-힣a-zA-Z0-9]{2,20})\s*[,，]\s*이하\s*['\"]?수탁자['\"]?", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"을\s*\(\s*(?:주\.)?\s*([가-힣a-zA-Z0-9]{2,20})\s*[,，]\s*이하\s*['\"]?대리점['\"]?", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"대리점\s*:\s*(?:주\.)?\s*([가-힣a-zA-Z0-9]{2,20})", t)
    if m:
        return m.group(1).strip()

    # Pattern 4: specific company names known to be counterparties
    _KNOWN_COMPANIES = [
        ("스카이인텔리전스", r"스카이인텔리전스|스카이\s*인텔리전스|SKAI"),
    ]
    for name, pattern in _KNOWN_COMPANIES:
        if re.search(pattern, t, re.IGNORECASE):
            return name

    if "대리점" in t:
        return "대리점"
    if "수탁자" in t or "수급인" in t:
        return "수탁자"
    if "구매자" in t or "발주자" in t:
        return "구매자"
    return "상대방"


def _infer_legal_roles(
    type_code: str, contract_type: str, text: str, entity: str = ""
) -> tuple[str, str]:
    # purchase_supply/equipment_purchase_installation은 거래방향이 대칭적
    # 이다 — 우리가 물품을 사는 쪽일 수도, 파는(제작·설치하는) 쪽일 수도
    # 있어 type_code만으로는 판단할 수 없다("웹젠은 퍼시스로부터 가구를
    # 구매한다"인데 퍼시스=buyer로 고정 분류되던 사고). 계약문에 "OO(이하
    # "갑"이라 한다)"류 정의와 "매도인으로서" 자기선언 또는 "OO로부터 ...
    # 구매한다" 같은 거래방향 문언이 명시되어 있으면 그 신호를 우선한다
    # (변호사형 전체계약 판단 지시, 2026-08-31). party_role.py도 같은
    # party_label_binding 모듈을 공유해 동일한 결론에 도달한다.
    if type_code in ("purchase_supply", "equipment_purchase_installation"):
        from runtime.review.party_label_binding import (
            bind_party_labels_to_entities, explicit_role_from_labels, role_word_near_entity,
        )
        _bind = bind_party_labels_to_entities(text or "", entity or "")
        _explicit = None
        if _bind is not None:
            _our_lbl, _cp_lbl = _bind
            _explicit = explicit_role_from_labels(text or "", _our_lbl, _cp_lbl)
        if _explicit is None:
            # "(이하 ...)" 정의문 없이 "매도인 퍼시스를 (을)이라 칭한다"처럼
            # 역할 명사가 회사명 바로 옆에 오는 형식에 대한 fallback.
            _explicit = role_word_near_entity(text or "", entity or "")
        if _explicit == "supplier":
            return "supplier", "buyer"
        if _explicit == "buyer":
            return "buyer", "seller_or_supplier"

    if type_code in ("advertising_content_production", "content_production_service", "creative_agency_service"):
        return "도급인/발주자/콘텐츠 사용권자", "콘텐츠 제작 수탁자"
    if type_code == "consignment_sales_agency":
        return "supplier", "consignment_dealer"
    if type_code == "direct_customer_sales_support":
        return "supplier", "sales_support_agent"
    if type_code == "dealer_rental_service_contract":
        return "supplier", "rental_service_dealer"
    if type_code in ("dealer_agency", "distribution_resale"):
        return "supplier", "dealer"
    if type_code == "purchase_supply":
        return "buyer", "seller_or_supplier"
    if type_code == "equipment_purchase_installation":
        return "buyer", "vendor_installer"
    if type_code == "store_operation_outsourcing":
        return "principal", "operator"
    if type_code == "advisory_service":
        return "client", "advisor"
    if type_code == "testing_inspection_service":
        return "시험의뢰인(위탁자)", "시험수행기관(수탁자)"
    if type_code in ("software_app_development", "ai_search_marketing"):
        return "ordering_party", "developer"
    if type_code == "rental":
        return "renter", "rental_provider"
    if type_code == "construction":
        return "ordering_party", "contractor"
    if type_code == "nda_confidentiality":
        return "계약당사자(비밀유지)", "계약당사자(비밀유지)"
    return "unknown", "unknown"


def _infer_customer_contract_details(
    text: str, our_party: str
) -> dict[str, Any]:
    t = text or ""
    unresolved: list[str] = []

    _direct_signals = [
        "공급업자는 고객과 직접",
        "공급업자가 고객과 직접",
        "공급업자와 고객 간 계약",
        "고객과 공급업자가 직접",
        "공급업자와 고객이 직접",
        "공급업자와 최종 소비자 간의",
        "공급업자와 최종소비자 간의",
        "임대인과 고객이 직접",
        "임대인인 공급업자",
        "고객과 직접 렌탈",
        "공급업자와 고객 간 렌탈",
        "공급업자는 고객(임차인)과 직접",
    ]
    # 대리점이 계약 당사자인 것처럼 기술하는 신호 (HIGH 리스크)
    _dealer_contracts_signals = [
        "대리점은 고객과 계약",
        "대리점은 고객에게 판매",
        "대리점은 최종소비자에게",
        "위탁받은 상품을 최종소비자에게 판매",
    ]
    # 대리점 "지원" 역할임을 명시 (고객계약서 작성 지원, 수금 지원)
    _dealer_support_signals = [
        "대리점은 위탁받은 범위 내에서",
        "대리점은 계약 당사자가 아니며",
        "공급업자의 사전 서면 동의 없이 공급업자를 대리",
        "고객 발굴, 상담",
    ]
    _supplier_invoice_signals = [
        "공급업자가 세금계산서",
        "공급업자가 발행",
        "공급자가 세금계산서",
        # 퍼시스 이름 직접 언급 패턴
        "세금계산서는 퍼시스가",
        "세금계산서를 퍼시스가",
        "퍼시스가 고객에게 세금계산서",
        "세금계산서는 공급업자",
        "세금계산서 발행일(익월",  # 표준 렌탈계약서 패턴
        "세금계산서는 퍼시스",
        "법적 주체는 공급업자",
        "법적 주체는 공급업자",
    ]
    _dealer_invoice_signals = [
        "대리점은 고객에게 세금계산서",
        "각종 법률이 규정하고 있는 의무를 수행",
        "세금계산서 발행 및 대금의 청구",
    ]

    has_direct = any(s in t for s in _direct_signals)
    has_dealer_support = any(s in t for s in _dealer_support_signals)
    has_dealer_contracts = any(s in t for s in _dealer_contracts_signals) and not has_dealer_support
    has_supplier_invoice = any(s in t for s in _supplier_invoice_signals)
    has_dealer_invoice = any(s in t for s in _dealer_invoice_signals)

    # 공급업자 이름 포함 세금계산서 패턴 추가 검색
    if our_party and our_party != "미상":
        party_invoice_patterns = [
            f"세금계산서는 {our_party}",
            f"{our_party}가 세금계산서",
            f"{our_party}가 고객에게 세금계산서",
        ]
        if any(p in t for p in party_invoice_patterns):
            has_supplier_invoice = True

    # Customer contracting party
    # dealer_rental_service 핵심 구조: 공급업자가 고객과 직접 계약
    # 대리점이 "고객과 계약서 작성"이라고 기술되어 있어도 실제로는 지원 역할이므로
    # has_direct 신호가 있으면 공급업자를 우선 적용
    if has_direct or has_dealer_support:
        ccp = our_party if our_party and our_party != "미상" else "공급업자"
    elif has_dealer_contracts:
        ccp = "needs_clarification_with_high_risk"
        unresolved.append("대리점이 고객과 직접 계약하는 것처럼 기술됨 — 거래구조 HIGH 리스크")
    else:
        ccp = "needs_clarification_with_high_risk"
        unresolved.append("고객과의 계약 당사자가 명확히 특정되지 않음")

    # Tax invoice issuer
    if has_supplier_invoice:
        tii = our_party if our_party and our_party != "미상" else "공급업자"
    elif has_dealer_invoice and not has_direct:
        # 공급업자가 직접 계약 신호가 있으면 대리점 이슈도 지원 역할로 해석
        tii = "needs_clarification_with_high_risk"
        unresolved.append("세금계산서 발행 주체가 대리점으로 기재되어 있어 구조 불일치 HIGH 리스크")
    else:
        tii = None

    # Payment collection party — dealer_support 신호 있으면 대리점은 수금 지원자
    has_dealer_collects_hard = any(s in t for s in [
        "대금수금의 책임",
    ])
    has_dealer_collects_soft = any(s in t for s in [
        "수금 업무를 성실히",
        "수요자의 대금지급이 이루어질 수 있도록",
        "대금의 청구 및 수금 업무를 수행",
    ])
    if has_dealer_collects_hard:
        pcp = "needs_clarification_with_high_risk"
        unresolved.append("대금 수금 책임이 대리점에게 부과됨 — 대리점법 불이익 제공 리스크")
    elif has_dealer_collects_soft and (has_direct or has_dealer_support):
        # 렌탈대리점: 대리점은 수금 "지원"이지 법적 주체가 아님
        pcp = our_party if our_party and our_party != "미상" else "공급업자"
    elif has_dealer_collects_soft:
        pcp = "needs_clarification_with_high_risk"
        unresolved.append("대금 수금 책임이 대리점에게 부과됨 — 대리점법 불이익 제공 리스크")
    else:
        pcp = our_party if our_party and our_party != "미상" else "공급업자"

    # Agency authority
    has_agency_denied = "공급업자를 대리하여" in t and "할 수 없다" in t
    agency_authority: bool | None = False if has_agency_denied else None

    return {
        "customer_contracting_party": ccp,
        "payment_collection_party": pcp,
        "tax_invoice_issuer": tii,
        "agency_authority": agency_authority,
        "unresolved": unresolved,
    }


def _compute_confidence(type_code: str, reasons: list[str], text: str) -> float:
    strong_types = {
        "consignment_sales_agency",
        "dealer_rental_service_contract",
        "software_app_development",
        "rental",
        "construction",
        "store_operation_outsourcing",
        "testing_inspection_service",
    }
    if "no_strong_signal" in reasons:
        return 0.40
    if type_code in strong_types and len(reasons) >= 1:
        return 0.88
    if type_code == "general":
        return 0.40
    return 0.75
