"""건설공사 계약 거래구조·당사자 지위 판정과 그 게이트의 회귀 테스트.

2026-09-18 지시 —
  "건설계약 검토 시 당사자 지위를 먼저 정확히 확정한 뒤 검토할 것.
   원도급과 재하도급을 반드시 분리할 것.
   하도급법을 원도급 대금관계에 기계적으로 적용하지 말 것."

여기서 고정하는 것은 **판정의 방향**이지 조문 문안이 아니다. 문안은 바뀔 수
있으나, 수급인 계약을 도급인 계약으로 읽거나 원도급 대금에 하도급법을 붙이는
것은 언제나 오류다.
"""
from __future__ import annotations

from runtime.review.construction_transaction_model import (
    ROLE_CONTRACTOR,
    ROLE_CONTRACTOR_WITH_SUBCONTRACT,
    ROLE_OWNER,
    SCOPE_APPLICABLE_AS_PRINCIPAL,
    SCOPE_APPLICABLE_AS_SUBCONTRACTOR,
    SCOPE_NOT_APPLICABLE_PRIME,
    classify_construction_transaction,
    deactivate_foreign_template_findings,
    deactivate_role_mismatched_findings,
    resolve_construction_transaction_model,
    scrub_subcontract_act_from_prime_relationship,
    subcontract_act_scope,
)

# ── 실측형 계약 원문(축약) ──────────────────────────────────────────────────

CONTRACT_WE_ARE_CONTRACTOR = """
공사도급계약서

주식회사 대한개발(이하 "도급인"이라 한다)과 주식회사 퍼시스(이하 "수급인"이라 한다)는
다음과 같이 공사도급계약을 체결한다.

제1조(공사의 내용) 도급인은 아래 인테리어공사를 수급인에게 도급하고, 수급인은 이를
인수하여 시공한다.
제2조(공사기간) 착공일은 2026. 10. 1.로 하고 준공일은 2027. 3. 31.로 한다.
제3조(공사대금) 도급금액은 금 이십억원으로 한다. 기성금은 도급인이 정하는 바에 따라
지급한다.
제4조(준공검사) 수급인은 공사를 완료한 때에는 도급인의 준공검사를 받아야 한다.
제5조(설계변경) 설계도서의 변경이 필요한 경우 도급인의 지시에 따른다.
제6조(지체상금) 수급인이 준공일까지 공사를 완성하지 못한 경우 지체일수 1일당
계약금액의 1000분의 1에 해당하는 지체상금을 지급한다.
제7조(하자담보책임) 수급인은 준공일부터 5년간 하자보수의무를 부담한다.
제8조(대금의 유보 및 상계) 도급인은 이의가 있는 경우 공사대금의 지급을 유보할 수 있고,
수급인에 대한 일체의 채권으로 공사대금과 상계할 수 있다.
제9조(책임) 본 공사와 관련하여 발생하는 일체의 사고 및 손해에 대하여는 수급인이
전적으로 책임진다.
제10조(안전관리) 현장의 안전관리는 수급인이 전적으로 책임진다.
"""

CONTRACT_WE_ARE_OWNER = """
공사도급계약서

주식회사 퍼시스(이하 "도급인"이라 한다)와 주식회사 성원건설(이하 "수급인"이라 한다)은
다음과 같이 계약을 체결한다.

제1조(목적) 도급인은 본사 사옥 리모델링 건설공사를 수급인에게 도급하고 수급인은 이를
수급하여 시공한다.
제2조(공사기간) 착공 2026. 11. 1., 준공 2027. 5. 31.
제3조(공사대금) 계약금액은 금 삼십억원이며 기성 부분에 대하여 매월 지급한다.
제4조(설계변경) 설계변경이 있는 경우 계약금액을 조정한다.
제5조(준공검사) 도급인은 준공검사를 실시한다.
제6조(하자) 수급인은 하자담보책임을 진다.
"""

CONTRACT_SUBCONTRACT_PLANNED = CONTRACT_WE_ARE_CONTRACTOR + """
제11조(하도급) 수급인은 도급인의 서면 승인을 받아 공사의 일부를 전문업체에 재하도급할
수 있다. 하수급인의 귀책사유로 인한 손해는 수급인이 책임진다.
"""

