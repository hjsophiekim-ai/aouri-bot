"""Word 단락 안의 한 구간만 실제 변경내용 추적(w:del/w:ins)으로 바꾸고, 변경 범위를 읽어 내는 도구.

2026-11-02 지시(변경추적본·화면 일치)
──────────────────────────────────────
종전 엔진은 고칠 문장이 여러 run 에 걸치면 단락 전체를 지우고 첫 run 서식으로 다시 썼다 — 굵게·밑줄·글꼴이 섞인 원본
DOCX 의 서식이 수정 대상 밖에서도 바뀌었다. 또 조항이 두 단락에 걸쳐 있으면(PDF 변환본의 제9.9조: "…demand:" / "(a) …")
첫 단락에 조항 전체 문안을 써 넣어, 클린본에 같은 문장이 두 번 들어갔다.

여기서는
  · 단락의 직계 run 글자 위치를 계산해, 고칠 구간 경계에서만 run 을 쪼갠다(나머지 run 은 서식째 그대로).
  · 낱말 차이(text_diff)대로 유지 run 은 두고, 지울 run 은 w:del 로 감싸 w:delText 로, 넣을 글자는 w:ins 로 넣는다.
  · 변경의 첫·끝 요소를 돌려줘, 메모(commentRangeStart/End)가 실제 변경 범위에 걸리게 한다.
  · 변경추적본에서 단락별 (유지/삭제/추가) 조각을 읽어, 화면·검토의견서가 파일과 같은 변경 표시를 쓰게 한다.
"""
from __future__ import annotations

import copy
import re
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

#: 직계 run 이 아닌데 글자를 품을 수 있는 요소 — 그 앞뒤로 문장이 이어진 것으로 보지 않는다(경계).
_BARRIER = {f"{W}{t}" for t in ("ins", "del", "hyperlink", "smartTag", "sdt", "fldSimple", "customXml", "moveFrom", "moveTo")}
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', " ": " "})


def _t_text(run: ET.Element) -> str:
    return "".join(c.text or "" for c in run if c.tag == f"{W}t")


def _spans(para: ET.Element) -> tuple[str, list[tuple[ET.Element, int, int]]]:
    """단락의 매칭용 글자열과 직계 run 별 [start, end). 경계 요소 자리는 \\x00 한 글자."""
    buf: list[str] = []
    spans: list[tuple[ET.Element, int, int]] = []
    pos = 0
    for el in list(para):
        if el.tag == f"{W}r":
            t = _t_text(el)
            spans.append((el, pos, pos + len(t)))
            buf.append(t)
            pos += len(t)
        elif el.tag in _BARRIER:
            buf.append("\x00")
            pos += 1
    return "".join(buf), spans


