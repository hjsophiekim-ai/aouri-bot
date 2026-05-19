from __future__ import annotations

import re
from typing import Any

from runtime.services.query_service import TRIGGER_MAP
from runtime.review.clause_extraction import ClauseChunk, extract_clauses
from runtime.review.rewrite_engine import propose_clause_specific_rewrite
from runtime.review.party_role import PartyRole
from runtime.review.word_markers import contains_wordprocessingml_markers
from runtime.review.clause_topic import classify_clause_topic, infer_rewrite_topics, is_topic_compatible, TOPIC_OTHER
from runtime.review.dealer_direct_findings import (
    analyze_clause_for_structure_findings,
    is_false_positive_compliance,
    STRUCTURE_DIRECT_CUSTOMER_KEY,
)


REPLACEMENT_TEXT_BY_RULE_ID = {
    "RISK-001": "책임은 계약금액(또는 연간 총 대금)을 상한으로 하며, 간접손해/특별손해/영업손실 등은 제외한다. 단, 고의·중과실 및 법령상 책임은 제외한다.",
    "RISK-002": "면책/배상 구조는 상호주의를 원칙으로 하며, 범위·사유·절차를 합리적으로 제한한다(제3자 청구는 통지/방어권/승인 절차 포함).",
    "RISK-004": "기술자료 제공은 목적·범위·기간을 특정하고, 최소한으로 제공하며, 반환/파기 및 제3자 제공 금지, 보안조치, 위반 시 손해배상 기준을 포함한다.",
    "RISK-005": "단가 조정/감액은 객관적 사유 및 사전 협의·서면 합의에 한정하고, 감액 범위·기간·산식·근거를 명시한다.",
    "RISK-006": "비용 부담(판촉비/반품/광고비 등)은 항목별 상한·정산 기준·증빙·사전 서면 합의 조건을 명시하고, 일방 전가를 금지한다.",
}

SUGGESTION_BY_RULE_ID = {
    "RISK-001": "무제한 책임 표현을 책임상한+간접손해 제외 구조로 변경",
    "RISK-002": "일방 면책/일방 배상 구조를 상호주의+절차(통지/방어권/승인) 포함 구조로 변경",
    "RISK-004": "기술자료 요구 범위를 최소화하고 목적 제한/반환·파기/보안조항을 추가",
    "RISK-005": "하도급 단가 감액 요건을 사전협의·서면합의로 제한하고 산식/근거 명시",
    "RISK-006": "대리점 비용전가 항목을 상한/정산 기준/증빙/사전합의로 제한",
}

def _contains_wordprocessingml_markers(text: str) -> bool:
    return contains_wordprocessingml_markers(text)


def split_into_clauses(text: str) -> list[ClauseChunk]:
    clauses, _ = extract_clauses(text)
    return clauses


def _extract_trigger_keywords(rule: dict[str, Any]) -> list[str]:
    rid = rule.get("rule_id", "")
    if rid in TRIGGER_MAP:
        return TRIGGER_MAP[rid]
    out: list[str] = []
    for tag in rule.get("tags", []):
        if isinstance(tag, str) and tag.startswith("trigger:"):
            out.append(tag.split(":", 1)[1].replace("_", " "))
    phrase = rule.get("contract_evidence", {}).get("example_phrase")
    if isinstance(phrase, str) and phrase.strip():
        out.append(phrase.strip())
    return out


