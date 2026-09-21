"""건설공사 계약의 **거래구조와 당사자 지위**를 조항 검토보다 먼저 확정한다.

2026-09-18 지시 —
  "퍼시스는 인테리어공사·건설공사를 도급받아 수급인으로 수행하는 경우가 많고,
   필요하면 일부 공종을 전문업체에 재하도급하기도 한다. 반대로 퍼시스가 다른
   업체에게 공사를 발주하는 경우도 있으므로, 건설계약 검토 시 당사자 지위를
   먼저 정확히 확정한 뒤 검토할 것."

왜 지위를 먼저 정하는가
─────────────────────
같은 조문이 지위에 따라 정반대의 위험이 된다.

    "수급인은 도급인의 검사 완료 전까지 기성금을 청구할 수 없다"
        우리가 수급인이면   → 돈을 못 받는 최대 리스크
        우리가 도급인이면   → 우리를 보호하는 정상 조항(KEEP)

    "수급인은 도급인의 승인 없이 하도급할 수 없다"
        우리가 수급인이면   → 재하도급 승인 지연이 곧 공기 리스크
        우리가 도급인이면   → 유지해야 할 통제 장치

지위를 정하지 않은 채 조항을 읽으면 두 방향의 지적이 한 문서에 섞인다.
그래서 이 모듈은 **검토 이전에** 셋 중 하나로 확정한다.

    ROLE_CONTRACTOR                 퍼시스 = 수급인/원도급자
    ROLE_OWNER                      퍼시스 = 도급인(발주)
    ROLE_CONTRACTOR_WITH_SUBCONTRACT 퍼시스 = 수급인 + 재하도급인

원도급과 재하도급은 **다른 관계**다
──────────────────────────────
퍼시스가 발주자에게서 공사대금을 받는 관계(원도급)와, 퍼시스가 전문업체에
재하도급하는 관계는 적용 법률이 다르다.

    원도급 관계    민법 도급 + 건설산업기본법 + 계약조건
    재하도급 관계  건설산업기본법 + 하도급법(요건 충족 시)

계약서에 "하도급" 이라는 낱말이 있다는 이유로 **원도급 대금관계**에 하도급법
지급기한·직접지급을 적용하면, 담당자는 상대방에게 적용되지 않는 법을 근거로
협상하게 된다. 그 분리는 `subcontract_act_scope()` 가 담당한다.

설계 원칙
────────
· 회사명·계약명·조항번호를 하드코딩하지 않는다. 판정은 거래구조 문형으로만 한다.
· 사용자 설명(검토요청)과 계약 원문을 **함께** 본다. 엇갈리면 확신하지 않는다.
· 확신하지 못하면 아무것도 확정하지 않는다 — 틀린 지위로 검토서를 만드는 것이
  지위를 못 정했다고 말하는 것보다 나쁘다(지시 9항).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── canonical role ──────────────────────────────────────────────────────────
ROLE_CONTRACTOR = "contractor"
ROLE_OWNER = "owner"
ROLE_CONTRACTOR_WITH_SUBCONTRACT = "contractor_with_subcontract"
ROLE_UNSETTLED = ""

SETTLED_ROLES: frozenset[str] = frozenset({
    ROLE_CONTRACTOR, ROLE_OWNER, ROLE_CONTRACTOR_WITH_SUBCONTRACT,
})

ROLE_LABELS: dict[str, str] = {
    ROLE_CONTRACTOR: "수급인/원도급자 (우리가 공사를 도급받아 수행)",
    ROLE_OWNER: "도급인 (우리가 공사를 발주)",
    ROLE_CONTRACTOR_WITH_SUBCONTRACT: "수급인 + 재하도급인 (도급받은 공사의 일부를 전문업체에 재하도급)",
    ROLE_UNSETTLED: "당사자 지위 미확정",
}

#: 건설공사 도급계약의 canonical 계약유형 코드. 분류기(`contract_classifier`)·
#: 역할표(`_TYPE_TO_ROLE_BUCKET`)가 이미 쓰는 코드와 같은 값을 쓴다 — 여기서
#: 새 코드를 만들면 downstream 표에 전부 구멍이 생긴다.
CONSTRUCTION_CONTRACT_TYPE_CODE = "construction"

#: 거래구조에 맞지 않는 타 유형 템플릿이 섞였을 때(지시 9항 전단).
REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH = "REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH"
#: 다른 계약유형의 질문·쟁점·문구가 이 검토에 섞인 경우 (2026-09-21 지시 8항).
REVIEW_FAILED_CROSS_CONTRACT_CONTAMINATION = "REVIEW_FAILED_CROSS_CONTRACT_CONTAMINATION"
#: 당사자 지위를 셋 중 하나로 확정하지 못했을 때(지시 9항 후단).
REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED = "REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED"


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# ── 1. 이 계약이 건설공사 도급인가 ──────────────────────────────────────────
#
# 지시 1항 후단 — "계약서에 공사도급, 도급인, 수급인, 착공, 준공, 공정표,
# 기성, 설계변경, 추가공사, 시공, 하자, 공사대금 등의 신호가 충분하면
# 자문/용역/공급/대리점 계약으로 분류하지 말 것."
#
# 낱말 하나로는 판정하지 않는다. "시공" 은 가구 납품계약에도, "하자" 는 물품
# 매매에도 나온다(실측: 전략적 제휴계약이 "시공" 16회만으로 건설산업기본법
# 적용으로 판정된 사고가 있었다). **서로 다른 축**의 신호가 모여야 한다.
_CONSTRUCTION_SIGNALS: dict[str, re.Pattern[str]] = {
    "works_contract": _rx(r"공사\s*도급|건설공사|공사\s*계약|도급\s*계약|construction\s+(?:works?|contract)"),
    "party_words": _rx(r"도급인|수급인|수급자|시공(?:사|자)|발주자|발주처|건축주|시행사"),
    "commencement": _rx(r"착공|착수(?:계|신고)|현장\s*(?:인도|인수)"),
    "completion": _rx(r"준공|완공|사용승인|인수인계|준공검사"),
    "schedule": _rx(r"공정표|공정률|공정\s*계획|공사\s*기간|공기(?:\s*연장|를|의)"),
    "progress_payment": _rx(r"기성(?:고|금|률|검사|청구|부분)|기성\s*대가"),
    "design_change": _rx(r"설계\s*변경|물량\s*(?:증감|증가)|추가\s*공사|변경\s*시공"),
    "construction_act": _rx(r"시공(?:한다|하여|을|의|계획|상세)|시공\s*관리|현장\s*대리인"),
    "defect": _rx(r"하자\s*(?:담보|보수|보증|검사)|하자보수보증(?:금|서)"),
    "works_price": _rx(r"공사\s*(?:대금|금액|비)|도급\s*(?:금액|대금)|계약\s*금액"),
    "design_docs": _rx(r"설계\s*도서|시방서|도면|내역서|산출\s*내역"),
    "site_safety": _rx(r"산업안전보건|중대재해|안전관리(?:자|비|계획)|현장\s*안전"),
    "guarantee": _rx(r"계약\s*이행\s*보증|선급금\s*보증|하자\s*이행\s*보증|보증\s*증권"),
}

#: 이것만으로도 건설공사 도급임이 사실상 확정되는 강한 표지.
_STRONG_CONSTRUCTION = ("works_contract", "progress_payment", "design_change")


# ── 2. 당사자 지위 신호 ─────────────────────────────────────────────────────
#: 우리가 도급받는 쪽임을 사용자가 설명한 경우.
_RX_USER_CONTRACTOR = _rx(
    r"도급\s*받|수급인|수주(?:했|한|하여|받)|공사를?\s*(?:맡아|수행|진행)"
    r"|시공(?:을|사로|사로서)?\s*(?:맡|수행|담당)|우리(?:가|는)\s*시공"
    r"|원도급(?:자|사|인)|우리\s*회사가\s*공사를"
)
#: 우리가 발주하는 쪽임을 사용자가 설명한 경우.
_RX_USER_OWNER = _rx(
    r"발주(?:한|하는|했|합니다|를\s*하)|도급(?:을|를)?\s*(?:주|줍|하는\s*쪽)"
    r"|공사를?\s*(?:맡기|의뢰|위탁)|시공사를?\s*(?:선정|선발)|우리(?:가|는)\s*도급인"
)
#: 재하도급이 예정되어 있음을 사용자가 설명한 경우.
_RX_USER_SUBCONTRACT = _rx(
    r"재하도급|하도급(?:을|를)?\s*(?:주|줍|한다|합니다|하기도)|전문\s*업체에"
    r"|일부\s*공종(?:을|를)?\s*(?:맡기|위탁|하도급)"
)
#: "돈을 못 받는 리스크가 최대" 라는 사용자 우선순위 선언(지시 3항 후단).
_RX_USER_PAYMENT_RISK = _rx(
    r"돈을?\s*못\s*받|대금\s*(?:회수|미지급|못\s*받)|미지급\s*리스크"
    r"|지급\s*(?:유보|거절)|받지\s*못할|회수\s*(?:위험|리스크)|최대\s*리스크"
)

#: 재하도급 구조가 계약 원문에 있는가.
_RX_SUBCONTRACT_IN_TEXT = _rx(
    r"재하도급|하수급인|하도급\s*(?:업체|인|계약|공사|승인|통보)"
    r"|일부(?:를|의)?\s*(?:제3자|타인|전문업체)에게\s*(?:위탁|도급|하도급)"
    r"|공종(?:의)?\s*(?:일부|전부)를?\s*(?:위탁|하도급)"
)

#: 상대방이 **원도급사**라는 신호 — 그러면 우리는 하도급법상 수급사업자다.
#: (발주자→원사업자→우리) 이 구조에서는 하도급법이 **우리를 보호하는 방향**
#: 으로 적용된다. 원도급 관계와 혼동해서는 안 된다(지시 2항).
#: 우리가 **하도급받는 쪽**(하수급인)이라는 신호.
#:
#: 2026-09-21 2차 지시 1항 — 종전 패턴은 `하도급\s*계약(?:서)?` 만으로도
#: 참이 됐다. 그래서 우리가 **원사업자로서** 전문업체와 맺을 하도급계약을
#: 규정한 조항 하나 때문에 우리가 하수급인으로 뒤집혔다. 실측(인테리어 2차
#: 본계약 제21조 제4항):
#:
#:     "수급인은 하도급계약 체결 시 건설산업기본법 및 하도급거래 공정화에
#:      관한 법률에 따른 의무를 이행하며 …"
#:
#: 이 한 줄로 `we_are_subcontractor=True` 가 되어, 하도급법이 "우리를 보호하는
#: 방향으로 적용" 된다는 정반대의 결론이 나왔다. 그 결론의 근거 문장은
#: 발주자를 원사업자라고 서술했다(지시 1항 위반).
#:
#: 하수급인이라는 것은 **상대방이 원사업자**라는 뜻이다. 그 사실을 직접
#: 가리키는 문언만 신호로 삼는다.
_RX_WE_ARE_SUBCONTRACTOR = _rx(
    r"원사업자(?:은|는|이|가|와|과|로부터|에게|의)"
    r"|원도급(?:사|인|자)(?:은|는|이|가|와|과|로부터|에게|의)"
    r"|원도급\s*계약[^.\n]{0,30}(?:에\s*따른|에\s*기초한|의)\s*하도급"
    r"|(?:하수급인|수급사업자)(?:으)?로\s*(?:한다|본다|정한다)"
    r"|이하\s*[\"'“”']?(?:하수급인|수급사업자)"
    r"|발주(?:처|자)(?:로부터|에서)\s*(?:수주|도급받)(?:은|는)\s*[^.\n]{0,20}로부터"
)

#: 상대방을 원사업자·원도급인으로 **정의**하는 문언. 이것이 있으면 우리
#: 호칭이 "수급인" 이어도 층위는 하도급이다.
_RX_COUNTERPARTY_IS_PRINCIPAL = _rx(
    r"[\"'“”]?\s*(?:원사업자|원도급인|원도급사|원수급인)\s*[\"'“”]?\s*(?:라|이라)?\s*한다"
    r"|(?:원사업자|원도급인|원도급사|원수급인)(?:은|는|이|가|와|과|로부터|에게)"
    r"|원도급\s*계약에\s*따른[^.\n]{0,40}하도급"
)

#: 계약 원문의 당사자 정의에서 쓰이는 역할 명사.
_CONTRACTOR_LABELS = ("수급인", "수급자", "시공사", "시공자", "을")
_OWNER_LABELS = ("도급인", "발주자", "발주처", "건축주", "시행사", "갑")


@dataclass
class ConstructionTransactionModel:
    """건설계약 하나에 대한 거래구조·당사자 지위 판정."""

    is_construction: bool = False
    construction_confident: bool = False
    our_role: str = ROLE_UNSETTLED
    role_confident: bool = False
    role_basis: str = ""
    role_signals: list[str] = field(default_factory=list)
    text_signals: dict[str, int] = field(default_factory=dict)
    has_subcontracting: bool = False
    we_are_subcontractor: bool = False
    user_signal: str = ""
    payment_risk_priority: bool = False

    # ── 판정 결과를 읽는 창구 ───────────────────────────────────────────────
    @property
    def is_contractor_side(self) -> bool:
        """우리가 공사를 **수행**하는 쪽인가(원도급자·수급인)."""
        return self.our_role in (ROLE_CONTRACTOR, ROLE_CONTRACTOR_WITH_SUBCONTRACT)

    @property
    def is_owner_side(self) -> bool:
        """우리가 공사를 **발주**하는 쪽인가(도급인)."""
        return self.our_role == ROLE_OWNER

    @property
    def subcontract_relationship_in_scope(self) -> bool:
        """이 검토에서 **재하도급 관계**를 따로 봐야 하는가(지시 5항)."""
        return self.is_contractor_side and self.has_subcontracting

    @property
    def is_settled(self) -> bool:
        """지위가 셋 중 하나로 확정됐는가 — 검토 결과를 낼 수 있는 조건(지시 9항)."""
        return bool(
            self.is_construction and self.role_confident and self.our_role in SETTLED_ROLES
        )

    @property
    def canonical_contract_type(self) -> str:
        """이 거래구조가 확정하는 canonical 계약유형 코드.

        확신하지 못하면 빈 문자열이다 — 모르는 상태에서 유형을 덮어쓰면 틀린
        유형의 체크리스트를 주입하게 된다(v10 원칙).
        """
        if not (self.is_construction and self.construction_confident):
            return ""
        return CONSTRUCTION_CONTRACT_TYPE_CODE

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.our_role, ROLE_LABELS[ROLE_UNSETTLED])

    @property
    def party_role_pair(self) -> tuple[str, str]:
        """`party_role.PartyRole` 이 쓰는 (our_role, counterparty_role) 버킷."""
        if self.is_contractor_side:
            return "contractor", "ordering_party"
        if self.is_owner_side:
            return "ordering_party", "contractor"
        return "unknown", "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_construction": self.is_construction,
            "construction_confident": self.construction_confident,
            "our_role": self.our_role,
            "role_label": self.role_label,
            "role_confident": self.role_confident,
            "role_basis": self.role_basis,
            "role_signals": list(self.role_signals),
            "text_signals": dict(self.text_signals),
            "has_subcontracting": self.has_subcontracting,
            "subcontract_relationship_in_scope": self.subcontract_relationship_in_scope,
            "we_are_subcontractor": self.we_are_subcontractor,
            "user_signal": self.user_signal,
            "payment_risk_priority": self.payment_risk_priority,
            "canonical_contract_type": self.canonical_contract_type,
            "settled": self.is_settled,
        }


# ── 판정 ────────────────────────────────────────────────────────────────────

def _signal_hits(text: str) -> dict[str, int]:
    return {
        key: len(pat.findall(text or "")) for key, pat in _CONSTRUCTION_SIGNALS.items()
    }


def _is_construction_contract(hits: dict[str, int]) -> tuple[bool, bool]:
    """(건설공사 도급인가, 확신하는가).

    서로 다른 축이 4개 이상 모이면 건설공사로 본다. 강한 표지(공사도급·기성·
    설계변경)가 둘 이상이면 축이 적어도 건설공사다 — 그 낱말들은 다른 거래에
    등장할 이유가 거의 없다.
    """
    axes = sum(1 for v in hits.values() if v)
    strong = sum(1 for key in _STRONG_CONSTRUCTION if hits.get(key))
    if axes >= 6 or (strong >= 2 and axes >= 3):
        return True, True
    if axes >= 4 or (strong >= 1 and axes >= 3):
        return True, False
    return False, False


def _answer_values(answers: Any) -> list[str]:
    """답변에서 **값만** 모은다.

    질문 문구는 넣지 않는다 — 질문 템플릿이 만든 낱말("발주", "시공")이
    사용자 설명으로 둔갑해 지위 판정을 뒤집는 일을 막기 위함이다.
    """
    if not answers:
        return []
    vals: list[str] = []
    if isinstance(answers, dict):
        vals = [str(v) for v in answers.values() if isinstance(v, (str, int, float))]
    elif isinstance(answers, list):
        for row in answers:
            if isinstance(row, dict):
                for key in ("answer", "value", "text", "answer_text"):
                    v = row.get(key)
                    if isinstance(v, (str, int, float)) and str(v).strip():
                        vals.append(str(v))
                        break
            elif isinstance(row, str):
                vals.append(row)
    return vals


#: 사전질문 답변이 지위를 직접 확정하는 경우. 담당자가 확인해 준 사실은
#: 어떤 텍스트 휴리스틱보다 앞선다.
_ANSWER_ROLE_MAP: dict[str, str] = {
    "we_are_contractor": ROLE_CONTRACTOR,
    "we_are_construction_contractor": ROLE_CONTRACTOR,
    "we_are_ordering_party": ROLE_OWNER,
    "we_are_construction_owner": ROLE_OWNER,
    "we_are_contractor_with_subcontract": ROLE_CONTRACTOR_WITH_SUBCONTRACT,
}

_ROLE_ANSWER_KEYS = (
    "Q-CONST-ROLE-001-our-position",
    "Q-ROLE-001-our-position",
)


def _role_from_answers(answers: Any) -> tuple[str, str]:
    """(role, 신호 이름). 답변이 지위를 말하지 않으면 ("", "")."""
    if not isinstance(answers, dict):
        return "", ""
    for key in _ROLE_ANSWER_KEYS:
        value = answers.get(key)
        if isinstance(value, str) and value in _ANSWER_ROLE_MAP:
            return _ANSWER_ROLE_MAP[value], f"answer:{key}={value}"
    return "", ""


def _role_from_user_text(desc: str) -> tuple[str, str]:
    """사용자 설명에서 읽는 지위. 양쪽 신호가 섞이면 확정하지 않는다."""
    contractor = bool(_RX_USER_CONTRACTOR.search(desc))
    owner = bool(_RX_USER_OWNER.search(desc))
    if contractor and not owner:
        return ROLE_CONTRACTOR, "user_description_contractor"
    if owner and not contractor:
        return ROLE_OWNER, "user_description_owner"
    return "", ""


def _role_from_labels(text: str, entity: str) -> tuple[str, str]:
    """계약 원문의 당사자 정의에서 읽는 지위.

    `party_label_binding` 이 이미 하는 일(회사명 ↔ 라벨 결속)을 그대로 쓰고,
    거기서 나온 라벨을 **건설계약의 역할 명사**로 해석한다. 라벨이 갑/을이면
    도급 방향을 말하는 문장을 찾는다 — "갑은 을에게 … 공사를 도급하고".
    """
    from runtime.review.party_label_binding import (
        bind_party_labels_to_entities, role_word_near_entity,
    )

    body = str(text or "")
    bound = bind_party_labels_to_entities(body, entity)
    if bound is not None:
        our_label, cp_label = bound
        if our_label in _CONTRACTOR_LABELS and our_label not in ("을",):
            return ROLE_CONTRACTOR, f"party_label:{our_label}"
        if our_label in _OWNER_LABELS and our_label not in ("갑",):
            return ROLE_OWNER, f"party_label:{our_label}"
        role, signal = _role_from_direction_sentence(body, our_label, cp_label)
        if role:
            return role, signal

    near = role_word_near_entity(body, entity)
    if near == "supplier":
        return ROLE_CONTRACTOR, "role_word_near_entity:contractor_side"
    if near == "buyer":
        return ROLE_OWNER, "role_word_near_entity:owner_side"
    return "", ""


def _role_from_direction_sentence(text: str, our_label: str, cp_label: str) -> tuple[str, str]:
    """"갑은 을에게 공사를 도급하고" 류의 방향 문장에서 지위를 읽는다."""
    if not our_label or not cp_label:
        return "", ""
    ol = re.escape(our_label)
    cl = re.escape(cp_label)
    q = "[\"'“”‘’]?"

    # 우리가 역할 명사로 직접 지목된 경우.
    if re.search(rf"{q}{ol}{q}\s*(?:은|는|이|가)[^.\n]{{0,30}}(?:수급인|수급자|시공사|시공자)", text):
        return ROLE_CONTRACTOR, "self_declared_contractor"
    if re.search(rf"{q}{ol}{q}\s*(?:은|는|이|가)[^.\n]{{0,30}}(?:도급인|발주자|건축주|시행사)", text):
        return ROLE_OWNER, "self_declared_owner"

    # 도급 방향 — 주는 쪽이 도급인이다.
    if re.search(rf"{q}{ol}{q}\s*(?:은|는|이|가)[^.\n]{{0,60}}{q}{cl}{q}\s*(?:에게|에)[^.\n]{{0,40}}도급", text):
        return ROLE_OWNER, "direction_we_award_works"
    if re.search(rf"{q}{cl}{q}\s*(?:은|는|이|가)[^.\n]{{0,60}}{q}{ol}{q}\s*(?:에게|에)[^.\n]{{0,40}}도급", text):
        return ROLE_CONTRACTOR, "direction_they_award_works"

    # 수급 방향 — 받아서 시공하는 쪽이 수급인이다.
    if re.search(
        rf"{q}{ol}{q}\s*(?:은|는|이|가)[^.\n]{{0,50}}(?:이를|본\s*공사를|공사를)\s*"
        r"(?:수급|인수하여|맡아)[^.\n]{0,20}(?:시공|수행|완성)",
        text,
    ):
        return ROLE_CONTRACTOR, "direction_we_undertake_works"
    if re.search(
        rf"{q}{cl}{q}\s*(?:은|는|이|가)[^.\n]{{0,50}}(?:이를|본\s*공사를|공사를)\s*"
        r"(?:수급|인수하여|맡아)[^.\n]{0,20}(?:시공|수행|완성)",
        text,
    ):
        return ROLE_OWNER, "direction_they_undertake_works"
    return "", ""


def classify_construction_transaction(
    *,
    contract_text: str,
    user_description: str = "",
    entity: str = "",
    answers: Any = None,
    contract_type_code: str = "",
) -> ConstructionTransactionModel:
    """건설계약의 거래구조와 당사자 지위를 가른다.

    건설공사 도급이 아니면 아무것도 판정하지 않는다 — 건설이 아닌 계약에
    이 판단을 적용할 이유가 없다.
    """
    body = str(contract_text or "")
    desc = str(user_description or "")
    hits = _signal_hits(body)
    is_construction, confident = _is_construction_contract(hits)

    # 분류기가 이미 건설로 확정했으면 그 판정을 존중한다 — 같은 판단을 두 곳에서
    # 하면 갈라진다. 다만 신호가 전혀 없으면 따라가지 않는다.
    if str(contract_type_code or "").strip() in ("construction", "construction_contract"):
        if sum(1 for v in hits.values() if v) >= 2:
            is_construction = True
            confident = confident or sum(1 for v in hits.values() if v) >= 4

    if not is_construction:
        return ConstructionTransactionModel(
            is_construction=False, text_signals=hits,
            role_basis="건설공사 도급의 신호가 충분하지 않습니다.",
        )

    desc_all = "\n".join(x for x in (desc, *_answer_values(answers)) if str(x).strip())
    has_sub_text = bool(_RX_SUBCONTRACT_IN_TEXT.search(body))
    has_sub_user = bool(_RX_USER_SUBCONTRACT.search(desc_all))
    has_subcontracting = has_sub_text or has_sub_user
    we_are_subcontractor = bool(_RX_WE_ARE_SUBCONTRACTOR.search(body))
    #: 상대방이 스스로를 원사업자·원도급인으로 정의했는가. 하도급계약서는
    #: 우리를 "수급인" 이라고 부르므로, 우리 호칭만으로는 층위를 알 수 없다.
    counterparty_is_principal = bool(_RX_COUNTERPARTY_IS_PRINCIPAL.search(body))
    payment_risk = bool(_RX_USER_PAYMENT_RISK.search(desc_all))

    signals: list[str] = []
    role = ROLE_UNSETTLED
    role_confident = False
    basis = ""

    answer_role, answer_signal = _role_from_answers(answers)
    user_role, user_signal_name = _role_from_user_text(desc_all)
    label_role, label_signal = _role_from_labels(body, entity)
    for sig in (answer_signal, user_signal_name, label_signal):
        if sig:
            signals.append(sig)

    if answer_role:
        role, role_confident = answer_role, True
        basis = "담당자가 사전질문에서 당사자 지위를 직접 확인했습니다."
    elif user_role and label_role and user_role != label_role:
        # 엇갈리면 확정하지 않는다. 틀린 지위로 검토서를 만드는 것이
        # 지위를 못 정했다고 말하는 것보다 나쁘다(지시 9항).
        role, role_confident = ROLE_UNSETTLED, False
        basis = (
            f"검토요청 설명({ROLE_LABELS.get(user_role, user_role)})과 계약서 당사자 "
            f"정의({ROLE_LABELS.get(label_role, label_role)})가 서로 다른 지위를 가리킵니다."
        )
    elif label_role:
        role, role_confident = label_role, True
        basis = "계약서의 당사자 정의에서 지위가 확정됩니다."
        if user_role == label_role:
            basis = "검토요청 설명과 계약서 당사자 정의가 같은 지위를 가리킵니다."
    elif user_role:
        role, role_confident = user_role, True
        basis = "검토요청 설명에서 지위가 확정됩니다(계약서 당사자 정의는 명시적이지 않음)."
    else:
        basis = (
            "계약서 당사자 정의와 검토요청 설명 어디에서도 도급인/수급인 지위를 "
            "특정하지 못했습니다."
        )

    # 재하도급까지 하는 구조면 지위는 "수급인 + 재하도급인" 이다(지시 1항 3호).
    if role == ROLE_CONTRACTOR and has_subcontracting:
        role = ROLE_CONTRACTOR_WITH_SUBCONTRACT
        signals.append("subcontracting_present")

    # 확정된 지위가 "**발주자와 직접** 계약한 수급인" 이면 우리는 하수급인이
    # 아니다 (2026-09-21 2차 지시 1항). 이 값이 하도급법의 적용 **방향**을
    # 정하므로, 뒤집히면 "하도급법이 우리를 보호한다" 는 정반대의 결론이 나온다.
    #
    # 다만 상대방이 스스로를 원사업자·원도급인으로 정의했으면 우리 쪽 호칭이
    # "수급인" 이어도 우리는 하수급인이다 — 하도급계약서는 우리를 대개
    # "수급인" 이라고 부른다. 그래서 **상대방의 정의**를 먼저 본다.
    if role_confident and role in (ROLE_CONTRACTOR, ROLE_CONTRACTOR_WITH_SUBCONTRACT):
        if we_are_subcontractor and not counterparty_is_principal:
            signals.append("we_are_subcontractor_signal_overridden_by_role")
            we_are_subcontractor = False

    return ConstructionTransactionModel(
        is_construction=True,
        construction_confident=confident,
        our_role=role,
        role_confident=role_confident,
        role_basis=basis,
        role_signals=signals,
        text_signals=hits,
        has_subcontracting=has_subcontracting,
        we_are_subcontractor=we_are_subcontractor,
        user_signal=user_role,
        payment_risk_priority=payment_risk,
    )


def resolve_construction_transaction_model(
    *,
    contract_text: str,
    user_description: str = "",
    entity: str = "",
    answers: Any = None,
    contract_type_code: str = "",
) -> ConstructionTransactionModel:
    """거래구조·지위의 **단일 확정 지점**.

    사전질문 생성기와 검토 파이프라인이 각자 `classify_…()` 를 부르면 입력이
    조금만 달라져도 서로 다른 지위를 들고 일하게 된다 — 질문은 수급인 기준으로
    나가고 finding 은 도급인 기준으로 생성되는 상태다. 두 경로 모두 이 함수만
    부른다.
    """
    return classify_construction_transaction(
        contract_text=contract_text,
        user_description=user_description,
        entity=entity,
        answers=answers,
        contract_type_code=contract_type_code,
    )


# ══════════════════════════════════════════════════════════════════════════
# 하도급법 적용범위 — 원도급 관계와 재하도급 관계를 분리한다(지시 2항·6항)
# ══════════════════════════════════════════════════════════════════════════

SCOPE_NOT_APPLICABLE_PRIME = "not_applicable_to_prime_payment"
#: 우리가 도급인(발주)일 때 — 적용 여부는 "우리가 건설업을 영위하며 도급받은
#: 공사를 다시 위탁하는가" 에 달려 있다. 그 판단은 회사의 업(業) 정보를 가진
#: `statute_applicability_gate` 의 일반 로직이 한다. 여기서 단정하지 않는다.
SCOPE_OWNER_DEPENDS_ON_BUSINESS = "owner_depends_on_our_business"
SCOPE_APPLICABLE_AS_PRINCIPAL = "applicable_to_subcontract_as_principal"
SCOPE_APPLICABLE_AS_SUBCONTRACTOR = "applicable_to_this_contract_as_subcontractor"
SCOPE_NEEDS_FACTS = "needs_facts"


@dataclass(frozen=True)
class SubcontractActScope:
    """하도급법이 **어느 관계에** 적용되는가."""

    scope: str
    reason: str
    #: 이 계약(우리가 검토 중인 문서) 자체의 대금관계에 하도급법이 적용되는가.
    applies_to_this_contract: bool
    #: 별도의 재하도급 계약에 적용되는가(이 계약이 아니라).
    applies_to_subcontract: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "reason": self.reason,
            "applies_to_this_contract": self.applies_to_this_contract,
            "applies_to_subcontract": self.applies_to_subcontract,
        }


def subcontract_act_scope(model: ConstructionTransactionModel) -> SubcontractActScope:
    """하도급법의 적용 **관계**를 가른다.

    세 갈래다.

    1. 우리가 **수급사업자** — 상대방이 원도급사이고 우리가 그로부터 하도급을
       받는 구조. 이 계약의 대금관계에 하도급법이 **우리를 보호하는 방향**으로
       적용된다(지급기한·직접지급청구권·부당특약 무효).
    2. 우리가 **원사업자** — 도급받은 공사의 일부를 전문업체에 재하도급하는
       구조. 하도급법은 그 **재하도급 계약**에 적용되며, 지금 검토 중인 원도급
       계약의 대금관계에는 적용되지 않는다.
    3. 그 밖의 원도급 관계 — 발주자와 직접 체결한 도급계약이면 하도급법상
       하도급거래가 아니다. 민법 도급과 건설산업기본법으로 본다.

    "하도급" 이라는 낱말이 계약서에 있다는 이유만으로 원도급 대금관계에 지급
    기한·직접지급을 적용하면, 담당자는 적용되지 않는 법으로 협상하게 된다.
    """
    if not model.is_construction:
        return SubcontractActScope(
            scope=SCOPE_NEEDS_FACTS,
            reason="건설공사 도급계약이 아니어서 건설 하도급 관계를 판단하지 않았습니다.",
            applies_to_this_contract=False,
            applies_to_subcontract=False,
        )

    if model.is_contractor_side and model.we_are_subcontractor:
        return SubcontractActScope(
            scope=SCOPE_APPLICABLE_AS_SUBCONTRACTOR,
            reason=(
                "상대방이 발주자로부터 공사를 도급받은 원사업자이고 우리 회사가 그 일부를 "
                "하도급받는 구조이므로, 이 계약의 대금관계에 하도급법이 우리 회사를 보호하는 "
                "방향으로 적용됩니다(대금 지급기한, 발주자에 대한 직접지급청구권, 부당특약 무효)."
            ),
            applies_to_this_contract=True,
            applies_to_subcontract=False,
        )

    if model.our_role == ROLE_CONTRACTOR_WITH_SUBCONTRACT:
        return SubcontractActScope(
            scope=SCOPE_APPLICABLE_AS_PRINCIPAL,
            reason=(
                "우리 회사가 도급받은 공사의 일부를 전문업체에 재하도급하는 구조입니다. "
                "하도급법은 그 재하도급 계약(우리 회사가 원사업자)에 적용되며, 지금 검토하는 "
                "원도급 계약의 대금관계에는 적용되지 않습니다 — 원도급 대금은 민법 도급과 "
                "건설산업기본법, 그리고 이 계약의 지급조건으로 판단합니다."
            ),
            applies_to_this_contract=False,
            applies_to_subcontract=True,
        )

    if model.is_owner_side:
        # 우리가 발주자라고 해서 곧바로 원사업자가 되는 것은 아니다. 하도급법상
        # 건설위탁은 **건설업을 영위하는 사업자**가 건설공사를 위탁하는 경우를
        # 말하므로(법 제2조 제9항), 자기 시설을 짓기 위해 발주하는 것은 여기에
        # 해당하지 않는다. 우리 회사가 무엇을 업으로 하는지는 계약이 아니라
        # 회사 정보이므로, 그 판단은 업(業) 표를 가진 법률 게이트에 맡긴다.
        return SubcontractActScope(
            scope=SCOPE_OWNER_DEPENDS_ON_BUSINESS,
            reason=(
                "우리 회사가 공사를 발주하는 도급인입니다. 하도급법상 건설위탁은 건설업을 "
                "영위하는 사업자가 건설공사를 위탁하는 경우를 말하므로, 적용 여부는 우리 "
                "회사가 건설업을 업으로 영위하는지와 이 공사의 수주 경위에 따라 결정됩니다."
            ),
            applies_to_this_contract=False,
            applies_to_subcontract=False,
        )

    if model.is_contractor_side:
        return SubcontractActScope(
            scope=SCOPE_NOT_APPLICABLE_PRIME,
            reason=(
                "우리 회사가 발주자와 직접 체결하는 원도급 계약입니다. 하도급법상 하도급거래는 "
                "원사업자가 수급사업자에게 위탁하는 관계를 말하므로(법 제2조), 이 원도급 "
                "대금관계에는 하도급법의 지급기한·직접지급 규정이 적용되지 않습니다. "
                "대금은 민법 도급과 건설산업기본법, 이 계약의 지급조건으로 판단합니다."
            ),
            applies_to_this_contract=False,
            applies_to_subcontract=False,
        )

    return SubcontractActScope(
        scope=SCOPE_NEEDS_FACTS,
        reason=(
            "당사자 지위(도급인/수급인/재하도급인)가 확정되지 않아 하도급법의 적용 관계를 "
            "판단할 수 없습니다."
        ),
        applies_to_this_contract=False,
        applies_to_subcontract=False,
    )


# ══════════════════════════════════════════════════════════════════════════
# Hard Gate 1 — 타 계약유형 템플릿 혼입 차단(지시 9항 전단)
# ══════════════════════════════════════════════════════════════════════════

#: 건설공사 도급계약에 섞이면 안 되는 **타 유형 전용** 어휘.
#: 계약 원문이 그 말을 쓰고 있으면 혼입이 아니다 — 호출부에서 원문과 대조한다.
FOREIGN_TEMPLATE_TERMS: dict[str, tuple[str, ...]] = {
    "advisory_service": (
        "자문 결과보고서", "자문료", "컨설팅 보고서", "자문 범위", "용역수행계획서",
        "과업지시서", "투입 인력 등급", "맨먼스", "M/M",
    ),
    "goods_supply": (
        "판매가격", "재판매", "출고가", "반품 조건", "제품 단가표", "최소주문수량",
        "MOQ", "위험이전 시점", "인코텀즈",
    ),
    "dealer_distribution": (
        "대리점", "판매점", "딜러", "판매장려금", "판촉비", "판매목표", "판매지역",
        "경영간섭", "구입강제", "대리점법",
    ),
    "sales_support": (
        "판매지원금", "영업지원 수수료", "고객 유치", "판매수수료", "매장 운영",
    ),
    "content_production": (
        "숏폼", "협찬 표시", "2차적저작물", "저작인격권", "크리에이터", "인플루언서",
        "시안 검수", "2차 활용", "2차적 이용", "콘텐츠 재가공",
    ),
    # 2026-09-21 지시 8항이 예시로 든 혼입 어휘. 매장 운영·광고·개인정보
    # 흐름은 건설공사 도급계약의 급부 구조에 존재하지 않는다 — 계약 원문에
    # 그 말이 없는데도 나오면 다른 계약의 체크리스트가 따라 들어온 것이다.
    "store_operation": (
        "상담 인력", "전시", "쇼룸", "POS", "재고관리", "재고 실사", "진열",
        "매장 인테리어 유지", "고객 응대 매뉴얼",
    ),
    "advertising": (
        "광고 게재", "광고 집행", "매체 집행", "노출 보장", "송출", "광고비",
        "협찬", "브랜드 노출",
    ),
    "personal_data": (
        "개인정보 처리방침", "개인정보 국외 이전", "정보주체", "가명정보",
        "개인정보 위탁", "수탁자 관리·감독",
    ),
}


def _terms_for_all() -> tuple[str, ...]:
    out: list[str] = []
    for terms in FOREIGN_TEMPLATE_TERMS.values():
        out.extend(terms)
    return tuple(out)


#: finding 이 담당자에게 실제로 말하는 내용 전부.
FINDING_TEXT_FIELDS: tuple[str, ...] = (
    "issue_title", "clause_title", "problem", "rewrite_reason",
    "legal_business_reason", "suggested_rewrite", "proposed_revision",
    "recommendation_text", "negotiation_position", "negotiation_strategy",
)


def finding_blob(cr: dict[str, Any]) -> str:
    parts = [str(cr.get(k) or "") for k in FINDING_TEXT_FIELDS]
    detected = cr.get("detected_issue_list")
    if isinstance(detected, list):
        parts += [
            str(d.get("issue_title") or "") for d in detected if isinstance(d, dict)
        ]
    return "\n".join(parts)


def foreign_template_terms_in(cr: dict[str, Any], *, contract_text: str) -> list[str]:
    """이 finding 이 쓰고 있는, 계약 원문에 없는 타 유형 전용 어휘."""
    blob = finding_blob(cr)
    body = str(contract_text or "")
    return [t for t in _terms_for_all() if t in blob and t not in body]


def deactivate_foreign_template_findings(
    clause_results: list[dict[str, Any]],
    model: ConstructionTransactionModel,
    *,
    contract_text: str,
) -> list[dict[str, Any]]:
    """건설공사 도급계약에서 자문/용역·공급·대리점·판매지원 템플릿을 걷어낸다.

    건설공사로 **확신**할 때만 돈다. 확신하지 못한 상태에서 지우면 정당한
    지적까지 사라진다.
    """
    if not (model.is_construction and model.construction_confident):
        return []

    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        # 건설 체크리스트가 스스로 만든 항목은 대상이 아니다 — 그 항목들이
        # 바로 "이 거래구조에서 무엇을 볼 것인가" 의 답이다.
        if bool(cr.get("is_construction_checklist")) or bool(cr.get("is_common_legal_risk")):
            kept.append(cr)
            continue
        terms = foreign_template_terms_in(cr, contract_text=contract_text)
        if not terms:
            kept.append(cr)
            continue
        removed.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            "foreign_terms": terms[:5],
            "reason": (
                "건설공사 도급계약인데 다른 계약유형(자문·공급·대리점·판매지원) 전용 "
                "문언을 근거로 한 항목이라 제거했습니다."
            ),
        })
    clause_results[:] = kept
    return removed


# ══════════════════════════════════════════════════════════════════════════
# Hard Gate 2 — 지위와 반대 방향의 finding 차단(지시 3항·4항·7항)
# ══════════════════════════════════════════════════════════════════════════

#: 우리가 **수급인**일 때 성립할 수 없는 권고 — 상대방(도급인)을 보호하려고
#: 우리 자신의 의무를 키우는 방향이다.
_RX_OWNER_SIDE_RECOMMENDATION = _rx(
    r"수급인(?:의|에게|에\s*대한)?[^.\n]{0,25}(?:책임|의무|부담)[^.\n]{0,15}(?:강화|확대|추가|명확히\s*부과)"
    r"|지체상금[^.\n]{0,20}(?:요율|율)[^.\n]{0,15}(?:인상|상향|높)"
    r"|하자\s*담보(?:책임)?\s*기간[^.\n]{0,15}(?:연장|확대)"
    r"|하자보수보증금[^.\n]{0,15}(?:비율|요율)[^.\n]{0,15}(?:인상|상향)"
    r"|수급인[^.\n]{0,20}연대\s*보증[^.\n]{0,15}(?:요구|징구)"
    r"|도급인(?:의|에게)[^.\n]{0,20}(?:해지권|중지권)[^.\n]{0,15}(?:확대|추가|부여)"
)

#: 우리가 **도급인**일 때 성립할 수 없는 권고 — 상대방(수급인)의 면책을
#: 넓혀 우리 회수 수단을 깎는 방향이다.
_RX_CONTRACTOR_SIDE_RECOMMENDATION = _rx(
    r"수급인(?:의|에게)?[^.\n]{0,20}(?:책임|의무)[^.\n]{0,15}(?:완화|축소|감경|면제)"
    r"|지체상금[^.\n]{0,20}(?:면제|삭제|폐지)"
    r"|하자\s*담보(?:책임)?\s*기간[^.\n]{0,15}(?:단축|축소)"
    r"|도급인(?:의|에게)[^.\n]{0,20}(?:해지권|중지권|검사권)[^.\n]{0,15}(?:삭제|제한|축소)"
)


def find_role_mismatched_findings(
    clause_results: list[dict[str, Any]],
    model: ConstructionTransactionModel,
) -> list[dict[str, Any]]:
    """지위와 반대 방향으로 우리에게 불리한 권고를 찾아낸다.

    지우지 않고 **찾아만 준다** — 제거 여부는 호출부(파이프라인)가 정한다.
    강행법규 준수를 위한 수정(`legal_compliance_override`)은 제외한다.
    우리에게 유리하고 위법하지 않은 조항은 KEEP 이어야 한다(지시 7항 후단).
    """
    if not model.is_settled:
        return []
    pattern = (
        _RX_OWNER_SIDE_RECOMMENDATION if model.is_contractor_side
        else _RX_CONTRACTOR_SIDE_RECOMMENDATION
    )
    out: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("legal_compliance_override")):
            continue
        proposal = "\n".join(
            str(cr.get(k) or "")
            for k in ("suggested_rewrite", "proposed_revision", "recommendation_text",
                      "rewrite_reason", "negotiation_position")
        )
        m = pattern.search(proposal)
        if m is None:
            continue
        out.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            "matched": m.group(0)[:80],
            "our_role": model.our_role,
            "reason": (
                f"우리 회사는 {model.role_label}인데 반대 지위를 전제한 권고입니다."
            ),
        })
    return out


def deactivate_role_mismatched_findings(
    clause_results: list[dict[str, Any]],
    model: ConstructionTransactionModel,
) -> list[dict[str, Any]]:
    """지위와 반대 방향의 권고를 결과에서 제거한다. 제거 내역을 돌려준다."""
    hits = find_role_mismatched_findings(clause_results, model)
    if not hits:
        return []
    bad = {h["clause_id"] for h in hits if h.get("clause_id")}
    clause_results[:] = [
        cr for cr in clause_results
        if not (isinstance(cr, dict) and str(cr.get("clause_id") or "") in bad)
    ]
    return hits


# ══════════════════════════════════════════════════════════════════════════
# Hard Gate 3 — 하도급법을 원도급 대금관계에 기계적으로 적용하지 않기(지시 2항)
# ══════════════════════════════════════════════════════════════════════════

#: 하도급법 **전용** 용어. 이 말이 나왔다는 것은 그 법을 근거로 삼았다는 뜻이다.
SUBCONTRACT_ACT_TERMS: tuple[str, ...] = (
    "하도급대금",
    "하도급 대금",
    "원사업자",
    "수급사업자",
    "하도급거래 공정화",
    "하도급법",
    "발주자에 대한 직접지급",
    "직접지급청구권",
)

#: 근거를 떼어낼 때 손대는 필드. 계약서에 들어가는 문안(`suggested_rewrite`)은
#: 건드리지 않는다 — 문장을 고치면 그것이 곧 계약서 훼손이다.
_SCOPE_TEXT_FIELDS = (
    "issue_title", "problem", "rewrite_reason", "legal_business_reason",
    "recommendation_text", "negotiation_position", "negotiation_strategy",
    "worst_case_scenario",
)


def scrub_subcontract_act_from_prime_relationship(
    clause_results: list[dict[str, Any]],
    model: ConstructionTransactionModel,
    scope: SubcontractActScope,
) -> list[dict[str, Any]]:
    """원도급 관계를 다루는 finding 에서 하도급법 근거를 떼어낸다.

    퍼시스가 도급받은 공사의 일부를 재하도급하는 구조에서는 하도급법이
    **재하도급 계약**에 적용된다. 그런데 같은 계약서에 "하도급" 이라는 낱말이
    있다는 이유로, 발주자와의 원도급 대금 조항에 "하도급대금 지급기한 60일"·
    "발주자에 대한 직접지급청구권" 이 붙는 일이 생긴다. 담당자는 상대방에게
    적용되지 않는 법을 근거로 협상하게 된다.

    재하도급 체크리스트가 만든 항목(`construction_scope == "subcontract"`)은
    그 법이 실제로 적용되는 관계를 다루므로 손대지 않는다.

    바뀐 내역을 돌려준다 — 조용히 사라지지 않게 하기 위함이다.
    """
    if not scope.applies_to_subcontract or scope.applies_to_this_contract:
        return []

    note = (
        "하도급법은 이 원도급 계약의 대금관계가 아니라 우리 회사가 전문업체와 체결하는 "
        "재하도급 계약에 적용됩니다. 원도급 대금은 민법 도급과 건설산업기본법, 이 계약의 "
        "지급조건으로 판단합니다."
    )
    changed: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if str(cr.get("construction_scope") or "") == "subcontract":
            continue
        hits: list[str] = []
        for field_name in _SCOPE_TEXT_FIELDS:
            value = cr.get(field_name)
            if not isinstance(value, str) or not value.strip():
                continue
            sentences = re.split(r"(?<=[.!?])\s+|\n+", value)
            survivors: list[str] = []
            for sentence in sentences:
                matched = next((t for t in SUBCONTRACT_ACT_TERMS if t in sentence), "")
                if matched and len(sentences) > 1:
                    hits.append(matched)
                    continue
                if matched:
                    # 문장이 하나뿐이면 지우면 설명이 사라진다. 용어만 중화한다.
                    hits.append(matched)
                    for term in SUBCONTRACT_ACT_TERMS:
                        sentence = sentence.replace(term, "관련 법령")
                survivors.append(sentence)
            rebuilt = " ".join(x.strip() for x in survivors if x.strip()).strip()
            if rebuilt != value.strip():
                cr[field_name] = rebuilt
        if hits:
            cr["subcontract_act_scope_note"] = note
            changed.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "removed_terms": sorted(set(hits)),
                "reason": note,
            })
    return changed
