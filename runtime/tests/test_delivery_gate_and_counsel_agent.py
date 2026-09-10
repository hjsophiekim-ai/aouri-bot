"""수정본 다운로드 전달 게이트 + 사내변호사 에이전트 회귀테스트 (2026-09-10 지시).

지시 항목 2 — "최종 수정본 워드파일 생성이 또 실패했다. 앞으로 절대 에러나지
않고 최종수정본이 다운로드되게 하라."

실측 실패: POST /api/revision/download_docx → 409 REVIEW_FAILED_SEMANTIC_MISMATCH.
원인은 게이트의 **판정**이 아니라 **처리 방식**이었다 —
`finding_integrity_gates` 는 whitelist(당시 `nda_confidentiality` 하나뿐)에 없는
계약유형에서는 결함을 제거할 수단 없이 `status` 만 세웠고, 그 상태가 다운로드
핸들러의 409 로 이어져 몇 번을 눌러도 같은 실패가 났다.

지시 항목 3 — 사내변호사형 에이전트가 만든 논점이 인용 검증을 통과하는지,
그리고 조 단위 병합·강등에 흡수돼 사라지지 않는지.
"""
from __future__ import annotations

import unittest

from runtime.review.counsel_agent import (
    CounselIssue,
    CounselReport,
    counsel_issues_to_clause_results,
    verify_grounding,
)
from runtime.review.delivery_gate import (
    NON_REMEDIABLE_STATUSES,
    DeliveryReport,
    disclosure_rows,
    is_advisory_only,
    remediate_review_status,
    withdraw_proposal,
)
from runtime.review.finding_integrity_gates import enforce_clause_semantic_gate
from runtime.review.output_filter import build_final_findings
from runtime.review.transaction_consistency import check_transaction_consistency

_CONTRACT = """제5조 (대물교환 및 대가의 정산)
① 본 계약은 상호 등가의 대가로 하는 대물교환 계약이며, 양 당사자는 상대방에게 별도의 현금 대가를 지급하지 아니한다.
② 양 당사자는 각자 상대방에게 세금계산서를 발행한다.
제9조 (저작권의 귀속 및 2차 활용)
③ "갑사"은 본건 콘텐츠를 기간·지역·횟수·매체의 제한 없이 자유롭게 이용할 수 있으며, 그 이용의 범위는 다음 각 호를 포함한다.
"""


def _issue(**kw) -> CounselIssue:
    base = dict(
        axis="legal", title="t", clause_path="", quote="", is_missing_clause=False,
        our_exposure="노출", legal_basis="근거", recommendation="권고",
        severity="HIGH", materiality_reason="중요",
    )
    base.update(kw)
    return CounselIssue(**base)


class DeliveryGateTest(unittest.TestCase):
    def test_remediable_status_is_cleared_and_recorded(self) -> None:
        meta = {
            "review_status": "REVIEW_FAILED_SEMANTIC_MISMATCH",
            "review_status_detail": "CP-003 불일치",
        }
        report = DeliveryReport()
        blocking = remediate_review_status(meta, report)
        self.assertEqual(blocking, "", "제거 가능한 상태가 다운로드를 막으면 안 된다")
        self.assertEqual(meta["review_status"], "")
        self.assertEqual(meta["review_status_remediated"], "REVIEW_FAILED_SEMANTIC_MISMATCH")
        rows = disclosure_rows(report)
        self.assertEqual(len(rows), 1)
        self.assertIn("법률효과", rows[0]["reason"])
        self.assertIn("CP-003", rows[0]["detail"])

    def test_unknown_review_failed_status_defaults_to_remediable(self) -> None:
        """게이트가 하나 늘 때마다 다운로드가 다시 막히면 안 된다 —
        기본값은 '차단'이 아니라 '기록 후 전달'이다."""
        meta = {"review_status": "REVIEW_FAILED_SOMETHING_BRAND_NEW"}
        blocking = remediate_review_status(meta, DeliveryReport())
        self.assertEqual(blocking, "")

    def test_non_remediable_status_still_blocks(self) -> None:
        """내보낼 내용 자체가 없는 경우까지 전달하지는 않는다."""
        status = next(iter(NON_REMEDIABLE_STATUSES))
        meta = {"review_status": status}
        self.assertEqual(remediate_review_status(meta, DeliveryReport()), status)

    def test_withdraw_proposal_substitutes_a_minimal_edit(self) -> None:
        """[2026-09-10 아키텍처 지시 항목 7] 신뢰할 수 없는 문안을 회수하되
        자리표시자를 남기지 않는다 — 원문의 법률효과를 유지한 최소수정안을
        직접 만들어 넣는다. finding 도 그대로 남아야 한다."""
        cr = {
            "clause_id": "KR-5-p2",
            "original_text": "양 당사자는 각자 상대방에게 세금계산서를 발행한다.",
            "risk_tier": "HIGH",
            "rewrite_reason": "과세표준 산정 근거가 불명확",
            "suggested_rewrite": "엉뚱한 문안",
            "redline_instruction": {"edit_location": "제5조 제2항 교체"},
        }
        withdraw_proposal(cr, status="REVIEW_FAILED_SEMANTIC_MISMATCH")

        rewrite = str(cr["suggested_rewrite"] or "")
        self.assertNotIn("엉뚱한 문안", rewrite, "신뢰할 수 없는 문안이 남았다")
        self.assertTrue(cr["minimal_edit_applied"])
        self.assertIn("세금계산서를 발행한다", rewrite, "원문이 보존되어야 한다")
        for banned in ("[수정문안 보류]", "담당 변호사가 직접 확정", "추후 협의"):
            self.assertNotIn(banned, rewrite)
            self.assertNotIn(banned, str(cr.get("recommendation_text") or ""))
        self.assertTrue(cr["negotiation_position"], "practical position 이 있어야 한다")
        self.assertIsInstance(cr["redline_instruction"], dict)

        findings = build_final_findings([cr], contract_type_code="", include_low=False)
        self.assertEqual(findings["high_count"], 1, "문안 교체가 finding 을 지워버렸다")

    def test_fact_confirmation_when_no_original_text(self) -> None:
        """원문이 없어 문구를 만들 수 없을 때만 FACT_CONFIRMATION_REQUIRED —
        그때도 무엇을 확인해야 하는지 구체적으로 적는다."""
        cr = {"clause_id": "x", "original_text": "", "risk_tier": "MEDIUM",
              "suggested_rewrite": "믿을 수 없는 문안"}
        withdraw_proposal(cr, status="REVIEW_FAILED_SEMANTIC_MISMATCH")
        self.assertEqual(cr["fact_confirmation_required"], "FACT_CONFIRMATION_REQUIRED")
        self.assertTrue(cr["fact_confirmation_items"])
        self.assertIn("사실확인 필요", str(cr["recommendation_text"]))


