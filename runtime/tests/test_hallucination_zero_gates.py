"""Hallucination Zero — 존재하지 않는 조항·문구를 만들어내지 않는지 확인한다.

2026-09-14 지시. 골든 사례는 **SNS마케팅 제휴 계약(실사례 익명화)**이다
(`fixtures/sns_marketing_partnership.txt`).

    실제 계약: 제1조 ~ 제10조
    사고 당시 결과:
        CP-006  "제12조 제3항 — 해지 시 정산 및 산출물 인도 기준 보완 필요"
                원문: "[제12조] 계약의 해제 및 해지 관련 조항"
        CP-007  "제14조 — 손해배상 범위 보완 필요"
        CP-008  "제11조 — 을의 포트폴리오·외부 공개 금지 조항 보완 필요"

제11·12·14조는 존재하지 않는다. 원인은 콘텐츠 제작 체크리스트가 표준계약서
양식의 조항번호를 상수로 들고 있다가, 실제 계약에서 그 조항을 못 찾으면
번호가 든 가짜 원문을 조립한 것이었다.

이 파일은 두 방향을 같이 본다.
  · 지어낸 참조가 결과에 남지 않는가          (본래 목적)
  · 정상 항목이 과차단되지 않는가             (이 게이트의 진짜 실패 양식)

두 번째가 특히 중요하다. 1차 구현에서 "저작권법, 제46조" 와 "부가가치세법,
제29조" 를 계약 조항으로 오인해 정상 finding 2건을 삭제했고, 조 제목 대조가
표시 문자열 전체를 제목으로 읽어 정상 finding 5건을 날렸다.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.clause_index import build_clause_index
from runtime.review.existence_gate import (
    ABSENT_CLAUSE_MARKER,
    STATUS_FAKE_QUOTE,
    STATUS_NONEXISTENT_CLAUSE,
    audit_final_references,
    enforce_existence_gate,
    enforce_title_consistency,
    verify_finding,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = FIXTURES / "sns_marketing_partnership.txt"


def _index(text: str):
    extracted = extract_clauses(text)
    clauses = extracted[0] if isinstance(extracted, tuple) else extracted
    return build_clause_index(text, clauses)


class ClauseIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = GOLDEN.read_text(encoding="utf-8")
        cls.index = _index(cls.text)

    def test_index_matches_the_real_contract(self) -> None:
        self.assertEqual(
            self.index.to_dict()["article_numbers"],
            [str(n) for n in range(1, 11)],
            "실제 계약은 제1조~제10조다",
        )
        self.assertFalse(self.index.structure_uncertain, self.index.uncertainty_reasons)

    def test_nonexistent_articles_are_reported_as_absent(self) -> None:
        for n in (11, 12, 14):
            self.assertFalse(self.index.has_article(n), f"제{n}조는 존재하지 않는다")
        self.assertTrue(self.index.has_article(10))

    def test_next_new_article_follows_the_last_one(self) -> None:
        self.assertEqual(self.index.max_article(), 10)
        self.assertEqual(self.index.next_new_article(), "11")

    def test_real_quote_passes_and_fabricated_quote_fails(self) -> None:
        real = "본 계약은 회사가 브랜드사의 마케팅을 대행함에 있어 원활한 협업을 위하여"
        self.assertTrue(self.index.quote_exists(real))
        self.assertFalse(self.index.quote_exists("[제12조] 계약의 해제 및 해지 관련 조항"))

    def test_title_is_read_from_the_contract(self) -> None:
        # 이 계약의 제9조는 "분쟁 해결 및 관할" 이다 — 표준양식의 "소유권의 귀속" 이 아니다.
        self.assertIn("분쟁", self.index.title_of(9))
        self.assertFalse(self.index.title_matches(9, "소유권의 귀속"))
        self.assertTrue(self.index.title_matches(9, "분쟁 해결 및 관할"))


class ExistenceGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = GOLDEN.read_text(encoding="utf-8")
        cls.index = _index(cls.text)

    def _cp006(self) -> dict:
        """사고 당시 CP-006 의 형태 그대로."""
        return {
            "clause_id": "CP-006",
            "risk_tier": "MEDIUM",
            "clause_ids": ["제12조 제3항"],
            "clause_titles": ["계약의 해제 및 해지(정산)"],
            "clause_title": "제12조 제3항",
            "issue_title": "제12조 제3항 — 해지 시 정산 및 산출물 인도 기준 보완 필요",
            "original_text": "[제12조] 계약의 해제 및 해지 관련 조항",
            "problem": "해지 시 정산 기준과 중간 산출물 인도 의무가 없습니다.",
            "checklist_status": "absent",
            "suggested_rewrite": "[제12조] 계약의 해제 및 해지 관련 조항 해지 사유와 절차를 정한다.",
        }

    def test_golden_fabricated_clause_is_converted_to_a_new_clause(self) -> None:
        results = [self._cp006()]
        report = enforce_existence_gate(results, self.index)

        self.assertEqual(report["status"], STATUS_NONEXISTENT_CLAUSE)
        self.assertEqual(len(results), 1, "지적 자체는 유효하므로 남아야 한다")
        cr = results[0]
        self.assertTrue(cr["is_new_clause"])
        self.assertEqual(cr["new_clause_number"], "11", "제10조 다음은 제11조다")
        self.assertEqual(cr["display_path"], "제11조 신설")
        self.assertEqual(cr["original_text"], ABSENT_CLAUSE_MARKER)
        self.assertEqual(
            cr["redline_instruction"]["edit_location"], "제10조 뒤에 제11조 신설"
        )
        self.assertEqual(cr["redline_instruction"]["edit_type"], "new_clause")

    def test_no_fabricated_article_number_survives_anywhere(self) -> None:
        results = [self._cp006()]
        enforce_existence_gate(results, self.index)
        blob = "\n".join(
            str(v) for v in results[0].values() if isinstance(v, str)
        ) + str(results[0].get("redline_instruction"))
        for n in (12, 14):
            self.assertNotIn(f"제{n}조", blob, f"제{n}조가 결과에 남았다")

    def test_new_clause_numbers_do_not_collide(self) -> None:
        a, b, c = self._cp006(), self._cp006(), self._cp006()
        b["clause_id"], c["clause_id"] = "CP-007", "CP-008"
        results = [a, b, c]
        enforce_existence_gate(results, self.index)
        numbers = [r["new_clause_number"] for r in results]
        self.assertEqual(numbers, ["11", "12", "13"], "신설 번호가 겹치면 안 된다")

    def test_statute_citation_is_not_a_contract_clause(self) -> None:
        """"저작권법, 제46조" 는 계약 조항 참조가 아니다 — 삭제하면 안 된다.

        1차 구현이 여기서 정상 finding 2건(저작권 2차활용·부가세 세금계산서)을
        통째로 지웠다.
        """
        for citation in (
            "저작권법, 제46조에 따라 2차적저작물작성권은 별도 특약이 필요합니다.",
            "부가가치세법, 제29조상 공급가액 산정 기준을 확인해야 합니다.",
            "「하도급거래 공정화에 관한 법률」 제13조를 확인하십시오.",
        ):
            cr = {
                "clause_id": "S-1", "risk_tier": "HIGH",
                "issue_title": "법령 검토",
                "legal_business_reason": citation,
            }
            self.assertEqual(
                verify_finding(cr, self.index), [],
                f"법령 인용을 계약 조항으로 오인했다: {citation}",
            )

    def test_parenthesised_structural_note_is_not_a_fake_quote(self) -> None:
        """괄호로 스스로 설명임을 밝힌 값은 인용 주장이 아니다.

        1차 구현이 이것을 가짜 인용으로 보고 원문을 비워, 그림닷컴 판매지원
        계약의 HIGH 2건 중 1건이 최종 목록에서 사라졌다.
        """
        cr = {
            "clause_id": "clr_x", "risk_tier": "HIGH",
            "issue_title": "기존 계약 연동",
            "original_text": "(계약 전체 구조 — 별도 계약이라는 형식과 실제 존속기간·해지 연동 조항)",
        }
        self.assertEqual(verify_finding(cr, self.index), [])

    def test_fabricated_quote_of_an_existing_clause_is_cleared(self) -> None:
        cr = {
            "clause_id": "AI-1", "risk_tier": "HIGH",
            "issue_title": "제5조 저작권",
            "original_text": "제5조에 따라 회사는 모든 콘텐츠의 저작권을 영구히 보유하며 제휴사는 어떠한 권리도 주장할 수 없다.",
            "problem": "권리 귀속이 일방적입니다.",
        }
        results = [cr]
        report = enforce_existence_gate(results, self.index)
        self.assertEqual(len(results), 1, "인용만 잘못됐으면 지적은 남긴다")
        self.assertEqual(results[0]["original_text"], "")
        self.assertIn(STATUS_FAKE_QUOTE, report["violations"][0]["codes"])

    def test_real_quote_is_untouched(self) -> None:
        quote = "본 계약은 회사가 브랜드사의 마케팅을 대행함에 있어 원활한 협업을 위하여 상호 권리와 의무를 명확히 규정함을 목적으로 한다."
        cr = {
            "clause_id": "KR-1", "risk_tier": "MEDIUM",
            "issue_title": "제1조 목적", "original_text": quote,
        }
        results = [cr]
        enforce_existence_gate(results, self.index)
        self.assertEqual(results[0]["original_text"], quote)


class TitleConsistencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = _index(GOLDEN.read_text(encoding="utf-8"))

    def test_wrong_title_strips_the_number_without_guessing_a_new_one(self) -> None:
        """번호는 있는데 그 조가 다른 내용이면, 번호를 떼되 **다시 지어내지 않는다**."""
        cr = {
            "clause_id": "CP-004", "risk_tier": "HIGH",
            "clause_ids": ["제9조"], "clause_titles": ["소유권의 귀속"],
            "clause_title": "제9조",
            "issue_title": "제9조 — 콘텐츠 권리 이전 범위 보완 필요",
            "problem": "권리 이전 범위가 불명확합니다.",
        }
        results = [cr]
        report = enforce_title_consistency(results, self.index)
        self.assertEqual(len(results), 1, "지적을 지우지 않는다")
        self.assertTrue(cr["clause_reference_unresolved"])
        self.assertEqual(cr["clause_title"], "조항 위치 확인 필요")
        self.assertNotIn("제9조", cr["issue_title"])
        self.assertEqual(report["unresolved"][0]["actual_titles"]["제9조"], "분쟁 해결 및 관할")

    def test_finding_that_asserts_no_title_is_not_flagged(self) -> None:
        """제목을 주장하지 않는 표시는 대조 대상이 아니다.

        1차 구현이 "제4조 제2항 — 존속조항 부재" 같은 정상 표시를 전부
        "제목 불일치" 로 판정해 5건을 날렸다.
        """
        cr = {
            "clause_id": "eb_x", "risk_tier": "MEDIUM",
            "issue_title": "제4조 제2항 — 존속조항이 없습니다",
            "display_path": "제4조 제2항",
        }
        results = [cr]
        report = enforce_title_consistency(results, self.index)
        self.assertEqual(report["unresolved"], [])
        self.assertNotIn("clause_reference_unresolved", cr)

    def test_correct_title_passes(self) -> None:
        cr = {
            "clause_id": "KR-9", "risk_tier": "MEDIUM",
            "clause_title": "제9조(분쟁 해결 및 관할)",
            "issue_title": "제9조(분쟁 해결 및 관할) — 관할 합의 확인",
        }
        results = [cr]
        self.assertEqual(enforce_title_consistency(results, self.index)["unresolved"], [])


class StructureUncertaintyTest(unittest.TestCase):
    def test_unparsable_contract_suspends_existence_judgement(self) -> None:
        """구조를 확신하지 못하면 존재/부재를 단정하지 않는다(지시 항목 9)."""
        index = build_clause_index("스캔 이미지에서 글자가 깨진 문서 ￦￦￦", [])
        self.assertTrue(index.structure_uncertain)
        self.assertTrue(index.uncertainty_reasons)
        cr = {
            "clause_id": "X", "risk_tier": "HIGH",
            "issue_title": "제99조 위반", "original_text": "존재하지 않는 인용",
        }
        results = [cr]
        report = enforce_existence_gate(results, index)
        self.assertEqual(len(results), 1, "구조 미확정 상태에서 임의로 지우면 안 된다")
        self.assertEqual(report["violations"], [])
        self.assertTrue(report["structure_uncertain"])


class GoldenPipelineTest(unittest.TestCase):
    """AI 없이 전체 파이프라인을 돌려 지어낸 조항이 남지 않는지 본다."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.rules.loader import RuleLoader
        from runtime.review.clause_level import build_clause_level_result
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.bundle = build_clause_level_result(
            service=RuleQueryService(loader),
            entity="일룸",
            contract_type="마케팅계약서",
            text=GOLDEN.read_text(encoding="utf-8"),
            filename="sns_marketing_partnership.txt",
            answers=None, review_focus=None, law_service=None,
            ai_provider=None, ai_model="", ai_timeout_sec=60.0,
            ai_max_tokens=2000, ai_temperature=0.1,
        )

    def _live(self) -> list[dict]:
        return [
            c for c in self.bundle.clause_results
            if isinstance(c, dict)
            and not c.get("dedup_suppressed") and not c.get("keep_as_is")
        ]

    def test_clause_index_is_published_in_meta(self) -> None:
        index = self.bundle.meta.get("clause_index") or {}
        self.assertEqual(index.get("article_numbers"), [str(n) for n in range(1, 11)])
        self.assertFalse(index.get("structure_uncertain"))

    def test_no_finding_cites_a_nonexistent_clause_as_existing(self) -> None:
        offenders: list[str] = []
        fields = (
            "issue_title", "clause_title", "display_path", "problem",
            "suggested_rewrite", "recommendation_text", "original_text",
        )
        statute = re.compile(r"(?:법|법률|령|규칙|약관|」|\))\s*[,、·:：]?$")
        for cr in self._live():
            for field in fields:
                value = str(cr.get(field) or "")
                for m in re.finditer(r"제\s*(\d{1,3})\s*조", value):
                    if int(m.group(1)) <= 10:
                        continue
                    if statute.search(value[max(0, m.start() - 20): m.start()].rstrip()):
                        continue
                    if "신설" in value[max(0, m.start() - 30): m.start() + 30]:
                        continue
                    offenders.append(f"{cr.get('clause_id')}/{field}: {m.group(0)}")
        self.assertEqual(offenders, [], "존재하지 않는 조항을 기존 조항처럼 인용했다")

    def test_findings_still_produced(self) -> None:
        """과차단 확인 — 게이트를 걸고도 검토 결과가 비면 안 된다."""
        final = self.bundle.meta.get("final_findings") or {}
        total = int(final.get("high_count") or 0) + int(final.get("medium_count") or 0)
        self.assertGreater(total, 0, "게이트가 결과를 통째로 지웠다")

    def test_final_reference_audit_is_clean(self) -> None:
        audit = self.bundle.meta.get("final_reference_audit") or {}
        self.assertEqual(
            audit.get("failures", []), [],
            "최종 전수검증에서 남은 지어낸 참조가 있다",
        )


if __name__ == "__main__":
    unittest.main()
