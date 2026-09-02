from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from runtime.review.word_markers import contains_wordprocessingml_markers


# extract_clauses() only ever mints clause_ids with these prefixes: "KR-" for
# 조/항/호-segmented Korean contracts, "EN-" for English "Article N" contracts,
# "P-" for the unstructured-paragraph fallback when no heading pattern is
# found at all, "AP-" for a trailing [별표]/부속서 appendix section split off
# from the article it used to be absorbed into. Any other clause_id format
# belongs to a rule-engine-injected finding (e.g. clr_*, tsr_*, MI-/MR-,
# DLR-*, isr_/pi_/svc_/sppc_/mi_/CP-) and was never meant to correspond to a
# raw segmented clause.
REAL_SEGMENT_ID_PREFIXES = ("KR-", "EN-", "P-", "AP-")


def is_real_segment_clause_id(clause_id: str) -> bool:
    """True only for a clause_id that extract_clauses() itself could have
    produced — used to distinguish a genuine extraction/segmentation
    inconsistency from a rule-engine finding id that has no counterpart in
    original_clauses by design."""
    return bool(clause_id) and clause_id.startswith(REAL_SEGMENT_ID_PREFIXES)


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

# text_extract.extract_text_from_pdf() prefixes every page with a "[페이지 N]"
# marker line so page boundaries survive into the joined document text. If
# this line is left in, it ends up verbatim inside whichever clause's body
# happens to span that page break — polluting the "원문" quote shown to the
# reviewer with a marker that was never actually in the contract. Must be
# dropped before clause segmentation, not just before display, since clause
# boundaries are computed from these same lines.
_RX_PAGE_MARKER_LINE = re.compile(r"^\[\s*페이지\s*\d+\s*\]$")

_RX_KR_ARTICLE_HEAD = re.compile(r"^(제\s*\d+(?:\s*의\s*\d+)?\s*조)\s*(?:\(([^)]{1,80})\))?\s*(.*)$")


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
        if _RX_PAGE_MARKER_LINE.match(l):
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


def _parse_paragraph_start_circled_only(line: str) -> tuple[str, str] | None:
    """Circled-number paragraph markers only — no bare "제N항" text
    fallback. Used once an article has already shown at least one circled
    marker (①②③...): a later plain "제N항 ..." line can then only be a
    PDF line-wrap splitting a cross-reference mid-sentence (e.g. "...제3조\n
    제3항 또는 제4항을 위반하여..." — confirmed against a real FITI
    시험분석약정서 where this fabricated a nonexistent 제11조 제3항), never a
    genuine new paragraph heading — a real document never mixes both
    numbering styles for the same hierarchy level within one article.
    """
    l = (line or "").strip()
    if l and l[0] in _CIRCLED_NUMS:
        pn = _circled_to_int(l[0])
        if pn:
            return pn, _strip_prefix(l, 1)
    return None


def _split_inline_paragraph_from_article_heading(lines: list[str]) -> list[str]:
    """A 조문 heading line sometimes carries its first paragraph's full text
    on the very same physical line, e.g.:
        "제14조(기타사항) ① 본 약정에 달리 정함이 없는 사항에 대하여는 ... 적용한다."
    The article-heading regex's trailing catch-all group would otherwise
    swallow that "① ..." text into the article's `title` — the paragraph
    then never becomes its own line, so _parse_kr_article_hierarchy never
    sees it and it silently vanishes from segmentation (not merged into any
    other article — just dropped). Detect this and split the paragraph text
    back onto its own line so it flows into `body_lines` like any other
    paragraph.
    """
    out: list[str] = []
    for line in lines:
        raw = line or ""
        s = raw.strip()
        m = _RX_KR_ARTICLE_HEAD.match(s)
        if m:
            rest = (m.group(3) or "").strip()
            if rest and _parse_paragraph_start(rest) is not None:
                head = m.group(1) + (f"({m.group(2)})" if m.group(2) else "")
                out.append(head)
                out.append(rest)
                continue
        out.append(raw)
    return out


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


