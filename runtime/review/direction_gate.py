"""수정안 방향 게이트 — 우리 측 권리를 줄이거나 의무를 늘리는 수정 문구를 생성 단계에서 차단한다(범용).

2026-11-27 실측: 구매자(우리)가 불량 수량을 잔금에서 공제하는 계약에 "공제/상계는 당사자 간 사전 서면합의가 있는
경우에 한한다", "갑은 정산서 및 증빙을 제공하고, 을은 이의제기할 수 있다" 를 추가하라는 수정안이 나왔다. 공제권자는
우리인데 우리 공제권을 묶고 우리 의무를 늘리는 문안이다. 템플릿이 "상대방이 공제하는 계약"만 가정했기 때문이다.

판정은 계약 유형·회사명과 무관하게 문장 구조로 한다.

1. **권리 축소** — 추가 문장이 권리 계열(공제·상계, 해지·해제, 청구·환급, 검수·거절)을 제한하는 표현("사전 서면합의가
   있는 경우에 한한다", "할 수 없다", "only with prior written consent" …)을 담고, 그 권리의 행사자가
   (a) 문장에서 우리 호칭이거나 (b) 문장에 행사자가 없으면 **계약 원문에서 그 권리를 행사하는 쪽이 우리**일 때.
2. **의무 확대** — 추가 문장의 주어가 우리 호칭이고 의무 동사(제공·부담·지급·배상·보증·이행·통지 …)로 끝나는데
   원문에 같은 의무가 없을 때. 상호 의무("각 당사자", "Each Party")는 제외한다.

차단하면 그 문장만 수정안에서 빼고, 남는 문장이 없으면 수정안을 거둔다. 지적(위험) 자체는 지우지 않는다 —
수정 문구가 잘못됐을 뿐 위험은 남기 때문이다. 무엇을 왜 뺐는지 `direction_blocked` 에 남긴다.
"""
from __future__ import annotations

import re
from typing import Any

#: 권리 계열 — 이름, 낱말.
RIGHT_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("공제·상계", re.compile(r"공제|차감|상계|set[- ]?off|deduct", re.I)),
    ("해지·해제", re.compile(r"해지|해제|terminat|rescind|rescission", re.I)),
    ("청구·환급", re.compile(r"청구|환급|refund|reimburs|claim", re.I)),
    ("검수·거절", re.compile(r"검수|거절|반송|reject|inspect", re.I)),
)

#: 권리를 묶는 표현.
RX_RESTRICT = re.compile(
    r"사전\s*(?:서면\s*)?(?:합의|동의|승인)(?:가|이|를)?\s*(?:있는|얻은|받은)?\s*(?:경우|때)?(?:에)?\s*(?:한한다|한하여|에\s*한)"
    r"|(?:합의|동의|승인)(?:가|이)?\s*있는\s*경우(?:에|로)?\s*(?:한|제한)"
    r"|경우로\s*제한|제한한다|할\s*수\s*없다|하지\s*못한다|에\s*한하여"
    r"|\bonly\s+(?:if|with|upon|after)\b|\bsubject\s+to\s+(?:the\s+)?(?:other\s+party'?s\s+)?(?:prior\s+)?(?:written\s+)?(?:consent|agreement|approval)"
    r"|\bshall\s+not\b|\bmay\s+not\b",
    re.I,
)

RX_OBLIGATION = re.compile(
    r"(?:제공|부담|지급|배상|보증|이행|통지|보고|협조|제출|보상|면책)(?:하여야|해야|하고|하며|한다|하기로|할\s*의무)"
    r"|\bshall\s+(?:provide|bear|pay|indemnify|compensate|guarantee|notify|report|submit|reimburse)",
    re.I,
)
RX_MUTUAL = re.compile(r"각\s*당사자|양\s*당사자|쌍방|상호|\b(?:each|either|both)\s+part(?:y|ies)\b", re.I)

#: 정의어 묶음 — `구매자 (Buyer / 이하 "갑")`, `Buyer ("Party A")`, `구매자(이하 "갑")`.
_Q = r"[\"“”'‘’]"
RX_DEFINITION = re.compile(
    rf"(?P<a>[가-힣A-Za-z][가-힣A-Za-z ]{{0,20}}?)\s*[(（]\s*(?:(?P<b>[A-Za-z][A-Za-z ]{{0,20}}?)\s*/\s*)?(?:이하|hereinafter)?\s*{_Q}?\s*"
    rf"(?P<c>[가-힣A-Za-z][가-힣A-Za-z ]{{0,15}}?)\s*{_Q}?\s*(?:이라\s*한다|라\s*한다)?\s*[)）]"
)


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _ws(t: str) -> str:
    return re.sub(r"\s+", " ", _s(t)).strip()


