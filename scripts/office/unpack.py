#!/usr/bin/env python3
"""Unpack a DOCX file into a directory for editing."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def unpack(docx_path: str, output_dir: str) -> Path:
    src = Path(docx_path)
    dst = Path(output_dir)
    if dst.exists():
        import shutil
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as z:
        z.extractall(dst)
    print(f"[unpack] {src.name} -> {dst}/  ({len(list(dst.rglob('*')))} files)")
    return dst


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: unpack.py <input.docx> <output_dir>")
        sys.exit(1)
    unpack(sys.argv[1], sys.argv[2])
