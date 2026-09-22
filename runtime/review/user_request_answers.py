"""검토요청서의 번호 매긴 요청사항에 **하나씩 직접** 답한다.

2026-09-21 3차 지시 1·5항 —
  "사용자 요청 → 관련 실제 조항 검색 → 현재 문구가 요청을 충족하는지 평가
   → KEEP / 보완 필요 / 별도계약 필요 / 사실확인 필요 중 하나 결정."
  "사용자가 8개 질문을 했다면 각각 반드시 직접 답하세요.
   형식: 판단 / 이유 / 관련 조항 / 필요한 경우에만 수정문구.
   다른 이슈를 섞어 답하지 마세요."

무엇이 문제였나
─────────────
실측(오킨 NDA 수정안, 2026-09-21). 검토요청서의 요청사항은 1~8번으로 또렷이
나뉘어 있는데, 자유서술 파서가 문장·쉼표 단위로 잘라 13조각을 만들었다.

    user_free_1  "Ltd.와 수면센서"                 ← 회사명 중간이 잘렸다
    user_free_2  "모션베드 제어시스템"             ← 요청이 아니다
    user_free_7  "요청사항:"                       ← 머리말이 요청이 됐다

그 결과 "8번 질문에 대한 답" 이라는 것이 리포트에 없다. 담당자는 자기가 물은
것을 찾지 못한다.

**번호 목록은 번호로 나눈다.** 문장 부호로 나누지 않는다.

판정은 네 가지뿐
──────────────
    KEEP           현재 문구가 요청을 이미 충족한다 — 고치지 않는다
    SUPPLEMENT     일부 보완하면 낫다 — 그 부분만 최소로
    SEPARATE       이 계약(NDA)이 아니라 후속 계약에서 정할 사항이다
    NEEDS_FACTS    계약 문언만으로는 판단할 수 없다(다른 언어본 부재 등)

"고칠 게 없다" 도 답이다. 답을 비워 두지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: 다른 언어본·자료 없이 "일치/적정" 으로 결론 내리면 세우는 상태
#: (2026-09-21 4차 지시 10항).
REVIEW_FAILED_MISSING_SOURCE = "REVIEW_FAILED_MISSING_SOURCE"

VERDICT_KEEP = "KEEP"
VERDICT_SUPPLEMENT = "SUPPLEMENT"
VERDICT_SEPARATE = "SEPARATE"
VERDICT_NEEDS_FACTS = "NEEDS_FACTS"

VERDICT_LABELS = {
    VERDICT_KEEP: "적정 — 현재 문구로 충분",
    VERDICT_SUPPLEMENT: "일부 보완 권고",
    VERDICT_SEPARATE: "후속 계약에서 정할 사항",
    VERDICT_NEEDS_FACTS: "확인 불가 — 사실관계·자료 필요",
}

#: "요청사항" 머리말 뒤의 번호 목록. 머리말이 없어도 번호 목록만 있으면 쓴다.
_RX_REQUEST_HEADER = re.compile(r"요청\s*사항|검토\s*요청|질의\s*사항|문의\s*사항")
_RX_NUMBERED_ITEM = re.compile(r"^\s*(\d{1,2})\s*[.)]\s*(\S.*)$")

#: 이 계약에서 정하지 않고 후속 계약으로 넘기는 것이 맞는 주제
#: (지시 6항 — NDA 단계와 개발계약 단계의 구분).
_RX_SEPARATE_CONTRACT_TOPIC = re.compile(
    r"개발\s*범위|개발비|개발\s*비용|일정|성능\s*보증|유지보수|양산"
    r"|최종\s*귀속|소유권\s*확정|단가|대금"
)

#: 다른 언어본이 있어야 답할 수 있는 주제(지시 9항).
_RX_MULTILINGUAL_TOPIC = re.compile(
    r"국문[^.\n]{0,20}영문|영문[^.\n]{0,20}중문|중문[^.\n]{0,20}국문"
    r"|번역본|언어본|3개\s*(?:국어|버전)|일치\s*여부"
)

#: 집행 가능성처럼 계약 문언 밖의 판단이 필요한 주제(지시 8항).
_RX_ENFORCEABILITY_TOPIC = re.compile(
    r"집행\s*가능성|승인[·\s]*집행|뉴욕협약|외국\s*판결|강제\s*집행"
)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


@dataclass(frozen=True)
class RequestTopic:
    """요청 문장에서 읽어낼 주제와, 그 주제를 규정한 조항을 찾는 단서."""

    key: str
    question_rx: re.Pattern[str]
    title_rx: re.Pattern[str]
    body_rx: re.Pattern[str]


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


#: NDA·기술협업 계약에서 실제로 물어 오는 주제들. 계약유형에 상관없이
#: 낱말로만 판단하므로 다른 유형의 요청서에도 그대로 쓸 수 있다.
REQUEST_TOPICS: tuple[RequestTopic, ...] = (
    RequestTopic(
        "third_party_sharing",
        _rx(r"제3자|국내\s*개발사|협력업체|시험기관|인증기관|공유"),
        _rx(r"비밀유지|제3자|개발|공동"),
        _rx(r"제3자[^.\n]{0,80}(?:제공|공개)|협력업체[^.\n]{0,60}제공"),
    ),
    RequestTopic(
        "core_tech_approval",
        _rx(r"핵심기술|사전\s*승인|사전\s*동의|승인\s*범위"),
        _rx(r"비밀유지|SDK|제3자|보호"),
        _rx(r"핵심기술[^.\n]{0,80}(?:승인|동의)"),
    ),
    RequestTopic(
        "ip_ownership_split",
        _rx(r"보유기술|기존\s*기술|개발성과|권리\s*구분|귀속|background|foreground"),
        _rx(r"지식재산|권리\s*귀속|개발"),
        _rx(r"(?:체결\s*전부터|이전부터)\s*보유[^.\n]{0,80}귀속"
            r"|개발\s*성과[^.\n]{0,120}별도"),
    ),
    RequestTopic(
        "independent_development",
        _rx(r"독자\s*개발|독자개발|다른\s*업체|타사와의?\s*협업|제한하지"),
        _rx(r"지식재산|비밀유지|권리"),
        _rx(r"독자(?:적으로)?\s*(?:개발|연구)[^.\n]{0,80}(?:제한되지|할\s*수\s*있)"),
    ),
    RequestTopic(
        "term_and_damages",
        _rx(r"비밀유지\s*기간|보호\s*기간|존속|손해배상|배상\s*범위"),
        _rx(r"기간|위반|배상|책임"),
        _rx(r"비밀유지의무[^.\n]{0,60}(?:\d+\s*년|영업비밀)"
            r"|손해[^.\n]{0,80}(?:직접손해|배상)"),
    ),
    RequestTopic(
        "personal_data",
        _rx(r"개인정보|수면\s*데이터|데이터\s*처리|DPA"),
        _rx(r"데이터|개인정보|보안"),
        _rx(r"개인정보[^.\n]{0,120}(?:법령|별도|처리계약|동의)"),
    ),
    RequestTopic(
        "governing_law_arbitration",
        _rx(r"준거법|중재|KCAB|상사중재|분쟁\s*해결|집행\s*가능성"),
        _rx(r"준거법|분쟁"),
        _rx(r"중재[^.\n]{0,80}(?:최종|구속력|규칙)"),
    ),
    RequestTopic(
        "prevailing_language",
        _rx(r"국문|영문|중문|언어|우선\s*조항|번역"),
        _rx(r"기타|일반|언어"),
        _rx(r"(?:영문|국문|중문)본[^.\n]{0,60}(?:기준|우선)"),
    ),
)


# ── 국제중재 조항의 구성요소 (지시 9항) ──────────────────────────────────
#: "조항이 있다/없다" 가 아니라 **무엇으로 정해져 있는지**를 항목별로 읽는다.
_ARBITRATION_FIELDS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("institution", "중재기관", _rx(
        r"대한상사중재원|KCAB|ICC|SIAC|HKIAC|CIETAC|국제상업회의소"
    )),
    ("seat", "중재지", _rx(
        r"(?:서울|부산|싱가포르|홍콩|런던|베이징|상하이|제네바)(?:에서|특별시)?"
    )),
    ("language", "중재언어", _rx(r"(?:영어|한국어|중국어|영문|국문)로\s*진행")),
    ("arbitrators", "중재인 수", _rx(r"중재인은?\s*(?:\d+\s*인|[일이삼]\s*인)")),
    ("finality", "판정의 구속력", _rx(r"최종적(?:이고|이며)[^.\n]{0,20}구속력")),
)


def extract_arbitration_terms(clause_text: str) -> dict[str, str]:
    """중재 조항에서 항목별 값을 그대로 뽑는다. 없으면 빈 값."""
    body = _norm(clause_text)
    out: dict[str, str] = {}
    for key, _label, pattern in _ARBITRATION_FIELDS:
        m = pattern.search(body)
        out[key] = m.group(0) if m else ""
    return out


def _arbitration_clause_text(clauses: list[Any] | None, found: list[str]) -> str:
    wanted = {re.sub(r"[^\d]", "", p) for p in found}
    parts: list[str] = []
    for c in clauses or []:
        article = str(getattr(c, "article_number", "") or "")
        if article and article in wanted:
            parts.append(str(getattr(c, "text", "") or ""))
    return "\n".join(parts)


def _arbitration_reason(terms: dict[str, str], found: list[str]) -> str:
    settled = [
        f"{label} {terms.get(key)}"
        for key, label, _rxp in _ARBITRATION_FIELDS
        if terms.get(key)
    ]
    unsettled = [
        label for key, label, _rxp in _ARBITRATION_FIELDS if not terms.get(key)
    ]
    head = (
        f"중재 조항은 {', '.join(found)}에 있습니다. " if found
        else "중재 조항을 계약에서 확인했습니다. "
    )
    body = (
        ("확정된 항목 — " + " / ".join(settled) + ". ") if settled
        else "조항에서 읽어낸 구성요소가 없습니다. "
    )
    gap = (
        ("미확정 항목 — " + ", ".join(unsettled) + ". ") if unsettled else ""
    )
    return (
        head + body + gap
        + "다만 상대국에서의 집행 가능성은 계약 문언이 아니라 집행지 법제의 "
        "문제입니다. 중국은 뉴욕협약 가입국이나 상호주의·상사 유보를 두고 있고, "
        "승인·집행은 피신청인 주소지 또는 재산 소재지의 중급인민법원이 관할합니다. "
        "따라서 ① 상대방의 집행 대상 재산이 중국 내에 실재하는지, ② 중재합의의 "
        "서면성과 수권대표 서명이 갖추어졌는지, ③ 판정문의 중국어 번역·공증·인증 "
        "절차를 누가 부담하는지를 별도로 확인해야 합니다. 조항 자체는 수정할 "
        "필요가 없더라도 이 세 가지는 체결 전에 확인하시기 바랍니다."
    )


@dataclass
class RequestAnswer:
    index: int
    question: str
    verdict: str
    reason: str
    clauses: list[str] = field(default_factory=list)
    topic: str = ""
    rewrite_needed: bool = False
    related_finding_ids: list[str] = field(default_factory=list)
    #: 국제중재 질문일 때 항목별로 읽어낸 값(지시 9항).
    arbitration: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "question": self.question,
            "verdict": self.verdict,
            "verdict_label": VERDICT_LABELS.get(self.verdict, self.verdict),
            "reason": self.reason,
            "clauses": list(self.clauses),
            "topic": self.topic,
            "rewrite_needed": self.rewrite_needed,
            "related_finding_ids": list(self.related_finding_ids),
            "arbitration": dict(self.arbitration),
        }


def parse_numbered_requests(text: str) -> list[tuple[int, str]]:
    """검토요청 설명에서 번호 매긴 요청사항만 뽑는다.

    번호 목록이 없으면 빈 목록을 돌려준다 — 없는 것을 지어내지 않는다.
    """
    lines = str(text or "").split("\n")
    out: list[tuple[int, str]] = []
    expected = 1
    seen_header = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if _RX_REQUEST_HEADER.search(line) and len(line) <= 30:
            seen_header = True
            continue
        m = _RX_NUMBERED_ITEM.match(line)
        if not m:
            continue
        num = int(m.group(1))
        body = _norm(m.group(2))
        # 1부터 차례로 올라가는 목록만 요청사항으로 본다 — 본문 중의 우연한
        # 번호("2026년 2. 27.")를 요청으로 세지 않기 위함이다.
        if num != expected:
            continue
        if len(body) < 6:
            continue
        out.append((num, body))
        expected += 1
    if not out:
        return []
    # 머리말도 없고 항목이 둘뿐이면 목록이라고 보기 어렵다.
    if not seen_header and len(out) < 3:
        return []
    return out


def _find_clauses(topic: RequestTopic, clauses: list[Any] | None) -> list[str]:
    """그 주제를 규정한 조항들. 제목을 먼저 보고, 없으면 본문을 본다."""
    by_title: list[str] = []
    by_body: list[str] = []
    for c in clauses or []:
        article = str(getattr(c, "article_number", "") or "")
        if not article:
            continue
        path = f"제{article}조"
        title = str(getattr(c, "title", "") or "")
        body = str(getattr(c, "text", "") or "")
        if topic.body_rx.search(body) and path not in by_body:
            by_body.append(path)
        elif title and topic.title_rx.search(title) and path not in by_title:
            by_title.append(path)
    # 본문에서 실제 규정을 찾은 조항이 먼저다 — 제목만 맞는 조항은 보조다.
    ordered = by_body + [p for p in by_title if p not in by_body]
    return ordered[:3]


def answer_requests(
    *,
    review_focus: str,
    clauses: list[Any] | None,
    clause_results: list[dict[str, Any]] | None,
    contract_type_code: str = "",
    other_language_versions_available: bool = False,
) -> list[RequestAnswer]:
    """요청사항 하나하나에 판단을 붙인다."""
    requests = parse_numbered_requests(review_focus)
    if not requests:
        return []

    open_findings = [
        cr for cr in (clause_results or [])
        if isinstance(cr, dict)
        and not cr.get("dedup_suppressed")
        and not cr.get("keep_as_is")
        and str(cr.get("risk_tier") or cr.get("severity") or "").upper()
        in ("HIGH", "CRITICAL", "MEDIUM")
    ]

    out: list[RequestAnswer] = []
    for index, question in requests:
        topic = next(
            (t for t in REQUEST_TOPICS if t.question_rx.search(question)), None,
        )
        found = _find_clauses(topic, clauses) if topic else []

        # 다른 언어본을 실제로 받지 않았으면 일치 여부는 판단할 수 없다.
        if _RX_MULTILINGUAL_TOPIC.search(question) and not other_language_versions_available:
            out.append(RequestAnswer(
                index=index, question=question, verdict=VERDICT_NEEDS_FACTS,
                topic=(topic.key if topic else ""),
                clauses=found,
                reason=(
                    "국문본만 검토 대상으로 제출되어 영문본·중문본과의 내용 일치 "
                    "여부는 비교할 수 없습니다. 우선언어 조항의 적정성은 "
                    + (f"{', '.join(found)}에서 별도로 판단했습니다." if found
                       else "해당 조항을 찾아 별도로 판단해야 합니다.")
                    + " 세 언어본을 모두 제출해 주시면 대조하겠습니다."
                ),
            ))
            continue

        # 집행 가능성은 계약 문언이 아니라 집행지 법제의 문제다.
        # 지시 9항 — "조항 존재 여부만 확인하지 말고 중재기관·중재지·언어·
        # 중재인 수·집행 가능성·고려사항을 분석하세요. '별도 수정 필요 없음'
        # 한 줄로 끝내지 마세요."
        if _RX_ENFORCEABILITY_TOPIC.search(question):
            clause_text = _arbitration_clause_text(clauses, found)
            terms = extract_arbitration_terms(clause_text)
            out.append(RequestAnswer(
                index=index, question=question, verdict=VERDICT_NEEDS_FACTS,
                topic=(topic.key if topic else ""), clauses=found,
                arbitration=terms,
                reason=_arbitration_reason(terms, found),
            ))
            continue

        related = [
            cr for cr in open_findings
            if topic is not None and (
                topic.question_rx.search(
                    " ".join(
                        _norm(cr.get(k))
                        for k in ("issue_title", "clause_title", "problem")
                    )
                )
                or str(cr.get("display_path") or "") in found
            )
        ]

        if related:
            out.append(RequestAnswer(
                index=index, question=question, verdict=VERDICT_SUPPLEMENT,
                topic=(topic.key if topic else ""), clauses=found or [
                    str(r.get("display_path") or "") for r in related[:3]
                ],
                rewrite_needed=True,
                related_finding_ids=[str(r.get("clause_id") or "") for r in related[:5]],
                reason=(
                    "관련 조항은 있으나 보완이 필요한 점이 확인되었습니다: "
                    + "; ".join(
                        _norm(r.get("issue_title") or r.get("clause_title"))
                        for r in related[:3]
                    )
                ),
            ))
            continue

        if found:
            out.append(RequestAnswer(
                index=index, question=question, verdict=VERDICT_KEEP,
                topic=(topic.key if topic else ""), clauses=found,
                reason=(
                    f"{', '.join(found)}에서 이 쟁점을 정하고 있고, 이번 검토에서 "
                    "수정이 필요한 위험은 확인되지 않았습니다. 현행 문언을 "
                    "유지하시면 됩니다."
                ),
            ))
            continue

        if _RX_SEPARATE_CONTRACT_TOPIC.search(question):
            out.append(RequestAnswer(
                index=index, question=question, verdict=VERDICT_SEPARATE,
                topic=(topic.key if topic else ""),
                reason=(
                    "이 쟁점은 비밀유지 단계가 아니라 후속 개발계약에서 정하는 "
                    "것이 통상적입니다. 지금 계약에 확정형으로 넣으면 아직 정해지지 "
                    "않은 조건을 미리 구속하게 됩니다."
                ),
            ))
            continue

        out.append(RequestAnswer(
            index=index, question=question, verdict=VERDICT_NEEDS_FACTS,
            topic=(topic.key if topic else ""),
            reason=(
                "이 쟁점을 직접 다루는 조항을 계약 문언에서 찾지 못했습니다. "
                "사실관계를 확인한 뒤 조항 신설 여부를 결정해야 합니다."
            ),
        ))
    return out