class SemanticGateRemediationTest(unittest.TestCase):
    def test_non_whitelisted_type_withdraws_instead_of_failing(self) -> None:
        """whitelist 밖 계약유형에서도 결함을 실제로 해소한다 — status 만 세우고
        방치하면 그 상태가 409 로 이어져 영원히 다운로드되지 않는다."""
        clause_results = [{
            "clause_id": "CP-003",
            "original_text": "을사는 어떠한 경우에도 금전 지급을 청구할 수 없다.",
            "risk_tier": "MEDIUM",
            "original_effect_tags": ["payment_obligation"],
            "rewrite_effect_tags": ["payment_withholding"],
            "suggested_rewrite": "대금 지급을 유보할 수 있다.",
        }]
        report = enforce_clause_semantic_gate(
            clause_results, contract_type_code="advertising_content_production",
        )
        self.assertEqual(report["status"], "", "해소했으면 검토 실패 상태를 세우지 않는다")
        self.assertEqual(report["withdrawn_count"], 1)
        self.assertEqual(len(clause_results), 1, "finding 자체는 남아야 한다")
        rewrite = str(clause_results[0]["suggested_rewrite"] or "")
        self.assertNotIn("대금 지급을 유보할 수 있다", rewrite, "잘못된 문안이 남았다")
        self.assertNotIn("[수정문안 보류]", rewrite)
        self.assertTrue(clause_results[0].get("minimal_edit_applied"))


class TransactionConsistencyTest(unittest.TestCase):
    def test_cash_payment_template_is_withdrawn_in_barter_contract(self) -> None:
        clause_results = [{
            "clause_id": "KR-9-p3",
            "original_text": "갑사은 본건 콘텐츠를 자유롭게 이용할 수 있다.",
            "suggested_rewrite": "대금을 완납한 때에 사용권이 이전된다.",
        }]
        report = check_transaction_consistency(clause_results, contract_text=_CONTRACT)
        self.assertEqual(report["consideration_structure"], "non_monetary_exchange")
        self.assertEqual(len(report["withdrawn"]), 1)
        self.assertIsNone(clause_results[0]["suggested_rewrite"])

    def test_cash_contract_is_untouched(self) -> None:
        clause_results = [{
            "clause_id": "x",
            "original_text": "원문",
            "suggested_rewrite": "대금을 완납한 때에 사용권이 이전된다.",
        }]
        report = check_transaction_consistency(
            clause_results, contract_text="갑은 을에게 용역대금 1억원을 지급한다.",
        )
        self.assertEqual(report["withdrawn"], [])
        self.assertIsNotNone(clause_results[0]["suggested_rewrite"])


