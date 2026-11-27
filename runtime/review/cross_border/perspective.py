"""검토 관점(우리 회사가 계약의 어느 당사자인가) — 국제계약.

2026-11-27 승인 기준: 당사자 표의 지위와 요청문으로 관점을 정하고, 둘이 충돌하거나 요청문이 아무 말도 하지 않으면
추측하지 않고 사전질문으로 묻는다. 그룹사 목록은 그룹사가 실제 당사자로 등장할 때만 쓴다(group_entities).

- 당사자 표에 "구매자 (Buyer / 이하 갑)"처럼 지위가 명시돼 있으면 지위 자체는 확정이다.
- 요청문의 거래 동사(구입·수입 ↔ 판매·공급·수출)가 한쪽만 가리키면 그 지위를 우리 쪽으로 본다.
- 사용자가 사전질문에 답했으면(answers) 그 답이 우선한다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.cross_border.facts import extract_facts
from runtime.review.cross_border.signals import assess_cross_border

QUESTION_ID = "Q-XB-ROLE-001-our-party"

_BUY = re.compile(r"구입|구매|수입하|매입|사들|발주하|purchas|\bbuy|\bimport", re.I)
_SELL = re.compile(r"판매하|공급하|수출하|납품하|\bsell|\bsupply\s+(?:to|the)|\bexport", re.I)
_ROLE_WORDS_IN_REQUEST: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("distributor", re.compile(r"대리점|총판|판매점|distributor|dealer", re.I)),
    ("licensee", re.compile(r"사용권을\s*받|라이선스를\s*받|라이선시|licensee", re.I)),
    ("licensor", re.compile(r"사용권을\s*(?:주|부여)|라이선스를\s*(?:주|부여)|라이선서|licensor", re.I)),
)
_ROLE_FOR_SIDE = {"buy": ("buyer", "licensee", "client", "distributor"), "sell": ("seller", "licensor", "service_provider", "principal")}
_ROLE_LABEL = {"buyer": "구매자", "seller": "공급자", "licensor": "라이선서", "licensee": "라이선시", "distributor": "판매점·대리점",
               "principal": "본사(공급자)", "client": "위탁자", "service_provider": "용역 제공자"}


def user_words(request_text: str) -> str:
    """사용자가 직접 쓴 말만 — 요청 본문 + 사전질문 답변 값. 질문 문구("…공급자의 …은 무엇입니까?")는 뺀다.

    2026-11-27 실측: 질문 문구에 든 거래 동사가 섞여 '구입하는 계약'이라는 요청이 충돌로 판정됐다.
    """
    t = str(request_text or "")
    head, sep, tail = t.partition("[사용자 확인 답변]")
    answers = []
    for ln in tail.splitlines():
        m = re.match(r"^\s*[-•·]?\s*.+?[?？]\s*[:：]\s*(.+)$", ln) or re.match(r"^\s*[-•·]?\s*[^:：]{0,80}[:：]\s*(.+)$", ln)
        if m:
            answers.append(m.group(1))
    return (head + "\n" + "\n".join(answers)).strip()


def resolve_perspective(*, text: str, request_text: str = "", answers: dict[str, Any] | None = None) -> dict[str, Any]:
    a = assess_cross_border(text)
    if not a.is_cross_border:
        return {}
    facts = extract_facts(text)
    roles = [p.role for p in facts.parties]
    ans = str((answers or {}).get(QUESTION_ID) or "").strip()
    if ans and ans in roles:
        return {"confirmed": True, "our_role": ans, "our_label": facts.label_of_role(ans), "basis": "사전질문 답변"}
    if len(facts.parties) < 2:
        return {"confirmed": False, "reason": "당사자 표에 지위가 명시되지 않음"}
    req = user_words(request_text)
    # 요청문이 지위 자체를 말하면(“대리점 계약”, “사용권을 받는”) 거래 동사보다 앞선다
    for role, rx in _ROLE_WORDS_IN_REQUEST:
        if role in roles and rx.search(req):
            return {"confirmed": True, "our_role": role, "our_label": facts.label_of_role(role),
                    "basis": f"당사자 표의 지위({_ROLE_LABEL.get(role, role)}) + 요청문의 지위 표현"}
    buy, sell = bool(_BUY.search(req)), bool(_SELL.search(req))
    if buy == sell:
        return {"confirmed": False, "reason": "요청문이 우리 지위를 가리키지 않거나 서로 다른 지위를 가리킴",
                "options": roles}
    side = "buy" if buy else "sell"
    role = next((r for r in _ROLE_FOR_SIDE[side] if r in roles), "")
    if not role:
        return {"confirmed": False, "reason": "요청문의 거래 방향과 맞는 지위가 당사자 표에 없음", "options": roles}
    return {"confirmed": True, "our_role": role, "our_label": facts.label_of_role(role),
            "basis": f"당사자 표의 지위({_ROLE_LABEL.get(role, role)}) + 요청문의 거래 방향"}


def perspective_question(*, text: str, request_text: str = "") -> Any:
    """관점을 확정하지 못하면 사전질문(Question) — 확정되면 None."""
    p = resolve_perspective(text=text, request_text=request_text)
    if not p or p.get("confirmed"):
        return None
    from runtime.questions.model import Question, QuestionOption

    facts = extract_facts(text)
    opts = [QuestionOption(pf.role, f"{_ROLE_LABEL.get(pf.role, pf.role)}({pf.label}) — {pf.role_word}") for pf in facts.parties]
    if not opts:
        return None
    return Question(
        question_id=QUESTION_ID,
        title="이 국제계약에서 우리 회사는 어느 당사자입니까?",
        description=("같은 조항도 어느 쪽이냐에 따라 정반대의 위험이 됩니다(예: 잔금 공제 조항은 구매자에게 보호, 공급자에게 위험). "
                     f"자동 판정 보류 사유: {p.get('reason', '')}"),
        answer_type="single_choice",
        required=True,
        options=opts,
        tags=["topic:cross_border_party_role", "reason_code:our_party_unsettled"],
        related_rule_ids=[],
    )
