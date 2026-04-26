from __future__ import annotations

import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from runtime.api.server import build_httpd
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService


class IntegrationFlowTest(unittest.TestCase):
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

    def test_upload_to_db_and_admin_query(self) -> None:
        boundary = f"----WebKitFormBoundary{uuid4().hex}"
        payload_text = "This contract includes without limitation liability and indemnify obligations."
        parts = []
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            b'Content-Disposition: form-data; name="file"; filename="sample_NDA.txt"\r\n'
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
                upload = json.loads(res.read().decode("utf-8"))
        except HTTPError as e:
            self.fail(e.read().decode("utf-8", errors="replace"))

        self.assertTrue(upload["extraction"]["success"])
        self.assertIn("question_session_id", upload)
        sid = upload["question_session_id"]

        req2 = Request(
            f"http://127.0.0.1:{self.port}/api/question_sessions/{sid}/answers",
            data=json.dumps({"answers": {"Q-010-liability-cap": "need_cap"}}, ensure_ascii=False).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req2) as res:
            _ = json.loads(res.read().decode("utf-8"))

        req3 = Request(
            f"http://127.0.0.1:{self.port}/api/question_sessions/{sid}/review",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req3) as res:
            review_wrap = json.loads(res.read().decode("utf-8"))
        self.assertIsNotNone(review_wrap.get("request_id"))
        request_id = review_wrap["request_id"]
        review = review_wrap["review"]

        self.assertGreaterEqual(review["summary"]["matched_rule_count"], 1)
        self.assertGreaterEqual(
            review["summary"]["approval_required_match_count"] + review["summary"]["matched_rule_count"], 1
        )

        with urlopen(
            f"http://127.0.0.1:{self.port}/api/reviews?high_risk_only=true&approval_required_only=false&limit=50&offset=0"
        ) as res:
            lst = json.loads(res.read().decode("utf-8"))
        self.assertGreaterEqual(lst["count"], 1)

        with urlopen(f"http://127.0.0.1:{self.port}/api/reviews/{request_id}") as res:
            detail = json.loads(res.read().decode("utf-8"))
        self.assertIn("rules_version", detail)
        self.assertIn("applied_rules", detail)

        with urlopen(f"http://127.0.0.1:{self.port}/api/approval_queue?status=new&limit=50&offset=0") as res:
            q = json.loads(res.read().decode("utf-8"))
        self.assertGreaterEqual(q["count"], 1)

        req4 = Request(
            f"http://127.0.0.1:{self.port}/api/revision/suggest",
            data=json.dumps({"session_id": sid}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req4) as res:
            rev = json.loads(res.read().decode("utf-8"))
        self.assertIn("revision", rev)
        self.assertIn("items", rev["revision"])


if __name__ == "__main__":
    unittest.main()

