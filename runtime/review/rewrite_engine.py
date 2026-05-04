from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from runtime.review.party_role import PartyRole
from runtime.review.korean_polish import polish_korean_legal_style
from runtime.review.jurisdiction import classify_jurisdiction_profile


# ---------------------------------------------------------------------------
# 시디즈(SIDIZ) 사내 변호사 / 유통·대리점법 전문 변호사 역할
# ---------------------------------------------------------------------------
# 검토 원칙:
#   1단계 (독소 제거): "무제한", "즉시", "일방적으로", "최종적" 등을
#                      "합리적인 범위 내에서", "최고 후", "상호 합의된" 등으로 치환
#   2단계 (방어권 삽입): 이의제기권 + 자료검토권 + 상계권 세트 구성
#   3단계 (스타일 교정): korean_polish 고도 법률 문어체 적용
# ---------------------------------------------------------------------------

# 독소 표현 → 방어 표현 치환 테이블 (1단계)
_TOXIN_REPLACEMENTS: list[tuple[str, str]] = [
    (r"무제한\s*책임", "합리적인 범위 내의 책임(상한 적용)"),
    (r"무제한으로", "합리적인 범위 내에서"),
    (r"무제한\s*으로", "합리적인 범위 내에서"),
    (r"즉시\s*해지", "상당한 기간을 정하여 최고한 후 해지"),
    (r"즉시\s*종료", "상당한 기간을 정하여 최고한 후 종료"),
    (r"즉시\s*지급", "청구일로부터 합리적인 기간 내에 지급"),
    (r"즉시\s*반환", "계약 종료일로부터 합리적인 기간 내에 반환"),
    (r"즉시\s*배상", "귀책 확정 후 합리적인 기간 내에 배상"),
    (r"일방적으로\s*결정", "상호 합의된 절차에 따라 결정"),
    (r"일방적으로\s*변경", "당사의 사전 서면 동의를 득하여 변경"),
    (r"일방적으로\s*해지", "본 계약에서 정한 절차에 따라 해지"),
    (r"일방적으로", "상호 합의된 절차에 따라"),
    (r"최종적으로\s*결정", "관련 법령 및 본 계약에서 정한 절차에 따라 결정"),
    (r"최종적\s*결정권", "본 계약에서 정한 절차에 따른 결정권"),
    (r"임의로\s*변경", "당사의 사전 서면 동의를 득하여 변경"),
    (r"임의로\s*해지", "본 계약에서 정한 절차에 따라 해지"),
    (r"임의로", "본 계약에서 정한 절차에 따라"),
    (r"모든\s*손해를\s*배상", "직접손해(간접손해·특별손해·영업손실 제외)를 배상"),
    (r"모든\s*비용을\s*부담", "사전 서면 합의된 항목에 한하여 비용을 부담"),
    (r"전적으로\s*책임", "귀책 범위 내에서 책임"),
    (r"무조건\s*", "본 계약에서 정한 요건 충족 시 "),
]

# 대리점법 제18조 경영간섭 위험 패턴
_MGMT_INTERFERENCE_PATTERNS: list[str] = [
    r"의\s*지시에\s*따른다",
    r"의\s*지시에\s*따라",
    r"의\s*지시를\s*따른다",
    r"의\s*지시를\s*따라야",
    r"의\s*지시\s*사항을\s*이행",
    r"가격을\s*(?:지정|결정|통제|강제)",
    r"판매가격을\s*(?:지정|결정|통제|강제)",
    r"(판매가격|가격).{0,20}(승인|사전\s*승인|승인을\s*받)",
    r"인사\s*(?:에\s*관여|를\s*지시|를\s*통제)",
    r"노무\s*(?:에\s*관여|를\s*지시|를\s*통제)",
    r"영업\s*방침을\s*(?:지시|강제|통제)",
    r"경영에\s*(?:관여|간섭|개입)",
]


def _apply_toxin_removal(text: str) -> tuple[str, list[dict[str, str]]]:
    """1단계: 독소 표현을 방어 표현으로 치환하고 변경 세그먼트를 반환한다."""
    s = text
    segments: list[dict[str, str]] = []
    for pattern, replacement in _TOXIN_REPLACEMENTS:
        new_s = re.sub(pattern, replacement, s)
        if new_s != s:
            # 변경된 원문 추출
            m = re.search(pattern, s)
            before_text = m.group(0) if m else pattern
            segments.append({"before": before_text, "after": replacement})
            s = new_s
    return s, segments


def _insert_defense_rights(text: str, *, posture: str, our: str, cp: str) -> tuple[str, list[dict[str, str]]]:
    """2단계: 이의제기권 + 자료검토권 + 상계권 세트를 삽입한다."""
    segments: list[dict[str, str]] = []
    s = text

    # 이의제기권 삽입 조건: 청구·배상·공제·감액 관련 조항
    if re.search(r"(청구|배상|공제|감액|차감|부과|벌금|위약금|지체상금)", s):
        defense_clause = (
            f" {our}는 상대방의 청구에 대하여 이의제기권을 보유하며, "
            f"청구 수령일로부터 14일 이내에 서면으로 이의를 제기할 수 있다."
        )
        if "이의제기권" not in s:
            s = s + defense_clause
            segments.append({"before": "(이의제기권 없음)", "after": defense_clause.strip()})

    # 자료검토권 삽입 조건: 정산·비용·수수료·판촉비 관련 조항
    if re.search(r"(정산|비용|수수료|판촉비|광고비|반품비|원가|단가)", s):
        audit_clause = (
            f" {our}는 관련 산출 근거 및 증빙 자료의 제출을 요구할 수 있으며, "
            f"{cp}는 요청일로부터 7영업일 이내에 이를 제공하여야 한다."
        )
        if "자료" not in s or "제출" not in s:
            s = s + audit_clause
            segments.append({"before": "(자료검토권 없음)", "after": audit_clause.strip()})

    # 상계권 삽입 조건: 대금·지급·정산 관련 조항
    if re.search(r"(대금|지급|정산|상계|공제)", s):
        offset_clause = (
            f" {our}는 {cp}에 대한 확정 채권을 자동채무와 상계할 수 있으며, "
            f"상계 통지는 서면으로 한다."
        )
        if "상계" not in s:
            s = s + offset_clause
            segments.append({"before": "(상계권 없음)", "after": offset_clause.strip()})

    return s, segments


def _detect_mgmt_interference_risk(text: str) -> list[str]:
    """대리점법 제18조 경영간섭 위험 패턴을 감지하고 해당 패턴 목록을 반환한다."""
    found: list[str] = []
    for pat in _MGMT_INTERFERENCE_PATTERNS:
        if re.search(pat, text):
            found.append(pat)
    return found