def _merge_paragraphs_with_non_leading_items(
    para_blocks: list[tuple[tuple[str, str], list[str]]],
) -> list[tuple[tuple[str, str], list[str]]]:
    """A genuine 항(paragraph)'s own 호(item) list always starts at item 1 —
    Korean legal drafting never begins an item list at item 2 or later. A
    paragraph block whose first detected item is not "1" is a strong signal
    that this paragraph boundary is spurious rather than real: e.g. a stray
    circled-number fragment from another article bled in and interrupted a
    still-open item list from the PRECEDING paragraph. Confirmed against a
    real FITI 시험분석약정서: "③ 제2항에 따른 본 약정의 연장은 1회로
    한정한다." (actually 제9조 제3항) bled into the middle of 제12조 제3항's
    4-item 해지사유 list, fabricating a spurious "제12조 제4항" whose only
    item was numbered 4. Such a block is merged back onto the previous
    block instead of being kept as its own paragraph, so the real item list
    (1~4) ends up correctly under its one genuine paragraph.

    The spurious block's own header line (`first_line` — the text
    immediately after the stray circled-number marker that triggered the
    false split) is DROPPED rather than merged back in: since this pattern
    only fires when the block's own item list doesn't start at 1, that
    header line is always the foreign sentence that caused the false split
    in the first place (confirmed above: "제2항에 따른 본 약정의 연장은
    1회로 한정한다." is itself 제9조 제3항's content, not 제12조's) — never
    genuine content of the article being parsed. Everything after it
    (`body`) — the real continuation of the interrupted item plus any
    following genuine items — is kept and merged back in.
    """
    if len(para_blocks) < 2:
        return para_blocks
    out: list[tuple[tuple[str, str], list[str]]] = [para_blocks[0]]
    for (pn, first_line), body in para_blocks[1:]:
        candidate_lines = [x for x in ([first_line] + body) if (x or "").strip()]
        items = _split_blocks(candidate_lines, _parse_item_start)
        first_item_num = items[0][0][0] if items else None
        if first_item_num is not None and first_item_num != "1":
            prev_pn, prev_first = out[-1][0]
            merged_body = out[-1][1] + body
            out[-1] = ((prev_pn, prev_first), merged_body)
            continue
        out.append(((pn, first_line), body))
    return out


def _renumber_duplicate_paragraph_markers(
    para_blocks: list[tuple[tuple[str, str], list[str]]],
) -> list[tuple[tuple[str, str], list[str]]]:
    """A source document occasionally mislabels a second, genuinely distinct
    paragraph with the same circled number as an earlier one within the same
    article (e.g. two separate "①" blocks — real authoring defect, not a
    parsing artifact: confirmed against an actual FITI 시험분석약정서 whose
    제5조 has two "①"-headed blocks with unrelated content, the second one
    logically being 제5조 제2항). Left as-is, both blocks collide on the
    same paragraph_number and produce duplicate clause_ids, so the second
    (and any further) genuinely-duplicate marker is renumbered to the next
    unused paragraph number in document order — a purely structural fix,
    never touching which article/paragraph the ORIGINAL numbering correctly
    identifies when it isn't duplicated.
    """
    seen: set[str] = set()
    max_pn = 0
    out: list[tuple[tuple[str, str], list[str]]] = []
    for (pn, first_line), body in para_blocks:
        try:
            pn_int: int | None = int(pn)
        except (TypeError, ValueError):
            pn_int = None
        if pn in seen:
            max_pn += 1
            pn = str(max_pn)
        elif pn_int is not None:
            max_pn = max(max_pn, pn_int)
        else:
            max_pn += 1
        seen.add(pn)
        out.append(((pn, first_line), body))
    return out


_RX_STRAY_CIRCLED_PARAGRAPH_MARKER = re.compile(f"[{''.join(_CIRCLED_NUMS)}]")


