"""시니어 사내변호사 정리 패스 회귀테스트 (2026-09-08 지시 항목 1~5).

각 테스트는 사용자가 실제로 지적한 실패 케이스를 그대로 재현한다.
"""
from __future__ import annotations

import unittest

from runtime.review.senior_counsel_pass import (
    REVIEW_FAILED_DUPLICATE_FINDINGS,
    TOPIC_UNKNOWN,
    apply_high_severity_policy,
    check_no_duplicate_findings,
    check_no_overbroad_exculpation,
    classify_topic,
    merge_duplicate_findings,
    run_senior_counsel_pass,
    sanitize_liability_revisions,
)
from runtime.review.structure_summary_policy import (
    fields_for,
    fieldset_name,
    is_field_allowed,
    render_rows,
    stale_fields_present,
)


def _f(**kw):
    base = {
        "clause_id": kw.pop("clause_id", "c1"),
        "display_path": kw.pop("display_path", "제1조"),
        "article_number": kw.pop("article_number", ""),
        "risk_tier": kw.pop("risk_tier", "MEDIUM"),
        "issue_title": kw.pop("issue_title", ""),
        "clause_title": kw.pop("clause_title", ""),
        "rewrite_reason": kw.pop("rewrite_reason", ""),
        "suggested_rewrite": kw.pop("suggested_rewrite", ""),
    }
    base.update(kw)
    return base


# ═══════════════════════════════════════════════════════════════════════════
# 항목 2 — 중복 finding 자동 통합
# ═══════════════════════════════════════════════════════════════════════════