def _rewrite_mgmt_interference(text: str, *, our: str, cp: str) -> RewriteProposal | None:
    """
    대리점법 제18조 경영간섭 위험 조항을 무력화한다.
    '지시' 표현을 '품질 유지 및 소비자 보호를 위한 최소한의 기준 제시'로 치환하여
    경영간섭으로 오해받지 않으면서도 브랜드 가이드라인을 강제할 수 있는 구조로 재설계한다.
    """
    original = _norm_ws(text)
    if not original:
        return None

    interference_patterns = _detect_mgmt_interference_risk(original)
    if not interference_patterns:
        return None

    s = original
    changed_segs: list[dict[str, str]] = []

    # 지시 → 품질 가이드라인 기준 제시로 치환
    replacements = [
        (r"(갑|을|당사|시디즈|SIDIZ)\s*의\s*지시에\s*따른다",
         r"\1이 제시한 품질 유지 및 소비자 보호를 위한 최소한의 기준을 존중하되, "
         r"인사·노무·가격 결정의 독립성을 보장하는 범위 내에서 협의한다"),
        (r"(갑|을|당사|시디즈|SIDIZ)\s*의\s*지시에\s*따라",
         r"\1이 제시한 품질 가이드라인의 범위 내에서"),
        (r"(갑|을|당사|시디즈|SIDIZ)\s*의\s*지시를\s*따른다",
         r"\1이 제시한 품질 유지 기준을 존중하되, 경영 독립성을 침해하지 아니하는 범위 내에서 협의한다"),
        (r"(갑|을|당사|시디즈|SIDIZ)\s*의\s*지시를\s*따라야",
         r"\1이 제시한 품질 가이드라인을 준수하여야"),
        (r"가격을\s*(지정|결정|통제|강제)한다",
         "품질 유지 및 소비자 보호를 위한 권장 가격 기준을 제시할 수 있으며, "
         "최종 판매가격 결정권은 대리점에 귀속한다"),
        (r"판매가격을\s*(지정|결정|통제|강제)한다",
         "소비자 보호를 위한 권장 소비자가격(RRP)을 제시할 수 있으며, "
         "최종 판매가격 결정권은 대리점에 귀속한다"),
        (r"(판매가격|가격)\s*(?:변경|결정|설정)?\s*(?:에\s*대하여)?\s*(?:사전\s*)?승인",
         r"\1 변경/결정에 관하여 사전 협의"),
        (r"(판매가격|가격)\s*(?:변경|결정|설정)?\s*시\s*(?:사전\s*)?승인을\s*받",
         r"\1 변경/결정 시 사전 협의하"),
        (r"인사에\s*관여",
         "품질 유지를 위한 최소한의 자격 기준을 제시"),
        (r"경영에\s*(관여|간섭|개입)한다",
         "품질 유지 및 소비자 보호를 위한 최소한의 기준을 제시하되, "
         "대리점의 경영 독립성을 침해하지 아니한다"),
    ]

    for pat, repl in replacements:
        new_s = re.sub(pat, repl, s)
        if new_s != s:
            m = re.search(pat, s)
            before_text = m.group(0) if m else pat
            changed_segs.append({"before": before_text, "after": re.sub(r"\\1", "", repl).strip()})
            s = new_s

    # 브랜드 가이드라인 강제 조항 추가 (경영간섭 방어 문구)
    brand_clause = (
        " 단, 시디즈가 제시하는 브랜드 가이드라인(매장 인테리어 기준, 제품 진열 방식, "
        "고객 응대 품질 기준 등)은 품질 유지 및 소비자 보호를 위한 최소한의 기준으로서 "
        "대리점법 제18조의 경영간섭에 해당하지 아니하며, 대리점은 이를 준수하여야 한다."
    )
    if "브랜드 가이드라인" not in s and "품질 유지" not in s:
        s = s + brand_clause
        changed_segs.append({"before": "(브랜드 가이드라인 강제 조항 없음)", "after": brand_clause.strip()})

    reason = (
        "해당 조항의 '지시' 표현은 대리점법 제18조(경영간섭 금지)에 저촉될 구체적 위험이 있음. "
        "동조는 공급업자가 대리점의 인사·노무·가격 결정 등 경영 활동에 관여하는 행위를 금지하며, "
        "'지시에 따른다'는 문구는 그 자체로 경영간섭의 증거로 활용될 수 있음. "
        "이를 '품질 유지 및 소비자 보호를 위한 최소한의 기준 제시'로 치환하여 "
        "브랜드 가이드라인 강제력은 유지하되 경영간섭 리스크를 차단함."
    )
    return RewriteProposal(
        suggested_rewrite=_norm_ws(s),
        rewrite_reason=reason,
        reason_codes=["DEALER-001"],
        changed_segments=changed_segs,
    )


def _infer_risk_tier(*, reason_codes: list[str], text: str) -> str:
    """
    risk_tier를 산정한다.
    HIGH: 실질적 경영권 침해 및 금전적 손실 가능성
    MEDIUM: 절차적 불이익 또는 조건부 리스크
    LOW: 표현 개선 권고 수준
    """
    high_codes = {"RISK-001", "RISK-002", "RISK-004", "RISK-005", "RISK-006",
                  "DEALER-001", "APP-001", "APP-007", "ACT-004", "FURSYS-CT-001", "FURSYS-RENT-001"}
    medium_codes = {"RISK-003", "APP-002", "APP-003", "APP-004", "APP-006",
                    "APP-009", "APP-010", "APP-011", "C-001"}

    for c in reason_codes:
        if c in high_codes:
            return "HIGH (실질적 경영권 침해 및 금전적 손실 가능성)"

    # 텍스트 기반 HIGH 판정
    high_text_patterns = [
        r"무제한", r"즉시\s*해지", r"일방적", r"모든\s*손해", r"전적으로\s*책임",
        r"지시에\s*따른다", r"경영에\s*관여", r"가격을\s*(지정|통제|강제)",
    ]
    for pat in high_text_patterns:
        if re.search(pat, text):
            return "HIGH (실질적 경영권 침해 및 금전적 손실 가능성)"

    for c in reason_codes:
        if c in medium_codes:
            return "MEDIUM (절차적 불이익 또는 조건부 리스크)"

    return "LOW (표현 개선 권고)"


def _extract_changed_segments(original: str, rewritten: str) -> list[dict[str, str]]:
    """원문과 수정문을 비교하여 변경된 세그먼트를 추출한다."""
    segments: list[dict[str, str]] = []
    orig_sents = _split_sentences(original)
    new_sents = _split_sentences(rewritten)

    # 추가된 문장 감지
    orig_set = set(orig_sents)
    for s in new_sents:
        if s not in orig_set and len(s) > 10:
            segments.append({"before": "(없음)", "after": s})

    # 변경된 문장 감지 (길이 기반 매칭)
    for i, (o, n) in enumerate(zip(orig_sents, new_sents)):
        if o != n and len(o) > 5:
            segments.append({"before": o, "after": n})

    return segments[:8]  # 최대 8개 세그먼트


