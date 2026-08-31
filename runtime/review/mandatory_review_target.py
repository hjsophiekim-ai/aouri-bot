"""Mandatory review target tracking — user-cited clause numbers must survive.

When the user names specific clause numbers in review_focus (e.g. "제5조
제2항 제1호, 제6조 제4항"), those clauses must appear in the final Word
output whether or not the rule engine or AI happened to flag them —
dropping a clause the user explicitly asked about is a "사용자 요청사항
누락", not an editorial omission, so this module gives that request its own
tracked, never-truncated status separate from ordinary risk findings.

Pipeline:
  1. parse_mandatory_review_targets(review_focus) — extract every explicit
     "제N조[의M] [제P항] [제I호]" citation from the user's own request text.
  2. annotate_and_track_mandatory_targets(...) — for each target, find any
     clause_result whose article/paragraph/item identity (or whose
     related_clauses) matches it, tag it `is_mandatory_review_target=True`
     so it can never be silently truncated (see output_filter.py), and — if
     nothing matches at all but the cited clause really exists in the
     contract — synthesize a "확인완료: 특이사항 없음" NOTE entry so the
     request is still answered rather than dropped.
  3. check_all_targets_addressed(...) — hard gate used by self_check.py and
     server.py's docx download path: a "flagged" target (a real issue was
     found) that doesn't survive into the final high/medium output blocks
     the result as REVIEW_FAILED_USER_REQUEST_MISSING.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

def _clause_field(c: Any, field: str) -> Any:
    """Read `field` off a clause whether it's a ClauseChunk instance or a
    plain dict (session-stored original_clauses)."""
    if isinstance(c, dict):
        return c.get(field)
    return getattr(c, field, None)


_RX_CITATION = re.compile(
    r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?"
    r"(?:\s*제\s*(\d+)\s*항)?"
    r"(?:\s*제\s*(\d+)\s*호)?"
)


@dataclass(frozen=True)
class MandatoryReviewTarget:
    article: str
    sub_article: str | None
    paragraph: str | None
    item: str | None
    raw_citation: str
    display_path: str


def _display_path(article: str, sub_article: str | None, paragraph: str | None, item: str | None) -> str:
    parts = [f"제{article}{('의' + sub_article) if sub_article else ''}조"]
    if paragraph:
        parts.append(f"제{paragraph}항")
    if item:
        parts.append(f"제{item}호")
    return " ".join(parts)


def parse_mandatory_review_targets(review_focus: str | None) -> list[MandatoryReviewTarget]:
    """Extract every explicit clause citation the user named in review_focus.

    Only scans review_focus (the user's own request text), never the
    contract body — a full-document scan would treat every clause as a
    "user-cited" target and defeat the purpose of this priority track.
    """
    s = (review_focus or "").strip()
    if not s:
        return []
    out: list[MandatoryReviewTarget] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for m in _RX_CITATION.finditer(s):
        article, sub_article, paragraph, item = m.group(1), m.group(2), m.group(3), m.group(4)
        key = (article, sub_article, paragraph, item)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            MandatoryReviewTarget(
                article=article,
                sub_article=sub_article,
                paragraph=paragraph,
                item=item,
                raw_citation=m.group(0).strip(),
                display_path=_display_path(article, sub_article, paragraph, item),
            )
        )
    return out


def _matches_target(cr: dict[str, Any], target: MandatoryReviewTarget) -> bool:
    an = str(cr.get("article_number") or "").strip()
    if not an or an != target.article:
        return False
    if target.paragraph:
        pn = str(cr.get("paragraph_number") or "").strip()
        if pn and pn != target.paragraph:
            return False
    if target.item:
        inum = str(cr.get("item_number") or "").strip()
        if inum and inum != target.item:
            return False
    return True


def _related_mentions_target(cr: dict[str, Any], target: MandatoryReviewTarget) -> bool:
    related = cr.get("related_clauses")
    if not isinstance(related, list):
        return False
    # A related-clause entry that names the same article and (if the target
    # names one) the same paragraph counts as covering the target — e.g. a
    # single "clr_fault_blind_exemption" finding anchored at 제6조 that lists
    # "제11조 제1항" in related_clauses answers a 제11조 제1항 target too.
    art_token = f"제{target.article}조"
    for r in related:
        rs = str(r or "")
        if art_token not in rs:
            continue
        if target.paragraph and f"제{target.paragraph}항" not in rs:
            continue
        if target.item and f"제{target.item}호" not in rs:
            continue
        return True
    return False


def _find_chunk_for_target(clauses: list[Any] | None, target: MandatoryReviewTarget) -> Any | None:
    for c in (clauses or []):
        an = str(_clause_field(c, "article_number") or "").strip()
        if an != target.article:
            continue
        if target.paragraph:
            pn = str(_clause_field(c, "paragraph_number") or "").strip()
            if pn and pn != target.paragraph:
                continue
        if target.item:
            inum = str(_clause_field(c, "item_number") or "").strip()
            if inum and inum != target.item:
                continue
        return c
    return None


def annotate_and_track_mandatory_targets(
    *,
    clause_results: list[dict[str, Any]],
    clauses: list[Any] | None,
    review_focus: str | None,
) -> list[dict[str, Any]]:
    """Mutates clause_results in place (tags matches, appends "no issue"
    notes for uncovered-but-real targets) and returns a status list — one
    entry per cited target — suitable for both the self-check gate and the
    Word "최초 요청사항 반영 여부" summary table.
    """
    targets = parse_mandatory_review_targets(review_focus)
    status: list[dict[str, Any]] = []
    if not targets:
        return status

    for target in targets:
        matched = [
            cr for cr in clause_results
            if isinstance(cr, dict) and (_matches_target(cr, target) or _related_mentions_target(cr, target))
        ]
        for cr in matched:
            cr["is_mandatory_review_target"] = True

        if matched:
            severities = [str(cr.get("risk_tier") or cr.get("severity") or "").upper() for cr in matched]
            top_severity = next((s for s in ("HIGH", "MEDIUM", "LOW") if s in severities), (severities[0] if severities else ""))
            # A target matched to a real, reviewed clause that turned out
            # LOW-severity is a legitimate "검토완료, 낮은 위험" outcome, not
            # a dropped finding — only HIGH/MEDIUM matches need to survive
            # the output_filter's truncation/quality gates into the final
            # HIGH/MEDIUM sections, so only those are marked "flagged" (the
            # status check_all_targets_addressed() enforces presence for).
            is_actionable = top_severity in ("HIGH", "MEDIUM")
            status.append({
                "raw_citation": target.raw_citation,
                "display_path": target.display_path,
                "status": "flagged" if is_actionable else "checked_low_risk",
                "matched_clause_ids": [str(cr.get("clause_id") or "") for cr in matched],
                "severity": top_severity,
            })
            continue

        chunk = _find_chunk_for_target(clauses, target)
        if chunk is None:
            status.append({
                "raw_citation": target.raw_citation,
                "display_path": target.display_path,
                "status": "clause_not_found",
                "matched_clause_ids": [],
                "severity": "",
            })
            continue

        # Real clause exists but nothing flagged it — synthesize a "checked,
        # no issue" note so the user's request is answered, not silently
        # dropped. NOTE-tier: informational, never a risk finding, and
        # therefore never subject to the HIGH/MEDIUM truncation gates.
        note_id = f"mrt_note_{target.article}" + (f"_p{target.paragraph}" if target.paragraph else "") + (f"_i{target.item}" if target.item else "")
        clause_text = str(_clause_field(chunk, "text") or "").strip()
        clause_results.append({
            "clause_id": note_id,
            "article_number": target.article,
            "paragraph_number": target.paragraph,
            "item_number": target.item,
            "display_path": target.display_path,
            "clause_title": f"{target.display_path} [사용자 요청 검토]",
            "clause_topic": None,
            "original_text": clause_text[:500] if clause_text else f"[{target.display_path}] 관련 조항",
            "risk_tier": "LOW",
            "severity": "LOW",
            "high_risk": False,
            "must_fix": False,
            "approval_required": False,
            "review_tier": "NOTE",
            "suggested_rewrite": None,
            "rewrite_reason": "사용자 요청에 따라 검토하였으나 특이사항이 확인되지 않았습니다.",
            "negotiation_position": "",
            "confidence": 0.9,
            "is_mandatory_review_target": True,
            "is_mandatory_review_note": True,
            "has_rewrite_change": False,
            "display_kind": "note",
            "dedup_suppressed": False,
            "keep_as_is": True,
            "user_focus_hit": True,
            "factual_hit": False,
            "ai_deep_reviewed": False,
        })
        status.append({
            "raw_citation": target.raw_citation,
            "display_path": target.display_path,
            "status": "checked_no_issue",
            "matched_clause_ids": [note_id],
            "severity": "LOW",
        })

    return status


def check_all_targets_addressed(
    status_list: list[dict[str, Any]],
    *,
    final_findings_clause_ids: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Hard gate: a "flagged" target (a real finding was matched at tagging
    time) must still be present in the final high/medium output that
    actually ships. "checked_no_issue" and "clause_not_found" targets are
    already fully answered (via the summary table) and never block.

    If `final_findings_clause_ids` is None, presence is not verified against
    the final filtered output (only that a target was resolved at all) —
    callers that build the final findings list should always pass it.
    """
    missing: list[str] = []
    for t in status_list or []:
        if t.get("status") != "flagged":
            continue
        if final_findings_clause_ids is None:
            continue
        matched_ids = t.get("matched_clause_ids") or []
        if not any(cid in final_findings_clause_ids for cid in matched_ids):
            missing.append(str(t.get("display_path") or t.get("raw_citation") or ""))
    return (not missing, missing)
