"""상가 임대차 변형 계약 e2e 결과 판정 — 회사명·조번호·담보 수준·당사자 역할이 달라도 같은 판단이 나오는가.

Usage: python scripts/check_lease_variant.py RUN_DIR KIND
  KIND = renamed_shifted | sufficient | missing | role_reversed
조항 위치는 원문 문형으로 찾는다. 파이프라인 모듈은 쓰지 않는다(출력물만 본다).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_freelancer_acceptance as base  # noqa: E402
import check_lease_acceptance as lease  # noqa: E402


def _art_of(src_full: str, rx: str) -> str:
    m = re.search(rx, src_full)
    if not m:
        return ""
    heads = [(h.start(), h.group(1)) for h in re.finditer(r"(?m)^제\s*(\d+)\s*조", src_full)]
    return next((n for pos, n in reversed(heads) if pos <= m.start()), "")


def main() -> None:
    run, kind = Path(sys.argv[1]), sys.argv[2]
    review = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8")).get("review") or {}
    meta = review.get("clause_meta") or {}
    rd = lambda n: (run / n).read_text(encoding="utf-8") if (run / n).exists() else ""  # noqa: E731
    docx, pdf, clean = rd("05_report.txt"), rd("06_report.txt"), rd("08_clean.txt")
    findings = base._final_findings(review)
    blobs = {str(f.get("clause_id")): lease._blob(f) for f in findings}
    allb = "\n".join(blobs.values())
    src_full = "\n".join(f"제{c.get('article_number')}조\n{c.get('text')}" for c in review.get("original_clauses") or []
                         if c.get("article_number"))
    checks: list[tuple[str, bool, str]] = []
    ctype = (re.search(r"계약유형:\s*([^\n]+)", docx) or [None, ""])[1]
    role = (re.search(r"우리 측 지위:\s*([^\n]+)", docx) or [None, ""])[1]
    checks.append(("계약유형 = 부동산 임대차", bool(re.search(r"(?:부동산|상가|건물)[^\n]{0,6}임대차", ctype)), ctype))
    highs = [f for f in findings if base._is_high(f)]
    deposit_high = [f for f in highs if re.search(r"보증금", lease._blob(f)) and re.search(r"회수|무담보", lease._blob(f))]
    a_mort = _art_of(src_full, r"근저당권자로")
    a_dep = _art_of(src_full, r"보증금은\s*금")
    a_guar = _art_of(src_full, r"연대하여\s*보증")

    if kind in ("renamed_shifted", "sufficient", "missing"):
        checks.append(("우리 측 지위 = 임차인", "임차인" in role, role))
    if kind == "renamed_shifted":
        checks.append(("보증금 회수 HIGH 가 바뀐 조번호(근저당 조항)에 앵커",
                       any(str(f.get("article_number")) == a_mort for f in deposit_high), f"근저당 조항 제{a_mort}조"))
        g = [f for f in highs if re.search(r"보증", str(f.get("issue_title") or "")) and re.search(r"최고액", lease._blob(f))]
        checks.append(("연대보증 최고액 HIGH 가 바뀐 조번호에 앵커",
                       any(str(f.get("article_number")) == a_guar for f in g), f"보증 조항 제{a_guar}조"))
        checks.append(("주차장 사용권 지적", any("주차장" in str(f.get("issue_title") or "") for f in findings), ""))
        checks.append(("이전 계약 당사자·지명 혼입 없음",
                       not re.search(r"가람개발|일룸|남궁민|가온리|가온읍", allb + docx + pdf), ""))
        checks.append(("요청 답변 5칸", not lease.check(run)["L8"]["evidence"], "; ".join(lease.check(run)["L8"]["evidence"])[:200]))
    if kind == "sufficient":
        checks.append(("보증금 회수 HIGH 없음(1순위·전액 담보)", not deposit_high, str([f.get("clause_id") for f in deposit_high])))
        checks.append(("보증 최고액 지적 없음(금액 특정됨)",
                       not any(re.search(r"최고액", lease._blob(f)) for f in findings), ""))
        checks.append(("주차장 승계 지적 없음(승계 포함·단독 소유)",
                       not any(re.search(r"승계", str(f.get("issue_title") or "")) for f in findings), ""))
        checks.append(("거래 전체 판단은 유지(체결 전 확인 자료 제시)", bool(re.search(r"등기사항\s*전부\s*증명서", docx)), ""))
        checks.append(("HIGH 없음을 안전으로 표시하지 않음",
                       not re.search(r"안전한\s*계약|문제\s*없는\s*계약|위험\s*없음", docx + pdf), ""))
    if kind == "missing":
        checks.append(("보증금 무담보 HIGH, 보증금 조항에 앵커",
                       any(str(f.get("article_number")) == a_dep for f in deposit_high), f"보증금 조항 제{a_dep}조"))
    if kind == "role_reversed":
        checks.append(("우리 측 지위 = 임대인", "임대인" in role, role))
        checks.append(("보증금 회수 위험을 우리 위험으로 쓰지 않음", not deposit_high, str([f.get("clause_id") for f in deposit_high])))
        rows = [r for r in meta.get("user_review_coverage") or [] if isinstance(r, dict) and r.get("source") == "deal_request"
                and re.search(r"담보|부담", str(r.get("original_user_text") or ""))]
        checks.append(("담보 제공 부담 요청에 5칸 답", bool(rows) and all(
            str(rows[0].get(k) or "").strip() for k, _ in lease.ANSWER_FIELDS), str(rows[:1])[:160]))
        checks.append(("담보를 '우리 보호'로 읽지 않음",
                       not re.search(r"■\s*근저당권[^\n]*— (?:작동|일부만)", docx), ""))
    ok = all(c[1] for c in checks)
    for name, passed, ev in checks:
        print(("PASS " if passed else "FAIL ") + name + (f" — {ev}" if ev and not passed else ""))
    (run / f"variant_{kind}.json").write_text(json.dumps(
        {"kind": kind, "passed": ok, "checks": [{"name": n, "pass": p, "evidence": e} for n, p, e in checks]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("ALL PASS" if ok else "SOME FAIL")


if __name__ == "__main__":
    main()
