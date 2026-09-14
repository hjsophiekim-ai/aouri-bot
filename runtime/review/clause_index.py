"""검증된 Clause Index — "이 계약에 실제로 존재하는 것" 의 단일 목록.

2026-09-14 지시(Hallucination Zero) 항목 4 —
  "검토 시작 전에 실제 원문에서 article_id / title / paragraph / subparagraph /
   exact_text 형태의 Clause Index 를 만들고, 이후 모든 finding·rewrite·UI·DOCX 는
   이 index 만 참조. AI 가 자유롭게 조항번호를 생성하지 못하게 할 것."

왜 필요했나 (실측 — SNS마케팅 제휴계약(실사례), 2026-09-14)
────────────────────────────────────────────────────────────
계약은 **제1조부터 제10조까지** 다. 그런데 검토 결과에 이런 항목이 실렸다.

    CP-006  "제12조 제3항 — 해지 시 정산 및 산출물 인도 기준 보완 필요"
            원문: "[제12조] 계약의 해제 및 해지 관련 조항"
    CP-007  "제14조 — 손해배상 범위 보완 필요"
    CP-008  "제11조 — 을의 포트폴리오·외부 공개 금지 조항 보완 필요"

제11·12·14조는 **존재하지 않는다.** 원인은 콘텐츠 제작 체크리스트가 표준계약서
양식의 조항번호를 상수로 박아 두고, 실제 계약에서 그 조항을 못 찾으면
`clause_text or "[제12조] … 관련 조항"` 으로 **번호가 든 가짜 원문**을 만들어
낸 것이었다. 담당자에게는 "제12조를 이렇게 고치라" 로 읽힌다 — 존재하지 않는
조항을 고치라는 지시다.

설계 원칙
────────
· **파서를 새로 만들지 않는다.** 조항 구조 판단의 주체는 이미
  `clause_extraction` 하나로 정해져 있다(v8: 판단 주체가 여럿이면 갈라진다).
  이 모듈은 그 결과를 **색인**으로 바꾸고, 원문으로 **대조**만 한다.
· 모르는 것은 모른다고 한다. 구조를 확신할 수 없으면 `structure_uncertain` 을
  세우고, 그 상태에서는 조항 존재를 단정하지 않는다(지시 항목 9).
· 인용 검증은 **원문 문자열 대조**로 한다. AI 에게 묻지 않는다.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

#: 인용문이 원문과 이 비율 이상 일치해야 "원문" 으로 표시할 수 있다(지시 항목 3).
QUOTE_MATCH_THRESHOLD = 0.90

#: 이 길이 미만의 인용은 대조 의미가 없다(조항 제목 등). 검증 대상에서 뺀다.
MIN_QUOTE_LEN = 12

STATUS_CLAUSE_STRUCTURE_UNCERTAIN = "CLAUSE_STRUCTURE_UNCERTAIN"

_RX_ARTICLE_IN_TEXT = re.compile(r"제\s*(\d{1,3})\s*조")


def _norm(text: str) -> str:
    """대조용 정규화 — 공백·따옴표·괄호 모양 차이로 인용이 어긋나지 않게."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = re.sub(r"\s+", "", s)
    return s


@dataclass(frozen=True)
class IndexedArticle:
    """원문에서 실재가 확인된 조(條) 하나."""

    number: str                                   # "10"
    title: str                                    # "부속 문서의 효력"
    paragraphs: tuple[str, ...] = ()              # ("1", "2")
    items: dict[str, tuple[str, ...]] = field(default_factory=dict)  # 항 -> 호
    exact_text: str = ""

    @property
    def display(self) -> str:
        return f"제{self.number}조"

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.number,
            "display": self.display,
            "title": self.title,
            "paragraphs": list(self.paragraphs),
            "subparagraphs": {k: list(v) for k, v in self.items.items()},
            "exact_text": self.exact_text,
        }


