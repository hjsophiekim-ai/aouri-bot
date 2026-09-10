"""우리에게 유리한 기존 조항을 수정안이 되돌리지 못하게 한다.

2026-09-10 지시 — "우리 회사에 유리한 기존 조항을 약화시키지 말 것. 현재
조항이 우리 회사에 유리하고 법적으로 문제없으면 ACCEPT 처리. 굳이 상대방
청구권이나 비용청구권을 새로 열어주는 수정 금지."

실측 사례 (대물교환 콘텐츠 계약, 제5조 제4항)
────────────────────────────────────────
원문:

    ④ "을"은 어떠한 경우에도 본 계약을 이유로 "갑"에게
       제작비, 출연료, 채널 운영비, 광고비 기타 명목의 금전 지급을
       청구할 수 없다.

이 조항은 우리(갑)에게 전면적으로 유리하다 — 상대방의 금전 청구를
원천 차단한다. 그런데 수정안은 이렇게 나갔다.

    … 청구할 수 없다. **단, 쌍방이 사전에 서면으로 합의한 비용 항목에
    한하여 … 청구가 가능하며** …

"정산 절차를 명확히 한다"는 좋은 의도의 템플릿이지만, 실제 효과는 **없던
상대방 청구권을 새로 열어주는 것**이다. 협상 테이블에 그대로 가져가면 우리
쪽에서 먼저 양보안을 제시하는 셈이 된다.

판정 방식
────────
원문이 상대방의 청구·권리를 **차단**하고 있는데(전면 부정형), 수정안이
그 차단에 **예외를 신설**하면(다만/단서 + 청구 가능) 그 수정안은 적용하지
않는다. 문제 제기 자체는 남긴다 — 정산 절차가 불명확하다는 지적이 틀린
것은 아니고, 다만 그 해법을 우리 권리를 깎는 방향으로 자동 생성하지 않을
뿐이다.

특정 계약·조항 번호를 하드코딩하지 않는다. "차단 → 예외 신설"이라는 문형
관계만 본다.

강행법규 준수가 우선한다 (2026-09-10 추가 지시)
──────────────────────────────────────────
"우리에게 유리하니 그대로 두자"가 **법을 어겨도 된다**는 뜻은 아니다. 우리
계약서가 하도급법·대리점법·대규모유통업법·공정거래법 등 강행법규에 어긋나는
방식으로 상대방에게 불이익을 주고 있다면, 그 조항은 유리하더라도 **법을
준수하도록 고쳐야 한다**. 그런 수정안은 이 보호의 대상이 아니다.

두 원칙의 경계는 이렇게 잡는다.

  · 수정 근거가 **적용되는** 강행법규의 위반 시정이면      → 보호하지 않는다(수정 유지)
  · 그저 "형평성·균형" 같은 일반론이거나, 애초에 **비적용**으로
    확정된 법률을 근거로 든 것이면                        → 보호한다(문안 회수)

적용 여부는 `statute_applicability_gate` 가 이미 판단한 결과를 그대로 쓴다 —
비적용으로 확정된 법률을 근거로 우리 권리를 깎는 일이 없도록 하기 위함이다.
"""
from __future__ import annotations

import re
from typing import Any

#: 원문이 상대방의 청구·권리를 원천 차단하는 문형.
_RX_ORIGINAL_FORECLOSES = re.compile(
    r"(?:청구|요구|주장)할\s*수\s*없다"
    r"|(?:지급|부담|보상|배상)하지\s*아니한다"
    r"|(?:지급|부담|보상|배상)하지\s*않는다"
    r"|권리를\s*(?:갖지|가지지)\s*(?:아니한다|않는다)"
    r"|일체의?\s*책임을\s*지지\s*(?:아니한다|않는다)",
)

#: 그 차단에 예외를 여는 문형 — 단서로 상대방의 청구를 되살린다.
_RX_REWRITE_REOPENS = re.compile(
    r"(?:다만|단)[,\s].{0,120}?"
    r"(?:청구(?:가|할\s*수)?\s*(?:가능|있다|있으며|할\s*수\s*있)"
    r"|지급(?:한다|하여야|해야|할\s*수\s*있)"
    r"|부담(?:한다|하여야|해야)"
    r"|보상(?:한다|하여야|해야))",
    re.DOTALL,
)

#: 예외의 여지를 남기지 않는 **전면** 금지. 여기에 단서가 붙으면, 그 단서가
#: 어떤 동사로 끝나든 조항은 조건부로 약해진다.
_RX_ABSOLUTE_PROHIBITION = re.compile(
    r"(?:어떠한\s*경우에도|일체의?|전혀|어떤\s*명목으로도|여하한)[^.\n]{0,80}?"
    r"(?:할\s*수\s*없다|하지\s*(?:아니한다|않는다)|없다)",
)

#: 단서·예외를 여는 표지.
_RX_EXCEPTION_MARKER = re.compile(
    r"(?:^|[.\s])(?:다만|단)[,\s]"
    r"|에\s*한하여|한\s*경우에만|경우에\s*한(?:하여|한다)|를\s*제외하고|except",
    re.IGNORECASE,
)

#: 거래상 지위 남용을 규율하는 강행법규. 이 법들이 **적용되는** 계약에서
#: 우리 조항이 위법하면, 유리하더라도 준수하도록 고쳐야 한다.
MANDATORY_FAIRNESS_STATUTES: tuple[str, ...] = (
    "하도급법",
    "하도급거래 공정화에 관한 법률",
    "대리점법",
    "대리점거래의 공정화에 관한 법률",
    "대규모유통업법",
    "대규모유통업에서의 거래 공정화에 관한 법률",
    "공정거래법",
    "독점규제 및 공정거래에 관한 법률",
    "가맹사업법",
    "약관규제법",
    "약관의 규제에 관한 법률",
)

