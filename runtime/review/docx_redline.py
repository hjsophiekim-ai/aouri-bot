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
#: 변경내용·메모 작성자(2026-11-02 지시: "아우리봇" → 2026-11-13 지시: 메모 작성자 "법무팀").
DEFAULT_AUTHOR = "법무팀"
ACTION_CLASS = {"필수수정": "필수 수정", "권장수정": "협상 권고", "사업부 결정": "협상 권고",
                "체결 전 확인": "사실 확인", "현행 유지": "현행 유지"}


def action_class(cr: dict[str, Any]) -> str:
    """조치 구분 세 가지(필수 수정 / 협상 권고 / 사실 확인) — 화면·메모·검토의견서가 같은 이름을 쓴다."""
    cat = str(cr.get("review_category") or "").strip()
    if cat in ACTION_CLASS:
        return ACTION_CLASS[cat]
    return "필수 수정" if str(cr.get("risk_tier") or "").upper() == "HIGH" else "협상 권고"


def comment_text(cr: dict[str, Any]) -> str:
    """메모 — 수정 이유 / 우리 회사에 생길 위험 / 미확정 조건. 짧게, 확정되지 않은 법률 판단은 단정하지 않는다."""
    def one(*keys: str, limit: int = 260) -> str:
        for k in keys:
            v = " ".join(str(cr.get(k) or "").split())
            if v:
                return v if len(v) <= limit else v[:limit].rsplit(" ", 1)[0] + " …(검토의견서 참고)"
        return ""

    risk = str(cr.get("risk_tier") or "MEDIUM").upper()
    head = f"[{risk} · {action_class(cr)}] {str(cr.get('display_path') or '').strip()}".strip()
    reason = one("brief_action", "rewrite_reason", "problem")
    harm = one("brief_risk", "our_company_risk", "worst_case_scenario")
    und = [str(u).split(" — ")[0].strip() for u in cr.get("undecided_terms") or [] if str(u).strip()]
    lines = [head, f"수정 이유: {reason or '검토의견서 참고'}", f"우리 회사 위험: {harm or '검토의견서 참고'}",
             "미확정 조건: " + ("; ".join(dict.fromkeys(und)) + " — 서명 전 확정 필요" if und else "없음")]
    memo = " ".join(str(cr.get("drafting_memo") or "").split())
    if memo:
        # 본문에 넣지 않는 검토 의견(담보 요구 여부·선택지 등)은 메모에만 싣는다(2026-11-09)
        lines.append("검토 메모: " + (memo if len(memo) <= 300 else memo[:300].rsplit(" ", 1)[0] + " …"))
    lim = " ".join(str(cr.get("legal_limits") or "").split())
    if lim:
        lines.append("판단 한계: " + (lim if len(lim) <= 160 else lim[:160].rsplit(" ", 1)[0] + " …"))
    return "\n".join(lines)

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
    rpr: ET.Element | None = None,
) -> list[ET.Element]:
    """
    텍스트 교체 — 낱말 단위 차이만 <w:del>/<w:ins> 로, 그대로인 부분은 원래 서식의 일반 run 으로 둔다.
    OOXML 규격: del·ins 는 <w:p> 안에서 <w:r> 의 sibling 이어야 함.

    2026-11-02 지시 6항: 종전에는 단락 전체를 지우고 새 단락 전체를 넣어, 한 낱말만 고쳐도 조항 전체가 변경으로
    보였다. 모두 거절하면 old_text, 모두 수락하면 new_text 가 된다(text_diff 불변식).
    """
    from runtime.review.text_diff import diff_segments

    out: list[ET.Element] = []
    for op, txt in diff_segments(old_text, new_text):
        if op == "=":
            out.append(_make_run(txt, rpr))
        elif op == "-":
            del_el = ET.Element(f"{W}del")
            del_el.set(f"{W}id", str(ids.next()))
            del_el.set(f"{W}author", author)
            del_el.set(f"{W}date", date)
            del_r = ET.SubElement(del_el, f"{W}r")
            if rpr is not None:
                del_r.append(copy.deepcopy(rpr))
            del_t = ET.SubElement(del_r, f"{W}delText")
            del_t.text = txt
            if txt and (txt[0] == " " or txt[-1] == " "):
                del_t.set(XML_SPACE, "preserve")
            out.append(del_el)
        else:
            ins_el = ET.Element(f"{W}ins")
            ins_el.set(f"{W}id", str(ids.next()))
            ins_el.set(f"{W}author", author)
            ins_el.set(f"{W}date", date)
            ins_el.append(_make_run(txt, rpr))
            out.append(ins_el)
    return out


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


def _insert_after_ppr(para: ET.Element, el: ET.Element) -> None:
    """<w:pPr> 는 단락의 첫 자식이어야 한다(스키마) — 코멘트 시작 표지는 그 뒤에 넣는다."""
    ppr = para.find(f"{W}pPr")
    para.insert(list(para).index(ppr) + 1 if ppr is not None else 0, el)


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


