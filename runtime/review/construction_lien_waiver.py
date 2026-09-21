"""유치권 포기 — 공사대금 채권보전 수단이 통째로 사라지는 조항.

2026-09-18 수정 지시 —
  "본문/특약/첨부서류/선행조건/착수조건/지급조건에 유치권 포기, 포기각서 제출,
   불행사 확약, 하수급인 포기각서 징구 의무, 착수금·기성금·준공금 지급의
   선행조건으로 포기각서 요구, 점유·담보·채권보전 제한이 있으면 반드시 별도
   핵심리스크로 검토할 것. 세금·형식·일반 참고사항보다 우선하여 HIGH 후보."

왜 별도 축인가
────────────
유치권은 수급인이 공사대금을 받지 못했을 때 **실제로 작동하는 거의 유일한
자력구제 수단**이다. 민법 제320조는 타인의 물건에 관하여 생긴 채권이 변제기에
있는 경우 그 물건을 유치할 수 있다고 정한다. 공사대금 채권은 그 전형이다.

이것을 포기하면 남는 것은 소송·가압류뿐인데, 그때쯤 도급인은 이미 건물을
사용·처분하고 있고 우리는 일반채권자가 된다. 조항 하나로 회수 순위가
"점유하고 버티는 자" 에서 "번호표 뽑고 기다리는 자" 로 내려간다.

그런데도 이 조항은 계약서 본문이 아니라 **특약·첨부서류·착수 선행조건**에
숨어 있는 경우가 많다. "착수금 지급 전 제출서류: ① 착공계 ② 공정표
③ 유치권 포기각서" 처럼 서류 목록의 한 줄로 들어온다. 조항 검토가 본문만
훑으면 놓친다.

무엇을 말해야 하는가(지시 2항)
────────────────────────────
"유치권 포기 조항 존재" 로 끝내면 담당자는 아무 판단도 할 수 없다. 반드시
  · 누가 포기하는지(수급인만인가, 하수급인·자재업체까지인가)
  · 언제 제출하는지(계약 시·착수 전·기성 청구 시)
  · 지급조건과 어떻게 연결되는지(제출이 지급의 선행조건인가)
  · 하수급인에게까지 징구 의무가 있는지
  · 그래서 우리 채권보전 수단이 얼마나 약해지는지
를 적는다.

수정 방향(지시 기본 방향)
───────────────────────
삭제를 요구하면 협상이 막힌다. **조건부 포기**로 바꾼다 — 도급인이 확정
공사대금을 기한 내 정상 지급하는 것을 전제로만 포기하고, 지급지체·추가공사대금
미지급·확정 기성금 미지급에는 carve-out 을 둔다. 하수급인 징구 의무는 "우리가
실제로 관리 가능한 범위" 로 한정해 무한책임으로 해석되지 않게 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from runtime.review.construction_transaction_model import ConstructionTransactionModel

#: 조항이 실재하나 번호를 특정하지 못했을 때의 표기(지시 5항).
#: 추측한 번호를 적는 것보다 위치를 확인하라고 말하는 편이 낫다.
LOCATION_UNCERTAIN = "조항 위치 확인 필요"


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


# ── 탐지 ────────────────────────────────────────────────────────────────────

#: 유치권을 포기·불행사한다는 문언 그 자체.
RX_LIEN_WAIVER = _rx(
    r"유치권[^.\n]{0,30}(?:포기|불행사|행사하지\s*(?:아니|않)|주장하지\s*(?:아니|않)"
    r"|행사할\s*수\s*없)"
    r"|유치권\s*(?:의)?\s*포기"
    r"|(?:포기|불행사)[^.\n]{0,15}유치권"
)

#: 포기각서·확약서라는 **서류**를 내라는 문언.
RX_WAIVER_DOCUMENT = _rx(
    r"유치권[^.\n]{0,20}(?:포기|불행사)\s*(?:각서|확약서|동의서|증서|서약서)"
    r"|(?:각서|확약서|동의서)[^.\n]{0,20}유치권"
)

#: 하수급인·노무자·자재업체에게까지 받아 오라는 의무.
RX_SUBCONTRACTOR_WAIVER = _rx(
    r"(?:하수급인|하도급(?:업체|인)|협력업체|노무자|근로자|자재(?:업체|업자|납품업자)"
    r"|장비업체|제3자)[^.\n]{0,50}유치권"
    r"|유치권[^.\n]{0,50}(?:하수급인|협력업체|노무자|자재업체)"
)

#: 유치권 조항 구간 안에서 하수급인 징구 의무를 찾는 패턴. 위 정규식과 달리
#: "유치권" 이라는 낱말이 같은 문장에 없어도 된다 — 이미 유치권 조항 안이다.
RX_SUBCONTRACTOR_IN_WINDOW = _rx(
    r"(?:하수급인|하도급(?:업체|인)|협력업체|자재(?:업체|업자)|장비업체|제3자)"
    r"[^.\n]{0,80}(?:포기각서|확약서|징구)"
    r"|징구[^.\n]{0,40}(?:하수급인|협력업체)"
)

#: 그 서류 제출이 **돈을 받는 조건**으로 걸려 있는가.
RX_PAYMENT_PRECONDITION = _rx(
    r"(?:착수금|선급금|계약금|기성금|기성\s*대가|준공금|잔금|공사대금)"
    r"[^.\n]{0,80}유치권"
    r"|유치권[^.\n]{0,80}(?:착수금|선급금|기성금|준공금|잔금)"
    r"|유치권[^.\n]{0,60}(?:제출|징구|제출한\s*후|제출을\s*조건)"
    r"[^.\n]{0,40}(?:지급|청구|착수)"
)

#: 제출서류 목록·선행조건 목록 안에 들어 있는가.
RX_DOCUMENT_LIST_CONTEXT = _rx(
    r"제출\s*(?:서류|문서|자료)|첨부\s*(?:서류|문서)|구비\s*서류|선행\s*조건"
    r"|착수\s*(?:조건|서류)|다음\s*각\s*호의?\s*서류"
)

#: 점유·담보·채권보전 수단 자체를 제한하는 문언.
RX_SECURITY_RESTRICTION = _rx(
    r"점유[^.\n]{0,30}(?:포기|이전|주장하지\s*(?:아니|않)|해제)"
    r"|(?:담보권|저당권|질권)[^.\n]{0,30}(?:설정하지\s*(?:아니|않)|포기)"
    r"|채권\s*보전[^.\n]{0,30}(?:조치|수단)[^.\n]{0,30}(?:하지\s*(?:아니|않)|제한)"
    r"|가압류[^.\n]{0,30}(?:하지\s*(?:아니|않)|포기|신청하지)"
)

#: 이미 조건부(carve-out)로 되어 있는가 — 있으면 우리가 요구할 것이 줄어든다.
RX_CONDITIONAL_CARVEOUT = _rx(
    r"유치권[^.\n]{0,120}(?:다만|단,|그러하지\s*아니|예외)"
    r"|(?:지급(?:하지|을\s*지체|지체)|미지급)[^.\n]{0,80}유치권"
    r"|유치권[^.\n]{0,80}(?:지급(?:하지\s*아니|을\s*지체)|미지급|지체하는\s*경우)"
)

#: 제출 시점 신호.
_TIMING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("계약 체결 시", _rx(r"계약\s*(?:체결|서명)\s*(?:시|과\s*동시)[^.\n]{0,60}유치권"
                       r"|유치권[^.\n]{0,60}계약\s*체결\s*(?:시|과\s*동시)")),
    ("착공·착수 전", _rx(r"착(?:공|수)[^.\n]{0,60}유치권|유치권[^.\n]{0,60}착(?:공|수)")),
    ("기성 청구 시", _rx(r"기성[^.\n]{0,60}유치권|유치권[^.\n]{0,60}기성")),
    ("준공·인도 시", _rx(r"(?:준공|인도|인수인계)[^.\n]{0,60}유치권"
                       r"|유치권[^.\n]{0,60}(?:준공|인도|인수인계)")),
)


@dataclass
class LienWaiverFindings:
    """이 계약의 유치권·채권보전 제한 실태."""

    present: bool = False
    #: 어떤 형태로 나타나는가.
    waiver_clause: bool = False
    waiver_document_required: bool = False
    subcontractor_waiver_required: bool = False
    payment_precondition: bool = False
    in_document_list: bool = False
    security_restriction: bool = False
    conditional_already: bool = False
    submission_timing: str = ""
    #: 이 포기각서가 어느 대금의 선행조건인가 (지시 10항).
    precondition_payments: list[str] = field(default_factory=list)
    #: 근거가 된 계약 원문(인용).
    excerpts: list[str] = field(default_factory=list)

    @property
    def unconditional(self) -> bool:
        """조건 없는 포기인가 — carve-out 이 전혀 없는 상태."""
        return self.present and not self.conditional_already

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "waiver_clause": self.waiver_clause,
            "waiver_document_required": self.waiver_document_required,
            "subcontractor_waiver_required": self.subcontractor_waiver_required,
            "payment_precondition": self.payment_precondition,
            "in_document_list": self.in_document_list,
            "security_restriction": self.security_restriction,
            "conditional_already": self.conditional_already,
            "unconditional": self.unconditional,
            "submission_timing": self.submission_timing,
            "precondition_payments": list(self.precondition_payments),
            "excerpts": list(self.excerpts),
        }


def _excerpt_around(text: str, m: re.Match[str] | None) -> str:
    """매치가 걸린 줄의 **계약 원문 그대로**. 인용은 원문에서만 잘라 온다."""
    if m is None:
        return ""
    body = text or ""
    start = body.rfind("\n", 0, m.start()) + 1
    end = body.find("\n", m.end())
    if end == -1:
        end = len(body)
    return body[start:end].strip()[:400]


#: 조 단위로 끊어 본다. 선행조건은 "착수금을 지급한다 … 1. 착공계 2. 보증서
#: 3. 유치권 포기각서" 처럼 **목록 사이에** 들어오므로, 글자 거리로 재면
#: 놓친다(실측: 같은 조 안에 있는데 80자를 넘어 탐지 실패).
_RX_ARTICLE_SPLIT = re.compile(r"(?=제\s*\d+\s*조)")
_RX_PAYMENT_WORD = _rx(r"착수금|선급금|계약금|기성금|기성\s*대가|준공금|잔금|공사대금")
_RX_PRECONDITION_WORD = _rx(
    r"선행\s*조건|제출(?:한|하는)\s*(?:후|때|경우)|제출을\s*조건|갖추어야|구비"
    r"|모두\s*제출|제출\s*서류|다음\s*각\s*호"
)


#: 계약 원문에 적힌 제출 시점을 **그대로** 뽑는다 (2026-09-21 지시 10항 —
#: "원문에 제출시점이 있으면 '미특정' 이라고 쓰지 마세요").
#:
#: 실측: 제16조 제3호 "유치권 포기각서 : 본 계약 체결일로부터 10일 이내에
#: 제출하며 …" 가 있는데도 종전 표기는 "제출 시점이 특정되지 않음" 이었다.
#: 고정 라벨 4개(계약 체결 시/착공 전/기성 청구 시/준공 시)에만 맞춰 보았기
#: 때문이다. 기한은 계약마다 다르게 쓰이므로 문언을 그대로 인용한다.
#: **우선순위 순서**로 시도한다. 정규식 하나에 `|` 로 늘어놓으면 가장 왼쪽에서
#: 매치되는 것이 이기는데, 그러면 유치권 구간 안의 "③ 착공계의 제출" 이
#: 시점 문언보다 앞서 잡혀 "착공" 이 답이 된다(실측). 구체적인 기한 표현부터
#: 본다.
_TIMING_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    _rx(
        r"(?:[^,.\n:·]{0,20}?(?:로부터|부터|까지|이전에|전까지))?"
        r"\s*\d+\s*(?:일|개월|영업일)\s*(?:이내|전|안)"
    ),
    _rx(r"(?:본\s*)?계약\s*(?:체결|서명)\s*(?:과\s*)?동시"),
    _rx(r"(?:본\s*)?계약\s*체결(?:일|\s*시)"),
    _rx(r"(?:준공|인도|인수인계)\s*(?:검사)?\s*(?:합격)?\s*(?:일|시)(?![가-힣])"),
    _rx(r"기성\s*(?:청구|검사)\s*시(?![가-힣])"),
    # "착공계"·"착수서" 같은 **서류 이름**과 구분한다 — 뒤에 한글이 이어지면
    # 시점 표현이 아니다.
    _rx(r"착(?:공|수)\s*(?:일|시)(?![가-힣])"),
)


#: 유치권 조항 뒤에 이어지는 세부 항목까지 함께 본다. 실측(인테리어 2차
#: 본계약 제16조): 제출 시점이 유치권을 언급한 줄이 아니라 **그 다음 줄의
#: 하위 항목**에 적혀 있다.
#:
#:     3. 유치권 포기각서
#:     - 본 계약 체결과 동시에 제출하며, 계약금(착수금) 지급의 선행조건으로 한다.
#:     - 계약금액 2억원 이상의 주요 하수급인에 대하여도 동일한 내용의 포기각서를
#:       징구하여 제출한다.
#:
#: 그 줄만 보면 "제출 시점 미특정" 이 되고, 하수급인 징구 의무도 놓친다.
_WAIVER_WINDOW_CHARS = 260


def waiver_windows(text: str) -> list[str]:
    """유치권·포기각서 언급 지점과 그 뒤에 이어지는 세부 항목 구간."""
    body = str(text or "")
    out: list[str] = []
    for rx in (RX_WAIVER_DOCUMENT, RX_LIEN_WAIVER):
        for m in rx.finditer(body):
            start = body.rfind("\n", 0, m.start()) + 1
            # 조 제목 줄에서 시작한 구간은 그 조 전체를 끌고 오므로, 다른
            # 호(계약이행보증·하자보수보증)의 기한이 포기각서의 것으로
            # 잘못 읽힌다.
            if re.match(r"\s*제\s*\d+\s*조", body[start : start + 12]):
                continue
            out.append(body[start : m.end() + _WAIVER_WINDOW_CHARS])
    return out


def extract_submission_timing(text: str) -> str:
    """유치권 포기각서의 제출 시점을 계약 문언 그대로 돌려준다."""
    # 구간 우선 — 유치권 포기각서를 **그 자리에서** 규정한 구간을 먼저 본다.
    # 패턴을 먼저 돌리면, 조 제목("제16조(보증 : 이행·하자·유치권 포기)")에서
    # 시작한 구간 안의 "계약이행보증보험증권 … 10일 이내" 가 포기각서의
    # 제출 시점으로 잘못 잡힌다(실측). 조 제목에서 시작한 구간은 아예 뺀다.
    for window in waiver_windows(text):
        flat = re.sub(r"\s*\n\s*", " ", window)
        for pattern in _TIMING_PHRASE_PATTERNS:
            m = pattern.search(flat)
            if m:
                return re.sub(r"\s+", " ", m.group(0)).strip(" ,.-")
    return ""


def precondition_payments(text: str) -> list[str]:
    """유치권 포기각서 제출이 **어느 대금**의 선행조건인지 (지시 10항)."""
    found: list[str] = []
    for block in _RX_ARTICLE_SPLIT.split(str(text or "")):
        if not (RX_LIEN_WAIVER.search(block) or RX_WAIVER_DOCUMENT.search(block)):
            continue
        if not _RX_PRECONDITION_WORD.search(block):
            continue
        for m in _RX_PAYMENT_WORD.finditer(block):
            word = re.sub(r"\s+", "", m.group(0))
            if word not in found:
                found.append(word)
    return found


def _payment_precondition(text: str) -> bool:
    """유치권 포기(각서)가 **돈을 받는 조건**으로 걸려 있는가.

    같은 조 안에 ① 대금 지급 문언 ② 제출·선행조건 문언 ③ 유치권 문언이
    함께 있으면 선행조건 결합으로 본다. 조를 나누지 않고 문서 전체에서 보면
    무관한 조항끼리 엮여 오탐이 된다.
    """
    body = str(text or "")
    if RX_PAYMENT_PRECONDITION.search(body):
        return True
    for block in _RX_ARTICLE_SPLIT.split(body):
        if not RX_LIEN_WAIVER.search(block) and not RX_WAIVER_DOCUMENT.search(block):
            continue
        if _RX_PAYMENT_WORD.search(block) and _RX_PRECONDITION_WORD.search(block):
            return True
    return False


def detect_lien_waiver(text: str) -> LienWaiverFindings:
    """본문·특약·첨부·지급조건 어디에 있든 유치권 관련 문언을 찾아낸다."""
    body = str(text or "")
    out = LienWaiverFindings()
    if not body.strip():
        return out

    m_waiver = RX_LIEN_WAIVER.search(body)
    m_doc = RX_WAIVER_DOCUMENT.search(body)
    m_sub = RX_SUBCONTRACTOR_WAIVER.search(body)
    m_sec = RX_SECURITY_RESTRICTION.search(body)

    out.waiver_clause = m_waiver is not None
    out.waiver_document_required = m_doc is not None
    # 하수급인 징구 의무가 유치권 언급 줄이 아니라 그 다음 하위 항목에
    # 적혀 있는 경우까지 본다 (2026-09-21 지시 10항).
    out.subcontractor_waiver_required = m_sub is not None or any(
        RX_SUBCONTRACTOR_IN_WINDOW.search(re.sub(r"\s*\n\s*", " ", w))
        for w in waiver_windows(body)
    )
    out.security_restriction = m_sec is not None
    out.present = any((m_waiver, m_doc, m_sub, m_sec))
    if not out.present:
        return out

    out.payment_precondition = _payment_precondition(body)
    out.conditional_already = bool(RX_CONDITIONAL_CARVEOUT.search(body))

    # 서류 목록 맥락은 유치권 문언 **주변**에서만 본다. 계약서 어딘가에
    # "제출서류" 라는 말이 있다는 사실만으로는 이 조항이 목록에 들어 있다는
    # 뜻이 아니다.
    anchor = m_doc or m_waiver or m_sub
    if anchor is not None:
        window = body[max(0, anchor.start() - 400): anchor.end() + 400]
        out.in_document_list = bool(RX_DOCUMENT_LIST_CONTEXT.search(window))

    out.submission_timing = extract_submission_timing(body)
    if not out.submission_timing:
        for label, pat in _TIMING_PATTERNS:
            if pat.search(body):
                out.submission_timing = label
                break
    out.precondition_payments = precondition_payments(body)

    for m in (m_waiver, m_doc, m_sub, m_sec):
        ex = _excerpt_around(body, m)
        if ex and ex not in out.excerpts:
            out.excerpts.append(ex)
    return out


# ── 수정 문안 ───────────────────────────────────────────────────────────────

#: 조건부 포기 — 지시가 제시한 문안을 그대로 쓰고, 하수급인 항을 덧붙인다.
CONDITIONAL_WAIVER_CLAUSE = (
    "① 수급인은 도급인이 본 계약에 따른 확정 공사대금을 약정기한 내 정상적으로 "
    "지급하는 것을 전제로 본 공사와 관련한 유치권을 행사하지 아니한다. 다만 "
    "도급인이 지급기한이 도래한 기성금, 준공금, 추가공사대금 등 확정된 금원을 "
    "정당한 사유 없이 지급하지 아니하는 경우에는 그러하지 아니하다.\n"
    "② 제1항에 따라 수급인이 제출하는 유치권 포기각서 또는 확약서에는 제1항 "
    "단서의 내용이 포함된 것으로 보며, 그 내용에 반하는 무조건적 포기 문언은 "
    "효력이 없다.\n"
    "③ 도급인은 유치권 포기각서의 제출을 착수금·기성금·준공금 등 공사대금 지급의 "
    "선행조건으로 삼지 아니한다. 수급인이 제1항의 확약서를 제출한 때에는 관련 "
    "서류 제출의무를 이행한 것으로 본다.\n"
    "④ 하수급인·자재업자 등 제3자의 유치권 포기각서 징구에 관하여 수급인은 자신이 "
    "직접 계약한 하수급인에 대하여 징구에 필요한 합리적인 조치를 다하는 것으로 "
    "의무를 이행한 것으로 보며, 제3자가 이를 거부하는 경우 수급인은 그에 대한 "
    "책임을 지지 아니한다. 다만 도급인이 해당 제3자에게 하도급대금을 직접 지급한 "
    "경우 그 범위에서 수급인의 의무는 소멸한다."
)


def _build_problem(f: LienWaiverFindings) -> str:
    """"누가·언제·어떻게 연결되는가" 를 구체적으로 적는다(지시 2항)."""
    parts: list[str] = []
    who = "수급인(당사)"
    if f.subcontractor_waiver_required:
        who += " 및 하수급인·자재업자 등 제3자"
    parts.append(f"포기 주체: {who}.")

    if f.waiver_document_required:
        timing = f.submission_timing or "제출 시점이 특정되지 않음"
        parts.append(f"유치권 포기각서·확약서의 제출 의무가 있습니다(제출 시점: {timing}).")
    elif f.waiver_clause:
        parts.append("계약 조항 자체로 유치권을 포기·불행사하도록 정하고 있습니다.")

    if f.payment_precondition:
        which = (
            "·".join(f.precondition_payments[:4])
            if f.precondition_payments
            else "착수금·기성금·준공금 등 공사대금"
        )
        parts.append(
            f"그 제출이 {which} 지급의 선행조건으로 연결되어 있어, 포기각서를 내지 "
            "않으면 돈을 받을 수 없는 구조입니다."
        )
    if f.in_document_list:
        parts.append(
            "해당 의무가 본문 조항이 아니라 제출서류 목록·착수 선행조건에 한 줄로 "
            "들어가 있어 조항 검토에서 놓치기 쉽습니다."
        )
    if f.security_restriction:
        parts.append(
            "점유·담보 설정·가압류 등 다른 채권보전 수단까지 함께 제한되어 있어, "
            "유치권 외의 대체 수단도 남지 않습니다."
        )
    if f.conditional_already:
        parts.append(
            "다만 지급지체 등에 관한 예외 문언이 일부 확인되므로, 그 예외의 범위가 "
            "확정 기성금·추가공사대금까지 포함하는지 확인이 필요합니다."
        )
    else:
        parts.append(
            "지급지체·미지급에 대한 예외(carve-out)가 없는 **무조건적 포기**입니다."
        )
    return " ".join(parts)


_LEGAL_REASON = (
    "민법 제320조는 타인의 물건에 관하여 생긴 채권이 변제기에 있는 경우 그 물건을 "
    "유치할 수 있다고 정하며, 공사대금 채권은 그 전형적인 예입니다. 유치권은 수급인이 "
    "공사대금을 받지 못했을 때 별도의 재판 없이 곧바로 행사할 수 있는 사실상 유일한 "
    "자력 구제수단이고, 도급인이 목적물을 사용·처분·담보제공하려면 우리 채권을 먼저 "
    "해결해야 하므로 협상력의 실질이기도 합니다.\n"
    "유치권을 무조건 포기하면 공사대금 미지급 시 남는 수단은 소송과 가압류뿐이며, "
    "그 시점에 도급인은 이미 목적물을 인도받아 사용·처분하고 있고 우리 회사는 담보 없는 "
    "일반채권자가 됩니다. 도급인이 다른 채권자에게 근저당을 설정했거나 도산한 경우 "
    "회수 가능성은 사실상 사라집니다.\n"
    "특히 포기각서 제출이 대금 지급의 선행조건이면, 기성금 분쟁·추가공사비 분쟁이 "
    "생겼을 때 우리 회사는 '돈을 받기 위해 먼저 담보를 내놓아야 하는' 위치에 놓입니다. "
    "하수급인·자재업자의 포기각서까지 징구하도록 되어 있으면, 우리가 통제할 수 없는 "
    "제3자의 거부가 곧 우리 회사의 계약 위반이 되어 무한책임처럼 작동합니다."
)

_NEGOTIATION = (
    "삭제를 요구하면 협상이 막히기 쉽습니다. '포기하지 않겠다'가 아니라 '정상적으로 "
    "지급되면 행사하지 않겠다'는 **조건부 포기**로 제시하십시오 — 도급인이 원하는 것은 "
    "대금을 정상 지급하는 상황에서 공사 목적물이 묶이지 않는 것이므로, 지급을 전제로 한 "
    "포기는 거부 명분이 약합니다.\n"
    "우선순위는 ① 지급지체 시 carve-out(제1항 단서), ② 포기각서 제출을 지급 선행조건에서 "
    "분리(제3항), ③ 하수급인 징구 의무를 '합리적 조치' 로 한정(제4항) 순입니다. "
    "①이 관철되지 않으면 나머지는 의미가 없으므로 ①에 협상력을 집중하십시오."
)

_WORST_CASE = (
    "기성금 2회분과 추가공사비를 받지 못한 상태에서 준공이 임박했는데, 이미 제출한 "
    "무조건적 유치권 포기각서 때문에 현장을 점유해 버틸 수 없어 목적물을 인도하게 되는 "
    "상황. 인도 후 도급인이 하자·지체상금을 주장하며 잔금을 상계하면, 우리 회사는 담보 "
    "없는 일반채권자로서 소송으로만 다투게 되고, 그 사이 도급인이 목적물에 근저당을 "
    "설정하거나 도산하면 투입 원가 전액이 미회수로 남습니다."
)


def lien_waiver_finding(
    findings: LienWaiverFindings,
    *,
    text: str,
    clauses: list[Any] | None,
    model: ConstructionTransactionModel,
) -> dict[str, Any] | None:
    """유치권 포기를 **필수수정(HIGH)** 항목 하나로 만든다.

    수급인 지위에서만 돈다 — 도급인에게 유치권 포기 요구는 정상적인 채권보전
    수단이지 위험이 아니다(우리에게 유리한 조항은 KEEP).
    """
    if not findings.present:
        return None
    if not (model.is_contractor_side and model.is_settled):
        return None

    from runtime.review.redline_instruction import (
        build_redline_instruction, find_article_for_pattern,
        location_insert_after_last_paragraph, paragraph_marker,
    )

    # 앵커는 **유치권 문언 자체**가 있는 조항이어야 한다. 그 조항을 찾지 못하면
    # (특약·첨부·서류목록에만 있는 경우) 번호를 지어내지 않고 위치 확인으로 둔다.
    anchor = RX_WAIVER_DOCUMENT if findings.waiver_document_required else RX_LIEN_WAIVER
    loc = find_article_for_pattern(
        clauses, anchor, title_pattern=_rx(r"유치권|보증|담보|대금|지급"),
    )
    if loc is None and findings.subcontractor_waiver_required:
        loc = find_article_for_pattern(clauses, RX_SUBCONTRACTOR_WAIVER)

    if loc is not None:
        display_path = f"제{loc['article_number']}조"
        edit_location = location_insert_after_last_paragraph(loc)
        edit_type = "insert_after"
        article_number = loc["article_number"]
    else:
        # 조항은 실재하는데(원문에 문언이 있다) 번호를 특정하지 못한 경우다.
        # "신설" 이라고 쓰면 이미 있는 조항을 없는 것처럼 말하게 된다.
        display_path = LOCATION_UNCERTAIN
        edit_location = (
            f"{LOCATION_UNCERTAIN} — 유치권 포기 문언이 있는 조항(또는 특약·첨부서류) "
            "전체를 아래 문안으로 교체"
        )
        edit_type = "replace"
        article_number = None

    marker = paragraph_marker(
        (loc["max_paragraph_number"] + 1) if loc and loc.get("max_paragraph_number") else 1
    )
    clause_text = CONDITIONAL_WAIVER_CLAUSE
    if marker and marker != "①":
        clause_text = f"[{marker} 이하로 신설]\n{clause_text}"

    quoted = findings.excerpts[0] if findings.excerpts else ""
    problem = _build_problem(findings)

    title = "유치권 포기로 공사대금 채권보전 수단이 사라짐"
    if findings.payment_precondition:
        title = "유치권 포기각서 제출이 공사대금 지급의 선행조건으로 걸려 있음"
    elif findings.subcontractor_waiver_required:
        title = "유치권 포기 의무가 하수급인·자재업자까지 확대되어 있음"

    finding: dict[str, Any] = {
        "clause_id": "CWC-LIEN-WAIVER",
        "article_number": article_number,
        "display_path": display_path,
        "clause_title": "유치권 포기·채권보전 수단 제한",
        "clause_topic": "payment",
        "risk_tier": "HIGH",
        "severity": "HIGH",
        "counsel_severity": "HIGH",
        "high_risk": True,
        "must_fix": True,          # UI·DOCX 모두 "필수수정" 으로 표시된다
        "approval_required": True,
        "review_tier": "MUST",
        "issue_title": title,
        "original_text": quoted or LOCATION_UNCERTAIN,
        "problem": problem,
        "legal_business_reason": _LEGAL_REASON,
        "suggested_rewrite": clause_text,
        "recommendation_text": clause_text,
        "proposed_revision": clause_text,
        "rewrite_reason": problem,
        "negotiation_position": _NEGOTIATION,
        "negotiation_strategy": _NEGOTIATION,
        "worst_case_scenario": _WORST_CASE,
        "high_severity_basis": (
            "유치권 포기 — 공사대금 미회수 시 유일한 자력 구제수단이 사라지고, "
            "포기각서가 지급 선행조건으로 걸려 있으면 담보를 먼저 내놓아야 돈을 받는 구조"
        )[:400],
        "confidence": 0.95,
        "is_mandatory": True,
        "is_construction_checklist": True,
        "is_payment_risk_package": True,
        "is_lien_waiver": True,
        "construction_scope": "contractor",
        "construction_tags": ["유치권", "채권보전", "대금회수"],
        "lien_waiver_profile": findings.to_dict(),
        "detected_issue_list": [
            {"issue_title": "[Payment Risk Package] 유치권 포기 — 채권보전 수단 상실"},
        ],
    }
    finding["redline_instruction"] = build_redline_instruction(
        clause_id=finding["clause_id"],
        severity="HIGH",
        edit_location=edit_location,
        edit_type=edit_type,
        target_text=quoted if edit_type == "replace" else "",
        replacement_text=clause_text,
        original_text=quoted if edit_type == "replace" else "",
        reason=problem,
    )
    return finding
