"""v16 회귀 — 이미 수정된 안을 존중하는 검토(KEEP 우선 / 과수정 방지).

2026-09-21 3차 지시 —
  "사업부가 1차로 수정한 부분에 대해서 무조건 검토하지 말고 맞는지 틀린지
   판단하고, 검토한 부분이 맞으면 또 똑같이 수정하지 않는 로직."

골든 사례: ILOOM × DewertOkin 기술협업 NDA 수정안(실사례, fixture 는 익명화).
사업부가 워드 주석 18건을 달아 1차 수정한 문서이고, 검토요청서에는 번호
매긴 요청사항 8개가 있다.
"""
from __future__ import annotations

import unittest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mutual_nda_revised_draft.txt"
NOTES_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mutual_nda_revision_notes.txt"

REVIEW_FOCUS = """상대방이 제공한 NDA 초안을 바탕으로 당사의 협업 구조와 보호 필요사항을 반영한 수정안을 작성했습니다. 현재는 정식 공동개발 착수 전이며 구체적 개발범위·비용·일정·성과물 소유권은 추후 별도 기술개발계약에서 정할 예정입니다.
요청사항
1. 국내 개발사 등 제3자에게 기술정보를 공유할 수 있도록 한 조항의 적정성
2. 상대방 핵심기술에 대한 사전승인 범위가 과도하지 않은지 여부
3. 기존 보유기술과 공동·신규 개발성과의 권리구분이 적절한지 여부
4. 당사의 독자개발 및 다른 업체와의 협업을 제한하지 않는지 여부
5. 비밀유지기간 및 손해배상 범위의 적정성
6. 개인정보·수면데이터 관련 별도 계약 규정의 충분성
7. 대한민국법 및 KCAB 국제중재 조항의 적정성과 중국 내 집행 가능성
8. 국문·영문·중문 계약서 간 내용의 일치 여부 및 영문본 우선 조항의 적정성"""


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _notes() -> list[str]:
    return [b for b in NOTES_FIXTURE.read_text(encoding="utf-8").split("\n\n") if b.strip()]


# ══════════════════════════════════════════════════════════════════════════
# 요청사항 파싱 — 번호 목록은 번호로 나눈다 (지시 5항)
# ══════════════════════════════════════════════════════════════════════════


