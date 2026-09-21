"""우리에게 유리하고 적법한 조항은 `ACCEPT/KEEP` 으로 확정한다.

2026-09-10 지시 항목 2 — "우리 회사에 유리한 조항은 함부로 약화 금지.
상대방의 면책·배상·즉시해지 책임을 줄이는 수정은 특별한 법적 이유가 있을
때만. `ACCEPT/KEEP` 판단을 적극 사용."

`our_side_protection.py` 는 "원문이 상대방의 청구를 차단하는데 수정안이
예외를 신설하는" 한 가지 문형을 잡는다. 이 모듈은 그보다 앞단에서 한 걸음
더 나간다 — **상대방에게 부과된 책임(면책·배상·보증·즉시해지)을 줄이는
방향의 수정안** 을 일반적으로 잡아 `ACCEPT/KEEP` 으로 되돌린다.

실측 사고의 형태
──────────────
상대방이 우리를 면책하도록 정한 조항에 "귀책 있는 당사자가 부담한다",
"쌍방 협의하여", "상호 면책" 같은 문구를 넣으면, 읽기에는 균형이 잡히지만
실제로는 **우리가 갖고 있던 일방적 면책을 쌍방 부담으로 바꾸는** 양보다.
"형평성"·"균형" 은 그 양보를 정당화하는 법적 이유가 아니다.

판정 방식
────────
    원문이 상대방에게 책임을 부과 + 수정안이 그것을 완화·분담·상호화
        → 강행법규 위반 시정 근거가 없으면 ACCEPT/KEEP

강행법규 준수는 여전히 우선한다 — 판단은 `our_side_protection` 의
`is_legal_compliance_fix()` 를 그대로 재사용한다(같은 기준을 두 곳에서
따로 정의하지 않는다).
"""
from __future__ import annotations

import re
from typing import Any

VERDICT_ACCEPT = "ACCEPT/KEEP"

#: 원문이 **상대방에게** 책임을 지우는 문형. 이런 조항은 우리에게 유리하다.
#:
#: "비용은 을이 부담한다" 같은 평범한 형태까지 포함해야 한다 — 종전에는
#: 면책·전액배상 같은 강한 문형만 잡아서, 검수 수정비용을 상대방이 전부
#: 부담하도록 한 조항(우리에게 유리)을 "귀책사유가 있는 경우에 한하여"로
#: 축소하는 수정안이 그대로 나갔다(2026-09-10 실측, 제8조 제2항).
#: 우리 쪽이 부담자인 경우는 `_ours_bears()` 가 따로 걸러낸다.
_RX_COUNTERPARTY_BURDEN = re.compile(
    r"면책(?:시킨다|하며|하고|한다)"
    r"|자신의\s*(?:비용과\s*)?책임으로"
    r"|일체의\s*책임(?:과|및)?\s*비용(?:을)?\s*부담"
    r"|모든\s*손해(?:를)?\s*배상"
    r"|전액(?:을)?\s*(?:배상|지급|부담)"
    r"|보증(?:한다|하며|하여야)"
    r"|즉시\s*해[지제]할\s*수\s*있"
    r"|(?:청구|요구)할\s*수\s*없다"
    r"|(?:비용|책임|손해)(?:은|는|을|를)?[^.\n]{0,25}부담(?:한다|하며|하여야)"
    # ── 우리가 **받아 내는** 권리 (2026-09-16 지시 7항) ────────────────────
    # "환불권·연장권·상대방 귀책 손해배상·송출의무·실적 확인권은 KEEP 처리하고
    #  불필요하게 약화하지 마세요."
    #
    # 위 문형들은 전부 "상대방이 무엇을 부담한다" 는 꼴이라, 상대방이 **우리에게
    # 무엇을 해 주기로 한** 급부 조항은 하나도 잡지 못했다. 실측(디지털 사이니지
    # 광고 계약 제5조): 미방영 시 "연장하여 방영하여야 한다", 철거 시 "일할
    # 계산하여 반환한다" 는 우리 쪽 구제수단인데, 이 모듈의 보호 대상이 아니어서
    # "쌍방 협의로 정한다" 같은 완화 수정이 그대로 나갈 수 있었다.
    r"|(?:반환|환불|상환)(?:한다|하여야|하며)"
    r"|일할\s*계산[^.\n]{0,20}(?:반환|정산)"
    r"|연장하여[^.\n]{0,20}(?:방영|송출|표출|게재|제공)"
    r"|(?:기간|기한)(?:을)?\s*연장(?:한다|하여야|하며)"
    r"|(?:송출|표출|게재|방영)[^.\n]{0,20}(?:하여야\s*한다|제공한다|이행하여야)"
    r"|(?:실적|내역|리포트|보고서)(?:를)?[^.\n]{0,20}(?:제출|제공|통보|보고)(?:한다|하여야|하며)",
)

