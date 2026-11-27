"""필수 검증 단계 — 우리 회사 관점 · 수정 문구 정확성 · 계약 전체 완결성 (2026-11-03).

프롬프트 주의사항이 아니라 코드가 판정하고, 실패하면 수정안을 다시 쓰거나(AI) 빼고(코드), 그래도 남으면 최종 출력을 제한한다.
모든 계약 유형에 같은 규칙을 쓴다 — 조항 번호·계약 이름에 기대지 않고 문장의 법률 구조(주체·상대·원인·예외·한도·기간)로 본다.

1. 검토 기준(review basis): 우리 당사자명·거래상 역할·거래 목적·지급/수취금·확보할 권리. 원문·요청에서 확인하지 못한 값은
   추측하지 않고 "확인 필요". 조항마다 권리자·의무자·배상하는 자·배상받는 자.
2. 우리 회사에 미치는 효과: 수정 전후를 비교해 우리 권리·의무·책임·지급, 상대방 책임·면책·한도, 삭제된 유리 조건을 판정한다.
   불리한 효과는 근거(명시적 사용자 지시·확인된 합의·표시된 협상 교환조건)가 있어야 한다. '상호 공평'·'상대방 부담' 만으로는 근거가 아니다.
3. 문구 의미: 수정 문구를 누가/누구에게/어떤 조건에서/무엇을/언제까지/어떤 예외·한도로 다시 읽어 한글 설명과 대조한다(부정문·unless·
   except·only·to the extent·notwithstanding·고의·중과실).
4. 계약 전체 완결성: deal_scenarios(책임 충돌·한도 구조·연장·종료 후 활동·로열티) + 상호참조·정의어 삭제·미확정 값 표시.
5. 상황별 검증: 우리 귀책·상대방 귀책·공동 귀책·귀책 없는 사고·보험금 거절/지연·정상 만료·중도해지·종료 후 주문/판매/A/S —
   기대 결과(검토 목적·합의에서 먼저 정함)와 최종 문구의 실제 결과를 비교한다.
6. 출력 통제: 마지막 수정까지 넣은 같은 버전(fingerprint)을 검증한다. 수정이 바뀌면 이전 결과를 버리고 다시 검증한다.
   책임 방향 역전·근거 없는 우리 보호 축소·설명과 문구 불일치·중대한 조항 충돌/권리 공백이 하나라도 남으면 '검증 미통과 초안'.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from runtime.review.deal_scenarios import (
    LIABLE,
    NOT_LIABLE,
    OUT_OF_SCOPE,
    SCENARIO_LABEL,
    SCENARIOS,
    SILENT,
    Parties,
    clause_outcome,
    description_intents,
    evaluate,
    parse_liability,
    sentences,
    wind_down_structure,
)

logger = logging.getLogger(__name__)

STATUS_PASS = "검증 통과"
STATUS_FAIL = "검증 미통과 초안"
STATUS_NONE = "검증 대상 수정 없음"

CAT_DIRECTION = "책임 방향 역전"
CAT_PROTECTION = "근거 없는 우리 보호 축소"
CAT_MISMATCH = "설명과 수정 문구의 불일치"
CAT_GAP = "중대한 조항 충돌·권리 공백"
CAT_BASIS = "검토 기준 미확정"
CRITICAL_CATEGORIES = (CAT_DIRECTION, CAT_PROTECTION, CAT_MISMATCH, CAT_GAP, CAT_BASIS)

#: 문제 코드 → 출력 차단 범주. 여기 없는 코드는 차단하지 않는다(확인·보완 권고로 표시).
CODE_CATEGORY: dict[str, str] = {
    # 책임 방향
    "NEW_LIABILITY": CAT_DIRECTION, "OUR_LIABILITY_UP": CAT_DIRECTION, "THEIR_LIABILITY_DOWN": CAT_DIRECTION,
    "SIT_THEIR_FAULT_OURS": CAT_DIRECTION,
    # 우리 보호 축소(근거 없을 때만 문제로 만든다)
    "THEIR_CAP_NEW": CAT_PROTECTION, "OUR_CAP_REMOVED": CAT_PROTECTION, "OUR_RIGHT_REMOVED": CAT_PROTECTION,
    "THEIR_RIGHT_NEW": CAT_PROTECTION, "OUR_PAYMENT_UP": CAT_PROTECTION, "THEIR_PAYMENT_DOWN": CAT_PROTECTION,
    "NEW_ROYALTY_BASE": CAT_PROTECTION, "SIT_JOINT_ALL_OURS": CAT_PROTECTION, "SIT_NOFAULT_OURS": CAT_PROTECTION,
    # 설명 ↔ 문구
    "DIRECTION_MISMATCH": CAT_MISMATCH, "THEIR_DIRECTION_MISMATCH": CAT_MISMATCH, "DESC_EFFECT_MISMATCH": CAT_MISMATCH,
    # 충돌·공백
    "LIABILITY_CONFLICT": CAT_GAP, "XREF_BROKEN": CAT_GAP, "DEFINITION_REMOVED": CAT_GAP, "WD_SERVICE_MISSING": CAT_GAP,
    "WD_SERVICE_SCOPE": CAT_GAP, "ROYALTY_NONSALE": CAT_GAP, "RENEWAL_CONSENT": CAT_GAP, "RENEWAL_BLOCKABLE": CAT_GAP,
    "SIT_INSURANCE_THEIRS": CAT_GAP, "SIT_INSURANCE_OUR_CAP": CAT_GAP,
    # 검토 기준 — 우리 당사자를 확정하지 못하면 방향 검증 자체를 신뢰할 수 없다
    "BASIS_PARTY_UNCONFIRMED": CAT_BASIS,
}

#: 충돌·공백 범주 중 수정안 자체가 새 부담을 만든 것 — 제거로 해결한다.
_REMOVABLE_GAP_CODES = {"ROYALTY_NONSALE", "XREF_BROKEN", "DEFINITION_REMOVED"}

#: 사업팀 전달본에 들어가면 안 되는 내부 표지(코드명·디버깅 문구).
RX_INTERNAL = re.compile(r"\b[A-Z]{2,}(?:_[A-Z]{2,})+\b|edits\[\d+\]|clause_id|fingerprint|Traceback|_repaired|\[계약 전체 검증\]|\bfnd_[0-9a-f]{6,}")


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", _s(s)).strip()


def _strip_markers(text: str) -> str:
    try:
        from runtime.review.docx_redline import _strip_display_markers

        return _strip_display_markers(text)
    except Exception:  # noqa: BLE001
        return re.sub(r"\[(?:추가 권고|신설 제안|수정 제안)\]", " ", _s(text))


# ── 수정 전/후 지도(최종 clause_results 그대로) ─────────────────────────────────

def _new_path(num: str, location: str) -> str:
    if num:
        return f"Article {num}" if re.match(r"^\d", num) else num
    m = re.search(r"(?:Article|Section|Clause)\s+\d+(?:\.\d+)*|제\s*\d+\s*조(?:의\s*\d+)?(?:\s*제\s*\d+\s*항)?", location or "")
    return m.group(0) if m else (location or "신설 조항")


def live_edits(clause_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """출력(화면·변경추적본·클린본·검토의견서)에 실리는 수정안 — 보류·KEEP·중복 숨김 제외."""
    out = []
    for cr in clause_results or []:
        # docx_redline.build_redline_docx 의 적용 대상과 같은 기준 — 검증한 수정안 = 변경추적본·클린본에 들어가는 수정안
        if not isinstance(cr, dict) or cr.get("dedup_suppressed") or cr.get("keep_as_is") or not cr.get("has_rewrite_change"):
            continue
        if not _s(cr.get("original_text")).strip() or _s(cr.get("risk_tier")).upper() not in ("HIGH", "MEDIUM"):
            continue
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        if ri.get("held"):
            continue
        if not (_s(ri.get("replacement_text")).strip() or _s(cr.get("suggested_rewrite")).strip() or ri.get("edit_mode") == "delete"):
            continue
        out.append(cr)
    return out


def _original_map(clauses: list[Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in clauses or []:
        p = _s(c.get("display_path") if isinstance(c, dict) else getattr(c, "display_path", ""))
        t = _ws(c.get("text") if isinstance(c, dict) else getattr(c, "text", ""))
        if p and t:
            out[p] = (out[p] + " " + t) if p in out and t not in out[p] else t
    return out


def build_maps(clauses: list[Any] | None, clause_results: list[dict[str, Any]] | None
               ) -> tuple[dict[str, str], dict[str, str], dict[str, list[dict[str, Any]]]]:
    """(수정 전, 수정 후, {조항: [그 조항을 바꾼 finding]}) — 변경추적본·클린본에 들어가는 것과 같은 수정안만."""
    orig = _original_map(clauses)
    rev = dict(orig)
    raw: dict[str, str] = {}
    for c in clauses or []:
        p = _s(c.get("display_path") if isinstance(c, dict) else getattr(c, "display_path", ""))
        t = _s(c.get("text") if isinstance(c, dict) else getattr(c, "text", ""))
        if p and t:
            raw[p] = (raw[p] + "\n" + t) if p in raw else t
    owners: dict[str, list[dict[str, Any]]] = {}
    for cr in live_edits(clause_results):
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        path = _s(cr.get("display_path"))
        repl = _ws(_strip_markers(_s(ri.get("replacement_text"))))
        if ri.get("edit_mode") == "new_paragraph" or (ri.get("edit_type") in ("insert_after", "new_clause") and not ri.get("target_text")):
            np = _new_path(_s(ri.get("new_paragraph_number")), _s(ri.get("edit_location")))
            if np in orig and np == path:
                rev[np] = _ws(rev[np] + " " + (repl or _ws(_strip_markers(_s(cr.get("suggested_rewrite"))))))
            else:
                rev[np] = repl or _ws(_strip_markers(_s(cr.get("suggested_rewrite"))))
            owners.setdefault(np, []).append(cr)
            continue
        tgt = _ws(_strip_markers(_s(ri.get("target_text"))))
        if tgt and path in rev and tgt in rev[path]:
            if ri.get("edit_mode") == "delete" or ri.get("edit_type") == "delete":
                rev[path] = _ws(rev[path].replace(tgt, "", 1))
            elif repl:
                rev[path] = rev[path].replace(tgt, repl, 1)
            owners.setdefault(path, []).append(cr)
        elif _s(cr.get("suggested_rewrite")).strip() and path:
            # 대상 문장 없는 조항 교체 — 변경추적본(docx_redline)·검토의견서와 같은 기준으로 '가장 비슷한 항' 하나만 바꾼다
            new = _ws(_strip_markers(_s(cr.get("suggested_rewrite"))))
            src = _s(cr.get("original_text")) or raw.get(path, "")
            bp = None
            try:
                from runtime.review.business_brief import _best_paragraph

                bp = _best_paragraph(src, new)
            except Exception:  # noqa: BLE001
                bp = None
            cur = rev.get(path, "")
            if bp and _ws(bp[1]) and _ws(bp[1]) in cur:
                rev[path] = cur.replace(_ws(bp[1]), new, 1)
            elif _ws(cr.get("original_text")) and _ws(cr.get("original_text")) in cur:
                rev[path] = cur.replace(_ws(cr.get("original_text")), new, 1)
            else:
                rev[path] = new
            owners.setdefault(path, []).append(cr)
    # 판독용 정규화 — 국문 계약의 “임대인”이 처럼 닫는 따옴표가 조사를 가리면 주체·지급·권리 문장을 놓친다(2026-11-03)
    unq = lambda t: _ws(re.sub(r"[“”]", "", t))  # noqa: E731
    return {p: unq(t) for p, t in orig.items()}, {p: unq(t) for p, t in rev.items()}, owners


def fingerprint(clause_results: list[dict[str, Any]] | None) -> str:
    """검증한 버전의 지문 — 출력에 실리는 수정안(위치·문구·보류 여부)이 하나라도 바뀌면 달라진다."""
    rows = []
    for cr in clause_results or []:
        if not isinstance(cr, dict) or not cr.get("has_rewrite_change"):
            continue
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        rows.append([_s(cr.get("clause_id")), _s(cr.get("display_path")), bool(ri.get("held")), bool(cr.get("dedup_suppressed")),
                     bool(cr.get("keep_as_is")), _ws(ri.get("target_text")), _ws(ri.get("replacement_text")),
                     _ws(cr.get("suggested_rewrite"))])
    rows.sort()
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


# ── 1. 검토 기준 ───────────────────────────────────────────────────────────────

def _rx_side(parties: Parties, side: str) -> re.Pattern[str]:
    return parties.rx_ours if side == "ours" else parties.rx_theirs


def _gap(parties: Parties, side: str, n: int, stop: str = ".") -> str:
    return "[^" + stop + "]{0," + str(n) + "}"


#: 국문 연결어미에서 절을 나눈다 — "임차인은 … 조치를 취할 수 있으며, 이로 인한 비용은 임대인이 부담한다" 의 두 절은 주체가 다르다.
#: 조건절("을이 … 출고하지 아니하는 경우, 갑은 … 취소할 수 있다")도 나눈다 — 조건절의 주어는 주절 권리의 주체가 아니다(2026-11-09).
_RX_KO_CLAUSE = re.compile(r"(?<=[며고])\s*,\s*|(?<=으며)\s+|(?<=하며)\s+|(?<=하고)\s+|(?<=되며)\s+|(?<=경우)\s*,\s*|(?<=경우에는)\s*,?\s*")


def _hit(rx: re.Pattern[str], sentence: str) -> bool:
    """문장 또는 그 국문 절 하나에서 맞으면 참 — 절을 넘어 다른 주체의 동사와 잇지 않는다."""
    parts = [c for c in _RX_KO_CLAUSE.split(sentence or "") if c.strip()]
    return any(rx.search(c) for c in parts) if len(parts) > 1 else bool(rx.search(sentence or ""))


def _rx_pay(parties: Parties, side: str) -> re.Pattern[str]:
    p = _rx_side(parties, side).pattern
    g60, g80, g30 = _gap(parties, side, 60, ".;"), _gap(parties, side, 80), _gap(parties, side, 30)
    return re.compile(rf"{p}{g60}\b(?:shall|must|will|agrees?\s+to)\s+(?:\w+\s+){{0,2}}(?:pay|reimburse|refund|compensate|bear\s+the\s+costs?)"
                      rf"|{p}(?:은|는|이|가){g80}(?:지급|상환|환급)(?:하여야|한다|하기로|할\s*의무)"
                      # '부담' 은 비용·금액을 부담할 때만 지급이다 — "배상할 책임을 부담한다" 는 책임 문장(책임 분석이 본다)
                      rf"|{p}(?:은|는|이|가){g60}(?:비용|금액|대금|수수료|요금|위약금|사용료|로열티){_gap(parties, side, 20)}부담(?:하여야|한다|하기로)"
                      rf"|(?:비용|금액|대금|수수료|요금|위약금)(?:은|는|을|를)?{g30}{p}(?:이|가)\s*(?:이를\s*)?부담(?:하여야|한다|하기로)", re.I)


def _rx_right(parties: Parties, side: str) -> re.Pattern[str]:
    p = _rx_side(parties, side).pattern
    # '청구할 수 없다' 는 권리가 아니라 권리 제한이다
    return re.compile(rf"{p}{_gap(parties, side, 40, '.;')}\b(?:may(?!\s+not)|is\s+entitled|shall\s+be\s+entitled|shall\s+have\s+the\s+right|is\s+permitted|reserves\s+the\s+right)"
                      rf"|{p}(?:은|는|이|가){_gap(parties, side, 80)}(?:할\s*수\s*있(?:다|으며|고|음)|권리를\s*(?:가진다|갖는다)|청구할\s*수\s*있)", re.I)


def _rx_obl(parties: Parties, side: str) -> re.Pattern[str]:
    p = _rx_side(parties, side).pattern
    return re.compile(rf"{p}{_gap(parties, side, 30, '.;')}\b(?:shall|must)\b(?!\s+not\b)(?!\s+(?:be\s+)?(?:entitled|have\s+the\s+right))"
                      rf"|{p}(?:은|는|이|가){_gap(parties, side, 80)}(?:하여야\s*한다|할\s*의무가\s*있다)", re.I)


#: 주어 없는·수동형 지급 문장 — 금액 낱말 + 지급 동사.
_RX_PASSIVE_PAY = re.compile(
    r"(?:대금|금액|선급금|잔금|계약\s*금액|용역료|수수료)[^.。;]{0,160}?(?:지급한다|지급하여야\s*한다|지급하기로\s*한다|송금한다)"
    r"|\b(?:amount|price|fee|payment|balance|advance)\b[^.;]{0,160}?\bshall\s+be\s+(?:paid|remitted|transferred)\b",
    re.IGNORECASE,
)


def build_basis(*, parties: Parties, original: dict[str, str], our_name: str = "", our_role: str = "",
                counterparty_name: str = "", counterparty_role: str = "", purpose: str = "", payment_flow: str = "",
                request_text: str = "", answers_text: str = "") -> dict[str, Any]:
    """검토 시작 기준 — 원문·요청에서 확인한 것만. 모르는 것은 '확인 필요'."""
    need: list[str] = []
    pays: list[dict[str, str]] = []
    for p, t in original.items():
        for s in sentences(t):
            for side, other in (("ours", "theirs"), ("theirs", "ours")):
                if _hit(_rx_pay(parties, side), s):
                    pays.append({"path": p, "payer": "우리" if side == "ours" else "상대방",
                                 "payee": "상대방" if other == "theirs" else "우리", "text": s[:220]})
                    break
    rights: list[str] = []
    for ln in re.split(r"[\n\r]+|(?<=[.!?])\s+", f"{request_text}\n{answers_text}"):
        ln = _ws(ln)
        if 6 <= len(ln) <= 300 and re.search(r"확보|보장|유지|연장|허용|사용권|권리|받을\s*수|청구|한정|제한|면책|A/S|재고|로열티|royalt|right", ln, re.I):
            rights.append(ln)
    basis = {
        "our_party": our_name or (parties.ours[0] if parties.ours else ""),
        "our_defined_terms": list(dict.fromkeys(parties.ours)),
        "counterparty": counterparty_name or (parties.theirs[0] if parties.theirs else ""),
        "counterparty_defined_terms": list(dict.fromkeys(parties.theirs)),
        "our_role": our_role,
        "counterparty_role": counterparty_role,
        "purpose": _ws(purpose)[:300],
        "payment_flow": _ws(payment_flow)[:300],
        "payments": pays[:12],
        "rights_to_secure": list(dict.fromkeys(rights))[:10],
    }
    if not basis["our_party"]:
        need.append("우리 회사의 계약 당사자명")
    if not our_role:
        need.append("우리 회사의 거래상 역할")
    if not basis["purpose"]:
        need.append("거래 목적")
    if not pays and not basis["payment_flow"]:
        # 주어 없는·수동형 지급 문장("총 계약 금액은 … 지급한다", "shall be paid/remitted by T/T")은 당사자 호칭으로 시작하지
        # 않아 위 판독이 놓친다 — 계약 전체의 지급 구조 문장으로는 충분하다(2026-11-27, 국영 병기 매매계약 실측).
        for p, t in original.items():
            hit = next((s for s in sentences(t) if _RX_PASSIVE_PAY.search(s)), "")
            if hit:
                basis["payment_flow"] = _ws(hit)[:300]
                basis["payment_flow_path"] = p
                break
    if not pays and not basis["payment_flow"]:
        need.append("주요 지급·수취금(누가 누구에게 무엇을 지급하는지)")
    if not basis["rights_to_secure"]:
        need.append("우리가 확보해야 할 권리(요청·답변에 없음)")
    basis["needs_confirmation"] = need
    return basis


def clause_roles(texts: dict[str, str], parties: Parties, paths: list[str]) -> dict[str, list[dict[str, str]]]:
    """조항별 권리자·의무자·배상하는 자·배상받는 자."""
    side = {"ours": "우리", "theirs": "상대방", "": "확인 필요"}
    out: dict[str, list[dict[str, str]]] = {}
    for p in paths:
        t = texts.get(p, "")
        rows: list[dict[str, str]] = []
        rules, caps = parse_liability(p, t, parties)
        for r in rules:
            rows.append({"kind": "면제" if r.negative else "배상·면책", "배상하는 자": side[r.obligor],
                         "배상받는 자": side.get(r.beneficiary, "확인 필요"), "sentence": r.sentence[:200]})
        for c in caps:
            rows.append({"kind": "책임한도", "한도로 보호받는 자": side[c.obligor], "sentence": c.sentence[:200]})
        for s in sentences(t):
            for sd in ("ours", "theirs"):
                if _hit(_rx_pay(parties, sd), s):
                    rows.append({"kind": "지급", "의무자": side[sd], "권리자": side["theirs" if sd == "ours" else "ours"], "sentence": s[:200]})
                elif _hit(_rx_right(parties, sd), s):
                    rows.append({"kind": "권리", "권리자": side[sd], "sentence": s[:200]})
        out[p] = rows[:12]
    return out


# ── 3. 문구 의미 재해석 ─────────────────────────────────────────────────────────

_RX_COND = re.compile(r"\b(?:if|where|in\s+the\s+event\s+(?:that|of)|provided\s+that|upon|subject\s+to)\b[^,.;]{0,120}|[^.,]{0,60}(?:경우|때)(?:에는|에)?", re.I)
_RX_DEADLINE = re.compile(r"(?:within|no\s+later\s+than|at\s+least|prior\s+to|before|until)\s+[^,.;]{0,60}|[^\s]{0,20}\s*(?:이내|까지|전에)", re.I)
_RX_EXC = re.compile(r"\b(?:except|unless|save|only|solely|to\s+the\s+extent|notwithstanding|in\s+no\s+event|shall\s+not\s+exceed)\b[^.;]{0,140}"
                     r"|다만[^.]{0,120}|(?:고의|중과실|중대한\s*과실)[^.]{0,60}|한도[^.]{0,60}|제외[^.]{0,60}", re.I)
_RX_NEG_ANY = re.compile(r"\bnot\b|\bno\b|\bnever\b|\bneither\b|\bnor\b|않|아니|없|면제|배제", re.I)
_RX_FAULT = re.compile(r"gross(?:ly)?\s+neglig\w*|wil+ful\s+misconduct|intent\w*|neglig\w*|고의|중(?:대한\s*)?과실|과실|귀책", re.I)


def read_sentence(s: str, parties: Parties) -> dict[str, str]:
    """누가 / 누구에게 / 어떤 조건에서 / 무엇을 / 언제까지 / 어떤 예외·한도로 — 문구만 읽은 결과."""
    side = {"ours": "우리", "theirs": "상대방", "": ""}
    rules, caps = parse_liability("_", s, parties)
    who, whom = "", ""
    if rules:
        who, whom = side[rules[0].obligor], side.get(rules[0].beneficiary, "")
    elif caps:
        who = side[caps[0].obligor]
    else:
        m_o, m_t = parties.rx_ours.search(s), parties.rx_theirs.search(s)
        first = sorted([m for m in (m_o, m_t) if m], key=lambda m: m.start())
        if first:
            who = "우리" if first[0] is m_o else "상대방"
            if len(first) > 1:
                whom = "상대방" if who == "우리" else "우리"
    what = ""
    m = re.search(r"\b(?:shall|must|will|may|agrees?\s+to)\b\s+(?:not\s+)?[^,.;]{0,90}|(?:하여야|한다|할\s*수\s*있다|하지\s*(?:아니한다|않는다))", s, re.I)
    if m:
        what = _ws(m.group(0))
    exc = [_ws(x.group(0)) for x in _RX_EXC.finditer(s)][:3]
    return {
        "누가": who or "확인 필요", "누구에게": whom or "-", "조건": _ws((_RX_COND.search(s) or [""])[0])[:120] if _RX_COND.search(s) else "-",
        "무엇을": what[:120] or "-", "언제까지": _ws(_RX_DEADLINE.search(s).group(0))[:80] if _RX_DEADLINE.search(s) else "-",
        "예외·한도": " / ".join(exc)[:240] or "-", "부정": "있음" if rules and rules[0].negative else ("문장 내 부정 표현" if _RX_NEG_ANY.search(s) else "없음"),
        "귀책 범위": ", ".join(dict.fromkeys(x.group(0).lower() for x in _RX_FAULT.finditer(s)))[:80] or "-",
    }


#: 설명(한글)이 말하는 상대방 책임 방향 — "NDG 귀책 손해는 NDG 가 배상", "상대방이 면책한다".
def their_intents(desc: str, parties: Parties) -> dict[str, str]:
    t = _ws(desc)
    th = "(?:상대방|상대\\s*회사|" + "|".join(re.escape(x) for x in parties.theirs if x) + ")"
    out: dict[str, str] = {}
    pos = re.search(rf"{th}\s*(?:이|가|은|는|측이)?\s*[^.]{{0,40}}(?:배상(?:하|한|책임을\s*지)|면책(?:하|한)|방어(?:하|한)|책임(?:을)?\s*(?:지도록|진다|지게|부담))", t)
    neg = re.search(rf"{th}\s*(?:의|측)?\s*(?:책임|배상\s*책임)[^.]{{0,30}}(?:제한|면제|배제|삭제|지지\s*않|부담하지\s*않)|{th}\s*(?:은|는|이|가)?\s*[^.]{{0,30}}책임(?:을)?\s*(?:지지|부담하지)\s*않", t)
    if pos and not neg:
        out["their_negligence"] = LIABLE
        if re.search(r"디자인|지식재산|IP|특허|저작권", t[pos.start():pos.end() + 60]):
            out["their_design"] = LIABLE
    elif neg and not pos:
        out["their_negligence"] = NOT_LIABLE
    return out


_RX_DESC_PROTECT = re.compile(r"(?:우리|당사|회사)\s*(?:의|측)?\s*(?:보호|권리|이익)[^.]{0,20}(?:강화|확보|보장|명시|추가|유지)"
                              r"|(?:상대방|상대\s*회사)\s*(?:의|측)?\s*(?:책임|의무|배상)[^.]{0,20}(?:명시|강화|확대|추가|부담)"
                              r"|(?:우리|당사)\s*(?:의|측)?\s*(?:책임|부담|의무)[^.]{0,20}(?:제한|한정|축소|감경|면제|삭제|줄)"
                              r"|(?:우리|당사)\s*(?:의|측)?\s*책임\s*한도", re.I)
_RX_DESC_OUR_CAP = re.compile(r"(?:우리|당사|회사)\s*(?:의|측)?\s*(?:책임|배상)?\s*(?:한도|상한)|(?:우리|당사)\s*(?:의|측)?\s*책임[^.]{0,20}(?:한도|상한)", re.I)
_RX_DESC_CONCEDE = re.compile(r"양보|교환\s*조건|수용|감수|받아들|accept", re.I)


# ── 2. 우리 회사에 미치는 효과 ──────────────────────────────────────────────────

def _table(texts: dict[str, str], parties: Parties, side: str) -> tuple[dict[str, dict[str, str]], dict[str, list[Any]], dict[str, list[Any]]]:
    table: dict[str, dict[str, str]] = {}
    rules_by: dict[str, list[Any]] = {}
    caps_by: dict[str, list[Any]] = {}
    for p, t in texts.items():
        rules, caps = parse_liability(p, t, parties)
        rs = [r for r in rules if r.obligor == side]
        if rs:
            rules_by[p] = rs
            table[p] = {k: clause_outcome(rs, k, obligor=side) for k, _ in SCENARIOS}
        cs = [c for c in caps if c.obligor == side]
        if cs:
            caps_by[p] = cs
    return table, rules_by, caps_by


def _sent_diff(o: str, r: str) -> tuple[list[str], list[str]]:
    """(수정 전에만 있는 문장, 수정 후에만 있는 문장) — 3-gram 겹침으로 같은 문장을 가린다."""
    so, sr = sentences(o), sentences(r)

    def sim(a: str, b: str) -> float:
        wa = re.findall(r"\w+", a.lower())
        wb = re.findall(r"\w+", b.lower())
        if not wa or not wb:
            return 0.0
        ga = {" ".join(wa[i:i + 3]) for i in range(max(1, len(wa) - 2))}
        gb = {" ".join(wb[i:i + 3]) for i in range(max(1, len(wb) - 2))}
        return len(ga & gb) / max(1, len(ga))

    removed = [s for s in so if not any(sim(s, x) >= 0.8 and sim(x, s) >= 0.8 for x in sr)]
    added = [s for s in sr if not any(sim(s, x) >= 0.8 and sim(x, s) >= 0.8 for x in so)]
    return removed, added


def _grams(text: str, n: int = 4) -> set[str]:
    t = re.sub(r"[\s\W_]+", "", _s(text).lower())
    return {t[i:i + n] for i in range(max(1, len(t) - n + 1))} if t else set()


def _containment(a: str, b: str) -> float:
    """a 의 글자 4-gram 중 b 에 든 비율 — 국문 조사·띄어쓰기 변화에 강하다."""
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / len(ga) if ga else 0.0


_RX_AMOUNT = re.compile(r"(?:EUR|USD|KRW|€|\$|₩)\s*(\d[\d.,]*)|(\d[\d.,]*)\s*(?:EUR|USD|KRW|원|만\s*원|억\s*원|%|percent)", re.I)


def _amounts(text: str) -> set[float]:
    """금액·비율만(조항 번호 '13.4' 는 금액이 아니다)."""
    out = set()
    for m in _RX_AMOUNT.finditer(text or ""):
        v = (m.group(1) or m.group(2) or "").strip(".,")
        try:
            out.add(float(v.replace(".", "").replace(",", "")) if re.search(r"[.,]\d{3}\b", v) else float(v.replace(",", "")))
        except ValueError:
            continue
    return out


_RX_LIMITING = re.compile(r"한하여|한해|한정|경우에만|에\s*대해서만|제외|다만|아니한다|않는다|\bonly\b|\bexcept\b|\bunless\b|to\s+the\s+extent|shall\s+not|in\s+no\s+event", re.I)


def _kept(sentence: str, revised_clause: str) -> bool:
    return _containment(sentence, revised_clause) >= 0.75


def effect_rows(original: dict[str, str], revised: dict[str, str], parties: Parties) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """조항별 효과 표와 불리한 효과(문제 후보). 효과는 근거 확인 전 — 근거가 있으면 나중에 걸러진다."""
    changed = sorted(p for p in set(original) | set(revised) if _ws(original.get(p, "")) != _ws(revised.get(p, "")))
    if not changed:
        return [], []
    o_sub = {p: original.get(p, "") for p in changed}
    r_sub = {p: revised.get(p, "") for p in changed}
    ob_t, _ob_r, ob_c = _table(o_sub, parties, "ours")
    oa_t, _oa_r, oa_c = _table(r_sub, parties, "ours")
    tb_t, _tb_r, tb_c = _table(o_sub, parties, "theirs")
    ta_t, _ta_r, ta_c = _table(r_sub, parties, "theirs")
    rows: list[dict[str, Any]] = []
    cands: list[dict[str, Any]] = []

    def cand(code: str, p: str, msg: str, scenario: str = "", sentence: str = "") -> None:
        cands.append({"code": code, "paths": [p], "scenario": scenario, "message": msg, "sentence": sentence[:240]})

    for p in changed:
        o, r = original.get(p, ""), revised.get(p, "")
        removed, added = _sent_diff(o, r)
        eff: list[str] = []
        moves: dict[str, list[str]] = {"our_up": [], "our_down": [], "their_down": [], "their_up": []}
        for k, _label in SCENARIOS:
            b, a = (ob_t.get(p) or {}).get(k, SILENT), (oa_t.get(p) or {}).get(k, SILENT)
            if a == LIABLE and b != LIABLE:
                moves["our_up"].append(k)
            elif b == LIABLE and a != LIABLE:
                moves["our_down"].append(k)
            tb_, ta_ = (tb_t.get(p) or {}).get(k, SILENT), (ta_t.get(p) or {}).get(k, SILENT)
            if tb_ == LIABLE and ta_ != LIABLE:
                moves["their_down"].append(k)
            elif ta_ == LIABLE and tb_ != LIABLE:
                moves["their_up"].append(k)
        labels = lambda ks: ", ".join(SCENARIO_LABEL[k] for k in ks)  # noqa: E731
        for key, text in (("our_up", "우리 책임 증가"), ("our_down", "우리 책임 감소"), ("their_down", "상대방 책임 감소"),
                          ("their_up", "상대방 책임 증가")):
            if moves[key]:
                eff.append(f"{text}({labels(moves[key])})")
        if moves["our_up"]:
            cands.append({"code": "OUR_LIABILITY_UP", "paths": [p], "scenario": moves["our_up"][0], "scenarios": moves["our_up"],
                          "message": f"{p}: 수정으로 우리 책임이 새로 생김 — {labels(moves['our_up'])}", "sentence": ""})
        if moves["their_down"]:
            cands.append({"code": "THEIR_LIABILITY_DOWN", "paths": [p], "scenario": moves["their_down"][0], "scenarios": moves["their_down"],
                          "message": f"{p}: 수정으로 상대방 책임이 없어지거나 좁아짐 — {labels(moves['their_down'])}", "sentence": ""})
        if len(ta_c.get(p, [])) > len(tb_c.get(p, [])):
            eff.append("상대방 책임한도 신설")
            cand("THEIR_CAP_NEW", p, f"{p}: 수정으로 상대방의 책임한도가 새로 생김 — '{ta_c[p][-1].sentence[:160]}'",
                 sentence=ta_c[p][-1].sentence)
        if len(ob_c.get(p, [])) > len(oa_c.get(p, [])):
            eff.append("우리 책임한도 삭제")
            cand("OUR_CAP_REMOVED", p, f"{p}: 수정으로 우리 책임한도가 사라짐 — '{ob_c[p][0].sentence[:160]}'", sentence=ob_c[p][0].sentence)
        elif len(oa_c.get(p, [])) > len(ob_c.get(p, [])):
            eff.append("우리 책임한도 신설")
        rx_r_o, rx_r_t = _rx_right(parties, "ours"), _rx_right(parties, "theirs")
        rx_p_o, rx_p_t = _rx_pay(parties, "ours"), _rx_pay(parties, "theirs")
        rx_o_o = _rx_obl(parties, "ours")
        # 표현만 바뀐 문장('다만,' 삭제·조사 변화)은 삭제가 아니다 — 수정 후 조항에 같은 내용이 남아 있으면 지운 것으로 보지 않는다
        removed = [s for s in removed if not _kept(s, r)
                   # 한정·예외 문장을 한정 표현을 유지한 채 다시 쓴 경우(“…경우에 한하여 책임을 부담한다”)도 유지로 본다
                   and not (_RX_LIMITING.search(s) and any(_containment(s, x) >= 0.35 and _RX_LIMITING.search(x) for x in added))]
        for s in removed:
            if _hit(rx_r_o, s) and not any(_hit(rx_r_o, x) for x in added):
                eff.append("우리 권리 삭제")
                cand("OUR_RIGHT_REMOVED", p, f"{p}: 우리에게 유리한 기존 권리 문장이 수정으로 사라짐 — '{s[:160]}'", sentence=s)
            elif re.search(r"shall\s+not\s+be\s+liable|책임(?:을)?\s*(?:지지|부담하지)\s*(?:아니|않)|except|unless|다만", s, re.I) \
                    and parties.who(s) == "ours" and not any(re.search(r"shall\s+not\s+be\s+liable|책임(?:을)?\s*(?:지지|부담하지)", x, re.I) for x in added):
                eff.append("우리 면책·예외 삭제")
                cand("OUR_RIGHT_REMOVED", p, f"{p}: 우리 면책·예외 문장이 수정으로 사라짐 — '{s[:160]}'", sentence=s)
            if _hit(rx_p_t, s) and not any(_hit(rx_p_t, x) for x in added):
                eff.append("상대방 지급 의무 삭제")
                cand("THEIR_PAYMENT_DOWN", p, f"{p}: 상대방이 우리에게 지급하던 의무가 수정으로 사라짐 — '{s[:160]}'", sentence=s)
        o_pays = [x for x in sentences(o) if _hit(rx_p_o, x)]
        for s in added:
            if _hit(rx_p_o, s):
                prior = max(o_pays, key=lambda x: _containment(s, x), default="")
                if prior and _containment(s, prior) >= 0.35:
                    # 기존 지급 문장의 수정 — 상한이 빠지거나 금액이 커질 때만 불리하다
                    lost_cap = bool(re.search(r"not\s+exceed|in\s+no\s+event|maximum|up\s+to|한도|상한|초과하지", prior, re.I)) and \
                        not re.search(r"not\s+exceed|in\s+no\s+event|maximum|up\s+to|한도|상한|초과하지", s, re.I)
                    nums_o, nums_n = _amounts(prior), _amounts(s)
                    bigger = bool(nums_o and nums_n and max(nums_n) > max(nums_o))
                    if lost_cap or bigger:
                        eff.append("우리 지급 부담 확대")
                        cand("OUR_PAYMENT_UP", p, f"{p}: 수정으로 우리 지급 " + ("상한이 빠짐" if lost_cap else "금액이 커짐")
                             + f" — '{s[:160]}'", sentence=s)
                    else:
                        eff.append("우리 지급 조건 변경(상한·금액 유지)")
                    continue
                eff.append("우리 지급·비용 부담 추가")
                cand("OUR_PAYMENT_UP", p, f"{p}: 수정으로 우리 지급·비용 부담 문장이 새로 생김 — '{s[:160]}'", sentence=s)
            if _hit(rx_r_t, s) and re.search(r"terminat|suspend|withhold|set\s*off|offset|해지|중지|상계|보류|거절", s, re.I):
                eff.append("상대방 해지·정지·상계 권리 신설")
                cand("THEIR_RIGHT_NEW", p, f"{p}: 수정으로 상대방에게 해지·정지·상계 등 권리가 새로 생김 — '{s[:160]}'", sentence=s)
            if _hit(rx_r_o, s):
                eff.append("우리 권리 추가")
            if _hit(rx_o_o, s) and not _hit(rx_p_o, s):
                eff.append("우리 의무 추가")
        rows.append({"path": p, "effects": list(dict.fromkeys(eff)) or ["효과 변화 없음(표현 정리)"],
                     "removed_sentences": [x[:200] for x in removed][:4], "added_sentences": [x[:200] for x in added][:4]})
    return rows, cands


# ── 근거: 사용자 지시 · 확인된 합의 · 협상 교환조건 ─────────────────────────────

_GROUND_KW: dict[str, str] = {
    "OUR_LIABILITY_UP": r"책임|배상|면책|indemn|liab",
    "NEW_LIABILITY": r"책임|배상|면책|indemn|liab",
    "THEIR_LIABILITY_DOWN": r"면책|책임\s*(?:제한|면제|감경|배제|삭제)|면제|exclu|limit",
    "THEIR_CAP_NEW": r"한도|상한|\bcap\b|limit",
    "OUR_CAP_REMOVED": r"한도|상한|\bcap\b|limit|삭제",
    "OUR_RIGHT_REMOVED": r"삭제|제외|포기|delete|remove|waive",
    "THEIR_RIGHT_NEW": r"해지|정지|상계|권리|허용|부여|terminat|right",
    "OUR_PAYMENT_UP": r"지급|비용|부담|pay|cost|fee",
    "THEIR_PAYMENT_DOWN": r"지급|감액|면제|삭제|pay",
    "NEW_ROYALTY_BASE": r"로열티|사용료|royalt",
    "SIT_JOINT_ALL_OURS": r"공동|전부\s*부담|책임|indemn",
    "SIT_NOFAULT_OURS": r"귀책\s*(?:없|불문)|무과실|책임|indemn",
}
_RX_FAIRNESS_ONLY = re.compile(r"상호|공평|형평|균형|대칭|mutual|reciprocal|부담이\s*크|상대방(?:의)?\s*부담", re.I)
_RX_DIRECTIVE = re.compile(r"삭제|추가|신설|한도|상한|제한|면제|양보|수용|받아들|동의|합의|감수|accept|agree|delete|add|limit|cap|해\s*주|하도록|으로\s*한정|로\s*한정", re.I)


def _path_tokens(path: str) -> list[str]:
    m = re.search(r"(\d{1,3}(?:\.\d{1,3})+)", path or "")
    if m:
        return [m.group(1)]
    m = re.search(r"제\s*(\d{1,3})\s*조(?:의\s*(\d+))?", path or "")
    if m:
        n = m.group(1) + (f"의{m.group(2)}" if m.group(2) else "")
        return [f"제{n}조", f"{n}조"]
    m = re.search(r"(?:Article|Section|Clause)\s+(\d{1,3})", path or "", re.I)
    return [m.group(1)] if m else []


def _lines(text: str) -> list[str]:
    return [_ws(x) for x in re.split(r"[\n\r]+|(?<=[.!?。])\s+", _s(text)) if _ws(x)]


def find_ground(problem: dict[str, Any], owners: list[dict[str, Any]], *, request_text: str, answers_text: str,
                agreements: list[dict[str, Any]], revised_text: str, parties: Parties) -> dict[str, str] | None:
    """불리한 효과의 근거. 없으면 None — '상호 공평'·'상대방 부담' 만 있는 문장은 근거가 아니다."""
    code = problem["code"]
    for cr in owners:
        c = cr.get("concession") if isinstance(cr.get("concession"), dict) else None
        if c and _s(c.get("disadvantage")).strip() and _s(c.get("exchange")).strip():
            return {"kind": "협상 교환조건", "text": f"양보: {c['disadvantage']} / 교환: {c['exchange']}"}
    kw = _GROUND_KW.get(code)
    if not kw:
        return None
    toks = [t for p in problem.get("paths") or [] for t in _path_tokens(p)]
    for src, txt in (("사용자 지시", request_text), ("사용자 답변", answers_text)):
        for ln in _lines(txt):
            if toks and not any(re.search(rf"(?<![\d.]){re.escape(t)}(?![\d])", ln) for t in toks):
                continue
            if not toks:
                continue
            if not re.search(kw, ln, re.I):
                continue
            if _RX_FAIRNESS_ONLY.search(ln) and not _RX_DIRECTIVE.search(_RX_FAIRNESS_ONLY.sub(" ", ln)):
                continue
            ks = list(problem.get("scenarios") or ([problem["scenario"]] if problem.get("scenario") else []))
            if ks:
                want = description_intents(ln, parties)
                # 요청이 이 상황에서 반대 결과를 원하면(우리 책임 없음을 원했는데 생김) 근거가 아니다
                if code in ("OUR_LIABILITY_UP", "NEW_LIABILITY") and any(want.get(k) == NOT_LIABLE for k in ks):
                    continue
                if code == "THEIR_LIABILITY_DOWN" and any(their_intents(ln, parties).get(k) == LIABLE for k in ks):
                    continue
            return {"kind": src, "text": ln[:300]}
    for a in agreements or []:
        if a.get("in_revision") == "반영" and a.get("source") not in ("요청·답변",):
            content = _s(a.get("content"))
            if content and re.search(kw, content, re.I) and any(t in content for t in toks):
                return {"kind": "확인된 합의", "text": content[:300]}
    return None


# ── 4. 완결성 보강(상호참조·정의어·미확정 값·종료 후 A/S) ─────────────────────────

_RX_REF = re.compile(r"(?:Article|Section|Clause|clause|article|section)\s+(\d{1,3}(?:\.\d{1,3})*)|제\s*(\d{1,3})\s*조(?:\s*제\s*(\d{1,2})\s*항)?")
_RX_DEFINE = re.compile(r"\((?:the\s+|hereinafter\s+(?:referred\s+to\s+as\s+)?)?[\"“]([A-Z][\w\s-]{1,40})[\"”]\)|[\"“]([A-Z][\w\s-]{1,40})[\"”]\s+(?:shall\s+)?means?\b"
                        r"|이하\s*[\"“']([^\"”']{1,20})[\"”']")
_RX_VALUE = re.compile(r"(?:(?:EUR|USD|KRW|€|\$|₩)\s*\d[\d.,]*|\d[\d.,]*\s*(?:%|percent|EUR|USD|원|만\s*원|억\s*원))"
                       r"|(?:\w+\s*\(\d+\)|\d+)\s*(?:calendar\s+|business\s+|working\s+)?(?:days?|weeks?|months?|years?)\b|\d+\s*(?:일|개월|년)(?![가-힣]*\s*조)", re.I)


def _path_index(texts: dict[str, str]) -> set[str]:
    out: set[str] = set()
    for p in texts:
        for t in _path_tokens(p):
            out.add(t.replace("제", "").replace("조", ""))
        m = re.search(r"(\d{1,3}(?:\.\d{1,3})*)", p)
        if m:
            out.add(m.group(1))
            out.add(m.group(1).split(".")[0])
    return out


_RX_WARRANTY_FROM_DELIVERY = re.compile(
    r"warrant[^.]{0,250}?\bfrom\s+the\s+(?:date\s+of\s+)?(?:shipment|delivery|bill\s+of\s+lading|acceptance)"
    r"|warrant[^.]{0,250}?\bfrom\s+the\s+(?:shipment|delivery)\s+date"
    r"|(?:인도|납품|출고|선적|검수\s*완료)\s*일\s*(?:로)?\s*부터[^.。]{0,80}?(?:보증|하자)", re.I | re.S)
_RX_UNDER_THIS = re.compile(r"under\s+this\s+Agreement|in\s+accordance\s+with\s+this\s+Agreement|(?:본|이)\s*계약에\s*(?:따라|의하여)", re.I)
_RX_WARRANTY_DUTY = re.compile(r"warrant|after[- ]sales|spare\s+parts|\bA/S\b|하자\s*보수|보증\s*(?:기간|책임|수리)|무상\s*수리", re.I)


def completeness_problems(original: dict[str, str], revised: dict[str, str], *, request_text: str, answers_text: str
                          ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(문제, 미확정 값 표시) — 수정으로 생긴 상호참조 끊김·정의어 삭제·종료 후 A/S 공백, 근거 없는 확정 값."""
    probs: list[dict[str, Any]] = []
    deleted = {p for p in original if not _ws(revised.get(p, ""))}
    if deleted:
        live_nums = _path_index({p: t for p, t in revised.items() if _ws(t)})
        for p, t in revised.items():
            for m in _RX_REF.finditer(t):
                n = m.group(1) or m.group(2)
                if not n:
                    continue
                if any(n == (re.search(r"(\d{1,3}(?:\.\d{1,3})*)", d) or [None, ""])[1] or n == (_path_tokens(d) or [""])[0].replace("제", "").replace("조", "")
                       for d in deleted) and n not in live_nums:
                    probs.append({"code": "XREF_BROKEN", "severity": "block", "paths": [p],
                                  "message": f"{p} 가 수정으로 삭제된 조항({n})을 가리킴 — 참조를 고치거나 삭제한 보호를 옮길 것"})
    # 정의어 — 수정으로 정의 문장이 사라졌는데 계약에서 계속 쓰이는 용어
    o_all, r_all = " ".join(original.values()), " ".join(revised.values())
    for m in _RX_DEFINE.finditer(o_all):
        term = _ws(next(g for g in m.groups() if g))
        if not term or len(term) < 2:
            continue
        defined_after = re.search(rf"[\"“']{re.escape(term)}[\"”']", r_all)
        used_after = len(re.findall(rf"(?<!\w){re.escape(term)}(?!\w)", r_all))
        if not defined_after and used_after:
            where = next((p for p, t in original.items() if re.search(rf"[\"“']{re.escape(term)}[\"”']", t)), "")
            probs.append({"code": "DEFINITION_REMOVED", "severity": "block", "paths": [where] if where else [],
                          "message": f"정의어 '{term}' 의 정의가 수정으로 사라졌는데 계약에서 계속 쓰임 — 정의를 살리거나 용어를 바꿀 것"})
    # 미확정 값 — 수정으로 새로 들어간 숫자가 원문·요청·답변 어디에도 없으면 '제안값(미합의)'
    # 근거 숫자 — 원문·요청·답변에 실제 값으로 나온 숫자(요청 번호 "6." 같은 줄머리 번호는 값이 아니다)
    _src_txt = "\n".join([o_all, re.sub(r"(?m)^\s*\d{1,2}\s*[.)]\s+", " ", f"{request_text}\n{answers_text}")])
    src_nums = {d.strip(".,") for d in re.findall(r"\d[\d.,]*", _src_txt)}
    undecided: list[dict[str, Any]] = []
    for p in sorted(set(revised) | set(original)):
        r, o = revised.get(p, ""), original.get(p, "")
        if _ws(r) == _ws(o):
            continue
        _rm, added = _sent_diff(o, r)
        for s in added:
            for m in _RX_VALUE.finditer(s):
                v = _ws(m.group(0))
                digits = re.findall(r"\d[\d.,]*", v)
                if not digits or "[" in s[max(0, m.start() - 2):m.start()]:
                    continue
                if all(d.strip(".,") in src_nums for d in digits):
                    continue
                undecided.append({"path": p, "value": v, "sentence": s[:200]})
    # 종료 후 판매·주문을 허용하면서 그 제품의 A/S·보증을 빠뜨림(계약에 보증·A/S 의무가 있을 때)
    wd = wind_down_structure(revised)
    acts = wd["activities"]
    # 보증기간이 선적·인도일부터 진행하고, 종료 후 주문을 '이 계약에 따라' 이행하게 하면 그 제품의 보증은 이미 계약 보증 조항이
    # 다룬다 — 이것을 공백으로 세면 있는 보호를 없다고 하는 오판이다(2026-11-13 시디즈 영문 공급계약 15.6·9.1).
    _wd_txt = " ".join(_ws(revised.get(p, "")) for p in wd["paths"])
    _covered = bool(_RX_WARRANTY_FROM_DELIVERY.search(r_all)) and bool(_RX_UNDER_THIS.search(_wd_txt))
    if wd["paths"] and ({"order", "selloff"} & set(acts)) and "service" not in acts and _RX_WARRANTY_DUTY.search(r_all) \
            and not _covered:
        probs.append({"code": "WD_SERVICE_MISSING", "severity": "block", "paths": list(wd["paths"]),
                      "message": "종료 후 주문 납품·재고 판매를 허용하면서 그 제품의 A/S·보증수리(부품 공급, 필요한 사용권, 기간)를 정하지 않음 "
                                 "— 판매한 제품의 보증의무를 이행할 근거가 없음"})
    return probs, undecided


