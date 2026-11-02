"""모든 수정안을 **함께** 반영한 상태를 검사한다 (2026-10-21 지시 3항).

왜 필요했나 (실측 — 프리랜서 콘텐츠 용역계약)
─────────────────────────────────────────────
수정안 하나하나는 게이트를 통과했지만, 같이 넣으면 계약서가 깨졌다.

  · 제8조 보완 문장과 제10조 보완 문장이 둘 다 "제12조 뒤에 제13조 신설" — 조 번호 중복.
    신설 위치는 지적마다 "마지막 조 + 1" 로 따로 계산됐다(clause_level 의 fallback).
  · 제8조 보완 문장의 "제1항에 따라 … 귀속되는 권리" 가 새 제13조에 들어가면 어느 조의
    제1항인지 알 수 없다 — 제8조 안의 새 항으로 들어가야 맞는 문장이다.
  · 수정 지시는 "신설" 인데 실무 포지션은 "문구 교체" — 그대로 교체하면 제8조 제1항의 귀속
    문언이 지워진다.

여기서 하는 일 (새 판단을 만들지 않는다 — 위치·번호·참조의 정합성만 본다)
  1. 실재 조를 보완하는 신설 문장은 그 조의 **새 항**으로 둔다(부분 보완 우선).
  2. 조 신설이 여럿이면 번호를 겹치지 않게 차례로 매긴다.
  3. 실무 포지션의 위치·방식을 수정 지시와 맞춘다.
  4. 반영 후 문안이 가리키는 조·항이 실재(또는 이번에 신설)하는지 본다.
  5. 교체로 기존 보호 문구가 사라지면 자동 적용을 보류한다.
  검증하지 못한 수정안은 **자동 적용만 보류**한다 — 지적 자체는 남긴다.
"""
from __future__ import annotations

import re
from typing import Any

_RX_ART = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*\d+)?")
_RX_ART_PARA = re.compile(r"제\s*(\d+)\s*조\s*제\s*(\d+)\s*항")
#: 조 없이 쓴 "제N항" — 같은 조의 항을 가리킨다.
_RX_BARE_PARA = re.compile(r"(?<![조\d])\s*제\s*(\d+)\s*항")
_RX_LAW_BEFORE = re.compile(r"(?:법|법률|령|규칙|시행령)\s*$")
_RX_TOKEN = re.compile(r"[가-힣A-Za-z]{2,}")
#: 교체로 사라지면 보호 범위가 줄어드는 낱말(보호 대상·의무·존속·예외).
_RX_PROTECTIVE = re.compile(
    r"비밀|비공개|내부\s*자료|영업\s*정보|고객\s*정보|생성형|제3자|외부\s*서비스|목적\s*외|누설|종료\s*후|존속"
    r"|귀속|독점|배타|보증|면책|배상|해지|시정|승인|동의|서면|기한|이내"
)

#: 기존 수정 방식(redline_instruction.EDIT_TYPES)을 쓴다 — 새 유형을 만들면 다운로드 경로의 완결성 검사가 미완성으로 본다.
EDIT_INSERT_PARAGRAPH = "insert_after"
EDIT_NEW_CLAUSE = "new_clause"
#: "제A조(제목) 제N항 뒤에 제M항 신설"
_RX_PARA_INSERT = re.compile(r"제\s*(\d+)\s*조(?:\s*\([^)]*\))?\s*제\s*(\d+)\s*항\s*뒤에\s*제\s*(\d+)\s*항\s*신설")
#: "제A조 뒤에 제B조(의C) 신설"
_RX_NEW_ART_AFTER = re.compile(r"^\s*제\s*(\d+)\s*조(?:\([^)]*\))?\s*뒤에\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*신설")


def _live(cr: Any) -> bool:
    # 수정본(clean)도 HIGH/MEDIUM 만 반영한다(docx_redline) — 반영하는 것과 검사하는 것이 같은 집합이다.
    return (isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM"))


#: 계약 문안이 아니라 수정 지시문 — "제12조 제3항을 다음과 같이 수정한다. '…'" 를 그대로 넣으면 계약서에 지시문이 남는다.
_RX_INSTRUCTION = re.compile(r"다음과\s*같이\s*(?:수정|변경|개정|보완)(?:한다|함)|다음\s*(?:문단|문장|항|호|내용)을\s*(?:추가|신설)(?:한다|함)")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).replace("“", '"').replace("”", '"')