@dataclass(frozen=True)
class RewriteProposal:
    suggested_rewrite: str
    rewrite_reason: str
    reason_codes: list[str]
    changed_segments: list[dict[str, str]] = field(default_factory=list)


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
    changed_segs: list[dict[str, str]] = []

    def repl(s: str) -> str:
        ns = s
        # 1단계: 독소 표현 직접 치환
        new_ns = re.sub(r"무제한\s*책임", "합리적인 범위 내의 책임(상한 적용)", ns)
        if new_ns != ns:
            changed_segs.append({"before": "무제한 책임", "after": "합리적인 범위 내의 책임(상한 적용)"})
            ns = new_ns
        new_ns = re.sub(r"모든\s*손해를\s*배상", "직접손해(간접손해·특별손해·영업손실 제외)를 배상", ns)
        if new_ns != ns:
            changed_segs.append({"before": "모든 손해를 배상", "after": "직접손해(간접손해·특별손해·영업손실 제외)를 배상"})
            ns = new_ns
        new_ns = re.sub(r"\bwithout\s+limitation\b", "subject to the liability cap set forth herein", ns, flags=re.IGNORECASE)
        if new_ns != ns:
            changed_segs.append({"before": "without limitation", "after": "subject to the liability cap set forth herein"})
            ns = new_ns
        new_ns = re.sub(r"\bunlimited\b", "capped at the contract value", ns, flags=re.IGNORECASE)
        if new_ns != ns:
            changed_segs.append({"before": "unlimited", "after": "capped at the contract value"})
            ns = new_ns
        # 책임 상한 문구 삽입
        cap_clause = " 단, 각 당사자의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며, 간접손해·특별손해·영업손실은 제외한다(고의·중과실 및 강행법규상 책임 제외)."
        if ns == s:
            ns = s + cap_clause
            changed_segs.append({"before": "(책임 상한 없음)", "after": cap_clause.strip()})
        else:
            ns = ns + " (총 책임 상한: 계약금액 또는 연간 총 대금. 간접손해·특별손해·영업손실 제외. 고의·중과실 및 강행법규상 책임 제외)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = (
            "해당 조항의 '" + ", ".join(matched_keywords[:3]) + "' 표현은 책임 범위를 무제한으로 확장할 위험이 있음. "
            "민법 제393조 및 계약 실무상 책임 상한(계약금액 기준)과 간접손해·특별손해·영업손실 제외를 "
            "조항 문장 내에 직접 삽입하여 과도한 손해배상 청구를 차단함."
        )
        return RewriteProposal(
            suggested_rewrite=_norm_ws(" ".join(patched)),
            rewrite_reason=reason,
            reason_codes=["RISK-001"],
            changed_segments=changed_segs,
        )
    if posture == "buyer_favorable":
        suffix = " 단, 당사의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며, 간접손해·특별손해·영업손실은 제외한다(고의·중과실 및 강행법규상 책임 제외)."
    elif posture == "seller_favorable":
        suffix = " 단, 상대방(구매자)의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며, 간접손해·특별손해·영업손실은 제외한다(고의·중과실 및 강행법규상 책임 제외)."
    else:
        suffix = " 단, 각 당사자의 총 책임은 계약금액(또는 연간 총 대금)을 상한으로 하며, 간접손해·특별손해·영업손실은 제외한다(고의·중과실 및 강행법규상 책임 제외)."
    suggested = _norm_ws(original + suffix)
    reason = "책임 상한 및 간접손해 제외가 명시되지 않아 책임 범위가 과도하게 확장될 위험이 있으므로, 상한 조건을 조항 내에 직접 삽입하여 보완함."
    return RewriteProposal(
        suggested_rewrite=suggested,
        rewrite_reason=reason,
        reason_codes=["RISK-001"],
        changed_segments=[{"before": "(책임 상한 없음)", "after": suffix.strip()}],
    )


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
    changed_segs: list[dict[str, str]] = []

    def repl(s: str) -> str:
        ns = s
        # 1단계: 일방 면책 → 상호주의로 치환
        if party_style == "KR-AB":
            new_ns = re.sub(r"(을은\s*갑을\s*면책(?:한다|함))", "각 당사자는 상대방을 합리적인 범위에서 면책", ns)
            if new_ns != ns:
                changed_segs.append({"before": "을은 갑을 면책", "after": "각 당사자는 상대방을 합리적인 범위에서 면책"})
                ns = new_ns
        # 2단계: 이의제기권 + 방어권 + 승인 절차 삽입
        procedure_clause = (
            " (제3자 청구에 따른 배상은 상호주의를 원칙으로 하며, "
            "①통지: 청구 수령 후 즉시 상대방에게 서면 통지, "
            "②방어권: 통지받은 당사자는 자신의 비용으로 방어에 참여할 권리를 가짐, "
            "③승인: 합의·변제는 상대방의 사전 서면 승인 없이 불가, "
            "④이의제기권: 배상 청구에 대하여 14일 이내 서면 이의 가능, "
            "⑤범위·한도: 귀책 범위 내로 제한)"
        )
        if ns == s:
            ns = s + procedure_clause
            changed_segs.append({"before": "(면책 절차 없음)", "after": procedure_clause.strip()})
        else:
            ns = ns + " (통지·방어권·승인·이의제기권·범위 한도 포함)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = (
            "면책·배상 조항이 일방 부담 또는 절차 부재로 해석될 소지가 있음(예: " + ", ".join(matched_keywords[:3]) + "). "
            "상호주의 원칙과 제3자 청구 절차(통지·방어권·승인·이의제기권)를 조항 문장 내에 직접 삽입하여 "
            "일방적 배상 청구 리스크를 차단함."
        )
        return RewriteProposal(
            suggested_rewrite=_norm_ws(" ".join(patched)),
            rewrite_reason=reason,
            reason_codes=["RISK-002"],
            changed_segments=changed_segs,
        )
    if posture == "buyer_favorable":
        suffix = (
            " (제3자 청구에 따른 배상은 상대방(공급자/시공자)의 귀책 범위 내에서 당사를 방어·면책하는 구조를 기본으로 하며, "
            "통지·방어권·합의/변제 승인·이의제기권 절차를 포함하고, 범위·사유·한도를 합리적으로 규정한다.)"
        )
    elif posture == "seller_favorable":
        suffix = (
            " (제3자 청구에 따른 배상은 상대방(구매자)의 귀책 범위 내에서 당사를 방어·면책하는 구조를 기본으로 하며, "
            "통지·방어권·합의/변제 승인·이의제기권 절차를 포함하고, 범위·사유·한도를 합리적으로 규정한다.)"
        )
    else:
        suffix = (
            " (제3자 청구에 따른 배상은 상호주의를 원칙으로 하며, "
            "통지·방어권·합의/변제 승인·이의제기권 절차를 포함하고, 범위·사유·한도를 합리적으로 제한한다.)"
        )
    suggested = _norm_ws(original + suffix)
    reason = "면책·제3자 청구 배상 조항의 절차(통지·방어권·승인·이의제기권)와 상호주의가 명확히 드러나지 않아 보완함."
    return RewriteProposal(
        suggested_rewrite=suggested,
        rewrite_reason=reason,
        reason_codes=["RISK-002"],
        changed_segments=[{"before": "(면책 절차 없음)", "after": suffix.strip()}],
    )


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
    changed_segs: list[dict[str, str]] = []

    def repl(s: str) -> str:
        ns = s
        # 1단계: 포괄적 자료 제공 요구 → 목적·범위 특정으로 치환
        new_ns = re.sub(r"기술자료를\s*제공(?:한다|하여야|해야)", "기술자료를 목적·범위·기간을 특정하여 최소한으로 제공하여야", ns)
        if new_ns != ns:
            changed_segs.append({"before": "기술자료를 제공", "after": "기술자료를 목적·범위·기간을 특정하여 최소한으로 제공하여야"})
            ns = new_ns
        # 2단계: 자료검토권 + 반환·파기 조건 삽입
        control_clause = (
            " (기술자료 제공 시: ①목적·범위·기간 특정 및 최소 제공 원칙, "
            "②계약 종료 또는 목적 달성 시 즉시 반환·파기 및 파기 확인서 제출, "
            "③제3자 제공·재사용·역설계 금지, "
            "④보안조치 의무 및 위반 시 손해배상, "
            "⑤당사의 자료검토권: 제공 자료의 사용 현황을 연 1회 이상 점검할 수 있음)"
        )
        if ns == s:
            ns = s + control_clause
            changed_segs.append({"before": "(기술자료 통제 조건 없음)", "after": control_clause.strip()})
        else:
            ns = ns + " (목적·범위·기간 특정, 최소 제공, 반환/파기, 제3자 제공 금지, 보안조치, 자료검토권)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = (
            "기술자료 제공 요구가 목적·범위·보안·반환 조건 없이 포괄적으로 해석될 수 있음(예: " + ", ".join(matched_keywords[:3]) + "). "
            "하도급법 제12조의3(기술자료 제공 요구 금지) 및 대리점법상 불이익 제공 금지 규정에 따라 "
            "제공 조건(목적·범위·기간)과 통제 수단(반환·파기·자료검토권)을 조항 내에 직접 삽입함."
        )
        return RewriteProposal(
            suggested_rewrite=_norm_ws(" ".join(patched)),
            rewrite_reason=reason,
            reason_codes=["RISK-004"],
            changed_segments=changed_segs,
        )
    if posture == "buyer_favorable":
        suffix = (
            " (당사가 제공하는 기술자료·원가자료·소스 등은 목적·범위·기간을 특정하여 최소한으로 제공하며, "
            "반환·파기, 재사용·역설계 금지, 제3자 제공 금지, 보안조치 및 위반 시 손해배상 기준을 포함하고, "
            "당사의 자료검토권을 보유한다.)"
        )
    else:
        suffix = (
            " (기술자료 제공은 목적·범위·기간을 특정하여 최소한으로 제공하며, "
            "반환·파기, 제3자 제공 금지, 보안조치 및 위반 시 손해배상 기준을 포함하고, "
            "당사의 자료검토권을 보유한다.)"
        )
    suggested = _norm_ws(original + suffix)
    reason = "기술자료 제공의 목적·범위·보안·반환 조건 및 자료검토권이 불명확하여 최소 통제 문구를 삽입함."
    return RewriteProposal(
        suggested_rewrite=suggested,
        rewrite_reason=reason,
        reason_codes=["RISK-004"],
        changed_segments=[{"before": "(기술자료 통제 조건 없음)", "after": suffix.strip()}],
    )


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
    changed_segs: list[dict[str, str]] = []

    def repl(s: str) -> str:
        ns = s
        # 1단계: 일방적 단가 조정 → 사전 협의·서면 합의로 치환
        new_ns = re.sub(r"일방적으로\s*(단가|가격|대금)를?\s*(조정|감액|변경)(?:한다|할\s*수\s*있다)",
                        r"사전 협의 및 서면 합의에 의하여만 \1를 \2할 수 있다", ns)
        if new_ns != ns:
            changed_segs.append({"before": "일방적으로 단가를 조정", "after": "사전 협의 및 서면 합의에 의하여만 단가를 조정할 수 있다"})
            ns = new_ns
        # 2단계: 이의제기권 + 자료검토권 삽입
        control_clause = (
            " (단가 조정·감액 시: ①객관적 사유(원가 변동, 시장 가격 변동 등)에 한정, "
            "②사전 협의 및 서면 합의 필수, "
            "③감액 범위·기간·산식·근거 명시, "
            "④당사의 이의제기권: 조정 통보 수령 후 14일 이내 서면 이의 가능, "
            "⑤당사의 자료검토권: 산출 근거 자료 제출 요구 가능)"
        )
        if ns == s:
            ns = s + control_clause
            changed_segs.append({"before": "(단가 조정 통제 조건 없음)", "after": control_clause.strip()})
        else:
            ns = ns + " (객관적 사유 + 사전협의/서면합의 + 산식/근거 명시 + 이의제기권 + 자료검토권)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = (
            "단가 감액·조정이 일방적으로 적용될 수 있는 표현이 있음(예: " + ", ".join(matched_keywords[:3]) + "). "
            "대리점법 제6조(불이익 제공 금지) 및 하도급법 제11조(부당한 단가 인하 금지)에 따라 "
            "객관적 요건·서면합의·산식·근거·이의제기권·자료검토권을 조항 내에 직접 삽입함."
        )
        return RewriteProposal(
            suggested_rewrite=_norm_ws(" ".join(patched)),
            rewrite_reason=reason,
            reason_codes=["RISK-005"],
            changed_segments=changed_segs,
        )
    suffix = (
        " (단가 조정·감액은 객관적 사유에 한정하고, 사전 협의 및 서면 합의로만 가능하며, "
        "범위·기간·산식·근거를 명시한다. 당사는 조정 통보 수령 후 14일 이내 서면으로 이의를 제기할 수 있으며, "
        "산출 근거 자료의 제출을 요구할 수 있다.)"
    )
    suggested = _norm_ws(original + suffix)
    reason = "단가 조정·감액의 객관적 요건·절차(사전협의/서면합의)·산식·근거·이의제기권·자료검토권이 불명확하여 보완함."
    return RewriteProposal(
        suggested_rewrite=suggested,
        rewrite_reason=reason,
        reason_codes=["RISK-005"],
        changed_segments=[{"before": "(단가 조정 통제 조건 없음)", "after": suffix.strip()}],
    )


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
    changed_segs: list[dict[str, str]] = []

    def repl(s: str) -> str:
        ns = s
        # 1단계: 포괄적 비용 부담 → 사전 서면 합의 조건으로 치환
        new_ns = re.sub(r"(판촉비|광고비|반품비|수수료|비용)를?\s*부담(?:한다|하여야|해야)",
                        r"\1을 사전 서면 합의된 항목·상한·정산 기준에 따라 부담하여야", ns)
        if new_ns != ns:
            changed_segs.append({"before": "비용을 부담", "after": "비용을 사전 서면 합의된 항목·상한·정산 기준에 따라 부담하여야"})
            ns = new_ns
        # 2단계: 이의제기권 + 자료검토권 + 상계권 세트 삽입
        defense_clause = (
            " (비용 부담 시: ①사전 서면 합의된 항목에 한정, "
            "②항목별 상한·정산 기준·증빙 명시, "
            "③일방 전가 금지, "
            "④당사의 이의제기권: 비용 청구 수령 후 14일 이내 서면 이의 가능, "
            "⑤당사의 자료검토권: 산출 근거 및 증빙 자료 제출 요구 가능, "
            "⑥당사의 상계권: 확정 채권을 자동채무와 상계 가능)"
        )
        if ns == s:
            ns = s + defense_clause
            changed_segs.append({"before": "(비용 전가 통제 조건 없음)", "after": defense_clause.strip()})
        else:
            ns = ns + " (사전 서면합의 + 항목별 상한/정산/증빙 + 일방전가 금지 + 이의제기권 + 자료검토권 + 상계권)"
        return ns

    patched, changed = _patch_sentence(sentences=sents, target_patterns=pats, replace_fn=repl)
    if changed:
        reason = (
            "비용 부담·전가가 포괄적으로 해석될 소지가 있음(예: " + ", ".join(matched_keywords[:3]) + "). "
            "대리점법 제6조(불이익 제공 금지) 및 제7조(경제적 이익 제공 강요 금지)에 따라 "
            "항목별 상한·정산·증빙·사전 서면합의 요건과 이의제기권·자료검토권·상계권을 조항 내에 직접 삽입함."
        )
        return RewriteProposal(
            suggested_rewrite=_norm_ws(" ".join(patched)),
            rewrite_reason=reason,
            reason_codes=["RISK-006"],
            changed_segments=changed_segs,
        )
    if posture == "buyer_favorable":
        suffix = (
            " (추가 비용·판촉비·광고비·반품비 등은 사전 서면 합의된 경우에 한하여 발생하며, "
            "항목별 상한·정산 기준·증빙을 명시한다. 상대방의 과실·지시·하자·지연으로 발생한 비용은 상대방이 부담한다. "
            "당사는 이의제기권·자료검토권·상계권을 보유한다.)"
        )
    else:
        suffix = (
            " (비용 부담 항목은 사전 서면 합의된 경우에 한하며, 항목별 상한·정산 기준·증빙을 명시하고 일방 전가를 금지한다. "
            "당사는 이의제기권·자료검토권·상계권을 보유한다.)"
        )
    suggested = _norm_ws(original + suffix)
    reason = "판촉비·광고비·반품 등 비용 부담 조항의 항목별 기준(상한·정산·증빙)과 사전 서면합의 요건 및 방어권 세트가 불명확하여 보완함."
    return RewriteProposal(
        suggested_rewrite=suggested,
        rewrite_reason=reason,
        reason_codes=["RISK-006"],
        changed_segments=[{"before": "(비용 전가 통제 조건 없음)", "after": suffix.strip()}],
    )


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


