"""Document Hierarchy — 조항을 보기 전에 **문서 우선순위**를 먼저 복원한다
(2026-09-09 지시 2·6항).

실무 계약은 한 덩어리 문서가 아니다. 본계약서(갑지) 뒤에 일반조건이 붙고,
그 위에 특수조건이 얹히고, 입찰지침서·내역서·시방서·도면이 첨부된다. 그리고
거의 모든 계약이 "상이한 사항이 있을 경우 A > B > C 순위에 의해서 해석된다"는
조항을 둔다. 이 순위를 모르면 검토가 틀린다 — 일반조건에서 찾은 보호조항이
특수조건에서 이미 뒤집혀 있는데도 "보호장치가 있다"고 결론 내리게 된다.

실측 사례(2026-09-09, 공사도급계약 26,738자)는 이 문제를 그대로 보여준다.
한 PDF 안에 일반조건과 특수조건이 **각각 제1조부터 다시 시작**하고, 순위는
`공사도급계약서 > 특수조건 > 일반조건 > 입찰질의회신 > 입찰지침서 > …` 이며,
특수조건이 일반조건의 보호를 실제로 무력화한다:

    일반조건 제17조  공기연장 사유가 있으면 계약금액을 증액
    특수조건 제8조3항 공기만회 돌관작업비·추가 투입비는 전액 수급인 부담

    일반조건 제22조  설계변경 시 계약금액 조정
    특수조건 제4조3항 계약조건 미숙지·적자보전 등으로 계약금액 변경을
                     요구하거나 시공을 거부할 수 없다

이 모듈이 하는 일:

    1. 한 텍스트 안의 문서 구간을 식별한다 (일반조건 / 특수조건 / 별첨 / …)
    2. 계약이 **선언한** 우선순위를 파싱한다 (`A > B > C`, 각 호 나열)
    3. 선언이 없으면 실무 통례 순서를 쓴다
    4. 상위 문서가 하위 문서의 위험배분을 뒤집은 축을 찾아 보고한다

설계 — **하드코딩 금지**. 특정 계약명·회사명·조항번호를 쓰지 않는다. 문서
종류는 실무에서 쓰이는 일반 명칭(국문·영문)으로만 식별하고, 무력화 판정은
위험배분 매트릭스를 문서 구간별로 각각 돌려 그 결과를 비교하는 방식으로
계산한다. 그래서 처음 보는 계약유형·문서 구성에도 적용된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: 검토 상태 — 우선순위가 선언됐는데 상위 문서가 하위 문서의 보호를
#: 무력화한 사실이 결과에 반영되지 않은 경우.
REVIEW_FAILED_DOCUMENT_HIERARCHY_IGNORED = "REVIEW_FAILED_DOCUMENT_HIERARCHY_IGNORED"

DOC_MAIN = "main_agreement"
DOC_SPECIAL = "special_conditions"
DOC_GENERAL = "general_conditions"
DOC_QA = "qa_reply"
DOC_BID = "bid_instructions"
DOC_BOQ = "bill_of_quantities"
DOC_SPEC = "specifications"
DOC_DRAWING = "drawings"
DOC_SOW = "statement_of_work"
DOC_ANNEX = "annex"

DOC_LABELS: dict[str, str] = {
    DOC_MAIN: "본계약서",
    DOC_SPECIAL: "특수조건",
    DOC_GENERAL: "일반조건",
    DOC_QA: "입찰질의회신",
    DOC_BID: "입찰지침서",
    DOC_BOQ: "내역서",
    DOC_SPEC: "시방서",
    DOC_DRAWING: "설계도면",
    DOC_SOW: "과업지시서",
    DOC_ANNEX: "별첨",
}

#: 문서 종류별 명칭. 순서가 중요하다 — 긴 이름이 짧은 이름을 포함하는 경우
#: (예: "공사계약 특수조건" 안의 "계약")를 피하려고 구체적인 것을 먼저 둔다.
#: 각 항목은 (문서 종류, 명칭들). 명칭은 소문자로 비교한다.
_DOC_NAMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (DOC_SPECIAL, ("특수조건", "특별조건", "특약사항", "특약조건",
                   "special conditions", "particular conditions")),
    (DOC_GENERAL, ("일반조건", "일반약관", "공통조건", "표준약관",
                   "general conditions", "general terms")),
    (DOC_QA, ("입찰질의회신", "입찰 질의회신", "질의회신", "질의응답",
              "질의 회신", "clarification")),
    (DOC_BID, ("입찰지침서", "입찰안내서", "현장설명서", "세부유의사항",
               "입찰유의서", "instructions to bidders")),
    (DOC_BOQ, ("계약내역서", "산출내역서", "물량내역서", "내역서",
               "bill of quantities")),
    (DOC_SPEC, ("공사시방서", "특별시방서", "시방서", "specification")),
    (DOC_DRAWING, ("설계도면", "설계도서", "입찰도면", "도면", "drawings")),
    (DOC_SOW, ("과업지시서", "과업내용서", "업무기술서", "업무범위서",
               "statement of work", "scope of work")),
    (DOC_ANNEX, ("별첨", "별지", "별표", "부속합의서", "부속협정",
                 "annex", "appendix", "exhibit", "schedule")),
    (DOC_MAIN, ("공사도급계약서", "도급계약서", "본계약서", "계약서(갑지)",
                "갑지", "본 계약", "본계약", "agreement")),
)

#: 선언이 없을 때 쓰는 실무 통례 순서(앞이 우선).
DEFAULT_PRIORITY: tuple[str, ...] = (
    DOC_MAIN, DOC_SPECIAL, DOC_GENERAL, DOC_QA, DOC_BID,
    DOC_BOQ, DOC_SPEC, DOC_DRAWING, DOC_SOW, DOC_ANNEX,
)

#: 우선순위 선언 문장. "상이한 사항이 있을 경우 … 순위에 의해서 해석된다",
#: "계약문서의 우선 순위는 다음 각 호에 따른다" 등.
_RX_PRIORITY_DECLARATION = re.compile(
    r"(?:우선\s*순위|우선순위|해석\s*순위|순위에\s*의(?:해서|하여)|"
    r"우선(?:하여|한다|합니다)|상이한\s*사항|모순|불일치|"
    r"order\s+of\s+precedence|shall\s+prevail|takes?\s+precedence)",
    re.IGNORECASE,
)

#: 순위 사슬 구분자. 실무에서 ">" 가 압도적이고, "→"·"우선한다" 도 쓰인다.
_RX_CHAIN_SPLIT = re.compile(r"\s*(?:>|＞|»|→|->|➤)\s*")

#: 문서 구간의 머리. 줄 하나가 (거의) 문서 이름만으로 되어 있으면 그 지점부터
#: 새 문서가 시작된다고 본다. 조문 본문 안에서 다른 문서를 **인용**하는
#: 표현("일반조건 제22조 1항에 따른다")을 구간 시작으로 오인하면 안 되므로
#: 줄 전체 길이를 제한한다.
_MAX_HEADING_LEN = 40

#: 목차 항목을 표시하는 번호. 문서 머리는 번호 없이 이름만 온다.
_RX_LIST_MARKER = re.compile(r"^\s*(?:\d+\s*[.)]|[①-⑳]|[가-하]\s*[.)]|●|·|-\s)")


@dataclass(frozen=True)
class DocumentSection:
    """한 텍스트 안에서 식별된 문서 구간."""

    kind: str
    label: str
    heading: str
    start: int
    end: int

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "heading": self.heading,
            "start": self.start,
            "end": self.end,
            "length": self.length,
        }


def _match_doc_kind(line: str) -> tuple[str, str] | None:
    """한 줄이 문서 이름 머리인지 판정한다. (종류, 매칭된 명칭) 또는 None."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LEN:
        return None
    # 조문 머리가 붙어 있으면 문서 머리가 아니다.
    if re.search(r"제\s*\d+\s*조", stripped):
        return None
    # 번호가 붙은 줄은 계약문서 **목차**다("1. 공사계약 일반조건 및 특수조건",
    # "3. 설계도서(입찰도면)"). 목차를 구간 시작으로 보면 첨부 목록 몇 줄이
    # 하나의 문서로 잡힌다(2026-09-09 실측: "설계도면" 317자 구간).
    if _RX_LIST_MARKER.match(stripped):
        return None
    low = stripped.lower()
    for kind, names in _DOC_NAMES:
        for name in names:
            if name in low:
                # 이름 외의 잔여 글자가 많으면 문장이지 머리가 아니다.
                residual = low.replace(name, "").strip(" \t·-—:：[]()\"'“”")
                if len(residual) <= 12:
                    return kind, stripped
    return None


