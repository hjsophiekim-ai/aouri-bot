"""회귀검증(2026-09-02 지시) — 마코디-퍼시스 "전략적 파트너십 및 마감재
공급·설계·시공 지원 업무협약서"(16개 조항 혼합계약) 실사례.

원래 결과(acceptance failure): contract_type=NDA 비밀유지계약서 단일분류,
당사자 지위 미확인(rental_provider 오분류), HIGH/MEDIUM 0건. 근본원인은
파이프라인 실패(image-only/CID 폰트 손상 PDF의 네이티브 추출 텍스트가
글자마다 공백이 낀 판독불가 상태였는데도 "성공"으로 처리되고, 그 상태에서
UI가 이전 세션의 stale contract_type 힌트를 그대로 제출)였다.

이 테스트는 문언 하드코딩이 아니라 구조를 검증한다 — 사용자가 직접 붙여준
클린 원문을 fixture로 사용해, 위 사고를 일으킨 각 근본원인이 개별적으로
고쳐졌는지 확인한다. 실제 AI 판단 품질(법률효과 추론)은 이 세션에서 이미
real AI로 직접 확인했으므로(문서 참고), 여기서는 stub AI로 배선만
검증한다.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from runtime.ai.provider import AIResponse, AIUsage
from runtime.review.clause_level import build_clause_level_result
from runtime.review.contract_classifier import classify_contract_detailed
from runtime.review.legal_applicability_review import detect_user_cited_statutes, infer_additional_relevant_statutes
from runtime.review.text_extract import assess_text_quality
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService, TRIGGER_MAP
from runtime.review.user_focus import get_objective_keywords

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "macodi_strategic_partnership.txt"
REVIEW_FOCUS = (
    "우리회사(퍼시스)가 인테리어 사업을 하는데, 스페이스시프트라는 회사를 통해서, "
    "마감재의 공급 및 조달 체계를 구축하고, 설계지원, 프로젝트 지원등의 업무를 지원받으려고 해. "
    "대신에 퍼시스는 연간 최소 마감재 발주량이 있는 형식이야. 혹시 위 계약서가 "
    "하도급법 또는 공정거래법 또는 건설산업기본법 등에 문제가 되지 않는지 판단해줘."
)
# 2026-09-02 실제 두 번째 세션 재현 — 사용자가 "공정거래법"을 문언으로
# 언급하지 않고 "그외 법령"이라고만 했는데, 최소구매의무·직접거래제한·
# 위약벌이라는 명백한 공정거래법 쟁점이 통째로 누락된 사고.
REVIEW_FOCUS_GENERIC_OTHER_LAW = (
    "퍼시스(우리회사)가 인테리어 사업을 하는데, 마코디 라는 업체와 업무협약을 체결하고, "
    "설계업무를 지원받고 자재를 구매하고자 함. 단 우리쪽에 의무적으로 자재를 사야하는 내용이 있음. "
    "건설산업기본법, 하도급법 그외 법령상 문제가 없는지, 우리회사에 불리한 내용이 없는지 검토요청."
)


class _StubAIProvider:
    """Contract Legal Map 호출에는 실제 AI가 답했던 것과 동일한 방향
    (recipient, 확신도 high)을 고정 응답하고, 그 외(조항별 리뷰, 법률
    적용성 검토, meta-extraction)는 각각 결정론적 응답을 준다."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete(self, req):
        payload = json.loads(req.messages[-1].content)
        self.calls.append(payload)
        if "contract_text" in payload and "statutes" not in json.dumps(payload):
            # Contract Legal Map 호출 (payload에 legal_applicability 전용
            # 키가 없는 "contract_text" 단독 payload)
            if "entity" in payload and "contract_type_code" in payload:
                resp = {
                    "our_party": payload.get("entity"),
                    "counterparty": "스페이스시프트",
                    "party_roles": "퍼시스=마감재 구매·프로젝트 발주 측, 스페이스시프트=마감재 판매·플랫폼·설계시공지원 측",
                    "contract_purpose": "마감재 공급 체계 구축 및 설계·시공 연계를 위한 전략적 파트너십",
                    "our_role_direction": "recipient",
                    "our_role_direction_confidence": "high",
                }
                return AIResponse(content=json.dumps(resp, ensure_ascii=False), usage=AIUsage(10, 10, 20), raw=None)
        if "contract_legal_map" in payload:
            # Mandatory Legal Applicability Review 호출
            resp = [
                {
                    "statute": s,
                    "applicability": "있음(추가 확인 필요)",
                    "reasoning": "stub reasoning",
                    "additional_facts_needed": ["stub fact"],
                    "related_clauses": ["제5조"],
                    "risk_level": "MEDIUM",
                }
                for s in ("하도급법", "공정거래법", "건설산업기본법")
            ]
            return AIResponse(content=json.dumps(resp, ensure_ascii=False), usage=AIUsage(10, 10, 20), raw=None)
        if "items" in payload:
            return AIResponse(content="[]", usage=AIUsage(5, 5, 10), raw=None)
        return AIResponse(content="{}", usage=AIUsage(5, 5, 10), raw=None)


