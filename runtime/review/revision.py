from __future__ import annotations

import re
from typing import Any

from runtime.services.query_service import TRIGGER_MAP
from runtime.review.clause_extraction import ClauseChunk, extract_clauses
from runtime.review.rewrite_engine import propose_clause_specific_rewrite
from runtime.review.party_role import PartyRole
from runtime.review.word_markers import contains_wordprocessingml_markers


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
        clause_issues: list[dict[str, Any]] = []
        applied_rules: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        high_risk = False
        approval_required = False

        for rid, kws in rule_keywords.items():
            if not kws:
                continue
            matched_kws = [k for k in kws if k.lower() in c.text.lower()]
            if matched_kws:
                r = matched_by_id[rid]
                risk_level = str(r.get("risk_level", "") or "")
                is_high = risk_level.lower() in ("high", "very_high", "critical")
                is_approval = bool(r.get("approval_required")) or r.get("rule_status") == "approval_required"
                high_risk = high_risk or is_high
                approval_required = approval_required or is_approval
                clause_issues.append(
                    {
                        "issue_title": str(r.get("title", rid)),
                        "issue_detail": str(r.get("description", "")),
                        "review_action": list(r.get("review_action") or []),
                        "risk_level": risk_level,
                        "high_risk": is_high,
                        "approval_required": is_approval,
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

        proposal = propose_clause_specific_rewrite(clause_text=c.text, applied_rules=applied_rules, posture=posture, party=party)
        recommended_rewrite = proposal.suggested_rewrite if proposal else None
        rewrite_reason = proposal.rewrite_reason if proposal else None
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
                "clause_title": c.title,
                "original_clause": c.text,
                "detected_issues": clause_issues,
                "applied_rules": applied_rules,
                "match_evidence": evidence,
                "suggested_direction": suggestion_dirs,
                "fallback_text": replacement_texts,
                "recommended_rewrite": recommended_rewrite,
                "rewrite_reason": rewrite_reason,
                "high_risk": high_risk,
                "approval_required": approval_required,
                "unfavorable_to_us": unfavorable_to_us,
            }
        )

    items.sort(key=lambda it: (0 if it.get("approval_required") else 1, 0 if it.get("high_risk") else 1, str(it.get("clause_id") or "")))
    summary = {
        "issue_clause_count": len(items),
        "high_risk_clause_count": sum(1 for it in items if it["high_risk"]),
        "approval_required_clause_count": sum(1 for it in items if it["approval_required"]),
        "recommended_rewrite_clause_count": sum(1 for it in items if it.get("recommended_rewrite")),
        "unfavorable_to_us_clause_count": sum(1 for it in items if bool(it.get("unfavorable_to_us"))),
    }
    return {"summary": summary, "items": items}


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