CONTRACT_WE_ARE_SUBCONTRACTOR = """
건설공사 하도급계약서

주식회사 종합건설(이하 "원사업자"라 한다)과 주식회사 퍼시스(이하 "수급인"이라 한다)는
원사업자가 발주처로부터 도급받은 공사 중 가구공사에 관하여 다음과 같이 하도급계약을
체결한다.

제1조(공사내용) 원사업자는 원도급계약에 따른 공사 중 가구 설치공사를 수급인에게
하도급하고 수급인은 이를 시공한다.
제2조(공사기간) 착공 2026. 12. 1., 준공 2027. 2. 28.
제3조(하도급대금) 계약금액은 금 오억원으로 하며 기성에 따라 지급한다.
제4조(준공검사) 원사업자는 준공검사를 실시한다.
제5조(설계변경) 설계변경 시 계약금액을 조정한다.
제6조(하자담보) 수급인은 하자담보책임을 진다.
"""

NOT_CONSTRUCTION = """
비밀유지계약서

갑과 을은 상호 제공하는 비밀정보의 보호에 관하여 다음과 같이 약정한다.
제1조(비밀정보의 정의) 본 계약에서 비밀정보라 함은 ...
제2조(비밀유지의무) 수령당사자는 비밀정보를 제3자에게 누설하여서는 아니 된다.
"""


# ── 1. 거래구조 판정 ────────────────────────────────────────────────────────

def test_건설공사_신호가_충분하면_건설계약으로_본다():
    model = classify_construction_transaction(contract_text=CONTRACT_WE_ARE_CONTRACTOR)
    assert model.is_construction
    assert model.construction_confident


def test_건설이_아닌_계약은_판정하지_않는다():
    model = classify_construction_transaction(contract_text=NOT_CONSTRUCTION)
    assert not model.is_construction
    assert model.canonical_contract_type == ""
    assert not model.is_settled


def test_당사자_정의에서_우리가_수급인임을_읽는다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    assert model.our_role == ROLE_CONTRACTOR
    assert model.role_confident
    assert model.is_contractor_side
    assert not model.is_owner_side
    assert model.is_settled


def test_당사자_정의에서_우리가_도급인임을_읽는다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_OWNER, entity="주식회사 퍼시스",
    )
    assert model.our_role == ROLE_OWNER
    assert model.is_owner_side
    assert not model.is_contractor_side


def test_재하도급이_예정되면_지위는_수급인_겸_재하도급인이다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_SUBCONTRACT_PLANNED, entity="주식회사 퍼시스",
    )
    assert model.our_role == ROLE_CONTRACTOR_WITH_SUBCONTRACT
    assert model.is_contractor_side
    assert model.subcontract_relationship_in_scope


def test_사전질문_답변이_텍스트_판정보다_우선한다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR,
        entity="주식회사 퍼시스",
        answers={"Q-CONST-ROLE-001-our-position": "we_are_ordering_party"},
    )
    assert model.our_role == ROLE_OWNER
    assert model.role_confident


def test_사용자_설명과_계약서가_엇갈리면_지위를_확정하지_않는다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR,
        user_description="우리가 다른 업체에 공사를 발주하는 건입니다.",
        entity="주식회사 퍼시스",
    )
    assert not model.is_settled
    assert model.our_role == ""
    assert "다른 지위" in model.role_basis


def test_돈을_못_받는_리스크_선언을_읽는다():
    model = resolve_construction_transaction_model(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR,
        user_description="공사는 우리가 도급받아 수행합니다. 돈을 못 받는 리스크가 최대 리스크입니다.",
        entity="주식회사 퍼시스",
    )
    assert model.payment_risk_priority
    assert model.is_contractor_side


def test_canonical_계약유형은_construction으로_확정된다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    assert model.canonical_contract_type == "construction"


# ── 2. 하도급법 적용 관계 분리(지시 2항) ────────────────────────────────────

def test_원도급_대금관계에는_하도급법을_적용하지_않는다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    scope = subcontract_act_scope(model)
    assert scope.scope == SCOPE_NOT_APPLICABLE_PRIME
    assert not scope.applies_to_this_contract
    assert not scope.applies_to_subcontract


def test_재하도급이_있으면_그_계약에만_하도급법이_적용된다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_SUBCONTRACT_PLANNED, entity="주식회사 퍼시스",
    )
    scope = subcontract_act_scope(model)
    assert scope.scope == SCOPE_APPLICABLE_AS_PRINCIPAL
    assert not scope.applies_to_this_contract
    assert scope.applies_to_subcontract


