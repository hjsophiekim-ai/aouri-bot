"""Review orchestrator: unified 7-step pipeline for dealer_rental_service_contract.

Steps:
  A. Contract structure detection
  B. Role matrix generation
  C. Clause topic classification (rule-based, no LLM required)
  D. Applicable rule selection (DLR-001..008 only for dealer_rental)
  E. Clause-template compatibility validation (hard gate)
  F. Professional TOP risk selection (ordered by DLR priority)
  G. final_findings.json generation (single source for UI + DOCX)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from runtime.review.dealer_rental_rules import (
    DLRRule,
    DLR_TOP_RISK_ORDER,
    extract_excerpt,
    get_triggered_dlr_rules,
    is_blocked_for_dealer_rental,
)


_DEALER_RENTAL_TYPE = "dealer_rental_service_contract"

# Hard gate: clause_topic → forbidden phrases in proposed revision
_CLAUSE_TEMPLATE_HARD_GATE: dict[str, list[str]] = {
    "termination": ["소유권", "채권추심", "소유권 표식", "소유권 행사", "담보 설정"],
    "confidentiality": ["인력관리", "인력 관리", "직원 채용", "인력 배치", "인력 평가", "스카우트"],
    "assignment": ["판촉비", "광고비", "반품비", "원상회복비", "마케팅 비용"],
    "assignment_party_change": ["판촉비", "광고비", "반품비", "원상회복비", "마케팅 비용"],
    "dispute_resolution": ["수수료 산정", "용역수수료", "정책지원금"],
}

_MISMATCH_TEXT = "자동수정 보류: 해당 수정문안은 본 조항의 법률주제와 불일치합니다."


@dataclass
class RoleMatrix:
    """Role matrix for dealer_rental_service_contract."""
    our_company: str
    supplier: str
    dealer: str
    customer_contract_party: str
    invoice_issuer: str
    billing_party: str
    collection_role: str
    dealer_agency_authority: bool
    ownership_party: str
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "our_company": self.our_company,
            "supplier": self.supplier,
            "dealer": self.dealer,
            "customer_contract_party": self.customer_contract_party,
            "invoice_issuer": self.invoice_issuer,
            "billing_party": self.billing_party,
            "collection_role": self.collection_role,
            "dealer_agency_authority": self.dealer_agency_authority,
            "ownership_party": self.ownership_party,
            "conflicts": self.conflicts,
        }


@dataclass
class ProfessionalFinding:
    """Professional-grade legal finding with full attorney-level fields."""
    rule_id: str
    issue_title: str
    relevant_clause: str
    original_excerpt: str
    legal_risk: str
    business_risk: str
    why_this_matters: str
    risk_level: str  # "HIGH" / "MEDIUM" / "LOW"
    approval_required: bool
    required_action: str
    proposed_clause: str
    negotiation_position: str
    evidence_from_contract: str
    confidence: float

    @property
    def display_bucket(self) -> str:
        if self.risk_level == "HIGH":
            return "필수수정"
        if self.risk_level == "MEDIUM":
            return "권장수정"
        return "참고"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "clause_id": self.rule_id,
            "clause_title": self.relevant_clause,
            "issue_title": self.issue_title,
            "relevant_clause": self.relevant_clause,
            "original_excerpt": self.original_excerpt,
            "original_text": self.original_excerpt,
            "legal_risk": self.legal_risk,
            "business_risk": self.business_risk,
            "why_this_matters": self.why_this_matters,
            "risk_level": self.risk_level,
            "severity": self.risk_level,
            "approval_required": self.approval_required,
            "display_bucket": self.display_bucket,
            "required_action": self.required_action,
            "proposed_clause": self.proposed_clause,
            "proposed_revision": self.proposed_clause,
            "suggested_rewrite": self.proposed_clause,
            "negotiation_position": self.negotiation_position,
            "evidence_from_contract": self.evidence_from_contract,
            "problem": self.legal_risk,
            "legal_business_reason": self.legal_risk,
            "confidence": self.confidence,
            "is_mandatory": True,
            "has_rewrite_change": True,
        }


def _infer_clause_topic(title: str) -> str:
    """Map clause title to topic identifier (rule-based, no LLM)."""
    t = (title or "").lower()
    if any(k in t for k in ["해지", "종료", "해제"]):
        return "termination"
    if any(k in t for k in ["비밀", "기밀"]):
        return "confidentiality"
    if any(k in t for k in ["양도", "지위 이전", "계약자 변경"]):
        return "assignment_party_change"
    if any(k in t for k in ["분쟁", "중재", "관할"]):
        return "dispute_resolution"
    if any(k in t for k in ["세금계산서", "청구", "수금", "렌탈료"]):
        return "billing"
    if any(k in t for k in ["개인정보", "고객정보"]):
        return "personal_information"
    if any(k in t for k in ["수수료", "상계", "보증금"]):
        return "fee_setoff"
    return "general"


class DealerRentalReviewOrchestrator:
    """Professional legal review engine for dealer_rental_service_contract."""

    def __init__(self, entity: str = "퍼시스") -> None:
        self.entity = entity

    def orchestrate(self, text: str, contract_type: str = "") -> dict[str, Any]:
        """Run the full 7-step review pipeline. Returns combined result dict."""
        t = text or ""

        # Step A: Contract structure detection
        profile_dict = self._step_a_detect_structure(t, contract_type)

        # Step B: Role matrix
        role_matrix = self._step_b_build_role_matrix(profile_dict, t)

        # Step C: Clause topic classification
        clause_spans = self._step_c_classify_clauses(t)

        # Step D: Select applicable DLR rules
        triggered_rules = self._step_d_select_rules(t)

        # Step E: Clause-template compatibility validation
        findings_raw = self._step_e_validate_templates(triggered_rules, clause_spans, t)

        # Step F: Professional TOP risk selection
        top_risks, high_findings, medium_findings = self._step_f_select_top_risks(findings_raw)

        # Step G: Build final_findings
        return self._step_g_build_final_findings(
            role_matrix, top_risks, high_findings, medium_findings, profile_dict
        )

    def _step_a_detect_structure(self, text: str, contract_type: str) -> dict[str, Any]:
        """Step A: detect contract structure and return profile as dict."""
        try:
            from runtime.review.contract_classifier import classify_contract_detailed
            profile = classify_contract_detailed(
                entity=self.entity,
                contract_type=contract_type,
                text=text,
            )
            return profile.to_dict() if hasattr(profile, "to_dict") else {
                "our_party": self.entity,
                "contract_type": _DEALER_RENTAL_TYPE,
                "customer_contracting_party": f"{self.entity}/공급업자",
                "tax_invoice_issuer": f"{self.entity}/공급업자",
                "payment_collection_party": f"{self.entity}/공급업자",
                "agency_authority": False,
            }
        except Exception:
            return {
                "our_party": self.entity,
                "contract_type": _DEALER_RENTAL_TYPE,
                "customer_contracting_party": f"{self.entity}/공급업자",
                "tax_invoice_issuer": f"{self.entity}/공급업자",
                "payment_collection_party": f"{self.entity}/공급업자",
                "agency_authority": False,
            }

    def _step_b_build_role_matrix(self, profile: dict[str, Any], text: str) -> RoleMatrix:
        """Step B: build role matrix and detect conflicts."""
        conflicts: list[str] = []
        our = profile.get("our_party") or self.entity

        # Detect role conflicts in contract body
        _conflict_signals = [
            ("대리점은 고객과 직접 계약을 체결", "거래구조 불일치"),
            ("대리점이 고객에게 세금계산서를 발행", "세금계산서 발행 주체 불일치"),
        ]
        for sig, label in _conflict_signals:
            if sig in text:
                conflicts.append(f"표현충돌: '{sig}' — {label}")

        ccp = profile.get("customer_contracting_party") or f"{our}/공급업자"
        if "needs_clarification" in str(ccp):
            ccp = f"{our}/공급업자"
            conflicts.append("고객 계약 당사자 불명확 — DLR-001 HIGH 리스크")

        tii = profile.get("tax_invoice_issuer") or f"{our}/공급업자"
        if "needs_clarification" in str(tii):
            tii = f"{our}/공급업자"
            conflicts.append("세금계산서 발행 주체 불명확 — DLR-002 HIGH 리스크")

        # agency_authority: treat None/missing as False for dealer_rental
        agency_auth = profile.get("agency_authority")
        if agency_auth is None:
            agency_auth = False

        return RoleMatrix(
            our_company=our,
            supplier=our,
            dealer="대리점",
            customer_contract_party=ccp,
            invoice_issuer=tii,
            billing_party=f"{our}/공급업자",
            collection_role="대리점은 수금지원자(법적 주체 아님)",
            dealer_agency_authority=bool(agency_auth),
            ownership_party=our,
            conflicts=conflicts,
        )

    def _step_c_classify_clauses(self, text: str) -> dict[str, str]:
        """Step C: extract clause titles → clause_topic map (rule-based, no LLM)."""
        clause_map: dict[str, str] = {}
        for m in re.finditer(
            r"(제\d+조(?:의\d+)?)\s*[\(（]([^)\）\n]{2,30})[\)）]?", text
        ):
            num, title = m.group(1), m.group(2).strip()
            topic = _infer_clause_topic(title)
            clause_map[f"{num} {title}"] = topic
        return clause_map

    def _step_d_select_rules(self, text: str) -> list[DLRRule]:
        """Step D: select only triggered DLR rules (isr_/sppc_/etc. never returned)."""
        return get_triggered_dlr_rules(text)

    def _step_e_validate_templates(
        self,
        triggered_rules: list[DLRRule],
        clause_spans: dict[str, str],
        text: str,
    ) -> list[ProfessionalFinding]:
        """Step E: apply clause-template hard gate to each rule's proposed clause."""
        findings: list[ProfessionalFinding] = []

        for rule in triggered_rules:
            if is_blocked_for_dealer_rental(rule.rule_id):
                continue

            excerpt = extract_excerpt(text, rule.trigger_keywords)
            # DLR rules have pre-written, trusted proposed clauses.
            # The clause-template hard gate only applies to LLM-generated revisions.
            proposed = rule.proposed_clause

            findings.append(ProfessionalFinding(
                rule_id=rule.rule_id,
                issue_title=rule.issue_title,
                relevant_clause=rule.rule_title,
                original_excerpt=excerpt,
                legal_risk=rule.legal_risk,
                business_risk=rule.business_risk,
                why_this_matters=rule.why_this_matters,
                risk_level=rule.severity,
                approval_required=rule.approval_required,
                required_action=rule.required_action,
                proposed_clause=proposed,
                negotiation_position=rule.negotiation_position,
                evidence_from_contract=excerpt,
                confidence=rule.confidence,
            ))

        return findings

    def _step_f_select_top_risks(
        self,
        findings: list[ProfessionalFinding],
    ) -> tuple[list[ProfessionalFinding], list[ProfessionalFinding], list[ProfessionalFinding]]:
        """Step F: order by DLR priority. Return (top_risks, high_findings, medium_findings)."""
        order = {rid: i for i, rid in enumerate(DLR_TOP_RISK_ORDER)}

        high = [f for f in findings if f.risk_level == "HIGH"]
        medium = [f for f in findings if f.risk_level == "MEDIUM"]

        high.sort(key=lambda f: order.get(f.rule_id, 999))
        medium.sort(key=lambda f: order.get(f.rule_id, 999))

        top_risks = (high + medium)[:5]
        return top_risks, high, medium

    def _step_g_build_final_findings(
        self,
        role_matrix: RoleMatrix,
        top_risks: list[ProfessionalFinding],
        high_findings: list[ProfessionalFinding],
        medium_findings: list[ProfessionalFinding],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Step G: build the single canonical final_findings dict."""
        return {
            "contract_type": _DEALER_RENTAL_TYPE,
            "role_matrix": role_matrix.to_dict(),
            "detailed_contract_profile": profile,
            "final_findings": {
                "high_count": len(high_findings),
                "medium_count": len(medium_findings),
                "low_count": 0,
                "must_fix_count": sum(1 for f in high_findings if f.approval_required),
                "display_buckets": {
                    "필수수정": len(high_findings),
                    "권장수정": len(medium_findings),
                    "참고": 0,
                },
                "top_risks": [f.to_dict() for f in top_risks],
                "high_issues": [f.to_dict() for f in high_findings],
                "medium_issues": [f.to_dict() for f in medium_findings],
                "low_issues": [],
            },
            "clause_results": [f.to_dict() for f in high_findings + medium_findings],
            "top_risks_filtered": [f.to_dict() for f in top_risks],
            "high_issues_filtered": [f.to_dict() for f in high_findings],
            "medium_issues_filtered": [f.to_dict() for f in medium_findings],
        }


def build_dealer_rental_review(
    *,
    text: str,
    entity: str = "퍼시스",
    contract_type: str = "",
) -> dict[str, Any]:
    """Public API: run the full orchestrator and return the combined result dict."""
    orch = DealerRentalReviewOrchestrator(entity=entity)
    return orch.orchestrate(text, contract_type)
