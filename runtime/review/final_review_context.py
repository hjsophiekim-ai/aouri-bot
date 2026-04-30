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
    is_counterparty_form: bool | None
    jurisdiction: JurisdictionProfile
    contract_profile: ContractProfile

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_focus_issues": [x.to_dict() for x in self.user_focus_issues],
            "review_objectives": [x.to_dict() for x in self.review_objectives],
            "factual_answers": dict(self.factual_answers or {}),
            "party_role": self.party_role,
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
        is_counterparty_form=is_form,
        jurisdiction=jur,
        contract_profile=prof,
    )
