"""당사자 법인명 정정 회귀테스트 (2026-09-29 지시).

  · 알로소는 주식회사 시디즈의 브랜드 — "주식회사 알로소" → "주식회사 시디즈"
  · 슬로우는 주식회사 일룸의 브랜드 — "주식회사 슬로우" → "주식회사 일룸"
  · 퍼시스그룹·FURSYS GROUP 은 법적 엔터티가 아니다 → 실제 계약 주체 법인

실측으로 잡힌 함정도 함께 고정한다.
  1. 오기는 대개 조항 밖(전문·서명란)에 있다 — 조항만 보면 놓친다.
  2. 전문 줄의 id 를 "line_3" 으로 두면 제1~3조 보호 게이트가 제3조로 읽어
     수정안을 지웠다.
  3. 같은 issue_title 은 output_filter 가 한 건으로 병합해, 전문과 서명란의
     같은 오기 중 하나만 남았다.
  4. 관할 조항에 붙은 서명란의 정정이 관할 보정 게이트에서 KEEP 로 떨어졌다.
"""
from __future__ import annotations

import http.client
import json
import logging
import threading
import unittest
import zipfile
from io import BytesIO

from runtime.review.entity_name_correction import (
    build_name_correction_findings,
    correct_entity_names,
    find_name_hits,
)
from runtime.review.group_entities import resolve_entity

CONTRACT = """물품공급계약서

주식회사 알로소(이하 "갑"이라 한다)와 주식회사 한빛목재(이하 "을"이라 한다)는 다음과 같이 물품공급계약을 체결한다.

제1조 (목적)
본 계약은 을이 갑에게 가구용 목재를 공급하고, 갑이 그 대금을 지급하는 데 필요한 사항을 정함을 목적으로 한다.

제2조 (납품)
① 을은 갑이 지정한 장소에 발주서에 기재된 기일까지 물품을 납품한다.
② 갑은 납품일로부터 7일 이내에 검수를 완료한다.

제3조 (대금 지급)
갑은 검수 완료 후 다음 달 말일까지 을에게 물품대금을 현금으로 지급한다.

제4조 (계약기간)
본 계약의 기간은 계약 체결일로부터 1년으로 하며, 퍼시스그룹과 을이 별도로 합의하는 경우 연장할 수 있다.

제5조 (관할)
본 계약에 관한 분쟁은 서울중앙지방법원을 관할법원으로 한다.

2026년 9월 29일

갑: 주식회사 알로소 대표이사 (인)
을: 주식회사 한빛목재 대표이사 (인)
"""


class NameRuleTest(unittest.TestCase):
    def test_brand_with_corporate_marker_is_corrected(self) -> None:
        cases = {
            "주식회사 알로소": "주식회사 시디즈",
            "㈜알로소": "주식회사 시디즈",
            "(주) 알로소": "주식회사 시디즈",
            "알로소 주식회사": "주식회사 시디즈",
            "주식회사 슬로우": "주식회사 일룸",
            "㈜ 슬로우": "주식회사 일룸",
            "주식회사 데스커": "주식회사 일룸",
            "㈜데스커": "주식회사 일룸",
            "데스커 주식회사": "주식회사 일룸",
            "DESKER Co., Ltd.": "Iloom Inc.",
            "ALLOSO Co., Ltd.": "Sidiz Inc.",
            "SLOU Inc.": "Iloom Inc.",
        }
        for wrong, right in cases.items():
            self.assertEqual(correct_entity_names(wrong), right, wrong)

    def test_brand_in_party_definition_is_corrected(self) -> None:
        self.assertEqual(
            # 브랜드는 정의 괄호 안에 보조 표기로 남긴다(2026-09-29 Entity Resolution 4항).
            correct_entity_names('알로소(이하 "갑")는'), '주식회사 시디즈(브랜드명: 알로소, 이하 "갑")는',
        )

    def test_brand_itself_is_not_wrong(self) -> None:
        """상품·매장을 가리키는 브랜드명은 그대로 둔다."""
        for ok in (
            "알로소 매장에서 판매한다", "슬로우 매트리스", "슬로우베드 제품",
            "주식회사 슬로우베드", "www.alloso.co.kr", "the slouch position",
            "데스커 라운지 대구", "DESKER MATE 위탁거래", "주식회사 퍼시스데스커드림센터",
        ):
            self.assertEqual(correct_entity_names(ok), ok, ok)

    def test_group_name_as_party_is_corrected(self) -> None:
        self.assertEqual(correct_entity_names('퍼시스그룹(이하 "갑")'), '주식회사 퍼시스(이하 "갑")')
        self.assertEqual(correct_entity_names("퍼시스 그룹과 을은"), "주식회사 퍼시스와 을은")
        self.assertEqual(correct_entity_names('FURSYS GROUP ("Company")'), 'Fursys Inc. ("Company")')

    def test_group_name_follows_the_contracting_affiliate(self) -> None:
        """검토 요청 계열사가 일룸이면 그룹명은 주식회사 일룸으로 고친다."""
        self.assertEqual(
            correct_entity_names("퍼시스그룹이 정한", entity="일룸"), "주식회사 일룸이 정한",
        )

    def test_descriptive_group_phrase_is_kept(self) -> None:
        for ok in ("퍼시스그룹 계열사", "퍼시스그룹사 임직원", "퍼시스 그룹 내 모든 회사",
                   "Fursys Group affiliates"):
            self.assertEqual(correct_entity_names(ok), ok, ok)

    def test_particle_follows_the_new_name(self) -> None:
        cases = {
            "주식회사 슬로우는": "주식회사 일룸은",
            "주식회사 슬로우가 ": "주식회사 일룸이 ",
            "주식회사 슬로우로": "주식회사 일룸으로",
            "퍼시스그룹을": "주식회사 퍼시스를",
            "퍼시스그룹으로": "주식회사 퍼시스로",
        }
        for wrong, right in cases.items():
            self.assertEqual(correct_entity_names(wrong), right, wrong)

    def test_brand_resolves_to_owner_entity(self) -> None:
        self.assertEqual(resolve_entity("알로소").key, "sidiz")
        self.assertEqual(resolve_entity("슬로우").key, "iloom")
        self.assertEqual(resolve_entity("데스커").key, "iloom")
        self.assertEqual(resolve_entity("DESKER").key, "iloom")

    def test_message_names_the_brand_actually_used(self) -> None:
        """일룸은 브랜드가 둘이다 — 메시지에 실제로 쓰인 브랜드를 적는다."""
        out = build_name_correction_findings([], full_text="주식회사 데스커(이하 \"갑\")", entity="일룸")
        self.assertIn("데스커는 주식회사 일룸의 브랜드", out[0]["problem"])
        self.assertIn("'주식회사 일룸'으로", out[0]["problem"])

    def test_correct_names_are_not_hits(self) -> None:
        self.assertEqual(find_name_hits("주식회사 퍼시스, 주식회사 시디즈, 주식회사 일룸"), [])


