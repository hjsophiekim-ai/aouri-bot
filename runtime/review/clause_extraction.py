from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from runtime.review.word_markers import contains_wordprocessingml_markers


@dataclass(frozen=True)
class ClauseChunk:
    clause_id: str
    article_number: str | None
    paragraph_number: str | None
    item_number: str | None
    subitem_number: str | None
    display_path: str
    parent_clause_id: str | None
    context_text: str | None
    title: str
    text: str


@dataclass(frozen=True)
class ClauseExtractionReport:
    strategy: str
    clause_count: int
    headings_found: bool
    fallback_only: bool
    dropped_lines: int
    split_long_clauses: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "clause_count": self.clause_count,
            "headings_found": self.headings_found,
            "fallback_only": self.fallback_only,
            "dropped_lines": self.dropped_lines,
            "split_long_clauses": self.split_long_clauses,
            "warnings": list(self.warnings),
        }


_RX_XML_TAG_LINE = re.compile(r"^\s*</?[A-Za-z0-9]+:[^>]+>\s*$")
_RX_NS_ANGLE_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*:[^>]{1,200}>")


def _strip_zero_width_and_ctrl(text: str) -> str:
    if not text:
        return ""
    s = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s


def _norm_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _normalize_clause_id(raw: str) -> str:
    s = re.sub(r"\s+", "", raw or "")
    s = s.replace("의", "-")
    s = re.sub(r"[^0-9\-]", "", s)
    s = re.sub(r"\-+", "-", s).strip("-")
    return s or "0"


def _clean_lines(text: str) -> tuple[list[str], int]:
    s = _strip_zero_width_and_ctrl(text)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    dropped = 0
    lines: list[str] = []
    for line in s.split("\n"):
        l = line.strip()
        if not l:
            lines.append("")
            continue
        if contains_wordprocessingml_markers(l):
            dropped += 1
            continue
        if _RX_XML_TAG_LINE.match(l):
            dropped += 1
            continue
        if l.startswith("<?xml"):
            dropped += 1
            continue
        l2 = _RX_NS_ANGLE_TAG.sub("", l)
        if l2 != l:
            dropped += 1
        lines.append(l2)
    return lines, dropped


_CIRCLED_NUMS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _circled_to_int(ch: str) -> str | None:
    if not ch:
        return None
    i = _CIRCLED_NUMS.find(ch)
    if i >= 0:
        return str(i + 1)
    return None


def _display_path(*, article: str | None, paragraph: str | None, item: str | None, subitem: str | None) -> str:
    parts: list[str] = []
    if article:
        parts.append(f"제{article}조")
    if paragraph:
        parts.append(f"제{paragraph}항")
    if item:
        parts.append(f"{item}호")
    if subitem:
        parts.append(f"{subitem}목")
    return " ".join(parts).strip()


def _strip_prefix(line: str, n: int) -> str:
    return (line or "")[n:].lstrip()


def _parse_paragraph_start(line: str) -> tuple[str, str] | None:
    l = (line or "").strip()
    if not l:
        return None
    if l[0] in _CIRCLED_NUMS:
        pn = _circled_to_int(l[0])
        if pn:
            return pn, _strip_prefix(l, 1)
    m = re.match(r"^(?:제\s*)?(\d{1,3})\s*항\s*(.*)$", l)
    if m:
        return str(int(m.group(1))), (m.group(2) or "").strip()
    return None


def _parse_item_start(line: str) -> tuple[str, str] | None:
    l = (line or "").strip()
    if not l:
        return None
    m = re.match(r"^\(?(\d{1,3})\)?\s*(?:호|[.)])\s*(.+)$", l)
    if m:
        return str(int(m.group(1))), (m.group(2) or "").strip()
    return None


def _parse_subitem_start(line: str) -> tuple[str, str] | None:
    l = (line or "").strip()
    if not l:
        return None
    m = re.match(r"^\(?([가-하])\)?\s*(?:목|[.)])\s*(.+)$", l)
    if m:
        return (m.group(1) or "").strip(), (m.group(2) or "").strip()
    return None