#: 그 책임을 **완화·분담·상호화** 하는 수정 신호.
_RX_BURDEN_SOFTENED = re.compile(
    r"귀책(?:사유)?(?:가|이)?\s*있는\s*당사자"
    r"|쌍방(?:이)?\s*(?:협의|분담|부담)"
    r"|상호\s*면책"
    r"|각자\s*(?:부담|책임)"
    r"|상대방(?:도|과)\s*(?:함께|공동)"
    r"|합리적(?:인)?\s*범위\s*내(?:에서)?"
    r"|직접손해에\s*한하며"
    r"|고의\s*(?:또는|또)\s*중(?:대한\s*)?과실(?:이)?\s*(?:있는\s*경우|인\s*경우)에\s*한"
    r"|사전\s*(?:서면\s*)?최고|시정(?:을)?\s*요구한\s*후"
    r"|협의하여\s*(?:정한다|처리)"
    # 실측(제8조 제2항): "자신의 귀책사유로 인한 경우에 한하여 … 부담하며,
    # 그 외 사유로 인한 수정은 별도 협의에 따른다" — 상대방의 전부 부담을
    # 귀책 한정 + 협의로 바꾸는 전형적인 완화 문형인데 잡히지 않았다.
    r"|자신의\s*귀책(?:사유)?"
    r"|귀책(?:사유)?[^.\n]{0,20}(?:인|있는)\s*경우에\s*한(?:하여|한다)"
    r"|별도\s*협의|협의(?:에|하여)\s*(?:따른다|정한다|처리)"
    r"|에\s*한하여[^.\n]{0,25}(?:부담|배상|책임)",
)

#: 우리 쪽이 부담자로 지목되는 문형 — 이 조항은 우리에게 유리하지 않으므로
#: 이 모듈의 대상이 아니다(정상적으로 수정 대상이다).
#:
#: 주격 조사(은/는/이/가)를 반드시 요구한다. 목적격("갑을 면책시킨다")은 우리가
#: **보호받는** 문형인데, 조사를 가리지 않으면 그것까지 "우리 부담"으로 세어
#: 우리에게 유리한 면책조항이 전부 이 모듈의 대상에서 빠진다.
_RX_OURS_BURDEN = re.compile(
    r"(?:갑|당사|우리)[\"'”’]?\s*(?:은|는|이|가)\s*[^.\n]{0,30}"
    r"(?:부담(?:한다|하며|하여야)|배상(?:한다|하여야)|보증(?:한다|하며)|책임을\s*진다)"
)

_PROPOSAL_FIELDS = ("suggested_rewrite", "proposed_revision", "recommendation_text")


def _proposed(cr: dict[str, Any]) -> str:
    return "\n".join(str(cr.get(k) or "") for k in _PROPOSAL_FIELDS)


def _ours_bears(original: str, our_labels: tuple[str, ...]) -> bool:
    """이 조항의 부담자가 **우리 쪽**인가.

    계약서는 당사자를 "갑/을" 이 아니라 회사명·약칭으로 부르는 경우가 많다
    (예: "일룸-DESKER", "공급자"). 우리 호칭을 넘겨받아 함께 확인하지 않으면,
    우리가 부담자인 조항까지 "상대방 책임" 으로 오인해 정당한 완화 수정을
    막게 된다.
    """
    if _RX_OURS_BURDEN.search(original):
        return True
    # 호칭 기반 판단은 `clause_direction` 하나에 맡긴다. 여기에 사본을 두면
    # "갑"을 우리로 가정하거나 관형절 주어·부정형을 놓치는 결함이 이 파일에만
    # 남아, 같은 계약을 두 모듈이 다르게 읽는다.
    from runtime.review.clause_direction import ours_bears_burden

    return ours_bears_burden(original, tuple(our_labels or ()))


