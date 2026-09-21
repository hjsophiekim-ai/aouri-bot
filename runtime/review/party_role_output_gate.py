"""출력물이 확정된 당사자 지위를 뒤집지 않는지 본다.

2026-09-21 2차 지시 1항 —
  "사용자 설명과 계약 전문이 모두 같은 역할을 가리키면 이후 어떤
   rule/classifier 도 이를 뒤집지 못하게 하세요.
   '퍼시스 = 발주자/도급인/콘텐츠 사용권자' 같은 다른 role 이 출력되면
   REVIEW_FAILED_PARTY_ROLE_MISMATCH."

지위는 판정 단계에서 이미 고정된다(v13 `construction_transaction_model`,
v14 `contract_model`). 여기서 보는 것은 **출력된 문장**이다 — 판정은 맞는데
설명 문장이 반대로 적히는 일이 실제로 있다.

실측(인테리어 2차 본계약, 2026-09-21 15:45 검토). 확정 지위는
`우리=수급인 / 상대방=도급인` 인데, 적용법률 분석의 근거 문장이 이렇게 나갔다:

    "퍼시스가 중견기업 이상, 라온로보틱스가 원사업자에 해당할 가능성이 높습니다"

라온로보틱스는 발주자다. 발주자를 원사업자로 보면 하도급법 적용 결론이
통째로 뒤집히고(지시 7항 충돌의 원인이기도 하다), 담당자는 자기 회사가
어느 쪽인지 헷갈린다.

**지적을 지우지 않는다.** 뒤집힌 문장을 찾아 기록하고, 그 항목에 확정 지위를
명시한 정정 문구를 붙인다. 구조적 오류(우리 회사를 상대방 지위로 서술)는
`REVIEW_FAILED_PARTY_ROLE_MISMATCH` 로 세운다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REVIEW_FAILED_PARTY_ROLE_MISMATCH = "REVIEW_FAILED_PARTY_ROLE_MISMATCH"

#: 우리 지위 코드 → 우리에게 붙을 수 없는 상대편 호칭.
#: 같은 낱말이라도 재하도급 관계에서는 정당하므로(우리가 하수급인에 대해
#: 도급인이 된다), 문장에 재하도급 맥락이 있으면 판정하지 않는다.
OPPOSITE_LABELS: dict[str, tuple[str, ...]] = {
    "contractor": ("발주자", "도급인", "원사업자", "발주처"),
    "contractor_with_subcontract": ("발주자", "도급인", "원사업자", "발주처"),
    "owner": ("수급인", "하수급인", "시공사", "수급사업자"),
    "supplier": ("매수인", "구매자", "발주자"),
    "buyer": ("매도인", "공급자", "수급인"),
}

#: 상대방 지위 코드 → 상대방에게 붙을 수 없는 호칭.
COUNTERPARTY_OPPOSITE_LABELS: dict[str, tuple[str, ...]] = {
    "ordering_party": ("수급인", "수급사업자", "하수급인", "시공사"),
    "contractor": ("발주자", "도급인", "원사업자"),
}

#: 이 낱말이 문장에 있으면 재하도급 층위를 말하는 것이므로 판정하지 않는다.
_SUBCONTRACT_CONTEXT = (
    "재하도급", "하수급인", "전문업체", "재하도급 계약", "원사업자가 됩니다",
    "도급인이 됩니다", "별도 체결",
)

#: 검사 대상 필드 — 담당자가 실제로 읽는 문장들.
_TEXT_FIELDS: tuple[str, ...] = (
    "issue_title", "problem", "legal_business_reason", "rewrite_reason",
    "reasoning", "negotiation_position", "worst_case_scenario",
    # 적용요건 판단(StatuteDecision)의 근거 문장. 실측에서 발주자를
    # 원사업자로 서술한 문장이 여기에도 있었다.
    "reason",
)


#: 계약서가 당사자를 부르는 역할 명사·약칭. 이름이 아니므로 대조에서 뺀다.
_ROLE_NOUNS: frozenset[str] = frozenset({
    "갑", "을", "병", "정",
    "도급인", "수급인", "발주자", "발주처", "시공사", "시공자", "건축주", "시행사",
    "하수급인", "원사업자", "수급사업자", "원도급인", "원도급사",
    "매도인", "매수인", "공급자", "구매자", "위탁자", "수탁자",
    "당사", "우리 회사", "상대방",
})


def _is_company_name(value: Any) -> bool:
    name = re.sub(r"\s+", "", str(value or ""))
    if len(name) < 2 or name in _ROLE_NOUNS:
        return False
    return re.sub(r"\s+", " ", str(value or "")).strip() not in _ROLE_NOUNS


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _has_subcontract_context(sentence: str) -> bool:
    return any(k in sentence for k in _SUBCONTRACT_CONTEXT)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.。])\s+|\n", str(text or "")) if s.strip()]


@dataclass
class PartyRoleOutputReport:
    violations: list[dict[str, Any]] = field(default_factory=list)
    checked: int = 0

    @property
    def status(self) -> str:
        return REVIEW_FAILED_PARTY_ROLE_MISMATCH if self.violations else ""

    @property
    def detail(self) -> str:
        if not self.violations:
            return ""
        names = ", ".join(
            f"{v['where']}({v['wrong_label']})" for v in self.violations[:3]
        )
        return (
            f"확정된 당사자 지위와 반대로 서술한 문장 {len(self.violations)}건을 "
            f"찾아 정정 표시했습니다 — {names}."
        )


def check_party_role_output(
    *,
    our_names: list[str] | None,
    counterparty_names: list[str] | None,
    our_role: str,
    counterparty_role: str,
    our_role_label: str = "",
    counterparty_role_label: str = "",
    clause_results: list[dict[str, Any]] | None = None,
    extra_records: list[dict[str, Any]] | None = None,
) -> PartyRoleOutputReport:
    """출력 문장이 확정 지위를 뒤집는지 본다.

    `extra_records` 로 적용법률 분석처럼 finding 이 아닌 산출물도 함께 볼 수
    있다(그 근거 문장에서 실제로 사고가 났다).
    """
    report = PartyRoleOutputReport()
    # **회사 이름만** 본다. 계약서가 당사자를 부르는 역할 명사("수급인",
    # "도급인")를 이름으로 넣으면, "도급인 귀책으로 발생한 손해까지 수급인이
    # 부담한다" 처럼 두 역할을 모두 언급하는 정상 문장이 전부 위반으로
    # 잡힌다(실측: CWC-13 에서 9건). 역할 명사는 지위를 뒤집는 증거가 아니라
    # 그냥 계약을 설명하는 말이다.
    ours = [n for n in (our_names or []) if _is_company_name(n)]
    theirs = [n for n in (counterparty_names or []) if _is_company_name(n)]
    bad_for_us = OPPOSITE_LABELS.get(str(our_role or ""), ())
    bad_for_them = COUNTERPARTY_OPPOSITE_LABELS.get(str(counterparty_role or ""), ())
    if not (bad_for_us or bad_for_them):
        return report

    targets: list[tuple[str, dict[str, Any]]] = []
    for cr in clause_results or []:
        if isinstance(cr, dict) and not cr.get("dedup_suppressed"):
            targets.append((str(cr.get("clause_id") or cr.get("display_path") or ""), cr))
    for row in extra_records or []:
        if isinstance(row, dict):
            targets.append((str(row.get("statute") or row.get("title") or "기타"), row))

    for where, record in targets:
        for field_name in _TEXT_FIELDS:
            value = _norm(record.get(field_name))
            if not value:
                continue
            report.checked += 1
            for sentence in _sentences(value):
                if _has_subcontract_context(sentence):
                    continue
                hit = _violation_in(sentence, ours, bad_for_us, theirs, bad_for_them)
                if hit is None:
                    continue
                subject, wrong = hit
                report.violations.append({
                    "where": where,
                    "field": field_name,
                    "subject": subject,
                    "wrong_label": wrong,
                    "sentence": sentence[:180],
                })
                note = (
                    f"[당사자 지위 정정] 이 계약에서 "
                    f"{(ours[0] if ours else '우리 회사')}는 "
                    f"{our_role_label or our_role}이고, "
                    f"{(theirs[0] if theirs else '상대방')}는 "
                    f"{counterparty_role_label or counterparty_role}입니다."
                )
                if note not in str(record.get(field_name) or ""):
                    record[field_name] = f"{record[field_name]}\n{note}"
                record["party_role_corrected"] = True
                break
    return report


def _violation_in(
    sentence: str,
    ours: list[str],
    bad_for_us: tuple[str, ...],
    theirs: list[str],
    bad_for_them: tuple[str, ...],
) -> tuple[str, str] | None:
    """한 문장 안에서 '이름 + 반대 지위' 가 붙어 있는지."""
    for names, bad in ((ours, bad_for_us), (theirs, bad_for_them)):
        for name in names:
            for idx in _find_all(sentence, str(name)):
                window = sentence[idx: idx + len(str(name)) + 30]
                for label in bad:
                    if label in window:
                        return str(name), label
    return None


def _find_all(haystack: str, needle: str) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i < 0:
            return out
        out.append(i)
        start = i + 1
