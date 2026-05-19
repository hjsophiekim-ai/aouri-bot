#!/usr/bin/env python3
"""Validate tracked-changes structure in a DOCX file."""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _wt(tag: str) -> str:
    return f"{W_NS}:{tag}"


def _find_all(root: ET.Element, tag: str) -> list[ET.Element]:
    return root.findall(f".//{W}{tag}")


def validate(docx_path: str) -> bool:
    src = Path(docx_path)
    errors: list[str] = []
    warnings: list[str] = []

    with zipfile.ZipFile(src, "r") as z:
        names = set(z.namelist())
        doc_xml = z.read("word/document.xml") if "word/document.xml" in names else b""
        comments_xml = z.read("word/comments.xml") if "word/comments.xml" in names else b""

    if not doc_xml:
        errors.append("word/document.xml missing")
        _report(errors, warnings)
        return False

    root = ET.fromstring(doc_xml)

    # ── Check 1: tracked changes have author + date ───────────────────────────
    required_attrs = [f"{W}author", f"{W}date"]
    for tag in ("ins", "del"):
        for el in _find_all(root, tag):
            for attr in required_attrs:
                if not el.get(attr):
                    errors.append(f"<w:{tag}> missing {attr}")

    # ── Check 2: no w:ins nested inside w:ins ────────────────────────────────
    for ins in _find_all(root, "ins"):
        if ins.find(f".//{W}ins") is not None:
            errors.append("<w:ins> is nested inside another <w:ins>")

    # ── Check 3: comment IDs match between document.xml and comments.xml ─────
    doc_refs = {el.get(f"{W}id") for el in _find_all(root, "commentReference") if el.get(f"{W}id")}
    if comments_xml:
        cr = ET.fromstring(comments_xml)
        comment_ids = {el.get(f"{W}id") for el in _find_all(cr, "comment") if el.get(f"{W}id")}
        unmatched = doc_refs - comment_ids
        if unmatched:
            errors.append(f"commentReference IDs not in comments.xml: {sorted(unmatched)}")
    elif doc_refs:
        warnings.append(f"document.xml has {len(doc_refs)} comment references but comments.xml is missing")

    # ── Check 4: IDs are unique ───────────────────────────────────────────────
    seen_ids: dict[str, int] = {}
    for tag in ("ins", "del", "comment"):
        for el in _find_all(root, tag):
            eid = el.get(f"{W}id")
            if eid:
                seen_ids[eid] = seen_ids.get(eid, 0) + 1
    dup = {k: v for k, v in seen_ids.items() if v > 1}
    if dup:
        errors.append(f"Duplicate w:id values: {dup}")

    _report(errors, warnings)
    return len(errors) == 0


def _report(errors: list[str], warnings: list[str]) -> None:
    for w in warnings:
        print(f"  [WARN] {w}")
    for e in errors:
        print(f"  [ERR]  {e}")
    if not errors and not warnings:
        print("  [OK] No issues found.")
    elif not errors:
        print(f"  [OK] {len(warnings)} warning(s), 0 errors.")
    else:
        print(f"  [FAIL] {len(errors)} error(s), {len(warnings)} warning(s).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: validate.py <file.docx> [file2.docx ...]")
        sys.exit(1)
    all_ok = True
    for path in sys.argv[1:]:
        print(f"\nValidating: {path}")
        ok = validate(path)
        if not ok:
            all_ok = False
    sys.exit(0 if all_ok else 1)