def _norm_map(raw: str) -> tuple[str, list[int]]:
    """공백 묶음을 한 칸으로, 굽은 따옴표를 곧은 따옴표로 — 정규화 글자 i 가 원문 몇 번째 글자인지 함께."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(raw.translate(_QUOTES)):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch)
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def find_in_paragraph(para: ET.Element, target: str) -> list[tuple[int, int]]:
    """target 이 단락 직계 run 글자에 나오는 [start, end) 원문 위치들(공백·따옴표 차이 무시)."""
    raw, _ = _spans(para)
    norm, idx = _norm_map(raw)
    t, _ = _norm_map(" ".join(str(target or "").split()))
    t = t.strip()
    if not t:
        return []
    out: list[tuple[int, int]] = []
    start = 0
    while True:
        k = norm.find(t, start)
        if k < 0:
            break
        s, e = idx[k], idx[k + len(t) - 1] + 1
        if "\x00" not in raw[s:e]:
            out.append((s, e))
        start = k + 1
    return out


def _split_run(run: ET.Element, k: int) -> tuple[ET.Element, ET.Element]:
    rpr = run.find(f"{W}rPr")
    left, right = ET.Element(run.tag, run.attrib), ET.Element(run.tag, run.attrib)
    if rpr is not None:
        left.append(copy.deepcopy(rpr))
        right.append(copy.deepcopy(rpr))
    pos = 0
    for c in list(run):
        if c.tag == f"{W}rPr":
            continue
        if c.tag == f"{W}t":
            s = c.text or ""
            if pos + len(s) <= k:
                left.append(copy.deepcopy(c))
            elif pos >= k:
                right.append(copy.deepcopy(c))
            else:
                a, b = copy.deepcopy(c), copy.deepcopy(c)
                a.text, b.text = s[: k - pos], s[k - pos:]
                for x in (a, b):
                    x.set(XML_SPACE, "preserve")
                left.append(a)
                right.append(b)
            pos += len(s)
        else:
            (left if pos <= k else right).append(copy.deepcopy(c))
    return left, right


def _split_at(para: ET.Element, offset: int) -> None:
    _, spans = _spans(para)
    for run, s, e in spans:
        if s < offset < e:
            left, right = _split_run(run, offset - s)
            i = list(para).index(run)
            para.remove(run)
            para.insert(i, right)
            para.insert(i, left)
            return


def _new_run(text: str, rpr: ET.Element | None) -> ET.Element:
    r = ET.Element(f"{W}r")
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = ET.SubElement(r, f"{W}t")
    t.text = text
    t.set(XML_SPACE, "preserve")
    return r


def splice_tracked(
    para: ET.Element, start: int, end: int, replacement: str, *, next_id, author: str, date: str,
) -> tuple[ET.Element, ET.Element] | None:
    """단락의 원문 [start, end) 를 replacement 로 바꾸는 변경내용 추적을 넣는다. (첫 변경 요소, 끝 변경 요소) 또는 None."""
    from runtime.review.text_diff import diff_segments

    raw, _ = _spans(para)
    old = raw[start:end]
    segs = diff_segments(old, replacement)
    if not any(op != "=" for op, _ in segs):
        return None
    cuts = {start, end}
    pos = start
    for op, txt in segs:
        if op in ("=", "-"):
            cuts.add(pos)
            pos += len(txt)
            cuts.add(pos)
    for c in sorted(cuts, reverse=True):
        _split_at(para, c)
    _, spans = _spans(para)
    first: ET.Element | None = None
    last: ET.Element | None = None
    anchor: ET.Element | None = None   # 다음 추가 글자를 넣을 자리(이 요소 뒤)
    pos = start

    def runs_in(a: int, b: int) -> list[ET.Element]:
        return [r for r, s, e in spans if s >= a and e <= b and e > s]

    def rpr_near(p: int) -> ET.Element | None:
        cand = [r for r, s, e in spans if s <= p <= e and e > s] or [r for r, s, e in spans if e > s]
        r = cand[0] if cand else None
        return r.find(f"{W}rPr") if r is not None else None

    for op, txt in segs:
        if op == "=":
            rs = runs_in(pos, pos + len(txt))
            if rs:
                anchor = rs[-1]
            pos += len(txt)
        elif op == "-":
            rs = runs_in(pos, pos + len(txt))
            if not rs:
                return None
            d = ET.Element(f"{W}del", {f"{W}id": str(next_id()), f"{W}author": author, f"{W}date": date})
            para.insert(list(para).index(rs[0]), d)
            for r in rs:
                para.remove(r)
                for t in r.findall(f"{W}t"):
                    t.tag = f"{W}delText"
                    t.set(XML_SPACE, "preserve")
                d.append(r)
            first = first if first is not None else d
            last = anchor = d
            pos += len(txt)
        else:
            ins = ET.Element(f"{W}ins", {f"{W}id": str(next_id()), f"{W}author": author, f"{W}date": date})
            ins.append(_new_run(txt, rpr_near(pos)))
            if anchor is not None:
                para.insert(list(para).index(anchor) + 1, ins)
            else:
                nxt = next((r for r, s, e in spans if s >= pos), None)
                if nxt is not None and nxt in list(para):
                    para.insert(list(para).index(nxt), ins)
                else:
                    para.append(ins)
            first = first if first is not None else ins
            last = anchor = ins
    if first is None or last is None:
        return None
    return first, last


def find_across_paragraphs(paras: list[ET.Element], target: str, *, max_span: int = 12
                           ) -> list[list[tuple[ET.Element, int, int]]]:
    """target 이 이어진 여러 단락에 걸쳐 나오는 위치들 — 각 위치는 단락별 [start, end) 원문 조각 목록.

    PDF 변환본의 제9.9조처럼 한 문장이 "…demand:" / "(a) …" 두 단락에 걸치면 한 단락 안에서는 찾을 수 없다
    (2026-11-03 Norden: 포괄 면책 축소 수정이 '위치 미확정' 으로 보류돼 변경추적본에 빠졌다). 단락 경계는 공백 하나로 본다.
    """
    t, _ = _norm_map(" ".join(str(target or "").split()))
    t = t.strip()
    if not t:
        return []
    infos = []
    for p in paras:
        raw, _ = _spans(p)
        norm, idx = _norm_map(raw)
        infos.append((p, raw, norm, idx))
    found: list[list[tuple[ET.Element, int, int]]] = []
    for i in range(len(infos)):
        joined = ""
        bounds: list[tuple[int, int, int]] = []   # (정규화 결합 문자열 시작, 끝, 단락 번호)
        for j in range(i, min(len(infos), i + max_span)):
            norm = infos[j][2]
            if joined and not joined.endswith(" ") and not norm.startswith(" "):
                joined += " "
            bounds.append((len(joined), len(joined) + len(norm), j))
            joined += norm
            if j == i:
                continue
            k = joined.find(t)
            if k < 0 or k >= bounds[0][1]:
                continue   # 첫 단락에서 시작하지 않으면 다음 시작점이 찾는다
            end = k + len(t)
            if end <= bounds[-2][1]:
                break      # 마지막 단락까지 가지 않음 — 더 짧은 범위에서 이미 끝나는 경우(한 단락 매칭은 따로)
            pieces: list[tuple[ET.Element, int, int]] = []
            for a, b, jj in bounds:
                s, e = max(a, k), min(b, end)
                if s >= e:
                    continue
                _p, raw, _n, idx = infos[jj]
                rs, re_ = idx[s - a], idx[e - a - 1] + 1
                if "\x00" in raw[rs:re_]:
                    pieces = []
                    break
                pieces.append((_p, rs, re_))
            if len(pieces) >= 2:
                found.append(pieces)
            break
    return found


def split_replacement(olds: list[str], replacement: str) -> list[str]:
    """여러 단락에 걸친 원문 조각들(olds)을 replacement 로 바꿀 때, 단락별 새 글자를 낱말 차이로 나눈다.

    유지·삭제 글자는 원래 단락에, 추가 글자는 그 자리가 속한 단락(경계면 앞 단락)에 둔다 — 각 단락을 따로 변경추적하면
    단락 구조(번호·들여쓰기)가 그대로 남는다.
    """
    from runtime.review.text_diff import diff_segments

    joined = " ".join(olds)
    owner: list[int] = []
    for k, o in enumerate(olds):
        owner.extend([k] * len(o))
        if k < len(olds) - 1:
            owner.append(-1)   # 경계 공백
    news = [""] * len(olds)
    pos = 0
    last = 0
    for op, txt in diff_segments(joined, replacement):
        if op == "+":
            news[last] += txt
            continue
        for ch in txt:
            o = owner[pos] if pos < len(owner) else len(olds) - 1
            if o >= 0:
                last = o
                if op == "=":
                    news[o] += ch
            pos += 1
    return news


def anchor_comment(para_first: ET.Element, first: ET.Element, para_last: ET.Element, last: ET.Element,
                   comment_id: int) -> None:
    """메모를 변경 범위(first..last)에 건다 — 단락 전체가 아니라 실제로 바뀐 부분."""
    crs = ET.Element(f"{W}commentRangeStart", {f"{W}id": str(comment_id)})
    cre = ET.Element(f"{W}commentRangeEnd", {f"{W}id": str(comment_id)})
    ref = ET.Element(f"{W}r")
    rpr = ET.SubElement(ref, f"{W}rPr")
    ET.SubElement(rpr, f"{W}rStyle", {f"{W}val": "CommentReference"})
    ET.SubElement(ref, f"{W}commentReference", {f"{W}id": str(comment_id)})
    para_first.insert(list(para_first).index(first), crs)
    i = list(para_last).index(last) + 1
    para_last.insert(i, cre)
    para_last.insert(i + 1, ref)


# ── 변경추적본 읽기 ──────────────────────────────────────────────────────────

def is_inserted_paragraph(p: ET.Element) -> bool:
    ppr = p.find(f"{W}pPr")
    return ppr is not None and ppr.find(f"{W}rPr/{W}ins") is not None


def paragraph_segments(p: ET.Element) -> list[tuple[str, str]]:
    """단락의 (op, 글자) — "=" 유지 · "-" 삭제 · "+" 추가. 메모 표지 run(commentReference)은 글자가 없어 빠진다."""
    out: list[tuple[str, str]] = []
    ins_para = is_inserted_paragraph(p)
    for el in list(p):
        if el.tag == f"{W}r":
            t = _t_text(el)
            if t:
                out.append(("+" if ins_para else "=", t))
        elif el.tag == f"{W}del":
            t = "".join(x.text or "" for x in el.iter(f"{W}delText"))
            if t:
                out.append(("-", t))
        elif el.tag == f"{W}ins":
            t = "".join(x.text or "" for x in el.iter(f"{W}t"))
            if t:
                out.append(("+", t))
        elif el.tag in _BARRIER:
            t = "".join(x.text or "" for x in el.iter(f"{W}t"))
            if t:
                out.append(("+" if ins_para else "=", t))
    return out


def reject_text(p: ET.Element) -> str:
    return "".join(t for op, t in paragraph_segments(p) if op in ("=", "-")) if not is_inserted_paragraph(p) else ""


def coalesce(segs: list[tuple[str, str]]) -> list[list[str]]:
    out: list[list[str]] = []
    for op, t in segs:
        if not t:
            continue
        if out and out[-1][0] == op:
            out[-1][1] += t
        else:
            out.append([op, t])
    return out


def range_segments(paras: list[ET.Element]) -> list[list[str]]:
    segs: list[tuple[str, str]] = []
    for i, p in enumerate(paras):
        if i:
            segs.append(("+" if is_inserted_paragraph(p) else "=", "\n"))
        segs.extend(paragraph_segments(p))
    return coalesce(segs)


def flat(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").translate(_QUOTES)).strip()


__all__ = ["anchor_comment", "coalesce", "find_across_paragraphs", "find_in_paragraph", "flat", "is_inserted_paragraph",
           "paragraph_segments", "range_segments", "reject_text", "splice_tracked", "split_replacement"]
