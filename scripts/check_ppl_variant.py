"""협찬(PPL) 변형 계약 e2e 결과 판정 — 회사명·조번호·보호조건·당사자 역할이 달라도 같은 판단이 나오는가.

Usage: python scripts/check_ppl_variant.py RUN_DIR KIND
  KIND = renamed_shifted | sufficient | missing | role_reversed
조항 위치는 원문 문형으로 찾는다. 파이프라인 모듈은 쓰지 않는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_freelancer_acceptance as base  # noqa: E402
import check_ppl_acceptance as ppl  # noqa: E402


def main() -> None:
    run, kind = Path(sys.argv[1]), sys.argv[2]
    review = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8")).get("review") or {}
    rd = lambda n: (run / n).read_text(encoding="utf-8") if (run / n).exists() else ""  # noqa: E731
    docx, pdf, clean = rd("05_report.txt"), rd("06_report.txt"), rd("08_clean.txt")
    findings = base._final_findings(review)
    blobs = {str(f.get("clause_id")): ppl._blob(f) for f in findings}
    allb = "\n".join(blobs.values())
    src_full = "\n".join(f"제{c.get('article_number')}조\n{c.get('text')}" for c in review.get("original_clauses") or []
                         if c.get("article_number"))
    checks: list[tuple[str, bool, str]] = []
    role = (re.search(r"우리 측 지위:\s*([^\n]+)", docx) or [None, ""])[1] if docx else ""
    ctype = (re.search(r"계약유형:\s*([^\n]+)", docx) or [None, ""])[1] if docx else ""
    checks.append(("계약유형 = 협찬·PPL(광고)", bool(re.search(r"협찬|PPL|광고", ctype)), ctype))
    has = lambda prefix: [c for c in blobs if c.startswith(prefix)]  # noqa: E731
    conflict = [f for f in findings if re.search(r"예정", ppl._blob(f)) and re.search(r"보장|개런티|최소", ppl._blob(f))]
    a_tent = ppl._art_of(src_full, r"예정에\s*해당")
    a_ip = ppl._art_of(src_full, r"사전\s*서면\s*합의를\s*거쳐야")

    if kind in ("renamed_shifted", "sufficient", "missing"):
        checks.append(("우리 측 지위 = 광고주(협찬사)", bool(re.search(r"광고주|협찬사", role)), role))
    if kind == "renamed_shifted":
        checks.append(("보장 vs 예정 충돌 HIGH, 바뀐 조번호에 앵커",
                       any(base._is_high(f) and str(f.get("article_number")) == a_tent for f in conflict),
                       f"예정 조항 제{a_tent}조"))
        lic = [f for f in findings if re.search(r"라이선스", ppl._blob(f)) and re.search(r"사전\s*서면\s*합의", ppl._blob(f))]
        checks.append(("라이선스 vs 별도 합의 충돌, 바뀐 조번호에 앵커",
                       any(str(f.get("article_number")) == a_ip for f in lic), f"제{a_ip}조"))
        checks.append(("이전 계약 당사자·브랜드명 혼입 없음", not re.search(r"시디즈|씨제이|CJ\s*ENM|알로소|적수다", allb + docx), ""))
    if kind == "sufficient":
        for prefix, label in (("sp_guarantee_vs_tentative", "보장 충돌"), ("sp_performance_guarantee", "성과 기준"),
                              ("sp_schedule_deadline", "최종 기한"), ("sp_payment_timing", "청구 시점"),
                              ("sp_license_vs_approval", "라이선스 승인"), ("sp_disclosure", "표시 책임")):
            checks.append((f"이미 있는 보호({label})를 다시 지적하지 않음", not has(prefix), str(has(prefix))))
        rep = [cid for cid, b in blobs.items() if re.search(r"조회\s*수[^\n]{0,40}(?:미달|보상|환급)", b) and base._is_high(
            next(f for f in findings if str(f.get("clause_id")) == cid))]
        checks.append(("조회수 미달 보상 공백을 HIGH 로 재지적하지 않음", not rep, str(rep)))
    if kind == "missing":
        perf = [f for f in findings if str(f.get("clause_id")).startswith("sp_performance_guarantee")]
        checks.append(("반환 조항이 없으면 성과 보장 지적이 HIGH", bool(perf) and base._is_high(perf[0]),
                       str([(f.get("clause_id"), f.get("risk_tier")) for f in perf])))
        checks.append(("불가항력 시 미제공분 반환 지적", bool(has("sp_force_majeure_refund")), ""))
        checks.append(("없는 반환 조항을 근거로 인용하지 않음",
                       not re.search(r"제\s*9\s*조\s*제\s*3\s*항|제\s*10\s*조\s*제\s*1\s*항", "\n".join(
                           str((f.get("redline_instruction") or {}).get("final_clause_text") or "") for f in findings)), ""))
    if kind == "role_reversed":
        checks.append(("우리 측 지위 = 제작·채널 운영사(협찬 수령)", bool(re.search(r"제작|채널|수령", role)), role))
        sponsor_side = [c for c in blobs if re.match(r"sp_(?:guarantee_vs|performance_guarantee|schedule|payment|license|disclosure)", c)]
        checks.append(("광고주 쪽 수정안을 내지 않음", not sponsor_side, str(sponsor_side)))
        checks.append(("우리가 지는 조회수 보장의 책임 범위를 지적", bool(has("sp_recipient_guarantee_exposure")), ""))
        rw = "\n".join(str((f.get("redline_instruction") or {}).get("final_clause_text") or f.get("suggested_rewrite") or "")
                       for f in findings)
        checks.append(("상대방(광고주) 권리를 강화하는 문안 없음",
                       not re.search(r"[‘'“\"]갑[’'”\"]의\s*사전\s*서면\s*동의\s*없이\s*이를\s*변경", rw), ""))
    checks.append(("조 번호가 빠진 법령 인용 없음", not re.search(r"(?:저작권법|민법|상법)\s*제\s*\d+\s*항", docx + pdf), ""))
    if clean:
        checks.append(("반영본에 비계약 표지 없음", "추가 권고" not in clean, ""))
    ok = all(c[1] for c in checks)
    lines = [f"{'PASS' if c[1] else 'FAIL'}  {c[0]}" + (f"  — {c[2]}" if c[2] else "") for c in checks]
    (run / "variant_check.txt").write_text("\n".join(lines) + ("\nALL_PASS\n" if ok else "\nSOME_FAIL\n"), encoding="utf-8")
    print("\n".join(lines))
    print("ALL_PASS" if ok else "SOME_FAIL")


if __name__ == "__main__":
    main()
