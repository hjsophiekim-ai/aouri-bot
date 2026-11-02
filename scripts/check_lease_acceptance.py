"""부동산(상가) 임대차 — 임차인 관점 e2e 결과의 합격 기준(L1~L14) 판정.

reports_evidence/cheonan_lease/ACCEPTANCE_CRITERIA.md 를 옮긴 것이다. 수정 전 결과에 먼저 돌려 고정했다.
조항 위치는 상수로 쓰지 않고 원문 문형으로 찾는다 — 회사명·조번호를 바꾼 변형에도 그대로 쓴다.
파이프라인 모듈은 쓰지 않는다(검증 대상 코드로 검증하지 않는다). 출력물만 본다.

Usage: python scripts/check_lease_acceptance.py RUN_DIR
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_freelancer_acceptance as base  # noqa: E402  (UI 표시 필터를 그대로 쓴다)

#: 요청 답변 행이 갖춰야 할 다섯 칸(UI 데이터 키, DOCX/PDF 표시 이름).
ANSWER_FIELDS = (
    ("judgment", "판단"), ("basis", "근거"), ("existing_protection", "기존 보호"),
    ("residual_risk", "남은 위험"), ("required_action", "필요 조치"),
)
#: 이 사례의 요청(검토요청서 번호 2~5) — 요청 원문 낱말로 찾는다.
REQUESTS = {
    "보증금": r"보증금에\s*대한\s*보호|보증금\s*보호",
    "연대보증": r"연대보증",
    "전대": r"전대",
    "투자비": r"투자비",
}


def _blob(f: dict) -> str:
    keys = ("issue_title", "problem", "rewrite_reason", "legal_business_reason", "suggested_rewrite",
            "loss_path_text", "our_company_risk")
    out = [str(f.get(k) or "") for k in keys]
    out += [str(d.get("issue_title") or "") for d in f.get("detected_issue_list") or [] if isinstance(d, dict)]
    return "\n".join(out)


def _lines(s: str) -> list[str]:
    return [ln.strip() for ln in str(s or "").splitlines() if ln.strip()]


def _row_text(r: dict) -> str:
    return "\n".join(str(v) for v in r.values() if isinstance(v, (str, int, float)))


def _request_blocks(report: str) -> dict[str, str]:
    """보고서에서 요청별 답변 블록. '요청' 으로 시작하는 줄부터 다음 '요청' 줄 앞까지."""
    lines = report.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"\s*(?:요청\s*\d+|요청사항)\s*[.:)]?", ln)]
    blocks: dict[str, str] = {}
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else min(len(lines), i + 40)
        head = lines[i]
        body = "\n".join(lines[i:end])
        for key, rx in REQUESTS.items():
            if key not in blocks and re.search(rx, head):
                blocks[key] = body
    return blocks


def check(run: Path) -> dict:
    deep = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))
    review = deep.get("review") or {}
    meta = review.get("clause_meta") or {}
    rd = lambda n: (run / n).read_text(encoding="utf-8") if (run / n).exists() else ""  # noqa: E731
    docx, pdf, clean = rd("05_report.txt"), rd("06_report.txt"), rd("08_clean.txt")
    src = "\n".join(str(c.get("text") or "") for c in review.get("original_clauses") or [])
    findings = base._final_findings(review)
    all_blob = "\n".join(_blob(f) for f in findings)
    coverage = [r for r in meta.get("user_review_coverage") or [] if isinstance(r, dict)]
    cov_blob = "\n".join(_row_text(r) for r in coverage)
    exec_blob = json.dumps(review.get("executive_summary") or {}, ensure_ascii=False)
    res: dict[str, dict] = {}

    # L1 — 거래 분류
    t = re.search(r"계약유형:\s*([^\n]+)", docx)
    me = re.search(r"우리 측 지위:\s*([^\n]+)", docx)
    cp = re.search(r"상대방:\s*([^\n]+)", docx)
    bad = []
    if not t or not re.search(r"(?:부동산|상가|건물)[^\n]{0,6}임대차", t.group(1)) or re.search(r"렌탈", t.group(1)):
        bad.append(f"계약유형={t.group(1) if t else '없음'}")
    if not me or "임차인" not in me.group(1):
        bad.append(f"우리 측 지위={me.group(1) if me else '없음'}")
    if not cp or re.search(r"계약은|임대차\s*계약", cp.group(1)):
        bad.append(f"상대방={cp.group(1) if cp else '없음'}")
    roles = [str(p.get("role") or "") for p in (meta.get("party_map") or {}).get("parties") or [] if isinstance(p, dict)]
    if any(re.search(r"공급자|구매자|판매자", r) for r in roles):
        bad.append(f"당사자 역할={roles}")
    res["L1"] = {"pass": not bad, "evidence": bad}

    # L2 — 무관 전문 규칙
    rx_foreign = re.compile(
        r"대리점(?!법,)|위탁\s*판매|제품\s*렌탈|렌탈료|세금계산서\s*발행\s*주체|고객\s*계약\s*당사자|대금청구/수금"
        r"|하도급법:\s*사실확인|표시광고법:\s*(?:일부\s*)?적용|산업안전|중대재해|제조물|소비자\s*클레임|과징금")
    hits = []
    for name, body in (("UI", all_blob + "\n" + cov_blob), ("요약", exec_blob), ("DOCX", docx), ("PDF", pdf)):
        for ln in _lines(body):
            if ln.startswith("비적용으로 판단한 법률"):
                continue
            m = rx_foreign.search(ln)
            if m:
                hits.append(f"{name}: …{ln[max(0, m.start() - 20): m.end() + 20]}…")
    res["L2"] = {"pass": not hits, "evidence": hits[:12]}

    # L3 — 보호수단별 실효성 평가(보고서 문장 단위)
    rep = docx + "\n" + pdf
    devices = {
        "근저당": (r"근저당", r"선순위|후순위|순위|채권최고액|낙찰|경매|배당"),
        "예금질권": (r"질권", r"승낙|확정일자|상계|인출|해지|재예치|제3채무자"),
        "상계": (r"상계", r"차임|월\s*임대료|남은|소멸|종료|경매|작동"),
        "연대보증": (r"연대\s*보증|보증인", r"최고액|서면|자력|한도|범위|재산"),
    }
    bad = []
    for name, (dev, cue) in devices.items():
        ok = any(re.search(dev, ln) and re.search(cue, ln) and re.search(r"평가|작동|한계|부족|공백|조건|확인|위험|회수", ln)
                 for ln in _lines(rep))
        if not ok:
            bad.append(f"{name} 실효성 평가 없음")
    res["L3"] = {"pass": not bad, "evidence": bad}

    # L4 — 보증금 회수 vs 영업 지속·투자비 회수
    bad = []
    if not any(re.search(r"영업\s*(?:지속|중단|계속)|임차권[^\n]{0,30}(?:소멸|대항)", ln) for ln in _lines(rep)):
        bad.append("영업 지속(임차권 존속) 위험 미구분")
    inv = [ln for ln in _lines(rep) if re.search(r"투자비", ln)]
    if not any(re.search(r"무담보|담보[^\n]{0,10}(?:없|되지)|자력|회수[^\n]{0,15}(?:불확실|보장되지|어렵)|별도", ln) for ln in inv):
        bad.append("투자비 회수 가능성(무담보·자력 의존) 미평가")
    # 부정문("…확보됐다는 뜻은 아니다")은 확보 판단이 아니다 — 2026-10-30 정밀도 수정(기준 자체는 그대로).
    if any(re.search(r"투자비[^\n]{0,40}(?:회수가?\s*확보|보전이?\s*확보|보호된다)", ln)
           and not re.search(r"아니다|않는다|않다|없다", ln) for ln in _lines(rep)):
        bad.append("손해배상 약정 존재를 투자비 회수 확보로 판단")
    res["L4"] = {"pass": not bad, "evidence": bad}

    # L5 — 주차장 담보가치 vs 사용권
    park = [ln for ln in _lines(rep + "\n" + cov_blob) if "주차장" in ln]
    bad = []
    if not any(re.search(r"담보\s*가치|지분|감정", ln) for ln in park):
        bad.append("주차장 담보가치 미평가")
    if not any(re.search(r"사용\s*(?:권|승인|승낙)", ln) and re.search(r"승계|공유|양수인|대항|동의|제3자", ln) for ln in park):
        bad.append("주차장 사용권(승계·공유) 미평가")
    for r in coverage:
        if "주차장" in str(r.get("original_user_text") or "") and re.search(r"적정|커버", str(r.get("review_status") or "") + str(r.get("direct_answer") or "")[:30]):
            bad.append(f"주차장 요청 '{r.get('review_status')}' 판정")
    res["L5"] = {"pass": not bad, "evidence": bad}

    # L6 — 자료 없이 회수 가능성 확정 금지
    bad = []
    if not re.search(r"등기사항\s*전부\s*증명서|등기부", rep):
        bad.append("등기부 등 필요 자료 미제시")
    m = re.search(r"(?:보증금|회수)[^\n.]{0,30}(?:전액\s*)?(?:보장된다|보장됨|확보되어\s*있|확보됨|문제\s*없|충분히\s*담보)", rep)
    if m:
        bad.append(f"단정: {m.group(0)}")
    res["L6"] = {"pass": not bad, "evidence": bad}

    # L7 — 수정안 전부 반영본에서 기존 보호 보존
    keep = {
        "근저당": r"근저당권", "질권": r"질권", "상계권 불행사 확약": r"상계권\s*불행사",
        "기한도래 간주": r"기한이\s*도래한\s*것으로\s*본다", "상계": r"월\s*임대료를[^\n]{0,20}상계",
        "대위변제": r"대신\s*변제", "연대보증": r"연대하여\s*보증", "주차장 사용 승인": r"주차장\s*사용을\s*승인",
        "계약금 반환": r"계약금\s*전액을\s*즉시\s*반환",
    }
    bad = []
    if not clean:
        bad.append("수정안 반영본(08_clean) 없음")
    for name, rx in keep.items():
        if re.search(rx, src) and not re.search(rx, clean):
            bad.append(f"반영본에서 '{name}' 삭제")
    res["L7"] = {"pass": not bad, "evidence": bad}

    # L8 — 요청 직접 답변(UI 데이터 + 보고서)
    bad = []
    blocks = _request_blocks(docx)
    for key, rx in REQUESTS.items():
        rows = [r for r in coverage if re.search(rx, str(r.get("original_user_text") or ""))]
        full = [r for r in rows if all(str(r.get(k) or "").strip() for k, _ in ANSWER_FIELDS)]
        if not full:
            bad.append(f"[UI] 요청 '{key}' — 판단/근거/기존 보호/남은 위험/필요 조치 중 빈 칸")
        blk = blocks.get(key, "")
        missing = [lab for _, lab in ANSWER_FIELDS if not re.search(rf"{lab}\s*:\s*\S", blk)]
        if missing:
            bad.append(f"[DOCX] 요청 '{key}' 답변 칸 누락: {missing}")
        if re.search(r"찾지\s*못했습니다", blk):
            bad.append(f"[DOCX] 요청 '{key}' — 조항을 찾지 못했다는 답")
        if key == "보증금":
            j = "\n".join(_row_text(r) for r in full) + blk
            if not re.search(r"근저당|질권", j):
                bad.append("보증금 요청 답에 근저당·질권 평가 없음")
            if re.search(r"인도\s*지연|렌트\s*프리", "\n".join(str(r.get("judgment") or "") for r in full)):
                bad.append("보증금 요청을 인도 지연 의견으로 대체")
    res["L8"] = {"pass": not bad, "evidence": bad}

    # L9 — 미답변인데 검토완료 표시 금지
    unanswered = any(
        not all(str(r.get(k) or "").strip() for k, _ in ANSWER_FIELDS)
        for r in coverage if r.get("source") in ("explicit_user_request", "user_request", "deal_request")
    ) or bool(res["L8"]["evidence"])
    status = str(meta.get("review_status") or "")
    bad = []
    if unanswered and re.search(r"검토\s*완료", docx + pdf):
        bad.append("미답변 요청이 있는데 보고서에 '검토완료'")
    if unanswered and status in ("", "OK", "REVIEW_OK", "COMPLETE", "REVIEW_COMPLETE"):
        bad.append(f"미답변 요청이 있는데 review_status='{status}'")
    res["L9"] = {"pass": not bad, "evidence": bad}

    # L10 — HIGH 마다 손실 경로
    bad = []
    for f in findings:
        if not base._is_high(f):
            continue
        lp = f.get("loss_path") or {}
        if not (isinstance(lp, dict) and lp.get("event") and lp.get("failed_protection") and lp.get("loss")):
            bad.append(f"{f.get('clause_id')} HIGH 손실 경로 없음")
        if re.search(r"과징금", _blob(f)):
            bad.append(f"{f.get('clause_id')} 과징금 근거 HIGH")
    res["L10"] = {"pass": not bad, "evidence": bad}

    # L11 — HIGH 없음 ≠ 안전
    m = re.search(r"안전한\s*계약|문제\s*없는\s*계약|리스크\s*없음|위험\s*없음", docx + pdf)
    res["L11"] = {"pass": not m, "evidence": [m.group(0)] if m else []}

    # L12 — 일관성
    bad = []
    ui_h, ui_m = base._ui_header_counts(review)  # 데모 UI 상단 '필수수정=N 권장=M'
    for name, body in (("DOCX", docx), ("PDF", pdf)):
        mm = re.search(r"HIGH\s*(\d+)\s*건\s*\|\s*MEDIUM\s*(\d+)\s*건", body)
        if not mm:
            bad.append(f"{name} 건수 줄 없음")
        elif (int(mm.group(1)), int(mm.group(2))) != (ui_h, ui_m):
            bad.append(f"{name} HIGH {mm.group(1)}/MEDIUM {mm.group(2)} ≠ UI {ui_h}/{ui_m}")
    core = [c for c in (meta.get("deal_assessment") or {}).get("core_risks") or [] if isinstance(c, dict)]
    if not core:
        bad.append("거래 핵심 위험 없음(deal_assessment.core_risks)")
    for c in core:
        title = str(c.get("title") or "")[:14]
        if title and (title not in docx or title not in pdf):
            bad.append(f"핵심 위험 '{title}' DOCX/PDF 누락")
    res["L12"] = {"pass": not bad, "evidence": bad}

    # L13 — 핵심 위험 이력
    trace = meta.get("core_risk_trace") or {}
    bad = []
    if not isinstance(trace, dict) or not trace.get("risks"):
        bad.append("core_risk_trace 없음")
    else:
        for r in trace.get("risks") or []:
            for ev in r.get("events") or []:
                if ev.get("change") in ("removed", "downgraded", "hidden") and not str(ev.get("reason") or "").strip():
                    bad.append(f"{r.get('id')}: {ev.get('stage')} {ev.get('change')} 사유 없음")
            if r.get("final_state") in ("missing", "hidden") and not r.get("restored"):
                bad.append(f"{r.get('id')}: 최종 출력에서 빠짐")
    res["L13"] = {"pass": not bad, "evidence": bad}

    # L14 — 수정안 전체 반영 검증
    rsc = meta.get("revision_set_check") or {}
    bad = []
    if not rsc:
        bad.append("revision_set_check 없음")
    if rsc and "protections_checked" not in rsc:
        bad.append("기존 보호 보존 검사 기록 없음")
    for h in rsc.get("held") or []:
        if not str(h.get("reason") or "").strip():
            bad.append(f"{h.get('display_path')} 보류 사유 없음")
        elif str(h.get("reason"))[:20] not in docx:
            bad.append(f"{h.get('display_path')} 보류 사유가 DOCX 에 없음")
    res["L14"] = {"pass": not bad, "evidence": bad}
    return res


def main() -> None:
    run = Path(sys.argv[1])
    res = check(run)
    out = {"run": str(run), "passed": sum(1 for v in res.values() if v["pass"]), "total": len(res), "results": res}
    (run / "acceptance.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for k, v in res.items():
        print(k, "PASS" if v["pass"] else "FAIL", "; ".join(v["evidence"])[:400])
    print(f"{out['passed']}/{out['total']}")


if __name__ == "__main__":
    main()
