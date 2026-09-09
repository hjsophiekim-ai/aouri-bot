"""Risk Allocation Matrix — 조항별 검토 **전에** 위험배분을 먼저 판단한다
(2026-09-09 지시 항목 4).

시니어 사내변호사는 조항을 순서대로 읽지 않는다. 먼저 "이 계약에서 무슨 일이
생기면 누가 돈을 내는가"를 한 장으로 그린 다음, 그 그림에서 우리 회사가
과도하게 떠안은 칸을 찾아 그 칸에 해당하는 조항을 본다.

이 모듈은 계약 전체에서 위험축별로 **부담 주체**를 판정한다:

    공기 지연 / 대금 미지급 / 설계변경 / 추가공사 / 검수 / 하자 / 안전사고 /
    불가항력 / 제3자 손해 / 하수급인 책임 / 보험 / 계약해지 / 보증금 몰취 /
    손해배상 / 상계 / IP·기술자료

판정 결과는 세 값 중 하나다:

    ours            우리 회사가 부담
    counterparty    상대방이 부담
    shared          분담 또는 귀책에 따라 나뉜다
    unallocated     계약이 정하지 않았다 (분쟁 시 다툼이 된다)

설계 — **하드코딩 금지**. 회사명·조항번호를 쓰지 않는다. 계약서가 당사자를
부르는 이름("도급인/수급인", "갑/을", "Employer/Contractor")을 먼저 우리
회사 쪽/상대방 쪽으로 매핑한 다음, 위험축 문형에서 어느 쪽 호칭이 부담
주체로 등장하는지를 본다. 그래서 처음 보는 계약유형에도 적용된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

SIDE_OURS = "ours"
SIDE_COUNTERPARTY = "counterparty"
SIDE_SHARED = "shared"
SIDE_UNALLOCATED = "unallocated"

SIDE_LABELS = {
    SIDE_OURS: "우리 회사 부담",
    SIDE_COUNTERPARTY: "상대방 부담",
    SIDE_SHARED: "분담/귀책에 따름",
    SIDE_UNALLOCATED: "미배분 — 계약이 정하지 않음",
}

#: 계약서가 쓰는 당사자 호칭. 각 쌍은 (급부 제공자 쪽, 급부 수령자 쪽).
#: 어느 쪽이 우리 회사인지는 `our_role_direction` 으로 결정한다.
_PARTY_PAIRS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("수급인", "시공사", "시공자", "공급업자", "공급자", "제조자", "매도인"),
     ("도급인", "발주자", "발주처", "주문자", "구매자", "매수인")),
    (("을", "“을”", '"을"'), ("갑", "“갑”", '"갑"')),
    (("contractor", "supplier", "seller", "vendor"),
     ("employer", "owner", "buyer", "purchaser", "client")),
    (("수탁자", "위탁받은", "대리점", "판매점"), ("위탁자", "본인")),
    (("임차인", "lessee"), ("임대인", "lessor")),
    (("수령자", "정보수령자", "receiving party"), ("제공자", "정보제공자", "disclosing party")),
    (("licensee",), ("licensor",)),
)


@dataclass(frozen=True)
class RiskAxis:
    key: str
    label: str
    #: 이 위험이 논의되는 문맥을 찾는 패턴
    context: re.Pattern[str]
    #: 부담 주체가 명시되는 문형 — {P} 자리에 당사자 호칭이 들어간다
    bearer_templates: tuple[str, ...]
    #: 귀책에 따라 나뉘는 구조를 나타내는 문형
    shared_pattern: re.Pattern[str] | None = None
    #: **수익자**가 명시되는 문형. 여기에 걸린 당사자는 이득을 보는 쪽이므로
    #: 부담자는 그 반대편이다. 보증금 몰취가 대표적이다 — "보증금은 도급인에게
    #: 귀속된다"는 도급인이 부담한다는 뜻이 아니라 우리가 잃는다는 뜻이다.
    #: 이걸 구분하지 않아 보증금 몰취가 "상대방 부담"으로 나왔다(2026-09-09 실측).
    beneficiary_templates: tuple[str, ...] = ()


def _rx(*alts: str) -> re.Pattern[str]:
    return re.compile("|".join(alts), re.IGNORECASE | re.DOTALL)


#: 부담 동사. 납부·지급은 지체상금·보증금을 배분하는 표준 어휘다.
_BURDEN_VERB = (
    r"(?:부담(?:한다|하며|하고|하여야|으로|이다)|"
    r"책임(?:을\s*)?(?:진다|부담|이다|이며|으로|하에)|"
    r"배상(?:한다|하며|하여야|할\s*책임)|지급(?:한다|하며|하여야)|"
    r"납부(?:한다|하며|하여야)|귀속(?:한다|된다|한))"
)

#: 부담 주체를 지목하는 문형.
#:
#: **주격 조사를 요구한다** — "{P}에게 납부하여야 한다"는 P 가 부담한다는 뜻이
#: 아니라 P 가 받는다는 뜻이다. 이걸 구분하지 않으면 "수급인은 … 지체상금을
#: 도급인에게 납부하여야 한다"에서 도급인이 지체상금을 부담하는 것으로 읽는다.
#:
#: 주체와 동사 사이의 필러는 **길이를 제한하지 않고 마침표만 못 넘게** 한다.
#: 즉 한 문장이 곧 스코프다. 길이로 제한하면 어느 쪽으로도 틀린다(2026-09-09
#: 실측): 60자면 "“수급인”은 준공예정일까지 … “도급인”에게 납부하여야 한다"
#: 같은 긴 조건절에서 주체를 놓쳐 지체상금 부담자가 도급인으로 읽혔고, 200자로
#: 늘리면 문장을 넘어 아무 동사에나 주체가 붙어 16축 중 13축이 우리 부담으로
#: 과탐됐다.
_BEAR = (
    r"{P}(?:\s*[”\"'’])?\s*(?:은|는|이|가)[^.]*?" + _BURDEN_VERB,
    r"(?:모든|일체의?)\s*(?:책임|비용|손해|손실)[^.\n]{{0,20}}?{P}",
    r"{P}\s*(?:의|이|가|은|는)?\s*(?:자신의\s*)?(?:책임과\s*)?"
    r"(?:비용|부담)(?:으로|은|는|이다|에)",
    # "책임은 수급인에게 있다" — 부담 명사가 앞에 오면 여격도 부담자를 가리킨다.
    r"(?:책임|부담|의무|비용)[^.\n]{{0,20}}?{P}(?:\s*[”\"'’])?\s*"
    r"(?:에게|에)\s*(?:있다|귀속)",
)

_SHARED = _rx(
    r"귀책\s*사유(?:에\s*따라|가\s*있는)", r"각자\s*부담", r"협의(?:하여|를\s*통해)\s*정",
    r"과실\s*비율", r"분담", r"상호\s*(?:협의|합의)",
)

RISK_AXES: tuple[RiskAxis, ...] = (
    RiskAxis("schedule_delay", "공기 지연",
             _rx(r"지체상금", r"준공(?:기한|예정일)[^.\n]{0,30}?(?:지연|지체)", r"공기\s*지연",
                 r"delay[^.\n]{0,30}?(?:completion|works)"),
             _BEAR, _SHARED),
    RiskAxis("payment_default", "대금 미지급",
             _rx(r"(?:대금|기성금|정산금)[^.\n]{0,30}?(?:미지급|지연|지체)",
                 r"지연\s*이자", r"late\s+payment"),
             _BEAR, _SHARED),
    RiskAxis("design_change", "설계변경",
             _rx(r"설계\s*변경", r"variation", r"공사\s*내용[^.\n]{0,20}?변경"),
             _BEAR, _SHARED),
    RiskAxis("extra_work", "추가공사",
             _rx(r"추가\s*공사", r"추가\s*시공", r"additional\s+works?"),
             _BEAR, _SHARED),
    RiskAxis("acceptance", "검수",
             _rx(r"준공\s*검사", r"검\s*수", r"인수\s*검사", r"acceptance\s+test"),
             _BEAR, _SHARED),
    RiskAxis("defects", "하자",
             _rx(r"하자\s*(?:보수|담보|보증)", r"defects?\s+liability"),
             _BEAR, _SHARED),
    RiskAxis("safety_accident", "안전사고",
             _rx(r"산업\s*안전", r"중대\s*재해", r"안전\s*사고", r"재해[^.\n]{0,20}?발생",
                 r"industrial\s+safety"),
             _BEAR, _SHARED),
    RiskAxis("force_majeure", "불가항력",
             _rx(r"불가항력", r"force\s+majeure", r"천재\s*지변"),
             _BEAR, _SHARED),
    RiskAxis("third_party_damage", "제3자 손해",
             _rx(r"제\s*3\s*자[^.\n]{0,30}?(?:손해|피해|청구)", r"third\s+part(?:y|ies)[^.\n]{0,30}?claim"),
             _BEAR, _SHARED),
    RiskAxis("subcontractor", "하수급인 책임",
             _rx(r"하\s*도급", r"하\s*수급", r"재\s*위탁", r"subcontract"),
             _BEAR, _SHARED),
    RiskAxis("insurance", "보험",
             _rx(r"보험[^.\n]{0,30}?(?:가입|부보|체결)", r"insurance"),
             _BEAR, _SHARED),
    RiskAxis("termination", "계약해지",
             _rx(r"계약(?:의)?\s*(?:해지|해제)", r"terminat(?:e|ion)"),
             _BEAR, _SHARED),
    RiskAxis("bond_forfeiture", "보증금 몰취",
             _rx(r"보증금[^.\n]{0,30}?(?:귀속|몰취|몰수)", r"forfeit"),
             _BEAR, _SHARED,
             beneficiary_templates=(
                 r"보증금[^.\n]{{0,40}}?{P}(?:\s*에게|\s*에)?\s*(?:귀속|몰취|몰수)",
                 r"{P}(?:\s*에게|\s*에)?\s*(?:귀속(?:된다|한다)|몰취|몰수)",
                 r"forfeited?\s+to\s+{P}",
             )),
    RiskAxis("damages", "손해배상",
             _rx(r"손해\s*배상", r"damages"),
             _BEAR, _SHARED),
    RiskAxis("setoff", "상계",
             _rx(r"상\s*계", r"공\s*제[^.\n]{0,20}?(?:할\s*수|한다)", r"set[- ]?off"),
             _BEAR, _SHARED),
    RiskAxis("ip_data", "IP·기술자료",
             _rx(r"지식\s*재산", r"설계\s*도서[^.\n]{0,20}?귀속", r"기술\s*자료",
                 r"intellectual\s+property"),
             _BEAR, _SHARED),
)


def _side_aliases(our_role_direction: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(우리 쪽 호칭, 상대방 호칭).

    `our_role_direction` 이 "provider"(급부 제공자)면 각 쌍의 앞쪽이 우리 쪽,
    "recipient"면 뒤쪽이 우리 쪽이다. 확신할 수 없으면 provider 로 둔다 —
    우리 회사가 급부를 제공하는 계약이 더 흔하고, 방향이 틀리면 매트릭스가
    좌우로 뒤집혀 보이므로 판정 근거를 리포트에 함께 남긴다.
    """
    direction = str(our_role_direction or "").strip().lower()
    ours_is_provider = "recipient" not in direction and "수령" not in direction
    ours: list[str] = []
    theirs: list[str] = []
    for provider, recipient in _PARTY_PAIRS:
        if ours_is_provider:
            ours.extend(provider)
            theirs.extend(recipient)
        else:
            ours.extend(recipient)
            theirs.extend(provider)
    return tuple(ours), tuple(theirs)


