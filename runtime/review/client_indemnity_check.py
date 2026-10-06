"""우리 회사가 상대방을 **귀책과 무관하게** 방어·면책하는 일방 조항 (2026-10-06 범용 보정).

실측(서울대 산학연구계약 제12조 제2항):
    "“(주)퍼시스”는 연구에서 직접 발생하거나 연구와 관련되어 발생하는 모든 담보책임, 소송, 고소로부터
     “학교”와 연구책임자를 방어하고 손해가 없도록 보호한다."

연구를 수행하는 쪽은 상대방인데, 그 연구에서 생기는 모든 책임·소송을 우리가 막아 주도록 되어 있다.
상대방(또는 그 연구책임자)의 고의·과실로 생긴 청구까지 우리가 떠안는다. 같은 문형의 반대 방향 조항이
없으면(상호 면책이 아니면) 일방적 위험전가다.

이 점검은 계약유형을 묻지 않는다 — 법률효과(누가 누구를, 어떤 범위로 방어·면책하는가)만 본다.
"""
from __future__ import annotations

import re
from typing import Any

#: 넓은 범위 — "모든/일체의 … 책임·청구·소송·손해" 와 방어·면책 동사가 한 문장에 함께 있다.
_RX_BROAD = re.compile(r"(?:모든|일체의?|어떠한)\s*[^.]{0,40}(?:책임|청구|소송|고소|손해|분쟁)")
_RX_DEFEND = re.compile(r"방어하(?:고|며|여야)|손해가\s*없도록|면책(?:시키|하여야|한다)|보호한다")
#: 귀책으로 범위를 좁힌 문언이 이미 있으면 일방 조항이라도 위험전가가 아니다.
_RX_FAULT_LIMIT = re.compile(r"귀책|고의|과실|책임\s*있는\s*사유|위반으로\s*인(?:한|하여)|에\s*기인한")
_RX_PROTECTED = re.compile(r"로부터\s*(.{1,40}?)(?:을|를)\s*(?:방어|보호|면책)")


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _flat(s: str) -> str:
    return re.sub(r"\s*\n\s*", " ", str(s or "")).strip()


def _subject_rx(labels: list[str]) -> re.Pattern[str] | None:
    cores = sorted({re.sub(r"주식회사|㈜|\(주\)", "", lb).strip() for lb in labels if lb}, key=len, reverse=True)
    cores = [c for c in cores if len(c) >= 2]
    if not cores:
        return None
    alt = "|".join(re.escape(c) for c in cores)
    return re.compile(r"^\s*([“\"]?(?:\(주\)|㈜|주식회사\s*)?(?:" + alt + r")[”\"]?)\s*(?:은|는|이|가)\s")


def find_client_indemnity(
    *, clauses: list[Any] | None, our_labels: list[str],
) -> list[dict[str, Any]]:
    subj = _subject_rx(our_labels)
    if subj is None:
        return []
    out: list[dict[str, Any]] = []
    defend_sentences: list[tuple[Any, str]] = []
    for c in clauses or []:
        if not _attr(c, "article_number"):
            continue
        for sent in re.split(r"(?<=다\.)\s+", _flat(_attr(c, "text"))):
            if _RX_DEFEND.search(sent) and _RX_BROAD.search(sent):
                defend_sentences.append((c, sent))
    for c, sent in defend_sentences:
        m = subj.search(sent)
        if not m or _RX_FAULT_LIMIT.search(sent):
            continue
        protected = _RX_PROTECTED.search(sent)
        them = protected.group(1).strip() if protected else "상대방"
        # 같은 문형으로 상대방이 우리를 방어하는 조항이 있으면 상호 면책이다.
        if any(other is not c and not subj.search(s) for other, s in defend_sentences):
            continue
        us = m.group(1)
        addition = (f"다만, 본 항의 책임은 {us}의 고의 또는 과실로 발생한 청구에 한하며, {them}의 고의 또는 "
                    "과실로 발생한 경우에는 그러하지 아니하다.")
        original = _attr(c, "text").rstrip()
        out.append({
            "clause_id": f"clr_one_sided_client_indemnity__{_attr(c, 'clause_id')}",
            "clause_title": _attr(c, "title"),
            "display_path": _attr(c, "display_path"),
            "article_number": _attr(c, "article_number"),
            "paragraph_number": _attr(c, "paragraph_number"),
            "original_text": _attr(c, "text"),
            "risk_tier": "HIGH", "severity": "HIGH", "confidence": 0.95,
            "is_common_legal_risk": True,
            "problem": (f"{us}가 {them}를 '모든' 책임·소송·고소로부터 방어하고 손해가 없도록 보호하도록 되어 있고, "
                        f"귀책사유로 범위를 한정하는 문언이 없다. 반대 방향의 면책 조항도 없어 {them} 쪽의 고의·과실로 "
                        "생긴 청구까지 우리가 떠안는다."),
            "legal_business_reason": ("손해배상은 원래 귀책사유가 있는 당사자가 부담한다(민법 제390조). 이 항은 그 원칙을 "
                                      "뒤집어 상대방이 수행하는 업무에서 생기는 모든 분쟁의 방어비용과 배상까지 우리에게 "
                                      "돌리며, 금액 상한도 없다."),
            "high_severity_basis": "상한·귀책 제한 없는 일방적 방어·면책 의무",
            "suggested_rewrite": f"{original} {addition}",
            "recommendation_text": f"{original} {addition}",
            "location_instruction": f"{_attr(c, 'display_path')} 말미에 다음 문구 추가",
            "negotiation_position": ("삭제가 어려우면 우리 귀책·우리 사용으로 생긴 청구로 한정하는 단서를 1순위로, "
                                     "그것도 어려우면 상호 면책으로 바꾸도록 요청합니다."),
            "detected_issue_list": [{"issue_title": "[일방적 방어·면책] 귀책과 무관하게 상대방을 모든 책임·소송에서 보호"}],
            "legal_effect_tags": ["indemnity", "uncapped_liability"],
        })
    return out


__all__ = ["find_client_indemnity"]
