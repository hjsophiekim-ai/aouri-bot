"""안정적인 finding_id 부여 — UI와 DOCX/PDF가 동일한 finding을 동일한 ID로
가리키게 한다(2026-09-03 지시, UI·DOCX 최종 동일성 보증).

`clause_id`는 두 가지 서로 다른 개념을 겸하고 있어(조항 위치 ID이거나
규칙 ID이거나) 그 자체로는 안정적인 finding 정체성이 아니다 — dedup 병합
시 대표 clause_id가 실행마다 바뀔 수 있고, 같은 규칙이 여러 조항에 매칭되면
`related_clauses`로 흡수되기도 한다. `finding_id`는 이런 병합/재정렬과
무관하게, "이 finding이 실제로 무엇을 지적하는가"(clause_id + 인용 원문)에서
결정론적으로 파생되는 해시이므로, 같은 리뷰를 UI에서 보여줄 때와 DOCX로
내보낼 때 항상 같은 값을 갖는다.
"""
from __future__ import annotations

import hashlib
from typing import Any


def _mint_finding_id(cr: dict[str, Any]) -> str:
    clause_id = str(cr.get("clause_id") or "")
    original_text = str(cr.get("original_text") or "")[:200]
    basis = f"{clause_id}|{original_text}"
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
    return f"fnd_{digest}"


def ensure_finding_ids(clause_results: list[dict[str, Any]]) -> None:
    """In place: finding_id가 없는 항목에 안정적인 ID를 부여한다.

    이미 `finding_id`가 있는 항목은 절대 덮어쓰지 않는다 — 여러 처리
    단계(UI 저장 시점, DOCX 다운로드 시점)에서 반복 호출돼도 한번 정해진
    ID는 그대로 유지된다.
    """
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if str(cr.get("finding_id") or "").strip():
            continue
        cr["finding_id"] = _mint_finding_id(cr)
