"""임직원 비밀유지계약(Employee NDA) 사전질문 — whitelist + 계약 간 오염 차단.

2026-09-28 지시. 실측(신규 입사자 비밀유지계약, California):

    Q-EFF-payment-basis        "대가(금액·단가)를 어떤 근거로 산정했나요?"
                               — 부가가치세법 제29조·특수관계인 거래
    Q-EFF-liability-exposure   "최대 손해 규모" — 배상 한도를 계약 대가 기준으로
    Q-EFF-termination-recovery "이미 제공한 것을 회수할 수 있나요?"
    Q-FOCUS-privacy            "개인정보를 제3자에게 제공하거나 재위탁하는 절차"
                               — 담당자는 '위탁이 아니라 내부 직원' 이라고 답했다

모두 사업자 간 유상거래의 질문이다. 직원 비밀유지 서약에는 대가·단가·처리위탁이
없다. 원인은 질문 생성이 'NDA' 라는 큰 분류만 보고, 그 안의 거래모델
(`employee_nda_model`)을 모른 채 법률효과 질문(`effect_questions`)을
기계적으로 채웠기 때문이다.

이 모듈이 하는 일
──────────────
1. **whitelist** — 직원 비밀유지계약에서 법률판단을 바꾸는 미확정 사실만
   질문 후보로 둔다. 각 질문은 (a) 없으면 어떤 판단을 못 하는지,
   (b) 어느 조항/쟁점에 연결되는지, (c) 원문·담당자 설명에 이미 답이
   있는지를 스스로 확인한 뒤에만 나간다.
2. **거래모델 확정 후 다른 질문군 비활성화** — 대리점·공사·광고·용역·세무
   템플릿 질문은 whitelist 밖이므로 전부 `QUESTION_REJECTED_OUT_OF_SCOPE`.
   AI 가 계약을 읽고 만든 질문은 whitelist 주제에 대응하면 그 주제의
   판정(열림/이미 답 있음)을 따르고, 대응하지 않으면 오염 검사를 통과한
   1건까지만 "원문에서 새로 발견된 쟁점" 으로 허용한다.
3. **개인정보 취급 구조** — 내부 직원 접근으로 확정되면 처리위탁·재위탁·
   제3자 제공 질문을 반복하지 않는다.
4. **계약 간 오염 hard gate** — 계약단가·부가가치세·특수관계인·경영간섭·
   판매정책·공사대금·검수·준공·광고매체·위탁수수료 질문은 원문에 직접
   근거가 없으면 제거한다. 제거 후에도 남으면
   `REVIEW_FAILED_QUESTION_CROSS_CONTRACT_CONTAMINATION`.

오염 검사(4)는 직원 비밀유지계약에 한정하지 않는다 — 비밀유지 계열 전체에서
"원문에 근거 없는 사업거래 질문" 은 같은 실패다. whitelist(1·2)는 거래모델이
confident 인 직원 비밀유지계약에서만 켠다. 확신하지 못하면 끄지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from runtime.questions.model import Question
from runtime.review.employee_nda_model import (
    INFO_TYPE_LABELS,
    NDA_TYPE_CODES,
    PD_EMPLOYEE_INTERNAL,
    EmployeeNdaModel,
)

QUESTION_REJECTED_OUT_OF_SCOPE = "QUESTION_REJECTED_OUT_OF_SCOPE"
QUESTION_REJECTED_ALREADY_ANSWERED = "QUESTION_REJECTED_ALREADY_ANSWERED"
QUESTION_REJECTED_DUPLICATE = "QUESTION_REJECTED_DUPLICATE"
QUESTION_REJECTED_PD_STRUCTURE_SETTLED = "QUESTION_REJECTED_PD_STRUCTURE_SETTLED"
REVIEW_FAILED_QUESTION_CROSS_CONTRACT_CONTAMINATION = (
    "REVIEW_FAILED_QUESTION_CROSS_CONTRACT_CONTAMINATION"
)

#: 원문에서 새로 발견된 쟁점으로 허용하는 AI 질문의 최대 개수.
MAX_NOVEL_AI_QUESTIONS = 1


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════════
# 1. 계약 간 오염 — 질문 문형 ↔ 원문 근거
# ══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ContaminationAxis:
    key: str
    label: str
    #: 질문(제목+설명)이 이 축을 묻고 있는가.
    question: re.Pattern[str]
    #: 계약 원문에 이 축을 물을 **직접 근거**가 있는가. 없으면 오염이다.
    basis: re.Pattern[str]


#: 원문 근거 패턴은 **그 거래를 규정하는 문형**으로 잡는다. 직원 비밀유지계약도
#: "vendor pricing", "tax records", "payment terms" 같은 낱말을 **보호대상
#: 정보의 목록**으로 쓴다 — 낱말이 있다고 그 거래가 있는 것이 아니다.
_PRICE_BASIS = (
    r"단가|대금|계약금액|용역비|공사비|납품가|purchase\s+price|\bfees?\s+(?:of|payable|shall|are|is)"
    r"|\$\s?\d[\d,]*|USD\s?\d|KRW\s?\d|금\s*[\d,]+\s*원|[\d,]{4,}\s*원"
)
CONTAMINATION_AXES: tuple[ContaminationAxis, ...] = (
    ContaminationAxis(
        "unit_price", "계약단가·대가 산정",
        _rx(r"계약\s*단가|납품\s*단가|단가\s*(?:산정|근거|인하)|대가\s*\(?\s*금액|대가[^.?\n]{0,12}산정|계약\s*대가\s*기준|대가를?\s*크게\s*넘"),
        _rx(_PRICE_BASIS),
    ),
    ContaminationAxis(
        "vat", "부가가치세",
        _rx(r"부가가치세|\bVAT\b|세금계산서"),
        _rx(r"부가가치세|\bVAT\b|세금계산서|tax\s+invoice|sales\s+tax"),
    ),
    ContaminationAxis(
        "related_party", "특수관계인 거래",
        _rx(r"특수\s*관계(?:인|자)|부당행위\s*계산"),
        _rx(r"특수\s*관계|related\s+part(?:y|ies)|arm['’]?s[- ]length"),
    ),
    ContaminationAxis(
        "withholding", "원천징수",
        _rx(r"원천\s*징수"),
        _rx(r"원천\s*징수|withholding\s+tax"),
    ),
    ContaminationAxis(
        "management_interference", "경영간섭·판매정책 통제",
        _rx(r"경영\s*간섭|영업\s*정책|판매\s*정책|가격\s*/\s*인사|인사\s*/\s*영업|재판매\s*가격"),
        _rx(r"경영\s*간섭|영업\s*정책|판매\s*정책|판매\s*가격|resale\s+price|\bdealers?\b|대리점"),
    ),
    ContaminationAxis(
        "dealer_resale", "대리점·재판매",
        _rx(r"대리점|재판매|위탁\s*판매|판매\s*장려금|판촉비|반품비"),
        _rx(r"대리점|재판매|위탁\s*판매|\bdealers?\b|distribut(?:or|ion)\s+(?:agreement|rights)|resell|resale"),
    ),
    ContaminationAxis(
        "advertising", "광고비·매체집행",
        _rx(r"광고\s*(?:비|매체|집행|송출)|매체\s*(?:집행|송출|비)"),
        _rx(r"광고|advertis|매체|media\s+placement"),
    ),
    ContaminationAxis(
        "construction", "공사대금·검수·준공",
        _rx(r"공사\s*대금|준공|기성|착공|하자\s*보수"),
        _rx(r"공사|준공|기성|construction|contractor|하자"),
    ),
    ContaminationAxis(
        "acceptance", "검수·인수",
        _rx(r"검수|인수\s*기준|합격\s*기준|acceptance\s+(?:test|criteria)"),
        _rx(r"검수|검사|acceptance\s+(?:test|criteria|of\s+deliverables)|inspection|deliverables?"),
    ),
    ContaminationAxis(
        "commission", "위탁수수료",
        _rx(r"위탁\s*수수료|판매\s*수수료|수수료율"),
        _rx(r"수수료|commissions?\b"),
    ),
    ContaminationAxis(
        "liability_cap", "계약대가 대비 손해배상 한도",
        _rx(r"최대\s*손해\s*규모|손해\s*규모|배상\s*(?:한도|상한)[^.?\n]{0,20}(?:대가|금액)|책임\s*(?:한도|상한)"),
        _rx(_PRICE_BASIS + r"|limitation\s+of\s+liability|책임\s*(?:한도|상한)|배상\s*(?:한도|상한|총액)"),
    ),
)

#: 개인정보 처리위탁·제3자 제공을 묻는 질문 — 내부 접근으로 확정되면 묻지 않는다.
_RX_PROCESSOR_QUESTION = _rx(
    r"(?:처리\s*)?위탁|재위탁|수탁|processor|outsourc|제\s*3\s*자\s*(?:에게\s*)?제공|제삼자\s*제공"
)


def _q_text(q: Any) -> str:
    if isinstance(q, dict):
        return f"{q.get('title') or ''}\n{q.get('description') or ''}"
    return f"{getattr(q, 'title', '') or ''}\n{getattr(q, 'description', '') or ''}"


def _q_id(q: Any) -> str:
    if isinstance(q, dict):
        return str(q.get("question_id") or "")
    return str(getattr(q, "question_id", "") or "")


def contamination_axes_for(question: Any, contract_text: str) -> list[str]:
    """이 질문이 원문 근거 없이 묻고 있는 다른 거래유형의 축."""
    blob = _q_text(question)
    body = str(contract_text or "")
    return [
        ax.key for ax in CONTAMINATION_AXES
        if ax.question.search(blob) and not ax.basis.search(body)
    ]


# ══════════════════════════════════════════════════════════════════════════
# 2. Employee NDA whitelist
# ══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EmployeeNdaQuestion:
    question_id: str
    topic: str
    title: Callable[[EmployeeNdaModel], str]
    why: str
    #: 이 질문이 없으면 내릴 수 없는 법률판단.
    legal_judgment: str
    #: 연결되는 조항·쟁점.
    linked_issue: str
    #: 이 질문이 성립하는가(거래모델 기준). False 면 판단에 필요 없는 질문이다.
    needed: Callable[[EmployeeNdaModel, str], bool]
    #: 원문 또는 담당자 설명에 이미 답이 있는가.
    answered: Callable[[EmployeeNdaModel, str, str], bool]
    #: AI·정적 질문을 이 주제로 대응시키는 문형.
    topic_rx: re.Pattern[str] = field(default_factory=lambda: _rx(r"(?!x)x"))


def _affiliate_names(m: EmployeeNdaModel) -> str:
    """계약서가 쓰는 언어의 법인명으로 부른다(영문 계약이면 영문 명칭)."""
    from runtime.review.employee_nda_review import _english_name

    names = list(m.requested_affiliates) or list(m.named_affiliates_in_contract)
    if m.employee_label == "Employee":
        names = [_english_name(n) for n in names]
    return ", ".join(names) if names else "계열사"


_RX_ROLE_CREATIVE = _rx(r"engineer|developer|designer|R\s*&\s*D|research|scientist|개발|디자인|설계|연구")
_RX_USER_AFFILIATE_ACCESS = _rx(
    r"(?:양사|두\s*회사|계열사)[^.\n]{0,20}(?:업무|회계|정보)[^.\n]{0,20}(?:수행|담당|접근|처리)"
    r"|(?:shared|common)\s+services|both\s+(?:companies|entities)"
)
def _user_says_affiliate_access(m: EmployeeNdaModel, user: str) -> bool:
    """담당자 설명에 직원이 계열사 업무도 맡는다는 사실이 이미 있는가.

    "●담당업무: SIDIZ America 및 Fursys America 양사 회계·재무 업무" 처럼 업무를
    적은 한 줄에 우리 회사와 계열사가 함께 나오면 답이 있는 것이다.
    """
    if _RX_USER_AFFILIATE_ACCESS.search(user):
        return True
    names: list[str] = []
    try:
        from runtime.review.group_entities import resolve_entity

        for n in (m.our_company, *m.requested_affiliates):
            ent = resolve_entity(n)
            if ent is not None:
                names.append("|".join(re.escape(x) for x in ent.all_names()))
    except Exception:  # noqa: BLE001
        return False
    if len(names) < 2:
        return False
    for line in re.split(r"\n|●|•", str(user or "")):
        if _rx(r"업무|담당|duties|responsib|role").search(line) and all(re.search(p, line, re.IGNORECASE) for p in names):
            return True
    return False


_RX_USER_WORK_LOCATION = _rx(
    r"근무지|근무\s*(?:장소|지역)|(?:캘리포니아|California)[^.\n]{0,12}(?:근무|거주|사무소|office)|(?:works?|based|located|resides?)\s+in\s+[A-Z]"
)
_RX_CONTRACT_WORK_LOCATION = _rx(
    r"(?:work|perform\s+services|be\s+based|be\s+located)\s+(?:primarily\s+)?(?:in|at)\s+(?:the\s+Company['’]?s\s+)?[A-Z][a-z]+|근무\s*장소"
)

EMPLOYEE_NDA_QUESTIONS: tuple[EmployeeNdaQuestion, ...] = (
    EmployeeNdaQuestion(
        question_id="Q-ENDA-role-access",
        topic="role_access",
        title=lambda m: "이 직원의 직무와 실제로 접근하게 될 정보의 범위는 무엇인가요?",
        why="비밀정보 정의가 실제 접근 정보를 포괄하는지, 과도하게 넓어 집행력이 약해지는지는 직무와 접근 범위에 따라 달라집니다.",
        legal_judgment="비밀정보 정의의 적정성(과소·과대 정의)",
        linked_issue="비밀정보 정의 조항",
        needed=lambda m, t: True,
        answered=lambda m, t, u: bool(m.position) and len(m.information_types) >= 3,
        topic_rx=_rx(r"직무|담당\s*업무|접근\s*(?:하게\s*될|할)\s*정보의?\s*범위|업무\s*범위"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-affiliate-access",
        topic="affiliate",
        title=lambda m: (
            f"이 직원이 {m.employer_label or '회사'} 외에 {_affiliate_names(m)}의 정보에도 "
            "실제로 접근하나요? (공동 회계·ERP·급여 업무 등)"
        ),
        why=(
            "계열사 정보에 실제로 접근한다면 계약상 '회사'만 보호하는 구조로는 계열사가 직접 권리를 행사할 수 없고, "
            "업무상 계열사 담당자에게 정보를 전달하는 것조차 '회사 외부 제공'으로 금지될 수 있습니다. "
            "계열사 정의·제3자 수익자 조항·계열사 내부 공유 허용 문언의 필요 여부가 이 답에 달려 있습니다."
        ),
        legal_judgment="계열사 기밀정보 보호 가능 여부(당사자성·제3자 수익자·내부 공유 허용)",
        linked_issue="비밀정보 정의(계열사 정보) / 비공개 의무",
        needed=lambda m, t: bool(m.requested_affiliates) or bool(m.named_affiliates_in_contract),
        answered=lambda m, t, u: _user_says_affiliate_access(m, u),
        topic_rx=_rx(r"계열사|affiliat|양사|자회사|관계\s*회사|시디즈|SIDIZ"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-affiliate-scope-need",
        topic="affiliate_scope",
        title=lambda m: "계열사의 기밀정보도 이 계약의 보호대상에 포함할 필요가 있나요?",
        why="원문이 계열사 정보를 막연히 언급하지만 어느 계열사인지 특정하지 않아, 보호 범위와 권리행사 주체가 불명확합니다.",
        legal_judgment="계열사 정보 보호범위 특정 필요성",
        linked_issue="비밀정보 정의(계열사 정보)",
        needed=lambda m, t: m.contract_mentions_affiliates and not m.requested_affiliates and not m.named_affiliates_in_contract,
        answered=lambda m, t, u: False,
        topic_rx=_rx(r"(?!x)x"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-hr-personal-data",
        topic="hr_personal_data",
        title=lambda m: "이 직원이 HR·급여·재무 자료 등 다른 직원의 개인정보에 접근하나요?",
        why="직원 개인정보에 접근한다면 비밀유지 외에 접근통제·목적 외 이용 금지·보안의무·퇴직 시 삭제 의무를 명시해야 합니다.",
        legal_judgment="개인정보 보호 의무(접근통제·내부 목적 외 이용 금지·보안)의 필요 수준",
        linked_issue="비밀정보 정의(급여·인사) / 주의의무 / 반환·삭제",
        needed=lambda m, t: True,
        answered=lambda m, t, u: (
            "payroll_hr_personal" in m.information_types or m.personal_data_structure == PD_EMPLOYEE_INTERNAL
        ),
        topic_rx=_rx(r"개인정보|\bPII\b|CCPA|급여|payroll|인사\s*정보|HR"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-trade-secret-access",
        topic="trade_secret",
        title=lambda m: "이 직원이 고객정보·가격·원가·사업계획·기술자료 등 영업비밀에 해당하는 정보에 접근하나요?",
        why="영업비밀 접근 여부에 따라 영업비밀 보호조치(비밀 표시·접근 기록)와 DTSA 면책 고지의 실익이 달라집니다.",
        legal_judgment="영업비밀 보호 요건(합리적 비밀관리 노력) 충족 여부",
        linked_issue="비밀정보 정의 / 주의의무",
        needed=lambda m, t: True,
        answered=lambda m, t, u: len(set(m.information_types) & {
            "customer_vendor", "pricing_cost", "business_plan", "technical", "trade_secret",
        }) >= 2,
        topic_rx=_rx(r"영업\s*비밀|고객\s*정보|원가|사업\s*계획|기술\s*자료|trade\s+secret"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-ip-assignment",
        topic="ip",
        title=lambda m: "이 직원이 업무상 발명·저작물·개선사항을 만들게 되나요? 만든다면 회사 귀속 조항을 둘 계획인가요?",
        why="창작 업무가 있는데 귀속 조항이 없으면 성과물 권리가 직원에게 남을 수 있고, 캘리포니아에서는 Labor Code §2870 고지가 함께 필요합니다.",
        legal_judgment="업무 성과물·직무발명 귀속 조항의 필요성",
        linked_issue="(조항 없음) 지식재산 귀속",
        needed=lambda m, t: (not m.ip_assignment_present) and bool(_RX_ROLE_CREATIVE.search(m.position or "")),
        answered=lambda m, t, u: bool(_rx(r"발명|저작물|성과물|invention|work\s+product").search(u)),
        topic_rx=_rx(r"발명|지식\s*재산|저작권|성과물|invention|work\s+product|\bIP\b"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-post-employment",
        topic="post_employment",
        title=lambda m: "퇴직 후 경업금지·고객유인 금지·직원유인 금지 같은 제한을 둘 계획인가요?",
        why="관할에 따라 퇴직 후 제한의 효력이 크게 다릅니다(캘리포니아는 원칙적으로 무효). 계획이 있다면 관할별 허용 범위 안으로 좁혀야 합니다.",
        legal_judgment="퇴직 후 제한의 효력(관할별 강행규정)",
        linked_issue="존속기간 / 준거법",
        # 캘리포니아는 계획과 무관하게 무효라 답이 판단을 바꾸지 않는다.
        needed=lambda m, t: not m.is_california,
        answered=lambda m, t, u: (
            m.restraint_disclaimer_present or m.noncompete_present
            or m.customer_nonsolicit_present or m.employee_nonsolicit_present
        ),
        topic_rx=_rx(r"경업|비경쟁|non[- ]?compet|유인|solicit|전직\s*금지"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-noncompete-consideration",
        topic="noncompete_consideration",
        title=lambda m: "퇴직 후 경업금지에 대한 대가(보상금·수당)를 지급하나요? 지급한다면 금액과 지급 방식은 어떻게 되나요?",
        why=(
            "경업금지 약정의 유효성은 보호할 이익, 제한 기간·지역·대상 직종, 그리고 대가 지급 여부를 종합해 "
            "판단합니다(대법원 2009다82244 등). 대가가 없으면 약정 자체가 무효로 판단될 위험이 큽니다."
        ),
        legal_judgment="퇴직 후 경업금지 약정의 유효성",
        linked_issue="경업금지 조항",
        needed=lambda m, t: m.noncompete_present and not m.is_california,
        answered=lambda m, t, u: bool(
            _rx(r"경업[^.\n]{0,40}(?:대가|보상|수당)|(?:대가|보상|수당)[^.\n]{0,40}경업|non[- ]?compet[^.]{0,80}(?:compensat|consideration|pay)").search(t + "\n" + u)
        ),
        topic_rx=_rx(r"경업[^.?\n]{0,20}(?:대가|보상)|non[- ]?compet[^.?]{0,30}compensat"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-return-deletion",
        topic="return_deletion",
        title=lambda m: "퇴직 시 회사 자료의 반환·개인 기기 내 사본 삭제를 어떻게 확인할 계획인가요?",
        why="반환·삭제 조항이 없으면 퇴직자가 보유한 사본에 대한 청구 근거가 약해집니다.",
        legal_judgment="퇴직 시 자료 반환·삭제 의무의 필요성",
        linked_issue="(조항 없음) 반환·삭제",
        needed=lambda m, t: not m.return_deletion_present,
        answered=lambda m, t, u: bool(_rx(r"반환|삭제|파기|return|delete").search(u)),
        topic_rx=_rx(r"반환|삭제|파기|return|delete|destroy"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-work-location",
        topic="work_location",
        title=lambda m: (
            f"이 직원의 실제 근무지(주·국가)는 어디인가요? (준거법: {m.governing_law or '미기재'})"
        ),
        why=(
            "고용법상 강행규정은 준거법 조항이 아니라 근무지 기준으로 적용됩니다. 캘리포니아 근무자라면 "
            "Labor Code §925·B&P Code §16600이 계약 선택과 무관하게 적용되고, 다른 주 근무자라면 그 주의 "
            "비밀유지·내부고발 보호 규정을 추가로 확인해야 합니다."
        ),
        legal_judgment="적용되는 고용법(강행규정)의 확정 — 준거법·법정 공개 예외 적정성",
        linked_issue="준거법 / 법정 공개 예외",
        # 주(州)마다 고용법이 다른 미국, 또는 준거법이 없는 계약에서만 판단을 바꾼다.
        needed=lambda m, t: (not m.jurisdiction_key) or m.jurisdiction_key.startswith("us"),
        answered=lambda m, t, u: bool(_RX_USER_WORK_LOCATION.search(u) or _RX_CONTRACT_WORK_LOCATION.search(t)),
        topic_rx=_rx(r"근무지|근무\s*(?:장소|지역)|캘리포니아|California|주법|노동법|고용법|준거법|관할|governing|해외\s*거래|overseas"),
    ),
    EmployeeNdaQuestion(
        question_id="Q-ENDA-lawful-disclosure",
        topic="lawful_disclosure",
        title=lambda m: "이 직원의 근무지 관할에서 요구하는 내부고발·정부신고 예외 문언을 확인할 수 있도록 근무지를 알려 주시겠어요?",
        why="법정 공개 예외가 빠진 비밀유지 서약은 관할에 따라 그 부분이 무효이거나 사용자에게 제재가 따릅니다.",
        legal_judgment="법정 공개 예외(내부고발·정부신고·영업비밀 면책 고지)의 적정성",
        linked_issue="(조항 없음) 법정 공개 예외",
        # 예외 문언이 이미 있거나 관할이 확정되면 법률판단의 문제이지 사실확인 질문이 아니다.
        needed=lambda m, t: not m.carve_outs and not m.governing_law,
        answered=lambda m, t, u: bool(_RX_USER_WORK_LOCATION.search(u)),
        topic_rx=_rx(r"내부\s*고발|whistle|정부\s*(?:기관|신고)|carve[- ]?out|DTSA|Defend\s+Trade"),
    ),
)

_WHITELIST_IDS = frozenset(q.question_id for q in EMPLOYEE_NDA_QUESTIONS)


def _topic_of(question: Any) -> str:
    blob = _q_text(question)
    for eq in EMPLOYEE_NDA_QUESTIONS:
        if eq.topic_rx.search(blob):
            return eq.topic
    return ""


def _to_question(eq: EmployeeNdaQuestion, model: EmployeeNdaModel) -> Question:
    return Question(
        question_id=eq.question_id,
        title=eq.title(model),
        description=f"{eq.why} (판단 대상: {eq.legal_judgment} · 연결: {eq.linked_issue})",
        answer_type="text",
        required=eq.topic in ("affiliate", "work_location"),
        options=[],
        tags=[
            f"topic:employee_nda_{eq.topic}",
            "source:employee_nda_whitelist",
            f"legal_judgment:{eq.legal_judgment}",
        ],
        related_rule_ids=[],
    )


def build_employee_nda_questions(
    *, model: EmployeeNdaModel, contract_text: str, answered_topics: str = "",
) -> tuple[list[Question], list[dict[str, Any]], dict[str, str]]:
    """whitelist 질문 중 **판단에 필요하고 아직 답이 없는** 것만 만든다.

    반환: (질문, 제외 기록, 주제별 상태 {topic: "open"|"answered"|"not_needed"})
    """
    body = str(contract_text or "")
    user = str(answered_topics or "")
    out: list[Question] = []
    log: list[dict[str, Any]] = []
    state: dict[str, str] = {}
    for eq in EMPLOYEE_NDA_QUESTIONS:
        if not eq.needed(model, body):
            state[eq.topic] = "not_needed"
            continue
        if eq.answered(model, body, user):
            state[eq.topic] = "answered"
            log.append({
                "question_id": eq.question_id,
                "code": QUESTION_REJECTED_ALREADY_ANSWERED,
                "reason": f"원문 또는 담당자 설명에 이미 답이 있습니다 — {eq.legal_judgment}",
            })
            continue
        state[eq.topic] = "open"
        out.append(_to_question(eq, model))
    return out, log, state


# ══════════════════════════════════════════════════════════════════════════
# 3. 정책 적용
# ══════════════════════════════════════════════════════════════════════════

def apply_nda_question_policy(
    questions: list[Question],
    *,
    model: EmployeeNdaModel | None,
    contract_text: str,
    contract_type_code: str = "",
    answered_topics: str = "",
    max_questions: int = 7,
) -> dict[str, Any]:
    """비밀유지 계열 계약의 사전질문을 최종 확정한다.

    - 모든 비밀유지 계열: 원문 근거 없는 사업거래 질문(오염 축) 제거.
    - confident 한 직원 비밀유지계약: whitelist 로 교체, 개인정보 구조 반영.
    """
    code = str(contract_type_code or "").strip()
    is_nda = code in NDA_TYPE_CODES or bool(model and model.is_employee_nda)
    rejected: list[dict[str, Any]] = []
    if not is_nda:
        return {"questions": list(questions), "rejected": rejected, "applied": False}

    body = str(contract_text or "")
    employee_mode = bool(model and model.is_employee_nda and model.confident)

    kept: list[Question] = []
    for q in questions:
        axes = contamination_axes_for(q, body)
        if axes:
            rejected.append({
                "question_id": q.question_id, "title": q.title,
                "code": QUESTION_REJECTED_OUT_OF_SCOPE,
                "reason": "원문에 직접 근거가 없는 다른 거래유형의 질문: " + ", ".join(axes),
            })
            continue
        kept.append(q)

    if not employee_mode:
        return {"questions": kept[:max_questions], "rejected": rejected, "applied": True, "employee_mode": False}

    assert model is not None
    wl, wl_log, topic_state = build_employee_nda_questions(
        model=model, contract_text=body, answered_topics=answered_topics,
    )
    rejected.extend(wl_log)
    wl_ids = {q.question_id for q in wl}

    novel: list[Question] = []
    for q in kept:
        if q.question_id in wl_ids:
            continue
        if model.personal_data_internal and _RX_PROCESSOR_QUESTION.search(_q_text(q)):
            rejected.append({
                "question_id": q.question_id, "title": q.title,
                "code": QUESTION_REJECTED_PD_STRUCTURE_SETTLED,
                "reason": "개인정보 취급 구조가 내부 직원 접근으로 확정되어 처리위탁·제3자 제공 질문은 성립하지 않습니다.",
            })
            continue
        if not q.question_id.startswith("Q-AI-"):
            # 계약유형 템플릿·법률효과 질문은 whitelist 밖이면 비활성화한다.
            rejected.append({
                "question_id": q.question_id, "title": q.title,
                "code": QUESTION_REJECTED_OUT_OF_SCOPE,
                "reason": "임직원 비밀유지계약 whitelist 밖의 질문 템플릿입니다.",
            })
            continue
        topic = _topic_of(q)
        if topic:
            st = topic_state.get(topic, "")
            code_ = QUESTION_REJECTED_DUPLICATE if st == "open" else QUESTION_REJECTED_ALREADY_ANSWERED
            rejected.append({
                "question_id": q.question_id, "title": q.title, "code": code_,
                "reason": (
                    f"같은 쟁점({topic})의 whitelist 질문이 이미 나갑니다." if st == "open"
                    else f"쟁점({topic})은 원문·담당자 설명으로 이미 확정되었거나 판단에 필요하지 않습니다."
                ),
            })
            continue
        if len(novel) >= MAX_NOVEL_AI_QUESTIONS:
            rejected.append({
                "question_id": q.question_id, "title": q.title,
                "code": QUESTION_REJECTED_OUT_OF_SCOPE,
                "reason": "원문에서 새로 발견된 쟁점 질문은 1건까지만 허용합니다(질문 최소화).",
            })
            continue
        novel.append(q)

    final = (wl + novel)[:max_questions]
    return {
        "questions": final,
        "rejected": rejected,
        "applied": True,
        "employee_mode": True,
        "topic_state": topic_state,
    }


def check_question_contamination(
    questions: list[Any] | None,
    *,
    contract_text: str,
    contract_type_code: str,
    employee_nda: bool = False,
) -> dict[str, Any]:
    """담당자에게 **실제로 나간** 질문의 오염 여부(hard gate).

    생성 단계에서 제거에 성공하면 여기서 걸릴 것이 없다. 걸렸다면 생성 이후
    (AI 문장 다듬기 등) 다른 경로가 오염된 질문을 다시 넣은 것이다.
    """
    code = str(contract_type_code or "").strip()
    if not questions or (code not in NDA_TYPE_CODES and not employee_nda):
        return {"checked": 0, "contaminated": [], "status": ""}
    bad: list[dict[str, Any]] = []
    for q in questions:
        axes = contamination_axes_for(q, contract_text)
        if axes:
            bad.append({"question_id": _q_id(q), "axes": axes})
    return {
        "checked": len(questions),
        "contaminated": bad,
        "status": REVIEW_FAILED_QUESTION_CROSS_CONTRACT_CONTAMINATION if bad else "",
        "detail": (
            "원문 근거 없이 다른 거래유형의 사전질문이 나갔습니다: "
            + ", ".join(f"{b['question_id']}({'/'.join(b['axes'])})" for b in bad[:5])
        ) if bad else "",
    }


def filter_question_dicts(
    items: list[dict[str, Any]],
    *,
    contract_text: str,
    contract_type_code: str,
    model: EmployeeNdaModel | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """직렬화된 질문(dict)에 같은 오염·개인정보 구조 게이트를 다시 건다.

    AI 가 질문 문장을 다듬은 뒤(`polish_questions`)에도 게이트가 유지되어야 한다 —
    거래모델이 확정된 뒤 다른 단계가 그 판단을 뒤집지 못하게 하기 위함이다.
    """
    code = str(contract_type_code or "").strip()
    is_nda = code in NDA_TYPE_CODES or bool(model and model.is_employee_nda)
    if not is_nda:
        return list(items), []
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    internal = bool(model and model.confident and model.personal_data_internal)
    for it in items or []:
        if not isinstance(it, dict):
            continue
        axes = contamination_axes_for(it, contract_text)
        if axes:
            rejected.append({"question_id": _q_id(it), "code": QUESTION_REJECTED_OUT_OF_SCOPE, "axes": axes})
            continue
        if internal and _RX_PROCESSOR_QUESTION.search(_q_text(it)):
            rejected.append({"question_id": _q_id(it), "code": QUESTION_REJECTED_PD_STRUCTURE_SETTLED})
            continue
        kept.append(it)
    return kept, rejected


__all__ = [
    "CONTAMINATION_AXES",
    "EMPLOYEE_NDA_QUESTIONS",
    "INFO_TYPE_LABELS",
    "QUESTION_REJECTED_ALREADY_ANSWERED",
    "QUESTION_REJECTED_DUPLICATE",
    "QUESTION_REJECTED_OUT_OF_SCOPE",
    "QUESTION_REJECTED_PD_STRUCTURE_SETTLED",
    "REVIEW_FAILED_QUESTION_CROSS_CONTRACT_CONTAMINATION",
    "apply_nda_question_policy",
    "build_employee_nda_questions",
    "check_question_contamination",
    "contamination_axes_for",
    "filter_question_dicts",
]