#: 당사자 호칭 바로 뒤에 오는 닫는 인용부호. 실무 계약은 당사자를 거의 항상
#: 따옴표로 감싼다("“수급인”의 비용으로"). 이것을 흘려보내지 않으면 부담 문형이
#: 호칭과 어미 사이에서 끊긴다 — 특수조건 전체가 "미배분"으로 나왔다
#: (2026-09-09 실측).
_CLOSING_QUOTE = r"[”\"'’」』\)]?"


def _bearer_hit(
    text: str,
    templates: tuple[str, ...],
    aliases: tuple[str, ...],
    *,
    anchor: int = 0,
) -> tuple[str, str, int]:
    """(매칭된 호칭, 그 문형이 있는 문장, 축 키워드와의 거리).

    못 찾으면 ("", "", 큰 값).

    문장을 함께 돌려주는 이유: 근거로 조항 머리를 보여주면 결론과 어긋나 보인다
    ("공기 지연 — 근거: 제8조 1. 공정표를 작성 제출하여야 한다"). 실제 판정을
    만든 문장("돌관작업비는 수급인의 비용으로 시행하여야 한다")을 보여야
    변호사가 검증할 수 있다.

    `anchor` 는 창 안에서 이 축의 키워드가 있는 위치다. 창은 조문 범위로
    잘려 있지만 그 안에도 여러 문장이 있어, 첫 번째로 걸린 부담 문형을 쓰면
    같은 조문의 다른 주제 문장이 근거로 붙는다. 키워드에 **가장 가까운** 문형을
    고른다.
    """
    best: tuple[int, str, re.Match[str]] | None = None
    for alias in aliases:
        p = re.escape(alias) + _CLOSING_QUOTE
        for tpl in templates:
            for m in re.finditer(tpl.format(P=p), text, re.IGNORECASE | re.DOTALL):
                if m.start() <= anchor <= m.end():
                    distance = 0
                else:
                    distance = min(abs(m.start() - anchor), abs(m.end() - anchor))
                if best is None or distance < best[0]:
                    best = (distance, alias, m)
    if best is None:
        return "", "", 1 << 30
    distance, alias, m = best
    return alias, _sentence_around(text, m.start(), m.end()), distance