def _split_blocks(lines: list[str], is_start) -> list[tuple[tuple[str, str], list[str]]]:
    idxs: list[int] = []
    heads: dict[int, tuple[str, str]] = {}
    for i, line in enumerate(lines):
        p = is_start(line)
        if p:
            idxs.append(i)
            heads[i] = p
    idxs = sorted(set(idxs))
    if not idxs:
        return []
    idxs.append(len(lines))
    out: list[tuple[tuple[str, str], list[str]]] = []
    for j in range(len(idxs) - 1):
        start = idxs[j]
        end = idxs[j + 1]
        head = heads.get(start)
        if not head:
            continue
        body = [x for x in lines[start + 1 : end]]
        out.append((head, body))
    return out


def _parse_kr_article_hierarchy(
    *,
    base_clause_id: str,
    article_number: str,
    title: str,
    body_lines: list[str],
) -> list[ClauseChunk]:
    lines = [x for x in body_lines if (x or "").strip()]
    para_blocks = _split_blocks(lines, _parse_paragraph_start)
    if not para_blocks:
        full = _norm_text("\n".join(lines))
        head = _norm_text(title)
        text = _norm_text((head + "\n" + full).strip()) if full else head
        return [
            ClauseChunk(
                clause_id=base_clause_id,
                article_number=article_number,
                paragraph_number=None,
                item_number=None,
                subitem_number=None,
                display_path=_display_path(article=article_number, paragraph=None, item=None, subitem=None),
                parent_clause_id=None,
                context_text=None,
                title=title,
                text=text,
            )
        ]

    first_para_idx = None
    for i, line in enumerate(lines):
        if _parse_paragraph_start(line):
            first_para_idx = i
            break
    article_intro = _norm_text("\n".join(lines[: first_para_idx or 0])) if first_para_idx is not None else ""
    article_path = _display_path(article=article_number, paragraph=None, item=None, subitem=None)
    article_head = (article_path + (" " + title if title else "")).strip()

    out: list[ClauseChunk] = []
    for (pn, para_first), para_body in para_blocks:
        para_lines = [para_first] + para_body
        para_lines = [x for x in para_lines if (x or "").strip()]
        items = _split_blocks(para_lines, _parse_item_start)

        para_path = _display_path(article=article_number, paragraph=pn, item=None, subitem=None)
        para_parent_id = f"{base_clause_id}-p{pn}"

        if not items:
            para_text = _norm_text("\n".join(para_lines))
            ctx = "\n".join([x for x in [article_head, article_intro] if x])
            out.append(
                ClauseChunk(
                    clause_id=para_parent_id,
                    article_number=article_number,
                    paragraph_number=pn,
                    item_number=None,
                    subitem_number=None,
                    display_path=para_path,
                    parent_clause_id=base_clause_id,
                    context_text=_norm_text(ctx) if ctx else None,
                    title=title,
                    text=para_text,
                )
            )
            continue

        item_start_positions: list[int] = []
        for i, line in enumerate(para_lines):
            if _parse_item_start(line):
                item_start_positions.append(i)
        first_item_idx = item_start_positions[0] if item_start_positions else None
        para_intro = _norm_text("\n".join(para_lines[: first_item_idx or 0])) if first_item_idx is not None else ""

        for (inm, item_first), item_body in items:
            item_lines = [item_first] + item_body
            item_lines = [x for x in item_lines if (x or "").strip()]
            subitems = _split_blocks(item_lines, _parse_subitem_start)

            item_path = _display_path(article=article_number, paragraph=pn, item=inm, subitem=None)
            item_id = f"{base_clause_id}-p{pn}-i{inm}"
            base_ctx = "\n".join([x for x in [article_head, article_intro, f"{para_path}", para_intro] if x])

            if not subitems:
                out.append(
                    ClauseChunk(
                        clause_id=item_id,
                        article_number=article_number,
                        paragraph_number=pn,
                        item_number=inm,
                        subitem_number=None,
                        display_path=item_path,
                        parent_clause_id=para_parent_id,
                        context_text=_norm_text(base_ctx) if base_ctx else None,
                        title=title,
                        text=_norm_text("\n".join(item_lines)),
                    )
                )
                continue

            sub_start_positions: list[int] = []
            for i, line in enumerate(item_lines):
                if _parse_subitem_start(line):
                    sub_start_positions.append(i)
            first_sub_idx = sub_start_positions[0] if sub_start_positions else None
            item_intro = _norm_text("\n".join(item_lines[: first_sub_idx or 0])) if first_sub_idx is not None else ""
            for (sn, sub_first), sub_body in subitems:
                sub_lines = [sub_first] + sub_body
                sub_lines = [x for x in sub_lines if (x or "").strip()]
                sub_path = _display_path(article=article_number, paragraph=pn, item=inm, subitem=sn)
                sub_id = f"{base_clause_id}-p{pn}-i{inm}-s{sn}"
                ctx = "\n".join([x for x in [base_ctx, item_path, item_intro] if x])
                out.append(
                    ClauseChunk(
                        clause_id=sub_id,
                        article_number=article_number,
                        paragraph_number=pn,
                        item_number=inm,
                        subitem_number=sn,
                        display_path=sub_path,
                        parent_clause_id=item_id,
                        context_text=_norm_text(ctx) if ctx else None,
                        title=title,
                        text=_norm_text("\n".join(sub_lines)),
                    )
                )
    return out


