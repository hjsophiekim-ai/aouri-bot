"""
runtime/review/docx_redline.py — Word OOXML Tracked Changes 엔진

원본 계약서 DOCX + clause_results → redline DOCX (w:ins/w:del) + clean DOCX

OOXML 규격 준수:
  1. 텍스트 교체: <w:del> + <w:ins> — w:r 의 sibling 요소 (w:r 내부에 넣으면 스키마 오류)
  2. 신규 단락: <w:pPr><w:rPr><w:ins/> 로 단락 마크 표시 + <w:ins><w:r> 로 텍스트 감싸기
  3. change ID: 문서 전체 고유 (1부터 순차 증가)
  4. 코멘트: word/comments.xml + commentReference
"""
from __future__ import annotations

import copy
import difflib
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CT = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)

_NS_MAP = {
    "w": W_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}
for _p, _u in _NS_MAP.items():
    ET.register_namespace(_p, _u)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _wt(tag: str) -> str:
    return f"{W}{tag}"


def _para_text(para: ET.Element) -> str:
    """단락 내 모든 텍스트(run, ins, del 포함) 합산."""
    return "".join(
        el.text or ""
        for el in para.iter()
        if el.tag in (f"{W}t", f"{W}delText") and el.text
    )


def _text_sim(a: str, b: str) -> float:
    """두 문자열의 유사도 (0~1)."""
    if not a or not b:
        return 0.0
    a, b = a.strip()[:400], b.strip()[:400]
    return difflib.SequenceMatcher(None, a, b).ratio()


def _make_run(text: str, rpr: ET.Element | None = None) -> ET.Element:
    r = ET.Element(f"{W}r")
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = ET.SubElement(r, f"{W}t")
    t.text = text
    if text and (text[0] == " " or text[-1] == " "):
        t.set(XML_SPACE, "preserve")
    return r


# ── change ID 관리 ─────────────────────────────────────────────────────────────

class _IDGen:
    def __init__(self, start: int = 1) -> None:
        self._n = start

    def next(self) -> int:
        v = self._n
        self._n += 1
        return v


# ── tracked changes 생성 ──────────────────────────────────────────────────────

def _make_del_ins(
    old_text: str,
    new_text: str,
    ids: _IDGen,
    author: str,
    date: str,
) -> list[ET.Element]:
    """
    텍스트 교체용 <w:del> + <w:ins> 형제 요소 쌍.
    OOXML 규격: 둘 다 <w:p> 안에서 <w:r> 의 sibling 이어야 함.
    """
    # <w:del>
    del_el = ET.Element(f"{W}del")
    del_el.set(f"{W}id", str(ids.next()))
    del_el.set(f"{W}author", author)
    del_el.set(f"{W}date", date)
    del_r = ET.SubElement(del_el, f"{W}r")
    del_t = ET.SubElement(del_r, f"{W}delText")
    del_t.text = old_text
    if old_text and (old_text[0] == " " or old_text[-1] == " "):
        del_t.set(XML_SPACE, "preserve")

    # <w:ins>
    ins_el = ET.Element(f"{W}ins")
    ins_el.set(f"{W}id", str(ids.next()))
    ins_el.set(f"{W}author", author)
    ins_el.set(f"{W}date", date)
    ins_el.append(_make_run(new_text))

    return [del_el, ins_el]


def _make_ins_paragraph(
    text: str,
    ids: _IDGen,
    author: str,
    date: str,
    base_ppr: ET.Element | None = None,
) -> ET.Element:
    """
    신규 단락 삽입:
      <w:p>
        <w:pPr> ... <w:rPr><w:ins/></w:rPr> </w:pPr>
        <w:ins><w:r><w:t>...</w:t></w:r></w:ins>
      </w:p>
    """
    p = ET.Element(f"{W}p")

    # pPr (단락 서식 + 삽입 마크)
    ppr = ET.SubElement(p, f"{W}pPr")
    if base_ppr is not None:
        for child in base_ppr:
            if child.tag != f"{W}rPr":
                ppr.append(copy.deepcopy(child))
    rpr_in_ppr = ET.SubElement(ppr, f"{W}rPr")
    ppr_ins = ET.SubElement(rpr_in_ppr, f"{W}ins")
    ppr_ins.set(f"{W}id", str(ids.next()))
    ppr_ins.set(f"{W}author", author)
    ppr_ins.set(f"{W}date", date)

    # 텍스트 (ins 로 감싸기)
    ins_el = ET.SubElement(p, f"{W}ins")
    ins_el.set(f"{W}id", str(ids.next()))
    ins_el.set(f"{W}author", author)
    ins_el.set(f"{W}date", date)
    ins_el.append(_make_run(text))

    return p


