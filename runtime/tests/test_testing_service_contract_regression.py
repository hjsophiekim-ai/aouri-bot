"""Regression tests for the FITI 시험분석약정서 misclassification incident.

Background (2026-08-27): a 시디즈-FITI시험연구원 시험분석 약정서 (a testing/
inspection service agreement — 시디즈 is the party requesting testing, FITI is
the testing lab) was misclassified as an "AI 검색·마케팅 서비스 계약" because
the word "광고" appeared once, inside an incidental usage-restriction clause
("시험성적서를 광고에 사용하지 말 것"). That single misclassification cascaded
through several contract-type-agnostic injector functions and produced a
review full of boilerplate that has nothing to do with the actual contract:
  - "[공급자 보호]" 검수/반품/A/S/위험이전/설치환경/주문취소/이행유보권 항목
    (물품공급 계약 전용 체크리스트, _apply_supplier_product_checklist)
  - "[시디즈 위탁자 보호]" CI/SI 위반 즉시해지 + 위약벌 조항
    (_apply_sidiz_position_strategy, 계약유형 게이트가 아예 없었음)
  - "[수정 제안 — 제3자 권리 침해 보증]" IP/저작권 보증 조항
    (_apply_advisory_ip_review, "용역" 키워드만으로 발동)
  - "원문" 인용이 제8조/제10조/제12조 문장을 뒤섞어 존재하지 않는 문장을 인용
  - "문제점" 필드에 "사용자 중점 이슈: 구상권/소송비용 전가" 같은 내부 카테고리
    라벨이 설명 없이 그대로 노출

These tests pin the fix: contract_classifier now recognises
"testing_inspection_service" as its own type, the three injector functions
are hard-blocked for non-matching contract classes, and a final self-check
backstop strips anything that slips through regardless of which upstream
function caused it.
"""
from __future__ import annotations

import unittest
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fiti_testing_service_agreement.txt"

_FORBIDDEN_MARKERS = [
    # 반품
    "반품이 불가", "반품 요청서",
    # A/S
    "무상 A/S 대상", "A/S 제외",
    # 설치환경
    "설치 환경 요건",
    # 주문제작 취소
    "주문제작 공정", "주문제작 또는 설치가 완료된",
    # 물품 위험이전
    "위험은 공급자가", "위험이전 시점",
    # 오픈소스
    "오픈소스", "오픈소스 라이선스",
    # CI/SI 위약벌
    "CI/SI 가이드라인", "브랜드를 훼손", "위약벌을",
    # 콘텐츠/IP 결과물 보증
    "제3자의 저작권", "결과물 소유권", "저작재산권",
    "검수 완료 간주", "이행유보권",
    "sppc_", "MI-001", "MI-002", "MI-003", "MI-004", "MR-001", "MR-005",
]