def _is_new(ri: dict[str, Any]) -> bool:
    return str(ri.get("edit_type") or "") in (EDIT_NEW_CLAUSE, EDIT_INSERT_PARAGRAPH) or "신설" in str(
        ri.get("edit_location") or "")


def _statute_ref(text: str, start: int) -> bool:
    return bool(_RX_LAW_BEFORE.search(text[max(0, start - 12): start]))


def _paragraphs_of(index: Any, art: str) -> list[str]:
    a = (getattr(index, "articles", None) or {}).get(str(art))
    return [str(p) for p in (getattr(a, "paragraphs", ()) or ())] if a is not None else []


def _protective_loss(target: str, replacement: str) -> list[str]:
    """교체 전 문구에 있던 보호 낱말 중 교체 후 문구에 없는 것."""
    lost: list[str] = []
    rep = _norm(replacement)
    for m in _RX_PROTECTIVE.finditer(str(target or "")):
        w = _norm(m.group(0))
        if w and w not in rep and w not in lost:
            lost.append(w)
    return lost


def _retention(target: str, replacement: str) -> float:
    toks = set(_RX_TOKEN.findall(str(target or "")))
    if not toks:
        return 1.0
    rep = str(replacement or "")
    return sum(1 for t in toks if t in rep) / len(toks)


#: 계약 전체에서 세는 보호 표지 — 담보·보증·상계·이용권·환급·해지·면책.
_PROTECTION_MARKERS: tuple[tuple[str, str], ...] = (
    ("근저당", r"근저당권?"), ("질권", r"질권"), ("상계", r"상계"), ("기한이익 상실", r"기한이\s*도래한\s*것으로\s*본다"),
    ("보증", r"연대하여\s*보증|연대\s*보증|보증한다|보증인"), ("물상보증", r"물상보증"),
    ("사용 승인", r"사용(?:을)?\s*(?:승인|승낙)"), ("환급·반환", r"반환(?:한다|하여야)|환급"),
    ("대위변제", r"대신\s*변제"), ("손해배상", r"손해를?\s*배상"), ("해지권", r"해지할\s*수\s*있"),
    ("면책", r"면책"), ("승계", r"승계"),
)
_RX_SUBJECT = re.compile(r"[“\"]([^”\"]{1,10})[”\"](?:은|는|이|가)\s")


def _ws_pattern(text: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in re.split(r"\s+", str(text or "").strip()) if p]
    return re.compile(r"\s*".join(parts))


def _inventory(text: str) -> dict[str, int]:
    return {name: len(re.findall(rx, text or "")) for name, rx in _PROTECTION_MARKERS}