def _strip_stray_circled_number_tail(text: str) -> str:
    """A single 항/호/목 leaf's own body must never contain another circled
    paragraph marker (①②③...) — those are consumed exclusively as this
    hierarchy parser's own paragraph-boundary markers one level up, so a
    circled number surviving inside a leaf's joined text means an unrelated
    paragraph's opening line bled into this leaf (e.g. a stray "③ 제2항에
    따른 본 약정의 연장은 1회로 한정한다." landing inside a different
    article's 호 body — confirmed against a real FITI 시험분석약정서 where
    this happened at a page boundary). Truncate at the first such marker
    (allowing one at position 0 — this function is never called on that
    case since a genuine leaf's own first character is never a fresh
    circled number) so no finding ever quotes text that isn't really part
    of this clause.
    """
    m = _RX_STRAY_CIRCLED_PARAGRAPH_MARKER.search(text)
    if m is None or m.start() == 0:
        return text
    return text[: m.start()].rstrip()


_RX_APPENDIX_HEAD = re.compile(
    r"^\[\s*(별표|부속서|첨부(?:\s*서류)?|Appendix|Schedule|Exhibit)\s*\]\s*(.*)$",
    re.IGNORECASE,
)
_RX_SIGNATURE_BLOCK_START = re.compile(
    r"^(계약\s*체결일|체결일|계약일)\s*[:：]"
    r"|^(갑|을)\s*[\(（](甲|乙)[\)）]\s*$"
)


def _split_trailing_appendix_and_signature(
    body_lines: list[str],
) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """A trailing "[별표]" appendix table and/or a bilingual signature block
    (계약일/사업자등록번호/대표/주소/날인) that follows the LAST numbered
    paragraph of an article has no heading of its own, so the segmenter used
    to absorb it wholesale into that paragraph's leaf clause — a real
    strategic-partnership 계약 confirmed this: the entire [별표] 지원금 rate
    table plus both parties' full signature block ended up quoted inside
    "제16조 제4항 [기타]", so a legitimate 별표/제8조 정산구조 finding was
    misattributed to 제16조④ instead. Cut the article's body at the first
    such marker: an appendix marker starts its own separately reviewable
    chunk (it references real clause content, e.g. 제8조 rates); a signature
    marker is pure boilerplate and is dropped entirely, never quoted in any
    finding.
    """
    app_idx: int | None = None
    app_title = ""
    sig_idx: int | None = None
    for i, line in enumerate(body_lines):
        l = (line or "").strip()
        if not l:
            continue
        if app_idx is None:
            m = _RX_APPENDIX_HEAD.match(l)
            if m:
                app_idx = i
                app_title = (m.group(1) or "").strip()
                continue
        if sig_idx is None and _RX_SIGNATURE_BLOCK_START.match(l):
            sig_idx = i
            if app_idx is not None:
                break

    if app_idx is None and sig_idx is None:
        return body_lines, []

    cut_idx = app_idx if app_idx is not None else sig_idx
    clause_body = body_lines[:cut_idx]
    appendix_sections: list[tuple[str, list[str]]] = []
    if app_idx is not None:
        appendix_end = sig_idx if (sig_idx is not None and sig_idx > app_idx) else len(body_lines)
        appendix_lines = body_lines[app_idx:appendix_end]
        if appendix_lines:
            appendix_sections.append((app_title or "별표", appendix_lines))
    return clause_body, appendix_sections


def _parse_kr_article_hierarchy(
    *,
    base_clause_id: str,
    article_number: str,
    title: str,
    body_lines: list[str],
) -> list[ClauseChunk]:
    lines = [x for x in body_lines if (x or "").strip()]
    has_circled_paragraph_marker = any((l.strip()[:1] in _CIRCLED_NUMS) for l in lines if l.strip())
    para_start_fn = _parse_paragraph_start_circled_only if has_circled_paragraph_marker else _parse_paragraph_start
    para_blocks = _split_blocks(lines, para_start_fn)
    para_blocks = _merge_paragraphs_with_non_leading_items(para_blocks)
    para_blocks = _renumber_duplicate_paragraph_markers(para_blocks)
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
            para_text = _strip_stray_circled_number_tail(_norm_text("\n".join(para_lines)))
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
                        text=_strip_stray_circled_number_tail(_norm_text("\n".join(item_lines))),
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
                        text=_strip_stray_circled_number_tail(_norm_text("\n".join(sub_lines))),
                    )
                )
    return out


