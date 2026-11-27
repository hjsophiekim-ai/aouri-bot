"""생성된 Word 수정본 재검사 — 변경을 수락한 문구를 다시 읽어 검사하고, 실패하면 수정안을 고쳐 다시 만든다 (2026-11-09).

검사(변경 수락본 기준, 원문에 이미 있던 것은 문제로 삼지 않는다):
  1. 조 번호 중복("제6조" 머리글 두 번), 항 번호 중복(같은 조 안 "6.1" 두 번, ① 두 번)
  2. 문장 중복(원문에 없던 같은 문장 두 번)
  3. 잘못된 참조(존재하지 않는 조·항을 가리키는 새 문구)
  4. 검토 메모·지침의 본문 삽입(당사자 없는 지시문, '예:', '요구한다', 선택지, 내부 표지)
  5. 검토서·메모·수정본 일치 — 출력에 실리는 수정 문구가 수락본에 그대로 있는가

실패 → 원인 수정안을 찾아 문구를 고치거나(머리글·지침 문장 제거) 보류 → Word 재생성 → 재검사(최대 3회).
남으면 미해결로 기록하고, 검증을 통과하지 못한 산출물에는 최종본·서명 가능 표시를 붙이지 않는다.

2026-11-12 보강:
  6. 대조 대상은 검토서가 '수정 반영' 으로 보여 주는 수정안 전부다 — Word 생성기가 집어 든 것(live_edits)만이 아니다. 검토서에는
     있는데 Word 생성 대상에서 빠진 수정안(편집 지시문 형태·변경 표시 누락 등)도 '검토서 문구가 수정본에 없음' 으로 잡는다.
  7. 반영 누락은 먼저 수정안을 적용 가능한 형태로 바로잡고(편집 지시 → 계약 문장) 다시 만든다. 다시 만든 뒤에도 없으면
     '제안만 있음·파일 미반영' 으로 표시하고 최종본 출력을 막는다(final_blocked).
  8. 계약 본문에 들어간 편집 지시문("다음 문단을 추가한다")은 문제로 잡고 메모로 옮긴다.
  9. 시스템이 붙인 표지(검증 미통과 초안·협상 초안 안내 단락)는 계약 본문이 아니다 — 검사 대상에서 뺀다(자기 경고를 계약 오류로
     다시 세지 않는다).
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review import deal_flow as _df

_RX_ART_HEAD = re.compile(r"^\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?(?=[\s(（]|$)")
NOT_REFLECTED = "제안만 있음·파일 미반영"
#: 시스템이 문서 첫머리에 붙이는 안내 단락 — 계약 본문이 아니다
_RX_SYSTEM_BANNER = re.compile(r"^\s*\[(?:검증\s*미통과\s*초안|협상\s*초안[^\]]*)\]|^\s*(?:UNVERIFIED DRAFT|DRAFT FOR NEGOTIATION)")
_RX_LEAD_NO = re.compile(r"^\s*(?:\(\d+\)|[①-⑳]|\d+(?:\.\d+)*\.?(?=\s))\s*")
_RX_SUB = re.compile(r"^\s*(\d+)\.(\d+)\s")
_RX_CIRCLED = re.compile(r"^\s*([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])")
_RX_INTERNAL = re.compile(r"\[(?:추가\s*권고|HIGH|MEDIUM|LOW|필수수정|권장수정|검토\s*의견|수정\s*이유)[^\]]*\]|수정\s*이유\s*[:：]|"
                          r"우리\s*회사\s*위험\s*[:：]|아우리봇|검증\s*미통과")


def _s(v: Any) -> str:
    return str(v or "").strip()


def _ws(v: Any) -> str:
    return " ".join(str(v or "").split())


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.。])\s+", text or "") if len(x.strip()) >= 15]


def _structure(paras: list[str]) -> tuple[dict[str, int], dict[tuple[str, str], int], set[str]]:
    arts: dict[str, int] = {}
    subs: dict[tuple[str, str], int] = {}
    cur = ""
    for p in paras:
        m = _RX_ART_HEAD.match(p)
        if m:
            cur = m.group(1) + (f"의{m.group(2)}" if m.group(2) else "")
            arts[cur] = arts.get(cur, 0) + 1
            continue
        ms = _RX_SUB.match(p)
        if ms:
            k = (ms.group(1), f"{ms.group(1)}.{ms.group(2)}")
            subs[k] = subs.get(k, 0) + 1
            continue
        mc = _RX_CIRCLED.match(p)
        if mc and cur:
            k = (cur, mc.group(1))
            subs[k] = subs.get(k, 0) + 1
    subnos = {k[1] for k in subs}
    return arts, subs, subnos


def is_system_banner(p: str) -> bool:
    return bool(_RX_SYSTEM_BANNER.match(p or ""))


def _proposal_text(cr: dict[str, Any]) -> str:
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
    return _s(ri.get("final_clause_text") or ri.get("replacement_text") or cr.get("suggested_rewrite"))


def shown_edits(review_result: dict[str, Any]) -> list[dict[str, Any]]:
    """검토서·화면이 수정 문구로 보여 주는 수정안 — Word 적용 대상(live_edits)에 더해, 최종 지적 목록(HIGH/MEDIUM)에 수정 문구가
    실린 것. 보류·KEEP·중복 숨김·조치 전용은 뺀다."""
    from runtime.review.verification_gate import live_edits

    crs = [cr for cr in review_result.get("clause_results") or [] if isinstance(cr, dict)]
    out = list(live_edits(crs))
    meta = review_result.get("clause_meta") if isinstance(review_result.get("clause_meta"), dict) else {}
    ff = meta.get("final_findings") if isinstance(meta.get("final_findings"), dict) else {}
    ids = {_s(d.get("clause_id")) for k in ("high_issues", "medium_issues") for d in ff.get(k) or [] if isinstance(d, dict)}
    ids |= {_s(d.get("finding_id")) for k in ("high_issues", "medium_issues") for d in ff.get(k) or [] if isinstance(d, dict)}
    ids.discard("")
    for cr in crs:
        if cr in out or (_s(cr.get("clause_id")) not in ids and _s((cr.get("redline_instruction") or {}).get("finding_id")) not in ids):
            continue
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        if ri.get("held") or cr.get("keep_as_is") or cr.get("dedup_suppressed") or cr.get("action_only") or cr.get("verification_removed"):
            continue
        if _s(cr.get("risk_tier")).upper() not in ("HIGH", "MEDIUM") or len(_proposal_text(cr)) < 15:
            continue
        out.append(cr)
    return out


def check_docx(accepted: list[str], original: list[str], *, labels: list[str], live: list[dict[str, Any]],
               shown: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """수락본 단락(accepted)과 원본 단락(original)을 비교해 문제 목록을 만든다."""
    probs: list[dict[str, Any]] = []
    accepted = [p for p in accepted if not is_system_banner(p)]
    original = [p for p in original if not is_system_banner(p)]
    a_arts, a_subs, a_nos = _structure(accepted)
    o_arts, o_subs, _o_nos = _structure(original)
    for art, n in a_arts.items():
        if n > 1 and n > o_arts.get(art, 0):
            probs.append({"code": "DUP_ARTICLE", "where": f"제{art}조", "detail": f"제{art}조 머리글 {n}회"})
    for (art, no), n in a_subs.items():
        if n > 1 and n > o_subs.get((art, no), 0):
            probs.append({"code": "DUP_SUBNO", "where": f"제{art}조", "detail": f"제{art}조 안 '{no}' {n}회", "token": no})
    orig_set = {_ws(p) for p in original}
    new_paras = [p for p in accepted if _ws(p) and _ws(p) not in orig_set]
    o_sent: dict[str, int] = {}
    for p in original:
        for x in _sentences(p):
            o_sent[_ws(x)] = o_sent.get(_ws(x), 0) + 1
    a_sent: dict[str, int] = {}
    for p in accepted:
        for x in _sentences(p):
            a_sent[_ws(x)] = a_sent.get(_ws(x), 0) + 1
    for x, n in a_sent.items():
        if n > 1 and n > o_sent.get(x, 0):
            probs.append({"code": "DUP_SENTENCE", "where": "", "detail": f"같은 문장 {n}회: {x[:60]}", "token": x})
    existing_arts = set(a_arts)
    for p in new_paras:
        for m in re.finditer(r"제\s*(\d+)\s*조", p):
            if re.search(r"(?:법|법률|시행령|시행규칙|령|규칙|규정|협약|조약)\s*$", p[:m.start()]):
                continue   # 법령 조문 인용("개인정보 보호법 제29조")은 계약 조 참조가 아니다
            if m.group(1) not in existing_arts and existing_arts:
                probs.append({"code": "BAD_REF", "where": "", "detail": f"없는 조 참조 '제{m.group(1)}조': {p[:60]}", "token": p})
        for m in re.finditer(r"(?<![\d.])(\d+)\.(\d+)(?=에|의|에\s*따른|\s*또는|\s*및|\s*이하|\)|,)", p):
            no = f"{m.group(1)}.{m.group(2)}"
            if no not in a_nos and a_nos:
                probs.append({"code": "BAD_REF", "where": "", "detail": f"없는 항 참조 '{no}': {p[:60]}", "token": p})
        body = _RX_SUB.sub("", p)
        for g in _df.guidance_sentences(body, labels):
            if _ws(g) not in " ".join(orig_set):
                probs.append({"code": "GUIDANCE_IN_BODY", "where": "", "detail": f"검토 지침 문장: {g[:80]}", "token": g})
        if _RX_INTERNAL.search(p):
            probs.append({"code": "MEMO_IN_BODY", "where": "", "detail": f"검토 메모·내부 표지: {p[:80]}", "token": p})
        if _df.RX_EDIT_INSTRUCTION_ANY.search(p) and not _df.RX_EDIT_INSTRUCTION_ANY.search(" ".join(orig_set)):
            probs.append({"code": "EDIT_INSTRUCTION_IN_BODY", "where": "", "detail": f"편집 지시문이 계약 본문에 들어감: {p[:80]}", "token": p})
    from runtime.review.docx_redline import _strip_display_markers

    # 단락 머리 번호((1)·①·1.)는 Word 자동 번호로 들어가 본문 글자에 없을 수 있다 — 번호를 떼고 대조한다
    flat_acc = _ws(" ".join(_RX_LEAD_NO.sub("", p) for p in accepted))
    seen: set[int] = set()
    for cr in list(live) + list(shown or []):
        if id(cr) in seen:
            continue
        seen.add(id(cr))
        rep = _strip_display_markers(_proposal_text(cr))
        for line in [ln for ln in rep.split("\n") if len(ln.strip()) >= 15]:
            if _ws(_RX_LEAD_NO.sub("", line)) not in flat_acc:
                probs.append({"code": "NOT_IN_DOCX", "where": _s(cr.get("display_path")),
                              "detail": f"검토서 수정 문구가 수정본에 없음: {line[:60]}", "token": line, "owner": _s(cr.get("clause_id"))})
                break
    return probs


def _owner(problem: dict[str, Any], live: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if problem.get("owner"):
        return [cr for cr in live if _s(cr.get("clause_id")) == problem["owner"]]
    tok = _ws(problem.get("token"))
    out = []
    for cr in live:
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        rep = _ws(ri.get("final_clause_text") or ri.get("replacement_text") or cr.get("suggested_rewrite"))
        if tok and (tok in rep or (len(tok) > 30 and tok[:30] in rep)):
            out.append(cr)
        elif problem["code"] in ("DUP_ARTICLE", "DUP_SUBNO") and _s(cr.get("display_path")).split(" ")[0] == problem.get("where"):
            out.append(cr)
    return out


def _repair(problem: dict[str, Any], cr: dict[str, Any], labels: list[str]) -> str:
    """문구를 고칠 수 있으면 고치고 'rewritten', 아니면 보류하고 'held'.
    반영 누락(NOT_IN_DOCX): 1회차는 수정안을 적용 가능한 형태로 바로잡고 'regenerate', 다시 만든 뒤에도 없으면 'not_reflected'."""
    if problem["code"] == "NOT_IN_DOCX":
        cr["_apply_attempts"] = int(cr.get("_apply_attempts") or 0) + 1
        if cr["_apply_attempts"] == 1:
            _df.split_edit_instruction(cr)
            ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
            if not cr.get("has_rewrite_change") and _proposal_text(cr):
                cr["has_rewrite_change"] = True
            if not _s(ri.get("replacement_text")) and _s(cr.get("suggested_rewrite")):
                ri["replacement_text"] = _s(cr["suggested_rewrite"])
            return "regenerate"
        cr["apply_status"] = NOT_REFLECTED
        cr["apply_status_reason"] = f"Word 재생성 후에도 수정본에 없음 — {problem['detail']}"[:300]
        return "not_reflected"
    if problem["code"] == "EDIT_INSTRUCTION_IN_BODY":
        if _df.split_edit_instruction(cr):
            return "rewritten"
    if problem["code"] in ("GUIDANCE_IN_BODY", "MEMO_IN_BODY", "DUP_ARTICLE", "DUP_SUBNO", "DUP_SENTENCE"):
        moved = _df.strip_guidance(cr, labels)
        ri = cr.get("redline_instruction") or {}
        if moved and not ri.get("held"):
            return "rewritten"
        if problem["code"] in ("DUP_SENTENCE", "MEMO_IN_BODY", "GUIDANCE_IN_BODY") and problem.get("token"):
            tok = _s(problem["token"])
            changed = False
            for k in ("replacement_text", "final_clause_text"):
                if tok in _s(ri.get(k)):
                    ri[k] = _s(ri[k]).replace(tok, "", 1).strip()
                    changed = True
            if tok in _s(cr.get("suggested_rewrite")):
                cr["suggested_rewrite"] = _s(cr["suggested_rewrite"]).replace(tok, "", 1).strip()
                changed = True
            if changed and _ws(ri.get("replacement_text") or cr.get("suggested_rewrite")):
                return "rewritten"
    _df._hold(cr, f"Word 수정본 재검사 실패로 수정안 보류 — {problem['detail']}"[:300])
    return "held"


def run(session: dict[str, Any], review_result: dict[str, Any], *, build: Any, max_rounds: int = 3) -> dict[str, Any]:
    """build(session, review_result) → docs(dict with redline/clean). 검사·수리·재생성 기록을 돌려준다."""
    from runtime.review.docx_redline import docx_paragraph_texts
    from runtime.review.source_docx import source_docx_for_session
    from runtime.review.verification_gate import live_edits

    meta = review_result.get("clause_meta") if isinstance(review_result.get("clause_meta"), dict) else {}
    df = meta.get("deal_flow") if isinstance(meta.get("deal_flow"), dict) else {}
    role = df.get("role") or {}
    labels = [x for x in (role.get("our_label"), role.get("counterparty_label")) if x] or ["갑", "을"]
    src = source_docx_for_session({**session, "review_result": review_result})
    if src is None:
        return {"status": "검사 대상 없음", "history": [], "docs": None}
    original = [p for p in docx_paragraph_texts(src.docx_bytes) if p.strip()]
    history: list[dict[str, Any]] = []
    for cr in review_result.get("clause_results") or []:
        if isinstance(cr, dict):
            cr.pop("_apply_attempts", None)
            if cr.get("apply_status") == NOT_REFLECTED:
                cr.pop("apply_status", None)
                cr.pop("apply_status_reason", None)
    docs = build(session, review_result)
    probs: list[dict[str, Any]] = []
    for rnd in range(1, max_rounds + 1):
        if docs is None:
            break
        accepted = [p for p in docx_paragraph_texts(docs["redline"], mode="accept") if p.strip()]
        crs = review_result.get("clause_results") or []
        live = live_edits(crs)
        shown = shown_edits(review_result)
        probs = check_docx(accepted, original, labels=labels, live=live, shown=shown)
        entry: dict[str, Any] = {"round": rnd, "problems": [f"[{p['code']}] {p['detail']}" for p in probs]}
        if not probs:
            history.append(entry)
            break
        actions = []
        for p in probs:
            owners = _owner(p, shown)
            if len(owners) > 1 and p["code"] in ("DUP_ARTICLE", "DUP_SUBNO", "DUP_SENTENCE"):
                # 같은 조의 중복은 흐름·연결 검토가 만든 수정안을 남기고 다른 수정안부터 고친다
                others = [c for c in owners if not c.get("is_deal_flow_revision")]
                owners = others or owners
            for cr in owners:
                if (cr.get("redline_instruction") or {}).get("held"):
                    continue
                act = _repair(p, cr, labels)
                actions.append(f"{_s(cr.get('display_path'))}({_s(cr.get('clause_id'))}): {act} — {p['code']}")
        entry["repairs"] = actions
        history.append(entry)
        if not [a for a in actions if not a.endswith("not_reflected — NOT_IN_DOCX")]:
            break   # 고친 것이 없으면(반영 누락 확정만 남음) 다시 만들어도 같다
        docs = build(session, review_result)   # 수정안을 고친 뒤 Word 를 다시 만든다
    status = "통과" if not probs else "미통과"
    not_reflected = [{"clause_id": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")),
                      "location": _s((cr.get("redline_instruction") or {}).get("edit_location")),
                      "proposal": _proposal_text(cr)[:300], "reason": _s(cr.get("apply_status_reason"))}
                     for cr in review_result.get("clause_results") or [] if isinstance(cr, dict) and cr.get("apply_status") == NOT_REFLECTED]
    return {
        "status": status,
        "history": history,
        "unresolved": [{"category": NOT_REFLECTED if p["code"] == "NOT_IN_DOCX" else "Word 수정본 재검사",
                        "paths": p.get("where", ""), "detail": p["detail"]} for p in probs],
        "not_reflected": not_reflected,
        "final_blocked": bool(not_reflected) or any(p["code"] == "NOT_IN_DOCX" for p in probs),
        "docs": docs,
    }


__all__ = ["NOT_REFLECTED", "check_docx", "is_system_banner", "run", "shown_edits"]
