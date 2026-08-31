from __future__ import annotations

import re


TOPIC_DISPUTE = "dispute"
TOPIC_PAYMENT = "payment_settlement"
TOPIC_PRIVACY = "personal_data"
TOPIC_SAFETY = "safety"
TOPIC_OSS = "open_source"
TOPIC_SOW = "sow_change"
TOPIC_TERMINATION = "termination"
TOPIC_COST = "cost_burden"
TOPIC_DEALER_UNFAIR = "dealer_unfair"
TOPIC_OTHER = "other"

# Dealer-direct structure topics (direct_customer_contract_with_dealer_service)
TOPIC_DEALER_STRUCTURE = "dealer_structure"
TOPIC_INVOICE_BILLING = "invoice_billing"
TOPIC_COLLECTION = "collection_support"
TOPIC_TRADEMARK_IP = "trademark_ip_use"


def _has_any_ci(text: str, needles: list[str]) -> bool:
    low = (text or "").lower()
    for n in needles:
        if not n:
            continue
        nl = n.lower()
        if nl in low:
            if nl.isalnum() and len(nl) <= 4:
                if re.search(rf"\b{re.escape(nl)}\b", low):
                    return True
                continue
            return True
    return False


_RX_PAYMENT_ACTION = re.compile(
    r"(대금|용역비|수수료|보수|사용료|렌탈료)[^.\n]{0,20}(지급|납부|정산|청구|지불|공제|상계)"
    r"|(지급|납부|정산|청구|지불|공제|상계)[^.\n]{0,20}(대금|용역비|수수료|보수|사용료|렌탈료)"
    r"|정산\s*(서|식|기준|주기|기한)|공제\s*[/·]?\s*상계|상계\s*[/·]?\s*공제"
    r"|세금계산서|invoice|지체상금|지연이자",
    re.IGNORECASE,
)


def classify_clause_topic(*, title: str | None, text: str | None) -> str:
    t = (title or "").strip()
    b = (text or "").strip()
    hay = (t + "\n" + b).strip()
    if not hay:
        return TOPIC_OTHER

    # "대금"/"지급" 같은 단어가 조항 어딘가에 한 번이라도 나오면(예: 계약
    # 변경 조항이 "대금의 증감이 예상되는 경우" 정도만 언급) 그 조항 전체를
    # payment_settlement로 분류하던 bare 키워드 스캔을 대금/정산 관련 "행위"
    # 문맥(지급한다/정산한다/공제·상계 등)이 실제로 있는지로 좁혔다 —
    # 계약변경·해지 등 다른 주제의 조항에 정산/공제/상계 rewrite 템플릿이
    # 잘못 삽입되는 rewrite contamination을 막기 위함(계약유형·회사명에
    # 무관한 일반 판단 기준).
    pay_hint = bool(_RX_PAYMENT_ACTION.search(hay))

    if _has_any_ci(hay, ["개인정보", "개인정보보호", "고객정보", "정보주체", "privacy", "dpa", "personal data"]):
        return TOPIC_PRIVACY

    if _has_any_ci(hay, ["산업안전", "중대재해", "안전관리", "작업중지", "보호구", "현장", "시공", "설치", "공사", "산안법"]):
        return TOPIC_SAFETY

    if _has_any_ci(hay, ["오픈소스", "opensource", "open source", "sbom", "gpl", "mit", "apache", "copyleft", "license", "라이선스"]):
        return TOPIC_OSS

    if _has_any_ci(hay, ["sow", "statement of work", "요구사항", "사양", "범위", "변경요청", "change request", "변경관리"]):
        return TOPIC_SOW

    term_hit = _has_any_ci(hay, ["계약해지", "해지", "종료", "중도해지", "갱신", "시정", "최고", "시정기간", "termination"])
    dispute_hit = _has_any_ci(
        hay,
        ["준거법", "관할", "재판관할", "전속관할", "합의관할", "중재", "조정", "분쟁해결", "jurisdiction", "governing law", "arbitration"],
    )
    if term_hit and dispute_hit:
        return TOPIC_TERMINATION
    if term_hit:
        return TOPIC_TERMINATION
    if dispute_hit:
        return TOPIC_DISPUTE

    if _has_any_ci(hay, ["판촉", "광고비", "반품", "판매장려금", "리베이트", "수수료", "비용부담", "비용 부담", "비용전가", "비용 전가", "원상회복"]):
        return TOPIC_COST

    if _has_any_ci(hay, ["대리점", "유통", "위탁거래", "위탁판매", "거래상", "지위", "불이익", "강요", "구속", "공정거래", "대리점법"]):
        return TOPIC_DEALER_UNFAIR

    if pay_hint:
        return TOPIC_PAYMENT

    return TOPIC_OTHER


def infer_rewrite_topics(*, rewrite_text: str | None, reason_codes: list[str] | None = None) -> set[str]:
    out: set[str] = set()
    rc = [str(x) for x in (reason_codes or []) if isinstance(x, str) and x.strip()]
    for c in rc:
        if c in ("ACT-004", "STD-004"):
            out.add(TOPIC_DISPUTE)
        if c in ("RISK-006", "ACT-009"):
            out.add(TOPIC_COST)
        if c in ("RISK-003", "ACT-010"):
            out.add(TOPIC_SAFETY)
        if c in ("APP-002",):
            out.add(TOPIC_OSS)
        if c in ("APP-003",):
            out.add(TOPIC_SOW)
        if c in ("APP-010", "APP-011"):
            out.add(TOPIC_TERMINATION)
        if c in ("APP-007",):
            out.add(TOPIC_PRIVACY)

    txt = (rewrite_text or "").strip()
    if txt:
        out.add(classify_clause_topic(title=None, text=txt))

    out.discard(TOPIC_OTHER)
    return out


def is_topic_compatible(*, clause_topic: str, rewrite_topics: set[str]) -> bool:
    if not rewrite_topics:
        return True
    if clause_topic == TOPIC_DISPUTE:
        return TOPIC_DISPUTE in rewrite_topics
    if clause_topic == TOPIC_PRIVACY:
        return bool(rewrite_topics.intersection({TOPIC_PRIVACY, TOPIC_TERMINATION}))
    if clause_topic == TOPIC_SAFETY:
        return TOPIC_SAFETY in rewrite_topics
    if clause_topic == TOPIC_OSS:
        return TOPIC_OSS in rewrite_topics
    if clause_topic == TOPIC_SOW:
        return TOPIC_SOW in rewrite_topics
    if clause_topic == TOPIC_COST:
        return bool(rewrite_topics.intersection({TOPIC_COST, TOPIC_PAYMENT, TOPIC_DEALER_UNFAIR}))
    if clause_topic == TOPIC_PAYMENT:
        return bool(rewrite_topics.intersection({TOPIC_PAYMENT, TOPIC_COST}))
    if clause_topic == TOPIC_DEALER_UNFAIR:
        return bool(rewrite_topics.intersection({TOPIC_DEALER_UNFAIR, TOPIC_COST, TOPIC_PAYMENT, TOPIC_TERMINATION, TOPIC_DISPUTE, TOPIC_PRIVACY}))
    if clause_topic == TOPIC_TERMINATION:
        return bool(rewrite_topics.intersection({TOPIC_TERMINATION, TOPIC_PRIVACY, TOPIC_COST, TOPIC_PAYMENT}))
    return True
