"""상대방 역할이 어긋나면 결과를 내보내지 않는다.

2026-09-11 지시 — "상대방 역할 오분류 시 결과 생성 금지."

왜 이것만 따로 막는가
──────────────────
당사자 지위는 검토 전체의 **좌표축**이다. 우리가 공급자인지 발주자인지가
뒤집히면 그 아래 모든 판단이 반대로 선다 — 어느 조항이 유리한지, 어느 의무를
줄여야 하는지, 어떤 법률이 우리에게 적용되는지가 전부. 다른 오류는 finding
하나가 틀리는 것으로 끝나지만, 이 오류는 문서 전체가 틀린다.

그래서 여기서는 finding 을 고치지 않고 **상태를 세운다**. 사람이 역할을
확인하기 전에는 결과를 확정본으로 쓰면 안 된다는 뜻이다.

다운로드와의 관계
──────────────
`delivery_gate.REMEDIABLE_STATUSES` 의 기본 동작을 따른다 — 사유를 문서에
명시한 채 다운로드는 계속 가능하다. "절대 에러나지 않고 다운로드" 요구와
양립시키되, 무엇이 미확정인지는 감추지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

REVIEW_FAILED_ROLE_CONFLICT = "REVIEW_FAILED_COUNTERPARTY_ROLE_CONFLICT"

#: 서로 양립할 수 없는 지위 쌍. 한 계약에서 같은 쪽이 둘 다일 수 없다.
_OPPOSED_ROLES: tuple[frozenset[str], ...] = (
    frozenset({"supplier", "buyer"}),
    frozenset({"contractor", "ordering_party"}),
    frozenset({"licensor", "licensee"}),
    frozenset({"lessor", "lessee"}),
    frozenset({"consignor", "consignee"}),
    frozenset({"disclosing_party", "receiving_party"}),
)

#: 비대칭 지위 — 한 계약에서 양쪽이 같을 수 없는 것들.
_ASYMMETRIC_ROLES: frozenset[str] = frozenset(
    r for pair in _OPPOSED_ROLES for r in pair
)

#: 양쪽이 **정당하게** 같은 지위일 수 있는 대칭 구조. 상호 비밀유지처럼 서로
#: 같은 의무를 지는 계약이 여기 속한다. 이걸 모순으로 읽으면 정상적인 NDA가
#: 전부 역할 충돌로 막힌다.
_SYMMETRIC_ROLES: frozenset[str] = frozenset({
    "party", "both", "mutual", "neutral", "each_party", "counterparty", "unknown",
})

#: 계약서가 스스로 밝힌 우리 지위. 이것과 판정이 반대면 판정이 틀린 것이다.
_SELF_DECLARED: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("supplier", re.compile(
        r"(?:이하|이를)?\s*[\"'“]?공급자[\"'”]?(?:라\s*한다|로\s*한다)"
        r"|공급자\s*[:：]\s*\S*(?:퍼시스|일룸|시디즈|레터스|데스커|당사)"
    )),
    ("buyer", re.compile(
        r"(?:이하|이를)?\s*[\"'“]?(?:구매자|매수인|발주자)[\"'”]?(?:라\s*한다|로\s*한다)"
        r"|(?:구매자|발주자)\s*[:：]\s*\S*(?:퍼시스|일룸|시디즈|레터스|데스커|당사)"
    )),
)


def _norm_role(value: Any) -> str:
    return str(value or "").strip().lower()


def find_role_conflicts(
    legal_state: dict[str, Any] | None,
    *,
    party_role: dict[str, Any] | None = None,
    contract_text: str = "",
) -> list[str]:
    """당사자 지위 판정에서 모순을 찾는다. 사람이 읽을 사유 문자열로 돌려준다."""
    state = legal_state if isinstance(legal_state, dict) else {}
    role = party_role if isinstance(party_role, dict) else {}

    ours = _norm_role(state.get("our_role") or role.get("our_role"))
    theirs = _norm_role(state.get("counterparty_role") or role.get("counterparty_role"))
    our_label = str(state.get("our_label") or role.get("our_label") or "").strip()
    their_label = str(
        state.get("counterparty_label") or role.get("counterparty_label") or ""
    ).strip()

    conflicts: list[str] = []

    # (1) 양쪽이 같은 **비대칭** 지위로 판정됐다. 성립할 수 없는 구조다.
    #     대칭 지위(상호 NDA 의 "party" 등)는 양쪽이 같은 것이 정상이다.
    if (
        ours and theirs and ours == theirs
        and ours in _ASYMMETRIC_ROLES
        and ours not in _SYMMETRIC_ROLES
    ):
        conflicts.append(
            f"우리와 상대방이 모두 '{ours}' 로 판정되었습니다. "
            "한 계약에서 같은 지위가 둘일 수 없습니다."
        )

    # (2) 우리 지위는 비대칭인데 상대방이 비어 있다. 좌표축이 반만 섰다.
    #     대칭 구조에서는 상대방 지위를 따로 적지 않는 것이 자연스럽다.
    if ours in _ASYMMETRIC_ROLES and ours not in _SYMMETRIC_ROLES and not theirs:
        conflicts.append(
            f"우리 지위는 '{ours}' 로 판정되었으나 상대방 지위가 확정되지 않았습니다."
        )

    # (3) 호칭이 같다. 갑/을 매핑이 어긋난 경우다.
    if our_label and their_label and our_label == their_label:
        conflicts.append(
            f"우리와 상대방의 호칭이 모두 '{our_label}' 입니다. "
            "계약서상 갑·을 지정을 다시 확인해야 합니다."
        )

    # (4) 계약서가 스스로 밝힌 우리 지위와 판정이 반대다.
    body = str(contract_text or "")
    if body.strip() and ours:
        for declared, pattern in _SELF_DECLARED:
            if not pattern.search(body):
                continue
            if declared == ours:
                continue
            if frozenset({declared, ours}) in _OPPOSED_ROLES:
                conflicts.append(
                    f"계약서는 우리를 '{declared}' 로 지정하고 있으나 판정은 "
                    f"'{ours}' 입니다."
                )
    return conflicts


def enforce_counterparty_role(
    legal_state: dict[str, Any] | None,
    *,
    party_role: dict[str, Any] | None = None,
    contract_text: str = "",
) -> dict[str, Any]:
    """역할 판정에 모순이 있으면 상태를 세운다.

    finding 을 손대지 않는다 — 어느 하나가 틀린 것이 아니라 축이 틀렸기
    때문에, 개별 수정으로 해소되지 않는다.
    """
    conflicts = find_role_conflicts(
        legal_state, party_role=party_role, contract_text=contract_text,
    )
    if not conflicts:
        return {"status": "", "conflicts": []}
    return {
        "status": REVIEW_FAILED_ROLE_CONFLICT,
        "conflicts": conflicts,
        "detail": (
            "당사자 지위 판정이 일관되지 않아 검토 결과를 확정본으로 쓸 수 "
            "없습니다. 계약서의 갑·을 지정과 실제 역할을 확인한 뒤 재검토하십시오. "
            "— " + " / ".join(conflicts[:3])
        ),
    }
