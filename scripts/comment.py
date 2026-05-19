#!/usr/bin/env python3
"""
Add a Word comment to an unpacked DOCX directory.

Usage:
  python scripts/comment.py <unpacked_dir> <target_index> "<comment text>" --author "퍼시스법무"

target_index: 0-based index of the modified paragraph (paragraphs with <w:ins> or <w:del>) to attach to.
              Pass -1 to attach to the last paragraph in the document.
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"

ET.register_namespace("w", W_NS)
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")


def _wt(tag: str) -> str:
    return f"{W}{tag}"


def _next_comment_id(comments_path: Path) -> int:
    if not comments_path.exists():
        return 0
    root = ET.parse(str(comments_path)).getroot()
    ids = [int(el.get(f"{W}id", -1)) for el in root.findall(f".//{W}comment")]
    return max(ids, default=-1) + 1


def _ensure_comments_xml(unpacked: Path) -> Path:
    cp = unpacked / "word" / "comments.xml"
    if not cp.exists():
        root = ET.Element(f"{W}comments")
        root.set("xmlns:w", W_NS)
        tree = ET.ElementTree(root)
        tree.write(str(cp), encoding="unicode", xml_declaration=True)
    return cp


def _ensure_comments_rel(unpacked: Path) -> None:
    rels_path = unpacked / "word" / "_rels" / "document.xml.rels"
    if not rels_path.exists():
        return
    tree = ET.parse(str(rels_path))
    root = tree.getroot()
    existing = [el.get("Type") for el in root]
    if COMMENTS_REL_TYPE not in existing:
        el = ET.SubElement(root, "Relationship")
        el.set("Id", f"rIdComments")
        el.set("Type", COMMENTS_REL_TYPE)
        el.set("Target", "comments.xml")
        tree.write(str(rels_path), encoding="unicode", xml_declaration=True)


def _ensure_comments_content_type(unpacked: Path) -> None:
    ct_path = unpacked / "[Content_Types].xml"
    if not ct_path.exists():
        return
    tree = ET.parse(str(ct_path))
    root = tree.getroot()
    parts = [el.get("PartName") for el in root]
    if "/word/comments.xml" not in parts:
        el = ET.SubElement(root, "Override")
        el.set("PartName", "/word/comments.xml")
        el.set("ContentType", COMMENTS_CT)
        tree.write(str(ct_path), encoding="unicode", xml_declaration=True)


def add_comment(
    unpacked_dir: str,
    target_index: int,
    comment_text: str,
    author: str = "퍼시스법무",
    date: str = "2026-05-15T00:00:00Z",
) -> int:
    unpacked = Path(unpacked_dir)
    doc_path = unpacked / "word" / "document.xml"

    _ensure_comments_xml(unpacked)
    _ensure_comments_rel(unpacked)
    _ensure_comments_content_type(unpacked)

    comments_path = unpacked / "word" / "comments.xml"
    comment_id = _next_comment_id(comments_path)

    # -- Add comment to comments.xml ------------------------------------------
    c_root = ET.parse(str(comments_path)).getroot()
    c_el = ET.SubElement(c_root, f"{W}comment")
    c_el.set(f"{W}id", str(comment_id))
    c_el.set(f"{W}author", author)
    c_el.set(f"{W}date", date)
    c_el.set(f"{W}initials", author[:2])
    c_p = ET.SubElement(c_el, f"{W}p")
    c_r = ET.SubElement(c_p, f"{W}r")
    c_t = ET.SubElement(c_r, f"{W}t")
    c_t.text = comment_text
    ET.ElementTree(c_root).write(str(comments_path), encoding="unicode", xml_declaration=True)

    # -- Add commentReference to document.xml ---------------------------------
    doc_tree = ET.parse(str(doc_path))
    doc_root = doc_tree.getroot()
    body = doc_root.find(f".//{W}body")
    if body is None:
        raise ValueError("No body element in document.xml")

    # Find paragraphs that have w:ins or w:del (modified paragraphs)
    all_paras = [el for el in body if el.tag == f"{W}p"]
    modified = [p for p in all_paras if p.find(f".//{W}ins") is not None or p.find(f".//{W}del") is not None]

    if not modified:
        # Fall back to last paragraph
        target_para = all_paras[-1] if all_paras else None
    elif target_index < 0 or target_index >= len(modified):
        target_para = modified[-1]
    else:
        target_para = modified[target_index]

    if target_para is None:
        print(f"[comment] WARNING: no target paragraph found, skipping comment {comment_id}")
        return comment_id

    # Insert commentRangeStart before first child, commentRangeEnd + reference after last
    crs = ET.Element(f"{W}commentRangeStart")
    crs.set(f"{W}id", str(comment_id))
    cre = ET.Element(f"{W}commentRangeEnd")
    cre.set(f"{W}id", str(comment_id))
    ref_r = ET.Element(f"{W}r")
    ref_rpr = ET.SubElement(ref_r, f"{W}rPr")
    ref_rst = ET.SubElement(ref_rpr, f"{W}rStyle")
    ref_rst.set(f"{W}val", "CommentReference")
    ref_cr = ET.SubElement(ref_r, f"{W}commentReference")
    ref_cr.set(f"{W}id", str(comment_id))

    # Insert at start and end of paragraph
    target_para.insert(0, crs)
    target_para.append(cre)
    target_para.append(ref_r)

    doc_tree.write(str(doc_path), encoding="unicode", xml_declaration=True)
    print(f"[comment] Added comment #{comment_id}: {comment_text[:60]}...")
    return comment_id


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("unpacked_dir")
    p.add_argument("target_index", type=int)
    p.add_argument("comment_text")
    p.add_argument("--author", default="퍼시스법무")
    p.add_argument("--date", default="2026-05-15T00:00:00Z")
    args = p.parse_args()
    add_comment(args.unpacked_dir, args.target_index, args.comment_text, args.author, args.date)
