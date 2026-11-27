"""변경추적을 걸 원본 DOCX — DOCX 업로드는 그 파일, PDF·HWP·텍스트 업로드는 검증된 추출 텍스트로 만든 변환본.

2026-11-02 지시 6항: 원본이 PDF 이면 PDF 에 Word 변경추적을 직접 적용한 것처럼 표시하지 않는다. 텍스트·조항을
검증하여 DOCX 로 변환한 뒤 그 변환본을 기준으로 변경추적을 적용했다고 밝힌다. 변환·위치 대조가 불확실한 부분은
자동 적용을 보류하고 그 범위를 알린다.

종전에는 PDF 세션에서 변경추적본·클린본 다운로드가 400("DOCX 파일로 업로드한 세션만 지원")으로 막혀, PDF 로 받은
계약서에는 수정안을 반영한 Word 파일을 줄 수 없었다.
"""
from __future__ import annotations

import base64
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

_RX_PAGE = re.compile(r"^\s*\[페이지\s*\d+\]\s*$")
#: 새 단락을 여는 줄 — 조항 번호, 항목 기호, 목록 번호.
_RX_PARA_START = re.compile(
    r"^\s*(?:\d{1,3}(?:\s?\.\s?\d{1,3}){0,3}\.?\s+\S|(?:Article|Section)\s+\d|제\s*\d+\s*조|[①-⑳]|"
    r"[•▪◦■○●\-–]\s|\[[ivxlc]+\]|[a-z]\]\s|\(\s*[a-z0-9]{1,3}\s*\)\s|_{5,}|[가-하]\.\s)",
    re.IGNORECASE,
)
#: 조 제목 줄 — 굵게.
_RX_HEADING = re.compile(r"^\s*(?:\d{1,2}\.\s+[A-Z가-힣][^.;:]{0,90}|(?:Article|Section)\s+\d{1,3}\b[^.;:]{0,90}|"
                         r"제\s*\d+\s*조(?:\s*\([^)]{0,40}\))?)\s*$")


@dataclass
class SourceDocx:
    docx_bytes: bytes
    converted: bool
    source_kind: str = "docx"
    notice: str = ""
    verification: dict[str, Any] = field(default_factory=dict)


def _paragraphs(text: str) -> list[str]:
    paras: list[str] = []
    cur: list[str] = []
    for raw in str(text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if _RX_PAGE.match(line):
            continue
        if not line:
            # 빈 줄 뒤가 같은 문장의 이어지는 줄(소문자로 시작)이면 단락을 끊지 않는다 — PDF 조판의 빈 줄이 문장을 둘로
            # 나누면 수정 대상 문장이 두 단락에 걸쳐 변경추적을 넣을 수 없다(2026-11-02 Norden 제12조).
            if cur and cur[-1] != "\x00":
                cur.append("\x00")
            continue
        if cur and cur[-1] == "\x00":
            cur.pop()
            if not re.match(r"^[a-z(]", line):
                paras.append(" ".join(cur))
                cur = []
        if cur and (_RX_PARA_START.match(line) or _RX_HEADING.match(" ".join(cur))):
            paras.append(" ".join(cur))
            cur = []
        cur.append(line)
    if cur and cur[-1] == "\x00":
        cur.pop()
    if cur:
        paras.append(" ".join(cur))
    return [re.sub(r"\s{2,}", " ", p).strip() for p in paras if p.strip()]


def _p_xml(text: str, *, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return (f'<w:p><w:pPr><w:spacing w:after="120"/></w:pPr><w:r>{rpr}'
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


_CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
       '<Default Extension="xml" ContentType="application/xml"/>'
       '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
       '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
       '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
       '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
       '</Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
         '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
         '</Relationships>')
_DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
             '</Relationships>')
_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Malgun Gothic"/>'
           '<w:sz w:val="20"/></w:rPr></w:rPrDefault></w:docDefaults></w:styles>')
_SETTINGS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')


def build_docx_from_text(text: str, *, title: str = "", description: str = "") -> bytes:
    body = "".join(_p_xml(p, bold=bool(_RX_HEADING.match(p))) for p in _paragraphs(text))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1440" w:right="1200" w:bottom="1440" w:left="1200"/></w:sectPr></w:body></w:document>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:title>{escape(title)}</dc:title><dc:description>{escape(description)}</dc:description>'
            '</cp:coreProperties>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/settings.xml", _SETTINGS)
        z.writestr("docProps/core.xml", core)
    return buf.getvalue()


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def verify_conversion(docx_bytes: bytes, clauses: list[dict[str, Any]] | None) -> dict[str, Any]:
    """조항마다 원문이 변환본에 빠짐없이·한 번만 들어갔는지 본다."""
    from runtime.review.docx_redline import docx_paragraph_texts

    full = _flat(" ".join(docx_paragraph_texts(docx_bytes)))
    missing: list[str] = []
    duplicated: list[str] = []
    checked = 0
    for c in clauses or []:
        t = _flat(c.get("text") if isinstance(c, dict) else getattr(c, "text", ""))
        path = str((c.get("display_path") if isinstance(c, dict) else getattr(c, "display_path", "")) or "")
        if len(t) < 20:
            continue
        checked += 1
        probe = t[:160]
        n = full.count(probe)
        if n == 0:
            missing.append(path)
        elif n > 1 and len(probe) >= 60:
            duplicated.append(path)
    return {"clauses_checked": checked, "missing": missing, "duplicated": duplicated,
            "ok": not missing and not duplicated}


def source_docx_for_session(doc: dict[str, Any]) -> SourceDocx | None:
    """세션의 변경추적 기준 문서. 없으면 None."""
    b64 = doc.get("original_docx_b64")
    if b64:
        return SourceDocx(docx_bytes=base64.b64decode(b64), converted=False)
    text = str(doc.get("text") or "")
    if not text.strip():
        return None
    fname = str(((doc.get("input") or {}).get("filename")) or "")
    kind = fname.rsplit(".", 1)[-1].lower() if "." in fname else "text"
    rr = doc.get("review_result") if isinstance(doc.get("review_result"), dict) else {}
    clauses = rr.get("original_clauses") or doc.get("original_clauses") or []
    notice = (f"이 문서는 원본 {kind.upper()} 에서 텍스트를 추출·검증해 만든 DOCX 변환본입니다. 변경내용 추적은 이 변환본을 "
              f"기준으로 적용했습니다 — {kind.upper()} 원본 자체에 적용한 것이 아닙니다. 서명본은 원본과 대조해 확정하십시오.")
    data = build_docx_from_text(text, title=fname, description=notice)
    ver = verify_conversion(data, clauses)
    if not ver["ok"]:
        notice += (" 변환본에서 원문을 확인하지 못한 조항: " + ", ".join(ver["missing"][:10])
                   + ("; 중복: " + ", ".join(ver["duplicated"][:10]) if ver["duplicated"] else ""))
    return SourceDocx(docx_bytes=data, converted=True, source_kind=kind, notice=notice, verification=ver)


__all__ = ["SourceDocx", "build_docx_from_text", "source_docx_for_session", "verify_conversion"]
