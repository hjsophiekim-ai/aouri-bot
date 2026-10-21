"""변형 계약 e2e 결과의 불변 조건 판정 — 회사명·조항번호가 달라도 같은 판단이 나와야 한다.

Usage: python scripts/check_variant_invariants.py RUN_DIR KIND
  KIND = renamed_shifted | sufficient | ip_missing | other_type

판정은 출력물(04_review_deep.json · 05_report.txt · 06_report.txt)만 본다. 파이프라인 모듈은 쓰지 않는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _live(review: dict) -> list[dict]:
    out = []
    for it in review.get("clause_results") or []:
        if not isinstance(it, dict) or it.get("dedup_suppressed") or it.get("keep_as_is"):
            continue
        tier = str(it.get("risk_tier") or "").upper()
        if tier in ("HIGH", "MEDIUM") or it.get("approval_required") or it.get("high_risk"):
            out.append(it)
    return out


def main() -> None:
    run, kind = Path(sys.argv[1]), sys.argv[2]
    review = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8")).get("review") or {}
    docx = (run / "05_report.txt").read_text(encoding="utf-8") if (run / "05_report.txt").exists() else ""
    pdf = (run / "06_report.txt").read_text(encoding="utf-8") if (run / "06_report.txt").exists() else ""
    live = _live(review)
    blob = json.dumps(live, ensure_ascii=False)
    checks: list[tuple[str, bool, str]] = []

    def row(label: str) -> str:
        m = re.search(rf"{label}:\s*([^\n]+)", docx)
        return m.group(1) if m else "(행 없음)"

    checks.append(("문서 생성", bool(docx and pdf), f"docx={len(docx)} pdf={len(pdf)}"))
    checks.append(("'양도가 아니라 이용허락' 설명 없음", "양도가 아니라 이용허락" not in blob + docx, ""))
    checks.append(("조 번호 빠진 법령 인용 없음",
                   not re.search(r"(?:저작권법|민법|상법)\s*제\s*\d+\s*항", docx + pdf), ""))
    new_arts = [str((c.get("redline_instruction") or {}).get("new_article")) for c in live
                if (c.get("redline_instruction") or {}).get("new_article")]
    checks.append(("신설 조번호 중복 없음", len(new_arts) == len(set(new_arts)), f"{new_arts}"))
    checks.append(("'분석 신뢰도 %' 없음", not re.search(r"분석\s*신뢰도:\s*\d+%", docx + pdf), ""))
    checks.append(("개인정보 항목 HIGH 아님", not [c for c in live if "개인정보" in str(c.get("issue_title") or "")
                                             and str(c.get("risk_tier")).upper() == "HIGH"], ""))
    sec03 = docx.split("1. 계약 구조")[0]
    checks.append(("전반 검토 요청을 '적정'으로 답하지 않음(지적이 있을 때)",
                   not (live and "전반" in sec03 and re.search(r"판단:\s*적정", sec03)), ""))
    xref = [c for c in live if c.get("is_cross_reference_error")]
    two_deriv = [c for c in live if "2차적" in str(c.get("suggested_rewrite") or "")]
    if kind in ("renamed_shifted", "sufficient"):
        for label in ("산출물 지식재산권 귀속", "검수 기준", "대금 지급 조건"):
            checks.append((f"요약 {label} = 규정 있음", row(label).startswith("규정 있음"), row(label)[:60]))
    if kind == "renamed_shifted":
        checks.append(("상호참조 오류 지적(조번호 밀림 반영)", bool(xref) and xref[0].get("display_path") == "제3조 제2항",
                       str([c.get("display_path") for c in xref])))
        checks.append(("IP 보완은 IP 조(제9조)의 새 항", bool(two_deriv) and str(
            (two_deriv[0].get("redline_instruction") or {}).get("edit_location", "")).startswith("제9조 제"),
                       str([(c.get("redline_instruction") or {}).get("edit_location") for c in two_deriv])))
        checks.append(("당사자명 오염 없음(퍼시스·선샤인·하늘빛 미등장)",
                       not re.search(r"퍼시스|선샤인|하늘빛", blob + docx), ""))
    if kind == "sufficient":
        checks.append(("상호참조 오류 오탐 없음", not xref, str([c.get("display_path") for c in xref])))
        checks.append(("이미 있는 재가공·지급 전 이용권을 다시 제안하지 않음", not two_deriv,
                       str([c.get("clause_id") for c in two_deriv])))
    if kind == "ip_missing":
        checks.append(("요약 IP 귀속 ≠ 규정 있음", not row("산출물 지식재산권 귀속").startswith("규정 있음"),
                       row("산출물 지식재산권 귀속")[:60]))
        checks.append(("IP 귀속 공백을 지적", bool(re.search(r"지식재산|저작권|권리\s*(?:귀속|이전)", blob)), ""))
    ok = all(c[1] for c in checks)
    lines = [f"{'PASS' if c[1] else 'FAIL'}  {c[0]}" + (f"  — {c[2]}" if c[2] else "") for c in checks]
    (run / "variant_check.txt").write_text("\n".join(lines) + ("\nALL_PASS\n" if ok else "\nSOME_FAIL\n"), encoding="utf-8")
    print("\n".join(lines))
    print("ALL_PASS" if ok else "SOME_FAIL")


if __name__ == "__main__":
    main()
