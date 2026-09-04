from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.review.jurisdiction import JurisdictionProfile, classify_jurisdiction_profile
from runtime.review.priority_map import ContractProfile, infer_contract_profile
from runtime.review.user_focus import UserFocusObjective, derive_focus_objectives_from_answers, parse_user_focus_issues
from runtime.review.contract_classifier import (
    ContractProfile as DetailedContractProfile,
    classify_contract_detailed,
)
from runtime.review.canonical_transaction_facts import build_canonical_transaction_facts_from_answers


@dataclass(frozen=True)
class FinalReviewContext:
    user_focus_issues: list[UserFocusObjective]
    review_objectives: list[UserFocusObjective]
    factual_answers: dict[str, Any]
    canonical_transaction_facts: dict[str, Any]
    party_role: dict[str, Any] | None
    expert_mode: bool
    expert_strategy: list[str]
    is_counterparty_form: bool | None
    jurisdiction: JurisdictionProfile
    contract_profile: ContractProfile
    detailed_contract_profile: DetailedContractProfile | None

    def to_dict(self) -> dict[str, Any]:
        base = {
            "user_focus_issues": [x.to_dict() for x in self.user_focus_issues],
            "review_objectives": [x.to_dict() for x in self.review_objectives],
            "factual_answers": dict(self.factual_answers or {}),
            # canonical_transaction_facts(2026-09-04 지시) — UI가 원문을
            # 다시 보고 seller/owner_of_goods 등을 재추정하지 않도록, 이미
            # 구조화된 사실관계를 그대로 노출한다.
            "canonical_transaction_facts": dict(self.canonical_transaction_facts or {}),
            "party_role": self.party_role,
            "expert_mode": bool(self.expert_mode),
            "expert_strategy": list(self.expert_strategy or []),
            "is_counterparty_form": self.is_counterparty_form,
            "jurisdiction": self.jurisdiction.to_dict(),
            "contract_profile": self.contract_profile.to_dict(),
        }
        if self.detailed_contract_profile is not None:
            base["detailed_contract_profile"] = self.detailed_contract_profile.to_dict()
        return base


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

    # canonical 분류(classify_contract_detailed)를 먼저 계산해, 뒤이은
    # infer_contract_profile()이 raw contract_type 라벨 대신 이 값을
    # 우선 신뢰하도록 한다(2026-09-01) — 이전엔 이 함수가 detailed_prof를
    # infer_contract_profile() 호출 18줄 뒤에 계산해놓고도 넘겨주지 않아,
    # canonical 값이 바로 옆에 있는데도 쓰이지 못하고 있었다.
    detailed_prof: DetailedContractProfile | None = None
    try:
        detailed_prof = classify_contract_detailed(
            entity=entity,
            contract_type=contract_type,
            text=text,
            filename=filename,
        )
    except Exception:
        pass

    prof = infer_contract_profile(
        contract_type=contract_type, text=text,
        canonical_type_code=(detailed_prof.contract_type if detailed_prof is not None else ""),
    )

    from runtime.review.contract_classifier import is_fursys_group
    expert_mode = is_fursys_group(entity or "")
    # [REMOVED] expert_strategy 포지션 자동 추론 비활성화 — requirement.md Section Removal Specs 참조
    expert_strategy: list[str] = []

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
        canonical_transaction_facts=build_canonical_transaction_facts_from_answers(ans),
        party_role=party_role,
        expert_mode=expert_mode,
        expert_strategy=expert_strategy,
        is_counterparty_form=is_form,
        jurisdiction=jur,
        contract_profile=prof,
        detailed_contract_profile=detailed_prof,
    )
