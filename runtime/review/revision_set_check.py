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
    return (isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM"))


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
            text_ = str(ri.get("final_clause_text") or ri.get("replacement_text") or "").strip()
            if text_ and not re.match(r"^[①-⑳]", text_):
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
        lost = _protective_loss(target, repl)
        if lost and _retention(target, repl) < 0.6:
            _hold(cr, ri, "교체하면 기존 보호 문구(" + "·".join(lost[:5]) + ")가 사라짐 — 보호 축소 여부를 담당자가 확인해야 함", report)
        _sync_practical_position(cr, ri)

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

    if report["held"]:
        report["status"] = "REVISION_SET_HELD"
        report["detail"] = (f"수정안 {len(report['held'])}건은 함께 반영했을 때 위치·참조·기존 보호를 확인하지 못해 "
                            "자동 적용을 보류했습니다(지적은 유지).")
    return report