#: 문장 경계. 한국어 계약은 항·호 기호로도 문장을 나눈다.
#: 단순 줄바꿈은 경계가 **아니다**. PDF 에서 추출한 계약서는 문장 중간에서
#: 하드랩되므로, 줄바꿈을 경계로 보면 "“수급인”은 … 준공예정일까지 …
#: “도급인”에게 납부하여야 한다" 한 문장이 여러 조각으로 쪼개져 주체를 잃는다
#: (2026-09-09 실측: 지체상금 부담자가 도급인으로 읽혔다).
_RX_SENTENCE_BREAK = re.compile(
    r"(?:[.。](?:\s|$)|\n\s*\n|[①-⑳]|(?m:^[ \t]*\d+\.[ \t]))"
)


def _sentence_around(text: str, start: int, end: int, *, limit: int = 220) -> str:
    """주어진 구간을 포함하는 문장을 잘라낸다."""
    left = 0
    for m in _RX_SENTENCE_BREAK.finditer(text, 0, start):
        left = m.end()
    right = len(text)
    m2 = _RX_SENTENCE_BREAK.search(text, end)
    if m2:
        right = m2.start() if m2.group().strip() else m2.end()
    seg = re.sub(r"\s+", " ", text[left:right]).strip()
    return seg[:limit]


