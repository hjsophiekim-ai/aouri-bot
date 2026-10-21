"""프리랜서(콘텐츠 제작) 용역계약 e2e 결과의 합격 기준(C1~C8) 판정.

reports_evidence/freelancer_q4/ACCEPTANCE_CRITERIA.md 의 기준을 그대로 옮긴 것이다.
수정 전 결과에 먼저 돌려 기준을 고정했다 — 이후 판정 문형을 느슨하게 바꾸지 않는다.

파이프라인의 검증 모듈을 쓰지 않는다. 수정안 적용도 여기서 따로 한다 — 검증 대상
코드로 검증하면 같은 버그를 같이 놓친다.

Usage: python scripts/check_freelancer_acceptance.py RUN_DIR SOURCE_TXT [--ui-legacy]
  --ui-legacy  수정 전 UI(상단 건수에 중복생략·현행유지 포함)로 판정
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _n(s: str) -> str:
    s = str(s or "").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", "", s)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]


def _final_findings(review: dict) -> list[dict]:
    """데모 UI renderClauseList 의 표시 필터를 그대로 옮긴 것 — 화면에 카드로 뜨는 항목."""
    out = []
    for it in review.get("clause_results") or []:
        if not isinstance(it, dict) or it.get("dedup_suppressed") or it.get("keep_as_is"):
            continue
        tier = str(it.get("risk_tier") or "").upper()
        if it.get("is_checklist_item"):
            if tier in ("HIGH", "MEDIUM") or it.get("user_focus_hit") or it.get("factual_hit"):
                out.append(it)
            continue
        high = tier == "HIGH" or bool(it.get("approval_required")) or bool(it.get("high_risk"))
        has_rw = bool(str(it.get("suggested_rewrite") or "").strip())
        if high or tier == "MEDIUM" or (it.get("user_focus_hit") and has_rw):
            out.append(it)
    return out


#: 실행 당시 데모 UI 의 상단 건수 계산식. 수정 전(legacy)은 중복생략·현행유지까지 셌다.
_UI_COUNTS_VISIBLE_ONLY = True


def _ui_header_counts(review: dict) -> tuple[int, int]:
    """데모 UI resultMeta 의 '필수수정=N 권장=M' 계산을 그대로 옮긴 것."""
    items = [x for x in (review.get("clause_results") or []) if isinstance(x, dict)]
    if _UI_COUNTS_VISIBLE_ONLY:
        items = [x for x in items if not x.get("dedup_suppressed") and not x.get("keep_as_is")]
    must = sum(1 for x in items if x.get("approval_required") or x.get("high_risk")
               or (_UI_COUNTS_VISIBLE_ONLY and str(x.get("risk_tier") or "").upper() == "HIGH"))
    med = sum(1 for x in items if not x.get("approval_required") and not x.get("high_risk")
              and str(x.get("risk_tier") or "").upper() == "MEDIUM")
    return must, med


def _is_high(f: dict) -> bool:
    return str(f.get("risk_tier") or "").upper() == "HIGH" or bool(f.get("high_risk")) or bool(f.get("approval_required"))


def _article_spans(src: str) -> dict[str, str]:
    """원문 '제 N 조' 머리 → 그 조의 원문."""
    heads = list(re.finditer(r"(?m)^\s*제\s*(\d+)\s*조\s*[.\[]", src))
    spans: dict[str, str] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(src)
        spans.setdefault(m.group(1), src[m.start():end])
    return spans


def _apply_all(src: str, findings: list[dict]) -> tuple[str, list[str]]:
    """모든 redline_instruction 을 원문에 반영한 텍스트와 적용 실패 목록.

    교체는 대상 문구를 바꾸고, 항 신설("제A조 … 제N항 신설")은 그 조의 끝에 넣고,
    조 신설("제A조 뒤에 제B조 신설")은 문서 끝에 "제B조 [신설]" 머리로 붙인다.
    자동 적용 보류(held) 항목은 반영하지 않는다 — 보류는 '그대로 넣지 말라' 는 뜻이다.
    """
    text = src
    failures: list[str] = []
    appended: list[str] = []
    para_inserts: list[tuple[str, str]] = []
    for cr in findings:
        ri = cr.get("redline_instruction") or {}
        if not isinstance(ri, dict) or not ri:
            continue
        if cr.get("rewrite_held") or ri.get("held"):
            continue
        loc = str(ri.get("edit_location") or "")
        repl = str(ri.get("final_clause_text") or ri.get("replacement_text") or "").strip()
        target = str(ri.get("target_text") or "").strip()
        if not repl:
            continue
        m_para = re.search(r"제\s*(\d+)\s*조[^\n]*?제\s*\d+\s*항\s*신설", loc)
        m_art = re.search(r"제\s*(\d+)\s*조\s*신설", loc)
        if m_para:
            para_inserts.append((m_para.group(1), repl))
            continue
        if m_art or "신설" in loc:
            num = m_art.group(1) if m_art else "?"
            appended.append(f"제 {num} 조. [신설]\n{repl}")
            continue
        if not target:
            failures.append(f"{cr.get('clause_id')}: 교체 대상 문구 없음")
            continue
        pat = r"\s*".join(re.escape(ch) for ch in _n(target))
        m = re.search(pat, text)
        if not m:
            failures.append(f"{cr.get('clause_id')}: 교체 대상이 원문에 없음 ({target[:40]})")
            continue
        text = text[:m.start()] + repl + text[m.end():]
    for art, repl in para_inserts:
        heads = list(re.finditer(r"(?m)^\s*제\s*(\d+)\s*조\s*[.\[]", text))
        pos = next((i for i, h in enumerate(heads) if h.group(1) == art), None)
        if pos is None:
            failures.append(f"항 신설 대상 제{art}조가 없음")
            continue
        end = heads[pos + 1].start() if pos + 1 < len(heads) else len(text)
        text = text[:end].rstrip("\n") + "\n" + repl + "\n" + text[end:]
    if appended:
        text = text + "\n" + "\n".join(appended)
    return text, failures


def check(run: Path, src_path: Path) -> dict:
    src = src_path.read_text(encoding="utf-8")
    deep = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))
    review = deep.get("review") or {}
    docx = (run / "05_report.txt").read_text(encoding="utf-8") if (run / "05_report.txt").exists() else ""
    pdf = (run / "06_report.txt").read_text(encoding="utf-8") if (run / "06_report.txt").exists() else ""
    findings = _final_findings(review)
    ui_blob = json.dumps({
        "clause_results": findings,
        "executive_summary": review.get("executive_summary"),
        "user_review_coverage": (review.get("clause_meta") or {}).get("user_review_coverage"),
    }, ensure_ascii=False)
    outputs = {"docx": docx, "pdf": pdf, "ui_json": ui_blob}
    res: dict[str, dict] = {}

    # C1 — 존재하는 IP·대금·검수 규정을 미기재로
    rx_c1 = re.compile(
        r"(지식재산권?\s*귀속|권리\s*귀속|IP\s*귀속|검수\s*(?:기준|규정|절차)|대금\s*지급\s*(?:조건|규정)|지급\s*조건)"
        r"[^.\n]{0,12}(?:미기재|규정\s*없음|조항\s*없음|누락)"
    )
    hits = [f"{k}: {m.group(0)}" for k, t in outputs.items() for m in rx_c1.finditer(t)]
    # 요약 헤더의 세 축은 원문에 명시돼 있다 — "규정 있음" 외의 판정(불명확·확인 불가 등)도 실패다.
    for k, t in (("docx", docx), ("pdf", pdf)):
        for label in ("산출물 지식재산권 귀속", "검수 기준", "대금 지급 조건"):
            m = re.search(rf"{label}:\s*([^\n]+)", t)
            if m and not m.group(1).startswith("규정 있음"):
                hits.append(f"{k}: {label}: {m.group(1)[:50]}")
    res["C1"] = {"pass": not hits, "evidence": hits[:10]}

    # C2 — 권리 귀속(제8조①)을 이용허락으로 설명
    rx_c2 = re.compile(r"(?:이\s*조항은|제\s*8\s*조[^.\n]{0,20}(?:은|는))[^.\n]{0,40}이용허락(?:입니다|이다|에\s*해당)"
                       r"|양도가\s*아니라\s*이용허락")
    hits = [f"{k}: {m.group(0)}" for k, t in outputs.items() for m in rx_c2.finditer(t)]
    res["C2"] = {"pass": not hits, "evidence": hits[:10]}

    # C3 — 개인정보 미확인을 확정 위반·HIGH·필수수정으로
    bad = []
    for cr in findings:
        title = str(cr.get("issue_title") or "")
        if "개인정보" in title and (_is_high(cr) or cr.get("must_fix")):
            bad.append(f"ui_json: {cr.get('clause_id')} {title[:60]}")
    for k, t in (("docx", docx), ("pdf", pdf)):
        sec = t.split("4. 권장수정")[0].split("3. 필수수정")[-1] if "3. 필수수정" in t else ""
        for ln in _lines(sec):
            if ln.startswith("[HIGH]") and "개인정보" in ln:
                bad.append(f"{k}: {ln[:80]}")
        for m in re.finditer(r"개인정보\s*보호법\s*(?:을|를)?\s*위반(?:한다|하였다|입니다|이다)", t):
            bad.append(f"{k}: {m.group(0)}")
    res["C3"] = {"pass": not bad, "evidence": bad[:10]}

    # C4/C5 — 수정안 전부 반영본
    applied, apply_fail = _apply_all(src, findings)
    (run / "applied_all_revisions.txt").write_text(applied, encoding="utf-8")
    spans = _article_spans(applied)
    art7 = spans.get("7", "")
    need = {"내부 자료": r"내부\s*자료", "영업정보": r"영업\s*정보", "생성형 AI": r"생성형\s*AI", "종료 후 유효": r"종료\s*후에도"}
    lost = [k for k, p in need.items() if not re.search(p, art7)]
    res["C4"] = {"pass": bool(art7) and not lost, "evidence": [f"제7조에서 사라진 보호: {lost}"] if lost else []}

    c5: list[str] = []
    heads = re.findall(r"(?m)^\s*제\s*(\d+)\s*조\s*[.\[]", applied)
    for n in sorted(set(heads), key=int):
        if heads.count(n) > 1:
            c5.append(f"조 번호 중복: 제{n}조 x{heads.count(n)}")
    art_spans = _article_spans(applied)

    def _paras(a: str) -> set[str]:
        body = art_spans.get(a, "")
        return {str("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳".index(ch) + 1) for ch in re.findall(r"(?m)^\s*([①-⑳])", body)}

    for a, body in art_spans.items():
        for m in re.finditer(r"(?<![법률령])\s제\s*(\d+)\s*조(?:\s*제\s*(\d+)\s*항)?", " " + body):
            ra, rp = m.group(1), m.group(2)
            if ra not in art_spans:
                c5.append(f"제{a}조 안에 없는 조 참조: 제{ra}조")
            elif rp and _paras(ra) and rp not in _paras(ra):
                c5.append(f"제{a}조 안에 없는 항 참조: 제{ra}조 제{rp}항")
        no_art = re.sub(r"제\s*\d+\s*조\s*제\s*\d+\s*항", "", body)
        is_new_article = bool(re.match(r"\s*제\s*\d+\s*조\.\s*\[신설\]", body))
        for m in re.finditer(r"제\s*(\d+)\s*항", no_art):
            if is_new_article and not _paras(a):
                c5.append(f"신설 제{a}조 안의 '제{m.group(1)}항' — 어느 조의 항인지 불명확")
            elif _paras(a) and m.group(1) not in _paras(a):
                c5.append(f"제{a}조 안의 '제{m.group(1)}항' 이 같은 조에 없음(참조 불명확)")
    c5 = list(dict.fromkeys(c5))
    # 원문 상호참조 오류 — 큐레이션형 뉴스레터는 제2조①3호인데 '제2호 및 제5호'
    orig_err = bool(re.search(r"제\s*2\s*호\s*및\s*제\s*5\s*호", src))
    still = bool(re.search(r"제\s*2\s*호\s*및\s*제\s*5\s*호", applied))
    flagged = any(re.search(r"(?:제\s*5\s*호|상호\s*참조|호\s*번호|제\s*3\s*호)", str(cr.get("problem") or "") + str(cr.get("issue_title") or ""))
                  and re.search(r"제\s*2\s*조|제\s*5\s*조\s*제\s*3\s*항", json.dumps(cr, ensure_ascii=False)) for cr in findings)
    flagged = flagged or bool(re.search(r"(?:상호\s*참조|참조\s*오류)[^\n]{0,80}제\s*[35]\s*호|제\s*5\s*호[^\n]{0,60}(?:큐레이션|월\s*1회|참조)", docx))
    if orig_err and still and not flagged:
        c5.append("원문 상호참조 오류(제2호 및 제5호)가 지적·수정되지 않음")
    c5 += [f"적용 실패: {x}" for x in apply_fail]
    res["C5"] = {"pass": not c5, "evidence": c5[:15]}

    # C6 — 지적·근거·수정 위치·문구 일치
    c6: list[str] = []
    src_n = _n(src)
    foreign = re.compile(r"개발\s*범위|SOW|소프트웨어|라이브러리|솔루션|공사|렌탈|대리점|가맹|하자보수")
    for cr in findings:
        cid = cr.get("clause_id")
        ot = str(cr.get("original_text") or "")
        if len(_n(ot)) >= 12 and _n(ot) not in src_n and not ot.startswith("["):
            c6.append(f"{cid}: 원문 인용이 원문에 없음 ({ot[:40]})")
        for fld in ("issue_title", "problem", "suggested_rewrite"):
            v = str(cr.get(fld) or "")
            for m in foreign.finditer(v):
                if not re.search(re.escape(m.group(0)), src):
                    c6.append(f"{cid}: 다른 계약 설명 혼입 [{fld}] '{m.group(0)}'")
        rw = str(cr.get("suggested_rewrite") or "")
        if re.search(r"당사(?:의|는|가|에)", rw) and "당사" not in src.replace("당사자", ""):
            c6.append(f"{cid}: 계약에 정의되지 않은 '당사' 사용")
        ri = cr.get("redline_instruction") or {}
        loc = str(ri.get("edit_location") or "")
        m = re.match(r"제\s*(\d+)\s*조", loc)
        if m and "신설" not in loc and str(cr.get("article_number") or m.group(1)) != m.group(1):
            c6.append(f"{cid}: 수정 위치 {loc} ≠ 지적 조항 제{cr.get('article_number')}조")
    for k, t in (("docx", docx), ("pdf", pdf)):
        for m in re.finditer(r"(?:저작권법|민법|상법|개인정보\s*보호법)\s*제\s*\d+\s*항", t):
            c6.append(f"{k}: 조 번호가 빠진 법령 인용 '{m.group(0)}'")
    res["C6"] = {"pass": not c6, "evidence": sorted(set(c6))[:20]}

    # C7 — 요약·상세·UI·다운로드 일치
    c7: list[str] = []
    for k, t in (("docx", docx), ("pdf", pdf)):
        sec = t.split("1. 계약 구조")[0]
        if "전반" in sec and re.search(r"판단:\s*적정", sec) and len(findings) > 0:
            c7.append(f"{k}: '계약서 전반' 요청을 '적정' 처리하면서 별도 지적 {len(findings)}건 존재")
        if re.search(r"분석\s*신뢰도:\s*\d+%", t):
            c7.append(f"{k}: 근거 없는 '분석 신뢰도 %' 표시")
        roles = set(re.findall(r"우리 측 지위:\s*([^\n]+)", t))
        if len(roles) > 1:
            c7.append(f"{k}: 우리 측 지위가 둘로 표시 {sorted(roles)}")
        m = re.search(r"HIGH\s*(\d+)건\s*\|\s*MEDIUM\s*(\d+)건", t)
        if m:
            hi = sum(1 for f in findings if _is_high(f))
            md = len(findings) - hi
            if (int(m.group(1)), int(m.group(2))) != (hi, md):
                c7.append(f"{k}: 건수 {m.group(1)}/{m.group(2)} ≠ UI 카드 {hi}/{md}")
            uh = _ui_header_counts(review)
            if (int(m.group(1)), int(m.group(2))) != uh:
                c7.append(f"{k}: 건수 {m.group(1)}/{m.group(2)} ≠ UI 상단 표시 필수수정={uh[0]} 권장={uh[1]}")
        warn = t.split("자동 검증에서 보류")[-1] if "자동 검증에서 보류" in t else ""
        for cid in re.findall(r"KR-[\w-]+", warn):
            body = t.split("자동 검증에서 보류")[0]
            if f"보류" not in body and cid:
                c7.append(f"{k}: 경고({cid} 완성문구 없음)가 본문 항목 상태에 반영되지 않음")
        # 경고가 이름을 댄 항목(CP-/xref_/eb_ 등)이 본문에 '보류' 표시 없이 완성 문안으로 실려 있으면 모순이다.
        body_part = t.split("자동 검증에서 보류")[0]
        for cid in re.findall(r"해당 항목:\s*([^\n]+)", warn):
            for one in [x.strip() for x in cid.split(",") if x.strip()]:
                f_ = next((f for f in findings if str(f.get("clause_id")) == one), None)
                if f_ is not None and not (f_.get("rewrite_held") or (f_.get("redline_instruction") or {}).get("held")) \
                        and "자동 적용 보류" not in body_part:
                    c7.append(f"{k}: 경고가 {one} 를 보류했다고 하나 본문에는 완성 문안으로 실림")
        if "대응 검토항목이 없습니다" in warn:
            c7.append(f"{k}: '대응 검토항목 없음' 경고가 어느 항목·최종 상태에도 반영되지 않음")
    # DOCX 와 PDF 의 핵심 결론 줄이 같은가
    def _core(t: str) -> list[tuple[str, str]]:
        """(위험도, 조항 위치) — 표기 형식이 아니라 판단을 비교한다."""
        out = []
        for ln in _lines(t):
            m = re.match(r"^(?:-\s*)?\[(HIGH|MEDIUM)\]\s*(제\s*\d+\s*조(?:\s*제\s*\d+\s*항)?)", ln)
            if m:
                out.append((m.group(1), _n(m.group(2))))
        return out
    if docx and pdf and _core(docx) != _core(pdf):
        c7.append(f"DOCX 와 PDF 의 HIGH/MEDIUM 판단(위험도·위치)이 다름: {_core(docx)} vs {_core(pdf)}")
    res["C7"] = {"pass": not c7, "evidence": c7[:15]}

    # C8 — 누락 방지
    c8 = []
    rep = docx or ui_blob
    if not re.search(r"2차적\s*저작물|재가공", rep):
        c8.append("재가공·2차적저작물 권한 미검토")
    if not re.search(r"지급\s*전[^\n]{0,20}(?:게시|이용|사용)", rep):
        c8.append("지급 전 게시·이용권 미검토")
    if orig_err and not flagged:
        c8.append("상호참조 오류 미검토")
    res["C8"] = {"pass": not c8, "evidence": c8}

    return {"run": str(run), "all_pass": all(v["pass"] for v in res.values()), "criteria": res,
            "final_findings": [{"id": f.get("clause_id"), "tier": f.get("risk_tier"), "title": str(f.get("issue_title"))[:70]} for f in findings]}


def main() -> None:
    global _UI_COUNTS_VISIBLE_ONLY
    run, src = Path(sys.argv[1]), Path(sys.argv[2])
    if "--ui-legacy" in sys.argv:
        _UI_COUNTS_VISIBLE_ONLY = False
    out = check(run, src)
    (run / "acceptance.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in out["criteria"].items():
        print(k, "PASS" if v["pass"] else "FAIL", *(["\n   - " + e for e in v["evidence"]] if v["evidence"] else []))
    print("ALL_PASS" if out["all_pass"] else "SOME_FAIL")


if __name__ == "__main__":
    main()
