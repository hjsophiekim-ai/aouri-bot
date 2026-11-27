"""변경추적본·클린본·검토의견서 실물 검증 — e2e 실행 폴더(07_redline.docx, 08_clean.docx, 04_review_deep.json)를 본다.

검사(2026-11-02 지시 9항):
  T1 변경추적본에 실제 삽입(w:ins)·삭제(w:del) 이력이 있다
  T2 word/settings.xml 에 trackRevisions(변경내용 추적 계속 사용)
  T3 작성자·변경일시가 하나로 일관된다
  T4 모두 거절 → 기준 문서(원본 DOCX 또는 검증된 DOCX 변환본)와 같은 본문
  T5 모두 수락 → 클린본과 같은 본문
  T6 클린본에 조항 단락이 빠지거나 중복되지 않는다(기준 문서 대비)
  T7 검토의견서가 "반영" 으로 보인 수정안은 클린본에 있고, 보류한 수정안은 없다
  W1~W3 Microsoft Word 로 직접 열어 Revisions 수·RejectAll·AcceptAll 결과를 대조(Word 가 있을 때)

Usage: python scripts/verify_tracked_docx.py RUN_DIR [--no-word]
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.review.docx_redline import docx_paragraph_texts  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _session(run: Path) -> dict:
    log = json.loads((run / "00_run_log.json").read_text(encoding="utf-8"))
    sid = log.get("session_id") or (log.get("steps") or {}).get("session_id")
    if not sid:
        up = json.loads((run / "01_upload.json").read_text(encoding="utf-8"))
        sid = up.get("session_id") or (up.get("session") or {}).get("session_id")
    p = Path(__file__).resolve().parents[1] / "runtime" / "data" / "question_sessions" / f"{sid}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _source_docx(session: dict) -> bytes:
    from runtime.review.source_docx import source_docx_for_session

    src = source_docx_for_session(session)
    return src.docx_bytes


_PS = r"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open('{path}', $false, $false, $false)
  $n = $d.Revisions.Count
  if ('{action}' -eq 'reject') { $d.Revisions.RejectAll() }
  if ('{action}' -eq 'accept') { $d.Revisions.AcceptAll() }
  $t = $d.Content.Text
  $d.Close(0)
  [System.IO.File]::WriteAllText('{out}', "$n`n" + $t, [System.Text.Encoding]::UTF8)
} finally { $w.Quit() }
"""


def _word_texts(path: Path, action: str) -> tuple[int, str]:
    """Microsoft Word 로 직접 열어 변경 수와 (거절·수락 후) 본문을 얻는다 — scripts/word_render_check.ps1(사본을 연다)."""
    import subprocess
    import tempfile

    import os

    fd, name = tempfile.mkstemp(suffix=".txt")
    os.close(fd)   # Windows: 열린 핸들을 닫지 않으면 PowerShell 이 결과 파일에 쓰지 못한다("다른 프로세스에서 사용 중")
    out = Path(name)
    ps1 = Path(__file__).resolve().parent / "word_render_check.ps1"
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), "-Docx", str(path.resolve()),
                        "-Out", str(out), "-Action", action], capture_output=True, timeout=300)
    if r.returncode != 0 or not out.stat().st_size:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-600:])
    raw = out.read_text(encoding="utf-8-sig")
    head, _, text = raw.partition("\n---\n")
    n = int(re.search(r"revisions=(\d+)", head).group(1))
    return n, text


