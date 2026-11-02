"""사업팀 전달본 합격 판정 — 다운로드한 실제 파일로 (reports_evidence/business_brief/ACCEPTANCE_CRITERIA.md B1~B13).

Usage: python scripts/check_brief_acceptance.py RUN_DIR --kind lease|ppl|service [--input INPUT_TEXT]
결과는 RUN_DIR/brief_acceptance.json 에 쓰고 요약을 출력한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.review.business_brief import undecided_terms  # noqa: E402

SECTIONS = ("1. 검토 결론", "2. 계약서 수정사항", "3. 계약 전 확인사항", "4. 사업부 결정사항", "별첨. 수정 위치와 완성 문구")
RX_INTERNAL = re.compile(
    r"REVIEW_[A-Z_]+|STATUS_[A-Z_]+|\bKR-\d|\bEN-\d|\bclr_|\bdeal_|\bfnd_|\beb_|\bcounsel_|\bHIGH\b|\bMEDIUM\b|\bLOW\b"
    r"|AI\s*자체|자동\s*검증|게이트|에이전트|finding|triage"
)


def _norm(s: str) -> str:
    s = re.sub(r"[“”\"'‘’]", "", str(s or ""))
    return re.sub(r"\s+", "", s)


def _sections(text: str) -> dict[str, str]:
    idx = [(text.find(h), h) for h in SECTIONS]
    out: dict[str, str] = {}
    pos = sorted((i, h) for i, h in idx if i >= 0)
    for k, (i, h) in enumerate(pos):
        end = pos[k + 1][0] if k + 1 < len(pos) else len(text)
        out[h] = text[i + len(h):end]
    return out


def _pdf_pages(path: Path) -> list[str]:
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        return [p.get_text() for p in doc]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--kind", default="")
    ap.add_argument("--variant", action="store_true", help="원본 천안 계약이 아닌 변형 — 원본 고유 문구(L) 검사 생략")
    args = ap.parse_args()
    run = Path(args.run)
    deep = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))
    review = deep.get("review") or deep
    meta = review.get("clause_meta") or {}
    clauses = review.get("original_clauses") or []
    contract_text = "\n".join(str(c.get("text") or "") for c in clauses if isinstance(c, dict))
    answers = json.loads((run / "02_answers.json").read_text(encoding="utf-8")) if (run / "02_answers.json").exists() else {}
    brief_docx = (run / "09_brief.txt").read_text(encoding="utf-8")
    brief_pdf = (run / "10_brief.txt").read_text(encoding="utf-8")
    internal = (run / "05_report.txt").read_text(encoding="utf-8")
    clean_path = run / "08_clean.txt"
    clean = clean_path.read_text(encoding="utf-8") if clean_path.exists() else None   # PDF 원본은 수정본(redline) 미지원
    ui_brief = meta.get("business_brief") or {}
    ui_secs = meta.get("business_brief_sections") or []
    res: dict[str, dict] = {}

    def put(key: str, ok: bool, evidence) -> None:
        res[key] = {"pass": bool(ok), "evidence": evidence}

    # B1 순서
    pos_d = [brief_docx.find(h) for h in SECTIONS]
    pos_p = [_norm(brief_pdf).find(_norm(h)) for h in SECTIONS]
    put("B1_section_order", all(p >= 0 for p in pos_d) and pos_d == sorted(pos_d) and all(p >= 0 for p in pos_p) and pos_p == sorted(pos_p),
        {"docx_pos": pos_d, "pdf_pos": pos_p})

    sec = _sections(brief_docx)
    s1 = sec.get(SECTIONS[0], "")
    concl_block = s1.split("요청하신 사항")[0]
    concl_lines = [ln.strip() for ln in concl_block.splitlines() if ln.strip()]
    has_verdict = any(ln.startswith("판단:") for ln in concl_lines)
    body_sents = [ln for ln in concl_lines if not ln.startswith("판단:")]
    need_risk = bool(ui_brief.get("revisions") or ui_brief.get("checks"))
    has_risk = any("잔존 위험" in ln for ln in body_sents) or not any(
        it.get("level") in ("필수", "중요") for it in (ui_brief.get("revisions") or []) + (ui_brief.get("checks") or []))
    put("B2_conclusion", has_verdict and 3 <= len(concl_lines) <= 6 and (has_risk or not need_risk),
        {"lines": concl_lines})

    # B3 누락 없음
    trace = ui_brief.get("trace") or {}
    ff = meta.get("final_findings") or {}
    live_ids = []
    for it in (ff.get("high_issues") or []) + (ff.get("medium_issues") or []):
        live_ids.append(str(it.get("clause_id") or it.get("finding_id")))
    core_ids = [str(c.get("id")) for c in ((meta.get("deal_assessment") or {}).get("core_risks") or [])
                if isinstance(c, dict)] if (meta.get("deal_assessment") or {}).get("active") else []
    missing = [i for i in live_ids + core_ids if not trace.get(i)]
    req_idx = [str(r.get("request_index") or "") for r in (meta.get("user_review_coverage") or []) if isinstance(r, dict)]
    req_missing = [i for i in req_idx if i and f"요청 {i}." not in s1]
    if not any(req_idx) and (meta.get("user_review_coverage") or []):
        req_missing = [] if "요청 1." in s1 else ["1"]
    # 항목 번호가 실제 파일에도 있는가
    nos = sorted({n for v in trace.values() for n in v})
    nos_missing = [n for n in nos if f"{n} " not in brief_docx]
    put("B3_no_omission", not missing and not req_missing and not nos_missing,
        {"internal_live": live_ids, "core_risks": core_ids, "missing_in_brief": missing,
         "requests": req_idx, "requests_missing": req_missing, "item_numbers_missing_in_file": nos_missing})

    # B4 반복
    body = "\n".join(sec.get(h, "") for h in SECTIONS[:4])
    sents = [s.strip() for s in re.split(r"(?<=[.다])\s+|\n", body) if len(s.strip()) >= 30]
    seen: dict[str, int] = {}
    for s in sents:
        k = _norm(re.sub(r"^(?:현재|문제|할 일|선택에 따라 남는 위험|남는 위험|정할 것|결정 내용|함께 확인)\s*:\s*", "", s))
        seen[k] = seen.get(k, 0) + 1
    dups = [k for k, n in seen.items() if n > 1]
    multi_explained = [i for i, v in trace.items() if len([n for n in v if not n.startswith("결정")]) > 1]
    put("B4_no_repetition", not dups and not multi_explained, {"duplicate_sentences": dups[:10], "explained_twice": multi_explained})

    # B5 행동·미확정
    lacks = []
    for it in ui_brief.get("revisions") or []:
        if f"{it['no']} " in brief_docx and "할 일:" not in brief_docx.split(it["no"] + " ", 1)[1][:1500]:
            lacks.append(it["no"])
    for it in ui_brief.get("checks") or []:
        blk = brief_docx.split(it["no"] + " ", 1)[1][:2500] if it["no"] + " " in brief_docx else ""
        if "누가:" not in blk or "언제까지:" not in blk:
            lacks.append(it["no"])
    for it in ui_brief.get("decisions") or []:
        blk = brief_docx.split(it["no"] + " ", 1)[1][:800] if it["no"] + " " in brief_docx else ""
        if "정할 것:" not in blk and "결정 내용:" not in blk:
            lacks.append(it["no"])
    und_missing = []
    for e in ui_brief.get("appendix") or []:
        terms = undecided_terms(e.get("new_text") or "", contract_text=contract_text,
                                answers_text=" ".join(str(v) for v in answers.values()))
        if terms and "미확정" not in brief_docx.split(e["no"] + " ", 1)[-1][:3000]:
            und_missing.append({"edit": e["no"], "terms": terms})
    put("B5_actionable", not lacks and not und_missing, {"items_without_action": lacks, "undecided_not_marked": und_missing})

    # B6 내부 코드·처리 과정
    hits = sorted({m.group(0) for m in RX_INTERNAL.finditer(brief_docx + "\n" + brief_pdf)})
    put("B6_no_internal_codes", not hits, {"hits": hits})

    # B7 무관한 법률 근거 (원인 단계: 검토 데이터의 조문)
    bad = []
    lease = args.kind == "lease"
    for cr in review.get("clause_results") or []:
        if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
            continue
        g = cr.get("legal_grounding") or {}
        cites = " ".join(str(s.get("citation") or "") + " " + str(s.get("title") or "") for s in g.get("statutes") or [] if isinstance(s, dict))
        if not cites:
            continue
        title = " ".join(str(cr.get(k) or "") for k in ("issue_title", "problem"))
        if lease:
            if "저작권법" in cites and not re.search(r"저작|콘텐츠|디자인|이미지", title + str(cr.get("original_text") or "")):
                bad.append((cr.get("clause_id"), "저작권법 on non-IP lease clause"))
            if "제543조" in cites and re.search(r"질권|예금", title):
                bad.append((cr.get("clause_id"), "해지권(제543조) on 예금질권"))
            if "제667조" in cites:
                bad.append((cr.get("clause_id"), "수급인 담보책임(제667조) in lease"))
            if "제390조" in cites and re.search(r"보증금|연대\s*보증|근저당", title) and "권리" not in title:
                bad.append((cr.get("clause_id"), "권리보증(제390조) on 보증금·연대보증"))
        else:
            if re.search(r"민법 제(?:623|629|265|357|356|349|353)조", cites):
                bad.append((cr.get("clause_id"), "lease/security statute in non-lease"))
    for line in internal.splitlines():
        if line.startswith("[관련 법령]"):
            if lease and ("저작권법" in line or "제667조" in line):
                bad.append(("report", line[:80]))
    put("B7_relevant_statutes", not bad, {"mismatches": bad})

    # B8 근거 없는 수용
    acc_lines = [ln for ln in brief_docx.splitlines() if re.search(r"수용", ln)]
    unsupported = [ln for ln in acc_lines if not re.search(r"수용을 뜻하지 않|수용 여부|수용 범위는 사업부|수용할지|명시|감수", ln)]
    accepted_core = [c.get("id") for c in ((meta.get("deal_assessment") or {}).get("core_risks") or [])
                     if isinstance(c, dict) and c.get("category") == "수용 가능한 위험"]
    explicit = any(re.search(r"수용|감수|감내", str(v)) for v in answers.values())
    # 답변 인용이 그 주제의 질문에서 온 것인가(11-02 실측: 연대보증 답이 투자비 결정에 인용됨 — 종전 체커가 놓쳤다).
    from runtime.review.deal_assessment import _question_topic

    up = json.loads((run / "01_upload.json").read_text(encoding="utf-8")) if (run / "01_upload.json").exists() else {}
    q_by_id = {str(q.get("question_id") or q.get("id")): str(q.get("title") or q.get("question") or "")
               for q in up.get("questions") or [] if isinstance(q, dict)}
    misattributed = []
    for ln in brief_docx.splitlines():
        for m in re.finditer(r"사용자 답변 '([^']{2,40})'", ln):
            line_topic = ("investment" if "투자비" in ln.split("사용자 답변")[0][-120:] and "보증 문장" not in ln
                          else "guarantee" if "보증" in ln else "parking" if "주차장" in ln else "")
            if not line_topic:
                continue
            src = [qid for qid, a in answers.items() if str(a).strip().startswith(m.group(1).strip().rstrip(".")[:10])]
            if src and not any(_question_topic(q_by_id.get(qid, "")) == line_topic for qid in src):
                misattributed.append({"line": ln[:120], "quoted": m.group(1), "from_questions": [q_by_id.get(q, q)[:60] for q in src]})
    put("B8_no_unsupported_acceptance", not unsupported and (not accepted_core or explicit) and not misattributed,
        {"lines_with_수용": acc_lines, "unsupported": unsupported, "core_marked_accept": accepted_core,
         "user_explicit_acceptance": explicit, "answer_misattributed": misattributed})

    # B9 수정 문구 완전·위치·전체 반영
    appx = sec.get(SECTIONS[4], "")
    trunc = [ln for ln in appx.splitlines() if re.search(r"…|\.\.\.", ln) and not ln.startswith("현재 문구")]
    loc_bad, not_applied = [], []
    for e in ui_brief.get("appendix") or []:
        m = re.search(r"제\s*(\d+)\s*조", e.get("location") or "")
        cur = e.get("current_text") or ""
        if m and cur:
            host = [c for c in clauses if isinstance(c, dict) and _norm(cur)[:30] in _norm(c.get("text"))]
            if host and all(str(c.get("article_number")) != m.group(1) for c in host):
                loc_bad.append({"edit": e["no"], "location": e.get("location"), "found_in": [c.get("display_path") for c in host]})
        probe = e.get("added_text") or e.get("new_text") or ""
        probe_n = _norm(re.sub(r"^[①-⑳]\s*", "", probe))
        if clean is not None and probe_n and probe_n[:60] not in _norm(clean) and e.get("mode") != "선택 시 추가":
            not_applied.append({"edit": e["no"], "location": e.get("location"), "probe": probe[:80]})
    put("B9_rewrites_complete_located_applied", not trunc and not loc_bad and not not_applied,
        {"truncated_lines": trunc, "location_mismatch": loc_bad, "not_in_clean_docx": not_applied,
         "appendix_count": len(ui_brief.get("appendix") or []),
         "clean_docx": "checked" if clean is not None else "N/A — PDF 원본은 수정본 생성 미지원(문구 위치·완전성만 판정)"})

    # B10 화면 = 다운로드, 내부와 핵심 판단 일치
    ui_lines = [r[1] for _h, rows in ui_secs for r in rows]
    file_norm = _norm(brief_docx)
    ui_missing = [ln for ln in ui_lines if _norm(ln) not in file_norm]
    must_internal = sorted(str(it.get("clause_id")) for it in ff.get("high_issues") or [])
    must_brief = sorted(i for i in must_internal if any(n.startswith(("수정", "확인")) for n in trace.get(i, [])))
    verdict = ui_brief.get("verdict") or ""
    verdict_ok = (not must_internal) or not verdict.startswith("진행 가능")
    put("B10_internal_brief_consistent", not ui_missing and must_internal == must_brief and verdict_ok,
        {"ui_lines_not_in_download": ui_missing[:5], "internal_HIGH": must_internal, "brief_linked_HIGH": must_brief,
         "verdict": verdict})

    # B11 보류 항목 공개
    pend = [ln for ln in brief_docx.splitlines() if "법무 추가 확인 중:" in ln]
    put("B11_pending_disclosed", all("체결 영향" in ln for ln in pend), {"pending_lines": pend})

    # B12 실행 조건
    log = json.loads((run / "00_run_log.json").read_text(encoding="utf-8"))
    dl = log.get("downloads") or {}
    need = ("05_report.docx", "09_brief.docx", "10_brief.pdf") + (("08_clean.docx",) if clean is not None else ())
    put("B12_fresh_session_downloads", bool(log.get("session_id")) and all(
        isinstance(dl.get(n), dict) and dl[n].get("bytes") for n in need),
        {"session_id": log.get("session_id"), "started_at": log.get("started_at"), "downloads": dl, "ai": (log.get("ai") or {}).get("provider") if isinstance(log.get("ai"), dict) else log.get("ai")})

    # B13 분량(참고)
    pages = _pdf_pages(run / "10_brief.pdf")
    body_pages = next((i + 1 for i, t in enumerate(pages) if "별첨. 수정 위치" in t), len(pages))
    res["B13_length_info"] = {"pass": None, "evidence": {"pdf_pages_total": len(pages), "body_ends_on_page": body_pages,
                                                         "internal_report_chars": len(internal), "brief_chars": len(brief_docx)}}

    # L 임대차 추가
    if lease and clean is not None and not args.variant:
        probes = {"guarantee_max": "이보증채무의최고액은", "parking_succession": "제2호의사용승인을승계", "pledge_same_day": "같은날진행한다"}
        got = {k: (v in _norm(clean or "")) for k, v in probes.items()}
        put("L_all_edits_in_clean", all(got.values()), got)

    passed = all(v["pass"] for v in res.values() if v["pass"] is not None)
    out = {"run": str(run), "kind": args.kind, "all_pass": passed, "results": res}
    (run / "brief_acceptance.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for k, v in res.items():
        print(f"{'PASS' if v['pass'] else ('INFO' if v['pass'] is None else 'FAIL')}  {k}")
    print("ALL_PASS" if passed else "NOT_ALL_PASS")


if __name__ == "__main__":
    main()
