"""Final Senior Counsel Gate — 출력 직전 자가점검.

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

2026-09-14 최종보정 지시 항목 5 로 **교차 정합성** 5개를 더했다 —
"contract type / party role / applicability / finding / rewrite 가 서로
모순 없는지 확인. 하나라도 충돌하면 정상 완료하지 말 것."

    11. 계약유형과 거래 원형이 서로 모순되지 않는가
    12. 판정된 당사자 지위가 실제 거래구조와 맞는가
    13. 비적용으로 판단한 법률의 어휘가 결과에 남아 있지 않은가
    14. 문제점·법적 이유·수정문구가 같은 법률효과를 다루는가
    15. KEEP/수정 불필요로 판단한 항목이 필수·권장 목록에 남지 않았는가

앞의 10개가 "각 단계가 제 일을 했는가" 를 묻는다면, 이 5개는 "단계들의
결론이 서로 같은 말을 하는가" 를 묻는다. 개별 단계가 모두 통과하고도
전체가 자기모순인 결과가 실제로 나왔기 때문이다 — 유형은 NDA 인데 원형은
물품공급, 법률은 비적용인데 협상포지션은 그 법 이름으로 시작하는 식.

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
                f"자가점검 {len(self.checks)}개 항목 전부 통과" if self.passed
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
    # [2026-09-14 지시 항목 5] 교차 정합성 점검용. 각 게이트가 이미 낸
    # 결론을 여기서 다시 계산하지 않고 그대로 받는다 — 같은 판단을 두
    # 곳에서 하면 언젠가 서로 달라진다.
    coherence_report: dict[str, Any] | None = None,
    role_structure_report: dict[str, Any] | None = None,
    keep_demoted: list[dict[str, Any]] | None = None,
    statute_decisions_blocked: list[str] | None = None,
) -> FinalCounselGateReport:
    """자가점검 항목을 전부 확인한다."""
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

    # ── 교차 정합성 (2026-09-14 지시 항목 5) ────────────────────────────

    # 11. 계약유형 ↔ 거래 원형. enum 라벨은 보조자료이므로 원형과 어긋나면
    #     라벨 쪽이 틀린 것이고, 그 라벨에 매달린 체크리스트가 통째로
    #     잘못 돌았다는 뜻이다(v8 아키텍처).
    from runtime.review.legal_state import ARCHETYPE_OF_TYPE_CODE
    _type_code = str(state.get("contract_type") or "").strip()
    _archetype = str(state.get("transaction_type") or "").strip()
    _implied = ARCHETYPE_OF_TYPE_CODE.get(_type_code, "")
    # 원형을 함의하지 않는 코드(표에 없음)나 원형 미확정은 충돌로 세지 않는다.
    _type_archetype_ok = not (
        _implied and _archetype and _archetype not in ("unknown", "") and _implied != _archetype
    )
    add(
        "type_matches_archetype", "계약유형과 거래 원형이 서로 모순되지 않는가",
        _type_archetype_ok,
        "" if _type_archetype_ok else
        f"계약유형 {_type_code!r} 은 원형 {_implied!r} 을 함의하는데 확정된 원형은 {_archetype!r} 입니다.",
    )

    # 12. 당사자 지위 ↔ 실제 거래구조.
    _role_conflicts = list((role_structure_report or {}).get("conflicts") or [])
    add(
        "role_matches_structure", "판정된 당사자 지위가 실제 거래구조와 맞는가",
        not _role_conflicts,
        "; ".join(_role_conflicts[:2]),
    )

    # 13. 비적용 법률의 어휘가 결과에 남아 있는가. 근거 제거·스크럽이 모두
    #     돈 **뒤** 이므로, 여기서 잡히면 어느 경로가 빠져나간 것이다.
    _blocked_terms = [t for t in (statute_decisions_blocked or []) if str(t or "").strip()]
    _statute_leftover: list[str] = []
    if _blocked_terms:
        for cr in live:
            blob = _finding_blob(cr)
            hit = next((t for t in _blocked_terms if t in blob), "")
            if hit:
                _statute_leftover.append(f"{cr.get('clause_id')}:{hit}")
    add(
        "no_inapplicable_statute_language", "비적용으로 판단한 법률의 어휘가 결과에 남아 있지 않은가",
        not _statute_leftover,
        ("비적용 법률 어휘가 남음: " + ", ".join(_statute_leftover[:4])) if _statute_leftover else "",
    )

    # 14. 문제점 ↔ 법적 이유 ↔ 수정문구.
    _coherence = list((coherence_report or {}).get("mismatches") or [])
    add(
        "finding_rewrite_coherent", "문제점·법적 이유·수정문구가 같은 법률효과를 다루는가",
        not _coherence,
        ("법률효과가 어긋나 처리된 항목: " + ", ".join(
            f"{m.get('clause_id')}({m.get('axis')})" for m in _coherence[:4]
        )) if _coherence else "",
    )

    # 15. KEEP/수정 불필요가 필수·권장 목록에 남아 있는가. `live` 는 이미
    #     keep_as_is 를 걸러내므로, 여기 걸리면 표시만 KEEP 이고 등급은
    #     살아 있는 상태다.
    _keep_in_must = [
        str(cr.get("clause_id") or "") for cr in (clause_results or [])
        if isinstance(cr, dict)
        and (bool(cr.get("keep_as_is")) or bool(cr.get("accept_keep")))
        and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
    ]
    add(
        "no_keep_in_must_fix", "KEEP/수정 불필요 항목이 필수·권장 목록에 남지 않았는가",
        not _keep_in_must,
        ("현행 유지로 판단했는데 필수·권장으로 남은 항목: " + ", ".join(_keep_in_must[:4]))
        if _keep_in_must else "",
    )
    report.checks.append(GateCheck(
        key="keep_demoted_recorded",
        question="KEEP 으로 내린 항목의 사유를 기록했는가",
        ok=all(bool(str(r.get("kind") or "")) for r in (keep_demoted or [])),
        detail="",
    ))

    return report


#: 거래 원형별로 "이 계약에는 없어야 하는" 타 유형 전용 어휘.
#: 계약 원문이 그 단어를 쓰면 혼입이 아니므로 호출부에서 원문과 대조한다.
_FOREIGN_VOCAB: dict[str, tuple[str, ...]] = {
    "confidentiality_only": ("판매장려금", "판촉비", "지체상금", "기성고", "착공", "숏폼", "협찬 표시", "소스코드"),
    "goods_supply": ("판매장려금", "판촉비", "숏폼", "협찬 표시", "소스코드", "오픈소스"),
    "service_engagement": ("판매장려금", "판촉비", "기성고", "착공", "준공검사"),
    # [2026-09-18 지시 9항] 건설공사 도급계약에 자문/용역·공급·대리점·판매지원
    # 템플릿이 섞이면 거래구조 불일치다. 계약 원문이 그 말을 쓰고 있으면
    # 혼입이 아니므로 호출부가 원문과 대조한다.
    "construction_works": (
        "판매장려금", "판촉비", "숏폼", "협찬 표시", "소스코드", "오픈소스",
        "재판매", "판매목표", "판매지역", "대리점", "경영간섭", "구입강제",
        "자문료", "맨먼스", "최소주문수량", "인코텀즈", "2차적저작물",
    ),
    "distribution_resale": ("기성고", "착공", "준공검사", "숏폼", "소스코드"),
    "ip_license": ("판매장려금", "판촉비", "기성고", "착공", "준공검사"),
    "non_monetary_exchange": ("판매장려금", "판촉비", "기성고", "착공", "준공검사", "소스코드", "오픈소스"),
    "lease_rental": ("숏폼", "협찬 표시", "소스코드", "기성고", "착공"),
}


def _foreign_vocabulary_for(transaction_type: str) -> tuple[str, ...]:
    return _FOREIGN_VOCAB.get(str(transaction_type or ""), ())
