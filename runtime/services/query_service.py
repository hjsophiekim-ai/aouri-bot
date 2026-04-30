from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.rules.loader import RuleLoader
from runtime.review.jurisdiction import classify_jurisdiction_profile
from runtime.review.user_focus import parse_user_focus_issues


FURSYS_GROUP_ENTITIES = (
    "퍼시스",
    "시디즈",
    "일룸",
    "데스커",
    "바로스",
    "일룸홀딩스",
    "해외법인",
)

TRIGGER_MAP = {
    "ACT-001": ["상호협의", "별도협의", "mutual agreement"],
    "ACT-002": ["사전 서면동의", "prior written consent"],
    "ACT-003": ["정산", "payment", "compensation", "대금"],
    "ACT-004": ["준거법", "관할", "jurisdiction", "governing law"],
    "ACT-005": ["unlimited liability", "without limitation", "무제한 책임"],
    "ACT-006": ["indemnify", "hold harmless", "면책"],
    "ACT-007": ["기술자료", "자료제출", "source code", "원가자료"],
    "ACT-008": ["하도급", "단가 감액", "단가 인하", "price reduction"],
    "ACT-009": ["대리점", "비용부담", "판촉비", "반품 비용", "광고비"],
    "ACT-010": ["안전", "산업안전", "중대재해"],
    "RISK-001": ["unlimited liability", "without limitation", "무제한 책임"],
    "RISK-002": ["indemnify", "hold harmless", "일체 책임 없음", "면책"],
    "RISK-004": ["기술자료", "자료제출", "원가자료", "source code"],
    "RISK-005": ["하도급", "단가 감액", "단가 인하", "price reduction"],
    "RISK-006": ["대리점", "비용부담", "판촉비", "반품 비용", "광고비", "원상회복"],
    "RISK-003": ["안전", "산업안전", "중대재해"],
}


@dataclass
class ReviewInput:
    entity: str
    contract_type: str
    text: str
    filename: str | None = None
    answers: dict[str, Any] | None = None
    review_focus: str | None = None


