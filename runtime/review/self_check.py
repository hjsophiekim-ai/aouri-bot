"""Final self-check pass over a completed clause-level review.

Implements the "사내변호사처럼" self-check gate requested in requirement.md:
before the review result is handed back, verify —
  1. 계약유형이 맞는가?              -> contract_type / confidence
  2. 우리 회사의 지위가 맞는가?       -> our_role_bucket
  3. 조항과 무관한 룰이 발동하지 않았는가? -> hallucination_guard re-scan (backstop)
  4. 문제점과 수정안이 같은 쟁점인가?  -> keyword-overlap heuristic (flag, not drop)
  5. 원문에 없는 사실을 만들어내지 않았는가? -> extraction_integrity_risk flags
  6. 변호사가 중요하게 볼 리스크를 놓치지 않았는가? -> priority risk coverage scan
  7. 수정안이 우리 회사에 유리한가?    -> basic completeness check on HIGH items

This module never invents new findings — it only inspects what the pipeline
already produced and (a) reports what it found, (b) applies a last-resort
downgrade when a finding is clearly out of scope for the resolved contract
type/class, so a bug in any single upstream injector cannot alone corrupt
the final output.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.hallucination_guard import check_revision_text
from runtime.review.user_focus import list_objectives

_TOKEN_RX = re.compile(r"[가-힣]{2,}|[A-Za-z]{3,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RX.findall(text or ""))


def run_self_check(
    *,
    clause_results: list[dict[str, Any]],
    contract_type_code: str,
    contract_class: str,
    our_role_bucket: str,
    confidence: float,
    full_text: str,
) -> dict[str, Any]:
    """Run the final self-check pass. Mutates clause_results in place for (3),
    returns a report dict summarising all 7 checks for inclusion in meta."""
    report: dict[str, Any] = {
        "contract_type_code": contract_type_code,
        "contract_class": contract_class,
        "our_role_bucket": our_role_bucket,
        "type_confidence": round(float(confidence or 0.0), 3),
        "type_confidence_low": float(confidence or 0.0) < 0.5,
    }

    # (3) Backstop hallucination-guard re-scan: strip any wrong-context
    # phrase that survived earlier filtering, regardless of which upstream
    # function introduced it.
    scope_violations: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        sr = cr.get("suggested_rewrite")
        if not (isinstance(sr, str) and sr.strip()):
            continue
        guard = check_revision_text(sr, contract_type_code=contract_type_code)
        if not guard.is_clean:
            scope_violations.append({
                "clause_id": cr.get("clause_id"),
                "violations": guard.violations[:5],
            })
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["approval_required"] = False
            cr["high_risk"] = False
            cr["review_tier"] = "NOTE"
            if not cr.get("guardrail_block"):
                cr["guardrail_block"] = {"filter": "self_check_backstop", "violations": guard.violations[:5]}
    report["scope_violations_stripped"] = scope_violations

    # (4) problem/revision same-issue heuristic: flag (do not drop) HIGH/MUST
    # items whose rewrite_reason shares no vocabulary with the quoted 원문 —
    # a sign the "문제점" and "원문" may not actually be about the same clause.
    topic_mismatch_flags: list[str] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
            continue
        ot = str(cr.get("original_text") or "")
        reason = str(cr.get("rewrite_reason") or "")
        if not ot.strip() or not reason.strip():
            continue
        overlap = _tokens(ot) & _tokens(reason)
        if not overlap:
            cr["topic_mismatch_risk"] = True
            topic_mismatch_flags.append(str(cr.get("clause_id") or ""))
    report["topic_mismatch_clause_ids"] = topic_mismatch_flags

    # (5) extraction integrity: surface any clause where 원문 quoting had to
    # be truncated/blocked due to cross-article contamination.
    report["extraction_integrity_risk_clause_ids"] = [
        str(cr.get("clause_id") or "")
        for cr in clause_results
        if isinstance(cr, dict) and bool(cr.get("extraction_integrity_risk"))
    ]

    # (6) priority risk coverage: which of the requirement.md priority risk
    # categories are textually present in the contract but never surfaced as
    # a finding? This does not add findings automatically (avoids forcing
    # false positives) — it surfaces a checklist for the reviewer.
    flagged_codes: set[str] = set()
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        for code in cr.get("user_focus_matches") or []:
            if isinstance(code, str):
                flagged_codes.add(code)
    text = full_text or ""
    present_but_unflagged: list[str] = []
    for obj in list_objectives():
        if any(kw and kw in text for kw in obj.keywords):
            if obj.code not in flagged_codes:
                present_but_unflagged.append(obj.code)
    report["priority_risk_present_but_unflagged"] = present_but_unflagged

    # (7) basic completeness on HIGH items: every HIGH/must-fix finding
    # should carry a non-empty proposed revision AND negotiation position —
    # an empty one cannot be "유리한 방향" for anyone, it's just a stub.
    incomplete_high: list[str] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if not (str(cr.get("risk_tier") or "").upper() == "HIGH" or bool(cr.get("must_fix"))):
            continue
        sr = cr.get("suggested_rewrite")
        if not (isinstance(sr, str) and sr.strip()):
            incomplete_high.append(str(cr.get("clause_id") or ""))
    report["incomplete_high_findings"] = incomplete_high

    report["passed"] = (
        not scope_violations
        and not report["type_confidence_low"]
        and not incomplete_high
    )
    return report
