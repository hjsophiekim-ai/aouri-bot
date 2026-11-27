"""검토서(화면·다운로드)·변경추적본 메모·앱 비교 화면(change_set)이 같은 판단을 말하는지 대조한다(2026-11-03 지시 4·5항).

Usage: python scripts/check_delivery_consistency.py RUN_DIR

RUN_DIR: ui_e2e_capture / e2e_upload_review_download 결과 폴더(04_review_deep.json, 07_redline.docx, 09_brief.txt).
판정 항목
  D1 화면 검토서와 다운로드 검토서의 쟁점 카드(번호·등급·조치·제목)가 같다
  D2 요청 답변이 중복 없이 한 번씩, 화면과 다운로드가 같은 건수, 상태는 반영/부분 반영/미반영/확인 필요 가운데 하나
  D3 Word 메모의 [등급 · 조치]가 같은 조항 검토서 카드의 등급·조치와 같다
  D4 앱 비교 화면(change_set) 카드의 등급·조치가 검토서 카드와 같다
  D5 결론의 '가장 큰 잔존 위험' 이 HIGH 카드(있으면)를 가리키고 근거를 적는다
  D6 사업부 결정사항에 상대방 동의·수용 여부, 법률 효력 확인이 없다
  D7 요청이 가리키는 쟁점 번호가 그 요청의 조항을 다루는 카드다
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ACTION_MAP = {"필수수정": "필수 수정", "권장수정": "협상 권고", "사업부 결정": "협상 권고", "체결 전 확인": "사실 확인", "현행 유지": "현행 유지"}
STATUSES = ("반영", "부분 반영", "미반영", "확인 필요")


def _lines(sections: list) -> list[str]:
    out = []
    for _h, rows in sections:
        for st, txt in rows:
            if st in ("h", "p", "k", "m"):
                out.append(str(txt))
    return out


def _cards(lines: list[str]) -> list[tuple[str, str, str, str]]:
    rx = re.compile(r"^(쟁점 \d+) \[([A-Z]+) · ([^\]]+)\] (.+?)(?: \[[^\]]+\])?$")
    return [m.groups() for ln in lines if (m := rx.match(ln.strip()))]


def _requests(lines: list[str]) -> list[str]:
    return [ln for ln in lines if re.match(r"^요청 \d+\. ", ln.strip())]


def _comments(docx: Path) -> list[str]:
    if not docx.exists():
        return []
    with zipfile.ZipFile(docx) as z:
        if "word/comments.xml" not in z.namelist():
            return []
        x = z.read("word/comments.xml").decode("utf-8")
    out = []
    for c in re.findall(r"<w:comment\b.*?</w:comment>", x, re.S):
        paras = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in re.findall(r"<w:p\b.*?</w:p>", c, re.S)]
        out.append("\n".join(paras))
    return out


def main() -> int:
    run = Path(sys.argv[1])
    r = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))["review"]
    meta = r.get("clause_meta") or {}
    screen = _lines(meta.get("business_brief_sections") or [])
    down_txt = (run / "09_brief.txt").read_text(encoding="utf-8") if (run / "09_brief.txt").exists() else ""
    down = [ln for ln in down_txt.splitlines()]
    results: list[tuple[str, bool, str]] = []

    sc, dc = _cards(screen), _cards(down)
    results.append(("D1 화면·다운로드 쟁점 카드 동일", sc == dc and bool(sc),
                    f"화면 {len(sc)}건 / 다운로드 {len(dc)}건" + ("" if sc == dc else f" — 차이: {set(sc) ^ set(dc)}")))

    sr, dr = _requests(screen), _requests(down)
    def clause_of(line: str) -> str:
        m = re.search(r"제\s*(\d+(?:\.\d+)?)\s*조|Article\s+(\d+(?:\.\d+)?)", line)
        return (m.group(1) or m.group(2)) if m else ""
    keys = [clause_of(x) for x in sr]
    dup = sorted({k for k in keys if k and keys.count(k) > 1})
    bad_status = [x[:40] for x in sr if not re.search(r": \[(?:" + "|".join(STATUSES) + r")\]", x)]
    results.append(("D2 요청 한 번씩·상태 4종·화면=다운로드", not dup and not bad_status and len(sr) == len(dr) and bool(sr),
                    f"화면 {len(sr)}건 / 다운로드 {len(dr)}건, 중복 조항 {dup or '없음'}, 상태 없음 {bad_status or '없음'}"))

    card_by_clause: dict[str, set[tuple[str, str]]] = {}
    clause_lines = {}
    cur = None
    for ln in screen:
        m = re.match(r"^(쟁점 \d+) \[([A-Z]+) · ([^\]]+)\]", ln)
        if m:
            cur = m.groups()
            continue
        m2 = re.match(r"^관련 조항: (.+?)(?: — .*)?$", ln)
        if m2 and cur:
            for p in re.split(r",\s*", m2.group(1)):
                card_by_clause.setdefault(p.strip(), set()).add((cur[1], ACTION_MAP.get(cur[2], cur[2])))
                clause_lines.setdefault(cur[0], []).append(p.strip())
    mism = []
    comments = _comments(run / "07_redline.docx")
    for c in comments:
        m = re.match(r"\[([A-Z]+) · ([^\]]+)\] (.+)", c.splitlines()[0] if c else "")
        if not m:
            continue
        risk, act, path = m.groups()
        cards_here = card_by_clause.get(path.strip())
        if cards_here and (risk, act) not in cards_here:
            mism.append(f"{path}: 메모 [{risk} · {act}] vs 카드 {sorted(cards_here)}")
    results.append(("D3 Word 메모 등급·조치 = 검토서 카드", bool(comments) and not mism, f"메모 {len(comments)}건, 불일치 {mism or '없음'}"))

    cs = meta.get("change_set") or {}
    mism2 = []
    for card in cs.get("cards") or []:
        for f in card.get("findings") or []:
            c = card_by_clause.get(str(f.get("path")))
            if c and (f.get("risk"), f.get("action")) not in c:
                mism2.append(f"{f.get('path')}: 비교화면 [{f.get('risk')} · {f.get('action')}] vs 카드 {sorted(c)}")
    results.append(("D4 앱 비교 화면 등급·조치 = 검토서 카드", bool(cs.get("cards")) and not mism2,
                    f"비교 카드 {len(cs.get('cards') or [])}건, 불일치 {mism2 or '없음'}"))

    concl = next((ln for ln in screen if ln.startswith("가장 큰 잔존 위험")), "")
    m = re.search(r"(쟁점 \d+)", concl)
    high = [c for c in sc if c[1] == "HIGH"]
    ok5 = bool(m) and (not high or any(c[0] == m.group(1) for c in high)) and "근거:" in concl
    results.append(("D5 최대 잔존 위험 = HIGH 카드 + 근거", ok5, concl[:160]))

    decs = [ln for ln in screen if re.match(r"^결정 \d+ \[", ln)]
    badd = [d[:80] for d in decs if re.search(r"(?:동의|수용|수락)\s*여부|효력|적법", d)]
    results.append(("D6 결정사항에 상대방 동의·법률 효력 없음", not badd, f"결정 {len(decs)}건, 위반 {badd or '없음'}"))

    badlink = []
    for x in sr:
        k = clause_of(x)
        for no in re.findall(r"쟁점 \d+", x.split("→")[-1] if "→" in x else ""):
            cl = " ".join(clause_lines.get(no, []))
            if k and k not in cl:
                badlink.append(f"요청({k}) → {no}({cl})")
    results.append(("D7 요청 → 쟁점 연결이 같은 조항", not badlink, f"{badlink or '모두 일치'}"))

    ok_all = True
    for name, ok, detail in results:
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")
    print(f"{'ALL PASS' if ok_all else 'FAIL'} ({sum(ok for _, ok, _ in results)}/{len(results)})")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