# ── 5. 상황별 기대 결과 vs 실제 결과 ───────────────────────────────────────────

_RX_INS_ONLY_THEIRS = re.compile(r"(?:only\s+)?to\s+the\s+extent\s+(?:\w+\s+){0,3}(?:covered|paid|recovered)\s+(?:by|under)\s+(?:\w+\s+){0,2}insurance"
                                 r"|limited\s+to\s+(?:the\s+)?(?:amount\s+of\s+)?(?:\w+\s+){0,2}insurance\s+(?:proceeds|cover\w*)|보험금\s*(?:의\s*)?(?:범위|한도)\s*(?:내|에서|로)", re.I)
_RX_INS_WAIT = re.compile(r"(?:upon|after|following)\s+(?:the\s+)?receipt\s+of\s+(?:the\s+)?(?:\w+\s+){0,2}insurance|보험금(?:을)?\s*(?:수령|지급받)(?:한|하는|은)\s*(?:후|때)", re.I)
_RX_ACCEPT = re.compile(r"수용|감수|합의|동의|받아들|accept|agreed", re.I)
_SIT_KW = {
    "joint": r"공동\s*(?:귀책|과실|책임)|joint",
    "nofault": r"귀책\s*(?:없|불문)|무과실|불가항력|no[- ]fault|force\s+majeure",
    "insurance": r"보험|insur",
}