def _run_pipeline():
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)
    stub = _StubAIProvider()
    bundle = build_clause_level_result(
        service=service, entity="퍼시스", contract_type="", text=text, filename="macodi_strategic_partnership.txt",
        answers=None, review_focus=REVIEW_FOCUS, law_service=None,
        ai_provider=stub, ai_model="stub-model", ai_timeout_sec=30.0, ai_max_tokens=2000, ai_temperature=0.2,
    )
    return bundle, stub


class _SelfDiscoveryStubAIProvider(_StubAIProvider):
    """법률적용성 검토 호출에서, 사용자가 요청하지 않은 법률(공정거래법)을
    AI가 스스로 추가 판단해 반환하는 상황을 재현한다(2026-09-02 지시:
    "사용자가 법률을 언급하지 않아도 AI가 스스로 판단")."""

    def complete(self, req):
        payload = json.loads(req.messages[-1].content)
        if "contract_legal_map" in payload:
            resp = [
                {
                    "statute": "공정거래법",
                    "applicability": "높음",
                    "reasoning": "최소구매의무·직접거래제한·위약벌 구조로 볼 때 거래상 지위 남용 소지가 있다.",
                    "additional_facts_needed": ["시장 내 지위 확인 필요"],
                    "related_clauses": ["제6조", "제7조"],
                    "risk_level": "HIGH",
                },
            ]
            return AIResponse(content=json.dumps(resp, ensure_ascii=False), usage=AIUsage(10, 10, 20), raw=None)
        return super().complete(req)


class MacodiClassificationTest(unittest.TestCase):
    """title_zone에서 raw contract_type 라벨 제거 수정(2026-09-02) —
    stale "NDA 비밀유지계약서" 힌트가 주어져도 실제 문서 내용 기준으로
    분류되어야 한다."""

    def test_canonical_type_is_not_nda_even_with_stale_hint(self) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        p = classify_contract_detailed(
            entity="퍼시스", contract_type="NDA 비밀유지계약서", text=text,
            filename="[마코디X퍼시스] 전략적_파트너십_업무_협약서.pdf",
        )
        self.assertNotEqual(p.contract_type, "nda_confidentiality")

    def test_canonical_type_is_not_nda_with_clean_hint(self) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        p = classify_contract_detailed(entity="퍼시스", contract_type="", text=text, filename="x.pdf")
        self.assertNotEqual(p.contract_type, "nda_confidentiality")
        self.assertEqual(p.our_party, "퍼시스")
        self.assertEqual(p.counterparty, "스페이스시프트")


class MacodiPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.stub = _run_pipeline()
        cls.meta = cls.bundle.meta
        cls.by_id = {str(cr.get("clause_id") or ""): cr for cr in cls.bundle.clause_results if isinstance(cr, dict)}

    def test_party_role_is_buyer_not_rental_provider(self) -> None:
        """Legal Map role override(v5.6)가 whole-document 키워드 오탐(제8조
        '회수 진행 상황'의 '회수'가 렌탈 반납으로 오인되어 rental_provider로
        잘못 분류되던 문제)을 실제로 교정하는지 확인한다."""
        party = self.meta.get("party_role") or {}
        self.assertEqual(party.get("our_role"), "buyer")
        self.assertEqual(party.get("counterparty_role"), "seller_or_supplier")
        self.assertEqual(self.meta.get("review_posture"), "buyer_favorable")
        override = self.meta.get("legal_map_role_override")
        self.assertIsNotNone(override, "rental_provider 오분류가 override로 교정되어야 한다")
        self.assertEqual(override["previous_our_role"], "rental_provider")
        self.assertEqual(override["overridden_our_role"], "buyer")

    def test_mandatory_legal_applicability_review_covers_all_three_statutes(self) -> None:
        cited = self.meta.get("user_cited_statutes")
        self.assertEqual(set(cited), {"하도급법", "공정거래법", "건설산업기본법"})
        review = self.meta.get("legal_applicability_review")
        self.assertEqual(len(review), 3)
        for item in review:
            self.assertEqual(item["source"], "ai")
            self.assertIn(item["applicability"], ("높음", "있음(추가 확인 필요)", "낮음"))
        # 결과가 있으므로 REVIEW_FAILED_USER_LEGAL_SCOPE_MISSING이 아니어야 한다
        self.assertNotEqual(self.meta.get("review_status"), "REVIEW_FAILED_USER_LEGAL_SCOPE_MISSING")

    def test_no_isr_or_nda_only_checklist_leak(self) -> None:
        isr_ids = [cid for cid in self.by_id if cid.startswith("isr_")]
        self.assertEqual(isr_ids, [])