def _replace_first_line(
    text: str,
    *,
    predicate,
    replacement_line: str,
) -> tuple[str, bool]:
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if predicate(line):
            lines[i] = replacement_line
            return _norm_ws("\n".join(lines)), True
    return _norm_ws(text), False


def _insert_after_first_match(text: str, *, predicate, insert_line: str) -> str:
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if predicate(line):
            lines.insert(i + 1, insert_line)
            return _norm_ws("\n".join(lines))
    if lines:
        lines.append(insert_line)
        return _norm_ws("\n".join(lines))
    return _norm_ws(insert_line)


def _has_any(text: str, needles: list[str]) -> bool:
    t = (text or "").lower()
    return any((n or "").lower() in t for n in needles if isinstance(n, str) and n)


_AMBIG = ["별도 협의", "추후 협의", "상호 협의", "협의한다", "협의하여", "별도로 정한다", "추후 정한다", "to be agreed", "tbd"]


def _rewrite_app_001_ip(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    repl = (
        f"개발 산출물(소스코드 포함)에 대한 저작권 및 지식재산권은 {our}에게 귀속하며, "
        f"{cp}는 제3자 권리침해가 없음을 보증하고 권리침해 주장 시 자신의 비용과 책임으로 시정하며 {our}를 면책한다."
    )
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["저작권", "지식재산", "산출물", "소스코드", "ip"]) and _has_any(l, _AMBIG),
        replacement_line=repl,
    )
    if not replaced and _has_any(original, ["저작권", "지식재산", "산출물", "소스코드", "ip"]):
        out = _insert_after_first_match(
            out,
            predicate=lambda l: _has_any(l, ["저작권", "지식재산", "산출물", "소스코드", "ip"]),
            insert_line=repl,
        )
    reason = "산출물/소스코드/IP 귀속 및 제3자 권리침해 보증·시정 책임을 문장 내에 직접 반영."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-001"])


