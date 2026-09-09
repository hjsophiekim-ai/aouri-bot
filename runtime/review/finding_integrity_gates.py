"""Finding 무결성 HARD GATE 2종(2026-09-08 지시 항목 3·9).

1. Clause Semantic Gate (항목 3)
   finding을 최종 출력에 올리기 전에 `original clause legal effect ==
   proposed finding legal effect`를 검사한다. 두 효과가 전혀 겹치지 않으면
   그 finding은 원문이 규정하지 않는 법률효과를 계약에 밀어 넣는 것이므로
   **finding 자체를 삭제**하고 `REVIEW_FAILED_SEMANTIC_MISMATCH`로 기록한다.

   종전 `clause_level.py`의 semantic gate는 mismatch를 감지해도 수정문안만
   비우고 finding은 남겨두었다(로그·추적 목적). 그 결과 "NDA 무보증 조항 →
   광고콘텐츠 저작권 이전" 같은 항목이 문제점 서술만 남은 채 최종 결과에
   그대로 노출됐다. 이 모듈은 그 처리를 삭제로 승격한다.

2. Invalid Clause Reference Gate (항목 9)
   실제 계약이 제13조까지인데 제14조를 가리키는 finding은 존재할 수 없다.
   confirmed original clause set에 없는 조항번호를 가리키는 finding을 삭제하고
   `REVIEW_FAILED_INVALID_CLAUSE_REFERENCE`로 기록한다. 신설 조항(제8조의2 등)은
   그 기준 조항(제8조)이 실재하면 유효한 참조로 본다.

두 게이트 모두 계약유형별 scope policy가 정의된 유형에서만 **삭제**까지
수행한다(`contract_scope_policy.CONTRACT_TYPE_DOMAIN_WHITELIST`). 그 외
유형에서는 종전과 동일하게 감지·기록만 하고 기존 파이프라인의 처리를
그대로 둔다 — 전 계약유형에 하드 삭제를 일괄 적용하면 태그 추론이
보수적으로 비어 있는 기존 룰들에서 예기치 않은 대량 삭제가 발생한다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.contract_scope_policy import CONTRACT_TYPE_DOMAIN_WHITELIST
from runtime.review.legal_effect_taxonomy import (
    LEGAL_EFFECT_TAGS,
    effects_overlap,
    infer_legal_effects,
)

STATUS_SEMANTIC_MISMATCH = "REVIEW_FAILED_SEMANTIC_MISMATCH"

#: 2026-09-09 지시 항목 10 이 요청한 명칭. 같은 게이트를 가리키는 별칭이다 —
#: "건설 손해배상 조항에 비밀유지의무 문구가 들어가면 semantic failure".
#: 기존 상태값을 바꾸면 저장된 세션·리포트의 상태 문자열이 깨지므로, 이름을
#: 하나 더 노출하되 값은 유지한다.
STATUS_SEMANTIC_REWRITE_MISMATCH = STATUS_SEMANTIC_MISMATCH
REVIEW_FAILED_SEMANTIC_REWRITE_MISMATCH = STATUS_SEMANTIC_MISMATCH
STATUS_INVALID_CLAUSE_REFERENCE = "REVIEW_FAILED_INVALID_CLAUSE_REFERENCE"

_RX_ARTICLE_REF = re.compile(r"제\s*(\d{1,3})\s*조(?:\s*의\s*(\d{1,2}))?")
# 법령 인용("「개인정보 보호법」 제17조", "부정경쟁방지법 제2조")은 계약
# 조항 참조가 아니므로 이 게이트의 대상이 아니다.
_RX_STATUTE_PREFIX = re.compile(r"(?:법|법률|령|규칙|조례|」|약관)\s*$")


def _tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if isinstance(x, str) and x in LEGAL_EFFECT_TAGS]


def _proposed_text(cr: dict[str, Any]) -> str:
    """이 finding이 계약에 실제로 넣으라고 제안하는 **문안**만 모은다.

    `rewrite_reason`/`issue_title` 같은 설명 필드는 포함하지 않는다 — 그것은
    "왜 보는가"를 적은 라우팅·서술 텍스트이지 계약에 삽입될 법률효과가
    아니다. 실제로 수정문안이 없는 user_focus 표식 항목의 설명 문구("사용자
    중점 이슈: 개인정보/처리위탁 …")를 제안 효과로 오인해 정상 항목을
    삭제하던 오탐이 있었다. 주제 자체가 이 계약유형에서 허용되는지는
    contract_scope_policy가 별도로 판단한다.
    """
    parts: list[str] = []
    for key in ("suggested_rewrite", "proposed_revision", "recommendation_text"):
        v = cr.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    ri = cr.get("redline_instruction")
    if isinstance(ri, dict):
        for key in ("replacement_text", "final_clause_text"):
            v = ri.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v)
    return "\n".join(parts)


def enforce_clause_semantic_gate(
    clause_results: list[dict[str, Any]],
    *,
    contract_type_code: str,
) -> dict[str, Any]:
    """원문 조항의 법률효과와 제안된 finding의 법률효과가 전혀 겹치지 않는
    finding을 삭제한다. 삭제 내역 리포트를 돌려준다."""
    hard_delete = bool(CONTRACT_TYPE_DOMAIN_WHITELIST.get((contract_type_code or "").strip()))
    report: dict[str, Any] = {
        "hard_delete": hard_delete,
        "status": "",
        "mismatches": [],
    }

    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        # 결정론적 rule(common_legal_risk.py의 clr_*, nda_scope_rules.py 등)은
        # 원문에 실제로 존재하는 문언을 정규식으로 직접 확인해 만든 finding이라
        # 주제가 구조적으로 원문에 묶여 있다. 그리고 redline의 본질은 "원문의
        # 법률효과를 바꾸는 것"이므로, 이 rule군에서는 원문과 수정문안의 효과가
        # 달라지는 것이 정상이다 — 예: 윤리조항의 손해배상청구권 포기
        # (ethics_morality)를 제거하는 수정문안은 waiver_of_claims로 분류된다.
        # 여기에 겹침을 요구하면 정확한 룰이 오히려 삭제된다(퍼시스–웹젠 NDA
        # 골든 테스트에서 실제로 재현). hallucination guard·relevance gate·
        # HIGH 캡이 같은 이유로 이 rule군을 예외 처리하는 것과 동일한 근거다.
        # 이 게이트의 대상은 원문에 근거가 없는 AI 생성·체크리스트 주입
        # finding이며, 그것이 이번 사고(콘텐츠 제작 권고 혼입)의 발생원이다.
        if bool(cr.get("is_common_legal_risk")):
            kept.append(cr)
            continue
        original_text = str(cr.get("original_text") or "")
        proposed = _proposed_text(cr)
        if not original_text.strip() or not proposed.strip():
            kept.append(cr)
            continue

        original_tags = _tags(cr.get("original_effect_tags")) or infer_legal_effects(original_text)
        proposed_tags = _tags(cr.get("rewrite_effect_tags")) or infer_legal_effects(proposed)
        if not original_tags or not proposed_tags or effects_overlap(original_tags, proposed_tags):
            kept.append(cr)
            continue

        entry = {
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "original_effect_tags": original_tags,
            "proposed_effect_tags": proposed_tags,
            "stage": "finding_semantic_gate",
            "status": STATUS_SEMANTIC_MISMATCH,
        }
        report["mismatches"].append(entry)
        if hard_delete:
            continue
        cr["semantic_mismatch"] = entry
        kept.append(cr)

    # 삭제로 실제 제거된 mismatch는 "해결된" 것이다 — 그 자체로 검토 전체를
    # 실패 처리하면 항상 REVIEW_FAILED가 되어 정상 결과까지 내려받을 수 없다.
    # 제거하지 못한 채 결과에 남은 mismatch만 검토 실패 사유로 승격한다.
    if report["mismatches"] and not hard_delete:
        report["status"] = STATUS_SEMANTIC_MISMATCH
    report["removed_count"] = len(report["mismatches"]) if hard_delete else 0
    clause_results[:] = kept
    return report


def confirmed_article_numbers(clauses: list[Any] | None) -> set[str]:
    """계약 원문에서 실제로 확인된 조 번호 집합."""
    out: set[str] = set()
    for c in (clauses or []):
        raw = c.get("article_number") if isinstance(c, dict) else getattr(c, "article_number", None)
        raw = str(raw or "").strip()
        if raw.isdigit():
            out.add(str(int(raw)))
    return out


def _referenced_articles(text: str, *, skip_statutes: bool) -> set[str]:
    out: set[str] = set()
    for m in _RX_ARTICLE_REF.finditer(text or ""):
        if skip_statutes:
            before = (text or "")[max(0, m.start() - 20): m.start()]
            if _RX_STATUTE_PREFIX.search(before.rstrip()):
                continue
        out.add(str(int(m.group(1))))
    return out


def enforce_valid_clause_references(
    clause_results: list[dict[str, Any]],
    clauses: list[Any] | None,
    *,
    contract_type_code: str,
) -> dict[str, Any]:
    """confirmed original clause set에 없는 조항번호를 가리키는 finding을 삭제한다.

    검사 대상은 시스템이 생성한 구조 필드(display_path / clause_title /
    redline_instruction.edit_location)와 수정문안이다. 원문 인용(original_text)은
    계약서 자신의 문언이므로 검사하지 않는다.
    """
    valid = confirmed_article_numbers(clauses)
    hard_delete = bool(CONTRACT_TYPE_DOMAIN_WHITELIST.get((contract_type_code or "").strip()))
    report: dict[str, Any] = {
        "hard_delete": hard_delete,
        "status": "",
        "confirmed_articles": sorted(valid, key=lambda x: int(x)),
        "invalid_references": [],
    }
    if not valid:
        # 조 단위 구조를 확인하지 못한 계약(스캔 PDF 등)에서는 참조 유효성을
        # 판단할 근거 자체가 없으므로 아무 것도 차단하지 않는다.
        return report

    # 신설 조항 권고는 정의상 아직 존재하지 않는 번호를 가리킨다. 계약의
    # 마지막 조 바로 다음 번호(제13조까지인 계약의 "제14조 신설")까지만
    # 유효한 참조로 허용한다 — 그 이상을 가리키면 여전히 지어낸 번호다.
    _next_article = str(max(int(n) for n in valid) + 1)
    valid_with_new = valid | {_next_article}

    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        refs: set[str] = set()
        new_clause_refs: set[str] = set()
        for key in ("display_path", "clause_title"):
            refs |= _referenced_articles(str(cr.get(key) or ""), skip_statutes=False)
        ri = cr.get("redline_instruction")
        if isinstance(ri, dict):
            loc = str(ri.get("edit_location") or "")
            target = new_clause_refs if "신설" in loc else refs
            target |= _referenced_articles(loc, skip_statutes=False)
        for key in ("suggested_rewrite", "proposed_revision", "recommendation_text"):
            body = str(cr.get(key) or "")
            target = new_clause_refs if "신설" in body else refs
            target |= _referenced_articles(body, skip_statutes=True)

        invalid = sorted((refs - valid) | (new_clause_refs - valid_with_new), key=lambda x: int(x))
        if not invalid:
            kept.append(cr)
            continue

        entry = {
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "invalid_articles": [f"제{n}조" for n in invalid],
            "status": STATUS_INVALID_CLAUSE_REFERENCE,
        }
        report["invalid_references"].append(entry)
        if hard_delete:
            continue
        cr["invalid_clause_reference"] = entry
        kept.append(cr)

    # semantic gate와 같은 이유 — 삭제로 제거된 잘못된 참조는 해결된 것이고,
    # 제거하지 못하고 결과에 남은 것만 검토 실패 사유가 된다.
    if report["invalid_references"] and not hard_delete:
        report["status"] = STATUS_INVALID_CLAUSE_REFERENCE
    report["removed_count"] = len(report["invalid_references"]) if hard_delete else 0
    clause_results[:] = kept
    return report
