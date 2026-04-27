from __future__ import annotations

import unittest
from pathlib import Path

from runtime.draft.service import suggest_template_ids
from runtime.law.search_service import _derive_queries
from runtime.review.classify import classify
from runtime.review.clause_level import build_clause_level_result
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


class AppDevContractFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)

    def test_classify_contract_type_app_dev(self) -> None:
        text = Path("runtime/tests/fixtures/app_dev_contract.txt").read_text(encoding="utf-8")
        res = classify(entity=None, contract_type=None, text=text, filename="앱 개발 용역 계약서.docx")
        self.assertIn("앱개발/소프트웨어개발", res.contract_type)

    def test_suggest_template_ids_not_empty_for_app_dev(self) -> None:
        tids = suggest_template_ids("앱 개발/소프트웨어 개발/SI/유지보수/SaaS")
        self.assertTrue(tids)
        self.assertTrue(any("개인정보" in t or "DPA" in t for t in tids))

    def test_law_queries_suppress_ads_topics_for_app_dev(self) -> None:
        text = "앱 개발 계약이며 앱 내 광고 기능이 포함될 수 있다. 소스코드 산출물 SLA 유지보수"
        qobjs = _derive_queries(entity="일룸/데스커", contract_type="앱개발/소프트웨어개발/SI/유지보수/SaaS", text=text, matched_rules=[], scope="contract")
        qs = [q.get("query") for q in qobjs if isinstance(q, dict) and isinstance(q.get("query"), str)]
        self.assertTrue(any("저작권" in q or "민법" in q for q in qs))
        self.assertFalse(any("표시광고" in q for q in qs))
        self.assertFalse(any("모델" in q for q in qs))

    def test_app_dev_rules_produce_clause_results(self) -> None:
        text = Path("runtime/tests/fixtures/app_dev_contract.txt").read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=self.service,
            entity="일룸/데스커",
            contract_type="앱개발/소프트웨어개발/SI/유지보수/SaaS",
            text=text,
            filename="app_dev_contract.docx",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        matched = bundle.review.get("matched_rules") if isinstance(bundle.review, dict) else None
        self.assertTrue(isinstance(matched, list) and matched)
        self.assertTrue(any(isinstance(r, dict) and str(r.get("rule_id") or "").startswith("APP-") for r in matched))
        self.assertTrue(bundle.clause_results)
        self.assertTrue(any(isinstance(cr, dict) and isinstance(cr.get("suggested_rewrite"), str) and cr.get("suggested_rewrite") for cr in bundle.clause_results))


if __name__ == "__main__":
    unittest.main()