def _parse_en_paragraph_start(line: str, article_number: str) -> tuple[str, str] | None:
    """Match an English "N.M " numbered-paragraph marker (e.g. "3.4 If
    Consultant fails...") at the start of a line, only when N equals the
    article this body belongs to — so a stray decimal number elsewhere in
    the text (a date, a percentage) can never be mistaken for a paragraph
    heading of a *different* article."""
    l = (line or "").strip()
    if not l:
        return None
    m = re.match(r"^(\d{1,3})\.(\d{1,2})\s+(.*)$", l)
    if not m:
        return None
    if m.group(1) != article_number:
        return None
    return m.group(2), (m.group(3) or "").strip()


def _parse_en_article_hierarchy(
    *,
    base_clause_id: str,
    article_number: str,
    title: str,
    body_lines: list[str],
) -> list[ClauseChunk]:
    """English-contract analogue of `_parse_kr_article_hierarchy` — splits an
    "Article N" body into its "N.1", "N.2", ... numbered paragraphs so each
    gets its own leaf clause instead of the whole article (every paragraph
    concatenated) being treated as one undifferentiated chunk.

    Without this, an AI or rule-engine pass over "Article 3" as a single
    ~600-word blob has to notice, on its own, that 3.4's uncapped 10%-per-day
    penalty is a materially different issue from 3.1-3.3's delivery/reporting
    duties — confirmed against a real KOTRA 3자 컨설팅계약 where exactly this
    happened: Article 3.4 (10%/day, no cap) and Article 4.3 (Company
    guarantees Consultant's refund debt) were both missed or under-weighted
    while sitting inside Article 3's and Article 4's single merged chunk.
    """
    lines = [x for x in body_lines if (x or "").strip()]
    para_blocks = _split_blocks(lines, lambda l: _parse_en_paragraph_start(l, article_number))
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
                display_path=f"Article {article_number}",
                parent_clause_id=None,
                context_text=None,
                title=title,
                text=text,
            )
        ]

    article_head = f"Article {article_number}" + (f" {title}" if title else "")
    # Any text before the first "N.1" marker (e.g. an unnumbered intro
    # sentence) belongs to the article as a whole, not to any one paragraph —
    # carried as context only, mirroring the Korean parser's article_intro.
    first_marker_idx = None
    for i, line in enumerate(lines):
        if _parse_en_paragraph_start(line, article_number):
            first_marker_idx = i
            break
    article_intro = _norm_text("\n".join(lines[: first_marker_idx or 0])) if first_marker_idx is not None else ""

    out: list[ClauseChunk] = []
    for (pn, para_first), para_body in para_blocks:
        para_lines = [x for x in ([para_first] + para_body) if (x or "").strip()]
        para_text = _norm_text("\n".join(para_lines))
        para_path = f"Article {article_number}.{pn}"
        ctx = "\n".join([x for x in [article_head, article_intro] if x])
        out.append(
            ClauseChunk(
                clause_id=f"{base_clause_id}.{pn}",
                article_number=f"{article_number}.{pn}",
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
    lines = _split_inline_paragraph_from_article_heading(lines)
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

        m = _RX_KR_ARTICLE_HEAD.match(l)
        if m:
            idxs.append(i)
            head = (m.group(1) or "").strip()
            name = (m.group(2) or "").strip()
            rest = (m.group(3) or "").strip()
            title = " ".join(x for x in [name, rest] if x).strip() or head
            titles[i] = title
            num = re.sub(r"[^\d의\s]", "", head)
            ids[i] = "KR-" + _normalize_clause_id(num)
            continue

        m2 = re.match(r"^Article\s+(\d{1,3}|[IVXLC]{1,10})\.?\s*(.*)$", l, flags=re.IGNORECASE)
        if m2:
            idxs.append(i)
            num = (m2.group(1) or "").strip()
            rest = (m2.group(2) or "").strip()
            titles[i] = ("Article " + num + (" " + rest if rest else "")).strip()
            # "EN-{number}" (e.g. "EN-1"), matching the same id shape the
            # "1. TITLE" fallback path below already uses — the article's
            # bare number (not the whole "Article N" phrase) is what
            # article_number ends up holding downstream, and what
            # _parse_en_article_hierarchy() matches "N.M" paragraph markers
            # against, so it must never be embedded inside a longer token
            # like the old "ARTICLE-1" id used to produce.
            ids[i] = "EN-" + num.upper()
            continue

    # Phase 1-2: English numbered format "1. TITLE" fallback
    # Only used when no Korean/Article headings found and text appears English-heavy
    if not idxs:
        _english_heavy = sum(1 for ch in (cleaned[:3000]) if "a" <= ch.lower() <= "z") / max(1, min(3000, len(cleaned))) >= 0.20
        if _english_heavy:
            for i, line in enumerate(lines):
                l = (line or "").strip()
                if not l:
                    continue
                # Accept "N. <any text>" — no length limit so long clause bodies don't prevent detection.
                # "shall/will/must" etc. are allowed in the title: for English NDA the heading
                # often IS the first sentence (e.g. "8. For any disputes...").
                m3 = re.match(r"^(\d{1,2})\.\s+(.+)$", l)
                if not m3:
                    continue
                num = m3.group(1)
                rest = (m3.group(2) or "").strip()
                # Must start with uppercase letter (avoids matching list items like "1. first item")
                if not re.match(r"^[A-Z]", rest):
                    continue
                # Skip lines that are clearly mid-sentence continuations (all lowercase start)
                # Already handled above. Also skip lines that look like sub-bullets "1. (a)"
                if re.match(r"^\(\w\)", rest):
                    continue
                # Require the preceding context is not already inside a numbered section
                # (simple heuristic: only accept if number is sequential or first occurrence)
                idxs.append(i)
                titles[i] = f"{num}. {rest[:120]}"
                ids[i] = f"EN-{num}"

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
        body_lines, appendix_sections = _split_trailing_appendix_and_signature(body_lines)

        def _flush_appendix_sections() -> None:
            for ap_title, ap_lines in appendix_sections:
                ap_num = sum(1 for c in out if c.clause_id.startswith("AP-")) + 1
                ap_text = _norm_text("\n".join(ap_lines))
                if ap_text:
                    out.append(
                        ClauseChunk(
                            clause_id=f"AP-{ap_num}",
                            article_number=None,
                            paragraph_number=None,
                            item_number=None,
                            subitem_number=None,
                            display_path=f"[{ap_title}]",
                            parent_clause_id=None,
                            context_text=None,
                            title=ap_title,
                            text=ap_text,
                        )
                    )

        body = _norm_text("\n".join(body_lines))
        full_text = _norm_text((head + "\n" + body).strip()) if body else _norm_text(head)
        if not full_text:
            _flush_appendix_sections()
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
            _flush_appendix_sections()
            continue

        if cid.startswith("EN-") and article_number:
            hier = _parse_en_article_hierarchy(
                base_clause_id=cid,
                article_number=article_number,
                title=head,
                body_lines=body_lines,
            )
            out.extend(hier)
            _flush_appendix_sections()
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
        _flush_appendix_sections()

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


# ─── Clause-scoped regex search ──────────────────────────────────────────────
# Shared by any rule-checklist module (common_legal_risk.py, testing_service_
# rules.py, mandatory_issues.py, ...) that needs to quote a matched span of
# contract text as "원문". A regex search over the raw whole-document string
# with a fixed before/after character window is exactly how contamination
# between unrelated clauses/articles has repeatedly entered these quotes
# (a match near the end of one 항/조 pulls in the start of the next) — these
# two functions scope the search to the already-confirmed segmentation
# instead, so a quote can never contain another clause's/article's text.


def _clause_field(c: Any, field: str) -> Any:
    """Read `field` off a clause whether it's a ClauseChunk instance (e.g.
    from extract_clauses()) or a plain dict (e.g. session-stored
    `original_clauses`, which are ClauseChunk fields serialized to JSON)."""
    if isinstance(c, dict):
        return c.get(field)
    return getattr(c, field, None)


def group_clause_text_by_article(clauses: list[Any] | None) -> list[tuple[str, str]]:
    """Concatenate each already-segmented clause's own text by article_number,
    in first-appearance order."""
    order: list[str] = []
    parts: dict[str, list[str]] = {}
    for c in (clauses or []):
        art = str(_clause_field(c, "article_number") or "").strip()
        if not art:
            continue
        if art not in parts:
            parts[art] = []
            order.append(art)
        t = str(_clause_field(c, "text") or "").strip()
        if t:
            parts[art].append(t)
    return [(art, "\n".join(parts[art])) for art in order]


def find_clause_scoped_excerpt(
    clauses: list[Any] | None,
    pattern: "re.Pattern[str]",
    *,
    before: int = 40,
    after: int = 120,
) -> tuple[str, str | None] | None:
    """Search `pattern` against already-segmented clause text (ClauseChunk
    instances or plain dicts with the same field names) and return (excerpt,
    article_number) for the first match, or None if nothing matches. Two
    passes, in order of preference:

    1. Per-leaf-clause: search each clause's own `.text` in isolation — the
       common case, and the only way to guarantee the excerpt can never
       spill into a sibling paragraph.
    2. Per-article fallback (grouped via `group_clause_text_by_article`):
       only reached when no single leaf clause contains the full match (e.g.
       the source text ran a paragraph intro and its enumerated items onto
       one physical line, so segmentation could not split them into
       separate leaves) — still never crosses into a *different* article.
    """
    for c in (clauses or []):
        leaf_text = str(_clause_field(c, "text") or "")
        m = pattern.search(leaf_text)
        if not m:
            continue
        start = max(0, m.start() - before)
        end = min(len(leaf_text), m.end() + after)
        art = str(_clause_field(c, "article_number") or "").strip() or None
        return leaf_text[start:end].strip(), art

    for art, art_text in group_clause_text_by_article(clauses):
        m = pattern.search(art_text)
        if not m:
            continue
        start = max(0, m.start() - before)
        end = min(len(art_text), m.end() + after)
        return art_text[start:end].strip(), art
    return None


@dataclass(frozen=True)
class ClauseScopedMatch:
    """Full clause identity for a single regex match against already-segmented
    clause text — everything a rule-engine injector (common_legal_risk.py,
    testing_service_rules.py, ...) needs to show a real "제N조 제N항 제N호"
    citation instead of only the bare article number `find_clause_scoped_excerpt`
    returns."""
    excerpt: str
    article_number: str | None
    paragraph_number: str | None
    item_number: str | None
    display_path: str | None


def find_all_clause_scoped_matches(
    clauses: list[Any] | None,
    pattern: "re.Pattern[str]",
    *,
    before: int = 40,
    after: int = 120,
    limit: int = 8,
) -> list[ClauseScopedMatch]:
    """Like find_clause_scoped_excerpt(), but returns every matching leaf
    clause (not just the first) with full article/paragraph/item identity —
    used so a rule-engine finding can (a) show the real clause number in its
    title instead of a bare rule id, and (b) list sibling clauses carrying
    the same defect pattern (e.g. a duplicated exemption clause repeated at
    both 제6조 and 제11조) in `related_clauses` instead of silently covering
    only the first occurrence."""
    out: list[ClauseScopedMatch] = []
    for c in (clauses or []):
        leaf_text = str(_clause_field(c, "text") or "")
        m = pattern.search(leaf_text)
        if not m:
            continue
        start = max(0, m.start() - before)
        end = min(len(leaf_text), m.end() + after)
        out.append(
            ClauseScopedMatch(
                excerpt=leaf_text[start:end].strip(),
                article_number=str(_clause_field(c, "article_number") or "").strip() or None,
                paragraph_number=str(_clause_field(c, "paragraph_number") or "").strip() or None,
                item_number=str(_clause_field(c, "item_number") or "").strip() or None,
                display_path=str(_clause_field(c, "display_path") or "").strip() or None,
            )
        )
        if len(out) >= limit:
            break
    return out