def suggest_revisions(
    clauses: list[ClauseChunk],
    matched_rules: list[dict[str, Any]],
    *,
    posture: str = "neutral",
    party: PartyRole | None = None,
    contract_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matched_by_id: dict[str, dict[str, Any]] = {}
    for r in matched_rules:
        if not isinstance(r, dict):
            continue
        rid = r.get("rule_id")
        if isinstance(rid, str) and rid:
            matched_by_id[rid] = r

    rule_keywords: dict[str, list[str]] = {}
    for rid, r in matched_by_id.items():
        kws = _extract_trigger_keywords(r)
        rule_keywords[rid] = [k for k in kws if isinstance(k, str) and k.strip()]

    items: list[dict[str, Any]] = []
    for c in clauses:
        clause_topic = classify_clause_topic(title=str(c.title or ""), text=str(c.text or ""))
        clause_issues: list[dict[str, Any]] = []
        applied_rules: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        high_risk = False
        approval_required = False
        search_text = ((str(c.title or "") + "\n" + str(c.text or "")).strip()) if (c.title or c.text) else str(c.text or "")
        if isinstance(c.context_text, str) and c.context_text.strip() and len(c.context_text.strip()) <= 120:
            search_text = (c.context_text.strip() + "\n" + search_text).strip()

        for rid, kws in rule_keywords.items():
            if not kws:
                continue
            matched_kws = [k for k in kws if k.lower() in search_text.lower()]
            if matched_kws:
                r = matched_by_id[rid]
                if rid in ("RISK-006", "ACT-009") and clause_topic not in ("cost_burden", "payment_settlement", "dealer_unfair"):
                    continue
                # False-positive suppression: harmless compliance clauses must not be flagged as cost burden
                if rid in ("RISK-006", "ACT-009") and is_false_positive_compliance(str(c.text or ""), rid):
                    continue
                if rid in ("RISK-003", "ACT-010") and clause_topic not in ("safety",):
                    continue
                if rid in ("C-001",) and clause_topic not in ("payment_settlement", "cost_burden"):
                    continue
                risk_level = str(r.get("risk_level", "") or "")
                is_high = risk_level.lower() in ("high", "very_high", "critical")
                is_approval = bool(r.get("approval_required")) or r.get("rule_status") == "approval_required"
                high_risk = high_risk or is_high
                approval_required = approval_required or is_approval
                clause_issues.append(
                    {
                        "rule_id": rid,
                        "issue_title": str(r.get("title", rid)),
                        "issue_detail": str(r.get("description", "")),
                        "review_action": list(r.get("review_action") or []),
                        "risk_level": risk_level,
                        "high_risk": is_high,
                        "approval_required": is_approval,
                        "summary_suppress": bool(r.get("summary_suppress")),
                        "supplemental_only": bool(r.get("supplemental_only")),
                    }
                )
                applied_rules.append(
                    {
                        "rule_id": rid,
                        "rule_status": r.get("rule_status"),
                        "risk_level": risk_level,
                        "approval_required": is_approval,
                        "matched_keywords": matched_kws,
                    }
                )
                evidence.append({"rule_id": rid, "matched_keywords": matched_kws})

        if not clause_issues:
            continue

        suggestion_dirs = []
        replacement_texts = []
        for ar in applied_rules:
            rid = ar["rule_id"]
            if rid in SUGGESTION_BY_RULE_ID:
                suggestion_dirs.append(SUGGESTION_BY_RULE_ID[rid])
            if rid in REPLACEMENT_TEXT_BY_RULE_ID:
                replacement_texts.append(REPLACEMENT_TEXT_BY_RULE_ID[rid])

        seen = set()
        suggestion_dirs = [x for x in suggestion_dirs if not (x in seen or seen.add(x))]
        seen = set()
        replacement_texts = [x for x in replacement_texts if not (x in seen or seen.add(x))]

        proposal = propose_clause_specific_rewrite(
            clause_text=c.text,
            applied_rules=applied_rules,
            posture=posture,
            party=party,
            contract_context=contract_context,
        )
        recommended_rewrite = proposal.suggested_rewrite if proposal else None
        rewrite_reason = proposal.rewrite_reason if proposal else None
        reason_codes = proposal.reason_codes if proposal else []
        changed_segments = list(proposal.changed_segments) if proposal and proposal.changed_segments else []
        rewrite_topics = infer_rewrite_topics(rewrite_text=recommended_rewrite, reason_codes=reason_codes)
        if recommended_rewrite and not is_topic_compatible(clause_topic=clause_topic, rewrite_topics=rewrite_topics):
            recommended_rewrite = None
            changed_segments = []
            if not (isinstance(rewrite_reason, str) and rewrite_reason.strip()):
                rewrite_reason = "조항 주제와 무관한 수정문안은 제외(guardrail)."

        # risk_tier 산정: HIGH / MEDIUM / LOW
        from runtime.review.rewrite_engine import _infer_risk_tier
        risk_tier = _infer_risk_tier(
            reason_codes=reason_codes,
            text=str(c.text or ""),
        )

        unfavorable_to_us = _infer_unfavorable_to_us(
            clause_text=str(c.text or ""),
            applied_rules=applied_rules,
            posture=str(posture or "neutral"),
            party=party,
        )


        items.append(
            {
                "clause_id": c.clause_id,
                "article_number": c.article_number,
                "paragraph_number": c.paragraph_number,
                "item_number": c.item_number,
                "subitem_number": c.subitem_number,
                "display_path": c.display_path,
                "parent_clause_id": c.parent_clause_id,
                "context_text": c.context_text,
                "clause_title": c.title,
                "original_clause": c.text,
                "detected_issues": clause_issues,
                "applied_rules": applied_rules,
                "match_evidence": evidence,
                "suggested_direction": suggestion_dirs,
                "fallback_text": replacement_texts,
                "recommended_rewrite": recommended_rewrite,
                "rewrite_reason": rewrite_reason,
                "rewrite_reason_codes": reason_codes,
                "risk_tier": risk_tier,
                "changed_segments": changed_segments,
                "clause_topic": clause_topic if clause_topic != TOPIC_OTHER else None,
                "high_risk": high_risk,
                "approval_required": approval_required,
                "unfavorable_to_us": unfavorable_to_us,
            }
        )

    # ── Dealer direct structure: merge structure-specific findings ──────────
    _contract_structure = None
    if isinstance(contract_context, dict):
        _contract_structure = contract_context.get("contract_structure")
    if _contract_structure == STRUCTURE_DIRECT_CUSTOMER_KEY:
        items = _merge_dealer_direct_findings(clauses=clauses, items=items)

    items.sort(key=lambda it: (0 if it.get("approval_required") else 1, 0 if it.get("high_risk") else 1, str(it.get("clause_id") or "")))
    summary = {
        "issue_clause_count": len(items),
        "high_risk_clause_count": sum(1 for it in items if it["high_risk"]),
        "approval_required_clause_count": sum(1 for it in items if it["approval_required"]),
        "recommended_rewrite_clause_count": sum(1 for it in items if it.get("recommended_rewrite")),
        "unfavorable_to_us_clause_count": sum(1 for it in items if bool(it.get("unfavorable_to_us"))),
    }
    return {"summary": summary, "items": items}


def _merge_dealer_direct_findings(
    *,
    clauses: list[ClauseChunk],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run dealer-direct structure analysis per clause and merge into items list."""
    existing_clause_ids: set[str] = {str(it.get("clause_id") or "") for it in items}
    items_by_clause_id: dict[str, dict[str, Any]] = {
        str(it.get("clause_id") or ""): it for it in items
    }

    for c in clauses:
        cid = str(c.clause_id or "")
        findings = analyze_clause_for_structure_findings(
            clause_title=str(c.title or ""),
            clause_text=str(c.text or ""),
            clause_id=cid,
        )
        if not findings:
            continue

        for f in findings:
            is_high = f.severity == "HIGH"
            is_medium = f.severity == "MEDIUM"

            if cid and cid in existing_clause_ids:
                # Enrich existing item
                existing = items_by_clause_id.get(cid)
                if existing is not None:
                    if is_high:
                        existing["high_risk"] = True
                    if f.suggested_rewrite and not existing.get("recommended_rewrite"):
                        existing["recommended_rewrite"] = f.suggested_rewrite
                    if f.worst_case_scenario and not existing.get("worst_case_scenario"):
                        existing["worst_case_scenario"] = f.worst_case_scenario
                    # Add structure finding to detected issues
                    existing_issues = existing.get("detected_issues")
                    if not isinstance(existing_issues, list):
                        existing_issues = []
                        existing["detected_issues"] = existing_issues
                    existing_issues.append({
                        "rule_id": f.finding_id,
                        "issue_title": f.issue_title,
                        "issue_detail": f.risk_description,
                        "review_action": [f.why_matters, f.supplier_strategy],
                        "risk_level": f.severity,
                        "high_risk": is_high,
                        "approval_required": is_high,
                        "summary_suppress": False,
                        "supplemental_only": False,
                        "is_structure_mismatch": f.is_structure_mismatch,
                        "clause_identity": f.clause_identity,
                        "worst_case_scenario": f.worst_case_scenario,
                    })
                    if is_high:
                        existing["approval_required"] = True
                    existing["unfavorable_to_us"] = True
            else:
                # Create new item for this clause
                new_item: dict[str, Any] = {
                    "clause_id": c.clause_id,
                    "article_number": c.article_number,
                    "paragraph_number": c.paragraph_number,
                    "item_number": c.item_number,
                    "subitem_number": c.subitem_number,
                    "display_path": c.display_path,
                    "parent_clause_id": c.parent_clause_id,
                    "context_text": c.context_text,
                    "clause_title": c.title,
                    "original_clause": c.text,
                    "detected_issues": [{
                        "rule_id": f.finding_id,
                        "issue_title": f.issue_title,
                        "issue_detail": f.risk_description,
                        "review_action": [f.why_matters, f.supplier_strategy],
                        "risk_level": f.severity,
                        "high_risk": is_high,
                        "approval_required": is_high,
                        "summary_suppress": False,
                        "supplemental_only": False,
                        "is_structure_mismatch": f.is_structure_mismatch,
                        "clause_identity": f.clause_identity,
                        "worst_case_scenario": f.worst_case_scenario,
                    }],
                    "applied_rules": [{
                        "rule_id": f.finding_id,
                        "rule_status": "confirmed_pattern",
                        "risk_level": f.severity,
                        "approval_required": is_high,
                        "matched_keywords": [f.original_excerpt[:80]] if f.original_excerpt else [],
                    }],
                    "match_evidence": [{"rule_id": f.finding_id, "matched_keywords": [f.original_excerpt[:80]] if f.original_excerpt else []}],
                    "suggested_direction": [f.supplier_strategy],
                    "fallback_text": [],
                    "recommended_rewrite": f.suggested_rewrite,
                    "rewrite_reason": f.risk_description,
                    "rewrite_reason_codes": [f.finding_id],
                    "risk_tier": f"{'HIGH (구조적 mismatch — 계약당사자/청구주체/수금책임 정합성 문제)' if is_high else 'MEDIUM (절차적 불이익 또는 조건부 리스크)'}",
                    "changed_segments": [],
                    "clause_topic": f.clause_identity,
                    "high_risk": is_high,
                    "approval_required": is_high,
                    "unfavorable_to_us": True,
                    "worst_case_scenario": f.worst_case_scenario,
                    "is_structure_mismatch": f.is_structure_mismatch,
                    "structure_finding": f.to_dict(),
                }
                items.append(new_item)
                if cid:
                    existing_clause_ids.add(cid)
                    items_by_clause_id[cid] = new_item

    return items


def _infer_unfavorable_to_us(
    *,
    clause_text: str,
    applied_rules: list[dict[str, Any]],
    posture: str,
    party: PartyRole | None,
) -> bool:
    if posture not in ("buyer_favorable", "seller_favorable", "neutral"):
        posture = "neutral"
    if posture == "neutral":
        return True

    t = (clause_text or "")
    rids = {str(ar.get("rule_id") or "") for ar in applied_rules if isinstance(ar, dict)}
    if posture == "buyer_favorable":
        if any(r in rids for r in ("RISK-001", "RISK-002", "RISK-004", "RISK-005", "RISK-006", "RISK-003", "ACT-010")):
            return True
        if ("보증" in t or "하자" in t or "품질" in t) and ("을" in t and ("보증" in t or "하자" in t)):
            return False
        return True
    if posture == "seller_favorable":
        if any(r in rids for r in ("RISK-001", "RISK-002")):
            return False
        return True
    return True