def _rewrite_app_002_oss(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    ins = (
        f"오픈소스/서드파티 사용 시 {cp}는 라이선스·버전·적용범위 및 목록(SBOM)을 {our}에게 제공하고, "
        f"카피레프트(GPL 등)는 {our}의 사전 서면 승인 없이 사용하지 않으며, 위반 시 자신의 비용과 책임으로 시정하고 손해를 배상한다."
    )
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["오픈소스", "open source", "라이선스", "license"]) and _has_any(l, _AMBIG),
        replacement_line=ins,
    )
    if not replaced and _has_any(original, ["오픈소스", "open source", "라이선스", "license", "서드파티", "third party"]):
        out = _insert_after_first_match(out, predicate=lambda l: _has_any(l, ["오픈소스", "open source", "라이선스", "license"]), insert_line=ins)
    reason = "오픈소스 사용의 고지·승인·준수·위반 시 시정/배상 구조를 조항 내에 직접 반영."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-002"])


def _rewrite_app_003_sow(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    ins = f"개발 범위/요구사항(SOW) 및 변경요청은 {our}의 서면 승인에 따라 확정되며, 승인 없는 추가 개발/비용 청구는 인정되지 않는다."
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["범위", "사양", "요구사항", "SOW", "변경"]) and _has_any(l, _AMBIG),
        replacement_line=ins,
    )
    if not replaced and _has_any(original, ["범위", "사양", "요구사항", "SOW", "변경요청", "change request"]):
        out = _insert_after_first_match(out, predicate=lambda l: _has_any(l, ["범위", "사양", "요구사항", "SOW"]), insert_line=ins)
    reason = "SOW/변경관리(승인·비용·일정) 핵심 문구를 별도 보강문이 아닌 본문 문장으로 흡수."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-003"])


