from __future__ import annotations

import re
from typing import Any


_RX_WS = re.compile(r"\s+")
_RX_BRACKETED = re.compile(r"^\s*[\[\(（【](.+?)[\]\)）】]\s*$")


def _norm_ws(s: str) -> str:
    return _RX_WS.sub(" ", (s or "").strip())


def _strip_brackets(s: str) -> str:
    m = _RX_BRACKETED.match(s or "")
    if m:
        return _norm_ws(m.group(1) or "")
    return _norm_ws(s)


def _is_kr_article_token(tok: str) -> bool:
    t = (tok or "").strip()
    if not t:
        return False
    if re.match(r"^제\s*\d{1,4}\s*조$", t):
        return True
    if re.match(r"^제\s*\d{1,4}\s*항$", t):
        return True
    if re.match(r"^\d{1,4}\s*호$", t):
        return True
    if re.match(r"^[가-하]\s*목$", t):
        return True
    return False


def _dedup_prefix_tokens(prefix: str, title: str) -> tuple[str, str]:
    p = _norm_ws(prefix)
    t = _norm_ws(title)
    if not p or not t:
        return p, t
    if _norm_ws(t).startswith(p + " "):
        t = _norm_ws(t[len(p) :])
        return p, t
    if p in t and t.startswith("제") and p.startswith("제"):
        parts = t.split(" ")
        if parts and _is_kr_article_token(parts[0]) and parts[0] in p:
            t = _norm_ws(" ".join(parts[1:]))
    return p, t


def format_clause_label(
    *,
    display_path: str | None = None,
    clause_title: str | None = None,
    style: str = "bracketed",
) -> str:
    dp = _norm_ws(display_path or "")
    title = _strip_brackets(clause_title or "")
    dp, title = _dedup_prefix_tokens(dp, title)

    if not dp and not title:
        return ""
    if not dp:
        return title
    if not title:
        return dp
    if style == "plain":
        return f"{dp} {title}".strip()
    return f"{dp} [{title}]".strip()


def format_clause_label_from_result(cr: dict[str, Any], *, style: str = "bracketed") -> str:
    return format_clause_label(
        display_path=(cr.get("display_path") if isinstance(cr.get("display_path"), str) else None),
        clause_title=(cr.get("clause_title") if isinstance(cr.get("clause_title"), str) else None),
        style=style,
    )



# ── 조항 경로의 언어 무관 키 (2026-11-02) ────────────────────────────────────
# 사용자는 영문 계약도 "제6.5조", "제13.1조"처럼 국문으로 지목한다. 화면 경로는
# "Article 6.5" 라서 문자열 비교로는 영원히 만나지 않았고, 지목한 조항 5개가 모두
# "해당 조항 없음"으로 답변됐다(Norden 디자인 계약 실측). 번호만 꺼내 비교한다.
_RX_KR_PATH = re.compile(
    r"제\s*(\d{1,4})\s*(?:[.\-]\s*(\d{1,3}))?\s*조(?:\s*의\s*(\d{1,3}))?"
    r"(?:\s*제?\s*(\d{1,3})\s*항)?(?:\s*제?\s*(\d{1,3})\s*호)?"
)
_RX_EN_PATH = re.compile(
    r"(?:article|section|clause|art\.|sec\.|§)?\s*(\d{1,4}(?:\s*\.\s*\d{1,3}){0,3})"
    r"(?:\s*[\(\[]?\s*([a-z]|[ivx]{1,4})\s*[\)\]])?",
    re.IGNORECASE,
)


def clause_path_key(path: str) -> tuple[str, ...] | None:
    """'제6.5조' / '제8조 제3항 제2호' / 'Article 6.5' / 'clause 9.9(b)' → ('6','5') 같은 번호 튜플."""
    s = (path or "").strip()
    if not s:
        return None
    m = _RX_KR_PATH.search(s)
    if m:
        parts = [m.group(1), m.group(2), m.group(4), m.group(5)]
        if m.group(3):  # 제3조의2 → ('3의2', …)
            parts[0] = f"{m.group(1)}의{m.group(3)}"
        return tuple(p for p in parts if p)
    m = _RX_EN_PATH.search(s)
    if m and m.group(1):
        nums = [p for p in re.split(r"\s*\.\s*", m.group(1)) if p]
        if m.group(2):
            nums.append(m.group(2).lower())
        return tuple(nums)
    return None


def clause_path_relation(cited: str, clause: str) -> str:
    """'exact' | 'inside'(조항이 지목 범위 안) | 'contains'(조항이 지목보다 넓음) | ''."""
    a, b = clause_path_key(cited), clause_path_key(clause)
    if not a or not b:
        return ""
    if a == b:
        return "exact"
    if b[: len(a)] == a:
        return "inside"
    if a[: len(b)] == b:
        return "contains"
    return ""
