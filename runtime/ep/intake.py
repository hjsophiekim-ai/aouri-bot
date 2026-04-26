from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EPIntake:
    ep_request_id: str | None
    entity: str | None
    contract_type: str | None
    counterparty: str | None
    purpose: str | None
    amount: str | None
    term_start: str | None
    term_end: str | None
    attachment_names: list[str]


def validate_ep_intake(obj: Any) -> tuple[EPIntake | None, list[str]]:
    errors: list[str] = []
    if not isinstance(obj, dict):
        return None, ["intake must be an object"]

    def s(key: str) -> str | None:
        v = obj.get(key)
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            errors.append(f"{key} must be string")
            return None
        return v

    ep_request_id = s("ep_request_id")
    entity = s("entity")
    contract_type = s("contract_type")
    counterparty = s("counterparty")
    purpose = s("purpose")
    amount = s("amount")
    term_start = s("term_start")
    term_end = s("term_end")

    attachment_names: list[str] = []
    an = obj.get("attachment_names", [])
    if an is None:
        an = []
    if not isinstance(an, list) or any(not isinstance(x, str) for x in an):
        errors.append("attachment_names must be list[str]")
    else:
        attachment_names = an

    intake = EPIntake(
        ep_request_id=ep_request_id,
        entity=entity,
        contract_type=contract_type,
        counterparty=counterparty,
        purpose=purpose,
        amount=amount,
        term_start=term_start,
        term_end=term_end,
        attachment_names=attachment_names,
    )
    return intake, errors


def intake_to_dict(intake: EPIntake) -> dict[str, Any]:
    return {
        "ep_request_id": intake.ep_request_id,
        "entity": intake.entity,
        "contract_type": intake.contract_type,
        "counterparty": intake.counterparty,
        "purpose": intake.purpose,
        "amount": intake.amount,
        "term_start": intake.term_start,
        "term_end": intake.term_end,
        "attachment_names": list(intake.attachment_names),
    }