class NumberedRequestParsingTest(unittest.TestCase):
    def test_eight_requests_are_parsed_as_eight(self) -> None:
        from runtime.review.user_request_answers import parse_numbered_requests

        items = parse_numbered_requests(REVIEW_FOCUS)
        self.assertEqual([i for i, _ in items], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertIn("제3자", items[0][1])
        self.assertIn("영문본", items[7][1])

    def test_prose_without_a_numbered_list_yields_nothing(self) -> None:
        from runtime.review.user_request_answers import parse_numbered_requests

        self.assertEqual(
            parse_numbered_requests("이 계약을 전반적으로 검토해 주세요. 특히 대금 부분이요."),
            [],
        )

    def test_incidental_numbers_in_prose_are_not_requests(self) -> None:
        from runtime.review.user_request_answers import parse_numbered_requests

        self.assertEqual(
            parse_numbered_requests("2026년 2. 27. 체결한 계약입니다.\n3. 그 뒤 변경했습니다."),
            [],
        )


# ══════════════════════════════════════════════════════════════════════════
# 수정 메모 인식 (지시 1항)
# ══════════════════════════════════════════════════════════════════════════


class PriorRevisionStateTest(unittest.TestCase):
    def test_word_comments_are_parsed_into_notes(self) -> None:
        from runtime.review.prior_revision_state import build_prior_revision_state

        state = build_prior_revision_state(
            margin_annotations=_notes(), user_description=REVIEW_FOCUS,
        )
        self.assertTrue(state.is_revised_draft)
        self.assertGreaterEqual(len(state.notes), 10)
        markers = {n.marker for n in state.notes}
        self.assertIn("ILOOM3", markers)

    def test_plain_draft_is_not_treated_as_revised(self) -> None:
        from runtime.review.prior_revision_state import build_prior_revision_state

        state = build_prior_revision_state(
            margin_annotations=None, user_description="이 계약서를 검토해 주세요.",
        )
        self.assertFalse(state.is_revised_draft)

    def test_high_findings_are_never_kept_by_a_memo(self) -> None:
        from runtime.review.prior_revision_state import (
            apply_prior_revision_keep,
            build_prior_revision_state,
        )

        state = build_prior_revision_state(margin_annotations=_notes())
        rows = [{
            "clause_id": "X", "article_number": "5", "display_path": "제5조",
            "issue_title": "제3자 제공 범위가 불명확",
            "risk_tier": "HIGH", "severity": "HIGH",
        }]
        report = apply_prior_revision_keep(rows, state, clauses=None)
        self.assertEqual(report.kept, [])
        self.assertFalse(rows[0].get("keep_as_is"))


# ══════════════════════════════════════════════════════════════════════════
# 과수정 방지 (지시 4항)
# ══════════════════════════════════════════════════════════════════════════


class OvercorrectionGuardTest(unittest.TestCase):
    def test_proposal_that_narrows_our_freedom_is_withdrawn(self) -> None:
        from runtime.review.overcorrection_guard import guard_overcorrection

        rows = [{
            "clause_id": "Y", "article_number": "5", "display_path": "제5조",
            "issue_title": "제3자 제공 범위",
            "risk_tier": "MEDIUM", "severity": "MEDIUM",
            "original_text": (
                "수령자는 본 프로젝트 수행에 필요한 범위에서 계열회사, 임직원, 전문자문기관 및 "
                "개발·시험·인증 협력업체에 비밀정보를 제공할 수 있다. 다만 공개자가 서면으로 "
                "핵심기술정보라고 지정한 자료는 그러하지 아니하다."
            ),
            "suggested_rewrite": (
                "수령자는 공개자의 사전 서면 승인 없이 어떠한 제3자에게도 비밀정보를 제공하여서는 "
                "아니 된다. 제3자에게 제공하려면 매 건마다 사전 서면 동의를 받아야 하며, 위반 시 "
                "수령자가 모든 책임을 부담한다."
            ),
            "problem": "제3자 제공 범위가 넓다",
        }]
        report = guard_overcorrection(rows)
        self.assertEqual(len(report.withdrawn), 1)
        self.assertTrue(rows[0]["keep_as_is"])
        self.assertEqual(rows[0]["suggested_rewrite"], "")

    def test_mandatory_law_fix_is_not_blocked(self) -> None:
        from runtime.review.overcorrection_guard import guard_overcorrection

        rows = [{
            "clause_id": "Z", "article_number": "7", "display_path": "제7조",
            "risk_tier": "HIGH", "severity": "HIGH",
            "original_text": "수령자는 어떠한 경우에도 손해를 배상하지 아니한다. " * 2,
            "suggested_rewrite": (
                "수령자는 고의 또는 중과실로 인한 손해에 대하여 책임을 부담한다. 이를 배제하는 "
                "약정은 약관규제법상 무효이므로 삭제하여야 한다. 수령자는 법령이 정한 범위에서 "
                "배상하여야 한다."
            ),
            "problem": "약관규제법상 무효인 전부면책 조항",
        }]
        report = guard_overcorrection(rows)
        self.assertEqual(report.withdrawn, [])

    def test_unanchored_finding_is_skipped(self) -> None:
        """현재 문구를 특정할 수 없으면 유불리를 따지지 않는다."""
        from runtime.review.overcorrection_guard import guard_overcorrection

        rows = [{
            "clause_id": "W", "display_path": "조항 위치 확인 필요",
            "clause_reference_unresolved": True,
            "risk_tier": "MEDIUM", "severity": "MEDIUM",
            "original_text": "가" * 80,
            "suggested_rewrite": (
                "상대방은 지연이자를 지급하여야 하며, 사전 서면 승인을 받아야 하고, "
                "책임을 부담한다. 통지하여야 한다."
            ),
        }]
        report = guard_overcorrection(rows)
        self.assertEqual(report.withdrawn, [])


# ══════════════════════════════════════════════════════════════════════════
# 전체 파이프라인 (AI off)
# ══════════════════════════════════════════════════════════════════════════


class RevisedNdaPipelineTest(unittest.TestCase):
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
        cls.findings = [
            c for c in cls.bundle.clause_results
            if isinstance(c, dict) and not c.get("dedup_suppressed")
        ]

    # ── 지시 5항 — 요청사항마다 직접 답한다 ──────────────────────────────
    def test_every_request_gets_a_direct_answer(self) -> None:
        answers = self.meta.get("user_request_answers") or []
        self.assertEqual(len(answers), 8, f"8개 요청에 대한 답이 아니다: {len(answers)}")
        self.assertEqual([a["index"] for a in answers], list(range(1, 9)))
        for a in answers:
            self.assertIn(a["verdict"], ("KEEP", "SUPPLEMENT", "SEPARATE", "NEEDS_FACTS"))
            self.assertTrue(a["reason"].strip(), f"{a['index']}번 답변에 이유가 없다")

    def test_multilingual_question_is_not_answered_as_if_compared(self) -> None:
        """지시 9항 — 없는 언어본을 비교한 것처럼 쓰지 않는다."""
        answers = {a["index"]: a for a in (self.meta.get("user_request_answers") or [])}
        eighth = answers.get(8)
        self.assertIsNotNone(eighth)
        self.assertEqual(eighth["verdict"], "NEEDS_FACTS")
        self.assertIn("비교할 수 없", eighth["reason"])

    def test_enforceability_question_is_answered_beyond_the_clause(self) -> None:
        """지시 8항 — KCAB 조항을 다시 쓰는 것으로 끝내지 않는다."""
        answers = {a["index"]: a for a in (self.meta.get("user_request_answers") or [])}
        seventh = answers.get(7)
        self.assertIsNotNone(seventh)
        self.assertIn("집행", seventh["reason"])
        self.assertTrue(
            any(k in seventh["reason"] for k in ("뉴욕협약", "승인·집행", "집행지")),
            seventh["reason"],
        )

    # ── 지시 2·3항 — 이미 있는 보호장치를 누락으로 판단하지 않는다 ───────
    def test_existing_reservation_clause_is_not_reported_missing(self) -> None:
        titles = " ".join(
            str(c.get("issue_title") or "") for c in self.findings
        )
        self.assertNotIn("유보되어 있지 않", titles)
        self.assertNotIn("우선순위가 정해져 있지 않", titles)

    def test_absence_verification_recorded_the_removals(self) -> None:
        report = self.meta.get("absence_verification") or {}
        concepts = {r.get("concept") for r in (report.get("removed") or [])}
        self.assertIn("foreground_ip_reservation", concepts)

    # ── 지시 1항 — 이미 수정된 안임을 인식한다 ──────────────────────────
    def test_prior_revision_is_recognised(self) -> None:
        state = self.meta.get("prior_revision_state") or {}
        self.assertTrue(state.get("is_revised_draft"))
        self.assertGreaterEqual(int(state.get("note_count") or 0), 10)

    # ── 지시 12항 — HIGH/MEDIUM 과잉생성 금지 ───────────────────────────
    def test_no_high_findings_on_an_already_balanced_draft(self) -> None:
        high = [
            c for c in self.findings
            if str(c.get("risk_tier") or "").upper() in ("HIGH", "CRITICAL")
        ]
        self.assertEqual(
            [c.get("clause_id") for c in high], [],
            "이미 균형 잡힌 수정안에 치명적 문제를 만들어 냈다",
        )


if __name__ == "__main__":
    unittest.main()
