"""v14 회귀 — 우리가 수급인인 인테리어 공사도급계약(2차 본계약).

2026-09-21 지시 1~15항. 실사례(인테리어 2차 본계약)를 익명화한
`fixtures/interior_works_prime_contractor.txt` 로 고정한다. 그 검토에서
실제로 나온 오류가 여기 전부 들어 있다.

    · 기본 분류기가 인테리어 공사도급계약을 광고 콘텐츠 제작 / 시험·검사
      용역으로 읽었고, canonical_state 는 유형=자문/용역, 계열=건설로
      갈라져 있었다 (지시 1항)
    · 줄머리 상호참조("제14조 제3항 …", "제26조 제4항의 …", "제15조의 …")가
      가짜 조 제목이 되어 제5조·제8조·제14조의 본문이 다른 조의 원문으로
      둔갑했다 (지시 4항)
    · 제15조는 제9항까지인데 번호 체계 오인으로 제11항까지 만들어졌다 (4항)
    · 제21조(하도급)가 실재하는데 "재하도급 규정이 계약에 없음" (6·7항)
    · 사전질문이 IP 중심이었다 (3항)
    · 유치권 포기각서의 제출 시점이 원문에 있는데 "미특정" (10항)

AI 를 쓰지 않는다(`ai_provider=None`) — 결정적이고 무과금이다.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.construction_lien_waiver import detect_lien_waiver

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "interior_works_prime_contractor.txt"

USER_DESCRIPTION = (
    "퍼시스가 발주처로부터 인테리어 공사를 도급받아 진행하는 인테리어 공사계약서. "
    "1차 입찰 업체 선정 이후 추가적인 설계 및 공사에 대한 최종 범위 계약 진행을 다시 "
    "하게 되면서 고객사에서 최종 계약서 초안을 전달해 줌. "
    "추가적으로 유치권포기각서에 대한 내용도 요청함."
)

ANSWERS = {
    "Q-EFF-liability-exposure": "공사를 진행하면서 지출한 공사원가입니다.",
    "Q-EFF-subcontract-plan": "우리가 인테리어 공사의 일부를 재하도급 할 예정입니다.",
    "Q-EFF-delivery-acceptance": (
        "우리가 인테리어 공사를 완료하고 상대방에게 검수를 요청하고 상대방이 승인을 합니다."
    ),
}


def _text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════
# 지시 4항 — Clause Index 를 먼저 확정하고 조항번호를 지어내지 않는다
# ══════════════════════════════════════════════════════════════════════════


class ClauseIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.clauses, cls.report = extract_clauses(_text())
        cls.by_id = {c.clause_id: c for c in cls.clauses}
        cls.paths = {c.display_path for c in cls.clauses}

    def test_inline_cross_reference_is_not_an_article_heading(self) -> None:
        """줄머리 상호참조가 새 조(條)를 만들지 않는다."""
        # 제14조·제26조·제15조는 각각 제 자리에 한 번씩만 존재해야 한다.
        for article in ("14", "26", "15"):
            dupes = [
                c.clause_id for c in self.clauses
                if c.clause_id.startswith(f"KR-{article}.D")
            ]
            self.assertEqual(
                dupes, [],
                f"제{article}조가 중복 조로 갈라졌다: {dupes}",
            )

    def test_article_bodies_stay_in_their_own_article(self) -> None:
        """제8조 본문이 제26조 원문으로 표시되지 않는다."""
        art8 = "\n".join(
            c.text for c in self.clauses if str(c.article_number or "") == "8"
        )
        self.assertIn("시공상세도", art8)
        self.assertIn("하자담보책임을 면제하지 아니한다", art8)
        art26 = "\n".join(
            c.text for c in self.clauses if str(c.article_number or "") == "26"
        )
        self.assertNotIn("시공상세도를 작성하여", art26)

    def test_paragraph_numbering_matches_the_document(self) -> None:
        """제15조는 제9항까지다 — 제10항 이상은 존재하지 않는다."""
        paras = {
            int(c.paragraph_number)
            for c in self.clauses
            if str(c.article_number or "") == "15"
            and str(c.paragraph_number or "").isdigit()
        }
        self.assertEqual(max(paras), 9, f"제15조 항 번호: {sorted(paras)}")
        self.assertNotIn("제15조 제11항", " ".join(self.paths))

    def test_no_clause_text_is_lost(self) -> None:
        """번호 체계를 바꿔도 본문이 사라지지 않는다."""
        import re

        blob = re.sub(
            r"\s+", "",
            " ".join(
                f"{c.title or ''} {c.text or ''} {c.context_text or ''}"
                for c in self.clauses
            ),
        )
        # 원숫자 하위 목록이 통째로 잘려 나가던 회귀조건.
        for needle in (
            "공장동:일금사십일억일백만원정",
            "산업안전보건관리비:일금구천이백육십만원정",
            "보증서·보험증권또는필수제출서류의미제출",
        ):
            self.assertIn(needle, blob, f"본문이 사라졌다: {needle}")


# ══════════════════════════════════════════════════════════════════════════
# 지시 10항 — 유치권: 원문에 제출시점이 있으면 '미특정' 이라고 쓰지 않는다
# ══════════════════════════════════════════════════════════════════════════


class LienWaiverTest(unittest.TestCase):
    def test_submission_timing_is_quoted_from_the_contract(self) -> None:
        f = detect_lien_waiver(_text())
        self.assertTrue(f.present)
        self.assertEqual(f.submission_timing, "본 계약 체결일로부터 10일 이내")

    def test_precondition_payment_is_identified(self) -> None:
        f = detect_lien_waiver(_text())
        self.assertTrue(f.payment_precondition)
        self.assertIn("계약금", f.precondition_payments)


# ══════════════════════════════════════════════════════════════════════════
# 지시 3항 — 사전질문은 계약유형에 맞는 것만
# ══════════════════════════════════════════════════════════════════════════


class QuestionPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from runtime.questions.generator import generate_questions

        cls.questions = generate_questions(
            "주식회사 퍼시스",
            "인테리어 공사도급계약서",
            [],
            contract_text=_text(),
            review_focus=USER_DESCRIPTION,
            contract_type_code="construction",
        )
        cls.ids = [q.question_id for q in cls.questions]

    def test_construction_questions_are_asked(self) -> None:
        self.assertTrue(
            [i for i in self.ids if i.startswith("Q-CONST-")],
            f"건설 전용 질문이 하나도 없다: {self.ids}",
        )

    def test_ip_centric_question_is_not_asked(self) -> None:
        self.assertNotIn("Q-EFF-ip-scope", self.ids)

    def test_lien_waiver_is_asked_when_the_contract_has_one(self) -> None:
        self.assertIn("Q-CONST-lien-waiver", self.ids)


# ══════════════════════════════════════════════════════════════════════════
# 전체 파이프라인 (AI off)
# ══════════════════════════════════════════════════════════════════════════


class PipelineTest(unittest.TestCase):
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

    # ── 지시 1항 — Contract Model 을 한 번만 확정한다 ─────────────────────
    def test_canonical_state_is_internally_consistent(self) -> None:
        state = self.meta.get("canonical_state") or {}
        self.assertEqual(state.get("contract_type"), "construction")
        self.assertEqual(state.get("contract_type_family"), "construction_contract")
        self.assertNotIn("자문", str(state.get("contract_type_label") or ""))

    def test_contract_model_records_all_seven_axes(self) -> None:
        model = self.meta.get("contract_model") or {}
        self.assertEqual(model.get("contract_type"), "construction")
        self.assertEqual(model.get("our_role_direction"), "provider")
        self.assertEqual(model.get("counterparty_role"), "ordering_party")
        self.assertEqual(model.get("payment_direction"), "we_receive")
        self.assertIn("재하도급", str(model.get("subcontract_structure") or ""))
        self.assertEqual(model.get("ip_role"), "ancillary")
        self.assertEqual(self.meta.get("contract_model_problems"), None)

    # ── 지시 2항 — 사용자 설명을 1차 factual source 로 쓴다 ───────────────
    def test_user_description_settles_our_role(self) -> None:
        cm = self.meta.get("construction_transaction_model") or {}
        self.assertEqual(cm.get("our_role"), "contractor_with_subcontract")
        self.assertTrue(cm.get("settled"))

    # ── 지시 5항 — 조항번호 존재검증 + 의미검증 ──────────────────────────
    def test_findings_anchor_to_the_semantically_right_article(self) -> None:
        by_id = {
            str(c.get("clause_id")): str(c.get("display_path") or "")
            for c in self.findings
        }
        # 안전 책임 전가 → 안전·보건·환경 조항(제20조)
        if "CWC-07" in by_id:
            self.assertEqual(by_id["CWC-07"], "제20조", by_id["CWC-07"])
        # 공사대금 회수 사슬 → 대금의 지급 조항(제15조)
        if "CWP-PAYMENT-PACKAGE" in by_id:
            self.assertEqual(by_id["CWP-PAYMENT-PACKAGE"], "제15조")
        # 유치권 → 대금 지급의 선행조건이 걸린 조항
        if "CWC-LIEN-WAIVER" in by_id:
            self.assertEqual(by_id["CWC-LIEN-WAIVER"], "제15조")

    def test_no_finding_points_at_a_nonexistent_article(self) -> None:
        import re

        real = {
            str(c.article_number)
            for c in extract_clauses(_text())[0]
            if c.article_number
        }
        bad: list[str] = []
        for c in self.findings:
            path = str(c.get("display_path") or "")
            if "신설" in path:
                continue
            for m in re.finditer(r"제\s*(\d+)\s*조", path):
                if m.group(1) not in real:
                    bad.append(f"{c.get('clause_id')}:{path}")
        self.assertEqual(bad, [], f"존재하지 않는 조항 참조: {bad}")

    # ── 지시 6·7항 — 실재하는 보호조항을 부재로 판단하지 않는다 ──────────
    def test_existing_subcontract_clause_is_not_reported_missing(self) -> None:
        titles = " ".join(
            str(c.get("issue_title") or "") for c in self.findings
        )
        self.assertNotIn("재하도급의 허용 여부·범위와 발주자 승인 요건이 계약에 없음", titles)

    def test_absence_verification_records_what_it_removed(self) -> None:
        report = self.meta.get("absence_verification") or {}
        self.assertGreater(int(report.get("checked") or 0), 0)
        concepts = {r.get("concept") for r in (report.get("contradictions") or [])}
        # 제21조(하도급)가 실재하는데 "재하도급 규정 없음"
        self.assertIn("subcontract", concepts)
        # 제18조 제2항에 총액 10% 상한이 있는데 "지체상금 상한 부재"
        self.assertIn("delay_penalty_cap", concepts)
        self.assertEqual(
            self.meta.get("review_status"), "REVIEW_FAILED_SOURCE_CONTRADICTION",
        )

    # ── 지시 8항 — 다른 계약유형 문언 혼입 없음 ──────────────────────────
    def test_no_cross_contract_terms_survive(self) -> None:
        from runtime.review.construction_transaction_model import finding_blob

        forbidden = ("대리점", "판매장려금", "POS", "재고관리", "협찬", "숏폼", "개인정보 처리방침")
        body = _text()
        bad: list[str] = []
        for c in self.findings:
            blob = finding_blob(c)
            for term in forbidden:
                if term in blob and term not in body:
                    bad.append(f"{c.get('clause_id')}:{term}")
        self.assertEqual(bad, [], f"타 계약유형 문언 혼입: {bad}")

    # ── 지시 9항 — 핵심 Risk Package 를 cross-clause 로 연결 ──────────────
    def test_risk_packages_are_evaluated_and_linked(self) -> None:
        packages = self.meta.get("construction_risk_packages") or []
        keys = {p.get("key") for p in packages}
        self.assertEqual(
            keys, {"scope_and_change", "schedule", "security", "termination"},
        )
        links = self.meta.get("construction_risk_package_links") or {}
        self.assertEqual(links.get("uncovered"), [])

    # ── 지시 11항 — 원도급과 재하도급을 섞지 않는다 ──────────────────────
    def test_subcontract_items_are_labelled_as_a_separate_document(self) -> None:
        for c in self.findings:
            if str(c.get("clause_id") or "").startswith("CWS-0") and str(
                c.get("target_contract") or ""
            ) == "subcontract":
                self.assertIn("재하도급 계약서", str(c.get("display_path") or ""))

    # ── 지시 13항 — HIGH 는 실제 손실 기준 ────────────────────────────────
    def test_tax_topics_do_not_occupy_high(self) -> None:
        from runtime.review.internal_control_split import is_finance_confirmation_topic

        bad = [
            str(c.get("clause_id"))
            for c in self.findings
            if str(c.get("risk_tier") or "").upper() in ("HIGH", "CRITICAL")
            and is_finance_confirmation_topic(
                " ".join(
                    str(c.get(k) or "")
                    for k in ("issue_title", "problem", "rewrite_reason")
                )
            )
        ]
        self.assertEqual(bad, [], f"세무·회계 논점이 HIGH 에 있다: {bad}")

    # ── 지시 14항 — 신설은 실재하는 마지막 항 다음 번호로 ────────────────
    def test_new_paragraph_numbers_follow_the_real_structure(self) -> None:
        import re

        real_max: dict[str, int] = {}
        for c in extract_clauses(_text())[0]:
            art = str(c.article_number or "")
            pn = str(c.paragraph_number or "")
            if art and pn.isdigit():
                real_max[art] = max(real_max.get(art, 0), int(pn))
        bad: list[str] = []
        for c in self.findings:
            instruction = str((c.get("redline_instruction") or {}).get("edit_location") or "")
            m = re.search(r"제(\d+)조[^제]*제(\d+)항 뒤에 제(\d+)항 신설", instruction)
            if not m:
                continue
            art, after, new = m.group(1), int(m.group(2)), int(m.group(3))
            if art in real_max and (after != real_max[art] or new != real_max[art] + 1):
                bad.append(f"{c.get('clause_id')}: {instruction} (실제 마지막 항 {real_max[art]})")
        self.assertEqual(bad, [], f"신설 항 번호가 실제 구조와 다르다: {bad}")

    # ── 지시 15항 — 최종 전수 self-check 가 12개 축을 기록한다 ───────────
    def test_final_self_check_records_every_axis(self) -> None:
        check = self.meta.get("v14_final_self_check") or {}
        axes = {a["key"] for a in (check.get("axes") or [])}
        for key in (
            "canonical_contract_type", "party_role", "clause_exists",
            "quote_exact", "legal_effect_match", "protection_elsewhere",
            "absence_full_search", "no_contamination", "question_model_fit",
            "user_request_mapping", "high_is_core_risk", "prime_vs_subcontract",
            "risk_package_linked",
        ):
            self.assertIn(key, axes)


if __name__ == "__main__":
    unittest.main()