class MacodiFalsePositiveRegressionTest(unittest.TestCase):
    """실제 리뷰에서 확인된 구체적 오탐 2건 — 근본원인을 각각 직접 검증."""

    def test_act008_risk005_trigger_no_longer_fires_on_bare_subcontract_word(self) -> None:
        """제6조①의 "갑의 하도급 시공사에게"라는 무관한 문구 하나만으로
        "하도급 단가감액/인하(후보) 탐지"(RISK-005/ACT-008, HIGH·승인필요)가
        발동하던 사고 — "하도급"을 단독 트리거에서 제거했으므로, 실제
        단가감액/인하 문구가 없는 텍스트에서는 더 이상 매칭되지 않아야 한다."""
        text_without_price_terms = "갑의 하도급 시공사에게 마감재를 판매하는 주체로서 그 매매의 당사자가 된다."
        self.assertFalse(any(kw in text_without_price_terms for kw in TRIGGER_MAP["ACT-008"]))
        self.assertFalse(any(kw in text_without_price_terms for kw in TRIGGER_MAP["RISK-005"]))
        # 실제 단가 감액/인하 문구가 있으면 여전히 정상적으로 매칭되어야 한다
        text_with_price_terms = "하도급 대금의 단가 감액을 요구하였다."
        self.assertTrue(any(kw in text_with_price_terms for kw in TRIGGER_MAP["ACT-008"]))

    def test_user_focus_status_keyword_no_longer_matches_bare_word(self) -> None:
        """제13조(권리·의무 양도금지)의 "본 협약상의 지위"라는 문구 하나로
        "대리점법상 불이익 제공/거래상 지위 남용" user-focus finding이
        잘못 붙던 사고 — 단독 "지위" 키워드를 제거했으므로 이 문구는 더
        이상 매칭되지 않아야 한다."""
        keywords = get_objective_keywords("dealer_unfair_disadvantage")
        self.assertNotIn("지위", keywords)
        assignment_clause = "본 협약상의 지위 또는 권리·의무의 전부나 일부를 제3자에게 양도하거나 담보로 제공할 수 없다."
        self.assertFalse(any(kw in assignment_clause for kw in keywords))
        # 실제 거래상 지위 남용 문구는 여전히 매칭되어야 한다
        real_case = "거래상 지위를 남용하여 불이익을 제공하였다."
        self.assertTrue(any(kw in real_case for kw in keywords))


class ExtractionQualityGateTest(unittest.TestCase):
    def test_clean_macodi_text_passes_quality_gate(self) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        q = assess_text_quality(text)
        self.assertEqual(q.verdict, "ok")

    def test_garbled_cid_corrupted_text_is_flagged_low_quality(self) -> None:
        # 실사례에서 확인된 손상 패턴을 재현(글자마다 공백) — 문언 자체를
        # 하드코딩 검증하지 않고 패턴(단일 글자 토큰 비율)만 확인한다.
        garbled = " ".join(list("연간전략적파트너십및마감재공급설계시공지원업무협약서")) * 5
        q = assess_text_quality(garbled)
        self.assertEqual(q.verdict, "low_quality")
        self.assertIn("single_char_token_ratio_too_high", q.reasons)