class RuleQueryService:
    def __init__(self, loader: RuleLoader) -> None:
        self.loader = loader
        self._decision_rules = loader.decision_rules()
        self._backlog_rules = loader.backlog_rules()

    @staticmethod
    def _contains_ci(haystack: str, needle: str) -> bool:
        return needle.lower() in haystack.lower()

    def _any_keyword(self, text: str, keywords: list[str]) -> bool:
        if not text or not keywords:
            return False
        return any(self._contains_ci(text, kw) for kw in keywords)

    def _derive_contract_types_from_text(self, text: str, *, contract_type_hint: str | None = None) -> list[str]:
        out: list[str] = []
        hint = (contract_type_hint or "").strip()
        hint_is_dealer = any(k in hint for k in ("대리점", "유통", "위탁"))
        dealer_in_text = self._any_keyword(text, ["대리점", "dealer", "distributor", "consignment", "위탁거래"])

        strong_app_dev = self._any_keyword(
            text,
            [
                "앱 개발",
                "소프트웨어 개발",
                "시스템 개발",
                "개발 용역",
                "프로그램 개발",
                "소스코드",
                "source code",
                "SaaS",
                "API 연동",
                "API integration",
                "오픈소스",
                "opensource",
                "open source",
                "SBOM",
                "SOW",
                "Statement of Work",
            ],
        )
        if strong_app_dev and not (hint_is_dealer or dealer_in_text):
            out.append("앱개발/소프트웨어개발/SI/유지보수/SaaS")
        if self._any_keyword(text, TRIGGER_MAP.get("ACT-009", []) + TRIGGER_MAP.get("RISK-006", [])):
            out.append("대리점/위탁/유통")
        if self._any_keyword(text, TRIGGER_MAP.get("ACT-008", []) + TRIGGER_MAP.get("RISK-005", [])):
            out.append("공사/도급/하도급")
        if self._any_keyword(text, TRIGGER_MAP.get("ACT-010", []) + TRIGGER_MAP.get("RISK-003", [])):
            out.append("공사/도급/하도급")
            out.append("바로스(물류/설치)")
        if self._any_keyword(text, ["개인정보", "처리위탁", "privacy", "dpa"]):
            out.append("개인정보/처리위탁")
        if self._any_keyword(text, ["광고", "마케팅", "협찬", "marketing", "sponsor", "모델"]):
            out.append("광고/마케팅/협찬")
        return list(dict.fromkeys(out))

    def _entity_match(self, rule_entity: str, input_entity: str) -> bool:
        if rule_entity in ("all", "", "unknown"):
            return True
        if rule_entity == "fursys_group":
            return any(e in input_entity for e in FURSYS_GROUP_ENTITIES) or input_entity == "all"
        return rule_entity in input_entity

    @staticmethod
    def _contract_type_match(rule_types: list[str], input_type: str) -> bool:
        if not rule_types:
            return False
        if "all" in rule_types:
            return True
        return any(rt in input_type or input_type in rt for rt in rule_types)

    def list_rules(
        self,
        status: str | None = None,
        entity: str | None = None,
        contract_type: str | None = None,
        clause_type: str | None = None,
        risk_level: str | None = None,
        include_backlog: bool = False,
    ) -> list[dict[str, Any]]:
        if status == "unconfirmed_backlog":
            base = list(self._backlog_rules)
        elif status:
            base = [r for r in self._decision_rules if r["rule_status"] == status]
        else:
            base = list(self._decision_rules)
            if include_backlog:
                base.extend(self._backlog_rules)

        if entity:
            base = [r for r in base if self._entity_match(r["entity"], entity)]
        if contract_type:
            base = [r for r in base if self._contract_type_match(r["contract_type"], contract_type)]
        if clause_type:
            ct = clause_type.strip()
            if ct:
                base = [r for r in base if ct in str(r.get("clause_type") or "")]
        if risk_level:
            rl = risk_level.strip().lower()
            if rl:
                base = [r for r in base if str(r.get("risk_level") or "").strip().lower() == rl]
        return base

    def list_backlog(self) -> list[dict[str, Any]]:
        return list(self._backlog_rules)

    def _extract_trigger_keywords(self, rule: dict[str, Any]) -> list[str]:
        rule_id = rule.get("rule_id", "")
        if rule_id in TRIGGER_MAP:
            return TRIGGER_MAP[rule_id]

        out: list[str] = []
        for tag in rule.get("tags", []):
            if tag.startswith("trigger:"):
                out.append(tag.split(":", 1)[1].replace("_", " "))
        phrase = rule.get("contract_evidence", {}).get("example_phrase")
        if isinstance(phrase, str) and phrase.strip():
            out.append(phrase.strip())
        return out

    def analyze(self, review_input: ReviewInput) -> dict[str, Any]:
        answers = review_input.answers or {}
        entity_input = review_input.entity or "all"
        contract_type_input = review_input.contract_type or "all"
        text = review_input.text or ""

        if answers.get("Q-002-overseas") == "yes":
            entity_input = f"{entity_input} 해외법인"

        additional_contract_types_by_questions: list[str] = []
        if answers.get("Q-003-personal-data") == "yes":
            additional_contract_types_by_questions.append("개인정보/처리위탁")
        if answers.get("Q-006-subcontract") == "yes":
            additional_contract_types_by_questions.append("공사/도급/하도급")
        if answers.get("Q-007-dealer") == "yes":
            additional_contract_types_by_questions.append("대리점/위탁/유통")
        if answers.get("Q-009-ad-model") == "yes":
            additional_contract_types_by_questions.append("광고/마케팅/협찬")

        additional_contract_types_by_text = self._derive_contract_types_from_text(text, contract_type_hint=contract_type_input)
        jur = classify_jurisdiction_profile(text=text, entity=entity_input, contract_type=contract_type_input, filename=review_input.filename)
        focus = parse_user_focus_issues(review_input.review_focus)

        base_applicable = self.list_rules(
            entity=entity_input,
            contract_type=contract_type_input,
            include_backlog=False,
        )

        expanded: dict[str, dict[str, Any]] = {r["rule_id"]: r for r in base_applicable if "rule_id" in r}
        expanded_by_questions: set[str] = set()
        for ct in additional_contract_types_by_questions:
            for r in self.list_rules(entity=entity_input, contract_type=ct, include_backlog=False):
                rid = r.get("rule_id")
                if not isinstance(rid, str):
                    continue
                if rid not in expanded:
                    expanded[rid] = r
                    expanded_by_questions.add(rid)

        expanded_by_text: set[str] = set()
        for ct in additional_contract_types_by_text:
            for r in self.list_rules(entity=entity_input, contract_type=ct, include_backlog=False):
                rid = r.get("rule_id")
                if not isinstance(rid, str):
                    continue
                if rid not in expanded:
                    expanded[rid] = r
                    expanded_by_text.add(rid)

        applicable = list(expanded.values())

        matched_rules: list[dict[str, Any]] = []
        checklist_rules: list[dict[str, Any]] = []

        for rule in applicable:
            rule_status = rule["rule_status"]
            trigger_keywords = self._extract_trigger_keywords(rule)
            is_trigger_rule = bool(trigger_keywords)

            if not is_trigger_rule:
                checklist_rules.append(rule)
                continue

            if any(self._contains_ci(text, kw) for kw in trigger_keywords):
                rid = rule.get("rule_id")
                if rid in expanded_by_questions or rid in expanded_by_text:
                    rule = dict(rule)
                    if rid in expanded_by_questions:
                        rule["context_expanded_by_questions"] = True
                    if rid in expanded_by_text:
                        rule["context_expanded_by_text"] = True
                if rid == "ACT-004" and jur.kind == "domestic_korea":
                    rule = dict(rule)
                    ct0 = str(contract_type_input or "")
                    is_dealer0 = any(k in ct0 for k in ("대리점", "유통", "위탁"))
                    focus_txt = str(review_input.review_focus or "")
                    wants_dispute = any(k in focus_txt for k in ("관할", "준거법", "분쟁", "중재", "조정"))
                    if is_dealer0 and not wants_dispute:
                        rule["risk_level"] = "LOW"
                        rule["title"] = "분쟁조항(보조) 점검"
                        rule["description"] = "국내 대리점 계약의 관할/준거법은 기본값으로 보되, 핵심 이슈 검토 후 보조적으로 전속관할/합의관할 구조만 요약 점검한다."
                        rule["summary_suppress"] = True
                        rule["supplemental_only"] = True
                    else:
                        rule["risk_level"] = "MEDIUM"
                        rule["title"] = "국내 계약 분쟁조항 점검"
                        rule["description"] = "국내 거래의 분쟁해결/재판관할 조항은 전속관할/합의관할/민사소송법상 관할 구조를 중심으로 점검한다."
                matched_rules.append(rule)
            elif rule_status == "confirmed_standard":
                rid = rule.get("rule_id")
                if rid in expanded_by_questions or rid in expanded_by_text:
                    rule = dict(rule)
                    if rid in expanded_by_questions:
                        rule["context_expanded_by_questions"] = True
                    if rid in expanded_by_text:
                        rule["context_expanded_by_text"] = True
                checklist_rules.append(rule)

        is_dealer = any(k in str(contract_type_input or "") for k in ("대리점", "유통", "위탁"))
        has_strong_app_dev = self._any_keyword(
            text,
            [
                "앱 개발",
                "소프트웨어 개발",
                "시스템 개발",
                "개발 용역",
                "프로그램 개발",
                "소스코드",
                "source code",
                "SaaS",
                "API 연동",
                "API integration",
                "오픈소스",
                "opensource",
                "open source",
                "SBOM",
                "SOW",
                "Statement of Work",
            ],
        )
        if is_dealer and not has_strong_app_dev:
            matched_rules = [r for r in matched_rules if not str(r.get("rule_id") or "").startswith("APP-")]
            checklist_rules = [r for r in checklist_rules if not str(r.get("rule_id") or "").startswith("APP-")]

        approval_required_matches = [
            r for r in matched_rules if r["rule_status"] == "approval_required" or r["approval_required"]
        ]
        high_risk_matches = [
            r
            for r in matched_rules
            if str(r.get("risk_level") or "").strip().lower() in ("high", "very_high", "critical")
        ]
        approval_required_flag = len(approval_required_matches) > 0
        high_risk_flag = len(high_risk_matches) > 0

        return {
            "input": {
                "entity": entity_input,
                "contract_type": contract_type_input,
                "filename": review_input.filename,
                "review_focus": (review_input.review_focus or None),
            },
            "question_answers": dict(answers),
            "derived_context": {
                "additional_contract_types_by_questions": additional_contract_types_by_questions,
                "additional_contract_types_by_text": additional_contract_types_by_text,
                "expanded_rule_count": len(expanded_by_questions) + len(expanded_by_text),
                "jurisdiction": jur.to_dict(),
                "user_focus_issues": [x.to_dict() for x in focus],
            },
            "summary": {
                "applicable_rule_count": len(applicable),
                "matched_rule_count": len(matched_rules),
                "checklist_rule_count": len(checklist_rules),
                "approval_required_match_count": len(approval_required_matches),
                "high_risk_match_count": len(high_risk_matches),
                "approval_required": approval_required_flag,
                "high_risk": high_risk_flag,
                "backlog_reference_count": len(self._backlog_rules),
            },
            "matched_rules": matched_rules,
            "checklist_rules": checklist_rules,
            "approval_required_matches": approval_required_matches,
            "backlog_reference_only": self._backlog_rules,
            "policy_note": "판정에는 confirmed 계열 rule만 사용하며, backlog는 참고용으로만 표시한다.",
        }

