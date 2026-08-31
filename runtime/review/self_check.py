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
from runtime.review.korean_polish import _strip_unverified_law_article_numbers
from runtime.review.user_focus import list_objectives

_TOKEN_RX = re.compile(r"[가-힣]{2,}|[A-Za-z]{3,}")

# Broad (looser than the Layer-1 detection regexes) keyword groups used only
# to catch a HIGH=0/MEDIUM=0 result that is implausible given the contract's
# own text — a lawyer would never sign off on "0 findings" for a contract
# that visibly contains exemption/indemnity/termination/confidentiality
# language. This is intentionally coarse: it exists to force a "재검토
# 필요" flag, not to auto-generate findings.
_FALSE_NEGATIVE_RISK_GROUPS: dict[str, list[str]] = {
    "면책": ["면책", "책임을 지지 아니한다", "책임을 부담하지 아니한다", "귀책사유"],
    "손해배상/구상": ["손해배상", "구상", "배상책임", "배상액"],
    "해지": ["해지", "계약기간", "약정기간"],
    "비밀유지": ["비밀유지", "기밀", "영업비밀"],
    "외부약관편입": ["약관", "규정을 적용", "규정을 준용"],
    "경쟁제한": ["유사한 내용의", "사전에 통보", "타 기관", "타기관"],
}


# Generic Korean legal-prose function words that end up in nearly every
# clause regardless of topic ("~하여야 한다", "~할 수 있다", "~에 대하여", ...).
# Left in, these trivially "overlap" any two unrelated sentences and make the
# topic-mismatch check (item 4 below) a no-op — the exact failure mode this
# stopword filter exists to close.
_STOPWORD_TOKENS: frozenset[str] = frozenset({
    "한다", "있다", "없다", "된다", "한다.", "하다", "되다",
    "아니한다", "아니된다", "하여야", "되어야", "하여서는", "하지",
    "경우", "때에", "대하여", "관하여", "관한", "대한", "위하여", "위한",
    "따라", "따른", "의하여", "의한",
    "각호", "각", "등의", "등을", "등이", "그리고", "또는", "및",
    "이러한", "그러한", "본", "당", "해당",
})


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RX.findall(text or "")) - _STOPWORD_TOKENS


