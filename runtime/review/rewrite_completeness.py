"""수정문안 완성도 게이트 — 복사해서 바로 넣을 수 있어야 '완료' 다.

2026-09-14 지시 —
  "MEDIUM/권장수정도 HIGH와 동일하게 반드시 실제 삽입 가능한 완성 문구를 제시.
   '~를 명시한다', '~를 보완한다', '담당 변호사가 확정' 같은 설명형 문구 금지.
   일반 사용자가 그대로 복사·붙여넣기 할 수 없는 수정안은 완료로 보지 말 것."

무엇이 문제였나 (실측 — SNS마케팅 제휴계약(실사례))
──────────────────────────────────────────────────
MEDIUM 항목의 제안 문안이 이랬다.

    "해지 사유와 절차, 해지의 효력이 미치는 범위를 본조에 명시한다."   (36자)
    "본조에 따른 손해배상의 범위와 총액 상한, 간접·특별손해의 취급을 본조에 명시한다."

이것은 **무엇을 써야 하는지 설명한 문장**이지 계약서에 넣을 조문이 아니다.
담당자는 이걸 받아서 결국 자기가 조문을 다시 써야 했다.

두 가지를 한다
─────────────
  1. 설명형·자리표시자 문안을 **탐지**하고, 완료로 표시하지 않는다.
  2. 같은 문안을 제안하는 항목이 여럿이면 **하나로 합친다**.

문안 자체를 만드는 일은 이 모듈이 하지 않는다 — 그것은
`minimal_edit`(효과별 중립 조문)과 각 rule·체크리스트의 템플릿이 담당한다.
이 모듈은 그 결과가 실제로 쓸 만한지 확인하는 **검사자**다.
"""
from __future__ import annotations

import re
from typing import Any

STATUS_INCOMPLETE_REWRITE = "REVIEW_FAILED_INCOMPLETE_REWRITE"

#: 복사해 넣을 수 있는 조문이라면 최소한 이 정도 길이는 된다. 그 아래는
#: 대부분 "…를 명시한다" 한 줄짜리 설명이다.
MIN_CLAUSE_LEN = 60

#: 지시가 명시적으로 금지한 표현.
_RX_FORBIDDEN = re.compile(
    r"담당\s*변호사가?\s*(?:직접\s*)?확정"
    r"|\[수정문안\s*보류\]"
    r"|수정\s*문구\s*자동생성\s*보류"
    r"|추후\s*협의"
    r"|별도\s*협의\s*필요"
    r"|\bTBD\b"
    r"|검토\s*필요",
    re.IGNORECASE,
)

#: 설명형 서술의 표지 — "~를 명시한다/보완한다/반영한다/규정한다" 로 끝나는 형태.
_RX_DESCRIPTIVE_TAIL = re.compile(
    r"(?:명시|특정|보완|반영|규정|추가|삽입|기재)(?:하도록)?\s*(?:한다|하여야\s*한다|할\s*것)\s*[.。]?\s*$"
)

#: 조문이라면 나타나는 규범적 어미. 하나도 없으면 문장이 아니라 메모다.
_RX_NORMATIVE = re.compile(
    # 실측 보정: "…공개할 수 없다" 로 끝나는 금지 조문이 규범 어미로 인식되지
    # 않아 완성된 143자 조문이 "설명형" 으로 오판됐다(CP-008).
    r"한다|하여야|해야"
    r"|할\s*수\s*(?:있다|없다)"
    r"|하지\s*(?:못한다|아니한다|않는다)"
    r"|하여서는\s*아니|아니\s*된다|아니한다"
    r"|본다|간주한다|부담한다|귀속(?:된다|한다)|이전한다|지급한다|배상한다|보증한다"
    r"|없다|된다|진다"
)

_REWRITE_FIELDS = ("suggested_rewrite", "proposed_revision")
_REDLINE_FIELDS = ("replacement_text", "final_clause_text")


def rewrite_text(cr: dict[str, Any]) -> str:
    """이 finding 이 계약에 넣으라고 제안하는 문안."""
    for key in _REWRITE_FIELDS:
        value = str(cr.get(key) or "").strip()
        if value:
            return value
    ri = cr.get("redline_instruction")
    if isinstance(ri, dict):
        for key in _REDLINE_FIELDS:
            value = str(ri.get(key) or "").strip()
            if value:
                return value
    return ""


