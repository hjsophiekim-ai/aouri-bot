"""변경 묶음(화면 데이터) ↔ 변경추적본 ↔ 클린본 ↔ 기준 문서 대조 — 2026-11-02 지시 5항.

  C1 모든 삽입·삭제가 실제 Word 메모 범위 안에 있다(메모 없는 변경 없음), 메모 작성자 = 아우리봇, 메모에 수정 이유/위험/미확정 조건
  C2 변경·메모 작성자가 '아우리봇' 하나
  C3 변경하지 않은 단락은 기준 문서와 XML 이 같다(수정 대상 밖 내용·서식 불변)
  C4 화면 카드의 수정 전 = 변경추적본 모두 거절 본문(같은 단락 범위), 수정 후 = 클린본 같은 단락
  C5 수정 전 조항 원문(카드)이 기준 문서에 그대로 있다 — 원문 매칭
  C6 클린본에 같은 긴 문장이 기준 문서·추가 문구보다 많이 나오지 않는다(중복 삽입 없음)
  C7 숫자·금액·통화·기간: 기준 문서의 값은 삭제 표시된 것 말고는 클린본에 그대로, 클린본의 새 값은 추가 표시에만
  C8 추가 문구의 참조 조항(Article/clause N.N)이 문서에 실재
  C9 추가 문구의 정의어(대문자 복합어)가 문서에 있거나 미확정 조건으로 표시됨
  C10 미확정 값([●])이 있으면 화면 데이터 draft=True·클린본 첫머리 안내·변경추적본 안내 메모
  C11 자동 적용 보류·PDF 변환 대조 문제가 화면 데이터 warnings 에 표시됨
  C12 검토 설명이 요구한 조치가 수정 문구에 반영됐거나 미반영 사유가 있다(조항 지목 요청 검토)
  C13 위험등급 건수(화면 상단) = 카드·보류·확인사항 합계, HIGH 는 '필수 수정' 에만

Usage: python scripts/verify_change_set.py RUN_DIR [--input ORIGINAL_FILE]
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.review.docx_redline import W, _accept_all, _reject_all  # noqa: E402
from runtime.review.docx_splice import flat, is_inserted_paragraph, paragraph_segments, range_segments  # noqa: E402

_RX_TERMS = re.compile(
    r"\d+(?:[.,]\d+)*\s*%|(?:EUR|USD|KRW|€|\$|₩)\s*[\d.,]+\d|[\d.,]*\d\s*(?:원|유로|달러)"
    r"|\b\d+\s*(?:days?|weeks?|months?|years?|일|주|개월|년)\b", re.I)


def _doc(b: bytes) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        return ET.fromstring(z.read("word/document.xml"))


def _part(b: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        return z.read(name) if name in z.namelist() else b""


def _ptext(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.iter(f"{W}t"))


def _terms(s: str) -> list[str]:
    return [re.sub(r"\s+", "", m.group(0)) for m in _RX_TERMS.finditer(s or "")]


def _source_bytes(run: Path, inp: Path | None) -> bytes:
    from runtime.review.source_docx import source_docx_for_session

    if inp is not None:
        from runtime.review.text_extract import extract_text_from_file
        import base64
        rr = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))["review"]
        sess = {"text": extract_text_from_file(inp).text, "input": {"filename": inp.name}, "review_result": rr}
        if inp.suffix.lower() == ".docx":
            sess["original_docx_b64"] = base64.b64encode(inp.read_bytes()).decode()
        return source_docx_for_session(sess).docx_bytes
    sys.path.insert(0, str(ROOT / "scripts"))
    from verify_tracked_docx import _session, _source_docx
    return _source_docx(_session(run))


def main() -> int:
    run = Path(sys.argv[1])
    inp = Path(sys.argv[sys.argv.index("--input") + 1]) if "--input" in sys.argv else None
    red_b = (run / "07_redline.docx").read_bytes()
    cln_b = (run / "08_clean.docx").read_bytes()
    src_b = _source_bytes(run, inp)
    rr = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))["review"]
    meta = rr.get("clause_meta") or {}
    cs = meta.get("change_set") or {}
    res: list[tuple[str, bool, str]] = []

    red = _doc(red_b)
    # ── C1·C2 메모 ──
    comments = ET.fromstring(_part(red_b, "word/comments.xml") or b"<w:comments xmlns:w='%s'/>" % W[1:-1].encode())
    cmap = {c.get(f"{W}id"): (c.get(f"{W}author"), "\n".join(_ptext(p) for p in c.iter(f"{W}p")))
            for c in comments.iter(f"{W}comment")}
    open_ids: set[str] = set()
    orphan = 0
    total = 0
    used: set[str] = set()
    for el in red.iter():
        if el.tag == f"{W}commentRangeStart":
            open_ids.add(el.get(f"{W}id"))
        elif el.tag == f"{W}commentRangeEnd":
            open_ids.discard(el.get(f"{W}id"))
        elif el.tag in (f"{W}ins", f"{W}del") and el.find(f"{W}r") is not None:
            total += 1
            if not open_ids:
                orphan += 1
            used |= open_ids
    change_comments = [cmap[i] for i in used if i in cmap]
    bad_body = [t[:40] for a, t in change_comments if not all(k in t for k in ("수정 이유", "위험", "미확정 조건"))]
    res.append(("C1 모든 변경에 실제 Word 메모(변경 범위)", total > 0 and orphan == 0 and not bad_body,
                f"변경 {total}건 · 메모 밖 {orphan}건 · 메모 {len(cmap)}개 · 형식 미달 {bad_body[:3]}"))
    authors = {e.get(f"{W}author") for e in red.iter() if e.tag in (f"{W}ins", f"{W}del")} | {a for a, _ in cmap.values()}
    res.append(("C2 작성자 = 아우리봇", authors == {"아우리봇"}, f"{sorted(a or '' for a in authors)}"))

    # ── C3 변경 없는 단락의 XML 불변 ──
    src = _doc(src_b)
    sp = list(src.iter(f"{W}p"))
    rp = [p for p in red.iter(f"{W}p") if not is_inserted_paragraph(p)]

    def _norm_xml(p: ET.Element) -> str:
        q = ET.fromstring(ET.tostring(p))
        for parent in list(q.iter()):
            for ch in list(parent):
                if ch.tag in (f"{W}commentRangeStart", f"{W}commentRangeEnd") or (
                        ch.tag == f"{W}r" and ch.find(f"{W}commentReference") is not None):
                    parent.remove(ch)
        return ET.tostring(q, encoding="unicode")

    changed_xml = 0
    untouched = 0
    if len(sp) != len(rp):
        res.append(("C3 수정 대상 밖 내용·서식 불변", False, f"단락 수 다름 {len(sp)} vs {len(rp)}"))
    else:
        for a, b in zip(sp, rp):
            if any(e.tag in (f"{W}ins", f"{W}del") for e in b.iter()):
                continue
            untouched += 1
            if _norm_xml(a) != _norm_xml(b):
                changed_xml += 1
        res.append(("C3 수정 대상 밖 내용·서식 불변", changed_xml == 0, f"변경 없는 단락 {untouched}개 중 XML 달라진 단락 {changed_xml}개"))

    # ── C4·C5 화면 카드 = 파일 ──
    rpar = list(red.iter(f"{W}p"))
    cln = _doc(cln_b)
    cpar = list(cln.iter(f"{W}p"))
    banner = bool(cpar) and _ptext(cpar[0]).startswith("[협상 초안")
    if banner:
        cpar = cpar[1:]
    acc_par = list(_accept_all(ET.fromstring(ET.tostring(red))).iter(f"{W}p"))
    src_flat = flat(" ".join(_ptext(p) for p in sp))
    mism: list[str] = []
    nomatch: list[str] = []
    for c in cs.get("cards") or []:
        lo, hi = c["para_range"]
        segs = range_segments(rpar[lo:hi + 1])
        if segs != c["segments"]:
            mism.append(f"{c['id']} 조각")
        after_file = "\n".join(_ptext(p) for p in cpar[lo:hi + 1])
        after_acc = "\n".join(_ptext(p) for p in acc_par[lo:hi + 1])
        if flat(after_file) != flat(c["after"]) or flat(after_acc) != flat(c["after"]):
            mism.append(f"{c['id']} 수정 후")
        if flat(c["before"]) and flat(c["before"]) not in src_flat:
            nomatch.append(c["id"])
    res.append(("C4 화면 변경 전·후 = 변경추적본·클린본", bool(cs.get("cards")) and not mism,
                f"카드 {len(cs.get('cards') or [])}개 · 불일치 {mism}"))
    res.append(("C5 카드 원문이 기준 문서에 그대로 있음", not nomatch, f"매칭 실패 {nomatch}"))

    # ── C6 중복 문장 ──
    # 추가 조각끼리는 문장 경계로 잇는다 — 공백으로 이으면 서로 다른 추가의 끝·첫 낱말이 붙어 "Customer If" 같은 가짜 낱말 묶음이 된다.
    plus = " | ".join(t for c in cs.get("cards") or [] for op, t in c["segments"] if op == "+")
    pool = src_flat + " " + flat(plus)
    sents = [s.strip() for s in re.split(r"(?<=[.;:])\s+", flat(" ".join(_ptext(p) for p in cpar))) if len(s.strip()) >= 60]
    dups = sorted({s[:50] for s in sents if sents.count(s) > max(1, pool.count(s))})
    res.append(("C6 클린본 문장 중복 없음", not dups, f"{dups[:3]}"))

    # ── C7 숫자·금액·기간 ──
    deleted = " ".join(t for c in cs.get("cards") or [] for op, t in c["segments"] if op == "-")
    src_terms, cln_terms = _terms(src_flat), _terms(" ".join(_ptext(p) for p in cpar))
    lost = [t for t in set(src_terms) if cln_terms.count(t) < src_terms.count(t) - _terms(deleted).count(t)]
    new = [t for t in set(cln_terms) if cln_terms.count(t) > src_terms.count(t) + _terms(plus).count(t)]
    res.append(("C7 숫자·금액·통화·기간 보존", not lost and not new, f"사라진 값 {lost[:5]} · 출처 없는 새 값 {new[:5]}"))

    # ── C8 참조 조항 ──
    nums = set(re.findall(r"(?m)^\s*(\d{1,2}(?:\.\d{1,2})?)\b", "\n".join(_ptext(p) for p in sp)))
    refs = set(re.findall(r"(?:Article|clause|Section)\s+(\d{1,2}(?:\.\d{1,2})?)", plus, re.I))
    bad_refs = sorted(r for r in refs if r not in nums and r.split(".")[0] not in nums)
    res.append(("C8 추가 문구의 참조 조항 실재", not bad_refs, f"참조 {sorted(refs)} · 없는 조항 {bad_refs}"))

    # ── C9 정의어 ──
    und = " ".join(u for c in cs.get("cards") or [] for u in c.get("undecided") or [])
    # 항목 소제목("(a) Order Fulfillment:")은 정의어가 아니다.
    terms = {m.group(0) for m in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b(?!\s*:)", plus)}
    # 소제목 안의 낱말 묶음("(c) After-Sales Service Parts:" 의 "Sales Service")도 정의어가 아니다.
    heads = re.findall(r"\(\s*[a-z0-9]{1,3}\s*\)\s*([A-Z][A-Za-z\-/ ]{2,60}):", plus)
    # 문장 가운데 대문자로 쓴 낱말 하나(정의어 꼴, 예: "its Affiliates")도 — 기준 문서나 추가 문구 안의 정의("Affiliates" shall
    # mean / means)에 없으면 정의 없는 용어다(2026-11-03 제12조: 정의 수정만 보류돼 클린본에 정의 없는 Affiliates 가 남음).
    clean_plus = " ".join(_ptext(p) for p in cpar)
    for m in re.finditer(r"\b(?:its|their|any|such|all|our|each)\s+([A-Z][a-z]{3,})\b(?!\s+of\b)", plus):
        w = m.group(1)
        if w in src_flat or w in und:
            continue
        defined = re.search(rf"[\"“']{w}[\"”']\s+(?:shall\s+mean|means)", clean_plus)
        if not defined:
            terms.add(w)
    undefined = sorted(t for t in terms if t not in src_flat and t not in und and not any(t in h for h in heads))
    res.append(("C9 추가 문구 정의어 = 계약 정의어(아니면 미확정 표시)", not undefined, f"{undefined[:6]}"))

    # ── C10 미확정 값 표시 ──
    blanks = "[●]" in plus or bool(und.strip())
    guide = any("협상 초안" in t for _, t in cmap.values())
    ok10 = (not blanks) or (cs.get("draft") and banner and guide)
    res.append(("C10 미확정 값 → 화면·클린본·변경추적본 표시", bool(ok10),
                f"미확정 {'있음' if blanks else '없음'} · draft={cs.get('draft')} · 클린본 안내={banner} · 메모 안내={guide}"))

    # ── C11 보류·변환 문제 표시 ──
    held = cs.get("held") or []
    ver = (cs.get("source") or {}).get("verification") or {}
    need = bool(held) or bool(ver.get("missing") or ver.get("duplicated"))
    shown = bool(cs.get("warnings")) if need else True
    res.append(("C11 매칭 실패·변환 누락이 화면 데이터에 표시", shown, f"보류 {len(held)} · 변환 {ver} · 경고 {len(cs.get('warnings') or [])}"))

    # ── C12 설명의 조치 ↔ 수정 문구 ──
    gaps: list[str] = []
    for cr in rr.get("clause_results") or []:
        if not cr.get("is_requested_clause_review") or cr.get("dedup_suppressed"):
            continue
        for g in cr.get("measure_gaps") or []:
            gaps.append(f"{cr.get('display_path')}: {str(g)[:60]}")
        for m in cr.get("measures") or []:
            if not m.get("reflected") and not str(m.get("not_reflected_reason") or "").strip():
                gaps.append(f"{cr.get('display_path')}: {str(m.get('measure'))[:40]}")
    res.append(("C12 설명의 조치가 수정 문구에 반영(또는 미반영 사유)", not gaps, f"{sorted(set(gaps))[:6]}"))

    # ── C13 건수·등급 ──
    counts = cs.get("counts") or {}
    fs = [f for c in cs.get("cards") or [] for f in c["findings"]] + held + [
        c for c in cs.get("confirmations") or [] if c.get("action") != "현행 유지"]
    # 쟁점 단위(요청 하나 = 한 건, 등급은 그 쟁점의 최고 등급) — 화면 상단 건수와 검토의견서 쟁점 수가 같은 단위다.
    from runtime.review.change_set import issue_key
    best: dict[str, str] = {}
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for f in fs:
        k = issue_key(f)
        if f.get("risk") in rank and rank[f["risk"]] < rank.get(best.get(k, ""), 3):
            best[k] = f["risk"]
    calc = {k: sum(1 for v in best.values() if v == k) for k in ("HIGH", "MEDIUM", "LOW")}
    high_bad = [f.get("path") for f in fs if f.get("risk") == "HIGH" and f.get("action") != "필수 수정"]
    res.append(("C13 건수 일치·HIGH 는 필수 수정만", calc == counts and not high_bad, f"화면 {counts} · 계산 {calc} · HIGH 아닌 조치 {high_bad}"))

    ok = all(r[1] for r in res)
    out = "\n".join(f"{'PASS' if r[1] else 'FAIL'}  {r[0]} — {r[2]}" for r in res) + ("\nALL_PASS" if ok else "\nSOME_FAIL")
    (run / "change_set_check.txt").write_text(out, encoding="utf-8")
    print(out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
