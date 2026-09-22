"""v17 회귀 — Legal Map 미기재 오판 / NDA 무관 축 제거 / 중재 직접답변.

2026-09-21 4차 지시 3·9·10·11항. v16 이 KEEP 판단과 요청사항 답변을 세운
뒤에도 남아 있던 것들을 고정한다.

    3항  실재하는 축을 Legal Map 에서 "미기재" 로 표시하지 않는다
    9항  중재 질문에는 기관·중재지·언어·중재인 수·집행 가능성까지 답한다
    10항 다른 언어본이 없으면 일치 여부는 확인 불가로만 답한다
    11항 NDA 에 대가 지급·검수/준공·추가공사 축을 요구하지 않는다
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.tests.test_v16_keep_first_review import (
    FIXTURE,
    NOTES_FIXTURE,
    REVIEW_FOCUS,
)


def _text() -> str:
    return Path(FIXTURE).read_text(encoding="utf-8")


def _notes() -> list[str]:
    return [
        b for b in Path(NOTES_FIXTURE).read_text(encoding="utf-8").split("\n\n")
        if b.strip()
    ]


# ══════════════════════════════════════════════════════════════════════════
# 지시 11항 — NDA 에 없는 것이 정상인 축
# ══════════════════════════════════════════════════════════════════════════


class NdaAxisScopeTest(unittest.TestCase):
    def test_nda_does_not_require_payment_or_acceptance_axes(self) -> None:
        from runtime.review.legal_map_gate import blocking_axes_for

        axes = blocking_axes_for("nda_confidentiality")
        self.assertNotIn("payment_flow", axes)
        self.assertNotIn("acceptance_and_completion", axes)
        self.assertIn("primary_obligations", axes)

    def test_inapplicable_axes_are_not_reported_missing(self) -> None:
        from runtime.review.legal_map_gate import evaluate_legal_map

        result = evaluate_legal_map(
            {"contract_purpose": "NDA", "our_role_direction": "mutual",
             "primary_obligations": "비밀유지의무"},
            contract_type_code="nda_confidentiality",
        )
        self.assertEqual(result["missing_blocking"], [])
        self.assertNotIn("대가 지급 구조", result["missing_advisory"])
        self.assertNotIn("검수/인도/준공 조건", result["missing_advisory"])

    def test_works_axes_are_skipped_for_nda_risk_matrix(self) -> None:
        from runtime.review.risk_allocation_matrix import (
            build_risk_allocation_matrix,
        )

        matrix = build_risk_allocation_matrix(
            _text(), our_role_direction="mutual",
            contract_type_code="nda_confidentiality",
        )
        keys = {r["key"] for r in matrix.get("rows") or []}
        for key in ("extra_work", "acceptance", "defects", "schedule_delay"):
            self.assertNotIn(key, keys, f"NDA 에 {key} 축이 남아 있다")

    def test_commercial_terms_are_not_required_for_nda(self) -> None:
        from runtime.review.commercial_terms_gate import scan_commercial_terms

        rows = scan_commercial_terms(_text(), contract_type_code="nda_confidentiality")
        self.assertEqual(rows, [])


# ══════════════════════════════════════════════════════════════════════════
# 지시 3항 — Legal Map "미기재" 는 원문으로 확인한다
# ══════════════════════════════════════════════════════════════════════════


class LegalMapGroundingTest(unittest.TestCase):
    def test_existing_axes_are_grounded_from_the_contract(self) -> None:
        from runtime.review.legal_map_grounding import ground_legal_map

        fields: dict[str, object] = {"contract_purpose": "NDA"}
        report = ground_legal_map(fields, contract_text=_text(), canonical_state=None)
        self.assertIn("ip_and_data_ownership", report.grounded)
        self.assertIn("primary_obligations", report.grounded)
        self.assertEqual(report.sources["ip_and_data_ownership"], "contract_text")
        self.assertTrue(str(fields["ip_and_data_ownership"]).startswith("[원문 확인]"))

    def test_canonical_state_fills_our_role(self) -> None:
        from runtime.review.canonical_state import build_canonical_state
        from runtime.review.legal_map_grounding import ground_legal_map

        from dataclasses import replace

        state = replace(
            build_canonical_state(
                contract_type="nda_confidentiality",
                contract_type_family="nda_confidentiality",
                contract_type_label="비밀유지계약(NDA)",
                party_role="party", party_label="",
                counterparty_role="party", counterparty_label="",
            ),
            # 상호 NDA 는 파이프라인에서 legal_state 가 방향을 mutual 로 채운다.
            party_role_direction="mutual",
        )
        fields: dict[str, object] = {}
        report = ground_legal_map(fields, contract_text="", canonical_state=state)
        self.assertEqual(report.sources.get("our_role_direction"), "canonical_state")

    def test_nothing_is_invented_when_the_contract_is_silent(self) -> None:
        from runtime.review.legal_map_grounding import ground_legal_map

        fields: dict[str, object] = {}
        report = ground_legal_map(
            fields, contract_text="이 문서는 아무 내용도 없습니다.", canonical_state=None,
        )
        self.assertEqual(report.grounded, {})


# ══════════════════════════════════════════════════════════════════════════
# 지시 9항 — 중재 질문은 구성요소까지 답한다
# ══════════════════════════════════════════════════════════════════════════


class ArbitrationAnswerTest(unittest.TestCase):
    def test_arbitration_terms_are_extracted(self) -> None:
        from runtime.review.user_request_answers import extract_arbitration_terms

        terms = extract_arbitration_terms(
            "대한상사중재원 국제중재규칙에 따라 서울에서 영어로 진행하는 중재로 최종 "
            "해결하며, 중재인은 1인으로 한다. 중재판정은 최종적이고 구속력을 가진다."
        )
        self.assertEqual(terms["institution"], "대한상사중재원")
        self.assertIn("서울", terms["seat"])
        self.assertIn("영어", terms["language"])
        self.assertIn("1인", terms["arbitrators"])
        self.assertTrue(terms["finality"])


# ══════════════════════════════════════════════════════════════════════════
# 전체 파이프라인 (AI off)
# ══════════════════════════════════════════════════════════════════════════


class NdaPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.bundle = build_clause_level_result(
            service=RuleQueryService(loader),
            entity="일룸",
            contract_type="비밀유지계약서(NDA)",
            text=_text(),
            filename="상호 비밀유지계약서 수정안.pdf",
            answers=None,
            review_focus=REVIEW_FOCUS,
            law_service=None,
            margin_annotations=_notes(),
            ai_provider=None,
            ai_model="",
            ai_timeout_sec=60.0,
            ai_max_tokens=2000,
            ai_temperature=0.1,
        )
        cls.meta = cls.bundle.meta

    def test_legal_map_has_no_false_missing_axis(self) -> None:
        lm = self.meta.get("legal_map_completeness") or {}
        self.assertEqual(lm.get("missing_blocking"), [])
        advisory = lm.get("missing_advisory") or []
        for label in ("대가 지급 구조", "검수/인도/준공 조건", "지식재산/자료 귀속"):
            self.assertNotIn(label, advisory, f"NDA 에서 '{label}' 를 공백으로 보고했다")

    def test_no_construction_axes_in_the_missing_risk_report(self) -> None:
        check = self.meta.get("final_lawyer_self_check") or {}
        detail = " ".join(
            str(c.get("detail") or "")
            for c in (check.get("checks") or [])
            if c.get("key") == "no_missing_risk"
        )
        for word in ("추가공사", "검수", "하자", "공기 지연"):
            self.assertNotIn(word, detail, f"NDA 검토에 '{word}' 축이 섞였다")

    def test_commercial_terms_is_empty_for_nda(self) -> None:
        self.assertEqual(self.meta.get("commercial_terms"), [])

    def test_arbitration_answer_covers_every_component(self) -> None:
        answers = {a["index"]: a for a in (self.meta.get("user_request_answers") or [])}
        seventh = answers.get(7)
        self.assertIsNotNone(seventh)
        terms = seventh.get("arbitration") or {}
        self.assertEqual(terms.get("institution"), "대한상사중재원")
        self.assertTrue(terms.get("seat"))
        self.assertTrue(terms.get("language"))
        self.assertTrue(terms.get("arbitrators"))
        self.assertIn("뉴욕협약", seventh["reason"])
        self.assertIn("중급인민법원", seventh["reason"])

    def test_semantic_fit_check_passes(self) -> None:
        """제8조(자료 관리)가 SOW 로 분류돼 개인정보 문안이 어긋나던 문제."""
        check = self.meta.get("final_lawyer_self_check") or {}
        failed = {
            c["key"] for c in (check.get("checks") or []) if not c.get("ok")
        }
        self.assertNotIn("semantic_fit", failed)


if __name__ == "__main__":
    unittest.main()
