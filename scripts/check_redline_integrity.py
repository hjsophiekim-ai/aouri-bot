"""수정안 무결성 기계 검사 — redline_e2e.py 결과 JSON 을 받아 지시 6항 ①~⑩ 중 기계로 볼 수 있는 항목을 판정한다.

Usage: python scripts/check_redline_integrity.py RESULT.json [RESULT2.json ...]  → 표(markdown) 출력
같은 모델의 자기선언을 쓰지 않는다 — 원문·다운로드 파일을 직접 대조한다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.review import redline_integrity as ri  # noqa: E402

W = lambda s: " ".join(str(s or "").split())  # noqa: E731
BANNER = re.compile(r"^\[협상 초안|DRAFT FOR NEGOTIATION")


def active(e: dict) -> bool:
    return bool(e.get("edit")) and not e.get("held") and e.get("tier") in ("HIGH", "MEDIUM")


def check(path: Path) -> list[tuple[str, str, str]]:
    r = json.loads(path.read_text(encoding="utf-8"))
    text = r.get("contract_text") or ""
    wt = W(text)
    eng = ri.is_english(text)
    req = " ".join(f"{k} {v}" for k, v in (r.get("questions") or {}).items())
    cvals = ri.values(text) | ri.values(req)
    edits = [e for e in r.get("edits") or [] if active(e)]
    rows: list[tuple[str, str, str]] = []

    def row(no: str, ok: bool | None, detail: str) -> None:
        rows.append((no, "통과" if ok else ("미실행" if ok is None else "실패"), detail))

    # ① 인용 원문이 실제 파일에 있는가
    bad = [e["path"] for e in edits if e["rewrite"] and W(e["original"])[:120] not in wt]
    row("① 원문 인용 일치", not bad, f"교체 수정 {len([e for e in edits if e['rewrite']])}건, 원문 불일치 {bad}")
    # ② 부재 지적 — 같은 주제 조항이 있는데 '없다' 로 남은 active finding
    absent = []
    for e in edits:
        if ri._ABSENCE.search(e["reason"]):
            for name, in_c, in_f in ri.TOPICS:
                if re.search(in_f, e["reason"][:200], re.I) and re.search(in_c, text, re.I) and not e["path"]:
                    absent.append(f"{name}")
    row("② 부재 지적 재확인", not absent, f"원문에 있는데 없다고 남은 지적: {absent}")
    # ③ 요청 답
    req_rows = [tx for h, rs in r.get("business_brief_sections") or [] for st, tx in rs if re.match(r"^요청\s*\d+\.", tx)]
    row("③ 요청별 답변", bool(req_rows), f"요청 답 {len(req_rows)}건")
    # ⑤·⑦ 기존 문구 삭제·하위 항목 파손
    lost = []
    for e in edits:
        if e["rewrite"] and e["original"]:
            d = ri.diff(e["original"], e["rewrite"])
            if (d.deleted or d.rewritten) and not ri._DELETE_INTENT.search(e["reason"]):
                lost.append(e["path"])
            om = re.findall(r"(?m)^\s*(\([a-z]\)|[①-⑳])", e["original"])
            nm = re.findall(r"(\([a-z]\)|[①-⑳])", e["rewrite"])
            if [m for m in om if m not in nm]:
                lost.append(e["path"] + " 하위항목")
    row("⑤ 기존 권리·문구 보존", not lost, f"이유 없는 삭제·하위 항목 손실: {lost}")
    # ⑥ 미합의 값 확정
    inv = []
    for e in edits:
        new = e["rewrite"] or e["addition"]
        for v in ri.values(new) - ri.values(e["original"]):
            if v not in cvals:
                inv.append(f"{e['path']}:{v}")
    row("⑥ 미합의 값 임의 확정", not inv, f"원문·요청·답변에 없는 값: {inv}")
    # 언어·호칭
    lang = [e["path"] for e in edits if eng and re.search(r"[가-힣]", e["rewrite"] + e["addition"])]
    loc = [e["location"] for e in edits if eng and re.search(r"제\s*\d+\s*조", e["location"])]
    row("④ 계약 언어·위치 정합", not lang and not loc, f"영문 계약 국문 삽입 {lang}, 국문 조 위치 {loc}")
    # ⑦ 번호 정합 — 수락본에서 같은 항 번호 중복
    acc = r.get("redline_accept") or []
    nums = [m.group(1) for p in acc for m in [re.match(r"^\s*(\d{1,2}\.\d{1,2}|제\s*\d+\s*조(?:의\d+)?)\s", p)] if m]
    dup = sorted({n for n in nums if nums.count(n) > 1})
    row("⑦ 번호·참조 정합", not dup, f"수락본 중복 번호: {dup}")
    # ⑧·⑨ Word 수락=clean, 거절=원문
    clean = [p for p in r.get("clean_paras") or [] if not BANNER.search(p)]
    row("⑧ 화면·Word·clean 일치(수락본=clean)", (W(" ".join(acc)) == W(" ".join(clean))) if r.get("clean_status") == 200 else None,
        f"수락본 {len(acc)}단락 / clean {len(clean)}단락 (clean 상태 {r.get('clean_status')})")
    rej = r.get("redline_reject") or []
    stray = [p[:60] for p in rej if W(p) and W(p)[:80] not in wt and not re.fullmatch(r"[\d\s./\-–:]+", W(p))]
    row("⑨ 전부 거절 = 기준 원문", not stray, f"원문에 없는 거절본 단락 {len(stray)}개 {stray[:3]}")
    # ⑩ 중요 위험이 남았는데 서명 가능 표시
    verdict = next((tx for h, rs in r.get("business_brief_sections") or [] for st, tx in rs if tx.startswith("판단:")), "")
    high = [e for e in r.get("edits") or [] if e["tier"] == "HIGH" and not e.get("keep")]
    row("⑩ 중요 위험 vs 판정", not (high and re.search(r"서명\s*가능|문제\s*없", verdict)), f"{verdict} / 남은 HIGH {len(high)}건")
    return rows


def main() -> int:
    out = []
    for p in sys.argv[1:]:
        out.append(f"\n### {Path(p).name}\n\n| 항목 | 결과 | 근거 |\n|---|---|---|")
        for no, res, det in check(Path(p)):
            out.append(f"| {no} | {res} | {det.replace('|', '/')[:300]} |")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