def _accepted(kind: str, request_text: str, answers_text: str, agreements: list[dict[str, Any]]) -> str:
    for ln in _lines(f"{request_text}\n{answers_text}") + [_s(a.get("content")) for a in agreements or []]:
        if re.search(_SIT_KW[kind], ln, re.I) and _RX_ACCEPT.search(ln):
            return ln[:200]
    return ""


def situation_matrix(original: dict[str, str], revised: dict[str, str], parties: Parties, *, request_text: str,
                     answers_text: str, agreements: list[dict[str, Any]], scenario_result: dict[str, Any]
                     ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """상황마다 기대 결과(검토 목적·합의) → 최종 문구로 읽은 실제 결과 → 일치 여부. 불일치는 문제 후보."""
    rows: list[dict[str, Any]] = []
    probs: list[dict[str, Any]] = []
    o_t, o_r, _ = _table(revised, parties, "ours")
    t_t, _t_r, _ = _table(revised, parties, "theirs")
    b_t, b_r, _ = _table(original, parties, "ours")

    def summ(table: dict[str, dict[str, str]], k: str) -> str:
        yes = sorted(p for p, v in table.items() if v.get(k) == LIABLE)
        no = sorted(p for p, v in table.items() if v.get(k) == NOT_LIABLE)
        if yes:
            return "책임 있음(" + ", ".join(yes) + ")" + (f"; 책임 없음({', '.join(no)})" if no else "")
        if no:
            return "책임 없음(" + ", ".join(no) + ")"
        return "정한 조항 없음"

    def row(sit: str, expected: str, actual: str, ok: bool | None, paths: list[str] | None = None, before: str = "") -> None:
        rows.append({"situation": sit, "expected": expected, "actual": actual, "before": before,
                     "result": "일치" if ok else ("해당 없음" if ok is None else "불일치"), "paths": paths or []})

    # 우리 귀책 — 우리 책임은 우리 귀책 범위
    row("우리 귀책(일반 과실)", "우리가 책임 — 우리 귀책 범위로 한정, 한도 적용", "우리: " + summ(o_t, "our_negligence"),
        True, before="우리: " + summ(b_t, "our_negligence"))
    row("우리 고의·중과실", "우리가 책임(한도 배제 가능)", "우리: " + summ(o_t, "our_gross"), True, before="우리: " + summ(b_t, "our_gross"))
    # 상대방 귀책 — 우리 책임 없음, 상대방 책임
    ours_their = [p for p, v in o_t.items() if v.get("their_negligence") == LIABLE]
    before_their = [p for p, v in b_t.items() if v.get("their_negligence") == LIABLE]
    row("상대방 귀책", "우리 책임 없음 — 상대방이 책임", f"우리: {summ(o_t, 'their_negligence')} / 상대방: {summ(t_t, 'their_negligence')}",
        not ours_their, ours_their, before="우리: " + summ(b_t, "their_negligence"))
    for p in ours_their:
        probs.append({"code": "SIT_THEIR_FAULT_OURS", "severity": "block", "paths": [p], "scenario": "their_negligence",
                      "pre_existing": p in before_their,
                      "message": f"상대방 귀책 사고인데 {p} 최종 문구로는 우리가 책임짐 — 상대방 귀책·상대방 제공 디자인/지식재산 원인 손해를 우리 책임에서 뺄 것"})
    # 공동 귀책 — 각자 귀책 비율
    all_ours = [p for p, rs in o_r.items() if any(r.catch_all and not r.limited and not r.negative
                                                   and not (r.except_causes.get("theirs")) for r in rs)]
    before_all = [p for p, rs in b_r.items() if any(r.catch_all and not r.limited and not r.negative
                                                     and not (r.except_causes.get("theirs")) for r in rs)]
    acc = _accepted("joint", request_text, answers_text, agreements)
    row("공동 귀책", "각자 귀책 비율로 부담" + (f"(합의: {acc})" if acc else ""),
        ("우리가 원인 불문 전부 부담(" + ", ".join(all_ours) + ")") if all_ours else "귀책 비율 또는 정함 없음(일반 원칙)",
        bool(acc) or not all_ours, all_ours)
    if all_ours and not acc:
        for p in all_ours:
            probs.append({"code": "SIT_JOINT_ALL_OURS", "severity": "block", "paths": [p], "pre_existing": p in before_all,
                          "message": f"공동 귀책 사고에서도 {p} 가 원인을 가리지 않는 포괄 배상이라 우리가 전부 부담 — '귀책 비율에 따라(to the extent caused by)' 로 좁힐 것"})
    # 귀책 없는 사고 — 합의 없으면 우리 부담 없음
    acc_nf = _accepted("nofault", request_text, answers_text, agreements)
    row("귀책 없는 사고", "합의가 없으면 우리 부담 없음" + (f"(합의: {acc_nf})" if acc_nf else ""),
        ("우리 부담(" + ", ".join(all_ours) + ")") if all_ours else "우리 부담 없음 또는 정함 없음", bool(acc_nf) or not all_ours, all_ours)
    if all_ours and not acc_nf:
        for p in all_ours:
            probs.append({"code": "SIT_NOFAULT_OURS", "severity": "block", "paths": [p], "pre_existing": p in before_all,
                          "message": f"어느 쪽 귀책도 없는 사고까지 {p} 에 따라 우리가 부담"})
    # 보험금 거절·지연
    ins_t = [p for p, t in revised.items() if any(_RX_INS_ONLY_THEIRS.search(s) and parties.who(s) == "theirs"
                                                  for s in sentences(t))]
    ins_t_b = [p for p, t in original.items() if any(_RX_INS_ONLY_THEIRS.search(s) and parties.who(s) == "theirs"
                                                     for s in sentences(t))]
    ins_cap = [c.get("path") for c in scenario_result.get("caps") or [] if c.get("insured_only")]
    wait = [p for p, t in revised.items() if any(_RX_INS_WAIT.search(s) and _hit(_rx_pay(parties, "theirs"), s) for s in sentences(t))]
    has_ins = any(re.search(r"insur|보험", t, re.I) for t in revised.values())
    acc_in = _accepted("insurance", request_text, answers_text, agreements)
    if has_ins:
        bad = (ins_t + ins_cap) if not acc_in else []
        row("보험금 거절·지연", "보험 처리와 무관하게 상대방 배상 의무·우리 책임한도 유지" + (f"(합의: {acc_in})" if acc_in else ""),
            "; ".join(x for x in [
                ("상대방 책임이 보험금 범위로 한정(" + ", ".join(ins_t) + ")") if ins_t else "",
                ("우리 한도가 보험 담보 청구에만 적용(" + ", ".join(ins_cap) + ")") if ins_cap else "",
                ("상대방 지급이 보험금 수령 후(" + ", ".join(wait) + ")") if wait else ""]
                if x) or "보험 거절·지연과 무관(영향 조항 없음)", not bad and not wait, bad + wait)
        for p in bad:
            probs.append({"code": "SIT_INSURANCE_THEIRS" if p in ins_t else "SIT_INSURANCE_OUR_CAP", "severity": "block", "paths": [p],
                          "pre_existing": p in ins_t_b if p in ins_t else False,
                          "message": (f"보험금이 거절되면 {p} 에 따라 상대방 배상 책임이 사라짐(보험금 범위로 한정)" if p in ins_t
                                      else f"보험이 거절·미담보하면 {p} 의 우리 책임한도가 적용되지 않음")})
        for p in wait:
            probs.append({"code": "SIT_INSURANCE_DELAY", "severity": "warn", "paths": [p],
                          "message": f"{p}: 상대방 지급이 보험금 수령 후로 되어 있어 보험 지연 시 지급도 늦어짐 — 지급 기한을 따로 정할 것"})
    else:
        row("보험금 거절·지연", "보험 조항 없음", "보험 조항 없음", None)
    # 종료: 정상 만료 / 중도해지 / 종료 후 주문·판매·A/S
    wd = scenario_result.get("wind_down") or {}
    codes = {p["code"]: p for p in scenario_result.get("problems") or []}
    acts = {a.get("activity"): a for a in wd.get("activities") or []}
    if wd.get("paths") and not ({"확정 주문 납품", "재고 판매"} & set(acts)):
        # 제품 판매·주문이 없는 종료 후 조항(임대차 원상복구 등)은 판매 기준 기대 결과로 판정하지 않는다
        row("정상 만료·중도해지·종료 후 활동", "종료 후 처리 조항", "종료 후 판매·주문 허용 없음(해당 계약 기준으로 확인)", None,
            list(wd.get("paths") or []))
    elif wd.get("paths") and _RX_UNDER_THIS.search(" ".join(_ws(revised.get(p, "")) for p in wd.get("paths") or [])):
        # 종료 시 남은 확정 주문을 '이 계약에 따라' 계속 이행 — 기간(그 주문 범위)·사용권·보증·정산은 계약 조항이 그대로 적용된다.
        # 라이선스형 종료 후 판매(기간·사용권·보고를 따로 정해야 하는 구조)와 다르다(2026-11-13 시디즈 15.6).
        warranty_ok = bool(_RX_WARRANTY_FROM_DELIVERY.search(" ".join(revised.values())))
        row("종료 후 확정 주문 이행", "남은 주문의 이행 조건이 정해져 있음", "이 계약 조건 그대로 적용(" + ", ".join(wd.get("paths") or []) + ")",
            True, list(wd.get("paths") or []))
        row("종료 후 A/S", "판매한 제품의 A/S·보증수리 근거", "보증 조항이 선적·인도일 기준으로 적용" if warranty_ok else "보증 기간 기준 확인 필요",
            True if warranty_ok else None, list(wd.get("paths") or []))
    elif wd.get("paths"):
        scope = codes.get("WD_SCOPE")
        row("정상 만료", "종료 후 허용 활동이 만료에도 적용", "적용 범위 미정" if scope and "만료" in _s(scope.get("message")) else "적용",
            not (scope and scope.get("severity") != "warn"), list(wd.get("paths") or []))
        row("중도해지", "해지 사유별 적용 범위가 명확", "사유별 적용 범위 미정" if scope else "명확", not scope, list(wd.get("paths") or []))
        for a, v in acts.items():
            row(f"종료 후 {a}", "기간·사용권·정산이 정해져 있음",
                ", ".join(x for x in [("기간 있음" if v.get("period") else "기간 없음"), ("사용권 있음" if v.get("license") else "사용권 없음"),
                                      ("정산·보고 있음" if v.get("report") else "정산·보고 없음")]),
                bool(v.get("period") and v.get("license")), list(wd.get("paths") or []))
        if "A/S·보증 부품" not in acts:
            sells = bool({"확정 주문 납품", "재고 판매"} & set(acts))
            warranty = any(_RX_WARRANTY_DUTY.search(t) for t in revised.values())
            row("종료 후 A/S", "판매한 제품의 A/S·보증수리 근거(기간·사용권)",
                "정함 없음" + ("" if warranty else " — 계약에 보증·A/S 의무 없음"),
                (False if warranty else None) if sells else None, list(wd.get("paths") or []))
    else:
        row("정상 만료·중도해지·종료 후 활동", "종료 후 처리 조항", "종료 후 처리 조항 없음(해당 계약에서 확인 필요)", None)
    return rows, probs


# ── 검증 1회(같은 버전 전체) ─────────────────────────────────────────────────────

def _descriptions(owners: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p, crs in owners.items():
        ds: list[str] = []
        for cr in crs:
            for k in ("brief_action", "rewrite_reason", "verification_description"):
                d = _ws(cr.get(k))
                if d and d not in ds:
                    ds.append(d)
        out[p] = " ".join(ds)
    return out


def verify(*, clauses: list[Any] | None, clause_results: list[dict[str, Any]] | None, parties: Parties,
           request_text: str = "", answers_text: str = "", basis_extra: dict[str, str] | None = None) -> dict[str, Any]:
    """마지막 수정까지 넣은 같은 버전을 한 번 검증한다. 결과는 이 버전(fingerprint)에만 유효하다."""
    orig, rev, owners = build_maps(clauses, clause_results)
    descs = _descriptions(owners)
    base = evaluate(original=orig, revised=orig, parties=parties, request_text=request_text, answers_text=answers_text)
    res = evaluate(original=orig, revised=rev, parties=parties, request_text=request_text, answers_text=answers_text, descriptions=descs)
    agreements = res.get("agreements") or []
    base_keys = {(p["code"], ",".join(sorted(p["paths"])), p.get("scenario", "")) for p in base["problems"]}
    changed = {p for p in set(orig) | set(rev) if _ws(orig.get(p, "")) != _ws(rev.get(p, ""))}
    problems: list[dict[str, Any]] = []

    def add(p: dict[str, Any]) -> None:
        key = (p["code"], ",".join(sorted(p.get("paths") or [])), p.get("scenario", ""))
        if any((x["code"], ",".join(sorted(x.get("paths") or [])), x.get("scenario", "")) == key for x in problems):
            return
        cat = CODE_CATEGORY.get(p["code"], "")
        introduced = key not in base_keys and not p.get("pre_existing")
        touched = bool(set(p.get("paths") or []) & changed)
        p = {**p, "category": cat, "introduced": introduced, "touched": touched,
             "owners": sorted({_s(cr.get("clause_id")) for path in p.get("paths") or [] for cr in owners.get(path, [])})}
        # 출력 차단: 범주가 있고 block 이며, 수정으로 생겼거나 수정한 조항에 남은 것. 손대지 않은 원문 문제는 '원문 잔존 위험'.
        p["critical"] = bool(cat) and p.get("severity", "block") == "block" and (introduced or touched)
        p.pop("pre_existing", None)
        problems.append(p)

    # (4) deal_scenarios — 책임 충돌·한도·연장·종료 후·로열티·설명 방향
    for p in res["problems"]:
        if p["code"] == "RIGHT_REMOVED":
            continue   # 아래 효과 분석(OUR_RIGHT_REMOVED)이 근거 확인까지 한다
        add(dict(p))
    # (2) 우리 회사 효과 + 근거
    eff_rows, cands = effect_rows(orig, rev, parties)
    grounds: list[dict[str, Any]] = []
    for c in cands:
        own = [cr for path in c["paths"] for cr in owners.get(path, [])]
        g = find_ground(c, own, request_text=request_text, answers_text=answers_text, agreements=agreements,
                        revised_text=rev.get(c["paths"][0], ""), parties=parties)
        er = next((r for r in eff_rows if r["path"] == c["paths"][0]), None)
        if not g and c["code"] == "OUR_PAYMENT_UP" and er and "우리 권리 추가" in er["effects"] \
                and re.search(r"royalt|fee|remuneration|로열티|사용료|대가", c.get("sentence", ""), re.I):
            # 같은 수정으로 우리가 새 권리(종료 후 판매 등)를 얻고 그 대가를 내는 구조 — 의도적 교환으로 표시하고 막지 않는다
            right = next((s for s in er["added_sentences"] if _hit(_rx_right(parties, "ours"), s)), "")
            g = {"kind": "같은 수정의 교환조건", "text": f"불리: {c['sentence'][:160]} / 교환(새 권리): {right[:160]}"}
        if g:
            grounds.append({"code": c["code"], "paths": c["paths"], **g})
            continue
        fair = [cr for cr in own if _RX_FAIRNESS_ONLY.search(_ws(cr.get("rewrite_reason")) + " " + _ws(cr.get("brief_action")))]
        msg = c["message"] + " — 사용자 지시·확인된 합의·협상 교환조건이 없음" + \
            (" ('상호 공평'·'상대방 부담' 은 우리 보호를 줄이는 근거가 아님)" if fair else "")
        add({**c, "severity": "block", "message": msg})
    # (3) 문구 의미 — 설명과 상황별 결과(상대방 쪽), 설명 극성과 효과
    _tt, _, _ = _table(rev, parties, "theirs")
    for path, desc in descs.items():
        want = their_intents(desc, parties)
        row = _tt.get(path) or {}
        for k, v in want.items():
            got = row.get(k)
            if got and ((v == LIABLE and got == NOT_LIABLE) or (v == NOT_LIABLE and got == LIABLE)):
                add({"code": "THEIR_DIRECTION_MISMATCH", "severity": "block", "paths": [path], "scenario": k,
                     "message": f"설명은 '{SCENARIO_LABEL[k]}' 을 상대방 {v} 으로 말하는데 {path} 수정 문구로는 상대방 {got} — 부정문·예외로 방향이 뒤집혔는지 확인"})
        er = next((r for r in eff_rows if r["path"] == path), None)
        if not er or not desc:
            continue
        bad = [e for e in er["effects"] if re.search(r"우리 책임 증가|상대방 책임 감소|상대방 책임한도 신설|우리 책임한도 삭제|우리 권리 삭제|우리 면책|상대방 지급 의무 삭제|우리 지급", e)]
        good = [e for e in er["effects"] if re.search(r"우리 책임 감소|상대방 책임 증가|우리 책임한도 신설|우리 권리 추가", e)]
        if _RX_DESC_PROTECT.search(desc) and bad and not good and not _RX_DESC_CONCEDE.search(desc):
            add({"code": "DESC_EFFECT_MISMATCH", "severity": "block", "paths": [path],
                 "message": f"설명은 우리 보호를 강화한다고 하는데 {path} 수정 문구의 실제 효과는 {', '.join(bad)} — 주체(우리/상대방)와 방향을 다시 쓸 것"})
        if _RX_DESC_OUR_CAP.search(desc) and "상대방 책임한도 신설" in er["effects"] and "우리 책임한도 신설" not in er["effects"]:
            add({"code": "DESC_EFFECT_MISMATCH", "severity": "block", "paths": [path],
                 "message": f"설명은 우리 책임한도를 두겠다는데 {path} 수정 문구는 상대방의 책임한도를 신설함(주체 뒤바뀜)"})
    # (4) 상호참조·정의어·미확정 값·종료 후 A/S
    comp, undecided = completeness_problems(orig, rev, request_text=request_text, answers_text=answers_text)
    for p in comp:
        add(p)
    # (5) 상황별
    sit_rows, sit_probs = situation_matrix(orig, rev, parties, request_text=request_text, answers_text=answers_text,
                                           agreements=agreements, scenario_result=res)
    for p in sit_probs:
        add(p)
    if changed and not getattr(parties, "confirmed", True):
        add({"code": "BASIS_PARTY_UNCONFIRMED", "severity": "block", "paths": [],
             "message": "우리 회사가 계약서의 어느 당사자(정의어)인지 원문·당사자 지도에서 확정하지 못함 — 책임·지급·권리의 방향 검증을 "
                        "신뢰할 수 없음. 우리 당사자명·역할을 확인한 뒤 다시 검증할 것"})
    critical = [p for p in problems if p["critical"]]
    readings = {}
    for path in sorted(changed):
        _rm, added = _sent_diff(orig.get(path, ""), rev.get(path, ""))
        readings[path] = [{"sentence": s[:240], **read_sentence(s, parties)} for s in added[:4]]
    return {
        "version": fingerprint(clause_results),
        "status": STATUS_FAIL if critical else (STATUS_PASS if changed else STATUS_NONE),
        "changed_paths": sorted(changed),
        "effects": eff_rows,
        "grounds": grounds,
        "readings": readings,
        "roles": clause_roles(rev, parties, sorted(changed)),
        "situations": sit_rows,
        "undecided_values": undecided,
        "problems": problems,
        "critical": critical,
        "residual_original": [p for p in problems if p.get("category") and not p["critical"] and not p["introduced"]],
        "scenario_result": res,
    }


# ── 재작성(AI) · 제거(코드) · 재검증 ────────────────────────────────────────────

_REPAIR_SYSTEM = """너는 우리 회사 사내변호사 책임자다. 수정안을 모두 넣은 계약을 코드가 검증했더니 아래 문제가 남았다. 문제 수정안만 다시 써라.

원칙
- 기준은 우리 회사다. 우리 권리를 줄이거나 우리 의무·비용·책임을 늘리거나 상대방 책임을 줄이거나 우리에게 유리한 기존 조건·예외·구제수단을 지우는 수정은
  사용자 지시·확인된 합의·설명 가능한 협상 교환조건이 있을 때만 쓴다. '상호 공평'·'상대방 부담이 크다' 는 이유가 아니다.
  의도적으로 양보하면 concession 에 불리한 효과와 교환조건을 적는다.
- 수정 문구를 '누가 / 누구에게 / 어떤 조건에서 / 무엇을 / 언제까지 / 어떤 예외·한도로' 로 다시 읽어 description(한국어 설명)과 같은 방향인지 확인한다.
  부정문(not, no), unless, except, only, to the extent, notwithstanding, 고의·중과실·일반 과실의 범위를 특히 확인한다. 주체(우리/상대방)를 바꿔 쓰지 않는다.
- 책임한도는 보호받는 쪽(누구의 책임을 묶는지)을 정확히 쓴다. 우리 책임한도를 상대방 책임한도로 쓰지 않는다.
- 다른 조항과 충돌하지 않게 하고, 삭제로 상호참조·정의어·보호가 빠지지 않게 한다. 종료 후 판매·주문을 허용하면 그 제품의 A/S·보증수리(기간·사용권)도 정한다.
- 합의되지 않은 금액·기간은 [●] 로 둔다. 바꾸지 않는 원문 숫자·정의어는 그대로 쓴다. 계약 원문 언어로 쓴다.
- 고칠 수 없으면 decision=remove (수정안을 빼고 원문을 유지).

JSON 하나만: {"fixes": [{"id": "<수정안 id>", "decision": "rewrite|remove", "new_text": "<현재 수정 문구(replacement)를 대신할 완성 문구>",
  "description": "한국어 설명", "concession": {"disadvantage": "", "exchange": ""}}]}"""


def _set_replacement(cr: dict[str, Any], new: str) -> None:
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else None
    if ri is None:
        cr["suggested_rewrite"] = new
        return
    old = _s(ri.get("replacement_text"))
    ri["replacement_text"] = new
    fin = _s(ri.get("final_clause_text"))
    ri["final_clause_text"] = fin.replace(old, new, 1) if fin and old and old in fin else new
    sr = _s(cr.get("suggested_rewrite"))
    cr["suggested_rewrite"] = sr.replace(old, new, 1) if sr and old and old in sr else new


def hold_edit(cr: dict[str, Any], reason: str) -> None:
    ri = cr.get("redline_instruction")
    if not isinstance(ri, dict):
        ri = {}
        cr["redline_instruction"] = ri
    ri["held"] = True
    ri["hold_reason"] = reason
    cr["verification_removed"] = reason


def _ai_repair(provider: Any, *, model: str, critical: list[dict[str, Any]], clause_results: list[dict[str, Any]],
               rev: dict[str, str], orig: dict[str, str], facts: str, timeout_sec: float, max_tokens: int,
               latin: bool) -> list[str]:
    from runtime.ai.enhance import _build_request, _try_json

    by_id = {_s(cr.get("clause_id")): cr for cr in live_edits(clause_results)}
    ids = sorted({i for p in critical for i in p.get("owners") or [] if i in by_id})
    if not ids:
        return []
    rows = []
    for i in ids:
        cr = by_id[i]
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        rows.append({"id": i, "path": _s(cr.get("display_path")), "target_text": _s(ri.get("target_text"))[:1500],
                     "current_replacement": _s(ri.get("replacement_text") or cr.get("suggested_rewrite"))[:2500],
                     "description": _ws(_s(cr.get("brief_action")) + " " + _s(cr.get("rewrite_reason")))[:600]})
    paths = sorted({p for x in critical for p in x.get("paths") or []})
    user = ("[거래 사실·검토 기준]\n" + facts + "\n\n[코드 검증 문제]\n- " + "\n- ".join(f"[{p['category']}] {p['message']}" for p in critical)
            + "\n\n[수정 전 조항]\n" + "\n".join(f"[{p}] {orig.get(p, '(없음)')[:1500]}" for p in paths)
            + "\n\n[현재 수정안을 모두 넣은 조항]\n" + "\n".join(f"[{p}] {rev.get(p, '(없음)')[:1500]}" for p in paths)
            + "\n\n[다시 쓸 수정안]\n" + json.dumps(rows, ensure_ascii=False, indent=1))
    try:
        resp = provider.complete(_build_request(model=model, system=_REPAIR_SYSTEM, user=user, timeout_sec=timeout_sec,
                                                max_tokens=max_tokens, temperature=0.1))
        out = _try_json(getattr(resp, "content", "") or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("verification repair call failed: %s", exc)
        return []
    done: list[str] = []
    for f in (out or {}).get("fixes") or [] if isinstance(out, dict) else []:
        cr = by_id.get(_s(f.get("id")))
        if cr is None:
            continue
        if _s(f.get("decision")).strip() == "remove":
            hold_edit(cr, "필수 검증 미통과 — 수정안 제거(원문 유지): " + "; ".join(p["message"] for p in critical if cr.get("clause_id") in p.get("owners", []))[:300])
            done.append(_s(cr.get("clause_id")))
            continue
        new = _s(f.get("new_text")).strip()
        if not new or re.search(r"…|\.\.\.(?!\])", new) or (latin and re.search(r"[가-힣]", new)):
            continue
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        tgt = _ws(_strip_markers(_s(ri.get("target_text"))))
        old = _ws(_strip_markers(_s(ri.get("replacement_text"))))
        if tgt and old.startswith(tgt) and not _ws(new).startswith(tgt[:60]):
            new = _s(ri.get("target_text")).rstrip() + " " + new   # 덧붙임 수정은 원문 문장을 지우지 않는다
        _set_replacement(cr, new)
        if _s(f.get("description")).strip():
            cr["verification_description"] = _s(f.get("description")).strip()
            cr["brief_action"] = _s(f.get("description")).strip()
        if isinstance(f.get("concession"), dict) and _s(f["concession"].get("disadvantage")).strip():
            cr["concession"] = {"disadvantage": _s(f["concession"].get("disadvantage")), "exchange": _s(f["concession"].get("exchange"))}
        cr["verification_rewritten"] = True
        done.append(_s(cr.get("clause_id")))
    return done


def _mark_undecided(clause_results: list[dict[str, Any]], owners: dict[str, list[dict[str, Any]]], undecided: list[dict[str, Any]]) -> int:
    n = 0
    for u in undecided:
        for cr in owners.get(u["path"], []):
            rw = _s((cr.get("redline_instruction") or {}).get("replacement_text") if isinstance(cr.get("redline_instruction"), dict) else "") \
                or _s(cr.get("suggested_rewrite"))
            if u["value"] not in _ws(rw) and u["value"] not in rw:
                continue
            label = f"{u['value']} — 제안값(원문·요청·답변에 없음, 미합의): 서명 전 확정"
            lst = [x for x in cr.get("undecided_terms") or []]
            if not any(_s(x).startswith(u["value"]) for x in lst):
                lst.append(label)
                cr["undecided_terms"] = lst
                n += 1
    return n


def _pkey(p: dict[str, Any]) -> tuple[str, str, str]:
    return (p["code"], ",".join(sorted(p.get("paths") or [])), p.get("scenario", ""))


def _culprits(problem: dict[str, Any], by_id: dict[str, dict[str, Any]], **kw: Any) -> list[str]:
    """문제를 만든 수정안만 — 같은 조항의 수정안이 여럿이면 하나씩 빼 보며 문제가 사라지는 것을 찾는다(요청한 다른 수정까지 빼지 않게)."""
    owners = [i for i in problem.get("owners") or [] if i in by_id]
    if len(owners) <= 1:
        return owners
    key = _pkey(problem)
    found: list[str] = []
    for i in owners:
        ri = by_id[i].get("redline_instruction")
        if not isinstance(ri, dict):
            ri = {}
            by_id[i]["redline_instruction"] = ri
        prev = ri.get("held")
        ri["held"] = True
        try:
            r = verify(**kw)
        finally:
            if prev is None:
                ri.pop("held", None)
            else:
                ri["held"] = prev
        if key not in {_pkey(x) for x in r["critical"]}:
            found.append(i)
    return found or owners


def run_verification_gate(*, clause_results: list[dict[str, Any]], clauses: list[Any] | None, parties: Parties,
                          contract_text: str = "", request_text: str = "", answers_text: str = "",
                          basis_fields: dict[str, str] | None = None, provider: Any = None, model: str = "",
                          facts: str = "", rounds: int = 2, timeout_sec: float = 150.0, max_tokens: int = 6000,
                          remove_on_fail: bool = True) -> dict[str, Any]:
    """검증 → (AI 재작성 → 재검증)×rounds → (근거 없는 불리한 수정 제거 → 재검증) → 최종 판정.

    매 단계 이전 결과를 버리고 마지막 버전 전체를 다시 검증한다. 남은 critical 이 있으면 STATUS_FAIL.
    """
    bf = basis_fields or {}
    orig0, _rev0, _ow0 = build_maps(clauses, clause_results)
    basis = build_basis(parties=parties, original=orig0, request_text=request_text, answers_text=answers_text,
                        our_name=bf.get("our_name", ""), our_role=bf.get("our_role", ""),
                        counterparty_name=bf.get("counterparty_name", ""), counterparty_role=bf.get("counterparty_role", ""),
                        purpose=bf.get("purpose", ""), payment_flow=bf.get("payment_flow", ""))
    latin = bool(re.search(r"[A-Za-z]", contract_text[:20000])) and \
        sum(ch.isascii() and ch.isalpha() for ch in contract_text[:20000]) >= 3 * max(1, sum("가" <= ch <= "힣" for ch in contract_text[:20000]))
    facts_all = facts + "\n- 검토 기준: " + json.dumps({k: basis[k] for k in ("our_party", "our_defined_terms", "counterparty", "our_role",
                                                                           "purpose", "needs_confirmation")}, ensure_ascii=False)
    history: list[dict[str, Any]] = []
    res = verify(clauses=clauses, clause_results=clause_results, parties=parties, request_text=request_text, answers_text=answers_text)
    history.append({"step": "검증 1", "version": res["version"], "status": res["status"],
                    "critical": [f"[{p['category']}] {p['message']}" for p in res["critical"]]})
    for n in range(rounds):
        if not res["critical"] or provider is None:
            break
        orig, rev, _ = build_maps(clauses, clause_results)
        backup = json.loads(json.dumps([cr for cr in clause_results if isinstance(cr, dict)], ensure_ascii=False, default=str))
        done = _ai_repair(provider, model=model, critical=res["critical"], clause_results=clause_results, rev=rev, orig=orig,
                          facts=facts_all, timeout_sec=timeout_sec, max_tokens=max_tokens, latin=latin)
        if not done:
            history.append({"step": f"AI 재작성 {n + 1}", "result": "응답 없음 또는 적용 가능한 수정 없음"})
            break
        res2 = verify(clauses=clauses, clause_results=clause_results, parties=parties, request_text=request_text, answers_text=answers_text)
        history.append({"step": f"AI 재작성 {n + 1} → 재검증", "rewritten": done, "version": res2["version"], "status": res2["status"],
                        "critical": [f"[{p['category']}] {p['message']}" for p in res2["critical"]]})
        if len(res2["critical"]) > len(res["critical"]):
            # 고친 결과가 더 나쁘면 되돌린다(이전 버전으로 돌아가므로 그 버전을 다시 검증한다)
            idx = [i for i, cr in enumerate(clause_results) if isinstance(cr, dict)]
            for i, b in zip(idx, backup):
                clause_results[i].clear()
                clause_results[i].update(b)
            res = verify(clauses=clauses, clause_results=clause_results, parties=parties, request_text=request_text, answers_text=answers_text)
            history.append({"step": f"AI 재작성 {n + 1} 되돌림", "version": res["version"], "status": res["status"]})
            break
        res = res2
    if res["critical"] and remove_on_fail:
        # 수정으로 생긴(introduced) 문제는 그 수정안을 빼면 없어진다 — 근거 없는 불리한 수정은 제거한다.
        removed: list[str] = []
        for _ in range(3):
            by_id = {_s(cr.get("clause_id")): cr for cr in live_edits(clause_results)}
            # 제거는 '해로운 수정'(방향 역전·근거 없는 보호 축소·설명 불일치·새 로열티 부담)에만. 충돌·공백은 수정안을 빼면
            # 요청한 보호까지 사라지므로 남겨 두고 '검증 미통과 초안' 으로 미해결 사항을 보인다(임의 통과 금지).
            todo = [p for p in res["critical"] if p["introduced"] and p.get("owners")
                    and (p["category"] in (CAT_DIRECTION, CAT_PROTECTION, CAT_MISMATCH) or p["code"] in _REMOVABLE_GAP_CODES)]
            if not todo:
                break
            for p in todo:
                for i in _culprits(p, by_id, clauses=clauses, clause_results=clause_results, parties=parties,
                                   request_text=request_text, answers_text=answers_text):
                    cr = by_id.get(i)
                    if cr is not None and not (cr.get("redline_instruction") or {}).get("held"):
                        hold_edit(cr, f"필수 검증 미통과로 수정안 제거(원문 유지) — {p['category']}: {p['message']}"[:400])
                        removed.append(i)
            res = verify(clauses=clauses, clause_results=clause_results, parties=parties, request_text=request_text, answers_text=answers_text)
            history.append({"step": "근거 없는·역전된 수정안 제거 → 재검증", "removed": sorted(set(removed)), "version": res["version"],
                            "status": res["status"], "critical": [f"[{p['category']}] {p['message']}" for p in res["critical"]]})
    _o, _r, owners = build_maps(clauses, clause_results)
    marked = _mark_undecided(clause_results, owners, res["undecided_values"])
    if marked:
        res = verify(clauses=clauses, clause_results=clause_results, parties=parties, request_text=request_text, answers_text=answers_text)
        history.append({"step": "미확정 값 표시 → 재검증", "marked": marked, "version": res["version"], "status": res["status"]})
    res["basis"] = basis
    res["history"] = history
    res["removed_edits"] = [{"clause_id": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")),
                             "reason": RX_INTERNAL.sub("", _s(cr.get("verification_removed"))).strip()}
                            for cr in clause_results if isinstance(cr, dict) and cr.get("verification_removed")]
    res["rewritten_edits"] = [_s(cr.get("clause_id")) for cr in clause_results if isinstance(cr, dict) and cr.get("verification_rewritten")]
    res["inputs"] = {"ours": list(parties.ours), "theirs": list(parties.theirs), "aliases_ours": list(parties.aliases_ours),
                     "party_confirmed": bool(getattr(parties, "confirmed", True)),
                     "aliases_theirs": list(parties.aliases_theirs), "request_text": request_text[:20000],
                     "answers_text": answers_text[:20000], "basis_fields": bf}
    res["unresolved"] = unresolved_items(res)
    return res


def unresolved_items(res: dict[str, Any]) -> list[dict[str, str]]:
    """사업팀에 보일 미해결 사항 — 코드명 없이 범주·조항·내용."""
    out = []
    for p in res.get("critical") or []:
        out.append({"category": p["category"], "paths": ", ".join(p.get("paths") or []), "detail": RX_INTERNAL.sub("", _s(p["message"])).strip()})
    return out


# ── 출력 통제: 같은 버전인지 확인하고 아니면 다시 검증 ───────────────────────────────

def parties_from_inputs(inp: dict[str, Any], meta: dict[str, Any] | None = None) -> Parties:
    ours = list(inp.get("ours") or [])
    theirs = list(inp.get("theirs") or [])
    if not ours and isinstance(meta, dict):
        pm = meta.get("party_map") if isinstance(meta.get("party_map"), dict) else {}
        ours = [_s(p.get("label")) for p in pm.get("parties") or [] if p.get("is_our_company") and p.get("label")]
        theirs = [_s(p.get("label")) for p in pm.get("parties") or [] if not p.get("is_our_company") and p.get("label")]
    return Parties(ours=ours or ["Customer", "Licensee"], theirs=theirs or ["Supplier", "Licensor"],
                   aliases_ours=list(inp.get("aliases_ours") or []), aliases_theirs=list(inp.get("aliases_theirs") or []),
                   confirmed=bool(inp.get("party_confirmed", bool(ours))))


def ensure_current(meta: dict[str, Any] | None, clause_results: list[dict[str, Any]] | None, clauses: list[Any] | None) -> dict[str, Any] | None:
    """출력 직전: 저장된 검증이 지금 수정안 버전과 같은지 확인한다. 다르면 이전 결과를 버리고 다시 검증한다(재작성·제거 없이)."""
    if not isinstance(meta, dict):
        return None
    vg = meta.get("verification_gate") if isinstance(meta.get("verification_gate"), dict) else None
    if vg is None or vg.get("error"):
        return vg
    cur = fingerprint(clause_results)
    if vg.get("version") == cur:
        apply_external(meta)
        return vg
    inp = vg.get("inputs") if isinstance(vg.get("inputs"), dict) else {}
    res = verify(clauses=clauses, clause_results=clause_results, parties=parties_from_inputs(inp, meta),
                 request_text=_s(inp.get("request_text")), answers_text=_s(inp.get("answers_text")))
    res["basis"] = vg.get("basis")
    res["inputs"] = inp
    res["history"] = list(vg.get("history") or []) + [{"step": "수정안 변경 감지 → 이전 검증 폐기·재검증", "previous_version": vg.get("version"),
                                                         "version": res["version"], "status": res["status"]}]
    res["unresolved"] = unresolved_items(res)
    meta["verification_gate"] = compact(res)
    meta["deal_scenarios"] = res["scenario_result"]
    apply_external(meta)
    return meta["verification_gate"]


def compact(res: dict[str, Any]) -> dict[str, Any]:
    """meta 에 둘 결과(세션 저장용) — scenario_result 는 meta['deal_scenarios'] 로 따로 둔다."""
    return {k: v for k, v in res.items() if k != "scenario_result"}


def external_unresolved(meta: dict[str, Any] | None) -> list[dict[str, str]]:
    """거래 흐름 선검증·Word 수정본 재검사가 해결하지 못한 항목(2026-11-09) — 필수 검증의 미해결과 같은 효력."""
    out: list[dict[str, str]] = []
    for key in ("deal_flow", "final_docx_check"):
        d = (meta or {}).get(key) if isinstance(meta, dict) else None
        if isinstance(d, dict):
            for u in d.get("unresolved") or []:
                if isinstance(u, dict):
                    out.append({"category": _s(u.get("category")), "paths": _s(u.get("paths")), "detail": _s(u.get("detail"))})
    return out


def apply_external(meta: dict[str, Any] | None) -> None:
    """외부 단계의 미해결이 있으면 검증 결과를 '검증 미통과 초안' 으로 두고 미해결 목록에 싣는다."""
    if not isinstance(meta, dict):
        return
    ext = external_unresolved(meta)
    vg = meta.get("verification_gate")
    if not ext or not isinstance(vg, dict):
        return
    have = {(_s(u.get("category")), _s(u.get("detail"))) for u in vg.get("unresolved") or [] if isinstance(u, dict)}
    vg["unresolved"] = list(vg.get("unresolved") or []) + [u for u in ext if (u["category"], u["detail"]) not in have]
    vg["status"] = STATUS_FAIL
    vg["external_unresolved"] = len(ext)


def is_failed(meta: dict[str, Any] | None) -> bool:
    if external_unresolved(meta):
        apply_external(meta)
        return True
    vg = (meta or {}).get("verification_gate") if isinstance(meta, dict) else None
    return isinstance(vg, dict) and vg.get("status") == STATUS_FAIL


__all__ = [
    "CAT_DIRECTION", "CAT_GAP", "CAT_MISMATCH", "CAT_PROTECTION", "RX_INTERNAL", "STATUS_FAIL", "STATUS_NONE", "STATUS_PASS",
    "CAT_BASIS", "build_basis", "build_maps", "compact", "effect_rows", "ensure_current", "fingerprint", "is_failed", "live_edits",
    "parties_from_inputs", "read_sentence", "run_verification_gate", "situation_matrix", "unresolved_items", "verify",
]
