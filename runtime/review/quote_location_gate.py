"""Exact Quote Location Gate — 인용문이 **그 조항 안의 것**인지 검증한다.

2026-09-21 2차 지시 3항 —
  "원문 인용은 반드시 실제 그 조항·항·호에 존재하는 문구만 사용하세요.
   제8조 원문을 제17조 원문처럼 표시 금지 / 제4조 문구를 제20조 원문처럼
   표시 금지. 하나라도 실패하면 REVIEW_FAILED_WRONG_QUOTE_LOCATION."

가짜 인용 게이트로는 잡히지 않는다
──────────────────────────────
기존 `existence_gate` 는 "이 문장이 계약 **어딘가에** 있는가" 를 본다. 그래서
제8조의 문장을 제17조의 원문으로 싣는 오류는 통과한다 — 문장은 진짜이기
때문이다. 틀린 것은 문장이 아니라 **위치**다.

실측(인테리어 2차 본계약, 2026-09-21 15:45 검토):

    CWC-13 | 제17조 | "질의 없이 임의로 시공한 경우 … 수급인이 부담한다"  ← 제8조
    CWC-07 | 제20조 | "수급인은 공정관리·품질관리·안전관리 … 계획서를"      ← 제4조
    CWC-10 | 제16조 | "⑤ 자재 사용설명서·품질보증서·시험성적서"            ← 제12조
    CWP    | 제15조 | "… 준공도서 작성 및 인수인계 — 제4조 및 별첨 …"      ← 제1조

원인은 체크리스트가 앵커 패턴을 **계약 전체**에서 검색해 첫 매치 줄을 잘라
온 것이었다(그 자리는 생성기에서 고쳤다). 이 게이트는 그 뒤에 남는 모든
경로 — AI 논점, counsel 에이전트, 룰 엔진 — 를 상대로 한 마지막 확인이다.

**고치는 것은 인용이지 지적이 아니다.** 앵커는 v14 에서 조 제목·법률효과로
바로잡았으므로 그 자리가 맞다. 잘못 실린 인용만 그 조항 안의 문장으로
바꾸고, 무엇을 바꿨는지 남긴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

REVIEW_FAILED_WRONG_QUOTE_LOCATION = "REVIEW_FAILED_WRONG_QUOTE_LOCATION"

#: 이보다 짧은 조각은 조항 제목·라벨이므로 위치를 따지지 않는다.
MIN_QUOTE_LEN = 20

#: 인용이 그 조항 안에 있다고 볼 유사도.
MATCH_THRESHOLD = 0.85

#: 인용이 아니라 자리표시자인 문자열.
_PLACEHOLDER_HINTS: tuple[str, ...] = (
    "해당 조항 없음", "신설 필요", "조항 위치 확인 필요", "미상", "없음",
)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _contains(haystack: str, needle: str) -> bool:
    hay, need = _norm(haystack), _norm(needle)
    if not need or not hay:
        return False
    if need in hay:
        return True
    matcher = SequenceMatcher(None, need, hay, autojunk=False)
    block = matcher.find_longest_match(0, len(need), 0, len(hay))
    return (block.size / len(need)) >= MATCH_THRESHOLD


def _is_placeholder(quote: str) -> bool:
    q = str(quote or "").strip()
    if not q:
        return True
    if any(h in q for h in _PLACEHOLDER_HINTS):
        return True
    return bool(re.match(r"^\s*[（(].{0,60}[)）]\s*$", q))


def anchored_article(cr: dict[str, Any]) -> str:
    art = str(cr.get("article_number") or "").strip()
    if art:
        return art
    m = re.search(r"제\s*(\d+)\s*조", str(cr.get("display_path") or ""))
    return m.group(1) if m else ""


def _first_substantive_line(article_text: str) -> str:
    """그 조항 안의 첫 실질 문장 — 대체 인용으로 쓴다."""
    lines = [l.strip() for l in str(article_text or "").split("\n")]
    for line in lines[1:] or lines:
        if len(line) >= MIN_QUOTE_LEN:
            return line[:400]
    for line in lines:
        if len(line) >= 12:
            return line[:400]
    return ""


@dataclass
class QuoteLocationReport:
    relocated: list[dict[str, Any]] = field(default_factory=list)
    checked: int = 0

    @property
    def status(self) -> str:
        return REVIEW_FAILED_WRONG_QUOTE_LOCATION if self.relocated else ""

    @property
    def detail(self) -> str:
        if not self.relocated:
            return ""
        names = ", ".join(
            f"{r['clause_id']}({r['display_path']}←제{r['quote_belongs_to']}조)"
            for r in self.relocated[:4]
            if r.get("quote_belongs_to")
        )
        return (
            f"다른 조항의 문장을 원문으로 표시한 항목 {len(self.relocated)}건의 인용을 "
            f"해당 조항의 문장으로 바로잡았습니다{(' — ' + names) if names else ''}."
        )


def enforce_quote_location(
    clause_results: list[dict[str, Any]],
    *,
    index: Any,
    contract_text: str = "",
) -> QuoteLocationReport:
    """각 finding 의 인용이 그 finding 이 가리키는 조항 안의 것인지 확인한다."""
    report = QuoteLocationReport()
    articles = getattr(index, "articles", None)
    if not isinstance(articles, dict) or not articles:
        return report
    if bool(getattr(index, "structure_uncertain", False)):
        return report

    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        if bool(cr.get("is_new_clause")) or bool(cr.get("clause_reference_unresolved")):
            continue
        quote = str(cr.get("original_text") or "")
        if _is_placeholder(quote) or len(_norm(quote)) < MIN_QUOTE_LEN:
            continue
        number = anchored_article(cr)
        if not number or number not in articles:
            continue
        article = articles[number]
        body = str(getattr(article, "exact_text", "") or "")
        if not body:
            continue
        report.checked += 1
        if _contains(body, quote):
            continue

        # 그 인용이 실제로 어느 조항의 것인지 찾는다 — 계약 어디에도 없으면
        # 그것은 위치 문제가 아니라 날조이고, 가짜 인용 게이트의 몫이다.
        owner = ""
        for key, art in articles.items():
            if key == number:
                continue
            if _contains(str(getattr(art, "exact_text", "") or ""), quote):
                owner = key
                break
        if not owner:
            continue

        replacement = _first_substantive_line(body)
        record = {
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or cr.get("clause_title") or "")[:90],
            "quote_belongs_to": owner,
            "was": _norm(quote)[:120],
            "now": _norm(replacement)[:120],
        }
        if replacement:
            cr["original_text"] = replacement
            record["remediation"] = "quote_replaced_with_anchored_article_text"
        else:
            cr["original_text"] = "조항 위치 확인 필요"
            cr["clause_reference_unresolved"] = True
            record["remediation"] = "quote_removed"
        cr["quote_location_corrected"] = record
        report.relocated.append(record)
    return report
