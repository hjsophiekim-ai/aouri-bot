"""Existing Protection Check — 이미 해결된 보호장치는 KEEP, 같은 쟁점을 다시 만들지 않는다.

2026-10-01 지시 (와이어드 Golden Fix 5항) — 법무팀 수정본이 이미 해결한 판단:
    A. 최저가     공급자가 통제할 수 있는 **직접판매**만 제한, 제3자 저가판매는 책임 없음
    B. 제3자 판매  판매자가 제3자(셀러)를 관리·감독하고 그 귀책 손해를 부담
    C. 정산 대행   대행시켜도 공급자에 대한 지급책임은 판매자가 부담
    D. 제조물책임  제품 결함 → 공급자 / 판매자의 보관·배송·임의 표시변경 → 판매자 귀책 범위
    E. 개인정보    목적 외 이용 제한·제3자 제공 제한·사고 통지·종료 후 파기
"이런 이미 해결된 이슈를 다시 HIGH/MEDIUM 으로 중복 생성하지 마세요."

계약유형 룰팩이 아니다 — 법률효과(문형)로만 판정하므로 다른 판매·공급 계약에도 그대로 쓴다.
각 보호장치는 **한 조 안에** 필요한 문형이 모두 있어야 성립한다(흩어진 낱말로 세지 않는다).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass(frozen=True)
class Protection:
    key: str
    title: str
    #: 한 조 안에 모두 있어야 하는 문형.
    required: tuple[re.Pattern[str], ...]
    keep_reason: str
    #: 이 보호장치가 이미 해결한 finding 의 표지(제목·문제).
    covers: re.Pattern[str]


PROTECTIONS: tuple[Protection, ...] = (
    Protection(
        "lowest_price_controllable",
        "최저가 — 공급자 통제 범위로 한정",
        (_rx(r"최저(?:판매)?가"), _rx(r"직접\s*판매하여서는\s*아니"),
         _rx(r"제\s*3\s*자[^.]{0,60}(?:책임도|책임을)\s*부담하지\s*아니")),
        "공급자가 직접 판매하는 가격만 제한하고, 제3자가 더 낮은 가격으로 파는 경우 공급자는 책임을 지지 않는다 — 통제할 수 있는 범위로 이미 한정되어 있다",
        _rx(r"최저가|최저\s*판매\s*가|가격\s*보장"),
    ),
    Protection(
        "third_party_seller_supervision",
        "제3자 판매·홍보 — 판매자 관리·감독과 귀책 손해 부담",
        (_rx(r"제\s*3\s*자를?\s*통하여[^.]{0,30}(?:판매|홍보)"), _rx(r"관리\s*[·ㆍ]?\s*감독"),
         _rx(r"(?:귀책|행위)[^.]{0,60}손해[^.]{0,30}배상")),
        "판매자가 제3자(셀러)의 판매·홍보를 관리·감독하고 그 행위·귀책으로 생긴 손해를 배상하도록 이미 규정되어 있다",
        _rx(r"셀러|인플루언서|제\s*3\s*자[^.]{0,20}(?:판매|홍보)|표시\s*[·ㆍ]?\s*광고|경제적\s*이해관계"),
    ),
    Protection(
        "payment_agent_liability_retained",
        "정산 대행 — 지급책임은 판매자에게 남음",
        (_rx(r"대행(?:하게|시킬|할)"), _rx(r"이\s*경우에도[^.]{0,60}지급\s*의무")),
        "정산 업무를 자회사에 대행시켜도 공급자에 대한 정산금 지급의무와 계약상 책임은 판매자가 부담하도록 이미 정해져 있다",
        _rx(r"정산\s*(?:주체|대행)|자회사|지급\s*주체|대금\s*미지급|이행\s*유보"),
    ),
    Protection(
        "product_liability_boundary",
        "제조물책임 — 결함은 공급자, 보관·배송·표시변경은 판매자 귀책 범위",
        (_rx(r"제조물\s*책임"), _rx(r"결함"),
         _rx(r"(?:보관|배송)[^.]{0,60}(?:과실|귀책)[^.]{0,120}(?:판매사|회사)[”\"']?(?:가|이)?[^.]{0,20}부담")),
        "제품 자체의 결함은 공급자가, 판매자의 보관·배송상 과실이나 승인 없는 표시 변경으로 생기거나 커진 손해는 판매자가 그 귀책 범위에서 부담하도록 경계가 이미 나뉘어 있다",
        _rx(r"제조물|결함|하자[^.]{0,20}책임|하자[^.]{0,6}귀책|소비자[^.]{0,30}책임\s*배분|배송·하자"),
    ),
    Protection(
        "personal_data_controls",
        "개인정보 — 목적 외 이용·제3자 제공 제한, 사고 통지, 종료 후 파기",
        (_rx(r"개인정보"), _rx(r"목적\s*외"), _rx(r"제\s*3\s*자에게\s*제공"),
         _rx(r"(?:유출|사고)[^.]{0,60}(?:알리|통지)"), _rx(r"파기")),
        "목적 외 이용 제한, 제3자 제공 제한, 유출 사고 통지, 계약 종료 후 파기가 이미 규정되어 있다",
        _rx(r"개인정보|보안\s*사고|유출"),
    ),
    Protection(
        "confidentiality_consent",
        "비밀유지 — 제3자 공개는 상대방 사전 서면동의",
        (_rx(r"비밀"), _rx(r"사전\s*서면\s*동의\s*없이[^.]{0,40}(?:공개|제공)")),
        "제3자 공개를 상대방의 사전 서면동의에 걸어 두는 합리적 구조다 — 동의권자·회신기한·무응답 간주를 덧붙일 실익이 없다",
        _rx(r"비밀유지[^.]{0,20}(?:동의|절차|응답)|동의권자|응답\s*기한|서면\s*동의\s*조건"),
    ),
    Protection(
        "assignment_consent",
        "양도금지 — 상호 사전 서면동의",
        (_rx(r"양도"), _rx(r"사전\s*서면\s*동의\s*없이")),
        "상대방의 사전 서면동의 없는 양도를 금지하는 상호 조항이다 — 응답기한·무응답 동의간주 같은 절차를 덧붙이지 않는다",
        _rx(r"양도[^.]{0,20}(?:동의|절차|응답|금지)|동의권자|응답\s*기한"),
    ),
)


@dataclass
class SatisfiedProtection:
    protection: Protection
    article: str
    display_path: str
    clause_paths: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.protection.key, "title": self.protection.title,
            "article": self.article, "display_path": self.display_path,
            "clause_paths": list(self.clause_paths), "keep_reason": self.protection.keep_reason,
        }


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def find_existing_protections(clauses: list[Any] | None) -> list[SatisfiedProtection]:
    by_article: dict[str, list[Any]] = {}
    for c in clauses or []:
        art = _attr(c, "article_number").strip()
        if art:
            by_article.setdefault(art, []).append(c)
    out: list[SatisfiedProtection] = []
    for p in PROTECTIONS:
        for art, cs in by_article.items():
            text = re.sub(r"\s*\n\s*", " ", " ".join(_attr(c, "title") + " " + _attr(c, "text") for c in cs))
            if all(rx.search(text) for rx in p.required):
                hit_paths = [
                    _attr(c, "display_path") for c in cs
                    if any(rx.search(re.sub(r"\s*\n\s*", " ", _attr(c, "text"))) for rx in p.required[1:])
                ] or [_attr(cs[0], "display_path")]
                out.append(SatisfiedProtection(p, art, hit_paths[0], hit_paths))
                break
    return out


def protection_covering(cr: dict[str, Any], satisfied: list[SatisfiedProtection]) -> SatisfiedProtection | None:
    """이 finding 이 이미 해결된 보호장치와 같은 쟁점인가.

    같은 조에 붙었거나, 조항 없이 "신설"로 나온 finding 이면 같은 쟁점으로 본다 — 다른 조에
    붙은 finding 은 그 조의 별개 쟁점일 수 있으므로 건드리지 않는다.
    """
    # ac_* 는 보호장치를 이미 고려해 만든 결정론 점검이다 — 다시 덮으면 C(정산 대행 책임)가
    # 해결하지 않은 결제창 Case A/B 쟁점까지 KEEP 이 된다(실측).
    if cr.get("is_entity_name_correction") or str(cr.get("clause_id") or "").startswith("ac_"):
        return None
    title = ""
    for d in cr.get("detected_issue_list") or []:
        if isinstance(d, dict) and d.get("issue_title"):
            title = str(d["issue_title"])
            break
    title = title or str(cr.get("issue_title") or cr.get("clause_title") or "")
    problem = str(cr.get("problem") or cr.get("rewrite_reason") or "")[:240]
    hay = " ".join([title, problem])
    art = str(cr.get("article_number") or "").strip()
    path = str(cr.get("display_path") or "")
    # "…책임 배분 없음" 같은 부재 주장은 계약 전체를 기준으로 판단한다 — 다른 조에 이미
    # 있으면 그 주장 자체가 틀렸다(실측: 제2조 제7항에 붙은 "소비자 책임 배분 없음").
    # "귀책 범위가 불명확" 도 책임 배분에 관한 계약 전체 판단이다 — 다른 조가 이미 나눴으면 틀린 주장.
    floating = not art or "신설" in path or bool(re.search(
        r"없음|부재|미규정|규정되(?:지|어\s*있지)\s*않|누락|정하지\s*않|정해져\s*있지\s*않"
        r"|귀책\s*범위가?\s*불명확|책임\s*(?:배분|소재|귀속)이?가?\s*불명확", title + " " + problem))
    for s in satisfied:
        if not s.protection.covers.search(hay):
            continue
        if floating or art == s.article:
            return s
    return None


__all__ = ["PROTECTIONS", "SatisfiedProtection", "find_existing_protections", "protection_covering"]
