from __future__ import annotations

import re
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from runtime.review.word_markers import contains_wordprocessingml_markers


@dataclass
class TextExtractionResult:
    success: bool
    text: str
    method: str
    error: str | None = None
    raw_markup_text: str | None = None
    meta: dict | None = None


def _norm_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _contains_wordprocessingml_markers(text: str) -> bool:
    return contains_wordprocessingml_markers(text)


def _strip_zero_width_and_ctrl(text: str) -> str:
    if not text:
        return ""
    s = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s



def extract_text_from_file(file_path: Path) -> TextExtractionResult:
    ext = file_path.suffix.lower()
    min_len = 10
    if ext == ".txt":
        try:
            raw = file_path.read_text(encoding="utf-8")
        except Exception:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
        text = _norm_text(_strip_zero_width_and_ctrl(raw))
        if _contains_wordprocessingml_markers(text):
            return TextExtractionResult(False, "", "txt_read", "WordprocessingML markers detected in input text")
        if len(text) < min_len:
            return TextExtractionResult(False, "", "txt_read", "extracted text too short")
        return TextExtractionResult(True, text, "txt_read", None)

    if ext == ".docx":
        try:
            extracted = extract_text_from_docx(file_path)
            text = _norm_text(_strip_zero_width_and_ctrl(extracted["text"]))
            raw_markup_text = extracted.get("raw_markup_text")
            meta = extracted.get("meta")
            if _contains_wordprocessingml_markers(text):
                return TextExtractionResult(
                    False,
                    "",
                    "docx_xml_parser",
                    "WordprocessingML markers detected in extracted text",
                    raw_markup_text=raw_markup_text,
                    meta=meta,
                )
            if len(text) < min_len:
                return TextExtractionResult(
                    False,
                    "",
                    "docx_xml_parser",
                    "extracted text too short",
                    raw_markup_text=raw_markup_text,
                    meta=meta,
                )
            return TextExtractionResult(True, text, "docx_xml_parser", None, raw_markup_text=raw_markup_text, meta=meta)
        except Exception as exc:
            return TextExtractionResult(False, "", "docx_xml_parser", str(exc))

    if ext == ".xlsx":
        try:
            text = extract_text_from_xlsx(file_path)
            text = _norm_text(_strip_zero_width_and_ctrl(text))
            if len(text) < min_len:
                return TextExtractionResult(False, "", "xlsx_reader", "extracted text too short")
            return TextExtractionResult(True, text, "xlsx_reader", None)
        except Exception as exc:
            return TextExtractionResult(False, "", "xlsx_reader", str(exc))

    if ext == ".pdf":
        try:
            text = extract_text_from_pdf(file_path)
            text = _norm_text(_strip_zero_width_and_ctrl(text))
            if len(text) < min_len:
                return TextExtractionResult(False, "", "pdf_reader", "extracted text too short")
            return TextExtractionResult(True, text, "pdf_reader", None)
        except Exception as exc:
            return TextExtractionResult(False, "", "pdf_reader", str(exc))

    if ext == ".hwp":
        try:
            text = extract_text_from_hwp(file_path)
            text = _norm_text(_strip_zero_width_and_ctrl(text))
            if len(text) < min_len:
                return TextExtractionResult(False, "", "hwp_reader", "extracted text too short")
            return TextExtractionResult(True, text, "hwp_reader", None)
        except Exception as exc:
            return TextExtractionResult(False, "", "hwp_reader", str(exc))

    return TextExtractionResult(False, "", "unsupported", f"unsupported extension: {ext}")


