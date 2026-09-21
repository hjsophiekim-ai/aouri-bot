"""Finding 내부 정합성 게이트 — 문제점 · 법적 이유 · 수정문구는 **같은 법률효과**를 다뤄야 한다.

2026-09-14 지시(범용 최종보정) 항목 1 —
  "각 finding 의 문제점, 법적 이유, 수정문구가 동일한 legal effect 를 다뤄야
   한다. 서로 다른 주제가 섞이면 즉시 REVIEW_FAILED_SEMANTIC_MISMATCH.
   예: 추가과업 이슈에 저작권 문구, 제품 인도 이슈에 콘텐츠 검수 문구 삽입 금지."

기존 게이트와 무엇이 다른가
─────────────────────────
이미 두 개의 semantic 게이트가 있었지만 둘 다 **축이 다르다**.

  · `finding_integrity_gates.enforce_clause_semantic_gate()`
        원문 조항의 효과  ↔  제안 문안의 효과
    그 함수는 설명 필드(problem/rewrite_reason)를 **일부러 제외**한다 —
    "왜 보는가" 는 계약에 삽입될 문장이 아니기 때문이다.

  · `clause_level` 의 clause_topic guardrail
        원문 조항의 topic  ↔  제안 문안의 topic

둘 다 비교 대상의 한쪽이 **원문 조항**이다. 그래서 한 조항이 여러 주제를
담고 있으면(대부분의 총칙·정산·해지 조항이 그렇다) "문제점은 추가과업을
말하는데 문안은 저작권을 넣는" finding 이 두 게이트를 모두 통과한다 —
저작권도 추가과업도 그 조항 어딘가에 걸쳐 있기 때문이다.

이 모듈은 원문을 보지 않고 **finding 자신의 세 부분끼리** 대조한다.
담당자가 받는 것은 "이 문제 때문에 이 문구로 고치라" 는 한 덩어리이므로,
그 세 부분이 서로 다른 이야기를 하면 근거와 문안이 어긋난 것이고 협상에
쓸 수 없다.

두 개의 축으로 본다
──────────────────
  (1) 법률효과(`legal_effect_taxonomy`) — 무엇을 하는 조항인가
  (2) 주제(`clause_topic`)             — 어느 영역의 이야기인가

한쪽 축이라도 "서로 다른 이야기" 라고 판정하면 mismatch 다. 다만 양쪽 모두
**판정을 내렸을 때만** 비교한다 — 태그가 비어 있는 것은 "효과 없음" 이 아니라
"의견 없음" 이므로 그것으로 무엇을 지우면 안 된다(`effects_overlap` 규약).

처리 방식
────────
  · 계약 원문을 직접 확인해 만든 finding(`is_common_legal_risk`), 구조
    분석 finding(`is_risk_package`), 사내변호사 에이전트 논점
    (`is_counsel_agent`) → **문안만 회수**하고 문제 제기는 남긴다.
    이 셋은 문제 제기 자체가 계약 문언·구조에 묶여 있어 유효하다. 틀린
    것은 거기 붙은 문안이다.
  · 그 밖(AI 조항검토·체크리스트 주입) → **finding 을 삭제**한다. 근거가
    문안과 어긋나면 남는 것이 없다.

어느 쪽이든 `REVIEW_FAILED_SEMANTIC_MISMATCH` 로 기록되고, 문서 말미
"자동 검증에서 보류·제외된 항목" 에 무엇이 왜 빠졌는지 실린다. 조용히
사라지지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.clause_topic import (
    TOPIC_OTHER,
    classify_clause_topic,
    infer_rewrite_topics,
    is_topic_compatible,
)
from runtime.review.delivery_gate import withdraw_proposal
from runtime.review.legal_effect_taxonomy import (
    LEGAL_EFFECT_TAGS,
    effects_overlap,
    infer_legal_effects,
)

STATUS_SEMANTIC_MISMATCH = "REVIEW_FAILED_SEMANTIC_MISMATCH"

#: 문제 제기가 계약 문언·구조에 묶여 있어, 문안만 회수하고 남겨야 하는 finding.
# `is_construction_checklist` 도 같은 이유로 예외다. 건설 체크리스트 항목은
# 하나의 위험이 대금·공기·책임에 동시에 걸쳐 있어(예: "설계변경 → 계약금액
# 조정 절차 부재" 는 문제점이 payment, 제안 문안이 sow_change 로 잡힌다)
# 단일 topic 라벨로 접으면 반드시 어긋난다. 실측: CWC-01 이 이 축에서
# 문안을 회수당했다(2026-09-18).
_STRUCTURAL_FLAGS = (
    "is_common_legal_risk", "is_risk_package", "is_counsel_agent",
    "is_construction_checklist",
)

#: 세 부분을 이루는 필드. 순서가 곧 사람이 읽는 순서다.
_PROBLEM_FIELDS = ("issue_title", "problem")
_REASON_FIELDS = ("legal_business_reason", "rewrite_reason")
#: 확실히 "계약에 넣자고 제안하는 문장" 인 필드.
_REWRITE_FIELDS = ("suggested_rewrite", "proposed_revision")
_REDLINE_FIELDS = ("replacement_text", "final_clause_text")
#: `recommendation_text` 는 경로에 따라 제안 문안일 때도, 서술형 권고일 때도,
#: **원문 조항 그대로** 일 때도 있다(실측: 영문 라이선스 계약의 효과 기반
#: finding 에 Article 1 전문이 들어와 있었다). 원문 사본을 제안 문안으로
#: 읽으면 그 조항의 온갖 효과가 "제안된 효과" 로 잡혀 정상 finding 이
#: 불일치로 삭제된다. 그래서 확실한 필드가 하나도 없을 때만, 그리고 원문
#: 사본이 아닐 때만 쓴다.
_FALLBACK_REWRITE_FIELD = "recommendation_text"


def _join(cr: dict[str, Any], keys: tuple[str, ...]) -> str:
    parts = [str(cr.get(k) or "").strip() for k in keys]
    return "\n".join(p for p in parts if p)


def _squash(text: str) -> str:
    return "".join(str(text or "").split())


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _is_copy_of_original(candidate: str, original: str) -> bool:
    """제안 문안 자리에 원문이 그대로 들어와 있는가."""
    c, o = _squash(candidate), _squash(original)
    if len(c) < 40 or len(o) < 40:
        return False
    return c in o or o in c


def _added_part(text: str, original: str) -> str:
    """제안 문안에서 **원문을 뺀 나머지**, 즉 실제로 더해진 문장.

    `minimal_edit.apply_minimal_edit()` 은 원문의 법률효과를 유지한 채 절차·
    한도·예외만 덧붙이는 식으로 문안을 만든다. 그래서 제안 문안 안에 원문이
    통째로 들어 있고, 그것을 그대로 태깅하면 **원문의 온갖 효과**가 "제안된
    효과" 로 잡힌다. 실측(대물교환 계약): 개인정보 동의근거 누락 지적에
    "존속조항 원문 + 개인정보 근거를 명시한다" 가 붙었는데, 원문 쪽의
    저작권·초상권·비밀유지가 제안 효과로 잡혀 정상 finding 이 삭제됐다.

    비교해야 하는 것은 **이 finding 이 계약에 새로 넣자고 하는 문장**이다.
    """
    t, o = _collapse(text), _collapse(original)
    if len(o) >= 40 and o in t:
        return t.replace(o, " ").strip()
    return text


def _rewrite_text(cr: dict[str, Any]) -> str:
    parts = [_join(cr, _REWRITE_FIELDS)]
    ri = cr.get("redline_instruction")
    if isinstance(ri, dict):
        parts.append(_join(ri, _REDLINE_FIELDS))
    text = "\n".join(p for p in parts if p.strip())
    if not text.strip():
        fallback = str(cr.get(_FALLBACK_REWRITE_FIELD) or "")
        if fallback.strip() and not _is_copy_of_original(
            fallback, str(cr.get("original_text") or "")
        ):
            text = fallback
    original = str(cr.get("original_text") or "")
    # 확실한 필드에 들어온 값이라도 원문 사본이면 비교 대상이 아니다.
    if _is_copy_of_original(text, original):
        return ""
    return _added_part(text, original)


def _declared(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if isinstance(x, str) and x in LEGAL_EFFECT_TAGS]


def _is_structural(cr: dict[str, Any]) -> bool:
    return any(bool(cr.get(flag)) for flag in _STRUCTURAL_FLAGS)


def assess_finding_coherence(cr: dict[str, Any]) -> dict[str, Any]:
    """finding 한 건의 세 부분이 같은 이야기를 하는지 본다.

    돌려주는 dict 의 `mismatch` 가 False 면 정합이거나 판단 근거가 없는 것이다
    (둘을 구분해 쓸 일이 없으므로 같이 묶는다 — 어느 쪽이든 지우지 않는다).
    """
    problem = _join(cr, _PROBLEM_FIELDS)
    reason = _join(cr, _REASON_FIELDS)
    rewrite = _rewrite_text(cr)

    out: dict[str, Any] = {
        "mismatch": False,
        "axis": "",
        "reason_text": "",
        "problem_effects": [],
        "reason_effects": [],
        "rewrite_effects": [],
        "problem_topic": "",
        "rewrite_topics": [],
    }
    # 비교할 양쪽이 다 있어야 비교가 성립한다. 수정문구가 없는 항목(검토의견
    # 전용·이미 회수된 항목)은 이 게이트의 대상이 아니다.
    if not problem.strip() or not rewrite.strip():
        return out

    # 선언된 태그와 추론된 태그를 **합집합**으로 쓴다.
    #
    # 종전에는 선언 태그가 있으면 그것만 썼다. 그런데 선언 태그는 그 finding 을
    # 만든 쪽이 한 가지 관점에서 붙인 한두 개짜리 라벨이라 대개 불완전하다 —
    # 실측(퍼시스 NDA): 개인정보 경계조항 신설 rule 이 제안 문안에
    # `confidentiality` 하나만 선언해 두어, 문제점의 `personal_data_protection`
    # 과 겹치지 않는 것으로 읽혔다. 문안 자체를 읽으면 두 태그가 다 나온다.
    #
    # 겹침 판정에서 태그가 늘어나는 것은 항상 **덜 지우는** 방향이다. 선언과
    # 추론이 서로를 보완하게 두는 것이 이 게이트의 성격(오탐 하나가 정당한
    # 검토의견을 지운다)에 맞다.
    def _effects(declared_key: str, text: str) -> list[str]:
        return sorted(set(_declared(cr.get(declared_key))) | set(infer_legal_effects(text)))

    pe = _effects("problem_effect_tags", problem)
    we = _effects("rewrite_effect_tags", rewrite)
    re_ = _effects("reason_effect_tags", reason)
    out["problem_effects"], out["reason_effects"], out["rewrite_effects"] = pe, re_, we

    # (1) 문제점 ↔ 수정문구. 지시가 든 예가 바로 이 축이다.
    if pe and we and not effects_overlap(pe, we):
        out.update({
            "mismatch": True,
            "axis": "problem_vs_rewrite",
            "reason_text": (
                f"문제점이 다루는 법률효과({', '.join(pe)})와 수정문구가 만들어내는 "
                f"법률효과({', '.join(we)})가 서로 다릅니다."
            ),
        })
        return out

    # (2) 법적 이유 ↔ (문제점 ∪ 수정문구) — **기록만 하고 지우지 않는다.**
    #
    #     법적 이유는 "왜 이것이 문제인가" 를 적는 자리이고, 그 설명은 거의
    #     항상 **다른 영역으로 번지는 결과**를 든다 — "검수 판정 기준이 없으면
    #     검수권이 자의적 거절권이 되어 대금 지급과 납기가 동시에 불안정해진다"
    #     처럼. 이것은 혼입이 아니라 리스크 사슬을 제대로 쓴 문장이다.
    #     겹침을 요구하면 잘 쓴 이유일수록 먼저 걸린다(실측: 대물교환 계약의
    #     검수기준 finding 이 이 축에서 삭제됐다).
    #
    #     그래서 이 축은 삭제 사유가 아니라 **자가점검 기록**으로 남긴다.
    #     지시가 요구한 "세 부분이 같은 법률효과" 중 강제되는 것은 문제점 ↔
    #     수정문구이고, 법적 이유는 어긋난 사실을 보고하는 데까지 한다.
    context = sorted(set(pe) | set(we))
    if re_ and context and not effects_overlap(re_, context):
        out["reason_axis_note"] = (
            f"법적 이유가 다루는 법률효과({', '.join(re_)})가 문제점·수정문구의 "
            f"법률효과({', '.join(context)})와 겹치지 않습니다."
        )

    # (3) 주제 축 — **법률효과가 판단을 내리지 못했을 때만** 본다.
    #
    #     `classify_clause_topic()` 은 텍스트 하나에 topic 을 **한 개**만 준다.
    #     실무 문안은 대개 여러 주제를 한 문단에 담으므로(검수 절차 + 대금 보류,
    #     추가과업 승인 + 대금 보류), 그 한 개가 앞쪽 분기에 먼저 걸린 주제로
    #     정해지고 나머지는 사라진다. 그 상태로 문제점의 topic 과 비교하면
    #     정상 finding 이 불일치로 판정된다(실측: 콘텐츠 제작 계약 CP-002/003 —
    #     법률효과는 payment_obligation 으로 양쪽이 일치하는데 topic 은
    #     payment_settlement ↔ sow_change 로 갈렸다).
    #
    #     그래서 이 축은 효과 축의 **보조**로만 쓴다. 양쪽 다 효과 태그가 붙어
    #     있고 겹쳤다면 그것이 더 정확한 판단이므로 뒤집지 않는다. 효과 태그가
    #     한쪽이라도 비어 있어 판단이 서지 않은 경우에만 topic 으로 본다 —
    #     실측 로그의 cost_burden ↔ sow_change 혼입이 그 경우다.
    #
    #     그리고 계약 문언·구조를 직접 확인해 만든 finding(결정론적 rule·리스크
    #     사슬·사내변호사 논점)은 이 축의 대상이 아니다. 이들은 애초에 여러
    #     주제에 걸쳐 판단하는 것이 정상이라 단일 topic 라벨로 접으면 반드시
    #     어긋난다 — `clause_level` 의 clause_topic guardrail 이 is_risk_package
    #     를 같은 이유로 예외 처리하는 것과 동일한 근거다. 실측(AI hold-out,
    #     공사도급): 세무 축 counsel 논점이 termination ↔ sow_change 로 갈려
    #     문안이 회수됐다.
    if (pe and we) or _is_structural(cr):
        return out
    pt = classify_clause_topic(title=None, text=problem)
    wt = infer_rewrite_topics(rewrite_text=rewrite)
    out["problem_topic"] = pt
    out["rewrite_topics"] = sorted(wt)
    if (
        pt != TOPIC_OTHER
        and wt
        and not is_topic_compatible(clause_topic=pt, rewrite_topics=wt)
    ):
        out.update({
            "mismatch": True,
            "axis": "problem_topic_vs_rewrite_topic",
            "reason_text": (
                f"문제점의 주제({pt})와 수정문구의 주제({', '.join(sorted(wt))})가 "
                "서로 다릅니다."
            ),
        })
    return out


def enforce_finding_coherence(
    clause_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """세 부분이 어긋난 finding 을 삭제하거나 문안을 회수한다.

    돌려주는 리포트: {"status", "detail", "mismatches", "removed_count",
    "withdrawn_count"}. `status` 가 비어 있으면 어긋난 항목이 없었다는 뜻이다.
    """
    report: dict[str, Any] = {
        "status": "",
        "detail": "",
        "mismatches": [],
        # 법적 이유 축은 삭제 사유가 아니라 기록이다(assess_finding_coherence 주석).
        "reason_axis_notes": [],
        "removed_count": 0,
        "withdrawn_count": 0,
    }
    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            kept.append(cr)
            continue

        verdict = assess_finding_coherence(cr)
        if verdict.get("reason_axis_note"):
            note = {
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "note": str(verdict["reason_axis_note"]),
            }
            report["reason_axis_notes"].append(note)
            cr["reason_axis_note"] = note["note"]
        if not verdict.get("mismatch"):
            kept.append(cr)
            continue

        entry = {
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:80],
            "axis": verdict["axis"],
            "reason": verdict["reason_text"],
            "problem_effects": verdict["problem_effects"],
            "reason_effects": verdict["reason_effects"],
            "rewrite_effects": verdict["rewrite_effects"],
            "problem_topic": verdict["problem_topic"],
            "rewrite_topics": verdict["rewrite_topics"],
            "stage": "finding_coherence_gate",
            "status": STATUS_SEMANTIC_MISMATCH,
        }
        report["mismatches"].append(entry)
        cr["finding_coherence_mismatch"] = entry

        if _is_structural(cr):
            # 문제 제기는 계약 문언·구조에 묶여 있어 유효하다. 틀린 것은 문안뿐.
            withdraw_proposal(cr, status=STATUS_SEMANTIC_MISMATCH, reason=verdict["reason_text"])
            entry["remediation"] = "proposal_withdrawn"
            report["withdrawn_count"] += 1
            kept.append(cr)
            continue

        entry["remediation"] = "finding_removed"
        report["removed_count"] += 1

    clause_results[:] = kept

    if report["mismatches"]:
        report["status"] = STATUS_SEMANTIC_MISMATCH
        report["detail"] = (
            "문제점·법적 이유·수정문구의 법률효과가 일치하지 않는 검토의견 "
            f"{len(report['mismatches'])}건을 처리했습니다"
            f"(삭제 {report['removed_count']}건, 문안 회수 {report['withdrawn_count']}건): "
            + "; ".join(
                f"{m['clause_id']}({m['axis']})" for m in report["mismatches"][:5]
            )
        )
    return report