class ContractClassifierTest(unittest.TestCase):
    """The classifier must recognise the testing-service type directly,
    not fall through to a marketing/dealer/product-supply guess."""

    def setUp(self) -> None:
        self.text = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_classified_as_testing_inspection_service(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(entity="시디즈", contract_type="", text=self.text)
        self.assertEqual(profile.contract_type, "testing_inspection_service")
        self.assertNotEqual(profile.contract_type, "ai_search_marketing")
        self.assertGreaterEqual(profile.confidence, 0.75)

    def test_our_role_is_service_recipient_not_supplier(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        profile = classify_contract_detailed(entity="시디즈", contract_type="", text=self.text)
        self.assertEqual(profile.our_role_bucket, "service_recipient")
        self.assertNotIn(profile.our_role_bucket, ("supplier", "contractor"))

    def test_single_incidental_ad_keyword_does_not_trigger_marketing(self) -> None:
        # The exact incidental phrase that caused the original misclassification.
        from runtime.review.contract_classifier import classify_contract_detailed

        text = "위탁자는 수탁자의 사전 서면동의 없이 시험성적서를 광고 ㆍ판촉 활동에 사용하여서는 아니 된다."
        profile = classify_contract_detailed(entity="시디즈", contract_type="", text=text)
        self.assertNotEqual(profile.contract_type, "ai_search_marketing")

    def test_incidental_dealer_keyword_anywhere_in_document_does_not_veto_testing_service(self) -> None:
        # Regression (2026-08-28, real-world upload): a real FITI-style PDF
        # can incidentally mention "대리점" once, far from any dealer-contract
        # context (e.g. a miscellaneous clause disclaiming that a test result
        # doesn't endorse resale through 대리점/유통 channels). A bare
        # whole-document keyword scan for "대리점" used to veto the otherwise
        # unambiguous testing_inspection_service classification and misroute
        # the whole review into consignment/dealer rule engines — which then
        # fired 기술자료/소스코드/안전 rules that have nothing to do with a
        # testing/inspection contract. has_testing_strong signals (시험연구원/
        # 시험기관/시험성적서 등) must win regardless of an incidental hit.
        from runtime.review.contract_classifier import classify_contract_detailed

        text = self.text + "\n제15조(기타) 본 시험성적서는 대리점을 통한 재판매를 보증하지 아니한다."
        profile = classify_contract_detailed(entity="시디즈", contract_type="", text=text)
        self.assertEqual(profile.contract_type, "testing_inspection_service")
        self.assertNotEqual(profile.contract_type, "consignment_sales_agency")

    def test_answers_override_low_confidence_classification(self) -> None:
        from runtime.review.contract_classifier import classify_contract_detailed

        ambiguous_text = "본 계약은 당사자 간 협력을 위해 체결한다. 갑과 을은 성실히 이행한다."
        baseline = classify_contract_detailed(entity="시디즈", contract_type="", text=ambiguous_text)
        self.assertLess(baseline.confidence, 0.75)

        confirmed = classify_contract_detailed(
            entity="시디즈", contract_type="", text=ambiguous_text,
            answers={
                "Q-TYPE-001-contract-nature": "testing_inspection",
                "Q-ROLE-001-our-position": "we_are_service_recipient",
            },
        )
        self.assertEqual(confirmed.contract_type, "testing_inspection_service")
        self.assertEqual(confirmed.our_role_bucket, "service_recipient")
        self.assertGreaterEqual(confirmed.confidence, 0.9)


class TemplateRecommendationNoMatchTest(unittest.TestCase):
    """Regression: a testing/inspection contract must never get a dealer or
    furniture-manufacturing subcontract template recommended.

    Two separate bugs produced this: (1) suggest_template_ids() used to fall
    back to whatever standard template sorted first alphabetically when
    nothing matched (가구제조업종 표준 하도급계약서.docx), and (2) "위탁" was
    listed as a 재판매대리점 template trigger keyword — far too generic, since
    it also appears in "위탁시험"/"위탁분석"/"위탁가공" style contract-type
    descriptions that have nothing to do with a dealer/distribution contract."""

    def test_wide_area_test_no_longer_matches_dealer_template_via_witak_keyword(self) -> None:
        from runtime.draft.service import suggest_template_ids

        hits = suggest_template_ids("시험위탁계약")
        self.assertNotIn("사내표준 재판매대리점 약정서.docx", hits)

    def test_real_dealer_contract_type_still_matches_dealer_template(self) -> None:
        # The keyword narrowing must not silently break legitimate matches.
        from runtime.draft.service import suggest_template_ids

        hits = suggest_template_ids("대리점 판매계약")
        self.assertIn("사내표준 재판매대리점 약정서.docx", hits)

    def test_no_match_returns_empty_not_a_blind_fallback(self) -> None:
        from runtime.draft.service import suggest_template_ids

        hits = suggest_template_ids("시험분석 성적서 발급")
        self.assertEqual(hits, [])


class PipelineNoOutOfScopeInjectionTest(unittest.TestCase):
    """End-to-end: build_clause_level_result on the FITI fixture must not
    inject product-supply / CI-SI / dealer-mandatory boilerplate."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        from runtime.review.clause_level import build_clause_level_result

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        cls.bundle = build_clause_level_result(
            service=service,
            entity="시디즈",
            contract_type="",
            text=text,
            filename="시디즈_FITI_시험분석약정서.pdf",
            answers=None,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )

    def test_contract_class_is_testing_service(self) -> None:
        self.assertEqual(self.bundle.meta.get("contract_class"), "testing_service")

    def test_no_forbidden_markers_anywhere_in_output(self) -> None:
        blob = str(self.bundle.clause_results) + str(self.bundle.meta)
        for marker in _FORBIDDEN_MARKERS:
            self.assertNotIn(marker, blob, f"forbidden out-of-scope marker leaked into output: {marker!r}")

    def test_no_out_of_scope_clause_ids(self) -> None:
        for cr in self.bundle.clause_results:
            if not isinstance(cr, dict):
                continue
            cid = str(cr.get("clause_id") or "")
            self.assertFalse(cid.startswith("sppc_"), f"sppc_ (product-supply) rule fired: {cid}")
            self.assertFalse(cid.startswith("MI-"), f"dealer mandatory issue fired: {cid}")
            self.assertFalse(cid.startswith("MR-"), f"dealer rental mandatory issue fired: {cid}")

    def test_no_safety_or_subcontract_rules_leak_via_text_expansion(self) -> None:
        # Regression: the fixture's 제3조④ ("시료를 ... 안전한 상태로 제공")
        # contains the bare keyword "안전", which query_service.py's
        # whole-document TRIGGER_MAP expansion (additional_contract_types_by_text)
        # used to pull in ACT-010/RISK-003 (안전/산업안전/중대재해) and the
        # sibling 하도급/기술자료 rules (ACT-007/008, RISK-004/005) — none of
        # which have anything to do with a testing/inspection service
        # agreement. These must be HARD BLOCKed for contract_class ==
        # "testing_service" regardless of how they entered the rule set.
        _OUT_OF_SCOPE_IDS = {"ACT-007", "ACT-008", "ACT-010", "RISK-003", "RISK-004", "RISK-005"}
        matched_ids = {r.get("rule_id") for r in self.bundle.review.get("matched_rules", []) if isinstance(r, dict)}
        checklist_ids = {r.get("rule_id") for r in self.bundle.review.get("checklist_rules", []) if isinstance(r, dict)}
        self.assertFalse(matched_ids & _OUT_OF_SCOPE_IDS, f"out-of-scope rule leaked into matched_rules: {matched_ids & _OUT_OF_SCOPE_IDS}")
        self.assertFalse(checklist_ids & _OUT_OF_SCOPE_IDS, f"out-of-scope rule leaked into checklist_rules: {checklist_ids & _OUT_OF_SCOPE_IDS}")

    def test_self_check_report_present_and_clean(self) -> None:
        report = self.bundle.meta.get("self_check")
        self.assertIsInstance(report, dict)
        self.assertEqual(report.get("contract_type_code"), "testing_inspection_service")
        self.assertEqual(report.get("scope_violations_stripped"), [])
        self.assertTrue(report.get("passed"))

    def test_no_false_negative_zero_findings(self) -> None:
        # This was the actual regression: HARD BLOCK removed the noise but
        # also (via an unrelated pre-existing bug in the priority engine)
        # suppressed every real finding down to HIGH=0/MEDIUM=0. Common
        # legal-risk rules (Layer 1) must now produce real findings.
        tier_counts = self.bundle.meta.get("tier_counts") or {}
        self.assertGreater(tier_counts.get("must", 0), 0, "expected at least one HIGH finding")
        self.assertGreater(tier_counts.get("medium", 0), 0, "expected at least one MEDIUM finding")
        report = self.bundle.meta.get("self_check")
        self.assertFalse(report.get("zero_findings_but_risk_language_present"))
        self.assertEqual(report.get("review_status"), "OK")

    def _clause_ids(self) -> set[str]:
        return {str(cr.get("clause_id") or "") for cr in self.bundle.clause_results if isinstance(cr, dict)}

    def _cr_by_id(self, clause_id: str) -> dict:
        for cr in self.bundle.clause_results:
            if isinstance(cr, dict) and cr.get("clause_id") == clause_id:
                return cr
        raise AssertionError(f"clause_id {clause_id!r} not found among findings: {sorted(self._clause_ids())}")

    def test_article6_4_and_11_1_fault_blind_exemption_is_high(self) -> None:
        # 제6조④ / 제11조① — 수탁자 귀책 여부와 무관한 전면 면책 -> HIGH
        cr = self._cr_by_id("clr_fault_blind_exemption")
        self.assertEqual(cr.get("risk_tier"), "HIGH")

    def test_article6_5_and_11_2_unlimited_recourse_is_high_or_medium(self) -> None:
        # 제6조⑤ / 제11조② — 배상액·소송비용/변호사보수 구상 -> HIGH 또는 MEDIUM
        cr = self._cr_by_id("clr_unlimited_recourse_with_legal_costs")
        self.assertIn(cr.get("risk_tier"), ("HIGH", "MEDIUM"))

    def test_article5_other_lab_notice_is_medium(self) -> None:
        # 제5조 — 타 시험기관과 유사 약정 체결 시 사전통보 -> MEDIUM
        cr = self._cr_by_id("clr_competitor_restriction_notice")
        self.assertEqual(cr.get("risk_tier"), "MEDIUM")

    def test_article6_2_advertising_consent_is_medium(self) -> None:
        # 제6조② — 성적서 광고·판촉 사전서면동의 -> MEDIUM
        cr = self._cr_by_id("tsr_certificate_usage_restriction")
        self.assertEqual(cr.get("risk_tier"), "MEDIUM")

    def test_article12_termination_right_vs_2yr_term_is_medium(self) -> None:
        # 제12조 — 2년 계약인데 편의해지권 없음 -> MEDIUM
        cr = self._cr_by_id("clr_termination_right_restricted")
        self.assertEqual(cr.get("risk_tier"), "MEDIUM")

    def test_article14_1_standard_terms_incorporation_is_high_or_medium(self) -> None:
        # 제14조① — FITI 표준시험약관·규정 포괄 적용 -> HIGH 또는 MEDIUM
        cr = self._cr_by_id("clr_external_terms_incorporation")
        self.assertIn(cr.get("risk_tier"), ("HIGH", "MEDIUM"))

    def test_article4_4_payment_guarantee_misreading_flagged(self) -> None:
        # 제4조④ — 협력사 미수금 관련 "적극 협조" -> 지급보증 오인 가능성 검토
        cr = self._cr_by_id("clr_payment_guarantee_ambiguous")
        self.assertIn(cr.get("risk_tier"), ("HIGH", "MEDIUM"))

    def test_article8_5_data_reuse_flagged(self) -> None:
        # 제8조⑤ — FITI의 자료 연구·분석 활용 -> 데이터 활용 리스크 검토
        cr = self._cr_by_id("tsr_data_reuse_by_lab")
        self.assertIn(cr.get("risk_tier"), ("HIGH", "MEDIUM"))

    def test_self_check_flags_real_exculpatory_clause_as_uncovered_by_catalog(self) -> None:
        # The user_focus priority-risk catalog's "exculpatory_clause" category
        # keyword-matches this contract's text but the actual finding lives
        # under a differently-named clause_id (clr_fault_blind_exemption) —
        # self-check's coverage scan should still list it so a reviewer can
        # cross-check the catalog against the concrete findings.
        report = self.bundle.meta.get("self_check")
        self.assertIn("exculpatory_clause", report.get("priority_risk_present_but_unflagged", []))


class ReviewFocusSurfacesEvenWithoutRuleDbMatchTest(unittest.TestCase):
    """Regression: a clause matching the user's stated review_focus keywords
    must appear in the output even when no JSON rule in the rule DB happens
    to trigger on it — a clause used to be silently dropped from
    revision.py's per-clause loop entirely (`if not clause_issues: continue`)
    whenever no rule matched, regardless of review_focus."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService
        from runtime.review.clause_level import build_clause_level_result

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        cls.bundle = build_clause_level_result(
            service=service,
            entity="시디즈",
            contract_type="",
            text=text,
            filename="시디즈_FITI_시험분석약정서.pdf",
            answers=None,
            review_focus="면책 조항과 구상권 범위를 중점적으로 봐주세요",
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )

    def test_focus_matched_clauses_are_surfaced(self) -> None:
        hit_ids = {
            str(cr.get("clause_id") or "")
            for cr in self.bundle.clause_results
            if isinstance(cr, dict) and cr.get("user_focus_hit")
        }
        self.assertTrue(hit_ids, "no clause was tagged user_focus_hit for a review_focus that clearly matches 제6조/제11조")

    def test_focus_matched_clause_is_not_silently_low(self) -> None:
        # At least one of the focus-matched clauses must be visible at
        # MEDIUM+ — LOW-only findings are excluded from default output, which
        # would mean the user's stated focus area is effectively invisible.
        promoted = [
            cr for cr in self.bundle.clause_results
            if isinstance(cr, dict) and cr.get("user_focus_hit")
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
        ]
        self.assertTrue(promoted, "review_focus-matched clause(s) were left at LOW and effectively hidden")


class HallucinationGuardBackstopTest(unittest.TestCase):
    """Direct unit tests on the new phrase lists — belt-and-suspenders even
    if a future injector function reintroduces the bug."""

    def test_product_supply_phrase_blocked_for_testing_service(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        text = "구매자는 물품 수령 후 [ ]영업일 이내에 검수를 완료하여야 하며, 검수 완료 간주 규정을 둔다."
        result = check_revision_text(text, contract_type_code="testing_inspection_service")
        self.assertFalse(result.is_clean)
        self.assertTrue(any("product_supply_phrase" in v for v in result.violations))

    def test_ci_brand_phrase_blocked_for_testing_service(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        text = "수탁자가 CI/SI 가이드라인을 위반한 경우 위약벌을 갑에게 지급한다."
        result = check_revision_text(text, contract_type_code="testing_inspection_service")
        self.assertFalse(result.is_clean)
        self.assertTrue(any("ci_brand_phrase" in v for v in result.violations))

    def test_product_supply_phrase_allowed_for_purchase_supply(self) -> None:
        from runtime.review.hallucination_guard import check_revision_text

        text = "구매자는 물품 수령 후 검수 완료 간주 규정에 동의한다."
        result = check_revision_text(text, contract_type_code="purchase_supply")
        self.assertTrue(result.is_clean)


class TopicMismatchSemanticValidationTest(unittest.TestCase):
    """Regression (2026-08-28, real-world report): 제14조② (dispute-jurisdiction
    clause, "본 약정과 관련된 분쟁은 서울중앙지방법원을 전속관할로 한다") got a
    "경영간섭"/인사권 (management-interference) rewrite_reason meant for a
    completely different (dealer-domain) clause — a wrong clause_id-to-
    reasoning pairing from a misrouted rule/AI merge.

    self_check flags (does not auto-strip) a HIGH/MEDIUM finding whose
    reasoning shares no vocabulary with its own quoted 원문. An earlier
    version of this fix auto-stripped HIGH matches on this signal, but a real
    end-to-end run against the FITI fixture with AI enabled showed the bare
    token-overlap check (even with common function words removed) firing on
    several of FITI's own genuine, on-topic findings — AI-written
    rewrite_reason text routinely paraphrases the clause rather than
    repeating its exact nouns, so "zero overlap" is not a reliable enough
    signal to delete content on. Flagging stays; auto-stripping doesn't."""

    def test_zero_vocabulary_overlap_is_flagged_not_stripped(self) -> None:
        from runtime.review.self_check import run_self_check

        clause_results = [
            {
                "clause_id": "KR-14-p2",
                "risk_tier": "HIGH",
                "must_fix": True,
                "approval_required": True,
                "high_risk": True,
                "original_text": "본 약정과 관련된 분쟁은 서울중앙지방법원을 전속관할로 한다.",
                # Deliberately avoids any hallucination_guard banned phrase
                # (대리점/판매대리점/CI-SI/product-supply/결과물/산출물 등) so
                # this test isolates the topic-mismatch check (item 4) rather
                # than the pre-existing phrase-based backstop (item 3), which
                # would otherwise strip it first for an unrelated reason.
                "rewrite_reason": "안전관리자를 지정하고 중대재해 발생 시 산업안전보건법에 따른 안전보건교육을 실시하여야 한다.",
                "suggested_rewrite": "현장에 안전관리자를 상시 배치하고 중대재해 예방 조치를 이행하여야 한다.",
            }
        ]
        report = run_self_check(
            clause_results=clause_results,
            contract_type_code="testing_inspection_service",
            contract_class="testing_service",
            our_role_bucket="service_recipient",
            confidence=0.9,
            full_text="",
        )
        cr = clause_results[0]
        self.assertIn("KR-14-p2", report.get("topic_mismatch_clause_ids", []))
        self.assertTrue(cr.get("topic_mismatch_risk"))
        # Flagged for reviewer visibility, but never auto-deleted.
        self.assertIsNotNone(cr["suggested_rewrite"])
        self.assertEqual(cr["risk_tier"], "HIGH")
        self.assertTrue(cr["approval_required"])

    def test_generic_stopwords_alone_do_not_count_as_overlap(self) -> None:
        # Two unrelated sentences sharing only generic sentence-final verbs
        # ("~한다") must still be flagged as mismatched — the stopword filter
        # in _tokens() exists so this class of trivial overlap doesn't mask
        # a real mismatch.
        from runtime.review.self_check import run_self_check

        clause_results = [
            {
                "clause_id": "KR-14-p2",
                "risk_tier": "MEDIUM",
                "original_text": "본 약정과 관련된 분쟁은 서울중앙지방법원을 전속관할로 한다.",
                "rewrite_reason": "현장에 안전관리자를 상시 배치하여야 한다.",
                "suggested_rewrite": "안전관리자를 지정한다.",
            }
        ]
        report = run_self_check(
            clause_results=clause_results,
            contract_type_code="testing_inspection_service",
            contract_class="testing_service",
            our_role_bucket="service_recipient",
            confidence=0.9,
            full_text="",
        )
        self.assertIn("KR-14-p2", report.get("topic_mismatch_clause_ids", []))

    def test_real_topical_overlap_is_not_flagged(self) -> None:
        # Sanity check against false positives: a genuine on-topic finding
        # that repeats an exact content word from its own quoted 원문 must
        # not be flagged. (Korean inflection means even on-topic paraphrases
        # often share zero *exact* tokens — see the class docstring — so
        # this only proves the mechanism works when a word IS repeated
        # verbatim, not that it never false-positives on paraphrases.)
        from runtime.review.self_check import run_self_check

        clause_results = [
            {
                "clause_id": "KR-9-p1",
                "risk_tier": "MEDIUM",
                "original_text": "본 약정의 계약기간은 2년으로 한다.",
                "rewrite_reason": "계약기간은 2년으로 장기임에도 임의 해지권이 없어 위탁자가 구속될 위험이 있음.",
                "suggested_rewrite": "위탁자는 3개월 전 서면 통지로 해지할 수 있다.",
            }
        ]
        report = run_self_check(
            clause_results=clause_results,
            contract_type_code="testing_inspection_service",
            contract_class="testing_service",
            our_role_bucket="service_recipient",
            confidence=0.9,
            full_text="",
        )
        self.assertNotIn("KR-9-p1", report.get("topic_mismatch_clause_ids", []))


class LawCitationBackstopCoversAllFieldsTest(unittest.TestCase):
    """Regression: mandatory_issues.py / dealer_rental_service_rules.py write
    hardcoded statute article numbers (e.g. "대리점법 제6조 불이익 제공 금지")
    into `legal_business_reason`/`problem`/`proposed_revision`/`issue_title` —
    not just `rewrite_reason`/`suggested_rewrite`. self_check's backstop guard
    must scrub the article number regardless of which field it landed in,
    since we have no live 국가법령정보 API/DB to confirm any specific number."""

    def test_legal_business_reason_field_is_scrubbed(self) -> None:
        from runtime.review.self_check import run_self_check

        clause_results = [
            {
                "clause_id": "MI-001",
                "risk_tier": "HIGH",
                "legal_business_reason": "대리점법 제6조 불이익 제공 금지 위반 소지가 있음.",
                "problem": "대리점법 제10조 위반 소지",
                "proposed_revision": "하도급법 제12조의3에 따라 수정 필요",
                "issue_title": "대리점법 제18조 위반 이슈",
                "why_matters": "대리점법 제6조 불이익 제공 금지 위반 가능성이 있습니다.",
                "worst_case_scenario": "대리점법 제6조 불이익 제공 금지 위반 가능성.",
                "negotiation_strategy": "민법 제397조의2 및 약관규제법상 무효 소지",
                # A field name the scrub cannot know about ahead of time —
                # exclusion-based scrubbing must still catch it.
                "some_future_field_no_one_added_to_a_list": "하도급법 제11조 위반 소지",
            }
        ]
        run_self_check(
            clause_results=clause_results,
            contract_type_code="consignment_dealer",
            contract_class="dealer",
            our_role_bucket="supplier",
            confidence=0.9,
            full_text="",
        )
        cr = clause_results[0]
        for field in (
            "legal_business_reason", "problem", "proposed_revision", "issue_title",
            "why_matters", "worst_case_scenario", "negotiation_strategy",
            "some_future_field_no_one_added_to_a_list",
        ):
            self.assertNotRegex(
                cr[field], r"제\d+조", f"unverified law article number survived in {field!r}: {cr[field]!r}"
            )
            self.assertIn("법", cr[field], f"law name itself should be preserved in {field!r}")

    def test_original_text_is_never_rewritten_even_if_it_quotes_a_statute(self) -> None:
        # original_text/context_text/clause_title must reproduce the source
        # document verbatim — even if the contract itself quotes an external
        # statute with an article number, that is real original_text content,
        # not a system-generated (and therefore unverifiable) citation.
        from runtime.review.self_check import run_self_check

        verbatim = "본 계약은 개인정보보호법 제17조에 따라 개인정보를 제3자에게 제공한다."
        clause_results = [
            {
                "clause_id": "KR-9",
                "risk_tier": "LOW",
                "original_text": verbatim,
                "context_text": verbatim,
                "clause_title": "제9조(개인정보보호법 제17조 근거 제공)",
            }
        ]
        run_self_check(
            clause_results=clause_results,
            contract_type_code="testing_inspection_service",
            contract_class="testing_service",
            our_role_bucket="service_recipient",
            confidence=0.9,
            full_text=verbatim,
        )
        cr = clause_results[0]
        self.assertEqual(cr["original_text"], verbatim)
        self.assertEqual(cr["context_text"], verbatim)
        self.assertIn("제17조", cr["clause_title"])


class PageMarkerSegmentationTest(unittest.TestCase):
    """text_extract.extract_text_from_pdf() prefixes every page with a
    "[페이지 N]" marker line so page boundaries survive into the joined
    document text. A real multi-page FITI-style PDF puts a page break in the
    middle of an article (e.g. 제6조 spans pages 3-4) — the marker line must
    never end up quoted inside a clause's original_text (it was never part of
    the actual contract), and it must never be mistaken for clause content
    that shifts a boundary."""

    def test_page_marker_stripped_from_clause_text(self) -> None:
        from runtime.review.clause_extraction import extract_clauses

        text = (
            "제1조(목적) 이 계약은 시험분석 업무를 목적으로 한다.\n"
            "[페이지 1]\n\n"
            "제2조(비밀유지) 양 당사자는 상대방으로부터 제공받은 자료를\n"
            "[페이지 2]\n\n"
            "제3자에게 제공하여서는 아니 된다.\n"
            "제3조(계약기간) 본 계약의 유효기간은 2년으로 한다.\n"
        )
        clauses, _report = extract_clauses(text)
        for c in clauses:
            self.assertNotIn("[페이지", c.text, f"page marker leaked into clause {c.clause_id} text")

    def test_page_break_mid_article_does_not_merge_into_next_article(self) -> None:
        from runtime.review.clause_extraction import extract_clauses

        text = (
            "제5조(상호협력) 위탁자는 다음 각 호의 사항을 수탁자에게 협조한다.\n"
            "[페이지 3]\n\n"
            "1. 수탁자 이외의 자와 유사한 약정을 체결하고자 할 경우 사전 통보한다.\n"
            "제6조(시험성적서) 위탁자는 사전 서면동의 없이 시험성적서를 광고에 사용하여서는 아니 된다.\n"
        )
        clauses, _report = extract_clauses(text)
        by_article = {c.article_number: c for c in clauses if c.article_number}
        self.assertIn("5", by_article)
        self.assertIn("6", by_article)
        self.assertNotIn("시험성적서", by_article["5"].text, "제6조 content bled into 제5조")
        self.assertNotIn("상호협력", by_article["6"].text.replace(by_article["6"].title, ""))


class InlineParagraphOnArticleHeadingLineTest(unittest.TestCase):
    """Regression: when a 조문 heading and its first paragraph sit on the SAME
    physical line — "제14조(기타사항) ① 본 약정에 달리 정함이 없는 ..." (exactly
    how the FITI fixture's 제14조 is written) — the heading regex's trailing
    catch-all group used to swallow the whole "① ..." paragraph into the
    article's `title`, so it silently never became its own clause at all
    (not merged into a different article — just dropped from segmentation).
    """

    def test_paragraph_on_same_line_as_heading_is_still_segmented(self) -> None:
        from runtime.review.clause_extraction import extract_clauses

        text = (
            "제14조(기타사항) ① 본 약정에 달리 정함이 없는 사항에 대하여는 수탁자의 표준시험약관 및 규정을 적용한다.\n"
            "② 본 약정과 관련된 분쟁은 서울중앙지방법원을 전속관할로 한다.\n"
        )
        clauses, _report = extract_clauses(text)
        by_id = {c.clause_id: c for c in clauses}
        self.assertIn("KR-14-p1", by_id, f"paragraph ① was dropped; got only {sorted(by_id)}")
        self.assertIn("표준시험약관", by_id["KR-14-p1"].text)
        self.assertIn("KR-14-p2", by_id)
        self.assertIn("전속관할", by_id["KR-14-p2"].text)
        # ① text must not still be glued into the article's own title.
        for c in clauses:
            if c.article_number == "14":
                self.assertNotIn("표준시험약관", c.title)


class CommonLegalRiskQuoteNeverCrossesClauseBoundaryTest(unittest.TestCase):
    """Regression: common_legal_risk.py used to build its "원문" quote by
    windowing +/-N raw characters around a regex match over the WHOLE
    document string, with no awareness of clause/article boundaries. On the
    FITI fixture this produced quotes that mixed in a completely different
    clause's text: 제6조④'s "귀책사유 불문 면책" finding pulled in the start of
    제6조⑤'s "구상" text, and 제6조⑤'s own finding pulled in 제7조(양도) and
    제8조(비밀유지의무)'s headings. Now the quote is built from the already-
    confirmed segmentation (clauses), scoped first to a single leaf clause
    and, failing that, to a single article — so it can never contain another
    clause's/article's content."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_extraction import extract_clauses
        from runtime.review.common_legal_risk import _apply_common_legal_risk_rules

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        clauses, _report = extract_clauses(text)
        cls.clause_results: list = []
        _apply_common_legal_risk_rules(cls.clause_results, text, clauses)

    def _cr_by_id(self, clause_id: str) -> dict:
        for cr in self.clause_results:
            if cr.get("clause_id") == clause_id:
                return cr
        raise AssertionError(f"clause_id {clause_id!r} not found: {[c.get('clause_id') for c in self.clause_results]}")

    def test_article6_4_quote_does_not_bleed_into_article6_5(self) -> None:
        cr = self._cr_by_id("clr_fault_blind_exemption")
        self.assertNotIn("소송비용", cr["original_text"])
        self.assertNotIn("변호사보수", cr["original_text"])
        self.assertEqual(cr.get("article_number"), "6")

    def test_article6_5_quote_does_not_bleed_into_article7_or_8(self) -> None:
        cr = self._cr_by_id("clr_unlimited_recourse_with_legal_costs")
        self.assertNotIn("권리 의무의 양도", cr["original_text"])
        self.assertNotIn("비밀유지의무", cr["original_text"])
        self.assertEqual(cr.get("article_number"), "6")

    def test_article14_1_quote_is_clean_and_does_not_bleed_into_article14_2(self) -> None:
        cr = self._cr_by_id("clr_external_terms_incorporation")
        self.assertTrue(cr["original_text"].startswith("본 약정에 달리 정함이 없는"))
        self.assertNotIn("전속관할", cr["original_text"])
        self.assertNotIn("분쟁", cr["original_text"])
        self.assertEqual(cr.get("article_number"), "14")


if __name__ == "__main__":
    unittest.main()