def extract_clauses(text: str) -> tuple[list[ClauseChunk], ClauseExtractionReport]:
    if contains_wordprocessingml_markers(text):
        rep = ClauseExtractionReport(
            strategy="blocked",
            clause_count=0,
            headings_found=False,
            fallback_only=False,
            dropped_lines=0,
            split_long_clauses=0,
            warnings=["word_xml_markers_detected_block"],
        )
        return [], rep

    lines, dropped = _clean_lines(text)
    cleaned = _norm_text("\n".join(lines))
    if not cleaned:
        rep = ClauseExtractionReport(
            strategy="empty",
            clause_count=0,
            headings_found=False,
            fallback_only=False,
            dropped_lines=dropped,
            split_long_clauses=0,
            warnings=["empty_text"],
        )
        return [], rep

    idxs: list[int] = []
    titles: dict[int, str] = {}
    ids: dict[int, str] = {}

    for i, line in enumerate(lines):
        l = (line or "").strip()
        if not l:
            continue

        m = re.match(r"^(제\s*\d+(?:\s*의\s*\d+)?\s*조)\s*(?:\(([^)]{1,80})\))?\s*(.*)$", l)
        if m:
            idxs.append(i)
            head = (m.group(1) or "").strip()
            name = (m.group(2) or "").strip()
            rest = (m.group(3) or "").strip()
            title = " ".join(x for x in [head, name, rest] if x).strip()
            titles[i] = title
            num = re.sub(r"[^\d의\s]", "", head)
            ids[i] = "KR-" + _normalize_clause_id(num)
            continue

        m2 = re.match(r"^(Article\s+(?:\d{1,3}|[IVXLC]{1,10}))\.?\s*(.*)$", l, flags=re.IGNORECASE)
        if m2:
            idxs.append(i)
            art = (m2.group(1) or "").strip()
            rest = (m2.group(2) or "").strip()
            titles[i] = (art + (" " + rest if rest else "")).strip()
            ids[i] = "EN-" + re.sub(r"\s+", "-", art.strip().upper())
            continue

    if not idxs:
        chunks = _fallback_split(cleaned)
        out = [
            ClauseChunk(
                clause_id=f"P-{i+1:03d}",
                article_number=None,
                paragraph_number=None,
                item_number=None,
                subitem_number=None,
                display_path=f"문단 {i+1}",
                parent_clause_id=None,
                context_text=None,
                title=f"문단 {i+1}",
                text=t,
            )
            for i, t in enumerate(chunks)
        ]
        rep = ClauseExtractionReport(
            strategy="fallback",
            clause_count=len(out),
            headings_found=False,
            fallback_only=True if out else False,
            dropped_lines=dropped,
            split_long_clauses=sum(1 for x in out if len(x.text) > 1800),
            warnings=["fallback_used"] if out else ["no_clauses"],
        )
        return out, rep

    idxs = sorted(set(idxs))
    idxs.append(len(lines))
    out: list[ClauseChunk] = []
    seen_ids: dict[str, int] = {}
    split_long = 0
    for j in range(len(idxs) - 1):
        start = idxs[j]
        end = idxs[j + 1]
        head = titles.get(start) or ids.get(start) or f"C-{j+1:03d}"
        body_lines = [x for x in lines[start + 1 : end] if (x or "").strip()]
        body = _norm_text("\n".join(body_lines))
        full_text = _norm_text((head + "\n" + body).strip()) if body else _norm_text(head)
        if not full_text:
            continue
        cid = ids.get(start) or f"C-{j+1:03d}"
        article_number = None
        if cid.startswith("KR-"):
            article_number = cid.replace("KR-", "", 1)
        elif cid.startswith("EN-"):
            article_number = cid.replace("EN-", "", 1)
        seen_ids[cid] = (seen_ids.get(cid, 0) + 1)
        if seen_ids[cid] > 1:
            cid = f"{cid}.D{seen_ids[cid]}"
        if cid.startswith("KR-") and article_number:
            hier = _parse_kr_article_hierarchy(
                base_clause_id=cid,
                article_number=article_number,
                title=head,
                body_lines=body_lines,
            )
            out.extend(hier)
            continue

        if len(full_text) > 2200:
            subs = _split_by_subclauses(full_text)
            if len(subs) > 1:
                split_long += 1
            for k, sub in enumerate(subs):
                sub_id = f"{cid}.{k+1}" if len(subs) > 1 else cid
                sub_article = f"{article_number}.{k+1}" if (article_number and len(subs) > 1) else article_number
                out.append(
                    ClauseChunk(
                        clause_id=sub_id,
                        article_number=sub_article,
                        paragraph_number=None,
                        item_number=None,
                        subitem_number=None,
                        display_path=(f"Article {sub_article}" if sub_article else sub_id),
                        parent_clause_id=None,
                        context_text=None,
                        title=head,
                        text=sub,
                    )
                )
        else:
            out.append(
                ClauseChunk(
                    clause_id=cid,
                    article_number=article_number,
                    paragraph_number=None,
                    item_number=None,
                    subitem_number=None,
                    display_path=(f"제{article_number}조" if article_number and cid.startswith("KR-") else (f"Article {article_number}" if article_number and cid.startswith("EN-") else cid)),
                    parent_clause_id=None,
                    context_text=None,
                    title=head,
                    text=full_text,
                )
            )

    headings_found = any(not (c.clause_id or "").startswith("P-") for c in out)
    rep = ClauseExtractionReport(
        strategy="heading",
        clause_count=len(out),
        headings_found=headings_found,
        fallback_only=False,
        dropped_lines=dropped,
        split_long_clauses=split_long,
        warnings=[] if out else ["no_clauses"],
    )
    return out, rep


