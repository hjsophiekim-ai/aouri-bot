"""Layer 2 — testing/inspection/certification service contract checklist.

Applies ONLY when contract_class == "testing_service" (시험·검사·인증/분석
용역). This is exactly the kind of type-specific rule set that the HARD
BLOCK in clause_level.py is meant to gate — it must never fire for a
product-supply, advisory, or content-production contract, and conversely a
testing-service contract must never be reviewed with product-supply/CI-SI/
IP-deliverable rules (those remain hard-blocked here).
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.clause_extraction import ClauseChunk, find_clause_scoped_excerpt

_TSR_ITEMS: list[dict[str, Any]] = [
    {
        "id": "tsr_certificate_usage_restriction",
        "name": "시험성적서 사용·광고·홍보 제한",
        "present": re.compile(
            r"사전\s*서면\s*동의\s*없이.{0,10}시험\s*성적서를?\s*.{0,20}(?:언론\s*보도|공표|광고|판촉|홍보)"
            r"|시험\s*성적서를?\s*(?:언론\s*보도|공표|광고|판촉|홍보).{0,20}(?:사전\s*서면\s*동의|승인)",
            re.IGNORECASE,
        ),
        "risk": "MEDIUM",
        "direction": "성적서를 내부 품질관리·규제 대응 목적으로 사용하는 경우까지 사전동의가 필요하지 않도록 예외를 명시",
        "reason": (
            "시험성적서의 광고·홍보 사용 시 사전 서면동의를 요구하는 것 자체는 통상적이나, "
            "동의 요청에 대한 수탁자의 응답 기한·거절 사유 기준이 없으면 위탁자의 정당한 "
            "품질 증빙·마케팅 활동이 불필요하게 지연될 수 있다."
        ),
        "rewrite": (
            "위탁자가 시험성적서 사용에 대한 서면동의를 요청한 경우, 수탁자는 요청일로부터 "
            "[7]영업일 이내에 동의 여부를 서면으로 통지하여야 하며, 그 기간 내 통지가 없는 경우 "
            "동의한 것으로 본다. 다만 내부 품질관리, 인증·규제기관 제출 등 대외 홍보 목적이 아닌 "
            "사용에는 사전동의를 요하지 아니한다."
        ),
        "clause_topic": "other",
    },
    {
        "id": "tsr_applicant_overbroad_liability",
        "name": "시험신청서·시료 관련 위탁자 책임 범위 과다",
        "present": re.compile(
            r"(?:신청서|시료).{0,30}(?:허위|부실|누락).{0,30}법적\s*책임을?\s*진다",
            re.IGNORECASE,
        ),
        "risk": "MEDIUM",
        "direction": "위탁자 책임을 고의·과실이 인정되는 경우로 한정하고, 책임 범위(직접손해 한도 등)를 명시",
        "reason": (
            "시험분석 신청서 기재 오류나 시료 하자에 대해 '법적 책임을 진다'고만 규정되어 "
            "있어 책임의 범위·한도가 불명확하다. 위탁자에게 고의·과실이 없는 단순 착오까지 "
            "포괄적 법적 책임으로 이어질 수 있다."
        ),
        "rewrite": (
            "위탁자는 고의 또는 과실로 신청서에 허위·부실 기재를 하거나 시료를 부적합한 "
            "상태로 제공한 경우에 한하여, 그로 인해 수탁자에게 발생한 직접손해를 배상한다."
        ),
        "clause_topic": "damage",
    },
    {
        "id": "tsr_other_lab_dealing_restriction",
        "name": "타 시험기관과의 거래·약정 제한(사전통보)",
        "present": re.compile(
            r"수탁자\s*이외의\s*자.{0,20}(?:시험분석\s*)?약정을?\s*체결.{0,30}사전에.{0,15}통보",
            re.IGNORECASE,
        ),
        "risk": "MEDIUM",
        "direction": "사전통보 의무가 실질적으로 타 시험기관 이용을 제한하는 효과를 갖지 않도록, 통보 거부권이 수탁자에게 없음을 명확히",
        "reason": (
            "위탁자가 다른 시험기관과 유사한 약정을 체결하려면 사전에 통보하도록 하는 조항은, "
            "통보를 조건으로 사실상 거래처 변경을 견제하거나 위탁자의 시험물량 정보가 "
            "특정 시험기관에 집중되는 결과를 가져올 수 있다."
        ),
        "rewrite": (
            "위탁자는 다른 시험기관과 유사한 내용의 약정을 체결하는 경우 이를 참고로 통보할 수 "
            "있으며, 통보 여부 또는 그 내용이 본 약정의 이행이나 조건에 영향을 미치지 아니한다."
        ),
        "clause_topic": "other",
    },
    {
        "id": "tsr_data_reuse_by_lab",
        "name": "수탁자의 위탁자 자료·데이터 연구·분석 활용",
        "present": re.compile(
            r"영업정책의?\s*수립.{0,15}평가.{0,15}(?:연구|분석).{0,20}활용.{0,200}자료\s*등을?\s*사용할\s*수\s*있다",
            re.IGNORECASE,
        ),
        "risk": "MEDIUM",
        "direction": "활용 가능한 자료의 범위(익명화·통계화 여부)와 제3자 제공 금지를 명확히, 위탁자의 사후 활용중단 요청권 확보",
        "reason": (
            "위탁자를 특정할 수 없는 범위라는 단서가 있으나, 실제로 어떤 자료가 '특정되지 않은' "
            "것으로 취급되는지 기준이 없어 시험분석 데이터가 위탁자의 의사와 무관하게 "
            "수탁자의 영업·연구 목적으로 광범위하게 활용될 위험이 있다."
        ),
        "rewrite": (
            "수탁자가 연구·분석 목적으로 활용하는 자료는 위탁자 및 특정 제품을 식별할 수 없도록 "
            "통계적으로 가공된 정보에 한하며, 원본 시험 데이터·시료 정보를 제3자에게 제공하거나 "
            "공개하여서는 아니 된다. 위탁자는 언제든 서면으로 활용 중단을 요청할 수 있다."
        ),
        "clause_topic": "confidentiality",
    },
    {
        "id": "tsr_retest_error_correction_missing",
        "name": "시험결과 오류 시 재시험·정정 절차 부재",
        "present": re.compile(r"재시험|재검사|성적\s*정정|오류\s*수정|재분석", re.IGNORECASE),
        "risk": "MEDIUM",
        "direction": "시험 결과에 오류가 확인된 경우의 재시험/정정 절차와 비용 부담 주체를 명시",
        "reason": (
            "시험 결과에 오류가 있음이 사후에 확인되었을 때의 재시험·정정 절차, 그 비용을 "
            "누가 부담하는지에 관한 규정이 없다. 제6조④·⑤이 수탁자의 시험 오류에 대한 "
            "책임을 사실상 배제하고 있는 것과 결합하면, 위탁자는 오류 있는 성적서로 인한 "
            "피해를 구제받을 절차 자체가 없는 상태가 된다."
        ),
        "rewrite": (
            "시험 결과에 수탁자의 시험 절차상 오류가 있음이 확인된 경우, 수탁자는 위탁자의 "
            "요청에 따라 무상으로 재시험을 실시하고 정정된 성적서를 재발급한다. 재시험에 "
            "소요되는 시료·비용은 수탁자가 부담한다."
        ),
        "clause_topic": "other",
        "is_missing_clause_check": True,
    },
]


def _apply_testing_service_checklist(
    clause_results: list[dict[str, Any]],
    full_text: str,
    contract_class: str,
    clauses: list[ClauseChunk] | None = None,
) -> None:
    """[Layer 2] Testing/inspection/certification service checklist.

    HARD BLOCK: must only run for contract_class == "testing_service".

    The "원문" quote is scoped to the already-confirmed segmentation
    (`clauses`) whenever available, so it can never bleed into an adjacent
    clause/article — a raw whole-document character-offset window (the
    previous behavior) doesn't know where one 항/조 ends and the next
    begins.
    """
    if contract_class != "testing_service":
        return
    text = str(full_text or "")
    existing_ids = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}

    for item in _TSR_ITEMS:
        if item["id"] in existing_ids:
            continue
        is_missing_check = bool(item.get("is_missing_clause_check"))
        if is_missing_check:
            # Inverted: inject the finding when the safeguard is ABSENT anywhere
            # in the document — this is a document-wide absence check, not a
            # quote, so it stays on the raw text (there is no clause to scope to).
            if item["present"].search(text):
                continue
            excerpt = ""
        else:
            scoped = find_clause_scoped_excerpt(clauses, item["present"])
            if scoped is not None:
                excerpt, _art = scoped
            else:
                if clauses:
                    # Segmented clauses exist but none of them matched — trust
                    # the segmentation over a raw full-text scan rather than
                    # risk a cross-clause quote.
                    continue
                m = item["present"].search(text)
                if not m:
                    continue
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 120)
                excerpt = text[start:end].strip()
        risk = item["risk"]
        clause_results.append({
            "clause_id": item["id"],
            "article_number": None,
            "clause_title": f"[시험·검사 용역] {item['name']}",
            "clause_topic": item.get("clause_topic", "other"),
            "original_text": excerpt or f"[{item['name']}] — 계약서에 해당 절차 없음",
            "risk_tier": risk,
            "severity": risk,
            "high_risk": risk == "HIGH",
            "must_fix": risk == "HIGH",
            "approval_required": risk == "HIGH",
            "review_tier": "MUST" if risk == "HIGH" else "SUGGEST",
            "suggested_rewrite": item["rewrite"],
            "rewrite_reason": item["reason"],
            "suggested_direction": [item["direction"]],
            "negotiation_position": "상대방 반발 가능성이 있으나 법적 책임 범위 명확화 차원에서 협상 필요",
            "confidence": 0.8,
            "is_checklist_item": True,
            "has_rewrite_change": True,
            "display_kind": "redline" if risk == "HIGH" else "guidance",
            "dedup_suppressed": False,
            "keep_as_is": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "ai_deep_reviewed": False,
        })