def softens_counterparty_burden(
    original_text: str,
    proposed_text: str,
    *,
    our_labels: tuple[str, ...] = (),
) -> bool:
    """상대방에게 부과된 책임을 수정안이 완화·분담·상호화하는가."""
    original = str(original_text or "")
    proposed = str(proposed_text or "")
    if not original.strip() or not proposed.strip():
        return False
    if not _RX_COUNTERPARTY_BURDEN.search(original):
        return False
    if _ours_bears(original, our_labels):
        # 우리가 부담자인 조항은 완화가 곧 우리 이익이다.
        return False
    # 원문에 이미 그 완화 문언이 있으면 계약이 그렇게 정한 것이다.
    if _RX_BURDEN_SOFTENED.search(original):
        return False
    return bool(_RX_BURDEN_SOFTENED.search(proposed))


#: 쌍방에 대칭으로 적용되는 조항의 표지.
_RX_MUTUAL = re.compile(
    r"각\s*당사자|양\s*당사자|쌍방|상호(?:간|적으로)?|서로|어느\s*一?일방"
    r"|each\s+party|both\s+parties|mutual",
    re.IGNORECASE,
)

#: 우리 권리·상대방 의무에 **새로 붙는** 제한. 원문에 없던 것만 본다.
_RX_RESTRICTION_ADDED = re.compile(
    r"에\s*한(?:하여|한다|함)|한\s*경우에만|경우에\s*한(?:하여|한다)"
    r"|범위\s*(?:내에서|내로)\s*(?:만)?|상당한\s*기간|사전\s*(?:서면\s*)?협의를\s*거쳐"
    r"|합의(?:하여|를\s*거쳐)\s*(?:정한다|결정)|상호\s*협의|쌍방\s*합의"
    r"|초과할\s*수\s*없|제외한다|배제한다",
)


#: 계약 **전체**가 당사자 지위를 번갈아 부여하는 구조인지. 상호 NDA 가 전형이다
#: ("정보 별로 제공자와 수신자를 분별한다"). 조항 문면만 보면 "수신자가 의무를
#: 부담한다" 로 읽히지만, 그 수신자가 이번에는 우리일 수 있다.
_RX_MUTUAL_CONTRACT = re.compile(
    r"제공(?:하는|한)\s*자를[^.\n]{0,20}(?:라고\s*)?하고[^.\n]{0,30}제공받는\s*자"
    r"|정보\s*별로[^.\n]{0,20}(?:제공자|수신자)"
    r"|각\s*당사자(?:는|가)[^.\n]{0,40}(?:제공자|수신자|공히|모두)"
    r"|상호(?:\s*간)?\s*(?:정보|비밀정보)(?:를)?\s*(?:주고\s*받|제공|교환)"
    r"|양사가\s*상호|쌍방(?:이|은)?\s*각각"
    r"|each\s+party\s+(?:may|shall)\s+(?:act\s+as|be)\s+(?:a\s+)?(?:disclos|receiv)",
    re.IGNORECASE,
)


def has_alternating_party_roles(contract_text: str) -> bool:
    """계약이 당사자 지위를 번갈아 부여하는가(상호 구조인가)."""
    return bool(_RX_MUTUAL_CONTRACT.search(str(contract_text or "")))


