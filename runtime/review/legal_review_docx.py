"""법무팀 검토용 DOCX 생성 — 변호사식 계약검토 형식 (v2).

구조 (변호사형 전체계약 판단 지시, 2026-08-31 — TOP 5 핵심 리스크 섹션 폐지,
HIGH 섹션과 중복되어 삭제):
  1. 계약 구조 및 검토 결론 (우리 측 지위·고객사 양식 여부·HIGH/MEDIUM 건수·핵심 결론 3줄)
  2. 필수수정 조항 — HIGH (빨간색)
  3. 권장수정 조항 — MEDIUM (주황색)
  4. 참고 조항 — LOW 부록 (파란색, include_low=True일 때만)
  5. 제외된 항목 요약

색상 기준:
  - HIGH / 필수수정: 빨간색 (FF0000)
  - MEDIUM / 권장수정: 주황색 (F28C28)
  - LOW / 참고: 파란색 (0070C0), 기본 숨김

금지 항목 (절대 출력 금지):
  - 제안 문안 없음 / 사유 없음 / 원문 핵심: - / 협상 전략 없음
  - 통합 관리 필요 / 대표 항의 수정안을 기준으로 통합 관리하십시오
  - 수탁자 / 위탁자 / 결과물 / 산출물 / 오픈소스 / 소스코드 / SLA (대리점 계약에서)
"""
from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Literal
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# ─── DOCX namespace constants ──────────────────────────────────────────────────
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("w", W_NS)

# ─── Color constants ───────────────────────────────────────────────────────────
COLOR_HIGH = "FF0000"    # RED
COLOR_MEDIUM = "F28C28"  # ORANGE
COLOR_LOW = "0070C0"     # BLUE
COLOR_DARK = "1F2937"    # Dark grey for headings
COLOR_LABEL = "374151"   # Medium grey

# ─── Placeholder markers ──────────────────────────────────────────────────────
_PLACEHOLDER_MARKERS: frozenset[str] = frozenset({
    "제안 문안 없음", "사유 없음", "원문 핵심: -", "원문핵심: -",
    "협상 전략 없음", "수정 문구 없음", "(없음)", "통합 관리 필요",
    "대표 항의 수정안을 기준으로 통합 관리하십시오",
    "(협상 전략 없음)",
})

# Dev-contract phrases forbidden in dealer/consignment revisions
_DEV_PHRASES: frozenset[str] = frozenset({
    "수탁자", "위탁자", "결과물", "산출물", "오픈소스",
    "무료 이미지", "라이선스 조건", "소스코드", "SLA",
    "개발 완료", "제3자 저작권·특허권 침해 보증",
    "소프트웨어 개발", "앱 개발", "유지보수 SLA",
})

_DEALER_TYPE_CODES: frozenset[str] = frozenset({
    "consignment_sales_agency", "direct_customer_sales_support",
    "dealer_agency", "distribution_resale", "dealer_rental_service_contract",
})


# ─── ReviewIssue dataclass ────────────────────────────────────────────────────

