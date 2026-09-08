"""계약유형별 "계약 구조 요약" 필드 구성 (2026-09-08 지시 항목 4).

문제: 구조 요약 필드가 대리점/렌탈 계약군 기준으로 하드코딩되어 있어서,
NDA 검토 결과에도 `세금계산서 발행 주체`, `대금청구/수금 주체`,
`대리점의 대리권` 같은 **계약과 무관한 stale 필드**가 그대로 출력됐다.
비밀유지계약에 세금계산서 발행 주체가 나오면 그 자체가 오답이다.

해결: 필드 집합을 계약유형별로 동적으로 구성한다. `fields_for()` 가
그 계약유형에서 **의미가 있는 필드만** 순서대로 돌려주고, 렌더러(DOCX/PDF/UI)
는 그 목록만 출력한다. 새 계약유형이 추가되면 `_COMMON` 만 나오므로
"엉뚱한 필드가 나오는" 실패 모드가 기본값에서 사라진다.

값이 비어 있을 때의 문구도 필드마다 다르다 — 대리점 계약에서 세금계산서
주체가 비면 구조 불일치 HIGH 신호지만, NDA 에서 비밀유지기간이 비는 것은
단순 미기재다. 그래서 `missing_is_high_risk` 를 필드 단위로 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructureField:
    #: detailed_contract_profile 의 키
    key: str
    #: 리포트에 찍히는 라벨
    label: str
    #: 값이 없을 때 보여줄 문구 (없으면 필드 자체를 생략)
    missing_text: str = ""
    #: 값이 없을 때 HIGH 리스크로 붉게 표시할지
    missing_is_high_risk: bool = False


# ── 모든 계약유형 공통 ────────────────────────────────────────────────────
_COMMON: tuple[StructureField, ...] = (
    StructureField("our_party", "우리 회사"),
    StructureField("counterparty", "상대방"),
    StructureField("contract_type", "계약유형"),
)

# ── 대리점·위탁판매·렌탈 계약군 전용 ──────────────────────────────────────
# 기존 동작을 그대로 유지한다. 이 필드들이 비면 구조 불일치 HIGH 신호다.
_DEALER_FIELDS: tuple[StructureField, ...] = (
    StructureField(
        "customer_contracting_party", "고객 계약 당사자",
        "명시 필요 — 현재 조항 간 표현 충돌 (HIGH RISK)", True,
    ),
    StructureField(
        "tax_invoice_issuer", "세금계산서 발행 주체",
        "명시 필요 — 현재 대리점이 발행 주체처럼 기재 (HIGH RISK)", True,
    ),
    StructureField(
        "payment_collection_party", "대금청구/수금 주체",
        "명시 필요 — 대리점의 지원업무와 법적 주체 구분 필요 (HIGH RISK)", True,
    ),
    StructureField("agency_authority", "대리점의 대리권", "명시 필요"),
)

# ── NDA / 비밀유지 계약군 전용 ────────────────────────────────────────────
_NDA_FIELDS: tuple[StructureField, ...] = (
    StructureField("nda_direction", "비밀정보 흐름", "명시 필요 — 일방/상호 구분 확인"),
    StructureField("disclosing_party", "정보 제공 주체"),
    StructureField("receiving_party", "정보 수령 주체"),
    StructureField("confidentiality_term", "비밀유지기간", "미기재 — 존속기간 명시 필요"),
    StructureField("permitted_recipients", "허용 수령자 범위", "미기재 — 임직원/협력업체 범위 명시 필요"),
    StructureField("background_ip_treatment", "Background IP 취급", "미기재 — 각 당사자 보유권 유지 조항 필요"),
    StructureField("foreground_ip_treatment", "개발결과물(Foreground IP) 귀속", "미기재 — 별도 개발계약 유보 필요"),
    StructureField("personal_data_scope", "개인정보 처리 경계", "미기재 — 처리 전 별도 계약 필요"),
)

# ── 용역·개발·도급 계약군 전용 ────────────────────────────────────────────
_SERVICE_FIELDS: tuple[StructureField, ...] = (
    StructureField("our_legal_role", "우리 측 지위"),
    StructureField("deliverables_ip_owner", "산출물 지식재산권 귀속", "미기재 — 귀속 주체 명시 필요"),
    StructureField("acceptance_criteria", "검수 기준", "미기재"),
    StructureField("payment_terms", "대금 지급 조건", "미기재"),
)

#: contract_type_code 접두/부분 문자열 → 추가 필드셋.
#: 가장 먼저 매칭된 것 하나만 적용한다(순서가 우선순위).
_TYPE_FIELDSETS: tuple[tuple[tuple[str, ...], tuple[StructureField, ...]], ...] = (
    (("nda", "confidential", "secrecy", "비밀유지"), _NDA_FIELDS),
    (("dealer", "agency", "consignment", "rental", "대리점", "위탁"), _DEALER_FIELDS),
    (("service", "development", "construction", "outsourcing", "용역", "개발", "도급"), _SERVICE_FIELDS),
)


def _norm(code: str) -> str:
    return str(code or "").strip().lower()


def fieldset_name(contract_type_code: str) -> str:
    """이 계약유형에 적용된 필드셋 이름 (감사·테스트용)."""
    code = _norm(contract_type_code)
    for needles, fields in _TYPE_FIELDSETS:
        if any(n in code for n in needles):
            if fields is _NDA_FIELDS:
                return "nda"
            if fields is _DEALER_FIELDS:
                return "dealer"
            return "service"
    return "common_only"


def fields_for(contract_type_code: str) -> tuple[StructureField, ...]:
    """이 계약유형에서 의미가 있는 구조 요약 필드만 순서대로 반환한다."""
    code = _norm(contract_type_code)
    for needles, fields in _TYPE_FIELDSETS:
        if any(n in code for n in needles):
            return _COMMON + fields
    return _COMMON


def is_field_allowed(contract_type_code: str, key: str) -> bool:
    """이 계약유형에서 해당 필드를 출력해도 되는지."""
    return any(f.key == key for f in fields_for(contract_type_code))


def render_rows(
    contract_type_code: str,
    profile: dict[str, Any] | None,
    *,
    include_missing: bool = True,
) -> list[dict[str, Any]]:
    """렌더러가 그대로 찍을 수 있는 (label, value, is_high_risk) 행 목록.

    값이 없고 `missing_text` 도 없으면 그 행은 아예 생략한다 — 무관한 필드를
    "미확정"으로 채워 넣는 것이 바로 항목 4 가 지적한 stale 출력이다.
    """
    dp = profile or {}
    rows: list[dict[str, Any]] = []
    for f in fields_for(contract_type_code):
        raw = dp.get(f.key)
        val = "" if raw is None else str(raw).strip()
        if val and val not in ("미확정", "미상", "unknown", "None"):
            rows.append({"key": f.key, "label": f.label, "value": val, "is_high_risk": False})
            continue
        if not include_missing or not f.missing_text:
            continue
        rows.append({
            "key": f.key,
            "label": f.label,
            "value": f.missing_text,
            "is_high_risk": bool(f.missing_is_high_risk),
        })
    return rows


def stale_fields_present(contract_type_code: str, emitted_keys: list[str] | None) -> list[str]:
    """이 계약유형에 허용되지 않은 필드가 출력된 경우 그 키 목록.

    렌더러 회귀를 잡는 게이트 — NDA 결과에 tax_invoice_issuer 가 다시 섞이면
    여기서 걸린다.
    """
    allowed = {f.key for f in fields_for(contract_type_code)}
    return [k for k in (emitted_keys or []) if k not in allowed]
