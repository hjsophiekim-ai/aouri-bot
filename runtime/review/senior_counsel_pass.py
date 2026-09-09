"""시니어 사내변호사 정리 패스 (2026-09-08 지시, NDA 검토 마무리 보정).

핵심 리스크를 "찾는" 단계가 끝난 뒤에 돌아, **협상할 조항만 남기는** 정리를
수행한다. 계약유형과 무관하게 적용된다.

  항목 2  `merge_duplicate_findings()`  — 같은 조문 + 같은 주제 + 같은
          legal effect 의 finding 을 하나로 병합. 병합 후에도 남아 있으면
          `check_no_duplicate_findings()` 가 잡아 REVIEW_FAILED 로 만든다.
          (예: 제12조 후속계약 우선순위가 두 번 나오던 케이스)

  항목 3  `apply_high_severity_policy()` — HIGH 는 **치명적 근거가 증명된**
          finding 에만 허용한다. 근거 없는 HIGH 는 MEDIUM 으로 강등하고,
          가처분 문구·통상적 무보증 조항은 원칙적으로 MEDIUM/LOW 로 내린다.
          "수정이 필요하다"는 사실만으로는 HIGH 가 되지 못한다.

  항목 5  `sanitize_liability_revisions()` — 수정안이 일반 과실 책임까지
          면제하는 과도한 문구("고의·중과실이 없는 경우 책임 없음")를 쓰지
          못하게 한다. 상호 NDA 에서는 직접·통상손해 중심의 합리적 제한으로
          바꾼다. 우리가 정보 제공자이면서 상대방 면책을 넓히는 문구는
          당사에 불리하므로 그대로 내보내면 안 된다.

세 함수 모두 멱등이다 — 파이프라인이 두 번 호출해도 결과가 같다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.legal_effect_taxonomy import infer_legal_effects

REVIEW_FAILED_DUPLICATE_FINDINGS = "REVIEW_FAILED_DUPLICATE_FINDINGS"

_SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "": 0}


# ═══════════════════════════════════════════════════════════════════════════
# 공통 헬퍼
# ═══════════════════════════════════════════════════════════════════════════

def _tier(cr: dict[str, Any]) -> str:
    t = str(cr.get("risk_tier") or cr.get("severity") or "").strip().upper()
    return t if t in _SEVERITY_RANK else ""


def _set_tier(cr: dict[str, Any], tier: str) -> None:
    cr["risk_tier"] = tier
    if str(cr.get("severity") or "").strip().upper() in _SEVERITY_RANK:
        cr["severity"] = tier


def _live(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        cr for cr in (clause_results or [])
        if isinstance(cr, dict) and not bool(cr.get("dedup_suppressed"))
    ]


def _text_blob(cr: dict[str, Any], *, include_rewrite: bool = True) -> str:
    keys = ["clause_title", "issue_title", "rewrite_reason", "legal_business_reason",
            "original_text", "clause_text"]
    if include_rewrite:
        keys += ["suggested_rewrite", "proposed_revision", "recommendation_text"]
    parts = [str(cr.get(k) or "") for k in keys]
    return "\n".join(p for p in parts if p.strip())


def _article_key(cr: dict[str, Any]) -> str:
    """조문 단위 키. 제12조 제2항과 제12조는 같은 조문으로 본다."""
    an = str(cr.get("article_number") or "").strip()
    if an:
        m = re.match(r"\s*(\d+)", an)
        if m:
            return f"art:{int(m.group(1))}"
        return f"art:{an}"
    dp = str(cr.get("display_path") or "")
    m = re.search(r"제\s*(\d+)\s*조", dp)
    if m:
        return f"art:{int(m.group(1))}"
    return "clause:" + str(cr.get("clause_id") or "")


# ═══════════════════════════════════════════════════════════════════════════
# 항목 2 — 중복 finding 자동 통합
# ═══════════════════════════════════════════════════════════════════════════

#: legal effect 태그가 아예 없을 때 쓰는, 조문 성격 기반 보조 시그니처.
#: 태그가 비면 모든 finding 의 키가 같아져 서로 다른 이슈까지 병합되는
#: 사고가 나므로, 여기서 최소한 주제는 갈라 준다.
_TOPIC_SIGNATURES: list[tuple[str, re.Pattern[str]]] = [
    ("priority_of_agreements", re.compile(r"후속\s*계약|우선(?:순위|하여\s*적용)|본\s*계약과\s*상충|간\s*우선")),
    ("confidential_scope", re.compile(r"비밀정보의?\s*(?:정의|범위)|파생정보|derivative")),
    ("background_ip", re.compile(r"background\s*ip|기존\s*보유|계약\s*전\s*보유|독자\s*개발")),
    ("foreground_ip", re.compile(r"공동\s*개발|추가\s*개발|개발\s*결과물|foreground")),
    ("ai_training", re.compile(r"범용\s*(?:ai|모델)|모델\s*학습|학습\s*데이터|타\s*프로젝트|다른\s*고객")),
    ("personal_data", re.compile(r"개인정보|민감정보|가명정보|음성정보|수면정보|건강\s*관련")),
    ("recipient_scope", re.compile(r"수령자\s*범위|협력업체|재위탁|제3자\s*제공|임직원")),
    ("term_survival", re.compile(r"비밀유지기간|존속|survival|유효기간")),
    ("return_destruction", re.compile(r"반환|폐기|백업")),
    ("damages_injunction", re.compile(r"손해배상|가처분|보전처분|위약")),
    ("governing_law", re.compile(r"관할|준거법|중재")),
]


#: 주제를 특정할 수 없을 때의 값. 호출자는 이 값을 "의견 없음"으로 다뤄야
#: 하며, 주제 불일치 판정의 근거로 쓰면 안 된다.
TOPIC_UNKNOWN = "unknown"

#: 주제 → 호환 그룹. **같은 그룹의 주제는 서로의 답이 될 수 있다.**
#:
#: 항목 1이 금지한 것은 "AI 학습 질문에 개인정보·외부협력업체 이슈를 섞는"
#: 것이지, 인접 쟁점끼리의 연결까지 끊으라는 것이 아니다. 예컨대 "우리
#: 독자개발 기술이 상대방에게 귀속되는가"(background_ip) 라는 질문에 대해
#: "개량 지식재산권이 제공자에게 귀속된다"(foreground_ip) 는 finding 은
#: 정확한 답이다 — 둘을 다른 주제로 보고 끊으면 답이 "적정"으로 뒤집힌다.
#: 그래서 엄격한 동일성 대신 그룹 단위로 판정한다.
_TOPIC_GROUPS: dict[str, str] = {
    # 지식재산 귀속 — 계약 전 보유분과 개발 결과물은 같은 협상 축이다.
    "background_ip": "ip_allocation",
    "foreground_ip": "ip_allocation",
    # 데이터 이용 목적 제한. 개인정보와는 **의도적으로 분리**한다.
    "ai_training": "data_use_restriction",
    # 개인정보·민감정보 처리 — 별도 법령(개인정보보호법) 축.
    "personal_data": "personal_data",
    # 정보를 받을 수 있는 자의 범위(임직원·협력업체·재위탁).
    "recipient_scope": "recipient_scope",
    # 비밀정보 자체의 정의·범위.
    "confidential_scope": "confidential_scope",
    "term_survival": "term_survival",
    "return_destruction": "return_destruction",
    "damages_injunction": "remedies",
    "priority_of_agreements": "contract_hierarchy",
    "governing_law": "dispute_forum",
}


def topics_compatible(a: str, b: str) -> bool:
    """두 주제가 서로의 답이 될 수 있는지.

    한쪽이라도 주제를 특정할 수 없으면(TOPIC_UNKNOWN) True — 과잉 차단으로
    답변이 비는 것이 잘못된 연결보다 나쁘다. 그룹이 등록되지 않은 주제도
    보수적으로 True 로 둔다.
    """
    if not a or not b or a == TOPIC_UNKNOWN or b == TOPIC_UNKNOWN:
        return True
    if a == b:
        return True
    ga, gb = _TOPIC_GROUPS.get(a), _TOPIC_GROUPS.get(b)
    if ga is None or gb is None:
        return True
    return ga == gb


def classify_topic(text: str) -> str:
    """자유 텍스트를 계약 쟁점 주제 하나로 분류한다.

    finding 병합(항목 2)과 사용자 요청↔finding 연결(항목 1)이 **같은 주제
    어휘**를 쓰도록 공개한다. 어느 패턴에도 걸리지 않으면 TOPIC_UNKNOWN —
    억지로 분류해서 서로 다른 쟁점을 묶는 것보다 "모른다"가 안전하다.
    """
    hay = text or ""
    for name, pat in _TOPIC_SIGNATURES:
        if pat.search(hay):
            return name
    return TOPIC_UNKNOWN


def _claim_blob(cr: dict[str, Any]) -> str:
    """finding 이 **스스로 주장하는 내용**만 모은다.

    주제 분류에 원문 조항 텍스트(`original_text`/`clause_text`)를 넣으면
    안 된다 — 원문은 온갖 키워드를 포함하므로, 예컨대 Background IP 침해를
    지적한 제8조 제3항 finding 이 원문에 섞인 "우선" 표현 때문에
    `priority_of_agreements` 로 오분류되고, 그 결과 사용자의 독자개발 질문에
    대한 답이 "적정" 으로 뒤집혔다(2026-09-08).
    """
    parts = [
        str(cr.get("issue_title") or ""),
        str(cr.get("clause_title") or ""),
        str(cr.get("rewrite_reason") or ""),
        str(cr.get("legal_business_reason") or ""),
    ]
    return "\n".join(p for p in parts if p.strip())


def _topic_signature(cr: dict[str, Any]) -> str:
    topic = classify_topic(_claim_blob(cr))
    if topic != TOPIC_UNKNOWN:
        return topic
    it = str(cr.get("issue_title") or "").strip()
    return "title:" + re.sub(r"\s+", "", it)[:24] if it else TOPIC_UNKNOWN


def finding_topic(cr: dict[str, Any]) -> str:
    """finding 이 실제로 다루는 주제. 특정 못하면 TOPIC_UNKNOWN."""
    return classify_topic(_claim_blob(cr))


def _effect_signature(cr: dict[str, Any]) -> str:
    """이 finding 이 다루는 법적 효과의 정규 시그니처."""
    tags: list[str] = []
    for key in ("legal_effect_tags", "original_effect_tags", "rewrite_effect_tags"):
        v = cr.get(key)
        if isinstance(v, list):
            tags.extend(str(x) for x in v if str(x).strip())
    if not tags:
        # 원문 조항 텍스트로 추론하면 안 된다 — 같은 조문의 서로 다른
        # finding 은 원문을 공유하므로 효과 시그니처가 같아지고, 전혀 다른
        # 두 이슈가 하나로 병합된다. finding 자신의 주장만 본다.
        tags = infer_legal_effects(_claim_blob(cr))
    if tags:
        return "eff:" + ",".join(sorted(set(tags)))
    return "topic:" + _topic_signature(cr)


def _mergeable(cr: dict[str, Any]) -> bool:
    """이 finding 을 병합해도 되는지.

    - `article_review_anchor`: 조문 전체 리뷰 anchor 는 개별 finding 과 층위가
      다르다.
    - `is_mandatory_review_target`: 사용자가 review_focus 에서 **직접 인용한**
      조항(예: "제6조 제5항")의 finding. 클라이언트가 콕 집어 물은 조항을
      상위 조문 finding 으로 접어버리면 그 인용이 최종 출력에서 사라져
      REVIEW_FAILED_USER_REQUEST_MISSING 이 된다(2026-09-08 확인). 시니어
      변호사도 의뢰인이 지목한 조항은 별도 항목으로 남긴다.
    """
    if bool(cr.get("article_review_anchor")):
        return False
    if bool(cr.get("is_mandatory_review_target")):
        return False
    return True


def _merge_key(cr: dict[str, Any]) -> tuple[str, str, str]:
    """병합 키 = (조문, 주제, 법적효과).

    주제를 빼면 안 된다. NDA 조항은 `infer_legal_effects()` 가 대부분
    `confidentiality` 하나로만 추론하므로, (조문+효과) 만으로는 같은 조문의
    전혀 다른 쟁점 — 제4조의 "범용 AI 모델 학습 제한 부재"와 "개인정보 처리
    경계 미설정", 제8조의 background/foreground IP — 이 하나로 뭉개진다
    (2026-09-08 확인). 주제 동일성이 병합의 실제 기준이고, 효과는 보조다.

    주의: 여기서 요구하는 것은 주제의 **동일성**이고, `topics_compatible()`
    이 판정하는 것은 주제의 **호환성**이다. background_ip 와 foreground_ip 는
    서로의 답이 될 수는 있어도(항목 1) 별개의 협상 항목이므로 병합하지 않는다.
    """
    return (_article_key(cr), _topic_signature(cr), _effect_signature(cr))


def _merge_score(cr: dict[str, Any]) -> tuple[int, int, int]:
    """병합 시 primary 로 남길 우선순위 — 심각도 > 수정안 충실도 > 근거 길이."""
    rewrite = str(cr.get("suggested_rewrite") or cr.get("proposed_revision") or "")
    reason = str(cr.get("rewrite_reason") or cr.get("legal_business_reason") or "")
    return (_SEVERITY_RANK.get(_tier(cr), 0), len(rewrite.strip()), len(reason.strip()))


def merge_duplicate_findings(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 조문·같은 legal effect 의 finding 을 하나로 병합한다.

    병합된 항목은 `dedup_suppressed=True` + `merged_into` 로 표시만 하고
    삭제하지 않는다(추적성 유지). primary 에는 `merged_from` 과 합집합
    `legal_effect_tags` 를 남긴다.

    반환값은 이번 호출에서 새로 병합한 항목들의 요약 리스트다.
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for cr in _live(clause_results):
        if _tier(cr) not in ("CRITICAL", "HIGH", "MEDIUM"):
            continue
        if not _mergeable(cr):
            continue
        groups.setdefault(_merge_key(cr), []).append(cr)

    merged: list[dict[str, Any]] = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=_merge_score, reverse=True)
        primary, dups = members[0], members[1:]
        tags: set[str] = set()
        for m in members:
            v = m.get("legal_effect_tags")
            if isinstance(v, list):
                tags.update(str(x) for x in v if str(x).strip())
        if tags:
            primary["legal_effect_tags"] = sorted(tags)
        from_ids = [str(d.get("clause_id") or "") for d in dups]
        primary["merged_from"] = sorted(set(list(primary.get("merged_from") or []) + from_ids))
        key_str = "|".join(key)
        primary["merge_key"] = key_str
        for d in dups:
            d["dedup_suppressed"] = True
            d["merge_key"] = key_str
            d["merged_into"] = str(primary.get("clause_id") or "")
            d["dedup_reason"] = "senior_counsel_duplicate_merge"
            merged.append({
                "merged_into": d["merged_into"],
                "merged_clause_id": str(d.get("clause_id") or ""),
                "merge_key": d["merge_key"],
                "display_path": str(d.get("display_path") or ""),
                "issue_title": str(d.get("issue_title") or ""),
            })
    return merged


def check_no_duplicate_findings(clause_results: list[dict[str, Any]]) -> list[str]:
    """병합 후에도 남은 중복(같은 조문+같은 효과) merge_key 목록.

    비어 있지 않으면 호출자는 REVIEW_FAILED_DUPLICATE_FINDINGS 로 처리해야
    한다 — 동일 이슈가 두 번 보고되는 것은 정상 완료가 아니다(항목 2).
    """
    seen: dict[tuple[str, str, str], int] = {}
    for cr in _live(clause_results):
        if _tier(cr) not in ("CRITICAL", "HIGH", "MEDIUM"):
            continue
        if not _mergeable(cr):
            continue
        key = _merge_key(cr)
        seen[key] = seen.get(key, 0) + 1
    return ["|".join(k) for k, n in sorted(seen.items()) if n > 1]


# ═══════════════════════════════════════════════════════════════════════════
# 항목 3 — HIGH 기준 강화
# ═══════════════════════════════════════════════════════════════════════════

#: HIGH 를 정당화하는 치명적 근거. 사용자가 든 NDA/IP 4종을 포함하되,
#: 계약유형과 무관하게 "회사가 통제권·금전을 실제로 잃는" 효과를 모은다.
_CATASTROPHIC_EFFECT_TAGS: frozenset[str] = frozenset({
    "uncapped_liability",
    "third_party_debt_guarantee",
    "counterparty_broad_self_liability_shield",
    "ip_ownership_transfer",
    "data_processing_restriction",
    "minimum_purchase_commitment",
    "penalty_for_bypass",
    "third_party_liability",
    "indemnity",
    "unilateral_amendment",
})

#: 사용자가 명시한 NDA/IP 치명 카테고리 + 기존 계약유형의 구조 불일치류.
_CATASTROPHIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 독자개발권 침해
    ("independent_development_infringement",
     re.compile(r"독자\s*개발.*(?:비밀정보|권리|귀속|제한|침해)|독자적으로\s*개발.*상대방")),
    # Background IP 침해
    ("background_ip_infringement",
     re.compile(r"(?:background\s*ip|기존\s*보유|계약\s*전\s*보유).*(?:귀속|이전|침해|상대방\s*권리)")),
    # 범용 AI 학습 · 타 프로젝트 활용
    ("general_ai_training_or_other_project_use",
     re.compile(r"(?:범용\s*(?:ai|모델)|모델\s*학습|학습\s*데이터).*(?:제한\s*없|동의\s*없|무제한)"
                r"|(?:타|다른)\s*(?:프로젝트|고객).*(?:활용|이용|개선)")),
    # 실제 개인정보 처리
    ("actual_personal_data_processing",
     re.compile(r"(?:개인정보|민감정보|가명정보|음성정보|수면정보|건강\s*관련\s*정보)"
                r".*(?:처리|수집|이전|위탁|국외)")),
    # 계약 당사자·세금·수금 구조 불일치 (대리점/렌탈 계약군의 기존 HIGH 근거)
    ("party_structure_mismatch",
     re.compile(r"세금계산서.*(?:대리점|주체\s*불명)|대리점.*계약\s*당사자|수금.*책임.*대리점")),
    # 포괄 책임 / 전부 배상
    ("overbroad_liability",
     re.compile(r"모든\s*책임|일체의?\s*책임|어떠한\s*경우에도.*(?:전부|전액)\s*배상|무제한\s*배상")),
    # 일방적 공급중단 / 보복
    ("unilateral_supply_or_retaliation",
     re.compile(r"공급을?\s*중단|물량을?\s*현저히\s*축소|불이익.*(?:신고|분쟁조정|단체)")),
    # ── 2026-09-09 지시 항목 7 의 HIGH 기준 보완 ──────────────────────────
    # "계약 체결 여부에 영향을 줄 수준"만 HIGH 다. 아래는 그 기준을 문형으로
    # 옮긴 것 — 단순히 문구를 개선할 수 있다는 것만으로는 HIGH 가 되지 않는다.
    ("large_monetary_exposure",
     re.compile(r"계약금액(?:의)?\s*(?:[3-9]\d|100)\s*%"          # 계약금액의 30% 이상
                r"|계약금액\s*(?:전액|전부)"
                r"|(?:배상|위약|지체상금)[^.\n]{0,30}?계약금액[^.\n]{0,10}?(?:초과|상당)")),
    ("unilateral_termination_right",
     re.compile(r"(?:필요하다고\s*인정|자신의\s*판단|재량)[^.\n]{0,30}?"
                r"(?:언제든지|수시로)?[^.\n]{0,20}?해(?:지|제)"
                r"|언제든지[^.\n]{0,20}?해(?:지|제)할\s*수\s*있"
                r"|일방적으로[^.\n]{0,20}?해(?:지|제)")),
    ("bond_forfeiture_plus_damages",
     re.compile(r"보증금[^.\n]{0,40}?(?:귀속|몰취|몰수)[^.\n]{0,60}?"
                r"(?:손해배상|별도로\s*청구|추가로\s*배상)"
                r"|(?:손해배상|별도\s*청구)[^.\n]{0,60}?보증금[^.\n]{0,20}?(?:귀속|몰취)")),
    ("safety_liability_fully_shifted",
     re.compile(r"(?:산업\s*안전|산재|중대\s*재해|안전\s*사고)[^.\n]{0,60}?"
                r"(?:일체의?\s*책임|모든\s*책임|전적으로|전부)"
                r"|(?:인적|물적)[^.\n]{0,20}?사고[^.\n]{0,40}?일체의?\s*책임")),
    ("core_ip_loss",
     re.compile(r"(?:설계도서|시공상세도|기술자료|소스코드|산출물|발명|노하우)"
                r"[^.\n]{0,60}?(?:일체의?\s*)?(?:지식재산권|권리)[^.\n]{0,30}?"
                r"(?:귀속|이전|양도)")),
    ("insolvency_exposure",
     re.compile(r"지급\s*불능|파산|회생\s*절차|부도[^.\n]{0,30}?(?:해지|정산)"
                r"|선급금[^.\n]{0,40}?(?:반환|정산)[^.\n]{0,30}?보증")),
]

#: 원칙적으로 HIGH 가 아닌 것들 — 통상적인 계약 문언이다(항목 3).
_ROUTINE_DEMOTE_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("injunction_boilerplate",
     re.compile(r"가처분|보전처분|injunctive\s*relief"), "MEDIUM"),
    ("routine_no_warranty",
     re.compile(r"무보증|보증하지\s*않|as\s*is|현\s*상태로\s*제공|warrant(?:y|ies)\s*of\s*any\s*kind"),
     "MEDIUM"),
]


def _catastrophic_basis(cr: dict[str, Any]) -> str:
    """이 finding 이 HIGH 를 유지할 치명적 근거. 없으면 빈 문자열."""
    tags: set[str] = set()
    for key in ("legal_effect_tags", "original_effect_tags"):
        v = cr.get(key)
        if isinstance(v, list):
            tags.update(str(x) for x in v)
    hit = tags & _CATASTROPHIC_EFFECT_TAGS
    if hit:
        return "effect:" + ",".join(sorted(hit))

    blob = _claim_blob(cr)
    for name, pat in _CATASTROPHIC_PATTERNS:
        if pat.search(blob):
            return f"pattern:{name}"

    # 계약 핵심조건 미확정은 지시 항목 7이 HIGH 사유로 명시한 항목이다
    # ("계약 핵심조건 미확정"). 금액·기간이 공란이면 그 금액에 연동된
    # 지체상금·보증금·손해배상 상한의 실제 노출 규모를 산정할 수 없어,
    # 문구 개선 수준이 아니라 체결 여부에 영향을 준다(2026-09-09).
    if cr.get("commercial_term_key") or bool(cr.get("is_commercial_terms_finding")):
        return "declared:essential_commercial_term_unsettled"

    # 기존 룰/재분류기가 이미 치명 근거를 명시해 둔 경우는 존중한다.
    for key in ("severity_upgrade_reasons", "high_severity_basis", "structure_conflict"):
        v = cr.get(key)
        if isinstance(v, list) and v:
            return f"declared:{key}"
        if isinstance(v, str) and v.strip():
            return f"declared:{key}"
    if bool(cr.get("approval_required")):
        return "declared:approval_required"
    return ""


def _routine_demotion(cr: dict[str, Any]) -> tuple[str, str] | None:
    """가처분·통상 무보증처럼 원칙적으로 HIGH 가 아닌 문구인지."""
    blob = _claim_blob(cr)
    for name, pat, target in _ROUTINE_DEMOTE_PATTERNS:
        if not pat.search(blob):
            continue
        # 같은 조항에 별도의 치명적 근거가 있으면 강등하지 않는다.
        basis = _catastrophic_basis(cr)
        if basis and not basis.startswith("declared:"):
            return None
        return name, target
    return None


def apply_high_severity_policy(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """HIGH 를 치명적 근거가 있는 finding 으로만 제한한다(항목 3).

    - 치명 근거가 있으면 HIGH 유지 + `high_severity_basis` 기록
    - 가처분/통상 무보증 문구는 MEDIUM 으로 강등
    - 근거 없는 HIGH 는 MEDIUM 으로 강등 (단순 "수정 필요"는 HIGH 불가)

    반환값은 이번 호출에서 강등한 항목들의 요약 리스트다.
    """
    demoted: list[dict[str, Any]] = []
    for cr in _live(clause_results):
        tier = _tier(cr)
        if tier not in ("CRITICAL", "HIGH"):
            continue

        routine = _routine_demotion(cr)
        if routine is not None:
            name, target = routine
            _set_tier(cr, target)
            cr["severity_demotion_reason"] = f"routine_clause:{name}"
            cr.pop("high_severity_basis", None)
            demoted.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "issue_title": str(cr.get("issue_title") or ""),
                "from": tier, "to": target, "reason": f"routine_clause:{name}",
            })
            continue

        basis = _catastrophic_basis(cr)
        if basis:
            cr["high_severity_basis"] = basis
            continue

        _set_tier(cr, "MEDIUM")
        cr["severity_demotion_reason"] = "no_catastrophic_basis"
        demoted.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or ""),
            "from": tier, "to": "MEDIUM", "reason": "no_catastrophic_basis",
        })
    return demoted


# ═══════════════════════════════════════════════════════════════════════════
# 항목 5 — 손해배상 수정안의 과도한 면책 문구 차단
# ═══════════════════════════════════════════════════════════════════════════

#: 한국어 부정 어미. 한글은 음절 단위 코드포인트라 `아니?하` 로는
#: "아니**한**다"("한" U+D55C ≠ "하" U+D558)를 잡지 못한다 — 어미를
#: 명시적으로 열거해야 한다.
_NEG = r"(?:아니한|아니하|않)"

#: 책임을 부정하는 술부.
_NO_LIABILITY = (
    r"(?:책임[을이도]?\s*(?:지지|부담하지)\s*" + _NEG
    + r"|책임[이을도]?\s*없"
    + r"|책임[을]?\s*면[하한]"
    + r"|면책)"
)

#: 고의·중과실이 **면책의 조건**으로 쓰인 경우 = 일반 과실 책임까지 면제.
#: 상호 NDA 에서 우리가 정보 제공자일 때 특히 불리하므로 내보내면 안 된다.
#: 반대로 고의·중과실이 **제한의 예외**로 쓰인 정상 문구(T3 형태)는
#: 조건절(없는/아닌 경우)이 없으므로 여기 걸리지 않는다.
_OVERBROAD_EXCULPATION = re.compile(
    r"[^.\n]*고의[^.\n]{0,12}(?:중대한\s*과실|중과실)[^.\n]{0,40}?"
    r"(?:없(?:는|을)\s*(?:경우|한|때)|아닌\s*경우|아니한\s*경우|아니면)[^.\n]{0,60}?"
    + _NO_LIABILITY + r"[^.\n]*[.]?",
    re.IGNORECASE,
)

#: 반대 어순 — "어떠한 책임도 지지 아니한다 … 고의·중과실" 형태.
_OVERBROAD_EXCULPATION_ALT = re.compile(
    r"[^.\n]*(?:어떠한|일체의?)\s*책임[도을]?\s*(?:지지|부담하지)\s*" + _NEG
    + r"[^.\n]*(?:고의|중과실)[^.\n]*[.]?",
    re.IGNORECASE,
)

_MUTUAL_NDA_LIMITATION = (
    "각 당사자는 본 계약 위반으로 상대방에게 발생한 직접적·통상의 손해를 배상한다. "
    "특별손해·간접손해·결과적 손해 및 영업이익 상실은, 위반 당사자가 그 사정을 알았거나 "
    "알 수 있었던 경우를 제외하고 배상 범위에서 제외한다. "
    "다만 고의 또는 중대한 과실에 의한 위반, 비밀정보의 제3자 무단 공개·유출, "
    "지식재산권 침해 및 관계 법령상 제한할 수 없는 책임에는 위 제한이 적용되지 않는다."
)

_REVISION_TEXT_KEYS = ("suggested_rewrite", "proposed_revision", "recommendation_text")


def _has_overbroad_exculpation(text: str) -> bool:
    t = text or ""
    return bool(_OVERBROAD_EXCULPATION.search(t) or _OVERBROAD_EXCULPATION_ALT.search(t))


def sanitize_liability_revisions(
    clause_results: list[dict[str, Any]],
    *,
    is_mutual_nda: bool = False,
) -> list[dict[str, Any]]:
    """수정안에서 일반 과실까지 면제하는 과도한 면책 문구를 제거한다(항목 5).

    상호 NDA 에서는 직접·통상손해 중심의 합리적 제한 문구로 대체한다.
    그 밖의 계약유형에서는 문구만 삭제하고 대체 문안을 강요하지 않는다 —
    책임 구조가 계약유형마다 다르므로 잘못된 문안을 심는 것이 더 위험하다.
    """
    fixed: list[dict[str, Any]] = []
    for cr in _live(clause_results):
        changed_keys: list[str] = []
        for key in _REVISION_TEXT_KEYS:
            raw = cr.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            if not _has_overbroad_exculpation(raw):
                continue
            new = _OVERBROAD_EXCULPATION.sub("", raw)
            new = _OVERBROAD_EXCULPATION_ALT.sub("", new)
            new = re.sub(r"[ \t]{2,}", " ", new).strip()
            if is_mutual_nda:
                new = (new + " " + _MUTUAL_NDA_LIMITATION).strip() if new else _MUTUAL_NDA_LIMITATION
            cr[key] = new
            changed_keys.append(key)
        if changed_keys:
            cr["liability_text_sanitized"] = True
            cr["liability_sanitize_reason"] = (
                "일반 과실 책임까지 면제하는 과도한 면책 문구 제거"
                + (" · 상호 NDA 기준 직접·통상손해 제한으로 대체" if is_mutual_nda else "")
            )
            fixed.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "keys": changed_keys,
                "replaced_with_mutual_nda_limitation": bool(is_mutual_nda),
            })
    return fixed


def check_no_overbroad_exculpation(clause_results: list[dict[str, Any]]) -> list[str]:
    """정리 후에도 과도한 면책 문구가 남아 있는 finding 의 display_path 목록."""
    out: list[str] = []
    for cr in _live(clause_results):
        for key in _REVISION_TEXT_KEYS:
            raw = cr.get(key)
            if isinstance(raw, str) and _has_overbroad_exculpation(raw):
                out.append(f"{cr.get('display_path') or cr.get('clause_id') or '?'}::{key}")
                break
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 파이프라인 진입점
# ═══════════════════════════════════════════════════════════════════════════

def run_senior_counsel_pass(
    clause_results: list[dict[str, Any]],
    *,
    contract_type_code: str = "",
    is_mutual_nda: bool = False,
    contract_text: str = "",
) -> dict[str, Any]:
    """시니어 사내변호사 정리를 정해진 순서로 적용하고 감사 리포트를 돌려준다.

    순서가 중요하다:

      1. **오염 제거**가 가장 먼저다. 다른 계약의 문안을 심은 finding 은
         병합·등급 판단의 입력이 되어서는 안 된다(2026-09-09 항목 3).
      2. **교차조항 정정** — "상한이 없다"는 주장이 사실인지 확인해 정정한다.
         등급 판단 **전에** 해야 정정된 등급이 반영된다(항목 5·6).
      3. 병합 — 중복된 항목에 severity 정책을 두 번 적용하지 않는다(항목 2).
      4. severity 정책 — 치명 근거 없는 HIGH 강등(항목 3/7).
      5. 문구 정리 — 강등으로 사라질 항목의 문구를 손대지 않도록 마지막.

    `contract_text` 가 비면 1·2 단계는 건너뛴다 — 원문 없이는 "이 문서에
    있는가"를 판단할 수 없고, 근거 없는 삭제·정정이 더 위험하다.
    """
    contamination: dict[str, Any] = {}
    cross_clause: dict[str, Any] = {}
    if str(contract_text or "").strip():
        from runtime.review.cross_clause_protection import reconcile_absence_claims
        from runtime.review.review_isolation import scrub_contaminated_findings

        contamination = scrub_contaminated_findings(
            clause_results, contract_text=contract_text,
        )
        cross_clause = reconcile_absence_claims(
            clause_results, contract_text=contract_text,
        )

    merged = merge_duplicate_findings(clause_results)
    demoted = apply_high_severity_policy(clause_results)
    sanitized = sanitize_liability_revisions(clause_results, is_mutual_nda=is_mutual_nda)

    residual_duplicates = check_no_duplicate_findings(clause_results)
    residual_exculpation = check_no_overbroad_exculpation(clause_results)

    return {
        "contract_type_code": contract_type_code,
        "is_mutual_nda": bool(is_mutual_nda),
        "contamination": contamination,
        "contamination_removed_count": int(contamination.get("removed_count") or 0),
        "cross_clause_protection": cross_clause,
        "absence_claims_corrected_count": int(cross_clause.get("corrected_count") or 0),
        "merged_findings": merged,
        "merged_count": len(merged),
        "severity_demotions": demoted,
        "demoted_count": len(demoted),
        "liability_text_sanitized": sanitized,
        "sanitized_count": len(sanitized),
        "residual_duplicate_keys": residual_duplicates,
        "residual_overbroad_exculpation": residual_exculpation,
    }
