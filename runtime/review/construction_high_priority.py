"""건설공사(수급인) HIGH 항목의 **손실 규모 기준** 정렬.

2026-09-21 2차 지시 9항 —
  "HIGH 는 실제 손실·책임 규모 기준으로 정렬:
   1) 공사대금 미회수 2) 유치권/담보수단 상실 3) 추가공사 무상 수행
   4) 지급유보·상계·공제 5) 과도한 보증 6) 지체상금/공기연장권 상실
   7) 해지·대체시공 8) 안전·산재 책임 전가.
   세금계산서, 원천징수, 비용인정 등은 [재경/세무 확인사항] 으로 별도 분리하고
   핵심 계약리스크보다 앞에 두지 마세요."

왜 정렬이 필요한가
────────────────
HIGH 안에서의 순서는 담당자가 협상 테이블에서 무엇을 먼저 꺼낼지를 정한다.
등급만 같으면 순서는 생성 순서(체크리스트 id 순, 룰 로딩 순)로 정해지는데,
그 순서는 손실 규모와 아무 관계가 없다. 실측(2026-09-21 15:45 검토)에서는
안전 서류 항목이 유치권 포기보다 앞에 실렸다.

**등급을 바꾸지 않는다.** 순서만 정한다 — 등급 조정은 다른 게이트의 몫이고,
여기서 함께 하면 어느 쪽이 바꿨는지 추적할 수 없게 된다.
"""
from __future__ import annotations

import re
from typing import Any

#: 지시 9항의 순서 그대로. 낮은 값이 앞이다.
LOSS_PRIORITY: tuple[tuple[int, str, re.Pattern[str]], ...] = (
    (1, "공사대금 미회수", re.compile(
        r"대금[^.\n]{0,20}(?:미회수|회수|못\s*받|지급받지)"
        r"|공사대금\s*회수|기성[^.\n]{0,20}확정[^.\n]{0,20}지연"
    )),
    (2, "유치권·담보수단 상실", re.compile(r"유치권|채권보전|담보\s*수단")),
    (3, "추가공사 무상 수행", re.compile(
        r"추가\s*공사[^.\n]{0,20}(?:무상|대가|청구)|설계\s*변경[^.\n]{0,30}조정"
        r"|계약금액[^.\n]{0,20}조정[^.\n]{0,20}(?:절차|없)"
    )),
    (4, "지급유보·상계·공제", re.compile(r"지급\s*유보|유보금|상계|공제")),
    (5, "과도한 보증", re.compile(r"보증(?:서|금|보험)|이행보증|하자보수보증")),
    (6, "지체상금·공기연장권", re.compile(
        r"지체\s*상금|지연배상|공기\s*연장|공사기간[^.\n]{0,10}연장|준공\s*기한"
    )),
    (7, "해지·대체시공", re.compile(r"해지|해제|대체\s*시공|기성\s*정산")),
    (8, "안전·산재 책임 전가", re.compile(r"안전|산재|중대재해|재해|보건")),
)

#: 핵심 계약리스크보다 **뒤**에 둔다(지시 9항 후단).
_RX_FINANCE_TOPIC = re.compile(
    r"세금계산서|원천징수|부가가치세|법인세|손금|비용\s*인정|회계\s*처리|과세표준"
)

FINANCE_RANK = 90
UNCLASSIFIED_RANK = 50

#: 재경·세무 항목에 붙일 표지 — 화면·문서에서 계약 협상 항목과 구분된다.
FINANCE_LABEL = "[재경/세무 확인사항]"


def _subject(cr: dict[str, Any]) -> str:
    return " ".join(
        str(cr.get(k) or "")
        for k in ("issue_title", "clause_title", "problem", "rewrite_reason")
    )


def loss_rank(cr: dict[str, Any]) -> tuple[int, str]:
    """이 항목의 손실 순위와 그 이름."""
    text = _subject(cr)
    if _RX_FINANCE_TOPIC.search(text):
        return FINANCE_RANK, "재경·세무 확인사항"
    for rank, label, pattern in LOSS_PRIORITY:
        if pattern.search(text):
            return rank, label
    return UNCLASSIFIED_RANK, ""


def apply_high_priority_order(
    clause_results: list[dict[str, Any]], *, model: Any = None,
) -> list[dict[str, Any]]:
    """손실 규모 순위를 기록하고, 재경·세무 항목에 표지를 붙인다.

    수급인 지위에서만 돈다 — 도급인에게는 손실 구조가 반대다.
    반환값은 무엇을 어떻게 매겼는지의 기록이다.
    """
    if model is not None:
        if not getattr(model, "is_construction", False):
            return []
        if not getattr(model, "is_contractor_side", False):
            return []
        if not getattr(model, "is_settled", False):
            return []

    assigned: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        rank, label = loss_rank(cr)
        cr["loss_priority_rank"] = rank
        cr["loss_priority_label"] = label
        if rank == FINANCE_RANK:
            title = str(cr.get("issue_title") or "")
            if title and not title.startswith(FINANCE_LABEL):
                cr["issue_title"] = f"{FINANCE_LABEL} {title}"
            cr["finance_confirmation_item"] = True
        assigned.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "rank": rank,
            "label": label,
            "severity": str(cr.get("severity") or ""),
        })

    # 정렬은 HIGH 안에서만 한다 — 등급 경계를 넘어 섞으면 화면의 묶음이 깨진다.
    def _key(cr: Any) -> tuple[int, int]:
        if not isinstance(cr, dict):
            return (1, UNCLASSIFIED_RANK)
        tier = str(cr.get("risk_tier") or cr.get("severity") or "").upper()
        if tier not in ("HIGH", "CRITICAL"):
            return (1, UNCLASSIFIED_RANK)
        return (0, int(cr.get("loss_priority_rank") or UNCLASSIFIED_RANK))

    clause_results.sort(key=_key)
    return assigned
