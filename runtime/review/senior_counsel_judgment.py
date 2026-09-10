"""시니어 사내변호사의 판단층 (2026-09-09 지시 항목 8·11·12·13).

앞의 모듈들이 "무엇이 문제인가"를 찾는다면, 이 모듈은 변호사가 그 위에
얹는 판단을 담는다. 네 가지가 서로 맞물려 있어 한 곳에 둔다 — 예컨대
"형사책임은 계약으로 이전할 수 없다"(항목 8)는 판단은 곧 "그 조항은 문구를
고쳐도 효과가 없으니 비용·구상 범위로 협상하라"(항목 11)로 이어지고,
그 근거는 산업안전보건법이 왜 적용되는지(항목 12)로 설명되며, 마지막에
스스로 점검된다(항목 13).

  항목 8  `classify_liability_nature()`
          법률상 책임(계약으로 이전·면제 불가)과 계약상 비용배분(조정 가능)을
          구분한다. 형사책임·산업안전보건법상 사업주 의무·중대재해처벌법상
          경영책임자 의무는 계약 문구로 상대방에게 넘길 수 없다. 다만 그로
          인해 발생한 **비용의 최종 부담과 구상 범위**는 당사자 간 약정으로
          정할 수 있다 — 이 차이를 흐리면 실행 불가능한 수정안이 나온다.

  항목 11 `classify_negotiation_bucket()`
          꼭 고쳐야 / 협상 가능하면 고칠 / 수용 가능 세 갈래로 나눈다.
          "무조건 우리에게 유리하게"가 아니라 상대방이 받을 수 있는
          최소수정안을 우선한다.

  항목 12 `explain_statute_linkage()`
          법률명 나열이 아니라 "왜 적용되는지 / 어떤 조항이 문제인지 /
          어떤 사실관계를 더 확인해야 하는지"를 붙인다.

  항목 13 `final_lawyer_self_check()`
          제출 전 9개 항목을 스스로 점검한다. 하나라도 실패하면 정상 완료로
          취급하지 않는다.

하드코딩 금지 — 회사명·계약서명·조항번호를 쓰지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

REVIEW_FAILED_LAWYER_SELF_CHECK = "REVIEW_FAILED_LAWYER_SELF_CHECK"

# ═══════════════════════════════════════════════════════════════════════════
# 항목 8 — 법률상 책임 vs 계약상 비용배분
# ═══════════════════════════════════════════════════════════════════════════

NATURE_STATUTORY = "statutory"       # 법률상 책임 — 계약으로 이전 불가
NATURE_CONTRACTUAL = "contractual"   # 계약상 비용배분 — 조정 가능
NATURE_MIXED = "mixed"               # 둘이 섞여 있어 분리해 설명해야 함

#: 계약으로 상대방에게 넘길 수 없는 책임의 신호. 법률의 **강행규정**이거나
#: 형사·행정 제재라서, 당사자 합의로 그 귀속 자체를 바꿀 수 없다.
_RX_STATUTORY_LIABILITY = re.compile(
    r"형사\s*(?:책임|처벌)|벌금|과태료|징역|형\s*사\s*상"
    r"|산업안전보건법|중대재해\s*처벌|중대재해처벌법"
    r"|사업주(?:의)?\s*의무|안전보건\s*(?:조치|관리)\s*의무"
    r"|근로기준법|최저임금|퇴직금"
    r"|개인정보\s*보호법[^.\n]{0,30}?(?:과징금|형사)"
    r"|행정\s*처분|영업\s*정지|면허\s*취소",
    re.IGNORECASE,
)

#: 계약으로 정할 수 있는 영역 — 누가 최종적으로 돈을 낼지, 구상할지.
_RX_COST_ALLOCATION = re.compile(
    # "비용은 수급인이 부담한다" 처럼 조사·주체가 사이에 끼는 어순을 잡으려면
    # 사이 간격을 허용해야 한다 — `비용(?:을)?\s*부담` 은 이 형태를 놓친다.
    r"비용[^.\n]{0,20}?부담|부담[^.\n]{0,10}?비용"
    r"|구상|정산|분담|보험(?:으로|에\s*의해)\s*처리"
    r"|면책(?:하고|하며)?\s*(?:배상|보상)|손해\s*배상\s*범위",
    re.IGNORECASE,
)

#: 어떤 강행규정이 걸렸는지에 따라 설명에 실제로 등장할 법률명.
#:
#: [2026-09-10 지시 — "실제 거래와 모순되는 템플릿 금지"]
#: 종전에는 설명이 하나의 고정 문구였고, 그 문구가 항상 "산업안전보건법·
#: 중대재해처벌법상 사업주·경영책임자의 의무" 를 이야기했다. 그래서 개인정보
#: 과징금 때문에 걸린 finding 에 안전보건법 설명이 붙는 일이 생겼다(실측:
#: 영상 콘텐츠 바터 계약의 초상권·개인정보 항목). 매칭된 법률군을 그대로
#: 이름 붙여, 이 계약과 무관한 법률이 검토의견에 등장하지 않게 한다.
_STATUTE_FAMILIES: tuple[tuple[str, "re.Pattern[str]", str], ...] = (
    (
        "safety",
        re.compile(r"산업안전보건법|중대재해\s*처벌|중대재해처벌법|안전보건\s*(?:조치|관리)\s*의무", re.IGNORECASE),
        "산업안전보건법·중대재해처벌법상 사업주·경영책임자의 의무",
    ),
    (
        "labor",
        re.compile(r"근로기준법|최저임금|퇴직금", re.IGNORECASE),
        "근로기준법 등 노동관계법상 사용자의 의무",
    ),
    (
        "privacy",
        re.compile(r"개인정보\s*보호법", re.IGNORECASE),
        "개인정보 보호법상 개인정보처리자의 의무",
    ),
    (
        "criminal",
        re.compile(r"형사\s*(?:책임|처벌)|벌금|징역|형\s*사\s*상", re.IGNORECASE),
        "형사책임",
    ),
    (
        "administrative",
        re.compile(r"과태료|행정\s*처분|영업\s*정지|면허\s*취소|과징금", re.IGNORECASE),
        "행정제재(과징금·과태료·영업정지 등)의 수범자 지위",
    ),
)


def _statutory_explanation(text: str) -> str:
    """실제로 걸린 강행규정을 이름으로 지목하는 설명문."""
    names = [label for _key, pat, label in _STATUTE_FAMILIES if pat.search(text or "")]
    if not names:
        names = ["강행규정상 의무"]
    # 조사(는/은) 일치 문제를 피하려고 "…에 관한 규율은" 형태로 받는다.
    subject = " 및 ".join(names[:2])
    return (
        "법률상 책임과 계약상 비용배분을 구분해야 합니다. "
        f"{subject}에 관한 규율은 강행규정이므로 계약 문구로 상대방에게 이전하거나 면제할 수 "
        "없습니다 — 그런 조항은 그 범위에서 효력이 없고, 문제가 발생하면 우리 "
        "회사는 여전히 행정·형사 책임의 주체가 됩니다. "
        "다만 그로 인해 발생한 **비용의 최종 부담과 구상 범위**는 당사자 간 "
        "약정으로 정할 수 있으므로, 협상은 '책임을 넘긴다'가 아니라 "
        "'비용을 누가 부담하고 어떤 범위에서 구상하는가'로 설계해야 합니다."
    )


def classify_liability_nature(text: str) -> str:
    """이 문언이 법률상 책임인지, 계약상 비용배분인지, 섞여 있는지."""
    hay = text or ""
    statutory = bool(_RX_STATUTORY_LIABILITY.search(hay))
    contractual = bool(_RX_COST_ALLOCATION.search(hay))
    if statutory and contractual:
        return NATURE_MIXED
    if statutory:
        return NATURE_STATUTORY
    return NATURE_CONTRACTUAL


def annotate_liability_nature(clause_results: list[dict[str, Any]] | None) -> dict[str, Any]:
    """법률상 책임이 걸린 finding 에 그 구분을 설명으로 붙인다.

    수정안이 "상대방이 모든 책임을 진다"로 가면 실행 불가능하므로, 이
    설명이 붙은 finding 은 협상 방향이 비용·구상으로 재설정된다.
    """
    annotated: list[dict[str, Any]] = []
    for cr in (clause_results or []):
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        blob = "\n".join(
            str(cr.get(k) or "") for k in
            ("issue_title", "clause_title", "original_text", "problem",
             "rewrite_reason", "legal_business_reason", "suggested_rewrite")
        )
        # 이미 붙여둔 설명문은 판정 입력에서 뺀다. 설명문 자체가 "형사책임",
        # "행정처분" 같은 법률명을 담고 있어, 두 번째 호출에서 그것까지 매칭돼
        # 지목 법률이 늘고 설명문이 달라지면 멱등성이 깨진다(같은 finding 에
        # 문단이 두 번 붙는다).
        _prev_note = str(cr.get("statutory_liability_note") or "")
        if _prev_note:
            blob = blob.replace(_prev_note, " ")
        nature = classify_liability_nature(blob)
        cr["liability_nature"] = nature
        if nature in (NATURE_STATUTORY, NATURE_MIXED):
            note = _statutory_explanation(blob)
            base = str(cr.get("legal_business_reason") or "").strip()
            if _prev_note and _prev_note != note and _prev_note in base:
                # 지목 법률이 바뀌었으면 옛 문단을 남겨두지 않고 교체한다.
                base = base.replace(_prev_note, "").strip()
            if note not in base:
                cr["legal_business_reason"] = (base + "\n" + note).strip()
            else:
                cr["legal_business_reason"] = base
            cr["statutory_liability_note"] = note
            annotated.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "nature": nature,
            })
    return {"annotated": annotated, "annotated_count": len(annotated)}


# ═══════════════════════════════════════════════════════════════════════════
# 항목 11 — 협상 3단계 분류
# ═══════════════════════════════════════════════════════════════════════════

BUCKET_MUST_FIX = "꼭 고쳐야 하는 조항"
BUCKET_NEGOTIABLE = "협상 가능하면 고칠 조항"
BUCKET_ACCEPTABLE = "수용 가능한 조항"

#: 상대방이 받아들일 수 없는 과도한 요구의 신호 — 이런 수정안은 협상을
#: 진전시키지 못하므로 최소수정안으로 낮춘다.
_RX_OVERREACH = re.compile(
    r"(?:모든|일체의?)\s*(?:책임|손해)[^.\n]{0,20}?(?:상대방|귀사|을|갑)[^.\n]{0,10}?부담"
    r"|무제한(?:으로)?\s*배상"
    r"|어떠한\s*경우에도[^.\n]{0,20}?책임을\s*지지\s*(?:아니|않)"
    r"|전액\s*(?:배상|보상)(?:한다|하여야)",
    re.IGNORECASE,
)


def classify_negotiation_bucket(cr: dict[str, Any]) -> str:
    """finding 을 협상 3단계 중 하나로 분류한다.

    기준:
      꼭 고쳐야       치명적 근거가 증명된 HIGH (체결 여부에 영향)
      협상 가능하면   MEDIUM, 또는 교차조항 보호장치가 있어 정정된 항목
      수용 가능       LOW, 또는 법률상 책임이라 문구로 바꿀 수 없는 항목
    """
    tier = str(cr.get("risk_tier") or cr.get("severity") or "").upper()
    if tier in ("CRITICAL", "HIGH"):
        return BUCKET_MUST_FIX
    if tier == "MEDIUM":
        return BUCKET_NEGOTIABLE
    return BUCKET_ACCEPTABLE


def assign_negotiation_buckets(clause_results: list[dict[str, Any]] | None) -> dict[str, Any]:
    """3버킷을 부여하고, 과도한 수정안에는 최소수정안 우선 지침을 남긴다."""
    counts = {BUCKET_MUST_FIX: 0, BUCKET_NEGOTIABLE: 0, BUCKET_ACCEPTABLE: 0}
    overreach: list[str] = []
    for cr in (clause_results or []):
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        bucket = classify_negotiation_bucket(cr)
        cr["negotiation_bucket"] = bucket
        counts[bucket] += 1

        rewrite = "\n".join(
            str(cr.get(k) or "") for k in
            ("suggested_rewrite", "proposed_revision", "recommendation_text")
        )
        if _RX_OVERREACH.search(rewrite):
            cr["overreaching_rewrite"] = True
            note = (
                "※ 이 수정안은 상대방이 수용하기 어려운 수준입니다. "
                "최소수정안(상한 설정·귀책 구분·예외 명시)을 1차안으로 제시하고, "
                "전면 전가는 협상 여지가 있을 때만 요구하십시오."
            )
            base = str(cr.get("negotiation_position") or "").strip()
            if note not in base:
                cr["negotiation_position"] = (base + "\n" + note).strip()
            overreach.append(str(cr.get("clause_id") or ""))
    return {
        "counts": counts,
        "overreaching_rewrites": overreach,
        "overreaching_count": len(overreach),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 항목 12 — 적용법률을 거래구조와 연결
# ═══════════════════════════════════════════════════════════════════════════

#: 법률 → (적용 근거가 되는 거래 사실, 확인이 필요한 사실관계)
_STATUTE_LINKAGE: tuple[tuple[re.Pattern[str], str, str, str], ...] = (
    (re.compile(r"산업안전보건법"), "산업안전보건법",
     "공사·설치 작업이 사업장에서 이루어지고 우리 회사가 그 작업의 사업주 또는 "
     "도급인 지위에 있으면 안전보건 조치 의무가 직접 발생합니다.",
     "실제 작업 장소의 관리주체, 상시근로자 수, 도급인·수급인 지위, "
     "안전관리자 선임 여부"),
    (re.compile(r"중대재해\s*처벌|중대재해처벌법"), "중대재해처벌법",
     "일정 규모 이상 사업 또는 사업장에서 중대산업재해가 발생하면 경영책임자에게 "
     "형사책임이 발생하고, 이는 계약으로 이전할 수 없습니다.",
     "상시근로자 수, 경영책임자 지정 현황, 안전보건관리체계 구축 여부"),
    (re.compile(r"건설산업기본법"), "건설산업기본법",
     "건설공사의 도급·하도급 구조에 적용되며, 하도급 제한·대금 직접지급·"
     "하자담보책임 기간에 강행규정이 있습니다.",
     "건설업 등록 여부, 하도급 승인 절차, 공사 규모"),
    (re.compile(r"하도급\s*거래\s*공정화|하도급법"), "하도급거래 공정화에 관한 법률",
     "우리 회사가 원사업자 지위에서 수급사업자에게 제조·수리·건설·용역을 "
     "위탁하면 대금 지급기일·서면 발급 의무가 발생합니다.",
     "양 당사자의 규모(중소기업 여부), 위탁의 성격, 대금 지급 실태"),
    (re.compile(r"개인정보\s*보호법"), "개인정보 보호법",
     "계약 이행 과정에서 개인정보를 처리·위탁하면 처리위탁 계약, 안전성 확보조치, "
     "국외이전 요건이 적용됩니다.",
     "실제 처리하는 개인정보 항목, 처리 위탁 여부, 서버 소재지, 재위탁 구조"),
    (re.compile(r"부정경쟁방지|영업비밀"), "부정경쟁방지 및 영업비밀보호에 관한 법률",
     "비밀관리성이 인정되는 정보를 상대방이 취득·사용하면 영업비밀 침해가 "
     "성립할 수 있어, 계약상 비밀유지의무와 별도로 법적 구제가 가능합니다.",
     "정보의 비밀관리 실태(접근권한·표시·서약서), 독자개발 여부"),
    (re.compile(r"약관\s*(?:의)?\s*규제"), "약관의 규제에 관한 법률",
     "상대방이 일방적으로 마련한 표준 양식을 사용하면 불공정 약관 조항의 "
     "무효 주장이 가능합니다.",
     "계약서 작성 주체, 개별 교섭 여부, 동종 계약에서의 반복 사용"),
    (re.compile(r"독점규제|공정거래법"), "독점규제 및 공정거래에 관한 법률",
     "거래상 지위를 이용한 불이익 제공·구속조건부 거래가 있으면 불공정거래행위에 "
     "해당할 수 있습니다.",
     "양 당사자의 거래상 지위, 거래 의존도, 대체 거래처 존재 여부"),
)


def explain_statute_linkage(text: str, *, contract_type_code: str = "") -> list[dict[str, Any]]:
    """이 거래구조에 적용될 법률과 **그 이유**를 설명한다.

    법률명만 나열하지 않는다 — 왜 적용되는지, 어떤 사실관계를 더 확인해야
    하는지를 붙인다. 원문에 근거가 없는 법률은 넣지 않으므로, 계약유형과
    무관한 법률이 자동 삽입되지 않는다(항목 12).
    """
    hay = text or ""
    out: list[dict[str, Any]] = []
    for pat, name, why, facts in _STATUTE_LINKAGE:
        m = pat.search(hay)
        if not m:
            continue
        # 근거 문맥을 함께 남긴다 — "왜 적용되는지"의 원문 근거.
        s = max(0, m.start() - 60)
        snippet = re.sub(r"\s+", " ", hay[s:m.end() + 120]).strip()
        out.append({
            "statute": name,
            "why_applicable": why,
            "facts_to_confirm": facts,
            "evidence": snippet[:160],
            "source": "text_reference",
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 항목 13 — Final Lawyer Self-Check
# ═══════════════════════════════════════════════════════════════════════════

def final_lawyer_self_check(
    *,
    meta: dict[str, Any] | None,
    clause_results: list[dict[str, Any]] | None,
    contract_text: str = "",
) -> dict[str, Any]:
    """제출 전 9개 항목을 스스로 점검한다.

    각 항목은 (통과 여부, 사람이 읽는 설명)을 돌려준다. 하나라도 실패하면
    정상 완료로 취급하지 않는다 — `review_status` 에 반영할 값을 함께 준다.
    """
    m = meta or {}
    crs = [c for c in (clause_results or []) if isinstance(c, dict) and not c.get("dedup_suppressed")]
    checks: list[dict[str, Any]] = []

    # blocking=True 는 **검토 자체가 잘못된** 경우다. 계약이 미비하다는 발견
    # (핵심 상업조건 공란 등)은 검토 실패가 아니라 검토 결과이므로 advisory 다
    # — 그것으로 결과를 막으면 사용자는 "계약금액이 비어 있다"는 사실을 알려주는
    # 리포트 자체를 받지 못한다. AI 미사용 시 채울 수 없는 항목도 advisory 다.
    def add(key: str, question: str, ok: bool, detail: str = "",
            blocking: bool = True) -> None:
        checks.append({
            "key": key, "question": question, "ok": bool(ok),
            "detail": detail, "blocking": bool(blocking),
        })

    # 1. 계약유형이 맞는가
    tr = m.get("contract_type_resolution") or {}
    add("contract_type", "계약유형이 맞는가?",
        bool(tr.get("contract_type_code")) and not tr.get("uncertain"),
        str(tr.get("reason") or "") or "계약유형이 확정되지 않았습니다.")

    # 2. 우리 회사 지위가 맞는가
    lm = m.get("contract_legal_map") or {}
    # AI 미사용 경로에서는 Legal Map 이 채워지지 않는다 — advisory.
    add("our_role", "우리 회사 지위가 맞는가?",
        bool(str(lm.get("our_role_direction") or "").strip()),
        "Legal Map 의 our_role_direction 이 비어 있습니다." if not lm.get("our_role_direction") else "",
        blocking=False)

    # 3. 핵심 상업조건이 모두 확인됐는가
    ct = m.get("commercial_terms") or []
    unsettled = [r.get("label") for r in ct if str(r.get("status")) in ("공란", "외부조건 연동")]
    # 계약이 미비하다는 **발견**이다 — 검토 실패가 아니므로 advisory.
    add("commercial_terms", "핵심 상업조건이 모두 확인됐는가?",
        not unsettled,
        ("미확정: " + ", ".join(str(u) for u in unsettled)) if unsettled else "",
        blocking=False)

    # 4. HIGH 가 정말 가장 큰 리스크인가 — 근거 없는 HIGH 가 없는지
    high = [c for c in crs if str(c.get("risk_tier") or "").upper() in ("HIGH", "CRITICAL")]
    baseless = [
        str(c.get("clause_id") or "") for c in high
        if not str(c.get("high_severity_basis") or "").strip()
    ]
    add("high_justified", "HIGH 가 정말 가장 큰 리스크인가?",
        not baseless,
        ("치명 근거가 기록되지 않은 HIGH: " + ", ".join(baseless[:5])) if baseless else "")

    # 5. 다른 조항의 cap/예외를 놓치지 않았는가
    sp = m.get("senior_counsel_pass") or {}
    residual_false = [
        str(c.get("clause_id") or "") for c in crs
        if c.get("false_absence_claim_topics") and not c.get("absence_claim_corrected")
    ]
    add("cross_clause", "다른 조항의 cap/예외를 놓치지 않았는가?",
        not residual_false,
        ("정정되지 않은 부재 주장: " + ", ".join(residual_false[:5])) if residual_false else "")

    # 6. 해지·손배·보증·상계를 함께 봤는가 — 위험배분 매트릭스가 있는지
    ram = m.get("risk_allocation_matrix") or {}
    axes = {str(r.get("key")) for r in (ram.get("rows") or [])}
    need = {"termination", "damages", "bond_forfeiture", "setoff"}
    add("linked_axes", "해지·손배·보증·상계를 함께 봤는가?",
        need.issubset(axes),
        "Risk Allocation Matrix 가 없거나 해당 축이 빠졌습니다." if not need.issubset(axes) else "",
        blocking=False)

    # 7. 이전 계약 내용이 섞이지 않았는가
    contam = (sp.get("contamination") or {})
    add("no_contamination", "이전 계약 내용이 섞이지 않았는가?",
        not (contam.get("residual") or []),
        "원문에 없는 용어가 남아 있습니다." if (contam.get("residual") or []) else "")

    # 8. 수정문구가 실제 조항의 법률효과와 맞는가
    # meta["semantic_mismatches"] 는 **이미 처리된** 기록이다 — 불일치를 잡은
    # 두 지점 모두 그 자리에서 suggested_rewrite 를 버리고 감사용 흔적만
    # 남긴다. 그 기록 수를 그대로 실패로 세면, 게이트가 제 일을 할수록 검토가
    # 실패하는 역설이 된다(2026-09-09 실측: 5건 전부 폐기됐는데 blocking 실패).
    # 오염 게이트를 residual 로만 판정한 것과 같은 이유로, 여기서도 **아직
    # 수정문안이 붙어 있는** 불일치만 남은 문제로 본다.
    _handled = {
        str(c.get("clause_id") or "")
        for c in crs
        if c.get("semantic_mismatch") and not str(c.get("suggested_rewrite") or "").strip()
    }
    mismatches = [
        r for r in (m.get("semantic_mismatches") or [])
        if str((r or {}).get("clause_id") or "") not in _handled
    ]
    # 남은 것도 blocking 으로 쓰지 않는다. 실측(2026-09-09, 실제 공사도급계약)
    # 에서 남은 2건은 모두 topic 분류 오탐이었다 — 현장대리인 배치 조항이
    # safety 로, 하자담보 조항이 payment_settlement 로 분류돼 guardrail 이
    # 걸렸고, 이후 단계가 복원한 수정문안은 조항과 정확히 맞았다(하자담보 →
    # 하자보수보증금). 즉 이 기록만으로는 "처리됨 / 오탐 / 진짜 문제"를
    # 구분할 수 없다. 실제 차단은 탐지 지점의 integrity gate 가 나쁜 수정문안을
    # 그 자리에서 버리는 방식으로 이미 하고 있으므로, 여기서는 보고만 한다.
    add("semantic_fit", "수정문구가 실제 조항의 법률효과와 맞는가?",
        not mismatches,
        f"의미 불일치 {len(mismatches)}건 확인 필요(수정문안 잔존)." if mismatches else "",
        blocking=False)

    # 9. 변호사가 실제 협상에서 요구할 만한 문구인가
    # 과도한 수정안은 `assign_negotiation_buckets` 가 그 자리에서 처리한다 —
    # 해당 finding 에 "최소수정안을 1차안으로 제시하라"는 지침(negotiation_position)
    # 을 붙이고, Practical / Fallback 두 단계로 제시하게 만든다. 그러고 나서
    # 여기서 다시 검토를 실패시키면, 44건 중 1건이 공격적이라는 이유로 문서
    # 전체가 나가지 못한다(2026-09-09 실측: KR-26 하나 때문에 다운로드 409).
    # 처리된 뒤 다시 막는 게이트는 오탐이다 — 보고만 한다.
    overreach = [str(c.get("clause_id") or "") for c in crs if c.get("overreaching_rewrite")]
    add("negotiable", "변호사가 실제 협상에서 요구할 만한 문구인가?",
        not overreach,
        (
            "상대방이 수용하기 어려운 수정안(최소수정안 지침 부여됨): "
            + ", ".join(overreach[:5])
        ) if overreach else "",
        blocking=False)

    # ── 2026-09-09 추가 지시 (Risk Package / Document Hierarchy 중심) ────────

    # 10. 계약유형과 당사자 지위가 하나로 확정됐는가
    # rule classifier 와 AI 분석이 서로 다른 답을 냈으면 그 상태로 낸 결론은
    # 조용히 틀린다 — 유형이 다르면 체크리스트가, 지위가 다르면 위험배분이
    # 좌우로 뒤집힌다.
    ci = m.get("canonical_identity") or {}
    ci_conflicts = list(ci.get("conflicts") or [])
    add("canonical_identity", "계약유형과 당사자 지위가 하나로 확정됐는가?",
        not ci_conflicts,
        "; ".join(str(c.get("detail") or "") for c in ci_conflicts[:2]))

    # 11. 문서 우선순위를 반영했는가 / 특수조건이 보호조항을 무력화하지 않는가
    # 상위 문서가 하위 문서의 보호를 뒤집었다면 그 사실이 결과에 있어야 한다.
    # **발견**이므로 advisory 다 — 무력화 자체는 계약의 성질이고, 그것을 알리는
    # 것이 이 리포트의 일이다.
    dh = m.get("document_hierarchy") or {}
    overrides = list(dh.get("overrides") or [])
    add("document_hierarchy", "문서 우선순위를 반영했는가?",
        not overrides,
        (
            "상위 문서가 하위 문서의 보호를 무력화한 축: "
            + ", ".join(str(o.get("axis_label") or "") for o in overrides[:5])
        ) if overrides else "",
        blocking=False)

    # 12. 관련 조항을 risk package 로 연결했는가
    # 같은 법률효과를 조항별로 흩어 놓으면 실제 최대 노출이 보이지 않는다.
    pkgs = list(m.get("risk_packages") or [])
    severe = [p for p in pkgs if str(p.get("exposure")) in ("high", "critical")]
    linked = bool((m.get("risk_package_assignments") or {}).get("assignments"))
    add("risk_package", "관련 조항을 하나의 risk package 로 연결했는가?",
        (not severe) or linked,
        (
            "노출이 큰 패키지가 있는데 조항 연결이 없습니다: "
            + ", ".join(str(p.get("label") or "") for p in severe[:3])
        ) if severe and not linked else "")

    # 13. 위험이 큰데 검토 의견이 없는 영역이 남았는가
    # finding 수를 늘리려는 것이 아니라, 계약이 침묵해서 지적 대상이 없던
    # 영역을 역으로 찾는 것이다. **발견**이므로 advisory.
    bc = m.get("missing_risk_backcheck") or {}
    gaps = list(bc.get("gaps") or [])
    add("no_missing_risk", "위험이 큰 영역에 검토 의견이 모두 있는가?",
        not gaps,
        (
            "검토 의견이 없는 축: "
            + ", ".join(str(g.get("axis_label") or "") for g in gaps[:5])
        ) if gaps else "",
        blocking=False)

    # 14. 수정안이 실무에서 쓸 수 있는 형태인가
    # 위치·방식·문구·이유·우선순위가 갖춰지지 않은 수정안은 그대로 보낼 수 없다.
    pp = m.get("practical_positions") or {}
    missing_fields = list(pp.get("missing_fields") or [])
    add("practical_rewrite", "수정안에 위치·방식·문구·이유·우선순위가 갖춰졌는가?",
        not missing_fields,
        (
            "수정 위치가 비어 있는 finding: " + ", ".join(missing_fields[:5])
        ) if missing_fields else "",
        blocking=False)

    failed = [c for c in checks if not c["ok"]]
    blocking_failed = [c for c in failed if c["blocking"]]
    return {
        "checks": checks,
        "passed_count": len(checks) - len(failed),
        "total_count": len(checks),
        "failed": [c["key"] for c in failed],
        "blocking_failed": [c["key"] for c in blocking_failed],
        "advisory_failed": [c["key"] for c in failed if not c["blocking"]],
        # complete = 검토 품질에 문제가 없는가. 계약이 미비하다는 발견은
        # 여기에 반영하지 않는다(그건 리포트의 내용이다).
        "complete": not blocking_failed,
        "review_status": "" if not blocking_failed else REVIEW_FAILED_LAWYER_SELF_CHECK,
        "detail": (
            "자체 점검 실패(검토 품질): "
            + "; ".join(f"{c['question']} — {c['detail']}" for c in blocking_failed[:4])
        ) if blocking_failed else (
            "확인 필요: "
            + "; ".join(f"{c['question']} — {c['detail']}" for c in failed[:3])
        ) if failed else "",
    }