def _split_sentences(text: str) -> list[tuple[int, int]]:
    """문장 구간 목록 [(start, end), …]."""
    hay = text or ""
    spans: list[tuple[int, int]] = []
    left = 0
    for m in _RX_SENTENCE_BREAK.finditer(hay):
        end = m.start() if m.group().strip() in ("", None) else m.end()
        if end > left:
            spans.append((left, end))
        left = m.end()
    if left < len(hay):
        spans.append((left, len(hay)))
    return [(s, e) for s, e in spans if (e - s) >= 8]


#: 항(項) 머리. 한국어 계약에서 위험배분이 완결되는 단위는 조문이 아니라
#: 항이다. 호(①②)에서는 자르지 않는다 — 항의 머리에 주제를 적고 호에서
#: 배분하는 구조가 흔하다("3. 공기 지연에 따른 조치 ① … ② 이에 발생하는
#: 모든 비용은 “수급인”의 부담으로 한다").
_RX_PARAGRAPH_MARKER = re.compile(r"(?m)^[ \t]*\d+\.[ \t]")


def _axis_units(text: str, axis: RiskAxis) -> list[tuple[str, int]]:
    """이 축의 키워드가 등장하는 **항** 목록. 각 항목은 (항 텍스트, 키워드 위치).

    스코프를 잘못 잡으면 어느 쪽으로도 틀린다(2026-09-09 실측):

        조문 + 고정 길이   인접 조항의 부담 문형까지 읽어 전 축이 "분담"
        문장              "공기 지연에 따른 조치"가 항 머리에 있고 배분이 두
                          문장 뒤에 오는 구조를 놓쳐 특수조건 전체가 "미배분"

    항으로 자르면 둘 다 피한다. 부담 문형(_BEAR) 자체가 마침표를 넘지 못하므로
    항 안에서도 문장 단위 정확성은 유지되고, 거리 순위가 키워드에 가장 가까운
    배분 문장을 근거로 고른다.
    """
    hay = text or ""
    bounds = {0, len(hay)}
    for m in _RX_ARTICLE_HEADING.finditer(hay):
        bounds.add(m.start())
    for m in _RX_PARAGRAPH_MARKER.finditer(hay):
        bounds.add(m.start())
    edges = sorted(bounds)
    units = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    if not units:
        return []

    hits: list[tuple[str, int]] = []
    seen: set[int] = set()
    for m in axis.context.finditer(hay):
        for idx, (s, e) in enumerate(units):
            if s <= m.start() < e:
                if idx not in seen:
                    seen.add(idx)
                    hits.append((hay[s:e], m.start() - s))
                break
    return hits