# ── 수정 지시(redline_instruction) 해석 ─────────────────────────────────────────

_RX_DISPLAY_MARKER = re.compile(r"^\s*\[(?:추가\s*권고|수정\s*제안)[^\]]*\]\s*", re.MULTILINE)


def _strip_display_markers(text: str) -> str:
    """화면 표시용 표지("[추가 권고]")는 계약서 문안이 아니다 — 반영본에 넣지 않는다(2026-10-21)."""
    return re.sub(r"\n{3,}", "\n\n", _RX_DISPLAY_MARKER.sub("", str(text or ""))).strip()


_RX_ARTICLE_HEADING = re.compile(r"^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\s*(?:[(\[【<]|$)")
_RX_ARTICLE_LEAD = re.compile(r"^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?(?![가-힣]|\s*제\s*\d)")


#: 영문 조 제목 — "13. Term and Extraordinary Termination of the Agreement", "Article 13 Term", "Article 1. Purpose and Scope".
#: 번호 뒤 마침표를 허용하지 않으면 "Article 1. …" 제목을 못 알아봐 신설 항이 문서 끝(별지 뒤)에 들어갔다(2026-11-13 시디즈).
_RX_EN_ARTICLE_HEADING = re.compile(
    r"^\s*(?:(?:Article|Section)\s+\d{1,3}\.?(?![\d.])[^.;:]{0,90}|\d{1,2}\.\s+[A-Z][^.;:]{0,90})\s*$")


def _is_article_heading(text: str) -> bool:
    """괄호 제목("제 4 조 (지급)")이거나, 제N조로 시작하는 짧은 단락(괄호 없는 제목), 또는 영문 조 제목."""
    return bool(_RX_ARTICLE_HEADING.match(text) or (_RX_ARTICLE_LEAD.match(text) and len(text.strip()) <= 30)
                or _RX_EN_ARTICLE_HEADING.match(text))


def _article_end(paras: list[ET.Element], art_index: dict[str, list[int]], art: str) -> int | None:
    """조의 마지막 내용 단락 인덱스."""
    host = art_index.get(str(art))
    if not host:
        return None
    start = next((i for i in host if _is_article_heading(_para_text(paras[i]))), host[0])
    # 다음 조의 시작은 조 제목 단락으로만 본다 — 본문 속 "제9조 제3항에 따라" 같은 인용(방금 넣은 신설 항 포함)을
    # 다음 조로 보면 그 앞에서 조가 끝나, 뒤에 넣을 항이 앞서 넣은 항보다 먼저 들어간다(2026-10-21).
    end = next((i for i in range(start + 1, len(paras)) if _is_article_heading(_para_text(paras[i]))),
               len(paras)) - 1
    while end > start and not _para_text(paras[end]).strip():
        end -= 1
    return end


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
    # 유지 부분은 원래 서식으로 남긴다 — 첫 run 의 서식을 쓴다.
    first_run = next((el for el in para.iter(f"{W}r") if el.find(f"{W}t") is not None), None)
    rpr = first_run.find(f"{W}rPr") if first_run is not None else None
    rpr = copy.deepcopy(rpr) if rpr is not None else None
    # 기존 run 요소 (ins/del 제외) 수집 후 제거
    to_remove = [
        el for el in list(para)
        if el.tag in (f"{W}r", f"{W}ins", f"{W}del",
                      f"{W}commentRangeStart", f"{W}commentRangeEnd")
    ]
    for el in to_remove:
        para.remove(el)

    for el in _make_del_ins(old_text, new_text, ids, author, date, rpr):
        para.append(el)


def _substitute_in_para(
    para: ET.Element, target: str, replacement: str, ids: _IDGen, author: str, date: str,
    *, run_only: bool = False,
) -> bool:
    """단락 안의 한 문장만 del+ins 로 바꾼다. 문장이 한 run 안에 있으면 그 run 을 쪼개고(줄바꿈·서식 보존),
    여러 run 에 걸치면 단락 전체 문안에서 그 문장만 바꾼 결과로 교체한다(내용 보존)."""
    for run in [el for el in list(para) if el.tag == f"{W}r"]:
        kids = [c for c in list(run) if c.tag != f"{W}rPr"]
        hit = next((i for i, c in enumerate(kids) if c.tag == f"{W}t" and c.text and target in c.text), None)
        if hit is None:
            continue
        before, after = kids[hit].text.split(target, 1)
        rpr = run.find(f"{W}rPr")
        idx = list(para).index(run)
        para.remove(run)
        head = _make_run(before, rpr)
        if not before:
            head.remove(head.find(f"{W}t"))
        for k, c in enumerate(kids[:hit]):
            head.insert(len(head) - (1 if before else 0), c)  # 앞쪽 줄바꿈·글자는 원래 순서대로 t(before) 앞에
        tail = _make_run(after, rpr)
        if not after:
            tail.remove(tail.find(f"{W}t"))
        for c in kids[hit + 1:]:
            tail.append(c)
        new_els: list[ET.Element] = []
        if len([c for c in head if c.tag != f"{W}rPr"]):
            new_els.append(head)
        new_els.extend(_make_del_ins(target, replacement, ids, author, date, rpr))
        if len([c for c in tail if c.tag != f"{W}rPr"]):
            new_els.append(tail)
        for k, el in enumerate(new_els):
            para.insert(idx + k, el)
        return True
    if run_only:
        # 이미 다른 수정이 들어간 단락 — 삭제 표시된 글자까지 합친 문안으로 단락을 다시 쓰면 앞 수정이 사라진다.
        return False
    full = _para_text(para)
    if target not in full:
        return False
    _replace_para_with_tracked_changes(para, full, full.replace(target, replacement, 1), ids, author, date)
    return True