class DuplicateFindingMergeTest(unittest.TestCase):
    def test_article12_priority_of_agreements_duplicate_is_merged(self) -> None:
        """사용자가 지적한 실패: 제12조 후속계약 우선순위가 두 번 나왔다."""
        crs = [
            _f(clause_id="a", display_path="제12조", article_number="12",
               risk_tier="MEDIUM", issue_title="후속계약과 본 계약의 우선순위 불명확",
               suggested_rewrite="본 계약과 후속 계약이 상충하는 경우 후속 계약이 우선한다."),
            _f(clause_id="b", display_path="제12조 제2항", article_number="12",
               risk_tier="MEDIUM", issue_title="후속 계약 우선 적용 조항 부재",
               suggested_rewrite="후속계약이 우선하여 적용된다."),
        ]
        merged = merge_duplicate_findings(crs)
        self.assertEqual(len(merged), 1, merged)
        live = [c for c in crs if not c.get("dedup_suppressed")]
        self.assertEqual(len(live), 1)
        self.assertTrue(any(c.get("merged_into") for c in crs if c.get("dedup_suppressed")))
        self.assertEqual(check_no_duplicate_findings(crs), [])

    def test_different_topics_in_same_article_are_not_merged(self) -> None:
        """같은 조문이라도 다른 쟁점이면 병합하면 안 된다."""
        crs = [
            _f(clause_id="a", article_number="2", issue_title="비밀정보의 정의에 파생정보 누락"),
            _f(clause_id="b", article_number="2", issue_title="개인정보 처리 경계 미설정"),
        ]
        self.assertEqual(merge_duplicate_findings(crs), [])
        self.assertEqual(len([c for c in crs if not c.get("dedup_suppressed")]), 2)

    def test_shared_original_text_does_not_cause_wrong_merge(self) -> None:
        """같은 조문의 두 finding은 원문을 공유한다 — 그 원문으로 효과를
        추론하면 서로 다른 이슈가 하나로 병합된다."""
        shared = (
            "제2조 (비밀정보) 수령자는 비밀정보를 제3자에게 제공할 수 없으며, "
            "손해배상 및 가처분의 대상이 되고, 개인정보 처리에 관하여는 별도로 정한다."
        )
        crs = [
            _f(clause_id="a", article_number="2", original_text=shared,
               issue_title="범용 AI 모델 학습 제한 부재",
               rewrite_reason="제공 데이터를 범용 모델 학습에 이용할 수 있다"),
            _f(clause_id="b", article_number="2", original_text=shared,
               issue_title="개인정보·민감정보 처리 경계 미설정",
               rewrite_reason="음성정보 등 민감정보 처리 범위가 정해지지 않았다"),
        ]
        self.assertEqual(merge_duplicate_findings(crs), [])
        self.assertEqual(len([c for c in crs if not c.get("dedup_suppressed")]), 2)

    def test_identical_effect_tag_but_different_topic_is_not_merged(self) -> None:
        """NDA 조항은 대부분 legal effect 가 confidentiality 하나로만 추론된다.

        (조문+효과) 만으로 병합하면 제4조의 "범용 AI 학습 제한 부재"(HIGH)와
        "개인정보 처리 경계 미설정"이 하나로 뭉개져 사용자가 HIGH 로 원한
        이슈가 사라진다 — 2026-09-08 실제 회귀.
        """
        crs = [
            _f(clause_id="ai", article_number="4", risk_tier="HIGH",
               legal_effect_tags=["confidentiality"],
               issue_title="범용 AI 모델 학습·개선 및 타 프로젝트 활용 제한이 명시되어 있지 않음"),
            _f(clause_id="pd", article_number="4", risk_tier="HIGH",
               legal_effect_tags=["confidentiality"],
               issue_title="실제 이용자 개인정보 처리에 대한 별도 계약 유보 조항이 없음"),
            _f(clause_id="rs", article_number="4", risk_tier="MEDIUM",
               legal_effect_tags=["confidentiality"],
               issue_title="외부 협력업체에 대한 정보제공 범위가 불명확"),
        ]
        self.assertEqual(merge_duplicate_findings(crs), [])
        live = {c["clause_id"] for c in crs if not c.get("dedup_suppressed")}
        self.assertEqual(live, {"ai", "pd", "rs"})
        self.assertEqual(check_no_duplicate_findings(crs), [])

    def test_background_and_foreground_ip_are_separate_negotiation_items(self) -> None:
        """답변 시에는 서로 호환되지만(항목 1), 병합해서는 안 된다."""
        crs = [
            _f(clause_id="bg", article_number="8", legal_effect_tags=["confidentiality"],
               issue_title="개량기술·독자개발 성과가 제공자 승인 대상으로 포섭됨"),
            _f(clause_id="fg", article_number="8", legal_effect_tags=["confidentiality"],
               issue_title="향후 공동·추가 개발결과의 귀속이 후속 개발계약으로 유보되어 있지 않음"),
        ]
        self.assertEqual(merge_duplicate_findings(crs), [])
        self.assertEqual(len([c for c in crs if not c.get("dedup_suppressed")]), 2)

    def test_same_topic_different_articles_are_not_merged(self) -> None:
        crs = [
            _f(clause_id="a", article_number="4", issue_title="범용 AI 모델 학습 제한 부재"),
            _f(clause_id="b", article_number="8", issue_title="범용 모델 학습 동의 없음"),
        ]
        self.assertEqual(merge_duplicate_findings(crs), [])

    def test_user_cited_clause_is_never_merged_away(self) -> None:
        """사용자가 직접 인용한 조항의 finding 은 접히면 안 된다.

        제6조 제5항을 상위 제6조 finding 으로 병합해 버리면 그 인용이 최종
        출력에서 사라져 REVIEW_FAILED_USER_REQUEST_MISSING 이 된다 —
        2026-09-08 FITI 실제 회귀.
        """
        crs = [
            _f(clause_id="broad", display_path="제6조", article_number="6",
               issue_title="비밀유지기간 존속 규정 미비"),
            _f(clause_id="cited", display_path="제6조 제5항", article_number="6",
               issue_title="비밀유지기간 존속 조항 부재",
               is_mandatory_review_target=True),
        ]
        self.assertEqual(merge_duplicate_findings(crs), [])
        live = {c["clause_id"] for c in crs if not c.get("dedup_suppressed")}
        self.assertEqual(live, {"broad", "cited"})
        # 보호된 항목은 중복 게이트도 건드리지 않는다(다운로드가 막히면 안 된다).
        self.assertEqual(check_no_duplicate_findings(crs), [])

    def test_article_review_anchor_is_not_merged(self) -> None:
        crs = [
            _f(clause_id="anchor", article_number="3",
               issue_title="반환·폐기 규정 미비", article_review_anchor=True),
            _f(clause_id="item", article_number="3",
               issue_title="반환·폐기 및 백업 예외 누락"),
        ]
        self.assertEqual(merge_duplicate_findings(crs), [])

    def test_merge_keeps_the_more_complete_finding_as_primary(self) -> None:
        crs = [
            _f(clause_id="thin", article_number="7", risk_tier="MEDIUM",
               issue_title="반환·폐기 규정 미비", suggested_rewrite="폐기한다."),
            _f(clause_id="rich", article_number="7", risk_tier="HIGH",
               issue_title="반환·폐기 및 자동 백업 예외 누락",
               suggested_rewrite="수령자는 요청 시 즉시 반환 또는 폐기하고, "
                                 "자동 백업본은 기술적으로 삭제가 불가능한 범위에서 "
                                 "접근을 차단하고 보존기간 경과 후 삭제한다."),
        ]
        merge_duplicate_findings(crs)
        live = [c for c in crs if not c.get("dedup_suppressed")]
        self.assertEqual(len(live), 1)
        self.assertEqual(live[0]["clause_id"], "rich")

    def test_merge_is_idempotent(self) -> None:
        crs = [
            _f(clause_id="a", article_number="12", issue_title="후속계약 우선순위 불명확"),
            _f(clause_id="b", article_number="12", issue_title="후속 계약이 우선하여 적용"),
        ]
        first = merge_duplicate_findings(crs)
        second = merge_duplicate_findings(crs)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [], "두 번째 호출에서 다시 병합하면 멱등이 아니다")

    def test_low_findings_are_not_merged_or_gated(self) -> None:
        crs = [
            _f(clause_id="a", article_number="12", risk_tier="LOW", issue_title="후속계약 우선순위"),
            _f(clause_id="b", article_number="12", risk_tier="LOW", issue_title="후속계약 우선 적용"),
        ]
        self.assertEqual(merge_duplicate_findings(crs), [])
        self.assertEqual(check_no_duplicate_findings(crs), [])

    def test_gate_reports_residual_duplicates(self) -> None:
        """병합을 건너뛴 상태를 직접 만들어 게이트가 실제로 잡는지 확인."""
        crs = [
            _f(clause_id="a", article_number="12", issue_title="후속계약 우선순위 불명확"),
            _f(clause_id="b", article_number="12", issue_title="후속계약 우선 적용 부재"),
        ]
        residual = check_no_duplicate_findings(crs)
        self.assertTrue(residual, "게이트가 중복을 감지하지 못했다")