def run_self_check(
    *,
    clause_results: list[dict[str, Any]],
    contract_type_code: str,
    contract_class: str,
    our_role_bucket: str,
    confidence: float,
    full_text: str,
    final_findings_counts: dict[str, Any] | None = None,
    mandatory_review_targets: list[dict[str, Any]] | None = None,
    final_findings_clause_ids: set[str] | None = None,
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

    # (3b) Backstop law-citation guard: strip any unverified external-law
    # article number (e.g. "대리점법 제18조") that survived upstream, no
    # matter which rule/checklist/AI-merge path produced it — only the law
    # name may remain, since we have no live 국가법령정보 API/DB to confirm
    # the article number is correct. Applied to every string field EXCEPT the
    # verbatim/structural ones (original_text/context_text/clause_title/
    # display_path/article_number/clause_id) — those must reproduce the
    # source document exactly, including any statute citation the contract
    # itself quotes, so they are never rewritten. Every other field is
    # system-generated commentary (rewrite_reason, why_matters,
    # worst_case_scenario, legal_business_reason, negotiation_strategy, ...)
    # and the set of field names injectors use keeps growing, so scrubbing by
    # exclusion rather than an allowlist avoids silently missing new ones.
    _VERBATIM_FIELDS = frozenset({
        "original_text", "context_text", "clause_title", "display_path",
        "article_number", "clause_id",
    })
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        for field, v in list(cr.items()):
            if field in _VERBATIM_FIELDS:
                continue
            if isinstance(v, str) and v:
                cr[field] = _strip_unverified_law_article_numbers(v)

    # (4) problem/revision same-issue heuristic: flag (do not drop) HIGH/MEDIUM
    # items whose rewrite_reason shares no vocabulary with the quoted 원문 —
    # a sign the "문제점" and "원문" may not actually be about the same clause.
    #
    # This is reporting-only, not an auto-strip gate: a bag-of-words overlap
    # check (even with common function words removed) is far too blunt to
    # safely delete content automatically — real AI-written rewrite_reason
    # text routinely paraphrases the clause instead of repeating its exact
    # nouns, which produces "zero overlap" for entirely correct, on-topic
    # findings. An earlier attempt to auto-strip HIGH findings on this signal
    # was reverted after it fired on FITI's own genuine 제5조/제6조/제11조/제14조
    # findings in a real run — false positives at a rate that made the
    # "validation" actively harmful. Use hallucination_guard's targeted
    # phrase-list backstop (item 3 above) for high-precision auto-stripping;
    # this heuristic stays a flag for manual review only.
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

    # (6) false-negative check: HIGH=0 and MEDIUM=0 must not silently pass as
    # "no risk" when the contract text visibly contains common-risk language.
    # When Layer 1 (common_legal_risk) and Layer 2 (type-specific) checklists
    # both found nothing, re-scan with the broader keyword groups below —
    # if any group hits, this is very likely a false negative (a detection
    # gap), not a genuinely clean contract, and must be reported as such
    # rather than shown to the reviewer as "이상 없음".
    high_count = sum(1 for cr in clause_results if isinstance(cr, dict) and str(cr.get("risk_tier") or "").upper() == "HIGH")
    medium_count = sum(1 for cr in clause_results if isinstance(cr, dict) and str(cr.get("risk_tier") or "").upper() == "MEDIUM")
    false_negative_suspected = False
    triggered_risk_groups: list[str] = []
    if high_count == 0 and medium_count == 0:
        for group_name, keywords in _FALSE_NEGATIVE_RISK_GROUPS.items():
            if any(kw in text for kw in keywords):
                triggered_risk_groups.append(group_name)
        false_negative_suspected = bool(triggered_risk_groups)
    report["zero_findings_but_risk_language_present"] = false_negative_suspected
    report["zero_findings_triggered_risk_groups"] = triggered_risk_groups

    # (8) hard integrity gate: a clause_id must exist on every finding (the UI
    # and DOCX both key off clause_id — a missing one means the two renderers
    # can silently diverge on which findings they show), and the single
    # final_findings source of truth (meta.final_findings, shared by the UI
    # and the DOCX writer) must actually match what clause_results contains.
    # Either condition means the result is not safe to present as "정상
    # 완료" — report REVIEW_FAILED rather than a passing status.
    missing_clause_id_ids: list[str] = []
    for idx, cr in enumerate(clause_results):
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")):
            continue
        if not str(cr.get("clause_id") or "").strip():
            missing_clause_id_ids.append(f"<missing:index{idx}>")
    report["clause_id_missing_count"] = len(missing_clause_id_ids)

    final_findings_count_mismatch = False
    if isinstance(final_findings_counts, dict):
        actual_high = sum(
            1 for cr in clause_results
            if isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")
            and str(cr.get("risk_tier") or "").upper() == "HIGH"
        )
        actual_medium = sum(
            1 for cr in clause_results
            if isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")
            and str(cr.get("risk_tier") or "").upper() == "MEDIUM"
        )
        reported_high = int(final_findings_counts.get("high_count") or 0)
        reported_medium = int(final_findings_counts.get("medium_count") or 0)
        # final_findings applies its own quality filter (output_filter.filter_issues),
        # so it may legitimately report fewer than the raw tier counts — but it
        # must never report MORE than what clause_results actually contains,
        # and never fewer than zero of what survives should be unaccounted for
        # by more than the filter's own exclusions.
        final_findings_count_mismatch = reported_high > actual_high or reported_medium > actual_medium
    report["final_findings_count_mismatch"] = final_findings_count_mismatch

    # (9) mandatory review targets: clause numbers the user explicitly named
    # in review_focus must survive into the final output — see
    # mandatory_review_target.py. A "flagged" target (a real issue was found
    # for it) that doesn't appear in the final high/medium findings means the
    # user's own request was silently dropped somewhere downstream (dedup,
    # truncation, a later guardrail stripping it) — this is not an editorial
    # omission and must block, distinctly from the generic false-negative
    # check above (which only samples broad keyword groups, not an explicit
    # user citation).
    from runtime.review.mandatory_review_target import check_all_targets_addressed
    targets_ok, missing_targets = check_all_targets_addressed(
        mandatory_review_targets or [],
        final_findings_clause_ids=final_findings_clause_ids,
    )
    report["mandatory_review_targets"] = mandatory_review_targets or []
    report["mandatory_targets_missing"] = missing_targets

    hard_integrity_failed = bool(missing_clause_id_ids) or final_findings_count_mismatch
    if missing_targets:
        report["review_status"] = "REVIEW_FAILED_USER_REQUEST_MISSING"
    elif hard_integrity_failed:
        report["review_status"] = "REVIEW_FAILED"
    elif false_negative_suspected:
        report["review_status"] = "REVIEW_FAILED_LIKELY_FALSE_NEGATIVE"
    else:
        report["review_status"] = "OK"

    report["passed"] = (
        not scope_violations
        and not report["type_confidence_low"]
        and not incomplete_high
        and not false_negative_suspected
        and not hard_integrity_failed
        and targets_ok
    )
    return report
