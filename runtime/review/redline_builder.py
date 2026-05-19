"""
Redline DOCX Builder — Word XML tracked-changes 엔진

기능:
  1. 원본 DOCX에 <w:ins>/<w:del> tracked changes 삽입
  2. 각 수정 위치에 Word comment 추가
  3. redline DOCX + clean DOCX (변경사항 수락 완료) 동시 생성

사용법:
  builder = RedlineBuilder(original_docx_bytes, author="퍼시스법무")
  amendments = [
      Amendment(
          article_pattern="제6조",
          insert_after_pattern="2)",   # 이 패턴 다음에 삽입
          insert_paragraphs=["3) 신규 문안..."],
          comment_text="[HIGH] 비용전가 방지",
          risk_level="HIGH",
      ),
  ]
  redline_bytes, clean_bytes = builder.apply(amendments)
"""
from __future__ import annotations

import copy
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"

_NAMESPACES = {
    "w": W_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
for _prefix, _uri in _NAMESPACES.items():
    ET.register_namespace(_prefix, _uri)


def _wt(tag: str) -> str:
    return f"{W}{tag}"


def _para_text(para: ET.Element) -> str:
    """모든 <w:t> 텍스트를 합쳐서 반환 (runs, ins, del 포함)."""
    parts = []
    for el in para.iter():
        if el.tag in (f"{W}t", f"{W}delText"):
            parts.append(el.text or "")
    return "".join(parts)


def _make_run(text: str, bold: bool = False, italic: bool = False) -> ET.Element:
    r = ET.Element(f"{W}r")
    if bold or italic:
        rpr = ET.SubElement(r, f"{W}rPr")
        if bold:
            ET.SubElement(rpr, f"{W}b")
        if italic:
            ET.SubElement(rpr, f"{W}i")
    t = ET.SubElement(r, f"{W}t")
    t.text = text
    if text and (text[0] == " " or text[-1] == " "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def _make_ins_para(
    text: str,
    author: str,
    date: str,
    change_id: int,
    ppr_el: ET.Element | None = None,
) -> ET.Element:
    """전체 단락을 <w:ins>로 감싼 삽입 단락 생성."""
    p = ET.Element(f"{W}p")

    # 단락 속성 (들여쓰기 등) — 원본 단락 속성 복사 또는 기본값
    ppr = ET.SubElement(p, f"{W}pPr")
    if ppr_el is not None:
        for child in ppr_el:
            if child.tag != f"{W}rPr":
                ppr.append(copy.deepcopy(child))
    # pPr 내부에 rPr > ins 마크 추가 (단락 마크가 삽입됨을 표시)
    rpr_in_ppr = ET.SubElement(ppr, f"{W}rPr")
    ins_mark = ET.SubElement(rpr_in_ppr, f"{W}ins")
    ins_mark.set(f"{W}id", str(change_id))
    ins_mark.set(f"{W}author", author)
    ins_mark.set(f"{W}date", date)

    # 텍스트를 <w:ins>로 감싸기
    ins_el = ET.SubElement(p, f"{W}ins")
    ins_el.set(f"{W}id", str(change_id + 1))
    ins_el.set(f"{W}author", author)
    ins_el.set(f"{W}date", date)
    ins_el.append(_make_run(text))

    return p


def _make_del_ins_run(
    old_text: str,
    new_text: str,
    author: str,
    date: str,
    del_id: int,
    ins_id: int,
) -> list[ET.Element]:
    """기존 텍스트를 <w:del>로 감싸고 신규 텍스트를 <w:ins>로 추가."""
    elements = []

    del_el = ET.Element(f"{W}del")
    del_el.set(f"{W}id", str(del_id))
    del_el.set(f"{W}author", author)
    del_el.set(f"{W}date", date)
    del_r = ET.SubElement(del_el, f"{W}r")
    del_t = ET.SubElement(del_r, f"{W}delText")
    del_t.text = old_text
    if old_text and (old_text[0] == " " or old_text[-1] == " "):
        del_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    elements.append(del_el)

    ins_el = ET.Element(f"{W}ins")
    ins_el.set(f"{W}id", str(ins_id))
    ins_el.set(f"{W}author", author)
    ins_el.set(f"{W}date", date)
    ins_el.append(_make_run(new_text))
    elements.append(ins_el)

    return elements


def _make_comment_elements(comment_id: int) -> tuple[ET.Element, ET.Element, ET.Element]:
    """(commentRangeStart, commentRangeEnd, commentRef run) 생성."""
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

    return crs, cre, ref_r


@dataclass
class Amendment:
    """계약서 수정안 하나."""
    article_pattern: str
    """대상 조항을 찾기 위한 패턴 (예: '제6조', '6.'). 이 텍스트를 포함한 단락 탐색."""

    insert_after_pattern: str | None = None
    """이 패턴을 포함한 단락 다음에 insert_paragraphs를 삽입. None이면 article_pattern 단락 바로 다음."""

    insert_paragraphs: list[str] = field(default_factory=list)
    """삽입할 신규 단락 텍스트 목록 (각 항목이 별도 w:p로 삽입됨)."""

    replace_article_text: str | None = None
    """이 패턴의 단락 내 텍스트 전체를 replace_with_text로 교체 (del+ins)."""

    replace_with_text: str | None = None
    """replace_article_text의 대체 텍스트."""

    comment_text: str = ""
    """Word 코멘트 내용."""

    risk_level: str = "MEDIUM"
    """CRITICAL / HIGH / MEDIUM / LOW."""

    related_laws: str = ""
    """관련 법령 (예: '대리점법 제6조')."""

    negotiation_strategy: str = ""
    """협상 전략 메모."""

    author: str = "퍼시스법무"
    date: str = "2026-05-15T00:00:00Z"


class RedlineBuilder:
    """원본 DOCX bytes + Amendment 목록 -> (redline bytes, clean bytes)."""

    def __init__(
        self,
        original_bytes: bytes,
        author: str = "퍼시스법무",
        date: str = "2026-05-15T00:00:00Z",
    ) -> None:
        self._original = original_bytes
        self._author = author
        self._date = date
        self._change_id = 1
        self._comment_id = 0
        self._comments: list[dict[str, Any]] = []

    def _next_change_id(self) -> int:
        cid = self._change_id
        self._change_id += 1
        return cid

    def _next_comment_id(self) -> int:
        cid = self._comment_id
        self._comment_id += 1
        return cid

    def apply(self, amendments: list[Amendment]) -> tuple[bytes, bytes]:
        """
        Returns:
            (redline_docx_bytes, clean_docx_bytes)
        """
        # DOCX 압축 해제
        with zipfile.ZipFile(io.BytesIO(self._original), "r") as z:
            names = z.namelist()
            contents: dict[str, bytes] = {n: z.read(n) for n in names}

        # document.xml 파싱
        doc_xml = contents.get("word/document.xml", b"")
        if not doc_xml:
            raise ValueError("word/document.xml not found in DOCX")
        root = ET.fromstring(doc_xml)

        # body 탐색
        body = root.find(f".//{W}body")
        if body is None:
            raise ValueError("No <w:body> in document.xml")

        # 각 수정안 적용
        for amendment in amendments:
            self._apply_amendment(body, amendment)

        # document.xml 직렬화
        xml_str = ET.tostring(root, encoding="unicode")
        contents["word/document.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_str
        ).encode("utf-8")

        # comments.xml 생성 및 관계 설정
        if self._comments:
            contents["word/comments.xml"] = self._build_comments_xml()
            contents = self._add_comments_relationship(contents)
            contents = self._add_comments_content_type(contents)

        # redline DOCX 빌드
        redline_bytes = self._build_docx(contents)

        # clean DOCX (변경사항 수락)
        clean_bytes = self._accept_all(redline_bytes)

        return redline_bytes, clean_bytes

    def _apply_amendment(self, body: ET.Element, am: Amendment) -> None:
        paras = [el for el in body if el.tag == f"{W}p"]

        # ── 1. 대상 조항 단락 찾기 ────────────────────────────────────────────
        article_idx = self._find_para_idx(paras, am.article_pattern)
        if article_idx is None:
            print(f"[redline] WARNING: article not found: {am.article_pattern!r}")
            return

        # ── 2. 삽입 위치 찾기 ────────────────────────────────────────────────
        if am.insert_after_pattern:
            # article 다음부터 탐색
            search_paras = paras[article_idx:]
            rel_idx = self._find_para_idx(search_paras, am.insert_after_pattern)
            if rel_idx is not None:
                insert_after_idx = article_idx + rel_idx
            else:
                insert_after_idx = article_idx
        else:
            insert_after_idx = article_idx

        # body 내에서의 절대 위치 계산
        body_children = list(body)
        para_el = paras[insert_after_idx]
        body_insert_idx = body_children.index(para_el) + 1

        # ── 3. 텍스트 교체 (replace) ──────────────────────────────────────────
        if am.replace_article_text and am.replace_with_text:
            rep_idx = self._find_para_idx(paras, am.replace_article_text)
            if rep_idx is not None:
                rep_para = paras[rep_idx]
                self._replace_para_text(rep_para, am.replace_article_text, am.replace_with_text, am)

        # ── 4. 신규 단락 삽입 ────────────────────────────────────────────────
        if am.insert_paragraphs:
            ppr_el = paras[insert_after_idx].find(f"{W}pPr")
            comment_attached = False
            for i, para_text in enumerate(am.insert_paragraphs):
                cid = self._next_change_id()
                new_p = _make_ins_para(para_text, am.author, am.date, cid, ppr_el)

                # 첫 번째 삽입 단락에 코멘트 붙이기
                if not comment_attached and am.comment_text:
                    comment_id = self._next_comment_id()
                    self._comments.append({
                        "id": comment_id,
                        "author": am.author,
                        "date": am.date,
                        "text": self._build_comment_text(am),
                    })
                    crs, cre, ref_r = _make_comment_elements(comment_id)
                    new_p.insert(0, crs)
                    new_p.append(cre)
                    new_p.append(ref_r)
                    comment_attached = True

                body.insert(body_insert_idx + i, new_p)
                self._change_id += 1  # pPr ins mark도 ID 소비

        # 삽입 없이 코멘트만 있는 경우
        elif am.comment_text and not am.replace_article_text:
            comment_id = self._next_comment_id()
            self._comments.append({
                "id": comment_id,
                "author": am.author,
                "date": am.date,
                "text": self._build_comment_text(am),
            })
            target_para = paras[insert_after_idx]
            crs, cre, ref_r = _make_comment_elements(comment_id)
            target_para.insert(0, crs)
            target_para.append(cre)
            target_para.append(ref_r)

    def _replace_para_text(
        self,
        para: ET.Element,
        old_text: str,
        new_text: str,
        am: Amendment,
    ) -> None:
        """단락의 텍스트를 del+ins로 교체."""
        # 기존 runs를 모두 제거하고 del+ins로 대체
        old_runs = [el for el in list(para) if el.tag == f"{W}r"]
        combined_old = _para_text(para)

        # 기존 runs 제거
        for r in old_runs:
            para.remove(r)

        # del+ins 생성
        del_id = self._next_change_id()
        ins_id = self._next_change_id()
        for el in _make_del_ins_run(combined_old, new_text, am.author, am.date, del_id, ins_id):
            para.append(el)

        # 코멘트 추가
        if am.comment_text:
            comment_id = self._next_comment_id()
            self._comments.append({
                "id": comment_id,
                "author": am.author,
                "date": am.date,
                "text": self._build_comment_text(am),
            })
            crs, cre, ref_r = _make_comment_elements(comment_id)
            para.insert(0, crs)
            para.append(cre)
            para.append(ref_r)

    @staticmethod
    def _find_para_idx(paras: list[ET.Element], pattern: str) -> int | None:
        """패턴을 포함하는 첫 번째 단락의 인덱스 반환 (대소문자 무시)."""
        pat_lower = pattern.lower()
        for i, p in enumerate(paras):
            if pat_lower in _para_text(p).lower():
                return i
        return None

    def _build_comment_text(self, am: Amendment) -> str:
        parts = [f"[{am.risk_level}] {am.comment_text}"]
        if am.related_laws:
            parts.append(f"관련 법령: {am.related_laws}")
        if am.negotiation_strategy:
            parts.append(f"협상 전략: {am.negotiation_strategy}")
        return " | ".join(parts)

    def _build_comments_xml(self) -> bytes:
        root = ET.Element(f"{W}comments")
        root.set("xmlns:w", W_NS)
        for c in self._comments:
            c_el = ET.SubElement(root, f"{W}comment")
            c_el.set(f"{W}id", str(c["id"]))
            c_el.set(f"{W}author", c["author"])
            c_el.set(f"{W}date", c["date"])
            c_el.set(f"{W}initials", c["author"][:2])
            c_p = ET.SubElement(c_el, f"{W}p")
            c_r = ET.SubElement(c_p, f"{W}r")
            c_t = ET.SubElement(c_r, f"{W}t")
            c_t.text = c["text"]
        xml_str = ET.tostring(root, encoding="unicode")
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_str).encode("utf-8")

    def _add_comments_relationship(self, contents: dict[str, bytes]) -> dict[str, bytes]:
        rels_key = "word/_rels/document.xml.rels"
        if rels_key not in contents:
            return contents
        try:
            rels_root = ET.fromstring(contents[rels_key])
            existing_types = [el.get("Type", "") for el in rels_root]
            if COMMENTS_REL_TYPE not in existing_types:
                el = ET.SubElement(rels_root, "Relationship")
                el.set("Id", "rIdComments")
                el.set("Type", COMMENTS_REL_TYPE)
                el.set("Target", "comments.xml")
                contents[rels_key] = ET.tostring(rels_root, encoding="unicode").encode("utf-8")
        except Exception:
            pass
        return contents

    def _add_comments_content_type(self, contents: dict[str, bytes]) -> dict[str, bytes]:
        ct_key = "[Content_Types].xml"
        if ct_key not in contents:
            return contents
        try:
            ct_root = ET.fromstring(contents[ct_key])
            parts = [el.get("PartName", "") for el in ct_root]
            if "/word/comments.xml" not in parts:
                el = ET.SubElement(ct_root, "Override")
                el.set("PartName", "/word/comments.xml")
                el.set("ContentType", COMMENTS_CT)
                contents[ct_key] = ET.tostring(ct_root, encoding="unicode").encode("utf-8")
        except Exception:
            pass
        return contents

    @staticmethod
    def _build_docx(contents: dict[str, bytes]) -> bytes:
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

    @staticmethod
    def _accept_all(redline_bytes: bytes) -> bytes:
        """
        모든 tracked changes 수락:
          - w:ins -> 내용 유지, 래퍼 제거
          - w:del -> 전체 제거
          - comments -> 제거
        """
        with zipfile.ZipFile(io.BytesIO(redline_bytes), "r") as z:
            names = z.namelist()
            contents: dict[str, bytes] = {n: z.read(n) for n in names}

        doc_xml = contents.get("word/document.xml", b"")
        if doc_xml:
            root = ET.fromstring(doc_xml)
            new_root = _accept_element_tree(root)
            xml_str = ET.tostring(new_root, encoding="unicode")
            contents["word/document.xml"] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_str
            ).encode("utf-8")

        # 코멘트 및 관련 파일 제거
        for key in list(contents.keys()):
            if key.endswith("comments.xml"):
                del contents[key]

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