# ═══════════════════════════════════════════════════════════════════════════
# 항목 3 — HIGH 기준 강화
# ═══════════════════════════════════════════════════════════════════════════

class HighSeverityPolicyTest(unittest.TestCase):
    def test_independent_development_stays_high(self) -> None:
        cr = _f(risk_tier="HIGH",
                issue_title="독자 개발 정보가 상대방 비밀정보로 해석될 위험",
                rewrite_reason="독자 개발한 기술이 상대방의 권리로 귀속될 수 있다")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "HIGH")
        self.assertTrue(cr.get("high_severity_basis"))

    def test_background_ip_stays_high(self) -> None:
        cr = _f(risk_tier="HIGH",
                issue_title="Background IP 침해 위험",
                rewrite_reason="계약 전 보유 기술이 상대방 권리로 귀속될 수 있음")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_general_ai_training_stays_high(self) -> None:
        cr = _f(risk_tier="HIGH",
                issue_title="범용 AI 모델 학습에 제한 없음",
                rewrite_reason="제공 데이터를 범용 모델 학습에 제한 없이 이용 가능")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_other_project_use_stays_high(self) -> None:
        cr = _f(risk_tier="HIGH",
                issue_title="다른 고객 서비스 개선에 활용 가능",
                rewrite_reason="타 프로젝트에 활용될 수 있어 통제 불가")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_actual_personal_data_processing_stays_high(self) -> None:
        cr = _f(risk_tier="HIGH",
                issue_title="음성정보·수면정보 처리",
                rewrite_reason="민감정보를 별도 계약 없이 처리·국외 이전")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_injunction_boilerplate_is_demoted(self) -> None:
        """가처분 문구는 원칙적으로 MEDIUM."""
        cr = _f(risk_tier="HIGH",
                issue_title="가처분 등 보전처분 조항",
                rewrite_reason="가처분을 신청할 수 있다는 통상적 문구")
        demoted = apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "MEDIUM")
        self.assertEqual(cr["severity_demotion_reason"], "routine_clause:injunction_boilerplate")
        self.assertEqual(len(demoted), 1)

    def test_routine_no_warranty_is_demoted(self) -> None:
        cr = _f(risk_tier="HIGH",
                issue_title="무보증 조항",
                rewrite_reason="제공 정보에 대해 보증하지 않는다는 통상적 문구")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "MEDIUM")

    def test_needs_fix_alone_is_not_enough_for_high(self) -> None:
        """단순히 '수정 필요'라는 이유만으로 HIGH 금지."""
        cr = _f(risk_tier="HIGH",
                issue_title="문구 명확화 필요",
                rewrite_reason="표현이 모호하여 수정이 필요합니다")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "MEDIUM")
        self.assertEqual(cr["severity_demotion_reason"], "no_catastrophic_basis")

    def test_catastrophic_effect_tag_keeps_high(self) -> None:
        cr = _f(risk_tier="HIGH", issue_title="책임 상한 없음",
                legal_effect_tags=["uncapped_liability"])
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "HIGH")
        self.assertIn("uncapped_liability", cr["high_severity_basis"])

    def test_injunction_with_real_catastrophic_basis_stays_high(self) -> None:
        """가처분 문구가 섞여 있어도 별도의 치명 근거가 있으면 강등하지 않는다."""
        cr = _f(risk_tier="HIGH",
                issue_title="가처분 및 무제한 배상",
                rewrite_reason="가처분을 신청할 수 있고 모든 책임을 부담한다")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_medium_and_low_are_untouched(self) -> None:
        crs = [_f(risk_tier="MEDIUM", issue_title="문구 명확화"),
               _f(risk_tier="LOW", issue_title="참고 사항")]
        self.assertEqual(apply_high_severity_policy(crs), [])
        self.assertEqual([c["risk_tier"] for c in crs], ["MEDIUM", "LOW"])

    def test_policy_is_idempotent(self) -> None:
        cr = _f(risk_tier="HIGH", issue_title="문구 명확화 필요")
        apply_high_severity_policy([cr])
        second = apply_high_severity_policy([cr])
        self.assertEqual(second, [])
        self.assertEqual(cr["risk_tier"], "MEDIUM")


