"""복합계약의 구성 — primary_contract_type + secondary_contract_elements.

2026-09-30 지시 1항 — "단일 유형으로 억지 분류하지 마세요. 실제 계약 목적과
급부가 복합적이면 primary_contract_type 과 secondary_contract_elements 를 함께
저장." 예: 한글날 협업계약은 canonical 유형으로는 라이선스지만 실제로는 창작·
개발, 제작, IP 이용허락, 전시·홍보, 상업판매, 로열티, 지원사업 정산이 한 계약에
들어 있다.

canonical 유형(`canonical_state.contract_type`)을 **바꾸지 않는다** — 규칙·법률
적용은 그 값 하나로 돈다(v12·v17 원칙). 이 모듈은 사람이 읽는 성격 표기와
구성요소 목록만 만든다.
"""
from __future__ import annotations

import re
from typing import Any

#: (구성요소 라벨, 본문에서 그 급부를 **규정**하는 문형). 단어가 스치는 것으로는
#: 부족하다 — 두 번 이상 나와야 구성요소로 센다.
_ELEMENTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("창작·개발", re.compile(r"창작|디자인\s*개발|작품\s*개발|제품\s*개발|개발(?:·|\s*및\s*)?제작")),
    ("제작", re.compile(r"제작(?:한다|하여|하고|·|\s*및)|시제품|제작사양|생산")),
    ("IP 이용허락", re.compile(r"이용권|이용을\s*허락|이용\s*허락|실시권|라이선스|사용권")),
    ("전시·홍보", re.compile(r"전시|홍보|아카이브")),
    ("상업판매", re.compile(r"판매(?:한다|하는|·|\s*및|기간)|유통|소비자")),
    ("로열티", re.compile(r"로열티|로얄티|royalt", re.IGNORECASE)),
    ("지원사업 정산", re.compile(r"지원사업|보조금|지원금|사업비")),
    ("물품공급", re.compile(r"물품(?:을)?\s*공급|납품(?:한다|하여야)|인도(?:한다|하여야)")),
    ("용역수행", re.compile(r"용역(?:을)?\s*수행|업무(?:를)?\s*수행|과업")),
    ("공사", re.compile(r"공사|시공")),
    # 비밀유지는 넣지 않는다 — 거의 모든 계약의 부수 조항이라 거래 성격을 말하지 않는다.
)
_MIN_HITS = 2
#: 이 이상이면 복합계약으로 본다.
_COMPOSITE_MIN_ELEMENTS = 3

_RX_TITLE = re.compile(r"^\s*([^\n]{2,60}?계약서?)\s*$", re.MULTILINE)
_RX_PUBLIC_PROGRAM = re.compile(r"지원사업|보조사업|국고보조|공모사업|주최하고|주관하는")


def _title(text: str) -> str:
    head = text[:1500]
    m = _RX_TITLE.search(head)
    if not m:
        return ""
    t = re.sub(r"\s*계약서$", "계약", m.group(1).strip())
    t = re.sub(r"\s+계약$", "계약", t)
    return t


def build_contract_composition(
    text: str,
    *,
    canonical_label: str = "",
    party_count: int = 0,
) -> dict[str, Any]:
    body = str(text or "")
    elements = [label for label, rx in _ELEMENTS if len(rx.findall(body)) >= _MIN_HITS]
    composite = len(elements) >= _COMPOSITE_MIN_ELEMENTS
    primary = canonical_label
    if composite:
        base = _title(body) or canonical_label
        prefix = []
        if _RX_PUBLIC_PROGRAM.search(body[:2500]) and "지원사업" not in base:
            prefix.append("공적 지원사업 기반")
        if party_count >= 3 and not re.search(r"3자|삼자", base):
            prefix.append(f"{party_count}자")
        primary = " ".join(prefix + [base]).strip()
    return {
        "primary_contract_type": primary,
        "secondary_contract_elements": elements if composite else [],
        "is_composite": composite,
        "canonical_label": canonical_label,
    }


__all__ = ["build_contract_composition"]