class FindingBuilderTest(unittest.TestCase):
    def test_preamble_and_signature_outside_clauses_are_covered(self) -> None:
        clauses = [{"clause_id": "KR-4", "title": "계약기간", "article_number": "4",
                    "text": ("본 계약의 기간은 계약 체결일로부터 1년으로 하며, 퍼시스그룹과 "
                             "을이 별도로 합의하는 경우 연장할 수 있다.")}]
        out = build_name_correction_findings(clauses, full_text=CONTRACT, entity="시디즈")
        by_id = {f["clause_id"]: f for f in out}
        self.assertIn("ENTITY_NAME__KR-4", by_id)
        blocks = [f for f in out if "party_block" in f["clause_id"]]
        self.assertEqual(len(blocks), 2)  # 전문 + 서명란
        for f in blocks:
            # 숫자가 있으면 조문 번호로 읽혀 제1~3조 보호 게이트에 걸린다.
            self.assertNotRegex(f["clause_id"], r"\d")
        for f in out:
            self.assertTrue(f["suggested_rewrite"])
        titles = [f["detected_issue_list"][0]["issue_title"] for f in out]
        self.assertEqual(len(titles), len(set(titles)), "issue_title 이 같으면 병합된다")


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)
        logging.disable(logging.CRITICAL)
        try:
            res = build_clause_level_result(
                service=cls.service, entity="시디즈", contract_type="", text=CONTRACT,
                filename="물품공급계약서.docx", answers={}, law_service=None, ai_provider=None,
                ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
            )
        finally:
            logging.disable(logging.NOTSET)
        cls.results = res.clause_results
        cls.meta = res.meta

    def _fixes(self) -> list[dict]:
        return [c for c in self.results if c.get("is_entity_name_correction")]

    def test_every_occurrence_survives_as_a_medium_rewrite(self) -> None:
        fixes = self._fixes()
        self.assertEqual(len(fixes), 3, [f["clause_id"] for f in fixes])
        for f in fixes:
            self.assertEqual(f["risk_tier"], "MEDIUM", f["clause_id"])
            self.assertFalse(f.get("dedup_suppressed"), f["clause_id"])
            self.assertFalse(f.get("keep_as_is"), f["clause_id"])
            self.assertTrue(f.get("suggested_rewrite"), f["clause_id"])

    def test_rewrites_carry_the_legal_name(self) -> None:
        joined = "\n".join(f["suggested_rewrite"] for f in self._fixes())
        self.assertIn('주식회사 시디즈(브랜드명: 알로소, 이하 "갑"', joined)
        self.assertIn("갑: 주식회사 시디즈 대표이사", joined)
        self.assertIn("주식회사 시디즈와 을이", joined)

    def test_no_surviving_rewrite_keeps_a_wrong_name(self) -> None:
        for c in self.results:
            if c.get("dedup_suppressed"):
                continue
            sr = c.get("suggested_rewrite")
            if isinstance(sr, str) and sr:
                self.assertEqual(find_name_hits(sr, entity="시디즈"), [], c.get("clause_id"))

    def test_meta_records_corrections(self) -> None:
        self.assertEqual(len(self.meta["entity_name_corrections"]["findings"]), 3)


class DownloadTest(unittest.TestCase):
    """앱의 '수정본 생성하기' 와 같은 HTTP 경로 — 다운로드가 깨지지 않아야 한다."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.api.server import build_httpd
        from runtime.questions.storage import create_session
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)
        cls.httpd = build_httpd("127.0.0.1", 0, cls.service)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        doc = create_session(
            cls.service, entity="시디즈", contract_type="", filename="물품공급계약서.docx",
            extraction={}, text=CONTRACT, classification={},
        )
        cls.session_id = doc["session_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def _download(self, fmt: str) -> bytes:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        conn.request(
            "POST", f"/api/revision/download_{fmt}",
            body=json.dumps({"session_id": self.session_id, "rebuild": True,
                             "ai_mode": "off", "law_mode": "off"}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        if resp.status != 200:
            self.fail(f"{fmt} 생성 실패 status={resp.status}: {body[:600]!r}")
        return body

    def test_docx_contains_the_corrected_name(self) -> None:
        body = self._download("docx")
        with zipfile.ZipFile(BytesIO(body)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("주식회사 시디즈", xml)
        self.assertIn("법인명 오기", xml)

    def test_pdf_succeeds(self) -> None:
        self.assertTrue(self._download("pdf").startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