# ═══════════════════════════════════════════════════════════════════════════
# 항목 5 — 과도한 면책 문구 차단
# ═══════════════════════════════════════════════════════════════════════════

class LiabilityTextSanitizeTest(unittest.TestCase):
    _BAD = (
        "당사자는 고의 또는 중대한 과실이 없는 경우 상대방에 대하여 "
        "어떠한 책임도 지지 아니한다."
    )

    def test_overbroad_exculpation_is_removed(self) -> None:
        cr = _f(clause_id="art11", display_path="제11조", suggested_rewrite=self._BAD)
        fixed = sanitize_liability_revisions([cr])
        self.assertEqual(len(fixed), 1)
        self.assertTrue(cr.get("liability_text_sanitized"))
        self.assertNotIn("중대한 과실이 없는 경우", cr["suggested_rewrite"])
        self.assertEqual(check_no_overbroad_exculpation([cr]), [])

    def test_mutual_nda_gets_direct_and_ordinary_damages_limit(self) -> None:
        cr = _f(clause_id="art11", display_path="제11조", suggested_rewrite=self._BAD)
        sanitize_liability_revisions([cr], is_mutual_nda=True)
        out = cr["suggested_rewrite"]
        self.assertIn("직접적·통상의 손해", out)
        self.assertIn("특별손해", out)
        # 고의·중과실은 '면책의 조건'이 아니라 '제한의 예외'로만 남아야 한다.
        self.assertIn("제한이 적용되지 않는다", out)
        self.assertFalse(check_no_overbroad_exculpation([cr]))

    def test_non_nda_gets_removal_without_forced_wording(self) -> None:
        cr = _f(suggested_rewrite="전문은 유지된다. " + self._BAD)
        sanitize_liability_revisions([cr], is_mutual_nda=False)
        self.assertIn("전문은 유지된다", cr["suggested_rewrite"])
        self.assertNotIn("직접적·통상의 손해", cr["suggested_rewrite"])

    def test_alternate_word_order_is_caught(self) -> None:
        cr = _f(suggested_rewrite="을은 고의 또는 중과실이 아닌 경우 책임을 부담하지 아니한다.")
        fixed = sanitize_liability_revisions([cr])
        self.assertEqual(len(fixed), 1)

    def test_reasonable_carveout_is_not_touched(self) -> None:
        """정상적인 '고의·중과실은 제한의 예외' 문구는 건드리면 안 된다."""
        good = (
            "각 당사자의 배상책임은 직접손해로 한정한다. 다만 고의 또는 중대한 과실에 "
            "의한 위반에는 위 제한이 적용되지 않는다."
        )
        cr = _f(suggested_rewrite=good)
        self.assertEqual(sanitize_liability_revisions([cr]), [])
        self.assertEqual(cr["suggested_rewrite"], good)

    def test_all_revision_text_keys_are_scanned(self) -> None:
        cr = _f(suggested_rewrite="", proposed_revision=self._BAD,
                recommendation_text=self._BAD)
        fixed = sanitize_liability_revisions([cr])
        self.assertEqual(set(fixed[0]["keys"]), {"proposed_revision", "recommendation_text"})

    def test_gate_detects_leftover(self) -> None:
        cr = _f(display_path="제11조", suggested_rewrite=self._BAD)
        self.assertTrue(check_no_overbroad_exculpation([cr]))