def _accept_element_tree(el: ET.Element) -> ET.Element:
    """재귀적으로 tracked changes를 수락."""
    tag = el.tag
    if tag == f"{W}ins":
        # ins 래퍼 제거 — 가상 컨테이너로 처리
        container = ET.Element("_container_")
        for child in list(el):
            container.append(_accept_element_tree(child))
        return container  # 호출자가 언래핑
    if tag in (f"{W}del", f"{W}commentRangeStart", f"{W}commentRangeEnd"):
        return ET.Element("_removed_")  # 호출자가 제거
    if tag == f"{W}r":
        if el.find(f"{W}commentReference") is not None:
            return ET.Element("_removed_")
        if el.find(f"{W}delText") is not None and el.find(f"{W}t") is None:
            return ET.Element("_removed_")

    new_el = ET.Element(tag, el.attrib)
    new_el.text = el.text
    new_el.tail = el.tail
    for child in list(el):
        processed = _accept_element_tree(child)
        if processed.tag == "_removed_":
            continue
        if processed.tag == "_container_":
            for grandchild in list(processed):
                new_el.append(grandchild)
        else:
            new_el.append(processed)

    # rPr 내부의 ins/del 마크 제거
    if tag == f"{W}rPr":
        for mark in list(new_el):
            if mark.tag in (f"{W}ins", f"{W}del"):
                new_el.remove(mark)

    return new_el


