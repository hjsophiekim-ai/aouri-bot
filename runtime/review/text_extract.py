from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TextExtractionResult:
    success: bool
    text: str
    method: str
    error: str | None = None


def _norm_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def extract_text_from_file(file_path: Path) -> TextExtractionResult:
    ext = file_path.suffix.lower()
    min_len = 10
    if ext == ".txt":
        try:
            raw = file_path.read_text(encoding="utf-8")
        except Exception:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
        text = _norm_text(raw)
        if len(text) < min_len:
            return TextExtractionResult(False, "", "txt_read", "extracted text too short")
        return TextExtractionResult(True, text, "txt_read", None)

    if ext == ".docx":
        try:
            text = extract_text_from_docx(file_path)
            text = _norm_text(text)
            if len(text) < min_len:
                return TextExtractionResult(False, "", "docx_zip_xml", "extracted text too short")
            return TextExtractionResult(True, text, "docx_zip_xml", None)
        except Exception as exc:
            return TextExtractionResult(False, "", "docx_zip_xml", str(exc))

    if ext == ".pdf":
        return TextExtractionResult(
            False,
            "",
            "pdf_unsupported_mvp",
            "PDF extraction excluded in MVP (OCR/text-layer handling out of scope)",
        )

    return TextExtractionResult(False, "", "unsupported", f"unsupported extension: {ext}")


def extract_text_from_docx(file_path: Path) -> str:
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
        for part in parts:
            if part not in names:
                continue
            xml_bytes = z.read(part)
            texts.extend(_extract_w_t_text(xml_bytes))
        return " ".join(t for t in texts if t)


def _extract_w_t_text(xml_bytes: bytes) -> list[str]:
    s = xml_bytes.decode("utf-8", errors="replace")
    matches = re.findall(r"<w:t[^>]*>(.*?)</w:t>", s, flags=re.DOTALL)
    out = []
    for m in matches:
        t = re.sub(r"\s+", " ", m).strip()
        if t:
            out.append(t)
    return out