# ── 코멘트 XML 빌드 ─────────────────────────────────────────────────────────────

def _build_comments_xml(comments: list[dict[str, Any]]) -> bytes:
    # xmlns:w 는 ElementTree 가 붙인다 — 직접 또 넣으면 속성이 두 번 들어가 comments.xml 이 깨진 XML 이 된다
    # (Word: "읽을 수 없는 내용" 복구 대화상자, 2026-11-02 verify_change_set C1 에서 발견).
    root = ET.Element(f"{W}comments")
    for c in comments:
        cel = ET.SubElement(root, f"{W}comment")
        cel.set(f"{W}id", str(c["id"]))
        cel.set(f"{W}author", c["author"])
        cel.set(f"{W}date", c["date"])
        cel.set(f"{W}initials", c["author"][:2])
        # 줄마다 한 단락 — 메모 안의 "\n" 은 Word 에서 공백으로 보인다(수정 이유 / 위험 / 미확정 조건 구분이 사라짐).
        for line in [ln for ln in str(c["text"]).split("\n") if ln.strip()] or [""]:
            cp = ET.SubElement(cel, f"{W}p")
            cr = ET.SubElement(cp, f"{W}r")
            ct = ET.SubElement(cr, f"{W}t")
            ct.text = line
            ct.set(XML_SPACE, "preserve")
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


def _reject_all(root: ET.Element) -> ET.Element:
    """모든 변경 거절: w:ins(삽입 단락 포함) 제거, w:del 언래핑(delText→t), 코멘트 마크 제거 — 검증용."""

    def _proc(el: ET.Element) -> list[ET.Element]:
        tag = el.tag
        if tag == f"{W}ins":
            return []
        if tag in (f"{W}commentRangeStart", f"{W}commentRangeEnd"):
            return []
        if tag == f"{W}p":
            ppr = el.find(f"{W}pPr")
            mark = ppr.find(f"{W}rPr/{W}ins") if ppr is not None else None
            if mark is not None:
                return []  # 삽입된 단락은 통째로 사라진다
        if tag == f"{W}r" and el.find(f"{W}commentReference") is not None:
            return []
        if tag == f"{W}del":
            out: list[ET.Element] = []
            for child in list(el):
                out.extend(_proc(child))
            return out
        new = ET.Element("{%s}t" % W_NS if tag == f"{W}delText" else tag, el.attrib)
        new.text = el.text
        new.tail = el.tail
        for child in list(el):
            for repl in _proc(child):
                new.append(repl)
        if tag == f"{W}rPr":
            for mark in list(new):
                if mark.tag in (f"{W}ins", f"{W}del"):
                    new.remove(mark)
        return [new]

    results = _proc(root)
    return results[0] if results else root


def docx_paragraph_texts(docx_bytes: bytes, *, mode: str = "as_is") -> list[str]:
    """DOCX 본문 단락 텍스트. mode: as_is(삭제 표시 글자 제외·삽입 포함) | accept | reject — 검증용."""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    if mode == "accept":
        root = _accept_all(root)
    elif mode == "reject":
        root = _reject_all(root)
    body = root.find(f".//{W}body")
    out: list[str] = []
    for p in (body.iter(f"{W}p") if body is not None else []):
        out.append("".join(t.text or "" for t in p.iter(f"{W}t")))
    return out


