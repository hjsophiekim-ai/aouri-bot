"""사전 질문의 **적용 범위** 게이트 — canned question 이 엉뚱한 계약에 붙는 것을 막는다.

2026-09-10 아키텍처 지시 항목 4 — "사용자가 직접 입력하지 않은 질문을
사용자 요청사항으로 기록하지 말 것. 사전 질문은 (a) 현재 계약의 법률효과를
판단하는 데 꼭 필요한 사실, (b) 사용자가 이미 설명하지 않은 사실만 물어볼 것.
**운영대행 계약이 아닌데 운영인력/KPI/재위탁 질문을 자동 생성하는 식의
유형별 canned question 금지.**"

실측 (hold-out, AI 미사용 경로)
──────────────────────────
    라이선스 계약   → Q-DL-002 "판촉비/광고비/반품비를 누가 부담하나요?"
                       Q-CA-001 "대리점/위탁 거래에서 비용 부담…"
    대물교환 계약   → Q-OPS-003 "운영 인력 배치(인원/자격/교체/교육)…"
                       Q-OPS-002 "운영 범위, 성과/KPI, 보고·검수 기준…"
    공사도급 계약   → Q-OPS-001 "이 운영대행/위탁운영 계약서는 상대방 양식인가요?"

질문 세트가 키워드로 선택되고, 그 선택이 틀렸을 때 걸러낼 장치가 없었다.

이 모듈이 하는 일
──────────────
질문군마다 **어느 거래 원형에서 성립하는지**를 선언하고, `clause_effect` 가
확정한 원형에 맞지 않는 질문을 버린다. 판단 근거가 계약유형 enum 이 아니라
효과 기반 원형이므로, enum 에 없는 유형(라이선스·바터)에서도 동작한다.

원형을 특정하지 못했으면(`unknown`) 아무것도 버리지 않는다 — 모르는 상태에서
질문을 지우면 물어야 할 것을 못 묻는다.
"""
from __future__ import annotations

from typing import Any

from runtime.review.clause_effect import (
    ARCHETYPE_BARTER,
    ARCHETYPE_DISTRIBUTION,
    ARCHETYPE_GOODS,
    ARCHETYPE_LEASE,
    ARCHETYPE_LICENSE,
    ARCHETYPE_NDA,
    ARCHETYPE_SERVICE,
    ARCHETYPE_UNKNOWN,
    ARCHETYPE_WORKS,
)

#: 모든 원형.
_ALL = (
    ARCHETYPE_NDA, ARCHETYPE_GOODS, ARCHETYPE_SERVICE, ARCHETYPE_WORKS,
    ARCHETYPE_DISTRIBUTION, ARCHETYPE_LICENSE, ARCHETYPE_BARTER, ARCHETYPE_LEASE,
)

