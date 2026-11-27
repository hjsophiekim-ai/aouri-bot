"""국제계약 유형과 룰 계열 게이트.

canonical 계약 유형(`contract_classifier` 가 정하는 세부 코드)은 그대로 둔다 — NDA·물품공급 등 기존 엔진이 그 코드로
돈다. 국제계약이면 같은 판정 결과를 **국제 계열 유형**(international_*)으로 사상해 `canonical_state.international_type`
에 싣고, 국제 체크리스트와 국내 전용 룰 게이트가 그 값을 읽는다. 사상 표는 여기 한 곳에만 둔다.
"""
from __future__ import annotations

import re

INTERNATIONAL_SALE_OF_GOODS = "international_sale_of_goods"
INTERNATIONAL_DISTRIBUTION = "international_distribution"
INTERNATIONAL_LICENSE = "international_license"
INTERNATIONAL_SERVICES = "international_services"
INTERNATIONAL_NDA = "international_nda"
INTERNATIONAL_MOU_JV = "international_mou_jv"

INTERNATIONAL_TYPES = (INTERNATIONAL_SALE_OF_GOODS, INTERNATIONAL_DISTRIBUTION, INTERNATIONAL_LICENSE,
                       INTERNATIONAL_SERVICES, INTERNATIONAL_NDA, INTERNATIONAL_MOU_JV)

INTERNATIONAL_TYPE_LABELS = {
    INTERNATIONAL_SALE_OF_GOODS: "국제 물품매매(수출입·공급)",
    INTERNATIONAL_DISTRIBUTION: "해외 대리점·총판·독점판매",
    INTERNATIONAL_LICENSE: "국제 라이선스(상표·기술·저작권)",
    INTERNATIONAL_SERVICES: "해외 용역·자문·개발",
    INTERNATIONAL_NDA: "국제 비밀유지계약",
    INTERNATIONAL_MOU_JV: "MOU·LOI·합작·공동투자",
}

#: 국내 세부 코드 → 국제 계열.
_BASE_TO_INTERNATIONAL = {
    "purchase_supply": INTERNATIONAL_SALE_OF_GOODS,
    "equipment_purchase_installation": INTERNATIONAL_SALE_OF_GOODS,
    "online_sales_supply": INTERNATIONAL_SALE_OF_GOODS,
    "distribution_resale": INTERNATIONAL_DISTRIBUTION,
    "dealer_agency": INTERNATIONAL_DISTRIBUTION,
    "consignment_sales_agency": INTERNATIONAL_DISTRIBUTION,
    "nda_confidentiality": INTERNATIONAL_NDA,
    "advisory_service": INTERNATIONAL_SERVICES,
    "software_app_development": INTERNATIONAL_SERVICES,
    "testing_inspection_service": INTERNATIONAL_SERVICES,
    "content_production_service": INTERNATIONAL_SERVICES,
    "advertising_content_production": INTERNATIONAL_SERVICES,
}

# 본문 구조 신호 — 세부 코드가 일반값(general/unknown)이거나 본문이 더 분명할 때 쓴다. 순서가 우선순위.
_STRUCTURE: tuple[tuple[str, re.Pattern[str]], ...] = (
    (INTERNATIONAL_MOU_JV, re.compile(r"Memorandum\s+of\s+Understanding|\bMOU\b|Letter\s+of\s+Intent|\bLOI\b|양해각서|Joint\s+Venture"
                                      r"|합작|공동\s*투자|shareholders'?\s+agreement", re.I)),
    (INTERNATIONAL_NDA, re.compile(r"Non[- ]?Disclosure\s+Agreement|Confidentiality\s+Agreement|비밀\s*유지\s*(?:계약|약정)", re.I)),
    (INTERNATIONAL_LICENSE, re.compile(r"License\s+Agreement|Licen[cs]e\s+Agreement|Trade\s*mark\s+License|라이선스\s*계약|사용권\s*허락"
                                       r"|\bLicensor\b|\bLicensee\b|royalt(?:y|ies)|로열티", re.I)),
    (INTERNATIONAL_DISTRIBUTION, re.compile(r"Distribut(?:ion|or)\s+Agreement|Dealer\s+Agreement|exclusive\s+(?:distributor|dealer)"
                                            r"|대리점\s*계약|총판|독점\s*판매|\bTerritory\b", re.I)),
    (INTERNATIONAL_SALE_OF_GOODS, re.compile(r"Incoterms|\b(?:EXW|FCA|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b|Purchase\s+Order|Proforma\s+Invoice"
                                             r"|Supply\s+Agreement|Sale(?:s)?\s+(?:and\s+Purchase\s+)?Agreement|OEM|매매\s*계약|공급\s*계약|수입|수출", re.I)),
    (INTERNATIONAL_SERVICES, re.compile(r"Services?\s+Agreement|Consult(?:ing|ancy)\s+Agreement|Statement\s+of\s+Work|용역\s*계약|자문\s*계약", re.I)),
)

