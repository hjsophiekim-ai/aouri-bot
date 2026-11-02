"""프로그램 협찬(PPL) 계약 e2e 결과의 합격 기준(P1~P13) 판정 — 광고주 관점.

reports_evidence/cjenm_ppl/ACCEPTANCE_CRITERIA.md 를 옮긴 것이다. 수정 전 결과에 먼저 돌려 고정했다.
조항 위치는 상수로 쓰지 않고 원문 문형으로 찾는다 — 회사명·조번호를 바꾼 변형에도 그대로 쓴다.
파이프라인 모듈은 쓰지 않는다(검증 대상 코드로 검증하지 않는다).

Usage: python scripts/check_ppl_acceptance.py RUN_DIR [--ui-legacy]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_freelancer_acceptance as base  # noqa: E402  (UI 표시 필터·건수 계산을 그대로 쓴다)


def _n(s: str) -> str:
    return base._n(s)


def _blob(f: dict) -> str:
    keys = ("issue_title", "problem", "rewrite_reason", "legal_business_reason", "suggested_rewrite",
            "negotiation_position", "negotiation_strategy")
    out = [str(f.get(k) or "") for k in keys]
    out += [str(d.get("issue_title") or "") for d in f.get("detected_issue_list") or [] if isinstance(d, dict)]
    ri = f.get("redline_instruction") or {}
    out += [str(ri.get("final_clause_text") or ""), str(ri.get("edit_location") or "")]
    g = f.get("legal_grounding") or {}
    out += [str(g.get("legal_reason") or "")]
    return "\n".join(out)


def _art_of(src: str, rx: str) -> str:
    """원문에서 문형이 처음 나오는 조 번호."""
    m = re.search(rx, src)
    if not m:
        return ""
    heads = [(h.start(), h.group(1)) for h in re.finditer(r"(?m)^\s*제\s*(\d+)\s*조", src)]
    return next((n for pos, n in reversed(heads) if pos <= m.start()), "")


def check(run: Path, legacy_ui: bool = False) -> dict:
    base._UI_COUNTS_VISIBLE_ONLY = not legacy_ui
    deep = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))
    review = deep.get("review") or {}
    src = "\n".join(str(c.get("text") or "") for c in review.get("original_clauses") or [])
    src_full = "\n".join(f"제{c.get('article_number')}조\n{c.get('text')}" for c in review.get("original_clauses") or []
                         if c.get("article_number"))
    rd = lambda n: (run / n).read_text(encoding="utf-8") if (run / n).exists() else ""  # noqa: E731
    docx, pdf, clean = rd("05_report.txt"), rd("06_report.txt"), rd("08_clean.txt")
    findings = base._final_findings(review)
    blobs = {str(f.get("clause_id")): _blob(f) for f in findings}
    all_blob = "\n".join(blobs.values())
    report = docx + "\n" + pdf
    res: dict[str, dict] = {}

    # 조 위치(원문 문형으로)
    a_indem = _art_of(src_full, r"면책한다")
    a_refund = _art_of(src_full, r"불이행\s*된?\s*협찬대가분|불이행분을\s*정산")
    a_tent = _art_of(src_full, r"예정에\s*해당")
    a_ip = _art_of(src_full, r"사전\s*서면\s*합의를\s*거쳐야")

    # P1
    t = re.search(r"계약유형:\s*([^\n]+)", docx)
    r_ = re.search(r"우리 측 지위:\s*([^\n]+)", docx)
    bad = []
    if not t or not re.search(r"협찬|PPL|간접광고|광고", t.group(1)):
        bad.append(f"계약유형={t.group(1) if t else '없음'}")
    if not r_ or not re.search(r"광고주|협찬사", r_.group(1)):
        bad.append(f"우리 측 지위={r_.group(1) if r_ else '없음'}")
    res["P1"] = {"pass": not bad, "evidence": bad}

    # P2 — 우리를 보호하는 조항 원문을 근거로 한 HIGH
    bad = []
    for f in findings:
        if not base._is_high(f):
            continue
        ot = _n(str(f.get("original_text") or ""))
        if re.search(r"면책한다", str(f.get("original_text") or "")) or re.search(
                r"불이행\s*된?\s*협찬대가분|불이행분을\s*정산", str(f.get("original_text") or "")):
            bad.append(f"{f.get('clause_id')} HIGH on 보호조항 ({str(f.get('original_text'))[:40]})")
        _ = ot
    res["P2"] = {"pass": not bad, "evidence": bad}

    # P3
    conflict = [f for f in findings if re.search(r"예정", _blob(f)) and re.search(r"보장|개런티|최소", _blob(f))]
    high_c = [f for f in conflict if base._is_high(f)]
    consent = [f for f in conflict if re.search(r"사전\s*서면\s*동의", _blob(f))]
    bad = []
    if not conflict:
        bad.append("보장 vs 예정·협의 충돌 미지적")
    elif not high_c:
        bad.append("충돌 지적이 HIGH 아님")
    if conflict and not consent:
        bad.append("보장 사항 변경을 사전 서면 동의로 묶는 수정안 없음")
    res["P3"] = {"pass": not bad, "evidence": bad}

    # P4
    perf = [f for f in findings if re.search(r"조회수", _blob(f)) and re.search(r"집계|기준|미달", _blob(f))]
    bad = []
    if not perf:
        bad.append("조회수 보장 집계·미달 처리 미검토")
    else:
        b = "\n".join(_blob(f) for f in perf)
        if a_refund and not re.search(rf"제\s*{a_refund}\s*조|정산|반환|반납", b):
            bad.append("기존 정산·반환 조항 연결 없음")
    if re.search(r"전액\s*(?:을\s*)?(?:환급|반환|반납)", all_blob):
        bad.append("전액 환급·반환 수정안")
    res["P4"] = {"pass": not bad, "evidence": bad}

    # P5
    pay = [f for f in findings
           if re.search(r"세금계산서|대금[^.]{0,30}지급|청구한다", str(f.get("original_text") or ""))
           and re.search(r"게시일|방송일|방영일|게시\s*완료", _blob(f))]
    bad = [] if pay else ["게시일 변동과 청구·지급 시점 연결 미검토"]
    if re.search(r"(?:지급|대금)[^\n]{0,30}판단:\s*적정", docx):
        bad.append("지급조건 적정 판정")
    res["P5"] = {"pass": not bad, "evidence": bad}

    # P6
    lic = [f for f in findings if re.search(r"라이선스", _blob(f)) and re.search(r"사전\s*서면\s*합의|별도\s*(?:승인|합의)", _blob(f))]
    start = re.search(r"기산|시작일|최초\s*게시일부터", all_blob)
    bad = []
    if not lic:
        bad.append("라이선스 vs 별도 사전 서면 합의 충돌 미지적")
    if not start:
        bad.append("라이선스 기산일 미검토")
    if re.search(r"양도(?:받|하여야|한다|를\s*요구)|양도\s*조항에\s*그\s*권리|[‘'\"]갑[’'\"]?에게\s*(?:모두\s*)?귀속", all_blob):
        bad.append("저작권 양도·갑 귀속 요구")
    res["P6"] = {"pass": not bad, "evidence": bad}

    # P7
    bad = []
    for cid, b in blobs.items():
        f = next(x for x in findings if str(x.get("clause_id")) == cid)
        rw = str(f.get("suggested_rewrite") or "") + str((f.get("redline_instruction") or {}).get("final_clause_text") or "")
        if re.search(r"초상", rw) and re.search(r"[‘'\"]?을[’'\"]?(?:은|이)[^.]{0,60}(?:확보|보장)", rw) \
                and not re.search(r"협상안|확인\s*사항|사업부", b):
            bad.append(f"{cid}: 초상권 확보 의무를 상대방에게 지우는 수정안(협상안 표시 없음)")
    res["P7"] = {"pass": not bad, "evidence": bad}

    # P8
    sched = [f for f in findings if re.search(r"편성|방송\s*일정|게시\s*일정|일정", _blob(f))
             and re.search(r"최종|기한|연장|정산", _blob(f))]
    res["P8"] = {"pass": bool(sched), "evidence": [] if sched else ["최종 이행기한·정산 미검토"]}

    # P9
    bad = []
    for m in re.finditer(r"■\s*방송법[^\n]*적용 가능성:\s*높음", report):
        bad.append("방송법 '적용 가능성 높음' 단정")
    # "직접 적용되는지는 … 확인 필요" 는 단정이 아니다 — 단정 어미만 본다.
    if re.search(r"방송법[^\n]{0,40}직접\s*적용(?:됩니다|된다|됨)(?!지)", report):
        bad.append("방송법 직접 적용 단정")
    if not re.search(r"경제적\s*이해관계|유료\s*광고\s*(?:포함|표시)|협찬\s*표시|추천\s*[·ㆍ]?\s*보증", all_blob + report):
        bad.append("경제적 이해관계 표시 미검토")
    if re.search(r"개인정보[^\n]{0,30}:\s*(?:일부 적용|수정 필요)", report):
        bad.append("개인정보 미확인을 적용·수정 필요로 단정")
    res["P9"] = {"pass": not bad, "evidence": bad}

    # P10
    bad = []
    foreign = re.compile(r"오픈소스|소스\s*코드|라이브러리|제품화|개발\s*범위|SOW|회수\s*의무|하자보수")
    for cid, b in blobs.items():
        for m in foreign.finditer(b):
            if m.group(0) not in src:
                bad.append(f"{cid}: 타 계약 문구 '{m.group(0)}'")
    for f in findings:
        ri = f.get("redline_instruction") or {}
        loc = str(ri.get("edit_location") or "")
        m = re.match(r"제\s*(\d+)\s*조", loc)
        art = str(f.get("article_number") or "")
        if m and art and m.group(1) != art and "신설" not in loc and not f.get("package_linked_edits"):
            bad.append(f"{f.get('clause_id')}: 지적 제{art}조 ≠ 수정 위치 {loc}")
    if clean:
        if "[추가 권고]" in clean or "추가 권고" in clean:
            bad.append("반영본에 '[추가 권고]' 비계약 표지")
        for label, rx in (("라이선스 문언", r"재편집\s*권한"), ("면책 문언", r"면책한다"),
                          ("정산·반환 문언", r"불이행\s*된?\s*협찬대가분|불이행분을\s*정산")):
            if re.search(rx, src) and not re.search(rx, clean):
                bad.append(f"반영본에서 기존 {label} 사라짐")
        # 신설 항 번호가 조 안에서 오름차순인지(⑪ 이 ⑩ 보다 먼저 오면 실패)
        for art_body in re.split(r"(?m)^\s*제\s*\d+\s*조\s*\(", clean):
            marks = ["①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮".index(m) for m in re.findall(r"(?m)^\s*([①-⑮])", art_body)]
            if marks != sorted(marks):
                bad.append("반영본 신설 항 순서 뒤바뀜")
        heads = re.findall(r"(?m)^\s*제\s*(\d+)\s*조\s*\(", clean)
        dup = sorted({h for h in heads if heads.count(h) > 1})
        if dup:
            bad.append(f"반영본 조번호 중복: {dup}")
    targets: dict[str, list[str]] = {}
    for f in findings:
        ri = f.get("redline_instruction") or {}
        if str(ri.get("edit_type") or "") == "replace" and not ri.get("held"):
            targets.setdefault(_n(str(ri.get("target_text") or "")), []).append(str(f.get("clause_id")))
    keys = [k for k in targets if k]
    for i, k in enumerate(keys):
        for k2 in keys[i:]:
            ids = targets[k] if k == k2 else targets[k] + targets[k2]
            if (k == k2 and len(ids) > 1) or (k != k2 and (k in k2 or k2 in k)):
                bad.append(f"같은 원문(또는 그 일부)을 교체하는 수정안 충돌: {ids}")
    res["P10"] = {"pass": not bad, "evidence": sorted(set(bad))[:20]}

    # P11
    hits = re.findall(r"업계\s*(?:표준|관행)|관행상|표준\s*요구사항|수용\s*가능성이\s*높", all_blob + report)
    res["P11"] = {"pass": not hits, "evidence": hits[:5]}

    # P12 — 프리랜서 기준의 C7 판정 일부를 그대로 쓴다(건수·DOCX/PDF 판단)
    c12 = []
    for k, t_ in (("docx", docx), ("pdf", pdf)):
        m = re.search(r"HIGH\s*(\d+)건\s*\|\s*MEDIUM\s*(\d+)건", t_)
        if m:
            hi = sum(1 for f in findings if base._is_high(f))
            md = len(findings) - hi
            if (int(m.group(1)), int(m.group(2))) != (hi, md):
                c12.append(f"{k}: 건수 {m.group(1)}/{m.group(2)} ≠ UI 카드 {hi}/{md}")
            uh = base._ui_header_counts(review)
            if (int(m.group(1)), int(m.group(2))) != uh:
                c12.append(f"{k}: 건수 ≠ UI 상단 {uh}")
        if re.search(r"분석\s*신뢰도:\s*\d+%", t_):
            c12.append(f"{k}: 분석 신뢰도 %")

    def _core(t_: str) -> list:
        return [(m.group(1), _n(m.group(2))) for m in re.finditer(
            r"(?m)^(?:-\s*)?\[(HIGH|MEDIUM)\]\s*(제\s*\d+\s*조(?:\s*제\s*\d+\s*항)?)", t_)]
    if docx and pdf and _core(docx) != _core(pdf):
        c12.append("DOCX/PDF 판단 불일치")
    res["P12"] = {"pass": not c12, "evidence": c12}

    # P13
    biz = re.search(r"사업부|재경", report)
    items = [w for w in ("쇼츠", "제품", "대행사") if re.search(rf"{w}[^\n]{{0,80}}(?:확인|협의|정해)", report)]
    bad = []
    if not biz:
        bad.append("사업부 확인사항 없음")
    if len(items) < 2:
        bad.append(f"누락 상업조건 확인 부족(확인된 축: {items})")
    res["P13"] = {"pass": not bad, "evidence": bad}

    return {"run": str(run), "all_pass": all(v["pass"] for v in res.values()), "criteria": res,
            "final_findings": [{"id": f.get("clause_id"), "tier": f.get("risk_tier"),
                                "title": str(f.get("issue_title"))[:70]} for f in findings],
            "anchors": {"indemnity": a_indem, "refund": a_refund, "tentative": a_tent, "ip_approval": a_ip}}


def main() -> None:
    run = Path(sys.argv[1])
    out = check(run, legacy_ui="--ui-legacy" in sys.argv)
    (run / "acceptance.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in out["criteria"].items():
        print(k, "PASS" if v["pass"] else "FAIL", *(["\n   - " + e for e in v["evidence"]] if v["evidence"] else []))
    print("ALL_PASS" if out["all_pass"] else "SOME_FAIL")


if __name__ == "__main__":
    main()
