"""인테리어 2차 본계약(수급인) 수정본 다운로드 e2e — v14.

[[feedback_do_not_break_revision_download]] — 검토 경로를 건드리면 DOCX/PDF
다운로드 e2e 를 반드시 돌린다. v14 는 새 상태 코드 네 개
(SOURCE_CONTRADICTION / CROSS_CONTRACT_CONTAMINATION /
QUESTION_MODEL_MISMATCH / USER_REQUEST_MAPPING_MISMATCH)를 세우므로,
그 코드들이 전달을 막지 않는지 앱과 같은 HTTP 경로로 확인한다.

`ai_mode=off` 로 결정적·무과금이다.
"""
from __future__ import annotations

import http.client
import json
import threading
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from runtime.api.server import build_httpd
from runtime.questions.storage import create_session
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService
from runtime.tests.test_interior_prime_contractor_review import (
    FIXTURE,
    USER_DESCRIPTION,
)


class InteriorPrimeContractorDownloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)
        cls.httpd = build_httpd("127.0.0.1", 0, cls.service)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

        doc = create_session(
            cls.service,
            entity="주식회사 퍼시스",
            contract_type="인테리어 공사도급계약서",
            filename="계약_인테리어_본계약_퍼시스_초안.pdf",
            extraction={},
            text=Path(FIXTURE).read_text(encoding="utf-8"),
            classification={},
        )
        cls.session_id = doc["session_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def _post(self, path: str, payload: dict):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=180)
        conn.request(
            "POST", path,
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp, body

    def test_docx_download_succeeds(self) -> None:
        resp, body = self._post(
            "/api/revision/download_docx",
            {
                "session_id": self.session_id,
                "rebuild": True,
                "ai_mode": "off",
                "review_focus": USER_DESCRIPTION,
            },
        )
        if resp.status != 200:
            self.fail(f"수정본(docx) 생성 실패 status={resp.status}: {body[:800]!r}")
        self.assertGreater(len(body), 1000, "docx 가 비어 있다")
        with zipfile.ZipFile(BytesIO(body)) as z:
            self.assertIn("word/document.xml", z.namelist())

    def test_pdf_download_succeeds(self) -> None:
        resp, body = self._post(
            "/api/revision/download_pdf",
            {
                "session_id": self.session_id,
                "rebuild": True,
                "ai_mode": "off",
                "review_focus": USER_DESCRIPTION,
            },
        )
        if resp.status != 200:
            self.fail(f"수정본(pdf) 생성 실패 status={resp.status}: {body[:800]!r}")
        self.assertTrue(body.startswith(b"%PDF"), "PDF 헤더가 아니다")

    def test_new_v14_statuses_do_not_block_delivery(self) -> None:
        """새 상태 코드 네 개가 전달을 막지 않는다."""
        from runtime.review.delivery_gate import NON_REMEDIABLE_STATUSES

        for code in (
            "REVIEW_FAILED_SOURCE_CONTRADICTION",
            "REVIEW_FAILED_CROSS_CONTRACT_CONTAMINATION",
            "REVIEW_FAILED_QUESTION_MODEL_MISMATCH",
            "REVIEW_FAILED_USER_REQUEST_MAPPING_MISMATCH",
        ):
            self.assertNotIn(code, NON_REMEDIABLE_STATUSES)

    def test_document_uses_real_clause_numbers(self) -> None:
        """문서 본문에 존재하지 않는 조항번호가 실리지 않는다.

        이 계약은 제27조까지다. 제15조는 제9항까지다.
        """
        import re
        import tempfile

        from runtime.review.text_extract import extract_text_from_file

        resp, body = self._post(
            "/api/revision/download_docx",
            {
                "session_id": self.session_id,
                "rebuild": True,
                "ai_mode": "off",
                "review_focus": USER_DESCRIPTION,
            },
        )
        self.assertEqual(resp.status, 200, body[:400])
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as fh:
            fh.write(body)
            path = Path(fh.name)
        try:
            text = extract_text_from_file(path).text
        finally:
            path.unlink(missing_ok=True)

        # 제15조 제10항 이상은 "신설" 문맥에서만 나올 수 있다.
        for m in re.finditer(r"제15조[^\n]{0,20}제(\d+)항", text):
            if int(m.group(1)) > 9:
                window = text[max(0, m.start() - 40): m.end() + 40]
                self.assertIn(
                    "신설", window,
                    f"제15조에 없는 항을 기존 조항처럼 인용했다: {window!r}",
                )


if __name__ == "__main__":
    unittest.main()