def weakens_our_favorable_clause(
    original_text: str,
    proposed_text: str,
    *,
    our_labels: tuple[str, ...] = (),
    contract_text: str = "",
) -> bool:
    """이미 우리에게 유리한 조항에 수정안이 **없던 제한**을 붙이는가.

    2026-09-11 지시 — "우리 회사에 유리하고 위법하지 않은 조항은 KEEP 처리하고
    불필요하게 약화하지 마세요."

    `softens_counterparty_burden` 은 상대방의 **책임**이 완화되는 문형만 본다.
    그런데 약화는 다른 모습으로도 온다 — 우리 권리에 "상호 협의를 거쳐",
    "상당한 기간을 정하여", "귀책 범위에 한하여" 같은 조건이 새로 붙는 식이다.
    문장만 보면 합리적으로 읽히지만, 결과적으로 우리가 행사할 수 있던 권리에
    상대방의 동의·기간·범위 제한이 생긴다.

    유리 판정은 `clause_direction` 하나만 쓴다 — 상대방이 부담자이거나 우리가
    권리자인 조항이 우리에게 유리한 조항이다.
    """
    from runtime.review.clause_direction import DIRECTION_THEY_BEAR, burden_direction

    original = str(original_text or "")
    proposed = str(proposed_text or "")
    if not original.strip() or not proposed.strip():
        return False
    # 쌍방에 똑같이 적용되는 조항은 우리에게 유리한 조항이 아니다. 제한을
    # 붙이면 양쪽이 같이 제한되고, 실제 위험은 상대방의 행사에서 온다.
    # 실측: 웹젠 NDA 의 "관련 계약 연쇄해지" 는 상호 조항인데 우리 권리로
    # 읽혀, 이를 제한하는 정당한 수정안이 KEEP 되고 HIGH finding 이 사라졌다.
    if _RX_MUTUAL.search(original):
        return False
    # 대칭성은 조항이 아니라 계약 앞부분에 선언되는 경우가 많다. 실측: 웹젠
    # NDA 는 제1조에서 "정보 별로 제공자와 수신자를 분별한다" 고 정해 두었다.
    # 조항만 보면 "수신자가 의무를 부담한다" 이므로 우리에게 유리해 보이지만,
    # 그 수신자는 이번에 우리다 — 이를 놓쳐 HIGH finding 두 건이 KEEP 됐다.
    if has_alternating_party_roles(contract_text):
        return False
    # 판정은 **부담 방향**으로만 한다. "우리가 권리자인가"(`ours_holds_right`)
    # 는 "…할 수 있다" 문형에 우리 호칭이 스치기만 해도 참이 되어, 우리에게
    # 불리한 조항까지 보호 대상으로 만든다.
    if burden_direction(original, our_labels) != DIRECTION_THEY_BEAR:
        return False
    # 원문에 이미 제한이 붙어 있으면 계약이 그렇게 정한 것이다.
    if _RX_RESTRICTION_ADDED.search(original):
        return False
    return bool(_RX_RESTRICTION_ADDED.search(proposed))


