"""사용자 요청별 답변 정확도 회귀테스트 (2026-09-08 지시 항목 1).

사용자가 지적한 두 가지 실패를 모두 고정한다:

  (a) 엉뚱한 결론 — "AI 학습이 충분히 제한되었는지" 질문에 개인정보·외부
      협력업체 finding 이 딸려와 답이 오염되는 것.
  (b) 놓친 결론 — 조항 연결이 엉뚱한 조문을 가리켜, 계약 어딘가에 있는
      같은 주제의 HIGH finding 을 못 찾고 "적정" 으로 답하는 것.
      (실측: 범용 AI 학습 질문 → 제4조 제1항 HIGH 가 있는데도 "적정")

또한 답변 구조가 original_user_text → relevant_clause → direct_answer 로
항상 채워지는지 확인한다.
"""
from __future__ import annotations

import unittest

from runtime.review.mandatory_review_issues import (
    VERDICT_NEEDS_FIX,
    VERDICT_OK,
)
from runtime.review.user_review_request import (
    VERDICT_NEEDS_FACTS,
    UserReviewIssue,
    build_user_request_coverage,
)


class _Clause:
    def __init__(self, clause_id: str, display_path: str) -> None:
        self.clause_id = clause_id
        self.display_path = display_path


CLAUSES = [
    _Clause("c2", "제2조"),
    _Clause("c4_1", "제4조 제1항"),
    _Clause("c4_3", "제4조 제3항"),
    _Clause("c4", "제4조"),
]

FINDING_AI = {
    "clause_id": "f_ai", "display_path": "제4조 제1항", "article_number": "4",
    "risk_tier": "HIGH",
    "issue_title": "범용 AI 모델 학습·개선 및 타 프로젝트 활용 제한이 명시되어 있지 않음",
    "rewrite_reason": "제공 데이터를 범용 모델 학습에 제한 없이 이용할 수 있다",
}
FINDING_PD = {
    "clause_id": "f_pd", "display_path": "제4조", "article_number": "4",
    "risk_tier": "HIGH",
    "issue_title": "실제 이용자 개인정보 처리에 대한 별도 계약 유보 조항이 없음",
    "rewrite_reason": "음성정보·수면정보 등 민감정보 처리 경계가 없다",
}
FINDING_RECIPIENT = {
    "clause_id": "f_rs", "display_path": "제4조 제3항", "article_number": "4",
    "risk_tier": "MEDIUM",
    "issue_title": "외부 협력업체에 대한 정보제공 범위가 불명확",
    "rewrite_reason": "협력업체 제3자 제공 기준이 없다",
}
ALL_FINDINGS = [FINDING_AI, FINDING_PD, FINDING_RECIPIENT]


def _issue(issue_id: str, text: str, *, clause_ids: list[str] | None = None,
           semantic: bool = True) -> UserReviewIssue:
    return UserReviewIssue(
        issue_id=issue_id,
        source="explicit_user_request",
        original_user_text=text,
        normalized_issue=text,
        relevant_clause_ids=list(clause_ids or []),
        semantic_parsed=semantic,
    )


def _cov(issue: UserReviewIssue) -> dict:
    out = build_user_request_coverage(
        [issue], clause_results=ALL_FINDINGS, clauses=CLAUSES,
    )
    return out[0]