def test_우리가_수급사업자면_이_계약에_하도급법이_적용된다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_SUBCONTRACTOR, entity="주식회사 퍼시스",
    )
    assert model.is_contractor_side
    assert model.we_are_subcontractor
    scope = subcontract_act_scope(model)
    assert scope.scope == SCOPE_APPLICABLE_AS_SUBCONTRACTOR
    assert scope.applies_to_this_contract


def test_법률_게이트가_원도급에서_하도급법을_비적용으로_확정한다():
    from runtime.review.statute_applicability_gate import assess_subcontract_act

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    decision = assess_subcontract_act(
        entity="주식회사 퍼시스",
        text=CONTRACT_WE_ARE_CONTRACTOR,
        construction_model=model,
    )
    assert decision.conclusion == "비적용"
    assert decision.blocked


def test_법률_게이트가_수급사업자_지위에서는_적용으로_확정한다():
    from runtime.review.statute_applicability_gate import assess_subcontract_act

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_SUBCONTRACTOR, entity="주식회사 퍼시스",
    )
    decision = assess_subcontract_act(
        entity="주식회사 퍼시스",
        text=CONTRACT_WE_ARE_SUBCONTRACTOR,
        construction_model=model,
    )
    assert decision.applicable
    assert not decision.blocked


def test_원도급_finding에서_하도급법_근거를_떼어낸다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_SUBCONTRACT_PLANNED, entity="주식회사 퍼시스",
    )
    scope = subcontract_act_scope(model)
    results = [
        {
            "clause_id": "c3",
            "problem": "공사대금 지급기한이 없습니다. 하도급법 제13조에 따라 원사업자는 60일 이내에 하도급대금을 지급해야 합니다.",
        },
        {
            "clause_id": "CWS-02",
            "construction_scope": "subcontract",
            "problem": "재하도급 계약에 하도급대금 지급기한을 반영해야 합니다.",
        },
    ]
    changed = scrub_subcontract_act_from_prime_relationship(results, model, scope)
    assert [c["clause_id"] for c in changed] == ["c3"]
    assert "하도급대금" not in results[0]["problem"]
    assert "공사대금 지급기한이 없습니다" in results[0]["problem"]
    # 재하도급 항목은 그대로 남는다 — 그 법이 실제로 적용되는 관계다.
    assert "하도급대금" in results[1]["problem"]


# ── 3. Hard Gate ────────────────────────────────────────────────────────────

def test_타_계약유형_템플릿이_섞이면_제거한다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    results = [
        {"clause_id": "ok", "problem": "기성금 지급 절차가 없습니다."},
        {"clause_id": "bad", "problem": "판매장려금 지급기준이 불명확합니다."},
        {"clause_id": "bad2", "issue_title": "대리점의 판매목표 강제 소지"},
    ]
    removed = deactivate_foreign_template_findings(
        results, model, contract_text=CONTRACT_WE_ARE_CONTRACTOR,
    )
    assert {r["clause_id"] for r in removed} == {"bad", "bad2"}
    assert [r["clause_id"] for r in results] == ["ok"]


def test_계약_원문이_쓰는_말은_혼입이_아니다():
    text = CONTRACT_WE_ARE_CONTRACTOR + "\n제12조(자문료) 설계 자문료는 별도로 정한다."
    model = classify_construction_transaction(contract_text=text, entity="주식회사 퍼시스")
    results = [{"clause_id": "a", "problem": "자문료 산정 기준이 없습니다."}]
    removed = deactivate_foreign_template_findings(results, model, contract_text=text)
    assert removed == []
    assert len(results) == 1


def test_수급인인데_수급인_책임을_키우는_권고는_제거한다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    results = [
        {
            "clause_id": "wrong",
            "suggested_rewrite": "수급인의 책임을 강화하여 하자담보책임 기간을 연장한다.",
        },
        {"clause_id": "right", "suggested_rewrite": "지체상금 총액은 계약금액의 10%를 초과하지 아니한다."},
    ]
    removed = deactivate_role_mismatched_findings(results, model)
    assert [r["clause_id"] for r in removed] == ["wrong"]
    assert [r["clause_id"] for r in results] == ["right"]


