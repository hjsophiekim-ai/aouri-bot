"""End-to-end regression: clicking "검토결과 최종본 출력하기" in the app posts
{"session_id": ...} to /api/revision/download_docx. This used to fail with
"consistency_check_failed: clause_id missing in original_clauses" for any
review containing a common_legal_risk finding (clause_id like
"clr_fault_blind_exemption") — which is most of the FITI 시험분석약정서's
required findings — because the consistency check in server.py flagged every
rule-engine-synthesized clause_id not already present in the raw
extract_clauses() output as "missing", instead of only flagging a genuine
segmented-clause id (KR-/EN-/P-) that actually vanished.

This test drives the real HTTP handler (not just the pipeline function) over
a real socket, exactly like the browser does, against the FITI fixture.
"""
from __future__ import annotations

import http.client
import json
import threading
import unittest
from pathlib import Path

from runtime.questions.storage import create_session
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService
from runtime.api.server import build_httpd

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fiti_testing_service_agreement.txt"


class FitiDownloadDocxEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)
        cls.httpd = build_httpd("127.0.0.1", 0, cls.service)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        doc = create_session(
            cls.service,
            entity="시디즈",
            contract_type="",
            filename="fiti.pdf",
            extraction={},
            text=text,
            classification={},
        )
        cls.session_id = doc["session_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def _post(self, path: str, payload: dict) -> http.client.HTTPResponse:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        body = json.dumps(payload).encode("utf-8")
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json; charset=utf-8"})
        resp = conn.getresponse()
        resp_body = resp.read()
        conn.close()
        return resp, resp_body

    def test_download_docx_succeeds_for_fiti_session(self) -> None:
        # ai_mode=off: this test is a regression guard on the consistency-check
        # / segmentation code path, not on real AI output — it must stay fast,
        # deterministic, and free of any live network/API dependency.
        resp, body = self._post(
            "/api/revision/download_docx", {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"}
        )
        if resp.status != 200:
            self.fail(f"download_docx failed with status {resp.status}: {body[:500]!r}")
        self.assertEqual(
            resp.getheader("Content-Type"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertGreater(len(body), 1000, "docx body suspiciously small/empty")
        # A valid .docx is a zip archive.
        self.assertEqual(body[:2], b"PK")

    def test_download_pdf_succeeds_for_fiti_session(self) -> None:
        resp, body = self._post(
            "/api/revision/download_pdf", {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"}
        )
        if resp.status != 200:
            self.fail(f"download_pdf failed with status {resp.status}: {body[:500]!r}")
        self.assertEqual(resp.getheader("Content-Type"), "application/pdf")
        self.assertGreater(len(body), 500, "pdf body suspiciously small/empty")


if __name__ == "__main__":
    unittest.main()
