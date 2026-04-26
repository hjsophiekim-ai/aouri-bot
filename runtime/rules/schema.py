from __future__ import annotations

from typing import Any


RULE_STATUS_ENUM = {
    "confirmed_standard",
    "confirmed_pattern",
    "exception_possible",
    "approval_required",
    "unconfirmed_backlog",
}

TOP_LEVEL_REQUIRED = {
    "schema_version",
    "generated_at",
    "source_documents",
    "status_enum",
    "rules_by_status",
}

RULE_REQUIRED_FIELDS = {
    "rule_id",
    "entity",
    "contract_type",
    "clause_type",
    "rule_level",
    "title",
    "description",
    "contract_evidence",
    "risk_level",
    "review_action",
    "approval_required",
    "tags",
}


def _is_list_of_str(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate_rules_document(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not isinstance(doc, dict):
        return ["rules document must be a JSON object"]

    for key in TOP_LEVEL_REQUIRED:
        if key not in doc:
            errors.append(f"missing top-level field: {key}")

    status_enum = doc.get("status_enum")
    if not _is_list_of_str(status_enum):
        errors.append("status_enum must be a list of strings")
    else:
        unknown = set(status_enum) - RULE_STATUS_ENUM
        missing = RULE_STATUS_ENUM - set(status_enum)
        if unknown:
            errors.append(f"status_enum includes unknown values: {sorted(unknown)}")
        if missing:
            errors.append(f"status_enum misses required values: {sorted(missing)}")

    rules_by_status = doc.get("rules_by_status")
    if not isinstance(rules_by_status, dict):
        errors.append("rules_by_status must be an object")
        return errors

    for status in RULE_STATUS_ENUM:
        rules = rules_by_status.get(status)
        if not isinstance(rules, list):
            errors.append(f"rules_by_status.{status} must be a list")
            continue
        for idx, rule in enumerate(rules):
            prefix = f"rules_by_status.{status}[{idx}]"
            if not isinstance(rule, dict):
                errors.append(f"{prefix} must be an object")
                continue
            missing_fields = RULE_REQUIRED_FIELDS - set(rule.keys())
            if missing_fields:
                errors.append(f"{prefix} missing fields: {sorted(missing_fields)}")
                continue
            if not isinstance(rule["rule_id"], str):
                errors.append(f"{prefix}.rule_id must be string")
            if not isinstance(rule["entity"], str):
                errors.append(f"{prefix}.entity must be string")
            if not _is_list_of_str(rule["contract_type"]):
                errors.append(f"{prefix}.contract_type must be list[str]")
            if not isinstance(rule["clause_type"], str):
                errors.append(f"{prefix}.clause_type must be string")
            if not isinstance(rule["rule_level"], str):
                errors.append(f"{prefix}.rule_level must be string")
            if not isinstance(rule["title"], str):
                errors.append(f"{prefix}.title must be string")
            if not isinstance(rule["description"], str):
                errors.append(f"{prefix}.description must be string")
            if not isinstance(rule["contract_evidence"], dict):
                errors.append(f"{prefix}.contract_evidence must be object")
            if not isinstance(rule["risk_level"], str):
                errors.append(f"{prefix}.risk_level must be string")
            if not _is_list_of_str(rule["review_action"]):
                errors.append(f"{prefix}.review_action must be list[str]")
            if not isinstance(rule["approval_required"], bool):
                errors.append(f"{prefix}.approval_required must be bool")
            if not _is_list_of_str(rule["tags"]):
                errors.append(f"{prefix}.tags must be list[str]")

    return errors