def sentences(text: str) -> list[str]:
    t = _s(text).replace("[추가]", "\n")
    parts = re.split(r"(?<=[.。!?])\s+|\n+|(?<=다)\s*[,，]?\s+(?=[①-⑳]|\(\d+\)|\d+\.\s)|(?=[①-⑳])", t)
    return [p.strip() for p in parts if p and p.strip()]


def label_groups(contract_text: str) -> list[set[str]]:
    """계약 서두·당사자 표의 정의어 묶음."""
    groups: list[set[str]] = []
    for m in RX_DEFINITION.finditer(_s(contract_text)[:20000]):
        a = (m.group("a") or "").split()[-1:]   # 정의되는 낱말은 괄호 바로 앞 한 낱말("본 계약서는 구매자" → "구매자")
        names = {x.strip() for x in (*a, m.group("b"), m.group("c")) if x and x.strip()}
        names = {n for n in names if 1 <= len(n) <= 20 and not re.fullmatch(r"이하|hereinafter", n, re.I)}
        if len(names) < 2:
            continue
        for g in groups:
            if g & names:
                g |= names
                break
        else:
            groups.append(set(names))
    return groups


def expand_labels(labels: list[str], contract_text: str) -> list[str]:
    out = {x for x in labels if x}
    for g in label_groups(contract_text):
        if g & out:
            out |= g
    return sorted(out, key=len, reverse=True)


def _subject_rx(labels: list[str]) -> re.Pattern[str] | None:
    """주어로 쓰인 호칭 — 소유격("갑의 요청")은 주어가 아니다."""
    labs = [re.escape(x) for x in labels if x]
    if not labs:
        return None
    return re.compile(rf"(?:{_Q})?(?:{'|'.join(labs)})(?:{_Q})?\s*(?:은|는|이|가)(?![가-힣])|\b(?:the\s+)?(?:{'|'.join(labs)})\s+(?:shall|may|will|must)\b", re.I)


RX_RIGHT = re.compile(r"할\s*수\s*있(?:다|으며|고)|청구할\s*수|이의\s*(?:를\s*)?제기|\bmay\b(?!\s+not)|is\s+entitled|shall\s+have\s+the\s+right", re.I)


def _first_subject(clause: str, o_rx: re.Pattern[str], t_rx: re.Pattern[str] | None) -> str:
    """절의 첫 주어가 누구인가 — 'ours' / 'theirs' / ''."""
    mo = o_rx.search(clause)
    mt = t_rx.search(clause) if t_rx is not None else None
    if mo and (not mt or mo.start() < mt.start()):
        return "ours"
    if mt:
        return "theirs"
    return ""


def _right_holder(family_rx: re.Pattern[str], contract_text: str, ours: re.Pattern[str] | None,
                  theirs: re.Pattern[str] | None) -> str:
    """계약 원문에서 그 권리 계열을 행사하는 쪽 — 'ours' / 'theirs' / ''(둘 다·불명)."""
    o = t = 0
    for s in sentences(contract_text):
        if not family_rx.search(s):
            continue
        for clause in re.split(r"(?<=[며고])\s*,\s*|,\s+(?=[가-힣\"“])", s):
            if not family_rx.search(clause):
                continue
            if ours is not None and ours.search(clause):
                o += 1
            if theirs is not None and theirs.search(clause):
                t += 1
    if o and not t:
        return "ours"
    if t and not o:
        return "theirs"
    if o >= 2 * max(1, t):
        return "ours"
    return ""