def _make_comment_markup(
    comment_id: int,
) -> tuple[ET.Element, ET.Element, ET.Element]:
    """(commentRangeStart, commentRangeEnd, commentRef run)"""
    crs = ET.Element(f"{W}commentRangeStart")
    crs.set(f"{W}id", str(comment_id))
    cre = ET.Element(f"{W}commentRangeEnd")
    cre.set(f"{W}id", str(comment_id))
    ref = ET.Element(f"{W}r")
    rpr = ET.SubElement(ref, f"{W}rPr")
    rst = ET.SubElement(rpr, f"{W}rStyle")
    rst.set(f"{W}val", "CommentReference")
    cr = ET.SubElement(ref, f"{W}commentReference")
    cr.set(f"{W}id", str(comment_id))
    return crs, cre, ref


# ── 조항 위치 탐색 ─────────────────────────────────────────────────────────────

_ART_PATTERNS = [
    re.compile(r"제\s*(\d+)\s*조", re.IGNORECASE),       # 제N조
    re.compile(r"第\s*(\d+)\s*條", re.IGNORECASE),       # 第N條
    re.compile(r"Article\s+(\d+)", re.IGNORECASE),
    re.compile(r"^\s*(\d{1,2})\.\s+[가-힣A-Z]"),          # 1. 제목
    re.compile(r"^\s*\((\d+)\)\s+[가-힣A-Z]"),            # (1) 제목
]
_PARA_PATTERNS = [
    re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]"),
    re.compile(r"^\s*(\d+)\s*[)）]"),
    re.compile(r"제\s*(\d+)\s*항"),
]
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def _extract_article_num(text: str) -> str | None:
    for pat in _ART_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return str(int(m.group(1)))
            except (IndexError, ValueError):
                pass
    return None


def _build_article_index(paras: list[ET.Element]) -> dict[str, list[int]]:
    """article_number → [para_idx, ...] 인덱스 구축."""
    idx: dict[str, list[int]] = {}
    for i, p in enumerate(paras):
        t = _para_text(p)
        n = _extract_article_num(t)
        if n:
            idx.setdefault(n, []).append(i)
    return idx


def _find_best_para(
    paras: list[ET.Element],
    article_number: str | None,
    paragraph_number: str | None,
    original_text: str,
    art_index: dict[str, list[int]],
    start_hint: int = 0,
) -> int | None:
    """
    clause에 해당하는 단락 인덱스를 찾는다.
    우선순위:
      1. article_number + 텍스트 유사도
      2. 전체 문서 텍스트 유사도
    """
    orig_stripped = original_text.strip()[:300]
    if not orig_stripped:
        return None

    candidates: list[int] = []

    # article_number 기반 후보 범위
    if article_number:
        art_paras = art_index.get(str(article_number), [])
        if art_paras:
            start = art_paras[0]
            # 다음 조항 시작 전까지
            end = len(paras)
            next_arts = [
                v[0]
                for k, v in art_index.items()
                if k != str(article_number) and v[0] > start
            ]
            if next_arts:
                end = min(next_arts)
            candidates = list(range(start, end))

    if not candidates:
        candidates = list(range(start_hint, len(paras)))

    # 유사도로 최적 단락 선택
    best_idx: int | None = None
    best_score = 0.0
    for i in candidates:
        t = _para_text(paras[i])
        if not t.strip():
            continue
        score = _text_sim(orig_stripped, t)
        # 원문이 단락 텍스트를 포함하거나 그 반대인 경우 보너스
        if orig_stripped[:40].lower() in t.lower() or t[:40].lower() in orig_stripped.lower():
            score += 0.3
        if score > best_score:
            best_score = score
            best_idx = i

    return best_idx if best_score >= 0.25 else None


# ── 텍스트→runs 교체 ────────────────────────────────────────────────────────────

def _replace_para_with_tracked_changes(
    para: ET.Element,
    old_text: str,
    new_text: str,
    ids: _IDGen,
    author: str,
    date: str,
) -> None:
    """
    단락 내 텍스트 전체를 del+ins 로 교체.
    기존 <w:r> 들을 제거하고 <w:del> + <w:ins> 형제 요소 삽입.
    """
    # 기존 run 요소 (ins/del 제외) 수집 후 제거
    to_remove = [
        el for el in list(para)
        if el.tag in (f"{W}r", f"{W}ins", f"{W}del",
                      f"{W}commentRangeStart", f"{W}commentRangeEnd")
    ]
    for el in to_remove:
        para.remove(el)

    for el in _make_del_ins(old_text, new_text, ids, author, date):
        para.append(el)


