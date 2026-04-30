from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractProfile:
    profile: str
    evidence: list[str]

    def to_dict(self) -> dict[str, object]:
        return {"profile": self.profile, "evidence": list(self.evidence)}


def infer_contract_profile(*, contract_type: str, text: str) -> ContractProfile:
    ct = (contract_type or "")
    t = (text or "")
    ev: list[str] = []

    low = (ct + "\n" + t).lower()

    def has_any(needles: list[str]) -> bool:
        return any(n.lower() in low for n in needles if n)

    def has_app_dev_strong() -> bool:
        return has_any(
            [
                "소스코드",
                "source code",
                "오픈소스",
                "open source",
                "sbom",
                "sow",
                "statement of work",
                "api 연동",
                "api integration",
                "프로그램 개발",
                "소프트웨어 개발",
                "앱 개발",
                "시스템 개발",
                "저작권 양도",
            ]
        )

    def has_ops_outsourcing() -> bool:
        return has_any(
            [
                "운영대행",
                "위탁운영",
                "운영위탁",
                "공간운영",
                "매장운영",
                "라운지",
                "시설운영",
                "시설관리",
                "관리용역",
                "운영용역",
                "서비스위탁",
                "운영관리",
                "운영인력",
                "인력배치",
                "근무",
                "교대",
                "보고",
                "자료제출",
                "검수",
                "운영수수료",
                "용역비",
                "도급",
                "하도급",
                "재위탁",
                "안전관리",
            ]
        )

    ct_pref_privacy = (("개인정보" in ct) and ("처리위탁" in ct or "DPA" in ct or "dpa" in ct.lower()))
    ct_pref_dealer = any(k in ct for k in ("대리점", "유통")) or any(k in low for k in ("dealer", "distributor"))
    ct_pref_ops = any(k in ct for k in ("운영대행", "위탁운영", "운영위탁", "공간운영", "매장운영", "서비스위탁", "관리용역", "운영용역"))

    if ct_pref_privacy:
        ev.append("privacy_token")
        return ContractProfile(profile="privacy_dpa", evidence=ev)
    if ct_pref_dealer:
        ev.append("dealer_token")
        return ContractProfile(profile="dealer_consignment", evidence=ev)
    if ct_pref_ops:
        ev.append("ops_outsourcing_token")
        return ContractProfile(profile="ops_outsourcing", evidence=ev)

    if has_ops_outsourcing() and not has_app_dev_strong():
        ev.append("ops_outsourcing_token")
        return ContractProfile(profile="ops_outsourcing", evidence=ev)

    is_dealer = has_any(["대리점", "유통", "위탁판매", "위탁거래", "consignment", "dealer", "distributor"])
    if is_dealer:
        ev.append("dealer_token")
        return ContractProfile(profile="dealer_consignment", evidence=ev)

    is_privacy_dpa = (("개인정보" in ct) and ("처리위탁" in ct or "DPA" in ct or "dpa" in ct.lower())) or (
        has_any(["처리위탁", "dpa", "data processing", "개인정보처리위탁", "개인정보 처리위탁"])
        and (not is_dealer)
        and (not has_ops_outsourcing())
        and (not has_app_dev_strong())
    )
    if is_privacy_dpa:
        ev.append("privacy_token")
        return ContractProfile(profile="privacy_dpa", evidence=ev)

    if has_any(["앱개발", "소프트웨어", "si", "saas"]) or has_app_dev_strong():
        ev.append("app_dev_token")
        return ContractProfile(profile="app_dev", evidence=ev)

    if any(k in ct for k in ("설치", "공사", "시공", "납품", "장비")) or any(k in t for k in ("설치", "시공", "현장", "시운전", "성능시험", "공사")):
        ev.append("onsite_token")
        return ContractProfile(profile="onsite_installation", evidence=ev)

    return ContractProfile(profile="generic", evidence=ev)


def priority_topics_for_profile(profile: str) -> list[str]:
    if profile == "dealer_consignment":
        return [
            "dealer_unfair_practice",
            "dealer_management_interference",
            "termination_disadvantage",
            "dealer_cost_shift",
            "dealer_incentive_promo_return",
            "payment_settlement_offset",
            "privacy_if_any",
            "dispute_resolution_domestic",
        ]
    if profile == "ops_outsourcing":
        return [
            "scope_kpi_reporting",
            "staffing_change_control",
            "payment_settlement_offset",
            "subcontract_approval",
            "safety_if_any",
            "privacy_if_any",
            "termination_dispute",
        ]
    if profile == "app_dev":
        return [
            "sow_change",
            "ip_deliverables",
            "open_source",
            "acceptance",
            "sla_security_privacy",
            "termination_handover",
        ]
    if profile == "onsite_installation":
        return [
            "safety",
            "subcontract",
            "inspection_commissioning",
            "delay_penalty",
            "warranty_defect",
        ]
    if profile == "privacy_dpa":
        return [
            "purpose_limit",
            "subcontract",
            "security_controls",
            "return_delete",
            "incident_notice",
        ]
    return ["payment_settlement_offset", "termination_dispute"]
