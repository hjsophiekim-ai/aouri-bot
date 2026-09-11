"""상대방에게 **없던 권리**를 새로 만들어주는 수정안을 차단한다.

2026-09-11 지시 —
  · "상대방에게 새로운 이의권·방어권·시정기간·책임제한을 만들어주는 수정은
     특별한 법적 필요가 있을 때만."
  · "거래구조상 우리 회사가 선이행자라면 즉시해지·환수·보전권을 약화하지 말 것."
  · "목표는 '중립적 문구'가 아니라 법적으로 유효하면서 우리 회사의 실질적
     위험을 줄이는 최소수정안."

`accept_keep` 은 "상대방의 **기존 의무**를 완화하는" 수정을 잡는다. 이
모듈은 반대 방향을 잡는다 — 원문에 **없던** 상대방의 권리를 수정안이 새로
만들어내는 경우다. 두 가지는 다른 사고다.

    accept_keep          을의 배상의무를 "귀책 있는 경우에 한하여" 로 축소
    이 모듈              을에게 "이의를 제기할 수 있다" 를 새로 부여

후자는 읽기에 절차적 보완처럼 보여서 그대로 통과하기 쉽다. 그러나 협상
테이블에서는 우리가 먼저 상대방의 카드를 만들어 건네는 것과 같다.

선이행 구조에서는 더 엄격하다. 우리가 먼저 이행하면 동시이행의 항변권을
잃으므로, **즉시해지·환수·보전권이 유일한 회수 장치**가 된다. 그 세 가지를
약화하는 수정은 강행법규 준수 목적이 아닌 한 허용하지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

GRANT_BLOCKED = "COUNTERPARTY_GRANT_BLOCKED"

#: 상대방에게 새로 주는 권리의 문형. 주어가 우리가 아니어야 한다.
_GRANT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("이의권", re.compile(
        r"이의(?:를)?\s*(?:제기|신청)할\s*수\s*있|이의\s*제기권|불복할\s*수\s*있"
    )),
    ("방어권", re.compile(
        r"방어(?:\s*및\s*화해)?\s*(?:절차에\s*)?참여할\s*권리|방어권(?:을)?\s*(?:가진다|보장)"
        r"|화해(?:에)?\s*(?:참여|동의)할\s*권리|소송\s*수행권"
    )),
    ("시정기간", re.compile(
        r"\d+\s*일\s*(?:전까지|이내에)?\s*시정(?:을)?\s*(?:요구|최고)"
        r"|시정할\s*(?:수\s*있는\s*)?기간(?:을)?\s*(?:부여|준다)"
        r"|상당한\s*기간(?:을)?\s*정하여\s*(?:최고|시정)"
        r"|유예기간(?:을)?\s*(?:부여|둔다)"
    )),
    ("책임제한", re.compile(
        r"책임(?:은|을)?[^.\n]{0,25}(?:한도|상한)(?:로|으로)?\s*한정"
        r"|초과하지\s*아니한다|간접손해[^.\n]{0,20}제외|직접손해에\s*한하며"
        r"|고의\s*(?:또는|또)\s*중(?:대한\s*)?과실[^.\n]{0,20}제외"
    )),
)

#: 선이행자가 잃으면 안 되는 회수 장치.
_RECOVERY_RIGHTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("즉시해지", re.compile(r"즉시\s*해[지제]|통지\s*없이\s*해[지제]")),
    ("환수", re.compile(r"반환(?:을)?\s*(?:청구|요구)|원상\s*(?:반환|회복)|회수(?:할|한다)")),
    ("보전", re.compile(r"담보|보증(?:보험|증권|금)|상계|질권|가압류|유보")),
)

#: 그 권리가 **약화**되는 신호.
_RX_WEAKENED = re.compile(
    r"(?:다만|단)[,\s]|에\s*한하여|한\s*경우에만|경우에\s*한(?:하여|한다)"
    r"|시정(?:을)?\s*요구한\s*후|최고(?:한|를\s*거친)\s*후|협의(?:하여|를\s*거쳐)"
    r"|제외하고|배제한다|하지\s*아니한다",
)

_PROPOSAL_FIELDS = ("suggested_rewrite", "proposed_revision", "recommendation_text")


def _proposed(cr: dict[str, Any]) -> str:
    return "\n".join(str(cr.get(k) or "") for k in _PROPOSAL_FIELDS)


def newly_granted_rights(original_text: str, proposed_text: str) -> list[str]:
    """수정안이 원문에 없던 상대방 권리를 새로 만들어내는가."""
    original = str(original_text or "")
    proposed = str(proposed_text or "")
    if not original.strip() or not proposed.strip():
        return []
    granted: list[str] = []
    for label, pattern in _GRANT_PATTERNS:
        if pattern.search(proposed) and not pattern.search(original):
            granted.append(label)
    return granted


def weakened_recovery_rights(
    original_text: str,
    proposed_text: str,
    *,
    our_labels: tuple[str, ...] = (),
) -> list[str]:
    """선이행자의 회수 장치(즉시해지·환수·보전)를 약화하는가.

    **우리가 보유한** 권리만 본다. 상대방이 우리를 상대로 쥔 담보·유보·해지권은
    지켜야 할 회수 장치가 아니라 우리가 줄여야 할 위험이다. 이 구분이 없으면
    우리가 을인 계약에서 상대방의 무제한 해지권까지 보호 대상이 된다.
    """
    from runtime.review.clause_direction import ours_holds_right

    original = str(original_text or "")
    proposed = str(proposed_text or "")
    if not original.strip() or not proposed.strip():
        return []
    if not ours_holds_right(original, our_labels):
        return []
    weakened: list[str] = []
    for label, pattern in _RECOVERY_RIGHTS:
        if not pattern.search(original):
            continue
        if not pattern.search(proposed):
            # 회수 수단 자체가 수정안에서 사라졌다. 조건이 붙는 것보다 무겁다.
            weakened.append(label)
            continue
        # 원문에 이미 조건이 붙어 있으면 계약이 그렇게 정한 것이지, 수정안이
        # 깎은 것이 아니다.
        if _RX_WEAKENED.search(original):
            continue
        if _RX_WEAKENED.search(proposed):
            weakened.append(label)
    return weakened


def enforce_no_new_counterparty_rights(
    clause_results: list[dict[str, Any]],
    *,
    statute_decisions: list[dict[str, Any]] | None = None,
    our_labels: tuple[str, ...] = (),
    we_perform_first: bool = False,
) -> list[dict[str, Any]]:
    """상대방에게 새 권리를 주거나 우리 회수 장치를 깎는 수정안을 되돌린다.

    강행법규 위반을 시정하는 수정안은 유지한다 — 법을 지키는 선이 우선이다.
    처리 내역을 돌려준다.
    """
    from runtime.review.clause_direction import (
        DIRECTION_THEY_BEAR,
        burden_direction,
        ours_holds_right,
    )
    from runtime.review.our_side_protection import (
        applicable_fairness_statutes,
        is_legal_compliance_fix,
    )

    allowed = applicable_fairness_statutes(statute_decisions)
    blocked: list[dict[str, Any]] = []

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        original = str(cr.get("original_text") or "")
        proposed = _proposed(cr)
        if not original.strip() or not proposed.strip():
            continue

        reasons: list[str] = []

        # (1) **이미 우리에게 유리한** 조항에만 "새 권리 부여"를 문제 삼는다.
        #     "우리가 부담자가 아니다"와 "우리에게 유리하다"는 다르다 — 상대방이
        #     자기 책임을 전부 면제하는 면책 조항은 우리가 부담자가 아니지만
        #     우리에게 불리하고, 그것을 바로잡는 수정은 반드시 상대방을 구속하게
        #     된다. 그 수정까지 막으면 정작 고쳐야 할 조항이 살아남는다.
        favorable = (
            burden_direction(original, our_labels) == DIRECTION_THEY_BEAR
            or ours_holds_right(original, our_labels)
        )
        if favorable:
            granted = newly_granted_rights(original, proposed)
            if granted:
                reasons.append("상대방에게 없던 " + "·".join(granted) + "을 새로 부여")

        # (2) 선이행 구조에서는 회수 장치를 약화하지 않는다.
        if we_perform_first:
            weakened = weakened_recovery_rights(
                original, proposed, our_labels=our_labels,
            )
            if weakened:
                reasons.append(
                    "선이행 구조에서 유일한 회수 장치인 " + "·".join(weakened) + "을 약화"
                )

        if not reasons:
            continue
        if is_legal_compliance_fix(cr, allowed):
            cr["legal_compliance_override"] = True
            continue

        note = (
            "현행 조항을 유지합니다 — " + "; ".join(reasons) + "하는 수정이며, "
            "이를 정당화할 강행법규상 필요가 확인되지 않았습니다. "
            "협상 상대가 요구하면 그때 검토할 사항이지, 우리가 먼저 제시할 문안이 아닙니다."
        )
        for key in _PROPOSAL_FIELDS:
            cr[key] = None
        cr["recommendation_text"] = note
        cr["proposed_revision"] = note
        cr["redline_instruction"] = None
        cr["changed_segments"] = []
        cr["has_rewrite_change"] = False
        cr["scope_verdict"] = "적정"
        cr["accept_keep"] = True
        cr["accept_keep_reason"] = note
        cr["keep_as_is"] = True
        cr["counterparty_grant_blocked"] = reasons
        cr["risk_tier"] = "LOW"
        cr["severity"] = "LOW"
        cr["review_tier"] = "NOTE"
        cr["must_fix"] = False
        cr["approval_required"] = False
        cr["high_risk"] = False
        cr["rewrite_reason"] = note
        cr["negotiation_position"] = (
            "협상 대상으로 먼저 올리지 마십시오 — 현행 문언이 우리에게 유리합니다."
        )
        blocked.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "reasons": reasons,
        })
    return blocked
