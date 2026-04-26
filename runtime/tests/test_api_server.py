from __future__ import annotations

import json
import threading
import time
import unittest
from urllib.request import Request, urlopen
from uuid import uuid4
from urllib.error import HTTPError

from runtime.api.server import build_httpd
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


class ApiServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        service = RuleQueryService(RuleLoader())
        cls.httpd = build_httpd("127.0.0.1", 0, service)
        cls.port = cls.httpd.server_port
        cls.th = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.th.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_health(self) -> None:
        with urlopen(f"http://127.0.0.1:{self.port}/health") as res:
            data = json.loads(res.read().decode("utf-8"))
        self.assertEqual(data["status"], "ok")

    def test_review_analyze(self) -> None:
        payload = {
            "entity": "퍼시스",
            "contract_type": "물품공급/구매/매매",
            "text": "without limitation 책임 및 indemnify 조항이 포함된다.",
        }
        req = Request(
            f"http://127.0.0.1:{self.port}/api/review/analyze",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as res:
            data = json.loads(res.read().decode("utf-8"))
        self.assertIn("summary", data)
        self.assertIn("matched_rules", data)

    def test_upload_txt(self) -> None:
        boundary = f"----WebKitFormBoundary{uuid4().hex}"
        payload_text = "without limitation 책임 및 indemnify 조항"
        parts = []
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            'Content-Disposition: form-data; name="entity"\r\n\r\n퍼시스\r\n'.encode(
                "utf-8"
            )
        )
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            'Content-Disposition: form-data; name="contract_type"\r\n\r\n물품공급/구매/매매\r\n'.encode(
                "utf-8"
            )
        )
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            b'Content-Disposition: form-data; name="file"; filename="sample.txt"\r\n'
        )
        parts.append(b"Content-Type: text/plain\r\n\r\n")
        parts.append(payload_text.encode("utf-8"))
        parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)

        req = Request(
            f"http://127.0.0.1:{self.port}/api/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urlopen(req) as res:
                data = json.loads(res.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            self.fail(f"upload endpoint returned {e.code}: {detail}")
        self.assertIn("extraction", data)
        self.assertTrue(data["extraction"]["success"])
        self.assertIn("question_session_id", data)
        self.assertIn("questions", data)

        session_id = data["question_session_id"]
        answers = {"Q-003-personal-data": "yes", "Q-002-overseas": "no"}
        req2 = Request(
            f"http://127.0.0.1:{self.port}/api/question_sessions/{session_id}/answers",
            data=json.dumps({"answers": answers}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req2) as res:
            saved = json.loads(res.read().decode("utf-8"))
        self.assertEqual(saved["session_id"], session_id)
        self.assertIn("answers", saved)

        req3 = Request(
            f"http://127.0.0.1:{self.port}/api/question_sessions/{session_id}/review",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req3) as res:
            review = json.loads(res.read().decode("utf-8"))
        self.assertIn("review", review)
        self.assertIn("request_id", review)
        self.assertIn("summary", review["review"])
        self.assertIn("question_answers", review["review"])
        self.assertEqual(review["review"]["question_answers"].get("Q-003-personal-data"), "yes")

        with urlopen(f"http://127.0.0.1:{self.port}/api/reviews?limit=10&offset=0") as res:
            lst = json.loads(res.read().decode("utf-8"))
        self.assertIn("items", lst)
        self.assertGreaterEqual(lst["count"], 1)
        rid = lst["items"][0]["request_id"]
        with urlopen(f"http://127.0.0.1:{self.port}/api/reviews/{rid}") as res:
            detail = json.loads(res.read().decode("utf-8"))
        self.assertIn("request", detail)
        self.assertIn("result", detail)
        self.assertIn("applied_rules", detail)


if __name__ == "__main__":
    unittest.main()

