"""Transaction Reconstruction — 온라인 판매·공동구매·판매대행을 수반하는 제품공급 계약.

2026-10-01 지시 (와이어드컴퍼니 계약 Golden Fix)
──────────────────────────────────────────────
실측: 일룸이 제품을 공급하고 와이어드컴퍼니가 SNS·쇼핑몰에서 공동구매로 파는 계약이
최초 초안에서는 "광고매체 집행 계약"(SNS·프로모션·광고 낱말), 법무팀 수정본에서는
"물품 구매·공급 계약"(상대방 = 구매자)으로 분류됐다. 그 뒤의 체크리스트·질문·finding 이
전부 그 유형으로 돌아 광고매체 송출 조항(ADM-*), 구매자 상계 제한 같은 엉뚱한 논점이 나왔다.

이 모듈은 분류기보다 먼저 **거래 실질**을 세운다.

    공급자          제품을 만들어 공급한다(우리: 일룸)
    판매채널 운영자  자기 SNS·쇼핑몰에서 판매·프로모션을 한다(와이어드)
    결제 흐름        Case A 공급자 결제창 — 고객 → 공급자, 공급자가 판매수수료 지급
                    Case B 판매자(·대행사) 결제창 — 고객 → 판매자, 판매자가 공급대금 지급
    정산 대행자      계약당사자가 아닌 자회사 등 — 대행해도 지급책임은 판매자에게 남는다
    제3자 셀러       판매자가 다시 맡기는 판매자(스마트스토어·셀러)

세 신호(공급·판매채널·정산)가 모두 있어야 확정한다. 확신하지 못하면 아무것도 바꾸지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CANONICAL_TYPE = "online_sales_supply"
LABEL = "온라인 공동구매·판매대행을 수반하는 제품판매 및 공급계약"
SUPPLIER_ROLE_LABEL = "공급사(상품 제조·공급자)"
SELLER_ROLE_LABEL = "판매사(판매채널 운영·판매·프로모션 수행자)"

_RX_SUPPLY = re.compile(r"(?:상품|제품)[^.\n]{0,25}(?:공급|입고|납품)|공급(?:하는|한)\s*(?:상품|제품)|공급사|메이커")
_RX_CHANNEL = re.compile(r"쇼핑몰|SNS|판매채널|공동구매|공구|스마트스토어|인터넷\s*판매|온라인\s*판매")
_RX_SETTLEMENT = re.compile(r"판매수수료|공급가|정산|판매대금|판매수익")
_RX_OPERATES = re.compile(
    r"[“\"']?([가-힣A-Za-z]{1,8})[”\"']?(?:가|이|은|는)\s*운영하는\s*(?:SNS|쇼핑몰|인터넷|판매채널|온라인)"
)
_RX_ALIAS = re.compile(r"(\S{2,30}?)\s*\(\s*이하\s*[“\"']\s*([^”\"']{1,10})\s*[”\"']")

#: Case A — 공급자가 고객 대금을 받는다.
_RX_SUPPLIER_COLLECTS = re.compile(
    r"(?:공급사|메이커|공급자)[”\"']?(?:는|가)?\s*고객으로부터[^.\n]{0,30}(?:직접\s*)?수취"
    r"|(?:공급사|메이커)[”\"']?\s*결제창"
    r"|판매수수료를[^.\n]{0,30}(?:판매사|회사)[”\"']?에(?:게)?\s*지급"
)
#: Case B — 판매자(또는 대행사)가 고객 대금을 받고 공급대금을 지급한다.
_RX_SELLER_COLLECTS = re.compile(
    r"(?:판매사|회사)[”\"']?\s*결제창"
    r"|현금화하여[^.\n]{0,20}지급"
    r"|정산금의?\s*(?:산정\s*및\s*)?지급"
    r"|공급가[^.\n]{0,40}(?:지급|결제)"
)
_RX_AGENT = re.compile(
    r"(?:자회사인?|100%\s*자회사인)\s*([가-힣A-Za-z]{2,12}?)(?:\s*주식회사|\s*㈜|에서|에게|에|이|가|\s)"
)
_RX_AGENT_DELEGATION = re.compile(r"대행(?:하게|시킬|할)|담당한다|대행")
_RX_AGENT_RETAINED = re.compile(
    r"이\s*경우에도[^.\n]{0,60}(?:지급\s*의무|책임)[^.\n]{0,40}(?:판매사|회사)[”\"']?(?:가|이)?\s*부담"
    r"|(?:지급\s*의무|지급\s*책임)[^.\n]{0,30}(?:판매사|회사)[”\"']?에(?:게)?\s*(?:남|있)"
)
_RX_THIRD_SELLER = re.compile(r"제\s*3\s*의\s*판매자|제3자를\s*통하여[^.\n]{0,20}판매|셀러|스마트스토어")

_ELEMENTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("상품공급", re.compile(r"공급|입고|납품")),
    ("공동구매/프로모션", re.compile(r"공동구매|공구|프로모션")),
    ("판매채널 운영", re.compile(r"쇼핑몰|SNS|판매채널")),
    ("판매수수료/정산", re.compile(r"판매수수료|정산")),
    ("제3자 셀러 활용", _RX_THIRD_SELLER),
    ("소비자 판매", re.compile(r"고객|소비자")),
    ("제조물책임", re.compile(r"제조물")),
    ("개인정보 처리", re.compile(r"개인정보")),
)


@dataclass
class OnlineSalesModel:
    confident: bool = False
    basis: str = ""
    supplier_label: str = ""
    seller_label: str = ""
    our_side: str = ""                 # "supplier" | "seller" | ""
    payment_flows: list[str] = field(default_factory=list)   # "supplier_collects" | "seller_collects"
    flows_separated: bool = False      # 결제창별로 나눠 정했는가
    payment_agent: str = ""
    payment_agent_retained: bool = False
    third_party_sellers: bool = False
    elements: list[str] = field(default_factory=list)

    @property
    def canonical_contract_type(self) -> str:
        return CANONICAL_TYPE if self.confident else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "confident": self.confident,
            "basis": self.basis,
            "canonical_contract_type": self.canonical_contract_type,
            "label": LABEL if self.confident else "",
            "supplier_label": self.supplier_label,
            "seller_label": self.seller_label,
            "our_side": self.our_side,
            "payment_flows": list(self.payment_flows),
            "flows_separated": self.flows_separated,
            "payment_agent": self.payment_agent,
            "payment_agent_retained": self.payment_agent_retained,
            "third_party_sellers": self.third_party_sellers,
            "elements": list(self.elements),
        }


def _aliases(text: str) -> list[tuple[str, str]]:
    """서두의 (당사자 표기, 약칭)."""
    head = text[:1500]
    return [(m.group(1).strip(), m.group(2).strip()) for m in _RX_ALIAS.finditer(head)]


def resolve_online_sales_model(*, contract_text: str, entity: str = "") -> OnlineSalesModel:
    body = str(contract_text or "")
    model = OnlineSalesModel()
    n_supply = len(_RX_SUPPLY.findall(body))
    n_channel = len(_RX_CHANNEL.findall(body))
    n_settle = len(_RX_SETTLEMENT.findall(body))
    m_op = _RX_OPERATES.search(body)
    if not (n_supply >= 2 and n_channel >= 3 and n_settle >= 2 and m_op):
        return model

    aliases = _aliases(body)
    seller = m_op.group(1)
    if seller not in {a for _, a in aliases} and aliases:
        # "판매사가 운영하는" 이 약칭과 다르게 적혔으면(조사 등) 가장 비슷한 약칭으로.
        seller = next((a for _, a in aliases if a in seller or seller in a), seller)
    others = [a for _, a in aliases if a != seller]
    supplier = others[0] if others else ""
    if not supplier:
        return model

    model.confident = True
    model.supplier_label = supplier
    model.seller_label = seller
    model.basis = (f"공급 {n_supply}·판매채널 {n_channel}·정산 {n_settle} 신호, "
                   f"'{seller}'가 판매채널을 운영")

    # 우리 쪽 — 계열사 registry 로 서두의 법인명을 판정한다.
    try:
        from runtime.review.group_entities import resolve_entity

        for name, alias in aliases:
            if resolve_entity(name) is not None or (entity and entity in name):
                model.our_side = "supplier" if alias == supplier else "seller" if alias == seller else ""
                break
    except Exception:  # noqa: BLE001 - 판정 실패 시 우리 쪽을 비워 둔다
        pass

    flat = re.sub(r"\s*\n\s*", " ", body)
    if _RX_SUPPLIER_COLLECTS.search(flat):
        model.payment_flows.append("supplier_collects")
    if _RX_SELLER_COLLECTS.search(flat):
        model.payment_flows.append("seller_collects")
    model.flows_separated = bool(re.search(r"결제창[^.\n]{0,80}(?:경우|때)[^.\n]{0,200}결제창[^.\n]{0,80}(?:경우|때)", flat)) \
        and bool(re.search(r"(?:공급사|메이커)[”\"']?\s*결제창[^.\n]{0,120}(?:지급|정산)", flat)) \
        and bool(re.search(r"(?:판매사|회사)[”\"']?\s*결제창[^.\n]{0,120}(?:지급|정산)", flat))
    m_agent = _RX_AGENT.search(flat)
    if m_agent and _RX_AGENT_DELEGATION.search(flat[m_agent.start(): m_agent.start() + 200]):
        model.payment_agent = m_agent.group(1)
        model.payment_agent_retained = bool(_RX_AGENT_RETAINED.search(flat))
    model.third_party_sellers = bool(_RX_THIRD_SELLER.search(flat))
    model.elements = [label for label, rx in _ELEMENTS if rx.search(flat)]
    return model


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _j(word: str, with_b: str, without_b: str) -> str:
    last = word[-1:] if word else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_b if has else without_b)


def payment_flow_finding(model: OnlineSalesModel, clauses: list[Any] | None) -> list[dict[str, Any]]:
    """지시 6항 — 결제창별 자금흐름을 먼저 재구성한다.

    Case A(공급자 결제창)와 Case B(판매자·대행사 결제창)가 한 계약에 함께 적혀 있는데
    나뉘어 있지 않거나, 정산 대행자에게 맡기면서 판매자의 지급책임을 남겨 두지 않았으면
    정산 조항 하나에 최소 문구를 붙인다. 실제 결제창 운영 방식은 사실확인 사항이다.
    """
    if not model.confident or model.our_side == "seller":
        return []
    mixed = len(model.payment_flows) >= 2 and not model.flows_separated
    unretained = bool(model.payment_agent) and not model.payment_agent_retained
    if not (mixed or unretained):
        return []
    sup, sel = model.supplier_label, model.seller_label
    agent = model.payment_agent or "정산 대행자"
    settle = [c for c in clauses or [] if re.search(r"정산|결제창|판매대금", _attr(c, "text"))]
    if not settle:
        return []

    def _score(c: Any) -> int:
        t = re.sub(r"\s*\n\s*", " ", _attr(c, "text"))
        return (3 * bool(re.search(r"결제창|자회사|대행", t)) + 2 * bool(_RX_SUPPLIER_COLLECTS.search(t))
                + bool(re.search(r"정산", _attr(c, "title"))))

    anchor = max(settle, key=_score)
    parts = []
    if mixed:
        parts.append(
            f"고객이 {sup}의 결제창에서 결제하는 경우 {_j(sup, '이', '가')} 판매대금을 수취하고 합의한 판매수수료를 "
            f"{sel}에 지급한다. 고객이 {sel} 또는 {sel}가 지정한 정산 대행자의 결제창에서 결제하는 경우 "
            f"{_j(sel, '이', '가')} 판매대금을 수취하고 정산한 공급대금을 {sup}에 지급한다."
        )
    if unretained:
        parts.append(
            f"{_j(sel, '이', '가')} {agent}에 정산금의 산정 및 지급 업무를 대행하게 하는 경우에도 {sup}에 대한 정산금 "
            f"지급의무 및 이 계약상 책임은 {_j(sel, '이', '가')} 부담한다."
        )
    gaps = []
    if mixed:
        gaps.append(f"'{_j(sup, '이', '가')} 고객 대금을 받고 수수료를 지급'하는 구조와 '{sel}(또는 {agent})가 정산금을 "
                    "지급'하는 구조가 함께 적혀 있으나 결제창별로 나뉘어 있지 않다")
    if unretained:
        gaps.append(f"{agent}는 계약당사자가 아닌데 {_j(agent, '이', '가')} 정산을 맡을 때 {sel}의 지급책임이 남는다는 문언이 없다")
    original = _attr(anchor, "text").rstrip()
    return [{
        "clause_id": f"ac_payment_flow_split__{_attr(anchor, 'clause_id')}",
        "clause_title": _attr(anchor, "title"),
        "display_path": _attr(anchor, "display_path"),
        "article_number": _attr(anchor, "article_number"),
        "paragraph_number": _attr(anchor, "paragraph_number"),
        "original_text": _attr(anchor, "text"),
        "risk_tier": "MEDIUM", "severity": "MEDIUM", "confidence": 0.85,
        "is_effect_baseline": True, "is_common_legal_risk": True,
        "fact_check_required": True,
        "problem": "; ".join(gaps) + ".",
        "rewrite_reason": "; ".join(gaps) + ".",
        "legal_business_reason": (
            f"누가 고객 대금을 받는지에 따라 {sup}가 받을 돈(공급대금)과 줄 돈(판매수수료)이 뒤바뀝니다. 정산 "
            f"대행자가 지급하지 않을 때 청구할 상대가 계약상 정해져 있어야 {sup}의 미수금 위험이 막힙니다."
        ),
        "suggested_rewrite": f"{original} " + " ".join(parts),
        "recommendation_text": f"{original} " + " ".join(parts),
        "location_instruction": f"{_attr(anchor, 'display_path')} 말미에 다음 문구 추가",
        "negotiation_position": "실제 결제창 운영 방식(누구 명의로 결제받는지)을 확인한 뒤 반영합니다.",
        "negotiation_strategy": "실제 결제창 운영 방식(누구 명의로 결제받는지)을 확인한 뒤 반영합니다.",
        "detected_issue_list": [{"issue_title": "결제창별 자금흐름과 정산 대행 시 지급책임 정리"}],
    }]


__all__ = [
    "CANONICAL_TYPE", "LABEL", "OnlineSalesModel", "SELLER_ROLE_LABEL", "SUPPLIER_ROLE_LABEL",
    "payment_flow_finding", "resolve_online_sales_model",
]
