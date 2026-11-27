"""변경 묶음(change set) — 화면·검토의견서·변경추적본·클린본이 함께 쓰는 하나의 구조화 데이터.

2026-11-02 지시 4항: 조항 ID, 원문, 삭제·추가 범위, 수정 후 문구, 위험등급, 수정이유를 한 곳에서 관리하고, 화면용
문구와 다운로드용 문구를 따로 만들지 않는다.

만드는 순서
  1. docx_redline 이 수정안을 원본(또는 PDF 검증 변환본) DOCX 에 실제 w:ins/w:del 로 넣고, 넣은 결과를 **그 파일에서 다시 읽어**
     조항 범위별 조각(segments: 유지/삭제/추가), 수정 전·후 전문, 메모 문구를 보고 행에 남긴다.
  2. 여기서 그 보고 행을 조항 카드로 묶고, 같은 finding 의 위험등급·조치 구분·왜 고치는지·사업팀 할 일을 붙인다.
  3. 수정하지 않는 확인사항(사실 확인·현행 유지)은 따로 모은다 — 변경하지 않았는데 변경된 것처럼 보이지 않게.
화면은 meta.change_set 을 그대로 그리고, 검토의견서는 같은 segments 로 변경 표시를 만든다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.docx_redline import action_class

RISK_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
ACTION_RANK = {"필수 수정": 0, "협상 권고": 1, "사실 확인": 2, "현행 유지": 3}
DRAFT_MARK = "협상 초안 · 서명 전 확정 필요"
_RX_BLANK = re.compile(r"\[\s*●\s*\]|\[\s*_+\s*\]|\[\s{2,}\]")


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _one(v: Any, limit: int = 300) -> str:
    t = " ".join(_s(v).split())
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " …"


def issue_key(f: dict[str, Any]) -> str:
    """쟁점 키 — 조항 지목 요청 검토는 요청 번호, 그 밖의 지적은 finding id."""
    ri = f.get("request_index")
    if ri not in (None, "") and str(f.get("finding_id") or "").startswith("rq"):
        return f"rq:{ri}"
    return f"f:{f.get('finding_id')}"


def _live(cr: dict[str, Any]) -> bool:
    return isinstance(cr, dict) and not cr.get("dedup_suppressed")


def _todo(cr: dict[str, Any]) -> list[str]:
    """사업팀이 할 일 — 결정·확인·미확정 값. 없으면 '수정안을 상대방에 제안'."""
    out: list[str] = []
    if _s(cr.get("business_todo")).strip():
        out.append(_one(cr.get("business_todo"), 200))
    for x in cr.get("required_actions") or []:
        x = _s(x).strip()
        if x.startswith("사업부 결정:"):
            out.append(x.replace("사업부 결정:", "결정:").strip())
    for c in cr.get("brief_checks") or []:
        if isinstance(c, dict) and _s(c.get("what")).strip():
            who = _s(c.get("who")).strip()
            out.append(f"확인: {_one(c.get('what'), 160)}" + (f" ({who})" if who else ""))
    und = [_s(u).split(" — ")[0].strip() for u in cr.get("undecided_terms") or [] if _s(u).strip()]
    if und:
        out.append("값 확정: " + ", ".join(dict.fromkeys(und)) + " — 서명 전 상대방과 합의")
    return list(dict.fromkeys(out))


def build_change_set(
    *,
    clause_results: list[dict[str, Any]],
    report: list[dict[str, Any]] | None,
    source: dict[str, Any] | None = None,
    verdict: str = "",
    request_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_id = {_s(cr.get("clause_id")): cr for cr in clause_results or [] if isinstance(cr, dict)}
    cards: dict[Any, dict[str, Any]] = {}
    held: list[dict[str, Any]] = []
    reported: set[str] = set()
    for r in report or []:
        cid = _s(r.get("clause_id"))
        reported.add(cid)
        cr = by_id.get(cid) or {}
        risk = _s(cr.get("risk_tier")).upper() or "MEDIUM"
        finding = {
            "finding_id": cid,
            "path": _s(r.get("path") or cr.get("display_path")),
            "issue_title": _one(cr.get("issue_title") or cr.get("clause_title"), 80),
            "risk": risk,
            "action": action_class(cr),
            "why": _one(cr.get("brief_risk") or cr.get("our_company_risk") or cr.get("rewrite_reason"), 360),
            "change": _one(cr.get("brief_action") or cr.get("rewrite_reason"), 360),
            "todo": _todo(cr) or ["수정안을 상대방에 제안하고 회신을 받는다."],
            "undecided": [_s(u) for u in cr.get("undecided_terms") or [] if _s(u).strip()],
            "existing_protection": _one(cr.get("existing_protection_note"), 300),
            "legal_limits": _one(cr.get("legal_limits"), 300),
            "request_index": cr.get("request_index"),
            "comment_id": r.get("comment_id"),
            "comment_text": _s(r.get("comment_text")),
            # 자기수정 뒤에도 남은 구조 문제(포괄 면책 미검토 등) — 숨기지 않고 '법무 추가 검토' 로 보인다.
            "gaps": [_s(g) for g in cr.get("measure_gaps") or [] if _s(g).strip()],
        }
        if r.get("status") != "applied" or r.get("change_group") is None:
            held.append({**finding, "status": _s(r.get("status")), "reason": _s(r.get("reason")),
                         "original_text": _s(cr.get("original_text")),
                         "proposed_text": _s((cr.get("redline_instruction") or {}).get("final_clause_text")
                                             or cr.get("suggested_rewrite"))})
            continue
        g = r.get("change_group")
        card = cards.setdefault(g, {
            "id": f"C{g}", "paths": [], "clause_title": _s(cr.get("clause_title")),
            "segments": r.get("segments") or [], "before": _s(r.get("before")), "after": _s(r.get("after")),
            "para_range": r.get("para_range"), "findings": [],
        })
        if finding["path"] and finding["path"] not in card["paths"]:
            card["paths"].append(finding["path"])
        card["findings"].append(finding)

    out_cards: list[dict[str, Any]] = []
    for card in cards.values():
        fs = sorted(card["findings"], key=lambda f: (RISK_RANK.get(f["risk"], 3), ACTION_RANK.get(f["action"], 9)))
        card["findings"] = fs
        card["risk"] = fs[0]["risk"]
        card["action"] = fs[0]["action"]
        card["blanks"] = len(_RX_BLANK.findall("".join(t for op, t in card["segments"] if op == "+")))
        card["undecided"] = list(dict.fromkeys(u for f in fs for u in f["undecided"]))
        out_cards.append(card)

    def _path_key(c: dict[str, Any]) -> tuple[int, ...]:
        from runtime.review.clause_label import clause_path_key
        k = clause_path_key(c["paths"][0] if c["paths"] else "") or ()
        return tuple(int(x) if x.isdigit() else 999 for x in k) or (999,)

    out_cards.sort(key=lambda c: (RISK_RANK.get(c["risk"], 3), ACTION_RANK.get(c["action"], 9), _path_key(c)))

    # 수정하지 않는 확인사항 — 고칠 문구가 없는 살아 있는 지적(사실 확인·현행 유지·사업부 결정만).
    confirmations: list[dict[str, Any]] = []
    for cr in clause_results or []:
        if not _live(cr) or _s(cr.get("clause_id")) in reported:
            continue
        if cr.get("has_rewrite_change") and not cr.get("keep_as_is"):
            continue   # 수정안이 있는데 변경추적본에 넣지 않은 LOW 참고 문안 — 아래 low_unapplied 로
        if not (cr.get("is_requested_clause_review") or cr.get("keep_as_is") or cr.get("action_only")):
            continue
        risk = _s(cr.get("risk_tier")).upper() or "LOW"
        confirmations.append({
            "finding_id": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")),
            "issue_title": _one(cr.get("issue_title") or cr.get("clause_title"), 80),
            "risk": risk, "action": "현행 유지" if cr.get("keep_as_is") else action_class(cr),
            "why": _one(cr.get("brief_risk") or cr.get("our_company_risk") or cr.get("problem"), 360),
            "todo": _todo(cr) or [_one(cr.get("brief_action"), 200) or "현행 문구 유지"],
            "existing_protection": _one(cr.get("existing_protection_note"), 300),
            "request_index": cr.get("request_index"),
        })
    confirmations.sort(key=lambda c: (RISK_RANK.get(c["risk"], 3), ACTION_RANK.get(c["action"], 9)))

    # 건수는 '쟁점' 단위 — 요청 하나가 여러 조항을 고쳐도(9.9 세 문장, 13.3 신설 + 4.1 로열티 존속) 한 건으로 센다.
    # 수정 건수로 세면 같은 쟁점이 HIGH 3건으로 부풀고 검토의견서 쟁점 수와도 달라졌다(2026-11-03). 등급은 그 쟁점의 최고 등급.
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    issue_risk: dict[str, str] = {}
    for f in [f for c in out_cards for f in c["findings"]] + held + [c for c in confirmations if c["action"] != "현행 유지"]:
        k = issue_key(f)
        if f["risk"] in counts and RISK_RANK.get(f["risk"], 3) < RISK_RANK.get(issue_risk.get(k, ""), 3):
            issue_risk[k] = f["risk"]
    for r_ in issue_risk.values():
        counts[r_] += 1
    undecided_total = sum(len(c["undecided"]) for c in out_cards) + sum(len(h["undecided"]) for h in held)
    blanks_total = sum(c["blanks"] for c in out_cards)
    draft = bool(undecided_total or blanks_total)
    src = source or {}
    warnings: list[str] = []
    if held:
        warnings.append(f"자동 적용 보류 {len(held)}건 — 원문에서 위치를 확정하지 못해 변경추적본·클린본에는 현재 문구가 남아 있습니다: "
                        + "; ".join(f"{h['path']}({h['reason']})" for h in held))
    ver = src.get("verification") if isinstance(src.get("verification"), dict) else {}
    if ver and (ver.get("missing") or ver.get("duplicated")):
        warnings.append("PDF 변환본 대조 문제 — 변환본에서 확인하지 못한 조항: " + ", ".join(ver.get("missing") or [])
                        + ("; 중복: " + ", ".join(ver.get("duplicated") or []) if ver.get("duplicated") else ""))
    gap_n = sum(len(f.get("gaps") or []) for c in out_cards for f in c["findings"])
    if gap_n:
        warnings.append(f"법무 추가 검토 필요 {gap_n}건 — 수정 문구가 설명한 조치·관련 조항 정합성을 아직 다 담지 못했습니다(카드의 ⚠ 표시).")
    if draft:
        warnings.append(f"{DRAFT_MARK} — 합의되지 않은 값·빈칸 {max(undecided_total, blanks_total)}건이 수정 문구에 남아 있습니다.")
    return {
        "version": 1,
        "verdict": verdict,
        "counts": counts,
        "cards": out_cards,
        "held": held,
        "confirmations": confirmations,
        "requests": [
            {"index": r.get("request_index"), "request": _s(r.get("normalized_issue") or r.get("original_user_text")),
             "status": _s(r.get("request_status") or ""), "answer": _one(r.get("direct_answer"), 400),
             "paths": list(r.get("relevant_clause_paths") or []), "finding_ids": list(r.get("matched_finding_ids") or [])}
            for r in request_rows or [] if isinstance(r, dict) and r.get("source") == "requested_clause_review"
        ],
        "draft": draft,
        "draft_mark": DRAFT_MARK if draft else "",
        "undecided_total": undecided_total,
        "source": {"converted": bool(src.get("converted")), "kind": _s(src.get("kind")), "notice": _s(src.get("notice")),
                   "verification": ver},
        "warnings": warnings,
    }


__all__ = ["DRAFT_MARK", "build_change_set"]