def _apply(body: str, edits: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    out = body
    for _cr, ri in edits:
        if ri.get("held"):
            continue
        repl = str(ri.get("replacement_text") or ri.get("final_clause_text") or "")
        if _is_new(ri):
            out += "\n" + repl
            continue
        target = str(ri.get("target_text") or "")
        if not target:
            continue
        m = _ws_pattern(target).search(out)
        if m:
            out = out[:m.start()] + repl + out[m.end():]
    return out


def _check_applied_set(edits: list[tuple[dict[str, Any], dict[str, Any]]], body: str,
                       report: dict[str, Any]) -> dict[str, Any]:
    """수정안 전부를 함께 반영한 계약에서 보호 표지가 줄었으면 원인 수정안의 자동 적용을 보류한다."""
    before = _inventory(body)
    after = _inventory(_apply(body, edits))
    lost = {k: before[k] - after[k] for k in before if after.get(k, 0) < before[k]}
    blamed: list[str] = []
    for name in lost:
        rx = dict(_PROTECTION_MARKERS)[name]
        for cr, ri in edits:
            if ri.get("held") or _is_new(ri):
                continue
            t = str(ri.get("target_text") or "")
            r = str(ri.get("replacement_text") or ri.get("final_clause_text") or "")
            if len(re.findall(rx, t)) > len(re.findall(rx, r)):
                _hold(cr, ri, f"수정안을 모두 반영하면 계약 전체에서 기존 보호({name})가 줄어듦 — 보완 문장으로 넣을지 담당자가 확인해야 함", report)
                blamed.append(str(cr.get("clause_id") or ""))
    flipped: list[str] = []
    for cr, ri in edits:
        if ri.get("held") or _is_new(ri):
            continue
        t = str(ri.get("target_text") or "")
        r = str(ri.get("replacement_text") or ri.get("final_clause_text") or "")
        st, sr = _RX_SUBJECT.findall(t), _RX_SUBJECT.findall(r)
        # 같은 문장인데 의무 주체 순서가 바뀌었다 — 책임 방향이 뒤집혔을 수 있다.
        if st and sr and len(st) == len(sr) and st != sr and sorted(st) == sorted(sr):
            _hold(cr, ri, "교체 문구에서 의무 주체가 바뀜(" + "→".join(st[:2]) + " ⇒ " + "→".join(sr[:2]) + ") — 책임 방향을 담당자가 확인해야 함", report)
            flipped.append(str(cr.get("clause_id") or ""))
    final_after = _inventory(_apply(body, edits))
    return {
        "edits_applied_together": sum(1 for _, ri in edits if not ri.get("held")),
        "before": before, "after": final_after,
        "lost_before_hold": lost, "held_for_protection_loss": blamed, "held_for_direction_change": flipped,
        "preserved": all(final_after.get(k, 0) >= v for k, v in before.items()),
    }


def _hold(cr: dict[str, Any], ri: dict[str, Any], reason: str, report: dict[str, Any]) -> None:
    ri["held"] = True
    ri["hold_reason"] = (str(ri.get("hold_reason") or "") + " / " if ri.get("hold_reason") else "") + reason
    cr["rewrite_held"] = True
    cr["rewrite_hold_reason"] = ri["hold_reason"]
    report["held"].append({"clause_id": str(cr.get("clause_id") or ""),
                           "display_path": str(cr.get("display_path") or ""), "reason": reason})


def _sync_practical_position(cr: dict[str, Any], ri: dict[str, Any]) -> None:
    pp = cr.get("practical_position")
    if not isinstance(pp, dict):
        return
    pp["location"] = str(ri.get("edit_location") or pp.get("location") or "")
    if _is_new(ri):
        pp["method"], pp["method_label"] = "insert", "신설"
    else:
        pp["method"], pp["method_label"] = "replace_text", "문구 교체"
    pp["text"] = str(ri.get("final_clause_text") or ri.get("replacement_text") or pp.get("text") or "")


def check_revision_set(
    clause_results: list[dict[str, Any]],
    *,
    clause_index: Any,
    contract_text: str,
) -> dict[str, Any]:
    """제자리에서 위치·번호를 정리하고, 검증 실패 항목은 자동 적용을 보류한다."""
    report: dict[str, Any] = {"relocated": [], "renumbered": [], "held": [], "reference_errors": [],
                              "status": "", "detail": ""}
    articles = set((getattr(clause_index, "articles", None) or {}).keys())
    if not articles or getattr(clause_index, "structure_uncertain", False):
        report["status"] = "SKIPPED_STRUCTURE_UNCERTAIN"
        return report
    last_article = max(int(a) for a in articles if a.isdigit())
    body = str(contract_text or "")

    edits = [(cr, cr["redline_instruction"]) for cr in clause_results
             if _live(cr) and isinstance(cr.get("redline_instruction"), dict)
             and str(cr["redline_instruction"].get("replacement_text") or cr["redline_instruction"].get("final_clause_text") or "").strip()]

    # 1. 위치가 이미 특정된 신설은 그대로 두고(규칙이 정한 "제2조(약정 기간) 제3항 뒤에 제4항 신설",
    #    "제5조 뒤에 제5조의2 신설" 등), 기본값 위치("마지막 조 뒤 신설"·"위치 확인 필요"·"계약 말미")만
    #    다시 정한다 — 실재 조를 보완하는 문장은 그 조의 새 항으로, 나머지는 겹치지 않는 새 조 번호로.
    from runtime.review.redline_instruction import paragraph_marker

    def _is_fallback(loc: str) -> bool:
        loc = str(loc or "")
        if not loc or "위치 확인" in loc or "말미" in loc or "계약 전반" in loc or "신설 조항 추가" in loc:
            return True
        m = _RX_NEW_ART_AFTER.match(loc)
        return bool(m and int(m.group(2)) == last_article + 1 and not m.group(3))

    used_paras: dict[str, set[int]] = {}
    used_articles: set[str] = set()
    fixed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    fallback: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for cr, ri in edits:
        if not _is_new(ri):
            continue
        loc = str(ri.get("edit_location") or "")
        if _is_fallback(loc):
            fallback.append((cr, ri))
            continue
        mp = _RX_PARA_INSERT.search(loc)
        ma = _RX_NEW_ART_AFTER.match(loc)
        if mp:
            art, num = mp.group(1), int(mp.group(3))
            if num in used_paras.setdefault(art, set()):
                fallback.append((cr, ri))  # 같은 자리에 둘 — 아래에서 다음 항으로 민다
                continue
            used_paras[art].add(num)
            ri["new_paragraph"] = f"{art}-{num}"
            text_ = str(ri.get("final_clause_text") or ri.get("replacement_text") or "").strip()
            if text_ and not re.match(r"^[①-⑳]", text_):
                ri["final_clause_text"] = f"{paragraph_marker(num)} {text_}"
        elif ma:
            key = ma.group(2) + (f"의{ma.group(3)}" if ma.group(3) else "")
            if key in used_articles:
                fallback.append((cr, ri))
                continue
            used_articles.add(key)
            ri["new_article"] = key
        fixed.append((cr, ri))

    new_articles: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for cr, ri in fallback:
        anchor = str(cr.get("article_number") or "").strip()
        paras = _paragraphs_of(clause_index, anchor) if anchor in articles else []
        if paras:
            base = max(int(p) for p in paras if p.isdigit())
            taken = used_paras.setdefault(anchor, set())
            n = base + 1
            while n in taken:
                n += 1
            taken.add(n)
            was = str(ri.get("edit_location") or "")
            ri["edit_location"] = f"제{anchor}조 제{n - 1}항 뒤에 제{n}항 신설"
            ri["edit_type"] = EDIT_INSERT_PARAGRAPH
            ri["new_paragraph"] = f"{anchor}-{n}"
            text_ = re.sub(r"^[①-⑳]\s*", "", str(ri.get("final_clause_text") or ri.get("replacement_text") or "").strip())
            if text_:
                ri["final_clause_text"] = f"{paragraph_marker(n)} {text_}"
            report["relocated"].append({"clause_id": str(cr.get("clause_id") or ""), "from": was,
                                        "to": ri["edit_location"]})
            _sync_practical_position(cr, ri)
            continue
        new_articles.append((cr, ri))

    # 2. 기본값 위치의 조 신설 — 이미 쓰인 번호를 피해 차례로
    created: set[str] = {k for k in used_articles if k.isdigit()}
    nxt = last_article + 1
    for cr, ri in new_articles:
        while str(nxt) in created:
            nxt += 1
        num = str(nxt)
        was = str(ri.get("edit_location") or "")
        ri["edit_location"] = f"제{nxt - 1}조 뒤에 제{num}조 신설"
        ri["edit_type"] = EDIT_NEW_CLAUSE
        ri["new_article"] = num
        created.add(num)
        if was != ri["edit_location"]:
            report["renumbered"].append({"clause_id": str(cr.get("clause_id") or ""), "from": was,
                                         "to": ri["edit_location"]})
        _sync_practical_position(cr, ri)
    created |= {k for k in used_articles}

    # 3. 교체 — 위치·대상·기존 보호
    for cr, ri in edits:
        if _is_new(ri):
            continue
        target = str(ri.get("target_text") or "")
        repl = str(ri.get("replacement_text") or ri.get("final_clause_text") or "")
        if target and _norm(target) not in _norm(body):
            _hold(cr, ri, "교체 대상 문구가 계약 원문에서 확인되지 않음 — 수정 위치를 담당자가 확정해야 함", report)
            continue
        if _RX_INSTRUCTION.search(repl):
            _hold(cr, ri, "문안에 수정 지시문(\"다음과 같이 수정한다\" 등)이 섞여 있음 — 계약 문장만 남겨 담당자가 확정해야 함", report)
            continue
        lost = _protective_loss(target, repl)
        kept_ratio = _retention(target, repl)
        if lost and kept_ratio < 0.6:
            _hold(cr, ri, "교체하면 기존 보호 문구(" + "·".join(lost[:5]) + ")가 사라짐 — 보호 축소 여부를 담당자가 확인해야 함", report)
        elif len(_norm(target)) >= 40 and kept_ratio < 0.35:
            # 보호 낱말 목록에 없는 권리 문언(예: 마케팅 라이선스의 범위·재편집 권한)도 통째로 지워질 수 있다 —
            # 실측(2026-10-21): 이용 범위 한 줄을 보완하려던 문안이 라이선스 호 전체를 대체했다.
            _hold(cr, ri, "교체 문구가 기존 문언 대부분을 지움 — 기존 문언을 두고 보완 문장으로 넣을지 담당자가 확인해야 함", report)
        _sync_practical_position(cr, ri)

    # 3-1. 같은 원문(또는 그 일부)을 두 수정안이 동시에 교체 — 나중 것이 앞의 수정을 덮는다. 등급이 낮은 쪽을 보류한다.
    replaces = [(cr, ri) for cr, ri in edits if not _is_new(ri) and not ri.get("held")
                and str(ri.get("target_text") or "").strip()]
    rank = {"HIGH": 2, "MEDIUM": 1}
    for i, (cr_a, ri_a) in enumerate(replaces):
        for cr_b, ri_b in replaces[i + 1:]:
            ta, tb = _norm(ri_a.get("target_text")), _norm(ri_b.get("target_text"))
            if not (ta in tb or tb in ta) or ri_a.get("held") or ri_b.get("held"):
                continue
            loser_cr, loser_ri = (cr_b, ri_b) if rank.get(str(cr_a.get("risk_tier")).upper(), 0) >= rank.get(
                str(cr_b.get("risk_tier")).upper(), 0) else (cr_a, ri_a)
            winner = cr_a if loser_cr is cr_b else cr_b
            _hold(loser_cr, loser_ri, f"같은 원문을 {winner.get('display_path') or winner.get('clause_id')} 수정안이 이미 교체함 — "
                  "두 수정안을 합칠지 담당자가 확인해야 함", report)

    # 4. 반영 후 참조 — 신설 조·항을 포함한 실재 구조로 본다
    for cr, ri in edits:
        repl = str(ri.get("replacement_text") or ri.get("final_clause_text") or "")
        home = ""
        if ri.get("new_paragraph"):
            home = str(ri["new_paragraph"]).split("-")[0]
        elif not ri.get("new_article"):
            home = str(cr.get("article_number") or "")
        errors: list[str] = []
        for m in _RX_ART_PARA.finditer(repl):
            if _statute_ref(repl, m.start()):
                continue
            a, p = m.group(1), m.group(2)
            if a in created:
                continue
            if a not in articles:
                errors.append(f"없는 조 참조: 제{a}조")
            elif _paragraphs_of(clause_index, a) and p not in _paragraphs_of(clause_index, a) \
                    and f"{a}-{p}" not in {str(x.get('new_paragraph')) for _, x in edits}:
                errors.append(f"없는 항 참조: 제{a}조 제{p}항")
        for m in _RX_ART.finditer(repl):
            if _statute_ref(repl, m.start()):
                continue
            a = m.group(1)
            if a not in articles and a not in created:
                errors.append(f"없는 조 참조: 제{a}조")
        stripped = _RX_ART_PARA.sub("", repl)
        for m in _RX_BARE_PARA.finditer(stripped):
            p = m.group(1)
            if not home:
                errors.append(f"참조 불명확: 조 없이 '제{p}항' (신설 조 안에서 어느 조의 항인지 알 수 없음)")
            elif _paragraphs_of(clause_index, home) and p not in _paragraphs_of(clause_index, home):
                errors.append(f"없는 항 참조: 제{home}조 제{p}항")
        if errors:
            errors = list(dict.fromkeys(errors))
            report["reference_errors"].append({"clause_id": str(cr.get("clause_id") or ""), "errors": errors})
            _hold(cr, ri, "반영 후 참조 오류 — " + "; ".join(errors[:3]), report)

    # 5. 전체 반영 — 남은 수정안을 **모두 함께** 계약 원문에 넣은 뒤 기존 보호가 줄었는지, 의무 주체가 바뀌었는지 본다
    #    (2026-10-30 천안 임대차: 제14조 특약을 짧은 문장으로 갈아 끼우면 상계·대위변제·연대보증·주차장 승인이 한꺼번에 사라진다).
    report["protections_checked"] = _check_applied_set(edits, body, report)

    if report["held"]:
        report["status"] = "REVISION_SET_HELD"
        report["detail"] = (f"수정안 {len(report['held'])}건은 함께 반영했을 때 위치·참조·기존 보호를 확인하지 못해 "
                            "자동 적용을 보류했습니다(지적은 유지).")
    return report
