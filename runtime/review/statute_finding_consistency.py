"""적용법률 결론과 finding 이 충돌하면 잡아낸다.

2026-09-11 지시 —
  · "대리점법 비적용으로 확정된 계약에서 대리점법 finding 생성 금지."
  · "최종 결과에서 applicability 결론과 finding 이 충돌하면 REVIEW_FAILED 처리."
  · "이미 2차적저작물작성권이 명시된 경우 '권리범위 불명확' 으로 HIGH 생성하지
     말고 실제 chain-of-title / 제3자 권리확보 여부만 검토."

왜 별도 게이트인가
────────────────
`statute_applicability_gate.deactivate_inapplicable_statute_findings()` 는
검토 **도중** 한 번 돈다. 그 뒤에도 finding 은 계속 만들어지고(에이전트 패스,
효과 기반 검토, 리스크 사슬), 후단에서 문구가 바뀌기도 한다. 그래서 최종
출력 직전에 한 번 더 확인해야 "비적용이라고 써놓고 그 법 위반을 지적하는"
자기모순이 남지 않는다.

이 모듈은 **최종 확인자**다. 여기서 충돌이 잡히면 그것은 파이프라인이 앞에서
막지 못했다는 뜻이므로, 충돌 finding 을 제거하고 `REVIEW_FAILED_STATUTE_CONFLICT`
를 세운다.

다운로드와의 관계
──────────────
이 상태는 `delivery_gate.REMEDIABLE_STATUSES` 에 속한다 — 충돌 finding 을
**제거**하는 것으로 결함이 실제로 해소되기 때문이다. 따라서 정상 완료로
표시되지는 않지만(사유가 문서 말미에 실린다) 다운로드는 계속 가능하다.
"절대 에러나지 않고 최종수정본이 다운로드되게" 라는 요구와 양립시키기 위한
설계다.
"""
from __future__ import annotations

import re
from typing import Any

REVIEW_FAILED_STATUTE_CONFLICT = "REVIEW_FAILED_STATUTE_CONFLICT"

#: 그 법률의 의무·금지·제재를 **주장**하는 문장의 표지.
_RX_ASSERTION = re.compile(
    r"위반|위법|무효|금지|의무|해당(?:한다|할\s*수\s*있|됩니다)|적용(?:된다|됩니다|받)"
    r"|시정명령|과징금|과태료|제재|처벌|규정에\s*따라|저촉",
)

#: 반대로 사실확인·누락을 지적하는 문장은 법률 적용이 아니다.
_RX_FACT_OR_GAP = re.compile(
    r"확인이?\s*필요|확정되지\s*(?:않|아니)|규정되지\s*(?:않|아니)|누락"
    r"|불명확|특정되지\s*(?:않|아니)|별도\s*계약|사실관계",
)

_TEXT_FIELDS = (
    "issue_title", "problem", "rewrite_reason", "legal_business_reason",
    "suggested_rewrite", "recommendation_text", "negotiation_strategy",
    "worst_case_scenario",
)


def _blob(cr: dict[str, Any]) -> str:
    parts = [str(cr.get(k) or "") for k in _TEXT_FIELDS]
    detected = cr.get("detected_issue_list")
    if isinstance(detected, list):
        parts += [str(d.get("issue_title") or "") for d in detected if isinstance(d, dict)]
    return "\n".join(parts)


def find_statute_conflicts(
    clause_results: list[dict[str, Any]],
    decisions: list[dict[str, Any]] | None,
    *,
    contract_text: str = "",
) -> list[dict[str, Any]]:
    """비적용으로 확정된 법률의 의무를 주장하는 finding 을 찾는다."""
    blocked = {
        str(d.get("statute") or ""): str(d.get("reason") or "")
        for d in (decisions or [])
        if isinstance(d, dict) and str(d.get("conclusion") or "") == "비적용"
    }
    if not blocked:
        return []
    body = str(contract_text or "")
    conflicts: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        blob = _blob(cr)
        for statute, reason in blocked.items():
            if statute not in blob:
                continue
            # 계약 원문이 그 법률을 언급하고 있으면 인용일 수 있다.
            if statute in body and not _RX_ASSERTION.search(blob):
                continue
            if not _RX_ASSERTION.search(blob):
                continue
            if _RX_FACT_OR_GAP.search(blob):
                continue
            conflicts.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "statute": statute,
                "reason": reason,
            })
            break
    return conflicts


