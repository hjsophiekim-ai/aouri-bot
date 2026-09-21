"""v15 회귀 — Party Role / Quote Location / Duplicate / Applicable Law.

2026-09-21 2차 지시 1~12항. 앞 라운드(v14)가 계약유형·조항 앵커를 바로잡은
뒤에도 남아 있던 네 가지를 고정한다.

    1항  출력 문장이 확정 당사자 지위를 뒤집지 않는다
    3항  인용문은 그 finding 이 가리키는 조항 **안의** 것이어야 한다
    7항  법률마다 결론은 하나다
    8항  같은 법률효과를 다루는 항목은 하나로 합친다
    9항  HIGH 는 실제 손실 규모 순으로 정렬한다

AI 를 쓰지 않는다(`ai_provider=None`) — 결정적이고 무과금이다.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses, is_article_heading_line
from runtime.review.redline_instruction import article_raw_span, article_raw_text
from runtime.tests.test_interior_prime_contractor_review import (
    ANSWERS,
    FIXTURE,
    USER_DESCRIPTION,
)


def _text() -> str:
    return Path(FIXTURE).read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════
# 지시 3항 — 조 구간 판별과 인용 위치
# ══════════════════════════════════════════════════════════════════════════


class ArticleSpanTest(unittest.TestCase):
    def test_inline_cross_reference_is_not_a_heading(self) -> None:
        self.assertIsNone(is_article_heading_line("제14조 제3항 제1목 제2호의 2차 견적에"))
        self.assertIsNone(is_article_heading_line("제15조의 대금 지급 회차 구성과"))
        self.assertEqual(
            is_article_heading_line("제12조 (검사·준공 및 인수인계)")[0], "12",
        )

    def test_article_span_covers_only_that_article(self) -> None:
        body = _text()
        art15 = article_raw_text(body, "15")
        self.assertIn("대금의 지급", art15)
        self.assertIn("유치권 포기각서의 제출", art15)
        # 이웃 조의 문장이 섞이면 인용이 그 조의 것이 아니게 된다.
        self.assertNotIn("보증 : 이행·하자·유치권 포기", art15)
        self.assertNotIn("지체상금", art15)

    def test_span_is_none_for_unknown_article(self) -> None:
        self.assertIsNone(article_raw_span(_text(), "99"))


class QuoteLocationGateTest(unittest.TestCase):
    def test_quote_from_another_article_is_corrected(self) -> None:
        from runtime.review.clause_index import build_clause_index
        from runtime.review.quote_location_gate import enforce_quote_location

        body = _text()
        clauses, _ = extract_clauses(body)
        index = build_clause_index(body, clauses)
        # 제17조(하자담보)를 가리키면서 제8조의 문장을 원문으로 싣는다.
        art8_line = next(
            l.strip() for l in article_raw_text(body, "8").split("\n")
            if "면제하지 아니한다" in l
        )
        findings = [{
            "clause_id": "TEST-1",
            "article_number": "17",
            "display_path": "제17조",
            "issue_title": "테스트",
            "original_text": art8_line,
        }]
        report = enforce_quote_location(findings, index=index, contract_text=body)
        self.assertEqual(len(report.relocated), 1)
        self.assertEqual(report.relocated[0]["quote_belongs_to"], "8")
        self.assertNotEqual(findings[0]["original_text"], art8_line)
        self.assertIn(
            findings[0]["original_text"].strip()[:20],
            article_raw_text(body, "17"),
        )

    def test_quote_from_the_same_article_is_left_alone(self) -> None:
        from runtime.review.clause_index import build_clause_index
        from runtime.review.quote_location_gate import enforce_quote_location

        body = _text()
        clauses, _ = extract_clauses(body)
        index = build_clause_index(body, clauses)
        line = next(
            l.strip() for l in article_raw_text(body, "18").split("\n")
            if len(l.strip()) > 25
        )
        findings = [{
            "clause_id": "TEST-2",
            "article_number": "18",
            "display_path": "제18조",
            "original_text": line,
        }]
        report = enforce_quote_location(findings, index=index, contract_text=body)
        self.assertEqual(report.relocated, [])
        self.assertEqual(findings[0]["original_text"], line)


# ══════════════════════════════════════════════════════════════════════════
# 지시 1항 — 출력 문장의 당사자 지위
# ══════════════════════════════════════════════════════════════════════════


class PartyRoleOutputTest(unittest.TestCase):
    def test_counterparty_described_as_principal_is_flagged(self) -> None:
        from runtime.review.party_role_output_gate import check_party_role_output

        rows = [{
            "statute": "하도급법",
            "reasoning": (
                "퍼시스가 중견기업 이상, 한빛로보틱스가 원사업자에 해당할 "
                "가능성이 높습니다."
            ),
        }]
        report = check_party_role_output(
            our_names=["퍼시스"],
            counterparty_names=["한빛로보틱스"],
            our_role="contractor_with_subcontract",
            counterparty_role="ordering_party",
            our_role_label="수급인",
            counterparty_role_label="도급인",
            extra_records=rows,
        )
        self.assertEqual(len(report.violations), 1)
        self.assertEqual(report.violations[0]["wrong_label"], "원사업자")
        self.assertIn("당사자 지위 정정", rows[0]["reasoning"])

    def test_role_nouns_alone_are_not_a_violation(self) -> None:
        """'도급인 귀책으로 … 수급인이 부담' 은 정상 문장이다."""
        from runtime.review.party_role_output_gate import check_party_role_output

        rows = [{
            "problem": "도급인 귀책으로 발생한 손해까지 수급인이 부담하도록 되어 있습니다.",
        }]
        report = check_party_role_output(
            our_names=["퍼시스", "수급인"],
            counterparty_names=["도급인"],
            our_role="contractor",
            counterparty_role="ordering_party",
            extra_records=rows,
        )
        self.assertEqual(report.violations, [])

    def test_subcontract_context_is_not_a_violation(self) -> None:
        from runtime.review.party_role_output_gate import check_party_role_output

        rows = [{
            "problem": "퍼시스가 전문업체에 재하도급하면 그 관계에서는 퍼시스가 도급인이 됩니다.",
        }]
        report = check_party_role_output(
            our_names=["퍼시스"],
            counterparty_names=["한빛로보틱스"],
            our_role="contractor_with_subcontract",
            counterparty_role="ordering_party",
            extra_records=rows,
        )
        self.assertEqual(report.violations, [])


# ══════════════════════════════════════════════════════════════════════════
# 지시 1·7항 — 하도급법 적용 **방향**
# ══════════════════════════════════════════════════════════════════════════


class SubcontractActDirectionTest(unittest.TestCase):
    def test_word_in_our_own_subcontracting_clause_does_not_flip_us(self) -> None:
        """제21조의 '하도급계약' 한 낱말로 우리가 하수급인이 되면 안 된다."""
        from runtime.review.construction_transaction_model import (
            resolve_construction_transaction_model,
        )

        model = resolve_construction_transaction_model(
            contract_text=_text(),
            user_description=USER_DESCRIPTION,
            entity="주식회사 퍼시스",
            contract_type_code="construction",
        )
        self.assertTrue(model.is_settled)
        self.assertFalse(
            model.we_are_subcontractor,
            "발주자와 직접 계약한 수급인을 하수급인으로 읽었다",
        )

    def test_counterparty_defined_as_principal_still_makes_us_subcontractor(self) -> None:
        from runtime.review.construction_transaction_model import (
            resolve_construction_transaction_model,
        )
        from runtime.tests.test_construction_transaction_model import (
            CONTRACT_WE_ARE_SUBCONTRACTOR,
        )

        model = resolve_construction_transaction_model(
            contract_text=CONTRACT_WE_ARE_SUBCONTRACTOR,
            user_description="",
            entity="주식회사 퍼시스",
            contract_type_code="construction",
        )
        self.assertTrue(model.we_are_subcontractor)


# ══════════════════════════════════════════════════════════════════════════
# 지시 7·8·9항 — 법률 상태 / 중복 / 우선순위
# ══════════════════════════════════════════════════════════════════════════


class StatuteCanonicalStateTest(unittest.TestCase):
    def test_ai_result_is_aligned_to_the_requirement_conclusion(self) -> None:
        from runtime.review.statute_canonical_state import (
            NOT_APPLIES,
            StatuteCanonicalState,
            reconcile_ai_applicability,
        )

        state = StatuteCanonicalState(
            statuses={"하도급법": NOT_APPLIES},
            reasons={"하도급법": "원도급 관계에는 적용되지 않습니다."},
        )
        rows = [{
            "statute": "하도급거래 공정화에 관한 법률",
            "applicability": "높음",
            "risk_level": "HIGH",
            "reasoning": "원사업자에 해당할 가능성이 높습니다.",
        }]
        reconcile_ai_applicability(rows, state)
        self.assertEqual(rows[0]["applicability"], "낮음")
        self.assertEqual(rows[0]["risk_level"], "LOW")
        self.assertEqual(rows[0]["canonical_status"], NOT_APPLIES)
        self.assertEqual(len(state.conflicts), 1)

    def test_calibrated_rows_are_not_overwritten(self) -> None:
        from runtime.review.statute_canonical_state import (
            NOT_APPLIES,
            StatuteCanonicalState,
            reconcile_ai_applicability,
        )

        state = StatuteCanonicalState(statuses={"대리점법": NOT_APPLIES})
        rows = [{
            "statute": "대리점법",
            "applicability": "있음(추가 확인 필요)",
            "risk_level": "MEDIUM",
            "applicability_calibrated": "dealer_act_floor",
        }]
        reconcile_ai_applicability(rows, state)
        self.assertEqual(rows[0]["risk_level"], "MEDIUM")
        self.assertEqual(state.conflicts, [])
        self.assertEqual(len(state.deferred), 1)


class DuplicateConsolidationTest(unittest.TestCase):
    def test_same_finding_twice_is_removed(self) -> None:
        from runtime.review.duplicate_consolidation import consolidate_duplicate_findings

        rows = [
            {"clause_id": "counsel_KR-16", "issue_title": "유치권 포기각서", "severity": "HIGH"},
            {"clause_id": "counsel_KR-16", "issue_title": "유치권 포기각서", "severity": "HIGH"},
        ]
        report = consolidate_duplicate_findings(rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(report.exact_duplicates, ["counsel_KR-16"])

    def test_same_legal_effect_is_folded_into_one(self) -> None:
        from runtime.review.duplicate_consolidation import consolidate_duplicate_findings

        rows = [
            {
                "clause_id": "CWC-LIEN-WAIVER", "display_path": "제15조",
                "issue_title": "유치권 포기각서 제출이 공사대금 지급의 선행조건",
                "risk_tier": "HIGH", "severity": "HIGH",
                "article_number": "15", "original_text": "② 유치권 포기각서의 제출",
                "suggested_rewrite": "①" + "가" * 300,
            },
            {
                "clause_id": "counsel_KR-16", "display_path": "제16조",
                "issue_title": "유치권 포기의 부당특약 가능성",
                "risk_tier": "HIGH", "severity": "HIGH",
                "article_number": "16", "original_text": "유치권 포기각서",
                "suggested_rewrite": "짧은 문안",
            },
        ]
        report = consolidate_duplicate_findings(rows)
        self.assertEqual(len(report.merged), 1)
        primary = rows[0]
        self.assertEqual(primary["clause_id"], "CWC-LIEN-WAIVER")
        self.assertTrue(rows[1].get("dedup_suppressed"))
        self.assertTrue(primary.get("consolidated_points"))

    def test_separate_document_items_are_not_folded_in(self) -> None:
        from runtime.review.duplicate_consolidation import consolidate_duplicate_findings

        rows = [
            {
                "clause_id": "CWS-02", "display_path": "재하도급 계약서(별도 체결)",
                "issue_title": "재하도급 계약에 하도급법상 대금 지급기한 규정 필요",
                "risk_tier": "HIGH", "severity": "HIGH", "target_contract": "subcontract",
            },
            {
                "clause_id": "CWS-04", "display_path": "재하도급 계약서(별도 체결)",
                "issue_title": "하수급인의 귀책이 우리 책임으로 연결되는 구조",
                "risk_tier": "HIGH", "severity": "HIGH", "target_contract": "subcontract",
            },
        ]
        consolidate_duplicate_findings(rows)
        self.assertFalse(rows[0].get("dedup_suppressed"))
        self.assertFalse(rows[1].get("dedup_suppressed"))


class HighPriorityOrderTest(unittest.TestCase):
    def test_loss_order_follows_the_instruction(self) -> None:
        from runtime.review.construction_high_priority import (
            FINANCE_LABEL,
            apply_high_priority_order,
        )

        rows = [
            {"clause_id": "A", "issue_title": "안전·산재 책임이 수급인에게 전가됨",
             "risk_tier": "HIGH", "severity": "HIGH"},
            {"clause_id": "B", "issue_title": "공사대금 회수 사슬이 끊겨 있음",
             "risk_tier": "HIGH", "severity": "HIGH"},
            {"clause_id": "C", "issue_title": "유치권 포기각서 제출이 선행조건",
             "risk_tier": "HIGH", "severity": "HIGH"},
            {"clause_id": "D", "issue_title": "세금계산서 분리 발행의 부가가치세법상 적정성",
             "risk_tier": "HIGH", "severity": "HIGH"},
        ]
        apply_high_priority_order(rows)
        self.assertEqual([r["clause_id"] for r in rows], ["B", "C", "A", "D"])
        self.assertTrue(rows[-1]["issue_title"].startswith(FINANCE_LABEL))
        self.assertTrue(rows[-1]["finance_confirmation_item"])


# ══════════════════════════════════════════════════════════════════════════
# 전체 파이프라인 (AI off)
# ══════════════════════════════════════════════════════════════════════════


class PipelineGroundingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.bundle = build_clause_level_result(
            service=RuleQueryService(loader),
            entity="주식회사 퍼시스",
            contract_type="인테리어 공사도급계약서",
            text=_text(),
            filename="계약_인테리어_본계약_퍼시스_초안.pdf",
            answers=ANSWERS,
            review_focus=USER_DESCRIPTION,
            law_service=None,
            ai_provider=None,
            ai_model="",
            ai_timeout_sec=60.0,
            ai_max_tokens=2000,
            ai_temperature=0.1,
        )
        cls.meta = cls.bundle.meta
        cls.findings = [
            c for c in cls.bundle.clause_results
            if isinstance(c, dict) and not c.get("dedup_suppressed")
        ]

    def test_every_quote_belongs_to_its_own_article(self) -> None:
        """인용문은 그 finding 이 가리키는 조 안의 문장이어야 한다.

        대조는 게이트와 **같은 기준**(검증된 색인의 조문 텍스트)으로 한다 —
        원문 raw 문자열과 대조하면 조 제목 표기·공백 정규화 차이로 정상
        인용까지 어긋난 것으로 보인다.
        """
        from runtime.review.clause_index import build_clause_index
        from runtime.review.quote_location_gate import _contains

        body = _text()
        index = build_clause_index(body, extract_clauses(body)[0])
        bad: list[str] = []
        for cr in self.findings:
            quote = str(cr.get("original_text") or "").strip()
            article = str(cr.get("article_number") or "")
            if not article or len(quote) < 20 or "해당 조항 없음" in quote:
                continue
            art = index.articles.get(article)
            if art is None or not art.exact_text:
                continue
            if not _contains(art.exact_text, quote):
                bad.append(f"{cr.get('clause_id')}({article}): {quote[:40]}")
        self.assertEqual(bad, [], f"다른 조항의 문장을 원문으로 실었다: {bad}")

    def test_party_role_is_not_reversed_in_output(self) -> None:
        gate = self.meta.get("party_role_output_gate") or {}
        self.assertEqual(gate.get("violations"), [])

    def test_each_statute_has_one_conclusion(self) -> None:
        state = self.meta.get("applicable_law_state") or {}
        statuses = state.get("statuses") or {}
        self.assertTrue(statuses, "적용법률 canonical 상태가 비어 있다")
        for statute, status in statuses.items():
            self.assertIn(
                status, ("APPLIES", "NOT_APPLIES", "NEEDS_FACT_CHECK"),
                f"{statute} 의 상태가 허용값이 아니다: {status}",
            )

    def test_subcontract_act_is_scoped_to_the_subcontract_relationship(self) -> None:
        state = self.meta.get("applicable_law_state") or {}
        reason = str((state.get("reasons") or {}).get("하도급법") or "")
        if not reason:
            self.skipTest("하도급법 판단이 없다")
        self.assertIn("재하도급", reason)
        self.assertNotIn("우리 회사가 그 일부를 하도급받는", reason)

    def test_high_findings_are_ordered_by_loss(self) -> None:
        order = self.meta.get("high_priority_order") or []
        self.assertTrue(order, "손실 순위가 매겨지지 않았다")
        ranks = [
            int(c.get("loss_priority_rank") or 50)
            for c in self.findings
            if str(c.get("risk_tier") or "").upper() in ("HIGH", "CRITICAL")
        ]
        self.assertEqual(ranks, sorted(ranks), f"HIGH 순서가 손실 규모 순이 아니다: {ranks}")

    def test_final_audit_covers_the_new_axes(self) -> None:
        check = self.meta.get("v14_final_self_check") or {}
        axes = {a["key"] for a in (check.get("axes") or [])}
        for key in (
            "quote_location_correct", "party_role_in_output",
            "applicable_law_single_state", "no_duplicate_finding",
        ):
            self.assertIn(key, axes)


if __name__ == "__main__":
    unittest.main()
