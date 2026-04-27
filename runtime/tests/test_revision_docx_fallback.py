from __future__ import annotations

import unittest
import zipfile
from io import BytesIO

from runtime.review.docx_writer import build_revision_docx


class RevisionDocxFallbackTest(unittest.TestCase):
    def test_docx_generated_when_no_clause_results(self) -> None:
        docx_bytes = build_revision_docx(
            entity="일룸/데스커",
            contract_type="앱개발/소프트웨어개발/SI/유지보수/SaaS",
            filename="app_dev.docx",
            original_clauses=[{"clause_id": "KR-000", "article_number": "", "clause_title": "(전체)", "text": "앱 개발 계약. 산출물 소스코드 검수 SLA 유지보수 개인정보 재위탁 종료 인수인계."}],
            clause_results=[],
            review_summary={"issue_count": 0},
            law_search={"results": {"laws": [{"title": "민법"}], "precedents": [], "interpretations": []}},
            questions=[{"question_id": "Q-1", "title": "검수 기준이 있나요?"}],
        )
        self.assertTrue(docx_bytes)
        z = zipfile.ZipFile(BytesIO(docx_bytes))
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        self.assertIn("핵심 쟁점 요약", xml)
        self.assertIn("검토된 주요 조항", xml)
        self.assertIn("수정 권고 조항", xml)
        self.assertIn("관련 법령", xml)
        self.assertIn("추가 확인 필요 질문", xml)


if __name__ == "__main__":
    unittest.main()

