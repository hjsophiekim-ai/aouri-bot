"""출력 직전 마지막 확인 — 거래모델이 처음부터 끝까지 하나로 서 있는가.

2026-09-16 지시 9항 —
  "출력 전 반드시 확인:
     · transaction model 이 일관적인가
     · 사전질문이 해당 유형에 맞는가
     · finding 이 해당 유형과 맞는가
     · 계약에 없는 사실을 만들어내지 않았는가
     · 문제점과 수정문구의 legal effect 가 일치하는가
     · canonical type 이 확정된 상태에서 '유형 미확정' 이 동시에 존재하지 않는가
   하나라도 실패하면 정상 완료하지 마세요."

왜 마지막에 또 보는가
───────────────────
각 축은 이미 자기 자리에서 한 번씩 검사된다. 그런데 **검사 시점 이후에
만들어지는 것들**이 있다 — 리스크 사슬, 에이전트 논점, 최종 재구성된
`final_findings`. v11 실측에서 앞단 비활성화를 통과한 뒤 생긴 리스크 사슬이
집행형 계약의 유일한 HIGH 로 남았다. 그래서 **출력 직전에** 같은 질문을 한
번 더 한다. 이 게이트가 보는 것은 원문이 아니라 **내보낼 결과 그 자체**다.

정상 완료로 표시하지 않는다는 것의 의미
──────────────────────────────────
다운로드를 막는다는 뜻이 아니다(2026-09-10 지시 2항 — 결함은 제거하고
전달은 계속한다). `review_status` 를 세워 문서에 "무엇이 왜 빠졌는지" 를
싣게 하고, 자동 검증을 통과한 확정본으로 표시하지 않을 뿐이다.
"""
from __future__ import annotations

import re
from typing import Any

REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH = "REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH"

#: 거래모델이 확정됐는데 이 상태가 함께 서 있으면 자기모순이다.
_TYPE_UNCERTAIN_STATUSES: frozenset[str] = frozenset({
    "REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN",
    "REVIEW_FAILED_TYPE_UNCERTAIN",
    "REVIEW_FAILED_CANONICAL_TYPE_CONFLICT",
})

#: 사용자에게 나간 질문 중 이 거래구조에서 성립하지 않는 것.
_RX_PRODUCTION_QUESTION = re.compile(
    r"2차\s*활용|2차적저작물|저작인격권|재가공|chain\s*of\s*title"
    r"|취득하는\s*지식재산|창작자[^?\n]{0,20}(?:권리|확약)",
    re.IGNORECASE,
)


def _finding_rows(final_findings: Any) -> list[dict[str, Any]]:
    """`meta["final_findings"]` 의 HIGH/MEDIUM 을 한 줄씩 펼친다."""
    ff = final_findings if isinstance(final_findings, dict) else {}
    rows: list[dict[str, Any]] = []
    for bucket in ("high_issues", "medium_issues", "low_issues"):
        for item in (ff.get(bucket) or []):
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _blob(row: dict[str, Any]) -> str:
    return "\n".join(
        str(row.get(k) or "")
        for k in ("issue_title", "clause_title", "problem", "rewrite_reason",
                  "legal_business_reason", "suggested_rewrite", "recommendation_text")
    )


