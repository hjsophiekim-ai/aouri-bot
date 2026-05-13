"""Strategic Inquiry — requirement.md > Strategic Inquiry + EMERGENCY PATCH 1/3/4/5
계약 유형별 쟁점 기반 계층형 추가 질문을 생성한다.
- PATCH 1: Ops 질문 Hard-Block (비-ops 계약)
- PATCH 3: 물품/제조물공급 13개 질문 엔진
- PATCH 4: 사용자 이슈 우선순위 오버라이드
- PATCH 5: 질문 유효성 검증 게이트
- CRITICAL FIX: Supplier-Side Product Contract 질문 엔진 (우리 회사 = 공급자)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategicQuestion:
    question_id: str
    priority: int
    title: str
    body: str
    blocks_next_stage: bool
    related_risk_codes: list[str] = field(default_factory=list)


# =============================================================================
# [EMERGENCY PATCH 1] Ops-Block 계약 유형 목록
# 이 유형들은 ops 질문(업무범위/KPI/인력배치 등) 생성을 완전 차단한다.
# =============================================================================
_OPS_BLOCK_TYPES = frozenset({
    "물품공급", "제조물공급", "납품", "구매", "설치포함공급", "판매", "B2B공급",
    "project_installation", "general", "construction", "rental",
})

# Ops 질문을 탐지하는 키워드 (이 키워드가 포함된 질문은 비-ops 계약에서 제거)
_OPS_CONTAMINATION_KW = re.compile(
    r"업무\s*범위|KPI|운영\s*보고|검수\s*절차|인력\s*배치|인수인계|운영\s*현장"
    r"|상시\s*운영|위탁\s*운영|운영\s*대행|고객\s*응대\s*인력|운영\s*센터",
    re.IGNORECASE,
)

# Ops 계약으로 확정하려면 아래 모두 필요 (7개 조건)
_OPS_REQUIRED_KW = re.compile(
    r"상시\s*운영\s*인력|KPI|SLA|운영\s*센터|지속적\s*운영|고객\s*응대|시설\s*운영",
    re.IGNORECASE,
)


# =============================================================================
# [PATCH 3] 물품/제조물공급 계약 전용 13개 질문
# =============================================================================
_PRODUCT_SUPPLY_QUESTIONS: list[StrategicQuestion] = [
    StrategicQuestion(
        "PS-001", 1, "물품 검수 기준",
        "물품 검수 기준(합격 판정 기준, 검수 주체, 검수 기간)이 계약서에 명확히 규정되어 있는가?",
        True, ["pi_commissioning_accident_liability"],
    ),
    StrategicQuestion(
        "PS-002", 2, "하자 처리 절차",
        "하자 발생 시 보수/교체/반품 절차 및 기한(SLA)이 명시되어 있는가?",
        True, ["pi_sla"],
    ),
    StrategicQuestion(
        "PS-003", 3, "납기 지연 지체상금",
        "납기 지연 시 지체상금 상한(캡) 및 면책 사유(불가항력, 발주자 귀책)가 설정되어 있는가?",
        True, ["SC-DL-001"],
    ),
    StrategicQuestion(
        "PS-004", 4, "검수 전 위험 부담",
        "검수 완료 전 물품 손상·멸실에 대한 위험 부담 주체는 누구인가?",
        True, ["pi_commissioning_accident_liability"],
    ),
    StrategicQuestion(
        "PS-005", 5, "제조물 결함 책임",
        "제조물 결함으로 인한 손해에 대한 책임 귀속(공급자 vs. 사용자 부주의)이 계약서에 명시되어 있는가?",
        True, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "PS-006", 6, "PL보험 가입",
        "제조물 책임보험(PL보험) 가입 여부 및 보상 한도는?",
        False, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "PS-007", 7, "안전 인증",
        "안전 인증(KC, CE, UL 등) 획득 여부 및 인증서 제출 의무가 계약서에 포함되어 있는가?",
        False, ["pi_legal_compliance"],
    ),
    StrategicQuestion(
        "PS-008", 8, "사용자 매뉴얼",
        "사용자 매뉴얼(한국어 포함) 및 경고 표시 제공 의무가 계약서에 명시되어 있는가?",
        False, ["SC-PL-002", "pi_ops_manual"],
    ),
    StrategicQuestion(
        "PS-009", 9, "리콜 절차",
        "결함 발견 시 리콜 처리 절차 및 비용 부담 주체가 계약서에 명시되어 있는가?",
        False, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "PS-010", 10, "하자담보/PL 분리",
        "하자담보책임(민법 제580조)과 제조물 책임(제조물책임법 제3조)을 분리하여 각각의 기간·범위를 별도로 규정하였는가?",
        True, ["SC-PL-001", "SC-PL-002"],
    ),
    StrategicQuestion(
        "PS-011", 11, "하도급 안전 연대책임",
        "설치 협력업체(하도급) 안전 연대책임 구조가 계약서에 포함되어 있는가?",
        False, ["pi_subcontractor_safety"],
    ),
    StrategicQuestion(
        "PS-012", 12, "손해배상 한도",
        "손해배상 한도(총액 상한) 및 간접손해 배제 조항이 설정되어 있는가?",
        False, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "PS-013", 13, "계약 종료 후 잔존 책임",
        "계약 종료 후에도 잔존하는 책임(PL 책임, 비밀유지, 개인정보 처리)의 기간과 범위가 명시되어 있는가?",
        False, ["SC-PL-001"],
    ),
]

# project_installation 전용 10개 우선 질문 (설치형 제조물)
_PI_QUESTIONS: list[StrategicQuestion] = [
    StrategicQuestion(
        "IQ-PI-001", 1, "설치 주체",
        "설치 주체는 누구인가? (당사 직영 설치 / 협력업체 하도급 설치)",
        True, ["pi_safety_responsibility", "pi_subcontractor_safety"],
    ),
    StrategicQuestion(
        "IQ-PI-002", 2, "설치 협력업체",
        "설치 협력업체(하도급)가 있는가? 있다면 안전 연대책임 구조는?",
        True, ["pi_subcontractor_safety"],
    ),
    StrategicQuestion(
        "IQ-PI-003", 3, "사고 유형",
        "사용 중 예상 가능한 사고 유형은? (끼임/낙하/전기/화재/폭발 등)",
        True, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "IQ-PI-004", 4, "안전 인증",
        "안전 인증 완료 여부? (KC, CE, UL 등 해당 인증을 획득하였는가?)",
        False, ["pi_legal_compliance"],
    ),
    StrategicQuestion(
        "IQ-PI-005", 5, "사용자 매뉴얼",
        "사용자 매뉴얼(한국어 포함) 제공 여부? 경고 표시 포함 여부?",
        False, ["SC-PL-002", "pi_ops_manual"],
    ),
    StrategicQuestion(
        "IQ-PI-006", 6, "PL보험",
        "제조물 책임보험(PL보험) 가입 여부 및 보상 한도는?",
        False, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "IQ-PI-007", 7, "리콜 절차",
        "결함 발견 시 리콜 발생 처리 절차가 계약에 명시되어 있는가?",
        False, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "IQ-PI-008", 8, "하자 SLA",
        "하자 발생 시 응답 시간·복구 목표 시간(SLA)이 존재하는가?",
        False, ["pi_sla"],
    ),
    StrategicQuestion(
        "IQ-PI-009", 9, "설치 완료 기준",
        "설치 완료 판정 기준(시운전 합격 기준 등)이 계약서에 명확히 정의되어 있는가?",
        False, ["pi_commissioning_accident_liability"],
    ),
    StrategicQuestion(
        "IQ-PI-010", 10, "위험 부담",
        "검수 완료 전 물품 손상·멸실에 대한 위험 부담 주체는 누구인가?",
        True, ["pi_commissioning_accident_liability"],
    ),
]

# 제조물 책임법(PL) 이슈 계층형 3단계 질문
_PL_QUESTIONS: list[StrategicQuestion] = [
    StrategicQuestion(
        "IQ-PL-001", 1, "PL 입증 책임",
        "제조물 결함에 대한 입증 책임을 공급자가 전적으로 부담할 것인가, "
        "아니면 사용자의 부주의를 적극 반영하여 책임을 분담할 것인가?",
        True, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "IQ-PL-002", 2, "배상 범위",
        "간접 손해 및 확대 손해에 대한 배상 한도를 설정할 것인가? "
        "설정 시 한도액(예: 계약금액의 몇 %)은?",
        True, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "IQ-PL-003", 3, "품질보증 분리",
        "하자담보책임(민법)과 제조물 책임(PL법)을 분리하여 각 책임의 기간·범위를 별도로 규정할 것인가?",
        True, ["SC-PL-001", "SC-PL-002"],
    ),
]


# =============================================================================
# [PATCH 4] 사용자 이슈 우선순위 오버라이드 — User Issue Priority Override
# review_focus에 특정 법령·이슈 키워드 감지 시 관련 질문 자동 주입
# =============================================================================
_USER_ISSUE_OVERRIDES: list[dict[str, Any]] = [
    {
        "triggers": re.compile(r"제조물책임법|PL법|제조물\s*책임|PL\s*보험", re.IGNORECASE),
        "questions": [
            StrategicQuestion("OV-PL-001", 0, "PL 결함 책임 귀속",
                "제조물 결함으로 인한 손해에 대한 책임 귀속이 명시되어 있는가? (공급자 vs. 사용자 과실 분담)",
                True, ["SC-PL-001"]),
            StrategicQuestion("OV-PL-002", 0, "PL 보험 및 한도",
                "PL보험 가입 의무 및 보상 한도가 계약서에 명시되어 있는가?",
                False, ["SC-PL-001"]),
            StrategicQuestion("OV-PL-003", 0, "하자담보/PL 분리",
                "하자담보책임(민법)과 PL책임(제조물책임법)을 별도 조항으로 분리하여 각 기간·범위를 규정하였는가?",
                True, ["SC-PL-001", "SC-PL-002"]),
        ],
    },
    {
        "triggers": re.compile(r"중대재해처벌법|중대재해|중대\s*산업사고", re.IGNORECASE),
        "questions": [
            StrategicQuestion("OV-MHD-001", 0, "안전 책임 주체",
                "시공·설치 전 과정에서 안전 책임 주체(도급인/수급인)가 계약서에 명확히 지정되어 있는가?",
                True, ["pi_safety_responsibility"]),
            StrategicQuestion("OV-MHD-002", 0, "안전관리자 지정",
                "현장 안전관리자가 지정되어 있으며, 교체 시 통보 의무가 포함되어 있는가?",
                False, ["pi_safety_responsibility"]),
            StrategicQuestion("OV-MHD-003", 0, "위험성 평가",
                "착공 전 위험성 평가(산업안전보건법 제36조)를 실시하고 결과를 상대방에게 제출하는 절차가 있는가?",
                True, ["pi_legal_compliance"]),
        ],
    },
    {
        "triggers": re.compile(r"개인정보보호법|개인정보|개인\s*정보\s*보호", re.IGNORECASE),
        "questions": [
            StrategicQuestion("OV-PI-001", 0, "처리 목적·범위",
                "개인정보 처리 목적과 범위가 계약서에 명확히 특정되어 있는가?",
                True, ["pi_legal_compliance"]),
            StrategicQuestion("OV-PI-002", 0, "수탁자 관리감독",
                "개인정보 수탁자에 대한 관리·감독 의무(개인정보보호법 제26조)가 명시되어 있는가?",
                False, ["pi_legal_compliance"]),
            StrategicQuestion("OV-PI-003", 0, "유출 시 구상권",
                "수탁자 귀책 유출 시 무제한 구상권이 계약서에 보장되어 있는가?",
                True, ["pi_legal_compliance"]),
        ],
    },
    {
        "triggers": re.compile(r"하도급법|하도급|하수급인", re.IGNORECASE),
        "questions": [
            StrategicQuestion("OV-SUB-001", 0, "하도급 대금 지급",
                "하도급 대금 지급 기준 및 지급 기간이 하도급법에 부합하는가?",
                True, ["pi_subcontractor_safety"]),
            StrategicQuestion("OV-SUB-002", 0, "기술 유용 금지",
                "원사업자의 기술 유용(하도급법 제12조의3) 방지 조항이 포함되어 있는가?",
                False, ["SC-IP-001"]),
            StrategicQuestion("OV-SUB-003", 0, "원사업자 책임",
                "하수급인 안전사고 발생 시 원사업자 연대책임 구조가 명시되어 있는가?",
                True, ["pi_subcontractor_safety"]),
        ],
    },
    {
        "triggers": re.compile(r"지식재산권|지재권|IP\b|저작권|특허", re.IGNORECASE),
        "questions": [
            StrategicQuestion("OV-IP-001", 0, "IP 귀속 조항",
                "결과물·개발물의 지식재산권 귀속 주체가 계약서에 명확히 규정되어 있는가?",
                True, ["SC-IP-001"]),
            StrategicQuestion("OV-IP-002", 0, "제3자 침해 보증",
                "공급자/수탁자가 제3자 IP를 침해하지 않음을 보증하며, 침해 시 면책·배상 의무가 포함되어 있는가?",
                False, ["SC-IP-001"]),
            StrategicQuestion("OV-IP-003", 0, "결과물 사용 범위",
                "계약 종료 후 결과물·산출물의 사용 범위 및 수탁자 재사용 제한이 명시되어 있는가?",
                False, ["SC-IP-001"]),
        ],
    },
]


# =============================================================================
# [PATCH 5] 질문 유효성 검증 게이트
# =============================================================================

_OPS_KW_IN_QUESTION = re.compile(
    r"업무\s*범위|KPI|운영\s*보고|검수\s*절차|인력\s*배치|인수인계|운영\s*현장"
    r"|상시\s*운영|위탁\s*운영|운영\s*대행|고객\s*응대\s*인력|운영\s*센터|운영\s*SLA",
    re.IGNORECASE,
)

# =============================================================================
# [CRITICAL FIX] Supplier-Side Product Contract 질문 엔진
# requirement.md > [NEW QUESTION ENGINE] Supplier-Side Product Contract
# 우리 회사 = 공급자인 물품공급계약 전용 8개 질문
# =============================================================================
_SUPPLIER_PRODUCT_QUESTIONS: list[StrategicQuestion] = [
    StrategicQuestion(
        "SUPPQ-001", 1, "주문제작 여부",
        "주문제작 제품인가? (주문제작 제품은 취소·반품 제한 조항이 필수이며, 취소 시 기발생 비용 구매자 부담 조항이 필요하다)",
        True, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "SUPPQ-002", 2, "설치 포함 여부",
        "설치가 포함되는가? (설치 포함 시 설치 완료 기준·검수 간주·위험이전 시점·설치환경 요건 미충족 시 면책 조항이 필요하다)",
        True, ["pi_safety_responsibility"],
    ),
    StrategicQuestion(
        "SUPPQ-003", 3, "검수 기준과 검수 기간",
        "검수 기준과 검수 기간이 있는가? (검수 기간 내 이의 없으면 검수 완료 간주 조항으로 무기한 클레임을 차단할 수 있다)",
        True, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "SUPPQ-004", 4, "하자 통지기간",
        "하자 통지기간이 있는가? (발견일로부터 7일 이내 서면 통지 의무 + 해태 시 클레임 제한 조항으로 공급자를 보호할 수 있다)",
        True, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "SUPPQ-005", 5, "반품 제한 필요성",
        "반품 제한이 필요한가? (주문제작·설치완료 제품의 반품 불가 조항과 반품 요건을 명시하여 일방적 반품 요구를 차단할 수 있다)",
        False, ["SC-PL-001"],
    ),
    StrategicQuestion(
        "SUPPQ-006", 6, "고객 제공 사양/도면",
        "고객이 제공하는 사양/도면이 있는가? (고객 제공 사양·도면에 기인한 결함·손해는 공급자 책임에서 제외하는 조항이 필요하다)",
        False, ["SC-PL-002"],
    ),
    StrategicQuestion(
        "SUPPQ-007", 7, "오사용·설치환경 리스크",
        "사용자 오사용 또는 설치환경 리스크가 있는가? (오사용·보관불량·임의개조·설치환경 부적합으로 인한 사고를 공급자 책임에서 제외하는 면책 조항이 필요하다)",
        False, ["SC-PL-001", "SC-PL-002"],
    ),
]

# 공급자 물품공급 계약에서 생성 금지 질문 패턴
_SUPPLIER_OPS_BLOCK_KW = re.compile(
    r"운영\s*범위|KPI|운영\s*인력|인수인계|운영\s*위탁|운영\s*대행"
    r"|상시\s*운영|위탁\s*운영|고객\s*응대\s*인력|운영\s*센터",
    re.IGNORECASE,
)


_FALLBACK_QUESTIONS: list[StrategicQuestion] = [
    StrategicQuestion("FB-001", 99, "손해배상 한도",
        "손해배상 한도(총액 상한) 및 간접손해 배제 조항이 설정되어 있는가?",
        False, []),
    StrategicQuestion("FB-002", 100, "해지 절차",
        "계약 해지 요건 및 절차(사전 통보 기간, 시정 기회)가 명시되어 있는가?",
        False, []),
    StrategicQuestion("FB-003", 101, "분쟁 해결",
        "분쟁 발생 시 협의 방법, 관할 법원, 준거법이 명시되어 있는가?",
        False, []),
]


def _validate_questions(
    questions: list[dict[str, Any]],
    contract_class: str,
    contract_nature: str,
    our_role: str | None = None,
) -> list[dict[str, Any]]:
    """[PATCH 5] 반환 전 유효성 검증.
    1. 비-ops 계약에서 ops 키워드 질문 제거
    2. 공급자 물품공급 계약에서 운영/KPI/인수인계 질문 추가 차단
    3. 빈 목록 fallback
    4. 중복 question_id 제거
    """
    is_non_ops = contract_class in _OPS_BLOCK_TYPES or contract_class == "general" or contract_class == "advisory"
    _our_role = str(our_role or "").lower()
    _is_supplier = _our_role in ("supplier", "seller", "rental_provider", "contractor")
    is_product_supply_context = (
        contract_nature == "제조물공급"
        or any(k in (contract_nature or "") for k in ("물품공급", "납품", "구매", "설치포함공급", "판매", "B2B공급"))
    )

    seen_ids: set[str] = set()
    cleaned: list[dict[str, Any]] = []

    for q in questions:
        qid = str(q.get("question_id") or "")
        # 중복 제거
        if qid and qid in seen_ids:
            continue
        if qid:
            seen_ids.add(qid)
        body = str(q.get("body") or "")
        title = str(q.get("title") or "")
        combined_text = body + " " + title
        # 비-ops 계약에서 ops 오염 질문 제거
        if is_non_ops:
            if _OPS_KW_IN_QUESTION.search(combined_text):
                continue
        # [CRITICAL FIX] 공급자 물품공급 계약에서 ops 관련 질문 추가 차단
        if _is_supplier and is_product_supply_context:
            if _SUPPLIER_OPS_BLOCK_KW.search(combined_text):
                continue
        cleaned.append(q)

    # 빈 목록 fallback
    if not cleaned:
        cleaned = [
            {
                "question_id": q.question_id,
                "priority": q.priority,
                "title": q.title,
                "body": q.body,
                "blocks_next_stage": q.blocks_next_stage,
                "related_risk_codes": q.related_risk_codes,
            }
            for q in _FALLBACK_QUESTIONS
        ]

    return cleaned


def _questions_to_dicts(questions: list[StrategicQuestion]) -> list[dict[str, Any]]:
    return [
        {
            "question_id": q.question_id,
            "priority": q.priority,
            "title": q.title,
            "body": q.body,
            "blocks_next_stage": q.blocks_next_stage,
            "related_risk_codes": q.related_risk_codes,
        }
        for q in sorted(questions, key=lambda x: x.priority)
    ]


def generate_strategic_inquiry(
    contract_class: str,
    contract_nature: str,
    existing_answers: dict[str, Any] | None,
    user_focus: str | None,
    our_role: str | None = None,
) -> list[dict[str, Any]]:
    """requirement.md > Strategic Inquiry + EMERGENCY PATCH 1/3/4/5 + CRITICAL FIX.

    - 계약 유형에 맞는 전략적 질문만 생성한다.
    - [PATCH 1] 비-ops 계약에서 ops 질문 Hard-Block.
    - [PATCH 3] 물품/제조물공급 계약 13개 질문 전용 엔진.
    - [PATCH 4] 사용자 이슈 키워드 감지 시 관련 질문 자동 주입.
    - [PATCH 5] 반환 전 유효성 검증 게이트.
    - [CRITICAL FIX] 우리 회사 = 공급자인 경우 Supplier-Side 질문 우선 라우팅.
    """
    answers = existing_answers or {}
    focus = str(user_focus or "")
    answered_ids = {str(k) for k in answers.keys()}
    _our_role = str(our_role or "").lower()
    _is_supplier = _our_role in ("supplier", "seller", "rental_provider", "contractor")

    selected: list[StrategicQuestion] = []

    # ── [PATCH 4] 사용자 이슈 우선순위 오버라이드 ──────────────────────────────
    override_qs: list[StrategicQuestion] = []
    for override in _USER_ISSUE_OVERRIDES:
        if override["triggers"].search(focus):
            override_qs.extend(override["questions"])
    # 우선순위 0으로 앞에 삽입 (중복 question_id 제외)
    seen_override: set[str] = set()
    deduped_override: list[StrategicQuestion] = []
    for q in override_qs:
        if q.question_id not in seen_override:
            seen_override.add(q.question_id)
            deduped_override.append(q)
    selected.extend(deduped_override)

    # ── 계약 유형별 질문 선택 ───────────────────────────────────────────────────
    is_pl_focused = any(k in focus for k in ("제조물", "pl", "pl법", "제품 책임", "책임법"))
    is_product_supply = (
        contract_class == "project_installation"
        or contract_nature == "제조물공급"
        or any(k in (contract_nature or "") for k in ("물품공급", "납품", "구매", "설치포함공급", "판매", "B2B공급"))
    )

    if is_product_supply:
        if _is_supplier and contract_class != "project_installation":
            # [CRITICAL FIX] 우리 회사 = 공급자 + 물품공급 → Supplier-Side 8개 질문 우선
            selected.extend(_SUPPLIER_PRODUCT_QUESTIONS)
            if is_pl_focused:
                selected.extend(_PL_QUESTIONS)
        elif contract_class == "project_installation":
            # [PATCH 3] project_installation은 PI 질문 + PS 질문 병합
            selected.extend(_PI_QUESTIONS)
            if is_pl_focused:
                selected.extend(_PL_QUESTIONS)
            # PS 질문 중 PI와 겹치지 않는 것 추가
            pi_ids = {q.question_id for q in _PI_QUESTIONS}
            for q in _PRODUCT_SUPPLY_QUESTIONS:
                if q.question_id not in pi_ids:
                    selected.append(q)
        else:
            # [PATCH 3] 구매자 측: 물품/제조물공급 전용 13개 질문
            selected.extend(_PRODUCT_SUPPLY_QUESTIONS)
            if is_pl_focused:
                selected.extend(_PL_QUESTIONS)
    elif contract_class == "advisory":
        # advisory 계약 전용 질문은 별도 questions/ 모듈에서 처리
        pass
    # ops_outsourcing은 별도 모듈 처리 (여기서는 생성 안 함)

    # 이미 답변된 질문 제거
    filtered = [q for q in selected if q.question_id not in answered_ids]

    # 우선순위 순 정렬 (override 질문은 priority=0이므로 최상단)
    result_dicts = _questions_to_dicts(filtered)

    # ── [PATCH 5] 유효성 검증 게이트 ───────────────────────────────────────────
    result_dicts = _validate_questions(result_dicts, contract_class, contract_nature, our_role=our_role)

    # ── [NEW SYSTEM] Senior Counsel Question Engine — 최대 5개 제한 ─────────────
    # 실제 책임 귀속·손실에 영향을 주는 질문만 남기고 나머지 제거
    # blocks_next_stage=True 질문 우선 유지, 이후 priority 순 최대 5개
    blocking = [q for q in result_dicts if q.get("blocks_next_stage")]
    non_blocking = [q for q in result_dicts if not q.get("blocks_next_stage")]
    result_dicts = (blocking + non_blocking)[:5]

    return result_dicts