def detect_document_sections(text: str) -> list[DocumentSection]:
    """텍스트 안의 문서 구간을 앞에서 뒤로 식별한다.

    구간을 하나도 찾지 못하면 빈 목록을 돌려준다 — 문서가 하나뿐인 계약에서
    억지로 계층을 만들어내면 그게 오탐이 된다.
    """
    hay = text or ""
    hits: list[tuple[int, str, str]] = []
    pos = 0
    for line in hay.splitlines(keepends=True):
        matched = _match_doc_kind(line)
        if matched:
            hits.append((pos, matched[0], matched[1]))
        pos += len(line)

    if not hits:
        return []

    # 같은 종류가 연달아 나오면 첫 번째만 구간 시작으로 본다(목차·언급 반복).
    deduped: list[tuple[int, str, str]] = []
    for start, kind, heading in hits:
        if deduped and deduped[-1][1] == kind:
            continue
        deduped.append((start, kind, heading))

    sections: list[DocumentSection] = []
    for idx, (start, kind, heading) in enumerate(deduped):
        end = deduped[idx + 1][0] if idx + 1 < len(deduped) else len(hay)
        sections.append(DocumentSection(
            kind=kind, label=DOC_LABELS.get(kind, kind),
            heading=heading, start=start, end=end,
        ))
    # 목차처럼 아주 짧은 구간은 실제 문서 본문이 아니다.
    return [s for s in sections if s.length >= 200]