class CounselAgentGroundingTest(unittest.TestCase):
    def test_fabricated_quote_is_dropped(self) -> None:
        kept, dropped = verify_grounding(
            [_issue(quote="이 계약에는 전혀 없는 문장이며 완전히 지어낸 인용입니다.")],
            _CONTRACT,
        )
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "quote_not_found_in_contract")

    def test_abridged_quote_is_kept_and_replaced_with_real_text(self) -> None:
        """AI 는 긴 조항을 축약 인용한다. 전체 대조만 하면 실재하는 조항을
        가리킨 정당한 논점까지 버려지므로, 앵커가 실재하면 남기되 표시되는
        인용문은 계약서의 실제 문장으로 교체한다."""
        issue = _issue(
            quote=(
                '"갑사"은 본건 콘텐츠를 기간·지역·횟수·매체의 제한 없이 자유롭게 '
                "이용할 수 있으며 … 가. … 마. …(중략)"
            )
        )
        kept, dropped = verify_grounding([issue], _CONTRACT)
        self.assertEqual(dropped, [])
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0].grounded)
        self.assertIn("기간·지역·횟수·매체의 제한 없이", kept[0].quote)
        self.assertNotIn("(중략)", kept[0].quote, "계약서에 없는 문장이 인용으로 남았다")

    def test_missing_clause_issue_needs_no_quote(self) -> None:
        kept, dropped = verify_grounding([_issue(quote="", is_missing_clause=True)], _CONTRACT)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])


class CounselIssueConversionTest(unittest.TestCase):
    def _report(self, issue: CounselIssue) -> CounselReport:
        return CounselReport(status="ai", issues=[issue])

    def test_high_issue_carries_severity_basis(self) -> None:
        """senior_counsel_judgment 의 'HIGH 가 정말 가장 큰 리스크인가' 점검은
        HIGH 마다 치명 근거를 요구한다 — 없으면 검토 전체가 실패 처리된다."""
        crs = counsel_issues_to_clause_results(
            self._report(_issue(quote="양 당사자는 각자 상대방에게 세금계산서를 발행한다.", axis="tax")),
            clauses=None,
        )
        self.assertEqual(len(crs), 1)
        self.assertTrue(crs[0]["high_severity_basis"])
        self.assertEqual(crs[0]["counsel_severity"], "HIGH")
        self.assertTrue(crs[0]["is_counsel_agent"])
        self.assertTrue(crs[0]["is_mandatory"])

    def test_quote_is_matched_to_a_real_clause_id(self) -> None:
        """조항 본문 대조로 붙이므로, 존재하지 않는 조항을 가리키지 않는다."""
        clauses = [{
            "clause_id": "KR-5-p2",
            "display_path": "제5조 제2항",
            "article_number": "5",
            "paragraph_number": "2",
            "title": "대물교환 및 대가의 정산",
            "text": "양 당사자는 각자 상대방에게 세금계산서를 발행한다.",
        }]
        crs = counsel_issues_to_clause_results(
            self._report(_issue(quote="양 당사자는 각자 상대방에게 세금계산서를 발행한다.")),
            clauses=clauses,
        )
        self.assertEqual(crs[0]["clause_id"], "KR-5-p2")
        self.assertEqual(crs[0]["display_path"], "제5조 제2항")

    def test_tax_issue_is_not_merged_away_by_clause_identity(self) -> None:
        """같은 조항에 룰 finding 이 이미 있어도 세무 축 논점은 별개다 —
        병합되면 이 검토의 유일한 세무 논점이 사라진다(실측 사고)."""
        rule_finding = {
            "clause_id": "KR-5-p2",
            "display_path": "제5조 제2항",
            "article_number": "5",
            "paragraph_number": "2",
            "original_text": "양 당사자는 각자 상대방에게 세금계산서를 발행한다.",
            "risk_tier": "MEDIUM",
            "rewrite_reason": "정산식·차감사유·증빙 필수화",
            "suggested_rewrite": "정산 기준을 명시한다.",
        }
        counsel = counsel_issues_to_clause_results(
            self._report(
                _issue(
                    axis="tax",
                    title="바터거래 과세표준 시가 적정성",
                    quote="양 당사자는 각자 상대방에게 세금계산서를 발행한다.",
                )
            ),
            clauses=None,
        )[0]
        counsel["display_path"] = "제5조 제2항"
        counsel["article_number"] = "5"
        counsel["paragraph_number"] = "2"

        findings = build_final_findings(
            [rule_finding, counsel], contract_type_code="", include_low=False,
        )
        titles = " ".join(
            str(i.get("issue_title") or "")
            for i in findings["high_issues"] + findings["medium_issues"]
        )
        self.assertIn("과세표준", titles, "세무 논점이 조항 동일성 병합에 흡수됐다")


if __name__ == "__main__":
    unittest.main()
