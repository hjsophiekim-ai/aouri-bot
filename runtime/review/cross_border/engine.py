"""cross_border 파이프라인 진입점.

1. 국제계약 판정(signals) — 아니면 아무것도 하지 않는다.
2. 국제 계열 유형(types) — canonical 세부 코드에서 사상.
3. 크로스보더 공통 + 유형별 체크리스트 → finding.
4. evidence_quote 정확 일치 검증 — 실패하면 버리고 사유를 남긴다.
5. 기존 finding 가운데 국내 전용 룰 계열(소비자 대면 판매·딜러 렌탈·위탁판매·하도급법·대리점법 …)은 사업팀 전달본에서
   빼고 법무 내부본에만 사유와 함께 남긴다.
6. 요청사항(하자·세금·대금 …)을 주제 기준으로 이 finding 들에 잇는다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.cross_border.checklist_common import run_common
from runtime.review.cross_border.checklist_sale import run_sale
from runtime.review.cross_border.context import Ctx
from runtime.review.cross_border.evidence import filter_verified
from runtime.review.cross_border.findings import ACTION_KEEP, to_clause_results
from runtime.review.cross_border.signals import assess_cross_border
from runtime.review.cross_border.types import (
    INTERNATIONAL_SALE_OF_GOODS, INTERNATIONAL_TYPE_LABELS, international_type_for, rule_family_allowed,
)

#: 기존 finding 의 룰 계열 판정 — (계열, clause_id·rule_id 패턴, 제목·사유 패턴)
_FAMILY_SIGNS: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    ("consumer_sales", re.compile(r"^clr_missing_consumer_product_liability|^clr_fault_blind_commission|^clr_unbounded_scope|^clr_linked_contract"),
     re.compile(r"소비자\s*대면|소비자\s*클레임|전자상거래법|청약\s*철회")),
    ("dealer_rental", re.compile(r"^DLR-|rental", re.I), re.compile(r"렌탈|딜러\s*렌탈")),
    ("consignment", re.compile(r"consign", re.I), re.compile(r"위탁\s*판매|위탁매매|수탁\s*판매")),
    ("subcontract", re.compile(r"^OV-SUB|subcontract|pi_subcontractor", re.I), re.compile(r"하도급법|수급사업자|원사업자")),
    ("dealer_act", re.compile(r"dealer_unfair|^ACT-DLR", re.I), re.compile(r"대리점법")),
    ("privacy", re.compile(r"^privacy_|^OV-PI", re.I), re.compile(r"개인정보\s*(?:보호법|처리\s*위탁)")),
)


def _family_of(cr: dict[str, Any]) -> str:
    ids = " ".join(str(cr.get(k) or "") for k in ("clause_id", "finding_id", "rule_id"))
    ids += " " + " ".join(str(d.get("rule_id") or "") for d in cr.get("detected_issue_list") or [] if isinstance(d, dict))
    words = " ".join(str(cr.get(k) or "") for k in ("clause_title", "rewrite_reason", "legal_business_reason"))
    for fam, rx_id, rx_word in _FAMILY_SIGNS:
        if any(rx_id.search(x) for x in ids.split()) or rx_word.search(words):
            return fam
    return ""


def _expand_to_paragraph(row: dict[str, Any], text: str) -> None:
    """교체 수정의 원문·수정안을 그 문구가 든 문단(줄) 전체로 넓힌다 — 전달본은 '문장 교체'로, 무결성 검사는 문단 단위
    대조로 정확히 읽는다. 대상 문구는 redline_instruction.target_text 에 그대로 남는다."""
    ri = row.get("redline_instruction") or {}
    target = str(ri.get("target_text") or "")
    if not target or ri.get("edit_type") != "replace":
        return
    i = text.find(target)
    if i < 0:
        return
    s = text.rfind("\n", 0, i) + 1
    e = text.find("\n", i + len(target))
    line = text[s: len(text) if e < 0 else e].strip()
    if not line or line == target:
        return
    row["original_text"] = line
    row["suggested_rewrite"] = line.replace(target, str(ri.get("replacement_text") or ""), 1)


def _set_anchor(row: dict[str, Any], ctx: Ctx) -> None:
    """신설 문안의 기준 단락 첫머리 — 변경추적본이 그 단락 바로 뒤(표 셀이면 같은 셀)에 넣는다."""
    ri = row.get("redline_instruction") or {}
    path = str(ri.get("anchor_path") or "")
    if not path or ri.get("edit_type") == "replace":
        return
    pair = next((p for p in ctx.pairs if p.path == path), None)
    if pair is None:
        return
    line = (pair.en_last or pair.en) if ri.get("lang") == "en" else (pair.ko_last or pair.ko)
    if line:
        ri["anchor_text"] = line[:60]


def gate_rule_families(clause_results: list[dict[str, Any]], international_type: str) -> list[dict[str, str]]:
    """국제계약 유형과 맞지 않는 국내 전용 룰 finding 을 전달본에서 뺀다(내부본에는 사유와 함께)."""
    from runtime.review.redline_integrity import exclude_from_brief

    out: list[dict[str, str]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("is_cross_border_check"):
            continue
        fam = _family_of(cr)
        if fam and not rule_family_allowed(international_type, fam):
            reason = f"국제계약 유형({INTERNATIONAL_TYPE_LABELS.get(international_type, international_type)})에 맞지 않는 국내 전용 룰({fam})"
            exclude_from_brief(cr, reason)
            out.append({"clause_id": str(cr.get("clause_id") or ""), "family": fam, "reason": reason})
    return out


def run_cross_border_review(*, text: str, clause_results: list[dict[str, Any]], base_type_code: str = "", our_role: str = "",
                            our_label: str = "", their_label: str = "", answers_text: str = "",
                            international_type: str = "", answers: dict[str, Any] | None = None,
                            request_text: str = "") -> dict[str, Any]:
    """`international_type` 은 canonical_state 가 정한 값(단일 진실 원천). 없을 때만 여기서 판정한다(단독 호출·시험)."""
    a = assess_cross_border(text)
    if not a.is_cross_border:
        return {"active": False, "assessment": a.to_dict()}
    itype = international_type or international_type_for(base_type_code, text)
    if not itype:
        # 근로관계 계약 등 국제 상거래 체크리스트 대상이 아닌 계약
        return {"active": False, "assessment": a.to_dict(), "reason": "국제 상거래 계약 유형 아님(근로관계 등)"}
    from runtime.review.cross_border.perspective import resolve_perspective

    persp = resolve_perspective(text=text, request_text=request_text or answers_text, answers=answers)
    if persp.get("confirmed"):
        # 당사자 표 + 요청문(또는 사전질문 답)으로 확정한 관점이 앞선 단계의 추정보다 우선한다
        our_role, our_label, their_label = persp["our_role"], persp["our_label"], ""
    ctx = Ctx(text=str(text or ""), assessment=a, intl_type=itype, our_role=our_role, our_label=our_label,
              their_label=their_label, answers_text=answers_text)
    findings = run_common(ctx)
    if itype == INTERNATIONAL_SALE_OF_GOODS:
        findings += run_sale(ctx)
    rows = [r for f in findings for r in to_clause_results(f)]
    from runtime.review.cross_border.checklist_sale import UNDECIDED_LABELS

    for r in rows:
        _expand_to_paragraph(r, str(text or ""))
        _set_anchor(r, ctx)
        code = str(r.get("translation_of") or r["clause_id"]).removeprefix("xb_")
        if code in UNDECIDED_LABELS:
            r["undecided_labels"] = list(UNDECIDED_LABELS[code])
    kept, dropped = filter_verified(rows, text)
    existing = {str(c.get("clause_id") or "") for c in clause_results if isinstance(c, dict)}
    added = [r for r in kept if r["clause_id"] not in existing]
    clause_results.extend(added)
    gated = gate_rule_families(clause_results, itype)
    blank_rows = [b.to_dict() for b in ctx.blanks]
    return {
        "active": True,
        "international_type": itype,
        "international_type_label": INTERNATIONAL_TYPE_LABELS.get(itype, itype),
        "assessment": a.to_dict(),
        "facts": ctx.facts.to_dict(),
        "our_role": our_role, "our_label": ctx.our_label, "their_label": ctx.their_label,
        "perspective": {**persp, "our_label": ctx.our_label, "their_label": ctx.their_label} if persp.get("confirmed") else persp,
        "blanks": blank_rows,
        "negotiable_values": [{"path": v.path, "value": v.value, "quote": v.quote} for v in ctx.values],
        "finding_ids": [r["clause_id"] for r in added],
        "kept_clauses": [r["clause_id"] for r in added if r.get("action_type") == ACTION_KEEP],
        "dropped_unverified": dropped,
        "gated_findings": gated,
    }


def drop_covered_blanks(rows: list[dict[str, Any]] | None, clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """cross_border finding 이 이미 '체결 전 필수 확정'으로 다루는 공란(같은 조)은 사업부 결정 목록에서 뺀다."""
    covered = {re.sub(r"\s*제\s*\d+\s*항.*$", "", str(c.get("display_path") or ""))
               for c in clause_results if isinstance(c, dict) and c.get("is_cross_border_check")
               and c.get("risk_tier") == "HIGH" and set(c.get("topic_tags") or []) & {"blank", "delivery"}}
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        art = re.sub(r"\s*제\s*\d+\s*항.*$", "", str(r.get("path") or ""))
        if r.get("classification") != "사업부 결정" and art in covered:
            continue
        out.append(r)
    return out


# ── 요청사항 연결 ─────────────────────────────────────────────────────────────

_RX_REVIEW_INTENT = re.compile(r"검토|확인|여부|문제|위험|리스크|책임|조항|불리|유리|가능한지|되는지|\?|해\s*주|부탁|봐\s*주|check|review", re.I)

def overlay_requests(rows: list[dict[str, Any]] | None, clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """요청 행을 주제가 맞는 cross_border finding 에 잇고, 답을 그 finding 으로 쓴다."""
    from runtime.review.user_review_request import request_topics

    xb = [c for c in clause_results if isinstance(c, dict) and c.get("is_cross_border_check") and not c.get("brief_merge_into")
          and c.get("action_type") != ACTION_KEEP]
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        text = " ".join(str(row.get(k) or "") for k in ("normalized_issue", "original_user_text"))
        topics = request_topics(text)
        if (not topics and not row.get("is_comprehensive_scope") and not _RX_REVIEW_INTENT.search(text)
                and re.search(r"(?:계약서|계약)\.?\s*$", text.strip()) and "사용자 확인 답변" not in text
                and str(row.get("source") or "") != "question_answer"):
            # "○○가 이탈리아 업체로부터 원단을 구입하는 물품구매계약서" 같은 배경 설명 — 검토 요청이 아니다.
            # 요청 답변에 "현행 커버"로 싣지 않는다(검토 맥락으로만 쓴다).
            continue
        if not topics or row.get("is_comprehensive_scope"):
            out.append(row)
            continue
        hits = [c for c in xb if set(c.get("topic_tags") or []) & set(topics)]
        if not hits:
            out.append(row)
            continue
        rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        hits.sort(key=lambda c: (rank.get(str(c.get("risk_tier")), 3), str(c.get("display_path") or "")))
        paths = list(dict.fromkeys(str(c.get("display_path") or "") for c in hits if c.get("display_path")))
        new = dict(row)
        new["matched_finding_ids"] = list(dict.fromkeys([c["clause_id"] for c in hits] + list(row.get("matched_finding_ids") or [])))
        new["relevant_clause_paths"] = paths
        items = "; ".join(f"{c.get('display_path')} — {re.sub(r'\s*\(영문\)$', '', str(c.get('clause_title') or ''))}" for c in hits[:5])
        need = any(str(c.get("action_type")) in ("필수수정", "권장수정", "체결 전 확인") for c in hits)
        new["judgment"] = new["brief_answer"] = (("수정·확정 필요 — " if need else "확인 — ") + items)
        new["request_status"] = "반영"
        new["review_status"] = "수정 필요" if need else "적정"
        new["topic_mapping"] = topics
        out.append(new)
    return out
