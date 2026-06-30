"""Final findings builder: converts professional_assessment output into 6-section report.

6 sections:
  1. 계약구조 + 역할매트릭스
  2. 필수수정 조항
  3. 보완권장 조항
  4. 이미 반영된 핵심 안전장치
  5. 별첨/고객계약 양식 정합성 참고
  6. 제외/숨김처리 항목 요약
"""
from __future__ import annotations

from typing import Any


def build_six_section_report(assessment_result: dict[str, Any]) -> dict[str, Any]:
    """Convert run_professional_assessment() output to 6-section report dict."""
    role_matrix = assessment_result.get("role_matrix", {})
    must_fix = assessment_result.get("must_fix", [])
    partial = assessment_result.get("partial", [])
    already_reflected = assessment_result.get("already_reflected", [])
    customer_notes = assessment_result.get("customer_form_notes", [])
    excluded = assessment_result.get("excluded", [])

    return {
        "section_1_role_matrix": _build_section_1(role_matrix),
        "section_2_must_fix": _build_section_2(must_fix),
        "section_3_partial": _build_section_3(partial),
        "section_4_already_reflected": _build_section_4(already_reflected),
        "section_5_customer_form": _build_section_5(customer_notes),
        "section_6_excluded": _build_section_6(excluded),
        "summary": {
            "must_fix_count": len(must_fix),
            "partial_count": len(partial),
            "already_reflected_count": len(already_reflected),
            "excluded_count": len(excluded),
            "has_customer_form": bool(customer_notes),
        },
    }


def _build_section_1(role_matrix: dict) -> dict:
    is_confirmed = bool(role_matrix.get("role_matrix_confirmed"))
    conflicts = role_matrix.get("conflicts", [])
    return {
        "title": "계약구조 및 역할매트릭스",
        "role_matrix_confirmed": is_confirmed,
        "customer_contract_party": role_matrix.get("customer_contract_party", ""),
        "invoice_issuer": role_matrix.get("invoice_issuer", ""),
        "billing_party": role_matrix.get("billing_party", ""),
        "collection_role": role_matrix.get("collection_role", ""),
        "dealer_is_not_contract_party": role_matrix.get("dealer_is_not_contract_party", False),
        "conflicts": conflicts,
        "summary": (
            "계약 구조 확인됨: 공급업자-고객 직접 렌탈계약, 대리점은 위탁 용역자"
            if is_confirmed else
            "계약 구조 검토 필요: 역할 분리 명확화 권장"
        ),
    }


def _build_section_2(must_fix: list[dict]) -> dict:
    return {
        "title": "필수수정 조항",
        "count": len(must_fix),
        "findings": must_fix,
        "summary": (
            f"{len(must_fix)}건의 필수수정 조항이 확인되었습니다. 법무 승인 후 수정 필요."
            if must_fix else
            "필수수정 조항이 없습니다."
        ),
    }


def _build_section_3(partial: list[dict]) -> dict:
    return {
        "title": "보완 권장 조항",
        "count": len(partial),
        "findings": partial,
        "summary": (
            f"{len(partial)}건의 보완 권장 조항이 확인되었습니다."
            if partial else
            "보완 권장 조항이 없습니다."
        ),
    }


def _build_section_4(already_reflected: list[dict]) -> dict:
    return {
        "title": "이미 반영된 핵심 안전장치",
        "count": len(already_reflected),
        "findings": already_reflected,
        "summary": (
            f"{len(already_reflected)}개의 핵심 안전장치가 계약서에 이미 반영되어 있습니다."
            if already_reflected else
            "확인된 반영 항목이 없습니다."
        ),
    }


def _build_section_5(customer_notes: list[dict]) -> dict:
    return {
        "title": "별첨/고객계약 양식 정합성 참고",
        "has_customer_form": bool(customer_notes),
        "findings": customer_notes,
        "summary": (
            "별첨/고객 렌탈계약서 양식이 포함되어 있습니다. "
            "고객용 양식은 본 검토 범위 외이며 별도 법무 검토를 권장합니다."
            if customer_notes else
            "별첨/고객계약 양식이 확인되지 않았습니다."
        ),
    }


def _build_section_6(excluded: list[dict]) -> dict:
    rule_ids = [f.get("rule_id", "") for f in excluded]
    return {
        "title": "제외/숨김처리 항목 요약",
        "count": len(excluded),
        "excluded_rule_ids": rule_ids,
        "summary": (
            f"{len(excluded)}개 항목이 해당 계약에 적용되지 않아 제외되었습니다. "
            f"({', '.join(rule_ids)})"
            if excluded else
            "제외된 항목이 없습니다."
        ),
    }