def check_added_text(added: str, *, contract_text: str, ours: list[str], theirs: list[str]) -> list[dict[str, str]]:
    """추가되는 문장 중 우리 권리를 줄이거나 우리 의무를 늘리는 것."""
    o_rx, t_rx = _subject_rx(ours), _subject_rx(theirs)
    if o_rx is None:
        return []
    original = _ws(contract_text)
    out: list[dict[str, str]] = []
    for sent in sentences(added):
        if RX_MUTUAL.search(sent):
            continue
        bare = re.sub(r"\([^()]*\)|（[^（）]*）", "", sent)   # "사전 서면합의(사유·금액 포함)가 있는 경우" — 괄호가 표현을 끊는다
        # 1. 권리 축소
        if RX_RESTRICT.search(bare):
            for name, frx in RIGHT_FAMILIES:
                if not frx.search(bare):
                    continue
                if o_rx.search(sent) and not (t_rx is not None and t_rx.search(sent)):
                    holder = "ours"
                elif t_rx is not None and t_rx.search(sent) and not o_rx.search(sent):
                    holder = "theirs"
                else:
                    holder = _right_holder(frx, contract_text, o_rx, t_rx)
                if holder == "ours":
                    out.append({"kind": "우리 권리 축소", "family": name, "sentence": sent})
                    break
            else:
                pass
            if out and out[-1]["sentence"] == sent:
                continue
        # 2. 의무 확대 — 같은 문장에서 우리에게 새 의무를 지우고 **그 대가로 상대방에게 권리**를 주는 구조
        #    ("갑은 정산서를 제공하고, 을은 이의제기할 수 있다"). 우리 의무만 있는 절차·법정 의무 문장(통지 절차,
        #    개인정보 안전조치 등)은 수정 취지상 필요할 수 있어 여기서 막지 않는다.
        clauses = [c for c in re.split(r"(?<=[며고])\s*,\s*|;\s*|,\s+and\s+", sent) if c.strip()]
        ours_obl = any(_first_subject(c, o_rx, t_rx) == "ours" and RX_OBLIGATION.search(c) and _ws(c) not in original
                       for c in clauses)
        theirs_right = any(_first_subject(c, o_rx, t_rx) == "theirs" and RX_RIGHT.search(c) for c in clauses)
        if ours_obl and theirs_right:
            out.append({"kind": "우리 의무 확대", "family": "", "sentence": sent})
    return out


def _added_part(original: str, new: str) -> str:
    """수정안에서 원문에 없던 문장만."""
    orig_n = {_ws(s) for s in sentences(original)}
    return "\n".join(s for s in sentences(new) if _ws(s) not in orig_n)


def apply_direction_gate(clause_results: list[dict[str, Any]], *, contract_text: str, ours: list[str],
                         theirs: list[str]) -> list[dict[str, Any]]:
    """수정안(suggested_rewrite·addition_text·redline replacement)에서 방향이 틀린 문장을 뺀다. 뺀 기록을 돌려준다."""
    ours = expand_labels([x for x in ours if x], contract_text)
    theirs = [x for x in expand_labels([x for x in theirs if x], contract_text) if x not in ours]
    if not ours:
        return []
    report: list[dict[str, Any]] = []
    for cr in clause_results or []:
        if not isinstance(cr, dict):
            continue
        orig = _s(cr.get("original_text"))
        blocked: list[dict[str, str]] = []
        for field in ("suggested_rewrite", "addition_text"):
            val = _s(cr.get(field))
            if not val.strip():
                continue
            bad = check_added_text(_added_part(orig, val), contract_text=contract_text, ours=ours, theirs=theirs)
            if not bad:
                continue
            blocked.extend(bad)
            bad_s = {_ws(b["sentence"]) for b in bad}
            kept = [s for s in sentences(val) if _ws(s) not in bad_s]
            added_left = [s for s in kept if _ws(s) not in {_ws(x) for x in sentences(orig)}]
            if not added_left or not [s for s in added_left if not re.fullmatch(r"\[추가\]", s)]:
                cr[field] = None
            else:
                cr[field] = "\n".join(kept)
        ri = cr.get("redline_instruction")
        if isinstance(ri, dict) and _s(ri.get("replacement_text")).strip():
            bad = check_added_text(_added_part(_s(ri.get("target_text")) or orig, _s(ri.get("replacement_text"))),
                                   contract_text=contract_text, ours=ours, theirs=theirs)
            if bad:
                blocked.extend(bad)
                ri["held"] = True
                ri["hold_reason"] = "수정 문구가 우리 측 권리를 줄이거나 의무를 늘림 — 방향 게이트 차단"
        if blocked:
            if not _s(cr.get("suggested_rewrite")).strip() and not _s(cr.get("addition_text")).strip():
                cr["has_rewrite_change"] = False
                cr["has_addition"] = False
            cr["direction_blocked"] = blocked
            report.append({"clause_id": _s(cr.get("clause_id")), "blocked": blocked})
    return report