def _rewrite_app_004_acceptance(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    ins = (
        f"검수 기준 및 검수 기간은 사전에 서면으로 확정하며, {our}의 서면 합격 통지 전에는 간주검수를 적용하지 않는다. "
        f"{cp}는 보완 요청이 있는 경우 무상으로 보완 후 재검수를 진행한다."
    )
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["검수", "인수", "acceptance", "간주검수"]) and _has_any(l, _AMBIG),
        replacement_line=ins,
    )
    if not replaced and _has_any(original, ["검수", "인수", "acceptance", "간주검수"]):
        out = _insert_after_first_match(out, predicate=lambda l: _has_any(l, ["검수", "인수", "acceptance"]), insert_line=ins)
    reason = "검수/간주검수 핵심 요건을 조항 내 문장으로 흡수하여 분쟁 가능성을 낮춤."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-004"])


def _rewrite_app_006_sla(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    ins = (
        f"유지보수/SLA는 장애 등급별 응답·복구 시간 및 에스컬레이션 절차를 포함하여 사전에 서면으로 확정하며, "
        f"반복 위반 시 {our}는 감액/크레딧 및 해지 등 구제수단을 가진다."
    )
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["SLA", "가용성", "응답", "복구", "장애", "유지보수", "uptime"]) and _has_any(l, _AMBIG),
        replacement_line=ins,
    )
    if not replaced and _has_any(original, ["SLA", "가용성", "응답", "복구", "장애", "유지보수", "uptime"]):
        out = _insert_after_first_match(out, predicate=lambda l: _has_any(l, ["SLA", "유지보수", "장애", "가용성", "uptime"]), insert_line=ins)
    reason = "SLA 핵심 요소(응답/복구·구제수단)를 과잉 보강문이 아닌 조항 문장으로 반영."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-006"])


def _rewrite_app_007_security(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    ins = (
        f"침해사고(보안사고/개인정보 유출) 발생 시 {cp}는 즉시 {our}에 통지하고 조사·시정·재발방지에 협력하며, "
        f"{cp}의 귀책으로 인한 사고에 대해서는 관련 비용 및 손해를 배상한다."
    )
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["보안", "침해", "유출", "사고", "incident", "개인정보"]) and _has_any(l, _AMBIG),
        replacement_line=ins,
    )
    if not replaced and _has_any(original, ["보안", "침해", "유출", "사고", "incident", "개인정보"]):
        out = _insert_after_first_match(out, predicate=lambda l: _has_any(l, ["보안", "침해", "유출", "사고", "개인정보"]), insert_line=ins)
    reason = "침해사고 통지·협력·배상 책임을 조항 본문에 직접 반영."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-007"])


def _rewrite_app_009_subcontract(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    repl = f"재위탁(하도급) 또는 협력업체 활용은 {our}의 사전 서면 승인 하에만 가능하며, {cp}는 하위수탁자에 대하여 동일한 책임을 부담한다."
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["재위탁", "하도급", "외주", "협력업체", "subcontract"]) and (_has_any(l, _AMBIG) or _has_any(l, ["할 수 있다", "가능하다"])),
        replacement_line=repl,
    )
    if not replaced and _has_any(original, ["재위탁", "하도급", "외주", "협력업체", "subcontract"]):
        out = _insert_after_first_match(out, predicate=lambda l: _has_any(l, ["재위탁", "하도급", "외주", "협력업체", "subcontract"]), insert_line=repl)
    reason = "재위탁 허용 문구를 최소 변경으로 ‘사전 서면 승인 + 동일 책임’ 구조로 전환."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-009"])


def _rewrite_app_010_data(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    ins = (
        f"계약 종료 또는 {our}의 요청 시 {cp}는 {our}의 데이터(백업/로그 포함)를 반환한 후 관련 법령 및 {our}의 지시에 따라 파기/삭제하고, 삭제 완료를 확인할 수 있는 증적을 제공한다."
    )
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["데이터", "반환", "삭제", "파기", "백업", "로그"]) and _has_any(l, _AMBIG),
        replacement_line=ins,
    )
    if not replaced and _has_any(original, ["데이터", "반환", "삭제", "파기"]):
        out = _insert_after_first_match(out, predicate=lambda l: _has_any(l, ["데이터", "반환", "삭제", "파기"]), insert_line=ins)
    reason = "종료 시 데이터 반환·삭제(백업/로그 포함) 및 삭제 확인을 조항 본문에 직접 반영."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-010"])


def _rewrite_app_011_handover(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    ins = (
        f"계약 종료 시 {cp}는 인수인계에 필요한 자료(소스코드, 빌드/배포 스크립트, 환경설정, 운영 매뉴얼 등)를 {our}에게 제공하고 전환(마이그레이션)에 협력한다."
    )
    out, replaced = _replace_first_line(
        original,
        predicate=lambda l: _has_any(l, ["종료", "해지", "인수인계", "전환", "migration", "마이그레이션"]) and _has_any(l, _AMBIG),
        replacement_line=ins,
    )
    if not replaced and _has_any(original, ["종료", "해지", "인수인계", "전환", "migration", "마이그레이션"]):
        out = _insert_after_first_match(out, predicate=lambda l: _has_any(l, ["종료", "해지", "인수인계", "전환", "migration", "마이그레이션"]), insert_line=ins)
    reason = "종료/전환(인수인계) 핵심 의무를 조항 본문 문장으로 흡수하여 과잉 수정(덧붙임) 최소화."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["APP-011"])


