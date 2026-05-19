#!/usr/bin/env python3
"""
Accept all tracked changes in a redline DOCX to produce a clean version.

Usage:
  python scripts/accept_changes.py <redline.docx> <clean.docx>

Rules:
  - <w:ins> elements: keep all children, remove the w:ins wrapper
  - <w:del> elements: remove entirely (including children)
  - <w:rPr><w:ins.../></w:rPr>: remove the inner w:ins mark
  - comments.xml: remove entirely from output
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

ET.register_namespace("w", W_NS)
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
ET.register_namespace("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006")
ET.register_namespace("wpc", "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas")


def _accept_element(parent: ET.Element, el: ET.Element) -> list[ET.Element]:
    """
    Return the replacement nodes for el:
      - w:ins -> its children (unwrapped)
      - w:del -> [] (removed)
      - w:commentRangeStart/End, w:commentReference -> [] (removed)
      - others -> [recursively processed el]
    """
    tag = el.tag
    if tag == f"{W}ins":
        result = []
        for child in list(el):
            result.extend(_accept_element(el, child))
        return result
    if tag in (f"{W}del", f"{W}commentRangeStart", f"{W}commentRangeEnd"):
        return []
    if tag == f"{W}r":
        # Remove commentReference runs entirely
        if el.find(f"{W}commentReference") is not None:
            return []
        # Remove w:del runs (runs that only have w:delText)
        if el.find(f"{W}delText") is not None and el.find(f"{W}t") is None:
            return []
    # Recursively process children
    new_el = ET.Element(tag, el.attrib)
    new_el.text = el.text
    new_el.tail = el.tail
    pos = 0
    orig_children = list(el)
    for child in orig_children:
        replacements = _accept_element(new_el, child)
        for repl in replacements:
            new_el.insert(pos, repl)
            pos += 1
    # Remove w:ins marks inside w:rPr
    if tag == f"{W}rPr":
        for ins_mark in new_el.findall(f"{W}ins"):
            new_el.remove(ins_mark)
        for del_mark in new_el.findall(f"{W}del"):
            new_el.remove(del_mark)
    return [new_el]


def _accept_body(root: ET.Element) -> ET.Element:
    new_root = ET.Element(root.tag, root.attrib)
    new_root.text = root.text
    new_root.tail = root.tail
    pos = 0
    for child in list(root):
        for repl in _accept_element(new_root, child):
            new_root.insert(pos, repl)
            pos += 1
    return new_root


def accept_changes(redline_path: str, clean_path: str) -> Path:
    src = Path(redline_path)
    dst = Path(clean_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(src, "r") as z:
        names = z.namelist()
        contents: dict[str, bytes] = {n: z.read(n) for n in names}

    # Process document.xml
    doc_xml = contents.get("word/document.xml", b"")
    if doc_xml:
        root = ET.fromstring(doc_xml)
        new_root = _accept_body(root)
        xml_str = ET.tostring(new_root, encoding="unicode")
        contents["word/document.xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_str).encode("utf-8")

    # Remove comments.xml
    for key in list(contents.keys()):
        if key.endswith("comments.xml"):
            del contents[key]

    # Clean up rels to remove comments relationship
    for key in list(contents.keys()):
        if "_rels" in key and key.endswith(".rels"):
            rel_xml = contents[key].decode("utf-8", errors="replace")
            if "comments" in rel_xml.lower():
                try:
                    rel_root = ET.fromstring(contents[key])
                    for rel in list(rel_root):
                        if "comments" in str(rel.get("Type", "")).lower():
                            rel_root.remove(rel)
                    contents[key] = ET.tostring(rel_root, encoding="unicode").encode("utf-8")
                except Exception:
                    pass

    # Clean up [Content_Types].xml to remove comments entry
    ct_key = "[Content_Types].xml"
    if ct_key in contents:
        try:
            ct_root = ET.fromstring(contents[ct_key])
            for ov in list(ct_root):
                if "comments" in str(ov.get("ContentType", "")).lower() or "comments" in str(ov.get("PartName", "")).lower():
                    ct_root.remove(ov)
            contents[ct_key] = ET.tostring(ct_root, encoding="unicode").encode("utf-8")
        except Exception:
            pass

    # Write clean DOCX
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml first
        if ct_key in contents:
            z.writestr(ct_key, contents[ct_key])
        for name, data in contents.items():
            if name == ct_key:
                continue
            z.writestr(name, data)

    dst.write_bytes(buf.getvalue())
    size_kb = dst.stat().st_size // 1024
    print(f"[accept_changes] {src.name} -> {dst.name}  ({size_kb} KB)")
    return dst


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: accept_changes.py <redline.docx> <clean.docx>")
        sys.exit(1)
    accept_changes(sys.argv[1], sys.argv[2])
