from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import RULE_STATUS_ENUM, validate_rules_document


DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "resources" / "review_rules_master.json"
)


class RuleLoader:
    def __init__(self, rules_path: Path | None = None) -> None:
        self.rules_path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
        self._doc: dict[str, Any] | None = None

    def load(self, force_reload: bool = False) -> dict[str, Any]:
        if self._doc is not None and not force_reload:
            return self._doc

        if not self.rules_path.exists():
            raise FileNotFoundError(f"rules file not found: {self.rules_path}")

        with self.rules_path.open("r", encoding="utf-8") as f:
            doc = json.load(f)

        errors = validate_rules_document(doc)
        if errors:
            joined = "\n".join(f"- {e}" for e in errors)
            raise ValueError(f"rules schema validation failed:\n{joined}")

        self._doc = doc
        return doc

    def rules_by_status(self) -> dict[str, list[dict[str, Any]]]:
        doc = self.load()
        return doc["rules_by_status"]

    def get_status_rules(self, status: str) -> list[dict[str, Any]]:
        if status not in RULE_STATUS_ENUM:
            raise ValueError(f"unknown status: {status}")
        return self.rules_by_status().get(status, [])

    def decision_rules(self) -> list[dict[str, Any]]:
        """Rules used for judgment (exclude backlog by policy)."""
        rules = []
        for status in (
            "confirmed_standard",
            "confirmed_pattern",
            "exception_possible",
            "approval_required",
        ):
            for rule in self.get_status_rules(status):
                merged = dict(rule)
                merged["rule_status"] = status
                rules.append(merged)
        return rules

    def backlog_rules(self) -> list[dict[str, Any]]:
        rules = []
        for rule in self.get_status_rules("unconfirmed_backlog"):
            merged = dict(rule)
            merged["rule_status"] = "unconfirmed_backlog"
            rules.append(merged)
        return rules