def _axis_windows(
    text: str, axis: RiskAxis, *, width: int = 300
) -> list[tuple[str, int]]:
    """이 위험축이 논의되는 구간 목록.

    계약 전체를 그대로 넣으면 다른 조항의 부담 주체 문형을 이 축의 것으로
    착각한다 — 축의 문맥 주변만 잘라서 판정한다. 그리고 구간들을 **하나로
    이어붙이면 안 된다**: 이어붙인 덩어리에서 부담 주체를 찾으면 어느 구간이
    그 판정을 만들었는지 알 수 없어, 근거로 정의 조항("수급인이라 함은 …")
    같은 무관한 문장이 표시된다(2026-09-09 실측). 구간별로 판정한다.

    각 항목은 (구간 텍스트, 그 안에서 축 키워드가 있는 위치)다. 위치를 함께
    돌려주어야 같은 조문 안의 여러 문장 중 키워드에 가장 가까운 부담 문형을
    근거로 고를 수 있다.
    """
    hay = text or ""
    out: list[tuple[str, int]] = []
    seen: set[tuple[int, int]] = set()
    for m in axis.context.finditer(hay):
        # 창은 "이 축이 논의되는 **조문**"이다. 앞뒤로 고정 길이를 잘라내면
        # 양쪽 인접 조항의 부담 주체 문형까지 함께 읽어 전부 "분담"으로
        # 뭉개진다(2026-09-09 실측). 조문 경계로 자른다.
        start = 0
        for b in _RX_ARTICLE_HEADING.finditer(hay, 0, m.start()):
            start = b.start()
        nxt = _RX_ARTICLE_HEADING.search(hay, m.end())
        end = nxt.start() if nxt else len(hay)
        # 조문이 지나치게 길면(조문 구분이 없는 산문형 계약) 창을 제한한다.
        start = max(start, m.start() - width)
        end = min(end, m.end() + width)
        span = (start, end)
        if span in seen:
            continue
        seen.add(span)
        out.append((hay[start:end], m.start() - start))
    return out