def is_descriptive_only(text: str) -> bool:
    """이 문안이 '조문' 이 아니라 '설명' 인가."""
    value = str(text or "").strip()
    if not value:
        return True
    if _RX_FORBIDDEN.search(value):
        return True
    if not _RX_NORMATIVE.search(value):
        return True
    # 한 문장짜리 짧은 글이 "…를 명시한다" 로 끝나면 설명이다.
    sentences = [s for s in re.split(r"(?<=[.。])\s+", value) if s.strip()]
    if len(sentences) <= 1 and len(value) < MIN_CLAUSE_LEN and _RX_DESCRIPTIVE_TAIL.search(value):
        return True
    return len(value) < MIN_CLAUSE_LEN and _RX_DESCRIPTIVE_TAIL.search(value) is not None


def _norm_for_dedup(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def merge_duplicate_rewrites(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 문안을 제안하는 항목을 하나로 합친다(지시: 중복 통합).

    **문안이 글자 그대로 같은 경우만** 합친다. 비슷해 보인다는 이유로 묶으면
    서로 다른 조항의 서로 다른 지적이 사라진다 — 이 엔진에서 이미 여러 번
    일어난 사고다. 합쳐진 쪽은 `dedup_suppressed` 로 표시만 하고 남겨 둔다.
    """
    merged: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
            continue
        key = _norm_for_dedup(rewrite_text(cr))
        if len(key) < MIN_CLAUSE_LEN:
            continue
        first = seen.get(key)
        if first is None:
            seen[key] = cr
            continue
        # 먼저 온 쪽에 흡수한다. 등급이 높은 쪽을 남긴다.
        keeper, absorbed = first, cr
        if str(cr.get("risk_tier")).upper() == "HIGH" and str(first.get("risk_tier")).upper() != "HIGH":
            keeper, absorbed = cr, first
            seen[key] = cr
        absorbed["dedup_suppressed"] = True
        absorbed["dedup_merged_into"] = str(keeper.get("clause_id") or "")
        related = keeper.setdefault("merged_clause_ids", [])
        if isinstance(related, list):
            related.append(str(absorbed.get("clause_id") or ""))
        merged.append({
            "kept": str(keeper.get("clause_id") or ""),
            "merged": str(absorbed.get("clause_id") or ""),
        })
    return merged


def enforce_rewrite_completeness(
    clause_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """HIGH/MEDIUM 전부가 삽입 가능한 완성 문구를 갖고 있는지 확인한다.

    갖고 있지 않은 항목은 **지우지 않는다** — 지적 자체는 유효하다. 대신
    `incomplete_rewrite` 로 표시하고 상태를 세워 "완료" 로 보이지 않게 한다.
    담당자는 그 항목이 아직 문안을 직접 써야 하는 것임을 알게 된다.
    """
    report: dict[str, Any] = {
        "status": "",
        "detail": "",
        "incomplete": [],
        "merged": [],
    }
    report["merged"] = merge_duplicate_rewrites(clause_results)

    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        if bool(cr.get("keep_as_is")):
            continue  # 현행 유지 항목은 문안이 없는 것이 정상이다
        if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
            continue
        text = rewrite_text(cr)
        if not is_descriptive_only(text):
            continue
        cr["incomplete_rewrite"] = True
        cr["incomplete_rewrite_reason"] = (
            "제안 문안이 계약서에 그대로 넣을 수 있는 조문이 아닙니다 — "
            "담당자가 문안을 직접 확정해야 합니다."
        )
        report["incomplete"].append({
            "clause_id": str(cr.get("clause_id") or ""),
            "risk_tier": str(cr.get("risk_tier") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            "rewrite_preview": text[:120],
        })

    if report["incomplete"]:
        report["status"] = STATUS_INCOMPLETE_REWRITE
        report["detail"] = (
            f"삽입 가능한 완성 문구가 없는 항목 {len(report['incomplete'])}건: "
            + ", ".join(x["clause_id"] for x in report["incomplete"][:6])
        )
    return report
