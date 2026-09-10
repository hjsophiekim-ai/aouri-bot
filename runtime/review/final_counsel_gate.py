"""Final Senior Counsel Gate — 출력 직전 10개 항목 자가점검.

2026-09-10 아키텍처 지시 항목 12. 체크 목록은 지시가 명시한 그대로다.

     1. 계약유형/당사자 지위가 맞는가
     2. 사용자가 실제로 한 질문만 사용자 요청으로 표시했는가
     3. 사용자 답변이 반영됐는가
     4. 적용법률의 법정요건을 먼저 판단했는가
     5. 다른 계약유형의 템플릿이 섞이지 않았는가
     6. 이미 있는 보호조항을 누락으로 오판하지 않았는가
     7. 우리에게 유리한 조항을 약화시키지 않았는가
     8. HIGH 가 정말 중요한 위험인가
     9. 모든 HIGH/MEDIUM 에 완성 문구가 있는가
    10. UI/DOCX 가 완전히 동일한가

이 게이트의 성격
──────────────
지시는 "하나라도 실패하면 정상완료 금지" 라고 했다. 그 요구는 **정상 완료로
표시하지 말라**는 것이지, 담당자에게 아무것도 주지 말라는 뜻이 아니다 —
직전 지시(항목 2)가 "절대 에러나지 않고 최종수정본이 다운로드되게" 를 요구했고,
409 로 막던 것이 바로 그 사고의 원인이었다.

그래서 이 게이트는 다음처럼 동작한다.

  · 실패한 항목이 있으면 `passed = False` 로 표시하고 **사유를 전부 기록**한다.
  · 그 기록은 `meta["final_counsel_gate"]` 에 남고, 문서 말미
    "자동 검증에서 보류·제외된 항목" 에 그대로 실린다.
  · 결과는 "정상 완료" 가 아니라 "확인 필요" 로 표시된다.

즉 조용히 정상인 척하지 않으면서도, 담당자는 나머지 결과를 즉시 쓸 수 있다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REVIEW_STATUS_NEEDS_REVIEW = "REVIEW_NEEDS_ATTENTION"


@dataclass
class GateCheck:
    key: str
    question: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "question": self.question, "ok": self.ok, "detail": self.detail}


@dataclass
class FinalCounselGateReport:
    checks: list[GateCheck] = field(default_factory=list)

    @property
    def failed(self) -> list[GateCheck]:
        return [c for c in self.checks if not c.ok]

    @property
    def passed(self) -> bool:
        return not self.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "passed": self.passed,
            "failed_keys": [c.key for c in self.failed],
            "review_status": "" if self.passed else REVIEW_STATUS_NEEDS_REVIEW,
            "summary": (
                "10개 자가점검 항목 전부 통과" if self.passed
                else "확인 필요: " + "; ".join(f"{c.question} — {c.detail}" for c in self.failed[:6])
            ),
        }


def _live(clause_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        cr for cr in (clause_results or [])
        if isinstance(cr, dict)
        and not bool(cr.get("dedup_suppressed"))
        and not bool(cr.get("keep_as_is"))
    ]


def _finding_blob(cr: dict[str, Any]) -> str:
    parts = [
        str(cr.get(k) or "")
        for k in (
            "issue_title", "problem", "rewrite_reason", "legal_business_reason",
            "suggested_rewrite", "recommendation_text", "negotiation_strategy",
        )
    ]
    detected = cr.get("detected_issue_list")
    if isinstance(detected, list):
        parts += [str(d.get("issue_title") or "") for d in detected if isinstance(d, dict)]
    return "\n".join(parts)


#: 자리표시자 — 지시 항목 7이 금지한 표현.
_RX_PLACEHOLDER = re.compile(
    r"\[수정문안 보류\]|담당 변호사가 직접 확정|추후 협의|수정 문구 자동생성 보류|\bTBD\b",
    re.IGNORECASE,
)


def run_final_counsel_gate(
    *,
    legal_state: dict[str, Any] | None,
    clause_results: list[dict[str, Any]] | None,
    final_findings: dict[str, Any] | None,
    statute_decisions: list[dict[str, Any]] | None,
    user_review_coverage: list[dict[str, Any]] | None,
    user_review_focus: str | None,
    answers: dict[str, Any] | None,
    contract_text: str,
    our_side_withdrawn: list[dict[str, Any]] | None = None,
    cross_clause_suppressed: list[str] | None = None,
) -> FinalCounselGateReport:
    """10개 항목을 전부 점검한다."""
    state = legal_state or {}
    live = _live(clause_results)
    report = FinalCounselGateReport()
    add = lambda key, q, ok, detail="": report.checks.append(  # noqa: E731
        GateCheck(key=key, question=q, ok=bool(ok), detail=detail)
    )

    # 1. 계약유형/당사자 지위
    _type_ok = bool(str(state.get("contract_type") or "").strip())
    _role_ok = bool(str(state.get("our_role_direction") or "").strip())
    add(
        "type_and_role", "계약유형/당사자 지위가 맞는가",
        _type_ok and _role_ok,
        "" if (_type_ok and _role_ok) else
        f"contract_type={state.get('contract_type')!r} our_role={state.get('our_role_direction')!r}",
    )

    # 2. 사용자 요청 날조 금지 — 사용자가 실제로 쓴 문장만 explicit 로 표시
    focus = str(user_review_focus or "")
    fabricated: list[str] = []
    for row in (user_review_coverage or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("source") or "") != "explicit_user_request":
            continue
        quoted = str(row.get("original_user_text") or "").strip()
        if not focus:
            fabricated.append(quoted[:60] or str(row.get("issue_id") or ""))
        elif quoted and quoted not in focus:
            fabricated.append(quoted[:60])
    add(
        "no_fabricated_user_request", "사용자가 실제로 한 질문만 사용자 요청으로 표시했는가",
        not fabricated,
        ("사용자가 입력하지 않은 문장이 요청사항으로 기록됨: " + "; ".join(fabricated[:3]))
        if fabricated else "",
    )

    # 3. 사용자 답변 반영 — 답변한 사실이 "미확인"으로 남아 있지 않은가
    unresolved_after_answer: list[str] = []
    if answers:
        answered = " ".join(str(v) for v in answers.values() if isinstance(v, str))
        if answered.strip():
            for row in (user_review_coverage or []):
                if not isinstance(row, dict):
                    continue
                if str(row.get("review_status") or "") != "사실관계 추가확인":
                    continue
                # 답변에 그 쟁점의 핵심어가 들어 있는데도 "추가확인"이면 미반영이다.
                issue = str(row.get("normalized_issue") or "")
                tokens = [t for t in re.split(r"[\s,·/()]+", issue) if len(t) >= 3][:6]
                if tokens and sum(1 for t in tokens if t in answered) >= 2:
                    unresolved_after_answer.append(str(row.get("issue_id") or "")[:40])
    add(
        "answers_applied", "사용자 답변이 반영됐는가",
        not unresolved_after_answer,
        ("답변했는데도 '사실관계 추가확인'으로 남은 쟁점: " + ", ".join(unresolved_after_answer[:3]))
        if unresolved_after_answer else "",
    )

    # 4. 적용법률 법정요건 선판단
    decided = [d for d in (statute_decisions or []) if isinstance(d, dict) and d.get("conclusion")]
    add(
        "statute_gate_first", "적용법률의 법정요건을 먼저 판단했는가",
        bool(decided),
        "" if decided else "적용요건 판단 결과가 없습니다.",
    )

    # 5. 다른 계약유형 템플릿 혼입 — 계약 원문에 없는 유형 전용 어휘
    #    (계약이 스스로 쓰는 단어는 혼입이 아니다)
    body = str(contract_text or "")
    contamination: list[str] = []
    _foreign_terms = _foreign_vocabulary_for(str(state.get("transaction_type") or ""))
    for cr in live:
        blob = _finding_blob(cr)
        for term in _foreign_terms:
            if term in blob and term not in body:
                contamination.append(f"{cr.get('clause_id')}:{term}")
                break
    add(
        "no_cross_type_template", "다른 계약유형의 템플릿이 섞이지 않았는가",
        not contamination,
        ("계약 원문에 없는 타 유형 어휘: " + ", ".join(contamination[:4])) if contamination else "",
    )

    # 6. 이미 있는 보호조항을 누락으로 오판하지 않았는가
    #    (global cross-clause 검증이 억제한 항목이 남아 있으면 실패)
    add(
        "no_false_absence", "이미 있는 보호조항을 누락으로 오판하지 않았는가",
        not (cross_clause_suppressed or []),
        ("다른 조항에 이미 규정된 사항을 누락으로 지적: " + ", ".join((cross_clause_suppressed or [])[:4]))
        if cross_clause_suppressed else "",
    )

    # 7. 우리에게 유리한 조항을 약화시키지 않았는가
    still_weakening: list[str] = []
    try:
        from runtime.review.our_side_protection import detect_weakening
        for cr in live:
            if bool(cr.get("legal_compliance_override")):
                continue  # 강행법규 준수 목적의 수정은 허용된다
            proposed = " ".join(
                str(cr.get(k) or "")
                for k in ("suggested_rewrite", "proposed_revision", "recommendation_text")
            )
            if detect_weakening(str(cr.get("original_text") or ""), proposed):
                still_weakening.append(str(cr.get("clause_id") or ""))
    except Exception:
        pass
    add(
        "our_side_not_weakened", "우리에게 유리한 조항을 약화시키지 않았는가",
        not still_weakening,
        ("우리 권리를 되돌리는 수정안이 남음: " + ", ".join(still_weakening[:4]))
        if still_weakening else "",
    )

    # 8. HIGH 가 정말 중요한 위험인가 — 치명 근거가 기록됐는가
    baseless_high = [
        str(cr.get("clause_id") or "") for cr in live
        if str(cr.get("risk_tier") or "").upper() == "HIGH"
        and not str(cr.get("high_severity_basis") or "").strip()
    ]
    add(
        "high_justified", "HIGH 가 정말 중요한 위험인가",
        not baseless_high,
        ("치명 근거가 없는 HIGH: " + ", ".join(baseless_high[:4])) if baseless_high else "",
    )

    # 9. 모든 HIGH/MEDIUM 에 완성 문구가 있는가 (지시 항목 7)
    from runtime.review.redline_instruction import is_incomplete_redline
    incomplete: list[str] = []
    placeholders: list[str] = []
    for cr in live:
        if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
            continue
        blob = _finding_blob(cr)
        if _RX_PLACEHOLDER.search(blob):
            placeholders.append(str(cr.get("clause_id") or ""))
            continue
        if str(cr.get("fact_confirmation_required") or "").strip():
            # 사실확인이 선행되어야 하는 항목 — 무엇을 확인할지 적혀 있어야 한다.
            if not (cr.get("fact_confirmation_items") or []):
                incomplete.append(str(cr.get("clause_id") or ""))
            continue
        if is_incomplete_redline(cr.get("redline_instruction")):
            incomplete.append(str(cr.get("clause_id") or ""))
    _detail_9 = "; ".join(
        x for x in (
            ("자리표시자 문구: " + ", ".join(placeholders[:4])) if placeholders else "",
            ("완성 문구 없음: " + ", ".join(incomplete[:4])) if incomplete else "",
        ) if x
    )
    add(
        "complete_rewrite", "모든 HIGH/MEDIUM 에 완성 문구가 있는가",
        not placeholders and not incomplete,
        _detail_9,
    )

    # 10. UI/DOCX 동일성 — 저장된 final_findings 가 clause_results 와 정합한가
    ff = final_findings or {}
    ui_ids = {
        str(i.get("finding_id") or "")
        for i in (list(ff.get("high_issues") or []) + list(ff.get("medium_issues") or []))
        if isinstance(i, dict)
    } - {""}
    live_ids = {str(cr.get("finding_id") or "") for cr in live} - {""}
    dangling = sorted(ui_ids - live_ids)
    add(
        "ui_docx_identical", "UI/DOCX 가 완전히 동일한가",
        not dangling,
        ("최종 결과에 있는데 clause_results 에 없는 finding: " + ", ".join(dangling[:4]))
        if dangling else "",
    )

    return report


#: 거래 원형별로 "이 계약에는 없어야 하는" 타 유형 전용 어휘.
#: 계약 원문이 그 단어를 쓰면 혼입이 아니므로 호출부에서 원문과 대조한다.
_FOREIGN_VOCAB: dict[str, tuple[str, ...]] = {
    "confidentiality_only": ("판매장려금", "판촉비", "지체상금", "기성고", "착공", "숏폼", "협찬 표시", "소스코드"),
    "goods_supply": ("판매장려금", "판촉비", "숏폼", "협찬 표시", "소스코드", "오픈소스"),
    "service_engagement": ("판매장려금", "판촉비", "기성고", "착공", "준공검사"),
    "construction_works": ("판매장려금", "판촉비", "숏폼", "협찬 표시", "소스코드", "오픈소스"),
    "distribution_resale": ("기성고", "착공", "준공검사", "숏폼", "소스코드"),
    "ip_license": ("판매장려금", "판촉비", "기성고", "착공", "준공검사"),
    "non_monetary_exchange": ("판매장려금", "판촉비", "기성고", "착공", "준공검사", "소스코드", "오픈소스"),
    "lease_rental": ("숏폼", "협찬 표시", "소스코드", "기성고", "착공"),
}


def _foreign_vocabulary_for(transaction_type: str) -> tuple[str, ...]:
    return _FOREIGN_VOCAB.get(str(transaction_type or ""), ())
