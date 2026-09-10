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
import re
import tempfile
import threading
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from runtime.review.text_extract import extract_text_from_file

from runtime.questions.storage import create_session
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService
from runtime.api.server import build_httpd

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fiti_testing_service_agreement.txt"

# The exact review request from the 2026-08-31 incident report: the user
# named these four issue groups (six clause citations total) explicitly and
# reported that 제5조 제1항 제1호 in particular vanished from the final Word
# output — see mandatory_review_target.py.
_FITI_USER_REVIEW_FOCUS = (
    "제5조 제1항 제1호: 경쟁/타 기관 거래 제한\n"
    "제6조 제4항, 제11조 제1항: 일방적 면책\n"
    "제6조 제5항, 제11조 제2항: 구상권/손해배상\n"
    "제6조 제2항: 광고·판촉 활용 제약"
)
_FITI_CITED_CLAUSES = [
    "제5조 제1항 제1호",
    "제6조 제4항",
    "제11조 제1항",
    "제6조 제5항",
    "제11조 제2항",
    "제6조 제2항",
]


def _docx_full_text(docx_bytes: bytes) -> str:
    z = zipfile.ZipFile(BytesIO(docx_bytes))
    xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    return "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, flags=re.DOTALL))


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
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
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


class FinalFindingsCollapseReviewFailedTest(unittest.TestCase):
    """Regression (2026-08-28, real-world report): "final_findings_count(ui)=17,
    docx=1인데 정상 완료로 표시" — a document whose HIGH/MEDIUM count collapsed
    relative to the raw clause_results feeding it must never be served as if
    it were a normal, complete review.

    2026-09-10 지시 항목 2로 그 처리 방식이 바뀌었다. 종전에는 409로 다운로드를
    막았는데, 그러면 담당자는 아무것도 받지 못한 채 원인도 알 수 없었다(실제로
    "수정본 생성 실패"가 반복된 주 원인 중 하나). 이제는

      · 계약유형 기반 문구 필터를 해제하고 한 번 더 만들어 회복을 시도하고,
      · 그래도 남는 붕괴는 문서 말미 "자동 검증에서 보류·제외된 항목"에 명시한 뒤
      · 파일 자체는 정상적으로 내보낸다.

    따라서 이 테스트가 고정하는 계약은 "차단"이 아니라 "**조용히 정상인 척하지
    않는 것**"이다 — 200으로 내려오되 붕괴 사실이 문서 안에 반드시 적혀 있어야
    한다."""

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

        from runtime.questions.storage import load_session, save_session, run_review_with_session

        run_review_with_session(cls.service, cls.session_id)
        stored = load_session(cls.session_id)
        crs = stored["review_result"]["clause_results"]
        # Simulate the reported "17 vs 1" shape directly: keep every real
        # HIGH/MEDIUM clause_result's risk_tier (so the raw tier count stays
        # >= 5, matching what a real broken pipeline would still report) but
        # blank out the fields output_filter's quality gate requires, so
        # every one of them is rejected except a single survivor — the real
        # final_findings count collapses to ~1 while the raw count stays high.
        kept_one = False
        for cr in crs:
            if not isinstance(cr, dict):
                continue
            if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
                continue
            if not kept_one:
                kept_one = True
                continue
            cr["original_text"] = ""
            cr["rewrite_reason"] = ""
            cr["suggested_rewrite"] = ""
            cr["problem"] = ""
            cr["proposed_revision"] = ""
        stored["review_result"]["clause_results"] = crs
        save_session(stored)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def _post(self, path: str, payload: dict) -> tuple:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        body = json.dumps(payload).encode("utf-8")
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json; charset=utf-8"})
        resp = conn.getresponse()
        resp_body = resp.read()
        conn.close()
        return resp, resp_body

    def test_collapsed_final_findings_is_disclosed_not_silently_served(self) -> None:
        resp, body = self._post(
            "/api/revision/download_docx", {"session_id": self.session_id, "ai_mode": "off"}
        )
        # 다운로드는 실패하지 않는다 — 담당자는 나머지 검토 결과를 즉시 쓸 수
        # 있어야 한다(2026-09-10 지시 항목 2).
        self.assertEqual(resp.status, 200, f"download must not fail, got {resp.status}: {body[:300]!r}")
        self.assertGreater(len(body), 500, "docx body suspiciously small/empty")

        # 그러나 붕괴 사실은 반드시 문서 안에 적혀 있어야 한다.
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as fh:
            fh.write(body)
            tmp_path = Path(fh.name)
        try:
            text = extract_text_from_file(tmp_path).text
        finally:
            tmp_path.unlink(missing_ok=True)
        self.assertIn(
            "자동 검증에서 보류·제외된 항목", text,
            "collapsed output was served without disclosing the collapse",
        )
        self.assertIn(
            "출력 필터가 검토항목 대부분을 제외했습니다", text,
            "collapse disclosure must state what happened",
        )


