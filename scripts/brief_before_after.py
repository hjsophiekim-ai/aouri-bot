"""수정 전(기본 다운로드 = 법무 상세 보고서) ↔ 수정 후(기본 다운로드 = 사업팀 전달본) 같은 잣대 비교.

Usage: python scripts/brief_before_after.py OUT.md RUN_LABEL:BEFORE_DIR:AFTER_DIR:KIND [...]
BEFORE_DIR 의 05_report.txt/06_report.pdf, AFTER_DIR 의 09_brief.txt/10_brief.pdf 와 05_report.txt(내부본)·08_clean.txt 를 읽는다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RX_CODES = re.compile(r"REVIEW_[A-Z_]+|STATUS_[A-Z_]+|\bKR-\d|\bclr_|\bdeal_|\bfnd_|\b(?:HIGH|MEDIUM|LOW)\b|AI\s*자체|자동\s*(?:검증|분석)|게이트|finding")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[“”\"'‘’]", "", s or ""))


def _pages(pdf: Path) -> int | str:
    try:
        import fitz

        with fitz.open(pdf) as d:
            return d.page_count
    except Exception:  # noqa: BLE001
        return "-"


def repeated(text: str) -> int:
    sents = [s.strip() for s in re.split(r"(?<=[.다])\s+|\n", text) if len(s.strip()) >= 40]
    seen: dict[str, int] = {}
    for s in sents:
        k = _norm(re.sub(r"^[^:]{1,12}:\s*", "", s))
        seen[k] = seen.get(k, 0) + 1
    return sum(n - 1 for n in seen.values() if n > 1)


def wrong_statutes(text: str, kind: str) -> list[str]:
    out = []
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "관련 법령" not in ln:
            continue
        ctx = " ".join(lines[max(0, i - 12):i])
        if kind == "lease":
            if "저작권법" in ln:
                out.append("저작권법 on lease: " + ln[:70])
            if "제667조" in ln:
                out.append("수급인 담보책임 on lease: " + ln[:70])
            if "제543조" in ln and "질권" in ctx:
                out.append("해지권 on 예금질권: " + ln[:70])
            if "제390조" in ln and re.search(r"보증금|연대보증|근저당", ctx) and "권리" not in ctx:
                out.append("권리보증 on 보증금·연대보증: " + ln[:70])
        elif re.search(r"민법 제(?:623|629|265|357|356|349|353)조", ln):
            out.append("lease/security statute on non-lease: " + ln[:70])
    return out


def truncated_rewrites(text: str) -> int:
    n, on = 0, False
    for ln in text.splitlines():
        if re.match(r"^(?:수정 문구|수정문안|반영 후 전체 문구)", ln.strip()):
            on = True
            continue
        if on and re.match(r"^(?:수정 이유|협상 포지션|\[|별첨 \d|미확정|현재 문구로)", ln.strip()):
            on = False
        if on and re.search(r"…|\.\.\.", ln):
            n += 1
    return n


def main() -> None:
    out_md = Path(sys.argv[1])
    rows = []
    for spec in sys.argv[2:]:
        label, before, after, kind = spec.split(":")
        b, a = Path(before), Path(after)
        bt = (b / "05_report.txt").read_text(encoding="utf-8")
        at = (a / "09_brief.txt").read_text(encoding="utf-8")
        ai = (a / "05_report.txt").read_text(encoding="utf-8")
        bclean = (b / "08_clean.txt").read_text(encoding="utf-8") if (b / "08_clean.txt").exists() else ""
        aclean = (a / "08_clean.txt").read_text(encoding="utf-8") if (a / "08_clean.txt").exists() else ""
        probes = {"연대보증 최고액": "이보증채무의최고액은", "주차장 승계": "제2호의사용승인을승계", "질권 같은 날": "같은날진행한다"}
        applied_b = [k for k, v in probes.items() if v in _norm(bclean)] if kind == "lease" and bclean else []
        applied_a = [k for k, v in probes.items() if v in _norm(aclean)] if kind == "lease" and aclean else []
        rows.append((label, "글자 수(기본 다운로드)", len(bt), len(at)))
        rows.append((label, "PDF 쪽수(기본 다운로드)", _pages(b / "06_report.pdf"), _pages(a / "10_brief.pdf")))
        rows.append((label, "40자 이상 문장 반복 횟수", repeated(bt), repeated(at)))
        rows.append((label, "내부 코드·AI 처리 표현 수", len(RX_CODES.findall(bt)), len(RX_CODES.findall(at))))
        rows.append((label, "잘린(…) 수정 문구 줄", truncated_rewrites(bt), truncated_rewrites(at)))
        rows.append((label, "무관한 법령 연결(내부 보고서 기준)", len(wrong_statutes(bt, kind)), len(wrong_statutes(ai, kind))))
        if kind == "lease" and (bclean or aclean):
            rows.append((label, "수정본에 실제 반영된 핵심 수정(3종)", ", ".join(applied_b) or "-", ", ".join(applied_a) or "-"))
    lines = ["| 사례 | 지표 | 수정 전 | 수정 후 |", "|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