def test_지위가_확정되지_않으면_지위_게이트는_아무것도_하지_않는다():
    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR,
        user_description="우리가 공사를 발주합니다.",
        entity="주식회사 퍼시스",
    )
    assert not model.is_settled
    results = [{"clause_id": "x", "suggested_rewrite": "수급인의 책임을 강화한다."}]
    assert deactivate_role_mismatched_findings(results, model) == []
    assert len(results) == 1


# ── 4. 체크리스트 ───────────────────────────────────────────────────────────

def test_수급인_체크리스트가_주입되고_도급인_항목은_섞이지_않는다():
    from runtime.review.checklists.construction_works import run_construction_checklist

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    items = run_construction_checklist(
        text=CONTRACT_WE_ARE_CONTRACTOR, clauses=[], model=model,
    )
    ids = {i["clause_id"] for i in items}
    assert any(i.startswith("CWC-") for i in ids)
    assert not any(i.startswith("CWO-") for i in ids)
    assert not any(i.startswith("CWS-") for i in ids)


def test_도급인이면_발주자_보호_체크리스트만_돈다():
    from runtime.review.checklists.construction_works import run_construction_checklist

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_OWNER, entity="주식회사 퍼시스",
    )
    items = run_construction_checklist(text=CONTRACT_WE_ARE_OWNER, clauses=[], model=model)
    ids = {i["clause_id"] for i in items}
    assert any(i.startswith("CWO-") for i in ids)
    assert not any(i.startswith("CWC-") for i in ids)


def test_재하도급이_예정되면_재하도급_체크리스트가_함께_돈다():
    from runtime.review.checklists.construction_works import run_construction_checklist

    model = classify_construction_transaction(
        contract_text=CONTRACT_SUBCONTRACT_PLANNED, entity="주식회사 퍼시스",
    )
    items = run_construction_checklist(
        text=CONTRACT_SUBCONTRACT_PLANNED, clauses=[], model=model,
    )
    ids = {i["clause_id"] for i in items}
    assert any(i.startswith("CWC-") for i in ids)
    assert any(i.startswith("CWS-") for i in ids)


def test_지위가_미확정이면_체크리스트를_주입하지_않는다():
    from runtime.review.checklists.construction_works import run_construction_checklist

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR,
        user_description="우리가 공사를 발주하는 쪽입니다.",
        entity="주식회사 퍼시스",
    )
    assert run_construction_checklist(
        text=CONTRACT_WE_ARE_CONTRACTOR, clauses=[], model=model,
    ) == []


def test_모든_체크리스트_항목에_완성_조문과_수정이유가_있다():
    from runtime.review.checklists.construction_works import ALL_CHECKS

    forbidden = ("보완 필요", "변호사 확인", "추후 협의", "검토 필요함")
    for check in ALL_CHECKS:
        assert check.clause_text.strip(), check.check_id
        assert len(check.clause_text) > 80, check.check_id
        assert check.problem.strip(), check.check_id
        assert check.legal_business_reason.strip(), check.check_id
        assert check.negotiation_position.strip(), check.check_id
        for bad in forbidden:
            assert bad not in check.clause_text, f"{check.check_id}: {bad}"
        if check.severity == "HIGH":
            assert check.high_basis.strip(), check.check_id


# ── 5. Payment Risk Package(지시 3항 후단) ──────────────────────────────────

def test_수급인_계약에서_대금_회수_사슬이_끊긴_것을_잡는다():
    from runtime.review.construction_payment_package import (
        build_payment_risk_package, payment_package_finding,
    )

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    pkg = build_payment_risk_package(text=CONTRACT_WE_ARE_CONTRACTOR, model=model)
    assert pkg["applied"]
    assert pkg["chain_broken"]
    broken = {b["key"] for b in pkg["broken_links"]}
    # 검사기한 없음 / 기성확정 절차 없음 / 유보 무제한 / 상계 무제한
    assert "completion_inspection" in broken
    assert "payment_withholding" in broken
    assert "set_off" in broken

    finding = payment_package_finding(
        pkg, text=CONTRACT_WE_ARE_CONTRACTOR, clauses=[], model=model,
    )
    assert finding is not None
    assert finding["risk_tier"] == "HIGH"
    assert finding["high_severity_basis"]
    assert "①" in finding["suggested_rewrite"]
    assert finding["redline_instruction"]


