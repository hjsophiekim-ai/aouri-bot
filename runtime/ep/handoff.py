from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ApprovalHandoffPayload:
    handoff_id: str
    idempotency_key: str
    ep_request_id: str
    aouribot_request_id: str
    entity: str
    contract_type: str
    approval_required: bool
    high_risk: bool
    counts: dict[str, int]
    issues: list[dict[str, Any]]


def build_handoff_payload(
    ep_request_id: str,
    review_detail: dict[str, Any],
) -> ApprovalHandoffPayload:
    req = review_detail.get("request") or {}
    res = review_detail.get("result") or {}
    issues = review_detail.get("issues") or []

    high_risk_count = int(res.get("high_risk_count") or 0)
    approval_required_count = int(res.get("approval_required_count") or 0)

    request_id = str(req.get("request_id") or "")
    return ApprovalHandoffPayload(
        handoff_id=uuid4().hex,
        idempotency_key=f"{ep_request_id}:{request_id}",
        ep_request_id=ep_request_id,
        aouribot_request_id=request_id,
        entity=str(req.get("entity") or ""),
        contract_type=str(req.get("contract_type") or ""),
        approval_required=approval_required_count > 0,
        high_risk=high_risk_count > 0,
        counts={
            "high_risk_count": high_risk_count,
            "approval_required_count": approval_required_count,
            "issue_count": len(issues) if isinstance(issues, list) else 0,
        },
        issues=issues if isinstance(issues, list) else [],
    )


def payload_to_dict(p: ApprovalHandoffPayload) -> dict[str, Any]:
    return {
        "handoff_id": p.handoff_id,
        "idempotency_key": p.idempotency_key,
        "ep_request_id": p.ep_request_id,
        "aouribot_request_id": p.aouribot_request_id,
        "entity": p.entity,
        "contract_type": p.contract_type,
        "approval_required": p.approval_required,
        "high_risk": p.high_risk,
        "counts": dict(p.counts),
        "issues": list(p.issues),
        "integration_mode": "stub",
        "next_system": "approval_system_stub",
    }