def _enable_track_revisions(contents: dict[str, bytes]) -> None:
    """word/settings.xml 에 <w:trackRevisions/> — 받은 사람이 고쳐도 계속 변경내용 추적이 켜져 있다(지시 6항)."""
    key = "word/settings.xml"
    if key in contents:
        root = ET.fromstring(contents[key])
    else:
        root = ET.Element(f"{W}settings")
        rels_key = "word/_rels/document.xml.rels"
        if rels_key in contents:
            rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            rels = ET.fromstring(contents[rels_key])
            st = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings"
            if st not in [el.get("Type", "") for el in rels]:
                el = ET.SubElement(rels, f"{{{rel_ns}}}Relationship")
                el.set("Id", "rIdSettingsTR")
                el.set("Type", st)
                el.set("Target", "settings.xml")
                contents[rels_key] = ET.tostring(rels, encoding="unicode").encode("utf-8")
        ct_key = "[Content_Types].xml"
        if ct_key in contents:
            ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
            ct = ET.fromstring(contents[ct_key])
            if "/word/settings.xml" not in [el.get("PartName", "") for el in ct]:
                el = ET.SubElement(ct, f"{{{ct_ns}}}Override")
                el.set("PartName", "/word/settings.xml")
                el.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml")
                contents[ct_key] = ET.tostring(ct, encoding="unicode").encode("utf-8")
    if root.find(f"{W}trackRevisions") is None:
        # 스키마 순서상 앞쪽(writeProtection·view·zoom 등 뒤) — 맨 앞 몇 요소 뒤에 둔다.
        order = ("writeProtection", "view", "zoom", "removePersonalInformation", "removeDateAndTime",
                 "doNotDisplayPageBoundaries", "displayBackgroundShape", "printPostScriptOverText",
                 "printFractionalCharacterWidth", "printFormsData", "embedTrueTypeFonts", "embedSystemFonts",
                 "saveSubsetFonts", "saveFormsData", "mirrorMargins", "alignBordersAndEdges",
                 "bordersDoNotSurroundHeader", "bordersDoNotSurroundFooter", "gutterAtTop", "hideSpellingErrors",
                 "hideGrammaticalErrors", "activeWritingStyle", "proofState", "formsDesign", "attachedTemplate",
                 "linkStyles", "stylePaneFormatFilter", "stylePaneSortMethod", "documentType", "mailMerge",
                 "revisionView")
        pos = 0
        for i, child in enumerate(list(root)):
            if child.tag.replace(W, "") in order:
                pos = i + 1
        tr = ET.Element(f"{W}trackRevisions")
        root.insert(pos, tr)
    contents[key] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                     + ET.tostring(root, encoding="unicode")).encode("utf-8")


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


_RX_LEAD_NO = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|\(?[a-z0-9]{1,3}\)|\[[a-z0-9]{1,3}\]|제\s*\d+\s*조(?:\s*\([^)]*\))?|[①-⑳])\s*")


def _attach_change_segments(body: ET.Element, rep: list[dict[str, Any]],
                            touched: dict[int, tuple[list[ET.Element], str, dict[str, Any]]]) -> None:
    """변경추적본 자체에서 조항 범위별 변경 표시(유지/삭제/추가)를 읽어 보고 행에 붙인다.

    화면·검토의견서는 이 조각을 그대로 그린다 — 따로 다시 계산한 문안을 보여 주면 파일과 화면이 갈린다(2026-11-02 지시 4항).
    조항 범위 = 수정한 단락 + 같은 조항 원문에 속하는 앞뒤 단락(제9.9조처럼 한 조항이 여러 단락이면 함께 보인다).
    """
    from runtime.review.docx_splice import flat, is_inserted_paragraph, range_segments, reject_text

    paras = list(body.iter(f"{W}p"))
    pos = {id(p): i for i, p in enumerate(paras)}
    spans: list[tuple[int, int, int]] = []   # (lo, hi, rep index)
    for k, (ps, orig, _cr) in touched.items():
        idxs = sorted(pos[id(p)] for p in ps if id(p) in pos)
        if not idxs:
            continue
        cf = flat(orig)

        def part(i: int) -> bool:
            p = paras[i]
            if is_inserted_paragraph(p):
                return False
            t = _RX_LEAD_NO.sub("", flat(reject_text(p)))
            return len(t) >= 12 and bool(cf) and t[:80] in cf

        lo, hi = idxs[0], idxs[-1]
        while lo - 1 >= 0 and part(lo - 1):
            lo -= 1
        while hi + 1 < len(paras) and part(hi + 1):
            hi += 1
        spans.append((lo, hi, k))
    # 겹치는 범위는 한 묶음(한 조항 카드)으로.
    spans.sort()
    groups: list[list[Any]] = []
    for lo, hi, k in spans:
        if groups and lo <= groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], hi)
            groups[-1][2].append(k)
        else:
            groups.append([lo, hi, [k]])
    for g, (lo, hi, ks) in enumerate(groups, 1):
        segs = range_segments(paras[lo:hi + 1])
        before = "".join(t for op, t in segs if op in ("=", "-"))
        after = "".join(t for op, t in segs if op in ("=", "+"))
        for k in ks:
            rep[k].update({"change_group": g, "para_range": [lo, hi], "segments": segs,
                           "before": before, "after": after})


# ── 메인 함수 ──────────────────────────────────────────────────────────────────