def run_ad_final_consistency_gate(
    *,
    model: Any,
    meta: dict[str, Any],
    clause_results: list[dict[str, Any]] | None,
    questions: list[Any] | None = None,
) -> dict[str, Any]:
    """지시 9항의 6개 축을 출력 직전에 확인한다.

    `model` 은 `AdTransactionModel`. 광고 거래가 아니거나 거래구조를 확정하지
    못했으면 아무것도 판정하지 않는다 — 모르는 상태에서 "불일치" 를 선언하면
    정상 검토가 실패로 표시된다.
    """
    report: dict[str, Any] = {
        "applied": False,
        "checks": [],
        "failed": [],
        "status": "",
        "detail": "",
    }
    if model is None or not getattr(model, "is_media_placement", False):
        return report
    if not getattr(model, "confident", False):
        return report
    report["applied"] = True

    m = meta or {}
    crs = [
        c for c in (clause_results or [])
        if isinstance(c, dict) and not c.get("dedup_suppressed")
    ]

    def add(key: str, question: str, ok: bool, detail: str = "") -> None:
        report["checks"].append(
            {"key": key, "question": question, "ok": bool(ok), "detail": detail}
        )
        if not ok:
            report["failed"].append(key)

    # 1. transaction model 이 일관적인가 — 거래모델과 canonical 계약유형.
    canonical_type = str(
        (m.get("canonical_state") or {}).get("contract_type")
        or (m.get("legal_state") or {}).get("contract_type")
        or ""
    ).strip()
    want_type = str(getattr(model, "canonical_contract_type", "") or "")
    add(
        "model_consistent",
        "거래모델과 canonical 계약유형이 같은가?",
        canonical_type == want_type,
        f"거래모델={want_type} / canonical 계약유형={canonical_type or '(비어 있음)'}",
    )

    # 2. 사전질문이 해당 유형에 맞는가.
    bad_questions: list[str] = []
    for q in (questions or []):
        title = str(getattr(q, "title", "") or (q.get("title") if isinstance(q, dict) else ""))
        desc = str(
            getattr(q, "description", "")
            or (q.get("description") if isinstance(q, dict) else "")
        )
        qid = str(
            getattr(q, "question_id", "")
            or (q.get("question_id") if isinstance(q, dict) else "")
        )
        if _RX_PRODUCTION_QUESTION.search(f"{title}\n{desc}"):
            bad_questions.append(qid or title[:40])
    add(
        "questions_fit_model",
        "사전질문이 이 거래구조에서 성립하는가?",
        not bad_questions,
        ("상대방이 제작하지 않는데 제작계약용 질문이 나갔습니다: "
         + ", ".join(bad_questions[:5])) if bad_questions else "",
    )

    # 3. finding 이 해당 유형과 맞는가 — 출력 집합(final_findings)까지 본다.
    from runtime.review.ad_transaction_model import is_production_only_finding

    offenders: list[str] = []
    for cr in crs:
        if is_production_only_finding(_blob(cr)):
            offenders.append(str(cr.get("clause_id") or ""))
    for row in _finding_rows(m.get("final_findings")):
        if is_production_only_finding(_blob(row)):
            cid = str(row.get("clause_id") or "")
            if cid not in offenders:
                offenders.append(cid)
    add(
        "findings_fit_model",
        "finding 이 이 거래구조에서 성립하는가?",
        not offenders,
        ("상대방이 제작하지 않는데 제작계약용 논점이 남았습니다: "
         + ", ".join(offenders[:5])) if offenders else "",
    )

    # 4. 계약에 없는 사실을 만들어내지 않았는가.
    fabricated = (m.get("fabricated_artifact_gate") or {}).get("removed") or []
    add(
        "no_fabricated_facts",
        "계약에 없는 산출물·의무를 만들어내지 않았는가?",
        not fabricated,
        ("계약에 없는 것을 전제한 항목을 제거했습니다: "
         + ", ".join(str(r.get("clause_id") or "") for r in fabricated[:5]))
        if fabricated else "",
    )

    # 5. 문제점과 수정문구의 legal effect 가 일치하는가 — 이미 돌아간
    #    정합성 게이트의 **남은** 불일치만 본다. 처리된 것을 다시 세면
    #    게이트가 일할수록 검토가 실패하는 역설이 된다.
    coherence = m.get("finding_coherence_gate") or {}
    residual = [
        r for r in (coherence.get("mismatches") or [])
        if isinstance(r, dict) and str(r.get("clause_id") or "") in {
            str(c.get("clause_id") or "") for c in crs
            if str(c.get("suggested_rewrite") or "").strip()
        }
    ]
    add(
        "problem_and_rewrite_align",
        "문제점과 수정문구의 법률효과가 일치하는가?",
        not residual,
        ("수정문안이 붙은 채 남은 불일치: "
         + ", ".join(str(r.get("clause_id") or "") for r in residual[:5]))
        if residual else "",
    )

    # 6. canonical type 이 확정됐는데 "유형 미확정" 이 동시에 서 있지 않은가.
    status_now = str(m.get("review_status") or "")
    self_check_failed = set(
        (m.get("final_lawyer_self_check") or {}).get("blocking_failed") or []
    )
    contradiction = bool(canonical_type) and (
        status_now in _TYPE_UNCERTAIN_STATUSES or "contract_type" in self_check_failed
    )
    add(
        "no_type_uncertain_contradiction",
        "유형이 확정됐는데 '유형 미확정' 이 함께 서 있지 않은가?",
        not contradiction,
        (f"canonical 유형={canonical_type} 인데 상태={status_now or 'self-check contract_type 실패'}")
        if contradiction else "",
    )

    if report["failed"]:
        report["status"] = REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH
        report["detail"] = " / ".join(
            f"{c['question']} — {c['detail']}"
            for c in report["checks"] if not c["ok"]
        )[:600]
    return report
