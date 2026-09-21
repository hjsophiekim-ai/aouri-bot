"""Payment Risk Package — 수급인의 "돈을 못 받는 경로" 를 하나의 사슬로 본다.

2026-09-18 지시 3항 후단 —
  "특히 '돈을 못 받는 리스크' 가 최대 리스크라고 사용자가 말한 경우,
   Payment Risk Package 로 묶어서
   준공검사 → 기성확정 → 지급유보 → 상계 → 잔금 → 하자·손해 주장
   전체를 연결해서 검토할 것."

왜 사슬로 보는가
──────────────
조항별로 따로 읽으면 여섯 개가 전부 "흔한 조항" 이다.

    준공검사 기한 없음        실무상 흔하다
    + 기성 확정 절차 없음      도급인이 정한다고만 되어 있다
    + 지급유보 사유 무제한     "이의가 있는 경우" 면 족하다
    + 상계 무제한             "일체의 채권으로 상계할 수 있다"
    + 잔금이 준공검사 합격 조건 당연해 보인다
    + 하자·손해 주장으로 공제  손해가 확정되기 전에도 뺀다
    ────────────────────────────────────────────────
    = 도급인이 검사를 미루면 기성이 확정되지 않고, 기성이 확정되지 않으면
      청구권이 발생하지 않으며, 청구해도 유보·상계로 공제된다. 공사는 100%
      끝났는데 받은 돈은 0 일 수 있다. **이것이 수급인의 최대 노출이다.**

이 모듈이 하는 일
──────────────
여섯 고리 각각에 대해 "우리를 실제로 지켜주는 방어 장치가 계약에 있는가" 를
보고, 끊긴 고리를 하나의 finding 으로 묶어 올린다. 조항 하나를 고치는 것으로는
회수가 되지 않기 때문에, 수정안도 여섯 고리를 한 번에 잇는 완성 조문으로 낸다.

설계 원칙
────────
· **수급인 지위에서만** 돈다. 도급인일 때 이 사슬은 우리를 보호하는 구조이므로
  끊겨 있어도 위험이 아니다(오히려 유지해야 한다).
· 조항번호를 지어내지 않는다. 실제 조 구조에서 위치를 찾고, 못 찾으면 신설로
  표시한다(v10 Hallucination Zero).
· 방어 장치가 **다른 조항에 이미 있으면** 그 고리는 present 로 센다 — 계약
  전체를 본 뒤에만 부재를 말한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.review.construction_transaction_model import ConstructionTransactionModel


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass(frozen=True)
class PaymentLink:
    key: str
    label: str
    #: 이 고리가 계약에 **존재**한다는 신호(위험이 발생할 자리).
    trigger: re.Pattern[str]
    #: 그 위험을 실제로 막아 주는 방어 장치.
    defense: re.Pattern[str]
    #: 방어가 없을 때 담당자에게 설명할 말.
    exposure: str


#: 준공검사 → 기성확정 → 지급유보 → 상계 → 잔금 → 하자·손해 주장.
PAYMENT_CHAIN: tuple[PaymentLink, ...] = (
    PaymentLink(
        key="completion_inspection",
        label="① 준공·기성 검사",
        trigger=_rx(r"준공\s*검사|검사(?:를)?\s*(?:받|실시|요청)|검수|기성\s*검사"),
        defense=_rx(
            r"검사(?:를)?[^.\n]{0,40}(?:\d+\s*일|기한)[^.\n]{0,30}(?:이내|내에)"
            r"|(?:\d+\s*일)[^.\n]{0,25}(?:이내|내에)[^.\n]{0,25}(?:검사|검수)"
            r"|(?:이의|통지)(?:가|를)?\s*없(?:는|으면|을)[^.\n]{0,30}(?:합격|완료)(?:한|된)?\s*것으로\s*(?:본다|간주)"
            r"|합격(?:한|된)?\s*것으로\s*(?:본다|간주|의제)"
        ),
        exposure=(
            "검사 기한과 무응답 시 합격 간주 규정이 없으면, 도급인이 검사를 미루는 "
            "것만으로 대금 청구권의 발생 자체가 무기한 늦춰집니다."
        ),
    ),
    PaymentLink(
        key="progress_certification",
        label="② 기성 확정",
        trigger=_rx(r"기성(?:고|금|률|부분|대가)|부분\s*(?:준공|급부)|중도금"),
        defense=_rx(
            r"기성[^.\n]{0,30}(?:월\s*\d회|매월|정기적|\d+\s*일마다)"
            r"|기성[^.\n]{0,30}(?:산정|확정)\s*(?:기준|방법)[^.\n]{0,20}(?:정한다|따른다|명시)"
            r"|기성[^.\n]{0,40}(?:신청|청구)[^.\n]{0,30}(?:\d+\s*일)[^.\n]{0,20}(?:이내|내에)"
            r"|공정률[^.\n]{0,25}(?:따라|비례하여)[^.\n]{0,20}(?:지급|산정)"
        ),
        exposure=(
            "기성 산정 기준·주기·확정 절차가 없으면 얼마를 언제 청구할 수 있는지가 "
            "도급인의 재량이 됩니다. 공사는 진행되는데 청구 가능한 금액이 확정되지 않습니다."
        ),
    ),
    PaymentLink(
        key="payment_withholding",
        label="③ 지급유보",
        trigger=_rx(
            r"유보|지급(?:을)?\s*(?:보류|거절|정지|중단)|지급하지\s*(?:아니|않)"
            r"|이의가?\s*있(?:는|을)\s*경우[^.\n]{0,30}지급"
        ),
        defense=_rx(
            r"유보[^.\n]{0,30}(?:한도|한하여|범위(?:를|에서)|비율)"
            r"|유보(?:할\s*수\s*있는)?\s*(?:사유|경우)(?:는|를)?[^.\n]{0,20}(?:다음|한정|열거)"
            r"|유보[^.\n]{0,40}(?:해소|해제)[^.\n]{0,25}(?:즉시|지체\s*없이|\d+\s*일)"
            r"|유보(?:금|액)[^.\n]{0,25}(?:\d+\s*(?:%|퍼센트))"
        ),
        exposure=(
            "유보 사유와 한도가 제한되지 않으면, 도급인은 다툼이 있다는 주장만으로 "
            "공사대금 전액의 지급을 무기한 보류할 수 있습니다."
        ),
    ),
    PaymentLink(
        key="set_off",
        label="④ 상계·공제",
        trigger=_rx(r"상계|공제(?:한다|할\s*수)|차감(?:한다|할\s*수)|충당(?:한다|할\s*수)"),
        defense=_rx(
            r"상계[^.\n]{0,40}(?:확정된|확정\s*판결|당사자\s*간\s*합의|서면\s*합의)"
            r"|상계[^.\n]{0,30}(?:사전|미리)[^.\n]{0,20}(?:통지|협의|서면)"
            r"|상계(?:할\s*수)?\s*(?:없다|없으며|아니한다)"
            r"|공제[^.\n]{0,40}(?:확정된|합의된|이의\s*없는)"
        ),
        exposure=(
            "상계·공제의 대상 채권이 제한되지 않으면, 도급인이 주장만 하는 미확정 "
            "손해배상채권으로 기성금을 공제할 수 있습니다. 다투는 동안 대금은 이미 빠져나갑니다."
        ),
    ),
    PaymentLink(
        key="final_payment",
        label="⑤ 잔금",
        trigger=_rx(r"잔금|최종\s*(?:대금|기성)|정산(?:금|대금)|준공\s*대금"),
        defense=_rx(
            r"(?:잔금|최종\s*대금|준공\s*대금)[^.\n]{0,40}(?:\d+\s*일)[^.\n]{0,20}(?:이내|내에)"
            r"|지급\s*기한[^.\n]{0,30}(?:\d+\s*일)"
            r"|지연(?:이자|손해금|배상금)[^.\n]{0,30}(?:지급|가산|적용)"
        ),
        exposure=(
            "잔금의 지급기한과 지연이자가 없으면 준공 후에도 지급 시기를 다툴 근거가 "
            "남지 않습니다. 청구권은 있으나 언제까지 지급해야 하는지가 없습니다."
        ),
    ),
    PaymentLink(
        key="defect_and_damages",
        label="⑥ 하자·손해 주장에 의한 공제",
        trigger=_rx(r"하자|손해(?:배상|액)|지체상금|위약(?:금|벌)"),
        defense=_rx(
            r"하자보수보증(?:금|서|증권)[^.\n]{0,30}(?:갈음|대신|제출)"
            r"|(?:하자|손해)[^.\n]{0,40}(?:확정된\s*(?:금액|손해)|합의(?:된|하여))[^.\n]{0,25}(?:공제|상계)"
            r"|지체상금[^.\n]{0,40}(?:총액|한도|상한)"
            r"|하자[^.\n]{0,30}(?:보수(?:를)?\s*요구|시정\s*기회|보수\s*기간)[^.\n]{0,30}(?:부여|먼저)"
        ),
        exposure=(
            "하자·손해 주장이 곧바로 대금 공제로 이어지면, 하자보수보증금 제도가 있어도 "
            "실제 회수는 대금에서 먼저 빠집니다. 보수 기회 부여와 확정 절차가 앞에 있어야 합니다."
        ),
    ),
)


#: 사슬 전체를 잇는 완성 조문. 여섯 고리를 한 조문에서 순서대로 막는다.
PAYMENT_PACKAGE_CLAUSE = (
    "① 도급인은 수급인의 기성 또는 준공 검사 요청을 받은 날부터 14일 이내에 검사를 "
    "완료하고 그 결과를 서면으로 통지한다. 위 기간 내에 검사 결과의 통지가 없는 경우 "
    "해당 기성 또는 준공은 검사에 합격한 것으로 본다.\n"
    "② 기성은 매월 말일을 기준으로 공정률에 따라 산정하며, 수급인의 기성 청구일부터 "
    "14일 이내에 기성금을 지급한다. 준공검사 합격일부터 30일 이내에 잔금을 지급한다.\n"
    "③ 도급인은 다음 각 호의 사유가 있는 경우에 한하여, 그 사유와 직접 관련된 금액의 "
    "범위에서만 대금의 지급을 유보할 수 있다. 유보 사유가 해소된 때에는 지체 없이 "
    "유보한 금액을 지급한다.\n"
    "  1. 해당 기성 부분에 검사 불합격 사유가 있고 그 사유를 서면으로 특정한 경우\n"
    "  2. 법령에 따라 지급이 제한되는 경우\n"
    "④ 도급인은 확정판결, 확정된 중재판정 또는 당사자 간 서면 합의로 확정된 채권에 "
    "한하여 공사대금과 상계·공제할 수 있으며, 상계·공제 7일 전까지 그 내역을 서면으로 "
    "통지한다. 다툼이 있는 미확정 손해배상채권으로는 상계·공제하지 아니한다.\n"
    "⑤ 하자가 발견된 경우 도급인은 수급인에게 상당한 기간을 정하여 하자보수를 먼저 "
    "요구하여야 하며, 수급인이 그 기간 내에 보수하지 아니한 때에 한하여 하자보수보증금 "
    "또는 하자보수에 실제 소요된 비용으로 충당한다. 이 경우에도 공사대금에서 직접 "
    "공제하지 아니한다.\n"
    "⑥ 도급인이 제2항의 지급기한을 지키지 못한 경우 그 다음 날부터 지급일까지 연 "
    "6퍼센트의 지연이자를 가산하여 지급한다."
)


def build_payment_risk_package(
    *, text: str, model: ConstructionTransactionModel,
) -> dict[str, Any]:
    """여섯 고리의 상태를 판정한다.

    수급인 지위에서만 돈다 — 도급인에게 이 사슬은 위험이 아니라 회수 수단이다.
    """
    if not model.is_contractor_side or not model.is_settled:
        return {"applied": False, "links": [], "broken_links": [], "chain_broken": False}

    body = str(text or "")
    links: list[dict[str, Any]] = []
    broken: list[dict[str, Any]] = []

    # ⑦ 유치권 포기는 사슬의 **마지막 고리**다(2026-09-18 수정 지시 4항).
    # 앞의 여섯 고리가 전부 끊겨도 목적물을 점유하고 버틸 수 있으면 회수
    # 가능성이 남는다. 유치권을 포기하면 그 마지막 수단까지 사라지므로,
    # 대금 회수 판단은 이것을 빼고 할 수 없다.
    from runtime.review.construction_lien_waiver import detect_lien_waiver

    lien = detect_lien_waiver(body)

    for link in PAYMENT_CHAIN:
        present = bool(link.trigger.search(body))
        defended = bool(link.defense.search(body))
        row = {
            "key": link.key,
            "label": link.label,
            "present_in_contract": present,
            "defended": defended,
            "exposure": link.exposure if (present and not defended) else "",
        }
        links.append(row)
        if present and not defended:
            broken.append(row)

    if lien.present:
        lien_row = {
            "key": "lien_waiver",
            "label": "⑦ 유치권(채권보전 최후수단)",
            "present_in_contract": True,
            "defended": lien.conditional_already,
            "exposure": (
                "유치권을 조건 없이 포기하면 앞의 여섯 고리가 모두 끊긴 상태에서 "
                "목적물을 점유해 버틸 수단까지 사라집니다. 남는 것은 소송·가압류뿐이고, "
                "그때 우리 회사는 담보 없는 일반채권자입니다."
            ) if not lien.conditional_already else "",
        }
        links.append(lien_row)
        if not lien.conditional_already:
            broken.append(lien_row)

    return {
        "applied": True,
        "our_role": model.our_role,
        "user_flagged_payment_risk": model.payment_risk_priority,
        "lien_waiver": lien.to_dict(),
        "links": links,
        "broken_links": broken,
        # 사슬은 고리 하나만 끊겨도 회수가 막힌다. 다만 한 고리만 비어 있고
        # 나머지가 모두 방어돼 있으면 조항 단위 지적으로 충분하므로, 묶어서
        # 올리는 것은 **둘 이상** 끊겼을 때다.
        "chain_broken": len(broken) >= 2,
    }


#: 조항을 찾지 못했을 때의 표기(v10 Hallucination Zero 규약).
ABSENT_MARKER = "해당 조항 없음 — 신설 필요"


def raw_excerpt(
    text: str, anchor: re.Pattern[str] | None, *, article_number: str | None = None,
) -> str:
    """앵커가 걸린 자리의 **계약 원문 그대로**를 잘라 온다.

    조항 추출기가 돌려주는 텍스트는 줄바꿈·공백이 정규화돼 있어 원문과 글자
    단위로 일치하지 않는다. 그대로 인용으로 쓰면 가짜 인용 게이트가 90% 기준에
    걸려 항목을 걷어낸다(광고 체크리스트 실측: 9건 중 8건 탈락).
    """
    body = str(text or "")
    if anchor is None or not body:
        return ABSENT_MARKER
    # 인용은 지적이 붙은 조 안에서만 자른다 (2026-09-21 2차 지시 3항). 실측:
    # 대금 회수 사슬 지적이 제15조에 붙었는데 인용문은 제1조에서 왔다.
    scoped = False
    if article_number:
        from runtime.review.redline_instruction import article_raw_span

        span = article_raw_span(body, article_number)
        if span is not None:
            # 조 제목 줄은 인용에서 뺀다 — "제15조 (대금의 지급)" 을 원문으로
            # 싣는 것은 담당자에게 아무 정보도 주지 않는다.
            head_end = body.find("\n", span[0])
            start = (head_end + 1) if (0 <= head_end < span[1]) else span[0]
            body = body[start: span[1]]
            scoped = True
    m = anchor.search(body)
    if m is None:
        if not scoped:
            return ABSENT_MARKER
        for line in body.split("\n")[1:]:
            candidate = line.strip()
            if len(candidate) >= 12:
                return candidate[:400]
        return ABSENT_MARKER
    start = body.rfind("\n", 0, m.start()) + 1
    end = body.find("\n", m.end())
    if end == -1:
        end = len(body)
    excerpt = body[start:end].strip()
    return excerpt[:400] if excerpt else ABSENT_MARKER


def payment_package_finding(
    package: dict[str, Any],
    *,
    text: str,
    clauses: list[Any] | None,
    model: ConstructionTransactionModel,
) -> dict[str, Any] | None:
    """끊긴 사슬을 하나의 HIGH finding 으로 만든다.

    사용자가 "돈을 못 받는 리스크가 최대" 라고 말했으면 그 사실을 근거에 적는다 —
    담당자가 왜 이것이 맨 위에 있는지 알 수 있어야 한다.
    """
    if not package.get("applied") or not package.get("chain_broken"):
        return None

    from runtime.review.redline_instruction import (
        build_redline_instruction, find_article_for_pattern,
        location_insert_after_last_paragraph, paragraph_marker,
    )

    broken = package.get("broken_links") or []
    broken_labels = ", ".join(str(b.get("label") or "") for b in broken)
    present_labels = ", ".join(
        str(row.get("label") or "") for row in (package.get("links") or [])
        if row.get("defended")
    )

    anchor = _rx(r"공사\s*(?:대금|금액)|기성|대금(?:의)?\s*지급|지급\s*조건|검사")
    # 대금 회수 사슬은 **대금 조항**에 붙여야 한다. 총칭 패턴에 '검사' 가
    # 들어 있어 문서 순서상 먼저 나오는 준공검사 조항에 걸리면, Semantic
    # Anchor Gate 가 연결을 끊어 '조항 위치 확인 필요' 로 나간다
    # (2026-09-21 실측). 제목이 대금·기성·지급인 조항을 먼저 본다.
    loc = find_article_for_pattern(
        clauses, anchor, title_pattern=_rx(r"대금|기성|지급|정산"),
    )
    marker = paragraph_marker(
        (loc["max_paragraph_number"] + 1) if loc and loc.get("max_paragraph_number") else 1
    )
    display_path = f"제{loc['article_number']}조" if loc else "신설 조항"
    # 인용은 **계약 원문에서 직접** 잘라 온다. 조항 추출기의 정규화된 텍스트를
    # 그대로 쓰면 가짜 인용 게이트(90% 일치)에 걸려 항목이 통째로 사라진다.
    original = raw_excerpt(
        str(text or ""), anchor,
        article_number=(str(loc["article_number"]) if loc else None),
    )

    problem = (
        "공사대금 회수 경로가 준공검사 → 기성확정 → 지급유보 → 상계 → 잔금 → "
        "하자·손해 주장으로 이어지는데, 그 사슬에서 우리 회사를 지켜 주는 고리가 "
        f"끊겨 있습니다. 끊긴 고리: {broken_labels}."
        + (f" 확인된 방어 장치: {present_labels}." if present_labels else " 확인된 방어 장치: 없음.")
    )
    reason_lines = [str(b.get("exposure") or "") for b in broken if b.get("exposure")]
    legal_reason = (
        "각 조항은 따로 보면 실무상 흔한 문언이지만, 여섯 고리가 동시에 작동하면 "
        "공사를 전부 이행하고도 대금을 받지 못하는 결과가 됩니다. 도급인이 검사를 "
        "미루면 기성이 확정되지 않고, 기성이 확정되지 않으면 청구권이 발생하지 않으며, "
        "청구하더라도 무제한 유보·상계로 공제됩니다. 민법 제665조는 도급인의 보수 지급을 "
        "일의 완성에 대응하는 의무로 정하고 있으나, 검사·확정 절차를 도급인의 재량에 맡긴 "
        "계약에서는 그 대응관계가 사실상 무력화됩니다.\n" + "\n".join(reason_lines)
    ).strip()

    clause_text = f"{marker} {PAYMENT_PACKAGE_CLAUSE}" if not loc else PAYMENT_PACKAGE_CLAUSE
    edit_location = location_insert_after_last_paragraph(loc) if loc else "계약 말미에 신설"

    priority_note = (
        "담당자가 '돈을 못 받는 리스크가 최대'라고 밝힌 사안이므로 이 항목을 협상 "
        "1순위로 둡니다. "
        if package.get("user_flagged_payment_risk") else ""
    )

    finding: dict[str, Any] = {
        "clause_id": "CWP-PAYMENT-PACKAGE",
        "article_number": (loc["article_number"] if loc else None),
        "display_path": display_path,
        "clause_title": "공사대금 회수 사슬(준공검사–기성–유보–상계–잔금–하자공제)",
        "clause_topic": "payment",
        "risk_tier": "HIGH",
        "severity": "HIGH",
        "counsel_severity": "HIGH",
        "high_risk": True,
        "must_fix": True,
        "approval_required": True,
        "review_tier": "MUST",
        "issue_title": "공사대금 회수 사슬이 끊겨 있어 공사를 완료하고도 대금을 받지 못할 수 있음",
        "original_text": original,
        "problem": problem,
        "legal_business_reason": legal_reason,
        "suggested_rewrite": clause_text,
        "recommendation_text": clause_text,
        "proposed_revision": clause_text,
        "rewrite_reason": problem,
        "negotiation_position": (
            priority_note
            + "여섯 고리를 한꺼번에 요구하면 거부당하기 쉽습니다. ① 검사기한과 무응답 "
            "합격간주, ② 상계 대상을 확정 채권으로 제한, 이 둘을 먼저 요구하십시오. "
            "둘 다 도급인에게 추가 비용을 발생시키지 않고 절차만 정하는 것이어서 "
            "거부 명분이 약합니다. 유보 한도와 지연이자는 그다음 단계로 둡니다."
        ),
        "worst_case_scenario": (
            "공정률 100%로 준공했으나 도급인이 검사 통지를 하지 않아 기성이 확정되지 "
            "않고, 그 사이 도급인이 타 공종 지연을 이유로 손해배상채권을 주장해 잔금 "
            "전액을 상계·유보하는 상황. 공사원가는 전부 투입된 상태에서 회수액이 0이 "
            "되고, 회수를 위해서는 소송으로 채권 존부를 다투어야 합니다."
        ),
        "high_severity_basis": (
            f"payment_risk_package: 끊긴 고리 {len(broken)}개 — {broken_labels}"
        )[:400],
        "confidence": 0.9,
        "is_mandatory": True,
        "is_construction_checklist": True,
        "is_payment_risk_package": True,
        "payment_chain_broken_links": [str(b.get("key") or "") for b in broken],
        "detected_issue_list": [
            {"issue_title": "[Payment Risk Package] 공사대금 회수 사슬 단절"},
        ],
    }
    finding["redline_instruction"] = build_redline_instruction(
        clause_id=finding["clause_id"],
        severity="HIGH",
        edit_location=edit_location,
        edit_type="insert_after" if loc else "new_clause",
        replacement_text=clause_text,
        reason=problem,
    )
    return finding
