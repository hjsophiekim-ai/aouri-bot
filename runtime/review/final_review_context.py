from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.review.jurisdiction import JurisdictionProfile, classify_jurisdiction_profile
from runtime.review.priority_map import ContractProfile, infer_contract_profile
from runtime.review.user_focus import UserFocusObjective, derive_focus_objectives_from_answers, parse_user_focus_issues


@dataclass(frozen=True)
class FinalReviewContext:
    user_focus_issues: list[UserFocusObjective]
    review_objectives: list[UserFocusObjective]
    factual_answers: dict[str, Any]
    party_role: dict[str, Any] | None
    expert_mode: bool
    expert_strategy: list[str]
    is_counterparty_form: bool | None
    jurisdiction: JurisdictionProfile
    contract_profile: ContractProfile

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_focus_issues": [x.to_dict() for x in self.user_focus_issues],
            "review_objectives": [x.to_dict() for x in self.review_objectives],
            "factual_answers": dict(self.factual_answers or {}),
            "party_role": self.party_role,
            "expert_mode": bool(self.expert_mode),
            "expert_strategy": list(self.expert_strategy or []),
            "is_counterparty_form": self.is_counterparty_form,
            "jurisdiction": self.jurisdiction.to_dict(),
            "contract_profile": self.contract_profile.to_dict(),
        }


def build_final_review_context(
    *,
    entity: str,
    contract_type: str,
    text: str,
    filename: str | None,
    answers: dict[str, Any] | None,
    review_focus: str | None,
    party_role: dict[str, Any] | None,
) -> FinalReviewContext:
    ans = dict(answers or {})
    focus = parse_user_focus_issues(review_focus)
    derived = derive_focus_objectives_from_answers(ans)
    merged: dict[str, UserFocusObjective] = {}
    for o in (focus + derived):
        merged[o.code] = o
    review_objectives = list(merged.values())
    jur = classify_jurisdiction_profile(text=text, entity=entity, contract_type=contract_type, filename=filename)
    prof = infer_contract_profile(contract_type=contract_type, text=text)

    expert_mode = "퍼시스" in (entity or "")
    expert_strategy: list[str] = []
    if expert_mode:
        our_role = str((party_role or {}).get("our_role") or "")
        if our_role == "supplier" or prof.profile == "dealer_consignment":
            expert_strategy = [
                "대리점법상 경영간섭·가격강제 리스크를 피하면서도, 채권 회수(정산/상계/증빙) 구조를 명확히 한다.",
                "해지/불이익 조치의 남용으로 보이지 않도록, 객관적 요건·절차(서면 최고/시정기회)를 중심으로 정교화한다.",
            ]
        elif our_role == "contractor":
            expert_strategy = [
                "퍼시스는 수급인(을) 포지션을 전제로, 도급인의 일방적 해지/공제권을 축소하고 수급인의 대금 수령/면책 범위를 확대한다.",
                "지체상금이 일 0.3% 수준으로 과도한 경우, 일 0.1% 이하로 조정하고 공기 연장(발주자 귀책·의사결정 지연·자료 미제공·현장 인도 지연·변경지시)을 함께 확보한다.",
                "상계/공제는 확정 채권 및 사전 서면 합의가 있는 경우로 제한하고, 정산서·증빙 제공 및 이의제기 절차를 포함한다.",
                "해지는 원칙적으로 30일 이상의 서면 최고 및 시정기간을 부여하고, 예외적 즉시해지는 신뢰관계를 본질적으로 훼손하는 중대한 위반으로 좁게 열거한다.",
                "안전관리 조항은 수급인 일방 책임 전가를 배제하고, 발주자 제공 자료/현장 하자 등 발주자 귀책 사유에 대한 면책·감경 및 상호 협력 구조를 명시한다.",
            ]
        else:
            expert_strategy = [
                "실제 손실 또는 법적 제재로 이어지는 독소조항(금전/권리/규제)만 우선 검토한다.",
                "중복 코멘트 없이 핵심 조항에서만 수정안을 제시한다.",
            ]

    is_form = None
    for k in ("Q-DL-001-form", "Q-000-form", "Q-001-counterparty-form"):
        v = ans.get(k)
        if isinstance(v, str):
            if v == "yes":
                is_form = True
            if v == "no":
                is_form = False
    return FinalReviewContext(
        user_focus_issues=focus,
        review_objectives=review_objectives,
        factual_answers=ans,
        party_role=party_role,
        expert_mode=expert_mode,
        expert_strategy=expert_strategy,
        is_counterparty_form=is_form,
        jurisdiction=jur,
        contract_profile=prof,
    )