#: 조문 머리. 창을 여기서 끊어 인접 조항과 섞이지 않게 한다.
#: **줄 첫머리**에 오는 것만 조문의 시작으로 본다. "산업안전보건법 제89조의
#: 규정에 의하여", "본계약서 제34조, 제35조의 계약해지사유를" 처럼 본문 안에서
#: 다른 조문을 인용하는 표현까지 머리로 오인하면 창이 문장 중간에서 시작해
#: 근거가 결론과 어긋난다(2026-09-09 실측). 항 번호가 붙은 줄("1. 제34조 …")도
#: 앞에 번호가 있어 자연히 걸러진다.
_RX_ARTICLE_HEADING = re.compile(
    r"(?m)^[ \t]*(?:제\s*\d+\s*조(?:\s*의\s*\d+)?|Article\s+\d+)",
    re.IGNORECASE,
)

#: 정의·용어 조항은 위험배분이 아니다. "수급인이라 함은 …" 같은 문장에서
#: 당사자 호칭이 등장한다고 그 축을 그 당사자가 부담한다고 볼 수 없다.
_RX_DEFINITION_CLAUSE = re.compile(
    r"(?:이라\s*함은|라\s*함은|(?:을|를)\s*말한다|의\s*정의|means\b|shall\s+mean)",
    re.IGNORECASE,
)


