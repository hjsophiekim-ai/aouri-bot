"""광고매체 집행형 계약의 고유 리스크 검토 — 시니어 사내변호사 관점.

2026-09-15 지시 —
  "이 계약을 단순 광고계약으로 보지 말고, 「광고매체 집행형」이라는 거래모델을
   먼저 확정한 뒤 **실제 광고가 제대로 송출되는지, 미송출 시 돈을 돌려받을 수
   있는지, 상대방 책임이 어디까지인지** 중심으로 검토할 것."

이 체크리스트가 다루는 9개 축(지시가 열거한 그대로)
────────────────────────────────────────────────
  1. 광고기간·매체 위치·수량·노출 기준·실적 증빙
  2. 미송출·부분송출·장애·시설철거 시 연장/대체송출/환불
  3. 중도해지 시 위약금·광고료·실비 중복 청구와 총액 cap
  4. 상대방의 일방적 송출 중단권
  5. 우리가 제공한 콘텐츠의 책임 ↔ 상대방의 임의 수정·송출 방식 책임의 구분
  6. 민원 시 귀책 무관 교체·제작비 부담
  7. 광고료 지급조건과 실제 송출 이행의 연동
  8. 상대방 귀책에 대한 환불·손해배상과 우리 쪽 무제한 면책
  9. 신용정보·개인정보 조항의 범위 과다

무엇을 **하지 않는가**
────────────────────
저작권 양도·2차적저작물작성권·저작인격권·창작자 chain of title 은 다루지
않는다. 상대방이 콘텐츠를 만들지 않으므로 성립하지 않는 논점이다. 그 비활성화는
`ad_transaction_model.deactivate_production_only_findings()` 가 담당하고, 이
모듈은 **대신 무엇을 볼 것인가**를 채운다.

설계 원칙
────────
· 계약유형 enum 이 아니라 **거래모델 판정**(`AdTransactionModel`)으로 켜진다.
  집행형이라고 확신할 때만 돈다.
· 조항번호를 지어내지 않는다. 실제 조 구조에서 위치를 찾고(`find_article_for_pattern`),
  못 찾으면 신설로 표시한다(v10 Hallucination Zero 원칙).
· 모든 HIGH/MEDIUM 에 **그대로 삽입 가능한 완성 조문**을 붙인다. "보완 필요",
  "추후 협의" 같은 설명형으로 끝내지 않는다.
· HIGH 는 실제 광고비 손실·미송출·무제한 책임·과도한 위약금·일방 중단권만.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from runtime.review.redline_instruction import (
    build_redline_instruction,
    find_article_for_pattern,
    location_insert_after_last_paragraph,
    paragraph_marker,
)


#: 조항을 찾지 못했을 때의 표기(v10 Hallucination Zero 규약).
ABSENT_MARKER = "해당 조항 없음 — 신설 필요"


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass
class AdMediaFinding:
    check_id: str
    severity: str            # HIGH / MEDIUM
    issue_title: str
    problem: str
    legal_business_reason: str
    clause_text: str         # 그대로 삽입 가능한 완성 조문
    negotiation_position: str
    anchor: re.Pattern[str] | None = None   # 이 조항 아래에 넣는다
    high_basis: str = ""
    tags: list[str] = field(default_factory=list)


# ── 조항 탐지 패턴 ──────────────────────────────────────────────────────────

# 앵커는 **그 체크가 지적하는 문언 자체**를 가리켜야 한다. "광고료" 같은 총칭
# 명사로 잡으면 계약서 앞쪽 표 조항에 전부 몰린다(실측: 중도해지·중단·지급
# 연동 세 건이 모두 제2조로 갔다).
_RX_ANCHOR_SCOPE = _rx(r"계약의?\s*내용|매체\s*위치|상품구분|광고기간")
_RX_ANCHOR_NON_DELIVERY = _rx(r"미\s*방영|방영중지|시설물의?\s*철거|부득이한\s*사정")
_RX_ANCHOR_TERMINATION_COST = _rx(r"중도에\s*해지|표준가로\s*산정|청약의?\s*취소|계약금")
_RX_ANCHOR_SUSPENSION = _rx(r"연체할\s*경우|즉시\s*중단|해지할\s*수\s*있|영업정책")
_RX_ANCHOR_INDEMNITY = _rx(r"법적\s*책임|면책|지식재산권\s*등의?\s*침해|소추")
_RX_ANCHOR_COMPLAINT = _rx(r"민원")
_RX_ANCHOR_PAYMENT = _rx(r"세금계산서를?\s*발행|광고료를?\s*현금으로|납부조건")
_RX_ANCHOR_CREDIT = _rx(r"신용정보")
_RX_ANCHOR_MISC = _rx(r"기타|해석상|상관례")

#: 1. 급부 특정
_RX_EXPOSURE_STANDARD = _rx(r"송출\s*(?:횟수|시간|주기)|노출\s*(?:횟수|시간|빈도)|1회\s*[^.\n]{0,10}초")
_RX_PERFORMANCE_REPORT = _rx(r"송출\s*(?:실적|내역|리포트)|모니터링\s*(?:보고|자료)|증빙\s*(?:자료|제출)")
#: 2. 미송출 구제
_RX_REMEDY_EXTEND = _rx(r"연장하여\s*광고를?\s*(?:방영|표출|송출)|기간을?\s*연장")
_RX_REMEDY_REFUND = _rx(r"반환한다|환불|일할\s*계산")
_RX_PARTIAL_FAILURE = _rx(r"부분\s*(?:미)?송출|일부\s*미\s*(?:방영|송출)|장애")
#: 3. 중도해지 비용
_RX_DISCOUNT_CLAWBACK = _rx(r"표준가로\s*산정|할인\s*금액을\s*표준가|정상가로\s*재산정")
_RX_DEPOSIT_FORFEIT = _rx(r"계약금은?\s*반환하지\s*(?:않|아니)")
_RX_LIABILITY_CAP = _rx(r"(?:배상|위약금|청구)[^.\n]{0,20}(?:총액|한도|상한)|초과하지\s*(?:아니한다|않는다)")
#: 4. 일방 중단권
_RX_UNILATERAL_STOP = _rx(
    r"즉시\s*중단할\s*수\s*있|송출[^.\n]{0,20}중단할\s*수\s*있|해지할\s*수\s*있다"
)
_RX_CURE_PERIOD = _rx(r"(?:시정|보완)[^.\n]{0,20}(?:기간|최고|요구)|(?:\d+)일[^.\n]{0,10}(?:시정|유예)")
_RX_VAGUE_STOP_GROUND = _rx(r"업무에\s*방해|영업정책|미풍양속|부적절하다고\s*판단")
#: 5. 제공 콘텐츠 책임 ↔ 매체사 귀책
_RX_BROAD_INDEMNITY = _rx(r"모든\s*법적\s*책임|일체의\s*책임|자신의\s*책임과\s*비용[^.\n]{0,30}면책")
_RX_MEDIA_FAULT_CARVEOUT = _rx(r"(?:매체사|상대방|중앙|을)[^.\n]{0,30}(?:귀책|고의|과실)[^.\n]{0,30}제외")
#: 6. 민원 부담
_RX_COMPLAINT_BURDEN = _rx(r"민원이?\s*발생[^.\n]{0,40}(?:제작|교체|전달)")
#: 7. 지급-이행 연동
_RX_PREPAY = _rx(r"세금계산서를?\s*발행하여\s*청구|선지급|선납")
#: 9. 신용정보
_RX_CREDIT_INFO = _rx(r"신용정보|신용판단|신용정보집중기관")


# ── 완성 조문 ───────────────────────────────────────────────────────────────

_CLAUSE_SCOPE = (
    "광고기간, 매체의 종류·위치·수량, 1일 송출 횟수와 1회 노출 시간, 송출 시간대는 "
    "본 계약 별첨 「광고 집행 명세」에 구체적으로 특정하며, 별첨에 기재되지 아니한 "
    "사항은 본 계약의 급부 범위에 포함되지 아니한다. 매체사는 매월 종료일부터 7일 "
    "이내에 매체별 실제 송출 일자·횟수·시간이 기재된 송출 실적 자료를 광고주에게 "
    "제출한다. 실제 송출량이 별첨에 정한 기준의 90퍼센트에 미달하는 경우 광고주는 "
    "미달 비율에 해당하는 광고료의 반환 또는 그에 상응하는 기간의 연장을 선택하여 "
    "청구할 수 있다."
)

_CLAUSE_NON_DELIVERY = (
    "매체사의 귀책사유 또는 매체·시스템의 장애로 광고가 송출되지 아니하거나 "
    "별첨에 정한 기준에 미달하여 송출된 경우, 광고주는 ① 미송출 시간에 상응하는 "
    "광고기간의 연장, ② 동등한 사양의 다른 매체를 통한 대체 송출, ③ 미송출 "
    "비율에 해당하는 광고료의 반환 중 하나를 선택하여 청구할 수 있다. 매체사의 "
    "부득이한 사정(시설물 철거, 임대차 종료, 행정기관의 명령 등)으로 송출을 "
    "계속할 수 없게 된 경우에도 같다. 매체사는 송출이 중단된 사실을 안 날부터 "
    "2영업일 이내에 광고주에게 서면으로 통지한다."
)

_CLAUSE_TERMINATION_CAP = (
    "광고주가 계약기간 만료 전에 본 계약을 해지하는 경우 매체사가 청구할 수 있는 "
    "금액은 ① 해지일까지 실제 송출된 기간에 해당하는 광고료와 ② 할인이 적용된 "
    "계약의 경우 이미 송출된 기간에 대한 할인액의 차액에 한정하며, 그 합계는 "
    "잔여 계약기간 광고료 총액의 100분의 30을 초과하지 아니한다. 매체사는 위 "
    "금액 외에 위약금·실비·기타 명목으로 중복하여 청구할 수 없다. 광고주의 "
    "귀책사유 없이 해지되는 경우 매체사는 미송출 기간에 해당하는 기수령 광고료를 "
    "해지일부터 30일 이내에 반환한다."
)

_CLAUSE_SUSPENSION = (
    "매체사는 다음 각 호의 어느 하나에 해당하는 경우에만 광고 송출을 중단할 수 "
    "있다. 1. 법령 또는 심의기준 위반이 행정기관·심의기관에 의하여 확인된 경우 "
    "2. 광고주가 광고료를 지급기일부터 30일 이상 연체하고, 매체사가 14일의 기간을 "
    "정하여 서면으로 최고하였음에도 이를 이행하지 아니한 경우. 매체사는 중단 전에 "
    "그 사유와 근거를 서면으로 통지하여야 하며, 광고주는 통지를 받은 날부터 7일 "
    "이내에 이의를 제기하고 시정할 기회를 가진다. 제1호 외의 사유로 중단된 기간에 "
    "대하여 매체사는 광고료를 청구할 수 없고, 이미 수령한 광고료를 반환한다."
)

_CLAUSE_IP_CARVEOUT = (
    "광고주는 자신이 매체사에 제공한 광고 콘텐츠 그 자체의 내용이 법령을 위반하거나 "
    "제3자의 지식재산권·초상권을 침해함으로 인하여 매체사에게 손해가 발생한 경우 "
    "이를 배상한다. 다만 ① 매체사가 광고주의 사전 서면 동의 없이 콘텐츠를 수정·"
    "편집·분할·재가공한 경우, ② 매체사가 본 계약 및 별첨에 정한 송출 사양·위치·"
    "시간과 다르게 송출한 경우, ③ 매체사의 고의 또는 과실로 발생한 경우에는 "
    "광고주는 책임을 부담하지 아니하며, 매체사가 이를 부담한다. 광고주의 배상 "
    "책임 총액은 본 계약에 따라 지급된 광고료 총액을 한도로 한다."
)

_CLAUSE_COMPLAINT = (
    "광고 송출과 관련하여 민원이 발생한 경우 매체사는 그 내용과 근거를 광고주에게 "
    "서면으로 통지하고, 광고주와 협의하여 대응 방법을 정한다. 민원이 광고 콘텐츠 "
    "자체의 위법 또는 광고주의 귀책사유에 기인하지 아니한 경우 광고주는 콘텐츠 "
    "교체 의무를 부담하지 아니하며, 교체가 필요한 경우에도 그 제작비용은 매체사가 "
    "부담한다. 민원으로 광고가 중단된 기간은 광고기간에 산입하지 아니하고 그 기간 "
    "만큼 연장한다."
)

_CLAUSE_PAYMENT_LINK = (
    "광고료는 매월 실제 송출이 이루어진 기간에 대하여 후급으로 지급한다. 매체사는 "
    "매월 종료 후 송출 실적 자료를 첨부하여 세금계산서를 발행하고, 광고주는 "
    "실적 자료와 세금계산서를 수령한 날부터 30일 이내에 지급한다. 실제 송출량이 "
    "별첨 기준에 미달하는 경우 광고주는 미달 비율에 해당하는 금액을 공제하고 "
    "지급할 수 있다."
)

_CLAUSE_MEDIA_LIABILITY = (
    "매체사는 본 계약상 송출 의무를 이행하지 아니하거나 불완전하게 이행함으로써 "
    "광고주에게 발생한 손해를 배상한다. 매체사의 배상 책임에는 미송출 기간에 "
    "해당하는 광고료의 반환이 포함되며, 그 반환은 광고주의 다른 손해배상청구에 "
    "영향을 미치지 아니한다. 본 계약의 어느 조항도 매체사의 고의 또는 중대한 "
    "과실로 인한 책임을 면제하는 것으로 해석되지 아니한다."
)

_CLAUSE_CREDIT_INFO = (
    "매체사는 본 계약의 이행을 위하여 필요한 최소한의 범위에서만 광고주의 정보를 "
    "이용하며, 광고주의 신용정보를 신용정보집중기관 또는 제3자에게 제공하거나 "
    "본 계약의 이행 외의 목적으로 이용하지 아니한다. 법령에 따라 제공이 요구되는 "
    "경우 매체사는 그 법령의 명칭과 조항을 명시하여 사전에 광고주의 별도 서면 "
    "동의를 받아야 하며, 동의를 받지 아니한 제공으로 발생한 손해는 매체사가 부담한다."
)


CHECKS: tuple[AdMediaFinding, ...] = (
    AdMediaFinding(
        check_id="ADM-01",
        severity="HIGH",
        issue_title="광고 급부(기간·매체 위치·수량·노출 기준)가 특정되지 않아 미이행을 다툴 수 없음",
        problem=(
            "광고기간, 매체의 위치와 수량, 1일 송출 횟수·노출 시간 등 우리가 무엇을 "
            "받기로 했는지가 계약서에 확정되어 있지 않습니다. 송출 실적을 확인할 "
            "자료를 받기로 한 규정도 없습니다."
        ),
        legal_business_reason=(
            "집행형 광고계약의 급부는 '어디에, 몇 대에, 얼마나 자주, 얼마 동안' 이 "
            "전부입니다. 이것이 특정되지 않으면 광고가 절반만 나가도 채무불이행을 "
            "주장할 근거가 없고, 광고료 전액을 지급해야 합니다."
        ),
        clause_text=_CLAUSE_SCOPE,
        negotiation_position=(
            "매체사가 표준 제공하는 '광고 집행 명세'를 별첨으로 붙이자고 요구하면 "
            "대부분 수용됩니다. 실적 자료 제출은 매체사가 이미 내부적으로 만들고 "
            "있으므로 추가 비용 부담이 없다는 점을 근거로 삼으십시오."
        ),
        anchor=_RX_ANCHOR_SCOPE,
        high_basis="급부가 특정되지 않아 광고료 전액이 회수 불가능한 위험에 노출됨",
        tags=["급부특정", "실적증빙"],
    ),
    AdMediaFinding(
        check_id="ADM-02",
        severity="HIGH",
        issue_title="미송출·부분송출·장애 시 구제수단이 기간 연장에 한정되어 환불 선택권이 없음",
        problem=(
            "매체사 과실로 광고가 나가지 않으면 그 시간만큼 연장하도록만 규정되어 "
            "있고, 광고주가 환불이나 대체 송출을 선택할 수 없습니다. 부분 송출이나 "
            "시스템 장애에 대한 기준도 없습니다."
        ),
        legal_business_reason=(
            "광고는 시점이 가치인 급부입니다. 시즌 프로모션이 끝난 뒤의 기간 연장은 "
            "대가로서 의미가 없는데, 연장만 규정되어 있으면 그 무의미한 구제를 "
            "강제로 받게 됩니다."
        ),
        clause_text=_CLAUSE_NON_DELIVERY,
        negotiation_position=(
            "연장 자체를 없애라는 요구가 아니라 '선택권' 을 달라는 요구이므로 "
            "매체사 부담이 크지 않습니다. 부득이한 사정에 이미 일할 반환 규정이 "
            "있다면 그 기준을 과실 미송출에도 적용하자고 하면 논리가 깔끔합니다."
        ),
        anchor=_RX_ANCHOR_NON_DELIVERY,
        high_basis="광고비를 지급하고도 광고가 나가지 않는 상황에서 실질 구제수단이 없음",
        tags=["미송출", "환불"],
    ),
    AdMediaFinding(
        check_id="ADM-03",
        severity="HIGH",
        issue_title="중도해지 시 할인액 소급 청구·계약금 몰취가 중복되고 총액 상한이 없음",
        problem=(
            "중도해지 시 이미 받은 할인을 표준가로 재산정해 차액을 청구하거나 "
            "계약금을 반환하지 않도록 되어 있습니다. 이 금액들의 합계에 상한이 "
            "없고, 실제 발생한 손해와 무관하게 청구됩니다."
        ),
        legal_business_reason=(
            "명칭이 '차액 정산' 이어도 계약 위반을 이유로 지급하는 금전이면 "
            "위약금으로 추정됩니다(민법 제398조 제4항). 상한이 없으면 남은 기간이 "
            "길수록 해지 자체가 불가능해지고, 매체 효과가 없어도 계약에 묶입니다."
        ),
        clause_text=_CLAUSE_TERMINATION_CAP,
        negotiation_position=(
            "할인 차액 정산 자체를 없애기보다 '이미 송출된 기간분에 한정' 과 "
            "'총액 30퍼센트 상한' 두 가지를 요구하는 편이 수용 가능성이 높습니다."
        ),
        anchor=_RX_ANCHOR_TERMINATION_COST,
        high_basis="해지 시 실손해와 무관한 금액이 상한 없이 청구될 수 있음",
        tags=["위약금", "중도해지"],
    ),
    AdMediaFinding(
        check_id="ADM-04",
        severity="HIGH",
        issue_title="매체사가 연체·자의적 사유로 시정기회 없이 송출을 즉시 중단·해지할 수 있음",
        problem=(
            "광고료 연체 시 즉시 송출을 중단하고 계약을 해지할 수 있게 되어 있으며, "
            "시정 최고 절차가 없습니다. '매체사의 업무에 방해를 초래하는 광고' 나 "
            "'영업정책' 처럼 매체사가 스스로 판단하는 사유로도 송출을 막을 수 있습니다."
        ),
        legal_business_reason=(
            "단순 착오나 내부 결재 지연으로 며칠 연체된 경우에도 광고가 즉시 끊기고, "
            "그 기간 광고료는 돌려받지 못합니다. 판단 기준이 매체사에게만 있는 중단 "
            "사유는 사실상 무제한 중단권입니다."
        ),
        clause_text=_CLAUSE_SUSPENSION,
        negotiation_position=(
            "연체 자체를 다투지 말고 '30일 연체 + 14일 최고' 라는 절차를 넣자고 "
            "요구하십시오. 매체사도 즉시 중단은 분쟁 소지가 크다는 점을 압니다."
        ),
        anchor=_RX_ANCHOR_SUSPENSION,
        high_basis="일방적 중단권으로 광고비를 지급하고도 송출이 끊길 수 있음",
        tags=["일방중단", "해지"],
    ),
    AdMediaFinding(
        check_id="ADM-05",
        severity="HIGH",
        issue_title="제공 콘텐츠 책임이 무제한이고 매체사의 임의 수정·송출 방식 귀책이 구분되지 않음",
        problem=(
            "우리가 제공한 콘텐츠에 대해 '모든 법적 책임' 을 부담하고, 제3자 청구 시 "
            "변호사비용까지 포함해 매체사를 면책하도록 되어 있습니다. 매체사가 "
            "콘텐츠를 임의로 수정하거나 약정과 다르게 송출해 발생한 문제까지 "
            "우리가 부담하는지 구분되어 있지 않습니다."
        ),
        legal_business_reason=(
            "집행형 계약의 진짜 IP 논점은 '권리를 취득하는가' 가 아니라 '우리가 준 "
            "소재 때문에 생긴 문제를 어디까지 책임지는가' 입니다. 귀책 구분과 한도가 "
            "없으면 매체사의 편집 실수로 생긴 분쟁까지 우리 비용으로 방어하게 됩니다."
        ),
        clause_text=_CLAUSE_IP_CARVEOUT,
        negotiation_position=(
            "콘텐츠 자체의 적법성 책임은 인정하되 '매체사가 수정·변형하거나 약정과 "
            "다르게 송출한 경우' 를 제외하는 carve-out 을 요구하십시오. 거절할 "
            "명분이 약한 조항입니다."
        ),
        anchor=_RX_ANCHOR_INDEMNITY,
        high_basis="무제한·무한도 면책으로 매체사 귀책까지 우리가 부담할 수 있음",
        tags=["면책", "IP책임"],
    ),
    AdMediaFinding(
        check_id="ADM-06",
        severity="MEDIUM",
        issue_title="민원 발생 시 귀책과 무관하게 광고주가 교체·제작비를 부담",
        problem=(
            "민원이 발생하면 광고주가 즉시 새 시안을 제작해 전달하도록 되어 있고, "
            "민원의 정당성이나 귀책 여부를 따지는 절차가 없습니다. 교체로 중단된 "
            "기간을 보전받는 규정도 없습니다."
        ),
        legal_business_reason=(
            "민원은 내용과 무관하게 제기될 수 있습니다. 귀책을 따지지 않고 교체 "
            "의무를 지면 민원 한 건에 제작비와 잔여 광고기간을 동시에 잃습니다."
        ),
        clause_text=_CLAUSE_COMPLAINT,
        negotiation_position=(
            "민원 대응 협조는 수용하되 '콘텐츠 자체의 위법에 기인하지 않은 민원' 은 "
            "제외하고, 중단 기간만큼 연장을 요구하십시오."
        ),
        anchor=_RX_ANCHOR_COMPLAINT,
        tags=["민원", "비용부담"],
    ),
    AdMediaFinding(
        check_id="ADM-07",
        severity="MEDIUM",
        issue_title="광고료 지급이 실제 송출 이행과 연동되지 않음",
        problem=(
            "광고료를 청구서 발행 기준으로 지급하도록 되어 있고, 실제 송출 실적과 "
            "연동되지 않습니다. 송출이 미달해도 감액할 근거가 없습니다."
        ),
        legal_business_reason=(
            "선지급 구조에서는 이행이 불완전해도 이미 지급한 대금을 회수하려면 "
            "별도로 청구해야 합니다. 후급 또는 실적 연동으로 바꾸면 회수 부담이 "
            "매체사에게 넘어갑니다."
        ),
        clause_text=_CLAUSE_PAYMENT_LINK,
        negotiation_position=(
            "전면 후급이 어렵다면 '실적 자료 첨부' 와 '미달 시 공제' 두 가지만 "
            "받아도 실질 효과는 대부분 확보됩니다."
        ),
        anchor=_RX_ANCHOR_PAYMENT,
        tags=["지급조건"],
    ),
    AdMediaFinding(
        check_id="ADM-08",
        severity="HIGH",
        issue_title="매체사 귀책에 대한 손해배상 규정이 없어 책임이 일방적으로 비대칭",
        problem=(
            "광고주는 광고료 지급·면책·비용 부담 의무를 지는 반면, 매체사가 송출 "
            "의무를 이행하지 않았을 때의 손해배상 책임은 규정되어 있지 않습니다."
        ),
        legal_business_reason=(
            "연장이나 일할 반환만으로는 광고 시점을 놓쳐 발생한 손해가 회복되지 "
            "않습니다. 배상 규정이 없으면 매체사의 고의·중과실에도 광고료 반환 "
            "이상을 청구하기 어렵습니다."
        ),
        clause_text=_CLAUSE_MEDIA_LIABILITY,
        negotiation_position=(
            "상호 배상 조항으로 제안하면 대칭성 때문에 수용되기 쉽습니다. 최소한 "
            "'고의·중과실 면책 불가' 문구만이라도 확보하십시오."
        ),
        anchor=_RX_ANCHOR_MISC,
        high_basis="상대방 불이행에 대한 구제수단이 사실상 없는 비대칭 구조",
        tags=["손해배상", "비대칭"],
    ),
    AdMediaFinding(
        check_id="ADM-09",
        severity="MEDIUM",
        issue_title="신용정보 제3자 제공 동의 범위가 계약 이행에 필요한 범위를 넘고 근거 법령이 불명확",
        problem=(
            "매체사가 취득한 우리 회사의 신용정보를 신용정보집중기관에 제공하고 "
            "공공기관의 정책자료로 활용하는 데 동의하도록 되어 있습니다. 근거로 든 "
            "법령이 조 번호만 적혀 있어 어떤 법률인지 특정되지 않습니다."
        ),
        legal_business_reason=(
            "광고 송출 계약의 이행에 신용정보의 제3자 제공이 필요하지 않습니다. "
            "근거 법령이 특정되지 않은 포괄 동의는 동의의 유효성 자체가 다투어질 "
            "수 있고, 그 위험은 동의한 쪽이 아니라 제공한 쪽에 남습니다."
        ),
        clause_text=_CLAUSE_CREDIT_INFO,
        negotiation_position=(
            "매체사 표준양식에 관행적으로 들어간 문구일 가능성이 높아 삭제 요구가 "
            "받아들여지는 경우가 많습니다. 삭제가 어려우면 '법령의 명칭과 조항 명시 "
            "+ 별도 동의' 로 좁히십시오."
        ),
        anchor=_RX_ANCHOR_CREDIT,
        tags=["신용정보"],
    ),
)


# ── 실행 ────────────────────────────────────────────────────────────────────

def _raw_excerpt(text: str, anchor: re.Pattern[str] | None) -> str:
    """앵커가 걸린 자리의 **계약 원문 그대로**를 잘라 온다.

    조항 추출기가 돌려주는 텍스트는 줄바꿈·공백이 정규화돼 있어 원문과 글자
    단위로 일치하지 않는다. 그대로 인용으로 쓰면 가짜 인용 게이트가 90% 기준에
    걸려 항목을 걷어낸다(실측: ADM 9건 중 8건이 "가짜 인용" 으로 처리됐다).
    원문에서 직접 잘라야 인용이 인용으로 성립한다.
    """
    body = str(text or "")
    if anchor is None or not body:
        return ABSENT_MARKER
    m = anchor.search(body)
    if m is None:
        return ABSENT_MARKER
    start = body.rfind("\n", 0, m.start()) + 1
    end = body.find("\n", m.end())
    if end == -1:
        end = len(body)
    excerpt = body[start:end].strip()
    return excerpt[:400] if excerpt else ABSENT_MARKER


def _is_satisfied(check: AdMediaFinding, text: str) -> bool:
    """이미 충분히 규정되어 있으면 지적하지 않는다."""
    if check.check_id == "ADM-01":
        return bool(_RX_EXPOSURE_STANDARD.search(text) and _RX_PERFORMANCE_REPORT.search(text))
    if check.check_id == "ADM-02":
        return bool(
            _RX_REMEDY_REFUND.search(text)
            and _RX_PARTIAL_FAILURE.search(text)
            and _RX_REMEDY_EXTEND.search(text)
        )
    if check.check_id == "ADM-03":
        has_cost = bool(_RX_DISCOUNT_CLAWBACK.search(text) or _RX_DEPOSIT_FORFEIT.search(text))
        return (not has_cost) or bool(_RX_LIABILITY_CAP.search(text))
    if check.check_id == "ADM-04":
        has_stop = bool(_RX_UNILATERAL_STOP.search(text) or _RX_VAGUE_STOP_GROUND.search(text))
        return (not has_stop) or bool(_RX_CURE_PERIOD.search(text))
    if check.check_id == "ADM-05":
        has_broad = bool(_RX_BROAD_INDEMNITY.search(text))
        return (not has_broad) or bool(_RX_MEDIA_FAULT_CARVEOUT.search(text))
    if check.check_id == "ADM-06":
        return not _RX_COMPLAINT_BURDEN.search(text)
    if check.check_id == "ADM-07":
        return not _RX_PREPAY.search(text)
    if check.check_id == "ADM-08":
        return bool(
            re.search(r"(?:매체사|중앙|을)[^.\n]{0,40}손해를?\s*배상", text)
        )
    if check.check_id == "ADM-09":
        return not _RX_CREDIT_INFO.search(text)
    return False


def run_ad_media_placement_checklist(
    *,
    text: str,
    clauses: list[Any] | None,
    model: Any,
) -> list[dict[str, Any]]:
    """집행형 계약의 9개 축을 점검해 clause_result 형태로 돌려준다.

    거래모델을 **집행형으로 확신**했을 때만 돈다. 확신하지 못한 상태에서
    체크리스트를 주입하면 그것이 곧 유형 오분류 주입이다.
    """
    if model is None or not getattr(model, "is_media_placement", False):
        return []
    if not getattr(model, "confident", False):
        return []

    body = str(text or "")
    out: list[dict[str, Any]] = []
    for check in CHECKS:
        if _is_satisfied(check, body):
            continue

        loc = find_article_for_pattern(clauses, check.anchor) if check.anchor else None
        # 앵커 조항의 **실제 문언**을 인용으로 싣는다. 비워 두면
        # `output_filter.is_valid_issue()` 의 첫 관문(원문 비어 있음)에서
        # 항목이 통째로 탈락해 화면에 아무것도 뜨지 않는다(실측 9건 전부).
        quoted = _raw_excerpt(body, check.anchor)
        edit_location = location_insert_after_last_paragraph(loc)
        marker = paragraph_marker(
            (loc["max_paragraph_number"] + 1) if loc and loc["max_paragraph_number"] else 1
        )
        clause_text = f"{marker} {check.clause_text}"
        display_path = f"제{loc['article_number']}조" if loc else "신설 조항"

        redline = build_redline_instruction(
            clause_id=check.check_id,
            severity=check.severity,
            edit_location=edit_location,
            edit_type="insert_after" if loc else "new_clause",
            replacement_text=clause_text,
            reason=check.problem,
        )
        out.append({
            "clause_id": check.check_id,
            "article_number": (loc["article_number"] if loc else None),
            "display_path": display_path,
            "clause_title": check.issue_title[:60],
            "clause_topic": "other",
            "risk_tier": check.severity,
            "severity": check.severity,
            "high_risk": check.severity == "HIGH",
            "must_fix": check.severity == "HIGH",
            "approval_required": check.severity == "HIGH",
            "review_tier": "MUST" if check.severity == "HIGH" else "SUGGEST",
            "high_severity_basis": check.high_basis,
            "issue_title": check.issue_title,
            "original_text": quoted,
            "problem": check.problem,
            "legal_business_reason": check.legal_business_reason,
            "suggested_rewrite": clause_text,
            "rewrite_reason": check.problem,
            "negotiation_position": check.negotiation_position,
            "redline_instruction": redline,
            "confidence": 0.9,
            "is_mandatory": True,
            "is_ad_media_checklist": True,
            "ad_media_tags": list(check.tags),
        })
    return out