def build_redline_docx(
    *,
    docx_bytes: bytes,
    original_clauses: list[dict[str, Any]],
    clause_results: list[dict[str, Any]],
    author: str = DEFAULT_AUTHOR,
    date: str | None = None,
    report: list[dict[str, Any]] | None = None,
    normalize_whitespace: bool = False,
    document_note: str = "",
) -> tuple[bytes, bytes]:
    """
    원본 계약서 DOCX + 검토 결과 → (redline_bytes, clean_bytes)

    report 를 넘기면 수정안마다 적용 결과({clause_id, path, status, reason})를 담는다 — 위치를 못 찾았거나 보류된
    수정안이 조용히 빠지지 않게(지시 6항: 위치 매칭이 불확실한 부분은 자동 적용을 보류하고 범위를 알린다).
    normalize_whitespace: PDF 를 변환한 DOCX 처럼 원문 줄바꿈이 단락 안 공백으로 바뀐 문서 — 대조할 문구의 공백을 맞춘다.

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
        # 보고서·화면이 수정안으로 보여 주는 것(HIGH/MEDIUM)만 반영한다. LOW(참고·기본 숨김) 문안까지 넣으면 보고서에 없는
        # 수정이 수정본에 들어가고, 검증되지 않은 문안이 엉뚱한 단락을 덮는다(2026-10-30 실측: 제4조 제3항용 문안이 담보
        # 조건이 든 제4조 제2항을, 참고 문안이 제1조 소재지 줄을 덮었다).
        and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
    ]

    # 항 신설은 교체를 마친 뒤 항 번호 순으로 넣는다 — 같은 조 끝에 차례로 붙이므로 처리 순서가 곧 항 순서다
    # (2026-10-21: ⑪ 이 ⑩ 보다 먼저 들어갔다).
    def _insert_order(cr: dict[str, Any]) -> tuple[int, int, int]:
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        if str(ri.get("edit_type") or "") not in ("insert_after", "new_clause"):
            return (0, 0, 0)
        m = re.search(r"제\s*(\d+)\s*조[^\n]*?제\s*(\d+)\s*(?:항|조)\s*신설", str(ri.get("edit_location") or ""))
        return (1, int(m.group(1)), int(m.group(2))) if m else (1, 9999, 0)

    applicable.sort(key=_insert_order)

    # 처리된 단락 추적 (중복 적용 방지)
    processed_paras: set[int] = set()

    _rep = report if report is not None else []
    #: 보고 행 번호 → (건드린 단락들, 조항 원문) — 끝에서 변경추적본을 읽어 화면·검토의견서용 변경 표시를 만든다.
    _touched: dict[int, tuple[list[ET.Element], str, dict[str, Any]]] = {}

    def _note(cr_: dict[str, Any], status: str, reason: str = "", paras: list[ET.Element] | None = None,
              comment_id: int | None = None, c_text: str = "") -> None:
        _rep.append({"clause_id": str(cr_.get("clause_id") or ""), "path": str(cr_.get("display_path") or ""),
                     "status": status, "reason": reason,
                     **({"comment_id": comment_id, "comment_text": c_text} if comment_id is not None else {})})
        if paras:
            _touched[len(_rep) - 1] = (list(paras), str(cr_.get("original_text") or ""), cr_)

    def _comment(cr_: dict[str, Any]) -> tuple[int, str]:
        c_id = comment_id_counter[0]
        comment_id_counter[0] += 1
        txt = comment_text(cr_)
        comments.append({"id": c_id, "author": author, "date": date, "text": txt})
        return c_id, txt

    def _splice(cr_: dict[str, Any], target: str, replacement: str) -> bool:
        """고칠 문장이 든 단락 하나를 찾아 그 구간만 변경추적한다. 처리했으면(적용·보류 모두) True."""
        from runtime.review.docx_splice import anchor_comment, find_in_paragraph, flat, splice_tracked

        paras_all = list(body.iter(f"{W}p"))
        hits = [(p, se) for p in paras_all for se in find_in_paragraph(p, target)]
        if len(hits) > 1:
            clause_flat = flat(str(cr_.get("original_text") or ""))
            inside = [(p, se) for p, se in hits if flat(_para_text(p)) and flat(_para_text(p))[:60] in clause_flat]
            hits = inside if inside else hits
        if not hits:
            # 한 문장이 여러 단락에 걸친 경우(PDF 변환본 제9.9조 "…demand:" / "(a) …") — 단락마다 그 단락 몫만 변경추적한다.
            from runtime.review.docx_splice import find_across_paragraphs, split_replacement

            spans_ = find_across_paragraphs([el for el in body if el.tag == f"{W}p"], target)
            if len(spans_) > 1:
                clause_flat = flat(str(cr_.get("original_text") or ""))
                inside_ = [sp for sp in spans_ if flat(_para_text(sp[0][0]))[:60] in clause_flat]
                spans_ = inside_ or spans_
            if len(spans_) == 1:
                pieces = spans_[0]
                olds = []
                for p_, s_, e_ in pieces:
                    from runtime.review.docx_splice import _spans as _sp
                    olds.append(_sp(p_)[0][s_:e_])
                news = split_replacement(olds, replacement)
                done: list[tuple[ET.Element, tuple[ET.Element, ET.Element]]] = []
                for (p_, s_, e_), new_ in zip(pieces, news):
                    r_ = splice_tracked(p_, s_, e_, new_, next_id=ids.next, author=author, date=date)
                    if r_ is not None:
                        done.append((p_, r_))
                if not done:
                    _note(cr_, "no_text", "원문과 수정 문구가 같음 — 바꿀 것이 없음")
                    return True
                c_id, txt = _comment(cr_)
                anchor_comment(done[0][0], done[0][1][0], done[-1][0], done[-1][1][1], c_id)
                _note(cr_, "applied", f"문장 교체({len(pieces)}개 단락에 걸침)", paras=[p_ for p_, _, _ in pieces],
                      comment_id=c_id, c_text=txt)
                return True
            _note(cr_, "not_found", "고칠 문장을 문서에서 찾지 못함(변환 누락 또는 원문과 다른 문구) — 자동 적용 보류, "
                                    "현재 문구 유지" if not spans_ else
                  f"같은 문장이 문서에 {len(spans_)}곳 있어 위치를 확정하지 못함 — 자동 적용 보류")
            return True
        if len(hits) > 1:
            _note(cr_, "not_found", f"같은 문장이 문서에 {len(hits)}곳 있어 위치를 확정하지 못함 — 자동 적용 보류")
            return True
        p, (s, e) = hits[0]
        res = splice_tracked(p, s, e, replacement, next_id=ids.next, author=author, date=date)
        if res is None:
            _note(cr_, "no_text", "원문과 수정 문구가 같음 — 바꿀 것이 없음")
            return True
        c_id, txt = _comment(cr_)
        anchor_comment(p, res[0], p, res[1], c_id)
        _note(cr_, "applied", "문장 교체", paras=[p], comment_id=c_id, c_text=txt)
        return True

    def _ws(x: str) -> str:
        return " ".join(str(x or "").split()) if normalize_whitespace else str(x or "")

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
        original_text = _ws(str(cr.get("original_text") or "")).strip()
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
        # 수정 지시가 있으면 그것을 따른다 — 위치·방식·보류 판단은 검토 파이프라인이 수정안 전부를 함께 놓고
        # 한 것이다. 종전에는 suggested_rewrite 로 근거 원문 단락을 교체해, "항 신설" 로 정한 문안이 근거 호(예:
        # "오프닝 PPL (30만 조회수 보장)")를 덮어썼고 자동 적용 보류도 무시됐다(2026-10-21).
        _ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        if _ri.get("held"):
            _note(cr, "held", str(_ri.get("hold_reason") or "자동 적용 보류"))
            continue
        if normalize_whitespace and _ri:
            _ri = dict(_ri)
            for _k in ("target_text", "replacement_text"):
                if _ri.get(_k):
                    # 표시용 표지("[추가 권고]")는 줄 머리 기준으로 지운다 — 공백을 먼저 합치면 줄 중간에 남아 계약서에 들어간다.
                    _ri[_k] = _ws(_strip_display_markers(str(_ri[_k])))
        _final = _strip_display_markers(str(_ri.get("final_clause_text") or _ri.get("replacement_text") or ""))
        if str(_ri.get("edit_type") or "") in ("insert_after", "new_clause") and _final:
            _loc = str(_ri.get("edit_location") or "")
            _all = [el for el in body if el.tag == f"{W}p"]
            _idx = _build_article_index(_all)
            _m_art = re.search(r"제\s*(\d+)\s*조", _loc) or re.search(r"(?:Article|Section|Clause)\s+(\d+)", _loc, re.I)
            _host = _m_art.group(1) if _m_art else article_number
            _end = _article_end(_all, _idx, _host) if _host else None
            if _end is None and _idx:
                _last = max(_idx, key=lambda k: _idx[k][0])
                _end = _article_end(_all, _idx, _last)
            if _end is None:
                _note(cr, "not_found", f"신설 위치({_loc})의 조를 문서에서 찾지 못함")
                continue
            _after = _all[_end]
            _base = _after.find(f"{W}pPr")
            _at = list(body).index(_after) + 1
            _lines = [ln.strip() for ln in _final.split("\n") if ln.strip()]
            _m_new = re.search(r"제\s*(\d+)\s*조(?:\s*의\s*\d+)?\s*신설", _loc)
            # 영문 항 신설("Article 13.4 신설") — 새 단락이 번호로 시작해야 계약서 안에서 항으로 읽힌다.
            _m_en_new = re.search(r"(?:Article|Section|Clause)\s+(\d+\.\d+)\s*신설", _loc, re.I)
            if _m_en_new and _lines and not re.match(r"^\s*\d+\.\d+", _lines[0]):
                _lines[0] = f"{_m_en_new.group(1)} {_lines[0]}"
            if str(_ri.get("edit_type")) == "new_clause" and _m_new and not re.match(r"^\s*제\s*\d+\s*조", _lines[0]):
                _lines.insert(0, _m_new.group(0).replace("신설", "").strip())
            _new_ps: list[ET.Element] = []
            for _ln in _lines:
                _np = _make_ins_paragraph(_ln, ids, author, date, _base)
                body.insert(_at, _np)
                _at += 1
                _new_ps.append(_np)
            if not _new_ps:
                _note(cr, "no_text", "반영할 문구가 없음")
                continue
            from runtime.review.docx_splice import anchor_comment
            c_id, c_txt = _comment(cr)
            anchor_comment(_new_ps[0], _new_ps[0].find(f"{W}ins"), _new_ps[-1], _new_ps[-1].find(f"{W}ins"), c_id)
            _note(cr, "applied", "신설", paras=_new_ps, comment_id=c_id, c_text=c_txt)
            continue
        # 문장 교체(조항 지목 요청 검토 등 target_text 가 있는 수정): 그 문장이 든 단락의 그 구간만 바꾼다 — 서식·다른 문장 보존.
        _tt = str(_ri.get("target_text") or "").strip()
        _rt = _strip_display_markers(str(_ri.get("replacement_text") or "")).strip()
        if (str(_ri.get("edit_type") or "") == "replace" and _tt
                and (_rt or str(_ri.get("edit_mode") or "") == "delete") and cr.get("is_requested_clause_review")):
            _splice(cr, _tt, _rt)
            continue
        if _final and str(_ri.get("edit_type") or "") == "replace":
            suggested = _final
        suggested = _ws(_strip_display_markers(suggested)) if normalize_whitespace else _strip_display_markers(suggested)
        addition_text = _strip_display_markers(addition_text)
        if not suggested and not has_addition:
            _note(cr, "no_text", "반영할 문구가 없음")
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
            _note(cr, "not_found", "고칠 단락을 문서에서 찾지 못함 — 자동 적용 보류")
            continue
        if para_idx in processed_paras:
            # 한 Word 단락에 여러 호가 들어 있으면(제14조 제6항 제1~4호) 서로 다른 문장을 고치는 수정이 같은 단락을 가리킨다.
            # 종전에는 두 번째 수정을 건너뛰어, 보고서·전체반영 검사에는 있는 주차장 승계 문구가 수정본에 빠졌다(2026-10-30 실측).
            # 문장 단위 수정은 함께 반영하고, 단락 전체 교체만 한 번으로 막는다.
            _ri2 = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
            _t2 = str(_ri2.get("target_text") or "").strip()
            _r2 = _strip_display_markers(str(_ri2.get("replacement_text") or "")).strip()
            _same_para = all_paras[para_idx]
            if (str(_ri2.get("edit_type") or "") == "replace" and _t2 and _r2
                    and _substitute_in_para(_same_para, _t2, _r2, ids, author, date, run_only=True)):
                c_id, c_txt = _comment(cr)
                crs, cre, ref = _make_comment_markup(c_id)
                _insert_after_ppr(_same_para, crs)
                _same_para.append(cre)
                _same_para.append(ref)
                _note(cr, "applied", "같은 단락의 다른 문장", paras=[_same_para], comment_id=c_id, c_text=c_txt)
            else:
                _note(cr, "not_found", "이미 수정한 단락 안에서 고칠 문장을 찾지 못함 — 자동 적용 보류")
            continue
        processed_paras.add(para_idx)

        target_para = all_paras[para_idx]
        base_ppr = target_para.find(f"{W}pPr")

        # ── 수정 적용 ──────────────────────────────────────────────────────────
        # [추가] 패턴: 원본 단락은 그대로 유지하고 새 단락만 삽입
        if has_addition and addition_text and not bool(cr.get("has_rewrite_change")):
            body_children = list(body)
            insert_at = body_children.index(target_para) + 1
            _added: list[ET.Element] = []
            for line in addition_text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                new_p = _make_ins_paragraph(line, ids, author, date, base_ppr)
                body.insert(insert_at, new_p)
                insert_at += 1
                _added.append(new_p)
            # 메모는 추가한 단락(변경 범위)에 건다.
            c_id, c_txt = _comment(cr)
            if _added:
                from runtime.review.docx_splice import anchor_comment
                anchor_comment(_added[0], _added[0].find(f"{W}ins"), _added[-1], _added[-1].find(f"{W}ins"), c_id)
            else:
                crs, cre, ref = _make_comment_markup(c_id)
                _insert_after_ppr(target_para, crs)
                target_para.append(cre)
                target_para.append(ref)
            _note(cr, "applied", "항 추가", paras=[target_para] + _added, comment_id=c_id, c_text=c_txt)
            continue

        # 일반 수정: del+ins 교체 또는 신규 단락 삽입
        # 문장 단위 보완(2026-10-30): 교체 대상이 단락 안의 한 문장이면 그 문장만 바꾼다. 한 Word 단락에 여러 항·호가
        # 줄바꿈으로 들어 있으면(제14조 제6항 제1~4호) 단락 전체를 문장 하나로 바꿀 때 다른 호(연대보증·주차장 승인)가 사라지고,
        # 거의 같은 문안이라 "신규 항 추가" 로 처리하면 같은 단락이 중복된다.
        _sub_target = str(_ri.get("target_text") or "").strip()
        _sub_repl = _strip_display_markers(str(_ri.get("replacement_text") or "")).strip()
        _substituted = (
            str(_ri.get("edit_type") or "") == "replace" and bool(_sub_target) and bool(_sub_repl)
            and _sub_target in _para_text(target_para) and len(_sub_target) <= len(_para_text(target_para))
            and _substitute_in_para(target_para, _sub_target, _sub_repl, ids, author, date)
        )
        if _substituted:
            pass
        else:
            # 단락의 **실제 문안**을 기준으로 바꾼다. 조항 원문(original_text)을 기준으로 지우고 쓰면 단락 머리의 번호
            # ("13.1 ")처럼 원문에 없는 글자가 사라져, 모두 거절해도 원본으로 돌아가지 않는다. 종전의 "거의 같으면 새 단락
            # 추가" 분기는 같은 조항을 한 번 더 넣어 원문이 중복됐다 — 낱말 단위 차이로 바뀐 부분만 표시한다(2026-11-02).
            para_now = _para_text(target_para)
            old_core = original_text if original_text in para_now else ""
            if not old_core and _ws(para_now).strip() == original_text:
                old_core = para_now.strip()
            if not old_core and _text_sim(" ".join(para_now.split()), " ".join(original_text.split())) < 0.6:
                # 고칠 문장도 조항 원문도 이 단락에 없다 — 조항이 여러 단락에 걸쳐 있다. 단락 하나를 조항 전체 문안으로
                # 덮으면 제목·다른 문장이 중복되므로 넣지 않고 보류로 알린다(2026-11-02 지시 6항: 위치 불확실 → 자동 적용 보류).
                processed_paras.discard(para_idx)
                _note(cr, "not_found", "고칠 문장이 여러 단락에 걸쳐 있어 위치를 확정하지 못함 — 자동 적용 보류")
                continue
            if old_core:
                new_full = para_now.replace(old_core, suggested, 1)
            else:
                lead = re.match(r"^\s*(?:\d+(?:\.\d+)*\.?|제\s*\d+\s*조(?:\s*\([^)]*\))?|[①-⑳]|\(\d+\))\s*", para_now)
                lead_txt = lead.group(0) if lead and not suggested.startswith(lead.group(0).strip()) else ""
                new_full = lead_txt + suggested
            _replace_para_with_tracked_changes(target_para, para_now, new_full, ids, author, date)
        _extra: list[ET.Element] = []
        if not _substituted and has_addition and addition_text:
            # [추가] 블록이 별도로 있으면 교체 후 추가 삽입
            body_children = list(body)
            insert_at = body_children.index(target_para) + 1
            for line in addition_text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                new_p = _make_ins_paragraph(line, ids, author, date, base_ppr)
                body.insert(insert_at, new_p)
                insert_at += 1
                _extra.append(new_p)

        # ── 메모: 수정 이유 / 위험 / 미확정 조건 ────────────────────────────────
        c_id, c_txt = _comment(cr)
        crs, cre, ref = _make_comment_markup(c_id)
        _insert_after_ppr(target_para, crs)
        target_para.append(cre)
        target_para.append(ref)
        _note(cr, "applied", "문장 교체" if _substituted else "단락 수정", paras=[target_para] + _extra,
              comment_id=c_id, c_text=c_txt)

    # ── 문서 안내 코멘트 — 변환본 여부·자동 적용 보류 범위를 계약 본문이 아니라 Word 코멘트로 알린다 ─────────────
    _held_notes = [f"{r['path'] or r['clause_id']}: {r['reason']}" for r in _rep if r.get("status") != "applied"]
    _und_n = sum(len(t[2].get("undecided_terms") or []) for t in _touched.values())
    _note_text = " ".join(x for x in (
        (f"[협상 초안 · 서명 전 확정 필요] 수정 문구에 합의되지 않은 값·빈칸 {_und_n}건이 있습니다(메모의 '미확정 조건')."
         if _und_n else ""),
        document_note,
        ("자동 적용 보류(현재 문구 유지): " + "; ".join(_held_notes)) if _held_notes else "",
    ) if x)
    _first_para = next((el for el in body if el.tag == f"{W}p" and _para_text(el).strip()), None)
    if _note_text and _first_para is not None:
        c_id = comment_id_counter[0]
        comment_id_counter[0] += 1
        comments.append({"id": c_id, "author": author, "date": date, "text": f"[안내] {_note_text}"})
        crs, cre, ref = _make_comment_markup(c_id)
        _ppr = _first_para.find(f"{W}pPr")
        _first_para.insert(1 if _ppr is not None else 0, crs)
        _first_para.append(cre)
        _first_para.append(ref)

    _attach_change_segments(body, _rep, _touched)

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
    clean_contents = _build_clean_docx(contents)
    _enable_track_revisions(contents)
    redline_bytes = _pack_docx(contents)
    clean_bytes = _pack_docx(clean_contents)

    return redline_bytes, clean_bytes


def generate_redline(
    contract_path: str | Path,
    original_clauses: list[dict[str, Any]],
    clause_results: list[dict[str, Any]],
    output_dir: str | Path | None = None,
    author: str = DEFAULT_AUTHOR,
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
