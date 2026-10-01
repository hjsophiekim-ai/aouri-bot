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
    "광고주(매체 이용자)": "광고주(매체 이용자)",
    "rental_provider": "렌탈업자",
    "principal": "위탁자",
    "client": "의뢰인",
    "unknown": "미확인",
}

#: contract_type 코드 → 사람이 읽는 계약유형명.
_CONTRACT_TYPE_LABELS: dict[str, str] = {
    "advertising_content_production": "제품 광고 콘텐츠 제작 대행 계약",
    "advertising_media_placement": "광고매체 집행 계약 (상대방은 송출·게재만 수행)",
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
    canonical_state: dict[str, Any] | None = None,
) -> list[HeaderRow]:
    """섹션 1 의 모든 행을 DOCX 기준 순서로 반환한다.

    `format_val` 은 렌더러가 쓰는 값 정규화 함수(`_format_val`)를 넘긴다 —
    "미확정"/None 표기를 두 포맷이 동일하게 처리하도록 하기 위함이다.

    `canonical_state` 가 있으면 계약유형·당사자 지위는 **거기서만** 읽는다
    (2026-09-09 3차 지시 1항). 전에는 detailed_contract_profile 에서 읽어서,
    본문 법률분석이 쓰는 값과 달라질 수 있었다 — 실측에서 상단은 "장비 구매·설치
    계약", 본문은 "공사도급계약"이었다.
    """
    dp = detailed_contract_profile or {}
    cs = canonical_state or {}
    rows: list[HeaderRow] = []

    rows.append(HeaderRow(f"계약명: {filename or '미상'}"))
    # 우리 회사는 **법인** 기준으로 적고 브랜드는 보조 표기로 둔다(2026-09-29
    # Entity Resolution 지시 6항) — "우리 회사: 알로소" 가 나가면 권리·의무의
    # 귀속 주체를 브랜드로 읽게 된다.
    _our_legal = str(cs.get("our_legal_entity") or "").strip()
    _our_brand = str(cs.get("our_brand") or "").strip()
    if _our_legal:
        rows.append(HeaderRow(
            f"우리 회사: {_our_legal}" + (f" (브랜드: {_our_brand})" if _our_brand else "")
        ))
    else:
        rows.append(HeaderRow(f"우리 회사: {format_val(dp.get('our_party') or entity)}"))
    _our_role = str(cs.get("party_label") or "").strip() or our_role_label(
        format_val(dp.get("our_legal_role")))
    rows.append(HeaderRow(f"우리 측 지위: {_our_role}"))
    _gt = cs.get("governing_transaction") if isinstance(cs.get("governing_transaction"), dict) else {}
    # 임직원 비밀유지계약 — 사업자 간 NDA 의 구조 필드(Background/Foreground IP,
    # 허용 수령자, 개인정보 처리 '별도 계약')는 이 계약에 성립하지 않는다
    # (2026-09-28 실측: 직원 서약서 리포트 상단에 그대로 나갔다).
    _employee_nda = str(_gt.get("subtype") or "") == "employee_nda"
    _counterparty = format_val(dp.get("counterparty"))
    if _employee_nda and str(_counterparty or "").strip() in ("", "상대방", "미확정", "미상"):
        _counterparty = str(cs.get("counterparty_label") or "") or _counterparty
    rows.append(HeaderRow(f"상대방: {_counterparty}"))
    _type_label = str(cs.get("contract_type_label") or "").strip() or contract_type_label(
        format_val(dp.get("contract_type") or contract_type))
    rows.append(HeaderRow(f"계약유형: {_type_label}"))
    # 복합계약은 단일 유형으로 억지 분류하지 않는다(2026-09-30 지시 1항) — 실제
    # 거래의 성격과 구성요소를 함께 적는다. 규칙·법률 적용은 위 canonical 유형이 정한다.
    _primary = str(cs.get("primary_contract_type") or "").strip()
    _elements = [str(x) for x in (cs.get("secondary_contract_elements") or []) if str(x).strip()]
    if _primary and _elements:
        rows.append(HeaderRow(f"계약 성격: {_primary} (구성요소: {'·'.join(_elements)})"))
    _counterparty_role = str(cs.get("counterparty_label") or "").strip()
    if _counterparty_role:
        rows.append(HeaderRow(f"상대방 지위: {_counterparty_role}"))

    # 계약유형별 구조 요약 필드 — NDA 에 세금계산서 주체 같은 stale 필드가
    # 나오지 않도록 structure_summary_policy 가 골라 준다(항목 4).
    struct_code = (
        str(cs.get("contract_type") or "").strip()
        or contract_type_code
        or str(dp.get("contract_type") or contract_type or "")
    )
    if _employee_nda:
        from runtime.review.employee_nda_model import PD_LABELS as _PD_LABELS

        _rel = {"employer_employee": "사용자(회사) – 직원(고용관계)"}.get(
            str(_gt.get("relationship") or ""), str(_gt.get("relationship") or "")
        )
        if _rel:
            rows.append(HeaderRow(f"당사자 관계: {_rel}"))
        rows.append(HeaderRow(f"준거법: {_gt.get('governing_law') or '미기재 — 근무지 관할 확인 필요'}"))
        _pd = _PD_LABELS.get(str(_gt.get("personal_data_structure") or ""), "")
        if _pd:
            rows.append(HeaderRow(f"개인정보 취급 구조: {_pd}"))
    else:
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

    # 직원 서약서는 사용자(회사)가 직원에게 받는 문서다 — 상대방 양식이 아니다.
    rows.append(HeaderRow(
        "고객사(상대방) 양식 여부: "
        + ("당사 양식(사용자가 직원에게 받는 서약서)" if _employee_nda
           else ("고객사(상대방) 양식" if is_counterparty_form else "당사 표준 양식"))
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