def build_risk_allocation_matrix(
    text: str, *, our_role_direction: str = "", contract_type_code: str = "",
) -> dict[str, Any]:
    """위험축별 부담 주체 매트릭스. 조항별 finding 생성 **전에** 호출한다."""
    ours_aliases, their_aliases = _side_aliases(our_role_direction)
    rows: list[dict[str, Any]] = []
    for axis in RISK_AXES:
        windows = _axis_units(text or "", axis)
        if not windows:
            rows.append({
                "key": axis.key, "label": axis.label, "side": SIDE_UNALLOCATED,
                "side_label": SIDE_LABELS[SIDE_UNALLOCATED],
                "evidence": "", "note": "계약에서 이 위험을 다루는 조항을 찾지 못했습니다.",
            })
            continue

        # 구간별로 판정하고, 판정을 만든 문장을 그대로 근거로 남긴다.
        # 같은 판정을 낸 구간이 여러 개면 부담 문형이 축 키워드에 **가장
        # 가까운** 것을 근거로 쓴다 — 첫 구간을 쓰면 같은 조문의 다른 주제
        # 문장이 근거로 붙어 결론과 어긋나 보인다(2026-09-09 실측).
        votes: dict[str, tuple[int, str]] = {}   # side -> (거리, 근거)
        for w, anchor in windows:
            if _RX_DEFINITION_CLAUSE.search(w):
                continue  # 정의 조항은 배분이 아니다
            ours_hit, ours_sentence, ours_dist = _bearer_hit(
                w, axis.bearer_templates, ours_aliases, anchor=anchor)
            their_hit, their_sentence, their_dist = _bearer_hit(
                w, axis.bearer_templates, their_aliases, anchor=anchor)
            if axis.beneficiary_templates:
                # 수익자로 지목된 쪽의 **반대편**이 부담자다.
                ben_ours, ben_ours_s, ben_ours_d = _bearer_hit(
                    w, axis.beneficiary_templates, ours_aliases, anchor=anchor)
                ben_theirs, ben_theirs_s, ben_theirs_d = _bearer_hit(
                    w, axis.beneficiary_templates, their_aliases, anchor=anchor)
                if ben_theirs and ben_theirs_d < ours_dist:
                    ours_hit, ours_sentence, ours_dist = (
                        ben_theirs, ben_theirs_s, ben_theirs_d)
                if ben_ours and ben_ours_d < their_dist:
                    their_hit, their_sentence, their_dist = (
                        ben_ours, ben_ours_s, ben_ours_d)
            shared = bool(axis.shared_pattern and axis.shared_pattern.search(w))
            if ours_hit and their_hit:
                side = SIDE_SHARED
                sentence, distance = (
                    (ours_sentence, ours_dist) if ours_dist <= their_dist
                    else (their_sentence, their_dist)
                )
            elif ours_hit:
                side = SIDE_SHARED if shared else SIDE_OURS
                sentence, distance = ours_sentence, ours_dist
            elif their_hit:
                side = SIDE_SHARED if shared else SIDE_COUNTERPARTY
                sentence, distance = their_sentence, their_dist
            elif shared:
                side = SIDE_SHARED
                sentence, distance = re.sub(r"\s+", " ", w).strip(), 1 << 29
            else:
                continue  # 이 구간은 부담 주체를 말하지 않는다
            prev = votes.get(side)
            if prev is None or distance < prev[0]:
                votes[side] = (distance, sentence)

        if not votes:
            side, evidence = SIDE_UNALLOCATED, re.sub(r"\s+", " ", windows[0][0]).strip()
            note = "관련 조항은 있으나 부담 주체가 명시되지 않았습니다."
        elif SIDE_OURS in votes and SIDE_COUNTERPARTY in votes:
            # 구간에 따라 다르게 배분된다 — 실제로 분담 구조다.
            side, evidence = SIDE_SHARED, votes[SIDE_OURS][1]
            note = "조항에 따라 부담 주체가 다릅니다."
        else:
            # 우리 회사 부담이 하나라도 확인되면 그것을 대표로 본다 —
            # 협상에서 중요한 것은 "우리가 지는 칸"이다.
            for pref in (SIDE_OURS, SIDE_COUNTERPARTY, SIDE_SHARED):
                if pref in votes:
                    side, evidence = pref, votes[pref][1]
                    break
            note = ""

        rows.append({
            "key": axis.key, "label": axis.label, "side": side,
            "side_label": SIDE_LABELS[side],
            "evidence": evidence[:220],
            "note": note,
        })

    ours_count = sum(1 for r in rows if r["side"] == SIDE_OURS)
    unallocated = [r["label"] for r in rows if r["side"] == SIDE_UNALLOCATED]
    return {
        "contract_type_code": contract_type_code,
        "our_role_direction": our_role_direction or "(미확정 — provider 로 가정)",
        "rows": rows,
        "ours_count": ours_count,
        "counterparty_count": sum(1 for r in rows if r["side"] == SIDE_COUNTERPARTY),
        "shared_count": sum(1 for r in rows if r["side"] == SIDE_SHARED),
        "unallocated": unallocated,
        "unallocated_count": len(unallocated),
        "summary": (
            f"위험 {len(rows)}축 중 우리 회사 부담 {ours_count}축, "
            f"미배분 {len(unallocated)}축"
            + (f" ({', '.join(unallocated[:5])})" if unallocated else "")
        ),
    }


def concentrated_risk_axes(matrix: dict[str, Any] | None, *, threshold: int = 6) -> list[str]:
    """우리 회사 부담이 과도하게 몰린 경우 그 축 목록(협상 우선순위 근거).

    개별 조항은 각각 수용 가능해 보여도, 지연·하자·안전·제3자·해지 위험이
    한쪽에 몰리면 그 자체가 협상해야 할 구조적 문제다 — 조항 단위 검토로는
    보이지 않는다.
    """
    rows = (matrix or {}).get("rows") or []
    ours = [r["label"] for r in rows if r.get("side") == SIDE_OURS]
    return ours if len(ours) >= threshold else []