class FitiMandatoryReviewTargetsPipelineTest(unittest.TestCase):
    """Regression (2026-08-31 incident): the user named six clause citations
    in their review request — including 제5조 제1항 제1호 (경쟁/타 기관 거래
    제한) — and 제5조 제1항 제1호 in particular vanished from the final
    Word output despite a matching rule (tsr_other_lab_dealing_restriction)
    existing in testing_service_rules.py. Every cited clause must resolve to
    either a real finding ("flagged") or a confirmed "no issue" note
    ("checked_no_issue") — never "clause_not_found", since all six citations
    correspond to clauses that genuinely exist in this fixture."""

    def test_all_cited_clauses_resolve_without_clause_not_found(self) -> None:
        from runtime.review.clause_level import build_clause_level_result

        text = FIXTURE_PATH.read_text(encoding="utf-8")
        loader = RuleLoader()
        loader.load()
        service = RuleQueryService(loader)
        bundle = build_clause_level_result(
            service=service,
            entity="시디즈",
            contract_type="",
            text=text,
            filename="시디즈_FITI_시험분석약정서.pdf",
            answers=None,
            review_focus=_FITI_USER_REVIEW_FOCUS,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        targets = bundle.meta.get("mandatory_review_targets")
        self.assertIsInstance(targets, list)
        self.assertEqual(len(targets), len(_FITI_CITED_CLAUSES))
        by_path = {t["display_path"]: t for t in targets}
        for citation in _FITI_CITED_CLAUSES:
            self.assertIn(citation, by_path, f"citation {citation!r} was not parsed from review_focus")
            status = by_path[citation]["status"]
            self.assertIn(
                status, ("flagged", "checked_no_issue"),
                f"{citation} resolved as {status!r} — the cited clause was not found in the contract at all",
            )
        # 제5조 제1항 제1호 specifically must be "flagged" — a real rule
        # (tsr_other_lab_dealing_restriction) matches this exact clause.
        self.assertEqual(by_path["제5조 제1항 제1호"]["status"], "flagged")

        self.assertNotEqual(
            bundle.meta.get("self_check", {}).get("review_status"),
            "REVIEW_FAILED_USER_REQUEST_MISSING",
        )


class FitiMandatoryReviewTargetsDocxTest(unittest.TestCase):
    """Same incident, exercised through the real download_docx HTTP path —
    every clause the user cited in review_focus must appear verbatim in the
    downloaded Word document, and the download must not be blocked."""

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
            review_focus=_FITI_USER_REVIEW_FOCUS,
        )
        cls.session_id = doc["session_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def _post(self, path: str, payload: dict) -> tuple:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        body = json.dumps(payload).encode("utf-8")
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json; charset=utf-8"})
        resp = conn.getresponse()
        resp_body = resp.read()
        conn.close()
        return resp, resp_body

    def test_all_cited_clauses_survive_into_downloaded_docx(self) -> None:
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"download_docx failed with status {resp.status}: {body[:800]!r}")
        full_text = _docx_full_text(body)
        for citation in _FITI_CITED_CLAUSES:
            self.assertIn(citation, full_text, f"{citation} missing from final docx — user-cited clause dropped")

    def test_clr_and_tsr_titles_carry_the_real_article_number(self) -> None:
        # Requirement: rule-engine findings (clr_*/tsr_*) must show the real
        # "제N조 제N항" citation, not a bare internal rule id, in the final
        # Word output — clause_title is what gets rendered as the heading.
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"download_docx failed with status {resp.status}: {body[:800]!r}")
        full_text = _docx_full_text(body)
        self.assertIn("제6조 제4항 [귀책사유 불문 일방적 면책]", full_text)
        self.assertIn("제5조 제1항 [동종 거래·경쟁 관계 제한(사전통보 의무)]", full_text)


if __name__ == "__main__":
    unittest.main()