#: 질문 id 접두어 → 그 질문군이 성립하는 거래 원형.
#:
#: 접두어 단위로 선언하는 이유: 질문 하나하나를 손보면 질문이 늘 때마다 표를
#: 고쳐야 하지만, 질문군은 애초에 한 거래 형태를 전제로 만들어졌기 때문이다.
QUESTION_SCOPE: dict[str, tuple[str, ...]] = {
    # 계약유형·지위 확인, 양식·해외·개인정보 — 어느 계약에서나 유효
    "Q-TYPE-": _ALL,
    "Q-ROLE-": _ALL,
    "Q-CA-997": _ALL,   # 개인정보 처리 여부
    "Q-CA-998": _ALL,   # 해외거래 여부
    "Q-CA-999": _ALL,   # 상대방 양식 여부
    "Q-CA-002": _ALL,   # 책임 한도
    "Q-CA-003": _ALL,   # 면책 절차
    "Q-FOCUS-": _ALL,   # 사용자가 직접 적은 검토요청에서 파생
    "Q-AI-": _ALL,      # 계약을 읽은 AI 가 만든 질문
    # 대리점·유통 전용
    "Q-DL-": (ARCHETYPE_DISTRIBUTION,),
    "Q-CA-001": (ARCHETYPE_DISTRIBUTION,),
    "Q-LAW-001": (ARCHETYPE_DISTRIBUTION,),
    "Q-LAW-002": (ARCHETYPE_DISTRIBUTION,),
    # 매매·위탁판매 거래구조 전용
    "Q-TXN-": (ARCHETYPE_DISTRIBUTION, ARCHETYPE_GOODS),
    # 운영대행·위탁운영 전용
    "Q-OPS-": (ARCHETYPE_SERVICE,),
    # 개발·SI 전용
    "Q-AD-": (ARCHETYPE_SERVICE,),
    # 현장 안전 — 공사·설치가 있는 거래에서만
    "Q-CA-005": (ARCHETYPE_WORKS, ARCHETYPE_GOODS, ARCHETYPE_SERVICE),
    # 검수·인수 — 급부가 인도되는 거래에서만
    "Q-CA-007": (ARCHETYPE_GOODS, ARCHETYPE_SERVICE, ARCHETYPE_WORKS, ARCHETYPE_BARTER),
    # 재위탁 승인 — 용역·공사에서만
    "Q-CA-008": (ARCHETYPE_SERVICE, ARCHETYPE_WORKS),
    # 개인정보 처리위탁 — 처리위탁이 성립하는 거래
    "Q-CA-004": (ARCHETYPE_SERVICE, ARCHETYPE_DISTRIBUTION, ARCHETYPE_WORKS),
    "Q-CA-006": (ARCHETYPE_SERVICE, ARCHETYPE_DISTRIBUTION, ARCHETYPE_WORKS),
    "Q-LAW-005": _ALL,
    # 하도급 기술자료·단가 — 위탁 구조에서만
    "Q-LAW-003": (ARCHETYPE_SERVICE, ARCHETYPE_WORKS, ARCHETYPE_GOODS),
    "Q-LAW-004": (ARCHETYPE_SERVICE, ARCHETYPE_WORKS, ARCHETYPE_GOODS),
}


def _scope_for(question_id: str) -> tuple[str, ...] | None:
    """가장 구체적인(긴) 접두어를 우선 적용한다."""
    qid = str(question_id or "")
    best: tuple[str, ...] | None = None
    best_len = -1
    for prefix, archetypes in QUESTION_SCOPE.items():
        if qid.startswith(prefix) and len(prefix) > best_len:
            best, best_len = archetypes, len(prefix)
    return best


def is_question_in_scope(question_id: str, transaction_type: str) -> bool:
    """이 질문이 이 거래 원형에서 성립하는가.

    원형을 모르면(unknown) 무엇도 버리지 않는다. 표에 없는 질문군도 버리지
    않는다 — 새 질문이 추가됐다는 이유로 조용히 사라지면 안 되기 때문이다.
    """
    archetype = str(transaction_type or "").strip()
    if not archetype or archetype == ARCHETYPE_UNKNOWN:
        return True
    scope = _scope_for(question_id)
    if scope is None:
        return True
    return archetype in scope


def filter_questions_by_transaction_type(
    questions: list[Any],
    transaction_type: str,
) -> list[Any]:
    """거래 원형에 맞지 않는 canned question 을 제거한다."""
    return [
        q for q in (questions or [])
        if is_question_in_scope(str(getattr(q, "question_id", "") or ""), transaction_type)
    ]


def out_of_scope_question_ids(
    questions: list[Any],
    transaction_type: str,
) -> list[str]:
    """제거된 질문의 id — 무엇이 왜 빠졌는지 기록하기 위한 것."""
    return [
        str(getattr(q, "question_id", "") or "")
        for q in (questions or [])
        if not is_question_in_scope(str(getattr(q, "question_id", "") or ""), transaction_type)
    ]
