"""건설공사(수급인) 핵심 Risk Package — 조항을 사슬로 연결해서 본다.

2026-09-21 지시 9항 —
  "건설공사 수급인인 경우 다음을 먼저 cross-clause 로 연결:
   [Payment] 준공검사→기성확정→지급조건→지급유보→상계/공제→잔금→하자/지체상금
             공제→유치권/채권보전
   [Scope & Change] 공사범위→완전시공 의무→설계불일치→도급인 지시→Change
             Order→추가공사비→단가조정
   [Schedule] 착수→공구인수→타공종 간섭→공기연장→notice bar→지체상금
   [Security] 이행보증→하자보증→유보금→유치권 포기→선행조건
   [Termination] 해지→대체시공→기성정산→자재/장비→보증청구→손해배상"

Payment 는 이미 `construction_payment_package` 가 하나의 HIGH 로 묶어
올린다. 이 모듈은 **나머지 네 묶음**을 같은 방식으로 평가하고, 그 결과를
기존 finding 에 연결한다.

새 finding 을 함부로 만들지 않는다
─────────────────────────────
각 축에는 이미 체크리스트 항목(CWC-01 설계변경, CWC-02 공기연장,
CWC-09 해지, CWC-10 보증)이 있다. 같은 이야기를 패키지 이름으로 한 번 더
올리면 v13 이 없앤 중복이 되살아난다. 그래서 기본은 **연결**이다 —
해당 축을 이미 다루는 finding 이 있으면 그 finding 에 사슬 정보를 붙이고,
아무도 다루지 않는 축에서만 하나의 finding 을 만든다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass(frozen=True)
class ChainLink:
    key: str
    label: str
    #: 이 고리가 계약에 존재한다는 신호(위험이 생길 자리).
    trigger: re.Pattern[str]
    #: 그 위험을 실제로 막아 주는 방어 장치.
    defense: re.Pattern[str]
    exposure: str


@dataclass(frozen=True)
class RiskPackage:
    key: str
    label: str
    #: 이 묶음을 이미 다루고 있는 finding 을 알아보는 주제.
    covered_by_topics: tuple[str, ...]
    links: tuple[ChainLink, ...]
    #: 주제 라벨만으로는 못 잡는 항목을 id 로 직접 지정한다. 체크리스트
    #: 항목은 한 축이 대금·공기·책임에 동시에 걸쳐 단일 주제 라벨과 어긋난다
    #: (실측: 보증·유보금 항목 CWC-10 의 clause_topic 은 "payment" 다).
    covered_by_ids: tuple[str, ...] = ()


SCOPE_AND_CHANGE = RiskPackage(
    key="scope_and_change",
    label="[Scope & Change] 공사범위→완전시공→설계불일치→지시→Change Order→추가공사비→단가조정",
    covered_by_topics=("scope", "sow_change", "change_order"),
    covered_by_ids=("CWC-01", "CWC-04"),
    links=(
        ChainLink(
            key="scope_definition",
            label="① 공사범위 확정",
            trigger=_rx(r"공사\s*범위|업무\s*범위|업무구분표|산출내역서"),
            defense=_rx(
                r"(?:공사|업무)\s*범위[^.\n]{0,60}(?:별첨|산출내역서|업무구분표|도서)[^.\n]{0,30}따른"
                r"|범위[^.\n]{0,40}제외[^.\n]{0,40}(?:각\s*호|다음)"
            ),
            exposure=(
                "공사범위의 경계 문서가 특정되지 않으면, 나중에 '완전시공 의무' 를 "
                "근거로 범위 밖 작업까지 무상으로 요구받습니다."
            ),
        ),
        ChainLink(
            key="complete_work_duty",
            label="② 완전시공 의무",
            trigger=_rx(
                r"완전한?\s*시공|기술적[^.\n]{0,20}상식|누락(?:이)?\s*되?었?더라도"
                r"|설계도서(?:상)?\s*누락"
            ),
            defense=_rx(
                r"누락[^.\n]{0,60}(?:계약금액|대가)[^.\n]{0,30}(?:조정|증액|반영)"
                r"|완전(?:한)?\s*시공[^.\n]{0,60}(?:범위\s*내|산출내역서)"
            ),
            exposure=(
                "'설계도서에 없어도 완전한 시공에 필요하면 수급인 부담' 조항은 범위 "
                "무한확장 장치입니다. 조정 근거가 함께 없으면 추가원가를 전부 떠안습니다."
            ),
        ),
        ChainLink(
            key="design_conflict",
            label="③ 설계 불일치·상충 처리",
            trigger=_rx(r"불명확|상충|일치하지\s*아니|우선(?:순위|한다)"),
            defense=_rx(
                r"(?:상충|불일치)[^.\n]{0,60}(?:우선순위|협의하여\s*결정|서면으로\s*확정)"
                r"|우선순위[^.\n]{0,40}(?:다음|아래)"
            ),
            exposure=(
                "도면·내역서·업무구분표가 어긋날 때의 우선순위가 없으면, 그 차이가 "
                "전부 수급인의 시공 책임으로 귀결됩니다."
            ),
        ),
        ChainLink(
            key="change_order_procedure",
            label="④ 변경 지시 → Change Order 절차",
            trigger=_rx(r"변경|change\s*order|추가\s*공사|지시"),
            defense=_rx(
                r"변경[^.\n]{0,60}서면[^.\n]{0,40}(?:합의|승인|통보)"
                r"|변경\s*요청서[^.\n]{0,40}(?:\d+\s*일)[^.\n]{0,20}(?:이내|내에)"
            ),
            exposure=(
                "구두 지시로 공사가 진행되고 서면 변경합의가 없으면, 준공 후 추가공사비 "
                "청구의 입증책임을 수급인이 전부 집니다."
            ),
        ),
        ChainLink(
            key="unit_price",
            label="⑤ 추가공사비·단가 조정 기준",
            trigger=_rx(r"단가|계약금액[^.\n]{0,20}조정|증감|정산"),
            defense=_rx(
                r"단가[^.\n]{0,60}(?:산출내역서|계약단가)[^.\n]{0,30}(?:우선|적용)"
                r"|단가[^.\n]{0,40}협의하여\s*(?:정한|결정)"
            ),
            exposure=(
                "단가 산정 기준이 없으면 증액은 협의 불성립으로 미뤄지고, 감액만 "
                "일방적으로 적용됩니다."
            ),
        ),
    ),
)

SCHEDULE = RiskPackage(
    key="schedule",
    label="[Schedule] 착수→공구인수→타공종 간섭→공기연장→notice bar→지체상금",
    covered_by_topics=("delay", "schedule"),
    covered_by_ids=("CWC-02", "CWC-05", "CWC-11"),
    links=(
        ChainLink(
            key="commencement",
            label="① 착수 시점",
            trigger=_rx(r"착수(?:일|\s*통지)|착공"),
            defense=_rx(
                r"착수(?:일)?[^.\n]{0,60}(?:\d+\s*일)[^.\n]{0,20}(?:전까지|이전에)[^.\n]{0,30}통지"
                r"|착수일[^.\n]{0,40}지연[^.\n]{0,40}(?:연장|조정)"
            ),
            exposure=(
                "착수일을 도급인이 일방적으로 정하는데 준공일은 고정돼 있으면, 통지가 "
                "늦어진 만큼 우리 공기만 줄어듭니다."
            ),
        ),
        ChainLink(
            key="site_handover",
            label="② 공구 인수",
            trigger=_rx(r"공구\s*인수|현장\s*인도|인수확인서"),
            defense=_rx(
                r"인수[^.\n]{0,60}(?:조건|상태)[^.\n]{0,40}(?:확인서|사진|기재)"
                r"|인수[^.\n]{0,40}지연[^.\n]{0,40}(?:연장|제외)"
            ),
            exposure=(
                "인수 조건과 지연 시 처리가 없으면, 선행 공종이 늦어도 그 지연이 우리 "
                "지체일수로 계산됩니다."
            ),
        ),
        ChainLink(
            key="interface",
            label="③ 타 공종 간섭",
            trigger=_rx(r"분리\s*발주|타\s*공종|병행|간섭|건축공사\s*수급인"),
            defense=_rx(
                r"(?:분리\s*발주|타\s*공종)[^.\n]{0,80}(?:귀책|책임)[^.\n]{0,40}"
                r"(?:제외|부담하지|그러하지\s*아니)"
                r"|훼손[^.\n]{0,40}복구[^.\n]{0,40}비용"
            ),
            exposure=(
                "같은 현장에서 여러 공종이 돌면 간섭은 반드시 생깁니다. 귀책 분리가 "
                "없으면 남의 지연이 우리 지체상금이 됩니다."
            ),
        ),
        ChainLink(
            key="extension",
            label="④ 공기연장 신청권",
            trigger=_rx(r"공사기간[^.\n]{0,10}연장|공기\s*연장|연장을\s*신청"),
            defense=_rx(
                r"연장[^.]{0,80}(?:\d+\s*일)[^.]{0,20}(?:이내|내에)[^.]{0,40}(?:통보|회신|승인)"
                r"|(?:\d+\s*일)[^.]{0,20}(?:이내|내에)[^.]{0,60}연장[^.]{0,40}(?:통보|회신|승인)"
                r"|회신(?:이)?\s*없(?:는|으면)[^.]{0,40}(?:승인|연장)(?:한|된)?\s*것으로"
            ),
            exposure=(
                "연장 신청에 대한 도급인의 회신 기한과 무응답 시 처리가 없으면, 신청권은 "
                "있으나 행사해도 결론이 나지 않습니다."
            ),
        ),
        ChainLink(
            key="notice_bar",
            label="⑤ notice bar(신청 기한 도과 시 실권)",
            trigger=_rx(r"(?:\d+\s*일)[^.\n]{0,30}(?:이내|내에)[^.\n]{0,40}(?:신청|통지)"),
            defense=_rx(
                r"기한[^.\n]{0,40}도과[^.\n]{0,40}(?:그러하지\s*아니|권리를\s*잃지)"
                r"|신청[^.\n]{0,40}(?:지연|늦어진)[^.\n]{0,40}(?:정당한\s*사유)"
            ),
            exposure=(
                "기한 내 신청하지 않으면 연장권을 잃는 구조에서, 정당한 사유에 대한 "
                "예외가 없으면 실무상 대부분의 연장권이 소멸합니다."
            ),
        ),
        ChainLink(
            key="delay_damages",
            label="⑥ 지체상금",
            trigger=_rx(r"지체상금|지연배상"),
            defense=_rx(r"지체상금[^.\n]{0,120}(?:총액|상한|한도)[^.\n]{0,60}초과하지"),
            exposure=(
                "위 고리들이 모두 끊긴 상태에서 지체상금에 상한까지 없으면, 남의 귀책으로 "
                "늦어진 공사에 무한 지체상금이 붙습니다."
            ),
        ),
    ),
)

SECURITY = RiskPackage(
    key="security",
    label="[Security] 이행보증→하자보증→유보금→유치권 포기→선행조건",
    covered_by_topics=("guarantee", "security"),
    covered_by_ids=("CWC-10", "CWC-LIEN-WAIVER"),
    links=(
        ChainLink(
            key="performance_bond",
            label="① 이행보증",
            trigger=_rx(r"계약이행보증|이행보증|이행\s*보증(?:보험|증권|금)"),
            defense=_rx(
                r"이행보증[^.\n]{0,60}(?:\d+\s*(?:%|퍼센트)|100\s*분의\s*\d+)"
                r"|보증[^.\n]{0,40}(?:반환|해지|소멸)[^.\n]{0,40}(?:준공|검사)"
            ),
            exposure="보증 비율과 반환 시점이 없으면 준공 후에도 보증이 묶여 있습니다.",
        ),
        ChainLink(
            key="defect_bond",
            label="② 하자보증",
            trigger=_rx(r"하자보수보증|하자\s*보증"),
            defense=_rx(
                r"하자[^.\n]{0,60}(?:기간|\d+\s*년)"
                r"|하자보수보증[^.\n]{0,40}(?:반환|소멸|종료)"
            ),
            exposure="하자담보 기간과 보증금 반환 시점이 없으면 보증이 무기한 존속합니다.",
        ),
        ChainLink(
            key="retention",
            label="③ 유보금",
            trigger=_rx(r"유보(?:금|액)|리테인|retention"),
            defense=_rx(r"유보(?:금|액)[^.\n]{0,60}(?:반환|지급)[^.\n]{0,40}(?:\d+\s*일|준공|검사)"),
            exposure="유보금의 반환 시점이 없으면 준공 후에도 돈이 남의 손에 있습니다.",
        ),
        ChainLink(
            key="lien_waiver",
            label="④ 유치권 포기",
            trigger=_rx(r"유치권|포기각서|불행사"),
            defense=_rx(
                r"유치권[^.\n]{0,120}(?:다만|단서|경우에는\s*그러하지\s*아니)"
                r"|미지급[^.\n]{0,60}유치권"
            ),
            exposure=(
                "미지급 carve-out 없는 무조건 포기는 대금 미회수 시 남는 마지막 수단을 "
                "먼저 버리는 것입니다."
            ),
        ),
        ChainLink(
            key="precondition",
            label="⑤ 지급의 선행조건화",
            trigger=_rx(r"선행\s*조건|모두\s*충족|제출한\s*(?:때|후)[^.\n]{0,20}지급"),
            defense=_rx(
                r"선행\s*조건[^.\n]{0,60}(?:한정|열거|다음\s*각\s*호)"
                r"|제출(?:을)?[^.\n]{0,40}(?:지급(?:의)?\s*조건으로\s*하지)"
            ),
            exposure=(
                "보증·포기각서 제출이 대금 지급의 선행조건이면, 서류 하나로 지급 전체가 "
                "멈춥니다."
            ),
        ),
    ),
)

TERMINATION = RiskPackage(
    key="termination",
    label="[Termination] 해지→대체시공→기성정산→자재·장비→보증청구→손해배상",
    covered_by_topics=("termination",),
    covered_by_ids=("CWC-09",),
    links=(
        ChainLink(
            key="termination_right",
            label="① 해지권",
            trigger=_rx(r"해지|해제"),
            defense=_rx(
                r"(?:수급인|을)(?:은|이)[^.\n]{0,60}해지할\s*수\s*있"
                r"|시정[^.\n]{0,40}(?:요구|최고)[^.\n]{0,40}해지"
            ),
            exposure=(
                "도급인에게만 해지권이 있고 우리에게 없으면, 대금을 못 받는 상태에서도 "
                "계약에서 빠져나올 수 없습니다."
            ),
        ),
        ChainLink(
            key="substitute_work",
            label="② 대체시공",
            trigger=_rx(r"대체\s*시공|제3자로\s*하여금|타인에게\s*시공"),
            defense=_rx(
                r"대체\s*시공[^.\n]{0,80}(?:비용|구상)[^.\n]{0,40}(?:합리적|실제|입증)"
            ),
            exposure=(
                "대체시공 비용을 도급인이 정하는 대로 청구할 수 있으면, 해지 자체가 "
                "손해 확정 장치가 됩니다."
            ),
        ),
        ChainLink(
            key="progress_settlement",
            label="③ 기성 정산",
            trigger=_rx(r"기성(?:고)?\s*정산|정산한다|정산에\s*관하여"),
            defense=_rx(
                r"기성(?:고)?[^.\n]{0,60}(?:확인|검사)[^.\n]{0,40}(?:후|한\s*다음)[^.\n]{0,30}지급"
                r"|정산[^.\n]{0,60}(?:\d+\s*일)[^.\n]{0,20}(?:이내|내에)"
            ),
            exposure=(
                "해지 시 기성 정산의 기준·기한이 없으면, 이미 투입한 공사원가의 회수가 "
                "협의에 맡겨집니다."
            ),
        ),
        ChainLink(
            key="materials",
            label="④ 자재·장비 처리",
            trigger=_rx(r"자재|장비|반출|잔존물"),
            defense=_rx(r"자재[^.\n]{0,60}(?:소유|정산|반출|대가)"),
            exposure="반입한 자재·장비의 소유와 정산이 없으면 현장에 두고 나와야 합니다.",
        ),
        ChainLink(
            key="bond_call",
            label="⑤ 보증청구·손해배상",
            trigger=_rx(r"보증(?:을|를)?\s*청구|손해배상"),
            defense=_rx(
                r"손해배상[^.\n]{0,60}(?:한도|상한|범위|직접\s*손해)"
                r"|보증\s*청구[^.\n]{0,60}(?:실제\s*손해|확정)"
            ),
            exposure=(
                "해지와 동시에 보증청구와 손해배상이 한도 없이 이어지면, 손실이 "
                "기성 미수금에 그치지 않습니다."
            ),
        ),
    ),
)

ALL_PACKAGES: tuple[RiskPackage, ...] = (SCOPE_AND_CHANGE, SCHEDULE, SECURITY, TERMINATION)


@dataclass
class PackageResult:
    key: str
    label: str
    links: list[dict[str, Any]] = field(default_factory=list)
    broken: list[dict[str, Any]] = field(default_factory=list)

    @property
    def chain_broken(self) -> bool:
        # 고리 하나가 비어 있는 것은 흔한 일이다. 둘 이상이 동시에 끊겨야
        # "사슬이 끊겼다" 고 말할 수 있다 — 하나만으로 올리면 개별 체크리스트
        # 항목과 같은 말을 패키지 이름으로 반복하게 된다.
        return len(self.broken) >= 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "links": list(self.links),
            "broken_links": list(self.broken),
            "chain_broken": self.chain_broken,
        }


def evaluate_packages(
    text: str, *, model: Any,
) -> list[PackageResult]:
    """네 묶음을 평가한다. 수급인 지위에서만 돈다."""
    if not getattr(model, "is_construction", False):
        return []
    if not getattr(model, "construction_confident", False):
        return []
    if getattr(model, "is_owner_side", False) or not getattr(model, "is_settled", False):
        return []

    # PDF 는 문장을 줄 폭에서 끊는다. 줄바꿈을 그대로 두면 줄바꿈을 금지한
    # 방어 패턴이 한 문장 안에서도 끊겨 "방어 없음" 으로 오판한다 — 실측:
    # 제19조 제2항의 "14일 이내에 … 통보한다" 가 줄바꿈 때문에 안 잡혔다.
    # 문장 경계는 마침표로 충분하므로 줄바꿈만 공백으로 접는다.
    body = re.sub(r"\s*\n\s*", " ", str(text or ""))
    out: list[PackageResult] = []
    for pkg in ALL_PACKAGES:
        result = PackageResult(key=pkg.key, label=pkg.label)
        for link in pkg.links:
            present = bool(link.trigger.search(body))
            defended = bool(link.defense.search(body)) if present else False
            row = {
                "key": link.key,
                "label": link.label,
                "present_in_contract": present,
                "defended": defended,
                "exposure": "" if (defended or not present) else link.exposure,
            }
            result.links.append(row)
            if present and not defended:
                result.broken.append(row)
        out.append(result)
    return out


def attach_packages_to_findings(
    clause_results: list[dict[str, Any]],
    packages: list[PackageResult],
) -> dict[str, Any]:
    """평가 결과를 해당 축을 이미 다루는 finding 에 연결한다.

    새 finding 을 만들지 않는다 — 연결만 한다. 어느 finding 도 그 축을 다루지
    않으면 `uncovered` 로 보고해, 최종 자가점검이 "위험이 큰 영역에 의견이
    없다" 를 판단할 수 있게 한다.
    """
    attached: list[dict[str, Any]] = []
    uncovered: list[str] = []
    for pkg in packages:
        if not pkg.chain_broken:
            continue
        spec = next((p for p in ALL_PACKAGES if p.key == pkg.key), None)
        topics = spec.covered_by_topics if spec else ()
        ids = spec.covered_by_ids if spec else ()
        hits = [
            cr for cr in clause_results
            if isinstance(cr, dict)
            and not cr.get("dedup_suppressed")
            and (
                str(cr.get("clause_topic") or "") in topics
                or str(cr.get("clause_id") or "") in ids
            )
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM", "CRITICAL")
            # 재하도급 계약서 등 **다른 문서**를 대상으로 하는 항목에는 이
            # 계약의 사슬을 붙이지 않는다(지시 11항).
            and str(cr.get("target_contract") or "this") == "this"
            and "재하도급 계약서" not in str(cr.get("display_path") or "")
        ]
        if not hits:
            uncovered.append(pkg.label)
            continue
        broken_labels = ", ".join(str(b["label"]) for b in pkg.broken)
        for cr in hits:
            chain = cr.setdefault("risk_package_chain", [])
            if isinstance(chain, list):
                chain.append({
                    "package": pkg.key,
                    "label": pkg.label,
                    "broken_links": broken_labels,
                })
            attached.append({
                "package": pkg.key,
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "broken_links": broken_labels,
            })
    return {"attached": attached, "uncovered": uncovered}
