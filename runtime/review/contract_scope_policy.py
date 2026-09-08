"""Contract Semantic Scope policy — "이 계약이 정해야 할 것"과 "다음 계약으로
남겨야 할 것"을 구분하는 범용 레이어(2026-09-08 지시).

배경(에이슬립–일룸 NDA acceptance failure)
------------------------------------------------
계약유형을 `nda_confidentiality`로 정확히 분류했음에도 최종 finding에
콘텐츠 제작·광고계약용 권고(콘텐츠 저작권 양도, SNS/광고매체 사용권,
음원·효과음, 모델 초상권, 촬영장소, 콘텐츠 검수, 지급조건, 포트폴리오,
광고집행 중단)가 대량 혼입됐다. 원인은 두 가지였다.

  1. `_classify_contract_type_by_substance()`의 content-production 키워드에
     맨 단어 "모델"이 있어, "AI 모델·학습 데이터"를 정의하는 NDA 제2조가
     content_production으로 오분류됐다 → content production 체크리스트가
     통째로 주입됐다.
  2. 주입된 뒤에는 "이 finding이 이 계약유형에서 애초에 나올 수 있는
     주제인가"를 계약유형 차원에서 다시 검증하는 레이어가 없었다.

이 모듈은 (2)를 담당한다. 특정 계약(에이슬립)에 대한 하드코딩이 아니라,
계약유형 → 허용 검토영역(whitelist) / 금지 검토영역(hard block) 표를 두고
그 표에 등록된 유형에서만 게이트를 작동시키는 범용 구조다. 표에 없는
계약유형은 종전과 동일하게 아무 것도 차단하지 않는다.

세 가지 판단을 제공한다.
  * `find_blocked_domain_hits()` — 계약유형상 나올 수 없는 영역의 finding
    (항목 4: Rule Whitelist HARD BLOCK).
  * `find_future_transaction_intrusions()` — 현재 계약이 아니라 "향후 체결할
    계약"에서 정할 사항을 현재 계약에 삽입하려는 finding (항목 1). 다만
    "후속 계약에서 정하도록 유보한다"는 취지의 문언은 NDA가 실제로 해야 할
    검토이므로 차단하지 않는다.
  * `enforce_contract_scope()` — 위 둘을 실제로 clause_results에 적용하고
    차단 내역을 리포트로 돌려준다.
"""
from __future__ import annotations

import re
from typing import Any

# ── 검토영역(review domain) 카탈로그 ────────────────────────────────────────
# NDA에서 원칙적으로 활성화되는 영역(2026-09-08 지시 항목 4). whitelist는
# 강제 필터가 아니라 "무엇을 검토했어야 하는가"의 정본 목록이며, 실제 차단은
# 아래 HARD BLOCK 표가 수행한다 — 자유 텍스트를 allowlist로 분류하는 방식은
# 오분류 시 정당한 finding까지 조용히 삭제하므로 채택하지 않는다.
NDA_ALLOWED_DOMAINS: tuple[str, ...] = (
    "confidential_information_definition",
    "permitted_purpose_use",
    "disclosure_recipient_restriction",
    "confidentiality_exceptions",
    "background_ip_no_implied_license",
    "independent_development",
    "development_result_reservation",
    "ai_data_reuse_restriction",
    "personal_data_boundary",
    "duration_survival",
    "return_destruction",
    "liability_injunctive_relief",
    "assignment",
    "governing_law_dispute",
    "subsequent_agreement_priority",
)

CONTRACT_TYPE_DOMAIN_WHITELIST: dict[str, tuple[str, ...]] = {
    "nda_confidentiality": NDA_ALLOWED_DOMAINS,
}