def enforce_statute_conclusion_consistency(
    clause_results: list[dict[str, Any]],
    decisions: list[dict[str, Any]] | None,
    *,
    contract_text: str = "",
) -> dict[str, Any]:
    """충돌 finding 을 제거하고 상태를 돌려준다.

    돌려주는 dict: {"status", "detail", "conflicts"}. status 가 비어 있으면
    충돌이 없다.
    """
    conflicts = find_statute_conflicts(
        clause_results, decisions, contract_text=contract_text,
    )
    if not conflicts:
        return {"status": "", "detail": "", "conflicts": []}

    removed_ids = {c["clause_id"] for c in conflicts}
    clause_results[:] = [
        cr for cr in clause_results
        if not (isinstance(cr, dict) and str(cr.get("clause_id") or "") in removed_ids)
    ]
    statutes = sorted({c["statute"] for c in conflicts})
    return {
        "status": REVIEW_FAILED_STATUTE_CONFLICT,
        "detail": (
            f"비적용으로 판단한 법률({', '.join(statutes)})의 의무·제재를 주장하는 "
            f"검토의견 {len(conflicts)}건이 최종 결과에 남아 있어 제거했습니다: "
            + ", ".join(c["clause_id"] for c in conflicts[:5])
        ),
        "conflicts": conflicts,
    }


# ── 이미 명시된 권리를 "불명확" 으로 다시 지적하지 않는다 (지시 항목 4) ────────

#: 계약이 2차적저작물작성권을 **명시적으로** 규정했다는 신호.
_RX_DERIVATIVE_GRANTED = re.compile(
    r"2차적저작물(?:작성권|의\s*작성)|derivative\s+works?",
    re.IGNORECASE,
)

#: "권리 범위가 불명확하다" 는 주장. 이미 명시돼 있으면 이 주장은 틀렸다.
_RX_SCOPE_UNCLEAR = re.compile(
    r"(?:범위|귀속)[^.\n]{0,20}(?:불명확|명확하지\s*(?:않|아니)|특정되지\s*(?:않|아니))"
    r"|불명확[^.\n]{0,20}(?:범위|귀속)"
    r"|포함\s*여부[^.\n]{0,20}(?:불명확|미명시)"
    r"|양도에\s*포함되지\s*(?:않|아니)",
)

#: 대신 검토해야 하는 것 — 실제 권리 확보의 사슬.
_CHAIN_OF_TITLE_FOCUS = (
    "권리 범위는 계약에 이미 명시되어 있으므로, 남는 쟁점은 그 권리가 실제로 "
    "확보되는가입니다 — 창작에 관여한 임직원·출연자·외주 스태프로부터의 권리 "
    "확약(chain of title)과, 콘텐츠에 포함된 제3자 소재(음원·서체·이미지)의 "
    "라이선스가 우리 이용 범위를 모두 덮는지를 확인해야 합니다."
)


def reframe_settled_ip_scope(
    clause_results: list[dict[str, Any]],
    *,
    contract_text: str,
) -> list[dict[str, Any]]:
    """2차적저작물작성권이 이미 명시된 계약에서 "범위 불명확" 주장을 바로잡는다.

    finding 을 지우지 않는다 — 권리 확보(chain of title·제3자 소재) 쟁점은
    여전히 유효하기 때문이다. 주장만 실제 쟁점으로 바꾸고, HIGH 였다면
    MEDIUM 으로 낮춘다.
    """
    if not _RX_DERIVATIVE_GRANTED.search(str(contract_text or "")):
        return []

    reframed: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        blob = _blob(cr)
        if "2차적저작물" not in blob and "derivative" not in blob.lower():
            continue
        if not _RX_SCOPE_UNCLEAR.search(blob):
            continue

        for key in ("issue_title", "problem", "rewrite_reason"):
            value = str(cr.get(key) or "")
            if not value.strip():
                continue
            cr[key] = _RX_SCOPE_UNCLEAR.sub("확보 여부 확인 필요", value)
        existing = str(cr.get("legal_business_reason") or "").strip()
        if _CHAIN_OF_TITLE_FOCUS not in existing:
            cr["legal_business_reason"] = (
                f"{existing}\n{_CHAIN_OF_TITLE_FOCUS}".strip()
                if existing else _CHAIN_OF_TITLE_FOCUS
            )
        detected = cr.get("detected_issue_list")
        if isinstance(detected, list):
            for d in detected:
                if isinstance(d, dict) and d.get("issue_title"):
                    d["issue_title"] = _RX_SCOPE_UNCLEAR.sub(
                        "확보 여부 확인 필요", str(d["issue_title"]),
                    )
        if str(cr.get("risk_tier") or "").upper() == "HIGH":
            cr["risk_tier"] = "MEDIUM"
            cr["severity"] = "MEDIUM"
            cr["counsel_severity"] = "MEDIUM"
            cr["must_fix"] = False
            cr["review_tier"] = "SUGGEST"
        cr["ip_scope_reframed"] = True
        reframed.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
        })
    return reframed
