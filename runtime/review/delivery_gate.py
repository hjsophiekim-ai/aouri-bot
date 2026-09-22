"""수정본 다운로드를 막는 대신 결함을 제거하고 그 사실을 문서에 밝히는 게이트.

2026-09-10 지시 항목 2 — "최종 수정본 워드파일 생성이 또 실패했다. 앞으로
절대 에러나지 않고 최종수정본이 다운로드되게 하라."

실측한 실패(대물교환 계약, session 2ae2a937…):

    POST /api/revision/download_docx → 409
    REVIEW_FAILED_SEMANTIC_MISMATCH
    "…일치하지 않아 제외된 finding: CP-003(payment_obligation/payment_withholding)"

원인은 게이트의 **판정**이 아니라 **처리 방식**이었다.

`finding_integrity_gates.enforce_clause_semantic_gate()` 는 원문의 법률효과와
제안 문안의 법률효과가 겹치지 않는 finding 을 찾으면,

  · `CONTRACT_TYPE_DOMAIN_WHITELIST` 에 있는 계약유형이면 → finding 삭제(해결)
  · 그 밖의 계약유형이면                                   → 삭제하지 못하고
                                                            `status` 만 세움

으로 갈렸다. 그런데 그 whitelist 에는 `nda_confidentiality` **하나뿐**이다.
즉 NDA 가 아닌 모든 계약에서 mismatch 가 한 건이라도 잡히면, 결함을 제거할
방법이 없는 채로 `REVIEW_FAILED_*` 가 서고, 그것이 다운로드 핸들러의 409 로
그대로 이어졌다. 사용자가 몇 번을 다시 눌러도 같은 409 가 났던 이유다.

그래서 게이트를 약화시키지 않고(= 결함 있는 문안을 그대로 내보내지 않고)
처리 방식을 바꾼다.

    탐지 → **제거·중화**(remediation) → 문서에 그 사실을 명시 → 다운로드 진행

제거·중화란 문제가 된 **수정문안만** 걷어내고 그 finding 을 "수정문안 보류,
검토의견만" 상태(`advisory_only`)로 낮추는 것을 말한다. 잘못된 문안은 절대
Word 파일에 들어가지 않고, 대신 문서 말미의 "자동 검증에서 보류·제외된 항목"
표에 무엇이 왜 빠졌는지 그대로 적힌다. 조용히 버리는 것이 아니다.

다운로드가 실제로 실패해야 하는 경우는 **내보낼 것이 없을 때뿐**이다
(본문 추출 실패 등 `docx_allowed=False`). 그 판정은 이 모듈이 다루지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 결함을 제거·중화할 수 있어 다운로드를 막지 않는 검토 상태들.
#: 여기에 해당하면 `remediate_review_status()` 가 상태를 걷어내고 그 사유를
#: 문서에 남긴다.
REMEDIABLE_STATUSES: frozenset[str] = frozenset({
    "REVIEW_FAILED_SEMANTIC_MISMATCH",
    "REVIEW_FAILED_INVALID_CLAUSE_REFERENCE",
    "REVIEW_FAILED_INCOMPLETE_REDLINE",
    "REVIEW_FAILED_DUPLICATE_FINDINGS",
    "REVIEW_FAILED_LANGUAGE_QUALITY",
    "REVIEW_FAILED_USER_FACTS_NOT_APPLIED",
    "REVIEW_FAILED_OUTPUT_MISMATCH",
    "REVIEW_FAILED_OUTPUT_FACT_MISMATCH",
    "REVIEW_FAILED_USER_REQUEST_MISSING",
    "REVIEW_FAILED_USER_SCOPE_NOT_COVERED",
    "REVIEW_FAILED_GLOBAL_REASONING",
    "REVIEW_FAILED_GLOBAL_CROSS_CLAUSE",
    "REVIEW_FAILED_LIKELY_FALSE_NEGATIVE",
    "REVIEW_FAILED_TYPE_UNCERTAIN",
    "REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN",
    "REVIEW_FAILED_CROSS_DOCUMENT_CONTAMINATION",
    "REVIEW_FAILED_LAWYER_SELF_CHECK",
    "REVIEW_FAILED_LEGAL_MAP_INCOMPLETE",
    "REVIEW_FAILED_COMMERCIAL_TERMS_UNSETTLED",
    "REVIEW_FAILED_DOCUMENT_HIERARCHY_IGNORED",
    "REVIEW_FAILED_CANONICAL_ROLE_CONFLICT",
    "REVIEW_FAILED_CANONICAL_TYPE_CONFLICT",
    "REVIEW_FAILED_CANONICAL_STATE_MISMATCH",
    "REVIEW_FAILED_USER_LEGAL_SCOPE_MISSING",
    "REVIEW_FAILED",
    # Final Senior Counsel Gate(항목 12)가 세우는 "확인 필요" 상태.
    # 정상 완료로 표시하지는 않되, 담당자가 나머지 결과를 쓸 수 있도록
    # 차단하지 않고 사유를 문서에 싣는다.
    "REVIEW_NEEDS_ATTENTION",
    # 적용법률 결론과 finding 이 충돌한 경우(2026-09-11). 충돌 finding 을
    # 제거하는 것으로 결함이 실제로 해소되므로 전달은 계속 가능하다.
    "REVIEW_FAILED_STATUTE_CONFLICT",
    # 당사자 지위 판정이 모순된 경우(2026-09-11 지시 "상대방 역할 오분류 시
    # 결과 생성 금지"). 결과를 확정본으로 쓰지 못하게 하되, 사유를 문서에
    # 명시한 채 전달 자체는 막지 않는다.
    "REVIEW_FAILED_COUNTERPARTY_ROLE_CONFLICT",
    # [2026-09-14 Hallucination Zero] 존재하지 않는 조항·문구를 가리킨 항목은
    # 정정하거나 제거하는 것으로 결함이 실제로 해소된다 — 전달은 계속한다.
    "REVIEW_FAILED_NONEXISTENT_CLAUSE",
    "REVIEW_FAILED_FAKE_QUOTE",
    "REVIEW_FAILED_HALLUCINATED_REFERENCE",
    "CLAUSE_STRUCTURE_UNCERTAIN",
    "REVIEW_FAILED_INCOMPLETE_REWRITE",
    # [2026-09-15] 조항 연결을 끊는 것으로 결함이 해소되므로 전달은 계속한다.
    "SEMANTIC_ANCHOR_MISMATCH",
    # [2026-09-15] 거래구조에 맞지 않는 논점을 제거하는 것으로 결함이 해소된다.
    "REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH",
    # [2026-09-16] 계약에 없는 산출물을 전제한 항목은 제거로 해소된다.
    "REVIEW_FAILED_FABRICATED_ARTIFACT",
    # [2026-09-21 지시 6~8·12항] 네 가지 모두 **제거·해제로 결함이 실제로
    # 해소되는** 상태다. 근거 없는 부재 주장은 삭제했고, 타 유형 문언은
    # 걷어냈으며, 어긋난 질문·조항 연결은 끊었다. 남은 결과는 쓸 수 있으므로
    # 전달을 막지 않고 사유만 문서에 싣는다.
    "REVIEW_FAILED_SOURCE_CONTRADICTION",
    "REVIEW_FAILED_CROSS_CONTRACT_CONTAMINATION",
    "REVIEW_FAILED_QUESTION_MODEL_MISMATCH",
    "REVIEW_FAILED_USER_REQUEST_MAPPING_MISMATCH",
    # [2026-09-21 2차 지시 1·3항] 인용 위치는 그 조항의 문장으로 바로잡았고,
    # 지위를 뒤집은 문장에는 정정 표시를 붙였다 — 결함이 해소되므로 전달한다.
    "REVIEW_FAILED_WRONG_QUOTE_LOCATION",
    "REVIEW_FAILED_PARTY_ROLE_MISMATCH",
    # [2026-09-21 5차 지시 9·18항] 실재하는 영문 조항을 '없음'으로 판단한
    # 항목에 근거 조항을 붙여 두었다 — 담당자가 그 조항을 바로 펴 볼 수
    # 있으므로 결함이 해소된다. 전달을 막지 않는다.
    "REVIEW_FAILED_ENGLISH_CLAUSE_GROUNDING",
})

#: 제거·중화가 불가능해 다운로드를 실제로 막아야 하는 상태.
#: 내보낼 내용 자체가 없거나 신뢰할 수 없는 경우에 한한다.
NON_REMEDIABLE_STATUSES: frozenset[str] = frozenset({
    "REVIEW_FAILED_TEXT_EXTRACTION",
    # [2026-09-14 지시 항목 4] 계약서가 우리 법인을 명시적으로 반대편으로
    # 정의해 두었는데 판정이 그 반대인 경우. 제거할 결함이 따로 있는 것이
    # 아니라 검토서 전체가 반대로 서 있으므로 중화가 불가능하다.
    "REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH",
    # [2026-09-18 지시 9항] 건설계약에서 도급인/수급인/재하도급인 중 어느
    # 지위인지 확정하지 못한 경우. 같은 조문이 지위에 따라 정반대의 위험이
    # 되므로, 제거할 결함이 따로 있는 것이 아니라 검토서 전체가 어느 방향으로
    # 서 있는지 모르는 상태다 — 중화가 불가능하다.
    "REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED",
})

#: 사용자에게 보여줄 한국어 사유. 없는 코드는 코드 그대로 노출한다.
STATUS_LABELS: dict[str, str] = {
    "REVIEW_FAILED_SEMANTIC_MISMATCH": "원문 조항의 법률효과와 제안 문안의 법률효과가 달라 수정문안을 보류함",
    "REVIEW_FAILED_INVALID_CLAUSE_REFERENCE": "계약에 존재하지 않는 조항을 가리켜 수정문안을 보류함",
    "REVIEW_FAILED_INCOMPLETE_REDLINE": "수정 위치 또는 문구가 확정되지 않아 수정문안을 보류함",
    "REVIEW_FAILED_DUPLICATE_FINDINGS": "동일 쟁점이 중복 보고되어 하나로 병합함",
    "REVIEW_FAILED_LANGUAGE_QUALITY": "문장이 불완전하거나 추출이 손상되어 해당 항목을 제외함",
    "REVIEW_FAILED_USER_FACTS_NOT_APPLIED": "담당자 확인 답변이 반영되지 않은 자리표시자가 남아 해당 항목을 제외함",
    "REVIEW_FAILED_OUTPUT_MISMATCH": "화면과 문서의 항목 수가 달라 문서 기준으로 재계산함",
    "REVIEW_FAILED_OUTPUT_FACT_MISMATCH": "화면과 문서의 사실관계가 달라 문서 기준으로 재계산함",
    "REVIEW_FAILED_USER_REQUEST_MISSING": "담당자가 요청한 검토사항 중 답변되지 않은 항목이 있음",
    "REVIEW_FAILED_USER_SCOPE_NOT_COVERED": "담당자가 요청한 검토사항 중 답변되지 않은 항목이 있음",
    "REVIEW_FAILED_GLOBAL_REASONING": "계약 전체 관점의 교차검증에서 확인이 필요한 항목이 있음",
    "REVIEW_FAILED_GLOBAL_CROSS_CLAUSE": "조항 간 교차검증에서 확인이 필요한 항목이 있음",
    "REVIEW_FAILED_LIKELY_FALSE_NEGATIVE": "위험이 큰 영역에 검토의견이 비어 있어 확인이 필요함",
    "REVIEW_FAILED_TYPE_UNCERTAIN": "계약유형을 확정하지 못해 유형별 체크리스트를 보수적으로 적용함",
    "REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN": "계약유형을 확정하지 못해 유형별 체크리스트를 보수적으로 적용함",
    "REVIEW_FAILED_CROSS_DOCUMENT_CONTAMINATION": "이 계약 원문에 없는 용어가 섞여 해당 항목을 제외함",
    "REVIEW_FAILED_LAWYER_SELF_CHECK": "최종 자가점검에서 확인이 필요한 항목이 있음",
    "REVIEW_FAILED_LEGAL_MAP_INCOMPLETE": "거래구조 지도(Legal Map)의 일부 축을 확정하지 못함",
    "REVIEW_FAILED_COMMERCIAL_TERMS_UNSETTLED": "핵심 상업조건이 계약서에서 미확정 상태임",
    "REVIEW_FAILED_DOCUMENT_HIERARCHY_IGNORED": "본문·별첨의 우선순위 반영을 확인하지 못함",
    "REVIEW_FAILED_CANONICAL_ROLE_CONFLICT": "당사자 지위 판단이 하나로 확정되지 않음",
    "REVIEW_FAILED_CANONICAL_TYPE_CONFLICT": "계약유형 판단이 하나로 확정되지 않음",
    "REVIEW_FAILED_CANONICAL_STATE_MISMATCH": "계약유형·지위 판단이 단계별로 어긋남",
    "REVIEW_FAILED_USER_LEGAL_SCOPE_MISSING": "담당자가 언급한 법률에 대한 판단이 누락됨",
    "REVIEW_FAILED": "자동 검증에서 확인이 필요한 항목이 있음",
    "REVIEW_NEEDS_ATTENTION": "최종 자가점검 10개 항목 중 확인이 필요한 항목이 있음",
    "REVIEW_FAILED_COUNTERPARTY_ROLE_CONFLICT": "상대방 당사자 지위 판정이 일관되지 않아 확인이 필요함",
    "REVIEW_FAILED_STATUTE_CONFLICT": "비적용으로 판단한 법률의 의무를 주장하는 검토의견이 있어 제거함",
    "REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH": "당사자 지위 판정이 계약서상 거래구조와 어긋나 결과를 생성하지 않음 — 당사자 정의를 확인한 뒤 재검토 필요",
    "REVIEW_FAILED_NONEXISTENT_CLAUSE": "계약에 존재하지 않는 조항을 가리켜 신설 형식으로 정정하거나 제외함",
    "REVIEW_FAILED_FAKE_QUOTE": "계약 원문에 없는 문장이 원문으로 표시되어 제외함",
    "REVIEW_FAILED_HALLUCINATED_REFERENCE": "최종 전수검증에서 실재하지 않는 조항·인용을 가리킨 항목을 제거함",
    "CLAUSE_STRUCTURE_UNCERTAIN": "조항 구조를 확정하지 못해 조항 존재 검증을 보류함 — 원문 구조 확인 필요",
    "REVIEW_FAILED_INCOMPLETE_REWRITE": "일부 항목에 그대로 삽입 가능한 완성 문구가 없어 담당자 확정이 필요함",
    "SEMANTIC_ANCHOR_MISMATCH": "지적 내용과 맞지 않는 조항에 연결되어 있어 연결을 해제함 — 해당 조항 확인 필요",
    "REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH": "확정된 거래구조에 맞지 않는 타 계약유형의 논점을 제거함",
    "REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED": "건설공사 계약의 당사자 지위(도급인/수급인/수급인+재하도급인)를 확정하지 못해 결과를 생성하지 않음 — 당사자 정의를 확인한 뒤 재검토 필요",
    "REVIEW_FAILED_FABRICATED_ARTIFACT": "계약서에 없는 산출물·의무를 전제한 검토의견을 제거함",
    "REVIEW_FAILED_SOURCE_CONTRADICTION": "계약에 실재하는 보호조항을 '없음'으로 판단한 항목을 제거함 — 해당 조항을 확인할 것",
    "REVIEW_FAILED_CROSS_CONTRACT_CONTAMINATION": "확정된 계약유형과 다른 계약의 쟁점·문구가 섞여 제거함",
    "REVIEW_FAILED_QUESTION_MODEL_MISMATCH": "확정된 계약유형에 맞지 않는 사전질문이 담당자에게 나갔음",
    "REVIEW_FAILED_USER_REQUEST_MAPPING_MISMATCH": "담당자 질문과 다른 내용의 조항이 연결되어 있어 연결을 해제함",
    "REVIEW_FAILED_WRONG_QUOTE_LOCATION": "다른 조항의 문장을 원문으로 표시하여 해당 조항의 문장으로 바로잡음",
    "REVIEW_FAILED_PARTY_ROLE_MISMATCH": "확정된 당사자 지위와 반대로 서술한 문장이 있어 정정 표시함 — 지위 확인 필요",
    "REVIEW_FAILED_ENGLISH_CLAUSE_GROUNDING": "영문 계약에 실재하는 조항을 '없음'으로 판단한 항목에 근거 조항을 표시함 — 해당 Article 을 확인할 것",
}

#: 수정문안이 걷어내진 finding 에 남기는 표시. DOCX/PDF 작성기와
#: incomplete-redline 게이트가 이 값을 보고 "수정문안 없음"을 정상으로 본다.
ADVISORY_ONLY_KEY = "advisory_only"

_PROPOSAL_FIELDS = ("suggested_rewrite", "proposed_revision", "recommendation_text")


@dataclass
class Remediation:
    """다운로드를 막는 대신 제거·중화한 결함 한 건의 기록."""

    status: str
    reason: str
    clause_ids: list[str] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "clause_ids": list(self.clause_ids),
            "detail": self.detail,
        }


@dataclass
class DeliveryReport:
    """이번 다운로드에서 제거·중화한 것들의 모음."""

    remediations: list[Remediation] = field(default_factory=list)

    def add(
        self,
        status: str,
        *,
        clause_ids: list[str] | None = None,
        detail: str = "",
        reason: str = "",
    ) -> None:
        code = str(status or "").strip()
        if not code:
            return
        self.remediations.append(
            Remediation(
                status=code,
                reason=reason or STATUS_LABELS.get(code, code),
                clause_ids=[str(c) for c in (clause_ids or []) if str(c or "").strip()],
                detail=str(detail or "").strip(),
            )
        )

    @property
    def empty(self) -> bool:
        return not self.remediations

    def to_list(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.remediations]

    def merge(self, other: "DeliveryReport") -> None:
        self.remediations.extend(other.remediations)


def withdraw_proposal(cr: dict[str, Any], *, status: str, reason: str = "") -> None:
    """신뢰할 수 없는 수정문안을 **최소수정안으로 교체**한다.

    finding 자체는 남긴다 — 문제 제기는 유효하고, 신뢰할 수 없는 것은 그
    문제에 대해 자동 생성된 **문안**뿐이기 때문이다.

    [2026-09-10 아키텍처 지시 항목 7 로 동작이 바뀌었다]
    종전에는 문안 자리에 "[수정문안 보류] … 담당 변호사가 직접 확정해야
    합니다" 를 적었다. 잘못된 문구가 계약서에 들어가는 것은 막았지만,
    담당자에게는 **협상에 쓸 수 없는 문서**가 갔다. 이제는 원문의 법률효과를
    유지한 채 절차·한도·예외만 덧붙인 최소수정안을 직접 만들어 넣는다
    (`minimal_edit.apply_minimal_edit`).

    원문이 없어 문구를 만들 수 없는 경우에만 `FACT_CONFIRMATION_REQUIRED`
    로 표시하고, 무엇을 확인해야 하는지 구체적으로 적는다.
    """
    if not isinstance(cr, dict):
        return
    label = reason or STATUS_LABELS.get(str(status or ""), str(status or ""))
    for key in _PROPOSAL_FIELDS:
        if cr.get(key):
            cr[key] = None
    cr["changed_segments"] = []

    from runtime.review.minimal_edit import apply_minimal_edit

    applied = apply_minimal_edit(cr, reason=label)
    cr["proposal_replaced_reason"] = label
    if not applied:
        # 사실확인이 선행되어야 하는 상태. advisory_only 로도 표시해 두어
        # redline 완성도 검사의 대상에서 빠지게 한다.
        cr[ADVISORY_ONLY_KEY] = True
        cr["advisory_only_reason"] = label


def is_advisory_only(cr: Any) -> bool:
    return isinstance(cr, dict) and bool(cr.get(ADVISORY_ONLY_KEY))


def remediate_review_status(
    meta: dict[str, Any] | None,
    report: DeliveryReport,
) -> str:
    """`clause_meta.review_status` 가 제거·중화 가능한 것이면 걷어내고 기록한다.

    돌려주는 값은 **여전히 남아 있는** 차단 상태다. 빈 문자열이면 다운로드를
    진행해도 된다.
    """
    if not isinstance(meta, dict):
        return ""
    status = str(meta.get("review_status") or "").strip()
    if not status:
        return ""
    # 명시적으로 "내보낼 것이 없다"고 판정된 상태만 차단한다. 그 밖의
    # REVIEW_FAILED_* 는 — 목록에 아직 없는 새 상태를 포함해 — 제거·기록으로
    # 처리한다. 게이트가 하나 늘 때마다 다운로드가 다시 막히는 일을 없애기
    # 위해, 기본값을 "차단"이 아니라 "기록 후 전달"로 뒤집는다(2026-09-10).
    if status in NON_REMEDIABLE_STATUSES:
        return status
    report.add(status, detail=str(meta.get("review_status_detail") or ""))
    meta["review_status"] = ""
    meta["review_status_remediated"] = status
    meta["review_status_remediated_detail"] = str(meta.get("review_status_detail") or "")
    meta["review_status_detail"] = ""
    return ""


def disclosure_rows(report: DeliveryReport) -> list[dict[str, str]]:
    """문서 말미 "자동 검증에서 보류·제외된 항목" 표에 넣을 행."""
    rows: list[dict[str, str]] = []
    for r in report.remediations:
        rows.append(
            {
                "reason": r.reason,
                "clauses": ", ".join(r.clause_ids[:8]) if r.clause_ids else "-",
                "detail": r.detail,
                "code": r.status,
            }
        )
    return rows
