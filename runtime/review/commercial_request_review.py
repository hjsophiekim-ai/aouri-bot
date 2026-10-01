"""User Request Mapping — 상거래 계약의 대표 요청사항에 조항·현재 문구·판단·최소수정문구로 직접 답한다.

2026-10-01 지시 (와이어드 Golden Fix 3·6·10항)
──────────────────────────────────────────
실측(아우리봇 검토본): 요청 ④ "배상 상한 부재" 의 결론이 "【 개인정보보호 】" 였고(조항 제목이
결론 칸에 들어감), 관련 조항으로 개인정보 조항이 연결됐다. 요청 ① 최저가 귀책 구분의 결론은
"【 상품등록 및 변경 】" 이었다.

주제(계약유형과 무관한 상거래 쟁점)
    lowest_price      최저가 보장 — 공급자가 통제할 수 있는 범위인가
    settlement_agent  정산 주체·정산 대행·결제창별 자금흐름
    jurisdiction      관할법원
    damages_cap       손해배상 상한

요청에 적힌 조항 번호("제7조")가 이 문서에서 다른 내용의 조항이면 번호가 아니라 **내용으로**
다시 연결하고 그 사실을 적는다(법무팀 수정본은 조 번호가 바뀌어 있다).
손해배상 상한 질문은 손해배상을 정한 조항에만 연결한다 — 개인정보 조항에 연결하면
REVIEW_FAILED_USER_REQUEST_MAPPING 이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STATUS_MAPPING = "REVIEW_FAILED_USER_REQUEST_MAPPING"

V_OK = "적정"
V_FIX = "수정 필요"
V_FACTS = "사실관계 추가확인"
V_BUSINESS = "사업부 결정 필요"


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass(frozen=True)
class CommercialTopic:
    key: str
    label: str
    question: re.Pattern[str]
    clause: re.Pattern[str]
    #: 이 주제에 연결하면 안 되는 조항(제목) — 오매핑 탐지.
    forbidden_title: re.Pattern[str] | None = None


TOPICS: tuple[CommercialTopic, ...] = (
    CommercialTopic("lowest_price", "최저가 보장과 귀책 구분",
                    _rx(r"최저가|최저\s*판매\s*가|가격\s*보장"),
                    _rx(r"최저(?:판매)?가|가격\s*경쟁력")),
    CommercialTopic("settlement_agent", "정산 주체·정산 대행",
                    _rx(r"정산\s*주체|정산\s*대행|지급\s*주체|결제창|버틀랩|자회사[^.\n]{0,10}정산"),
                    _rx(r"정산[^.\n]{0,80}(?:자회사|대행|담당|결제창)|(?:자회사|대행)[^.\n]{0,80}정산|결제창")),
    # "보관할" 에도 "관할" 이 들어 있다 — 법원·합의관할 문형으로만 찾는다.
    CommercialTopic("jurisdiction", "관할법원",
                    _rx(r"관할"),
                    _rx(r"관할\s*(?:지방)?법원|합의\s*관할|관할로|전속\s*관할")),
    CommercialTopic("damages_cap", "손해배상 상한",
                    _rx(r"배상\s*(?:상한|한도|범위)|책임\s*(?:상한|한도)|손해배상[^.\n]{0,10}(?:상한|한도|제한)|\bcap\b"),
                    _rx(r"손해(?:를|에\s*대해)?\s*(?:배상|부담)|배상(?:하여야|한다|의\s*책임)"),
                    forbidden_title=_rx(r"개인정보")),
)

_RX_CITED = re.compile(r"제\s*(\d+)\s*조(?:\s*제?\s*(\d+)\s*항)?")
_RX_ITEM = re.compile(r"(?:^|\s)(?:[①-⑳]|\(?\d{1,2}[.)])\s*")
#: "배상한다" 에도 "상한" 이 들어 있다 — 앞 글자가 "배" 인 "상한" 은 세지 않는다.
_RX_CAP_PRESENT = re.compile(
    r"손해배상[^.]{0,40}(?:한도|상한액)|(?<!배)상한(?:액|을|으로|은|이)|한도로\s*한다|을\s*한도로"
    r"|초과하(?:지|는)\s*(?:아니|않)|배상\s*총액"
)


@dataclass
class RequestReview:
    question: str
    topic: str
    verdict: str
    clauses: list[str] = field(default_factory=list)
    current_text: str = ""
    conclusion: str = ""
    proposed: list[str] = field(default_factory=list)
    cited_note: str = ""

    def to_coverage_row(self) -> dict[str, Any]:
        return {
            "original_user_text": self.question,
            "normalized_issue": next((t.label for t in TOPICS if t.key == self.topic), self.topic),
            "relevant_clause_paths": list(self.clauses),
            "review_status": self.verdict,
            "needs_revision": self.verdict in (V_FIX, V_BUSINESS) or (self.verdict == V_FACTS and bool(self.proposed)),
            "conclusion": (self.cited_note + " " if self.cited_note else "") + self.conclusion,
            "proposed_clauses": list(self.proposed),
            "current_text": self.current_text,
            "source": "user_request",
            "topic": self.topic,
        }


def split_requests(review_focus: str) -> list[str]:
    """①②… / 1. 2. / 줄바꿈으로 나뉜 요청사항."""
    text = str(review_focus or "").strip()
    # 파이프라인이 요청문 뒤에 덧붙이는 "[사용자 확인 사실관계]" 같은 블록은 요청이 아니다.
    text = re.split(r"\n\s*\n\s*\[|\n\s*\[(?=[^\]]{2,30}\])", text, maxsplit=1)[0].strip()
    if not text:
        return []
    parts = [p.strip(" \t-•■·") for p in _RX_ITEM.split(text)]
    parts = [p for p in parts if len(p) >= 3]
    if len(parts) <= 1:
        parts = [ln.strip(" \t-•■·") for ln in text.splitlines() if len(ln.strip()) >= 3]
    return parts


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _flat(s: str) -> str:
    return re.sub(r"\s*\n\s*", " ", s or "").strip()


def _find(topic: CommercialTopic, clauses: list[Any] | None, *, limit: int = 4) -> list[Any]:
    hits = []
    for c in clauses or []:
        if not _attr(c, "article_number"):
            continue
        if topic.forbidden_title and topic.forbidden_title.search(_attr(c, "title")) \
                and not topic.clause.search(_flat(_attr(c, "text"))):
            continue
        if topic.clause.search(_flat(_attr(c, "text"))) or topic.clause.search(_attr(c, "title")):
            hits.append(c)
    hits.sort(key=lambda c: _attr(c, "clause_id") in _APPENDIX)
    return hits[:limit]


def _appendix_ids(clauses: list[Any] | None) -> set[str]:
    """조 번호가 1부터 다시 시작한 뒤의 조항 — 별첨(판매 합의서 등)이다. 본문 조항과 같은
    번호를 쓰므로 그대로 적으면 "제2조" 가 본문 제2조로 읽힌다."""
    out: set[str] = set()
    top = 0
    restarted = False
    for c in clauses or []:
        art = _attr(c, "article_number")
        if not art.isdigit():
            continue
        n = int(art)
        if top >= 3 and n < top - 2:
            restarted = True
        top = max(top, n) if not restarted else top
        if restarted:
            out.add(_attr(c, "clause_id"))
    return out


_APPENDIX: set[str] = set()


def _paths(cs: list[Any]) -> list[str]:
    out: list[str] = []
    for c in cs:
        p = _attr(c, "display_path")
        if p and _attr(c, "clause_id") in _APPENDIX:
            p = f"[별첨] {p}"
        if p and p not in out:
            out.append(p)
    return out


def _cited_note(question: str, found: list[Any], clauses: list[Any] | None, topic: CommercialTopic) -> str:
    m = _RX_CITED.search(question)
    if not m:
        return ""
    art = m.group(1)
    if any(_attr(c, "article_number") == art for c in found):
        return ""
    cited = [c for c in clauses or [] if _attr(c, "article_number") == art]
    if not cited:
        return f"요청에 적힌 제{art}조는 이 문서에 없습니다 — 내용 기준으로 연결했습니다."
    title = re.sub(r"[【】\[\]]", "", _attr(cited[0], "title")).strip() or "다른 내용"
    return f"요청에 적힌 제{art}조는 이 문서에서 '{title}' 조항입니다 — 내용 기준으로 연결했습니다."


def _j(word: str, with_b: str, without_b: str) -> str:
    last = word[-1:] if word else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_b if has else without_b)


def _quote(cs: list[Any], limit: int = 220) -> str:
    s = " / ".join(_flat(_attr(c, "text")) for c in cs)
    return s[:limit] + ("…" if len(s) > limit else "")


# ── 주제별 판단 ─────────────────────────────────────────────────────────────

def _lowest_price(found: list[Any], *, model: Any, protections: list[Any]) -> tuple[str, str, list[str]]:
    if any(p.protection.key == "lowest_price_controllable" for p in protections):
        return V_OK, ("공급자가 직접 판매하는 가격만 프로모션 기간 동안 제한하고, 제3자가 더 낮은 가격에 파는 "
                      "경우 공급자는 책임을 지지 않습니다. 공급자가 통제할 수 있는 범위로 한정되어 있어 현행 유지가 "
                      "적정합니다."), []
    sup = getattr(model, "supplier_label", "") or "공급사"
    sel = getattr(model, "seller_label", "") or "판매사"
    text = " ".join(_flat(_attr(c, "text")) for c in found)
    period = "공동구매 개시일 전 2주부터 종료일 후 2주까지" if re.search(r"전후\s*2\s*주|2\s*주씩", text) \
        else "합의한 최저가 유지기간"
    proposal = (
        f"{sup}는 {sel}의 {period}의 기간 동안 해당 상품을 합의한 공동구매 판매가보다 낮은 가격으로 직접 "
        f"판매하여서는 아니 된다. 다만, {sup} 이외의 제3자가 해당 상품을 더 낮은 가격으로 판매하는 경우 "
        f"{sup}는 이에 대하여 책임을 부담하지 아니한다."
    )
    return V_FIX, (f"현재 문언은 {sup}가 최저가를 '보장·유지'하도록 되어 있어, {sup}가 통제할 수 없는 다른 "
                   "판매업체의 할인·쿠폰까지 환불·보상 책임으로 돌아올 수 있습니다. 직접판매만 제한하고 제3자 "
                   "저가판매는 책임을 지지 않도록 귀책을 나눠야 합니다."), [proposal]


def _settlement(found: list[Any], *, model: Any, protections: list[Any]) -> tuple[str, str, list[str]]:
    sup = getattr(model, "supplier_label", "") or "공급사"
    sel = getattr(model, "seller_label", "") or "판매사"
    agent = getattr(model, "payment_agent", "") or "정산 대행자"
    retained = any(p.protection.key == "payment_agent_liability_retained" for p in protections) \
        or bool(getattr(model, "payment_agent_retained", False))
    flows = list(getattr(model, "payment_flows", []) or [])
    mixed = len(flows) >= 2 and not getattr(model, "flows_separated", False)
    split = (
        f"고객이 {sup}의 결제창에서 결제하는 경우 {sup}가 판매대금을 수취하고 합의한 판매수수료를 {sel}에 "
        f"지급한다. 고객이 {sel} 또는 {sel}가 지정한 정산 대행자의 결제창에서 결제하는 경우 {sel}가 판매대금을 "
        f"수취하고 정산한 공급대금을 {sup}에 지급한다."
    )
    keep_liab = (f"{sel}가 {agent}에 정산금의 산정 및 지급 업무를 대행하게 하는 경우에도 {sup}에 대한 정산금 "
                 f"지급의무 및 이 계약상 책임은 {sel}가 부담한다.")
    if not retained:
        return V_FIX, (f"{_j(agent, '이', '가')} 정산을 담당한다고만 되어 있고, {_j(agent, '이', '가')} 지급하지 않을 때 {sel}가 책임진다는 "
                       f"문언이 없습니다. {_j(agent, '은', '는')} 계약당사자가 아니므로 계약상 지급책임이 {sel}에 남도록 "
                       "명시해야 합니다." + (" 결제창(일룸·판매사)에 따라 돈의 흐름도 달라지므로 두 경우를 나눠 "
                                          "적어야 합니다." if mixed else "")), [keep_liab] + ([split] if mixed else [])
    if mixed:
        return V_FACTS, (f"{_j(agent, '이', '가')} 대행하더라도 지급책임은 {sel}에 남도록 이미 정해져 있어 그 부분은 적정합니다. "
                         f"다만 '{sup}가 고객 대금을 직접 받고 수수료를 지급'하는 구조와 '{sel}(또는 {agent})가 "
                         f"정산금을 지급'하는 구조가 함께 적혀 있어, 실제 결제창 운영 방식을 확인한 뒤 두 경우를 "
                         "나눠 적어야 합니다."), [split]
    return V_OK, (f"{_j(agent, '이', '가')} 대행해도 지급책임은 {sel}가 부담하도록 정해져 있고 결제 흐름도 하나로 정리되어 "
                  "있습니다. 현행 유지가 적정합니다."), []


def _jurisdiction(found: list[Any], *, model: Any, protections: list[Any]) -> tuple[str, str, list[str]]:
    text = " ".join(_flat(_attr(c, "text")) for c in found)
    if re.search(r"서울중앙지방법원|합의관할", text):
        return V_OK, ("국내 법인 간 계약에서 서울중앙지방법원을 제1심 합의관할로 정해 두어 현행 유지가 적정합니다."), []
    if re.search(r"주소지|본점\s*소재지", text):
        return V_OK, ("상대방 주소지 관할법원으로 되어 있으나, 두 당사자 모두 서울 소재 국내 법인이어서 실제 "
                      "불이익은 크지 않습니다. 원하면 '서울중앙지방법원을 제1심 전속적 합의관할법원으로 한다'로 "
                      "정리할 수 있으나 필수 수정사항은 아닙니다."), []
    return V_OK, "국내 법인 간 계약의 일반적인 관할 조항으로 현행 유지가 적정합니다.", []


def _damages_cap(found: list[Any], *, model: Any, protections: list[Any]) -> tuple[str, str, list[str]]:
    text = " ".join(_flat(_attr(c, "text")) for c in found)
    if _RX_CAP_PRESENT.search(text):
        return V_OK, "손해배상 범위에 한도가 이미 정해져 있습니다.", []
    proposal = (
        "고의 또는 중대한 과실로 인한 손해, 제조물책임, 개인정보 침해, 지식재산권 침해 및 표시·광고 관련 법령 "
        "위반으로 인한 손해를 제외하고, 이 계약 위반으로 인한 각 당사자의 손해배상책임은 손해 발생일이 속한 "
        "달 직전 [○]개월간 이 계약에 따라 지급된 금액(또는 해당 프로모션의 거래대금) 상당액을 한도로 한다."
    )
    return V_BUSINESS, (
        "손해배상 조항은 있으나 상한이 없습니다. 모든 손해에 같은 상한을 두면 제조물책임·개인정보 침해처럼 "
        "법령상 제한이 부적절한 책임까지 묶이므로, 일반 계약위반에 한해 상한을 두는 것이 적절합니다. 상한 "
        "금액(기간·기준 금액)은 거래 규모를 보고 사업부가 정해야 합니다. 위치: 손해배상 범위 조항을 해지 "
        "조항 다음 조로 추가."
    ), [proposal]


_ANALYZERS = {
    "lowest_price": _lowest_price,
    "settlement_agent": _settlement,
    "jurisdiction": _jurisdiction,
    "damages_cap": _damages_cap,
}


def review_commercial_requests(
    *,
    review_focus: str,
    clauses: list[Any] | None,
    model: Any = None,
    protections: list[Any] | None = None,
) -> list[RequestReview]:
    out: list[RequestReview] = []
    _APPENDIX.clear()
    _APPENDIX.update(_appendix_ids(clauses))
    for q in split_requests(review_focus):
        topic = next((t for t in TOPICS if t.question.search(q)), None)
        if topic is None:
            continue
        found = _find(topic, clauses)
        verdict, conclusion, proposed = _ANALYZERS[topic.key](found, model=model, protections=protections or [])
        out.append(RequestReview(
            question=q, topic=topic.key, verdict=verdict, clauses=_paths(found),
            current_text=_quote(found), conclusion=conclusion, proposed=proposed,
            cited_note=_cited_note(q, found, clauses, topic),
        ))
    return out


def merge_into_coverage(
    coverage: list[dict[str, Any]] | None, reviews: list[RequestReview], *, clauses: list[Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """기존 coverage 행을 같은 요청의 정밀 답변으로 바꾼다. (새 coverage, 고친 오매핑 기록)."""
    rows = [dict(r) for r in (coverage or []) if isinstance(r, dict)]
    fixed: list[dict[str, str]] = []
    titles = {(_attr(c, "display_path")): _attr(c, "title") for c in clauses or []}
    def _core(s: str) -> str:
        s = re.split(r"\n\s*\n", str(s or ""), maxsplit=1)[0]
        return re.sub(r"[\s①-⑳()]|^\d+[.)]", "", s)

    for rv in reviews:
        new = rv.to_coverage_row()
        key = _core(rv.question)[:12]
        idx = next((i for i, r in enumerate(rows)
                    if key and (key in _core(r.get("original_user_text"))
                                or _core(r.get("original_user_text"))[:12] in _core(rv.question))), None)
        if idx is None:
            rows.append(new)
            continue
        old = rows[idx]
        topic = next(t for t in TOPICS if t.key == rv.topic)
        old_paths = [str(p) for p in old.get("relevant_clause_paths") or []]
        bad = [p for p in old_paths if topic.forbidden_title is not None
               and topic.forbidden_title.search(titles.get(p, "") or p)]
        if bad or re.match(r"^\s*【", str(old.get("conclusion") or "")):
            fixed.append({"request": rv.question, "was": ", ".join(old_paths) or str(old.get("conclusion") or ""),
                          "now": ", ".join(rv.clauses), "code": STATUS_MAPPING})
        rows[idx] = new
    return rows, fixed


__all__ = [
    "STATUS_MAPPING", "TOPICS", "RequestReview", "V_BUSINESS", "V_FACTS", "V_FIX", "V_OK",
    "merge_into_coverage", "review_commercial_requests", "split_requests",
]