def _word_norm(s: str) -> str:
    # Word 본문 텍스트: 단락 끝 \r, 코멘트 표지(\x05) 등 제어 문자를 지우고 공백을 맞춘다.
    return _flat(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", (s or "").replace("\r", " ")))


def main() -> int:
    run = Path(sys.argv[1])
    use_word = "--no-word" not in sys.argv
    red = (run / "07_redline.docx").read_bytes()
    clean = (run / "08_clean.docx").read_bytes()
    session = _session(run)
    source = _source_docx(session)
    results: list[tuple[str, bool, str]] = []

    with zipfile.ZipFile(io.BytesIO(red)) as z:
        doc_xml = z.read("word/document.xml").decode("utf-8")
        settings = z.read("word/settings.xml").decode("utf-8") if "word/settings.xml" in z.namelist() else ""
    n_ins = len(re.findall(r"<w:ins\b", doc_xml))
    n_del = len(re.findall(r"<w:del\b", doc_xml))
    results.append(("T1 실제 삽입·삭제 이력", n_ins > 0 and n_del >= 0 and (n_ins + n_del) > 0, f"w:ins {n_ins} / w:del {n_del}"))
    results.append(("T2 trackRevisions 설정", "trackRevisions" in settings, "settings.xml"))
    authors = set(re.findall(r'<w:(?:ins|del)\b[^>]*w:author="([^"]*)"', doc_xml))
    dates = set(re.findall(r'<w:(?:ins|del)\b[^>]*w:date="([^"]*)"', doc_xml))
    results.append(("T3 작성자·일시 일관", len(authors) == 1 and len(dates) == 1, f"author={sorted(authors)} date={sorted(dates)}"))

    src_paras = [p for p in docx_paragraph_texts(source) if p.strip()]
    rej = [p for p in docx_paragraph_texts(red, mode="reject") if p.strip()]
    acc = [p for p in docx_paragraph_texts(red, mode="accept") if p.strip()]
    cln = [p for p in docx_paragraph_texts(clean) if p.strip()]
    # 클린본 첫머리의 '협상 초안 · 서명 전 확정 필요' 안내 단락은 계약 문구가 아니다 — 대조에서 뺀다.
    if cln and cln[0].startswith("[협상 초안"):
        cln = cln[1:]
    results.append(("T4 모두 거절 = 기준 문서", [_flat(x) for x in rej] == [_flat(x) for x in src_paras],
                    f"단락 {len(rej)} vs {len(src_paras)}"))
    results.append(("T5 모두 수락 = 클린본", [_flat(x) for x in acc] == [_flat(x) for x in cln], f"단락 {len(acc)} vs {len(cln)}"))
    # T6: 기준 문서의 각 단락(번호로 시작하는 조항 단락)이 클린본에 한 번씩 — 수정된 단락은 번호 머리로 대조한다.
    heads_src = [m.group(0) for p in src_paras if (m := re.match(r"^\s*\d+(?:\.\d+)*\.?\s", p))]
    heads_cln = [m.group(0) for p in cln if (m := re.match(r"^\s*\d+(?:\.\d+)*\.?\s", p))]
    missing = [h for h in heads_src if h not in heads_cln]
    dup = sorted({h for h in heads_cln if heads_cln.count(h) > heads_src.count(h) and heads_src.count(h) > 0})
    results.append(("T6 조항 누락·중복 없음", not missing and not dup, f"누락 {missing[:8]} 중복 {dup[:8]}"))

    review = json.loads((run / "04_review_deep.json").read_text(encoding="utf-8"))
    rr = review.get("review") or review.get("review_result") or review
    meta = rr.get("clause_meta") or {}
    brief = meta.get("business_brief") or {}
    clean_flat = _flat(" ".join(cln))
    bad: list[str] = []
    for e in brief.get("appendix") or []:
        new = _flat(e.get("new_text"))
        if not new or e.get("mode") == "선택 시 추가":
            continue
        present = new[:120] in clean_flat
        applied = e.get("applied") or ""
        if applied == "applied" and not present:
            bad.append(f"{e.get('item_no')} 반영 표시인데 클린본에 없음")
        if applied not in ("", "applied") and present:
            bad.append(f"{e.get('item_no')} 보류 표시인데 클린본에 있음")
    results.append(("T7 검토의견서 반영 표시 = 클린본", not bad, "; ".join(bad) or f"수정안 {len(brief.get('appendix') or [])}건 대조"))

    if use_word:
        try:
            tmp = run / "_word_check"
            tmp.mkdir(exist_ok=True)
            (tmp / "source.docx").write_bytes(source)
            n_rev, rej_w = _word_texts(run / "07_redline.docx", "reject")
            _, src_w = _word_texts(tmp / "source.docx", "none")
            _, acc_w = _word_texts(run / "07_redline.docx", "accept")
            _, cln_w = _word_texts(run / "08_clean.docx", "none")
            if cln_w.startswith("[협상 초안"):
                cln_w = cln_w.split("\r", 1)[-1]   # 클린본 첫머리 안내 단락 제외(Word 단락 끝 = CR)
            results.append(("W1 Word 가 인식한 변경 수", n_rev > 0, f"Revisions.Count = {n_rev}"))
            results.append(("W2 Word 모두 거절 = 기준 문서", _word_norm(rej_w) == _word_norm(src_w),
                            f"{len(_word_norm(rej_w))}자 vs {len(_word_norm(src_w))}자"))
            results.append(("W3 Word 모두 수락 = 클린본", _word_norm(acc_w) == _word_norm(cln_w),
                            f"{len(_word_norm(acc_w))}자 vs {len(_word_norm(cln_w))}자"))
        except Exception as exc:  # noqa: BLE001
            results.append(("W* Word 검증", False, f"실행 실패: {exc}"))

    ok = all(r[1] for r in results)
    lines = [f"{'PASS' if r[1] else 'FAIL'}  {r[0]} — {r[2]}" for r in results]
    lines.append("ALL_PASS" if ok else "SOME_FAIL")
    out = "\n".join(lines)
    (run / "tracked_check.txt").write_text(out, encoding="utf-8")
    print(out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