# ── HARD BLOCK 영역별 탐지 패턴 ─────────────────────────────────────────────
# 각 패턴은 "그 영역 고유의 급부/권리"를 가리키는 문구여야 한다. NDA가
# 정당하게 쓰는 일반어(지식재산권, 귀속, 승인, 통지 등)는 절대 넣지 않는다.
_BLOCKED_DOMAIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "content_production_inspection": re.compile(
        r"콘텐츠[^.\n]{0,10}검수|시안[^.\n]{0,10}(검수|확정|승인)|검수\s*(기준|절차|기간|일정)"
        r"|수정\s*요청\s*횟수|납품\s*검수|산출물\s*검수"
    ),
    "advertising_media_license": re.compile(
        r"광고\s*매체|매체\s*사용권|SNS[^.\n]{0,12}(게재|노출|사용|활용)"
        r"|광고\s*집행|광고\s*게재|온·?오프라인\s*매체|2차\s*저작물\s*이용\s*매체"
    ),
    "portrait_or_location_release": re.compile(
        r"초상권|퍼블리시티권|모델\s*(계약|섭외|출연)|촬영\s*장소|로케이션|출연\s*동의"
    ),
    "music_and_sound_assets": re.compile(
        r"음원|효과음|배경\s*음악|\bBGM\b|폰트\s*라이선스|유상\s*폰트|스톡\s*이미지"
    ),
    "portfolio_usage": re.compile(r"포트폴리오|레퍼런스\s*활용|실적\s*홍보"),
    "copyright_transfer_to_client": re.compile(
        r"저작(?:재산)?권[^.\n]{0,20}(양도|이전)|저작(?:재산)?권[^.\n]{0,10}(?:전부|일체)[^.\n]{0,10}귀속"
        r"|2차적\s*저작물\s*작성권"
    ),
    "payment_terms": re.compile(
        r"(대금|용역비|제작비|개발비|광고비)[^.\n]{0,12}(지급\s*(?:조건|시기|기일|일정)|분할\s*지급|선급금|잔금)"
        r"|지급\s*조건|세금계산서\s*발행|지연\s*이자"
    ),
    "delivery_and_acceptance": re.compile(
        r"납기|납품\s*(?:기한|일정|장소)|인도\s*시기|위험\s*이전|검수\s*합격|검수\s*완료\s*간주|반품"
    ),
    "sla_and_maintenance": re.compile(
        r"\bSLA\b|서비스\s*수준\s*협약|유지보수\s*(?:기간|요율|대가|의무)|가동률|장애\s*대응\s*시간"
    ),
    "performance_warranty": re.compile(
        r"성능\s*보증|품질\s*보증\s*기간|하자\s*보수\s*(?:기간|보증금)|무상\s*A/?S"
    ),
}

# 계약유형별로 원천 차단할 영역. 표에 없는 계약유형은 아무 것도 차단하지 않는다.
CONTRACT_TYPE_HARD_BLOCKED_DOMAINS: dict[str, frozenset[str]] = {
    "nda_confidentiality": frozenset(_BLOCKED_DOMAIN_PATTERNS.keys()),
}

# ── 항목 1: Current Contract vs Future Transaction ──────────────────────────
# "향후 개발계약에서 정할 사항"을 현재 계약(NDA)에 삽입하려는 신호.
_FUTURE_TRANSACTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "development_fee": re.compile(r"개발비|개발\s*대가|용역\s*대금\s*(?:산정|지급)|단가\s*산정"),
    "acceptance_inspection": re.compile(r"검수\s*(?:기준|절차|기간|일정)|인수\s*시험|성능\s*시험\s*합격"),
    "delivery_schedule": re.compile(r"납기|납품\s*일정|개발\s*일정\s*준수|마일스톤\s*지연"),
    "performance_guarantee": re.compile(r"성능\s*보증|정확도\s*[0-9]|성능\s*지표\s*미달"),
    "maintenance": re.compile(r"유지보수\s*(?:기간|요율|대가|범위|의무)"),
    "content_usage_media": re.compile(r"이용\s*매체|사용\s*매체|매체\s*범위"),
    "final_ip_ownership": re.compile(
        r"(?:개발\s*성과물?|공동\s*개발\s*결과물?|프로젝트\s*결과물?)[^.\n]{0,25}"
        r"(?:최종\s*)?(?:귀속은?|소유(?:권)?은?)[^.\n]{0,25}(?:한다|에게\s*있다)"
    ),
}

# "후속 계약에서 정하도록 유보한다"는 취지의 문언 — NDA가 실제로 해야 할
# 검토이므로 위 신호가 있어도 차단하지 않는다(항목 1 후단).
_RESERVATION_LANGUAGE = re.compile(
    r"후속\s*계약|별도\s*계약|별도의\s*계약|별도로\s*체결|추후\s*체결|정식\s*계약"
    r"|본\s*계약에서는?\s*정하지|유보|따로\s*정한다|별도로\s*정한다"
)