def apply_accept_keep(
    clause_results: list[dict[str, Any]],
    *,
    statute_decisions: list[dict[str, Any]] | None = None,
    our_labels: tuple[str, ...] = (),
    contract_text: str = "",
) -> list[dict[str, Any]]:
    """상대방 책임을 줄이는 수정안을 `ACCEPT/KEEP` 으로 되돌린다.

    강행법규 위반을 시정하는 수정안은 그대로 유지한다(법을 지키는 선이 우선).
    처리 내역을 돌려준다.
    """
    from runtime.review.our_side_protection import (
        applicable_fairness_statutes,
        is_legal_compliance_fix,
    )

    allowed = applicable_fairness_statutes(statute_decisions)
    accepted: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        _original = str(cr.get("original_text") or "")
        _proposal = _proposed(cr)
        _softens = softens_counterparty_burden(
            _original, _proposal, our_labels=our_labels,
        )
        # 약화는 "상대방 책임 완화" 외에도 "우리 권리에 없던 제한 추가" 로 온다.
        _restricts = (
            False if _softens
            else weakens_our_favorable_clause(
                _original, _proposal,
                our_labels=our_labels, contract_text=contract_text,
            )
        )
        if not (_softens or _restricts):
            continue
        if is_legal_compliance_fix(cr, allowed):
            cr["legal_compliance_override"] = True
            continue

        # 현행 조항이 우리에게 유리하고 법적으로 문제없다 → 수정하지 않는다.
        reason = (
            "현행 조항은 상대방에게 면책·배상·보증 등의 책임을 지우고 있어 우리 회사에 "
            "유리하며, 강행법규에 저촉되는 부분도 확인되지 않았습니다. 상대방의 책임을 "
            "완화·분담하는 수정은 우리 쪽에서 먼저 양보안을 제시하는 셈이 되므로 "
            "현행 유지(ACCEPT/KEEP)를 권고합니다."
        ) if _softens else (
            "현행 조항은 우리 회사가 권리자이거나 상대방이 의무를 부담하는 구조로 "
            "우리에게 유리하며, 위법·무효 위험도 확인되지 않았습니다. 제안된 수정은 "
            "그 권리에 협의·기간·범위 제한을 새로 붙여 행사 요건을 무겁게 만들므로 "
            "현행 유지(ACCEPT/KEEP)를 권고합니다."
        )
        for key in _PROPOSAL_FIELDS:
            cr[key] = None
        cr["recommendation_text"] = reason
        cr["proposed_revision"] = reason
        cr["redline_instruction"] = None
        cr["changed_segments"] = []
        cr["has_rewrite_change"] = False
        cr["scope_verdict"] = "적정"
        cr["accept_keep"] = True
        cr["accept_keep_reason"] = reason
        cr["keep_as_is"] = True
        cr["risk_tier"] = "LOW"
        cr["severity"] = "LOW"
        cr["review_tier"] = "NOTE"
        cr["must_fix"] = False
        cr["approval_required"] = False
        cr["high_risk"] = False
        cr["rewrite_reason"] = reason
        cr["negotiation_position"] = "협상 대상으로 올리지 마십시오 — 현행 문언이 우리에게 유리합니다."
        accepted.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
        })
    return accepted


# ── KEEP/보류 판단이 필수수정 목록에 남지 않게 한다 (2026-09-14 지시 항목 3) ──

#: "고칠 필요가 없다" 는 결론의 표지. **결론**을 적은 문장이어야 하므로
#: 권고·수정문안 자리에서만 찾는다(문제점 서술에 "현행 유지가 어렵다" 처럼
#: 반대 취지로 등장할 수 있기 때문).
_RX_KEEP_VERDICT = re.compile(
    r"현행\s*(?:문언|조항|규정|계약)?\s*(?:을|를)?\s*유지"
    r"|그대로\s*유지"
    r"|수정(?:이|할)?\s*(?:필요\s*)?(?:없|불필요)"
    r"|수정하지\s*(?:않|아니)"
    r"|변경\s*불필요"
    r"|ACCEPT\s*/?\s*KEEP"
    r"|협상\s*대상으로\s*올리지",
    re.IGNORECASE,
)

#: 법률 적용 여부 자체가 미확정이라는 표지. 이것만으로는 **필수수정**의 근거가
#: 될 수 없다 — 적용될지도 모르는 법을 근거로 "반드시 고치라" 고 할 수는 없다.
_RX_APPLICABILITY_HELD = re.compile(
    r"(?:적용|판단)\s*(?:여부)?\s*보류"
    r"|적용\s*여부[^.\n]{0,20}(?:미확정|확정되지\s*(?:않|아니)|불분명)"
    r"|적용\s*가능성만",
)

_VERDICT_FIELDS = ("recommendation_text", "proposed_revision", "rewrite_reason")
_BASIS_FIELDS = ("legal_business_reason", "rewrite_reason", "problem")


def _demote_to_note(cr: dict[str, Any], *, reason: str, kind: str) -> None:
    """HIGH/MEDIUM 목록에서 빠지도록 등급과 표시를 낮춘다.

    `keep_as_is` 를 세우는 것이 핵심이다 — `output_filter.
    clause_results_to_review_issues()` 가 이 표시를 보고 최종 목록에서
    통째로 제외하므로, UI 와 DOCX 가 같이 빠진다.
    """
    cr["keep_as_is"] = True
    cr["accept_keep"] = True
    cr["accept_keep_reason"] = reason
    cr["keep_verdict_kind"] = kind
    cr["risk_tier"] = "LOW"
    cr["severity"] = "LOW"
    cr["review_tier"] = "NOTE"
    cr["must_fix"] = False
    cr["approval_required"] = False
    cr["high_risk"] = False


