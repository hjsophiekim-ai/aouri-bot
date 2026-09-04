"""사전질문(Q-TXN-*) 답변을 canonical_transaction_facts로 승격(2026-09-04 지시).

사전질문은 단순 참고용 대화가 아니라 "계약서만으로 확정할 수 없는 거래실질을
사용자가 보충해주는 법률검토의 증거자료"다. 이 모듈은 그 답변이 이후 모든
모듈(Contract Legal Map/party_role/contract overview/applicable law review/
clause-level review/missing-clause review/AI prompt/final_review_context/
UI/DOCX·PDF)에서 재추정 없이 그대로 쓰이도록 하는 single source of truth를
만든다.

우선순위(요청 3): explicit user answer > confirmed document text >
AI inference > rule inference. `transaction_structure_answers.py`가 이미
이 순서로 `ContractLegalMap.fields`에 사용자 답변을 최우선 반영하므로(항상
덮어씀), 이 모듈은 그 결과물(`legal_map_fields`)을 입력으로 받아 구조화된
facts로 정리하고, 남은 자리표시자를 치환하고, self-check에 필요한 헬퍼를
제공한다.
"""
from __future__ import annotations

import re
from typing import Any

# 사용자가 답변하면 최종 출력에서 "미확인"으로 덮어쓰면 안 되는 핵심 필드
# (요청 4/8) — Contract Legal Map의 UNIVERSAL_FIELDS와 동일한 이름을 쓴다.
MANDATORY_FACT_FIELDS: tuple[str, ...] = (
    "seller", "owner_of_goods", "payment_recipient", "revenue_recipient",
)

# Q-TXN-* question_id -> Contract Legal Map field name. 이 매핑의 단일
# 원본(single source of truth)이다 — transaction_structure_answers.py가
# 이 상수를 그대로 가져다 쓴다(중복 정의로 인한 드리프트 방지).
QUESTION_TO_FIELD: dict[str, str] = {
    "Q-TXN-001-seller": "seller",
    "Q-TXN-002-owner": "owner_of_goods",
    "Q-TXN-003-revenue": "revenue_recipient",
    "Q-TXN-004-payment-collection": "payment_recipient",
    "Q-TXN-005-inventory-risk": "inventory_risk_holder",
    "Q-TXN-006-consumer-liability": "consumer_liability_holder",
    "Q-TXN-007-ip-authenticity": "ip_authenticity_liability",
    "Q-TXN-009-existing-contract-link": "existing_related_contract",
}


def build_canonical_transaction_facts_from_answers(answers: dict[str, Any] | None) -> dict[str, Any]:
    """`ContractLegalMap.fields`가 아직 만들어지기 전(Layer 0 AI 호출 시점)에도
    AI 프롬프트에 확정된 사실관계를 넣을 수 있도록, 원본 answers dict에서
    직접 canonical facts를 구성한다. `build_canonical_transaction_facts()`와
    같은 필드 이름을 쓰되 입력이 answers dict라는 점만 다르다."""
    a = answers or {}
    fields: dict[str, Any] = {}
    for qid, field in QUESTION_TO_FIELD.items():
        val = a.get(qid)
        if isinstance(val, str) and val.strip():
            fields[field] = val.strip()
    support = a.get("Q-TXN-008-relationship-type")
    if isinstance(support, str) and support.strip() == "sales_support_service":
        fields["sales_support_provider"] = "단순 판매지원 용역자(매매계약 당사자 아님)"
    return build_canonical_transaction_facts(fields)

# 조항 원문/수정안에 남아있으면 안 되는 대표적 자리표시자(요청 5) — 계약마다
# 다른 표현을 쓸 수 있으므로 이 패턴은 예시일 뿐 완전하지 않다는 점에 유의:
# 새 rule을 추가할 때는 하드코딩된 대괄호 표기 대신 canonical facts를
# 참조하도록 만드는 것이 근본 해법이고, 이 정규식은 그렇게 하지 못한
# 나머지를 잡는 최종 안전망이다.
_PLACEHOLDER_RX = re.compile(
    r"\[(?:실제\s*판매자\s*[/·]?\s*소유자|확인\s*필요|당사자|실제\s*판매자|실제\s*소유자|미확인)\]"
)


def _normalize_entity_name(name: str) -> str:
    """법인표시(주식회사/(주)/㈜)와 공백 차이를 무시한 비교용 정규화."""
    return re.sub(r"\(주\)|주식회사|㈜|\s+", "", name or "").strip().lower()