@dataclass
class ClauseIndex:
    """계약 하나의 검증된 조항 목록. 모든 존재 판단은 여기를 거친다."""

    articles: dict[str, IndexedArticle] = field(default_factory=dict)
    contract_text: str = ""
    structure_uncertain: bool = False
    uncertainty_reasons: list[str] = field(default_factory=list)
    _normalized: str = ""

    # ── 존재 확인 ────────────────────────────────────────────────────────────

    def has_article(self, number: Any) -> bool:
        return self._key(number) in self.articles

    def has_paragraph(self, number: Any, paragraph: Any) -> bool:
        art = self.articles.get(self._key(number))
        if art is None:
            return False
        p = self._key(paragraph)
        # 항 구조를 뽑지 못한 조항에서는 "없다" 고 단정하지 않는다.
        return not art.paragraphs or p in art.paragraphs

    def has_item(self, number: Any, paragraph: Any, item: Any) -> bool:
        art = self.articles.get(self._key(number))
        if art is None:
            return False
        known = art.items.get(self._key(paragraph))
        return not known or self._key(item) in known

    def title_of(self, number: Any) -> str:
        art = self.articles.get(self._key(number))
        return art.title if art else ""

    def title_matches(self, number: Any, title: str) -> bool:
        """표시된 조 제목이 원문의 제목과 맞는가.

        원문에서 제목을 못 뽑았거나 표시된 제목이 비어 있으면 **어긋났다고
        하지 않는다** — 모르는 것으로 무엇을 지우지 않는다.
        """
        actual = _norm(self.title_of(number))
        claimed = _norm(title)
        if not actual or not claimed:
            return True
        return actual in claimed or claimed in actual

    # ── 인용 검증 (지시 항목 3) ──────────────────────────────────────────────

    def quote_exists(self, quote: str, *, threshold: float = QUOTE_MATCH_THRESHOLD) -> bool:
        """이 문장이 계약 원문에 실제로 있는가.

        완전 일치를 먼저 보고, 아니면 같은 길이 구간과의 최대 유사도를 본다.
        `threshold` 미만이면 원문으로 표시할 수 없다.
        """
        needle = _norm(quote)
        if len(needle) < MIN_QUOTE_LEN:
            # 짧은 조각(조항 제목·라벨)은 대조 의미가 없다. 막지 않는다.
            return True
        hay = self._norm_text()
        if not hay:
            return True
        if needle in hay:
            return True
        return self.quote_similarity(quote) >= threshold

    def quote_similarity(self, quote: str) -> float:
        needle = _norm(quote)
        hay = self._norm_text()
        if not needle or not hay:
            return 0.0
        if needle in hay:
            return 1.0
        matcher = SequenceMatcher(None, needle, hay, autojunk=False)
        block = matcher.find_longest_match(0, len(needle), 0, len(hay))
        return block.size / len(needle) if needle else 0.0

    # ── 신설 조항 (지시 항목 2·6) ────────────────────────────────────────────

    def max_article(self) -> int:
        numbers = [int(n) for n in self.articles if n.isdigit()]
        return max(numbers) if numbers else 0

    def next_new_article(self) -> str:
        """신설 조항에 쓸 수 있는 다음 번호. 구조를 모르면 빈 문자열."""
        top = self.max_article()
        return str(top + 1) if top else ""

    def new_clause_label(self, *, topic: str = "") -> str:
        nxt = self.next_new_article()
        if not nxt:
            return "해당 조항 없음 — 신설 필요"
        head = f"해당 조항 없음 — 제{nxt}조 신설 필요"
        return f"{head} ({topic})" if topic else head

    # ── 텍스트에서 조 번호 뽑기 ──────────────────────────────────────────────

    @staticmethod
    def referenced_articles(text: str) -> list[str]:
        return [str(int(m.group(1))) for m in _RX_ARTICLE_IN_TEXT.finditer(str(text or ""))]

    def unknown_articles(self, text: str) -> list[str]:
        """이 문장이 가리키는 조 번호 중 원문에 없는 것."""
        if self.structure_uncertain or not self.articles:
            # 구조를 확신하지 못하면 "없다" 고 단정하지 않는다(지시 항목 9).
            return []
        seen: list[str] = []
        for n in self.referenced_articles(text):
            if n not in self.articles and n not in seen:
                seen.append(n)
        return seen

    # ── 직렬화 ───────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "articles": [
                self.articles[k].to_dict()
                for k in sorted(self.articles, key=lambda x: int(x) if x.isdigit() else 0)
            ],
            "article_numbers": sorted(
                self.articles, key=lambda x: int(x) if x.isdigit() else 0
            ),
            "max_article": self.max_article(),
            "next_new_article": self.next_new_article(),
            "structure_uncertain": self.structure_uncertain,
            "uncertainty_reasons": list(self.uncertainty_reasons),
            "status": STATUS_CLAUSE_STRUCTURE_UNCERTAIN if self.structure_uncertain else "",
        }

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _norm_text(self) -> str:
        if not self._normalized and self.contract_text:
            self._normalized = _norm(self.contract_text)
        return self._normalized

    @staticmethod
    def _key(value: Any) -> str:
        raw = str(value or "").strip()
        digits = re.sub(r"[^\d]", "", raw)
        return str(int(digits)) if digits.isdigit() else ""


