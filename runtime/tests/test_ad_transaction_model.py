"""광고계약 거래구조 판정과 「광고매체 집행형」 검토 (2026-09-15 지시).

실측 출발점
──────────
사용자가 검토 요청에 "엘레베이터 내 미디어 광고 집행을 위탁하는 계약" 이라고
적었고 계약서도 "고객이 전달한 컨텐츠를 송출" 한다고 적혀 있는데, 사전질문에
이것이 나갔다.

    Q-EFF-ip-scope
    "이 계약으로 취득하는 지식재산을 앞으로 어디까지 활용할 계획인가요?
     (매체·기간·지역·재가공 포함 여부)"

상대방은 아무것도 만들지 않으므로 취득하는 지식재산이 없다. 2차적저작물작성권·
저작인격권·chain of title 은 콘텐츠 제작계약의 논점이다.

fixture 는 같은 구조의 **합성 계약서**다(실제 계약서는 공개 저장소에 두지 않는다).
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.questions.ad_media_questions import (
    MEDIA_PLACEMENT_QUESTIONS,
    apply_ad_media_question_policy,
    is_production_only_question,
)
from runtime.questions.model import Question
from runtime.review.ad_transaction_model import (
    AD_CONTENT_PRODUCTION,
    AD_HYBRID,
    AD_MEDIA_PLACEMENT,
    AD_NOT_ADVERTISING,
    classify_ad_transaction_model,
    deactivate_production_only_findings,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MEDIA = (FIXTURES / "ad_media_placement_contract.txt").read_text(encoding="utf-8")
PRODUCTION = (FIXTURES / "sns_marketing_partnership.txt").read_text(encoding="utf-8")

USER_MEDIA = "엘리베이터 내 미디어 광고 집행을 위탁하기 위한 계약서입니다."
USER_PRODUCTION = "SNS 콘텐츠 제작을 맡기는 계약입니다."


def _q(qid: str, title: str, description: str = "") -> Question:
    return Question(
        question_id=qid, title=title, description=description,
        answer_type="text", required=False, options=[], tags=[], related_rule_ids=[],
    )


class ClassificationTest(unittest.TestCase):
    def test_media_placement_is_recognised(self) -> None:
        m = classify_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_MEDIA,
        )
        self.assertEqual(m.model, AD_MEDIA_PLACEMENT)
        self.assertTrue(m.confident)
        self.assertFalse(m.counterparty_produces_content)

    def test_content_production_is_recognised(self) -> None:
        m = classify_ad_transaction_model(
            contract_text=PRODUCTION, user_description=USER_PRODUCTION,
        )
        self.assertEqual(m.model, AD_CONTENT_PRODUCTION)
        self.assertTrue(m.counterparty_produces_content)

    def test_conflicting_signals_stay_conservative(self) -> None:
        """사용자 설명과 원문이 엇갈리면 확신하지 않는다 — 아무것도 끄지 않는다."""
        m = classify_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_PRODUCTION,
        )
        self.assertEqual(m.model, AD_HYBRID)
        self.assertFalse(m.confident)

    def test_non_advertising_contract_is_out_of_scope(self) -> None:
        m = classify_ad_transaction_model(
            contract_text="본 계약은 물품 공급에 관한 것이다. 대금은 30일 이내 지급한다.",
        )
        self.assertEqual(m.model, AD_NOT_ADVERTISING)


class QuestionPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.media = classify_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_MEDIA,
        )

    def test_the_golden_question_is_suppressed(self) -> None:
        """사고를 일으킨 바로 그 질문."""
        q = _q(
            "Q-EFF-ip-scope",
            "이 계약으로 취득하는 지식재산을 앞으로 어디까지 활용할 계획인가요? "
            "(매체·기간·지역·재가공 포함 여부)",
        )
        self.assertTrue(is_production_only_question(q))
        report = apply_ad_media_question_policy([q], self.media)
        self.assertTrue(report["applied"])
        self.assertNotIn(
            "Q-EFF-ip-scope", {x.question_id for x in report["questions"]},
        )

    def test_production_only_questions_are_suppressed_by_wording(self) -> None:
        for title in (
            "결과물을 2차 활용할 계획이 있나요?",
            "2차적저작물작성권을 확보할 계획인가요?",
            "창작자의 저작인격권 불행사 확약을 받을 예정인가요?",
            "저작권을 양도받을 계획인가요?",
        ):
            self.assertTrue(is_production_only_question(_q("Q-X", title)), title)

    def test_media_placement_questions_are_added(self) -> None:
        report = apply_ad_media_question_policy([], self.media, max_questions=7)
        added = {x.question_id for x in report["questions"]}
        self.assertTrue(added)
        self.assertTrue(all(qid.startswith("Q-ADM-") for qid in added))

    def test_nothing_changes_when_not_confident(self) -> None:
        model = classify_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_PRODUCTION,
        )
        q = _q("Q-EFF-ip-scope", "이 계약으로 취득하는 지식재산을 …")
        report = apply_ad_media_question_policy([q], model)
        self.assertFalse(report["applied"])
        self.assertEqual(len(report["questions"]), 1)

    def test_production_contract_keeps_its_ip_question(self) -> None:
        model = classify_ad_transaction_model(
            contract_text=PRODUCTION, user_description=USER_PRODUCTION,
        )
        q = _q("Q-EFF-ip-scope", "이 계약으로 취득하는 지식재산을 …")
        report = apply_ad_media_question_policy([q], model)
        self.assertFalse(report["applied"])
        self.assertIn("Q-EFF-ip-scope", {x.question_id for x in report["questions"]})

    def test_question_ids_are_unique(self) -> None:
        ids = [q.question_id for q in MEDIA_PLACEMENT_QUESTIONS]
        self.assertEqual(len(ids), len(set(ids)))


class ProductionFindingDeactivationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.media = classify_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_MEDIA,
        )

    def test_chain_of_title_finding_is_removed(self) -> None:
        cr = {
            "clause_id": "pkg_ip_chain_of_title",
            "risk_tier": "HIGH",
            "issue_title": "[리스크 사슬] 창작자 → 권리 귀속·양도 → 2차적저작물작성권 "
                           "→ 매체·기간·지역 → 제3자 소재 → 저작인격권",
            "problem": "창작자로부터의 권리 확약이 없습니다.",
        }
        results = [cr]
        removed = deactivate_production_only_findings(results, self.media)
        self.assertEqual(len(removed), 1)
        self.assertEqual(results, [])

    def test_supplied_content_liability_finding_survives(self) -> None:
        """광고주가 제공한 콘텐츠의 책임 범위는 집행형의 진짜 논점이다."""
        cr = {
            "clause_id": "ADM-05",
            "risk_tier": "HIGH",
            "issue_title": "제공 콘텐츠 책임이 무제한이고 매체사 귀책이 구분되지 않음",
            "problem": "고객이 제공한 콘텐츠에 대해 모든 법적 책임을 부담하고, "
                       "지식재산권 침해 시 면책 의무가 무제한입니다.",
        }
        results = [cr]
        self.assertEqual(deactivate_production_only_findings(results, self.media), [])
        self.assertEqual(len(results), 1)

    def test_nothing_removed_for_production_contracts(self) -> None:
        model = classify_ad_transaction_model(
            contract_text=PRODUCTION, user_description=USER_PRODUCTION,
        )
        cr = {
            "clause_id": "X", "risk_tier": "HIGH",
            "issue_title": "2차적저작물작성권 미확보",
        }
        results = [cr]
        self.assertEqual(deactivate_production_only_findings(results, model), [])
        self.assertEqual(len(results), 1)


class MediaPlacementChecklistTest(unittest.TestCase):
    """지시가 열거한 9개 축이 전부 검토되는가."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.checklists.ad_media_placement import (
            run_ad_media_placement_checklist,
        )
        from runtime.review.clause_extraction import extract_clauses

        extracted = extract_clauses(MEDIA)
        clauses = extracted[0] if isinstance(extracted, tuple) else extracted
        cls.model = classify_ad_transaction_model(
            contract_text=MEDIA, user_description=USER_MEDIA,
        )
        cls.findings = run_ad_media_placement_checklist(
            text=MEDIA, clauses=clauses, model=cls.model,
        )
        cls.by_id = {f["clause_id"]: f for f in cls.findings}

    def test_all_nine_axes_are_covered(self) -> None:
        self.assertEqual(
            sorted(self.by_id),
            [f"ADM-0{n}" for n in range(1, 10)],
            "지시가 열거한 9개 축 중 빠진 것이 있다",
        )

    def test_every_finding_has_insertable_clause_text(self) -> None:
        from runtime.review.rewrite_completeness import is_descriptive_only

        bad = [
            f["clause_id"] for f in self.findings
            if is_descriptive_only(f["suggested_rewrite"])
        ]
        self.assertEqual(bad, [], "그대로 삽입할 수 없는 설명형 문안")

    def test_every_finding_points_at_a_real_clause(self) -> None:
        import re
        real = {str(n) for n in range(1, 6)}  # fixture 는 제1~5조
        for f in self.findings:
            for m in re.finditer(r"제\s*(\d{1,3})\s*조", str(f["display_path"])):
                self.assertIn(m.group(1), real, f"{f['clause_id']} 가 없는 조항을 가리킨다")

    def test_quotes_come_from_the_contract(self) -> None:
        from runtime.review.clause_extraction import extract_clauses
        from runtime.review.clause_index import build_clause_index

        extracted = extract_clauses(MEDIA)
        clauses = extracted[0] if isinstance(extracted, tuple) else extracted
        index = build_clause_index(MEDIA, clauses)
        for f in self.findings:
            quote = f["original_text"]
            if quote.startswith("해당 조항 없음"):
                continue
            self.assertTrue(
                index.quote_exists(quote),
                f"{f['clause_id']} 의 원문 인용이 계약서에 없다",
            )

    def test_high_is_reserved_for_money_and_suspension_risks(self) -> None:
        highs = {f["clause_id"] for f in self.findings if f["risk_tier"] == "HIGH"}
        # 급부 미특정·미송출 구제·해지비용·일방중단·면책·상대방 배상
        for expected in ("ADM-01", "ADM-02", "ADM-03", "ADM-04", "ADM-05", "ADM-08"):
            self.assertIn(expected, highs, expected)
        for note in ("ADM-06", "ADM-07", "ADM-09"):
            self.assertNotIn(note, highs, note)

    def test_no_production_rights_topic_appears(self) -> None:
        import re
        rx = re.compile(r"2차적저작물|저작인격권|chain\s*of\s*title|창작자")
        for f in self.findings:
            blob = f"{f['issue_title']}\n{f['problem']}\n{f['suggested_rewrite']}"
            self.assertIsNone(rx.search(blob), f"{f['clause_id']} 에 제작계약용 논점")

    def test_checklist_does_not_run_for_production_contracts(self) -> None:
        from runtime.review.checklists.ad_media_placement import (
            run_ad_media_placement_checklist,
        )
        from runtime.review.clause_extraction import extract_clauses

        extracted = extract_clauses(PRODUCTION)
        clauses = extracted[0] if isinstance(extracted, tuple) else extracted
        model = classify_ad_transaction_model(
            contract_text=PRODUCTION, user_description=USER_PRODUCTION,
        )
        self.assertEqual(
            run_ad_media_placement_checklist(
                text=PRODUCTION, clauses=clauses, model=model,
            ),
            [],
        )


