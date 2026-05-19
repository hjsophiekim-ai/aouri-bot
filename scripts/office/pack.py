#!/usr/bin/env python3
"""Repack an unpacked DOCX directory back into a DOCX file."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def pack(input_dir: str, output_docx: str, original: str | None = None) -> Path:
    src = Path(input_dir)
    dst = Path(output_docx)
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Collect all files — [Content_Types].xml must be first
    all_files: list[Path] = sorted(f for f in src.rglob("*") if f.is_file())
    ct_file = src / "[Content_Types].xml"
    ordered: list[Path] = []
    if ct_file in all_files:
        ordered.append(ct_file)
    for f in all_files:
        if f != ct_file:
            ordered.append(f)

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for f in ordered:
            arcname = str(f.relative_to(src)).replace("\\", "/")
            z.write(f, arcname)

    size_kb = dst.stat().st_size // 1024
    print(f"[pack] {src}/ -> {dst.name}  ({size_kb} KB, {len(ordered)} files)")
    return dst


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Repack DOCX directory into .docx")
    p.add_argument("input_dir")
    p.add_argument("output_docx")
    p.add_argument("--original", default=None, help="Original DOCX (unused, for reference)")
    args = p.parse_args()
    pack(args.input_dir, args.output_docx, args.original)