#: 그 법의 **위반을 시정**한다는 신호. 법률명만 스쳐도 예외를 열어주면
#: 보호가 무력해지므로, 위법성 판단 어휘가 함께 있어야 한다.
_RX_VIOLATION_LANGUAGE = re.compile(
    r"위반|위법|무효|금지(?:규정|행위|된다|하고)|불공정\s*거래행위|거래상\s*지위\s*남용"
    r"|부당(?:하게|한|성)|시정명령|과징금|강행규정|효력이\s*없",
)

WEAKENING_STATUS = "OUR_SIDE_RIGHT_WEAKENED"
WEAKENING_REASON = (
    "원문이 상대방의 청구를 차단하고 있는데 수정안이 예외를 신설해 "
    "우리 회사에 유리한 현행 조항을 약화시켜 적용을 보류함"
)

_PROPOSAL_FIELDS = ("suggested_rewrite", "proposed_revision", "recommendation_text")


def _proposed(cr: dict[str, Any]) -> str:
    return "\n".join(str(cr.get(k) or "") for k in _PROPOSAL_FIELDS)


def detect_weakening(original_text: str, proposed_text: str) -> bool:
    """원문의 차단을 수정안이 되돌리는가.

    두 가지를 본다.

    1. 차단 문형 + 청구를 되살리는 단서 (명시적)
    2. **전면 금지**("어떠한 경우에도 … 청구할 수 없다") + 원문에 없던 단서
       — 이 경우 단서가 어떤 동사로 끝나든 조항은 조건부로 약해진다.
       실측: "단, 쌍방이 사전에 서면으로 합의한 비용 항목에 한하여 … 명시하고,
       일방의 동의 없는 비용 전가는 불가하다" 는 '청구가 가능' 이라는 말을
       쓰지 않으면서도 전면 금지를 조건부 허용으로 바꾼다.
    """
    original = str(original_text or "")
    proposed = str(proposed_text or "")
    if not original.strip() or not proposed.strip():
        return False
    if not _RX_ORIGINAL_FORECLOSES.search(original):
        return False
    # 원문에 이미 같은 예외가 있으면 계약이 그렇게 정한 것이므로 약화가 아니다.
    if _RX_REWRITE_REOPENS.search(original):
        return False
    if _RX_REWRITE_REOPENS.search(proposed):
        return True
    if _RX_ABSOLUTE_PROHIBITION.search(original) and not _RX_EXCEPTION_MARKER.search(original):
        return bool(_RX_EXCEPTION_MARKER.search(proposed))
    return False


def applicable_fairness_statutes(
    statute_decisions: list[dict[str, Any]] | None,
) -> set[str]:
    """적용요건 게이트가 **적용**으로 판단한 거래공정화 강행법규.

    게이트가 판단하지 않은 법률은 판단 대상이 아니었다는 뜻이므로 그대로
    후보에 남긴다 — 게이트가 없다고 해서 법이 적용되지 않는 것은 아니다.
    비적용으로 **명시된** 법률만 후보에서 뺀다.
    """
    decided_not_applicable = {
        str(d.get("statute") or "")
        for d in (statute_decisions or [])
        if isinstance(d, dict) and str(d.get("conclusion") or "") == "비적용"
    }
    return {s for s in MANDATORY_FAIRNESS_STATUTES if s not in decided_not_applicable}


def is_legal_compliance_fix(cr: dict[str, Any], allowed_statutes: set[str]) -> bool:
    """이 수정안이 **적용되는** 강행법규 위반을 시정하는 것인가.

    맞다면 우리에게 불리해지더라도 유지해야 한다 — 우리 계약서가 법을 어기며
    갑질하는 내용이라면 고치는 것이 맞기 때문이다(2026-09-10 지시).
    """
    if not allowed_statutes:
        return False
    blob = " ".join(
        str(cr.get(k) or "")
        for k in (
            "rewrite_reason", "legal_business_reason", "problem",
            "issue_title", "legal_basis", "suggested_rewrite", "recommendation_text",
        )
    )
    if not blob.strip():
        return False
    if not any(s in blob for s in allowed_statutes):
        return False
    return bool(_RX_VIOLATION_LANGUAGE.search(blob))


def enforce_our_side_protection(
    clause_results: list[dict[str, Any]],
    *,
    statute_decisions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """우리에게 유리한 조항을 되돌리는 수정안을 회수한다.

    단, **적용되는 강행법규 위반을 시정하는 수정안은 회수하지 않는다** —
    법을 지키는 선이 우선이다.

    회수 내역을 돌려준다 — 조용히 사라지지 않게 하기 위함이다.
    """
    from runtime.review.delivery_gate import withdraw_proposal

    allowed = applicable_fairness_statutes(statute_decisions)
    withdrawn: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        if not detect_weakening(str(cr.get("original_text") or ""), _proposed(cr)):
            continue
        if is_legal_compliance_fix(cr, allowed):
            # 우리에게 불리해지더라도 유지한다. 왜 유지했는지는 남긴다.
            cr["legal_compliance_override"] = True
            cr["legal_compliance_note"] = (
                "현행 조항이 우리 회사에 유리하더라도 강행법규 위반 소지가 있어 "
                "법령 준수 방향의 수정을 유지합니다."
            )
            continue
        withdrawn.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
        })
        withdraw_proposal(cr, status=WEAKENING_STATUS, reason=WEAKENING_REASON)
        cr["our_side_right_protected"] = True
    return withdrawn
