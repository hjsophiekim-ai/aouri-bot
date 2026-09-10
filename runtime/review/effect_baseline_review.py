"""법률효과 기반 **기본 검토** — 계약유형 룰팩이 없어도 항상 도는 안전망.

2026-09-10 아키텍처 지시 항목 2 — "계약유형별 템플릿은 semantic layer 를
보조하는 역할만 하고, finding 생성의 출발점이 되지 않도록 할 것."

무엇이 문제였나
─────────────
finding 을 만드는 주체가 전부 **계약유형별 룰팩**이었다. 그래서 유형이
enum 에 없거나 룰팩이 얇으면 검토 결과가 사실상 비었다. 실측(hold-out):

  · `supply_purchase.txt` — "을은 납품일로부터 60일 이내에 대금을 지급한다",
    "을의 귀책이 아닌 경우에도 을은 모든 손해를 배상한다", "갑은 사전 통지
    없이 즉시 해지할 수 있다" 가 모두 들어 있는데 **대금·지연·하자 축의
    검토의견이 0건**이었다.
  · `_lm_license_1.txt` — 34,000자 라이선스 계약에서 finding 3건, 그중
    라이선스·로열티 축은 **0건**.

이 모듈이 하는 일
──────────────
조항의 **법률효과 범주**(clause_effect)만 보고, 그 효과에서 계약유형과 무관하게
성립하는 기본 점검을 수행한다. 배상 조항에 한도가 없으면 문제이고, 해지 조항에
최고 절차가 없으면 문제다 — 그 계약이 NDA 든 라이선스든 건설도급이든.

두 가지 원칙을 지킨다.

  · **부재 판정은 계약 전체를 보고 한다**(지시 항목 5). "한도 없음", "예외
    없음" 류는 다른 조항·별첨에 이미 있으면 만들지 않는다.
  · **우리에게 유리한 조항도 법적으로 위태로우면 짚는다**(지시 항목 6·강행법규
    우선). 다만 그 경우 수정 방향은 "권리를 내려놓아라"가 아니라 "법이 요구하는
    절차를 갖춰 그 권리가 실제로 집행되게 하라"다.

유형별 룰팩은 이 위에 얹혀 더 정밀한 판단을 더한다. 이 모듈이 만든 finding 과
같은 조항·같은 효과를 다루면 기존 dedup 이 병합한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.review.clause_effect import (
    EFFECT_CHANGE,
    EFFECT_CONFIDENTIALITY,
    EFFECT_DELIVERY,
    EFFECT_DISPUTE,
    EFFECT_IP,
    EFFECT_LIABILITY,
    EFFECT_OWNERSHIP,
    EFFECT_PAYMENT,
    EFFECT_PRIVACY,
    EFFECT_SUBCONTRACT,
    EFFECT_TERMINATION,
    EFFECT_WARRANTY,
    classify_clause_effects,
)
from runtime.review.minimal_edit import minimal_edit_for


@dataclass(frozen=True)
class EffectCheck:
    """효과 하나에 대한 기본 점검."""

    check_id: str
    effect: str
    severity: str                    # HIGH | MEDIUM
    title: str
    problem: str
    legal_reason: str
    #: 조항 본문에 이 패턴이 있으면 발동(있어서 문제인 경우).
    present: re.Pattern[str] | None = None
    #: 계약 **전체**에 이 패턴이 없으면 발동(없어서 문제인 경우, 지시 항목 5).
    absent_globally: re.Pattern[str] | None = None
    #: 이 패턴이 조항에 있으면 발동하지 않는다(이미 방어장치가 있음).
    unless: re.Pattern[str] | None = None


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


CHECKS: tuple[EffectCheck, ...] = (
    # ── 대가·지급 ────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_payment_long_term",
        effect=EFFECT_PAYMENT,
        severity="MEDIUM",
        title="대금 지급기일이 장기로 설정되어 자금 회수가 지연될 수 있음",
        problem="대금 지급기일이 60일 이상으로 정해져 있어 공급 이후 자금 회수까지의 기간이 길어집니다.",
        legal_reason="지급기일이 길수록 상대방 신용위험에 노출되는 기간이 늘어나며, 회수 지연 시 지연이자만으로는 자금비용을 보전하기 어렵습니다.",
        present=_rx(r"(?:6[0-9]|[7-9][0-9]|1[0-9]{2})\s*일\s*(?:이내|내)에?\s*(?:대금|대가|비용)?\s*지급|net\s*(?:60|90|120)"),
    ),
    EffectCheck(
        check_id="eb_payment_no_late_interest",
        effect=EFFECT_PAYMENT,
        severity="MEDIUM",
        title="지급 지연 시 지연손해금 규정이 없음",
        problem="대금 지급 지연에 대한 지연손해금(지연이자) 규정이 계약 전체에서 확인되지 않습니다.",
        legal_reason="지연이자 약정이 없으면 상법상 연 6%에 그쳐 실제 자금비용을 보전하지 못하고, 지급 지연을 억제하는 효과도 없습니다.",
        absent_globally=_rx(r"지연손해금|지연이자|연체이자|지체상금|late\s+payment\s+interest|default\s+interest"),
    ),
    EffectCheck(
        check_id="eb_payment_unilateral_withholding",
        effect=EFFECT_PAYMENT,
        severity="HIGH",
        title="상대방이 임의로 대금 지급을 유보할 수 있음",
        problem="지급 유보·보류의 사유와 절차가 특정되지 않아 상대방이 임의로 대금을 붙잡아 둘 수 있습니다.",
        legal_reason="유보 사유가 객관화되어 있지 않으면 이행을 마친 뒤에도 대가를 받지 못하고, 그 다툼의 입증책임이 우리 쪽에 남습니다.",
        present=_rx(r"(?:지급|대금)(?:을|의)?\s*(?:임의로\s*)?(?:유보|보류)(?:할\s*수\s*있|한다)"),
        unless=_rx(r"유보\s*사유|보류\s*사유|사전\s*서면\s*통지"),
    ),
    # ── 인도·검수 ────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_delivery_short_inspection",
        effect=EFFECT_DELIVERY,
        severity="MEDIUM",
        title="검수 기간이 지나치게 짧아 실질적 검수가 어려움",
        problem="검수 기간이 3일 이하로 설정되어 있어 목적물을 실제로 확인하기 어려운 구조입니다.",
        legal_reason="검수 기간이 비현실적으로 짧으면 형식적 합격 처리로 이어지고, 이후 하자 발견 시 책임 소재를 두고 다툼이 생깁니다.",
        present=_rx(r"(?:납품|인도|수령)\s*(?:후|일로부터)?\s*[1-3]\s*(?:일|영업일)\s*(?:내|이내)"),
    ),
    EffectCheck(
        check_id="eb_delivery_no_acceptance_standard",
        effect=EFFECT_DELIVERY,
        severity="MEDIUM",
        title="검수 합격·불합격의 판정 기준이 없음",
        problem="검수 절차는 있으나 무엇을 기준으로 합격·불합격을 판정하는지가 계약 전체에서 특정되지 않았습니다.",
        legal_reason="판정 기준이 없으면 검수권이 사실상 자의적 거절권으로 작동해 대금 지급과 납기 책임이 동시에 불안정해집니다.",
        absent_globally=_rx(r"검수\s*기준|합격\s*기준|사양(?:서)?에\s*따라|acceptance\s+criteria"),
    ),
    # ── 소유권·위험 ──────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_ownership_no_risk_transfer_point",
        effect=EFFECT_OWNERSHIP,
        severity="MEDIUM",
        title="소유권·위험의 이전 시점이 특정되지 않음",
        problem="목적물의 소유권과 멸실·훼손 위험이 언제 이전되는지가 계약 전체에서 특정되지 않았습니다.",
        legal_reason="이전 시점이 불명확하면 운송·보관 중 사고의 부담 주체가 다투어지고, 보험 부보 범위도 확정할 수 없습니다.",
        absent_globally=_rx(r"소유권(?:은|이).{0,40}(?:이전|귀속)|위험(?:은|이).{0,30}(?:이전|부담)|risk\s+of\s+loss"),
    ),
    # ── 책임·면책 ────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_liability_no_fault",
        effect=EFFECT_LIABILITY,
        severity="HIGH",
        title="귀책사유가 없어도 손해를 배상하도록 정하고 있음",
        problem="귀책사유를 묻지 않고 손해배상 의무를 지우는 무과실 책임 구조입니다.",
        legal_reason="무과실·전부배상 조항은 약관규제법 제7조 및 민법상 신의칙에 비추어 그 범위에서 효력이 부정될 수 있고, 우리가 그 조항의 수혜자인 경우에도 분쟁 시 집행되지 않을 위험이 있습니다.",
        present=_rx(r"귀책(?:사유)?(?:이)?\s*(?:아닌|없는)\s*경우에도|고의\s*·?\s*과실을?\s*불문|무과실"),
    ),
    EffectCheck(
        check_id="eb_liability_uncapped",
        effect=EFFECT_LIABILITY,
        severity="HIGH",
        title="손해배상 책임의 총액 한도가 없음",
        problem="손해배상 조항은 있으나 배상 총액의 상한이 계약 전체에서 정해져 있지 않습니다.",
        legal_reason="상한이 없으면 계약 대가를 크게 초과하는 배상 청구에 노출되며, 간접·특별손해까지 포함될 경우 노출 규모를 사전에 산정할 수 없습니다.",
        present=_rx(r"모든\s*손해|일체의?\s*손해|전액\s*배상|all\s+damages"),
        absent_globally=_rx(r"배상\s*(?:총액|한도|상한)|책임\s*(?:한도|상한|제한)|limitation\s+of\s+liability|cap\s+on\s+liability|초과하지\s*아니한다"),
    ),
    # ── 보증 ─────────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_warranty_no_period",
        effect=EFFECT_WARRANTY,
        severity="MEDIUM",
        title="하자담보책임의 기간이 특정되지 않음",
        problem="하자담보·품질보증 의무는 있으나 그 기간이 계약 전체에서 특정되지 않았습니다.",
        legal_reason="기간이 없으면 상법상 제척기간 해석에 의존하게 되어 책임 종료 시점을 예측할 수 없습니다.",
        absent_globally=_rx(r"하자담보\s*(?:책임)?\s*기간|보증\s*기간|warranty\s+period|기간은.{0,20}(?:년|개월)"),
    ),
    # ── 해지 ─────────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_termination_immediate_no_cure",
        effect=EFFECT_TERMINATION,
        severity="HIGH",
        title="최고 절차 없이 즉시 해지할 수 있도록 정하고 있음",
        problem="시정 요구(최고) 절차 없이 곧바로 계약을 해지할 수 있는 구조입니다.",
        legal_reason="최고 없는 즉시해지는 민법 제544조의 예외에 해당하는 좁은 사유에서만 유효하며, 약관규제법 제9조에 비추어 그 범위에서 효력이 부정될 수 있습니다. 우리가 해지권자인 경우에도 실제 행사 시 무효 주장을 받게 됩니다.",
        present=_rx(r"(?:사전\s*)?(?:통지|최고|催告)\s*없이\s*(?:즉시\s*)?해[지제]|즉시\s*해[지제]할\s*수\s*있"),
        unless=_rx(r"파산|회생|해산|압류|명백한\s*이행불능"),
    ),
    EffectCheck(
        check_id="eb_termination_no_survival",
        effect=EFFECT_TERMINATION,
        severity="MEDIUM",
        title="계약 종료 후 존속할 조항이 특정되지 않음",
        problem="비밀유지·지식재산·손해배상 등 종료 후에도 효력이 필요한 조항의 존속 규정이 계약 전체에서 확인되지 않습니다.",
        legal_reason="존속 규정이 없으면 종료와 동시에 비밀유지·권리귀속의 근거가 사라져, 종료 후 발생한 침해에 대응할 계약상 근거를 잃습니다.",
        absent_globally=_rx(r"존속(?:한다|하며|된다)|효력이?\s*(?:계속|유지)|surviv"),
    ),
    # ── 지식재산 ─────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_ip_no_derivative_right",
        effect=EFFECT_IP,
        severity="HIGH",
        title="2차적저작물작성권의 포함 여부가 명시되지 않음",
        problem="저작권의 이전 또는 이용허락을 정하면서 2차적저작물작성권의 포함 여부를 명시하지 않았습니다.",
        legal_reason="저작권법 제45조 제2항은 특약이 없으면 2차적저작물작성권이 양도에 포함되지 않는 것으로 추정합니다. 편집·재가공·번역이 예정된 거래에서 이 문구가 없으면 취득했다고 믿은 권리를 실제로는 갖지 못합니다.",
        present=_rx(r"저작권|저작재산권|copyright"),
        absent_globally=_rx(r"2차적저작물(?:작성권)?|derivative\s+works?"),
    ),
    EffectCheck(
        check_id="eb_ip_no_scope",
        effect=EFFECT_IP,
        severity="MEDIUM",
        title="이용허락의 매체·기간·지역이 특정되지 않음",
        problem="지식재산의 이용을 허락하면서 그 매체·기간·지역의 범위가 계약 전체에서 특정되지 않았습니다.",
        legal_reason="범위가 특정되지 않으면 허락 범위를 넘는 이용이라는 주장에 노출되고, 새로운 매체에서 사용할 때마다 추가 대가를 요구받을 수 있습니다.",
        present=_rx(r"이용(?:을)?\s*(?:허락|허여)|실시(?:권|허락)|licen[cs]e\s+to\s+use|사용권"),
        absent_globally=_rx(r"기간.{0,10}지역|매체(?:를|의)?\s*(?:불문|제한\s*없)|territor|기간·지역"),
    ),
    # ── 비밀유지 ─────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_confidentiality_no_exceptions",
        effect=EFFECT_CONFIDENTIALITY,
        severity="MEDIUM",
        title="비밀유지의무의 예외가 규정되지 않음",
        problem="비밀유지의무를 지우면서 공지 정보·기보유 정보·독자 개발 정보·법령상 공개 등 통상의 예외가 계약 전체에서 규정되지 않았습니다.",
        legal_reason="예외가 없으면 이미 알고 있던 정보나 독자적으로 개발한 결과물까지 의무 위반으로 주장될 수 있고, 법령상 공개 의무와 충돌합니다.",
        absent_globally=_rx(r"공지(?:의|된)|이미\s*(?:알고|보유)|독자적으로\s*개발|법령(?:에|상).{0,20}(?:공개|요구)|publicly\s+known|independently\s+developed"),
    ),
    # ── 개인정보 ─────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_privacy_no_consent_basis",
        effect=EFFECT_PRIVACY,
        severity="HIGH",
        title="개인정보 수집·이용의 동의 항목과 보유기간이 규정되지 않음",
        problem="개인정보를 처리하면서 수집·이용 목적, 항목, 보유기간, 제3자 제공 동의에 관한 규정이 계약 전체에서 확인되지 않습니다.",
        legal_reason="개인정보 보호법 제15조·제17조는 목적·항목·보유기간·제3자 제공을 특정한 동의를 요구합니다. 이를 갖추지 못하면 과태료와 함께 확보한 콘텐츠·데이터의 이용 자체가 중단될 수 있습니다.",
        absent_globally=_rx(r"보유기간|보유·?\s*이용\s*기간|수집·?\s*이용\s*목적|제3자\s*제공\s*동의"),
    ),
    # ── 변경·추가 ────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_change_no_written_agreement",
        effect=EFFECT_CHANGE,
        severity="MEDIUM",
        title="업무 변경·추가 시 대가와 기간의 조정 절차가 없음",
        problem="업무의 변경·추가가 예정되어 있으나 그에 따른 대가와 기간을 어떻게 조정하는지가 계약 전체에서 규정되지 않았습니다.",
        legal_reason="조정 절차가 없으면 추가 업무를 수행하고도 대가를 청구할 근거가 없고, 동시에 원래 납기 지연의 책임만 남습니다.",
        absent_globally=_rx(r"변경.{0,30}(?:대가|비용|기간).{0,20}(?:조정|합의)|추가.{0,20}(?:대가|비용).{0,20}(?:협의|합의|정한다)"),
    ),
    # ── 재위탁 ───────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_subcontract_without_consent",
        effect=EFFECT_SUBCONTRACT,
        severity="MEDIUM",
        title="사전 동의 없이 제3자에게 업무를 위탁할 수 있음",
        problem="상대방이 우리 동의 없이 제3자에게 업무를 위탁할 수 있는 구조입니다.",
        legal_reason="재위탁이 통제되지 않으면 우리가 심사하지 않은 제3자가 이행 주체가 되고, 비밀정보와 개인정보가 그 제3자에게 흘러갑니다.",
        present=_rx(r"제3자(?:에게)?\s*(?:재)?위탁(?:할\s*수\s*있|한다)|재위탁(?:할\s*수\s*있|한다)|subcontract"),
        unless=_rx(r"사전\s*(?:서면)?\s*동의|승낙을?\s*(?:받아|얻어)|prior\s+written\s+consent"),
    ),
    # ── 분쟁 ─────────────────────────────────────────────────────────────
    EffectCheck(
        check_id="eb_dispute_no_forum",
        effect=EFFECT_DISPUTE,
        severity="MEDIUM",
        title="관할 법원 또는 분쟁해결 절차가 특정되지 않음",
        problem="분쟁 발생 시 어느 법원 또는 어떤 절차로 해결하는지가 계약 전체에서 특정되지 않았습니다.",
        legal_reason="관할이 특정되지 않으면 상대방 소재지에서 응소해야 할 수 있고, 국제거래에서는 준거법 다툼까지 더해져 분쟁 비용이 크게 늘어납니다.",
        absent_globally=_rx(r"관할|중재|arbitrat|jurisdiction|venue"),
    ),
)

#: 같은 조항에 이미 같은 효과의 finding 이 있으면 중복이므로 만들지 않는다.
_EXISTING_EFFECT_KEY = "clause_effects"


def _clause_attr(clause: Any, name: str) -> str:
    if isinstance(clause, dict):
        return str(clause.get(name) or "")
    return str(getattr(clause, name, "") or "")


def run_effect_baseline_review(
    clauses: list[Any] | None,
    *,
    full_text: str,
    existing_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """조항별 법률효과만 보고 기본 점검을 수행한다.

    계약유형을 인자로 받지 않는다 — 이 검토는 유형과 무관하게 성립해야
    하기 때문이다(지시 항목 2).
    """
    body = str(full_text or "")
    existing = existing_results or []

    # 부재 판정은 계약 전체 기준으로 **한 번만** 한다(지시 항목 5).
    globally_absent: dict[str, bool] = {}
    for check in CHECKS:
        if check.absent_globally is not None:
            globally_absent[check.check_id] = not bool(check.absent_globally.search(body))

    # 이미 finding 이 있는 조항·효과 조합.
    covered: set[tuple[str, str]] = set()
    for cr in existing:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
            continue
        cid = str(cr.get("clause_id") or "")
        for eff in (cr.get(_EXISTING_EFFECT_KEY) or []):
            covered.add((cid, str(eff)))

    out: list[dict[str, Any]] = []
    seen_checks: set[str] = set()
    for clause in (clauses or []):
        clause_id = _clause_attr(clause, "clause_id")
        title = _clause_attr(clause, "title") or _clause_attr(clause, "clause_title")
        text = _clause_attr(clause, "text")
        if not text.strip():
            continue
        effects = classify_clause_effects(title=title, text=text)

        for check in CHECKS:
            if check.effect not in effects:
                continue
            if (clause_id, check.effect) in covered:
                continue
            if check.unless is not None and check.unless.search(text):
                continue

            fires = False
            if check.present is not None and check.present.search(text):
                fires = True
                if check.absent_globally is not None:
                    # 있어서 문제인데 방어장치가 계약 어딘가에 이미 있으면 아니다.
                    fires = globally_absent.get(check.check_id, False)
            elif check.present is None and check.absent_globally is not None:
                fires = globally_absent.get(check.check_id, False)
            if not fires:
                continue

            # 부재형 점검은 계약 전체에 대해 한 번만 보고한다.
            if check.absent_globally is not None and check.present is None:
                if check.check_id in seen_checks:
                    continue
            seen_checks.add(check.check_id)

            final_text, _addition, position = minimal_edit_for(
                original_text=text, clause_title=title, effects=[check.effect],
            )
            display_path = _clause_attr(clause, "display_path") or title
            out.append({
                "clause_id": f"{check.check_id}__{clause_id}" if clause_id else check.check_id,
                "clause_title": title,
                "display_path": display_path,
                "article_number": _clause_attr(clause, "article_number"),
                "paragraph_number": _clause_attr(clause, "paragraph_number"),
                "original_text": text,
                "risk_tier": check.severity,
                "severity": check.severity,
                "problem": check.problem,
                "rewrite_reason": check.problem,
                "legal_business_reason": check.legal_reason,
                "suggested_rewrite": final_text or None,
                "recommendation_text": final_text or check.problem,
                "negotiation_position": position,
                "negotiation_strategy": position,
                "confidence": 0.8,
                "clause_effects": [check.effect],
                "is_effect_baseline": True,
                "effect_check_id": check.check_id,
                "high_severity_basis": (
                    f"effect_baseline[{check.effect}]: {check.problem}"[:400]
                    if check.severity == "HIGH" else ""
                ),
                "detected_issue_list": [{"issue_title": check.title[:120]}],
            })
    return out