# ── 코멘트 XML 빌드 ─────────────────────────────────────────────────────────────

def _build_comments_xml(comments: list[dict[str, Any]]) -> bytes:
    root = ET.Element(f"{W}comments")
    root.set("xmlns:w", W_NS)
    for c in comments:
        cel = ET.SubElement(root, f"{W}comment")
        cel.set(f"{W}id", str(c["id"]))
        cel.set(f"{W}author", c["author"])
        cel.set(f"{W}date", c["date"])
        cel.set(f"{W}initials", c["author"][:2])
        cp = ET.SubElement(cel, f"{W}p")
        cr = ET.SubElement(cp, f"{W}r")
        ct = ET.SubElement(cr, f"{W}t")
        ct.text = c["text"]
    xml_str = ET.tostring(root, encoding="unicode")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_str
    ).encode("utf-8")


def _inject_comments_relationship(rels_bytes: bytes) -> bytes:
    try:
        root = ET.fromstring(rels_bytes)
        types = [el.get("Type", "") for el in root]
        if COMMENTS_REL_TYPE not in types:
            rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            el = ET.SubElement(root, f"{{{rel_ns}}}Relationship")
            el.set("Id", "rIdComments")
            el.set("Type", COMMENTS_REL_TYPE)
            el.set("Target", "comments.xml")
        return ET.tostring(root, encoding="unicode").encode("utf-8")
    except Exception:
        return rels_bytes


def _inject_comments_content_type(ct_bytes: bytes) -> bytes:
    try:
        root = ET.fromstring(ct_bytes)
        parts = [el.get("PartName", "") for el in root]
        if "/word/comments.xml" not in parts:
            ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
            el = ET.SubElement(root, f"{{{ct_ns}}}Override")
            el.set("PartName", "/word/comments.xml")
            el.set("ContentType", COMMENTS_CT)
        return ET.tostring(root, encoding="unicode").encode("utf-8")
    except Exception:
        return ct_bytes


# ── 변경사항 수락 (clean 버전) ──────────────────────────────────────────────────

def _accept_all(root: ET.Element) -> ET.Element:
    """w:ins 언래핑, w:del 제거, 코멘트 마크 제거."""

    def _proc(parent: ET.Element, el: ET.Element) -> list[ET.Element]:
        tag = el.tag
        if tag == f"{W}del":
            return []
        if tag in (f"{W}commentRangeStart", f"{W}commentRangeEnd"):
            return []
        if tag == f"{W}r":
            if el.find(f"{W}commentReference") is not None:
                return []
            if el.find(f"{W}delText") is not None and el.find(f"{W}t") is None:
                return []
        if tag == f"{W}ins":
            results = []
            for child in list(el):
                results.extend(_proc(el, child))
            return results

        new = ET.Element(tag, el.attrib)
        new.text = el.text
        new.tail = el.tail
        for child in list(el):
            for repl in _proc(new, child):
                new.append(repl)
        if tag == f"{W}rPr":
            for mark in list(new):
                if mark.tag in (f"{W}ins", f"{W}del"):
                    new.remove(mark)
        return [new]

    results = _proc(None, root)  # type: ignore[arg-type]
    return results[0] if results else root


def _build_clean_docx(redline_contents: dict[str, bytes]) -> dict[str, bytes]:
    clean = dict(redline_contents)
    doc_bytes = clean.get("word/document.xml", b"")
    if doc_bytes:
        root = ET.fromstring(doc_bytes)
        new_root = _accept_all(root)
        xml_str = ET.tostring(new_root, encoding="unicode")
        clean["word/document.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_str
        ).encode("utf-8")
    for key in list(clean.keys()):
        if "comments.xml" in key:
            del clean[key]
    return clean


