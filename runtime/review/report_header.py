"""리포트 섹션 1 "계약 구조 및 검토 결론" 공용 빌더 (2026-09-08 지시).

DOCX 와 PDF 가 각자 섹션 1 을 만들고 있었다. 그래서 DOCX 에는
`핵심 결론`·`미결 사항`·계약유형 한글 라벨·구조 요약 필드가 있는데
PDF 에는 없고, 제목마저 달랐다("계약 구조 및 검토 결론" vs
"계약 구조 및 우리 측 포지션"). 같은 검토 결과를 두 포맷으로 받은
사용자에게는 서로 다른 보고서로 보인다.

이 모듈이 섹션 1 의 **유일한 소스**다. `build_section1_rows()` 가 순서대로
행을 돌려주고, 렌더러는 그 행을 자기 포맷으로 그리기만 한다. 새 필드를
추가할 곳도 여기 한 곳이므로 두 포맷이 다시 어긋날 수 없다.

DOCX 를 기준으로 통일했다(사용자 지시) — 즉 PDF 가 DOCX 쪽으로 맞춰진다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.review.structure_summary_policy import render_rows as _structure_rows

SECTION1_TITLE = "1. 계약 구조 및 검토 결론"

#: our_legal_role 코드 → 한글 라벨. "미확정"을 그대로 노출하지 않는다.
_ROLE_LABELS: dict[str, str] = {
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

#: contract_type 코드 → 사람이 읽는 계약유형명.
_CONTRACT_TYPE_LABELS: dict[str, str] = {
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
    "nda_confidentiality": "비밀유지계약(NDA)",
}


@dataclass(frozen=True)
class HeaderRow:
    """렌더러가 그대로 그릴 수 있는 한 행."""

    text: str
    #: "plain" | "heading"(굵게) | "bullet"(들여쓴 목록 항목)
    kind: str = "plain"
    #: HIGH 색상으로 강조할지
    is_high_risk: bool = False
    #: MEDIUM 색상으로 강조할지 (핵심 결론의 MEDIUM 항목)
    is_medium_risk: bool = False


def contract_type_label(raw: Any) -> str:
    s = str(raw or "").strip()
    return _CONTRACT_TYPE_LABELS.get(s, s)


def our_role_label(raw: Any) -> str:
    s = str(raw or "").strip()
    label = _ROLE_LABELS.get(s, s)
    if label and label not in ("미확인", "미확정", ""):
        return label
    return "공급업자 (계약 내용 기반 판단)"


def _issue_attr(issue: Any, name: str) -> str:
    if isinstance(issue, dict):
        return str(issue.get(name) or "")
    return str(getattr(issue, name, "") or "")


def build_section1_rows(
    *,
    entity: str,
    contract_type: str,
    contract_type_code: str,
    filename: str | None,
    detailed_contract_profile: dict[str, Any] | None,
    high_issues: list[Any],
    medium_issues: list[Any],
    is_counterparty_form: bool = True,
    format_val=str,
) -> list[HeaderRow]:
    """섹션 1 의 모든 행을 DOCX 기준 순서로 반환한다.

    `format_val` 은 렌더러가 쓰는 값 정규화 함수(`_format_val`)를 넘긴다 —
    "미확정"/None 표기를 두 포맷이 동일하게 처리하도록 하기 위함이다.
    """
    dp = detailed_contract_profile or {}
    rows: list[HeaderRow] = []

    rows.append(HeaderRow(f"계약명: {filename or '미상'}"))
    rows.append(HeaderRow(f"우리 회사: {format_val(dp.get('our_party') or entity)}"))
    rows.append(HeaderRow(f"우리 측 지위: {our_role_label(format_val(dp.get('our_legal_role')))}"))
    rows.append(HeaderRow(f"상대방: {format_val(dp.get('counterparty'))}"))
    rows.append(HeaderRow(
        f"계약유형: {contract_type_label(format_val(dp.get('contract_type') or contract_type))}"
    ))

    # 계약유형별 구조 요약 필드 — NDA 에 세금계산서 주체 같은 stale 필드가
    # 나오지 않도록 structure_summary_policy 가 골라 준다(항목 4).
    struct_code = contract_type_code or str(dp.get("contract_type") or contract_type or "")
    for r in _structure_rows(struct_code, dp, include_missing=True):
        if r["key"] in ("our_party", "counterparty", "contract_type"):
            continue  # 위에서 이미 출력했다
        rows.append(HeaderRow(f"{r['label']}: {r['value']}", is_high_risk=bool(r["is_high_risk"])))

    conf = dp.get("confidence")
    if conf is not None:
        try:
            rows.append(HeaderRow(f"분석 신뢰도: {float(conf):.0%}"))
        except (TypeError, ValueError):
            pass

    rows.append(HeaderRow(
        "고객사(상대방) 양식 여부: "
        + ("고객사(상대방) 양식" if is_counterparty_form else "당사 표준 양식")
    ))

    approval_count = sum(1 for i in (high_issues or []) if _issue_attr(i, "approval_required") not in ("", "False", "0"))
    rows.append(HeaderRow(
        f"검토 결과: HIGH {len(high_issues or [])}건 | MEDIUM {len(medium_issues or [])}건"
        f" | 내부 승인 필요 {approval_count}건"
    ))

    # 핵심 결론 — TOP 5 섹션을 폐지한 대신, 첫 페이지에 HIGH 우선 최대 3건을
    # 한 줄 요약으로 압축해 "체결 전 반드시 봐야 할 것"을 바로 보여준다.
    source = list(high_issues or [])[:3]
    if len(source) < 3:
        source += list(medium_issues or [])[: 3 - len(source)]
    if source:
        rows.append(HeaderRow("핵심 결론:", kind="heading"))
        for i in source:
            sev = _issue_attr(i, "severity")
            rows.append(HeaderRow(
                f"- [{sev}] {_issue_attr(i, 'clause_title')} — {_issue_attr(i, 'issue_title')}",
                kind="bullet",
                is_high_risk=(sev == "HIGH"),
                is_medium_risk=(sev != "HIGH"),
            ))

    uq = dp.get("unresolved_questions") or []
    if isinstance(uq, list) and uq:
        rows.append(HeaderRow("미결 사항:", kind="heading"))
        for q in uq[:5]:
            rows.append(HeaderRow(f"- {q}", kind="bullet", is_high_risk=True))

    return rows
