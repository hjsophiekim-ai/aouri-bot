"""조항이 **누구에게** 의무를 지우고 **누가** 권리를 갖는지 — 방향 판단 단일 출처.

2026-09-11 지시 — "기존 조항이 우리 회사에 유리하고 위법·무효 위험이 크지
않으면 KEEP", "상대방에게 새로운 이의권·방어권·시정기간·책임제한을 만들어주는
수정은 특별한 법적 필요가 있을 때만", "거래구조상 우리 회사가 선이행자라면
즉시해지·환수·보전권을 약화하지 말 것".

이 판단들은 전부 같은 질문에 기댄다 — **이 조항은 어느 쪽을 위한 것인가**.
그런데 `accept_keep`, `effect_baseline_review`, `minimal_edit` 이 각자 같은
판단을 따로 구현하면, 한 곳을 고칠 때 다른 곳이 어긋난다(아키텍처 지시가
지적한 바로 그 구조다). 그래서 여기 하나만 둔다.

두 가지를 구분한다 — 조항 성격에 따라 봐야 할 것이 다르기 때문이다.

    의무·책임 조항(배상·부담·보증)   →  **부담자**가 누구인가
    권리 조항(해지권·청구권·승인권)  →  **보유자**가 누구인가

계약서는 당사자를 "갑/을" 이 아니라 회사명·약칭으로 부르는 경우가 많으므로,
우리 호칭(`our_labels`)을 함께 넘겨야 방향이 나온다.
"""
from __future__ import annotations

import re

#: 주격 조사. 목적격("갑을 면책시킨다")은 우리가 **보호받는** 문형이므로
#: 주체로 세면 안 된다 — 그렇게 세면 우리에게 유리한 조항이 전부 반대로 읽힌다.
_SUBJECT_SUFFIX = r"[\"'”’]?\s*(?:은|는|이|가)"

#: 의무·책임을 지는 동사. **어미만** 적는다 — 앞에 여백 패턴을 붙이면 주어를
#: 되짚을 기준점이 흐려진다(주어는 `_effective_subject` 가 따로 고른다).
_BURDEN_VERB = (
    r"(?:부담(?:한다|하며|하여야|하고)"
    r"|배상(?:한다|하여야|하며)"
    r"|책임(?:을)?\s*(?:진다|지며|부담)"
    r"|보증(?:한다|하며|하여야)"
    r"|면책(?:시킨다|하며|하여야))"
)

#: 권리를 행사하는 동사.
_RIGHT_VERB = (
    r"(?:할\s*수\s*있(?:다|으며)"
    r"|청구(?:할\s*수\s*있|한다)"
    r"|요구(?:할\s*수\s*있|한다)"
    r"|해[지제](?:할\s*수\s*있|한다)"
    r"|선택(?:할\s*수\s*있|에\s*따라))"
)

#: 어느 계약에서나 우리를 가리키는 표기.
_GENERIC_OUR_LABELS: tuple[str, ...] = ("당사", "우리")

#: 호칭을 **전혀** 알지 못할 때만 쓰는 추정. 발주자 쪽 관행 표기다.
#:
#: 호출자가 실제 호칭을 넘겨줬는데도 여기에 "갑"을 섞으면, 우리가 을인 계약에서
#: 상대방(갑)의 권리를 우리 권리로 읽어 방향이 통째로 뒤집힌다. 실측: 웹젠
#: 물품공급계약(갑=발주자 웹젠, 을=퍼시스)에서 "갑의 귀책불문 해지권"이 우리
#: 권리로 잡혀 HIGH finding 두 건이 LOW 로 떨어졌다.
_FALLBACK_OUR_LABELS: tuple[str, ...] = ("갑",)

DIRECTION_WE_BEAR = "we_bear"
DIRECTION_THEY_BEAR = "they_bear"
DIRECTION_UNKNOWN = "unknown"


def _labels(our_labels: tuple[str, ...] | None) -> tuple[str, ...]:
    # "갑"·"을" 은 한 글자다. 길이 2 이상만 받으면 정작 계약서가 쓰는 호칭이
    # 전부 걸러진다.
    given = tuple(
        str(x).strip() for x in (our_labels or ()) if str(x or "").strip()
    )
    if given:
        return _GENERIC_OUR_LABELS + given
    return _GENERIC_OUR_LABELS + _FALLBACK_OUR_LABELS


#: 주격 조사 뒤에 이런 관형형 동사가 오면, 그 주어는 문장의 주어가 아니라
#: 뒤 명사를 꾸미는 **관형절의 주어**다. "갑은 을이 입은 손해를 배상한다" 에서
#: 배상하는 주체는 갑이고, 을은 피해자다. 이걸 구분하지 못하면 우리가 피해자로
#: 적힌 조항까지 "우리가 부담한다" 로 읽혀 방향이 정반대로 뒤집힌다.
_RX_ADNOMINAL_AFTER = re.compile(
    r"\s*(?:입은|입을|받은|받을|발생한|발생할|발생하는|당한|겪은|청구한|제기한"
    r"|주장한|부담한|있는|없는|있을|없을|정한|정하는|아닌|아니한|아닐|같은)"
)

#: 주격 조사가 붙은 어절. 뒤에 공백·따옴표가 오는 지점만 주어로 센다.
_RX_SUBJECT_TOKEN = re.compile(
    r"([^\s,.\n]{1,24}?)[\"'”’]?(?:은|는|이|가)(?=[\s\"'”’])"
)


