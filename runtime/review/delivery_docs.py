"""검토 결과 → 변경추적본·클린본·검토의견서. 화면·다운로드가 같은 함수를 쓴다(2026-11-02 지시 3·7항).

변경추적본·클린본은 원본 DOCX(또는 PDF 등을 검증해 만든 DOCX 변환본)에 같은 수정안을 넣어 만든다. 수정안을 실제로 넣었는지
(적용·보류·위치 못 찾음)는 검토 직후 한 번 계산해 meta 에 남기고, 검토의견서가 그 결과를 표시한다 — 화면이 "반영" 이라고
말한 수정안이 Word 파일에는 없는 일이 없게.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from runtime.review.docx_redline import DEFAULT_AUTHOR  # 아우리봇


def change_date(meta: dict[str, Any] | None) -> str:
    """변경 일시 — 검토 시점으로 고정한다(다운로드할 때마다 바뀌지 않게)."""
    d = (meta or {}).get("redline_date") if isinstance(meta, dict) else None
    return str(d or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def build_tracked_docs(
    session: dict[str, Any],
    review_result: dict[str, Any],
    *,
    author: str = DEFAULT_AUTHOR,
    date: str | None = None,
) -> dict[str, Any] | None:
    """{redline, clean, report, source} 또는 기준 문서가 없으면 None."""
    from runtime.review.docx_redline import build_redline_docx
    from runtime.review.source_docx import source_docx_for_session

    src = source_docx_for_session({**session, "review_result": review_result})
    if src is None:
        return None
    clauses = review_result.get("original_clauses") or session.get("original_clauses") or []
    meta = review_result.get("clause_meta") if isinstance(review_result.get("clause_meta"), dict) else {}
    # 같은 버전 검증 — 검증 뒤 수정안이 바뀌었으면 이전 결과를 버리고 다시 검증한 결과로 표지를 정한다(2026-11-03)
    from runtime.review.verification_gate import ensure_current, is_failed

    ensure_current(meta, review_result.get("clause_results") or [], clauses)
    report: list[dict[str, Any]] = []
    redline, clean = build_redline_docx(
        docx_bytes=src.docx_bytes,
        original_clauses=clauses,
        clause_results=review_result.get("clause_results") or [],
        author=author,
        date=date or change_date(meta),
        report=report,
        normalize_whitespace=src.converted,
        document_note=src.notice,
    )
    from runtime.review.change_set import DRAFT_MARK, build_change_set

    cs = build_change_set(clause_results=review_result.get("clause_results") or [], report=report,
                          source={"converted": src.converted, "kind": src.source_kind, "notice": src.notice,
                                  "verification": src.verification},
                          request_rows=(meta or {}).get("user_review_coverage"))
    if cs["draft"]:
        # 클린본은 서명용 계약서라 메모를 지운다 — 그래도 합의되지 않은 값([●])이 남아 있으면 첫머리에 표시한다(지시 2항).
        clean = add_draft_banner(clean, f"[{DRAFT_MARK}] 이 문서에는 아직 합의되지 않은 값([●] 등)이 남아 있습니다. "
                                        "서명 전에 모든 빈칸·미확정 조건을 확정하고 이 문단을 삭제하십시오. "
                                        "/ DRAFT FOR NEGOTIATION — bracketed values ([●]) are not agreed; "
                                        "finalise them and delete this paragraph before signature.")
    vgm = meta.get("verification_gate") if isinstance(meta.get("verification_gate"), dict) else {}
    cs["verification"] = {"status": vgm.get("status", ""), "version": vgm.get("version", ""),
                          "unresolved": list(vgm.get("unresolved") or [])}
    if is_failed(meta):
        # 검증 미통과 초안: 최종본·서명본으로 쓰이지 않게 두 파일 첫머리에 표시한다(지시 6항).
        n = len(vgm.get("unresolved") or [])
        banner = (f"[{UNVERIFIED_MARK}] 이 수정안은 필수 검증을 통과하지 못했습니다(미해결 {n}건 — 검토의견서 1절 참고). "
                  "최종본이 아니며 서명용으로 쓰지 마십시오. / UNVERIFIED DRAFT — not a final or signature version.")
        clean = add_draft_banner(clean, banner)
        redline = add_draft_banner(redline, banner)
        cs["verdict"] = UNVERIFIED_MARK
        cs.setdefault("warnings", []).insert(0, f"{UNVERIFIED_MARK} — 미해결 {n}건: "
                                             + "; ".join(f"[{u.get('category')}] {u.get('paths')}" for u in (vgm.get("unresolved") or [])[:6]))
    blocked = meta.get("final_output_blocked") if isinstance(meta.get("final_output_blocked"), dict) else None
    if blocked:
        cs["final_blocked"] = True
        cs.setdefault("warnings", []).insert(0, "최종본 출력 차단 — 제안만 있음·파일 미반영 "
                                             + ", ".join(_s_(i.get("path") or i.get("location")) for i in blocked.get("items") or []))
    return {"redline": redline, "clean": clean, "report": report, "source": src, "change_set": cs,
            "final_blocked": bool(blocked), "final_blocked_items": list((blocked or {}).get("items") or [])}


def _s_(v: Any) -> str:
    return str(v or "").strip()


UNVERIFIED_MARK = "검증 미통과 초안"


def add_draft_banner(docx_bytes: bytes, text: str) -> bytes:
    """본문 맨 앞에 빨간 굵은 안내 단락을 넣는다(변경추적 없이 — 클린본 전용)."""
    import io
    import zipfile
    from xml.etree import ElementTree as ET

    from runtime.review.docx_redline import W, _pack_docx

    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        contents = {n: z.read(n) for n in z.namelist()}
    root = ET.fromstring(contents["word/document.xml"])
    body = root.find(f"{W}body")
    p = ET.Element(f"{W}p")
    r = ET.SubElement(p, f"{W}r")
    rpr = ET.SubElement(r, f"{W}rPr")
    ET.SubElement(rpr, f"{W}b")
    ET.SubElement(rpr, f"{W}color", {f"{W}val": "C00000"})
    ET.SubElement(rpr, f"{W}highlight", {f"{W}val": "yellow"})
    t = ET.SubElement(r, f"{W}t")
    t.text = text
    body.insert(0, p)
    contents["word/document.xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                                     + ET.tostring(root, encoding="unicode")).encode("utf-8")
    return _pack_docx(contents)


def brief_from_meta(
    *,
    clause_results: list[dict[str, Any]],
    meta: dict[str, Any],
    clauses: list[Any] | None,
    contract_text: str,
    answers: dict[str, Any] | None,
    filename: str | None = None,
    high_issues: list[dict[str, Any]] | None = None,
    medium_issues: list[dict[str, Any]] | None = None,
    user_review_coverage: list[dict[str, Any]] | None = None,
    delivery_remediations: list[dict[str, Any]] | None = None,
):
    from runtime.review.business_brief import build_business_brief
    from runtime.review.verification_gate import ensure_current

    ensure_current(meta, clause_results, clauses)
    ff = meta.get("final_findings") if isinstance(meta.get("final_findings"), dict) else {}
    tracked = meta.get("tracked_source") if isinstance(meta.get("tracked_source"), dict) else {}
    medium = list(medium_issues if medium_issues is not None else (ff.get("medium_issues") or []))
    # 국제계약 체크리스트의 LOW 항목(색상 기준·시험성적서·계좌 변경 검증 등)은 사업팀이 협상에서 함께 요청할 실무 항목이라
    # 전달본에 싣는다 — 화면·다운로드가 같은 목록을 쓰도록 여기서 한 번 더한다(2026-11-27).
    from runtime.review.output_filter import clause_results_to_review_issues

    seen_ids = {str(x.get("clause_id")) for x in medium + list(high_issues or ff.get("high_issues") or []) if isinstance(x, dict)}
    medium += [i.to_dict() for i in clause_results_to_review_issues(
        [c for c in clause_results if isinstance(c, dict) and c.get("is_cross_border_check")
         and str(c.get("risk_tier")) == "LOW" and not c.get("excluded_from_brief")])
        if i.clause_id not in seen_ids]
    return build_business_brief(
        clause_results=clause_results,
        high_issues=high_issues if high_issues is not None else ff.get("high_issues"),
        medium_issues=medium,
        user_review_coverage=user_review_coverage if user_review_coverage is not None else meta.get("user_review_coverage"),
        deal_assessment=meta.get("deal_assessment"),
        revision_set_check=meta.get("revision_set_check") if isinstance(meta.get("revision_set_check"), dict) else None,
        delivery_remediations=delivery_remediations,
        clauses=clauses,
        contract_text=contract_text,
        answers=answers,
        filename=filename,
        apply_report=meta.get("redline_apply_report") if isinstance(meta.get("redline_apply_report"), list) else None,
        overall_recommendation=str(meta.get("overall_recommendation") or ""),
        source_note=str(tracked.get("notice") or ""),
        deal_scenarios=meta.get("deal_scenarios") if isinstance(meta.get("deal_scenarios"), dict) else None,
        verification=meta.get("verification_gate") if isinstance(meta.get("verification_gate"), dict) else None,
        commercial_terms=((meta.get("redline_integrity") or {}).get("commercial_terms")
                          if isinstance(meta.get("redline_integrity"), dict) else None),
    )


def finalize_review_meta(session: dict[str, Any], review_result: dict[str, Any], *, build: Any = None) -> None:
    """검토 직후: 변경추적본을 한 번 만들어 적용 결과를 남기고, 그 결과로 검토의견서(화면)를 다시 만든다.
    build: Word 생성 함수(기본 build_tracked_docs) — 시험에서 반영 누락을 흉내 낼 때만 바꾼다."""
    build = build or build_tracked_docs
    from runtime.review.business_brief import brief_sections

    meta = review_result.get("clause_meta")
    if not isinstance(meta, dict):
        return
    meta.setdefault("redline_date", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        # 생성된 Word 를 변경 수락 상태로 다시 읽어 검사하고(조·항 번호 중복, 문장 중복, 잘못된 참조, 검토 지침·메모의 본문 삽입,
        # 검토서 문구 누락), 실패하면 원인 수정안을 고치거나 보류한 뒤 다시 만들어 재검사한다(2026-11-09). 검토서·메모·수정본은
        # 그 최종 수정안 하나로 만든다.
        from runtime.review.final_docx_check import run as _final_check

        _fc = _final_check(session, review_result, build=build)
        docs = _fc.pop("docs", None)
        meta["final_docx_check"] = _fc
        if any(h.get("repairs") for h in _fc.get("history") or []):
            # 수정안을 고쳤으면 화면·검토의견서용 최종 지적 목록도 다시 만든다
            try:
                from runtime.review.output_filter import build_final_findings as _bff_fc

                _ct = str(((meta.get("canonical_state") or {}).get("contract_type")) or "general")
                meta["final_findings"] = _bff_fc(review_result.get("clause_results") or [], contract_type_code=_ct, include_low=False)
            except Exception as _exc:  # noqa: BLE001
                meta["final_findings_rebuild_error"] = str(_exc)
        # 검토서에 보이는 수정안이 Word 에 재생성 후에도 없으면 최종본 출력을 막는다(2026-11-12) — 클린본 다운로드 거부·표지
        if _fc.get("final_blocked"):
            meta["final_output_blocked"] = {"reason": "제안만 있음·파일 미반영",
                                            "items": list(_fc.get("not_reflected") or [])
                                            or [{"path": u.get("paths"), "reason": u.get("detail")} for u in _fc.get("unresolved") or []
                                                if u.get("category") == "제안만 있음·파일 미반영"]}
        else:
            meta.pop("final_output_blocked", None)
        if (docs is None and _fc.get("status") != "검사 대상 없음") or _fc.get("status") == "미통과":
            # 미통과면 '검증 미통과 초안' 표지를 붙여 다시 만든다(최종본·서명 가능 표시 금지)
            docs = build(session, review_result)
    except Exception as exc:  # noqa: BLE001 - 변경추적본 실패는 기록하고 검토 결과는 그대로 둔다
        meta["redline_apply_error"] = str(exc)
        meta["final_docx_check"] = {"status": "미통과", "error": str(exc),
                                    "unresolved": [{"category": "Word 수정본 재검사", "paths": "", "detail": f"재검사 실행 실패: {exc}"[:200]}]}
        docs = None
    if docs is not None:
        src = docs["source"]
        meta["redline_apply_report"] = docs["report"]
        meta["change_set"] = docs["change_set"]
        meta["tracked_source"] = {"converted": src.converted, "kind": src.source_kind, "notice": src.notice,
                                  "verification": src.verification}
    try:
        brief = brief_from_meta(
            clause_results=review_result.get("clause_results") or [],
            meta=meta,
            clauses=review_result.get("original_clauses") or session.get("original_clauses"),
            contract_text=str(session.get("text") or ""),
            answers=session.get("answers") if isinstance(session.get("answers"), dict) else None,
            filename=str(((session.get("input") or {}).get("filename")) or "") or None,
        )
        meta["business_brief"] = brief.to_dict()
        meta["business_brief_sections"] = [[h, [list(r) for r in rows]] for h, rows in brief_sections(brief)]
        # 검토의견서(DOCX·PDF)의 '우리 역할·거래 흐름 / 해지·위약금 연결 / 개인정보 처리 흐름' 절과 같은 줄을 앱 화면에도 싣는다(2026-11-12)
        # 국제계약은 거래 흐름 분석을 cross_border 레이어가 대신한다 — 전달본(2~3쪽)에 흐름 절을 끼우지 않는다(2026-11-27)
        _flow_sec = [] if (meta.get("cross_border") or {}).get("active") else flow_sections(meta.get("deal_flow"))
        if _flow_sec:
            meta["business_brief_sections"][1:1] = _flow_sec
        meta["business_brief_delivery"] = brief_delivery(brief)
        if isinstance(meta.get("change_set"), dict):
            meta["change_set"]["verdict"] = brief.verdict
    except Exception as exc:  # noqa: BLE001
        meta["business_brief_rebuild_error"] = str(exc)
        brief = None
    try:
        meta["output_consistency"] = output_consistency(meta=meta, clause_results=review_result.get("clause_results") or [],
                                                        brief=brief, docs=docs)
    except Exception as exc:  # noqa: BLE001
        meta["output_consistency"] = {"ok": False, "error": str(exc)}


#: 사업팀 전달본에 나오면 안 되는 도구 상태 문구(2026-11-27) — 법무 내부 분석본·법무 화면에만.
RX_TOOL_STATUS = re.compile(
    r"⚠\s*미해결|제안만 있음·파일 미반영|변경추적본 자동 적용 보류|자동 적용 보류|Word 재생성|변경추적본에 자동으로 넣지 못한"
    r"|체결 전 확인 \d+건 — \d절 참고|법무 추가 확인 중|Traceback|\b[A-Z]\w*Error:|\bException\b|object has no attribute|검증 미통과 초안"
)


def brief_delivery(brief: Any) -> dict[str, Any]:
    """사업팀 전달 가능 여부 — 법무 화면·다운로드 거부 응답에만 쓴다(전달본 본문에는 싣지 않는다)."""
    reasons = list(getattr(brief, "delivery_block_reasons", []) or [])
    return {"blocked": bool(getattr(brief, "delivery_blocked", False)), "reasons": reasons,
            "message": ("사업팀 전달본 보류 — 수정안 일부가 변경추적본에 반영되지 않았거나 필수 검증이 남았습니다. "
                        "법무가 확인·재생성한 뒤 전달하십시오.") if reasons else ""}


def flow_sections(deal_flow: dict[str, Any] | None) -> list[list[Any]]:
    """deal_flow.section_lines(보고서 줄) → 앱 화면 절 [(제목, [[스타일, 문장]])]. 같은 데이터·같은 문장."""
    from runtime.review.deal_flow import section_lines

    out: list[list[Any]] = []
    cur: list[Any] | None = None
    for kind, text, tone in section_lines(deal_flow):
        if kind == "heading":
            cur = [text, []]
            out.append(cur)
            continue
        if cur is None:
            continue
        style = "h" if kind == "bold" and not tone else "k" if kind == "bold" or tone == "high" else "p"
        cur[1].append([style, ("· " + text) if kind == "bullet" else text])
    return [s for s in out if s[1]]


def output_consistency(*, meta: dict[str, Any], clause_results: list[dict[str, Any]], brief: Any, docs: dict[str, Any] | None
                       ) -> dict[str, Any]:
    """앱(meta)·검토의견서(brief)·변경추적본·클린본·메모가 같은 검증 버전·같은 수정안에서 나왔는지(2026-11-03 지시 6항)."""
    from runtime.review.verification_gate import RX_INTERNAL, fingerprint, live_edits

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    vgm = meta.get("verification_gate") if isinstance(meta.get("verification_gate"), dict) else {}
    cur = fingerprint(clause_results)
    add("검증 버전 = 현재 수정안", bool(vgm) and vgm.get("version") == cur, f"검증 {vgm.get('version')} / 현재 {cur}")
    failed = vgm.get("status") == UNVERIFIED_MARK
    if brief is not None:
        bv = brief.verification or {}
        add("검토의견서 검증 상태 = 앱", bv.get("status") == vgm.get("status") and bv.get("version") == vgm.get("version"))
        # 2026-11-27: 검증 미통과는 결론(계약 리스크 판단)을 바꾸지 않고 전달본을 보류한다 — 사업팀에 나가지 않으면 된다
        add("미통과면 전달본 보류", (not failed) or bool(getattr(brief, "delivery_blocked", False)), brief.verdict)
        from runtime.review.business_brief import brief_text

        txt = brief_text(brief)
        leak = sorted(set(m.group(0) for m in RX_INTERNAL.finditer(txt)))
        add("전달본에 내부 표지 없음", not leak, ", ".join(leak[:8]))
        tool = sorted(set(m.group(0) for m in RX_TOOL_STATUS.finditer(txt)))
        add("전달본에 도구 상태 문구 없음", not tool, ", ".join(tool[:8]))
        live_ids = {str(cr.get("clause_id")) for cr in live_edits(clause_results)}
        stale = [it.no for it in brief.cards for src in it.sources if src in {str(cr.get("clause_id")) for cr in clause_results
                                                                                if isinstance(cr, dict) and cr.get("verification_removed")}
                 and any(e.new_text for e in it.edits)]
        add("제거한 수정안이 검토의견서 수정 문구로 남지 않음", not stale, ", ".join(stale))
    if docs is not None:
        rep = docs.get("report") or []
        applied = {str(r.get("clause_id")) for r in rep if r.get("status") == "applied"}
        held_applied = sorted(i for i in applied if any(isinstance(cr, dict) and str(cr.get("clause_id")) == i
                                                       and (cr.get("redline_instruction") or {}).get("held") for cr in clause_results))
        add("보류·제거한 수정안이 변경추적본·클린본에 들어가지 않음", not held_applied, ", ".join(held_applied))
        cs = docs.get("change_set") or {}
        add("변경추적본·클린본 검증 표지 = 앱", (cs.get("verification") or {}).get("status") == vgm.get("status"))
        if brief is not None:
            nr = [e.location for e in getattr(brief, "appendix", []) or [] if e.applied == "제안만 있음·파일 미반영"]
            add("파일 미반영 수정안이 있으면 최종본 차단", (not nr) or bool(docs.get("final_blocked")), ", ".join(nr))
    return {"ok": all(c["ok"] for c in checks), "version": cur, "checks": checks}


__all__ = ["DEFAULT_AUTHOR", "UNVERIFIED_MARK", "brief_from_meta", "build_tracked_docs", "change_date", "finalize_review_meta",
           "output_consistency"]
