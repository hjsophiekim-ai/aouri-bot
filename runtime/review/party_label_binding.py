"""Explicit party-label ↔ company-name binding, shared by party_role.py and
contract_classifier.py so both compute "who are we" the same way instead of
independently re-implementing it (see requirement.md > 변호사형 전체계약
판단, 2026-08-31 지시).

Kept free of imports from either caller module to avoid a circular import —
party_role.py already imports from contract_classifier.py, so this module
must not import from either.
"""
from __future__ import annotations

import re

# Minimal Fursys Group brand token list, intentionally duplicated from
# contract_classifier.FURSYS_GROUP_NAMES (kept tiny and low-churn) rather
# than imported, to keep this module dependency-free.
_FURSYS_GROUP_TOKENS: tuple[str, ...] = (
    "퍼시스홀딩스", "퍼시스", "fursys", "FURSYS",
    "일룸", "iloom", "ILOOM",
    "시디즈", "sidiz", "SIDIZ",
    "데스커", "desker", "DESKER",
    "바로스", "baros", "BAROS",
)

# Korean contracts label the parties either with a semantically-empty
# placeholder (갑/을/병/정) or with a role noun that already states the
# relationship (발주자/공급자/매도인/매수인 ...). Both forms are common and
# contract-type/company-independent — this is a closed vocabulary of legal
# party-role nouns, not a hardcoded exception for any one contract.
_LABEL_WORDS = (
    "갑", "을", "병", "정",
    "발주자", "수급인", "도급인", "시공자",
    "공급자", "공급업자", "매도인", "매도자", "판매자",
    "구매자", "매수인", "매입자",
    "위탁자", "수탁자",
    "임대인", "임차인",
    "대리점",
    "용역제공자", "용역수행자", "용역위탁자", "용역수탁자",
)
_LABEL_ALT = "|".join(_LABEL_WORDS)

# A label that is itself a role noun already states the relationship, so no
# further self-declaration sentence is needed to resolve it.
_SUPPLIER_SIDE_LABELS = frozenset({
    "공급자", "공급업자", "매도인", "매도자", "판매자", "수급인", "시공자",
    "임대인", "수탁자", "용역제공자", "용역수행자", "용역수탁자",
})
_BUYER_SIDE_LABELS = frozenset({
    "발주자", "도급인", "구매자", "매수인", "매입자", "위탁자", "임차인",
    "용역위탁자",
})

_Q = "[\"'“”‘’]?"

_RX_LABEL_BINDING = re.compile(
    r"((?:[^\s(){}\[\]\"'“”‘’]{1,20}[ \t]?){1,4})\(\s*이하\s*" + _Q +
    rf"\s*({_LABEL_ALT})\s*" + _Q +
    r"\s*(?:이라\s*)?(?:한다|칭한다|함)?\s*\)?"
)


def _looks_like_our_entity(name_fragment: str, entity: str) -> bool:
    if any(tok in name_fragment for tok in _FURSYS_GROUP_TOKENS):
        return True
    entity = (entity or "").strip()
    return bool(entity) and entity in name_fragment


_RX_LEADING_PARTICLE = re.compile(r"^(?:와|과|은|는|이|가|를|을)\s+")
# 이름이 조사 하나로만 남는 경우(예: 회사명 자리가 "[ ]" 같은 빈 템플릿
# 칸이라 실제로는 이름이 없는 계약서) — 유효한 회사명이 아니므로 걸러낸다.
_BARE_PARTICLES = frozenset({"와", "과", "은", "는", "이", "가", "를", "을", "의"})


def _clean_name(raw: str) -> str | None:
    s = raw.strip("()（）,， ")
    # 두 번째 이후 바인딩은 바로 앞 정의문의 접속조사("...와", "...는")가
    # 공백 하나를 사이에 두고 회사명 앞에 붙어 캡처되는 경우가 있어 제거.
    s = _RX_LEADING_PARTICLE.sub("", s).strip()
    if len(s) < 2 or s in _BARE_PARTICLES:
        return None
    return s