@dataclass
class ReviewIssue:
    """Structured issue with all required fields for DOCX output."""
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
    related_clauses: list[str] = field(default_factory=list)
    confidence: float = 0.75
    is_checklist_item: bool = False
    is_mandatory_target: bool = False

    @property
    def display_bucket(self) -> str:
        """UI display bucket: 필수수정 / 권장수정 / 참고.

        Mirrors output_filter.ReviewIssue.display_bucket so UI and DOCX counts agree.
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
            "related_clauses": list(self.related_clauses),
            "confidence": self.confidence,
            "is_checklist_item": self.is_checklist_item,
        }


# ─── Helper functions ─────────────────────────────────────────────────────────

def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _has_placeholder(text: str) -> bool:
    if not text or not text.strip():
        return True
    return any(m in text for m in _PLACEHOLDER_MARKERS)


def _has_dev_phrase(text: str) -> bool:
    return any(phrase in text for phrase in _DEV_PHRASES)


def _is_dealer_contract(contract_type_code: str) -> bool:
    return contract_type_code in _DEALER_TYPE_CODES


def _compose_display_title(clause_title: str, display_path: str) -> str:
    """Every HIGH/MEDIUM finding's title must show its real "제N조 제N항
    제N호" citation, not a bare rule id or a generic article-heading name
    (e.g. "손해배상책임", "상호협력", "시험성적서" — an article's own title,
    shared by every paragraph/item under it, says nothing about WHICH
    paragraph the finding is actually about).

    Some injectors (common_legal_risk.py, testing_service_rules.py) already
    bake the citation into `clause_title` at the source (so it reads
    "제6조 제4항 [...]"); detect that and don't double-prefix. Everything
    else — in particular the main per-clause item, whose clause_title is
    just the bare article-heading name — gets `display_path` prefixed here.
    """
    title = (clause_title or "").strip()
    disp = (display_path or "").strip()
    if not disp:
        return title
    if title.startswith("제"):
        return title
    return f"{disp} [{title}]" if title else disp


def _clean_text(text: str, max_len: int = 3000) -> str:
    """Remove XML markers and truncate."""
    t = re.sub(r"<[^>]+>", "", str(text or "")).strip()
    return t[:max_len]


def _safe_text(text: str) -> str:
    return _clean_text(text, max_len=3000)


# ─── XML element helpers ──────────────────────────────────────────────────────

def _p(parent: ET.Element) -> ET.Element:
    return ET.SubElement(parent, _w("p"))


def _r(parent: ET.Element, *, bold: bool = False, color: str | None = None,
        strike: bool = False, underline: bool = False, italic: bool = False) -> ET.Element:
    r = ET.SubElement(parent, _w("r"))
    if bold or color or strike or underline or italic:
        rpr = ET.SubElement(r, _w("rPr"))
        if bold:
            ET.SubElement(rpr, _w("b"))
        if italic:
            ET.SubElement(rpr, _w("i"))
        if underline:
            u = ET.SubElement(rpr, _w("u"))
            u.set(_w("val"), "single")
        if strike:
            ET.SubElement(rpr, _w("strike"))
        if color:
            c = ET.SubElement(rpr, _w("color"))
            c.set(_w("val"), color)
    return r


def _t(parent: ET.Element, text: str) -> ET.Element:
    t = ET.SubElement(parent, _w("t"))
    t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = _safe_text(text)[:2000]
    return t


def _blank(body: ET.Element) -> None:
    ET.SubElement(body, _w("p"))


def _heading1(body: ET.Element, text: str) -> None:
    """Section 1 heading — large, bold."""
    p = _p(body)
    run = _r(p, bold=True)
    t = ET.SubElement(run, _w("t"))
    t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = _safe_text(text)[:500]


def _para(body: ET.Element, text: str, *, color: str | None = None,
          bold: bool = False, indent: int = 0, italic: bool = False) -> None:
    p = _p(body)
    prefix = "  " * indent
    run = _r(p, bold=bold, color=color, italic=italic)
    _t(run, prefix + str(text or ""))


def _separator(body: ET.Element) -> None:
    _blank(body)


def _format_val(val: Any, fallback: str = "미확인") -> str:
    if val is None:
        return fallback
    s = str(val).strip()
    if not s or s in ("None", "null", ""):
        return fallback
    return s


def _severity_color(severity: str) -> str:
    s = (severity or "").upper()
    if s == "HIGH":
        return COLOR_HIGH
    if s == "MEDIUM":
        return COLOR_MEDIUM
    return COLOR_LOW


# ─── Issue filtering ──────────────────────────────────────────────────────────

def _is_valid_issue(
    cr: dict[str, Any],
    *,
    contract_type_code: str = "general",
) -> bool:
    """Check if a clause_result qualifies as a valid issue for output."""
    # Required non-empty fields
    ot = str(cr.get("original_text") or "").strip()
    problem = str(cr.get("rewrite_reason") or cr.get("problem") or "").strip()
    sr = str(cr.get("suggested_rewrite") or cr.get("proposed_revision") or "").strip()

    if not ot and not cr.get("is_mandatory"):
        return False
    if not problem:
        return False
    if not sr:
        return False

    # Placeholder check
    if _has_placeholder(sr) or _has_placeholder(problem):
        return False

    # Dev phrase check for dealer contracts
    if _is_dealer_contract(contract_type_code) and _has_dev_phrase(sr):
        logger.warning("Dev phrase in dealer revision for clause_id=%s", cr.get("clause_id"))
        return False

    return True


def _review_issue_from_dict(d: dict, *, is_counterparty_form: bool = True) -> ReviewIssue:
    """Convert an already-filtered issue dict (e.g. output_filter.
    build_final_findings()'s high_issues/medium_issues/top_risks) back into a
    ReviewIssue for rendering. Shared by build_legal_review_docx and
    build_legal_review_pdf so a caller that passes pre-filtered issues gets
    identical DOCX/PDF content from the exact same conversion rule."""
    sev = str(d.get("severity") or d.get("risk_tier") or "LOW").upper()
    if sev not in ("HIGH", "MEDIUM", "LOW"):
        sev = "LOW"
    neg = str(d.get("negotiation_position") or "").strip()
    if not neg or _has_placeholder(neg):
        from runtime.review.mandatory_issues import get_mandatory_negotiation_position
        neg = get_mandatory_negotiation_position(is_counterparty_form)
    return ReviewIssue(
        clause_id=str(d.get("clause_id") or ""),
        clause_title=_compose_display_title(str(d.get("clause_title") or ""), str(d.get("display_path") or "")),
        severity=sev,  # type: ignore[arg-type]
        approval_required=bool(d.get("approval_required")),
        issue_title=str(d.get("issue_title") or "")[:120],
        original_text=str(d.get("original_text") or "")[:500],
        problem=str(d.get("problem") or d.get("rewrite_reason") or "")[:400],
        legal_business_reason=str(d.get("legal_business_reason") or d.get("problem") or "")[:400],
        proposed_revision=str(d.get("proposed_revision") or d.get("suggested_rewrite") or "")[:800],
        negotiation_position=neg[:300],
        # output_filter.build_final_findings() emits "related_clause_ids"
        # (ReviewIssue.to_dict()'s key there); legal_review_docx.py's own
        # _build_review_issues() (used only when no pre-filtered lists are
        # supplied) emits "related_clauses" — accept either so a sibling
        # clause carrying the same defect (e.g. "제11조 제1항" alongside a
        # 제6조 finding) survives into the DOCX "함께 수정할 조항" line
        # regardless of which path produced this dict.
        related_clauses=[str(r) for r in (d.get("related_clause_ids") or d.get("related_clauses") or [])][:6],
        confidence=float(d.get("confidence") or 0.75),
    )


def _build_review_issues(
    clause_results: list[dict[str, Any]],
    *,
    contract_type_code: str = "general",
    is_counterparty_form: bool = True,
) -> list[ReviewIssue]:
    """Convert clause_results to ReviewIssue objects with validation."""
    from runtime.review.mandatory_issues import get_mandatory_negotiation_position
    fallback_neg = get_mandatory_negotiation_position(is_counterparty_form)

    issues: list[ReviewIssue] = []
    seen_issue_ids: set[str] = set()

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) and not cr.get("is_mandatory"):
            continue
        if bool(cr.get("keep_as_is")):
            continue

        sev = str(cr.get("risk_tier") or cr.get("severity") or "LOW").upper()
        if sev not in ("HIGH", "MEDIUM", "LOW"):
            sev = "LOW"

        ot = str(cr.get("original_text") or "").strip()
        sr = str(cr.get("suggested_rewrite") or cr.get("proposed_revision") or cr.get("recommendation_text") or "").strip()
        problem = str(cr.get("rewrite_reason") or cr.get("problem") or "").strip()
        lr = str(cr.get("legal_business_reason") or problem).strip()

        # Get negotiation position
        neg = str(cr.get("negotiation_position") or cr.get("negotiation_strategy") or "").strip()
        if not neg or _has_placeholder(neg):
            neg = fallback_neg

        # Validate
        if not sr or _has_placeholder(sr):
            if sev == "HIGH" and not cr.get("is_mandatory"):
                logger.error("HIGH issue clause_id=%s has no proposed_revision", cr.get("clause_id"))
            continue
        if not problem:
            continue
        if _is_dealer_contract(contract_type_code) and _has_dev_phrase(sr):
            continue

        # Get issue title
        detected = cr.get("detected_issue_list") or []
        issue_title = ""
        if isinstance(detected, list) and detected:
            first = detected[0]
            if isinstance(first, dict):
                issue_title = str(first.get("issue_title") or "").strip()
        if not issue_title:
            issue_title = str(cr.get("issue_title") or problem).strip()[:120]

        clause_id = str(cr.get("clause_id") or "")
        if clause_id in seen_issue_ids and not cr.get("is_mandatory"):
            continue
        seen_issue_ids.add(clause_id)

        # Support both "related_clauses" and "clause_ids" keys
        related = cr.get("related_clauses") or cr.get("clause_ids") or []
        if not isinstance(related, list):
            related = []

        ri = ReviewIssue(
            clause_id=clause_id,
            clause_title=_compose_display_title(
                str(cr.get("clause_title") or clause_id), str(cr.get("display_path") or "")
            ),
            severity=sev,  # type: ignore[arg-type]
            approval_required=bool(cr.get("approval_required")),
            issue_title=issue_title or problem[:80],
            original_text=ot[:500] if ot else f"[{cr.get('clause_title', '')}] 관련 조항",
            problem=problem[:400],
            legal_business_reason=lr[:400],
            proposed_revision=sr[:800],
            negotiation_position=neg[:300],
            related_clauses=[str(r) for r in related[:6]],
            confidence=float(cr.get("confidence") or 0.75),
            is_checklist_item=bool(cr.get("is_checklist_item")),
            is_mandatory_target=bool(cr.get("is_mandatory_review_target") or cr.get("is_mandatory")),
        )
        issues.append(ri)

    return issues


def _filter_and_sort_issues(
    issues: list[ReviewIssue],
    *,
    max_medium: int = 10,
    max_top_risks: int = 5,
    contract_type_code: str = "",
) -> dict[str, list[ReviewIssue]]:
    """Filter, deduplicate, and sort issues by severity.

    Priority order in TOP 5:
    1. CP-* (content production checklist) — clause-grounded, sorted by ID
    2. MI-* (mandatory dealer issues) — sorted by ID
    3. Other clause-grounded issues (have real clause_ids)
    4. Generic advisory issues (filtered OUT by default)
    """
    # isr_*/sppc_* hard gate for dealer contracts
    _DEALER_TYPES = frozenset({
        "consignment_sales_agency", "direct_customer_sales_support",
        "dealer_agency", "dealer_rental_service_contract",
    })
    _SUPPRESS = ("isr_", "sppc_", "pi_", "svc_")
    if contract_type_code in _DEALER_TYPES:
        from dataclasses import replace as _dc_replace
        issues = [
            _dc_replace(i, severity="LOW", approval_required=False)
            if any(i.clause_id.startswith(p) for p in _SUPPRESS)
            else i
            for i in issues
        ]

    # Clause_id prefixes that indicate generic advisory (non-clause-grounded) items
    _ADVISORY_ID_PREFIXES = ("svc_", "pi_", "sppc_", "isr_")

    # Also filter by title substrings for anything that slipped through
    _SVC_DEV_EXCLUDED_TITLES = frozenset({
        "선급금 보증 구조", "[권고] 선급금 보증 구조",
        "미완성 시 환수 조항", "[권고] 미완성 시 환수 조항",
        "일정 지연 대응 조항", "[권고] 일정 지연 대응 조항",
        "용역 종료 후 결과물 활용 범위", "[권고] 용역 종료 후 결과물 활용 범위",
        "검수 후 지급 구조", "[권고] 검수 후 지급 구조",
        "단계별 deliverable 정의", "[권고] 단계별 deliverable 정의",
        "검수 없는 대금 지급 구조 개선",
        "제조물 결함 책임 귀속", "설치 하자 책임 귀속",
        "사용자 안전 보호 조항", "경고문구·사용자 매뉴얼 제공 의무",
        "안전 인증 완료 보증", "리콜 절차 및 비용 부담",
        "PL보험 가입 의무", "제3자 손해 배상 책임",
        "유지보수 및 정기점검 의무", "하자 대응 SLA",
        "사고 발생 즉시 보고 의무", "결함 발견 시 시정 조치 의무",
    })

    _sev_rank = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

    def _is_advisory_item(i: ReviewIssue) -> bool:
        """Return True if issue is a generic advisory (not clause-grounded).

        Checklist items (is_checklist_item=True) are exempt: the UI always shows
        them as "누락 구조 탐지" cards, so hiding them here silently made the DOCX
        diverge from what the user already saw on screen (up to a completely
        empty DOCX for advisory/service contracts whose only findings are
        checklist items). For dealer/consignment contract types this exemption
        is a no-op — those clause_ids are already forced to LOW severity above
        and dropped via include_low=False.
        """
        if i.is_checklist_item:
            return False
        if any(i.clause_id.startswith(p) for p in _ADVISORY_ID_PREFIXES):
            return True
        if i.clause_title in _SVC_DEV_EXCLUDED_TITLES:
            return True
        if i.issue_title in _SVC_DEV_EXCLUDED_TITLES:
            return True
        # Detect "[권고]" prefix in clause_title or issue_title
        if str(i.clause_title).startswith("[권고]") or str(i.issue_title).startswith("[권고]"):
            return True
        return False

    # Separate by priority class
    cp_issues = [i for i in issues if i.clause_id.startswith("CP-")]  # content production
    mi_issues = [i for i in issues if i.clause_id.startswith("MI-")]  # mandatory dealer
    other_issues = [i for i in issues
                    if not i.clause_id.startswith("CP-")
                    and not i.clause_id.startswith("MI-")
                    and not _is_advisory_item(i)]

    # Deduplicate other_issues by issue_title
    seen_titles: dict[str, ReviewIssue] = {}
    for issue in other_issues:
        key = issue.issue_title.strip()[:100]
        if key not in seen_titles:
            seen_titles[key] = issue
        else:
            existing = seen_titles[key]
            if _sev_rank.get(issue.severity, 0) > _sev_rank.get(existing.severity, 0):
                seen_titles[key] = issue

    # Deduplicate CP and MI by clause_id
    seen_cp: dict[str, ReviewIssue] = {}
    for issue in cp_issues:
        if issue.clause_id not in seen_cp:
            seen_cp[issue.clause_id] = issue

    seen_mi: dict[str, ReviewIssue] = {}
    for issue in mi_issues:
        if issue.clause_id not in seen_mi:
            seen_mi[issue.clause_id] = issue

    # Combine: CP first (sorted), then MI (sorted), then others
    all_issues = (
        sorted(seen_cp.values(), key=lambda i: i.clause_id)
        + sorted(seen_mi.values(), key=lambda i: i.clause_id)
        + list(seen_titles.values())
    )

    high = [i for i in all_issues if i.severity == "HIGH"]
    medium_all = [i for i in all_issues if i.severity == "MEDIUM"]
    medium = [i for i in medium_all if i.is_mandatory_target] + [i for i in medium_all if not i.is_mandatory_target][:max_medium]
    low = [i for i in all_issues if i.severity == "LOW"]

    # Sort within HIGH/MEDIUM: CP first, then MI, then others by confidence
    def _sort_key(i: ReviewIssue) -> tuple:
        if i.clause_id.startswith("CP-"):
            return (0, i.clause_id, -i.confidence)
        if i.clause_id.startswith("MI-"):
            return (1, i.clause_id, -i.confidence)
        return (2, "", -i.confidence)

    high.sort(key=_sort_key)
    medium.sort(key=_sort_key)

    combined = high + medium
    top_risks = combined[:max_top_risks]

    return {
        "high": high,
        "medium": medium,
        "low": low,
        "top_risks": top_risks,
    }


# ─── DOCX builder ─────────────────────────────────────────────────────────────

def build_legal_review_docx(
    *,
    entity: str,
    contract_type: str,
    filename: str | None,
    clause_results: list[dict[str, Any]],
    original_clauses: list[dict[str, Any]] | None = None,
    detailed_contract_profile: dict[str, Any] | None = None,
    # Pre-filtered issues (if None, will be built from clause_results)
    top_risks_filtered: list[dict[str, Any]] | None = None,
    high_issues_filtered: list[dict[str, Any]] | None = None,
    medium_issues_filtered: list[dict[str, Any]] | None = None,
    include_low: bool = False,
    contract_type_code: str = "general",
    is_counterparty_form: bool = True,
    mandatory_review_targets: list[dict[str, Any]] | None = None,
    legal_applicability_review: list[dict[str, Any]] | None = None,
) -> bytes:
    """Generate a lawyer-grade contract review DOCX.

    Colors:
      HIGH = RED (FF0000)
      MEDIUM = ORANGE (F28C28)
      LOW = BLUE (0070C0), hidden by default
    """
    dp = detailed_contract_profile or {}

    # Build review issues from clause_results
    issues_raw = _build_review_issues(
        clause_results,
        contract_type_code=contract_type_code,
        is_counterparty_form=is_counterparty_form,
    )

    # If pre-filtered issues are provided, use them (converted back to ReviewIssue)
    if top_risks_filtered is not None and (high_issues_filtered is not None or medium_issues_filtered is not None):
        def _from_dict(d: dict) -> ReviewIssue:
            return _review_issue_from_dict(d, is_counterparty_form=is_counterparty_form)

        top_issues = [_from_dict(d) for d in (top_risks_filtered or []) if isinstance(d, dict)]
        high_issues = [_from_dict(d) for d in (high_issues_filtered or []) if isinstance(d, dict)]
        medium_issues = [_from_dict(d) for d in (medium_issues_filtered or []) if isinstance(d, dict)]
        low_issues: list[ReviewIssue] = []
    else:
        filtered = _filter_and_sort_issues(issues_raw, max_medium=10, max_top_risks=5, contract_type_code=contract_type_code)
        top_issues = filtered["top_risks"]
        high_issues = filtered["high"]
        medium_issues = filtered["medium"]
        low_issues = filtered["low"] if include_low else []

    excluded_count = max(0, len(issues_raw) - len(high_issues) - len(medium_issues))

    # ── Build DOCX XML ──────────────────────────────────────────────────────
    doc = ET.Element(_w("document"))
    body = ET.SubElement(doc, _w("body"))

    # ── Title ──────────────────────────────────────────────────────────────
    _heading1(body, "아우리봇 계약 검토·수정본 (법무팀 검토용)")
    _blank(body)

    # Legend
    _para(body, "표시 기준:", bold=True)
    _para(body, "- HIGH / 필수수정: 빨간색", color=COLOR_HIGH)
    _para(body, "- MEDIUM / 권장수정: 주황색", color=COLOR_MEDIUM)
    _para(body, "- LOW / 참고: 파란색, 기본 숨김", color=COLOR_LOW)
    _blank(body)

    # ── Section 0: 최초 요청사항 반영 여부 요약표 ───────────────────────────
    # review_focus에서 사용자가 직접 인용한 조항번호(예: "제5조 제2항 제1호")가
    # 최종 결과에서 누락되지 않았는지 한눈에 확인할 수 있는 표. 모든 항목이
    # 채워지지 않으면(즉 하나라도 미확인/누락이면) 정상 완료로 취급하지 않는다
    # — self_check.py의 REVIEW_FAILED_USER_REQUEST_MISSING 게이트가 이를 강제한다.
    if mandatory_review_targets:
        _heading1(body, "0. 최초 요청사항 반영 여부")
        _status_label = {
            "flagged": "검토완료 · 수정 필요",
            "checked_low_risk": "검토완료 · 낮은 위험(현행 유지 가능)",
            "checked_no_issue": "검토완료 · 특이사항 없음",
            "clause_not_found": "계약서에서 조항 확인 불가",
        }
        for t in mandatory_review_targets:
            if not isinstance(t, dict):
                continue
            disp = str(t.get("display_path") or t.get("raw_citation") or "")
            status = str(t.get("status") or "")
            sev = str(t.get("severity") or "")
            label = _status_label.get(status, status or "미확인")
            color = COLOR_HIGH if status == "clause_not_found" else (COLOR_LOW if status in ("checked_no_issue", "checked_low_risk") else None)
            p_row = _p(body)
            r_row = _r(p_row, bold=True, color=color)
            sev_suffix = f" [{sev}]" if sev else ""
            _t(r_row, f"- {disp}: {label}{sev_suffix}")
        _blank(body)
        _separator(body)

    # ── Section 1: 계약 구조 및 검토 결론 ────────────────────────────────────
    _heading1(body, "1. 계약 구조 및 검토 결론")

    _para(body, f"계약명: {filename or '미상'}")
    _para(body, f"우리 회사: {_format_val(dp.get('our_party') or entity)}")

    # our_legal_role — must NOT show "미확정"
    our_role = _format_val(dp.get("our_legal_role"))
    role_label_map = {
        "supplier": "공급업자",
        "buyer": "구매자/발주자",
        "contractor": "수급인",
        "ordering_party": "도급인/발주자",
        "도급인/발주자/콘텐츠 사용권자": "도급인/발주자/콘텐츠 사용권자",
        "rental_provider": "렌탈업자",
        "principal": "위탁자",
        "client": "의뢰인",
        "unknown": "미확인",
    }
    role_ko = role_label_map.get(our_role, our_role)
    if role_ko and role_ko not in ("미확인", "미확정"):
        _para(body, f"우리 측 지위: {role_ko}")
    else:
        _para(body, "우리 측 지위: 공급업자 (계약 내용 기반 판단)")

    _para(body, f"상대방: {_format_val(dp.get('counterparty'))}")

    _ct_label = _format_val(dp.get("contract_type") or contract_type)
    # Map code to human-readable
    _ct_map = {
        "advertising_content_production": "제품 광고 콘텐츠 제작 대행 계약",
        "content_production_service": "콘텐츠 제작 용역 계약",
        "creative_agency_service": "광고 대행 용역 계약",
        "consignment_sales_agency": "위탁판매 대리점 계약 / 고객 직접계약형 판매지원 구조",
        "direct_customer_sales_support": "위탁판매 대리점 계약 / 고객 직접계약형 판매지원 구조",
        "dealer_agency": "대리점 계약",
        "distribution_resale": "유통/재판매 계약",
        "software_app_development": "소프트웨어/앱 개발 계약",
        "advisory_service": "자문/용역 계약",
        "ai_search_marketing": "AI 검색·마케팅 서비스 계약",
        "purchase_supply": "물품 구매·공급 계약",
        "equipment_purchase_installation": "장비 구매·설치 계약",
        "rental": "렌탈·임대 계약",
        "construction": "건설·공사 계약",
    }
    ct_display = _ct_map.get(_ct_label, _ct_label)
    _para(body, f"계약유형: {ct_display}")

    # Customer contracting party
    ccp = _format_val(dp.get("customer_contracting_party"))
    if ccp == "needs_clarification_with_high_risk":
        _para(body, "고객 계약 당사자: 명시 필요 — 현재 조항 간 표현 충돌 (HIGH RISK)", color=COLOR_HIGH)
    elif ccp:
        _para(body, f"고객 계약 당사자: {ccp}")

    # Tax invoice issuer
    tii = _format_val(dp.get("tax_invoice_issuer"))
    if tii == "needs_clarification_with_high_risk":
        _para(body, "세금계산서 발행 주체: 명시 필요 — 현재 대리점이 발행 주체처럼 기재 (HIGH RISK)", color=COLOR_HIGH)
    elif tii:
        _para(body, f"세금계산서 발행 주체: {tii}")

    # Payment collection party
    pcp = _format_val(dp.get("payment_collection_party"))
    if pcp == "needs_clarification_with_high_risk":
        _para(body, "대금청구/수금 주체: 명시 필요 — 대리점의 지원업무와 법적 주체 구분 필요 (HIGH RISK)", color=COLOR_HIGH)
    elif pcp:
        _para(body, f"대금청구/수금 주체: {pcp}")

    agency = dp.get("agency_authority")
    if agency is None or str(agency).strip() in ("None", ""):
        _para(body, "대리점의 대리권: 명시 필요")
    elif agency is False or str(agency).lower() in ("false", "없음", "none"):
        _para(body, "대리점의 대리권: 없음 (또는 명시적 제한)")
    else:
        _para(body, f"대리점의 대리권: {agency}")

    conf = dp.get("confidence")
    if conf is not None:
        _para(body, f"분석 신뢰도: {float(conf):.0%}")

    _para(body, "고객사(상대방) 양식 여부: " + ("고객사(상대방) 양식" if is_counterparty_form else "당사 표준 양식"))

    _para(body, f"검토 결과: HIGH {len(high_issues)}건 | MEDIUM {len(medium_issues)}건 | 내부 승인 필요 {sum(1 for i in high_issues if i.approval_required)}건")

    # 핵심 결론 3줄 — 변호사형 전체계약 판단(2026-08-31 지시): TOP 5 섹션을
    # 별도로 두지 않는 대신, 첫 페이지 결론에 HIGH 우선 최대 3건을 한 줄
    # 요약으로 압축해 "체결 전 반드시 봐야 할 것"을 바로 보여준다.
    _conclusion_source = (high_issues or [])[:3]
    if len(_conclusion_source) < 3:
        _conclusion_source = _conclusion_source + (medium_issues or [])[: 3 - len(_conclusion_source)]
    if _conclusion_source:
        _para(body, "핵심 결론:", bold=True)
        for _ci in _conclusion_source:
            _cc = COLOR_HIGH if _ci.severity == "HIGH" else COLOR_MEDIUM
            _para(body, f"- [{_ci.severity}] {_ci.clause_title} — {_ci.issue_title}", color=_cc, indent=1)

    uq = dp.get("unresolved_questions") or []
    if isinstance(uq, list) and uq:
        _para(body, "미결 사항:", bold=True)
        for q in uq[:5]:
            _para(body, f"- {q}", color=COLOR_HIGH, indent=1)

    _blank(body)

    # dealer_rental: 6-section professional report format
    _is_dealer_rental_docx = (contract_type_code == "dealer_rental_service_contract")
    # TOP 5 핵심 리스크 섹션을 폐지했으므로(HIGH 섹션과 중복), 번호를 항상 1씩
    # 당긴다 — dealer_rental은 원래도 TOP 5를 건너뛰었으므로 동작 변화 없음.
    # 다만 사용자가 특정 법률의 적용 여부를 물어 [관련 법률 적용성] 섹션이
    # 생기는 경우(2026-09-02 지시)에는 그 섹션이 TOP 5가 있던 자리를 대신
    # 차지하므로 원래 번호 체계(HIGH=3, MEDIUM=4)를 유지한다.
    _has_legal_applicability = bool(legal_applicability_review) and not _is_dealer_rental_docx
    _sec_offset = 0 if _has_legal_applicability else -1

    if _is_dealer_rental_docx:
        # ── dealer_rental 전용: 섹션 2 = 역할매트릭스 ──────────────────────────
        _heading1(body, "2. 계약구조 및 역할매트릭스")
        # collect already_reflected items from clause_results
        _refl_items = [c for c in clause_results if
                       (isinstance(c, dict) and c.get("display_bucket") == "이미반영")
                       or (hasattr(c, "display_bucket") and getattr(c, "display_bucket", "") == "이미반영")]
        _refl_ids = [
            (c.get("rule_id") or c.get("clause_id") or "") if isinstance(c, dict)
            else (getattr(c, "rule_id", "") or getattr(c, "clause_id", ""))
            for c in _refl_items
        ]
        _role_confirmed = any(
            rid in ("DLR-RS-001", "DLR-RS-002") for rid in _refl_ids
        )
        if _role_confirmed:
            _para(body, "역할 분리 구조: 확인됨", bold=True, color=COLOR_LOW)
            _para(body, "- 고객 렌탈계약 당사자: 공급업자 (대리점은 계약 당사자 아님)", indent=1)
            _para(body, "- 세금계산서 발행 주체: 공급업자", indent=1)
            _para(body, "- 렌탈료 청구·수금 주체: 공급업자", indent=1)
        else:
            _para(body, "역할 분리 구조: 명확화 필요", bold=True, color=COLOR_HIGH)
            _para(body, "고객 계약 당사자 또는 세금계산서 발행 주체가 불명확합니다. DLR-RS-001/002 참조.", indent=1)
        _blank(body)
        _separator(body)

    # TOP 5 핵심 리스크 섹션은 폐지 — 바로 뒤 필수수정(HIGH) 섹션과 내용이
    # 사실상 중복되어 문서 가독성을 해쳤다(변호사형 전체계약 판단 지시,
    # 2026-08-31). `top_issues`는 더 이상 별도 섹션으로 렌더링하지 않는다.

    # ── Section 2: 관련 법률 적용성 검토 ────────────────────────────────────
    # 사용자가 review_focus에서 특정 법률(하도급법/공정거래법/건설산업
    # 기본법 등)의 적용 여부를 직접 물으면, rule hit·finding 개수와 무관하게
    # 그 법률 각각에 대한 독립 분석을 반드시 표로 출력한다(2026-09-02 지시).
    if _has_legal_applicability:
        _heading1(body, "2. 관련 법률 적용성 검토")
        for item in legal_applicability_review or []:
            if not isinstance(item, dict):
                continue
            statute = str(item.get("statute") or "")
            applicability = str(item.get("applicability") or "")
            reasoning = str(item.get("reasoning") or "")
            facts = [str(x) for x in (item.get("additional_facts_needed") or []) if isinstance(x, str)]
            clauses_ref = [str(x) for x in (item.get("related_clauses") or []) if isinstance(x, str)]
            risk = str(item.get("risk_level") or "")
            _color = COLOR_HIGH if risk == "HIGH" else (COLOR_MEDIUM if risk == "MEDIUM" else None)
            p_st = _p(body)
            r_st = _r(p_st, bold=True, color=_color)
            _t(r_st, f"■ {statute} — 적용 가능성: {applicability}" + (f" [{risk}]" if risk else ""))
            _para(body, f"판단 이유: {reasoning}", indent=1)
            if clauses_ref:
                _para(body, f"관련 조항: {', '.join(clauses_ref)}", indent=1)
            if facts:
                _para(body, "추가 확인 필요 사실관계:", indent=1)
                for f in facts:
                    _para(body, f"- {f}", indent=2)
            _blank(body)
        _separator(body)

    _separator(body)

    # ── Section 3(or 2): 필수수정 조항 (HIGH) ─────────────────────────────────
    _sec_high = str(3 + _sec_offset)
    p_h3 = _p(body)
    r_h3 = _r(p_h3, bold=True, color=COLOR_HIGH)
    _t(r_h3, f"{_sec_high}. 필수수정 조항 — HIGH")

    if not high_issues:
        _para(body, "HIGH 조항이 없습니다.", italic=True)
    else:
        for issue in high_issues:
            p_title = _p(body)
            r_title = _r(p_title, bold=True, color=COLOR_HIGH)
            _t(r_title, f"[HIGH] {issue.clause_title}")

            if issue.approval_required:
                _para(body, "★ 내부 법무 승인 필요", bold=True, color=COLOR_HIGH, indent=1)

            if issue.original_text and not issue.original_text.startswith("["):
                _para(body, f"원문: {issue.original_text[:300]}", indent=1)

            _para(body, f"문제점: {issue.problem[:350]}", indent=1)
            _para(body, f"법적/실무상 이유: {issue.legal_business_reason[:350]}", indent=1)

            if issue.proposed_revision:
                _para(body, "수정문안:", bold=True, color=COLOR_HIGH, indent=1)
                for line in issue.proposed_revision.splitlines()[:15]:
                    line = line.strip()
                    if line:
                        p_line = _p(body)
                        r_line = _r(p_line, color=COLOR_HIGH)
                        t_elem = ET.SubElement(r_line, _w("t"))
                        t_elem.set(f"{{{XML_NS}}}space", "preserve")
                        t_elem.text = "      " + _clean_text(line)[:250]
            else:
                logger.error("HIGH issue %s has no proposed_revision", issue.clause_id)

            neg = issue.negotiation_position
            if neg and not _has_placeholder(neg):
                _para(body, f"협상 포지션: {neg[:200]}", indent=1, italic=True)

            if issue.related_clauses:
                _para(body, f"함께 수정할 조항: {', '.join(issue.related_clauses[:6])}", indent=1)

            _blank(body)

    _separator(body)

    # ── Section 4(or 3): 권장수정 조항 (MEDIUM) ──────────────────────────────
    _sec_med = str(4 + _sec_offset)
    p_h4 = _p(body)
    r_h4 = _r(p_h4, bold=True, color=COLOR_MEDIUM)
    _t(r_h4, f"{_sec_med}. 권장수정 조항 — MEDIUM")

    if not medium_issues:
        _para(body, "권장 수정 조항이 없습니다.", italic=True)
    else:
        for issue in medium_issues[:10]:
            p_title = _p(body)
            r_title = _r(p_title, bold=True, color=COLOR_MEDIUM)
            _t(r_title, f"[MEDIUM] {issue.clause_title} — {issue.issue_title}")

            if issue.original_text and not issue.original_text.startswith("["):
                _para(body, f"원문: {issue.original_text[:200]}", indent=1)

            _para(body, f"문제점: {issue.problem[:300]}", indent=1)
            _para(body, f"수정방향: {issue.proposed_revision[:350]}", indent=1)

            neg = issue.negotiation_position
            if neg and not _has_placeholder(neg):
                _para(body, f"협상 포지션: {neg[:200]}", indent=1, italic=True)

            if issue.related_clauses:
                _para(body, f"함께 수정할 조항: {', '.join(issue.related_clauses[:4])}", indent=1)

            _blank(body)

    # ── Section 5(or 4): LOW 부록 (옵션) ─────────────────────────────────────
    _sec_low = str(5 + _sec_offset)
    if include_low:
        _separator(body)
        p_h5 = _p(body)
        r_h5 = _r(p_h5, bold=True, color=COLOR_LOW)
        _t(r_h5, f"{_sec_low}. 참고 조항 — LOW (사용자 요청 시만 표시)")
        if not low_issues:
            _para(body, "LOW 분류 항목이 없습니다.", color=COLOR_LOW)
        else:
            for issue in low_issues[:20]:
                p_li = _p(body)
                r_li = _r(p_li, color=COLOR_LOW)
                _t(r_li, f"[LOW] {issue.clause_title}: {issue.issue_title}")

    # ── dealer_rental 전용: 이미 반영된 핵심 안전장치 + 별첨참고 ────────────────
    if _is_dealer_rental_docx:
        _separator(body)
        _sec_refl = str(4 + _sec_offset)
        p_h_refl = _p(body)
        r_h_refl = _r(p_h_refl, bold=True, color=COLOR_LOW)
        _t(r_h_refl, f"{_sec_refl}. 이미 반영된 핵심 안전장치")
        # collect 이미반영 findings from clause_results
        _reflected_items = [
            c for c in clause_results
            if (isinstance(c, dict) and c.get("display_bucket") == "이미반영")
            or (hasattr(c, "display_bucket") and getattr(c, "display_bucket", "") == "이미반영")
        ]
        _customer_form_items = [
            c for c in clause_results
            if (isinstance(c, dict) and c.get("display_bucket") == "별첨참고")
            or (hasattr(c, "display_bucket") and getattr(c, "display_bucket", "") == "별첨참고")
        ]
        if not _reflected_items:
            _para(body, "이미 반영된 안전장치가 확인되지 않았습니다.", italic=True, color=COLOR_LOW)
        else:
            for _ri in _reflected_items:
                _ri_title = _ri.get("clause_title", "") if isinstance(_ri, dict) else getattr(_ri, "clause_title", "")
                _ri_text = _ri.get("current_assessment_text", "") if isinstance(_ri, dict) else ""
                p_ri = _p(body)
                r_ri = _r(p_ri, bold=True, color=COLOR_LOW)
                _t(r_ri, f"[반영됨] {_ri_title}")
                if _ri_text:
                    _para(body, _ri_text[:350], indent=1, color=COLOR_LOW)
                _blank(body)

        if _customer_form_items:
            _separator(body)
            _sec_cf = str(5 + _sec_offset)
            p_h_cf = _p(body)
            r_h_cf = _r(p_h_cf, bold=True)
            _t(r_h_cf, f"{_sec_cf}. 별첨/고객계약 양식 정합성 참고")
            for _cfi in _customer_form_items:
                _cfi_text = _cfi.get("current_assessment_text", "") if isinstance(_cfi, dict) else ""
                _para(body, _cfi_text[:400] if _cfi_text else "고객 렌탈계약서 양식 — 별도 법무 검토 권장", indent=1)
            _blank(body)

    # ── Section (5 or 4 or 6): 제외된 항목 요약 ──────────────────────────────────────
    _separator(body)
    _sec_excl_base = 5 if not include_low else 6
    if _is_dealer_rental_docx:
        # After: 2=역할매트릭스, 3=필수수정, 4=이미반영, (+5=별첨참고 if exists), then 제외
        _has_cform = any(
            (isinstance(c, dict) and c.get("display_bucket") == "별첨참고")
            for c in clause_results
        )
        _sec_excl_base = 6 if _has_cform else 5
    _sec_excl = str(_sec_excl_base + _sec_offset)
    _heading1(body, f"{_sec_excl}. 제외된 항목 요약")
    if excluded_count > 0:
        _para(body, (
            f"계약유형과 무관하거나 수정문안이 없는 일반론적 의견 {excluded_count}건은 "
            "본문에서 제외하였습니다. "
            "(include_low=True 옵션 사용 시 LOW 항목을 부록으로 확인할 수 있습니다.)"
        ))
    else:
        _para(body, "제외된 항목: 없음")

    _blank(body)
    ET.SubElement(body, _w("sectPr"))

    # ── Build DOCX zip ──────────────────────────────────────────────────────
    document_xml = ET.tostring(doc, encoding="utf-8", xml_declaration=True)

    types_root = ET.Element(f"{{{PKG_TYPES_NS}}}Types")
    d1 = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Default")
    d1.set("Extension", "rels")
    d1.set("ContentType", "application/vnd.openxmlformats-package.relationships+xml")
    d2 = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Default")
    d2.set("Extension", "xml")
    d2.set("ContentType", "application/xml")
    ov = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Override")
    ov.set("PartName", "/word/document.xml")
    ov.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    content_types = ET.tostring(types_root, encoding="utf-8", xml_declaration=True)

    rels_root = ET.Element(f"{{{REL_NS}}}Relationships")
    rel = ET.SubElement(rels_root, f"{{{REL_NS}}}Relationship")
    rel.set("Id", "rId1")
    rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument")
    rel.set("Target", "word/document.xml")
    rels = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)

    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document_xml)
    return buf.getvalue()