def propose_clause_specific_rewrite(
    *,
    clause_text: str,
    applied_rules: list[dict[str, Any]],
    posture: str = "neutral",
    party: PartyRole | None = None,
    contract_context: dict[str, Any] | None = None,
) -> RewriteProposal | None:
    text = _norm_ws(clause_text)
    if not text:
        return None

    proposals: list[RewriteProposal] = []
    rids = {str(ar.get("rule_id") or "") for ar in applied_rules if isinstance(ar, dict)}

    # -----------------------------------------------------------------------
    # 0단계: 독소 표현 일괄 제거 (전처리)
    # -----------------------------------------------------------------------
    detoxed_text, toxin_segs = _apply_toxin_removal(text)

    # -----------------------------------------------------------------------
    # 1단계: 대리점법 제18조 경영간섭 위험 감지 및 방어 (DEALER-001)
    # -----------------------------------------------------------------------
    our = _party_term(party, which="our")
    cp = _party_term(party, which="counterparty")
    mgmt_proposal = _rewrite_mgmt_interference(detoxed_text, our=our, cp=cp)
    if mgmt_proposal:
        proposals.append(mgmt_proposal)

    contractor_proposal = _rewrite_fursys_contractor_picks(detoxed_text, party=party)
    if contractor_proposal:
        proposals.append(contractor_proposal)

    rental_proposal = _rewrite_fursys_rental_picks(detoxed_text, party=party)
    if rental_proposal:
        proposals.append(rental_proposal)

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
            p = _rewrite_risk_001_liability_cap(detoxed_text, matched_keywords=mk, posture=posture)
        elif rid == "RISK-002":
            p = _rewrite_risk_002_indemnity(detoxed_text, matched_keywords=mk, posture=posture)
        elif rid == "RISK-004":
            p = _rewrite_risk_004_tech_data(detoxed_text, matched_keywords=mk, posture=posture)
        elif rid == "RISK-005":
            p = _rewrite_risk_005_price_reduction(detoxed_text, matched_keywords=mk, posture=posture)
        elif rid == "RISK-006":
            p = _rewrite_risk_006_cost_shift(detoxed_text, matched_keywords=mk, posture=posture)
        elif rid == "APP-001":
            p = _rewrite_app_001_ip(detoxed_text, posture=posture, party=party)
        elif rid == "APP-002":
            p = _rewrite_app_002_oss(detoxed_text, posture=posture, party=party)
        elif rid == "APP-003":
            p = _rewrite_app_003_sow(detoxed_text, posture=posture, party=party)
        elif rid == "APP-004":
            p = _rewrite_app_004_acceptance(detoxed_text, posture=posture, party=party)
        elif rid == "APP-006":
            p = _rewrite_app_006_sla(detoxed_text, posture=posture, party=party)
        elif rid == "APP-007":
            p = _rewrite_app_007_security(detoxed_text, posture=posture, party=party)
        elif rid == "APP-009":
            p = _rewrite_app_009_subcontract(detoxed_text, posture=posture, party=party)
        elif rid == "APP-010":
            p = _rewrite_app_010_data(detoxed_text, posture=posture, party=party)
        elif rid == "APP-011":
            p = _rewrite_app_011_handover(detoxed_text, posture=posture, party=party)
        elif rid == "C-001":
            p = _rewrite_c_001_settlement(detoxed_text, posture=posture, party=party)
        elif rid == "ACT-004":
            jur = None
            if isinstance(contract_context, dict):
                j = contract_context.get("jurisdiction")
                if isinstance(j, dict) and isinstance(j.get("kind"), str):
                    jur = j
            if jur is None:
                jp = classify_jurisdiction_profile(text=str(contract_context.get("contract_text") if isinstance(contract_context, dict) else "") or detoxed_text)
                jur = jp.to_dict()
            p = _rewrite_act_004_dispute(detoxed_text, posture=posture, party=party, jur=jur)

        if p:
            proposals.append(p)

    if not proposals and any(r in rids for r in ("RISK-003", "ACT-010")):
        p2 = _rewrite_safety_gap(detoxed_text, posture=posture)
        if p2:
            proposals.append(p2)

    # 독소 제거만 있고 다른 proposal이 없는 경우에도 결과 반환
    if not proposals and toxin_segs:
        reason = "독소 표현(무제한·즉시·일방적으로 등)을 방어 표현으로 치환함."
        return RewriteProposal(
            suggested_rewrite=polish_korean_legal_style(_norm_ws(detoxed_text)),
            rewrite_reason=reason,
            reason_codes=["TOXIN-REMOVAL"],
            changed_segments=toxin_segs,
        )

    if not proposals:
        return None

    # -----------------------------------------------------------------------
    # 병합: reason_codes, reasons, changed_segments 통합
    # -----------------------------------------------------------------------
    merged_reason_codes: list[str] = []
    merged_reasons: list[str] = []
    merged_segments: list[dict[str, str]] = list(toxin_segs)  # 독소 제거 세그먼트 포함
    out_text = proposals[0].suggested_rewrite

    for p in proposals:
        if p.suggested_rewrite and p.suggested_rewrite != out_text:
            out_text = p.suggested_rewrite
        for c in p.reason_codes:
            if c not in merged_reason_codes:
                merged_reason_codes.append(c)
        if p.rewrite_reason and p.rewrite_reason not in merged_reasons:
            merged_reasons.append(p.rewrite_reason)
        for seg in (p.changed_segments or []):
            if seg not in merged_segments:
                merged_segments.append(seg)

    # 텍스트 기반 추가 세그먼트 추출
    auto_segs = _extract_changed_segments(text, out_text)
    for seg in auto_segs:
        if seg not in merged_segments:
            merged_segments.append(seg)

    # risk_tier 산정
    risk_tier = _infer_risk_tier(reason_codes=merged_reason_codes, text=text)

    final_rewrite = polish_korean_legal_style(_norm_ws(out_text))
    final_reason = polish_korean_legal_style(" / ".join(merged_reasons))[:900]

    return RewriteProposal(
        suggested_rewrite=final_rewrite,
        rewrite_reason=final_reason,
        reason_codes=merged_reason_codes,
        changed_segments=merged_segments[:10],
    )


