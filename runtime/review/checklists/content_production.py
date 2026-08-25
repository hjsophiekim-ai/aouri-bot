"""Mandatory checklist for content production / advertising content contracts.

Applies to: advertising_content_production, content_production_service, creative_agency_service

Key principle: Distinguish between
  ABSENT  — the clause does not exist in the contract
  PRESENT_BUT_WEAK — the clause exists but needs strengthening
  PRESENT_ACCEPTABLE — the clause is adequate (no issue generated)

This prevents the critical error of saying "검수 조항이 없어" when 제6조 검수 조항 is present.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChecklistStatus(Enum):
    ABSENT = "absent"
    PRESENT_BUT_WEAK = "present_but_weak"
    PRESENT_ACCEPTABLE = "present_acceptable"
    NOT_APPLICABLE = "not_applicable"


_CONTENT_TYPES = frozenset({
    "advertising_content_production",
    "content_production_service",
    "creative_agency_service",
})


@dataclass
class ContentCheckResult:
    checklist_id: str
    clause_ids: list[str]
    clause_titles: list[str]
    severity: str   # "HIGH", "MEDIUM", "LOW"
    issue_title: str
    original_text: str
    status: ChecklistStatus
    problem: str
    legal_business_reason: str
    proposed_revision: str
    negotiation_position: str = ""
    confidence: float = 0.90
    is_mandatory: bool = True

    def to_issue_dict(self) -> dict[str, Any]:
        """Convert to clause_result-compatible dict for downstream pipeline.

        clause_title: short clause reference e.g. "제9조" (for display)
        issue_title: the problem description (without [HIGH] prefix)
        """
        # Build a short clause label e.g. "제9조" or "제3조 제2항 및 제10조"
        _clause_label = " 및 ".join(self.clause_ids) if self.clause_ids else self.checklist_id
        # issue_title: problem description without severity prefix
        _issue_title = self.issue_title

        return {
            "clause_id": self.checklist_id,
            "clause_title": _clause_label,            # e.g. "제9조"
            "clause_ids": self.clause_ids,             # e.g. ["제9조"]
            "clause_titles": self.clause_titles,       # e.g. ["소유권의 귀속"]
            "related_clauses": self.clause_ids,        # for _build_review_issues
            "risk_tier": self.severity,
            "severity": self.severity,
            "approval_required": self.severity == "HIGH",
            "high_risk": self.severity == "HIGH",
            "must_fix": self.severity == "HIGH",
            "review_tier": "MUST" if self.severity == "HIGH" else "SUGGEST",
            "issue_title": _issue_title,               # e.g. "콘텐츠 권리 이전 및 사용권 범위 보완 필요"
            "original_text": self.original_text,
            "checklist_status": self.status.value,
            "problem": self.problem,
            "legal_business_reason": self.legal_business_reason,
            "suggested_rewrite": self.proposed_revision,
            "rewrite_reason": self.problem,
            "negotiation_position": self.negotiation_position,
            "confidence": self.confidence,
            "is_mandatory": True,
            "is_checklist_item": True,
            "mandatory_issue_id": self.checklist_id,
            "has_rewrite_change": True,
            "display_kind": "redline" if self.severity == "HIGH" else "guidance",
            "dedup_suppressed": False,
            "keep_as_is": False,
            "user_focus_hit": True,
        }


# ─── Pre-written revision texts ────────────────────────────────────────────────

_NEG_COUNTERPARTY = "상대방 반발 가능성이 있으나 법적 책임 범위 및 사용권 명확화 차원에서 협상 필요."

_REV_CP001_DELIVERABLES = (
    "을은 본 용역의 결과물로 최종 광고 콘텐츠 파일뿐 아니라, 갑이 사전에 요청한 경우 편집 가능한 원본 파일, "
    "프로젝트 파일, 자막 파일, 썸네일, 촬영 원본 중 합의된 항목을 [별지]에서 정한 형식과 기한에 따라 "
    "제출하여야 한다. 각 결과물의 해상도, 파일 형식, 분량, 버전, 사용 매체 및 납품 기한은 제작 견적서 "
    "또는 별도 산출물 명세서에 따른다."
)

_REV_CP002_INSPECTION = (
    "갑은 콘텐츠 수령일로부터 10영업일 이내에 검수 결과를 을에게 서면으로 통보한다. "
    "다만 콘텐츠의 분량, 매체 수, 수정 범위 또는 제3자 권리 확인 필요성 등을 고려하여 추가 검토가 "
    "필요한 경우 갑은 1회에 한하여 검수기간을 [10]영업일 연장할 수 있다. "
    "갑이 검수기간 내 보완을 요청한 경우 을은 무상으로 보완하여야 하며, 보완본에 대해서는 동일한 "
    "절차로 재검수를 진행한다. 중대한 하자, 제3자 권리 침해 우려 또는 갑의 브랜드 가이드라인 위반이 "
    "발견된 경우 갑은 검수 합격 이후에도 상당한 기간 내 보완을 요구할 수 있으며, 해당 하자가 해소될 "
    "때까지 관련 대금의 지급을 보류할 수 있다."
)

_REV_CP003_PAYMENT = (
    "을은 갑의 사전 서면 승인 없이 본 계약 및 제작 견적서의 범위를 초과하는 추가 과업을 수행하거나 "
    "그 비용을 청구할 수 없다. 추가 과업이 필요한 경우 을은 과업 범위, 산출물, 추가 비용, 납기 변경 "
    "여부를 기재한 변경요청서 또는 견적서를 갑에게 제출하고, 갑의 서면 승인을 받은 후에만 이를 수행할 "
    "수 있다. 갑은 검수 불합격 또는 보완 요청이 있는 경우 해당 부분에 관한 용역대금의 지급을 보류할 수 있다."
)

_REV_CP004_IP_TRANSFER = (
    "을은 본 계약에 따라 제작·납품한 콘텐츠 및 그 구성요소 중 을 또는 제3자의 기존 권리를 제외한 부분에 "
    "관한 저작재산권, 2차적저작물작성권, 편집·수정권, 복제권, 배포권, 전송권, 전시권 및 광고·홍보 목적의 "
    "이용권을 용역대금 완납과 동시에 갑에게 이전한다. 다만 용역대금 완납 전이라도 갑이 검수에 합격한 "
    "콘텐츠를 광고 집행, 내부 검토 또는 사전 홍보 목적으로 사용할 필요가 있는 경우 을은 갑에게 "
    "비독점적·무상 사용권을 부여한다. 갑은 콘텐츠를 홈페이지, SNS, 온라인 광고, 오프라인 매장, "
    "전시, 영업자료, 보도자료 및 기타 갑의 브랜드 홍보 매체에서 기간·지역의 제한 없이 사용할 수 있으며, "
    "필요한 범위에서 편집, 수정, 변형, 재가공할 수 있다.\n"
    "을이 본 용역 이전부터 보유하였거나 본 용역과 독립적으로 개발한 자료, 기술, 노하우를 콘텐츠에 "
    "포함하는 경우, 을은 해당 권리의 범위와 사용 제한 사항을 사전에 갑에게 서면 고지하여야 하며, "
    "갑의 콘텐츠 사용 목적 달성에 필요한 범위에서 기간·지역 제한 없는 무상 사용권을 갑에게 부여한다. "
    "을은 자신의 기존 권리를 이유로 갑의 콘텐츠 사용, 편집, 배포 또는 광고 집행을 제한할 수 없다."
)

_REV_CP005_THIRD_PARTY_IP = (
    "을은 콘텐츠 제작 과정에서 폰트, 이미지, 영상, 음원, 효과음, 스톡소스, 모델·출연자의 초상 및 성명, "
    "촬영 장소, AI 생성물 기타 제3자의 권리 또는 자료를 사용하는 경우, 해당 자료의 출처, 권리자, "
    "사용범위, 사용기간, 사용지역, 사용매체, 상업적 광고 사용 가능 여부 및 비용 부담 주체를 사전에 "
    "갑에게 서면으로 고지하고 갑의 승인을 받아야 한다. 을은 갑의 요청이 있는 경우 라이선스 계약서, "
    "사용허락서, 모델 릴리즈, 장소 사용동의서, 구매·사용 증빙 등 관련 자료를 제출하여야 한다. "
    "을은 위 권리 확보가 불충분하여 제3자의 이의제기, 사용중지 요청, 손해배상 청구 또는 광고 집행 "
    "중단이 발생하지 않도록 하여야 하며, 그러한 문제가 발생한 경우 자신의 비용과 책임으로 이를 "
    "해결하고 갑을 면책한다."
)

_REV_CP006_TERMINATION = (
    "본 계약이 해제 또는 해지되는 경우, 을은 해지 시점까지 제작한 콘텐츠, 시안, 촬영 원본, 편집 파일 등 "
    "갑이 요청하는 산출물을 지체 없이 갑에게 인도하여야 한다. "
    "갑 귀책으로 해지되는 경우 갑은 해지 시점까지 을이 실제 수행한 과업 중 갑이 승인한 부분에 한하여 "
    "합리적으로 산정된 대금을 지급한다. "
    "을 귀책으로 해지되는 경우 을은 갑이 이미 지급한 금액 중 미완성 또는 미승인 과업에 해당하는 금액을 "
    "반환하여야 하며, 갑이 인도받은 산출물을 사용하기 위해 필요한 권리를 무상으로 부여한다. "
    "해지로 인한 정산은 갑의 손해배상청구권에 영향을 미치지 않는다."
)

_REV_CP007_DAMAGES = (
    "을의 귀책사유로 인한 납기 지연, 콘텐츠 하자, 제3자 권리 침해, 비밀유지의무 위반, 갑 제공자료의 "
    "분실·훼손, 광고 집행 중단 또는 브랜드 이미지 훼손으로 갑에게 손해가 발생한 경우, 을은 갑에게 "
    "발생한 직접 손해, 제3자 청구 대응 비용, 합리적인 변호사 비용, 광고 중단·대체 제작 비용 등 "
    "상당인과관계 있는 손해를 배상한다. "
    "단, 손해배상 범위와 금액은 귀책사유, 손해 발생 경위, 위반의 중대성 및 손해 확대 방지 노력 등을 "
    "고려하여 정한다."
)

_REV_CP008_PORTFOLIO = (
    "을은 갑의 사전 서면 동의 없이 본 계약에 따라 제작된 콘텐츠, 시안, 촬영물, 작업 과정, 갑의 "
    "브랜드명·상표·제품명 또는 본 계약 수행 사실을 자신의 포트폴리오, 홈페이지, SNS, 보도자료, "
    "영업자료 또는 제3자 제안자료에 사용하거나 공개할 수 없다."
)


# ─── Pattern-based detection helpers ──────────────────────────────────────────

def _has_any(text: str, *patterns: str) -> bool:
    t = text.lower()
    return any(p.lower() in t for p in patterns)


def _find_clause_text(text: str, clause_nums: list[str]) -> str:
    """Extract original text snippet from specific clauses."""
    if not text:
        return ""
    lines = text.split("\n")
    result_lines: list[str] = []
    in_target = False
    targets = {f"제{n}조" for n in clause_nums}

    for line in lines:
        stripped = line.strip()
        is_new_clause = re.match(r"^제\d+조", stripped)
        if any(t in stripped for t in targets):
            in_target = True
        elif is_new_clause and in_target:
            break
        if in_target:
            result_lines.append(stripped)

    excerpt = " ".join(result_lines[:10])
    return excerpt[:300] if excerpt else ""


# ─── Individual checklist items ────────────────────────────────────────────────

def _check_cp001_deliverables(text: str) -> ContentCheckResult | None:
    """CP-001: 산출물 정의 및 제출 형식."""
    clause_text = _find_clause_text(text, ["2", "3"])

    # Check if deliverables are adequately defined
    has_file_format = _has_any(text, "원본 파일", "프로젝트 파일", "편집 가능", "파일 형식", "해상도")
    has_basic_deliverables = _has_any(text, "결과물", "산출물", "납품", "제출")
    has_견적서 = _has_any(text, "제작 견적서", "별첨")

    if not has_basic_deliverables:
        status = ChecklistStatus.ABSENT
        problem = "계약서에 산출물(결과물) 정의 및 제출 형식이 규정되어 있지 않습니다."
    elif has_file_format:
        return None  # PRESENT_ACCEPTABLE — skip
    elif has_견적서 and not has_file_format:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "산출물 납품 조항은 있으나, 편집 가능한 원본 파일, 프로젝트 파일, 자막 파일, 썸네일, "
            "촬영 원본 등 구체적인 파일 형식, 해상도, 버전 및 사용 매체 기준이 제작 견적서에만 "
            "의존하고 계약 본문에서 불명확합니다."
        )
    else:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = "산출물 정의가 있으나 구체적인 파일 형식, 해상도, 납품 기준이 불명확합니다."

    return ContentCheckResult(
        checklist_id="CP-001",
        clause_ids=["제2조", "제3조", "별첨 제작 견적서"],
        clause_titles=["용역의 범위", "콘텐츠 제작", "별첨 제작 견적서"],
        severity="MEDIUM",
        issue_title="제2조 및 제3조 — 산출물 정의 및 파일 제출 형식 보완 필요",
        original_text=clause_text or "[제2조/제3조] 용역의 범위 및 콘텐츠 제작 관련 조항",
        status=status,
        problem=problem,
        legal_business_reason=(
            "산출물 형식이 불명확하면 편집 원본, 촬영 소스, 2차 편집용 파일을 분쟁 없이 받기 어렵습니다. "
            "특히 향후 콘텐츠를 재편집하거나 다른 매체에 활용할 때 을에게 별도 비용을 요구받을 수 있습니다."
        ),
        proposed_revision=_REV_CP001_DELIVERABLES,
        negotiation_position=_NEG_COUNTERPARTY,
    )


def _check_cp002_inspection(text: str) -> ContentCheckResult | None:
    """CP-002: 검수 및 합격 간주 조항 — 검수 조항이 이미 있는지 반드시 확인."""
    clause_text = _find_clause_text(text, ["6", "7"])

    # Key: distinguish ABSENT from PRESENT_BUT_WEAK
    has_inspection_clause = _has_any(
        text, "검수", "합격", "불합격", "보완", "검수 결과"
    )
    has_deemed_acceptance = _has_any(
        text, "합격된 것으로 간주", "승인한 것으로 간주", "검수한 것으로 본다"
    )
    has_recheck = _has_any(text, "재검수", "보완본", "재제출")
    has_major_defect_handling = _has_any(text, "중대한 하자", "지급 보류", "검수 합격 이후에도")
    has_penalty_for_weak = _has_any(text, "보완 완료", "보완기간 연장", "검수 기간 연장")

    if not has_inspection_clause:
        status = ChecklistStatus.ABSENT
        problem = (
            "검수 조항이 없어 콘텐츠 합격 기준, 검수 기간, 보완 절차가 불명확합니다. "
            "검수 기준 및 지급 조건을 신설할 필요가 있습니다."
        )
    elif has_inspection_clause and has_deemed_acceptance and not has_major_defect_handling:
        # CRITICAL: must say "있으나" not "없어"
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "검수 조항은 있으나, 무응답 합격 간주 기간이 있고 재검수 횟수 제한, "
            "중대한 하자 발견 시 검수 철회 또는 지급 보류 규정이 없어 보완이 필요합니다."
        )
    elif has_inspection_clause and not has_recheck:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "검수 조항은 있으나, 보완 요청 후 재검수 절차 및 중대한 하자 처리 기준이 "
            "명확하지 않아 보완이 필요합니다."
        )
    else:
        return None  # PRESENT_ACCEPTABLE

    return ContentCheckResult(
        checklist_id="CP-002",
        clause_ids=["제6조", "제7조"],
        clause_titles=["콘텐츠의 제출 및 검수", "대금 지급"],
        severity="MEDIUM",
        issue_title="제6조 및 제7조 — 검수 간주 및 대금 지급 조건 보완 필요",
        original_text=clause_text or "[제6조] 콘텐츠의 제출 및 검수 관련 조항",
        status=status,
        problem=problem,
        legal_business_reason=(
            "무응답 합격 간주가 있으면 갑이 실수로 응답하지 못한 경우에도 하자 있는 콘텐츠가 "
            "합격 처리됩니다. 중대한 하자(IP 침해 우려 등) 발견 시 검수 합격 이후에도 "
            "대금 지급 보류 및 보완 요구 수단이 없으면 법적 분쟁이 어려워집니다."
        ),
        proposed_revision=_REV_CP002_INSPECTION,
        negotiation_position=_NEG_COUNTERPARTY,
    )


def _check_cp003_payment_additional(text: str) -> ContentCheckResult | None:
    """CP-003: 대금 지급 및 추가 과업 비용."""
    clause_text = _find_clause_text(text, ["7", "2"])

    has_additional_work_clause = _has_any(text, "추가 과업", "추가·변경", "추가 비용")
    has_written_approval = _has_any(text, "서면 승인", "서면으로 승인", "사전 서면")
    has_change_request = _has_any(text, "변경요청서", "견적서 제출", "사전 통보")
    has_payment_hold = _has_any(text, "지급을 보류", "대금 보류", "검수 불합격")

    if not has_additional_work_clause:
        status = ChecklistStatus.ABSENT
        problem = "추가 과업 발생 시 비용 처리 및 승인 절차 조항이 없습니다."
    elif has_additional_work_clause and not has_written_approval and not has_change_request:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "추가 과업 규정은 있으나, 갑의 사전 서면 승인, 변경요청서 제출, "
            "추가 비용 산정 기준이 명확하지 않아 분쟁 발생 시 입증이 어렵습니다. "
            "또한 검수 불합격 시 대금 지급 보류 수단이 명확하지 않습니다."
        )
    elif not has_payment_hold:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "추가 과업 승인 절차는 있으나, 검수 불합격 또는 보완 요청 중 "
            "대금 지급 보류 조항이 없어 하자 있는 결과물에 대한 대금 지급이 강제될 수 있습니다."
        )
    else:
        return None

    return ContentCheckResult(
        checklist_id="CP-003",
        clause_ids=["제2조 제2항", "제7조 제3항"],
        clause_titles=["용역의 범위(추가·변경)", "대금 지급(추가 과업)"],
        severity="MEDIUM",
        issue_title="제2조 제2항 및 제7조 제3항 — 추가 과업 및 비용 변경 절차 보완 필요",
        original_text=clause_text or "[제2조 제2항/제7조 제3항] 추가 과업 및 대금 관련 조항",
        status=status,
        problem=problem,
        legal_business_reason=(
            "추가 과업에 대한 서면 승인 없이 구두 지시로 진행하면 추가 비용 분쟁이 발생하며, "
            "을이 사후에 과도한 추가 비용을 청구할 수 있습니다. "
            "검수 불합격 시 대금 지급 보류 수단이 없으면 하자 있는 콘텐츠에 대해서도 대금 전액을 지급해야 합니다."
        ),
        proposed_revision=_REV_CP003_PAYMENT,
        negotiation_position=_NEG_COUNTERPARTY,
    )


def _check_cp004_ip_transfer(text: str) -> ContentCheckResult | None:
    """CP-004: 권리 이전 및 사용권 범위 — 핵심 리스크, TOP 5에 반드시 포함.

    Key: Only look for media scope WITHIN the IP/ownership clause (제9조 area),
    not in the entire contract (which may have "SNS" in the 별첨).
    """
    clause_text = _find_clause_text(text, ["9", "10"])
    # Search media scope only in Article 9/10 area (not in 별첨 etc.)
    ip_area = clause_text + " " + _find_clause_text(text, ["10"])

    has_ip_transfer = _has_any(text, "저작권", "소유권", "저작재산권", "권리 이전")
    # Media scope must appear in the IP clause area, not just anywhere in the contract
    has_media_scope_in_clause = _has_any(
        ip_area,
        "홈페이지", "SNS", "기간·지역", "전시", "영업자료", "매체",
    ) and _has_any(ip_area, "사용할 수 있", "이용할 수 있", "사용권")
    has_secondary_rights = _has_any(ip_area, "2차적저작물", "편집·수정권", "변형", "재가공")
    has_existing_exception = _has_any(text, "기존", "보유 자료", "노하우", "기존 권리")
    has_exception_unlimited = _has_any(ip_area, "사용권을 갑에게 부여", "기간·지역 제한 없는", "제한 없이 사용")

    # Check scope
    missing_scope: list[str] = []
    if not has_media_scope_in_clause:
        missing_scope.append("사용 매체·기간·지역 명시")
    if not has_secondary_rights:
        missing_scope.append("편집·변형·재가공·2차 저작물 허용")
    if has_existing_exception and not has_exception_unlimited:
        missing_scope.append("을의 기존 자료 예외에 대한 무제한 사용권 보장")

    if not has_ip_transfer:
        status = ChecklistStatus.ABSENT
        problem = "콘텐츠 저작권 및 지식재산권 이전 조항이 없습니다."
    elif missing_scope:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            f"소유권·저작권 이전 조항은 있으나, 다음 사항이 불명확합니다: {', '.join(missing_scope)}. "
            "사용 매체(홈페이지, SNS, 온라인 광고, 오프라인 매장, 전시, 영업자료 등), 기간, 지역이 없고, "
            "편집·변형·재가공 허용 여부도 불명확하며, "
            "대금 완납 전 사용권이 없어 광고 집행이 지연될 수 있습니다."
        )
    else:
        return None

    return ContentCheckResult(
        checklist_id="CP-004",
        clause_ids=["제9조"],
        clause_titles=["소유권의 귀속"],
        severity="HIGH",
        issue_title="제9조 — 콘텐츠 권리 이전 및 사용권 범위 보완 필요",
        original_text=clause_text or "[제9조] 소유권의 귀속 관련 조항",
        status=status,
        problem=problem,
        legal_business_reason=(
            "사용 매체·지역·기간이 불명확하면 SNS, 전시, 영업자료 등 새로운 매체에서 콘텐츠를 사용할 때 "
            "을에게 추가 사용료를 지급해야 하는 분쟁이 발생합니다. "
            "편집·변형·재가공 허용이 명확하지 않으면 마케팅 요구에 맞게 콘텐츠를 수정하는 데 제약이 생깁니다. "
            "대금 완납 전 사용권이 없으면 대금 분쟁 중 광고를 집행하지 못할 위험이 있습니다."
        ),
        proposed_revision=_REV_CP004_IP_TRANSFER,
        negotiation_position=_NEG_COUNTERPARTY,
        confidence=0.95,
    )


def _check_cp005_third_party_ip(text: str) -> ContentCheckResult | None:
    """CP-005: 제3자 권리·폰트·이미지·음원·초상권·AI 생성물."""
    clause_text = _find_clause_text(text, ["3", "10"])

    has_font_image = _has_any(text, "폰트", "이미지", "유상")
    has_third_party_ip = _has_any(text, "제3자의 저작권", "지식재산권", "권리 침해")
    has_music = _has_any(text, "음원", "효과음", "음향")
    has_portrait = _has_any(text, "초상권", "모델", "출연자")
    has_location = _has_any(text, "촬영 장소", "장소 사용", "로케이션")
    has_ai_content = _has_any(text, "ai 생성물", "ai생성", "인공지능 생성", "생성형 ai")
    has_license_evidence = _has_any(text, "라이선스 계약서", "사용허락서", "사용 증빙", "릴리즈")
    has_commercial_confirm = _has_any(text, "상업적", "광고 사용 가능", "매체 제한")

    # Check scope
    missing_items: list[str] = []
    if not has_music:
        missing_items.append("음원·효과음")
    if not has_portrait:
        missing_items.append("모델·출연자 초상권")
    if not has_location:
        missing_items.append("촬영 장소 사용 동의")
    if not has_ai_content:
        missing_items.append("AI 생성물 라이선스")
    if not has_license_evidence:
        missing_items.append("라이선스 증빙 제출 의무")
    if not has_commercial_confirm:
        missing_items.append("상업적 광고 사용 가능 여부 확인")

    if not has_font_image and not has_third_party_ip:
        status = ChecklistStatus.ABSENT
        problem = "제3자 권리(폰트·이미지·음원·초상권 등) 관련 조항이 없습니다."
    elif missing_items:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            f"제3자 자료 사용 보증 조항은 있으나, 다음 항목이 불명확합니다: {', '.join(missing_items)}. "
            "유상 폰트·이미지 이외에 음원, 영상소스, 모델 초상권, 촬영 장소, AI 생성물에 대한 "
            "라이선스 확인 및 증빙 제출 의무가 없어 갑이 광고 집행 중 제3자 권리 침해 위험에 노출됩니다."
        )
    else:
        return None

    return ContentCheckResult(
        checklist_id="CP-005",
        clause_ids=["제3조 제2항", "제10조"],
        clause_titles=["콘텐츠 제작(제3자 자료)", "지식재산권"],
        severity="HIGH",
        issue_title="제3조 제2항 및 제10조 — 제3자 권리·라이선스 증빙 보완 필요",
        original_text=clause_text or "[제3조 제2항/제10조] 제3자 자료 및 지식재산권 관련 조항",
        status=status,
        problem=problem,
        legal_business_reason=(
            "폰트·이미지에만 집중하고 음원, 모델 초상권, AI 생성물을 빠뜨리면 광고 집행 중 "
            "저작권자 또는 모델로부터 사용중지 가처분이나 손해배상 청구를 받을 수 있습니다. "
            "특히 상업적 광고 사용 가능 여부를 사전에 확인하지 않으면 계약 위반 및 "
            "광고 중단 손해를 부담해야 합니다."
        ),
        proposed_revision=_REV_CP005_THIRD_PARTY_IP,
        negotiation_position=_NEG_COUNTERPARTY,
        confidence=0.95,
    )


def _check_cp006_termination(text: str) -> ContentCheckResult | None:
    """CP-006: 해지 시 정산 및 중간 산출물 인도."""
    clause_text = _find_clause_text(text, ["12"])

    has_termination = _has_any(text, "해제", "해지", "계약의 해")
    has_settlement = _has_any(text, "정산", "비용 정산", "기성고")
    has_work_product_return = _has_any(text, "산출물", "시안", "촬영 원본", "인도")
    has_clear_basis = _has_any(text, "실제 수행", "합리적으로 산정", "비율", "기준")
    has_counterparty_refund = _has_any(text, "반환", "환급")

    if not has_termination:
        status = ChecklistStatus.ABSENT
        problem = "계약 해제·해지 관련 조항이 없습니다."
    elif has_termination and _has_any(text, "상호 협의한다", "협의하여 정한다") and not has_clear_basis:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "해지 조항은 있으나 정산 방법이 '상호 협의'에만 의존하고 구체적 기준이 없습니다. "
            "갑 귀책 해지 시 실수행 과업 산정 기준, 을 귀책 해지 시 대금 반환 범위, "
            "해지 시 중간 산출물(촬영 원본, 시안, 편집 파일 등) 인도 의무가 불명확합니다."
        )
    elif has_termination and not has_work_product_return:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "해지 시 정산 조항은 있으나, 을이 제작한 중간 산출물(촬영 원본, 시안, 편집 파일 등)을 "
            "갑에게 인도하는 의무가 명확하지 않습니다."
        )
    else:
        return None

    return ContentCheckResult(
        checklist_id="CP-006",
        clause_ids=["제12조 제3항"],
        clause_titles=["계약의 해제 및 해지(정산)"],
        severity="MEDIUM",
        issue_title="제12조 제3항 — 해지 시 정산 및 산출물 인도 기준 보완 필요",
        original_text=clause_text or "[제12조] 계약의 해제 및 해지 관련 조항",
        status=status,
        problem=problem,
        legal_business_reason=(
            "정산 기준이 없으면 해지 후 대금 반환 또는 추가 지급 금액을 두고 장기간 분쟁이 발생합니다. "
            "특히 촬영 완료 후 편집 미완성 단계에서 해지하면 갑이 촬영 원본을 받지 못하고 "
            "재제작 비용을 전액 부담해야 하는 상황이 생길 수 있습니다."
        ),
        proposed_revision=_REV_CP006_TERMINATION,
        negotiation_position=_NEG_COUNTERPARTY,
    )


def _check_cp007_damages(text: str) -> ContentCheckResult | None:
    """CP-007: 손해배상 및 책임 범위."""
    clause_text = _find_clause_text(text, ["14"])

    has_damages = _has_any(text, "손해배상", "손해")
    has_all_damages = _has_any(text, "모든 손해액", "전부 배상")
    has_ip_damages = _has_any(text, "지식재산권 침해", "저작권 침해")
    has_indirect = _has_any(text, "간접손해", "특별손해", "제3자 청구")
    has_lawyer_fees = _has_any(text, "변호사 비용", "소송 비용")
    has_ad_disruption = _has_any(text, "광고 집행 중단", "광고 중단", "브랜드")

    if not has_damages:
        status = ChecklistStatus.ABSENT
        problem = "손해배상 조항이 없습니다."
    elif has_all_damages and not has_indirect and not has_lawyer_fees:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "'모든 손해액' 배상 의무만 있고, 지식재산권 침해, 비밀유지 위반, 광고 집행 중단, "
            "브랜드 훼손으로 인한 손해배상의 범위(직접손해, 제3자 청구 대응 비용, 변호사 비용, "
            "광고 중단·대체 제작 비용)가 불명확합니다."
        )
    elif has_damages and not has_ip_damages:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "손해배상 조항은 있으나 지식재산권 침해로 인한 손해배상, "
            "제3자 청구 대응 비용, 광고 집행 중단 비용 등의 처리가 불명확합니다."
        )
    else:
        return None

    return ContentCheckResult(
        checklist_id="CP-007",
        clause_ids=["제14조"],
        clause_titles=["손해배상"],
        severity="MEDIUM",
        issue_title="제14조 — 손해배상 범위(IP 침해·광고중단·제3자 청구) 보완 필요",
        original_text=clause_text or "[제14조] 손해배상 관련 조항",
        status=status,
        problem=problem,
        legal_business_reason=(
            "콘텐츠 제작 계약에서 IP 침해가 발생하면 직접 손해 외에도 제3자 소송 대응 비용, "
            "광고 집행 중단 비용, 대체 제작 비용 등 상당한 간접 비용이 발생합니다. "
            "이를 명확히 규정하지 않으면 을이 '직접 손해'만 배상하면 된다고 주장할 수 있습니다."
        ),
        proposed_revision=_REV_CP007_DAMAGES,
        negotiation_position=_NEG_COUNTERPARTY,
    )


def _check_cp008_portfolio(text: str) -> ContentCheckResult | None:
    """CP-008: 포트폴리오·외부 공개 제한."""
    clause_text = _find_clause_text(text, ["11"])

    has_confidentiality = _has_any(text, "비밀유지", "비밀")
    has_portfolio_clause = _has_any(text, "포트폴리오", "홈페이지", "레퍼런스", "보도자료")
    has_portfolio_restrict = _has_any(text, "사전 서면 동의 없이", "사용하거나 공개할 수 없다")

    if has_portfolio_clause and has_portfolio_restrict:
        return None  # PRESENT_ACCEPTABLE

    if not has_confidentiality:
        status = ChecklistStatus.ABSENT
        problem = "비밀유지 조항이 없어 을이 계약 사실·콘텐츠를 자유롭게 공개할 수 있습니다."
    else:
        status = ChecklistStatus.PRESENT_BUT_WEAK
        problem = (
            "비밀유지 조항은 있으나 을이 제작물을 포트폴리오, 홈페이지, SNS, 보도자료에 "
            "공개할 수 있는지에 대한 금지·제한이 명확하지 않습니다. "
            "갑의 신제품 출시 전 비밀 유지 및 브랜드 관리에 문제가 생길 수 있습니다."
        )

    return ContentCheckResult(
        checklist_id="CP-008",
        clause_ids=["제11조"],
        clause_titles=["비밀유지"],
        severity="MEDIUM",
        issue_title="제11조 — 을의 포트폴리오·외부 공개 금지 조항 보완 필요",
        original_text=clause_text or "[제11조] 비밀유지 관련 조항",
        status=status,
        problem=problem,
        legal_business_reason=(
            "제품 출시 전 광고 콘텐츠가 을의 SNS나 포트폴리오로 유출되면 갑의 마케팅 계획이 "
            "훼손됩니다. 특히 신제품 launch 전략이 노출되면 경쟁사가 먼저 대응할 수 있습니다."
        ),
        proposed_revision=_REV_CP008_PORTFOLIO,
        negotiation_position=_NEG_COUNTERPARTY,
    )


# ─── Main runner ───────────────────────────────────────────────────────────────

def run_content_production_checklist(
    *,
    text: str,
    contract_type_code: str,
    entity: str = "",
    counterparty: str = "",
) -> list[ContentCheckResult]:
    """Run all content production checklist items and return issues found.

    Only runs for advertising_content_production / content_production_service.
    Returns results sorted by severity (HIGH first), then checklist order.
    """
    if contract_type_code not in _CONTENT_TYPES:
        # Also check for content signals in text
        has_content_signals = _has_any(
            text, "콘텐츠 제작", "광고 콘텐츠", "제품 광고", "시안", "촬영", "편집",
            "저작권 이전", "소유권의 귀속",
        )
        if not has_content_signals:
            return []

    checkers = [
        _check_cp004_ip_transfer,     # HIGH — TOP priority
        _check_cp005_third_party_ip,   # HIGH — TOP priority
        _check_cp002_inspection,       # MEDIUM — inspect clause specific
        _check_cp006_termination,      # MEDIUM
        _check_cp003_payment_additional,  # MEDIUM
        _check_cp007_damages,          # MEDIUM
        _check_cp001_deliverables,     # MEDIUM
        _check_cp008_portfolio,        # MEDIUM
    ]

    results: list[ContentCheckResult] = []
    for checker in checkers:
        try:
            result = checker(text)
            if result is not None:
                results.append(result)
        except Exception:
            pass

    return results
