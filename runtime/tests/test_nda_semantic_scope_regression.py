"""NDA Semantic Scope / User Review Focus 회귀 테스트 (2026-09-08 지시).

에이슬립–일룸 NDA acceptance failure 재발 방지:
계약유형을 nda_confidentiality로 정확히 분류했음에도 콘텐츠 제작·광고계약용
권고(콘텐츠 저작권 양도, 광고매체 사용권, 음원·효과음, 모델 초상권, 촬영장소,
콘텐츠 검수, 지급조건, 포트폴리오)가 혼입되고 존재하지 않는 제14조까지
생성됐던 사고를, 항목 1~11의 각 게이트별로 잠근다.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_level import (
    _classify_contract_type_by_substance,
    build_clause_level_result,
)
from runtime.review.contract_classifier import classify_contract_detailed
from runtime.review.contract_scope_policy import (
    enforce_contract_scope,
    find_blocked_domain_hits,
    find_future_transaction_intrusions,
)
from runtime.review.finding_integrity_gates import (
    enforce_clause_semantic_gate,
    enforce_valid_clause_references,
)
from runtime.review.mandatory_review_issues import (
    VERDICTS,
    answer_mandatory_review_issues,
    derive_mandatory_review_issues,
)
from runtime.review.nda_scope_rules import apply_nda_scope_rules
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService

FIXTURE = Path(__file__).parent / "fixtures" / "nda_ai_sleep_collaboration.txt"

NDA_CODE = "nda_confidentiality"

# 이 NDA 검토 결과에 절대 나와서는 안 되는 어휘(지시 항목 11 후단).
FORBIDDEN_TERMS = (
    "콘텐츠 검수", "광고 대금", "광고비", "초상권", "촬영장소", "촬영 장소",
    "음원", "효과음", "포트폴리오", "광고매체", "광고 매체", "매체 사용권",
    "시안", "제14조",
)

# 반드시 검토되어야 하는 golden acceptance 항목(지시 항목 11 전단).
GOLDEN_CLAUSE_IDS = (
    "nda_derived_information_overbroad",
    "nda_improvement_ip_assigned_to_discloser",
    "nda_foreground_ip_not_reserved",
    "nda_general_model_training_unrestricted",
    "nda_personal_data_boundary_missing",
    "nda_third_party_recipient_scope",
    "nda_trade_secret_survival_capped",
    "nda_return_destruction_backup_exception",
    "nda_injunction_prerequisites_preadmitted",
    "nda_subsequent_agreement_priority",
)

REVIEW_FOCUS = (
    "비밀정보 범위, background IP, 독자개발 정보, 향후 개발 결과, AI 학습 및 데이터 재사용, "
    "개인정보/민감정보, 제3자 제공(외부 개발사·시험기관), 비밀유지기간, 반환/폐기/백업, "
    "손해배상 및 가처분, 후속 계약 우선순위를 검토해주세요. "
    "향후 수면 분석 제품 공동개발 계약을 예정하고 있습니다."
)


class NdaSemanticScopeRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)
        cls.text = FIXTURE.read_text(encoding="utf-8")
        cls.clauses, _ = extract_clauses(cls.text)
        cls.bundle = build_clause_level_result(
            service=cls.service,
            entity="일룸",
            contract_type="",
            text=cls.text,
            filename="에이슬립-일룸_NDA_상호검토수정안.docx",
            answers=None,
            review_focus=REVIEW_FOCUS,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )

    # ── 분류 ────────────────────────────────────────────────────────────────
    def test_ai_nda_is_not_classified_as_content_production(self) -> None:
        """"AI 모델"이라는 단어 하나로 content_production이 되지 않아야 한다."""
        self.assertNotEqual(
            _classify_contract_type_by_substance("", self.text, "NDA.docx"),
            "content_production",
        )
        self.assertNotEqual(self.bundle.meta.get("contract_class"), "content_production")

    def test_canonical_classifier_still_says_nda(self) -> None:
        profile = classify_contract_detailed(
            entity="일룸", contract_type="", text=self.text, filename="NDA.docx", answers=None,
        )
        self.assertEqual(profile.contract_type, NDA_CODE)

    def test_real_advertising_contract_still_classified_as_content_production(self) -> None:
        """오분류를 좁히면서 진짜 광고 콘텐츠 제작 계약을 놓치지 않아야 한다."""
        self.assertEqual(
            _classify_contract_type_by_substance(
                "광고 콘텐츠 제작 대행 계약", "콘텐츠 제작 및 검수, 시안 확정", "ad.docx",
            ),
            "content_production",
        )

    # ── 항목 4: Rule Whitelist HARD BLOCK ───────────────────────────────────
    def test_content_production_findings_are_hard_blocked(self) -> None:
        injected = [
            {
                "clause_id": "cp004_ip_transfer",
                "display_path": "제8조",
                "suggested_rewrite": "제작된 콘텐츠의 저작재산권 일체는 갑에게 양도한다.",
            },
            {
                "clause_id": "cp_media",
                "display_path": "제9조",
                "suggested_rewrite": "갑은 온·오프라인 매체 및 SNS에 게재할 수 있다.",
            },
            {
                "clause_id": "cp_portrait",
                "display_path": "제3조",
                "suggested_rewrite": "모델의 초상권 및 촬영 장소 사용에 관하여 을이 책임진다.",
            },
            {
                "clause_id": "cp_portfolio",
                "display_path": "제5조",
                "suggested_rewrite": "을은 본 성과를 포트폴리오로 활용할 수 있다.",
            },
            {
                "clause_id": "keeper",
                "display_path": "제2조",
                "suggested_rewrite": "“비밀정보”의 범위에서 독자적으로 개발한 정보를 제외한다.",
            },
        ]
        report = enforce_contract_scope(injected, contract_type_code=NDA_CODE)
        self.assertTrue(report["policy_applied"])
        self.assertEqual([cr["clause_id"] for cr in injected], ["keeper"])
        self.assertEqual(len(report["blocked"]), 4)

    def test_scope_policy_is_inert_for_unlisted_contract_types(self) -> None:
        """표에 없는 계약유형은 종전대로 아무 것도 차단하지 않는다."""
        items = [{"clause_id": "x", "suggested_rewrite": "콘텐츠 검수 기준을 명시한다."}]
        report = enforce_contract_scope(items, contract_type_code="content_production_service")
        self.assertFalse(report["policy_applied"])
        self.assertEqual(len(items), 1)

    def test_blocked_domain_detector_covers_every_reported_leak(self) -> None:
        for phrase in (
            "콘텐츠 검수 기준", "광고 매체 사용권", "SNS에 게재", "모델 초상권",
            "촬영 장소", "음원 및 효과음", "포트폴리오 활용",
            "저작재산권을 양도한다", "대금 지급 조건", "납품 검수", "SLA 미준수",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(find_blocked_domain_hits(phrase, NDA_CODE))

    # ── 항목 1: Current Contract vs Future Transaction ──────────────────────
    def test_future_transaction_terms_are_blocked_but_reservations_are_not(self) -> None:
        intruding = "개발비는 총 1억원으로 하고 납기는 6개월로 한다."
        self.assertTrue(find_future_transaction_intrusions(intruding, NDA_CODE))

        reserving = "개발비 및 납기는 본 계약에서 정하지 아니하고 후속 개발계약에서 정한다."
        self.assertEqual(find_future_transaction_intrusions(reserving, NDA_CODE), [])

    # ── 항목 3: Clause Semantic Gate ────────────────────────────────────────
    def test_semantic_mismatch_finding_is_deleted_not_merely_flagged(self) -> None:
        items = [
            {
                # NDA 무보증 조항 → 광고콘텐츠 저작권 이전
                "clause_id": "bad_warranty",
                "original_text": "“정보제공자”는 “비밀정보”의 정확성에 대하여 어떠한 보증도 하지 아니한다.",
                "suggested_rewrite": "제작된 광고 콘텐츠의 저작재산권은 갑에게 양도한다.",
            },
            {
                "clause_id": "good_confidentiality",
                "original_text": "“정보수령자”는 “비밀정보”를 제3자에게 누설하여서는 아니된다.",
                "suggested_rewrite": "“정보수령자”는 “비밀정보”를 제3자에게 제공, 공개, 누설할 수 없다.",
            },
        ]
        report = enforce_clause_semantic_gate(items, contract_type_code=NDA_CODE)
        self.assertEqual([cr["clause_id"] for cr in items], ["good_confidentiality"])
        self.assertEqual(len(report["mismatches"]), 1)
        self.assertEqual(report["removed_count"], 1)

    def test_semantic_gate_exempts_deterministic_rule_findings(self) -> None:
        """redline의 본질은 원문의 법률효과를 바꾸는 것이므로, 원문 문언을
        정규식으로 직접 확인한 결정론적 rule은 효과가 달라져도 삭제하지 않는다
        (퍼시스–웹젠 NDA 골든 테스트 회귀 방지)."""
        items = [{
            "clause_id": "clr_ethics_morality_termination_waiver_cluster",
            "is_common_legal_risk": True,
            "original_text": "품위를 유지하여야 하며 이를 위반한 경우 손해배상 청구를 하지 않는다.",
            "suggested_rewrite": "본 조 위반을 이유로 한 청구권을 포기하는 것으로 해석되지 아니한다.",
        }]
        report = enforce_clause_semantic_gate(items, contract_type_code=NDA_CODE)
        self.assertEqual(len(items), 1)
        self.assertEqual(report["mismatches"], [])

    def test_semantic_gate_ignores_findings_without_a_proposed_revision(self) -> None:
        """수정문안이 없는 user_focus 표식 항목은 mismatch 판정 대상이 아니다."""
        items = [{
            "clause_id": "KR-7",
            "original_text": "“정보수령자”는 “비밀정보”를 반환하거나 폐기하여야 한다.",
            "rewrite_reason": "사용자 중점 이슈: 개인정보/처리위탁/재위탁/침해사고",
            "suggested_rewrite": None,
        }]
        enforce_clause_semantic_gate(items, contract_type_code=NDA_CODE)
        self.assertEqual(len(items), 1)

    # ── 항목 9: Invalid Clause Reference ────────────────────────────────────
    def test_finding_on_nonexistent_article_is_deleted(self) -> None:
        items = [
            {"clause_id": "ghost", "display_path": "제14조", "clause_title": "제14조 [광고 집행 중단]"},
            {"clause_id": "real", "display_path": "제13조", "clause_title": "제13조 [준거법]"},
        ]
        report = enforce_valid_clause_references(items, self.clauses, contract_type_code=NDA_CODE)
        self.assertEqual([cr["clause_id"] for cr in items], ["real"])
        self.assertEqual(report["invalid_references"][0]["invalid_articles"], ["제14조"])

    def test_new_clause_after_last_article_is_a_valid_reference(self) -> None:
        """제13조까지인 계약에서 "제13조 뒤에 제14조 신설"은 유효한 참조다."""
        items = [{
            "clause_id": "new",
            "display_path": "",
            "clause_title": "[신설 권고]",
            "redline_instruction": {"edit_location": "제13조 뒤에 제14조 신설", "edit_type": "new_clause"},
        }]
        enforce_valid_clause_references(items, self.clauses, contract_type_code=NDA_CODE)
        self.assertEqual(len(items), 1)

    # ── 항목 11: Golden Acceptance ──────────────────────────────────────────
    def test_all_golden_issues_are_reviewed(self) -> None:
        ff = self.bundle.meta["final_findings"]
        found = {i["clause_id"] for i in ff["high_issues"] + ff["medium_issues"]}
        for clause_id in GOLDEN_CLAUSE_IDS:
            with self.subTest(clause_id=clause_id):
                self.assertIn(clause_id, found)

    def test_no_forbidden_content_production_terms_in_output(self) -> None:
        blob = json.dumps(self.bundle.meta["final_findings"], ensure_ascii=False)
        for term in FORBIDDEN_TERMS:
            with self.subTest(term=term):
                self.assertNotIn(term, blob)

    def test_review_is_not_failed(self) -> None:
        self.assertIsNone(self.bundle.meta.get("review_status"))

    # ── 항목 5·6·7·8: 조항 앵커 정확성 ──────────────────────────────────────
    def test_background_and_foreground_ip_are_separated(self) -> None:
        by_id = {r["clause_id"]: r for r in self.bundle.clause_results if isinstance(r, dict)}
        background = by_id["nda_improvement_ip_assigned_to_discloser"]
        self.assertEqual(background["severity"], "HIGH")
        self.assertIn("제8조", background["display_path"])

        foreground = by_id["nda_foreground_ip_not_reserved"]
        self.assertEqual(foreground["redline_instruction"]["edit_type"], "new_clause")
        # NDA에서 최종 귀속을 임의로 정하지 않고 후속 개발계약으로 유보한다.
        self.assertIn("별도로 체결하는 개발계약에서 정한다", foreground["suggested_rewrite"])

    def test_personal_data_rule_never_replaces_an_existing_clause(self) -> None:
        by_id = {r["clause_id"]: r for r in self.bundle.clause_results if isinstance(r, dict)}
        pd = by_id["nda_personal_data_boundary_missing"]
        self.assertEqual(pd["redline_instruction"]["edit_type"], "new_clause")

    def test_third_party_disclosure_is_not_anchored_on_the_assignment_clause(self) -> None:
        """항목 8 — 제3자 제공 범위는 비밀정보 제공 조항에서 다뤄야 하고,
        권리·의무의 양도 금지 조항을 수정해 해결하지 않는다."""
        by_id = {r["clause_id"]: r for r in self.bundle.clause_results if isinstance(r, dict)}
        rule = by_id["nda_third_party_recipient_scope"]
        assignment_articles = {
            str(getattr(c, "article_number", "") or "")
            for c in self.clauses
            if "양도" in str(getattr(c, "title", "") or "")
        }
        self.assertTrue(assignment_articles, "픽스처에 양도금지 조항이 있어야 한다")
        self.assertNotIn(str(rule["article_number"]), assignment_articles)

    # ── 항목 10: Redline 완성도 ─────────────────────────────────────────────
    def test_every_finding_has_a_complete_redline_instruction(self) -> None:
        ff = self.bundle.meta["final_findings"]
        for issue in ff["high_issues"] + ff["medium_issues"]:
            with self.subTest(clause_id=issue["clause_id"]):
                ri = issue.get("redline_instruction")
                self.assertIsInstance(ri, dict)
                self.assertTrue(ri["edit_location"].strip())
                self.assertNotIn("위치 확인 필요", ri["edit_location"])
                self.assertTrue(ri["final_clause_text"].strip())
                self.assertTrue(ri["reason"].strip())

    # ── 항목 2: mandatory_review_issues ─────────────────────────────────────
    def test_every_mandatory_issue_is_answered_with_an_allowed_verdict(self) -> None:
        answers = self.bundle.meta["mandatory_review_issues"]
        self.assertEqual(len(answers), 11)
        for a in answers:
            with self.subTest(code=a["code"]):
                self.assertIn(a["verdict"], VERDICTS)

    def test_deferred_issues_are_answered_as_separate_agreement(self) -> None:
        answers = {a["code"]: a["verdict"] for a in self.bundle.meta["mandatory_review_issues"]}
        self.assertEqual(answers["future_development_results"], "별도계약 필요")
        self.assertEqual(answers["personal_sensitive_data"], "별도계약 필요")

    def test_unanswered_issue_triggers_user_scope_failure(self) -> None:
        issues = derive_mandatory_review_issues(contract_type_code=NDA_CODE, review_focus=None)
        answers = answer_mandatory_review_issues(issues, clause_results=[], full_text="")
        # 계약 원문도 finding도 없으면 모든 쟁점이 기본값으로 답변된다 —
        # 판정값 자체는 항상 허용 집합 안에 있어야 한다.
        for a in answers:
            self.assertIn(a["verdict"], VERDICTS)
        # 허용되지 않은 판정값은 미답변으로 잡힌다.
        from runtime.review.mandatory_review_issues import check_all_issues_answered
        self.assertEqual(
            check_all_issues_answered([{"code": "x", "verdict": ""}]), ["x"],
        )

    # ── NDA 룰 자체의 게이팅 ────────────────────────────────────────────────
    def test_nda_rules_do_not_run_for_other_contract_types(self) -> None:
        out: list[dict] = []
        apply_nda_scope_rules(out, self.text, self.clauses, contract_type_code="dealer_agency")
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
