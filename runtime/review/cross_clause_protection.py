"""다른 조항의 보호장치를 확인해 false positive 를 막는다
(2026-09-09 지시 항목 5·6).

한 조항만 보고 "상한이 없다 / 예외가 없다"고 결론 내리면, 계약서 다른 곳에
이미 상한·예외·보호장치가 있는 경우 그 finding 은 틀린 지적이 된다. 실무에서
이런 오탐은 신뢰를 가장 빠르게 깎는다 — 상대방 변호사가 "제O조에 이미 있는데
못 보셨나요"라고 지적하는 순간 검토 전체의 권위가 사라진다.

실측 사례(호텔 신축 공사도급계약):

    갑지 13. 지체 상금률 : 총계약금액 1/1,000(계약금액의 10%이내)   ← 갑지에 상한
    제30조 제1항         지체상금률(1/1000)을 계약금액에 곱하여
    제30조 제5항         지체상금 최대금액은 계약금액의 10% 까지     ← 본문에 상한

지체상금 상한이 **갑지와 본문 두 곳**에 있다. 제1항만 읽고 "누계 상한 없음"
이라고 하면 오탐이다.

이 모듈이 하는 일:
  1. `find_protections()`  계약 전체에서 보호장치(상한·예외·면책·보험·정산)를
     주제별로 수집한다.
  2. `absence_claims()`    finding 이 "없다"고 주장하는 대상을 식별한다.
  3. `suppress_false_absence_claims()` 주장 대상의 보호장치가 실제로
     존재하면 그 finding 을 제거하고 근거 조항을 남긴다.

설계: 조항번호를 하드코딩하지 않는다. 주제(topic) 단위로 "보호장치 문형"을
찾고, 같은 주제의 부재 주장과 맞춘다. 계약서 구조가 달라도 작동한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: 부재 주장을 무효화한 이유 코드.
SUPPRESS_REASON = "cross_clause_protection_exists"


@dataclass(frozen=True)
class ProtectionPattern:
    topic: str
    pattern: re.Pattern[str]
    #: 이 문형이 무엇을 보호하는지 — 리포트에 근거로 그대로 쓴다.
    label: str


def _p(topic: str, regex: str, label: str) -> ProtectionPattern:
    return ProtectionPattern(topic, re.compile(regex, re.IGNORECASE | re.DOTALL), label)


#: "이 주제에 보호장치가 있다"를 증명하는 문형.
#: 숫자(상한율·기간)를 포함하도록 요구해, 단순 언급과 실제 상한을 구분한다.
_PROTECTIONS: tuple[ProtectionPattern, ...] = (
    # 지체상금·위약금 누계 상한
    _p("late_penalty_cap",
       r"지체상금[^.\n]{0,60}?(?:최대|한도|상한|초과할\s*수\s*없|이내|까지로\s*한)[^.\n]{0,30}?\d",
       "지체상금 누계 상한"),
    _p("late_penalty_cap",
       r"\d+\s*(?:%|퍼센트)[^.\n]{0,20}?(?:이내|까지)[^.\n]{0,20}?지체상금"
       r"|지체\s*상금률[^.\n]{0,40}?\(\s*[^)]*?\d+\s*%\s*이내\s*\)",
       "지체상금률 표기 내 상한"),
    _p("late_penalty_cap",
       r"liquidated\s+damages[^.\n]{0,80}?(?:shall\s+not\s+exceed|capped|maximum)[^.\n]{0,30}?\d",
       "liquidated damages cap"),
    # 손해배상 총액 상한
    _p("liability_cap",
       r"(?:손해배상|배상책임|책임)[^.\n]{0,50}?(?:총액|누계|합계)?[^.\n]{0,20}?"
       r"(?:한도|상한|초과할\s*수\s*없|넘지\s*아니)[^.\n]{0,30}?\d",
       "손해배상 총액 상한"),
    _p("liability_cap",
       r"(?:aggregate|total)\s+liability[^.\n]{0,60}?(?:shall\s+not\s+exceed|limited\s+to)",
       "aggregate liability cap"),
    # 간접·특별손해 배제
    _p("consequential_exclusion",
       r"(?:간접|특별|결과적)\s*손해[^.\n]{0,40}?(?:제외|배제|배상하지\s*아니|책임을\s*지지\s*아니)"
       r"|영업이익\s*상실[^.\n]{0,30}?(?:제외|배제)",
       "간접·특별손해 배제"),
    # 불가항력 면책
    _p("force_majeure",
       r"불가항력[^.\n]{0,80}?(?:책임을\s*지지\s*아니|면(?:책|제)|의무가\s*(?:정지|면제))"
       r"|force\s+majeure",
       "불가항력 면책"),
    # 귀책 없는 경우의 면책·예외
    _p("fault_exception",
       r"(?:귀책사유|책임\s*있는\s*사유)[^.\n]{0,40}?(?:없는|아닌|없을)\s*경우[^.\n]{0,40}?"
       r"(?:면(?:책|제)|책임을\s*지지\s*아니|부담하지\s*아니)"
       r"|(?:도급인|발주자|갑)[^.\n]{0,10}?귀책[^.\n]{0,40}?(?:지체상금|책임)[^.\n]{0,20}?"
       r"(?:부과하지|지급하지|면)",
       "귀책 없는 경우 면책"),
    # 기간 연장 사유 (지체 판단의 예외)
    _p("time_extension",
       r"(?:공사|계약)\s*기간[^.\n]{0,30}?연장[^.\n]{0,60}?(?:요구할\s*수\s*있|승인|조치)"
       r"|준공기한[^.\n]{0,40}?연장",
       "기간 연장 청구권"),
    # 보험
    _p("insurance",
       r"보험[^.\n]{0,60}?(?:가입|부보|체결)[^.\n]{0,40}?(?:하여야|한다)"
       r"|(?:산재|영업배상|건설공사)\s*보험",
       "보험 부보 의무"),
    # 대금 미지급 시 우리 측 보호(중지권·지연이자)
    _p("payment_default_remedy",
       r"(?:지급|기성금|정산금)[^.\n]{0,40}?(?:지연|지체)[^.\n]{0,60}?"
       r"(?:중지할\s*수\s*있|지연이자|해지할\s*수\s*있)",
       "대금 미지급 시 중지·지연이자"),
    # 설계변경 시 금액·기간 조정
    _p("change_order_adjustment",
       r"(?:설계\s*변경|공사\s*내용\s*변경|추가\s*공사)[^.\n]{0,80}?"
       r"(?:계약금액[^.\n]{0,20}?(?:조정|증액|변경)|공사기간[^.\n]{0,20}?(?:조정|연장))",
       "설계변경 시 금액·기간 조정"),
    # 하자책임 기간 제한
    _p("defect_period_limit",
       r"하자(?:보수|담보)[^.\n]{0,40}?(?:기간|책임기간)[^.\n]{0,30}?\d+\s*(?:년|개월)",
       "하자책임 기간 제한"),
    # 상계 시 절차·통지
    _p("setoff_process",
       r"상계[^.\n]{0,60}?(?:통지|협의|서면|사전)|공제[^.\n]{0,40}?(?:통지|협의)",
       "상계 시 통지·협의 절차"),
)

#: finding 이 "없다"고 주장하는 문형 → 그 주장이 겨냥하는 주제.
_ABSENCE_CLAIMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("late_penalty_cap", re.compile(
        r"지체상금[^.\n]{0,40}?(?:누계\s*)?(?:상한|한도|cap)[^.\n]{0,20}?"
        r"(?:없|부재|미설정|없다)", re.IGNORECASE)),
    ("late_penalty_cap", re.compile(
        r"(?:상한|누계\s*상한)[^.\n]{0,20}?(?:없|부재)[^.\n]{0,40}?지체상금", re.IGNORECASE)),
    ("liability_cap", re.compile(
        r"(?:손해배상|배상)[^.\n]{0,40}?(?:한도|상한|총액\s*제한)[^.\n]{0,20}?"
        r"(?:없|부재|미설정)|무제한\s*(?:배상|책임)", re.IGNORECASE)),
    ("consequential_exclusion", re.compile(
        r"(?:간접|특별|결과적)\s*손해[^.\n]{0,40}?(?:제외|배제)[^.\n]{0,20}?(?:없|부재)"
        r"|간접손해[^.\n]{0,20}?포함", re.IGNORECASE)),
    ("force_majeure", re.compile(
        r"불가항력[^.\n]{0,40}?(?:규정|조항|면책)[^.\n]{0,20}?(?:없|부재|누락)", re.IGNORECASE)),
    ("fault_exception", re.compile(
        r"귀책[^.\n]{0,40}?(?:구분|예외)[^.\n]{0,20}?(?:없|부재|불명)"
        r"|무과실[^.\n]{0,20}?책임", re.IGNORECASE)),
    ("time_extension", re.compile(
        r"(?:공사|계약)\s*기간\s*연장[^.\n]{0,30}?(?:없|부재|불가)"
        r"|연장\s*청구권[^.\n]{0,20}?(?:없|부재)", re.IGNORECASE)),
    ("insurance", re.compile(
        r"보험[^.\n]{0,30}?(?:가입|부보)[^.\n]{0,20}?(?:의무\s*)?(?:없|부재|누락)", re.IGNORECASE)),
    ("payment_default_remedy", re.compile(
        r"대금\s*(?:미지급|지연)[^.\n]{0,40}?(?:대응|구제|중지권)[^.\n]{0,20}?(?:없|부재)",
        re.IGNORECASE)),
    ("change_order_adjustment", re.compile(
        r"(?:설계변경|추가공사)[^.\n]{0,40}?(?:금액|대금)[^.\n]{0,20}?"
        r"(?:조정|증액)[^.\n]{0,20}?(?:없|부재|불가)", re.IGNORECASE)),
    ("defect_period_limit", re.compile(
        r"하자[^.\n]{0,30}?(?:기간|책임기간)[^.\n]{0,20}?(?:없|무제한|제한\s*없)", re.IGNORECASE)),
    ("setoff_process", re.compile(
        r"상계[^.\n]{0,40}?(?:절차|통지|협의)[^.\n]{0,20}?(?:없|부재)", re.IGNORECASE)),
)


def find_protections(text: str) -> dict[str, list[str]]:
    """계약 전체에서 주제별 보호장치를 수집한다. topic -> [근거 문구]"""
    hay = text or ""
    out: dict[str, list[str]] = {}
    for prot in _PROTECTIONS:
        m = prot.pattern.search(hay)
        if not m:
            continue
        snippet = re.sub(r"\s+", " ", m.group(0)).strip()
        out.setdefault(prot.topic, []).append(f"{prot.label}: …{snippet[:110]}…")
    return out


def _finding_claim_text(cr: dict[str, Any]) -> str:
    keys = ("issue_title", "problem", "rewrite_reason", "legal_business_reason")
    return "\n".join(str(cr.get(k) or "") for k in keys)


def absence_claims(cr: dict[str, Any]) -> list[str]:
    """이 finding 이 '없다'고 주장하는 주제 목록."""
    blob = _finding_claim_text(cr)
    return sorted({topic for topic, pat in _ABSENCE_CLAIMS if pat.search(blob)})


_DOWNGRADE = {"CRITICAL": "MEDIUM", "HIGH": "MEDIUM", "MEDIUM": "LOW"}


def reconcile_absence_claims(
    clause_results: list[dict[str, Any]] | None, *, contract_text: str,
) -> dict[str, Any]:
    """"없다"는 주장이 사실과 다르면 **삭제하지 않고 정정**한다.

    삭제가 아니라 정정인 이유:

      1. 리스크 자체가 사라지는 것이 아니다. 상한이 있어도 그 수준이 과도하면
         여전히 협상 대상이고, 시니어 변호사는 "상한은 있으나 10%다"라고
         정확히 말한다 — 조항을 통째로 지우면 그 정보가 사라진다.
      2. 하위 정합성 게이트(REVIEW_FAILED_GLOBAL_REASONING 등)는 금전 리스크
         finding 이 최종 결과에 살아 있는지를 검사한다. 오탐이라며 지워버리면
         게이트가 "금전 리스크 미확인"으로 판단해 수정본 다운로드를 막는다
         (2026-09-09 실측). 표시용 판단이 정합성 게이트를 깨서는 안 된다.

    그래서 이 함수는 주장을 사실로 교체하고 등급을 한 단계 내린다 —
    HIGH→MEDIUM, MEDIUM→LOW. 결과적으로 "꼭 고쳐야 할 조항"에서 빠지고
    "협상 가능/수용 가능"으로 내려간다(항목 11).

    판정 기준은 엄격하게 잡는다 — finding 이 주장하는 **그 주제**의 보호장치가
    계약 전체에서 발견될 때만이다. 다른 주제의 상한이 있다고 해서 이 주장이
    틀린 것은 아니기 때문이다.
    """
    protections = find_protections(contract_text)
    corrected: list[dict[str, Any]] = []
    for cr in (clause_results or []):
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        if bool(cr.get("absence_claim_corrected")):
            continue  # 멱등
        claims = absence_claims(cr)
        if not claims:
            continue
        hit = [t for t in claims if protections.get(t)]
        if not hit:
            continue
        evidence = [e for t in hit for e in protections[t]]
        before = str(cr.get("risk_tier") or cr.get("severity") or "").upper()
        after = _DOWNGRADE.get(before, before)

        note = (
            "※ 교차조항 확인: 계약 다른 조항에 이미 해당 보호장치가 존재한다 — "
            + " / ".join(evidence[:2])
            + ". 따라서 '부재'가 아니라 '수준의 적정성'이 쟁점이다."
        )
        for key in ("rewrite_reason", "legal_business_reason"):
            base = str(cr.get(key) or "").strip()
            if base:
                cr[key] = f"{base}\n{note}"
        if not str(cr.get("rewrite_reason") or "").strip():
            cr["rewrite_reason"] = note

        if after != before:
            cr["risk_tier"] = after
            if str(cr.get("severity") or "").upper() in _DOWNGRADE or cr.get("severity"):
                cr["severity"] = after
        cr["absence_claim_corrected"] = True
        cr["false_absence_claim_topics"] = hit
        cr["cross_clause_protection_evidence"] = evidence[:4]
        cr["severity_demotion_reason"] = SUPPRESS_REASON

        corrected.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or ""),
            "topics": hit,
            "from": before,
            "to": after,
            "evidence": evidence[:4],
        })
    return {
        "protections_found": {k: v[:3] for k, v in protections.items()},
        "corrected": corrected,
        "corrected_count": len(corrected),
    }


def annotate_related_protections(
    clause_results: list[dict[str, Any]] | None, *, contract_text: str,
) -> int:
    """제거하지 않은 finding 에도 관련 보호장치를 붙여 준다(항목 5).

    상한이 있더라도 그 수준이 과도하면 여전히 협상 대상이다. 그럴 때
    "상한은 있으나 계약금액의 30%로 과도하다"처럼 **사실을 반영한 지적**을
    할 수 있도록, 관련 조항 근거를 finding 에 실어 보낸다.
    """
    protections = find_protections(contract_text)
    n = 0
    for cr in (clause_results or []):
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        topics = absence_claims(cr)
        related = [e for t in topics for e in protections.get(t, [])]
        if related:
            cr.setdefault("cross_clause_protection_evidence", related[:4])
            n += 1
    return n
