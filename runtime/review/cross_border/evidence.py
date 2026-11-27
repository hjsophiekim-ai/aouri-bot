"""원문 인용(evidence_quote) 정확 일치 검증.

모든 finding 은 계약 원문에서 그대로 잘라 낸 인용문을 가져야 하고, 그 인용문이 원문에 실제로 있어야 한다.
문서 추출 단계가 공백 폭을 바꾸는 일이 있어(“[      ]” → “[ ]”) 비교는 **같은 정규화를 양쪽에 똑같이** 적용한
뒤의 부분 문자열 일치로 한다. 정규화는 공백 접기와 따옴표 통일뿐이며, 낱말·숫자·구두점은 바꾸지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "＂": '"'})


def normalize_for_match(text: str) -> str:
    t = str(text or "").translate(_QUOTES)
    t = re.sub(r"\[\s+", "[", t)
    t = re.sub(r"\s+\]", "]", t)
    return re.sub(r"\s+", " ", t).strip()


def verify_quote(quote: str, source: str) -> bool:
    q = normalize_for_match(quote)
    return bool(q) and len(q) >= 4 and q in normalize_for_match(source)


def quote_around(text: str, start: int, end: int, *, before: int = 60, after: int = 60) -> str:
    """원문에서 [start, end) 주변을 그대로 잘라 낸 인용 — 줄 경계를 넘지 않는다."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end < 0 else line_end
    s = max(line_start, start - before)
    e = min(line_end, end + after)
    return text[s:e].strip()


def filter_verified(findings: list[dict[str, Any]], source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(통과, 폐기). evidence_quote 가 없거나 원문에 없으면 폐기한다 — 폐기 사유를 남긴다."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for f in findings:
        quotes = [q for q in (f.get("evidence_quotes") or [f.get("evidence_quote")]) if q]
        bad = [q for q in quotes if not verify_quote(q, source)]
        if not quotes or bad:
            dropped.append({"clause_id": f.get("clause_id"), "title": f.get("clause_title"),
                            "reason": "원문 인용 없음" if not quotes else "원문에 없는 인용: " + " / ".join(b[:60] for b in bad)})
            continue
        kept.append(f)
    return kept, dropped