#: 부정형 어미. 동사 매치 바로 뒤에 이것이 오면 의미는 정반대다.
_RX_NEGATED = re.compile(r"\s*하?지\s*(?:아니|않)|\s*(?:없|면제)")

#: 문장 경계. 주어는 **그 동사가 속한 문장** 안에서 찾아야 한다.
_RX_SENTENCE_BREAK = re.compile(r"[.!?\n;]|다\.\s")


def _sentence_start(body: str, verb_start: int) -> int:
    last = 0
    for m in _RX_SENTENCE_BREAK.finditer(body, 0, verb_start):
        last = m.end()
    return last


def _effective_subject(body: str, verb_start: int) -> str:
    """동사 앞쪽에서 **실제 주어**로 볼 어절을 고른다.

    한국어 계약 문장은 주어를 앞에 두므로, 같은 문장 안에서 관형절 주어를
    걸러낸 뒤 **처음 나오는** 어절을 주어로 본다. 동사에 가까운 쪽을 고르면
    "통지 없이"의 "없", "대하여"의 조사 같은 부사구 파편이 잡힌다.
    찾지 못하면 빈 문자열.
    """
    subject = ""
    start = _sentence_start(body, verb_start)
    for m in _RX_SUBJECT_TOKEN.finditer(body, start, verb_start):
        # "입은"·"받은" 같은 관형형은 그 자체가 어절+"은" 으로 잘려 주어처럼
        # 보인다. 후보에서 뺀다.
        if _RX_ADNOMINAL_AFTER.match(body, m.start()):
            continue
        # 뒤에 관형형이 오면 이 주어는 관형절의 주어다(뒤 명사를 꾸민다).
        if _RX_ADNOMINAL_AFTER.match(body, m.end()):
            continue
        subject = m.group(1)
        break
    return subject


def _matches(text: str, labels: tuple[str, ...], verb: str) -> bool:
    body = str(text or "")
    if not body.strip():
        return False
    for m in re.finditer(verb, body):
        if _RX_NEGATED.match(body, m.end()):
            # "책임을 부담하지 아니한다" 는 부담이 아니라 그 반대다.
            continue
        subject = _effective_subject(body, m.start())
        if subject and any(label in subject for label in labels):
            return True
    return False


def ours_bears_burden(clause_text: str, our_labels: tuple[str, ...] = ()) -> bool:
    """이 조항의 **부담자**가 우리 쪽인가."""
    return _matches(clause_text, _labels(our_labels), _BURDEN_VERB)


def ours_holds_right(clause_text: str, our_labels: tuple[str, ...] = ()) -> bool:
    """이 조항의 **권리자**가 우리 쪽인가."""
    return _matches(clause_text, _labels(our_labels), _RIGHT_VERB)


def burden_direction(clause_text: str, our_labels: tuple[str, ...] = ()) -> str:
    """의무·책임의 방향.

    `we_bear`    우리가 부담한다 — 한도·예외를 넣어 우리를 보호해야 한다
    `they_bear`  상대방이 부담한다 — 우리에게 유리하므로 희석하지 않는다
    `unknown`    판단 불가 — 방향에 의존하는 수정을 하지 않는다
    """
    body = str(clause_text or "")
    if not body.strip():
        return DIRECTION_UNKNOWN
    if ours_bears_burden(body, our_labels):
        return DIRECTION_WE_BEAR
    # 우리가 부담자가 아닌데 **긍정형** 부담 문형이 있으면 상대방이 지는 것이다.
    # 부정형("책임을 부담하지 아니한다")은 아무도 지지 않는 면책 문언이므로
    # 여기서 they_bear 로 읽으면 면책 조항이 통째로 우리에게 유리한 것으로
    # 오인된다.
    for m in re.finditer(_BURDEN_VERB, body):
        if not _RX_NEGATED.match(body, m.end()):
            return DIRECTION_THEY_BEAR
    return DIRECTION_UNKNOWN


#: 이 계약에서 우리가 **먼저 이행**하는 구조인가. 선이행자는 동시이행의
#: 항변권을 잃으므로, 즉시해지·환수·보전 수단이 유일한 회수 장치가 된다
#: (2026-09-11 지시 — 그 권리를 약화하지 말 것).
_RX_WE_PERFORM_FIRST = re.compile(
    r"선(?:이행|지급|급금|제공)"
    r"|먼저\s*(?:제공|인도|지급|이행)"
    r"|설치(?:를)?\s*완료(?:함으로써|한\s*후)"
    r"|인도(?:를)?\s*완료한\s*(?:후|뒤)"
    r"|제공한\s*(?:후|뒤)에\s*[^.\n]{0,30}(?:수행|납품|게시|제작)",
)


def we_perform_first(contract_text: str, *, is_non_monetary: bool = False) -> bool:
    """거래구조상 우리가 선이행자인가.

    무현금 교환(바터)에서 우리가 물품·서비스를 먼저 넘기는 구조는 전형적인
    선이행이다. 그 밖에는 명시적 선이행 문형이 있어야 한다.
    """
    body = str(contract_text or "")
    if not body.strip():
        return False
    if _RX_WE_PERFORM_FIRST.search(body):
        return True
    if is_non_monetary and re.search(r"소유권(?:은|이)?[^.\n]{0,40}(?:이전|귀속)", body):
        # 대가가 오가지 않는 교환에서 소유권을 먼저 넘기면 선이행이다.
        return True
    return False
