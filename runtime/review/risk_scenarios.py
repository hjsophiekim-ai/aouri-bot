"""Risk Scenario Modeling — requirement.md > Risk Scenario Modeling
가상 사고 시나리오를 계약 조항에 대입하여 치명적 법률적 결함을 추출한다.
"""
from __future__ import annotations

import re
from typing import Any

_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "SC-PL-001",
        "description": "공급 물품 파손·폭발로 사용자 상해 → 손해배상 청구",
        "trigger_kw": re.compile(
            r"제조물|하자|손해배상|면책|결함|보증|제품|물품|가구|설비|장비|공급", re.IGNORECASE
        ),
        "checks": [
            (
                "exemption_overbroad",
                re.compile(r"면책|책임\s*없음|책임\s*제한|면제|책임\s*부담하지\s*않", re.IGNORECASE),
                True,   # present=True means found, which means clause EXISTS (potential overbreadth)
                "면책 조항이 지나치게 포괄적인지 확인 필요",
                "HIGH",
            ),
            (
                "manual_present",
                re.compile(r"사용설명서|매뉴얼|안내서|경고문|주의사항|취급설명", re.IGNORECASE),
                False,  # present=False means MISSING → risk
                "사용설명서·경고 의무 조항이 없어 방어권 미비",
                "HIGH",
            ),
            (
                "burden_of_proof",
                re.compile(r"입증|증명책임|입증책임|결함\s*증명", re.IGNORECASE),
                False,
                "입증 책임 소재가 명시되지 않아 분쟁 시 불리",
                "MEDIUM",
            ),
        ],
    },
    {
        "id": "SC-PL-002",
        "description": "사용설명서 미비로 인한 오조작 사고",
        "trigger_kw": re.compile(
            r"제조물|물품|가구|설비|장비|공급|납품", re.IGNORECASE
        ),
        "checks": [
            (
                "manual_present",
                re.compile(r"사용설명서|매뉴얼|안내서|취급설명서", re.IGNORECASE),
                False,
                "사용설명서 제공 의무 조항 누락",
                "HIGH",
            ),
            (
                "warning_present",
                re.compile(r"경고|주의|안전 표시|위험 표시|안전 인증", re.IGNORECASE),
                False,
                "경고·주의 표시 의무 조항 누락",
                "MEDIUM",
            ),
        ],
    },
    {
        "id": "SC-DL-001",
        "description": "대리점 계약 해지 후 재고 미인수 분쟁",
        "trigger_kw": re.compile(
            r"대리점|위탁|유통|재고|반품|해지|위탁거래", re.IGNORECASE
        ),
        "checks": [
            (
                "inventory_return",
                re.compile(r"재고|반품|재매입|인수|반환", re.IGNORECASE),
                False,
                "해지 후 재고 처리 기준 조항 누락",
                "HIGH",
            ),
            (
                "termination_procedure",
                re.compile(r"해지\s*절차|서면\s*최고|시정\s*기간|해지\s*통보", re.IGNORECASE),
                False,
                "해지 절차(서면 최고·시정 기간) 미명시",
                "MEDIUM",
            ),
        ],
    },
    {
        "id": "SC-IP-001",
        "description": "용역 결과물 제3자 지재권 침해 소송",
        "trigger_kw": re.compile(
            r"저작권|특허|라이선스|귀속|지식재산|IP|결과물|산출물", re.IGNORECASE
        ),
        "checks": [
            (
                "ip_ownership_clear",
                re.compile(r"귀속|소유|이전|양도|전적으로", re.IGNORECASE),
                False,
                "IP 귀속 조항 미명시",
                "HIGH",
            ),
            (
                "third_party_warranty",
                re.compile(r"제3자.{0,20}(침해|보증|면책)|침해.{0,20}면책", re.IGNORECASE),
                False,
                "제3자 권리 침해 보증 조항 누락",
                "HIGH",
            ),
        ],
    },
]


def detect_risk_scenarios(
    full_text: str,
    contract_nature: str,
) -> list[dict[str, Any]]:
    """requirement.md > Risk Scenario Modeling.
    계약 전문에 시나리오를 대입하여 면책 과잉·방어권 미비·입증 책임 결함을 추출한다.
    """
    text = str(full_text or "")
    results: list[dict[str, Any]] = []

    for scenario in _SCENARIOS:
        if not scenario["trigger_kw"].search(text):
            continue

        findings: list[dict[str, Any]] = []
        for check_id, check_rx, risk_when_present, description, severity in scenario["checks"]:
            present = bool(check_rx.search(text))
            is_risk = present if risk_when_present else (not present)
            findings.append({
                "check_id": check_id,
                "description": description,
                "present": present,
                "is_risk": is_risk,
                "risk": severity if is_risk else "OK",
            })

        high_risk_findings = [f for f in findings if f["risk"] == "HIGH"]
        if not high_risk_findings:
            continue

        results.append({
            "scenario_id": scenario["id"],
            "description": scenario["description"],
            "findings": findings,
            "critical_finding": high_risk_findings[0]["description"],
            "high_count": len(high_risk_findings),
        })

    return results
