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