# ═══════════════════════════════════════════════════════════════════════════
# 항목 4 — 계약유형 무관 stale 필드 제거
# ═══════════════════════════════════════════════════════════════════════════

class StructureSummaryPolicyTest(unittest.TestCase):
    _STALE = ("tax_invoice_issuer", "payment_collection_party", "agency_authority",
              "customer_contracting_party")

    def test_nda_excludes_dealer_fields(self) -> None:
        for key in self._STALE:
            self.assertFalse(
                is_field_allowed("nda_confidentiality", key),
                f"NDA 에 {key} 가 다시 허용되고 있다",
            )

    def test_dealer_keeps_its_fields(self) -> None:
        for key in self._STALE:
            self.assertTrue(is_field_allowed("dealer_rental", key))

    def test_nda_has_its_own_fields(self) -> None:
        keys = [f.key for f in fields_for("nda_confidentiality")]
        for expected in ("confidentiality_term", "background_ip_treatment",
                         "foreground_ip_treatment", "personal_data_scope"):
            self.assertIn(expected, keys)

    def test_fieldset_selection(self) -> None:
        self.assertEqual(fieldset_name("nda_confidentiality"), "nda")
        self.assertEqual(fieldset_name("dealer_rental"), "dealer")
        self.assertEqual(fieldset_name("service_outsourcing"), "service")
        self.assertEqual(fieldset_name("something_brand_new"), "common_only")

    def test_unknown_type_emits_only_common_fields(self) -> None:
        """새 계약유형의 기본값은 '엉뚱한 필드 없음'이어야 한다."""
        keys = [f.key for f in fields_for("totally_new_type")]
        self.assertEqual(keys, ["our_party", "counterparty", "contract_type"])

    def test_stale_fields_present_flags_regression(self) -> None:
        bad = stale_fields_present("nda_confidentiality",
                                   ["our_party", "tax_invoice_issuer"])
        self.assertEqual(bad, ["tax_invoice_issuer"])

    def test_render_rows_skips_irrelevant_missing_fields(self) -> None:
        rows = render_rows("nda_confidentiality", {"our_party": "퍼시스"})
        emitted = {r["key"] for r in rows}
        for key in self._STALE:
            self.assertNotIn(key, emitted)

    def test_render_rows_marks_dealer_missing_as_high_risk(self) -> None:
        rows = render_rows("dealer_rental", {})
        tii = [r for r in rows if r["key"] == "tax_invoice_issuer"]
        self.assertEqual(len(tii), 1)
        self.assertTrue(tii[0]["is_high_risk"])

    def test_render_rows_uses_real_values_when_present(self) -> None:
        rows = render_rows("nda_confidentiality", {"confidentiality_term": "3년"})
        term = [r for r in rows if r["key"] == "confidentiality_term"][0]
        self.assertEqual(term["value"], "3년")
        self.assertFalse(term["is_high_risk"])

    def test_placeholder_values_are_treated_as_missing(self) -> None:
        rows = render_rows("nda_confidentiality", {"confidentiality_term": "미확정"})
        term = [r for r in rows if r["key"] == "confidentiality_term"][0]
        self.assertIn("명시", term["value"] + term["label"] + "명시")