#: 국내 전용 룰 계열과 그 룰이 허용되는 국제 유형. 여기 없는 국제 유형에서는 그 계열을 끈다.
_DOMESTIC_ONLY_FAMILIES: dict[str, frozenset[str]] = {
    "consumer_sales": frozenset(),                                   # 소비자 대면 판매 — 국제 B2B 계약에서는 끈다
    "dealer_rental": frozenset(),                                    # 국내 딜러 렌탈(DLR)
    "consignment": frozenset({INTERNATIONAL_DISTRIBUTION}),          # 위탁판매 전략
    "subcontract": frozenset({INTERNATIONAL_SERVICES}),              # 하도급법
    "dealer_act": frozenset(),                                       # 대리점법(국내 공정거래)
    "privacy": frozenset({INTERNATIONAL_SERVICES, INTERNATIONAL_NDA, INTERNATIONAL_DISTRIBUTION}),
}


#: 근로관계 계약 — 그 나라 강행 근로법이 우선하므로 상거래용 국제계약 체크리스트의 대상이 아니다(근로자 서약 전용 엔진이 본다).
_RX_EMPLOYMENT = re.compile(
    r"\(\s*(?:the\s+)?[\"“]?(?:Employee|Employer)[\"”]?\s*\)|Employment\s+Agreement|Employee\s+(?:Confidentiality|Non-?Disclosure|Proprietary)"
    r"|근로\s*계약|고용\s*계약|임직원\s*(?:비밀|보안)|근로자\s*(?:비밀|서약)|직원\s*(?:비밀|보안)\s*서약", re.I)


def is_employment_contract(text: str) -> bool:
    return bool(_RX_EMPLOYMENT.search(str(text or "")[:6000]))


def international_type_for(base_type_code: str, text: str) -> str:
    """국제계약이면 국제 계열 유형, 아니면 ""(호출부가 국제계약 여부를 먼저 판정한다). 근로관계 계약은 ""."""
    t = str(text or "")
    if is_employment_contract(t):
        return ""
    head = t[:6000]
    for code, rx in _STRUCTURE[:4]:
        # MOU·NDA·라이선스·대리점은 제목·서두의 명시가 세부 코드보다 앞선다
        if rx.search(head[:800]):
            return code
    mapped = _BASE_TO_INTERNATIONAL.get(str(base_type_code or ""))
    if mapped:
        return mapped
    for code, rx in _STRUCTURE:
        if rx.search(head):
            return code
    return INTERNATIONAL_SALE_OF_GOODS if re.search(r"물품|goods|products?", head, re.I) else INTERNATIONAL_SERVICES


def rule_family_allowed(international_type: str, family: str) -> bool:
    """국제계약 유형에서 그 룰 계열을 돌려도 되는가. 국내 계약("")이면 늘 True."""
    if not international_type:
        return True
    allowed = _DOMESTIC_ONLY_FAMILIES.get(family)
    if allowed is None:
        return True
    return international_type in allowed
