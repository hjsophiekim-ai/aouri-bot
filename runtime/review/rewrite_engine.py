from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.review.party_role import PartyRole


@dataclass(frozen=True)
class RewriteProposal:
    suggested_rewrite: str
    rewrite_reason: str
    reason_codes: list[str]


def _norm_ws(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _split_sentences(text: str) -> list[str]:
    s = _norm_ws(text)
    if not s:
        return []
    parts = re.split(r"(?<=[\.\?\!])\s+|(?<=[\.\?\!])\n+|(?<=[。])\s+|(?<=[。])\n+|(?<=[\u3002])\s+|(?<=[\u3002])\n+|(?<=\n)", s)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(p)
    return out or [s]


def _first_match_pattern(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            return pat
    return None


def _patch_sentence(
    *,
    sentences: list[str],
    target_patterns: list[str],
    replace_fn,
) -> tuple[list[str], bool]:
    out: list[str] = []
    changed = False
    for s in sentences:
        if not changed and _first_match_pattern(s, target_patterns):
            ns = replace_fn(s)
            out.append(ns)
            changed = (ns != s)
        else:
            out.append(s)
    return out, changed


def _pick_party_style(text: str) -> str:
    if "갑" in text and "을" in text:
        return "KR-AB"
    return "GEN"


def _rewrite_risk_001_liability_cap(text: str, *, matched_keywords: list[str], posture: str) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    pats = [
        r"\bwithout\s+limitation\b",
        r"\bunlimited\b",
        r"무제한",
        r"제한\s*없(?:이|음)",
        r"모든\s*손해",
        r"간접\s*손해",
        r"특별\s*손해",
        r"영업\s*손실",
    ]
    sents = _split_sentences(original)

    def repl(s: str) -> str:
        ns = s
        ns = re.sub(r"무제한\s*책임", "책임(상한 적용)", ns)
        ns = re.sub(r"\bwithout\s+limitation\b", "subject to the liability cap", ns, flags=re.IGNORECASE)
        ns = re.sub(r"\bunlimited\b", "capped", ns, flags=re.IGNORECASE)
        if ns == s:
            ns = s + " 단, 각 당사자의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며 간접손해/특별손해/영업손실 등은 제외한다(고의·중과실 및 강행법규상 책임 제외)."
        else:
            ns = ns + " (각 당사자의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며 간접손해/특별손해/영업손실 등은 제외. 단, 고의·중과실 및 강행법규상 책임 제외)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = "책임 범위가 과도하게 넓게 해석될 수 있는 표현이 있어(예: " + ", ".join(matched_keywords[:3]) + "), 책임 상한과 간접손해 제외를 명시하도록 조정."
        return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-001"])
    if posture == "buyer_favorable":
        suffix = " 단, 당사의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며 간접손해/특별손해/영업손실 등은 제외한다(고의·중과실 및 강행법규상 책임 제외)."
    elif posture == "seller_favorable":
        suffix = " 단, 상대방(구매자)의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며 간접손해/특별손해/영업손실 등은 제외한다(고의·중과실 및 강행법규상 책임 제외)."
    else:
        suffix = " 단, 각 당사자의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며 간접손해/특별손해/영업손실 등은 제외한다(고의·중과실 및 강행법규상 책임 제외)."
    suggested = _norm_ws(original + suffix)
    reason = "책임 상한/간접손해 제외가 명확히 보이지 않아, 책임 범위가 과도하게 확장될 위험이 있어 보완."
    return RewriteProposal(suggested_rewrite=suggested, rewrite_reason=reason, reason_codes=["RISK-001"])


def _rewrite_risk_002_indemnity(text: str, *, matched_keywords: list[str], posture: str) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    pats = [
        r"\bindemnif",
        r"면책",
        r"손해배상",
        r"배상(?:한다|하여야|의무)",
        r"hold\s+harmless",
        r"제3자\s*청구",
    ]
    sents = _split_sentences(original)
    party_style = _pick_party_style(original)

    def repl(s: str) -> str:
        ns = s
        if party_style == "KR-AB":
            ns = re.sub(r"(을은\s*갑을\s*면책(?:한다|함))", "각 당사자는 상대방을 합리적인 범위에서 면책", ns)
        if ns == s:
            ns = s + " (제3자 청구에 따른 배상은 상호주의를 원칙으로 하며, 통지·방어권·합의/변제 승인 절차를 포함하고, 범위·사유·한도를 합리적으로 제한한다.)"
        else:
            ns = ns + " (제3자 청구 배상: 통지·방어권·승인 절차 포함, 범위·한도 합리적 제한)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = "면책/배상 조항이 일방 부담 또는 절차 부재로 해석될 소지가 있어(예: " + ", ".join(matched_keywords[:3]) + "), 상호주의 및 제3자 청구 절차(통지·방어권·승인)를 명시."
        return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-002"])
    if posture == "buyer_favorable":
        suffix = " (제3자 청구에 따른 배상은 상대방(공급자/시공자)의 귀책 범위 내에서 당사를 방어·면책하는 구조를 기본으로 하며, 통지·방어권·합의/변제 승인 절차를 포함하고, 범위·사유·한도를 합리적으로 규정한다.)"
    elif posture == "seller_favorable":
        suffix = " (제3자 청구에 따른 배상은 상대방(구매자)의 귀책 범위 내에서 당사를 방어·면책하는 구조를 기본으로 하며, 통지·방어권·합의/변제 승인 절차를 포함하고, 범위·사유·한도를 합리적으로 규정한다.)"
    else:
        suffix = " (제3자 청구에 따른 배상은 상호주의를 원칙으로 하며, 통지·방어권·합의/변제 승인 절차를 포함하고, 범위·사유·한도를 합리적으로 제한한다.)"
    suggested = _norm_ws(original + suffix)
    reason = "면책/제3자 청구 배상 조항의 절차(통지·방어권·승인)와 상호주의가 명확히 드러나지 않아 보완."
    return RewriteProposal(suggested_rewrite=suggested, rewrite_reason=reason, reason_codes=["RISK-002"])


def _rewrite_risk_004_tech_data(text: str, *, matched_keywords: list[str], posture: str) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    pats = [
        r"기술자료",
        r"도면",
        r"설계",
        r"소스\s*코드",
        r"자료\s*제공",
        r"confidential\s+information",
    ]
    sents = _split_sentences(original)

    def repl(s: str) -> str:
        ns = s
        if ns == s:
            ns = (
                s
                + " (기술자료 제공은 목적·범위·기간을 특정하고 최소한으로 제공하며, 반환/파기, 제3자 제공 금지, 보안조치 및 위반 시 손해배상 기준을 포함한다.)"
            )
        else:
            ns = ns + " (목적·범위·기간 특정, 최소 제공, 반환/파기, 제3자 제공 금지, 보안조치)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = "기술자료 제공 요구가 목적/범위/보안/반환 조건 없이 포괄적으로 해석될 수 있어(예: " + ", ".join(matched_keywords[:3]) + "), 제공 조건과 제한을 명확화."
        return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-004"])
    if posture == "buyer_favorable":
        suffix = " (당사가 제공하는 기술자료/원가자료/소스 등은 목적·범위·기간을 특정해 최소한으로 제공하며, 반환/파기, 재사용·역설계 금지, 제3자 제공 금지, 보안조치 및 위반 시 손해배상 기준을 포함한다.)"
    else:
        suffix = " (기술자료 제공은 목적·범위·기간을 특정하고 최소한으로 제공하며, 반환/파기, 제3자 제공 금지, 보안조치 및 위반 시 손해배상 기준을 포함한다.)"
    suggested = _norm_ws(original + suffix)
    reason = "기술자료 제공의 목적/범위/보안/반환 조건이 불명확할 수 있어 최소 통제 문구를 추가."
    return RewriteProposal(suggested_rewrite=suggested, rewrite_reason=reason, reason_codes=["RISK-004"])


def _rewrite_risk_005_price_reduction(text: str, *, matched_keywords: list[str], posture: str) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    pats = [
        r"단가",
        r"감액",
        r"감가",
        r"조정",
        r"일방",
        r"price\s+reduction",
    ]
    sents = _split_sentences(original)

    def repl(s: str) -> str:
        ns = s
        if ns == s:
            ns = s + " (단가 조정/감액은 객관적 사유에 한정하고, 사전 협의 및 서면 합의로만 가능하며, 범위·기간·산식·근거를 명시한다.)"
        else:
            ns = ns + " (객관적 사유 + 사전협의/서면합의 + 산식/근거 명시)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = "단가 감액/조정이 일방적으로 적용될 수 있는 표현이 있어(예: " + ", ".join(matched_keywords[:3]) + "), 객관적 요건과 서면합의 및 산식/근거를 명시."
        return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-005"])
    suffix = " (단가 조정/감액은 객관적 사유에 한정하고, 사전 협의 및 서면 합의로만 가능하며, 범위·기간·산식·근거를 명시한다.)"
    suggested = _norm_ws(original + suffix)
    reason = "단가 조정/감액의 객관적 요건·절차(사전협의/서면합의)·산식/근거가 불명확할 수 있어 보완."
    return RewriteProposal(suggested_rewrite=suggested, rewrite_reason=reason, reason_codes=["RISK-005"])


def _rewrite_risk_006_cost_shift(text: str, *, matched_keywords: list[str], posture: str) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    pats = [
        r"판촉비",
        r"광고비",
        r"반품",
        r"수수료",
        r"비용\s*부담",
        r"비용\s*전가",
        r"marketing\s+fee",
    ]
    sents = _split_sentences(original)

    def repl(s: str) -> str:
        ns = s
        if ns == s:
            ns = s + " (비용 부담 항목은 사전 서면 합의된 경우에 한하며, 항목별 상한·정산 기준·증빙을 명시하고 일방 전가를 금지한다.)"
        else:
            ns = ns + " (사전 서면합의 + 항목별 상한/정산/증빙 + 일방전가 금지)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = "비용 부담/전가가 포괄적으로 해석될 소지가 있어(예: " + ", ".join(matched_keywords[:3]) + "), 항목별 상한·정산/증빙과 사전 서면합의 요건을 명시."
        return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-006"])
    if posture == "buyer_favorable":
        suffix = " (추가 비용/판촉비/광고비/반품비 등은 사전 서면 합의된 경우에 한하여 발생하며, 항목별 상한·정산 기준·증빙을 명시한다. 상대방의 과실/지시/하자/지연으로 발생한 비용은 상대방이 부담한다.)"
    else:
        suffix = " (비용 부담 항목은 사전 서면 합의된 경우에 한하며, 항목별 상한·정산 기준·증빙을 명시하고 일방 전가를 금지한다.)"
    suggested = _norm_ws(original + suffix)
    reason = "판촉비/광고비/반품 등 비용 부담 조항의 항목별 기준(상한·정산·증빙)과 사전 서면합의 요건이 불명확할 수 있어 보완."
    return RewriteProposal(suggested_rewrite=suggested, rewrite_reason=reason, reason_codes=["RISK-006"])


def _rewrite_safety_gap(text: str, *, posture: str) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    if posture != "buyer_favorable":
        return None
    already = original
    if (
        ("안전" in already or "산업안전" in already or "중대재해" in already)
        and ("준수" in already or "교육" in already or "보호구" in already)
        and ("책임" in already and ("공급자" in already or "수급" in already or "을" in already))
    ):
        return None
    suffix = (
        " (설치/현장 작업이 있는 경우, 상대방 및 그 협력업체는 산업안전보건법 등 관련 법령을 준수하고 "
        "작업 전 위험성 평가·안전교육·보호구·출입/작업허가·사고 보고/통지 체계를 갖추어야 하며, "
        "재위탁(하도급)은 당사의 사전 서면 승인 하에만 가능하고, 재위탁자에 대한 안전·품질 책임은 상대방이 부담한다. "
        "사고/중대재해 발생 시 즉시 통지 및 조사/시정 협력, 작업중지 요청권을 포함한다.)"
    )
    suggested = _norm_ws(original + suffix)
    reason = "설치/현장 작업 관련 안전관리 책임 귀속 및 재위탁 통제가 불명확할 수 있어, 당사 보호 관점에서 최소 안전/승인/통지 구조를 보완."
    return RewriteProposal(suggested_rewrite=suggested, rewrite_reason=reason, reason_codes=["RISK-003"])


def _party_term(party: PartyRole | None, *, which: str) -> str:
    if party is None:
        return "당사" if which == "our" else "상대방"
    if which == "our":
        if party.our_label in ("갑", "을"):
            return str(party.our_label)
        if party.our_role in ("buyer", "ordering_party", "client"):
            return "당사"
        return "당사"
    if party.counterparty_label in ("갑", "을"):
        return str(party.counterparty_label)
    return "상대방"


def _rewrite_app_001_ip(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (개발 산출물(소스코드·문서·설계서·테스트 산출물 등)에 대한 저작권 및 지식재산권은 "
        f"{our}가 검수 합격 및 대금 지급을 완료한 시점에 {our}에게 이전(양도)되는 것으로 하며, "
        f"{cp}는 제3자 권리침해가 없음을 보증한다. "
        f"오픈소스·서드파티 컴포넌트가 포함되는 경우 사전 고지 및 라이선스 준수 의무를 부담하고, "
        f"권리침해 주장 시 {cp}는 {our}를 방어·면책하며(통지·방어권·합의/변제 승인 절차 포함), "
        f"대체/수정/제거 등으로 시정한다.)"
    )
    reason = "산출물/소스코드/IP 귀속과 제3자 권리침해 보증·시정 구조가 불명확할 수 있어, 귀속·보증·방어/시정 프레임을 명시."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-001"])


def _rewrite_app_002_oss(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (오픈소스/서드파티 컴포넌트를 사용하는 경우 {cp}는 적용 라이선스 및 버전, 사용 범위, "
        f"소스 공개 의무/표시 의무 등을 포함한 목록(SBOM)을 {our}에게 제공하고 변경 시 사전 고지한다. "
        f"GPL 등 카피레프트 라이선스 적용이 발생할 수 있는 구성요소는 {our}의 사전 서면 승인 없이 사용하지 않는다. "
        f"라이선스 위반이 발생한 경우 {cp}는 자신의 비용과 책임으로 시정(대체/수정/제거)하고, "
        f"{our}에 발생한 손해를 배상한다.)"
    )
    reason = "오픈소스 사용 고지·승인·준수·위반 시 시정/배상 구조가 누락되면 소스 공개 의무 등 치명적 리스크로 이어질 수 있어 보완."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-002"])


def _rewrite_app_003_sow(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (개발 범위/요구사항/산출물/일정은 별지 SOW(요구사항정의서/기능명세/화면설계서 등)에 따른다. "
        f"범위 변경은 변경요청서 제출 → 영향분석(일정/비용/리스크) → {our}의 서면 승인에 따라 반영하며, "
        f"{our} 승인 없는 추가 개발/비용 청구는 인정되지 않는다.)"
    )
    reason = "SOW/변경관리(승인·비용·일정) 구조가 약하면 범위 확장 및 추가비용 분쟁이 커질 수 있어 보완."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-003"])


def _rewrite_app_004_acceptance(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (검수 기준(테스트 시나리오/성능 기준/결함 등급)과 검수 기간은 별지로 정하며, "
        f"{our}는 검수 기간 내 합격 또는 보완 요청을 통지한다. "
        f"{cp}는 보완 요청을 받은 날부터 합리적 기간 내 무상으로 수정하고 재검수를 진행한다. "
        f"간주검수는 {our}에게 산출물 제공 및 검수요청의 서면 통지, 합리적 대응기간 부여 등 요건을 충족한 경우에만 적용한다.)"
    )
    reason = "검수/간주검수/재검수 기준이 불명확하면 대금지급·책임전환 시점 분쟁으로 확대될 수 있어 절차를 명시."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-004"])


def _rewrite_app_006_sla(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (유지보수/SLA가 적용되는 경우, 장애 등급별 응답/복구 시간, 정기점검 및 업데이트 정책, "
        f"에스컬레이션 절차를 별지로 정한다. "
        f"SLA 위반 시 {our}는 서비스 크레딧/대금 감액 및 반복 위반 시 해지권을 가진다. "
        f"{cp}는 장애 원인 분석 및 재발방지 대책을 제공한다.)"
    )
    reason = "유지보수/SLA의 측정·구제수단(감액/크레딧/해지)과 장애 대응 절차가 약하면 운영 리스크를 통제하기 어려워 보완."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-006"])


def _rewrite_app_007_security(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (보안사고/개인정보 유출 등 침해사고 발생 시 {cp}는 즉시 {our}에 통지하고 조사·시정·재발방지에 협력한다. "
        f"{cp}는 접근통제/암호화/로그/취약점 조치 등 합리적 보안조치를 유지하고, "
        f"재위탁이 있는 경우 {our}의 사전 서면 승인 및 동일 수준의 보안·비밀유지 의무를 하위전가한다. "
        f"{cp}의 귀책으로 침해사고가 발생한 경우 관련 비용(조사/통지/대응) 및 손해를 배상한다.)"
    )
    reason = "보안사고/개인정보 유출은 통지·협력·비용 부담·재위탁 통제까지 명확해야 실무적으로 대응 가능하므로 책임 및 절차를 보완."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-007"])


def _rewrite_app_009_subcontract(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (재위탁(하도급) 또는 협력업체 활용은 {our}의 사전 서면 승인 하에만 가능하며, "
        f"{cp}는 하위수탁자의 행위에 대하여 동일한 책임을 부담한다. "
        f"하위수탁자에게도 비밀유지/보안/개인정보 보호 의무를 동일하게 부과하고, {our}의 요청 시 이를 증명한다.)"
    )
    reason = "재위탁 통제가 없으면 품질/보안/IP 리스크가 급증하므로, 사전 승인 및 책임 귀속·의무 하위전가 구조를 명시."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-009"])


def _rewrite_app_010_data(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (계약 종료 또는 {our}의 요청 시 {cp}는 {our}의 데이터 및 산출물을 합리적 포맷으로 반환하고, "
        f"개인정보를 포함하는 경우 관련 법령 및 {our}의 지시에 따라 파기/삭제한다. "
        f"백업/로그에 남는 데이터의 처리 기준과 삭제 완료 확인(증적 제공) 범위를 명시한다.)"
    )
    reason = "데이터 반환/삭제(백업·로그 포함)와 삭제 확인이 불명확하면 종료 후 분쟁 및 개인정보 리스크가 발생할 수 있어 보완."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-010"])


def _rewrite_app_011_handover(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    suffix = (
        f" (계약 종료 시 {cp}는 소스코드, 빌드/배포 스크립트, 환경설정, 계정/권한, 운영 매뉴얼, 테스트 결과 등 "
        f"인수인계에 필요한 자료를 {our}에게 제공하고 전환(마이그레이션) 지원에 협력한다. "
        f"인수인계 범위/기간/요율은 별지로 정하되, {cp}의 귀책으로 인한 종료 또는 계약상 의무 불이행이 있는 경우 "
        f"필수 인수인계는 무상으로 제공한다.)"
    )
    reason = "종료 시 인수인계/전환 협력이 명확하지 않으면 서비스 중단 리스크가 커지므로, 산출물 목록과 전환 협력 범위를 보완."
    prefix = "구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else ""
    return RewriteProposal(suggested_rewrite=_norm_ws(original + suffix), rewrite_reason=(prefix + reason)[:900], reason_codes=["APP-011"])


def propose_clause_specific_rewrite(
    *,
    clause_text: str,
    applied_rules: list[dict[str, Any]],
    posture: str = "neutral",
    party: PartyRole | None = None,
) -> RewriteProposal | None:
    text = _norm_ws(clause_text)
    if not text:
        return None

    proposals: list[RewriteProposal] = []
    rids = {str(ar.get("rule_id") or "") for ar in applied_rules if isinstance(ar, dict)}
    for ar in applied_rules:
        if not isinstance(ar, dict):
            continue
        rid = ar.get("rule_id")
        if not isinstance(rid, str) or not rid:
            continue
        matched_keywords = ar.get("matched_keywords") if isinstance(ar.get("matched_keywords"), list) else []
        mk = [str(x) for x in matched_keywords if isinstance(x, str) and x.strip()]

        p: RewriteProposal | None = None
        if rid == "RISK-001":
            p = _rewrite_risk_001_liability_cap(text, matched_keywords=mk, posture=posture)
        elif rid == "RISK-002":
            p = _rewrite_risk_002_indemnity(text, matched_keywords=mk, posture=posture)
        elif rid == "RISK-004":
            p = _rewrite_risk_004_tech_data(text, matched_keywords=mk, posture=posture)
        elif rid == "RISK-005":
            p = _rewrite_risk_005_price_reduction(text, matched_keywords=mk, posture=posture)
        elif rid == "RISK-006":
            p = _rewrite_risk_006_cost_shift(text, matched_keywords=mk, posture=posture)
        elif rid == "APP-001":
            p = _rewrite_app_001_ip(text, posture=posture, party=party)
        elif rid == "APP-002":
            p = _rewrite_app_002_oss(text, posture=posture, party=party)
        elif rid == "APP-003":
            p = _rewrite_app_003_sow(text, posture=posture, party=party)
        elif rid == "APP-004":
            p = _rewrite_app_004_acceptance(text, posture=posture, party=party)
        elif rid == "APP-006":
            p = _rewrite_app_006_sla(text, posture=posture, party=party)
        elif rid == "APP-007":
            p = _rewrite_app_007_security(text, posture=posture, party=party)
        elif rid == "APP-009":
            p = _rewrite_app_009_subcontract(text, posture=posture, party=party)
        elif rid == "APP-010":
            p = _rewrite_app_010_data(text, posture=posture, party=party)
        elif rid == "APP-011":
            p = _rewrite_app_011_handover(text, posture=posture, party=party)

        if p:
            proposals.append(p)

    if not proposals and any(r in rids for r in ("RISK-003", "ACT-010")):
        p2 = _rewrite_safety_gap(text, posture=posture)
        if p2:
            proposals.append(p2)

    if not proposals:
        return None

    merged_reason_codes: list[str] = []
    merged_reasons: list[str] = []
    out_text = proposals[0].suggested_rewrite
    for p in proposals:
        if p.suggested_rewrite and p.suggested_rewrite != out_text:
            out_text = p.suggested_rewrite
        for c in p.reason_codes:
            if c not in merged_reason_codes:
                merged_reason_codes.append(c)
        if p.rewrite_reason and p.rewrite_reason not in merged_reasons:
            merged_reasons.append(p.rewrite_reason)

    return RewriteProposal(
        suggested_rewrite=_norm_ws(out_text),
        rewrite_reason=(
            ("구매자 보호 방향(" + str(posture) + ") 기준으로 보완: " if posture == "buyer_favorable" else "")
            + " / ".join(merged_reasons)
        )[:900],
        reason_codes=merged_reason_codes,
    )

