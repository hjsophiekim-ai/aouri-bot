"""내부통제 권고를 **계약 조항에서 떼어낸다**.

2026-09-11 지시 — "세무·회계 내부통제는 계약조항이 아니라 내부 확인사항으로
분리."

무엇이 문제였나
─────────────
세무 논점이 잡히면 엔진은 습관적으로 조문 문안을 만들었다. 그런데 "부가가치세
신고 시 공급시기를 확인한다", "증빙을 5년간 보관한다" 같은 것은 **우리가 우리
안에서** 하는 일이지 상대방과 합의할 사항이 아니다. 그런 문장을 계약서에 넣으면

  · 상대방에게 우리 내부 절차를 이행할 의무를 지우거나(합의될 리 없다),
  · 반대로 우리가 상대방에게 그 절차의 이행을 약속하는 꼴이 된다.

둘 다 협상에서 불필요한 짐이다. 그래서 이런 권고는 조문이 아니라 **내부
확인사항**으로 돌린다.

무엇은 그대로 두는가
──────────────────
상대방에게 지우는 의무는 계약 조항이 맞다 — "을은 공급시기에 세금계산서를
발행하여 갑에게 교부한다" 는 전형적인 계약 문언이다. 판별 기준은 세무라는
**주제**가 아니라, 그 문장이 **누구의 행위**를 규율하는가이다.
"""
from __future__ import annotations

import re
from typing import Any

INTERNAL_CONTROL = "INTERNAL_CONTROL_ITEM"

#: 우리 조직 안에서 벌어지는 일. 계약 상대방이 관여하지 않는다.
_RX_INTERNAL_SIGNAL = re.compile(
    r"재경(?:팀|본부)?|세무(?:팀|대리인)|회계(?:팀|처리|정책)|경리"
    r"|내부\s*(?:통제|절차|검토|승인|기준|규정)|사내\s*(?:절차|규정|기준)"
    r"|품의|결재|전표|원가\s*배부|계정\s*과목|자산\s*계상|비용\s*처리"
    r"|손금\s*(?:산입|불산입)|익금|세무조정|법인세\s*신고|부가가치세\s*(?:신고|예정신고)"
    r"|원천징수\s*이행상황|증빙(?:을|의)?\s*(?:보관|비치|구비)"
    r"|국세청\s*(?:질의|예규)|세무\s*(?:자문|검토|리스크)\s*(?:를)?\s*(?:받|확인|의뢰)"
)

#: 계약 당사자에게 지우는 의무·권리. 이것이 있으면 조항으로 남긴다.
_RX_PARTY_OBLIGATION = re.compile(
    r"(?:갑|을|병|당사자|상대방|공급자|수급인|수탁자|위탁자|발주자|구매자|매수인|매도인"
    r"|사업자|대리점|가맹점|임차인|임대인)"
    r"[\"'”’]?\s*(?:은|는|이|가|에게|으로부터|에\s*대하여)"
)

#: 계약 문언의 종결형. 내부 메모에는 잘 나오지 않는다.
_RX_CLAUSE_FORM = re.compile(
    r"(?:하여야\s*한다|하여야\s*하며|한다\.|할\s*수\s*있다|지급한다|교부한다|통지한다"
    r"|발행하여|제공한다|보증한다|부담한다)"
)

_PROPOSAL_FIELDS = ("suggested_rewrite", "proposed_revision")


def looks_like_internal_control(text: str) -> bool:
    """이 문장이 **우리 내부**의 일인가.

    내부 신호가 있으면서 계약 당사자에게 지우는 의무 문형이 없어야 한다.
    """
    body = str(text or "")
    if not body.strip():
        return False
    if not _RX_INTERNAL_SIGNAL.search(body):
        return False
    if _RX_PARTY_OBLIGATION.search(body):
        return False
    return True


def split_internal_controls(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """내부통제 권고에서 조문 문안을 걷어내고 확인사항으로 돌린다.

    finding 자체는 남긴다 — 지적은 유효하고, 자리를 잘못 잡았을 뿐이다.
    옮긴 항목의 목록을 돌려준다.
    """
    moved: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        proposals = [
            str(cr.get(k) or "").strip() for k in _PROPOSAL_FIELDS
        ]
        proposal = next((p for p in proposals if p), "")
        if not proposal:
            continue
        # 원문을 고치는 수정안은 조항 작업이다. 원문이 없는 "신설 권고"만 본다.
        original = str(cr.get("original_text") or "").strip()
        if original and proposal.startswith(original[: min(len(original), 40)]):
            continue
        if not looks_like_internal_control(proposal):
            continue
        # 조문 형태를 완전히 갖춘 문안은 사람이 의도해서 쓴 것일 수 있다.
        if _RX_CLAUSE_FORM.search(proposal) and _RX_PARTY_OBLIGATION.search(proposal):
            continue

        note = (
            "이 항목은 계약 조항이 아니라 내부 확인사항입니다. 상대방과 합의할 "
            "사항이 아니라 우리 내부에서 처리·기록해야 하는 일이므로, 계약서에 "
            "넣지 않고 재경·세무 담당에게 전달합니다.\n\n확인할 내용: " + proposal
        )
        for key in _PROPOSAL_FIELDS:
            cr[key] = None
        cr["recommendation_text"] = note
        cr["redline_instruction"] = None
        cr["changed_segments"] = []
        cr["has_rewrite_change"] = False
        cr["internal_control_item"] = True
        cr["internal_control_note"] = proposal
        cr["finance_confirmation"] = proposal
        cr["advisory_only"] = True
        cr["advisory_only_reason"] = INTERNAL_CONTROL
        cr["must_fix"] = False
        cr["approval_required"] = False
        if str(cr.get("risk_tier") or "") == "HIGH":
            # 내부 절차로 해소되는 것을 계약 리스크 최상위로 올리지 않는다.
            cr["risk_tier"] = "MEDIUM"
            cr["severity"] = "MEDIUM"
        moved.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "note": proposal,
        })
    return moved
