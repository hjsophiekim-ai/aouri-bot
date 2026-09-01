"""Output quality filter and ReviewIssue dataclass.

Enforces:
  - No empty/placeholder fields in any ReviewIssue
  - No forbidden template phrases (hallucination guard)
  - LOW issues excluded from default output
  - HIGH issues must have non-trivial proposed_revision
  - Deduplication: same risk merged to representative clause
  - Count limits: HIGH unlimited (true risk only), MEDIUM max 10, LOW opt-in only
  - Top risks: max 5 across HIGH/MEDIUM
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from runtime.review.hallucination_guard import check_revision_text


# ─── ReviewIssue ──────────────────────────────────────────────────────────────

@dataclass
class ReviewIssue:
    """Single structured review finding with all required fields."""
    clause_id: str
    clause_title: str
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    approval_required: bool
    issue_title: str
    original_text: str
    problem: str
    legal_business_reason: str
    proposed_revision: str
    negotiation_position: str
    confidence: float
    related_clause_ids: list[str] = field(default_factory=list)
    is_mandatory: bool = False
    # Clause identity — carried through so the DOCX/PDF renderer can always
    # show a real "제N조 제N항 제N호" in the finding's title instead of a
    # bare rule id or a generic article-heading name (e.g. "손해배상책임"),
    # and so findings anchored on the exact same clause can be merged
    # instead of shown as separate, duplicate-looking findings.
    article_number: str = ""
    paragraph_number: str = ""
    item_number: str = ""
    display_path: str = ""

    @property
    def display_bucket(self) -> str:
        """UI display bucket: 필수수정 / 권장수정 / 참고.

        Derived from severity so UI and DOCX always agree.
        """
        if self.severity == "HIGH":
            return "필수수정"
        if self.severity == "MEDIUM":
            return "권장수정"
        return "참고"

    def to_dict(self) -> dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "clause_title": self.clause_title,
            "severity": self.severity,
            "display_bucket": self.display_bucket,
            "approval_required": self.approval_required,
            "issue_title": self.issue_title,
            "original_text": self.original_text,
            "problem": self.problem,
            "legal_business_reason": self.legal_business_reason,
            "proposed_revision": self.proposed_revision,
            "negotiation_position": self.negotiation_position,
            "confidence": round(self.confidence, 3),
            "related_clause_ids": list(self.related_clause_ids),
            "is_mandatory": self.is_mandatory,
            "article_number": self.article_number,
            "paragraph_number": self.paragraph_number,
            "item_number": self.item_number,
            "display_path": self.display_path,
        }


# ─── Empty / placeholder markers ──────────────────────────────────────────────

_EMPTY_MARKERS: frozenset[str] = frozenset({
    "제안 문안 없음",
    "사유 없음",
    "원문 핵심: -",
    "원문핵심: -",
    "수정 문구 없음",
    "수정안 없음",
    "(없음)",
    "해당 없음",
    "미작성",
    "-",
    "",
})

_GENERIC_MARKERS: tuple[str, ...] = (
    "통합 관리 필요",
    "일반적으로",
    "일반 법령에 따라",
    "법령에 따른 일반론",
    "수정 문구 자동생성 보류",
    "조항 정체성/거래구조 확인 필요",
)


def _is_empty(text: str | None) -> bool:
    if text is None:
        return True
    s = text.strip()
    if not s:
        return True
    return s in _EMPTY_MARKERS


def _is_generic(text: str | None) -> bool:
    if not text or not text.strip():
        return True
    return any(m in text for m in _GENERIC_MARKERS)


# ─── Validation ───────────────────────────────────────────────────────────────

def is_valid_issue(
    issue: ReviewIssue,
    *,
    contract_type_code: str = "",
) -> bool:
    """Return True iff the issue passes all quality gates.

    Quality gates:
    1. original_text, problem, legal_business_reason, proposed_revision must all be non-empty.
    2. No placeholder/marker text in any field.
    3. HIGH severity requires a substantive (non-generic) proposed_revision.
    4. Hallucination guardrail must pass.
    5. Issue must not be purely generic.
    """
    # Gate 1+2: required non-empty fields
    if _is_empty(issue.original_text):
        return False
    if _is_empty(issue.problem):
        return False
    if _is_empty(issue.legal_business_reason):
        return False
    if _is_empty(issue.proposed_revision):
        return False

    # Gate 3: HIGH must have substantive revision
    if issue.severity == "HIGH" and _is_generic(issue.proposed_revision):
        return False

    # Gate 4: hallucination guard
    if contract_type_code:
        guard = check_revision_text(
            issue.proposed_revision,
            contract_type_code=contract_type_code,
        )
        if not guard.is_clean:
            return False

    # Gate 5: not purely generic
    if _is_generic(issue.problem) and _is_generic(issue.legal_business_reason):
        return False

    return True


# ─── Deduplication ────────────────────────────────────────────────────────────

def _identity_snippet(text: str) -> str:
    """Normalize original_text down to a short, comparable fingerprint —
    strip whitespace/quotes/leading item numbers so two quotes of the exact
    same passage compare equal even with minor formatting differences."""
    import re as _re
    t = _re.sub(r'["\'“”‘’\s]+', "", text or "")
    t = _re.sub(r"^\d+[.\)]", "", t)
    return t[:40]


def _clause_identity_key(issue: ReviewIssue) -> tuple[str, str, str] | None:
    # Prefer the already-formatted display_path string ("제5조 제2항 1호")
    # over the separate article/paragraph/item fields: a clause_result whose
    # chunk lookup failed downstream can end up with paragraph_number/
    # item_number blank while display_path (set earlier, straight from the
    # matched segmentation leaf) is still correct — comparing the tuple in
    # that case would wrongly treat two findings on the exact same clause as
    # unrelated. display_path is normalized identically by every producer
    # (clause_extraction._display_path), so an exact string match is exactly
    # as precise as the tuple when both are present.
    #
    # [2026-09-01 실사례] rule-engine(clr_*) 항목은 article 단위까지만
    # display_path를 채우고 paragraph_number는 비워두는 경우가 많다 — 그
    # 결과 같은 조(예: "제6조") 안에서 서로 다른 항(①의 최선노력 기준,
    # ⑤의 제3자 연대책임, ⑥의 관련계약 해지)을 각각 가리키는 완전히 다른
    # findings 3건이 전부 "같은 조항"으로 뭉쳐져 2건이 조용히 사라지는
    # 사고가 실제 NDA 리뷰에서 발생했다. paragraph_number가 비어 있을 때는
    # 인용된 원문 스니펫으로 대신 구분해, 진짜 같은 문장을 가리키는 경우만
    # 병합되도록 한다.
    if issue.display_path:
        para = issue.paragraph_number or _identity_snippet(issue.original_text)
        return (issue.display_path, para, issue.item_number)
    if not issue.article_number:
        return None
    return (issue.article_number, issue.paragraph_number, issue.item_number)


def _merge_same_clause_issues(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    """Merge findings anchored on the exact same (article, paragraph, item)
    identity into one representative.

    The main per-clause AI-reviewed item and a rule-engine-injected item
    (clr_*/tsr_*/...) routinely both fire on the same real clause — in
    substance the same finding shown twice under two different titles (e.g.
    a generic AI item titled "손해배상책임" and "제11조 제2항 [구상권
    범위·한도 불명확]", both anchored on the exact same 제11조② text).
    Distinct item numbers (e.g. 제5조 제2항 1호 vs 2호) are never merged —
    only an EXACT (article, paragraph, item) match collapses, since those
    are genuinely different clauses even when they share an article/
    paragraph.
    """
    from runtime.review.clause_extraction import is_real_segment_clause_id

    _SEV_ORDER = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    groups: dict[tuple[str, str, str], list[ReviewIssue]] = {}
    standalone: list[ReviewIssue] = []
    for issue in issues:
        key = _clause_identity_key(issue)
        if key is None:
            standalone.append(issue)
        else:
            groups.setdefault(key, []).append(issue)

    def _priority(i: ReviewIssue) -> tuple[int, int, int]:
        # Higher severity wins first (never silently downgrade what's
        # shown); among equal severity, prefer a rule-engine-authored
        # finding (clr_*/tsr_*/MI-/...) over a raw per-clause AI item, since
        # the former is hand-reasoned, specific text rather than a generic
        # restatement; final tie-break favors the more detailed revision.
        return (
            _SEV_ORDER.get(i.severity, 0),
            0 if is_real_segment_clause_id(i.clause_id) else 1,
            len(i.proposed_revision),
        )

    out: list[ReviewIssue] = list(standalone)
    for group in groups.values():
        if len(group) == 1:
            out.append(group[0])
            continue
        rep = max(group, key=_priority)
        # The folded-in duplicate's own clause_id/display_path is NOT a
        # "related clause" — it names the exact same clause as `rep`, just
        # from a different source, so listing it as related would read as
        # self-reference ("함께 수정할 조항: 제6조 제4항" on a finding that
        # already IS about 제6조 제4항). Only genuinely different clauses —
        # each duplicate's own already-known related_clause_ids (e.g. a
        # sibling article carrying the same defect) — are worth carrying
        # forward.
        merged_related = list(rep.related_clause_ids)
        for other in group:
            if other is rep:
                continue
            for rc in other.related_clause_ids:
                if rc not in merged_related:
                    merged_related.append(rc)
            rep.approval_required = rep.approval_required or other.approval_required
            rep.is_mandatory = rep.is_mandatory or other.is_mandatory
        rep.related_clause_ids = merged_related
        out.append(rep)
    return out


def deduplicate_issues(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    """Merge issues with the same issue_title into the highest-severity representative.

    Related clause IDs are accumulated into the representative's `related_clause_ids`.
    """
    issues = _merge_same_clause_issues(issues)
    seen: dict[str, ReviewIssue] = {}
    _SEV_ORDER = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

    for issue in issues:
        key = issue.issue_title.strip()
        if key not in seen:
            seen[key] = issue
        else:
            existing = seen[key]
            # Keep the higher-severity one as representative
            if _SEV_ORDER.get(issue.severity, 0) > _SEV_ORDER.get(existing.severity, 0):
                # Move existing to related, replace with new
                new_related = list(issue.related_clause_ids) + [existing.clause_id]
                seen[key] = ReviewIssue(
                    clause_id=issue.clause_id,
                    clause_title=issue.clause_title,
                    severity=issue.severity,
                    approval_required=issue.approval_required or existing.approval_required,
                    issue_title=issue.issue_title,
                    original_text=issue.original_text,
                    problem=issue.problem,
                    legal_business_reason=issue.legal_business_reason,
                    proposed_revision=issue.proposed_revision,
                    negotiation_position=issue.negotiation_position,
                    confidence=max(issue.confidence, existing.confidence),
                    related_clause_ids=new_related,
                    is_mandatory=issue.is_mandatory or existing.is_mandatory,
                    article_number=issue.article_number,
                    paragraph_number=issue.paragraph_number,
                    item_number=issue.item_number,
                    display_path=issue.display_path,
                )
            else:
                # Add new clause_id to existing's related list
                existing.related_clause_ids.append(issue.clause_id)
                existing.is_mandatory = existing.is_mandatory or issue.is_mandatory

    return list(seen.values())


# ─── Main filter function ─────────────────────────────────────────────────────

def filter_issues(
    issues: list[ReviewIssue],
    *,
    contract_type_code: str = "",
    include_low: bool = False,
    max_medium: int = 10,
    max_top_risks: int = 5,
) -> dict[str, list[ReviewIssue]]:
    """Filter, deduplicate, and categorise issues by severity.

    Default output:
      - HIGH: all valid HIGH issues (no cap — only real risks should reach HIGH)
      - MEDIUM: up to max_medium valid MEDIUM issues
      - LOW: empty (unless include_low=True)
      - top_risks: up to max_top_risks, sorted by severity then confidence

    Args:
        issues: raw list of ReviewIssue objects
        contract_type_code: canonical code from contract_classifier
        include_low: if True, LOW issues are included in output (appendix)
        max_medium: maximum MEDIUM issues to include
        max_top_risks: maximum top risk count
    """
    # isr_*/sppc_* hard gate: 딜러 계약에서는 TOP 리스크/필수수정/승인필요 절대 금지
    _DEALER_TYPE_CODES = frozenset({
        "consignment_sales_agency", "direct_customer_sales_support",
        "dealer_agency", "dealer_rental_service_contract",
    })
    _ADVISORY_PREFIXES_FOR_DEALER = ("isr_", "sppc_", "pi_", "svc_")
    if contract_type_code in _DEALER_TYPE_CODES:
        downgraded: list[ReviewIssue] = []
        for i in issues:
            if any(i.clause_id.startswith(p) for p in _ADVISORY_PREFIXES_FOR_DEALER):
                # 딜러 계약에서 isr_/sppc_은 LOW 참고 처리, approval_required=False
                from dataclasses import replace as _dc_replace
                i = _dc_replace(i, severity="LOW", approval_required=False)
            downgraded.append(i)
        issues = downgraded

    # Step 1: quality gate
    valid = [i for i in issues if is_valid_issue(i, contract_type_code=contract_type_code)]

    # Step 2: deduplicate
    valid = deduplicate_issues(valid)

    # Step 3: split by severity. A clause the user explicitly named in
    # review_focus (is_mandatory=True, see mandatory_review_target.py) must
    # never be silently dropped by the max_medium cap — it is kept in
    # addition to, not counted against, the ordinary top-N MEDIUM slots.
    high = [i for i in valid if i.severity == "HIGH"]
    medium_all = [i for i in valid if i.severity == "MEDIUM"]
    medium_mandatory = [i for i in medium_all if i.is_mandatory]
    medium_other = [i for i in medium_all if not i.is_mandatory][:max_medium]
    medium = medium_mandatory + medium_other
    low = [i for i in valid if i.severity == "LOW"] if include_low else []

    # Step 4: top risks (HIGH first, then MEDIUM, sorted by confidence).
    # Mandatory items are boosted ahead of equal-severity ordinary ones so a
    # user-cited clause can't be squeezed out of the TOP N by confidence rank.
    _SEV_KEY = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    combined = sorted(
        high + medium,
        key=lambda x: (int(x.is_mandatory), _SEV_KEY.get(x.severity, 0), x.confidence),
        reverse=True,
    )
    top_risks = combined[:max_top_risks]

    return {
        "high": high,
        "medium": medium,
        "low": low,
        "top_risks": top_risks,
    }


def clause_results_to_review_issues(clause_results: list[dict[str, Any]]) -> list[ReviewIssue]:
    """Convert clause_results dicts to ReviewIssue objects.

    Single canonical conversion — used by both the initial review pipeline
    (clause_level.py, for meta.final_findings) and the DOCX/PDF download
    endpoint (server.py, after its own extra mandatory-issue/severity/
    guardrail post-processing) so "what the reviewer saw" and "what's in the
    downloaded file" are built by the same rule, not two independently
    maintained filters that can silently diverge in count and content."""
    out: list[ReviewIssue] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        sev = str(cr.get("risk_tier") or "LOW").upper()
        if sev not in ("HIGH", "MEDIUM", "LOW"):
            sev = "LOW"
        # Checklist items (is_checklist_item=True, e.g. isr_installation_defect)
        # flag a clause the contract is MISSING entirely — there is no quote to
        # show, by design, and the suggested new-clause text lives in
        # recommendation_text rather than suggested_rewrite/proposed_revision
        # (see clause_level.py's checklist injectors). Requiring a non-empty
        # original_text here silently dropped every such finding before it
        # ever reached the HIGH/MEDIUM buckets, which is what tripped the
        # REVIEW_FAILED collapse gate in server.py for contracts whose risk
        # was mostly missing-clause checklist items (e.g. project_installation).
        is_checklist = bool(cr.get("is_checklist_item"))
        ot = str(cr.get("original_text") or "").strip()
        if not ot and is_checklist:
            ot = "(해당 조항 없음 — 계약서에 신설 필요)"
        pr = str(
            cr.get("suggested_rewrite") or cr.get("proposed_revision") or cr.get("recommendation_text") or ""
        ).strip()
        pb = str(cr.get("rewrite_reason") or cr.get("problem") or "").strip()
        if not ot or not pb:
            continue
        detected = cr.get("detected_issue_list")
        issue_title = ""
        if isinstance(detected, list) and detected and isinstance(detected[0], dict):
            issue_title = str(detected[0].get("issue_title") or "").strip()
        if not issue_title:
            issue_title = pb[:120]
        out.append(ReviewIssue(
            clause_id=str(cr.get("clause_id") or ""),
            clause_title=str(cr.get("clause_title") or ""),
            severity=sev,  # type: ignore[arg-type]
            approval_required=bool(cr.get("approval_required")),
            issue_title=issue_title[:120],
            original_text=ot[:500],
            problem=pb[:400],
            legal_business_reason=str(cr.get("legal_business_reason") or pb)[:400],
            proposed_revision=pr[:600],
            negotiation_position=str(cr.get("negotiation_position") or cr.get("negotiation_strategy") or "").strip()[:300],
            confidence=float(cr.get("confidence") or 0.75),
            is_mandatory=bool(cr.get("is_mandatory_review_target") or cr.get("is_mandatory")),
            related_clause_ids=[str(r) for r in (cr.get("related_clauses") or []) if isinstance(r, str) and r][:6],
            article_number=str(cr.get("article_number") or "").strip(),
            paragraph_number=str(cr.get("paragraph_number") or "").strip(),
            item_number=str(cr.get("item_number") or "").strip(),
            display_path=str(cr.get("display_path") or "").strip(),
        ))
    return out


def build_final_findings(
    clause_results: list[dict[str, Any]],
    *,
    contract_type_code: str = "",
    include_low: bool = False,
) -> dict[str, Any]:
    """Canonical "what should the reviewer see as the final result" for a
    clause_results list — the single function both the initial review and
    the DOCX/PDF download endpoint call, so their counts and content can be
    directly compared (and must match)."""
    issues = clause_results_to_review_issues(clause_results)
    filtered = filter_issues(issues, contract_type_code=contract_type_code, include_low=include_low)
    return {
        "high_count": len(filtered["high"]),
        "medium_count": len(filtered["medium"]),
        "high_issues": [i.to_dict() for i in filtered["high"]],
        "medium_issues": [i.to_dict() for i in filtered["medium"]],
        "top_risks": [i.to_dict() for i in filtered["top_risks"]],
    }


def count_low_issues_in_output(raw_output: dict[str, Any]) -> int:
    """Count how many LOW-severity items appear in the raw bundle output.

    Used in tests to verify noise suppression.
    """
    count = 0
    clause_results = raw_output.get("clause_results", [])
    for cr in clause_results:
        if isinstance(cr, dict):
            rt = cr.get("risk_tier", "")
            if isinstance(rt, str) and rt.upper() == "LOW":
                count += 1
    return count


def has_placeholder_text(raw_output: dict[str, Any]) -> bool:
    """Return True if any placeholder text leaks into the output."""
    _MARKERS = {"제안 문안 없음", "사유 없음", "원문 핵심: -", "원문핵심: -"}
    import json
    text = json.dumps(raw_output, ensure_ascii=False)
    return any(m in text for m in _MARKERS)
