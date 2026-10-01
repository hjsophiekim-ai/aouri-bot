"""법조문 grounding — 법률명 나열이 아니라 "계약조항 → 법률관계 → 조문 → 법률효과".

2026-10-01 지시 (정확한 법조문 연결)
──────────────────────────────────
실측(한글날 협업계약, 실제 AI): 에이전트가 legal_basis 에 "저작권법, 민법" 만 적었고,
그 문자열이 그대로 "법적/실무상 이유: 저작권법, 민법 / 지식재산권 분쟁 발생 시 …" 로
보고서에 실렸다. 조문 번호도, 그 조문이 왜 이 조항에 적용되는지도 없었다.

이 모듈이 하는 일
──────────────
  1. finding 의 **법률관계**를 먼저 정한다 — 이용허락인가 양도인가, 대리인가 단순
     권리보증인가, 실물 소유권인가 저작권인가(지시 3항).
  2. 그 관계에 맞는 조문만 검증된 표(`STATUTES`)에서 고른다. 표 밖의 조문은 쓰지
     않는다 — 틀린 조문보다 생략이 낫다(지시 7항).
  3. AI 가 적은 조문은 표와 관계로 대조해, 법률명만 있는 것·표에 없는 것·관계가 맞지
     않는 것(이용허락 구조에 제45조 양도)을 걷어 내고 기록한다(REVIEW_FAILED_STATUTE_GROUNDING).
  4. 결과를 `legal_grounding` 으로 싣는다:
        contract_clauses  관련 계약조항(제10조 제1항, 제10조 제4항 …)
        statutes          [{citation, title, effect, role}]
        legal_reason      법률상 이유(조문이 이 조항에 어떤 효과를 주는가)
        business_reason   실무상 이유(판매중단·추가 비용·제3자 클레임 …)
        statute_note      조문을 생략한 경우 그 사유

표의 조문 문언은 법령 원문을 요약한 것이다. 조문을 추가할 때는 반드시 법령 원문을
확인하고, 그 조문이 성립하는 법률관계(`relations`)를 함께 선언한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

STATUS_STATUTE_GROUNDING = "REVIEW_FAILED_STATUTE_GROUNDING"


@dataclass(frozen=True)
class Statute:
    law: str
    article: str            # "46", "2" …
    paragraph: str          # "" | "1" | "2"
    title: str
    effect: str             # 조문의 법률효과(요약)
    relations: frozenset[str]
    role: str               # 이 조문이 finding 에서 하는 역할
    item: str = ""          # "1호 타목" 등

    @property
    def citation(self) -> str:
        s = f"{self.law} 제{self.article}조"
        if self.paragraph:
            s += f" 제{self.paragraph}항"
        if self.item:
            s += f" {self.item}"
        return s


def _s(law: str, art: str, para: str, title: str, effect: str, relations: set[str], role: str, item: str = "") -> Statute:
    return Statute(law, art, para, title, effect, frozenset(relations), role, item)


_CR = "저작권법"
_CIV = "민법"
_VAT = "부가가치세법"

#: 검증된 조문 표. 순서가 같은 관계 안의 우선순위다.
STATUTES: tuple[Statute, ...] = (
    # ── 저작권 ──────────────────────────────────────────────────────────────
    _s(_CR, "46", "2", "저작물의 이용허락",
       "이용허락을 받은 자는 허락받은 이용 방법 및 조건의 범위 안에서 그 저작물을 이용할 수 있다.",
       {"ip_license", "background_ip"}, "이용허락 범위 — 허락받은 방법·조건(기간·매체·지역) 밖의 이용은 침해가 된다"),
    _s(_CR, "46", "1", "저작물의 이용허락",
       "저작재산권자는 다른 사람에게 그 저작물의 이용을 허락할 수 있다.",
       {"license_grant"}, "이용허락의 근거"),
    _s(_CR, "46", "3", "저작물의 이용허락",
       "이용허락에 의하여 저작물을 이용할 수 있는 권리는 저작재산권자의 동의 없이 제3자에게 양도할 수 없다.",
       {"license_transfer"}, "이용권의 제3자 양도·재허락 제한"),
    _s(_CR, "22", "", "2차적저작물작성권",
       "저작자는 그의 저작물을 원저작물로 하는 2차적저작물을 작성하여 이용할 권리를 가진다.",
       {"derivative"}, "2차적 이용 — 변형·재구성해 제품화하려면 2차적저작물 작성·이용에 대한 허락이 따로 필요하다"),
    _s(_CR, "45", "2", "저작재산권의 양도",
       "저작재산권의 전부를 양도하는 경우에 특약이 없는 때에는 제22조에 따른 2차적저작물작성권은 포함되지 아니한 것으로 추정한다.",
       {"assignment_derivative"}, "전부 양도 시 2차적저작물작성권 특약 — 특약이 없으면 양도에서 빠진 것으로 추정"),
    _s(_CR, "45", "1", "저작재산권의 양도",
       "저작재산권은 전부 또는 일부를 양도할 수 있다.",
       {"ip_assignment"}, "권리 양도 구조 — 양도 대상 권리의 범위를 특정해야 한다"),
    _s(_CR, "14", "1", "저작인격권의 일신전속성",
       "저작인격권은 저작자 일신에 전속한다.",
       {"moral_right"}, "저작인격권은 양도할 수 없다 — 귀속이 아니라 불행사 약정으로 다뤄야 한다"),
    _s(_CR, "13", "1", "동일성유지권",
       "저작자는 그의 저작물의 내용·형식 및 제호의 동일성을 유지할 권리를 가진다.",
       {"moral_right"}, "변경 이용 시 동일성유지권 — 본질적 변경 금지·사전 협의 범위"),
    _s(_CR, "12", "1", "성명표시권",
       "저작자는 저작물의 원본이나 그 복제물에 또는 저작물의 공표 매체에 그의 실명 또는 이명을 표시할 권리를 가진다.",
       {"credit"}, "작가 크레딧 표시"),
    _s(_CR, "35", "1", "미술저작물등의 전시 또는 복제",
       "미술저작물등의 원본의 소유자나 그의 동의를 얻은 자는 그 저작물을 원본에 의하여 전시할 수 있다.",
       {"physical_ownership"}, "원본 소유와 저작권의 구분 — 원본 소유자는 원본 전시는 할 수 있으나 복제·상품화·이미지 이용에는 이용허락이 따로 필요하다"),
    # ── 소유권 ──────────────────────────────────────────────────────────────
    _s(_CIV, "211", "", "소유권의 내용",
       "소유자는 법률의 범위 내에서 그 소유물을 사용, 수익, 처분할 권리가 있다.",
       {"physical_ownership"}, "실물 소유권의 내용 — 실물의 사용·처분 권한"),
    _s(_CIV, "188", "1", "동산소유권 양도의 효력",
       "동산에 관한 물권의 양도는 그 동산을 인도하여야 효력이 생긴다.",
       {"ownership_transfer"}, "실물 소유권 이전 시점 — 인도로 이전된다"),
    # ── 대리·권한 ───────────────────────────────────────────────────────────
    _s(_CIV, "114", "1", "대리행위의 효력",
       "대리인이 그 권한 내에서 본인을 위한 것임을 표시한 의사표시는 직접 본인에게 대하여 효력이 생긴다.",
       {"agency"}, "적법한 대리의 효과 — 권한 범위 안의 행위만 아티스트(본인)에게 효력이 있다"),
    _s(_CIV, "130", "", "무권대리",
       "대리권 없는 자가 타인의 대리인으로 한 계약은 본인이 이를 추인하지 아니하면 본인에 대하여 효력이 없다.",
       {"agency"}, "무권대리 — 권한이 없으면 아티스트가 추인하지 않는 한 아티스트에게 효력이 없다"),
    _s(_CIV, "135", "1", "상대방에 대한 무권대리인의 책임",
       "대리권을 증명하지 못하고 본인의 추인을 받지 못한 대리인은 상대방의 선택에 따라 계약을 이행할 책임 또는 손해를 배상할 책임이 있다.",
       {"agency"}, "무권대리인 책임 — 그 경우 갤러리·에이전시에 이행 또는 손해배상을 구할 수 있을 뿐이다"),
    # ── 채무불이행·손해배상 ─────────────────────────────────────────────────
    _s(_CIV, "390", "", "채무불이행과 손해배상",
       "채무자가 채무의 내용에 좇은 이행을 하지 아니한 때에는 채권자는 손해배상을 청구할 수 있다.",
       {"warranty", "agency", "damages"}, "계약상 의무·권리보증 위반에 따른 손해배상"),
    _s(_CIV, "393", "", "손해배상의 범위",
       "채무불이행으로 인한 손해배상은 통상의 손해를 그 한도로 하고, 특별한 사정으로 인한 손해는 채무자가 그 사정을 알았거나 알 수 있었을 때에 한하여 배상한다.",
       {"damages_scope"}, "배상 범위 — 직접·통상손해로 한정하면 판매중단·회수 비용이 빠질 수 있다"),
    _s(_CIV, "398", "2", "배상액의 예정",
       "손해배상의 예정액이 부당히 과다한 경우에는 법원은 적당히 감액할 수 있다.",
       {"penalty"}, "위약금·손해배상액 예정 — 과다하면 감액 대상"),
    # ── 해제·해지 ───────────────────────────────────────────────────────────
    _s(_CIV, "543", "1", "해지, 해제권",
       "계약 또는 법률의 규정에 의하여 해지 또는 해제의 권리가 있는 때에는 그 해지 또는 해제는 상대방에 대한 의사표시로 한다.",
       {"termination"}, "해지권 행사 방식"),
    _s(_CIV, "544", "", "이행지체와 해제",
       "당사자 일방이 채무를 이행하지 아니한 때에는 상대방은 상당한 기간을 정하여 이행을 최고하고 그 기간 내에 이행하지 아니한 때에는 계약을 해제할 수 있다.",
       {"termination_cure"}, "최고(시정요구) 후 해제 — 시정기간과 그 경과 후 해지권을 계약에 정해야 한다"),
    _s(_CIV, "550", "", "해지의 효과",
       "당사자 일방이 계약을 해지한 때에는 계약은 장래에 대하여 그 효력을 잃는다.",
       {"termination_effect"}, "해지의 장래효 — 종료 후 정산·존속 조항을 따로 정해야 한다"),
    # ── 금전 ────────────────────────────────────────────────────────────────
    _s(_CIV, "492", "1", "상계의 요건",
       "쌍방이 서로 같은 종류를 목적으로 한 채무를 부담한 경우에 그 쌍방의 채무의 이행기가 도래한 때에는 각 채무자는 대등액에 관하여 상계할 수 있다.",
       {"setoff"}, "상계 요건"),
    _s("상법", "54", "", "상사법정이율",
       "상행위로 인한 채무의 법정이율은 연 6분으로 한다.",
       {"late_interest"}, "지연이자율의 기준"),
    # ── 세무 ────────────────────────────────────────────────────────────────
    _s(_VAT, "32", "1", "세금계산서 등",
       "사업자가 재화 또는 용역을 공급하는 경우에는 세금계산서를 그 공급을 받는 자에게 발급하여야 한다.",
       {"tax_invoice"}, "세금계산서 발급 의무와 발급 주체"),
    _s(_VAT, "16", "1", "용역의 공급시기",
       "용역이 공급되는 시기는 역무의 제공이 완료되는 때 또는 시설물, 권리 등 재화가 사용되는 때로 한다.",
       {"tax_invoice"}, "공급시기 — 로열티 등 권리 사용 대가의 세금계산서 발급 시점"),
    _s(_VAT, "60", "2", "가산세",
       "세금계산서를 공급시기가 지난 후 발급하거나 발급하지 아니한 경우 공급가액에 일정 비율의 가산세를 부과한다.",
       {"tax_invoice"}, "지연·미발급 시 가산세"),
    _s("소득세법", "127", "1", "원천징수의무",
       "국내에서 거주자나 비거주자에게 이 조에 규정된 소득을 지급하는 자는 그 소득세를 원천징수하여야 한다.",
       {"withholding"}, "개인 협업자에게 대가를 지급할 때의 원천징수 의무"),
    _s(_VAT, "29", "1", "과세표준",
       "재화 또는 용역의 공급에 대한 부가가치세의 과세표준은 해당 과세기간에 공급한 재화 또는 용역의 공급가액을 합한 금액으로 한다.",
       {"vat"}, "VAT 포함·별도 여부에 따른 과세표준과 실지급액"),
    # ── 기타 ────────────────────────────────────────────────────────────────
    _s("민사소송법", "29", "1", "합의관할",
       "당사자는 합의로 제1심 관할법원을 정할 수 있다.",
       {"jurisdiction"}, "관할 합의"),
    _s(_CIV, "34", "", "법인의 권리능력",
       "법인은 법률의 규정에 좇아 정관으로 정한 목적의 범위 내에서 권리와 의무의 주체가 된다.",
       {"legal_entity"}, "권리·의무의 주체는 법인 — 브랜드·그룹명은 당사자가 될 수 없다"),
    _s(_CIV, "667", "1", "수급인의 담보책임",
       "완성된 목적물 또는 완성 전의 성취된 부분에 하자가 있는 때에는 도급인은 수급인에 대하여 상당한 기간을 정하여 그 하자의 보수를 청구할 수 있다.",
       {"defect_works"}, "제작물 하자 보수 청구"),
    _s(_CIV, "580", "1", "매도인의 하자담보책임",
       "매매의 목적물에 하자가 있는 때에는 매도인은 하자담보책임을 진다.",
       {"defect_sale"}, "매매 목적물 하자담보"),
    _s("개인정보 보호법", "17", "1", "개인정보의 제공",
       "개인정보처리자는 정보주체의 동의를 받은 경우 등에 한하여 개인정보를 제3자에게 제공할 수 있다.",
       {"personal_data"}, "개인정보 제3자 제공 요건"),
    _s("약관의 규제에 관한 법률", "6", "1", "일반원칙",
       "신의성실의 원칙을 위반하여 공정성을 잃은 약관 조항은 무효이다.",
       {"standard_terms"}, "불공정 약관 조항의 무효"),
    _s("부정경쟁방지 및 영업비밀보호에 관한 법률", "2", "", "정의(부정경쟁행위)",
       "국내에 널리 인식되고 경제적 가치를 가지는 타인의 성명, 초상, 음성, 서명 등 그 타인을 식별할 수 있는 표지를 무단으로 사용하는 행위는 부정경쟁행위이다.",
       {"publicity"}, "성명·초상 등 퍼블리시티 이용", item="제1호 타목"),
)

#: 법률관계마다 법률상 이유(조문이 이 조항에 주는 효과)를 한 문장으로.
RELATION_REASON: dict[str, str] = {
    "ip_license": "이 조항은 저작재산권 양도가 아니라 이용허락입니다. 허락받은 이용 방법·조건(기간·매체·지역·용도) 밖의 이용은 저작권 침해가 되므로, 제품화·복제·판매·홍보에 필요한 이용 범위가 허락 문언에 빠짐없이 들어 있어야 합니다.",
    "background_ip": "프로젝트 이전부터 협업자가 보유한 작품·디자인·기법의 권리는 협업자에게 남습니다. 결과물에 그 기존 저작물이 포함되면 그 부분도 이용허락의 대상이어야 제품화·판매가 가능합니다.",
    "derivative": "작품을 제품의 형태로 변형·재구성하는 것은 2차적저작물 작성에 해당할 수 있고, 그 권리는 저작자에게 있습니다. 이용허락이 2차적저작물의 작성·이용까지 포함하는지 따로 정해야 합니다.",
    "assignment_derivative": "저작재산권 전부를 양도받더라도 특약이 없으면 2차적저작물작성권은 양도되지 않은 것으로 추정되므로, 양도 조항에 그 권리를 명시해야 합니다.",
    "ip_assignment": "저작재산권 양도 구조이므로 양도되는 권리의 범위(복제·배포·전시·2차적저작물작성권 등)를 특정해야 합니다.",
    "moral_right": "저작인격권은 저작자에게 전속해 양도할 수 없으므로, 변경 이용이 필요하면 귀속 조항이 아니라 불행사·사전 협의 약정으로 다뤄야 합니다.",
    "credit": "작가는 성명표시권을 가지므로 크레딧 표시 방법과 생략 가능한 경우를 정해 두어야 분쟁을 피할 수 있습니다.",
    "physical_ownership": "실물(원본) 소유권과 저작권은 별개의 권리입니다. 원본을 소유하면 원본을 전시·보관·처분할 수 있지만, 그 작품을 복제·상품화하거나 이미지를 이용하려면 저작권자의 이용허락이 따로 필요합니다.",
    "ownership_transfer": "동산 소유권은 인도로 이전되므로 귀속 주체와 함께 인도·이전 시점을 정해야 합니다.",
    "agency": "협업자가 아티스트 본인이 아니면, 갤러리·에이전시가 받은 권한 범위 안의 행위만 아티스트에게 효력이 있습니다. 권한이 없으면 아티스트가 추인하지 않는 한 아티스트에게 효력이 없고, 그때는 대리인에게 이행 또는 손해배상을 구할 수 있을 뿐입니다.",
    "warranty": "권리 보증은 계약상 의무이므로 보증이 사실과 다르면 채무불이행으로 손해배상을 청구할 수 있습니다.",
    "damages": "계약상 의무를 위반하면 채무불이행 손해배상 책임이 발생합니다.",
    "damages_scope": "배상 범위를 '직접적인 손해'로 한정하면 판매중단·제품 회수·재제작 비용처럼 통상손해 밖으로 다툴 여지가 있는 손해가 빠질 수 있습니다.",
    "penalty": "위약금·손해배상액의 예정은 부당히 과다하면 법원이 감액할 수 있습니다.",
    "termination": "해지는 상대방에 대한 의사표시로 하므로, 해지 사유·통지 방법을 계약에 정해 두어야 합니다.",
    "termination_cure": "법정 해제도 상당한 기간을 정한 최고(시정요구)를 거쳐야 하므로, 시정기간과 그 경과 후의 해지권을 계약에 명시해야 합니다.",
    "termination_effect": "해지하면 계약은 장래에 대해서만 효력을 잃으므로, 종료 후 정산·이용권 존속·자료 반환을 따로 정해야 합니다.",
    "setoff": "상계는 쌍방 채무의 이행기가 도래해야 가능하므로, 공제·상계의 대상과 시점을 계약에 정해야 합니다.",
    "late_interest": "금전채무 지연 시 법정이율에 의한 지연손해금이 발생합니다.",
    "tax_invoice": "재화·용역(권리 사용 포함)을 공급하는 사업자는 공급시기에 세금계산서를 발급해야 하고, 지연·미발급 시 가산세가 부과됩니다. 발급 주체와 공급시기를 지급 조항과 맞춰야 합니다.",
    "withholding": "사업자가 아닌 개인에게 로열티·제작 대가를 지급하면 지급자가 소득세를 원천징수해야 하므로, 협업자가 사업자인지 개인인지를 확정해야 합니다.",
    "vat": "계약금액이 부가가치세 포함인지 별도인지에 따라 과세표준과 실제 지급액이 달라집니다.",
    "jurisdiction": "제1심 관할은 서면 합의로 정할 수 있습니다.",
    "legal_entity": "계약상 권리·의무는 권리능력 있는 법인에 귀속되므로 당사자는 등기상 법인명으로 표시해야 합니다.",
    "defect_works": "제작물에 하자가 있으면 상당한 기간을 정해 보수를 청구할 수 있습니다.",
    "defect_sale": "매매 목적물에 하자가 있으면 매도인이 하자담보책임을 집니다.",
    "personal_data": "개인정보를 제3자에게 제공하려면 정보주체 동의 등 법정 요건이 필요합니다.",
    "standard_terms": "신의성실 원칙에 반해 공정성을 잃은 약관 조항은 무효입니다.",
    "publicity": "작가의 성명·초상 등을 홍보에 쓰려면 사용 범위를 정한 동의가 필요합니다.",
    "license_transfer": "이용권은 저작재산권자 동의 없이 제3자에게 넘길 수 없으므로, 생산 위탁·재허락이 필요하면 미리 동의를 받아 두어야 합니다.",
}


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


#: 법률관계 판정 — finding 의 제목·문제·하위 쟁점과 붙은 조항 원문을 본다.
RELATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ip_license", _rx(r"이용권|이용\s*허락|이용을\s*허락|라이선스|사용권|이용\s*범위|상품화|제품화")),
    ("background_ip", _rx(r"기존\s*(?:저작물|지식재산|작품|디자인|IP)|이전부터\s*보유|배경\s*IP|background|제작기법|조형\s*언어")),
    ("derivative", _rx(r"2차적|이차적|변형|각색|재가공|개작|재구성")),
    ("ip_assignment_word", _rx(r"(?:저작재산권|저작권|권리)[^.\n]{0,12}양도|양도[^.\n]{0,10}(?:저작재산권|저작권)")),
    ("moral_right", _rx(r"저작인격권|동일성\s*유지|본질적인?\s*내용을?\s*(?:임의로\s*)?변경")),
    ("credit", _rx(r"크레딧|성명\s*표시")),
    ("physical_ownership", _rx(r"실물\s*소유권|원본|원작|커미션\s*작품|작품의?\s*소유권|소유권[^.\n]{0,10}귀속\s*주체")),
    ("ownership_transfer", _rx(r"소유권[^.\n]{0,15}(?:이전|인도)\s*(?:시점|시기)")),
    ("agency", _rx(r"갤러리|에이전시|대리인|대리권|무권대리|위임(?:받|장)|권한\s*(?:부재|하자|위임|증빙|확보|확인|불충분)"
                     r"|(?:아티스트|작가|권리자)\s*(?:의\s*)?권한|권한\s*[·및]\s*보증")),
    ("warranty", _rx(r"보증|진술\s*및\s*보장|권리\s*하자")),
    ("damages_scope", _rx(r"직접적인\s*손해|통상\s*손해|특별\s*손해|간접\s*손해|배상\s*범위|일실")),
    ("damages", _rx(r"손해\s*배상|배상\s*책임")),
    ("penalty", _rx(r"위약금|손해배상액의?\s*예정|지체상금")),
    ("termination", _rx(r"해지|해제")),
    ("termination_cure", _rx(r"시정\s*(?:요구|기간)|최고")),
    ("termination_effect", _rx(r"종료\s*후|해지\s*(?:의\s*)?효과|존속|잔존")),
    ("setoff", _rx(r"상계|공제")),
    ("late_interest", _rx(r"지연\s*(?:이자|손해금)|연\s*\d+\s*%")),
    ("tax_invoice", _rx(r"세금계산서|공급시기|가산세")),
    ("withholding", _rx(r"원천징수")),
    ("vat", _rx(r"부가가치세|\bVAT\b")),
    ("jurisdiction", _rx(r"관할")),
    ("legal_entity", _rx(r"법인명|당사자\s*(?:표시|표기|법인)|권리능력|브랜드[^.\n]{0,10}(?:법인|당사자)")),
    ("defect", _rx(r"하자|A/S|보수\s*청구")),
    ("personal_data", _rx(r"개인정보")),
    ("standard_terms", _rx(r"약관")),
    ("publicity", _rx(r"초상|퍼블리시티|성명[^.\n]{0,6}(?:사용|이용)")),
    ("license_transfer", _rx(r"재허락|서브\s*라이선스|제3자에게\s*(?:이용권|사용권)")),
)

_LAW_NAMES = (
    "저작권법", "민법", "상법", "부가가치세법", "민사소송법", "개인정보 보호법", "개인정보보호법",
    "약관의 규제에 관한 법률", "약관규제법", "하도급법", "하도급거래 공정화에 관한 법률",
    "부정경쟁방지법", "부정경쟁방지 및 영업비밀보호에 관한 법률", "공정거래법", "대리점법",
    "전자상거래법", "표시광고법", "소비자기본법", "제조물 책임법", "제조물책임법",
    "소득세법", "법인세법", "국세기본법", "지방세법", "조세특례제한법", "상표법", "특허법",
    "디자인보호법", "근로기준법", "산업안전보건법", "중대재해처벌법", "건설산업기본법",
    "대규모유통업법", "가맹사업법", "정보통신망법", "독점규제법",
)
_LAW_ALIASES = {
    "개인정보보호법": "개인정보 보호법", "약관규제법": "약관의 규제에 관한 법률",
    "부정경쟁방지법": "부정경쟁방지 및 영업비밀보호에 관한 법률", "제조물책임법": "제조물 책임법",
    "하도급거래 공정화에 관한 법률": "하도급법",
}
_RX_LAW = "|".join(re.escape(n) for n in sorted(_LAW_NAMES, key=len, reverse=True))
_RX_CITATION = re.compile(
    rf"(?P<law>{_RX_LAW})\s*(?:상\s*)?제\s*(?P<art>\d+)\s*조(?:의\s*(?P<sub>\d+))?(?:\s*제\s*(?P<para>\d+)\s*항)?"
)
#: 법률명만 — "저작권법, 민법", "민법상", "관련 법령", "제45조 등".
_RX_NAME_ONLY = re.compile(
    rf"(?:(?:{_RX_LAW})(?:상|의|에\s*따른)?(?:\s*[,·및/]\s*|\s+))+(?=\s*/|\s*$|\s*\n)"
    rf"|(?:관련\s*법령|관계\s*법령|관련\s*법률)(?:상|에\s*따라)?"
)
_RX_LEADING_LAW_LIST = re.compile(rf"^\s*(?:(?:{_RX_LAW})(?:\s*등)?\s*[,·및]?\s*)+/\s*")


def _canonical_law(name: str) -> str:
    return _LAW_ALIASES.get(name, name)


def _haystack(cr: dict[str, Any]) -> str:
    parts = [str(cr.get(k) or "") for k in ("problem", "rewrite_reason", "issue_title", "clause_title")]
    for d in cr.get("detected_issue_list") or []:
        if isinstance(d, dict):
            parts.append(str(d.get("issue_title") or ""))
    for s in cr.get("sub_issues") or []:
        if isinstance(s, dict):
            parts.append(str(s.get("title") or "") + " " + str(s.get("problem") or ""))
    return " ".join(parts)


#: 세부 관계 → 그 세부 관계가 성립하려면 먼저 있어야 하는 주 관계.
_QUALIFIERS: dict[str, tuple[str, ...]] = {
    "termination_cure": ("termination",),
    "termination_effect": ("termination",),
    "derivative": ("ip_license", "ip_assignment_word"),
    "background_ip": ("ip_license", "derivative"),
    "moral_right": ("ip_license", "derivative", "ip_assignment_word"),
    "credit": ("ip_license", "moral_right"),
    "license_transfer": ("ip_license",),
    "damages_scope": ("damages", "warranty", "agency"),
    "ownership_transfer": ("physical_ownership",),
    "warranty": ("agency",),
}


def _title_hay(cr: dict[str, Any]) -> str:
    parts = [_title_of(cr)]
    for s in cr.get("sub_issues") or []:
        if isinstance(s, dict):
            parts.append(str(s.get("title") or ""))
    return " ".join(parts)


def detect_relations(cr: dict[str, Any], *, archetype: str = "") -> list[str]:
    """finding 의 법률관계.

    관계는 finding 이 **무엇에 관한 것인가**(제목·하위 쟁점 제목)로 정한다. 문제 서술은
    제목이 세운 주 관계의 세부만 보탠다 — "손해배상" 이 결과로 언급됐다고 IP 쟁점에
    민법 제390조를, "보증금·지체상금" 이 스쳤다고 계약금액 공란에 보증·위약금 조문을
    붙이던 오연결을 막는다(지시 3항). 원문 조항은 양도/이용허락 구분에만 쓴다.
    """
    title = re.sub(r"^\s*\[[^\]]{1,12}\]\s*", "", _title_hay(cr))
    detail = " ".join(str(cr.get(k) or "") for k in ("problem", "rewrite_reason"))
    original = str(cr.get("original_text") or "")
    found = [key for key, rx in RELATION_PATTERNS if rx.search(title)]
    if not found:
        # 제목이 법률관계를 말하지 않는 finding(규칙 id 제목 등)은 문제 서술의 **첫 문장**
        # (무엇이 문제인가)으로 정한다. 뒤 문장의 파급효과("지체상금·보증금이 연동")는
        # 그 finding 의 법률관계가 아니다.
        first = re.split(r"(?<=[.。])\s|(?<=다)\s", str(cr.get("problem") or cr.get("rewrite_reason") or ""), maxsplit=1)[0]
        found = [key for key, rx in RELATION_PATTERNS if rx.search(first)
                 and key not in _QUALIFIERS]
    for key, parents in _QUALIFIERS.items():
        if key not in found and any(p in found for p in parents):
            rx = dict(RELATION_PATTERNS)[key]
            if rx.search(detail):
                found.append(key)
    rel: list[str] = []
    for key in found:
        if key == "ip_assignment_word":
            # 양도는 이용허락과 다른 구조다 — 조항 문언이 양도를 말할 때만(지시 3항).
            if re.search(r"양도", original):
                rel.append("ip_assignment")
            continue
        if key == "defect":
            rel.append("defect_sale" if archetype in ("goods_supply", "distribution_resale") else "defect_works")
            continue
        rel.append(key)
    if "ip_assignment" in rel and "derivative" in rel:
        rel.append("assignment_derivative")
    elif "derivative" in rel and "ip_license" not in rel:
        # 양도가 아닌 구조에서의 2차적 이용은 이용허락의 범위 문제다 — 제22조만 붙이면
        # "왜 이 계약에서" 가 빠진다(지시 5항: 이용허락 → 제46조, 2차적 → 제22조).
        rel.insert(rel.index("derivative"), "ip_license")
    if "physical_ownership" in rel:
        # 실물 소유권 쟁점을 2차적저작물 문제로 오인하지 않는다(지시 14항 C) —
        # 제목이 2차적 이용을 직접 말하지 않으면 그 관계를 뺀다.
        if not re.search(r"2차적|이차적", _title_of(cr)):
            rel = [r for r in rel if r not in ("derivative", "assignment_derivative")]
    if "agency" in rel and "warranty" not in rel and re.search(r"보증", original):
        rel.append("warranty")
    if "agency" in rel and "ip_license" not in rel and re.search(
        r"이용|제품화|저작|이미지", original + " " + detail + " " + str(cr.get("suggested_rewrite") or "")
    ):
        # 대리인이 넘겨 주는 것이 저작물 이용 권한이면 그 권한의 범위가 제46조 문제다(지시 6항).
        at = rel.index("warranty") + 1 if "warranty" in rel else rel.index("agency") + 1
        rel.insert(at, "ip_license")
    # 해지 세부 관계는 해지 쟁점일 때만.
    if "termination" not in rel:
        rel = [r for r in rel if r not in ("termination_cure", "termination_effect")]
    # 손해배상 일반은 더 구체적인 관계가 있으면 뺀다.
    if "damages" in rel and any(r in rel for r in ("warranty", "agency", "penalty")):
        rel.remove("damages")
    return list(dict.fromkeys(rel))


def _title_of(cr: dict[str, Any]) -> str:
    for d in cr.get("detected_issue_list") or []:
        if isinstance(d, dict) and str(d.get("issue_title") or "").strip():
            return str(d["issue_title"])
    return str(cr.get("issue_title") or cr.get("clause_title") or "")


def statutes_for(relations: list[str], *, limit: int = 5) -> list[Statute]:
    out: list[Statute] = []
    for rel in relations:
        for st in STATUTES:
            if rel in st.relations and st not in out:
                out.append(st)
    return out[:limit]


def _find_statute(law: str, art: str, para: str | None) -> Statute | None:
    law = _canonical_law(law)
    cands = [s for s in STATUTES if s.law == law and s.article == art]
    if not cands:
        return None
    if para:
        exact = [s for s in cands if s.paragraph == para]
        return exact[0] if exact else None
    return cands[0]


def audit_cited_statutes(text: str, relations: list[str]) -> tuple[list[Statute], list[dict[str, str]]]:
    """AI·규칙이 적은 조문을 대조한다. (통과한 조문, 걷어 낸 조문과 사유)."""
    kept: list[Statute] = []
    removed: list[dict[str, str]] = []
    for m in _RX_CITATION.finditer(text or ""):
        law, art, para = m.group("law"), m.group("art"), m.group("para")
        cite = m.group(0).strip()
        if m.group("sub"):
            removed.append({"citation": cite, "reason": "검증된 조문 표에 없음(가지조문)"})
            continue
        st = _find_statute(law, art, para)
        if st is None:
            removed.append({"citation": cite, "reason": "검증된 조문 표에 없거나 항이 다름 — 정확한 조문 특정 필요"})
            continue
        if not (st.relations & set(relations)):
            removed.append({"citation": cite, "reason": f"이 finding 의 법률관계({', '.join(relations) or '미상'})에 맞지 않음"})
            continue
        if st not in kept:
            kept.append(st)
    for m in _RX_NAME_ONLY.finditer(text or ""):
        frag = m.group(0).strip(" ,·/")
        if frag:
            removed.append({"citation": frag, "reason": "법률명만 있고 조문이 없음"})
    return kept, removed


def strip_law_mentions(text: str) -> str:
    """서술에서 법률명 나열·근거 없는 조문 표기를 걷어 낸다 — 실무상 이유만 남긴다."""
    s = str(text or "")
    # 에이전트는 "근거 법령 / 실무 이유" 로 이어 붙인다 — 앞쪽이 법령 서술이면 통째로 뗀다
    # (실측: "저작권법 제46조 제1항: … / 제품화·판매 …" 에서 조문만 지우면 "제1항: … /" 가 남았다).
    head, sep, tail = s.partition(" / ")
    if sep and tail.strip() and (
        _RX_CITATION.search(head) or re.search(rf"{_RX_LAW}|제\s*\d+\s*[조항]|^\s*:", head)
    ):
        s = tail
    s = _RX_LEADING_LAW_LIST.sub("", s)
    s = _RX_CITATION.sub("", s)
    s = re.sub(rf"(?:{_RX_LAW})(?:상|의|에\s*따른|에\s*따라)?(?:\s*[,·및]\s*(?:{_RX_LAW})(?:상|의)?)*\s*", "", s)
    s = re.sub(r"(?:관련\s*법령|관계\s*법령|관련\s*법률)(?:상|에\s*따라)?\s*", "", s)
    s = re.sub(r"\s*등\s*(?=[,./]|$)", "", s)
    s = re.sub(r"^\s*[/,·]\s*", "", s)
    # 법률명을 지운 자리에 남는 빈 구분자 — "(민법, 거래안정성)" → "(거래안정성)".
    s = re.sub(r"\(\s*[,·/]\s*", "(", s)
    s = re.sub(r"\s*[,·]\s*\)", ")", s)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


__all__ = [
    "RELATION_REASON",
    "STATUS_STATUTE_GROUNDING",
    "STATUTES",
    "Statute",
    "audit_cited_statutes",
    "detect_relations",
    "statutes_for",
    "strip_law_mentions",
]
