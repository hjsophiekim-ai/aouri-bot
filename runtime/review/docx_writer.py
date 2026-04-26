from __future__ import annotations

import difflib
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("w", W_NS)


_WORD_XML_MARKERS = (
    "<w:",
    "</w:",
    "w:rPr",
    "w:pPr",
    "w:ins",
    "w:del",
    "w:delText",
    "<?xml",
    "xmlns:w=",
)


def _contains_wordprocessingml_markers(text: str) -> bool:
    s = text or ""
    if not s:
        return False
    return any(m in s for m in _WORD_XML_MARKERS)


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _ensure_safe_text(s: str) -> str:
    if _contains_wordprocessingml_markers(s):
        raise ValueError("WordprocessingML markers detected in docx content text")
    return s


def _p(parent: ET.Element) -> ET.Element:
    return ET.SubElement(parent, _w("p"))


def _r(
    parent: ET.Element,
    *,
    bold: bool = False,
    underline: bool = False,
    strike: bool = False,
    color_hex: str | None = None,
    highlight: str | None = None,
) -> ET.Element:
    r = ET.SubElement(parent, _w("r"))
    rpr = None
    if (
        bold
        or underline
        or strike
        or (isinstance(color_hex, str) and color_hex.strip())
        or (isinstance(highlight, str) and highlight.strip())
    ):
        rpr = ET.SubElement(r, _w("rPr"))
    if bold and rpr is not None:
        ET.SubElement(rpr, _w("b"))
    if underline and rpr is not None:
        u = ET.SubElement(rpr, _w("u"))
        u.set(_w("val"), "single")
    if strike and rpr is not None:
        ET.SubElement(rpr, _w("strike"))
    if isinstance(color_hex, str) and color_hex.strip() and rpr is not None:
        c = ET.SubElement(rpr, _w("color"))
        c.set(_w("val"), color_hex.strip())
    if isinstance(highlight, str) and highlight.strip() and rpr is not None:
        h = ET.SubElement(rpr, _w("highlight"))
        h.set(_w("val"), highlight.strip())
    return r


def _t(parent: ET.Element, text: str) -> ET.Element:
    t = ET.SubElement(parent, _w("t"))
    t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = _ensure_safe_text(text)
    return t


def _split_lines(s: str) -> list[str]:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return [x for x in (x.strip() for x in s.split("\n")) if x]


def _norm_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _words(s: str) -> list[str]:
    t = _norm_text(s)
    if not t:
        return []
    return re.findall(r"\S+|\s+", t)