def _fallback_split(text: str) -> list[str]:
    s = _norm_text(text)
    if not s:
        return []
    parts = re.split(r"\n\s*\n", s)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) <= 1800:
            out.append(p)
            continue
        cur = p
        while cur:
            out.append(cur[:1800].strip())
            cur = cur[1800:].strip()
    return out


def _split_by_subclauses(text: str) -> list[str]:
    s = _norm_text(text)
    if len(s) <= 2200:
        return [s]
    lines = s.splitlines()
    idxs: list[int] = [0]
    for i, line in enumerate(lines[1:], start=1):
        l = line.strip()
        if not l:
            continue
        if re.match(r"^\(?\d{1,3}(?:\.\d{1,3})*\)?\s*[.)]\s+.+", l):
            idxs.append(i)
            continue
        if re.match(r"^\(?[가-하]\)?\s*[.)]\s+.+", l):
            idxs.append(i)
            continue
        if re.match(r"^\(?[A-Za-z]\)?\s*[.)]\s+.+", l):
            idxs.append(i)
            continue
    idxs = sorted(set(idxs))
    if len(idxs) <= 1:
        return _fallback_split(s)
    idxs.append(len(lines))
    out: list[str] = []
    for j in range(len(idxs) - 1):
        block = _norm_text("\n".join(lines[idxs[j] : idxs[j + 1]]))
        if not block:
            continue
        out.append(block)
    if not out:
        return _fallback_split(s)
    return [_norm_text(x) for x in out]