def _same_entity(a: str, b: str) -> bool:
    na, nb = _normalize_entity_name(a), _normalize_entity_name(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def build_canonical_transaction_facts(legal_map_fields: dict[str, Any] | None) -> dict[str, Any]:
    """이미 사용자 답변이 최우선 반영된 Contract Legal Map fields에서
    canonical_transaction_facts 구조체를 만든다(요청 1의 예시 형태).

    새 fact를 추정하지 않는다 — legal_map_fields에 값이 있으면 그대로
    옮기고, 없으면 None으로 둔다(모든 모듈이 "없다"와 "확정됐다"를
    구분할 수 있어야 한다).
    """
    f = legal_map_fields or {}

    def _s(key: str) -> str | None:
        v = f.get(key)
        v = str(v).strip() if isinstance(v, str) else ""
        return v or None

    seller = _s("seller")
    owner = _s("owner_of_goods")
    revenue_recipient = _s("revenue_recipient")
    payment_recipient = _s("payment_recipient")
    sales_support_provider = _s("sales_support_provider")

    return {
        "seller": seller,
        "owner_of_goods": owner,
        "revenue_recipient": revenue_recipient,
        "payment_recipient": payment_recipient,
        "sales_support_provider": sales_support_provider,
        "sales_support_role": sales_support_provider,
        # resale_structure: 판매자와 소유자가 동일 주체로 확인된 경우(매입
        # 후 재판매 구조) — 둘 다 답변이 있어야 판단 가능하다.
        "resale_structure": bool(seller and owner and _same_entity(seller, owner)),
    }


def resolved_mandatory_fields(facts: dict[str, Any]) -> list[str]:
    """사용자가 실제로 답변한 핵심 필드 이름 목록(요청 4/8 self-check용)."""
    return [k for k in MANDATORY_FACT_FIELDS if facts.get(k)]


def resolved_party_label(facts: dict[str, Any]) -> str | None:
    """판매자/소유자를 하나의 표시용 라벨로 합친다 — 동일 주체면 이름만,
    다른 주체면 역할을 병기해 어느 쪽도 임의로 생략하지 않는다."""
    seller = facts.get("seller")
    owner = facts.get("owner_of_goods")
    if seller and owner:
        return seller if _same_entity(seller, owner) else f"{seller}(판매자)/{owner}(소유자)"
    return seller or owner


def substitute_resolved_placeholders(
    clause_results: list[dict[str, Any]], facts: dict[str, Any],
) -> list[str]:
    """clause_results 전체를 훑어, 이미 사실관계가 확정됐는데도 남아있는
    "[실제 판매자/소유자]"류 자리표시자를 실제 값으로 치환하는 최종
    안전망(요청 5). 개별 rule이 스스로 canonical facts를 참조해 생성 단계
    에서부터 실제 값을 쓰는 것이 원칙이고, 이 함수는 그렇게 하지 못한
    나머지(예: AI가 생성한 텍스트)를 잡는다. 치환된 clause_id 목록을
    반환한다.
    """
    resolved = resolved_party_label(facts)
    if not resolved:
        return []
    touched: list[str] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        changed = False
        for field_name in ("suggested_rewrite", "rewrite_reason", "legal_business_reason", "problem"):
            val = cr.get(field_name)
            if isinstance(val, str) and _PLACEHOLDER_RX.search(val):
                cr[field_name] = _PLACEHOLDER_RX.sub(resolved, val)
                changed = True
        if changed:
            touched.append(str(cr.get("clause_id") or ""))
    return touched


def find_unresolved_fact_placeholders(
    clause_results: list[dict[str, Any]], facts: dict[str, Any],
) -> list[dict[str, Any]]:
    """사실관계가 이미 확정됐는데(seller/owner 등) 여전히 자리표시자가
    남아있는 finding을 찾는다 — self_check 게이트(REVIEW_FAILED_USER_
    FACTS_NOT_APPLIED)의 입력."""
    if not resolved_party_label(facts):
        return []
    out: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        for field_name in ("suggested_rewrite", "rewrite_reason", "legal_business_reason", "problem"):
            val = cr.get(field_name)
            if isinstance(val, str) and _PLACEHOLDER_RX.search(val):
                out.append({
                    "clause_id": cr.get("clause_id"),
                    "field": field_name,
                    "excerpt": val[:120],
                })
    return out


def build_ai_fact_directive(facts: dict[str, Any]) -> str:
    """AI 프롬프트에 삽입할, 확정된 사실관계를 명시하는 지시문을 만든다
    (요청 2/6) — AI가 계약 원문에 명시되지 않았다는 이유로 이미 사용자가
    답변한 사실을 "미확인"으로 되돌리거나 자체 추정으로 덮어쓰지 못하게
    한다. 값이 하나도 없으면 빈 문자열을 반환한다(프롬프트에 삽입하지
    않음 — 답변이 없는 상태를 "확정된 사실이 없다"로 오인하게 만들면
    안 된다)."""
    lines: list[str] = []
    labels = {
        "seller": "최종 고객과의 매매계약상 판매자",
        "owner_of_goods": "상품(재고)의 소유자",
        "revenue_recipient": "판매대금의 매출 귀속 주체",
        "payment_recipient": "고객으로부터 대금을 실제 수령하는 주체",
        "sales_support_provider": "판매지원 용역 제공자(매매계약 당사자 아님)",
    }
    for key, label in labels.items():
        val = facts.get(key)
        if val:
            lines.append(f"- {label}: {val}")
    if facts.get("resale_structure"):
        lines.append("- 거래구조: 판매자가 상품을 매입한 후 재판매하는 구조(재판매/매입후재판매)")
    if not lines:
        return ""
    return (
        "[사용자 확인 사실관계 — 반드시 확정된 값으로 취급할 것]\n"
        + "\n".join(lines)
        + "\n위 사실관계는 사용자가 사전질문에 직접 답변해 확정한 것이다. 계약서 원문에 "
        "이 내용이 명시되어 있지 않다는 이유로 \"미확인\"이라고 쓰거나 다른 당사자로 "
        "추정하지 말고, 위 값을 그대로 전제해 법률 판단(예: 소비자 관련 책임의 원칙적 "
        "부담자, 매매계약 당사자)을 재구성하라."
    )
