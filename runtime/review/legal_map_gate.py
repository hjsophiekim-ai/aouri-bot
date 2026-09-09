"""Contract Legal Map 완결성 게이트 (2026-09-09 지시 항목 1).

"이 map 이 확정되지 않으면 조항별 검토를 시작하지 마세요."

Legal Map 은 이미 생성되고 있었지만 **게이트가 아니었다** — 절반이 비어 있어도
조항별 finding 이 그대로 만들어졌다. 그러면 무엇을 지적하는지는 알아도 그
지적이 이 거래구조에서 왜 문제인지는 모르는 상태로 검토가 진행된다.

게이트는 두 단계로 나눈다:

  BLOCKING   이것이 비면 조항 검토가 의미를 갖지 못한다 —
             누가 누구에게 무엇을 해주고 무슨 대가를 받는지.
             비면 REVIEW_FAILED_LEGAL_MAP_INCOMPLETE.

  ADVISORY   비면 검토 품질이 떨어지지만 조항 검토 자체는 가능하다.
             리포트에 "확인 필요"로 남기고 진행한다.

계약유형에 따라 필수 축이 다르다. NDA 에 위험 이전 시점을 요구하면 전부
오탐이고, 공사도급계약에 그것이 없으면 검토가 반쪽이다. 그래서 유형군별로
BLOCKING 축을 다르게 잡는다 — 특정 계약서가 아니라 **유형** 기준이므로
처음 보는 계약서에도 적용된다.
"""
from __future__ import annotations

from typing import Any

REVIEW_FAILED_LEGAL_MAP_INCOMPLETE = "REVIEW_FAILED_LEGAL_MAP_INCOMPLETE"

#: 요청된 15축 → Legal Map 필드. 리포트 표기용 한국어 라벨을 함께 둔다.
LEGAL_MAP_AXES: tuple[tuple[str, str], ...] = (
    ("contract_purpose", "계약의 법적 성격"),
    ("our_role_direction", "우리 회사의 지위"),
    ("counterparty", "상대방 지위"),
    ("primary_obligations", "핵심 급부"),
    ("payment_flow", "대가 지급 구조"),
    ("term", "계약기간/완료조건"),
    ("acceptance_and_completion", "검수/인도/준공 조건"),
    ("risk_transfer_point", "위험 이전 시점"),
    ("liability_structure", "책임 구조"),
    ("indemnity_structure", "손해배상 구조"),
    ("termination_structure", "해지 구조"),
    ("guarantee_structure", "보증/담보 구조"),
    ("third_party_liability", "제3자·하도급 구조"),
    ("ip_and_data_ownership", "지식재산/자료 귀속"),
    ("applicable_statutes", "적용 가능 법률"),
)

#: 모든 계약유형에서 비면 조항 검토가 의미를 갖지 못하는 축.
#: "누가(지위) 누구에게 무엇을(급부) 해주고 무슨 대가를(지급) 받는가".
_BLOCKING_ALWAYS: tuple[str, ...] = (
    "contract_purpose",
    "our_role_direction",
    "primary_obligations",
)

#: 유형군별 추가 BLOCKING 축.
_BLOCKING_BY_FAMILY: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("construction", "works", "공사", "도급", "installation", "설치",
         "supply", "purchase", "물품", "공급"),
        # 일의 완성·물건의 인도가 급부인 계약: 대가·완료판정·위험이전이 핵심.
        ("payment_flow", "acceptance_and_completion", "risk_transfer_point"),
    ),
    (
        ("development", "service", "용역", "개발", "outsourcing"),
        # 성과물 창출 계약: 대가·완료판정·산출물 귀속.
        ("payment_flow", "acceptance_and_completion", "ip_and_data_ownership"),
    ),
    (
        ("nda", "confidential", "비밀유지"),
        # 금전 급부가 없다 — 대가·위험이전을 요구하면 전부 오탐이다.
        (),
    ),
    (
        ("rental", "lease", "렌탈", "임대"),
        ("payment_flow", "term"),
    ),
    (
        ("sales_agency", "dealer", "대리점", "위탁", "distribut"),
        ("payment_flow", "third_party_liability"),
    ),
    (
        ("license", "라이선스", "실시권"),
        ("payment_flow", "ip_and_data_ownership"),
    ),
)

#: 값이 있어도 "모른다"는 뜻인 표기 — 채워진 것으로 보면 안 된다.
_EMPTY_MARKERS: frozenset[str] = frozenset({
    "", "none", "null", "n/a", "na", "-", "미확인", "미확정", "불명", "불명확",
    "확인 필요", "확인필요", "해당 없음", "해당없음", "미상", "알 수 없음",
})


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, (list, tuple, set)):
        return any(_is_filled(v) for v in value)
    if isinstance(value, dict):
        return any(_is_filled(v) for v in value.values())
    s = str(value).strip()
    return bool(s) and s.lower() not in _EMPTY_MARKERS


def blocking_axes_for(contract_type_code: str) -> tuple[str, ...]:
    """이 계약유형에서 비면 조항 검토를 시작할 수 없는 축."""
    code = str(contract_type_code or "").strip().lower()
    extra: tuple[str, ...] = ()
    for needles, axes in _BLOCKING_BY_FAMILY:
        if any(n in code for n in needles):
            extra = axes
            break
    else:
        # 유형을 특정하지 못하면 최소 공통 축만 요구한다 — 모르는 유형에
        # 임의의 필수 항목을 강요하면 그 자체가 오탐이다.
        extra = ()
    seen: list[str] = []
    for a in _BLOCKING_ALWAYS + extra:
        if a not in seen:
            seen.append(a)
    return tuple(seen)


def evaluate_legal_map(
    fields: dict[str, Any] | None, *, contract_type_code: str = "",
) -> dict[str, Any]:
    """Legal Map 완결성을 평가한다.

    반환:
      axes            축별 [{key, label, filled, blocking}]
      missing_blocking  비어 있는 BLOCKING 축 라벨
      missing_advisory  비어 있는 나머지 축 라벨
      complete        BLOCKING 축이 모두 채워졌는가
      review_status   미완이면 REVIEW_FAILED_LEGAL_MAP_INCOMPLETE
      detail          사람이 읽는 설명
    """
    f = fields or {}
    blocking = set(blocking_axes_for(contract_type_code))

    axes: list[dict[str, Any]] = []
    missing_blocking: list[str] = []
    missing_advisory: list[str] = []
    for key, label in LEGAL_MAP_AXES:
        filled = _is_filled(f.get(key))
        is_blocking = key in blocking
        axes.append({
            "key": key, "label": label, "filled": filled, "blocking": is_blocking,
        })
        if not filled:
            (missing_blocking if is_blocking else missing_advisory).append(label)

    complete = not missing_blocking
    detail = ""
    if missing_blocking:
        detail = (
            "조항별 검토를 시작하기 전에 확정되어야 하는 축이 비어 있습니다: "
            + ", ".join(missing_blocking)
            + ". 이 축이 비면 개별 조항의 지적이 이 거래구조에서 왜 문제인지 "
            "설명할 수 없습니다."
        )
    elif missing_advisory:
        detail = "확인이 필요한 축: " + ", ".join(missing_advisory)

    return {
        "axes": axes,
        "filled_count": sum(1 for a in axes if a["filled"]),
        "total_count": len(axes),
        "blocking_axes": sorted(blocking),
        "missing_blocking": missing_blocking,
        "missing_advisory": missing_advisory,
        "complete": complete,
        "review_status": "" if complete else REVIEW_FAILED_LEGAL_MAP_INCOMPLETE,
        "detail": detail,
    }
