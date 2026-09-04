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
    # 범용 사내변호사형 검토 엔진 전면 보정(2026-09-04 지시, 그림닷컴
    # 판매지원 용역계약 실사례) — 판매/위탁판매/대리판매/중개 계약에서
    # 자주 나타나는데 위 6개 그룹으로는 안 잡히던 리스크 신호군.
    "수수료/환수": ["수수료", "환수", "정산"],
    "기존계약연계": ["별도로", "위탁판매", "대리점", "계약기간과 동일"],
    "소비자/상품책임": ["고객", "하자", "진위", "반품", "환불"],
    "일방적권리/추가업무": ["갑의 해석", "기타", "요청사항"],
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


_RX_MONETARY_PENALTY_LANGUAGE = re.compile(
    r"지체상금|위약금|손해배상액의?\s*예정"
    r"|liquidated\s+damages|penalty\s+for\s+delay|\d+(?:\.\d+)?\s*%[^.\n]{0,40}(?:per|each)\s+day",
    re.IGNORECASE,
)
_RX_RATE_REDUCTION_MARKER = re.compile(r"인하|낮은\s*요율|lower(?:ed)?\s+rate", re.IGNORECASE)
_RX_CAP_MARKER = re.compile(r"상한|한도|cap\b|maximum|exceed", re.IGNORECASE)
_RX_CONDITIONAL_FUNDING_LANGUAGE = re.compile(
    r"정부\s*지원|보조금|지원사업|지원금|투자금(?:을|이)?\s*(?:지급|지원)|보험금"
    r"|government\s+(?:grant|program|subsidy|support)|support\s+company\s+under\s+the",
    re.IGNORECASE,
)


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
    legal_map_fields: dict[str, Any] | None = None,
    legal_applicability_results: list[dict[str, Any]] | None = None,
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
        # common_legal_risk.py의 결정론적 rule(is_common_legal_risk=True)은
        # 원문에 실제로 등장하는 문구를 정규식으로 직접 확인해 만든 고정밀
        # finding이다(2026-09-04 지시 회귀조건 — "위탁판매"/"용역수수료"처럼
        # 계약이 실제로 다루는 어휘를, contract_type_code 오분류 하나만으로
        # "wrong context"로 오인해 벗겨내는 사고를 방지). 다른 guardrail
        # (HIGH 캡 등)에서도 이미 같은 이유로 이 rule군을 예외 처리한다.
        if bool(cr.get("is_common_legal_risk")):
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
            # severity가 risk_tier와 별도 필드로 남아있으면(예: AI가 처음에
            # HIGH로 매긴 뒤 이 백스톱이 risk_tier만 LOW로 낮춘 경우), 어느
            # 필드를 읽느냐에 따라 UI(clause_meta.final_findings)와 DOCX
            # 다운로드 재구성 경로가 이 finding을 서로 다르게 HIGH/MEDIUM
            # 버킷에 포함/제외해 REVIEW_FAILED_OUTPUT_MISMATCH를 유발한다
            # (2026-09-04, KOTRA 다운로드 재현으로 확인) — 항상 함께 낮춘다.
            cr["severity"] = "LOW"
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

    # (10) Global Reasoning self-check (2026-09-03 지시, 요구 11) — 사내변호사가
    # 결과를 넘기기 전 마지막으로 스스로에게 던지는 8개 질문. 계산 가능한
    # 항목(10-1/10-2/10-3/10-5)이 구조적으로 실패하면 REVIEW_FAILED_GLOBAL_
    # REASONING으로 블록하고, 나머지는 감사 추적용 보고 필드로만 남긴다.
    active_clause_results = [
        cr for cr in clause_results
        if isinstance(cr, dict) and not bool(cr.get("dedup_suppressed")) and not bool(cr.get("keep_as_is"))
    ]

    # 10-1: 다른 조항에서 이미 해결된 문제를 중복 지적하지 않았는가 —
    # GLOBAL_CROSS_CLAUSE_VALIDATION을 백스톱으로 다시 실행해 놓친 게 있으면
    # 여기서 억제하고, 몇 건이 새로 억제됐는지 보고한다(0건이 정상).
    from runtime.review.global_cross_clause_validation import apply_global_cross_clause_validation
    _pre_suppressed_ids = {
        str(cr.get("clause_id") or id(cr)) for cr in clause_results
        if isinstance(cr, dict) and bool(cr.get("dedup_suppressed"))
    }
    apply_global_cross_clause_validation(clause_results, full_text)
    _newly_suppressed = [
        str(cr.get("clause_id") or "")
        for cr in clause_results
        if isinstance(cr, dict) and bool(cr.get("dedup_suppressed"))
        and str(cr.get("clause_id") or id(cr)) not in _pre_suppressed_ids
    ]
    report["cross_clause_duplicates_caught_at_self_check"] = _newly_suppressed

    # 10-2: 계약금액 대비 가장 큰 금전리스크(지체상금·위약금 등)를 찾았는가 —
    # 원문에 벌칙성 금전조항 언어가 있는데 대응 finding이 하나도 없으면 놓친 것.
    _has_penalty_finding = any(
        str(cr.get("clause_id") or "") == "clr_late_penalty_rate_uncapped"
        or "%" in str(cr.get("legal_business_reason") or "")
        for cr in active_clause_results
    )
    _monetary_risk_unconfirmed = bool(
        _RX_MONETARY_PENALTY_LANGUAGE.search(full_text or "") and not _has_penalty_finding
    )
    report["largest_monetary_risk_unconfirmed"] = _monetary_risk_unconfirmed

    # 10-3: 타인의 귀책을 우리가 떠안는 구조가 있는데 severity가 HIGH가
    # 아닌 경우 — indemnity_direction 메타데이터(있는 finding만) 기준.
    _third_party_fault_not_high: list[str] = []
    for cr in active_clause_results:
        direction = cr.get("indemnity_direction")
        if not isinstance(direction, dict):
            continue
        if direction.get("fault_source") in ("counterparty_own", "third_party_shifted_to_us"):
            if str(cr.get("risk_tier") or "").upper() != "HIGH":
                _third_party_fault_not_high.append(str(cr.get("clause_id") or ""))
    report["third_party_fault_borne_by_us_not_high"] = _third_party_fault_not_high

    # 10-4: rate와 cap을 같이 검토했는가 — negotiation_ladder가 있으면
    # 그 안에 요율 인하와 상한 설정이 모두 언급되는지 확인(보고 전용).
    _rate_cap_not_joint: list[str] = []
    for cr in active_clause_results:
        if str(cr.get("clause_id") or "") != "clr_late_penalty_rate_uncapped":
            continue
        ladder = cr.get("negotiation_ladder")
        ladder_text = " ".join(
            f"{t.get('action', '')} {t.get('rewrite_text', '')}"
            for t in ladder if isinstance(t, dict)
        ) if isinstance(ladder, list) else str(cr.get("suggested_rewrite") or "")
        if not (_RX_RATE_REDUCTION_MARKER.search(ladder_text) and _RX_CAP_MARKER.search(ladder_text)):
            _rate_cap_not_joint.append(str(cr.get("clause_id") or ""))
    report["penalty_rate_cap_not_jointly_reviewed"] = _rate_cap_not_joint

    # 10-5: 정부지원·환수 구조를 확인했는가 — 조건부 자금 언어가 있는데
    # 관련 finding도 legal_map 필드도 전혀 없으면 검토가 빠진 것.
    _lm_fields = legal_map_fields or {}
    _has_conditional_funding_review = any(
        str(cr.get("clause_id") or "") == "clr_conditional_funding_unclear"
        for cr in clause_results if isinstance(cr, dict)
    ) or bool(_lm_fields.get("conditional_funding_structure"))
    _conditional_funding_unchecked = bool(
        _RX_CONDITIONAL_FUNDING_LANGUAGE.search(full_text or "") and not _has_conditional_funding_review
    )
    report["conditional_funding_unchecked"] = _conditional_funding_unchecked

    # 10-6: 적용법률이 실제 업무지역과 맞는가 — nexus 미확인
    # (additional_facts_needed 존재)인데 risk_level이 HIGH로 남은 경우.
    _nexus_unconfirmed_but_high: list[str] = []
    for r in (legal_applicability_results or []):
        if not isinstance(r, dict):
            continue
        if str(r.get("risk_level") or "").upper() == "HIGH" and r.get("additional_facts_needed"):
            _nexus_unconfirmed_but_high.append(str(r.get("statute") or ""))
    report["jurisdiction_nexus_unconfirmed_but_high"] = _nexus_unconfirmed_but_high

    # 10-7: 우리에게 유리한 권리를 불필요하게 줄이지 않았는가 — Phase 7
    # do-not-harm 게이트가 실제로 보호한 항목 기록(정보 제공용).
    report["favorable_rights_protected"] = [
        str(cr.get("clause_id") or "")
        for cr in clause_results
        if isinstance(cr, dict)
        and isinstance(cr.get("guardrail_block"), dict)
        and cr["guardrail_block"].get("favorable_right_protection")
    ]

    # 10-8: 수정안이 실제 협상 가능한가 — HIGH/MEDIUM인데 suggested_rewrite도
    # negotiation_ladder도 전부 비어있으면 협상할 문안 자체가 없는 것.
    _no_negotiable_remedy: list[str] = []
    for cr in active_clause_results:
        if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
            continue
        sr = cr.get("suggested_rewrite")
        ladder = cr.get("negotiation_ladder")
        if not (isinstance(sr, str) and sr.strip()) and not (isinstance(ladder, list) and ladder):
            _no_negotiable_remedy.append(str(cr.get("clause_id") or ""))
    report["findings_without_negotiable_remedy"] = _no_negotiable_remedy

    # (10-9) Senior Counsel Self-Check (2026-09-04 지시, 요구 13) — 이미
    # 계산된 exposure/negotiation_priority 데이터를 재집계만 한다(새 판단을
    # 만들지 않는 순수 보고 필드, 게이트 아님). "직접/조건부 부담 리스크가
    # 몇 건인가", "실제로 지금 협상해야 할 항목은 몇 건인가"를 한눈에 보여줘
    # "모든 불리한 문구를 없애는 로펌"이 아니라 "치명적 리스크만 줄이는
    # 사내변호사" 관점으로 결과를 요약한다.
    _must_fix = [str(cr.get("clause_id") or "") for cr in active_clause_results if cr.get("negotiation_priority") == "MUST_FIX"]
    _negotiate = [str(cr.get("clause_id") or "") for cr in active_clause_results if str(cr.get("negotiation_priority") or "").startswith("NEGOTIATE_IF_POSSIBLE")]
    _accept = [str(cr.get("clause_id") or "") for cr in active_clause_results if cr.get("negotiation_priority") == "ACCEPT"]
    _direct_or_contingent = [
        str(cr.get("clause_id") or "") for cr in active_clause_results
        if cr.get("business_exposure") in ("direct", "contingent")
    ]
    report["senior_counsel_self_check"] = {
        "direct_or_contingent_exposure_findings": _direct_or_contingent,
        "must_fix_count": len(_must_fix),
        "must_fix_clause_ids": _must_fix,
        "negotiate_count": len(_negotiate),
        "accept_count": len(_accept),
        "feasibility_low_flagged": [
            str(cr.get("clause_id") or "") for cr in active_clause_results
            if cr.get("negotiation_feasibility") == "LOW"
        ],
    }

    # 10-1의 결과(백스톱이 새로 억제한 건)는 "다른 조항에 이미 있는 답을
    # 다시 지적"하는 구조적 오류로, 나머지 global reasoning 항목들과는 성격이
    # 달라 전용 상태(REVIEW_FAILED_GLOBAL_CROSS_CLAUSE)로 분리한다 — KOTRA
    # Article 8.2(Article 9에 이미 준거법·중재가 있는데 "부재"로 지적) 같은
    # 잔존 사례가 실제로 나오면 이 상태로 명시적으로 실패시켜야 한다는
    # 지시(2026-09-04)를 반영.
    cross_clause_failed = bool(_newly_suppressed)
    report["cross_clause_ok"] = not cross_clause_failed

    global_reasoning_failed = bool(
        _monetary_risk_unconfirmed
        or _third_party_fault_not_high
        or _conditional_funding_unchecked
    )
    report["global_reasoning_ok"] = not global_reasoning_failed

    # (11) 문장 완결성 HARD GATE (2026-09-03 지시, 요구 6) — 문장이 중간에서
    # 잘리거나("KOTRA shall pay Consultant a total of USD"), "[추가 권고]"
    # 뒤에 내용이 없거나, 원문 일부가 앞에서 잘려 "ayment"/"icle" 같은
    # 조각으로 시작하는 경우를 다른 어떤 판단보다 먼저 걸러낸다 — 깨진
    # 문장이 포함된 결과는 법적 판단의 정확성 여부를 따지기 이전에 이미
    # 사용할 수 없는 결과이기 때문이다.
    from runtime.review.language_quality_gate import detect_language_quality_issues
    language_quality_violations = detect_language_quality_issues(clause_results)
    report["language_quality_violations"] = language_quality_violations
    language_quality_failed = bool(language_quality_violations)

    hard_integrity_failed = bool(missing_clause_id_ids) or final_findings_count_mismatch
    if missing_targets:
        report["review_status"] = "REVIEW_FAILED_USER_REQUEST_MISSING"
    elif hard_integrity_failed:
        report["review_status"] = "REVIEW_FAILED"
    elif language_quality_failed:
        report["review_status"] = "REVIEW_FAILED_LANGUAGE_QUALITY"
    elif cross_clause_failed:
        report["review_status"] = "REVIEW_FAILED_GLOBAL_CROSS_CLAUSE"
    elif false_negative_suspected:
        report["review_status"] = "REVIEW_FAILED_LIKELY_FALSE_NEGATIVE"
    elif global_reasoning_failed:
        report["review_status"] = "REVIEW_FAILED_GLOBAL_REASONING"
    else:
        report["review_status"] = "OK"

    report["passed"] = (
        not scope_violations
        and not report["type_confidence_low"]
        and not incomplete_high
        and not false_negative_suspected
        and not hard_integrity_failed
        and targets_ok
        and not global_reasoning_failed
        and not language_quality_failed
        and not cross_clause_failed
    )
    return report
