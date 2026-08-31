"""Tests for Layer 0 (Contract Legal Map) and Layer 3 (semantic consistency
gate) — 변호사형 전체계약 판단 지시(2026-09-01) 항목 1/3.

No live API key in this environment — these exercise the wiring with a stub
AIProvider (same idiom as test_hybrid_ai_review.py's _StubAIProvider),
never a real network call.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from runtime.ai.provider import AIResponse, AIUsage
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService
from runtime.review.clause_level import build_clause_level_result
from runtime.review.contract_legal_map import (
    build_contract_legal_map, UNIVERSAL_FIELDS, NDA_EXTENSION_FIELDS,
)
from runtime.review.clause_extraction import extract_clauses

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fiti_testing_service_agreement.txt"


class _StubAIProvider:
    """Routes by payload shape: the Contract Legal Map call sends
    {"contract_text": ...} (no "items" key); the per-clause review call
    sends {"items": [...]}; everything else (meta-extraction) is answered
    with an empty object so it never contaminates the assertions below."""

    def __init__(self, *, legal_map_response: dict[str, Any] | None = None, items_respond=None) -> None:
        self._legal_map_response = legal_map_response or {}
        self._items_respond = items_respond
        self.legal_map_calls: list[dict[str, Any]] = []
        self.items_calls: list[dict[str, Any]] = []

    def complete(self, req):
        payload = json.loads(req.messages[-1].content)
        if "contract_text" in payload:
            self.legal_map_calls.append(payload)
            return AIResponse(content=json.dumps(self._legal_map_response, ensure_ascii=False), usage=AIUsage(10, 10, 20), raw=None)
        if "items" in payload:
            self.items_calls.append(payload)
            out = self._items_respond(payload) if self._items_respond else []
            return AIResponse(content=json.dumps(out, ensure_ascii=False), usage=AIUsage(10, 10, 20), raw=None)
        # meta-extraction or anything else unrecognized — harmless empty object.
        return AIResponse(content="{}", usage=AIUsage(5, 5, 10), raw=None)


def _run_pipeline(*, ai_provider):
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)
    return build_clause_level_result(
        service=service,
        entity="시디즈",
        contract_type="",
        text=text,
        filename="x.pdf",
        answers=None,
        review_focus=None,
        law_service=None,
        ai_provider=ai_provider,
        ai_model="stub-model",
        ai_timeout_sec=30.0,
        ai_max_tokens=2000,
        ai_temperature=0.2,
    )


class ContractLegalMapUnitTest(unittest.TestCase):
    """build_contract_legal_map() in isolation — AI path and no-AI fallback."""

    def setUp(self):
        self.text = FIXTURE_PATH.read_text(encoding="utf-8")
        self.clauses, _ = extract_clauses(self.text)

    def test_no_ai_provider_falls_back_to_regex_and_still_returns_all_universal_fields(self):
        legal_map = build_contract_legal_map(
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
            entity="시디즈", contract_type="시험분석약정서", contract_type_code="testing_inspection_service",
            text=self.text, clauses=self.clauses,
        )
        d = legal_map.to_dict()
        self.assertEqual(d["_legal_map_source"], "regex_fallback_no_ai")
        for k in UNIVERSAL_FIELDS:
            self.assertIn(k, d)
        # NDA 확장 필드는 NDA가 아닌 계약에는 아예 없어야 한다(불필요한 신규 필드 강요 금지).
        for k in NDA_EXTENSION_FIELDS:
            self.assertNotIn(k, d)

    def test_ai_provider_fills_universal_fields_with_single_call(self):
        stub = _StubAIProvider(legal_map_response={
            "parties": "시디즈, FITI시험연구원", "our_party": "시디즈", "counterparty": "FITI시험연구원",
            "party_roles": "위탁자(시험 의뢰인)", "contract_purpose": "가구 제품 시험분석 위탁",
            "primary_obligations": "시료 제출/시험 수행", "payment_flow": "수수료 청구·지급",
            "term": "2년", "termination_structure": "해지 요건 있음",
            "liability_structure": "수탁자 면책 조항 있음", "indemnity_structure": "구상권 조항 있음",
            "third_party_liability": None, "unilateral_rights": None,
            "survival_obligations": "비밀유지의무 존속", "amendment_structure": "서면합의",
            "key_deliverables": "시험성적서",
        })
        legal_map = build_contract_legal_map(
            ai_provider=stub, ai_model="stub-model", ai_timeout_sec=30.0, ai_max_tokens=2000, ai_temperature=0.2,
            entity="시디즈", contract_type="시험분석약정서", contract_type_code="testing_inspection_service",
            text=self.text, clauses=self.clauses,
        )
        d = legal_map.to_dict()
        self.assertEqual(d["_legal_map_source"], "ai")
        self.assertEqual(d["our_party"], "시디즈")
        self.assertEqual(len(stub.legal_map_calls), 1, "Contract Legal Map은 계약당 1회만 호출되어야 한다")

    def test_ai_call_failure_falls_back_gracefully(self):
        class _BrokenProvider:
            def complete(self, req):
                raise RuntimeError("network down")
        legal_map = build_contract_legal_map(
            ai_provider=_BrokenProvider(), ai_model="stub-model", ai_timeout_sec=30.0, ai_max_tokens=2000, ai_temperature=0.2,
            entity="시디즈", contract_type="", contract_type_code="testing_inspection_service",
            text=self.text, clauses=self.clauses,
        )
        self.assertEqual(legal_map.to_dict()["_legal_map_source"], "ai_call_failed_fallback")


class LegalMapPipelineIntegrationTest(unittest.TestCase):
    """The full build_clause_level_result() pipeline exposes the Contract
    Legal Map in bundle.meta, built before per-clause review runs."""

    def test_legal_map_present_in_meta_even_without_ai(self):
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        text = FIXTURE_PATH.read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=service, entity="시디즈", contract_type="", text=text, filename="x.pdf",
            answers=None, review_focus=None, law_service=None,
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )
        legal_map = bundle.meta.get("contract_legal_map")
        self.assertIsInstance(legal_map, dict)
        self.assertEqual(legal_map.get("_legal_map_source"), "regex_fallback_no_ai")

    def test_legal_map_built_via_ai_when_provider_configured(self):
        stub = _StubAIProvider(legal_map_response={"our_party": "시디즈", "contract_purpose": "시험분석 위탁"})
        bundle = _run_pipeline(ai_provider=stub)
        legal_map = bundle.meta.get("contract_legal_map")
        self.assertEqual(legal_map.get("_legal_map_source"), "ai")
        self.assertEqual(len(stub.legal_map_calls), 1)


class SemanticMismatchGateTest(unittest.TestCase):
    """AI가 스스로 보고한 원문/수정문안의 법률효과 태그가 겹치지 않으면
    REVIEW_FAILED_SEMANTIC_MISMATCH로 기록되고, 조용히 finding만 사라지지
    않아야 한다."""

    def test_mismatched_effect_tags_are_flagged_not_silently_dropped(self):
        def respond(payload: dict[str, Any]):
            out = []
            for item in payload["items"]:
                # 제7조(권리 의무의 양도) — 실제 법률효과는 assignment인데,
                # AI가 완전히 무관한 payment_obligation으로 수정문안을 재작성한
                # 것처럼 흉내 낸다(제10조 연대책임을 지급보증으로 오독한 실사례
                # 재현 — 조항번호/문언은 하드코딩하지 않고 임의의 mismatch를
                # 만들어 게이트 자체를 검증한다).
                if str(item.get("clause_id") or "").startswith("KR-7"):
                    ot = str(item["original_text"])
                    out.append({
                        "clause_id": item["clause_id"],
                        "original_text_quote": ot[:20],
                        "party_obligations": "양도 금지 의무",
                        "our_company_risk": "제3자 양도 시 통제력 상실",
                        "rewrite_reason": "양도 조항을 명확히 함",
                        "suggested_rewrite": "위탁자는 협력사의 미수금 채무를 보증하거나 연대하여 지급할 의무를 부담하지 아니한다.",
                        "risk_tier": "MEDIUM",
                        "must_fix": False,
                        "original_effect_tags": ["assignment"],
                        "rewrite_effect_tags": ["payment_obligation"],
                    })
            return out

        stub = _StubAIProvider(items_respond=respond)
        bundle = _run_pipeline(ai_provider=stub)
        art7 = [cr for cr in bundle.clause_results if isinstance(cr, dict) and str(cr.get("clause_id") or "").startswith("KR-7")]
        self.assertTrue(art7, "제7조(양도) clause_result가 파이프라인에 존재해야 검증 가능")
        mismatched = [cr for cr in art7 if cr.get("semantic_mismatch")]
        self.assertTrue(mismatched, "effect tag가 겹치지 않는 AI rewrite는 semantic_mismatch로 기록되어야 한다")
        for cr in mismatched:
            sm = cr["semantic_mismatch"]
            self.assertEqual(sm["status"], "REVIEW_FAILED_SEMANTIC_MISMATCH")
            self.assertEqual(sm["original_effect_tags"], ["assignment"])
            self.assertEqual(sm["rewrite_effect_tags"], ["payment_obligation"])
        # meta에도 집계되어 로그/추적 가능해야 한다(조용히 사라지면 안 됨).
        self.assertTrue(bundle.meta.get("semantic_mismatches"), "meta.semantic_mismatches에 집계되어야 한다")
        # mismatch된 rewrite 원문이 그대로 최종 finding에 적용되면 안 된다.
        for cr in mismatched:
            self.assertNotEqual(
                cr.get("suggested_rewrite"),
                "위탁자는 협력사의 미수금 채무를 보증하거나 연대하여 지급할 의무를 부담하지 아니한다.",
            )

    def test_matching_effect_tags_are_applied_normally(self):
        def respond(payload: dict[str, Any]):
            out = []
            for item in payload["items"]:
                if str(item.get("clause_id") or "").startswith("KR-7"):
                    ot = str(item["original_text"])
                    out.append({
                        "clause_id": item["clause_id"],
                        "original_text_quote": ot[:20],
                        "party_obligations": "양도 금지 의무",
                        "our_company_risk": "제3자 양도 시 통제력 상실",
                        "rewrite_reason": "양도 조항을 명확히 함",
                        "suggested_rewrite": "사전 서면 동의 없이 본 약정상의 권리·의무를 제3자에게 양도할 수 없다.",
                        "risk_tier": "MEDIUM",
                        "must_fix": False,
                        "original_effect_tags": ["assignment"],
                        "rewrite_effect_tags": ["assignment"],
                    })
            return out

        stub = _StubAIProvider(items_respond=respond)
        bundle = _run_pipeline(ai_provider=stub)
        art7 = [cr for cr in bundle.clause_results if isinstance(cr, dict) and str(cr.get("clause_id") or "").startswith("KR-7")]
        mismatched = [cr for cr in art7 if cr.get("semantic_mismatch")]
        self.assertEqual(mismatched, [], "effect tag가 겹치면 semantic_mismatch가 발생하면 안 된다")


if __name__ == "__main__":
    unittest.main()
