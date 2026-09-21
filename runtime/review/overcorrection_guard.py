"""수정안이 현재 문구보다 우리 회사에 불리하면 제안하지 않는다.

2026-09-21 3차 지시 4항 —
  "수정안은 기존보다 우리 회사에 불리해지지 않는지 반드시 비교하세요.
   현재는 일반 개발사·시험기관 제공은 허용하고 핵심기술만 사전승인인데,
   이를 모든 제3자 제공에 사전승인을 요구하도록 바꾸면 우리 회사의 활용
   자유를 축소하므로 수정 금지. 우리 회사에 불리해지면 KEEP_EXISTING_CLAUSE."
  13항 "이미 균형 잡힌 조항은 우리 회사 책임을 넓히는 방향으로 재작성하지
        마세요."

왜 이런 일이 생기는가
──────────────────
체크리스트는 "보호 장치가 있는가" 를 본다. 그래서 "모든 제3자 제공에 사전
서면 동의" 같은 **가장 빡빡한 문구**를 표준 해답으로 들고 있다. 그 문구는
정보를 **주는** 쪽에는 유리하지만, 받아서 국내 개발사와 함께 쓰려는 쪽에는
족쇄다. 우리가 어느 쪽인지 보지 않으면, 사업부가 애써 풀어 놓은 조항을
다시 조여서 돌려주게 된다.

무엇을 비교하는가
───────────────
문구의 좋고 나쁨이 아니라 **우리 회사의 자유와 의무**다.

    현재 문구 → 제안 문구 → 우리의 권리·의무 변화

· 우리 쪽 의무·제한을 늘리는 낱말이 늘었는가(사전 승인, 금지, 책임, 배상)
· 우리 쪽 허용·예외를 줄였는가(할 수 있다, 제외한다, 다만)

강행법규 준수를 위한 수정은 막지 않는다 — 유리함보다 적법함이 앞선다
(v7 지시).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

KEEP_EXISTING_CLAUSE = "KEEP_EXISTING_CLAUSE"

#: 우리 쪽 의무·제한을 늘리는 문형.
_RX_BURDEN = re.compile(
    r"사전\s*(?:서면\s*)?(?:승인|동의)|승인을\s*받아야|동의를\s*받아야"
    r"|하여서는\s*아니\s*된다|할\s*수\s*없다|금지한다|제한한다"
    r"|책임을\s*(?:부담|진다)|배상(?:하여야|한다)|보증한다|부담한다"
    r"|통지하여야|제출하여야|이행하여야"
)

#: 우리 쪽 자유·예외를 나타내는 문형.
_RX_FREEDOM = re.compile(
    r"할\s*수\s*있다|허용(?:된다|한다)|제외(?:한다|된다)|그러하지\s*아니하다"
    r"|다만|적용하지\s*아니한다|제한되지\s*않는다|필요하지\s*아니하다"
)

#: 강행법규 준수를 위한 수정 — 유불리로 막지 않는다.
_RX_MANDATORY_BASIS = re.compile(
    r"강행(?:법규|규정)|무효|위법|법령\s*위반|약관규제법|불공정\s*약관"
    r"|산업안전보건법|중대재해|개인정보\s*보호법|하도급법|공정거래법"
)

#: 이 정도 차이는 표현 차이로 본다.
_DELTA_TOLERANCE = 1


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _counts(text: str) -> tuple[int, int]:
    body = _norm(text)
    return len(_RX_BURDEN.findall(body)), len(_RX_FREEDOM.findall(body))


@dataclass
class OvercorrectionReport:
    withdrawn: list[dict[str, Any]] = field(default_factory=list)
    checked: int = 0

    @property
    def detail(self) -> str:
        if not self.withdrawn:
            return ""
        names = ", ".join(
            f"{w['display_path'] or w['clause_id']}" for w in self.withdrawn[:4]
        )
        return (
            f"현재 문구보다 우리 회사에 불리해지는 수정안 {len(self.withdrawn)}건을 "
            f"거두고 현행 유지로 정리했습니다 — {names}."
        )


def evaluate_proposal(original: str, proposal: str) -> dict[str, Any]:
    """현재 문구 대비 제안 문구가 우리 회사에 어떤 변화를 주는가."""
    o_burden, o_freedom = _counts(original)
    p_burden, p_freedom = _counts(proposal)
    burden_delta = p_burden - o_burden
    freedom_delta = p_freedom - o_freedom
    worse = (
        burden_delta > _DELTA_TOLERANCE and freedom_delta <= 0
    ) or (
        freedom_delta < -_DELTA_TOLERANCE and burden_delta >= 0
    )
    return {
        "burden_before": o_burden,
        "burden_after": p_burden,
        "freedom_before": o_freedom,
        "freedom_after": p_freedom,
        "burden_delta": burden_delta,
        "freedom_delta": freedom_delta,
        "worse_for_us": worse,
    }


def guard_overcorrection(
    clause_results: list[dict[str, Any]],
    *,
    our_role_direction: str = "",
) -> OvercorrectionReport:
    """제안 문구가 현재보다 우리에게 불리하면 거두고 현행 유지로 돌린다.

    지적 자체는 남긴다 — 담당자는 "이 쟁점을 봤고, 현재 문구가 더 낫다"
    는 판단을 받아야 한다.
    """
    report = OvercorrectionReport()
    if not isinstance(clause_results, list):
        return report

    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        if bool(cr.get("is_new_clause")) or bool(cr.get("keep_as_is")):
            continue
        # 실재하는 조항에 붙어 있을 때만 비교한다. 위치가 확정되지 않은
        # 항목은 "현재 문구" 가 무엇인지 모르므로 유불리를 따질 수 없다 —
        # 실측: 상대방에게 지연이자 지급 의무를 지우는 정당한 권고가
        # 의무 낱말 개수만으로 우리에게 불리하다고 잘못 판정됐다.
        if bool(cr.get("clause_reference_unresolved")):
            continue
        if not str(cr.get("article_number") or "").strip():
            continue
        original = _norm(cr.get("original_text"))
        proposal = _norm(
            cr.get("suggested_rewrite")
            or cr.get("proposed_revision")
            or cr.get("recommendation_text")
        )
        if len(original) < 40 or len(proposal) < 40:
            continue
        basis = " ".join(
            _norm(cr.get(k))
            for k in ("problem", "legal_business_reason", "rewrite_reason")
        )
        if _RX_MANDATORY_BASIS.search(basis):
            continue  # 적법성을 위한 수정은 유불리로 막지 않는다
        report.checked += 1
        verdict = evaluate_proposal(original, proposal)
        if not verdict["worse_for_us"]:
            continue

        cr["keep_as_is"] = True
        cr["scope_verdict"] = KEEP_EXISTING_CLAUSE
        cr["risk_tier"] = "LOW"
        cr["severity"] = "LOW"
        cr["review_tier"] = "NOTE"
        cr["must_fix"] = False
        cr["approval_required"] = False
        cr["overcorrection_guard"] = {
            **verdict,
            "reason": (
                "제안 문구가 현재 문구보다 우리 회사의 의무·제한을 넓히거나 "
                "활용 자유를 좁힙니다. 현행 문언을 유지하는 편이 유리하여 "
                "수정 제안을 거두었습니다."
            ),
        }
        for field_name in ("suggested_rewrite", "proposed_revision", "recommendation_text"):
            if cr.get(field_name):
                cr[field_name] = ""
        report.withdrawn.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            **verdict,
        })
    return report