def test_도급인_계약에서는_대금_회수_사슬을_위험으로_보지_않는다():
    from runtime.review.construction_payment_package import build_payment_risk_package

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_OWNER, entity="주식회사 퍼시스",
    )
    pkg = build_payment_risk_package(text=CONTRACT_WE_ARE_OWNER, model=model)
    assert not pkg["applied"]


# ── 6. 사전질문 ─────────────────────────────────────────────────────────────

def test_지위_미확정이면_지위_확인_질문이_나간다():
    from runtime.questions.generator import generate_questions

    qs = generate_questions(
        entity="주식회사 퍼시스",
        contract_type="공사도급계약",
        detected_rule_ids=[],
        contract_text=CONTRACT_WE_ARE_CONTRACTOR,
        review_focus="우리가 공사를 발주하는 건입니다.",
    )
    ids = [q.question_id for q in qs]
    assert "Q-CONST-ROLE-001-our-position" in ids
    q = next(q for q in qs if q.question_id == "Q-CONST-ROLE-001-our-position")
    assert {o.value for o in q.options} == {
        "we_are_contractor", "we_are_contractor_with_subcontract", "we_are_ordering_party",
    }


def test_지위가_확정되면_지위_확인_질문은_나가지_않는다():
    from runtime.questions.generator import generate_questions

    qs = generate_questions(
        entity="주식회사 퍼시스",
        contract_type="공사도급계약",
        detected_rule_ids=[],
        contract_text=CONTRACT_WE_ARE_CONTRACTOR,
        review_focus="우리가 도급받아 시공하는 공사입니다.",
    )
    assert "Q-CONST-ROLE-001-our-position" not in [q.question_id for q in qs]


def test_도급인_발주는_건설위탁이_아니다():
    """자기 시설을 짓기 위한 발주는 하도급법상 건설위탁이 아니다(지시 6항).

    발주자와 원사업자를 구분하지 않으면, 사옥 리모델링 발주 계약에
    '하도급대금 지급기한 60일'·'직접지급청구권' 이 붙는다.
    """
    from runtime.review.construction_transaction_model import (
        SCOPE_OWNER_DEPENDS_ON_BUSINESS,
    )
    from runtime.review.statute_applicability_gate import assess_subcontract_act

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_OWNER, entity="주식회사 퍼시스",
    )
    assert subcontract_act_scope(model).scope == SCOPE_OWNER_DEPENDS_ON_BUSINESS
    decision = assess_subcontract_act(
        entity="주식회사 퍼시스", text=CONTRACT_WE_ARE_OWNER, construction_model=model,
    )
    assert decision.conclusion == "비적용"
    assert "발주자" in decision.reason


def test_산업안전보건법은_현장_작업이_있을_때만_적용된다():
    from runtime.review.statute_applicability_gate import assess_safety_acts

    model = classify_construction_transaction(
        contract_text=CONTRACT_WE_ARE_CONTRACTOR, entity="주식회사 퍼시스",
    )
    applied = assess_safety_acts(text=CONTRACT_WE_ARE_CONTRACTOR, construction_model=model)
    assert applied.applicable
    assert "수급인" in applied.reason

    none = assess_safety_acts(text=NOT_CONSTRUCTION)
    assert none.blocked


def test_건설_신호가_약한_계약은_건설_전용_판단으로_넘기지_않는다():
    """전략적 제휴계약이 "시공" 을 여러 번 쓴다고 건설계약이 되지 않는다.

    v9에서 고쳐 둔 오판(전략적 제휴계약이 "시공" 16회만으로 건설산업기본법
    적용으로 판정)이 되살아나지 않게 고정한다. 확신하지 못하면 법률 판단은
    기존 일반 로직(업 기준·신호 개수)이 그대로 한다.
    """
    from pathlib import Path

    from runtime.review.statute_applicability_gate import (
        assess_construction_act, assess_subcontract_act,
    )

    fixture = Path(__file__).parent / "fixtures" / "macodi_strategic_partnership.txt"
    text = fixture.read_text(encoding="utf-8")
    model = classify_construction_transaction(contract_text=text, entity="주식회사 퍼시스")

    assert not model.construction_confident
    assert not model.is_settled
    # 확신하지 못하므로 계약유형을 덮어쓰지 않는다.
    assert model.canonical_contract_type == ""
    # 법률 판단도 건설 전용 경로로 넘어가지 않는다.
    assert assess_construction_act(text=text, construction_model=model).conclusion == "비적용"
    assert assess_subcontract_act(
        entity="주식회사 퍼시스", text=text, construction_model=model,
    ).conclusion == "비적용"