def enforce_keep_verdict_removal(
    clause_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """결론이 "고치지 않는다" 인 항목을 필수·권장 목록에서 뺀다.

    [2026-09-14 지시 항목 3]
      · "우리 회사에 유리한 조항이라 KEEP 또는 수정 불필요로 판단했으면
         HIGH/MEDIUM 목록에서 완전히 제거."
      · "'적용 보류' 라고 써놓고 필수수정으로 남기지 말 것."

    `apply_accept_keep()` 은 **수정안이 상대방 책임을 완화하는가**를 보고
    되돌린다. 그 경로를 타지 않은 채 결론만 "현행 유지" 로 적힌 항목 —
    AI 가 스스로 그렇게 판단했거나, 후단에서 등급이 되살아난 항목 — 은
    여전히 빨간 글씨 필수수정으로 남았다. 담당자는 "반드시 고치라" 는 칸에서
    "고칠 필요 없다" 는 문장을 읽게 된다.

    두 종류를 처리한다.
      keep_verdict  — 결론이 현행 유지·수정 불필요다.
      applicability_held — 근거로 든 법률의 적용 여부 자체가 보류 상태다.

    어느 쪽이든 **삭제가 아니라 참고(LOW)로 내린다.** 판단 자체는 기록으로
    남을 가치가 있고, 조용히 없애면 담당자가 "왜 이 조항은 아무도 안 봤나" 를
    되묻게 된다.
    """
    moved: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")):
            continue
        tier = str(cr.get("risk_tier") or "").upper()
        if tier not in ("HIGH", "MEDIUM"):
            # 이미 KEEP 인데 등급만 살아 있는 경우가 없으므로 여기서 끝.
            continue

        # 무결성 게이트가 문안을 의도적으로 회수한 항목은 "KEEP" 이 아니다 —
        # 문제 제기는 유효하고 문안만 보류된 상태다(v7 전달 게이트 설계).
        if bool(cr.get("advisory_only")) or str(cr.get("proposal_replaced_reason") or "").strip():
            continue
        if str(cr.get("fact_confirmation_required") or "").strip():
            continue

        if bool(cr.get("keep_as_is")) or bool(cr.get("accept_keep")):
            _demote_to_note(
                cr,
                reason=str(cr.get("accept_keep_reason") or "현행 유지로 판단된 항목입니다."),
                kind="keep_flag_restored",
            )
            moved.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "kind": "keep_flag_restored",
                "from_tier": tier,
            })
            continue

        verdict_text = "\n".join(
            str(cr.get(k) or "") for k in _VERDICT_FIELDS
        )
        has_change = bool(cr.get("has_rewrite_change")) or bool(
            str(cr.get("suggested_rewrite") or "").strip()
        )
        if not has_change and _RX_KEEP_VERDICT.search(verdict_text):
            _demote_to_note(
                cr,
                reason=(
                    "검토 결론이 '현행 유지·수정 불필요' 이므로 필수·권장 수정 목록에서 "
                    "제외하고 참고 항목으로 내립니다."
                ),
                kind="keep_verdict",
            )
            moved.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "kind": "keep_verdict",
                "from_tier": tier,
            })
            continue

        # 적용 여부가 보류인 법률만을 근거로 든 항목. 계약 문언을 직접 확인해
        # 만든 finding 은 법률과 무관하게 계약상 위험이 성립하므로 제외한다.
        if bool(cr.get("is_common_legal_risk")) or bool(cr.get("is_risk_package")):
            continue
        basis_text = "\n".join(str(cr.get(k) or "") for k in _BASIS_FIELDS)
        if not has_change and _RX_APPLICABILITY_HELD.search(basis_text):
            _demote_to_note(
                cr,
                reason=(
                    "근거로 든 법률의 적용 여부가 아직 확정되지 않아(적용 보류) "
                    "필수·권장 수정으로 제시하지 않고 참고 항목으로 내립니다. "
                    "적용요건이 확인되면 다시 검토하십시오."
                ),
                kind="applicability_held",
            )
            moved.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "kind": "applicability_held",
                "from_tier": tier,
            })
    return moved