def declared_priority(text: str) -> list[str]:
    """계약이 선언한 문서 우선순위를 문서 종류 목록으로 돌려준다.

    선언 문장 근처에서 `A > B > C` 사슬을 찾아 각 항목을 문서 종류로 매핑한다.
    """
    hay = text or ""
    best: list[str] = []
    for m in _RX_PRIORITY_DECLARATION.finditer(hay):
        window = hay[max(0, m.start() - 400): m.end() + 400]
        for chunk in window.split("\n\n"):
            parts = _RX_CHAIN_SPLIT.split(chunk)
            if len(parts) < 3:
                continue
            order: list[str] = []
            for part in parts:
                matched = _match_doc_kind_loose(part)
                if matched and matched not in order:
                    order.append(matched)
            if len(order) > len(best):
                best = order
    return best


def _match_doc_kind_loose(fragment: str) -> str | None:
    """사슬 항목 하나를 문서 종류로 매핑한다(길이 제한 없이 이름만 본다)."""
    low = (fragment or "").lower()
    if not low.strip():
        return None
    for kind, names in _DOC_NAMES:
        for name in names:
            if name in low:
                return kind
    return None


def resolve_priority(text: str, sections: list[DocumentSection]) -> dict[str, Any]:
    """실제 적용할 우선순위를 확정한다.

    선언된 순위를 우선 쓰고, 선언에 없는데 본문에 존재하는 문서는 통례
    순서를 따라 뒤에 붙인다.
    """
    declared = declared_priority(text)
    present = [s.kind for s in sections]
    order = [k for k in declared]
    for kind in DEFAULT_PRIORITY:
        if kind in present and kind not in order:
            order.append(kind)
    for kind in present:
        if kind not in order:
            order.append(kind)
    return {
        "order": order,
        "declared": declared,
        "source": "declared" if declared else ("inferred" if order else "none"),
        "labels": [DOC_LABELS.get(k, k) for k in order],
    }


def rank_of(kind: str, order: list[str]) -> int:
    """우선순위 등수(작을수록 상위). 목록에 없으면 맨 뒤로 본다."""
    try:
        return order.index(kind)
    except ValueError:
        return len(order) + 1