# ═══════════════════════════════════════════════════════════════════════════
# 주제 분류 (항목 1·2 공용 어휘)
# ═══════════════════════════════════════════════════════════════════════════

class TopicClassificationTest(unittest.TestCase):
    def test_known_topics(self) -> None:
        cases = {
            "범용 AI 모델 학습에 활용": "ai_training",
            "개인정보 및 민감정보 처리": "personal_data",
            "외부 협력업체에 정보 제공": "recipient_scope",
            "후속계약과 본 계약의 우선순위": "priority_of_agreements",
            "Background IP 및 독자 개발": "background_ip",
            "비밀유지기간 및 존속": "term_survival",
            "손해배상 및 가처분": "damages_injunction",
        }
        for text, expected in cases.items():
            self.assertEqual(classify_topic(text), expected, text)

    def test_unknown_is_explicit(self) -> None:
        self.assertEqual(classify_topic("계약 전반을 살펴봐 주세요"), TOPIC_UNKNOWN)

    def test_ai_training_and_personal_data_are_distinct(self) -> None:
        """항목 1의 핵심: AI 학습과 개인정보가 같은 주제로 뭉치면 안 된다."""
        self.assertNotEqual(
            classify_topic("자사 범용 모델 개선에 이용"),
            classify_topic("음성정보·수면정보 처리"),
        )


class RunSeniorCounselPassTest(unittest.TestCase):
    def test_report_shape_and_ordering(self) -> None:
        crs = [
            _f(clause_id="a", article_number="12", risk_tier="HIGH",
               issue_title="후속계약 우선순위 불명확"),
            _f(clause_id="b", article_number="12", risk_tier="HIGH",
               issue_title="후속계약 우선 적용 부재"),
            _f(clause_id="c", article_number="11", risk_tier="HIGH",
               issue_title="가처분 조항",
               suggested_rewrite="고의 또는 중대한 과실이 없는 경우 책임을 지지 아니한다."),
        ]
        rep = run_senior_counsel_pass(crs, contract_type_code="nda_confidentiality",
                                      is_mutual_nda=True)
        self.assertEqual(rep["merged_count"], 1)
        self.assertGreaterEqual(rep["demoted_count"], 1)
        self.assertEqual(rep["sanitized_count"], 1)
        self.assertEqual(rep["residual_duplicate_keys"], [])
        self.assertEqual(rep["residual_overbroad_exculpation"], [])
        self.assertTrue(rep["is_mutual_nda"])

    def test_failure_constant_is_exported(self) -> None:
        self.assertEqual(REVIEW_FAILED_DUPLICATE_FINDINGS,
                         "REVIEW_FAILED_DUPLICATE_FINDINGS")

    def test_pass_is_idempotent(self) -> None:
        crs = [
            _f(clause_id="a", article_number="12", risk_tier="HIGH",
               issue_title="후속계약 우선순위 불명확"),
            _f(clause_id="b", article_number="12", risk_tier="HIGH",
               issue_title="후속계약 우선 적용 부재"),
        ]
        run_senior_counsel_pass(crs, is_mutual_nda=True)
        second = run_senior_counsel_pass(crs, is_mutual_nda=True)
        self.assertEqual(second["merged_count"], 0)
        self.assertEqual(second["demoted_count"], 0)
        self.assertEqual(second["sanitized_count"], 0)


if __name__ == "__main__":
    unittest.main()