def _rewrite_fursys_contractor_picks(text: str, *, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    if party is None or party.our_role != "contractor":
        return None

    out = original
    changed: list[dict[str, str]] = []
    reasons: list[str] = []

    if "지체상금" in out and re.search(r"(0\s*\.\s*3\s*%|0\s*\.\s*3\s*퍼센트|0\s*\.\s*3\s*percent)", out, flags=re.IGNORECASE):
        before = re.search(r"(0\s*\.\s*3\s*%|0\s*\.\s*3\s*퍼센트|0\s*\.\s*3\s*percent)", out, flags=re.IGNORECASE)
        out2 = re.sub(r"(0\s*\.\s*3\s*%|0\s*\.\s*3\s*퍼센트|0\s*\.\s*3\s*percent)", "0.1%", out, count=1, flags=re.IGNORECASE)
        if out2 != out:
            changed.append({"before": (before.group(0) if before else "0.3%"), "after": "0.1%"})
            out = out2
            reasons.append("지체상금 일 0.3%는 과도하므로 일 0.1% 이하로 조정.")

    if re.search(r"(상계|공제|차감)", out) and ("확정" not in out or "채권" not in out):
        add = (
            " 공제/상계는 상대방에 대한 확정 채권이 존재하고, 사유·금액·산정 기준에 관하여 사전 서면 합의한 경우에 한하여 허용한다."
        )
        if add.strip() not in out:
            out = _norm_ws(out + "\n" + add)
            changed.append({"before": "(확정 채권/사전 서면합의 요건 없음)", "after": add.strip()})
            reasons.append("도급인의 임의 공제/상계(수수료 차감 등)를 방지하기 위해 확정 채권 및 사전 서면합의 요건을 추가.")

    if re.search(r"(해지|종료)", out) and ("최고" in out or "즉시" in out) and ("30일" not in out):
        add = " 해지 전 위반 사항을 특정하여 30일 이상의 기간을 정해 서면으로 최고하고, 상대방에게 시정 기회를 부여한다."
        out = _norm_ws(out + "\n" + add)
        changed.append({"before": "(30일 서면 최고 절차 없음)", "after": add.strip()})
        reasons.append("도급인의 일방적 즉시 해지권 남용을 방지하기 위해 30일 이상의 서면 최고·시정 절차를 삽입.")

    if re.search(r"(안전|안전사고|산업안전|중대재해|안전관리|작업중지|현장|시공|공사|산안법)", out) and ("발주자" not in out or "현장" not in out or "하자" not in out):
        add = (
            " 안전관리는 상호 협력 원칙에 따라 수행하며, 발주자가 제공한 자료/도면/지시의 하자 또는 발주자가 제공·관리하는 현장의 기존 하자(시설·전기·구조물 등)로 인한 사고는 수급인의 책임에서 면제 또는 감경한다."
        )
        out = _norm_ws(out + "\n" + add)
        changed.append({"before": "(발주자 제공자료/현장 하자 면책 없음)", "after": add.strip()})
        reasons.append("수급인 일방 책임 전가를 차단하고 발주자 제공자료/현장 하자 귀책을 명확히 하기 위해 안전 조항을 보강.")

    if not changed:
        return None

    reason = " / ".join(reasons)[:900]
    return RewriteProposal(
        suggested_rewrite=out,
        rewrite_reason=reason,
        reason_codes=["FURSYS-CT-001"],
        changed_segments=changed[:10],
    )


def _rewrite_fursys_rental_picks(text: str, *, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    if party is None or party.our_role != "rental_provider":
        return None

    out = original
    changed: list[dict[str, str]] = []
    reasons: list[str] = []

    if _has_any(out, ["소유권", "임의", "양도", "담보", "처분"]) and "소유권" in out:
        pass
    else:
        add = " 렌탈 기간 동안 목적물의 소유권은 렌탈업자(퍼시스)에 존속하며, 고객은 목적물을 임의로 처분·양도·담보 제공할 수 없다."
        out = _norm_ws(out + "\n" + add)
        changed.append({"before": "(소유권/임의처분 금지 명시 없음)", "after": add.strip()})
        reasons.append("자산 소유권을 명확히 하고 임의 처분을 방지.")

    if "위약금" in out or "중도해지" in out:
        if "10%" not in out:
            add = " 중도해지 위약금은 실제 손해를 초과하지 않는 범위에서 산정하며, 잔여 렌탈료의 10%를 상한으로 한다."
            out = _norm_ws(out + "\n" + add)
            changed.append({"before": "(중도해지 위약금 상한 없음)", "after": add.strip()})
            reasons.append("중도해지 위약금이 과도해 약관 리스크로 확대되지 않도록 상한을 명시.")

    if "청약철회" in out:
        if _has_any(out, ["불가", "제한", "불인정", "포기"]) and "방해" not in out:
            add = " 청약철회권의 행사 절차를 과도하게 제한하거나 방해하지 않으며, 법령상 제한 사유가 있는 경우에만 예외를 둔다."
            out = _norm_ws(out + "\n" + add)
            changed.append({"before": "(청약철회 절차 방해 가능)", "after": add.strip()})
            reasons.append("청약철회권 침해로 평가될 소지를 줄이기 위해 행사 절차를 정리.")

    if _has_any(out, ["신용정보", "채권추심", "추심", "연체", "위탁"]) and ("동의" not in out or "고지" not in out):
        add = " 렌탈료 연체에 따른 채권추심 위탁 또는 신용정보의 조회·제공이 필요한 경우, 관련 법령에 따른 사전 고지 및 적법한 동의를 전제로 한다."
        out = _norm_ws(out + "\n" + add)
        changed.append({"before": "(추심/신용정보 동의·고지 전제 없음)", "after": add.strip()})
        reasons.append("채권추심·신용정보 처리의 적법 절차를 명확히 함.")

    if not changed:
        return None

    reason = " / ".join(reasons)[:900]
    return RewriteProposal(
        suggested_rewrite=out,
        rewrite_reason=reason,
        reason_codes=["FURSYS-RENT-001"],
        changed_segments=changed[:10],
    )


def _rewrite_act_004_dispute(text: str, *, posture: str, party: PartyRole | None, jur: dict[str, object]) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    kind = str(jur.get("kind") or "")
    is_domestic = kind == "domestic_korea"
    if not (re.search(r"(준거법|관할|재판|전속관할|합의관할|중재|조정|분쟁)", original) or re.search(r"(governing law|jurisdiction|arbitration)", original, flags=re.IGNORECASE)):
        return None

    our = "당사"
    if party is not None:
        our = "당사"

    if is_domestic:
        if ("민사소송법" in original and "관할" in original) or ("전속관할" in original) or ("합의관할" in original) or ("관할법원" in original):
            return None
        if ("서울중앙지방법원" in original and "전속" in original) or ("서울중앙지방법원" in original and "관할" in original):
            return None
        has_governing = bool(re.search(r"(대한민국\s*법률|준거법|governing\s+law)", original, flags=re.IGNORECASE))
        venue_line = "본 계약과 관련하여 발생하는 분쟁에 관한 관할법원은 민사소송법 등 관련 법령에 따른 관할법원으로 한다."
        if has_governing:
            patched = _norm_ws(original + "\n" + venue_line)
        else:
            patched = _norm_ws(original + "\n" + venue_line)
        reason = "국내 계약 분쟁조항은 ‘해외 집행’ 논리보다 관할(전속관할/합의관할/민사소송법상 관할) 구조를 중심으로 점검."
        return RewriteProposal(suggested_rewrite=patched, rewrite_reason=reason, reason_codes=["ACT-004"])

    has_governing = bool(re.search(r"(준거법|governing\s+law)", original, flags=re.IGNORECASE))
    has_forum = bool(re.search(r"(전속관할|합의관할|관할\s*법원|jurisdiction|중재|arbitration)", original, flags=re.IGNORECASE))
    if has_governing and has_forum:
        return None
    add = "준거법과 분쟁해결 방식(관할 또는 중재)을 명시한다.\n- 준거법: [협의한 법률]\n- 관할 또는 중재: [관할법원/중재기관·중재지]"
    out = original + "\n" + add
    reason = "해외 거래에서는 준거법·관할/중재를 명확히 하고 집행 가능성, 비용, 기간 리스크를 함께 고려한다."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["ACT-004"])


def _rewrite_c_001_settlement(text: str, *, posture: str, party: PartyRole | None) -> RewriteProposal | None:
    original = _norm_ws(text)
    if not original:
        return None
    if not re.search(r"(정산|상계|공제|차감|대금|지급|invoice|세금계산서)", original, flags=re.IGNORECASE):
        return None
    if ("산식" in original or "정산기준" in original or "공제사유" in original or "증빙" in original) and ("기한" in original or "기간" in original):
        return None
    ins = "정산은 산식·정산주기·정산기한을 명시하고, 상계/공제는 사유를 제한적으로 열거하며, 증빙 요구는 목적·범위를 합리적으로 제한한다."
    out = original
    if ins not in out:
        out = out + "\n" + ins
    reason = "정산/상계/공제는 대금 분쟁의 핵심이므로 산식·사유·증빙·기한을 조항 본문 기준으로 명확화."
    return RewriteProposal(suggested_rewrite=out, rewrite_reason=reason, reason_codes=["C-001"])
