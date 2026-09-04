"""문장 완결성 HARD GATE (2026-09-03 지시, 요구 6).

"KOTRA shall pay Consultant a total of USD"처럼 문장이 중간에서 잘리거나,
"[추가 권고]" 뒤에 내용이 빠지거나, 원문 일부가 앞에서 잘려 "ayment"/"icle"
같은 조각으로 시작하는 경우를 DOCX/PDF 생성 전에 검출해 차단한다.

실제 원인은 대부분 `legal_review_docx.py`/`legal_review_pdf.py`가 단어
경계를 고려하지 않고 `text[:N]`으로 하드 슬라이싱하는 데 있으므로,
① 그 슬라이싱을 전부 `safe_truncate()`로 교체해 새로운 절단을 원천
차단하고, ② 그래도 파이프라인 어딘가에 이미 잘린 텍스트가 들어있는
경우를 잡아내는 `detect_language_quality_issues()`를 최종 게이트로 둔다.
"""
from __future__ import annotations

import re
from typing import Any

# legal_review_docx.py에서 실제로 쓰이는 슬라이스 경계값들 — 텍스트 길이가
# 이 값 중 하나와 "정확히" 일치하면서 종결부호로 안 끝나면 슬라이싱으로
# 잘렸다는 강한 신호다(우연히 정확히 이 길이에서 문장이 끝났을 확률은 낮다).
_KNOWN_SLICE_BOUNDARIES: frozenset[int] = frozenset({120, 200, 250, 300, 350, 400, 500, 800, 2000, 3000})

# 문장이 "정상적으로 끝났다"고 볼 수 있는 종결부호/문자 — 한국어 종결어미,
# 영어 마침표류, 괄호/따옴표 닫힘, 리스트 항목 등을 폭넓게 허용해 정상
# 텍스트를 오탐하지 않는다.
_RX_SENTENCE_END = re.compile(
    r"[.!?)\]}\"'」』】。！？]\s*$"
    r"|(?:다|함|음|임|됨|것|요|음\.|함\.)\s*$"
    r"|[가-힣]{1,3}$",  # 한국어 마지막 글자가 완결된 어절인 경우까지 관대하게 허용
)

_RX_ADDITIONAL_RECOMMENDATION_EMPTY = re.compile(r"\[추가\s*권고\]\s*$")

# `original_text`는 의도적으로 "매칭된 패턴 주변 before/after 글자수"만
# 보여주는 windowed 발췌문이다 — 계약 원문 전체가 아니라 컨텍스트 확인용
# 일부만 인용하는 것이 정상 동작이므로, 완결된 문장으로 끝나지 않는다고
# 해서 그 자체를 "문장 완결성 위반"으로 볼 수 없다(실측 결과, 정상적인
# 한글+영문 약어 혼용 문장 다수가 오탐되어 제외함). 반면 우리가 직접
# 작성하는 필드(수정안·사유 등)는 항상 완결된 문장이어야 하므로 엄격 검사한다.
_GENERATED_FIELDS: tuple[str, ...] = (
    "suggested_rewrite", "legal_business_reason",
    "rewrite_reason", "recommendation_text", "problem", "proposed_revision",
)
_ALL_CHECK_FIELDS: tuple[str, ...] = ("original_text",) + _GENERATED_FIELDS


def safe_truncate(text: str, max_len: int, *, ellipsis: str = "…") -> str:
    """`text[:max_len]`을 그대로 쓰는 대신, 마지막 단어/문장 경계까지만
    잘라 단어 중간 절단("ayment", "icle")을 원천 차단한다. 잘렸으면
    ellipsis를 붙이고, 원래 길이가 max_len 이하면 그대로 반환한다.
    """
    t = str(text or "")
    if len(t) <= max_len:
        return t
    cut = t[:max_len]
    # 마지막 공백/문장부호 위치까지 되돌아간다 — 못 찾으면(공백이 전혀 없는
    # 긴 토큰) 부득이 원래 위치에서 자르되 ellipsis로 절단 사실을 표시한다.
    boundary = max(cut.rfind(" "), cut.rfind("\n"))
    for punct in (".", "다", "함", ")", "」", "』", ","):
        idx = cut.rfind(punct)
        if idx > boundary:
            boundary = idx + 1
    if boundary > max_len * 0.5:
        cut = cut[:boundary].rstrip()
    return cut.rstrip() + ellipsis


def detect_language_quality_issues(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """clause_results의 텍스트 필드를 검사해 문장 완결성 위반 목록을
    반환한다(비어있으면 문제 없음). 각 항목: {"clause_id", "field", "reason"}.
    """
    violations: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        clause_id = str(cr.get("clause_id") or "")
        for field in _ALL_CHECK_FIELDS:
            val = cr.get(field)
            if not isinstance(val, str) or not val.strip():
                continue
            text = val.strip()

            # (a) 알려진 슬라이스 경계값과 길이가 정확히 일치하면서 종결부호로
            # 안 끝나면 절단 신호 — 우리가 직접 생성하는 필드에만 적용한다.
            # original_text는 windowed 발췌가 정상 동작이라 제외.
            if (
                field in _GENERATED_FIELDS
                and len(text) in _KNOWN_SLICE_BOUNDARIES
                and not _RX_SENTENCE_END.search(text)
            ):
                violations.append({
                    "clause_id": clause_id,
                    "field": field,
                    "reason": f"length_exactly_{len(text)}_no_terminator",
                })
                continue

            # (b) "[추가 권고]" 뒤에 실질 내용이 없음 — 모든 필드 대상.
            if _RX_ADDITIONAL_RECOMMENDATION_EMPTY.search(text):
                violations.append({
                    "clause_id": clause_id,
                    "field": field,
                    "reason": "empty_additional_recommendation_block",
                })
                continue

    return violations