def _all_bindings(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _RX_LABEL_BINDING.finditer(text or ""):
        name = _clean_name(m.group(1))
        if name is not None:
            out.append((name, m.group(2)))
    return out


def bound_counterparty_name(text: str, entity: str) -> str | None:
    """Return the counterparty's company name when the contract text's
    "OO(이하 "갑"이라 한다)" style definitions bind exactly one side to us —
    used so a "을(회사명, 이하 ...)" style regex miss doesn't fall back to a
    garbled/empty counterparty name when this cleaner signal is available."""
    bindings = _all_bindings(text)
    if len(bindings) < 2:
        return None
    ours = [b for b in bindings if _looks_like_our_entity(b[0], entity)]
    others = [b for b in bindings if b not in ours]
    if len(ours) == 1 and len(others) == 1:
        return others[0][0]
    return None


def bind_party_labels_to_entities(text: str, entity: str) -> tuple[str, str] | None:
    """Return (our_label, counterparty_label) when the contract text explicitly
    binds a company name to a party label (e.g. "㈜퍼시스(이하 "을"이라 한다)"
    or "주식회사 퍼시스(이하 '공급자')") and exactly one bound name matches
    our entity/Fursys Group — else None."""
    bindings = _all_bindings(text)
    if len(bindings) < 2:
        return None
    ours = [b for b in bindings if _looks_like_our_entity(b[0], entity)]
    others = [b for b in bindings if b not in ours]
    if len(ours) == 1 and others:
        return ours[0][1], others[0][1]
    return None


_RX_ROLE_WORD = re.compile(_LABEL_ALT)
_ROLE_WORD_WINDOW = 12


def role_word_near_entity(text: str, entity: str) -> str | None:
    """Fallback for recital formats that state the role directly next to the
    company name instead of inside an "(이하 ...)" bracket — e.g. "매도인
    퍼시스를 (을)이라 칭한다". Returns 'supplier'/'buyer' when a role noun is
    found within a short window of our entity/Fursys-brand mention — the
    closest such role word wins; None when none is found."""
    t = text or ""
    needles = list(_FURSYS_GROUP_TOKENS)
    entity = (entity or "").strip()
    if entity:
        needles.append(entity)
    best_role: str | None = None
    best_dist: int | None = None
    for needle in needles:
        if not needle:
            continue
        for m in re.finditer(re.escape(needle), t):
            start = max(0, m.start() - _ROLE_WORD_WINDOW)
            end = min(len(t), m.end() + _ROLE_WORD_WINDOW)
            window = t[start:end]
            anchor = m.start() - start
            for rm in _RX_ROLE_WORD.finditer(window):
                role = rm.group(0)
                if role in ("갑", "을", "병", "정") or role not in (_SUPPLIER_SIDE_LABELS | _BUYER_SIDE_LABELS):
                    continue
                dist = abs(rm.start() - anchor)
                if best_dist is None or dist < best_dist:
                    best_dist, best_role = dist, role
    if best_role in _SUPPLIER_SIDE_LABELS:
        return "supplier"
    if best_role in _BUYER_SIDE_LABELS:
        return "buyer"
    return None


def explicit_role_from_labels(text: str, our_label: str, counterparty_label: str) -> str | None:
    """Return 'supplier' or 'buyer' for our_label — first from the label
    word itself when it is already a role noun (발주자/공급자/매도인/...),
    otherwise (갑/을/병/정) from a self-declaration or transaction-direction
    sentence in the text. None when nothing resolves it."""
    if our_label in _SUPPLIER_SIDE_LABELS:
        return "supplier"
    if our_label in _BUYER_SIDE_LABELS:
        return "buyer"

    ol = re.escape(our_label)
    cl = re.escape(counterparty_label)
    self_supplier = re.search(rf'{_Q}{ol}{_Q}\s*(?:은|는)[^.]{{0,20}}(매도자|매도인|공급자|판매자)(?:로서)?', text)
    reverse_buy = re.search(
        rf"{_Q}{cl}{_Q}\s*(?:은|는)[^.]{{0,60}}{_Q}{ol}{_Q}\s*"
        r"(?:으로부터|로부터)[^.]{0,30}(구매|매수|매입|구입)",
        text,
    )
    if self_supplier or reverse_buy:
        return "supplier"
    self_buyer = re.search(rf'{_Q}{ol}{_Q}\s*(?:은|는)[^.]{{0,20}}(매수인|구매자|발주자)(?:로서)?', text)
    forward_buy = re.search(
        rf"{_Q}{ol}{_Q}\s*(?:은|는)[^.]{{0,60}}{_Q}{cl}{_Q}\s*"
        r"(?:으로부터|로부터)[^.]{0,30}(구매|매수|매입|구입)",
        text,
    )
    if self_buyer or forward_buy:
        return "buyer"
    return None