def find_priority_overrides(
    text: str,
    *,
    our_role_direction: str = "",
    contract_type_code: str = "",
) -> dict[str, Any]:
    """상위 문서가 하위 문서의 위험배분을 뒤집은 축을 찾는다.

    문서 구간별로 위험배분 매트릭스를 각각 돌려서, 같은 축을 하위 문서는
    상대방 부담 또는 분담으로 두었는데 상위 문서가 우리 부담으로 돌린 경우를
    "무력화"로 본다. 축·문형 판정을 매트릭스에 위임하므로 조항번호를
    하드코딩하지 않는다.
    """
    from runtime.review.risk_allocation_matrix import (
        SIDE_COUNTERPARTY,
        SIDE_OURS,
        SIDE_SHARED,
        build_risk_allocation_matrix,
    )

    sections = detect_document_sections(text)
    priority = resolve_priority(text, sections)
    order = list(priority["order"])

    if len(sections) < 2:
        return {
            "sections": [s.to_dict() for s in sections],
            "priority": priority,
            "overrides": [],
            "multi_document": False,
            "summary": (
                "문서가 하나뿐이거나 구간을 나눌 수 없어 우선순위 검토가 필요 없습니다."
            ),
        }

    per_doc: dict[str, dict[str, Any]] = {}
    for sec in sections:
        body = (text or "")[sec.start:sec.end]
        matrix = build_risk_allocation_matrix(
            body,
            our_role_direction=our_role_direction,
            contract_type_code=contract_type_code,
        )
        per_doc[sec.kind] = {
            "section": sec,
            "rows": {r["key"]: r for r in matrix["rows"]},
        }

    _WEAKER = (SIDE_COUNTERPARTY, SIDE_SHARED)
    overrides: list[dict[str, Any]] = []
    kinds = [s.kind for s in sections]
    for high in kinds:
        for low in kinds:
            if high == low:
                continue
            if rank_of(high, order) >= rank_of(low, order):
                continue
            high_rows = per_doc[high]["rows"]
            low_rows = per_doc[low]["rows"]
            for key, hi in high_rows.items():
                lo = low_rows.get(key)
                if not lo:
                    continue
                if hi.get("side") == SIDE_OURS and lo.get("side") in _WEAKER:
                    overrides.append({
                        "axis": key,
                        "axis_label": hi.get("label") or key,
                        "higher_document": DOC_LABELS.get(high, high),
                        "higher_document_kind": high,
                        "lower_document": DOC_LABELS.get(low, low),
                        "lower_document_kind": low,
                        "lower_side": lo.get("side"),
                        "evidence_higher": str(hi.get("evidence") or "")[:300],
                        "evidence_lower": str(lo.get("evidence") or "")[:300],
                        "why": (
                            f"{DOC_LABELS.get(low, low)}에서는 이 위험이 "
                            f"우리 회사 부담이 아니었지만, 우선순위가 더 높은 "
                            f"{DOC_LABELS.get(high, high)}에서 우리 회사 부담으로 "
                            f"돌려놓았습니다. 상이한 사항은 상위 문서가 우선하므로 "
                            f"실제 부담자는 우리 회사입니다."
                        ),
                    })

    # 같은 축이 여러 문서쌍에서 중복 보고되면 가장 상위 문서 건만 남긴다.
    best_by_axis: dict[str, dict[str, Any]] = {}
    for ov in overrides:
        key = str(ov["axis"])
        cur = best_by_axis.get(key)
        if cur is None or rank_of(str(ov["higher_document_kind"]), order) < rank_of(
            str(cur["higher_document_kind"]), order
        ):
            best_by_axis[key] = ov
    deduped = sorted(
        best_by_axis.values(),
        key=lambda o: rank_of(str(o["higher_document_kind"]), order),
    )

    if deduped:
        summary = (
            f"문서 {len(sections)}종({' > '.join(priority['labels'])}) 중 상위 문서가 "
            f"하위 문서의 위험배분을 뒤집은 축 {len(deduped)}개: "
            + ", ".join(str(o["axis_label"]) for o in deduped)
        )
    else:
        summary = (
            f"문서 {len(sections)}종({' > '.join(priority['labels'])}) — 상위 문서가 "
            f"하위 문서의 보호를 무력화한 축은 확인되지 않았습니다."
        )

    return {
        "sections": [s.to_dict() for s in sections],
        "priority": priority,
        "overrides": deduped,
        "multi_document": True,
        "summary": summary,
    }


def section_for_offset(sections: list[DocumentSection], offset: int) -> DocumentSection | None:
    """주어진 위치가 속한 문서 구간. 조항을 어느 문서 소속으로 볼지 정할 때 쓴다.

    같은 파일 안에서 일반조건과 특수조건이 각각 제1조부터 다시 시작하는 계약이
    흔하다. 구간을 붙여 주지 않으면 서로 다른 두 조항이 같은 "제3조"로 보인다.
    """
    for sec in sections:
        if sec.start <= offset < sec.end:
            return sec
    return None