def _pack_docx(contents: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ct_key = "[Content_Types].xml"
        if ct_key in contents:
            z.writestr(ct_key, contents[ct_key])
        for name, data in contents.items():
            if name == ct_key:
                continue
            z.writestr(name, data)
    return buf.getvalue()


# ── 메인 함수 ──────────────────────────────────────────────────────────────────

def build_redline_docx(
    *,
    docx_bytes: bytes,
    original_clauses: list[dict[str, Any]],
    clause_results: list[dict[str, Any]],
    author: str = "퍼시스법무",
    date: str | None = None,
) -> tuple[bytes, bytes]:
    """
    원본 계약서 DOCX + 검토 결과 → (redline_bytes, clean_bytes)

    Args:
        docx_bytes: 원본 계약서 DOCX bytes
        original_clauses: 원본 조항 목록 (article_number, paragraph_number, text 포함)
        clause_results: AI 검토 결과 목록 (suggested_rewrite, original_text 등 포함)
        author: tracked changes 작성자
        date: ISO 8601 날짜 (None이면 현재 시각)

    Returns:
        (redline_bytes, clean_bytes) — 두 파일 bytes
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── DOCX 압축 해제 ──────────────────────────────────────────────────────────
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as z:
        contents: dict[str, bytes] = {n: z.read(n) for n in z.namelist()}

    doc_xml = contents.get("word/document.xml", b"")
    if not doc_xml:
        raise ValueError("word/document.xml 없음 — 유효한 DOCX가 아닙니다")

    root = ET.fromstring(doc_xml)
    body = root.find(f".//{W}body")
    if body is None:
        raise ValueError("<w:body> 요소 없음")

    # ── 단락 목록 + 조항 인덱스 ────────────────────────────────────────────────
    all_paras: list[ET.Element] = [el for el in body if el.tag == f"{W}p"]
    art_index = _build_article_index(all_paras)

    # original_clauses를 clause_id 기준으로 인덱싱
    orig_by_id: dict[str, dict[str, Any]] = {
        str(c.get("clause_id") or ""): c
        for c in original_clauses
        if isinstance(c, dict) and c.get("clause_id")
    }

    # ── 변경 적용 루프 ─────────────────────────────────────────────────────────
    ids = _IDGen(1)
    comment_id_counter = [0]
    comments: list[dict[str, Any]] = []

    # 변경 있는 clause_results 필터링 (has_addition 전용 항목도 포함)
    applicable = [
        cr for cr in clause_results
        if isinstance(cr, dict)
        and (bool(cr.get("has_rewrite_change")) or bool(cr.get("has_addition")))
        and str(cr.get("original_text") or "").strip()
        and not bool(cr.get("dedup_suppressed"))
        and not bool(cr.get("keep_as_is"))
    ]

    # 처리된 단락 추적 (중복 적용 방지)
    processed_paras: set[int] = set()

    for cr in applicable:
        cid = str(cr.get("clause_id") or "")
        orig_clause = orig_by_id.get(cid) or {}

        article_number = str(
            cr.get("article_number")
            or orig_clause.get("article_number")
            or ""
        ).strip()
        para_number = str(
            cr.get("paragraph_number")
            or orig_clause.get("paragraph_number")
            or ""
        ).strip()
        original_text = str(cr.get("original_text") or "").strip()
        suggested = str(cr.get("suggested_rewrite") or "").strip()
        has_addition = bool(cr.get("has_addition"))
        addition_text = str(cr.get("addition_text") or "").strip()
        risk = str(cr.get("risk_tier") or "MEDIUM").upper()
        reason = str(cr.get("rewrite_reason") or "").strip()
        wcs = str(cr.get("worst_case_scenario") or "").strip()
        neg = str(cr.get("negotiation_strategy") or "").strip()
        related = str(cr.get("related_laws") or "").strip()

        if not original_text:
            continue
        if not suggested and not has_addition:
            continue

        # 단락 탐색
        # 갱신된 파라 목록 (DOM이 변경될 수 있으므로 재수집)
        all_paras = [el for el in body if el.tag == f"{W}p"]
        art_index = _build_article_index(all_paras)

        para_idx = _find_best_para(
            all_paras,
            article_number or None,
            para_number or None,
            original_text,
            art_index,
        )

        if para_idx is None:
            continue
        if para_idx in processed_paras:
            continue
        processed_paras.add(para_idx)

        target_para = all_paras[para_idx]
        base_ppr = target_para.find(f"{W}pPr")

        # ── 수정 적용 ──────────────────────────────────────────────────────────
        # [추가] 패턴: 원본 단락은 그대로 유지하고 새 단락만 삽입
        if has_addition and addition_text and not bool(cr.get("has_rewrite_change")):
            body_children = list(body)
            insert_at = body_children.index(target_para) + 1
            for line in addition_text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                new_p = _make_ins_paragraph(line, ids, author, date, base_ppr)
                body.insert(insert_at, new_p)
                insert_at += 1
            # 코멘트는 target_para에 부착
            if reason or risk:
                c_id = comment_id_counter[0]
                comment_id_counter[0] += 1
                c_parts = [f"[{risk}] {reason}" if reason else f"[{risk}] 신규 항 추가"]
                if wcs:
                    c_parts.append(f"최악: {wcs[:80]}")
                if neg:
                    c_parts.append(f"협상: {neg[:60]}")
                c_text = " | ".join(c_parts)
                comments.append({"id": c_id, "author": author, "date": date, "text": c_text})
                crs, cre, ref = _make_comment_markup(c_id)
                target_para.insert(0, crs)
                target_para.append(cre)
                target_para.append(ref)
            continue

        # 일반 수정: del+ins 교체 또는 신규 단락 삽입
        is_replacement = _text_sim(original_text, suggested) < 0.95

        if is_replacement:
            _replace_para_with_tracked_changes(
                target_para, original_text, suggested, ids, author, date
            )
            # [추가] 블록이 별도로 있으면 교체 후 추가 삽입
            if has_addition and addition_text:
                body_children = list(body)
                insert_at = body_children.index(target_para) + 1
                for line in addition_text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    new_p = _make_ins_paragraph(line, ids, author, date, base_ppr)
                    body.insert(insert_at, new_p)
                    insert_at += 1
        else:
            # 내용이 거의 같으면 신규 항 추가
            body_children = list(body)
            insert_at = body_children.index(target_para) + 1
            new_p = _make_ins_paragraph(suggested, ids, author, date, base_ppr)
            body.insert(insert_at, new_p)
            target_para = new_p

        # ── 코멘트 추가 ────────────────────────────────────────────────────────
        if reason or risk:
            c_id = comment_id_counter[0]
            comment_id_counter[0] += 1

            # 코멘트 텍스트 구성
            c_parts = [f"[{risk}] {reason}" if reason else f"[{risk}] 수정 필요"]
            if related:
                c_parts.append(f"법령: {related}")
            if wcs:
                c_parts.append(f"최악: {wcs[:80]}")
            if neg:
                c_parts.append(f"협상: {neg[:60]}")
            c_text = " | ".join(c_parts)

            comments.append({
                "id": c_id,
                "author": author,
                "date": date,
                "text": c_text,
            })

            crs, cre, ref = _make_comment_markup(c_id)
            target_para.insert(0, crs)
            target_para.append(cre)
            target_para.append(ref)

    # ── document.xml 직렬화 ────────────────────────────────────────────────────
    xml_str = ET.tostring(root, encoding="unicode")
    contents["word/document.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_str
    ).encode("utf-8")

    # ── comments.xml + 관계 추가 ───────────────────────────────────────────────
    if comments:
        contents["word/comments.xml"] = _build_comments_xml(comments)
        rels_key = "word/_rels/document.xml.rels"
        if rels_key in contents:
            contents[rels_key] = _inject_comments_relationship(contents[rels_key])
        ct_key = "[Content_Types].xml"
        if ct_key in contents:
            contents[ct_key] = _inject_comments_content_type(contents[ct_key])

    # ── 패킹 ─────────────────────────────────────────────────────────────────
    redline_bytes = _pack_docx(contents)
    clean_contents = _build_clean_docx(contents)
    clean_bytes = _pack_docx(clean_contents)

    return redline_bytes, clean_bytes


def generate_redline(
    contract_path: str | Path,
    original_clauses: list[dict[str, Any]],
    clause_results: list[dict[str, Any]],
    output_dir: str | Path | None = None,
    author: str = "퍼시스법무",
) -> tuple[Path, Path]:
    """
    계약서 파일 경로로 받아서 redline + clean 파일을 디스크에 저장.

    Returns:
        (redline_path, clean_path)
    """
    src = Path(contract_path)
    out = Path(output_dir) if output_dir else src.parent
    out.mkdir(parents=True, exist_ok=True)

    docx_bytes = src.read_bytes()
    redline_bytes, clean_bytes = build_redline_docx(
        docx_bytes=docx_bytes,
        original_clauses=original_clauses,
        clause_results=clause_results,
        author=author,
    )

    stem = src.stem
    redline_path = out / f"redline_{stem}.docx"
    clean_path = out / f"clean_{stem}.docx"

    redline_path.write_bytes(redline_bytes)
    clean_path.write_bytes(clean_bytes)

    n_changes = sum(
        1 for cr in clause_results
        if isinstance(cr, dict) and bool(cr.get("has_rewrite_change"))
    )
    print(f"[docx_redline] {n_changes}개 변경 적용")
    print(f"  (A) {redline_path}  ({len(redline_bytes)//1024} KB)")
    print(f"  (B) {clean_path}   ({len(clean_bytes)//1024} KB)")

    return redline_path, clean_path