class AnswerAccuracyTest(unittest.TestCase):
    def test_ai_training_question_is_not_contaminated(self) -> None:
        """(a) AI 학습 질문에 개인정보·협력업체 finding 이 섞이면 안 된다."""
        r = _cov(_issue("q_ai", "자사 범용 모델 개선이나 타 프로젝트 활용이 제한되는지",
                        clause_ids=["c4", "c4_1", "c4_3"]))
        self.assertEqual(r["issue_topic"], "ai_training")
        self.assertEqual(r["matched_finding_ids"], ["f_ai"])
        self.assertNotIn("f_pd", r["matched_finding_ids"])
        self.assertNotIn("f_rs", r["matched_finding_ids"])
        self.assertNotIn("개인정보", r["direct_answer"])
        self.assertNotIn("협력업체", r["direct_answer"])

    def test_personal_data_question_is_not_contaminated(self) -> None:
        r = _cov(_issue("q_pd", "실제 사용자의 음성정보·수면정보 처리 경계가 있는지",
                        clause_ids=["c4", "c4_1", "c4_3"]))
        self.assertEqual(r["issue_topic"], "personal_data")
        self.assertEqual(r["matched_finding_ids"], ["f_pd"])
        self.assertNotIn("범용", r["direct_answer"])

    def test_recipient_scope_question_is_not_contaminated(self) -> None:
        r = _cov(_issue("q_rs", "외부 협력업체에 정보를 제공할 수 있는 범위가 적절한지",
                        clause_ids=["c4", "c4_1", "c4_3"]))
        self.assertEqual(r["issue_topic"], "recipient_scope")
        self.assertEqual(r["matched_finding_ids"], ["f_rs"])

    def test_topic_match_survives_wrong_clause_linkage(self) -> None:
        """(b) 조항 연결이 제2조를 가리켜도 제4조 제1항 HIGH 를 찾아야 한다."""
        r = _cov(_issue("q_ai2", "범용 모델 학습에 우리 데이터가 쓰이지 않도록 제한되었는지",
                        clause_ids=["c2"]))
        self.assertEqual(r["review_status"], VERDICT_NEEDS_FIX,
                         "계약서가 정반대를 말하는데 '적정'으로 답했다")
        self.assertEqual(r["matched_finding_ids"], ["f_ai"])
        self.assertIn("제4조 제1항", r["relevant_clause"])

    def test_answer_structure_is_always_complete(self) -> None:
        """original_user_text → relevant_clause → direct_answer 3필드 필수."""
        for issue in (
            _issue("a", "범용 모델 학습 제한 여부", clause_ids=["c4_1"]),
            _issue("b", "존재하지 않는 쟁점에 대한 질문입니다", clause_ids=[]),
        ):
            r = _cov(issue)
            for key in ("original_user_text", "relevant_clause", "direct_answer"):
                self.assertTrue(str(r.get(key) or "").strip(), f"{issue.issue_id}: {key} 비어 있음")

    def test_ungrounded_question_says_needs_facts_not_ok(self) -> None:
        r = _cov(_issue("q_none", "본 계약의 준거법이 우리에게 유리한지", clause_ids=[]))
        self.assertEqual(r["review_status"], VERDICT_NEEDS_FACTS)
        self.assertEqual(r["relevant_clause"], "해당 조항 없음")

    def test_direct_answer_leads_with_a_real_answer(self) -> None:
        """'수정 필요'만 던지지 않고 예/아니요로 시작해야 한다."""
        r = _cov(_issue("q_ai3", "범용 모델 학습이 제한되는지", clause_ids=["c4_1"]))
        self.assertTrue(r["direct_answer"].startswith("아니요"), r["direct_answer"])

    def test_relevant_clause_lists_only_the_answering_clause(self) -> None:
        """결론과 무관한 조항을 '관련 조항'으로 열거하지 않는다."""
        r = _cov(_issue("q_ai4", "범용 모델 학습 제한", clause_ids=["c2", "c4", "c4_1", "c4_3"]))
        self.assertEqual(r["answer_clause_paths"], ["제4조 제1항"])

    def test_ok_verdict_when_topic_has_no_finding(self) -> None:
        """관련 조항은 있고 그 주제의 finding 이 없으면 '적정'이 맞다."""
        r = _cov(_issue("q_term", "비밀유지기간이 적절한지", clause_ids=["c2"]))
        self.assertEqual(r["review_status"], VERDICT_OK)
        self.assertEqual(r["matched_finding_ids"], [])


if __name__ == "__main__":
    unittest.main()