def build_clause_index(text: str, clauses: list[Any] | None) -> ClauseIndex:
    """추출된 조항 목록을 검증된 색인으로 바꾼다.

    조항 구조의 **판단 주체는 `clause_extraction` 하나**다. 여기서 원문을 다시
    파싱해 두 번째 판단을 만들지 않는다 — 그러면 두 판단이 어긋나는 순간
    어느 쪽이 맞는지 알 수 없게 된다(v8 아키텍처의 핵심 교훈).

    원문은 **제목 보강과 인용 대조**에만 쓴다.
    """
    body = str(text or "")
    index = ClauseIndex(contract_text=body)

    grouped: dict[str, dict[str, Any]] = {}
    for chunk in (clauses or []):
        number = _attr(chunk, "article_number")
        key = ClauseIndex._key(number)
        if not key:
            continue
        slot = grouped.setdefault(
            key, {"title": "", "paragraphs": [], "items": {}, "texts": []}
        )
        title = str(_attr(chunk, "title") or "").strip()
        if title and not slot["title"]:
            slot["title"] = title
        para = ClauseIndex._key(_attr(chunk, "paragraph_number"))
        if para and para not in slot["paragraphs"]:
            slot["paragraphs"].append(para)
        item = ClauseIndex._key(_attr(chunk, "item_number"))
        if para and item:
            slot["items"].setdefault(para, [])
            if item not in slot["items"][para]:
                slot["items"][para].append(item)
        chunk_text = str(_attr(chunk, "text") or "").strip()
        if chunk_text:
            slot["texts"].append(chunk_text)

    titles_from_text = _titles_from_text(body)
    for key, slot in grouped.items():
        index.articles[key] = IndexedArticle(
            number=key,
            title=slot["title"] or titles_from_text.get(key, ""),
            paragraphs=tuple(sorted(slot["paragraphs"], key=_as_int)),
            items={p: tuple(sorted(v, key=_as_int)) for p, v in slot["items"].items()},
            exact_text="\n".join(slot["texts"])[:4000],
        )

    _assess_uncertainty(index, body)
    return index


def _attr(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _as_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


#: "제10조 (부속 문서의 효력)" 에서 제목만. 괄호 없는 형태도 받는다.
_RX_HEADING = re.compile(
    r"제\s*(\d{1,3})\s*조\s*(?:[(\[（]\s*([^)\]）\n]{1,40})\s*[)\]）]|[ \t]+([^\n(（]{1,40}))?"
)


def _titles_from_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _RX_HEADING.finditer(text or ""):
        key = str(int(m.group(1)))
        title = (m.group(2) or m.group(3) or "").strip()
        if title and key not in out:
            out[key] = title
    return out


def _assess_uncertainty(index: ClauseIndex, text: str) -> None:
    """구조를 신뢰할 수 있는지 판단한다(지시 항목 9).

    믿을 수 없으면 존재/부재를 단정하지 않는다 — 그 상태에서 "없는 조항" 이라고
    단정하면, OCR 이 깨졌을 뿐인 멀쩡한 조항을 지우게 된다.
    """
    reasons: list[str] = []
    if not index.articles:
        reasons.append("원문에서 조(條) 구조를 하나도 확인하지 못했습니다.")
    else:
        numbers = sorted(int(n) for n in index.articles if n.isdigit())
        # 원문에 등장하는 조 번호 중 색인에 없는 것 — 파싱이 일부를 놓쳤다는 뜻.
        in_text = {int(n) for n in ClauseIndex.referenced_articles(text)}
        missed = sorted(n for n in in_text if n <= (numbers[-1] if numbers else 0)
                        and str(n) not in index.articles)
        if missed:
            reasons.append(
                "원문에 나타나는 조 번호 중 구조 추출에서 빠진 것이 있습니다: "
                + ", ".join(f"제{n}조" for n in missed[:8])
            )
        if numbers and numbers[0] != 1:
            reasons.append(f"조 번호가 제{numbers[0]}조부터 시작합니다.")
        gaps = [n for n in range(1, (numbers[-1] if numbers else 0)) if n not in set(numbers)]
        if gaps:
            reasons.append(
                "조 번호가 연속되지 않습니다(빠진 번호: "
                + ", ".join(f"제{n}조" for n in gaps[:8]) + ")."
            )
    index.uncertainty_reasons = reasons
    index.structure_uncertain = bool(reasons)
