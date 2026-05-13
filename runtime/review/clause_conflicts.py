"""Clause-Level Conflict Check — requirement.md > Clause-Level Conflict Check
손해배상·면책·하자보수·제조물책임 조항 간 논리적 모순을 감지하고 통합 Draft를 생성한다.
"""
from __future__ import annotations

import re
from typing import Any

_LIABILITY_LIMIT_KW = re.compile(
    r"직접\s*손해|손해.{0,15}(한정|제한|총액|이내)|배상\s*범위.{0,15}(한정|제한)|"
    r"손해배상.{0,20}(총액|상한|한도|초과하지)",
    re.IGNORECASE,
)
_LIABILITY_UNLIMITED_KW = re.compile(
    r"무제한|제한\s*없|한도\s*없|전액\s*배상|모든\s*손해|일체의\s*손해",
    re.IGNORECASE,
)
_TERMINATION_IMMEDIATE_KW = re.compile(
    r"즉시\s*해지|즉각\s*해지|즉시\s*해제|사전\s*통보\s*없이",
    re.IGNORECASE,
)
_TERMINATION_NOTICE_KW = re.compile(
    r"(\d+)일.{0,10}(전|이상).{0,10}(서면|통보|통지|최고)|"
    r"사전\s*(통보|통지|최고).{0,20}(해지|해제)",
    re.IGNORECASE,
)
_WARRANTY_PERIOD_KW = re.compile(
    r"하자\s*담보.{0,20}(\d+)\s*(년|개월|일)|하자\s*보수\s*기간.{0,15}(\d+)",
    re.IGNORECASE,
)
_PL_PERIOD_KW = re.compile(
    r"(제조물|PL).{0,20}(책임|보험).{0,20}(\d+)\s*(년|개월|일)",
    re.IGNORECASE,
)
_INDEMNITY_CAP_KW = re.compile(
    r"배상.{0,10}(한도|상한|총액).{0,30}(원|만원|천만|억)",
    re.IGNORECASE,
)


def detect_clause_conflicts(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """requirement.md > Clause-Level Conflict Check.
    조항 간 논리적 모순을 4가지 유형으로 감지하고 통합 수정 Draft를 반환한다.
    """
    conflicts: list[dict[str, Any]] = []
    _check_liability_scope_conflict(clause_results, conflicts)
    _check_termination_notice_conflict(clause_results, conflicts)
    _check_warranty_pl_overlap(clause_results, conflicts)
    _check_indemnity_cap_conflict(clause_results, conflicts)
    return conflicts


def _check_liability_scope_conflict(
    clause_results: list[dict[str, Any]],
    out: list[dict[str, Any]],
) -> None:
    limited: list[dict[str, Any]] = []
    unlimited: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
            continue
        text = str(cr.get("original_text") or "")
        if _LIABILITY_LIMIT_KW.search(text):
            limited.append(cr)
        if _LIABILITY_UNLIMITED_KW.search(text):
            unlimited.append(cr)
    if not (limited and unlimited):
        return
    ids = [str(cr.get("clause_id") or "") for cr in limited + unlimited]
    a_limit = str(limited[0].get("article_number") or "?")
    a_unlim = str(unlimited[0].get("article_number") or "?")
    out.append({
        "conflict_type": "liability_scope_conflict",
        "clause_ids": ids,
        "description": (
            f"제{a_limit}조는 손해배상을 직접 손해로 한정하나, "
            f"제{a_unlim}조에서는 무제한 책임 구조가 존재하여 충돌합니다."
        ),
        "severity": "HIGH",
        "resolution_draft": (
            "[통합 수정 Draft — 손해배상 범위 통일]\n"
            "손해배상 범위는 원칙적으로 직접 손해로 한정한다. "
            "단, 고의·중과실, 지식재산권 침해, 비밀유지 위반의 경우에는 "
            "위 한도의 제한을 받지 아니하며 실제 손해 전액을 배상한다."
        ),
    })


def _check_termination_notice_conflict(
    clause_results: list[dict[str, Any]],
    out: list[dict[str, Any]],
) -> None:
    immediate: list[dict[str, Any]] = []
    with_notice: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
            continue
        text = str(cr.get("original_text") or "")
        if _TERMINATION_IMMEDIATE_KW.search(text):
            immediate.append(cr)
        if _TERMINATION_NOTICE_KW.search(text):
            with_notice.append(cr)
    if not (immediate and with_notice):
        return
    ids = [str(cr.get("clause_id") or "") for cr in immediate + with_notice]
    out.append({
        "conflict_type": "termination_notice_conflict",
        "clause_ids": ids,
        "description": (
            "일부 조항은 즉시 해지를 허용하고, 다른 조항은 사전 서면 통보를 요구하여 "
            "해지 절차가 상충됩니다."
        ),
        "severity": "HIGH",
        "resolution_draft": (
            "[통합 수정 Draft — 해지 절차 통일]\n"
            "계약 해지는 원칙적으로 서면 최고 및 30일 이상의 시정 기간 부여를 전제로 한다. "
            "다만, 중대한 법령 위반, 신뢰관계 본질적 파괴, 반복 위반의 경우에는 "
            "예외적으로 즉시 해지를 허용하며, 해당 사유를 계약서에 열거한다."
        ),
    })


def _check_warranty_pl_overlap(
    clause_results: list[dict[str, Any]],
    out: list[dict[str, Any]],
) -> None:
    warranty: list[dict[str, Any]] = []
    pl: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
            continue
        text = str(cr.get("original_text") or "")
        if _WARRANTY_PERIOD_KW.search(text):
            warranty.append(cr)
        if _PL_PERIOD_KW.search(text):
            pl.append(cr)
    if not (warranty and pl):
        return
    ids = [str(cr.get("clause_id") or "") for cr in warranty + pl]
    out.append({
        "conflict_type": "warranty_pl_overlap",
        "clause_ids": ids,
        "description": (
            "하자담보책임(민법상) 기간과 제조물 책임(PL법상) 기간이 중복·상충되어 "
            "책임 범위가 불명확합니다."
        ),
        "severity": "MEDIUM",
        "resolution_draft": (
            "[통합 수정 Draft — 하자담보책임 vs PL책임 분리]\n"
            "하자담보책임(민법 제580조)과 제조물 책임(제조물책임법 제3조)은 별도 조항으로 분리하여 규정한다. "
            "각 책임의 기간·범위·입증 책임·면책 요건을 명확히 구분한다."
        ),
    })


def _check_indemnity_cap_conflict(
    clause_results: list[dict[str, Any]],
    out: list[dict[str, Any]],
) -> None:
    cap_items: list[tuple[dict[str, Any], str]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
            continue
        text = str(cr.get("original_text") or "")
        m = _INDEMNITY_CAP_KW.search(text)
        if m:
            cap_items.append((cr, m.group(0)))
    if len(cap_items) < 2:
        return
    ids = [str(cr.get("clause_id") or "") for cr, _ in cap_items]
    cap_desc = " vs ".join(cap for _, cap in cap_items[:2])
    out.append({
        "conflict_type": "indemnity_cap_conflict",
        "clause_ids": ids,
        "description": (
            f"배상 한도가 조항마다 다르게 설정되어 있어 충돌합니다: {cap_desc}"
        ),
        "severity": "MEDIUM",
        "resolution_draft": (
            "[통합 수정 Draft — 배상 한도 단일화]\n"
            "배상 한도는 계약서 내 단일 조항에서 통합하여 규정하며, "
            "예외 사유(고의·중과실, IP 침해, 비밀유지 위반)에 대해서는 한도를 적용하지 않는다고 명시한다."
        ),
    })
