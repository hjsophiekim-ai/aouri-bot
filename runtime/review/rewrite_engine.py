from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


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


def _rewrite_risk_001_liability_cap(text: str, *, matched_keywords: list[str]) -> RewriteProposal | None:
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
    if not changed:
        return None
    reason = "책임 범위가 과도하게 넓게 해석될 수 있는 표현이 있어(예: " + ", ".join(matched_keywords[:3]) + "), 책임 상한과 간접손해 제외를 명시하도록 조정."
    return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-001"])


def _rewrite_risk_002_indemnity(text: str, *, matched_keywords: list[str]) -> RewriteProposal | None:
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
    if not changed:
        return None
    reason = "면책/배상 조항이 일방 부담 또는 절차 부재로 해석될 소지가 있어(예: " + ", ".join(matched_keywords[:3]) + "), 상호주의 및 제3자 청구 절차(통지·방어권·승인)를 명시."
    return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-002"])


def _rewrite_risk_004_tech_data(text: str, *, matched_keywords: list[str]) -> RewriteProposal | None:
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
    if not changed:
        return None
    reason = "기술자료 제공 요구가 목적/범위/보안/반환 조건 없이 포괄적으로 해석될 수 있어(예: " + ", ".join(matched_keywords[:3]) + "), 제공 조건과 제한을 명확화."
    return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-004"])


def _rewrite_risk_005_price_reduction(text: str, *, matched_keywords: list[str]) -> RewriteProposal | None:
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
    if not changed:
        return None
    reason = "단가 감액/조정이 일방적으로 적용될 수 있는 표현이 있어(예: " + ", ".join(matched_keywords[:3]) + "), 객관적 요건과 서면합의 및 산식/근거를 명시."
    return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-005"])


def _rewrite_risk_006_cost_shift(text: str, *, matched_keywords: list[str]) -> RewriteProposal | None:
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
    if not changed:
        return None
    reason = "비용 부담/전가가 포괄적으로 해석될 소지가 있어(예: " + ", ".join(matched_keywords[:3]) + "), 항목별 상한·정산/증빙과 사전 서면합의 요건을 명시."
    return RewriteProposal(suggested_rewrite=_norm_ws(" ".join(patched)), rewrite_reason=reason, reason_codes=["RISK-006"])


def propose_clause_specific_rewrite(
    *,
    clause_text: str,
    applied_rules: list[dict[str, Any]],
    posture: str = "neutral",
) -> RewriteProposal | None:
    text = _norm_ws(clause_text)
    if not text:
        return None

    proposals: list[RewriteProposal] = []
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
            p = _rewrite_risk_001_liability_cap(text, matched_keywords=mk)
        elif rid == "RISK-002":
            p = _rewrite_risk_002_indemnity(text, matched_keywords=mk)
        elif rid == "RISK-004":
            p = _rewrite_risk_004_tech_data(text, matched_keywords=mk)
        elif rid == "RISK-005":
            p = _rewrite_risk_005_price_reduction(text, matched_keywords=mk)
        elif rid == "RISK-006":
            p = _rewrite_risk_006_cost_shift(text, matched_keywords=mk)

        if p:
            proposals.append(p)

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

