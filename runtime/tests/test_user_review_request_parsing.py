"""User Review Request 자유서술 의미 파싱 회귀 테스트 (2026-09-08 지시).

키워드 매칭만으로는 카탈로그에 없는 쟁점(공동 브랜드 사용, 고객데이터 이전,
신규 사업모델 책임 등)이 통째로 누락되던 한계를 잠근다.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from runtime.ai.provider import AIResponse
from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_level import build_clause_level_result
from runtime.review.user_review_request import (
    DEGRADED_NOTICE,
    PARSE_STATUS_AI,
    PARSE_STATUS_AI_FAILED,
    PARSE_STATUS_EMPTY,
    PARSE_STATUS_NO_AI,
    SOURCE_EXPLICIT,
    USER_REQUEST_VERDICTS,
    VERDICT_NEEDS_FACTS,
    VERDICT_NEEDS_FIX,
    build_user_request_coverage,
    check_user_request_coverage,
    issues_from_meta,
    link_clauses_to_issues,
    parse_user_review_request,
    superseded_catalog_codes,
)
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService

FIXTURE = Path(__file__).parent / "fixtures" / "nda_ai_sleep_collaboration.txt"
NDA_CODE = "nda_confidentiality"

FREE_TEXT = (
    "에이슬립이 우리 데이터를 자사 범용 AI 학습이나 다른 고객 서비스 개선에 쓰지 못하도록 "
    "충분한지 봐주세요. 공동 브랜드로 제품을 내보낼 때 브랜드 사용 권한이 정리돼 있는지도 "
    "봐주세요. 제8조 제3항이 우리 독자개발 기술까지 가져가는 구조인지 확인 부탁드립니다."
)

AI_PAYLOAD = [
    {
        "issue_id": "user_ai_secondary_use",
        "issue": "당사 제공정보 또는 프로젝트 데이터의 범용 AI 모델 학습 및 타 고객 목적 이용 제한",
        "original_user_text": "에이슬립이 우리 데이터를 자사 범용 AI 학습이나 다른 고객 서비스 개선에 쓰지 못하도록 충분한지 봐주세요.",
        "expected_answer": True,
        "catalog_code": "ai_training_data_reuse",
        "cited_clauses": [],
        "search_keywords": ["학습", "모델", "데이터", "고객"],
    },
    {
        "issue_id": "user_joint_brand_use",
        "issue": "공동 브랜드로 제품 출시 시 각 당사자의 상표·브랜드 사용 권한과 그 범위",
        "original_user_text": "공동 브랜드로 제품을 내보낼 때 브랜드 사용 권한이 정리돼 있는지도 봐주세요.",
        "expected_answer": True,
        "catalog_code": None,
        "cited_clauses": [],
        "search_keywords": ["브랜드", "상표", "공동"],
    },
    {
        "issue_id": "user_background_ip_grab",
        "issue": "제8조 제3항이 수령자의 독자개발 기술까지 제공자에게 귀속시키는지",
        "original_user_text": "제8조 제3항이 우리 독자개발 기술까지 가져가는 구조인지 확인 부탁드립니다.",
        "expected_answer": True,
        "catalog_code": "background_ip",
        "cited_clauses": ["제8조 제3항"],
        "search_keywords": ["개량", "지식재산권", "독자개발", "귀속"],
    },
]


class _StubProvider:
    """지정한 payload를 그대로 돌려주는 AI provider."""

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.last_request = None

    def complete(self, req):  # noqa: ANN001 — AIProvider Protocol
        self.last_request = req
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)
        return AIResponse(content=content, usage=None, raw=None)


class _FailingProvider:
    def complete(self, req):  # noqa: ANN001
        raise RuntimeError("provider unavailable")


def _parse_with(provider) -> object:
    return parse_user_review_request(
        review_focus=FREE_TEXT,
        contract_type_code=NDA_CODE,
        ai_provider=provider,
        ai_model="test-model",
        ai_timeout_sec=10.0,
        ai_max_tokens=1000,
        ai_temperature=0.2,
    )


class UserReviewRequestParsingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        cls.text = FIXTURE.read_text(encoding="utf-8")
        cls.clauses, _ = extract_clauses(cls.text)
        cls.bundle = build_clause_level_result(
            service=RuleQueryService(loader),
            entity="일룸",
            contract_type="",
            text=cls.text,
            filename="NDA.docx",
            answers=None,
            review_focus=FREE_TEXT,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )

    # ── 항목 1: LLM semantic parsing ────────────────────────────────────────
    def test_ai_parses_free_text_into_structured_issues(self) -> None:
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        self.assertEqual(res.status, PARSE_STATUS_AI)
        self.assertFalse(res.degraded)
        self.assertEqual(len(res.issues), 3)
        by_id = {i.issue_id: i for i in res.issues}
        ai_issue = by_id["user_ai_secondary_use"]
        self.assertEqual(ai_issue.source, SOURCE_EXPLICIT)
        self.assertEqual(ai_issue.catalog_code, "ai_training_data_reuse")
        self.assertIn("범용 AI 모델 학습", ai_issue.normalized_issue)
        self.assertTrue(ai_issue.expected_answer)

    def test_catalog_codes_are_sent_to_the_model(self) -> None:
        stub = _StubProvider(AI_PAYLOAD)
        _parse_with(stub)
        user_msg = stub.last_request.messages[-1].content
        self.assertIn("ai_training_data_reuse", user_msg)
        self.assertIn("catalog_codes", user_msg)

    # ── 항목 4: 카탈로그에 없는 요청도 버리지 않는다 ────────────────────────
    def test_issue_outside_the_catalog_is_kept_as_custom_user_issue(self) -> None:
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        brand = next(i for i in res.issues if i.issue_id == "user_joint_brand_use")
        self.assertTrue(brand.is_custom)
        self.assertEqual(brand.catalog_code, "")
        self.assertIn("브랜드", brand.normalized_issue)

    def test_unknown_catalog_code_is_not_force_fitted(self) -> None:
        payload = [{
            "issue_id": "user_weird",
            "issue": "독특한 환수구조에 따른 반환의무",
            "original_user_text": "환수구조 봐주세요",
            "catalog_code": "totally_made_up_code",
            "search_keywords": ["환수", "반환"],
        }]
        res = _parse_with(_StubProvider(payload))
        self.assertEqual(res.issues[0].catalog_code, "")
        self.assertTrue(res.issues[0].is_custom)

    def test_keyword_fallback_keeps_uncatalogued_sentences(self) -> None:
        """AI 없이도 카탈로그에 걸리지 않는 문장을 버리지 않는다."""
        res = parse_user_review_request(review_focus=FREE_TEXT, contract_type_code=NDA_CODE)
        self.assertEqual(res.status, PARSE_STATUS_NO_AI)
        joined = " ".join(i.normalized_issue for i in res.issues)
        self.assertIn("브랜드", joined)

    # ── 항목 6: AI unavailable fallback을 정상 완료로 위장하지 않는다 ───────
    def test_no_ai_is_reported_as_degraded(self) -> None:
        res = parse_user_review_request(review_focus=FREE_TEXT, contract_type_code=NDA_CODE)
        self.assertTrue(res.degraded)
        self.assertEqual(res.to_dict()["degraded_notice"], DEGRADED_NOTICE)

    def test_ai_failure_falls_back_and_is_reported_as_degraded(self) -> None:
        res = _parse_with(_FailingProvider())
        self.assertEqual(res.status, PARSE_STATUS_AI_FAILED)
        self.assertTrue(res.degraded)
        self.assertTrue(res.issues, "fallback으로라도 쟁점은 남아야 한다")
        self.assertTrue(res.error)

    def test_malformed_ai_response_falls_back(self) -> None:
        res = _parse_with(_StubProvider("이건 JSON이 아닙니다"))
        self.assertEqual(res.status, PARSE_STATUS_AI_FAILED)
        self.assertTrue(res.degraded)

    def test_empty_review_focus_is_not_degraded(self) -> None:
        res = parse_user_review_request(review_focus="  ", contract_type_code=NDA_CODE)
        self.assertEqual(res.status, PARSE_STATUS_EMPTY)
        self.assertFalse(res.degraded)
        self.assertEqual(res.issues, [])

    # ── 항목 5: 조항번호가 없어도 추적 ──────────────────────────────────────
    def test_cited_clause_is_used_as_the_anchor(self) -> None:
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        link_clauses_to_issues(res.issues, self.clauses)
        ip = next(i for i in res.issues if i.issue_id == "user_background_ip_grab")
        paths = {
            str(getattr(c, "display_path", ""))
            for c in self.clauses
            if str(getattr(c, "clause_id", "")) in ip.relevant_clause_ids
        }
        self.assertEqual(paths, {"제8조"})

    def test_clause_is_found_without_any_clause_number(self) -> None:
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        link_clauses_to_issues(res.issues, self.clauses)
        ai_issue = next(i for i in res.issues if i.issue_id == "user_ai_secondary_use")
        self.assertEqual(ai_issue.cited_clause_paths, [])
        self.assertTrue(ai_issue.relevant_clause_ids, "조항번호 없이도 관련 조항을 찾아야 한다")

    def test_topic_absent_from_the_contract_links_to_no_clause(self) -> None:
        """계약이 전혀 다루지 않는 쟁점에는 조항이 연결되지 않아야 한다 —
        그래야 "적정"이 아니라 "사실관계 추가확인"으로 답변된다."""
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        link_clauses_to_issues(res.issues, self.clauses)
        brand = next(i for i in res.issues if i.issue_id == "user_joint_brand_use")
        self.assertEqual(brand.relevant_clause_ids, [])

    # ── 항목 3: coverage tracking ───────────────────────────────────────────
    def test_every_request_is_answered_with_an_allowed_verdict(self) -> None:
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        link_clauses_to_issues(res.issues, self.clauses)
        coverage = build_user_request_coverage(
            res.issues,
            clause_results=self.bundle.clause_results,
            clauses=self.clauses,
            catalog_answers=self.bundle.meta["mandatory_review_issues"],
        )
        self.assertEqual(len(coverage), 3)
        for row in coverage:
            with self.subTest(issue_id=row["issue_id"]):
                self.assertIn(row["review_status"], USER_REQUEST_VERDICTS)
                for key in (
                    "issue_id", "original_user_text", "normalized_issue",
                    "relevant_clause_ids", "review_status", "conclusion",
                ):
                    self.assertIn(key, row)

    def test_ungroundable_issue_is_answered_as_needs_facts_not_ok(self) -> None:
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        link_clauses_to_issues(res.issues, self.clauses)
        coverage = build_user_request_coverage(
            res.issues, clause_results=self.bundle.clause_results, clauses=self.clauses,
        )
        brand = next(r for r in coverage if r["issue_id"] == "user_joint_brand_use")
        self.assertEqual(brand["review_status"], VERDICT_NEEDS_FACTS)
        self.assertFalse(brand["needs_revision"])

    def test_cited_clause_issue_leads_with_that_clause_finding(self) -> None:
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        link_clauses_to_issues(res.issues, self.clauses)
        coverage = build_user_request_coverage(
            res.issues, clause_results=self.bundle.clause_results, clauses=self.clauses,
        )
        ip = next(r for r in coverage if r["issue_id"] == "user_background_ip_grab")
        self.assertEqual(ip["review_status"], VERDICT_NEEDS_FIX)
        self.assertEqual(
            ip["matched_finding_ids"][0], "nda_improvement_ip_assigned_to_discloser",
        )

    def test_unanswered_request_is_reported_by_the_gate(self) -> None:
        self.assertEqual(
            check_user_request_coverage([{"issue_id": "x", "review_status": ""}]), ["x"],
        )
        self.assertEqual(
            check_user_request_coverage([{"issue_id": "y", "review_status": VERDICT_NEEDS_FACTS}]), [],
        )

    # ── 항목 2: 우선순위 ────────────────────────────────────────────────────
    def test_explicit_user_request_supersedes_the_catalog_default(self) -> None:
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        self.assertEqual(
            superseded_catalog_codes(res.issues),
            {"ai_training_data_reuse", "background_ip"},
        )

    def test_pipeline_marks_superseded_catalog_entries(self) -> None:
        answers = {a["code"]: a for a in self.bundle.meta["mandatory_review_issues"]}
        # keyword fallback 경로에서도 사용자가 직접 요청한 쟁점은 승격된다.
        self.assertTrue(answers["ai_training_data_reuse"].get("superseded_by_user_request"))

    # ── 파이프라인 통합 ─────────────────────────────────────────────────────
    def test_meta_exposes_parse_result_and_coverage(self) -> None:
        meta = self.bundle.meta
        self.assertIn("user_review_request_parse", meta)
        self.assertIn("user_review_coverage", meta)
        self.assertTrue(meta["user_review_coverage"])
        self.assertTrue(meta["user_review_request_parse"]["degraded"])

    def test_review_is_not_failed_when_every_request_is_answered(self) -> None:
        self.assertIsNone(self.bundle.meta.get("review_status"))

    def test_issues_round_trip_through_meta(self) -> None:
        """다운로드 경로가 LLM 재호출 없이 쟁점을 복원할 수 있어야 한다."""
        res = _parse_with(_StubProvider(AI_PAYLOAD))
        link_clauses_to_issues(res.issues, self.clauses)
        restored = issues_from_meta(res.to_dict())
        self.assertEqual([i.issue_id for i in restored], [i.issue_id for i in res.issues])
        self.assertEqual(restored[2].cited_clause_paths, ["제8조 제3항"])
        self.assertTrue(restored[0].semantic_parsed)


if __name__ == "__main__":
    unittest.main()
