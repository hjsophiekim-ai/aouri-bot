"""Explicit 갑/을 label ↔ company-name binding, shared by party_role.py and
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

_RX_LABEL_BINDING = re.compile(
    r'([^\s(){}\[\]"“”]{1,20})\s*\(\s*이하\s*["“]?\s*(갑|을|병|정)\s*["”]?\s*'
    r"(?:이라\s*)?(?:한다|칭한다|함)\s*\)?"
)


def _looks_like_our_entity(name_fragment: str, entity: str) -> bool:
    if any(tok in name_fragment for tok in _FURSYS_GROUP_TOKENS):
        return True
    entity = (entity or "").strip()
    return bool(entity) and entity in name_fragment


def bound_counterparty_name(text: str, entity: str) -> str | None:
    """Return the counterparty's company name when the contract text's
    "OO(이하 "갑"이라 한다)" style definitions bind exactly one side to us —
    used so a "을(회사명, 이하 ...)" style regex miss doesn't fall back to a
    garbled/empty counterparty name when this cleaner signal is available."""
    matches = list(_RX_LABEL_BINDING.finditer(text or ""))
    if len(matches) < 2:
        return None
    bindings = [(m.group(1).strip("()（）,， "), m.group(2)) for m in matches]
    ours = [b for b in bindings if _looks_like_our_entity(b[0], entity)]
    others = [b for b in bindings if b not in ours]
    if len(ours) == 1 and len(others) == 1:
        return others[0][0]
    return None


def bind_party_labels_to_entities(text: str, entity: str) -> tuple[str, str] | None:
    """Return (our_label, counterparty_label) when the contract text explicitly
    binds a company name to a 갑/을 label (e.g. "㈜퍼시스(이하 "을"이라 한다)")
    and exactly one bound name matches our entity/Fursys Group — else None."""
    matches = list(_RX_LABEL_BINDING.finditer(text or ""))
    if len(matches) < 2:
        return None
    bindings = [(m.group(1).strip("()（）,， "), m.group(2)) for m in matches]
    ours = [b for b in bindings if _looks_like_our_entity(b[0], entity)]
    others = [b for b in bindings if b not in ours]
    if len(ours) == 1 and others:
        return ours[0][1], others[0][1]
    return None


def explicit_role_from_labels(text: str, our_label: str, counterparty_label: str) -> str | None:
    """Return 'supplier' or 'buyer' when the text explicitly self-declares our
    label's role or states the transaction direction between the two labels —
    None when neither explicit pattern is found."""
    ol = re.escape(our_label)
    cl = re.escape(counterparty_label)
    self_supplier = re.search(rf'["“]?{ol}["”]?\s*(?:은|는)[^.]{{0,20}}(매도자|매도인|공급자|판매자)(?:로서)?', text)
    reverse_buy = re.search(
        rf'["“]?{cl}["”]?\s*(?:은|는)[^.]{{0,60}}["“]?{ol}["”]?\s*'
        r"(?:으로부터|로부터)[^.]{0,30}(구매|매수|매입|구입)",
        text,
    )
    if self_supplier or reverse_buy:
        return "supplier"
    self_buyer = re.search(rf'["“]?{ol}["”]?\s*(?:은|는)[^.]{{0,20}}(매수인|구매자|발주자)(?:로서)?', text)
    forward_buy = re.search(
        rf'["“]?{ol}["”]?\s*(?:은|는)[^.]{{0,60}}["“]?{cl}["”]?\s*'
        r"(?:으로부터|로부터)[^.]{0,30}(구매|매수|매입|구입)",
        text,
    )
    if self_buyer or forward_buy:
        return "buyer"
    return None
