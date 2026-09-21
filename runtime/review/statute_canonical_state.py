"""Applicable Law canonical state — 법률마다 결론은 **하나**다.

2026-09-21 2차 지시 7항 —
  "같은 문서 안에서 하도급법 적용 / 하도급법 비적용 / 하도급법 LOW /
   하도급법 HIGH 처럼 서로 다른 결론이 동시에 존재하지 못하게 하세요.
   법률별 canonical status: APPLIES / NOT_APPLIES / NEEDS_FACT_CHECK 중
   하나만 허용. 이 상태를 UI, DOCX, rule engine, AI 결과가 모두 공유해야
   합니다."

실측(인테리어 2차 본계약, 2026-09-21 15:45 검토). 같은 리포트 안에서:

    rule engine (statute_applicability_gate)
        하도급법 = 비적용
        "퍼시스가 발주자와 직접 계약한 수급인이므로 원도급 관계에는
         하도급법이 적용되지 않는다"(v13 지시 4항)

    AI (legal_applicability_review)
        하도급법 = 높음 / HIGH
        "퍼시스가 중견기업 이상, 라온로보틱스가 원사업자에 해당할 가능성이
         높습니다"                       ← 발주자를 원사업자로 본 오판

담당자는 같은 문서에서 정반대의 결론 둘을 읽는다. 게다가 AI 쪽 근거는
당사자 지위를 뒤집고 있어 지시 1항(Party Role) 위반이기도 하다.

누가 이기는가 — 적용요건을 **먼저** 판단한 쪽
──────────────────────────────────────
`statute_applicability_gate` 는 우리 업 도메인과 확정된 당사자 지위에서
법정 적용요건을 따진다(v7 지시). AI 는 계약 문언을 읽고 가능성을 말한다.
요건 판단이 선다면 그것이 canonical 이고, AI 판단은 그 아래로 맞춘다.
요건 판단이 없는 법률은 AI 판단을 그대로 쓴다 — 모르는 것을 덮어쓰지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

APPLIES = "APPLIES"
NOT_APPLIES = "NOT_APPLIES"
NEEDS_FACT_CHECK = "NEEDS_FACT_CHECK"

#: rule engine 결론 → canonical status.
_FROM_CONCLUSION: dict[str, str] = {
    "적용": APPLIES,
    "일부 적용": APPLIES,
    "비적용": NOT_APPLIES,
    "사실확인 필요": NEEDS_FACT_CHECK,
}

#: canonical status → AI 결과 표기(화면·DOCX 가 그대로 쓴다).
_APPLICABILITY_LABEL: dict[str, str] = {
    APPLIES: "높음",
    NOT_APPLIES: "낮음",
    NEEDS_FACT_CHECK: "있음(추가 확인 필요)",
}

#: canonical status → 위험도 상한. 비적용인 법률이 HIGH 로 남아 있으면
#: 그 자체가 모순이다.
_RISK_CEILING: dict[str, str] = {
    NOT_APPLIES: "LOW",
    NEEDS_FACT_CHECK: "MEDIUM",
}

_RISK_RANK = {"확인 필요": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _norm_statute(name: str) -> str:
    """법률명 표기 차이를 흡수한다 — 약칭과 정식명칭이 섞여 들어온다."""
    s = re.sub(r"\s+", "", str(name or ""))
    s = s.replace("「", "").replace("」", "")
    aliases = {
        "하도급거래공정화에관한법률": "하도급법",
        "독점규제및공정거래에관한법률": "공정거래법",
        "대리점거래의공정화에관한법률": "대리점법",
        "개인정보보호법": "개인정보보호법",
        "산업안전보건법": "산업안전보건법",
        "중대재해처벌등에관한법률": "중대재해처벌법",
        "건설산업기본법": "건설산업기본법",
        "대규모유통업에서의거래공정화에관한법률": "대규모유통업법",
    }
    return aliases.get(s, s)


@dataclass
class StatuteCanonicalState:
    """법률별 확정 결론. 이 값을 UI·DOCX·룰엔진·AI 결과가 함께 쓴다."""

    statuses: dict[str, str] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    #: 구조 보정이 값을 세워 요건 판단으로 덮지 않은 법률.
    deferred: list[dict[str, Any]] = field(default_factory=list)

    def status_of(self, statute: str) -> str:
        return self.statuses.get(_norm_statute(statute), "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "statuses": dict(self.statuses),
            "reasons": dict(self.reasons),
            "conflicts": list(self.conflicts),
            "deferred_to_calibration": list(self.deferred),
        }

    @property
    def detail(self) -> str:
        if not self.conflicts:
            return ""
        names = ", ".join(
            f"{c['statute']}({c['was']}→{c['now']})" for c in self.conflicts[:3]
        )
        return (
            f"같은 법률에 서로 다른 결론이 있어 적용요건 판단으로 통일했습니다 — {names}."
        )


def build_statute_canonical_state(
    statute_decisions: list[Any] | None,
) -> StatuteCanonicalState:
    """적용요건 판단을 canonical 상태로 굳힌다."""
    state = StatuteCanonicalState()
    for d in statute_decisions or []:
        statute = str(getattr(d, "statute", "") or (d.get("statute") if isinstance(d, dict) else ""))
        conclusion = str(
            getattr(d, "conclusion", "") or (d.get("conclusion") if isinstance(d, dict) else "")
        )
        key = _norm_statute(statute)
        status = _FROM_CONCLUSION.get(conclusion.strip(), "")
        if not key or not status:
            continue
        state.statuses[key] = status
        state.reasons[key] = str(
            getattr(d, "reason", "") or (d.get("reason") if isinstance(d, dict) else "")
        )
    return state


def reconcile_ai_applicability(
    results: list[dict[str, Any]] | None,
    state: StatuteCanonicalState,
) -> StatuteCanonicalState:
    """AI 적용가능성 결과를 canonical 상태에 맞춘다.

    제자리에서 고치고, 무엇이 어긋났는지 `state.conflicts` 에 남긴다.
    """
    for row in results or []:
        if not isinstance(row, dict):
            continue
        key = _norm_statute(row.get("statute"))
        status = state.statuses.get(key)
        if not status:
            continue
        # 구조 보정(`statute_applicability_calibration`)이 명시적으로 값을
        # 세운 법률은 그 판단이 이긴다. 그 보정은 실사례에서 법무팀이 확정한
        # 결론을 코드로 굳힌 것이라(그림닷컴 대리점법 floor, 판매지원
        # 하도급법 ceiling), 요건 판단으로 덮으면 그 결론이 사라진다.
        # 덮지 않되, 어느 쪽이 값을 정했는지는 남긴다.
        if row.get("applicability_calibrated"):
            state.deferred.append({
                "statute": key,
                "kept": f"{row.get('applicability')}/{row.get('risk_level')}",
                "calibration": str(row.get("applicability_calibrated")),
                "requirement_conclusion": status,
            })
            row["canonical_status"] = status
            continue
        want_label = _APPLICABILITY_LABEL[status]
        had_label = str(row.get("applicability") or "").strip()
        had_risk = str(row.get("risk_level") or "").strip()
        ceiling = _RISK_CEILING.get(status)
        over = bool(
            ceiling and _RISK_RANK.get(had_risk.upper(), 0) > _RISK_RANK.get(ceiling, 0)
        )
        if had_label == want_label and not over:
            continue
        state.conflicts.append({
            "statute": key,
            "was": f"{had_label or '미상'}/{had_risk or '미상'}",
            "now": f"{want_label}/{ceiling or had_risk or '미상'}",
            "canonical_status": status,
            "reason": state.reasons.get(key, ""),
        })
        row["applicability"] = want_label
        if ceiling:
            row["risk_level"] = ceiling
        row["canonical_status"] = status
        if state.reasons.get(key):
            row["reasoning"] = (
                f"[적용요건 판단] {state.reasons[key]}\n"
                f"(당초 자동 분석 의견: {had_label or '미상'} — 적용요건 판단으로 "
                f"통일했습니다.)"
            )
    return state
