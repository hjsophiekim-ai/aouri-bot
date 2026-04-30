from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocxCheck:
    path: Path
    has_refugee_law: bool
    dup_clause_label_examples: list[str]
    has_hierarchical_markers: bool
    keyword_counts: dict[str, int]


def _read_docx_document_xml(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as z:
        xml = z.read("word/document.xml")
    return xml.decode("utf-8", errors="replace")


def _xml_to_text(xml: str) -> str:
    x = xml
    x = re.sub(r"</w:p>", "\n", x)
    x = re.sub(r"</w:tr>", "\n", x)
    x = re.sub(r"<[^>]+>", "", x)
    x = re.sub(r"[ \t\r]+", " ", x)
    x = re.sub(r"\n{3,}", "\n\n", x)
    return x.strip()


def _find_dup_clause_labels(text: str) -> list[str]:
    out: list[str] = []
    rx = re.compile(r"(제\s*\d{1,4}\s*조)([^\n]{0,60})(제\s*\d{1,4}\s*조)")
    for m in rx.finditer(text):
        a = re.sub(r"\s+", " ", (m.group(1) or "").strip())
        b = re.sub(r"\s+", " ", (m.group(3) or "").strip())
        if a == b:
            snippet = (m.group(0) or "").strip()
            snippet = re.sub(r"\s+", " ", snippet)
            out.append(snippet[:140])
        if len(out) >= 5:
            break
    return out


def _has_hierarchical_markers(text: str) -> bool:
    rx = re.compile(r"\n\s*(?:\[[A-Z/]+\]\s*)?제\s*\d{1,4}\s*조[^\n]*\n\s*제\s*\d{1,4}\s*항")
    return bool(rx.search("\n" + text + "\n"))


def _count_keywords(text: str, keywords: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in keywords:
        out[k] = text.count(k)
    return out


def check_docx(path: Path) -> DocxCheck:
    xml = _read_docx_document_xml(path)
    text = _xml_to_text(xml)
    keywords = [
        "난민법",
        "SOW",
        "SBOM",
        "오픈소스",
        "소스코드",
        "침해사고",
        "보안사고",
        "개인정보 유출",
    ]
    counts = _count_keywords(text, keywords)
    return DocxCheck(
        path=path,
        has_refugee_law=(counts.get("난민법", 0) > 0),
        dup_clause_label_examples=_find_dup_clause_labels(text),
        has_hierarchical_markers=_has_hierarchical_markers(text),
        keyword_counts=counts,
    )


def _fmt_bool(v: bool) -> str:
    return "OK" if not v else "FAIL"


def main() -> None:
    base = Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output")
    targets = [
        base / "195_aouribot_revision_1_regenerated.docx",
        base / "195_aouribot_revision2_regenerated.docx",
    ]
    checks: list[DocxCheck] = []
    for p in targets:
        if p.exists():
            checks.append(check_docx(p))

    out_path = Path(r"C:\Users\FURSYS\Desktop\aouribot\docs\review_output\195_two_contract_revalidation_after_precision_fix.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# 195) DOCX 2건 재검증(조항표시/중복문안/무관법령/유형오염/계층표시)\n")
    if not checks:
        lines.append("- 대상 파일을 찾지 못했습니다.")
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    for c in checks:
        lines.append(f"## 파일: `{c.path}`\n")
        lines.append(f"- 난민법 노출: `{_fmt_bool(c.has_refugee_law)}`")
        lines.append(f"- 조항표시 중복(제N조...제N조) 탐지: `{('FAIL' if c.dup_clause_label_examples else 'OK')}`")
        if c.dup_clause_label_examples:
            lines.append("  - 예시: " + " | ".join(c.dup_clause_label_examples))
        lines.append(f"- 계층형 표시(제N조 다음 줄에 제M항) 탐지: `{('OK' if c.has_hierarchical_markers else 'WARN')}`")
        lines.append("- 키워드 카운트:")
        for k, v in c.keyword_counts.items():
            lines.append(f"  - {k}: `{v}`")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