def build_redline_from_analysis(
    original_bytes: bytes,
    clause_results: list[dict],
    author: str = "퍼시스법무",
    date: str = "2026-05-15T00:00:00Z",
) -> tuple[bytes, bytes]:
    """
    aouri-bot clause_results를 Amendment 목록으로 변환하여 redline DOCX 생성.

    Args:
        original_bytes: 원본 계약서 DOCX bytes
        clause_results: build_clause_level_result()의 clause_results
        author: 작성자 표시명
        date: ISO 8601 날짜 문자열

    Returns:
        (redline_bytes, clean_bytes)
    """
    amendments: list[Amendment] = []

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        clause_id = str(cr.get("clause_id") or "")
        original_text = str(cr.get("original_text") or "").strip()
        suggested = str(cr.get("suggested_rewrite") or "").strip()
        reason = str(cr.get("rewrite_reason") or "").strip()
        risk_tier = str(cr.get("risk_tier") or "MEDIUM").upper()
        wcs = str(cr.get("worst_case_scenario") or "").strip()
        neg = str(cr.get("negotiation_strategy") or "").strip()

        # 수정 제안이 없거나 원문과 같으면 스킵
        if not suggested or not original_text or suggested == original_text:
            continue

        # 코멘트 텍스트 구성
        comment_parts = [f"[{risk_tier}] {reason[:100]}" if reason else f"[{risk_tier}] 수정 필요"]
        if wcs:
            comment_parts.append(f"최악 시나리오: {wcs[:80]}")
        if neg:
            comment_parts.append(f"협상 전략: {neg[:80]}")

        # 조항 번호 기반 article_pattern 추출
        # clause_id 예: "A-6", "EN-8", "P-3" 등
        m = re.search(r"(\d+)", clause_id)
        article_num = m.group(1) if m else ""
        # 한국어 계약서: "제N조", 영문: "N."
        patterns = []
        if article_num:
            patterns = [f"제{article_num}조", f"{article_num}.", f"Article {article_num}"]
        article_pattern = patterns[0] if patterns else original_text[:20]

        # 원문 → 수정안 교체 amendment 생성
        amendments.append(Amendment(
            article_pattern=article_pattern,
            insert_after_pattern=None,
            insert_paragraphs=[],
            replace_article_text=original_text[:40] if len(original_text) > 40 else original_text,
            replace_with_text=suggested,
            comment_text=" | ".join(comment_parts),
            risk_level=risk_tier,
            author=author,
            date=date,
        ))

    if not amendments:
        return original_bytes, original_bytes

    builder = RedlineBuilder(original_bytes, author=author, date=date)
    return builder.apply(amendments)
