"""상대방(counterparty) 역할 분류 — 협상 전략을 상대방 유형에 따라
달리 적용하기 위한 범용 신호 기반 분류(2026-09-04 지시, Senior In-house
Counsel 판단 레이어).

계약유형이나 조항번호가 아니라, 계약 전문에 등장하는 키워드 신호로
상대방이 정부/지원기관인지, 일반 고객인지, 공급자인지 등을 판단한다.
어느 신호도 없으면 "unknown"을 반환한다 — 임의로 단정하지 않는다.
"""
from __future__ import annotations

import re

_RX_GOVERNMENT_OR_FUNDING = re.compile(
    r"KOTRA|중소벤처기업부|산업통상자원부|고용노동부|한국산업기술진흥원|정부\s*지원|"
    r"보조금|지원사업|국고보조|공단|진흥원|지자체|지방자치단체|"
    r"government\s+(?:agency|entity|body)|funding\s+agency|grant\s+agreement|"
    r"public\s+(?:institution|agency)",
    re.IGNORECASE,
)
_RX_CUSTOMER = re.compile(
    r"고객|수요자|발주자|구매자|주문자|이용자|소비자|"
    r"\bcustomer\b|\bclient\b|\bbuyer\b|\bpurchaser\b",
    re.IGNORECASE,
)
_RX_SUPPLIER = re.compile(
    r"공급자|제조사|납품업체|벤더|\bsupplier\b|\bvendor\b|\bmanufacturer\b",
    re.IGNORECASE,
)
_RX_CONSULTANT = re.compile(
    r"컨설턴트|자문사|용역사|\bconsultant\b|\badvisor\b",
    re.IGNORECASE,
)
_RX_LICENSOR = re.compile(
    r"라이선서|사용허락자|\blicensor\b|\blicense\s*agreement\b",
    re.IGNORECASE,
)
_RX_LANDLORD = re.compile(
    r"임대인|임대차|\blandlord\b|\blessor\b|\blease\s*agreement\b",
    re.IGNORECASE,
)
_RX_DISTRIBUTOR = re.compile(
    r"대리점|판매점|딜러|유통업자|\bdistributor\b|\breseller\b|\bdealer\b",
    re.IGNORECASE,
)


def classify_counterparty_role(text: str) -> str:
    """계약 전문 텍스트에서 상대방 역할을 분류한다.

    반환값: "government_or_funding_agency" | "customer" | "supplier" |
    "consultant" | "licensor" | "landlord" | "distributor" | "unknown"

    정부/지원기관 신호가 가장 강한 협상력 비대칭을 의미하므로 최우선으로
    확인한다.
    """
    t = text or ""
    if not t.strip():
        return "unknown"
    if _RX_GOVERNMENT_OR_FUNDING.search(t):
        return "government_or_funding_agency"
    if _RX_DISTRIBUTOR.search(t):
        return "distributor"
    if _RX_LANDLORD.search(t):
        return "landlord"
    if _RX_LICENSOR.search(t):
        return "licensor"
    if _RX_CONSULTANT.search(t):
        return "consultant"
    if _RX_SUPPLIER.search(t):
        return "supplier"
    if _RX_CUSTOMER.search(t):
        return "customer"
    return "unknown"
