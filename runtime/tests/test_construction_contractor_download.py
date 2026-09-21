"""수급인 지위 건설계약의 '수정본 생성' 다운로드 e2e (2026-09-18 지시).

기존 `test_construction_revision_download.py` 는 **도급인(발주)** 쪽 계약을
고정한다. 이번 지시로 새로 생긴 경로 — 지위를 수급인으로 확정하고, 지위별
체크리스트와 공사대금 회수 패키지를 주입하는 경로 — 는 그 테스트가 지나가지
않는다. 새 게이트가 다운로드를 막지 않는지, 그리고 주입된 완성 조문이 실제
문서에 실리는지를 앱과 같은 HTTP 경로로 확인한다.

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
from runtime.tests.test_construction_transaction_model import CONTRACT_WE_ARE_CONTRACTOR


def _extract_document_text(fmt: str, body: bytes) -> str:
    import tempfile

    from runtime.review.text_extract import extract_text_from_file

    suffix = ".docx" if fmt == "docx" else ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(body)
        path = Path(fh.name)
    try:
        return extract_text_from_file(path).text
    finally:
        path.unlink(missing_ok=True)


class ContractorSideRevisionDownloadTest(unittest.TestCase):
    """우리가 수급인인 공사도급계약의 수정본 생성."""

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
            contract_type="",
            filename="인테리어공사도급계약서.docx",
            extraction={},
            text=CONTRACT_WE_ARE_CONTRACTOR,
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
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off",
             "review_focus": "우리가 도급받아 시공합니다. 돈을 못 받는 리스크가 최대 리스크입니다."},
        )
        if resp.status != 200:
            self.fail(f"수정본(docx) 생성 실패 status={resp.status}: {body[:600]!r}")
        self.assertGreater(len(body), 1000, "docx 가 비어 있다")
        with zipfile.ZipFile(BytesIO(body)) as z:
            self.assertIn("word/document.xml", z.namelist())

    def test_pdf_download_succeeds(self) -> None:
        resp, body = self._post(
            "/api/revision/download_pdf",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"수정본(pdf) 생성 실패 status={resp.status}: {body[:600]!r}")
        self.assertTrue(body.startswith(b"%PDF"), "PDF 헤더가 아니다")

    def test_document_carries_contractor_side_clauses(self) -> None:
        """주입한 완성 조문이 실제 문서에 실리는가.

        체크리스트 항목이 파이프라인 후단의 강등·필터에서 조용히 사라지면
        화면에는 보이고 문서에는 없는 상태가 된다(v4.2 실측). 문서 본문을
        직접 읽어 확인한다.
        """
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        self.assertEqual(resp.status, 200, body[:400])
        text = _extract_document_text("docx", body)
        # 공사대금 회수 사슬(준공검사 → 기성 → 유보 → 상계 → 잔금 → 하자공제)
        self.assertIn("검사에 합격한 것으로 본다", text)
        # 도급인 귀책 전가 차단(민법 제669조)
        self.assertIn("담보책임", text)
        # 도급인 보호 관점의 항목이 섞이지 않았는가 — 우리는 수급인이다.
        self.assertNotIn("만회대책을 서면으로 제출하고", text)

    def test_no_false_block_on_download(self) -> None:
        """새 게이트가 오탐으로 다운로드를 막지 않는지 확인한다."""
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        self.assertEqual(resp.status, 200)
        self.assertNotIn(b"REVIEW_BLOCKED_CONSTRUCTION_ROLE_UNSETTLED", body)


if __name__ == "__main__":
    unittest.main()
