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

def deduplicate_issues(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    """Merge issues with the same issue_title into the highest-severity representative.

    Related clause IDs are accumulated into the representative's `related_clause_ids`.
    """
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
                )
            else:
                # Add new clause_id to existing's related list
                existing.related_clause_ids.append(issue.clause_id)

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
    # Step 1: quality gate
    valid = [i for i in issues if is_valid_issue(i, contract_type_code=contract_type_code)]

    # Step 2: deduplicate
    valid = deduplicate_issues(valid)

    # Step 3: split by severity
    high = [i for i in valid if i.severity == "HIGH"]
    medium = [i for i in valid if i.severity == "MEDIUM"][:max_medium]
    low = [i for i in valid if i.severity == "LOW"] if include_low else []

    # Step 4: top risks (HIGH first, then MEDIUM, sorted by confidence)
    _SEV_KEY = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    combined = sorted(
        high + medium,
        key=lambda x: (_SEV_KEY.get(x.severity, 0), x.confidence),
        reverse=True,
    )
    top_risks = combined[:max_top_risks]

    return {
        "high": high,
        "medium": medium,
        "low": low,
        "top_risks": top_risks,
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