def _diff_runs(original: str, revised: str) -> list[tuple[str, dict[str, Any]]]:
    a = _words(original)
    b = _words(revised)
    sm = difflib.SequenceMatcher(a=a, b=b)
    out: list[tuple[str, dict[str, Any]]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            s = "".join(a[i1:i2])
            if s:
                out.append((s, {}))
        elif tag == "insert":
            s = "".join(b[j1:j2])
            if s:
                out.append((s, {"color_hex": "D64545", "underline": True}))
        elif tag == "delete":
            s = "".join(a[i1:i2])
            if s:
                out.append((s, {"color_hex": "D64545", "strike": True}))
        elif tag == "replace":
            s_del = "".join(a[i1:i2])
            if s_del:
                out.append((s_del, {"color_hex": "D64545", "strike": True}))
            s_ins = "".join(b[j1:j2])
            if s_ins:
                out.append((s_ins, {"color_hex": "D64545", "underline": True}))
    merged: list[tuple[str, dict[str, Any]]] = []
    for text, style in out:
        if not text:
            continue
        if merged and merged[-1][1] == style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    return merged


def _extract_law_titles(cr: dict[str, Any], *, limit: int = 3) -> list[str]:
    law = cr.get("related_laws")
    out: list[str] = []
    if isinstance(law, dict) and isinstance(law.get("results"), dict):
        for k in ("laws", "precedents", "interpretations"):
            arr = law["results"].get(k)
            if isinstance(arr, list):
                for it in arr:
                    if isinstance(it, dict) and isinstance(it.get("title"), str) and it["title"].strip():
                        t = it["title"].strip()
                        if t not in out:
                            out.append(t)
                    if len(out) >= limit:
                        return out
    return out[:limit]


def _summarize_change_points(original: str, revised: str, *, limit: int = 4) -> tuple[list[str], list[str]]:
    a = [x for x in re.findall(r"[0-9A-Za-z가-힣]+", _norm_text(original)) if x]
    b = [x for x in re.findall(r"[0-9A-Za-z가-힣]+", _norm_text(revised)) if x]
    sm = difflib.SequenceMatcher(a=a, b=b)
    added: list[str] = []
    removed: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            for w in b[j1:j2]:
                if w not in added:
                    added.append(w)
                if len(added) >= limit:
                    break
        if tag in ("delete", "replace"):
            for w in a[i1:i2]:
                if w not in removed:
                    removed.append(w)
                if len(removed) >= limit:
                    break
        if len(added) >= limit and len(removed) >= limit:
            break
    return added[:limit], removed[:limit]

def _tbl(parent: ET.Element, *, col_widths: list[int]) -> ET.Element:
    tbl = ET.SubElement(parent, _w("tbl"))
    tbl_pr = ET.SubElement(tbl, _w("tblPr"))
    tbl_w = ET.SubElement(tbl_pr, _w("tblW"))
    tbl_w.set(_w("w"), "0")
    tbl_w.set(_w("type"), "auto")
    grid = ET.SubElement(tbl, _w("tblGrid"))
    for w in col_widths:
        gc = ET.SubElement(grid, _w("gridCol"))
        gc.set(_w("w"), str(int(w)))
    return tbl


def _tc(parent_tr: ET.Element, *, width: int) -> ET.Element:
    tc = ET.SubElement(parent_tr, _w("tc"))
    tc_pr = ET.SubElement(tc, _w("tcPr"))
    tcw = ET.SubElement(tc_pr, _w("tcW"))
    tcw.set(_w("w"), str(int(width)))
    tcw.set(_w("type"), "dxa")
    return tc


@dataclass(frozen=True)
class DocxFile:
    filename: str
    content: bytes


def build_revision_docx(
    *,
    entity: str,
    contract_type: str,
    filename: str | None,
    original_clauses: list[dict[str, Any]],
    clause_results: list[dict[str, Any]],
) -> bytes:
    contract_name = filename or "미상"
    counterparty = "미상"

    orig_by_id: dict[str, dict[str, Any]] = {}
    for c in original_clauses:
        if isinstance(c, dict) and isinstance(c.get("clause_id"), str) and str(c.get("clause_id") or "").strip():
            _ensure_safe_text(str(c.get("clause_id") or ""))
            _ensure_safe_text(str(c.get("clause_title") or ""))
            _ensure_safe_text(str(c.get("text") or ""))
            orig_by_id[str(c.get("clause_id"))] = c

    cr_by_id: dict[str, dict[str, Any]] = {}
    for cr in clause_results:
        if isinstance(cr, dict) and isinstance(cr.get("clause_id"), str):
            cr_by_id[str(cr.get("clause_id"))] = cr

    for cid, cr in cr_by_id.items():
        oc = orig_by_id.get(cid)
        if oc is None:
            raise ValueError(f"clause_id not found in original_clauses: {cid}")
        ot = str(oc.get("clause_title") or "").strip()
        rt = str(cr.get("clause_title") or "").strip()
        if ot and rt and ot != rt:
            raise ValueError(f"clause_title mismatch for {cid}")

    changed_clause_ids: list[str] = []
    for cid, oc in orig_by_id.items():
        cr = cr_by_id.get(cid)
        if not cr:
            continue
        sr = cr.get("suggested_rewrite")
        if not (isinstance(sr, str) and sr.strip()):
            continue
        if _norm_text(sr) == _norm_text(str(oc.get("text") or "")):
            continue
        changed_clause_ids.append(cid)

    title = "아우리봇 계약 검토·수정본 (법무팀 검토용)"
    meta = [
        f"계약명: {contract_name}",
        f"상대방: {counterparty}",
        f"법인: {entity}",
        f"계약유형: {contract_type}",
    ]

    doc = ET.Element(_w("document"))
    body = ET.SubElement(doc, _w("body"))

    p0 = _p(body)
    r0 = _r(p0, bold=True)
    _t(r0, title)
    for m in meta:
        pm = _p(body)
        rm = _r(pm)
        _t(rm, m)
    _p(body)

    high_risk_rows: list[dict[str, str]] = []
    approval_rows: list[dict[str, str]] = []
    for cid in changed_clause_ids:
        cr = cr_by_id.get(cid) or {}
        if bool(cr.get("high_risk")):
            high_risk_rows.append({"clause_id": cid, "title": str(cr.get("clause_title") or "")})
        if bool(cr.get("approval_required")):
            approval_rows.append({"clause_id": cid, "title": str(cr.get("clause_title") or "")})

    sec_sum = _p(body)
    _t(_r(sec_sum, bold=True), "1) 표지/요약")
    ps = _p(body)
    _t(_r(ps), f"핵심 변경 조항 수: {len(changed_clause_ids)}")
    ps2 = _p(body)
    _t(_r(ps2), f"High risk 조항 수: {len(high_risk_rows)} / Approval required 조항 수: {len(approval_rows)}")
    if changed_clause_ids:
        ph = _p(body)
        _t(_r(ph, bold=True), "핵심 리스크 요약:")
        for cid in changed_clause_ids[:8]:
            cr = cr_by_id.get(cid) or {}
            oc = orig_by_id.get(cid) or {}
            head = (cid + " " + str(oc.get("clause_title") or "")).strip()
            issues = cr.get("detected_issue_list") if isinstance(cr.get("detected_issue_list"), list) else []
            it = ""
            for x in issues:
                if isinstance(x, dict) and isinstance(x.get("issue_title"), str) and x["issue_title"].strip():
                    it = x["issue_title"].strip()
                    break
            rr = cr.get("rewrite_reason")
            line = f"- {head}: {it or (str(rr)[:60] if isinstance(rr, str) else '리스크/보완 필요')}"
            pl = _p(body)
            _t(_r(pl), line)
    _p(body)

    sec_red = _p(body)
    _t(_r(sec_red, bold=True), "2) 본문 redline 버전 (변경 조항만 표시)")
    if not changed_clause_ids:
        pnone = _p(body)
        _t(_r(pnone), "변경된 조항이 없습니다.")
    for cid in changed_clause_ids:
        oc = orig_by_id.get(cid) or {}
        cr = cr_by_id.get(cid) or {}
        ctitle = str(oc.get("clause_title") or "")
        head = (cid + " " + ctitle).strip() if (cid or ctitle) else "조항"
        ph = _p(body)
        _t(_r(ph, bold=True), head)

        original_text = str(oc.get("text") or "")
        revised_text = str(cr.get("suggested_rewrite") or "")
        pr = _p(body)
        for text, style in _diff_runs(original_text, revised_text):
            rr = _r(
                pr,
                bold=bool(style.get("bold")),
                underline=bool(style.get("underline")),
                strike=bool(style.get("strike")),
                color_hex=style.get("color_hex"),
                highlight=style.get("highlight"),
            )
            _t(rr, text)
        _p(body)

    sec_app = _p(body)
    _t(_r(sec_app, bold=True), "3) 조항별 수정 사유 부록 (변경 조항)")
    tbl = _tbl(body, col_widths=[1200, 1800, 1800, 2400, 1600])

    def add_row(cells: list[list[tuple[str, dict[str, Any]]]]) -> None:
        tr = ET.SubElement(tbl, _w("tr"))
        for i, paras in enumerate(cells):
            tc = _tc(tr, width=int([1200, 1800, 1800, 2400, 1600][i] if i < 5 else 1800))
            for text, style in paras:
                pp = _p(tc)
                rr = _r(
                    pp,
                    bold=bool(style.get("bold")),
                    underline=bool(style.get("underline")),
                    strike=bool(style.get("strike")),
                    color_hex=style.get("color_hex"),
                    highlight=style.get("highlight"),
                )
                _t(rr, text)

    add_row(
        [
            [("조항", {"bold": True})],
            [("원문 요지", {"bold": True})],
            [("수정 포인트", {"bold": True})],
            [("수정 이유", {"bold": True})],
            [("관련 법령", {"bold": True})],
        ]
    )
    for cid in changed_clause_ids:
        oc = orig_by_id.get(cid) or {}
        cr = cr_by_id.get(cid) or {}
        ctitle = str(oc.get("clause_title") or "")
        left = (cid + " " + ctitle).strip() if (cid or ctitle) else "조항"

        original_text = str(oc.get("text") or "")
        revised_text = str(cr.get("suggested_rewrite") or "")
        rr = str(cr.get("rewrite_reason") or "").strip() if isinstance(cr.get("rewrite_reason"), str) else ""
        laws = _extract_law_titles(cr, limit=3)
        added, removed = _summarize_change_points(original_text, revised_text, limit=4)
        change_points = []
        if removed:
            change_points.append("삭제/완화: " + ", ".join(removed))
        if added:
            change_points.append("추가/강화: " + ", ".join(added))
        cp_text = " / ".join(change_points)[:240] if change_points else "-"

        gist = _norm_text(original_text)
        gist = gist[:220] + ("…" if len(gist) > 220 else "")

        add_row(
            [
                [(left, {})],
                [(gist, {})],
                [(cp_text, {})],
                [(rr[:260] + ("…" if len(rr) > 260 else ""), {})] if rr else [("(사유 없음)", {})],
                [(" / ".join(laws), {})] if laws else [("-", {})],
            ]
        )

    sec_hr = _p(body)
    _t(_r(sec_hr, bold=True), "4) High risk / Approval required 표 (변경 조항)")
    tbl2 = _tbl(body, col_widths=[1200, 4200, 1200])

    def add_row2(cells: list[tuple[str, dict[str, Any]]]) -> None:
        tr = ET.SubElement(tbl2, _w("tr"))
        widths = [1200, 4200, 1200]
        for i, (text, style) in enumerate(cells):
            tc = _tc(tr, width=int(widths[i] if i < len(widths) else 2000))
            pp = _p(tc)
            rr = _r(pp, bold=bool(style.get("bold")))
            _t(rr, text)

    add_row2([("조항", {"bold": True}), ("제목", {"bold": True}), ("표시", {"bold": True})])
    for cid in changed_clause_ids:
        cr = cr_by_id.get(cid) or {}
        if not (bool(cr.get("high_risk")) or bool(cr.get("approval_required"))):
            continue
        title_txt = str((orig_by_id.get(cid) or {}).get("clause_title") or "")
        flag = []
        if bool(cr.get("high_risk")):
            flag.append("HIGH")
        if bool(cr.get("approval_required")):
            flag.append("APPROVAL")
        add_row2([(cid, {}), (title_txt, {}), ("/".join(flag), {"bold": True})])

    ET.SubElement(body, _w("sectPr"))
    document_xml = ET.tostring(doc, encoding="utf-8", xml_declaration=True)

    types_root = ET.Element(f"{{{PKG_TYPES_NS}}}Types")
    d1 = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Default")
    d1.set("Extension", "rels")
    d1.set("ContentType", "application/vnd.openxmlformats-package.relationships+xml")
    d2 = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Default")
    d2.set("Extension", "xml")
    d2.set("ContentType", "application/xml")
    ov = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Override")
    ov.set("PartName", "/word/document.xml")
    ov.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    content_types = ET.tostring(types_root, encoding="utf-8", xml_declaration=True)

    rels_root = ET.Element(f"{{{REL_NS}}}Relationships")
    rel = ET.SubElement(rels_root, f"{{{REL_NS}}}Relationship")
    rel.set("Id", "rId1")
    rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument")
    rel.set("Target", "word/document.xml")
    rels = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)

    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document_xml)
    return buf.getvalue()
