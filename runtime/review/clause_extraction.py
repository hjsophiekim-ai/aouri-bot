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
        out = [ClauseChunk(clause_id=f"P-{i+1:03d}", article_number=None, title=f"문단 {i+1}", text=t) for i, t in enumerate(chunks)]
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
        if len(full_text) > 2200:
            subs = _split_by_subclauses(full_text)
            if len(subs) > 1:
                split_long += 1
            for k, sub in enumerate(subs):
                sub_id = f"{cid}.{k+1}" if len(subs) > 1 else cid
                sub_article = f"{article_number}.{k+1}" if (article_number and len(subs) > 1) else article_number
                out.append(ClauseChunk(clause_id=sub_id, article_number=sub_article, title=head, text=sub))
        else:
            out.append(ClauseChunk(clause_id=cid, article_number=article_number, title=head, text=full_text))

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
