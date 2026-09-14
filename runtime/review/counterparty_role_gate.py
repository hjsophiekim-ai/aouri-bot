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

#: 계약서가 우리 법인을 명시적으로 어느 쪽으로 정의해 두었는데 판정이 그
#: 반대편인 경우. 위의 상태(내부 불일치)와 달리 **결과를 만들면 안 되는**
#: 상황이다 — 좌표축이 뒤집힌 검토서는 고칠 finding 이 따로 있는 것이 아니라
#: 전부가 반대로 서 있다(2026-09-14 지시 "party role 이 실제 거래구조와 맞지
#: 않으면 final output 생성 금지").
REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH = "REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH"

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


# ── 실제 거래구조와의 대조 (2026-09-14 지시 항목 4) ──────────────────────────
#
# 종전 게이트는 **판정끼리의 모순**만 봤다(양쪽이 같은 지위, 호칭 중복 등).
# 그러나 지시가 말하는 것은 "판정이 실제 거래구조와 맞는가" 다. 판정이 내부적
# 으로는 멀쩡하게 일관되면서 통째로 반대편일 수 있고, 그 경우가 가장 위험하다.
#
# 가장 신뢰할 수 있는 거래구조 증거는 **계약서 자신의 정의 조항**이다 —
# "주식회사 퍼시스(이하 "공급자"라 한다)". 계약이 우리를 공급자로 정의했는데
# 검토가 우리를 구매자로 보고 있으면, 그 아래 모든 유·불리 판단이 뒤집힌다.
#
# 종전에도 `_SELF_DECLARED` 가 비슷한 일을 했지만 (a) 회사명을 정규식에
# 하드코딩했고 (b) 공급자/구매자 두 단어만 봤다. 여기서는 회사 사실 데이터
# (`group_entities`)와 이미 있는 지위 정규화기(`canonical_identity.
# normalize_role`, provider/recipient 2방향)를 쓴다 — 새 어휘표를 만들지 않는다.

#: 정의 조항에서 당사자를 가리키는 말. `normalize_role()` 이 provider/recipient
#: 로 접어 주므로 여기서는 "정의 조항에 나올 수 있는 말" 만 모으면 된다.
_RX_ROLE_NOUN = re.compile(
    r"공급자|공급업자|공급사|매도인|판매자|제조자|제조사|수급인|수급자|시공자|시공사"
    r"|용역\s*수행자|수탁자|임대인|라이선서|제공자"
    r"|구매자|매수인|수요자|발주자|발주처|도급인|주문자|위탁자|임차인|실시권자|사용권자"
    r"|고객사?|의뢰인"
)

#: "… (이하 "공급자"라 한다)" / "… 를 "공급자" 라 한다" 형태.
_RX_DEFINES_AS = re.compile(
    r"[(\[［(]?\s*이하\s*[\"\'\u201c\u2018]?\s*(?P<role>[^\"\'\u201d\u2019)\]）]{1,10}?)"
    r"\s*[\"\'\u201d\u2019]?\s*(?:라고?|이라고?)\s*(?:한다|칭한다|약칭한다)"
)

#: ""공급자" : 주식회사 퍼시스" / "공급자(주식회사 퍼시스)" 형태.
_RX_LABELLED_PARTY = re.compile(
    r"[\"\'\u201c\u2018]?\s*(?P<role>[^\"\'\u201d\u2019\n:：(]{1,10}?)\s*[\"\'\u201d\u2019]?"
    r"\s*[:：(（]\s*(?P<name>[^)\n）]{1,40})"
)


def _our_entity_names(contract_text: str, entity: str = "") -> list[str]:
    """계약 원문에 등장하는 **우리 쪽** 법인명."""
    from runtime.review.group_entities import find_group_entities, resolve_entity

    names: list[str] = []
    for e in find_group_entities(contract_text):
        names.extend([e.name, *getattr(e, "aliases", ())])
    resolved = resolve_entity(entity)
    if resolved is not None:
        names.extend([resolved.name, *getattr(resolved, "aliases", ())])
    elif str(entity or "").strip():
        names.append(str(entity).strip())
    # 짧은 별칭은 본문 아무 데나 걸리므로 버린다.
    return sorted({n for n in names if len(str(n or "").strip()) >= 2}, key=len, reverse=True)