def _finding_text(cr: dict[str, Any]) -> str:
    """finding이 실제로 사용자에게 권고하는 내용 전부를 한 문자열로 모은다.

    `original_text`는 계약 원문 인용이므로 제외한다 — 원문에 그 단어가
    있다는 것은 그 영역이 계약에 실제로 존재한다는 뜻이지, 아우리봇이
    엉뚱한 영역을 권고했다는 뜻이 아니다.
    """
    parts: list[str] = []
    for key in (
        "clause_title", "issue_title", "suggested_rewrite", "proposed_revision",
        "recommendation_text", "rewrite_reason", "legal_business_reason",
        "problem", "why_matters", "negotiation_position", "negotiation_strategy",
        "worst_case_scenario",
    ):
        v = cr.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(str(x) for x in v if isinstance(x, str))
    ri = cr.get("redline_instruction")
    if isinstance(ri, dict):
        for key in ("replacement_text", "final_clause_text", "reason", "edit_location"):
            v = ri.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v)
    return "\n".join(parts)


def find_blocked_domain_hits(text: str, contract_type_code: str) -> list[tuple[str, str]]:
    """(domain, 매치된 문구) 목록. 차단 대상이 아니면 빈 목록."""
    blocked = CONTRACT_TYPE_HARD_BLOCKED_DOMAINS.get((contract_type_code or "").strip())
    if not blocked or not text:
        return []
    hits: list[tuple[str, str]] = []
    for domain in sorted(blocked):
        pat = _BLOCKED_DOMAIN_PATTERNS.get(domain)
        if pat is None:
            continue
        m = pat.search(text)
        if m:
            hits.append((domain, m.group(0).strip()))
    return hits


def find_future_transaction_intrusions(text: str, contract_type_code: str) -> list[tuple[str, str]]:
    """"향후 계약에서 정할 사항"을 현재 계약에 삽입하려는 신호 목록.

    유보 취지의 문언이 함께 있으면 빈 목록을 반환한다 — NDA에서 "이 사항은
    후속 개발계약에서 정한다"고 쓰는 것은 정확히 요구된 검토이기 때문이다.
    """
    if not CONTRACT_TYPE_DOMAIN_WHITELIST.get((contract_type_code or "").strip()):
        return []
    if not text:
        return []
    if _RESERVATION_LANGUAGE.search(text):
        return []
    hits: list[tuple[str, str]] = []
    for topic in sorted(_FUTURE_TRANSACTION_PATTERNS):
        m = _FUTURE_TRANSACTION_PATTERNS[topic].search(text)
        if m:
            hits.append((topic, m.group(0).strip()))
    return hits


def enforce_contract_scope(
    clause_results: list[dict[str, Any]],
    *,
    contract_type_code: str,
) -> dict[str, Any]:
    """계약유형 Semantic Scope를 clause_results에 실제로 적용한다.

    차단된 finding은 조용히 남겨두지 않고 목록에서 제거하고, 무엇이 왜
    제거됐는지 리포트로 돌려준다(meta.contract_scope_policy).
    """
    code = (contract_type_code or "").strip()
    report: dict[str, Any] = {
        "contract_type_code": code,
        "policy_applied": bool(CONTRACT_TYPE_DOMAIN_WHITELIST.get(code)),
        "allowed_domains": list(CONTRACT_TYPE_DOMAIN_WHITELIST.get(code, ())),
        "blocked": [],
        "future_transaction_blocked": [],
    }
    if not report["policy_applied"]:
        return report

    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        blob = _finding_text(cr)
        domain_hits = find_blocked_domain_hits(blob, code)
        if domain_hits:
            report["blocked"].append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "domains": [d for d, _ in domain_hits],
                "matched": [m for _, m in domain_hits][:5],
            })
            continue
        future_hits = find_future_transaction_intrusions(blob, code)
        if future_hits:
            report["future_transaction_blocked"].append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "topics": [t for t, _ in future_hits],
                "matched": [m for _, m in future_hits][:5],
            })
            continue
        kept.append(cr)

    clause_results[:] = kept
    return report
