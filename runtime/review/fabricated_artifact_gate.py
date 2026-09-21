"""계약에 없는 **산출물·의무**를 있는 것처럼 말하지 못하게 한다.

2026-09-16 지시 4항 —
  "계약에 '성적서', '결과물 저작권', '제3자 소재 라이선스 확보 의무' 등이
   실제로 없으면 있다고 가정하지 마세요. 사용자 질문 템플릿이 만든 단어를
   계약 사실처럼 승계하지 말 것."

v10 의 존재 검증(`existence_gate`)과 무엇이 다른가
──────────────────────────────────────────────
`existence_gate` 는 **조항번호와 인용문**이 실재하는지를 본다. "제12조" 가
없는데 제12조를 인용했는지, 원문에 없는 문장을 원문이라고 했는지.

이 게이트가 막는 것은 한 단계 다른 거짓말이다 — 조항번호도 맞고 인용도
맞는데, **설명이 계약에 없는 물건을 기정사실로 말하는** 경우다.

    "제4조가 정한 성적서 제출 기한이 …"        ← 계약에 성적서가 없다
    "결과물 저작권이 갑에게 귀속되므로 …"       ← 결과물도 그 귀속 조항도 없다
    "제3자 소재 라이선스 확보 의무를 이행할 때" ← 그런 의무가 없다

이런 문장은 담당자가 계약서를 다시 뒤지게 만들고, 없는 것을 찾다가 검토
전체를 믿지 못하게 된다.

어디서 흘러들어오는가
───────────────────
대개 **질문 템플릿과 유형별 체크리스트**다. 사전질문이 "결과물을 2차
활용할 계획인가요?" 라고 묻고 담당자가 아무 답이나 적으면, 그 뒤의 검토가
"결과물" 을 계약의 산출물로 받아 적는다. 그래서 이 게이트는 사용자 입력과
질문 문구를 **계약 사실의 근거로 인정하지 않는다** — 근거는 계약 원문뿐이다.

판정 방식
────────
1. finding 이 쓰는 산출물 명사를 찾는다(`_ARTIFACT_TERMS`).
2. 그 낱말이 **계약 원문에 없으면** 거짓 전제다.
3. 다만 "없다/규정되어 있지 않다/신설한다" 처럼 **부재를 지적하거나 신설을
   제안하는** 문장은 그대로 둔다 — 없는 것을 없다고 말하는 것은 정확히
   해야 할 일이다. 이 구분을 놓치면 "성적서 제출 의무를 신설하라" 는 정당한
   권고까지 지워진다.
4. 지운 뒤에는 무엇을 왜 지웠는지 남긴다. 조용히 버리지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

REVIEW_FAILED_FABRICATED_ARTIFACT = "REVIEW_FAILED_FABRICATED_ARTIFACT"

#: 계약에 **있어야만** 말할 수 있는 산출물·의무의 이름.
#:
#: 각 항목은 (표시 이름, finding 쪽 탐지 패턴, 계약 원문 쪽 존재 패턴).
#: 원문 쪽 패턴을 따로 두는 이유는 계약서가 같은 것을 다른 말로 적기
#: 때문이다 — "시험성적서" 를 "검사결과서" 로 쓰는 계약이 있다. 원문 쪽은
#: 넓게 잡는다. 존재를 넓게 인정하는 쪽이 안전하다(있는데 없다고 지우면
#: 정당한 검토가 사라진다).
_ARTIFACT_TERMS: tuple[tuple[str, str, str], ...] = (
    (
        "성적서",
        r"성적서",
        r"성적서|검사\s*결과(?:서|보고서)|시험\s*결과(?:서|보고서)|試驗成績書",
    ),
    (
        "결과물·산출물",
        r"(?:결과물|산출물|납품물|제작물)\s*(?:의|에\s*대한)?\s*"
        r"(?:저작권|저작재산권|권리|소유권|귀속)",
        r"결과물|산출물|납품물|제작물|성과물",
    ),
    (
        "제3자 소재 라이선스 확보 의무",
        r"(?:제3자|타인)\s*(?:소재|저작물|콘텐츠)[^.\n]{0,25}"
        r"(?:라이선스|이용허락|사용권|권리처리)",
        r"라이선스|이용허락|사용권|권리\s*처리|licen[sc]e",
    ),
    (
        "검수·승인 절차",
        r"검수\s*(?:기준|절차|기간|일정|합격|완료)|인수\s*검사",
        r"검수|인수\s*검사|수령\s*검사|합격",
    ),
    (
        "하자보수 보증",
        r"하자\s*보수\s*(?:기간|보증금|의무)",
        r"하자|보수\s*보증|warranty",
    ),
    (
        "이행보증·보증보험",
        r"이행\s*보증(?:금|보험)|계약\s*보증금|선급금\s*보증",
        r"보증금|보증\s*보험|이행\s*보증|담보",
    ),
    (
        "특수관계인 확인",
        r"특수관계(?:인|자)",
        r"특수관계(?:인|자)|계열회사|지배·?종속",
    ),
)

_COMPILED: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = tuple(
    (name, re.compile(f, re.IGNORECASE), re.compile(c, re.IGNORECASE))
    for name, f, c in _ARTIFACT_TERMS
)

#: **부재를 지적하거나 신설을 제안하는** 문형. 이런 문장은 거짓 전제가 아니다.
_RX_ABSENCE_OR_PROPOSAL = re.compile(
    r"없[다습]|없으[므며]|없는|아니[다한]|않[다는습]|미비|누락|부재"
    r"|규정되(?:어|지)\s*(?:있지\s*)?(?:않|아니)"
    r"|정하(?:고|지)\s*있지\s*(?:않|아니)"
    r"|신설|추가(?:한다|하고|하여|할)|삽입|명시(?:한다|하도록|할\s*필요)"
    r"|확보(?:할|해야|하여야)\s*(?:한다|합니다)?"
    r"|요구(?:한다|해야|하여야)|받(?:아야|기로)\s*(?:한다|합의)"
)

#: 이 필드들만 본다 — `original_text`(계약 원문 인용)는 제외한다. 원문에
#: 그 낱말이 있다는 것은 계약에 있다는 뜻이지 지어냈다는 뜻이 아니다.
_FIELDS = (
    "issue_title", "problem", "why_matters", "rewrite_reason",
    "legal_business_reason", "suggested_rewrite", "proposed_revision",
    "recommendation_text", "negotiation_position", "worst_case_scenario",
)


def _finding_blob(cr: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in _FIELDS:
        v = cr.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(str(x) for x in v if isinstance(x, str))
    return "\n".join(parts)


def find_fabricated_artifacts(*, finding_text: str, contract_text: str) -> list[str]:
    """이 finding 이 계약에 없는 산출물을 기정사실로 말하는가.

    돌려주는 것은 그렇게 쓰인 산출물 이름 목록이다. 비어 있으면 문제없다.
    """
    blob = str(finding_text or "")
    body = str(contract_text or "")
    if not blob.strip() or not body.strip():
        return []
    hits: list[str] = []
    for name, rx_finding, rx_contract in _COMPILED:
        m = rx_finding.search(blob)
        if not m:
            continue
        if rx_contract.search(body):
            continue  # 계약에 실제로 있다 — 말해도 된다
        # 없는 것을 "없다"고 지적하거나 "신설하라"고 제안하는 문장인지 본다.
        # 그 낱말이 나온 문장 하나만 본다 — finding 전체에서 아무 데나
        # "없다" 가 있으면 통과시키면 게이트가 사실상 꺼진다.
        start = blob.rfind("\n", 0, m.start()) + 1
        end = blob.find("\n", m.end())
        sentence = blob[start: end if end != -1 else len(blob)]
        if _RX_ABSENCE_OR_PROPOSAL.search(sentence):
            continue
        hits.append(name)
    return hits


def enforce_no_fabricated_artifacts(
    clause_results: list[dict[str, Any]],
    *,
    contract_text: str,
) -> dict[str, Any]:
    """계약에 없는 산출물을 기정사실로 말하는 finding 을 제거한다.

    돌려주는 리포트: {"removed": [...], "status": ""|REVIEW_FAILED_…, "detail": ""}
    """
    report: dict[str, Any] = {"removed": [], "status": "", "detail": ""}
    body = str(contract_text or "")
    if not body.strip():
        return report

    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        hits = find_fabricated_artifacts(
            finding_text=_finding_blob(cr), contract_text=body,
        )
        if not hits:
            kept.append(cr)
            continue
        report["removed"].append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            "artifacts": hits,
            "reason": (
                "계약서에 " + ", ".join(hits) + " 이(가) 없는데 있는 것을 전제로 "
                "작성된 검토의견이라 제외했습니다."
            ),
        })
    if report["removed"]:
        clause_results[:] = kept
        report["status"] = REVIEW_FAILED_FABRICATED_ARTIFACT
        report["detail"] = (
            "계약에 없는 산출물·의무를 전제한 검토의견을 제거했습니다: "
            + ", ".join(
                f"{r['clause_id']}({'/'.join(r['artifacts'])})"
                for r in report["removed"][:5]
            )
        )
    return report