def test_확신하지_못한_건설계약은_결과를_막지_않는다():
    """과차단 방지 — 건설공사로 확신하지 못하면 지위 미확정도 차단 사유가 아니다."""
    from runtime.review.checklists.construction_works import run_construction_checklist

    weak = "본 계약에 따라 을은 시공 및 설치를 담당하고 갑은 제품을 공급한다. 하자 발생 시 협의한다."
    model = classify_construction_transaction(contract_text=weak, entity="주식회사 퍼시스")
    assert not model.construction_confident
    assert run_construction_checklist(text=weak, clauses=[], model=model) == []


def test_지위_미확정이면_파이프라인이_결과를_확정본으로_내보내지_않는다():
    """지시 9항 후단 — 지위가 셋 중 하나로 확정되지 않으면 결과를 생성하지 않는다."""
    from runtime.review.clause_level import build_clause_level_result
    from runtime.review.construction_transaction_model import (
        REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED,
    )
    from runtime.review.delivery_gate import NON_REMEDIABLE_STATUSES, STATUS_LABELS
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService

    # 차단 상태는 전달 게이트에 등록되어 있어야 한다 — 등록되지 않으면
    # "기록 후 전달" 기본값으로 흘러가 차단이 아무 일도 하지 않는다.
    assert REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED in NON_REMEDIABLE_STATUSES
    assert STATUS_LABELS.get(REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED)

    loader = RuleLoader()
    loader.load()
    bundle = build_clause_level_result(
        service=RuleQueryService(loader),
        entity="주식회사 퍼시스",
        contract_type="공사도급계약",
        text=CONTRACT_WE_ARE_CONTRACTOR,
        filename="공사도급계약서.docx",
        answers=None,
        review_focus="우리가 다른 업체에 공사를 발주하는 건입니다.",
        law_service=None, ai_provider=None, ai_model="", ai_timeout_sec=60.0,
        ai_max_tokens=2000, ai_temperature=0.1,
    )
    meta = bundle.meta
    assert meta.get("review_status") == REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED
    assert meta.get("construction_role_unsettled")
    assert "도급인 / 수급인" in str(meta.get("review_status_detail"))
    # 지위를 모르는 상태에서 지위별 체크리스트를 주입하지 않았는가.
    assert meta.get("construction_checklist") == []


def test_지위가_확정되면_파이프라인이_지위별_체크리스트를_주입한다():
    from runtime.review.clause_level import build_clause_level_result
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService

    loader = RuleLoader()
    loader.load()
    bundle = build_clause_level_result(
        service=RuleQueryService(loader),
        entity="주식회사 퍼시스",
        contract_type="공사도급계약",
        text=CONTRACT_WE_ARE_CONTRACTOR,
        filename="공사도급계약서.docx",
        answers=None,
        review_focus="우리가 도급받아 시공합니다. 돈을 못 받는 리스크가 최대 리스크입니다.",
        law_service=None, ai_provider=None, ai_model="", ai_timeout_sec=60.0,
        ai_max_tokens=2000, ai_temperature=0.1,
    )
    meta = bundle.meta
    model = meta.get("construction_transaction_model") or {}
    assert model.get("our_role") == ROLE_CONTRACTOR
    assert meta.get("construction_role_override", {}).get("now") == "contractor"
    assert not meta.get("review_status")

    final = meta.get("final_findings") or {}
    ids = {
        str(i.get("clause_id"))
        for bucket in ("high_issues", "medium_issues")
        for i in (final.get(bucket) or [])
    }
    # 대금 회수 패키지가 HIGH 로 살아 있어야 한다 — 담당자가 최대 리스크라고
    # 밝힌 축이다.
    assert "CWP-PAYMENT-PACKAGE" in ids
    # 수급인 관점 축이 채워졌는가.
    assert len([i for i in ids if i.startswith("CWC-")]) >= 4
    # 도급인 관점 항목은 섞이지 않았는가.
    assert not [i for i in ids if i.startswith("CWO-")]
