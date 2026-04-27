from __future__ import annotations

import re
import zipfile
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

    if ext == ".pdf":
        return TextExtractionResult(
            False,
            "",
            "pdf_unsupported_mvp",
            "PDF extraction excluded in MVP (OCR/text-layer handling out of scope)",
        )

    return TextExtractionResult(False, "", "unsupported", f"unsupported extension: {ext}")


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

        texts: list[str] = []
        raw_parts: list[str] = []
        has_track_changes = False
        for part in parts:
            if part not in names:
                continue
            xml_bytes = z.read(part)
            piece = _extract_visible_text_from_word_xml(xml_bytes, track_changes_policy=track_changes_policy)
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


def _extract_visible_text_from_word_xml(
    xml_bytes: bytes,
    *,
    track_changes_policy: str,
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
        walk(p, in_del=False, in_ins=False, out=buf)
        joined = "".join(buf)
        joined = _strip_zero_width_and_ctrl(joined)
        joined = joined.replace("\t", " ")
        joined = re.sub(r"[ \t]+", " ", joined).strip()
        if joined:
            paras.append(joined)
    return {"texts": paras, "has_track_changes": has_track_changes, "raw_markup_text": raw_markup_text[:20000]}

