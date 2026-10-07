"""사전질문 답변 속 **사업부의 의도**에 직접 답한다 (2026-10-06 범용 보정 4·12항).

사전질문 답변은 원래 "사실"로만 읽었다(user_review_request — 답변 줄이 새 요청으로 세어지지 않게).
그런데 답변에는 사업부가 실제로 원하는 것이 들어 있다.

    "연구성과 미제출시 연구비를 지급하지 않고 싶습니다."                → 대금·성과물 연계 요청
    "지식재산권이 퍼시스에게 있기 때문에 별도의 승인없이 사용할 계획"   → 계약과 다른 전제 위의 계획

담당 사내변호사라면 둘 다 그 자리에서 답한다 — 앞의 것은 "지금 문언으로는 안 되니 이렇게 고친다",
뒤의 것은 "전제가 틀렸다(공동소유·사전 서면승인) — 이대로면 계약 위반이니 이렇게 고친다".

**판단은 새로 하지 않는다.** 같은 쟁점의 finding(본문 MUST/SHOULD)이 있으면 그 finding 의 조항·수정문을
그대로 싣는다 — 요청 답변은 "적정"인데 본문은 "수정 필요"인 모순을 막는다(지시 4항).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from runtime.review.user_review_request import ANSWER_BLOCK_MARKER

V_OK = "적정"
V_FIX = "수정 필요"
V_FACTS = "사실관계 추가확인"
V_BUSINESS = "사업부 결정 필요"

#: 답변이 바람·계획을 말하는가 — 사실 진술("~이 될 것입니다", "정함은 없습니다")은 요청이 아니다.
_RX_INTENT = re.compile(r"싶|원합니다|원함|희망|계획|하려(?:고|는)|할\s*예정|사용할|활용할|지급하지\s*않")
_RX_AFFIRM = re.compile(r"^\s*(?:예|네|있(?:습니다|음)|가능성이\s*있|있을\s*수)")

_RX_PAY_HOLD = re.compile(
    r"(?:미제출|제출하지|납품하지|미이행|미완성|지연)[^.]{0,40}(?:지급하지|미지급|지급을?\s*(?:보류|거절|하지))"
)
_RX_FREE_USE = re.compile(
    r"(?:승인|동의|허락)\s*(?:없이|없어도)[^.]{0,30}(?:사용|활용|이용|게재)|대외[^.]{0,15}활용|홍보[^.]{0,15}(?:사용|활용)"
)
_RX_OWNERSHIP_CLAIM = re.compile(r"(?:지식재산권|저작권|권리|소유권)[^.]{0,10}(?:이|가)?\s*[^.]{0,15}에게\s*(?:있|귀속)|단독\s*소유")
_RX_SUBCONTRACT_Q = re.compile(r"재위탁|하도급|제3자[^.?]{0,15}(?:위탁|맡기|수행)")


@dataclass
class AnswerReview:
    question: str
    answer: str
    topic: str
    label: str
    verdict: str
    clauses: list[str] = field(default_factory=list)
    current_text: str = ""
    conclusion: str = ""
    proposed: list[str] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)

    def to_coverage_row(self) -> dict[str, Any]:
        return {
            "issue_id": f"answer_{self.topic}",
            "original_user_text": f"{self.answer} (사전질문: {self.question})",
            "normalized_issue": self.label,
            "relevant_clause_paths": list(self.clauses),
            "review_status": self.verdict,
            "needs_revision": self.verdict in (V_FIX, V_BUSINESS) or bool(self.proposed),
            "conclusion": self.conclusion,
            "direct_answer": self.conclusion,
            "proposed_clauses": list(self.proposed),
            "current_text": self.current_text,
            "source": "user_answer_intent",
            "topic": self.topic,
            "matched_finding_ids": list(self.finding_ids),
        }


def answer_lines(review_focus: str) -> list[tuple[str, str]]:
    """"[사용자 확인 답변]" 블록의 (질문, 답변)."""
    text = str(review_focus or "")
    if ANSWER_BLOCK_MARKER not in text:
        return []
    block = text.split(ANSWER_BLOCK_MARKER, 1)[1]
    out: list[tuple[str, str]] = []
    for ln in block.splitlines():
        ln = ln.strip().lstrip("-•* ").strip()
        if not ln:
            continue
        # 질문은 "?" 로 끝나고 그 뒤 ": " 다음이 답이다.
        m = re.match(r"(.+?\?)\s*[:：]\s*(.+)$", ln)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def _p(word: str, with_b: str, without_b: str) -> str:
    core = re.sub(r"[\s“”\"'()]+$", "", word or "")
    last = core[-1:] if core else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_b if has else without_b)


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _flat(s: str) -> str:
    return re.sub(r"\s*\n\s*", " ", str(s or "")).strip()


def _live(clause_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [c for c in clause_results or [] if isinstance(c, dict) and not c.get("dedup_suppressed")
            and not c.get("keep_as_is") and str(c.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")]


def _addition(cr: dict[str, Any]) -> str:
    """finding 수정문에서 원문 뒤에 덧붙인(또는 바꾼) 부분만."""
    sr = str(cr.get("suggested_rewrite") or "").strip()
    orig = str(cr.get("original_text") or "").strip()
    if orig and sr.startswith(orig):
        return sr[len(orig):].strip()
    m = re.search(r"다만,.+$", _flat(sr))
    return m.group(0) if m else sr


def _quote(cs: list[Any], limit: int = 220) -> str:
    s = " / ".join(_flat(_attr(c, "text")) for c in cs)
    return s[:limit] + ("…" if len(s) > limit else "")


def _pay_hold(q: str, a: str, *, clauses: list[Any] | None, live: list[dict[str, Any]]) -> AnswerReview | None:
    pkg = next((c for c in live if str(c.get("clause_id") or "").startswith("tx_deliverable_payment")), None)
    if pkg is not None:
        edits = [f"{_attr(pkg, 'display_path')} 말미: {_addition(pkg)}"] + [
            f"{e.get('display_path')} 말미: {e.get('text')}" for e in pkg.get("package_linked_edits") or []]
        gaps = str(pkg.get("rewrite_reason") or "").rstrip(".")
        return AnswerReview(
            question=q, answer=a, topic="payment_on_deliverable", label="성과물 미제출 시 연구비(잔금) 지급 거절",
            verdict=V_FIX, clauses=list(pkg.get("related_clause_paths") or [_attr(pkg, "display_path")]),
            current_text=_quote([pkg]),
            conclusion=(f"아니요 — 지금 문언으로는 미제출을 이유로 지급을 거절할 수 없습니다. {gaps}. "
                        "잔금을 연구보고서 제출·확인 후 지급하도록 하고, 해지 시 초과 지급분을 돌려받는 문언을 함께 넣어야 "
                        "원하시는 결과가 됩니다(본문 MUST FIX ‘성과물 제출·대금 연계’와 같은 수정입니다)."),
            proposed=edits, finding_ids=[str(pkg.get("clause_id"))],
        )
    pay = [c for c in clauses or [] if re.search(r"지급", _attr(c, "text")) and re.search(r"잔금|대금|연구비|용역비", _attr(c, "text"))]
    linked = [c for c in pay if re.search(r"(?:제출|검수|확인|승인)[^.]{0,40}(?:후|때)[^.]{0,40}지급", _flat(_attr(c, "text")))]
    if linked:
        return AnswerReview(
            question=q, answer=a, topic="payment_on_deliverable", label="성과물 미제출 시 대금 지급 거절",
            verdict=V_OK, clauses=[_attr(c, "display_path") for c in linked[:3]], current_text=_quote(linked[:2]),
            conclusion="예 — 대금 지급이 이미 성과물 제출·확인 뒤로 정해져 있어, 미제출이면 지급하지 않아도 됩니다.",
        )
    return None


def _free_use(q: str, a: str, *, clauses: list[Any] | None, live: list[dict[str, Any]]) -> AnswerReview | None:
    ip_cl = [c for c in clauses or [] if re.search(r"지식재산권", _attr(c, "text"))
             and re.search(r"귀속|소유", _attr(c, "text")) and _attr(c, "paragraph_number")]
    ip_cl = [c for c in ip_cl if not re.search(r"이라\s*함은|이란|말한다", _attr(c, "text"))] or ip_cl
    name_cl = [c for c in clauses or [] if re.search(
        r"(?:승인|동의)\s*없이[^.]{0,80}(?:광고|판매\s*촉진|선전|홍보)", _flat(_attr(c, "text")))]
    joint = any(re.search(r"공동\s*소유|공유", _flat(_attr(c, "text"))) for c in ip_cl)
    pkg = next((c for c in live if str(c.get("clause_id") or "").startswith("tx_research_ip")), None)
    if not (joint or name_cl or pkg):
        return None
    parts: list[str] = []
    if _RX_OWNERSHIP_CLAIM.search(a) and joint:
        parts.append(f"답변의 전제와 계약이 다릅니다 — 지식재산권은 단독이 아니라 공동소유입니다"
                     f"({', '.join(_attr(c, 'display_path') for c in ip_cl if re.search(r'공동', _attr(c, 'text')))}).")
    if joint:
        parts.append("공동소유 저작물인 연구보고서는 공유자 전원의 합의 없이 이용할 수 없고(저작권법 제48조 제1항), "
                     "실시하려면 별도 실시계약이 필요하다고 정해져 있습니다.")
    if name_cl:
        parts.append(f"또 {_attr(name_cl[0], 'display_path')}에 따라 상대방이 제출한 문서(연구보고서 포함)의 내용과 상대방 "
                     "명칭을 광고·판매촉진에 쓰려면 사전 서면 승인이 필요합니다.")
    parts.append("지금 계약대로 승인 없이 홍보에 쓰면 계약 위반이 됩니다. 체결 전에 아래 문구로 바꿔야 계획대로 쓸 수 있습니다.")
    proposed: list[str] = []
    paths: list[str] = []
    fids: list[str] = []
    if pkg is not None:
        proposed.append(f"{_attr(pkg, 'display_path')}: {_addition(pkg)}")
        proposed += [f"{e.get('display_path')} 말미: {e.get('text')}" for e in pkg.get("package_linked_edits") or []
                     if any(_attr(n, "display_path") == e.get("display_path") for n in name_cl)]
        paths = list(pkg.get("related_clause_paths") or [])
        fids = [str(pkg.get("clause_id"))]
        parts.append("(본문 MUST FIX ‘연구성과 귀속·활용’과 같은 수정입니다.)")
    for c in ip_cl[:1] + name_cl[:1]:
        if _attr(c, "display_path") not in paths:
            paths.append(_attr(c, "display_path"))
    return AnswerReview(
        question=q, answer=a, topic="result_free_use", label="연구결과·지식재산권의 승인 없는 대외 활용",
        verdict=V_FIX, clauses=paths, current_text=_quote(ip_cl[:1] + name_cl[:1]),
        conclusion=" ".join(parts), proposed=proposed, finding_ids=fids,
    )


def _performer_label(clauses: list[Any] | None) -> str:
    """업무를 수행하는 상대방의 약칭 — 하도급·연구 수행 문장의 주어."""
    body = " ".join(_flat(_attr(c, "text")) for c in clauses or [])
    for rx in (r"[“\"”]([^”\"“]{1,8})[”\"]\s*(?:은|는)\s*[^.]{0,40}(?:하도급|재위탁)",
               r"[“\"”]([^”\"“]{1,8})[”\"]\s*(?:은|는)\s*(?:연구|용역|업무|서비스)를"):
        m = re.search(rx, body)
        if m:
            return f"“{m.group(1)}”"
    return "상대방"


def _subcontract(q: str, a: str, *, clauses: list[Any] | None, live: list[dict[str, Any]]) -> AnswerReview | None:
    if not _RX_AFFIRM.search(a):
        return None
    label = "제3자 수행(하도급·재위탁) 통제"
    sub_cl = [c for c in clauses or [] if re.search(r"재위탁|하도급|제3자에게\s*(?:위탁|수행)", _attr(c, "text"))]
    consent = [c for c in sub_cl if re.search(r"사전\s*(?:서면\s*)?(?:동의|승인)", _flat(_attr(c, "text")))]
    liable = [c for c in sub_cl if re.search(r"책임", _attr(c, "text"))]
    wants_consent = bool(re.search(r"동의|승인", q))
    if consent and (wants_consent or liable):
        # 2026-10-07 실측: "하도급 시 사전 동의 필요?" → "네" 인데 이미 사전 동의 조항이 있는 계약에
        # "재위탁 문언이 없다" 고 답했다. 있는 조항부터 찾는다.
        return AnswerReview(
            question=q, answer=a, topic="subcontracting", label=label,
            verdict=V_OK, clauses=[_attr(c, "display_path") for c in consent[:2]], current_text=_quote(consent[:1]),
            conclusion=(f"예 — {_p(_attr(consent[0], 'display_path'), '이', '가')} 이미 사전 동의를 받아야만 제3자에게 맡길 수 있도록 "
                        "정하고 있어 원하시는 대로입니다. 별도 수정은 필요하지 않습니다."),
            proposed=["해당 없음(현행 유지)"],
        )
    if liable:
        return AnswerReview(
            question=q, answer=a, topic="subcontracting", label=label,
            verdict=V_OK, clauses=[_attr(c, "display_path") for c in liable[:2]], current_text=_quote(liable[:1]),
            conclusion="예 — 제3자에게 맡기더라도 상대방이 책임을 지도록 이미 정해져 있습니다.",
            proposed=["해당 없음(현행 유지)"],
        )
    them = _performer_label(clauses)
    extra = [c for c in clauses or [] if re.search(r"별도[^.]{0,20}(?:용역|비용)|부속\s*합의서", _attr(c, "text"))]
    where = "별도 비용을 정하는 부속합의서 또는 업무 범위 조항" if extra else "업무 범위 조항"
    return AnswerReview(
        question=q, answer=a, topic="subcontracting", label=label,
        verdict=V_BUSINESS, clauses=[_attr(c, "display_path") for c in extra[:1]], current_text=_quote(extra[:1]),
        conclusion=(f"본 계약에는 제3자 수행(재위탁)을 직접 다루는 문언이 없습니다(양도 제한 조항은 권리·의무의 양도만 "
                    f"막습니다). 체결 자체를 막을 사항은 아니고, {where}에 아래 한 문장을 넣으면 충분합니다."),
        proposed=[f"{_p(them, '이', '가')} 업무의 전부 또는 일부를 제3자에게 수행하게 하는 경우에도, 그 수행 결과와 비밀유지에 관한 "
                  f"이 계약상 책임은 {_p(them, '이', '가')} 부담한다."],
    )


_RX_REUSE_PLAN_Q = re.compile(r"(?:게시|광고소재|활용|사용)[^?]{0,40}계획")


def _content_reuse(q: str, a: str, *, clauses: list[Any] | None, live: list[dict[str, Any]]) -> AnswerReview | None:
    if not _RX_AFFIRM.search(a):
        return None
    pkg = next((c for c in live if str(c.get("clause_id") or "").startswith("lr_content_use_rights")), None)
    if pkg is None:
        return None
    paths = list(pkg.get("related_clause_paths") or [_attr(pkg, "display_path")])
    return AnswerReview(
        question=q, answer=a, topic="content_reuse", label="결과물의 자체 채널·광고소재 활용",
        verdict=V_FIX, clauses=paths, current_text=_quote([pkg]),
        conclusion=("아니요 — 지금 계약대로면 계획하신 활용을 할 수 없습니다. " + str(pkg.get("rewrite_reason") or pkg.get("problem") or "")
                    .split(" [연계 수정]")[0] + " (본문 HIGH ‘이용권’과 같은 수정입니다.)"),
        proposed=[f"{_attr(pkg, 'display_path')}: {str(pkg.get('suggested_rewrite') or '').strip()}"],
        finding_ids=[str(pkg.get("clause_id"))],
    )


_TOPICS: tuple[tuple[re.Pattern[str], str, Any], ...] = (
    (_RX_PAY_HOLD, "answer", _pay_hold),
    (_RX_FREE_USE, "answer", _free_use),
    (_RX_SUBCONTRACT_Q, "question", _subcontract),
    (_RX_REUSE_PLAN_Q, "question", _content_reuse),
)


def review_answer_intents(
    *, review_focus: str, clauses: list[Any] | None, clause_results: list[dict[str, Any]] | None,
) -> list[AnswerReview]:
    live = _live(clause_results)
    out: list[AnswerReview] = []
    seen: set[str] = set()
    for q, a in answer_lines(review_focus):
        for rx, where, fn in _TOPICS:
            target = a if where == "answer" else q
            if not rx.search(target):
                continue
            if where == "answer" and not _RX_INTENT.search(a):
                continue
            rv = fn(q, a, clauses=clauses, live=live)
            if rv is not None and rv.topic not in seen:
                seen.add(rv.topic)
                out.append(rv)
            break
    return out


__all__ = ["AnswerReview", "answer_lines", "review_answer_intents"]
