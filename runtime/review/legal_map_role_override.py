"""Wires Layer 0 (Contract Legal Map) as the priority source of truth for
our-side role DIRECTION, overriding the rule-based classifier/party_role
result when they disagree and the AI is confident (변호사형 전체계약 판단
지시 후속, 2026-09-01 — 8건 hold-out 검증에서 처음 보는 계약유형(라이선스,
임대차 등)에 대해 rule 기반 classifier가 당사자 방향을 반대로 판정하는
사례가 발견된 후 요청됨).

Deliberately narrow in scope: only the PROVIDER/RECIPIENT axis is
overridden. This is the one dimension actually proven to change review
output — `_apply_do_not_harm_our_side_gate`, `_apply_supplier_product_
checklist`, and `infer_review_posture` (all in party_role.py /
clause_level.py) key off exactly this axis via
`party.our_role in ("buyer", "ordering_party")` vs
`("seller", "supplier", "contractor", "rental_provider")`.
`contract_type_code` itself and `_contract_class` (used for Layer-2
checklist routing / HARD BLOCK) are NOT touched here — overriding those
reliably would require the AI to emit a full type_code from the same large,
still-evolving enum the rule classifier uses, which is a bigger, separate
follow-up left undone by design.

The override never fires unless the AI was actually called
(`legal_map_source == "ai"`) and confidently disagreed with the polarity
the rule classifier/party_role already inferred — every existing test that
uses a stub AI provider (without these two new fields) or no AI provider at
all is completely unaffected, since the new fields are simply absent.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from runtime.review.party_role import PartyRole

logger = logging.getLogger(__name__)

_PROVIDER_ROLES = frozenset({"seller", "supplier", "contractor", "rental_provider"})
_RECIPIENT_ROLES = frozenset({"buyer", "ordering_party"})


def _polarity_of(our_role: str | None) -> str | None:
    r = (our_role or "").strip().lower()
    if r in _PROVIDER_ROLES:
        return "provider"
    if r in _RECIPIENT_ROLES:
        return "recipient"
    return None  # party/client/neutral/unknown 등 — 방향성 없음, override 대상 아님


def apply_legal_map_role_override(
    *,
    canonical_profile: Any,
    party: PartyRole,
    legal_map_dict: dict[str, Any],
    legal_map_source: str,
) -> tuple[Any, PartyRole, dict[str, Any] | None]:
    """Return (possibly-updated canonical_profile, possibly-updated party,
    an audit record dict — or None if nothing was overridden)."""
    if legal_map_source != "ai":
        return canonical_profile, party, None

    ai_direction = legal_map_dict.get("our_role_direction")
    ai_confidence = str(legal_map_dict.get("our_role_direction_confidence") or "").strip().lower()
    if ai_direction not in ("provider", "recipient") or ai_confidence != "high":
        return canonical_profile, party, None

    existing_polarity = _polarity_of(party.our_role)
    if existing_polarity == ai_direction:
        return canonical_profile, party, None  # 이미 일치 — 덮어쓸 필요 없음

    if ai_direction == "provider":
        new_our_role, new_cp_role = "supplier", "buyer"
    else:
        new_our_role, new_cp_role = "buyer", "seller_or_supplier"

    audit = {
        "stage": "legal_map_role_override",
        "previous_our_role": party.our_role,
        "previous_counterparty_role": party.counterparty_role,
        "previous_polarity": existing_polarity,
        "overridden_our_role": new_our_role,
        "overridden_counterparty_role": new_cp_role,
        "legal_map_confidence": ai_confidence,
    }
    logger.warning("legal_map_role_override applied: %s", audit)

    new_party = replace(party, our_role=new_our_role, counterparty_role=new_cp_role)

    try:
        canonical_profile.our_legal_role = new_our_role
        canonical_profile.counterparty_legal_role = new_cp_role
        canonical_profile.our_role_bucket = new_our_role
        canonical_profile.counterparty_role_bucket = new_cp_role
        canonical_profile.reasons = list(canonical_profile.reasons) + ["legal_map_role_override"]
    except Exception:
        pass

    return canonical_profile, new_party, audit