def extract_text_from_xlsx(file_path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    parts: list[str] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet_lines: list[str] = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                sheet_lines.append("\t".join(cells))
        if sheet_lines:
            parts.append(f"[시트: {sheet_name}]\n" + "\n".join(sheet_lines))
    wb.close()
    return "\n\n".join(parts)


def extract_text_from_docx(file_path: Path) -> dict[str, object]:
    track_changes_policy = "final"
    parts = ["word/document.xml"]
    with zipfile.ZipFile(file_path, "r") as z:
        names = z.namelist()
        for n in names:
            if re.match(r"word/header\d+\.xml$", n):
                parts.append(n)
            elif re.match(r"word/footer\d+\.xml$", n):
                parts.append(n)
            elif n in ("word/footnotes.xml", "word/endnotes.xml"):
                parts.append(n)
        numbering_xml = z.read("word/numbering.xml") if "word/numbering.xml" in names else None
        numbering_defs = _parse_numbering_xml(numbering_xml) if numbering_xml else None

        texts: list[str] = []
        raw_parts: list[str] = []
        has_track_changes = False
        for part in parts:
            if part not in names:
                continue
            xml_bytes = z.read(part)
            piece = _extract_visible_text_from_word_xml(
                xml_bytes,
                track_changes_policy=track_changes_policy,
                numbering_defs=numbering_defs,
            )
            texts.extend(piece["texts"])
            raw_parts.append(piece["raw_markup_text"])
            has_track_changes = has_track_changes or bool(piece["has_track_changes"])
        return {
            "text": "\n".join([t for t in texts if t]).strip(),
            "raw_markup_text": "\n".join([p for p in raw_parts if p]).strip()[:20000] or None,
            "meta": {
                "has_track_changes": has_track_changes,
                "track_changes_policy": track_changes_policy,
                "parts_included": parts,
            },
        }


def _parse_numbering_xml(xml_bytes: bytes) -> dict[str, object] | None:
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return None
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns = {"w": w_ns}
    num_to_abs: dict[str, str] = {}
    abs_levels: dict[str, dict[str, tuple[str, str]]] = {}

    for num in root.findall("w:num", ns):
        num_id = num.get(f"{{{w_ns}}}numId") or num.get("numId")
        abs_el = num.find("w:abstractNumId", ns)
        abs_id = abs_el.get(f"{{{w_ns}}}val") if abs_el is not None else None
        if isinstance(num_id, str) and isinstance(abs_id, str):
            num_to_abs[num_id] = abs_id

    for absn in root.findall("w:abstractNum", ns):
        abs_id = absn.get(f"{{{w_ns}}}abstractNumId") or absn.get("abstractNumId")
        if not isinstance(abs_id, str):
            continue
        levels: dict[str, tuple[str, str]] = {}
        for lvl in absn.findall("w:lvl", ns):
            ilvl = lvl.get(f"{{{w_ns}}}ilvl") or lvl.get("ilvl")
            if not isinstance(ilvl, str):
                continue
            fmt_el = lvl.find("w:numFmt", ns)
            txt_el = lvl.find("w:lvlText", ns)
            num_fmt = (fmt_el.get(f"{{{w_ns}}}val") if fmt_el is not None else None) or "decimal"
            lvl_text = (txt_el.get(f"{{{w_ns}}}val") if txt_el is not None else None) or "%1."
            levels[ilvl] = (str(num_fmt), str(lvl_text))
        abs_levels[abs_id] = levels

    return {"num_to_abs": num_to_abs, "abs_levels": abs_levels}


_HANGUL = ["가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타", "파", "하"]
_CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳"]


def _to_roman(n: int) -> str:
    vals = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    out = []
    x = n
    for v, sym in vals:
        while x >= v:
            out.append(sym)
            x -= v
    return "".join(out) or str(n)


def _fmt_num(n: int, fmt: str) -> str:
    f = (fmt or "decimal").lower()
    if f in ("decimal", "decimalzero"):
        return str(n)
    if f in ("lowerletter", "loweralpha"):
        return chr(ord("a") + (n - 1) % 26)
    if f in ("upperletter", "upperalpha"):
        return chr(ord("A") + (n - 1) % 26)
    if f == "lowerroman":
        return _to_roman(n).lower()
    if f == "upperroman":
        return _to_roman(n).upper()
    if f in ("koreanhangul", "hangul"):
        return _HANGUL[(n - 1) % len(_HANGUL)]
    if f in ("decimalenclosedcircle", "decimalenclosedcirclechinese"):
        return _CIRCLED[n - 1] if 1 <= n <= len(_CIRCLED) else str(n)
    return str(n)


def _numbering_prefix(
    *,
    numbering_defs: dict[str, object] | None,
    state: dict[str, list[int]],
    num_id: str,
    ilvl: int,
) -> str | None:
    if not num_id:
        return None
    counters = state.get(num_id) or []
    while len(counters) <= ilvl:
        counters.append(0)
    counters[ilvl] += 1
    for j in range(ilvl + 1, len(counters)):
        counters[j] = 0
    for j in range(0, ilvl):
        if counters[j] <= 0:
            counters[j] = 1
    state[num_id] = counters

    abs_id = None
    levels = None
    if isinstance(numbering_defs, dict):
        num_to_abs = numbering_defs.get("num_to_abs")
        abs_levels = numbering_defs.get("abs_levels")
        if isinstance(num_to_abs, dict):
            abs_id = num_to_abs.get(num_id)
        if isinstance(abs_levels, dict) and isinstance(abs_id, str):
            levels = abs_levels.get(abs_id)

    fmt_by_level: dict[int, str] = {}
    lvl_text = None
    if isinstance(levels, dict):
        t = levels.get(str(ilvl))
        if isinstance(t, tuple) and len(t) == 2:
            fmt_by_level[ilvl] = str(t[0])
            lvl_text = str(t[1])
        for k, v in levels.items():
            try:
                lk = int(k)
            except Exception:
                continue
            if isinstance(v, tuple) and len(v) == 2:
                fmt_by_level[lk] = str(v[0])
    if not lvl_text:
        lvl_text = "%1."

    def repl(m: re.Match) -> str:
        idx = int(m.group(1)) - 1
        if idx < 0 or idx >= len(counters):
            return m.group(0)
        fmt = fmt_by_level.get(idx, "decimal")
        return _fmt_num(int(counters[idx] or 0), fmt)

    label = re.sub(r"%(\d)", repl, lvl_text)
    label = label.strip()
    return label if label else None


def _extract_visible_text_from_word_xml(
    xml_bytes: bytes,
    *,
    track_changes_policy: str,
    numbering_defs: dict[str, object] | None,
) -> dict[str, object]:
    raw_markup_text = xml_bytes.decode("utf-8", errors="replace")
    has_track_changes = ("<w:ins" in raw_markup_text) or ("<w:del" in raw_markup_text) or ("<w:delText" in raw_markup_text)
    if track_changes_policy not in ("final", "original"):
        raise ValueError(f"unsupported track_changes_policy: {track_changes_policy}")
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as exc:
        raise ValueError("invalid WordprocessingML XML") from exc

    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns = {"w": w_ns}
    num_state: dict[str, list[int]] = {}

    def _include_text(*, in_del: bool, in_ins: bool) -> bool:
        if track_changes_policy == "final":
            return not in_del
        return not in_ins

    def walk(node: ET.Element, *, in_del: bool, in_ins: bool, out: list[str]) -> None:
        tag = node.tag
        if tag == f"{{{w_ns}}}del":
            in_del = True
        elif tag == f"{{{w_ns}}}ins":
            in_ins = True

        if tag == f"{{{w_ns}}}t" or tag == f"{{{w_ns}}}delText":
            txt = node.text or ""
            if txt and _include_text(in_del=in_del, in_ins=in_ins):
                out.append(txt)
        elif tag == f"{{{w_ns}}}tab":
            out.append("\t")
        elif tag == f"{{{w_ns}}}br" or tag == f"{{{w_ns}}}cr":
            out.append("\n")
        elif tag == f"{{{w_ns}}}noBreakHyphen":
            out.append("-")

        for ch in list(node):
            walk(ch, in_del=in_del, in_ins=in_ins, out=out)

    paras: list[str] = []
    for p in root.findall(".//w:p", ns):
        buf: list[str] = []
        prefix = None
        ppr = p.find("w:pPr", ns)
        if ppr is not None:
            numpr = ppr.find("w:numPr", ns)
            if numpr is not None:
                ilvl_el = numpr.find("w:ilvl", ns)
                numid_el = numpr.find("w:numId", ns)
                try:
                    ilvl = int(ilvl_el.get(f"{{{w_ns}}}val")) if ilvl_el is not None else None
                except Exception:
                    ilvl = None
                num_id = numid_el.get(f"{{{w_ns}}}val") if numid_el is not None else None
                if isinstance(num_id, str) and ilvl is not None:
                    prefix = _numbering_prefix(numbering_defs=numbering_defs, state=num_state, num_id=num_id, ilvl=ilvl)
        if prefix:
            buf.append(prefix + " ")
        walk(p, in_del=False, in_ins=False, out=buf)
        joined = "".join(buf)
        joined = _strip_zero_width_and_ctrl(joined)
        joined = joined.replace("\t", " ")
        joined = re.sub(r"[ \t]+", " ", joined).strip()
        if joined:
            paras.append(joined)
    return {"texts": paras, "has_track_changes": has_track_changes, "raw_markup_text": raw_markup_text[:20000]}


def extract_text_from_pdf(file_path: Path) -> str:
    import pdfplumber

    texts: list[str] = []
    with pdfplumber.open(str(file_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                texts.append(f"[페이지 {page_num}]\n{text.strip()}")
    return "\n\n".join(texts)


def extract_text_from_hwp(file_path: Path) -> str:
    import olefile

    HWPTAG_PARA_TEXT = 66

    if not olefile.isOleFile(str(file_path)):
        raise ValueError("올바른 HWP 파일이 아닙니다")

    with olefile.OleFileIO(str(file_path)) as ole:
        if not ole.exists("FileHeader"):
            raise ValueError("FileHeader 스트림이 없습니다")

        header_data = ole.openstream("FileHeader").read()
        if not header_data.startswith(b"HWP Document File"):
            raise ValueError("HWP 파일 형식이 아닙니다")

        is_compressed = True
        if len(header_data) >= 40:
            attrs = struct.unpack_from("<I", header_data, 36)[0]
            is_compressed = bool(attrs & 0x01)

        texts: list[str] = []
        section_idx = 0

        while True:
            section_path = f"BodyText/Section{section_idx:04d}"
            if not ole.exists(section_path):
                break

            raw = ole.openstream(section_path).read()
            data = zlib.decompress(raw, -15) if is_compressed else raw

            i = 0
            while i + 4 <= len(data):
                header = struct.unpack_from("<I", data, i)[0]
                tag_id = header & 0x3FF
                size = (header >> 20) & 0xFFF
                i += 4

                if size == 0xFFF:
                    if i + 4 > len(data):
                        break
                    size = struct.unpack_from("<I", data, i)[0]
                    i += 4

                record_end = i + size

                if tag_id == HWPTAG_PARA_TEXT:
                    para_chars: list[str] = []
                    j = i
                    while j + 2 <= record_end:
                        char_code = struct.unpack_from("<H", data, j)[0]
                        j += 2
                        if char_code == 0x000D:
                            break
                        elif char_code == 0x000A:
                            para_chars.append("\n")
                        elif char_code == 0x0009:
                            para_chars.append("\t")
                        elif char_code < 0x0020:
                            j += 16  # inline object: skip remaining bytes
                        else:
                            para_chars.append(chr(char_code))
                    text = "".join(para_chars).strip()
                    if text:
                        texts.append(text)

                i = record_end

            section_idx += 1

        if not texts:
            raise ValueError("텍스트를 추출할 수 없습니다")

        return "\n".join(texts)