class StatuteDetectionTest(unittest.TestCase):
    def test_detects_all_three_cited_statutes(self) -> None:
        self.assertEqual(
            set(detect_user_cited_statutes(REVIEW_FOCUS)),
            {"하도급법", "공정거래법", "건설산업기본법"},
        )

    def test_no_statutes_detected_when_not_mentioned(self) -> None:
        self.assertEqual(detect_user_cited_statutes("이 조항 좀 봐줘"), [])

    def test_generic_other_law_phrasing_infers_fair_trade_act(self) -> None:
        """실사례: "그외 법령상 문제가 없는지"라고만 했을 때 최소구매의무·
        직접거래제한·위약벌 구조로 볼 때 공정거래법이 추가로 잡혀야 한다."""
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cited = detect_user_cited_statutes(REVIEW_FOCUS_GENERIC_OTHER_LAW)
        self.assertEqual(set(cited), {"하도급법", "건설산업기본법"})
        extra = infer_additional_relevant_statutes(
            review_focus=REVIEW_FOCUS_GENERIC_OTHER_LAW, text=text, already_cited=cited,
        )
        self.assertIn("공정거래법", extra)

    def test_ai_self_identifies_statute_when_user_mentions_none(self) -> None:
        """사용자가 법률을 하나도 지정하지 않아도(review_focus에 법률명
        없음), AI가 사용 가능하면 스스로 판단해 관련 법률을 추가해야 한다
        — 실제 AI로 확인된 동작(문서 참고)을 stub으로 배선 검증."""
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        stub = _SelfDiscoveryStubAIProvider()
        bundle = build_clause_level_result(
            service=service, entity="퍼시스", contract_type="", text=text, filename="x.pdf",
            answers=None, review_focus="이 계약서 좀 검토해줘.", law_service=None,
            ai_provider=stub, ai_model="stub-model", ai_timeout_sec=30.0, ai_max_tokens=2000, ai_temperature=0.2,
        )
        meta = bundle.meta
        self.assertEqual(meta.get("user_cited_statutes"), [])
        review = meta.get("legal_applicability_review")
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["statute"], "공정거래법")
        self.assertEqual(review[0]["source"], "ai_self_identified")
        # 사용자가 요청하지 않았으므로, 이게 없다고 REVIEW_FAILED가 되면 안 된다
        self.assertNotEqual(meta.get("review_status"), "REVIEW_FAILED_USER_LEGAL_SCOPE_MISSING")

    def test_no_inference_without_generic_other_law_phrasing(self) -> None:
        """사용자가 특정 법률만 콕 집어 물었다면(포괄적 "그외 법령" 표현이
        없다면) 임의로 다른 법률을 추가하지 않는다 — 모든 계약에 무차별
        적용 방지."""
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cited = ["하도급법"]
        extra = infer_additional_relevant_statutes(
            review_focus="하도급법 문제 있는지만 봐줘", text=text, already_cited=cited,
        )
        self.assertEqual(extra, [])


class MacodiSeverityCalibrationTest(unittest.TestCase):
    """2026-09-02 후속 지시 — "부차적 정산 문구가 핵심 경제조항보다 HIGH
    상단에 올라오지 않도록" 요청. 신설된 Layer-1 규칙 2개(직접거래제한+
    배액위약벌, 매출연동 최소구매의무)가 실제로 HIGH로 잡히는지, AI 없이도
    (규칙 엔진만으로) 동작하는지 직접 확인한다."""

    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.bundle = build_clause_level_result(
            service=service, entity="퍼시스", contract_type="", text=text, filename="x.pdf",
            answers=None, review_focus=None, law_service=None,
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )
        cls.by_id = {str(cr.get("clause_id") or ""): cr for cr in cls.bundle.clause_results if isinstance(cr, dict)}
        cls.high_ids = {i.get("clause_id") for i in (cls.bundle.meta.get("high_issues_filtered") or [])}

    def test_direct_dealing_restriction_with_penalty_is_high_on_article_6_3(self) -> None:
        cr = self.by_id.get("clr_direct_dealing_restriction_with_penalty")
        self.assertIsNotNone(cr, "제6조 제3항의 직접거래제한+배액위약벌 조합이 탐지되어야 한다")
        self.assertEqual(cr["display_path"], "제6조 제3항")
        self.assertEqual(cr["severity"], "HIGH")
        self.assertEqual(cr.get("original_effect_tags"), ["non_circumvention", "direct_dealing_restriction", "penalty_for_bypass"])
        self.assertIn("clr_direct_dealing_restriction_with_penalty", self.high_ids)

    def test_minimum_purchase_commitment_is_high_on_article_7_1(self) -> None:
        cr = self.by_id.get("clr_minimum_purchase_commitment_fixed_by_revenue_ratio")
        self.assertIsNotNone(cr, "제7조 제1항의 매출연동 최소구매의무가 탐지되어야 한다")
        self.assertEqual(cr["display_path"], "제7조 제1항")
        self.assertEqual(cr["severity"], "HIGH")
        self.assertEqual(cr.get("original_effect_tags"), ["minimum_purchase_commitment"])
        self.assertIn("clr_minimum_purchase_commitment_fixed_by_revenue_ratio", self.high_ids)


if __name__ == "__main__":
    unittest.main()
