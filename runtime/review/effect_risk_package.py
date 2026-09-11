"""거래위험을 **사슬**로 연결해 판단한다 — 조항별 나열이 아니라 package 단위.

2026-09-10 지시 항목 1 — "선이행 구조는 반드시 package 로 검토. 선제공 →
소유권 이전 → 상대방 미이행 → 반환/환수 → 손해배상까지 연결해서 판단.
이번 건에서 선이행을 `적정`으로 처리한 것은 오류."

무엇이 문제였나
─────────────
`risk_package.py` 의 패키지들은 계약유형을 전제로 미리 써둔 목록이라, 실측한
대물교환 계약에서 `risk_packages: []` 가 나왔다. 선이행 구조가 아예 검토되지
않았고, 그래서 "우리가 가구를 **먼저 전부** 넘기고 상대방의 콘텐츠 납품은
그 뒤에 이루어진다" 는 이 거래의 핵심 위험이 판단에서 빠졌다.

이 모듈이 하는 일
──────────────
사슬을 **법률효과**로 정의한다(`clause_effect`). 계약유형을 인자로 받지
않으므로 어느 유형에서도 같은 사슬이 성립한다 — 물품을 먼저 주든 대금을
먼저 주든 라이선스를 먼저 허락하든, "선이행한 쪽이 회수 수단을 갖고 있는가"
라는 질문은 동일하다.

각 사슬은 두 종류의 고리로 이루어진다.

    trigger  이 사슬이 이 계약에 **존재하는가**
    link     그 위험을 실제로 막아주는 **방어 고리**

trigger 가 모이고 방어 고리가 비어 있으면 그 사슬을 하나의 finding 으로
올린다. 조항 하나하나는 정상으로 보여도 사슬이 끊겨 있으면 회수가 안 되기
때문이다 — 그것이 조항별 검토가 놓치는 지점이다.

**부재 판정은 계약 전체를 본 뒤에만 한다**(지시 항목 3). 다른 조항·별첨에
방어 고리가 있으면 그 고리는 present 로 세고, 사슬이 온전하면 finding 을
만들지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass(frozen=True)
class Link:
    key: str
    label: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class RiskChain:
    key: str
    label: str
    #: 이 사슬이 계약에 존재한다는 신호. `min_triggers` 개 이상 모여야 성립.
    triggers: tuple[Link, ...]
    min_triggers: int
    #: 위험을 실제로 막아주는 방어 고리.
    links: tuple[Link, ...]
    #: 방어 고리가 이만큼 빠지면 finding 을 만든다.
    max_missing_allowed: int
    severity: str
    problem: str
    legal_reason: str
    recommendation: str
    practical_position: str


CHAINS: tuple[RiskChain, ...] = (
    # ── 선이행 회수 사슬 (지시 항목 1) ──────────────────────────────────────
    RiskChain(
        key="pre_performance_recovery",
        label="선이행 → 소유권 이전 → 상대방 미이행 → 반환·환수 → 손해배상",
        triggers=(
            Link("we_deliver_first", "우리가 먼저 급부를 제공",
                 _rx(r"제공(?:한다|하며|하고)|인도(?:한다|하며)|설치(?:를)?\s*완료|공급(?:한다|하며)"
                     r"|선(?:지급|급금|이행|제공)|먼저\s*(?:제공|인도|지급)")),
            Link("ownership_moves", "소유권·위험이 상대방에게 이전",
                 _rx(r"소유권(?:은|이)?[^.\n]{0,40}(?:이전|귀속)|위험(?:은|이)?[^.\n]{0,30}이전"
                     r"|title\s+(?:shall\s+)?pass")),
            Link("their_performance_later", "상대방 이행은 그 이후에 이루어짐",
                 _rx(r"이후|완료된?\s*(?:날|때|후)|검수(?:가)?\s*완료|납품\s*기한|게시(?:한|하며)"
                     r"|업무수행(?:이)?\s*완료|기한\s*내")),
        ),
        min_triggers=3,
        links=(
            Link("return_claim", "원상 반환·환수 청구권",
                 _rx(r"반환(?:을)?\s*(?:청구|요구)|원상\s*(?:반환|회복)|회수(?:할|한다|를)")),
            Link("money_substitute", "반환 불가 시 금전 대체 청구권",
                 _rx(r"상당(?:하는|액)[^.\n]{0,20}금전|감가\s*상당|금전(?:으로)?\s*(?:지급|배상)"
                     r"|상당액(?:을)?\s*지급")),
            Link("damages", "손해배상 청구권 병존",
                 _rx(r"손해(?:를)?\s*배상|손해배상(?:을)?\s*청구|배상(?:하여야|한다)")),
            Link("security", "담보·보증·단계적 이행으로 회수 가능성 확보",
                 # "담보제공" 은 처분행위 금지 열거("매도, 양도, 담보제공, 임대")
                 # 안에도 나온다 — 그것은 상대방의 처분을 막는 문언이지 우리
                 # 회수를 담보하는 장치가 아니다. 그 열거는 아래
                 # `_strip_disposal_prohibitions()` 가 미리 지운다.
                 _rx(r"보증(?:보험|증권|금)|이행보증|보증서(?:를)?\s*제출|질권|근저당"
                     r"|담보(?:를)?\s*(?:제공하여야|제공한다|설정)"
                     r"|분할(?:하여)?\s*(?:제공|인도|지급)|단계적(?:으로)?\s*(?:제공|인도)"
                     r"|검수\s*완료\s*후(?:에)?\s*(?:제공|인도|지급)|에스크로")),
        ),
        max_missing_allowed=0,
        severity="HIGH",
        problem=(
            "우리가 급부를 먼저 전부 제공하고 소유권까지 이전한 뒤에 상대방의 이행이 "
            "이루어지는 선이행 구조입니다. 반환·금전 청구권은 규정되어 있으나, 그 청구권이 "
            "실제로 회수로 이어지게 하는 담보·보증 또는 단계적 이행 장치가 없습니다."
        ),
        legal_reason=(
            "선이행 후에는 우리가 이미 이행을 마친 상태이므로 동시이행의 항변권을 잃고, "
            "상대방이 이행하지 않으면 청구권만 남습니다. 상대방의 신용에 문제가 생기면 "
            "반환청구권과 손해배상청구권은 모두 일반채권에 불과해 실제 회수가 어렵습니다. "
            "조항 하나하나는 정상으로 보여도 사슬 끝의 회수 수단이 비어 있으면 노출은 급부의 "
            "전액입니다."
        ),
        # [2026-09-11 지시] "선이행 리스크는 반환청구 문구 강화보다 분할이행·
        # 소유권 이전시점·담보 구조를 우선 제안." 반환청구권은 이미 있어도
        # 상대방 신용이 무너지면 일반채권에 불과하다 — 문구를 다듬는 것으로는
        # 회수 가능성이 달라지지 않는다. 구조를 바꾸는 세 가지를 순서대로 둔다.
        recommendation=(
            "① 급부를 상대방의 이행 진척에 연동해 분할 제공한다(예: 착수 시 일부, "
            "검수 완료 시 잔여). ② 소유권과 위험의 이전 시점을 상대방의 이행 완료 "
            "시점으로 늦추고, 그때까지는 담보 목적의 소유권 유보를 명시한다. "
            "③ 위 둘이 어려우면 선이행 상당액에 대한 이행보증증권 또는 담보를 "
            "제공받는다. 반환·손해배상 청구권 문구의 보완은 이 세 가지를 갖춘 뒤의 "
            "보조 수단으로 둔다."
        ),
        practical_position=(
            "세 가지 중 분할이행이 상대방 부담이 가장 적어 먼저 제안하기 좋습니다. "
            "상대방이 분할을 거부하면 그것이 곧 신용 위험 신호이므로, 그때 소유권 "
            "유보나 보증증권을 요구하는 순서가 협상에서 설득력이 있습니다."
        ),
    ),
    # ── 저작권 chain of title ──────────────────────────────────────────────
    RiskChain(
        key="ip_chain_of_title",
        label="창작자 → 권리 귀속·양도 → 2차적저작물작성권 → 매체·기간·지역 → 제3자 소재 → 저작인격권",
        triggers=(
            Link("ip_transfer", "지식재산의 귀속·양도·이용허락",
                 _rx(r"저작권|저작재산권|지식재산|실시권|이용(?:을)?\s*허락|copyright")),
            Link("we_use_it", "우리가 그 결과물을 활용",
                 _rx(r"이용할\s*수\s*있|활용|사용할\s*수\s*있|광고|홍보|게시")),
        ),
        min_triggers=2,
        links=(
            Link("derivative_right", "2차적저작물작성권 포함 명시",
                 _rx(r"2차적저작물(?:작성권)?|derivative\s+works?")),
            Link("scope", "매체·기간·지역 범위 특정",
                 _rx(r"기간[^.\n]{0,10}지역|매체(?:를|의)?\s*(?:불문|제한\s*없)|territor")),
            Link("third_party_material", "제3자 소재의 라이선스 확보 의무",
                 _rx(r"제3자(?:의)?\s*(?:저작물|권리)|음원|서체|이미지|소품|라이선스(?:를)?\s*확보")),
            Link("moral_rights", "저작인격권 불행사 확약",
                 _rx(r"저작인격권|동일성유지권|성명표시권|moral\s+rights")),
        ),
        max_missing_allowed=1,
        severity="HIGH",
        problem=(
            "지식재산의 권리 사슬(창작자 → 양도 → 2차 가공 → 활용 범위 → 제3자 소재 → "
            "저작인격권)에 끊긴 고리가 있습니다."
        ),
        legal_reason=(
            "저작권법 제45조 제2항은 특약이 없으면 2차적저작물작성권이 양도에 포함되지 않는 "
            "것으로 추정합니다. 또한 결과물에 포함된 제3자 소재의 라이선스 범위가 우리의 "
            "이용 범위보다 좁으면, 권리를 양도받았더라도 그 범위에서는 이용할 수 없습니다. "
            "사슬의 한 고리만 비어도 취득했다고 믿은 권리를 실제로는 행사할 수 없습니다."
        ),
        recommendation=(
            "끊긴 고리를 해당 조항에 명시한다 — 2차적저작물작성권 포함, 매체·기간·지역 무제한, "
            "제3자 소재에 대해 우리의 이용 범위와 동일한 라이선스 확보 의무, 저작인격권 불행사 확약."
        ),
        practical_position=(
            "저작권법상 추정 규정을 근거로 제시하면 상대방도 거부 명분이 약합니다. "
            "제3자 소재 라이선스는 상대방의 확보 의무로 두는 것이 실무 관행입니다."
        ),
    ),
    # ── 변경 → 비용 → 기간 사슬 ────────────────────────────────────────────
    RiskChain(
        key="change_cost_schedule",
        label="변경·추가 → 대가 조정 → 기간 연장 → 지체책임 면제",
        triggers=(
            Link("change_expected", "업무 변경·추가가 예정",
                 _rx(r"설계\s*변경|추가\s*(?:공사|과업|업무)|변경(?:을)?\s*(?:요청|지시)|과업\s*변경")),
            Link("has_deadline", "납기·공기가 정해져 있음",
                 _rx(r"납기|기한|공기|준공|완료(?:일|기한)")),
        ),
        min_triggers=2,
        links=(
            Link("price_adjust", "변경에 따른 대가 조정",
                 _rx(r"변경[^.\n]{0,40}(?:대가|비용|금액)[^.\n]{0,20}(?:조정|합의|정한다)"
                     r"|추가[^.\n]{0,20}(?:대가|비용)[^.\n]{0,20}(?:청구|지급|협의)")),
            Link("time_extend", "변경에 따른 기간 연장",
                 _rx(r"기간(?:을)?\s*연장|공기(?:를)?\s*연장|납기(?:를)?\s*(?:연장|조정)")),
            Link("delay_relief", "변경 기인 지체에 대한 책임 면제",
                 _rx(r"지체(?:의)?\s*책임(?:을)?\s*(?:지지\s*아니|면)|귀책(?:이)?\s*아닌"
                     r"|지체상금[^.\n]{0,30}제외")),
        ),
        max_missing_allowed=1,
        severity="MEDIUM",
        problem="업무 변경·추가가 예정되어 있으나 그에 따른 대가·기간·지체책임의 조정 사슬이 끊겨 있습니다.",
        legal_reason=(
            "조정 절차가 없으면 추가 업무를 수행하고도 대가를 청구할 근거가 없고, 동시에 "
            "원래 납기 기준의 지체책임만 남습니다. 변경을 지시한 쪽이 이익을 얻고 수행한 쪽이 "
            "비용과 지체책임을 모두 부담하는 구조가 됩니다."
        ),
        recommendation="변경 시 대가·기간을 서면으로 조정하고, 변경에 기인한 지체는 책임에서 제외한다는 문구를 넣는다.",
        practical_position="양측 모두를 보호하는 조항이므로 수용 가능성이 높습니다.",
    ),
    # ── 비밀정보 ↔ IP 경계 사슬 ────────────────────────────────────────────
    RiskChain(
        key="confidential_ip_boundary",
        label="기보유 IP → 비밀정보 → 독자 개발 → 결과물 IP",
        triggers=(
            Link("confidential", "비밀유지의무",
                 _rx(r"비밀유지|비밀정보|기밀|confidential")),
            Link("ip_or_result", "결과물·지식재산이 함께 다뤄짐",
                 _rx(r"지식재산|저작권|개발\s*결과|성과물|산출물|improvement|발명")),
        ),
        min_triggers=2,
        links=(
            Link("background_ip", "기보유 지식재산·정보의 유보",
                 # NDA 는 이 경계를 "비밀정보의 예외" 로 규정한다 — "제공받기
                 # 이전부터 이미 알고 있었거나 보유하고 있던 정보". 그 문형을
                 # 놓치면 이미 있는 보호조항을 누락으로 오판한다(항목 3).
                 _rx(r"기(?:존|보유)[^.\n]{0,20}(?:권리|지식재산|자료)"
                     r"|이미\s*(?:알고|보유)(?:하고)?\s*있[었던]"
                     r"|제공받기?\s*(?:이)?전부터"
                     r"|종전부터\s*보유|background")),
            Link("independent_dev", "독자 개발의 예외",
                 _rx(r"독자적으로\s*개발|이용하지\s*않고\s*개발|independently\s+developed|자체\s*개발")),
            Link("result_ip", "이 계약으로 만들어지는 지식재산의 귀속 특정",
                 _rx(r"(?:결과물|성과물|창작물|콘텐츠)[^.\n]{0,30}귀속|foreground"
                     r"|저작권[^.\n]{0,30}귀속|지식재산[^.\n]{0,30}귀속")),
        ),
        max_missing_allowed=1,
        severity="MEDIUM",
        problem=(
            "비밀유지와 지식재산이 함께 규정되어 있으나 기보유 권리·독자 개발·신규 지식재산 "
            "귀속의 경계에 끊긴 고리가 있습니다."
        ),
        legal_reason=(
            "경계가 없으면 우리가 이전부터 보유했거나 독자적으로 만들어낸 것까지 상대방의 "
            "비밀정보에서 파생된 것으로 주장될 수 있고, 그 범위에서 우리 자체 사업 활동이 "
            "의무 위반으로 다투어집니다."
        ),
        recommendation="기보유 지식재산의 유보와 독자 개발의 예외를 비밀정보의 예외로 명시한다.",
        practical_position="국제 표준 문언에 해당해 거의 항상 수용됩니다.",
    ),
)


#: 처분행위 금지 열거. 여기 등장하는 "담보제공"·"판매"는 거래구조 신호가
#: 아니라 상대방을 제한하는 문언이다(2026-09-10 실측: 대물교환 계약 제6조
#: 제3항 "제3자에게 매도, 양도, 담보제공, 임대 또는 폐기할 수 없다" 가
#: 선이행 담보 고리로 오탐돼, 사슬이 온전한 것으로 판정됐다).
_RX_DISPOSAL_PROHIBITION = re.compile(
    r"(?:매도|판매|양도|대여|임대|담보제공|처분|폐기)"
    r"(?:\s*[,·]\s*(?:매도|판매|양도|대여|임대|담보제공|처분|폐기)){1,}",
)


def _strip_disposal_prohibitions(text: str) -> str:
    return _RX_DISPOSAL_PROHIBITION.sub(" ", text or "")


def _present(links: tuple[Link, ...], text: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    present: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for link in links:
        target = present if link.pattern.search(text) else missing
        target.append({"key": link.key, "label": link.label})
    return present, missing


def build_effect_risk_packages(*, text: str) -> list[dict[str, Any]]:
    """계약 전체를 보고 사슬별 상태를 판정한다.

    계약유형을 인자로 받지 않는다 — 사슬은 법률효과로 정의되므로 유형과
    무관하게 성립해야 한다.
    """
    body = _strip_disposal_prohibitions(str(text or ""))
    out: list[dict[str, Any]] = []
    for chain in CHAINS:
        triggers_present, _ = _present(chain.triggers, body)
        if len(triggers_present) < chain.min_triggers:
            continue
        links_present, links_missing = _present(chain.links, body)
        broken = len(links_missing) > chain.max_missing_allowed
        out.append({
            "key": chain.key,
            "label": chain.label,
            "severity": chain.severity,
            "triggers_present": triggers_present,
            "links_present": links_present,
            "links_missing": links_missing,
            "chain_broken": broken,
            "problem": chain.problem,
            "legal_reason": chain.legal_reason,
            "recommendation": chain.recommendation,
            "practical_position": chain.practical_position,
        })
    return out


#: 사슬별 앵커 조항을 찾을 때 쓰는 패턴. 그 사슬의 위험이 실제로 발생하는
#: 조항에 finding 을 붙이기 위한 것이다.
_ANCHOR_PATTERNS: dict[str, re.Pattern[str]] = {
    "pre_performance_recovery": _rx(
        r"소유권(?:은|이)?[^.\n]{0,40}(?:이전|귀속)|위험(?:은|이)?[^.\n]{0,30}이전"
        r"|반환(?:을)?\s*(?:청구|요구)|원상\s*(?:반환|회복)"
    ),
    "ip_chain_of_title": _rx(r"저작권|지식재산|실시권|이용(?:을)?\s*허락"),
    "change_cost_schedule": _rx(r"설계\s*변경|추가\s*(?:공사|과업|업무)|과업\s*변경"),
    "confidential_ip_boundary": _rx(r"비밀유지|비밀정보|기밀"),
}


def _anchor_clause(chain_key: str, clauses: list[Any] | None) -> Any | None:
    """이 사슬의 위험이 실제로 발생하는 조항을 찾는다."""
    pattern = _ANCHOR_PATTERNS.get(chain_key)
    if pattern is None or not clauses:
        return None
    best = None
    best_len = 0
    for c in clauses:
        body = c.get("text") if isinstance(c, dict) else getattr(c, "text", "")
        body = str(body or "")
        if not body.strip() or not pattern.search(body):
            continue
        # 같은 조건을 만족하는 조항이 여럿이면 더 구체적으로 규정한 쪽을 쓴다.
        if len(body) > best_len:
            best, best_len = c, len(body)
    return best


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def package_findings(
    packages: list[dict[str, Any]],
    *,
    clauses: list[Any] | None = None,
    last_article_number: int = 0,
    existing_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """끊긴 사슬을 finding 으로 만든다.

    가능하면 그 위험이 실제로 발생하는 **조항에 붙인다**. 신설 조항 권고로만
    내보내면 세 가지가 동시에 어긋난다(2026-09-10 실측):
      · 체크리스트 항목으로 분류돼 후단에서 LOW 로 강등되고,
      · UI 에는 "제14조 신설" 로 뜨는데 DOCX 에는 없어 두 화면이 갈리며,
      · "요청하지도 않은 새 의무를 제안한다" 는 골든 테스트에 걸린다.
    앵커 조항이 있으면 그 조항의 문제로 다루는 것이 실무적으로도 맞다 —
    선이행 위험은 소유권 이전 조항의 문제이지 없는 조항의 문제가 아니다.

    이미 같은 사슬을 다루는 finding 이 있으면 만들지 않는다.
    """
    covered = {
        str(cr.get("risk_chain_key") or "")
        for cr in (existing_results or [])
        if isinstance(cr, dict)
    }
    out: list[dict[str, Any]] = []
    for pkg in packages:
        if not pkg.get("chain_broken"):
            continue
        key = str(pkg.get("key") or "")
        if key in covered:
            continue
        missing_labels = ", ".join(m["label"] for m in (pkg.get("links_missing") or []))
        present_labels = ", ".join(m["label"] for m in (pkg.get("links_present") or []))
        problem = str(pkg.get("problem") or "")
        detail = (
            f"{problem} 확인된 방어 고리: {present_labels or '없음'}. "
            f"끊긴 고리: {missing_labels}."
        )
        severity = str(pkg.get("severity") or "MEDIUM")
        recommendation = str(pkg.get("recommendation") or "")

        anchor = _anchor_clause(key, clauses)
        if anchor is not None:
            original = _attr(anchor, "text")
            display_path = _attr(anchor, "display_path")
            cr: dict[str, Any] = {
                "clause_id": f"pkg_{key}__{_attr(anchor, 'clause_id')}",
                "clause_title": _attr(anchor, "title") or _attr(anchor, "clause_title"),
                "display_path": display_path,
                "article_number": _attr(anchor, "article_number"),
                "paragraph_number": _attr(anchor, "paragraph_number"),
                "original_text": original,
                "is_checklist_item": False,
            }
        else:
            location = (
                f"제{last_article_number + 1}조 신설" if last_article_number > 0
                else "계약 말미에 신설"
            )
            cr = {
                "clause_id": f"pkg_{key}",
                "clause_title": str(pkg.get("label") or ""),
                "display_path": location,
                "original_text": "(해당 조항 없음 — 계약서에 신설 필요)",
                "is_checklist_item": True,
            }

        cr.update({
            "risk_tier": severity,
            "severity": severity,
            "problem": detail,
            "rewrite_reason": detail,
            "legal_business_reason": str(pkg.get("legal_reason") or ""),
            "suggested_rewrite": recommendation,
            "recommendation_text": recommendation,
            "negotiation_position": str(pkg.get("practical_position") or ""),
            "negotiation_strategy": str(pkg.get("practical_position") or ""),
            "confidence": 0.85,
            "is_risk_package": True,
            # 후단 강등 루프가 "rewrite 가 없으면 가치가 낮다"는 전제로 이
            # finding 을 LOW 까지 내린다. 계약 전체를 보고 끊긴 고리를 확인한
            # 결과이므로 출력 직전에 등급을 복원한다.
            "counsel_severity": severity,
            "risk_chain_key": key,
            "risk_chain_links_missing": [m["key"] for m in (pkg.get("links_missing") or [])],
            "high_severity_basis": (
                f"risk_chain[{key}]: {detail}"[:400] if severity == "HIGH" else ""
            ),
            "detected_issue_list": [{"issue_title": f"[리스크 사슬] {pkg.get('label')}"[:120]}],
        })

        # 완성 문구를 반드시 붙인다(지시 항목 6) — 앵커 조항이 있으면 원문의
        # 법률효과를 유지한 최소수정안으로, 없으면 신설 조문 권고로 만든다.
        _attach_chain_edit(cr, recommendation=recommendation)
        out.append(cr)
    return out


def _attach_chain_edit(cr: dict[str, Any], *, recommendation: str) -> None:
    from runtime.review.redline_instruction import build_redline_instruction

    original = str(cr.get("original_text") or "").strip()
    display_path = str(cr.get("display_path") or "").strip()
    is_new = bool(cr.get("is_checklist_item")) or original.startswith("(해당 조항 없음")

    if is_new:
        final_text = recommendation
        edit_type = "new_clause"
        location = display_path or "계약 말미에 신설"
        target = ""
    else:
        # 원문을 유지하고 끊긴 고리만 덧붙인다.
        final_text = f"{original.rstrip()} {recommendation}".strip()
        edit_type = "replace"
        location = f"{display_path} 교체" if display_path else "해당 조항 교체"
        target = original

    cr["suggested_rewrite"] = final_text
    cr["recommendation_text"] = final_text
    cr["proposed_revision"] = final_text
    cr["has_rewrite_change"] = True
    cr["redline_instruction"] = build_redline_instruction(
        finding_id=str(cr.get("finding_id") or ""),
        clause_id=str(cr.get("clause_id") or ""),
        severity=str(cr.get("risk_tier") or ""),
        edit_location=location,
        edit_type=edit_type,
        target_text=target,
        replacement_text=final_text,
        original_text=target,
        reason=str(cr.get("rewrite_reason") or ""),
    )