def declared_our_side(contract_text: str, entity: str = "") -> tuple[str, str]:
    """계약서가 **우리 법인**을 어느 쪽으로 정의했는지 돌려준다.

    `(provider|recipient|"", 근거 문자열)`. 우리 법인 이름 가까이에서 정의
    표현을 찾고, 거기 쓰인 지위 명사를 `normalize_role()` 로 접는다. 두 방향이
    같이 잡히면 판단하지 않는다 — 모르는 것을 안다고 하지 않는다.
    """
    from runtime.review.canonical_identity import normalize_role

    body = str(contract_text or "")
    names = _our_entity_names(body, entity)
    if not body.strip() or not names:
        return "", ""

    found: dict[str, str] = {}
    for name in names:
        for m in re.finditer(re.escape(name), body):
            # 이름 바로 뒤 60자 안의 "(이하 "X"라 한다)".
            tail = body[m.end(): m.end() + 60]
            dm = _RX_DEFINES_AS.search(tail)
            if dm and _RX_ROLE_NOUN.search(dm.group("role") or ""):
                side = normalize_role(dm.group("role"))
                if side:
                    found.setdefault(side, f'{name} … 이하 "{dm.group("role")}"')
            # 이름 앞 40자 안의 ""X" : <이름>" / "X(<이름>)".
            head = body[max(0, m.start() - 40): m.start()]
            lm = None
            for lm in _RX_LABELLED_PARTY.finditer(head + name):
                pass
            if lm and name in (lm.group("name") or "") and _RX_ROLE_NOUN.search(lm.group("role") or ""):
                side = normalize_role(lm.group("role"))
                if side:
                    found.setdefault(side, f'{lm.group("role")} : {name}')
    if len(found) != 1:
        return "", ""
    side, evidence = next(iter(found.items()))
    return side, evidence


def find_role_structure_mismatch(
    legal_state: dict[str, Any] | None,
    *,
    party_role: dict[str, Any] | None = None,
    contract_text: str = "",
    entity: str = "",
) -> list[str]:
    """판정된 지위가 **실제 거래구조**와 반대인지 본다. 사유 목록을 돌려준다."""
    from runtime.review.canonical_identity import ROLE_LABELS, normalize_role

    state = legal_state if isinstance(legal_state, dict) else {}
    role = party_role if isinstance(party_role, dict) else {}
    conflicts: list[str] = []

    judged = normalize_role(
        str(state.get("our_role_direction") or state.get("our_role")
            or role.get("our_role_direction") or role.get("our_role") or "")
    )

    # (a) 계약서 정의 조항 ↔ 판정
    declared, evidence = declared_our_side(contract_text, entity)
    if judged and declared and judged != declared:
        conflicts.append(
            f"계약서는 우리 회사를 '{ROLE_LABELS.get(declared, declared)}' 로 정의하고 "
            f"있으나(근거: {evidence}), 검토는 '{ROLE_LABELS.get(judged, judged)}' 를 "
            "전제로 진행되었습니다."
        )

    # (b) 우리와 상대방이 **같은 방향**으로 정규화됐다. 한 거래에서 양쪽이
    #     모두 급부 제공자이거나 모두 수령자일 수는 없다. 상호계약(NDA·바터)은
    #     지위가 'mutual' 이라 normalize_role 이 방향을 내지 않으므로 걸리지 않는다.
    theirs = normalize_role(
        str(state.get("counterparty_role") or role.get("counterparty_role") or "")
    )
    if judged and theirs and judged == theirs:
        conflicts.append(
            f"우리와 상대방이 모두 '{ROLE_LABELS.get(judged, judged)}' 방향으로 "
            "판정되었습니다 — 대가 관계가 성립하지 않습니다."
        )
    return conflicts


def enforce_role_matches_transaction_structure(
    legal_state: dict[str, Any] | None,
    *,
    party_role: dict[str, Any] | None = None,
    contract_text: str = "",
    entity: str = "",
) -> dict[str, Any]:
    """실제 거래구조와 어긋나면 **결과를 확정 생성하지 못하도록** 상태를 세운다.

    [2026-09-14 지시 항목 4] 내부 불일치(`enforce_counterparty_role`)는 사유를
    밝히고 전달했다. 그러나 계약서가 명시적으로 우리를 반대편으로 정의해 둔
    경우는 다르다 — 어느 finding 하나가 틀린 것이 아니라 검토서 전체가 반대로
    서 있으므로, 그대로 내보내면 담당자가 정반대의 협상안을 들고 나가게 된다.

    그래서 이 상태만은 `delivery_gate.NON_REMEDIABLE_STATUSES` 에 넣어 실제로
    막는다. "절대 에러나지 않고 다운로드" 요구와의 관계는 이렇게 정리된다 —
    그 요구의 취지는 **결함을 제거할 수 있는데도 막지 말라**는 것이었고, 여기서는
    제거할 결함이 따로 없다. 사유 메시지가 무엇을 확인해야 하는지 그대로 알려준다.
    """
    conflicts = find_role_structure_mismatch(
        legal_state, party_role=party_role, contract_text=contract_text, entity=entity,
    )
    if not conflicts:
        return {"status": "", "conflicts": []}
    return {
        "status": REVIEW_BLOCKED_ROLE_STRUCTURE_MISMATCH,
        "conflicts": conflicts,
        "detail": (
            "당사자 지위 판정이 계약서상 실제 거래구조와 어긋나 검토 결과를 "
            "생성하지 않았습니다. 계약서의 당사자 정의(갑·을, 공급자·구매자 등)를 "
            "확인하고 검토 대상 법인을 바로잡은 뒤 다시 검토하십시오. — "
            + " / ".join(conflicts[:2])
        ),
    }