class GoldenPipelineTest(unittest.TestCase):
    """AI 없이 전체 파이프라인을 돌려 결과가 집행형으로 서는지 본다."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.review.clause_level import build_clause_level_result
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.bundle = build_clause_level_result(
            service=RuleQueryService(loader),
            entity="가나상사",
            contract_type="광고",
            text=MEDIA,
            filename="ad_media_placement_contract.txt",
            answers=None, review_focus=USER_MEDIA, law_service=None,
            ai_provider=None, ai_model="", ai_timeout_sec=60.0,
            ai_max_tokens=2000, ai_temperature=0.1,
        )

    def test_model_is_recorded_in_meta(self) -> None:
        model = self.bundle.meta.get("ad_transaction_model") or {}
        self.assertEqual(model.get("model"), AD_MEDIA_PLACEMENT)
        self.assertTrue(model.get("confident"))
        self.assertFalse(model.get("counterparty_produces_content"))

    def test_final_output_covers_media_placement_axes(self) -> None:
        final = self.bundle.meta.get("final_findings") or {}
        ids = {
            str(i.get("clause_id"))
            for bucket in ("high_issues", "medium_issues")
            for i in (final.get(bucket) or [])
            if isinstance(i, dict)
        }
        self.assertTrue(
            [x for x in ids if x.startswith("ADM-")],
            "집행형 검토 항목이 최종 결과에 하나도 없다",
        )

    def test_no_production_rights_finding_survives(self) -> None:
        import re
        rx = re.compile(r"2차적저작물|저작인격권|chain\s*of\s*title")
        offenders: list[str] = []
        for cr in self.bundle.clause_results:
            if not isinstance(cr, dict) or cr.get("dedup_suppressed") or cr.get("keep_as_is"):
                continue
            blob = "\n".join(
                str(cr.get(k) or "")
                for k in ("issue_title", "problem", "suggested_rewrite")
            )
            if rx.search(blob):
                offenders.append(str(cr.get("clause_id")))
        self.assertEqual(offenders, [], "집행형인데 제작계약용 논점이 남았다")


if __name__ == "__main__":
    unittest.main()
