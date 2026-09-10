"""건설(공사도급) 계약 '수정본 생성' 다운로드 회귀테스트 (2026-09-08 지시).

사용자 보고: 건설계약서를 검토하고 "수정본 생성하기"를 누르면
`REVIEW_FAILED_GLOBAL_REASONING: monetary_risk_unconfirmed` 로 409 가 나서
DOCX/PDF 를 받을 수 없었다.

원인은 게이트가 아니라 **탐지 누락**이었다. 게이트는 "본문에 지체상금이
있는데 그 금전 리스크를 지적한 finding 이 없다"를 정확히 잡아낸 것이고,
`_RX_LATE_PENALTY_RATE` 가 국가계약법 표준 문구인 한국식 천분율
("지체일수 1일당 계약금액의 1천분의 3")을 못 잡아 finding 자체가
생성되지 않았다. 세 가지가 겹쳐 있었다:

  1. 분모가 한글("1천분의")인 형태를 어느 갈래도 커버하지 않았다.
  2. 기준 금액 명사가 "대금" 뿐이어서 "계약금액"·"공사대금"·"도급금액"을
     놓쳤다(건설계약은 대부분 후자를 쓴다).
  3. 계약서는 "계약금액의\\n1천분의 3" 처럼 문장 중간에서 줄바꿈되는데
     filler 가 줄바꿈을 배제하고 있었다.

부수적으로 `_RX_PENALTY_CAP` 이 "상한을 두지 아니한다"(= 상한이 없다) 안의
"상한"을 매칭해, 무상한 지체상금이 MEDIUM 으로 과소평가되던 것도 고쳤다.

이 테스트는 실제 HTTP 서버를 띄워 다운로드 엔드포인트를 그대로 호출한다 —
사용자가 앱에서 누르는 것과 같은 경로다. `ai_mode=off` 로 결정적·무과금.
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
from runtime.questions.storage import create_session, load_session, save_session
from runtime.review.clause_extraction import extract_clauses
from runtime.review.common_legal_risk import (
    _RX_CAP_NEGATED,
    _RX_LATE_PENALTY_RATE,
    _RX_PENALTY_CAP,
    _apply_late_penalty_uncapped_check,
    _permille_denominator,
)
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService

FIXTURE = Path(__file__).parent / "fixtures" / "construction_works_contract.txt"


def _extract_document_text(fmt: str, body: bytes) -> str:
    """생성된 DOCX/PDF 본문 텍스트 — 문서에 실제로 무엇이 적혔는지 확인용."""
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


def _rate_pct(text: str) -> float | None:
    """룰 본문과 동일한 방식으로 요율(%)을 계산한다."""
    m = _RX_LATE_PENALTY_RATE.search(text)
    if not m:
        return None
    if m.group(1) and m.group(2):
        return float(m.group(1)) / float(m.group(2)) * 100
    if m.group(3):
        return float(m.group(3))
    if m.group(4):
        return float(m.group(4))
    if m.group(6):
        denom = _permille_denominator(m.group(0))
        return float(m.group(6)) / denom * 100 if denom else None
    return None


class LatePenaltyRateNotationTest(unittest.TestCase):
    """요율 표기 방식이 달라도 같은 숫자로 읽어야 한다."""

    def test_korean_permille_notation(self) -> None:
        cases = {
            "지체일수 1일당 계약금액의 1천분의 3에 해당하는 금액": 0.3,
            "지체일수 1일당 계약금액의 1,000분의 3": 0.3,
            "지체일수 1일당 도급금액의 1000분의 25": 2.5,
            "지체일수 1일당 공사대금의 1만분의 15": 0.15,
        }
        for text, expected in cases.items():
            self.assertAlmostEqual(_rate_pct(text), expected, places=6, msg=text)

    def test_line_break_inside_the_sentence(self) -> None:
        """계약서는 문장 중간에서 줄바꿈된다 — filler 가 이를 넘어야 한다."""
        self.assertAlmostEqual(
            _rate_pct("지체일수 1일당 계약금액의\n1천분의 3에 해당하는 금액"), 0.3, places=6,
        )

    def test_existing_notations_still_work(self) -> None:
        cases = {
            "지체일수 당 대금의 3/1000": 0.3,
            "지체 1일당 3% 의 지체상금": 3.0,
            "10 % of total amount for each day of delay": 10.0,
        }
        for text, expected in cases.items():
            self.assertAlmostEqual(_rate_pct(text), expected, places=6, msg=text)

    def test_decimal_rate_is_not_inflated(self) -> None:
        """filler 가 소수점 앞자리를 삼켜 10배로 읽히던 버그."""
        for text, expected in {
            "지체 1일당 0.3% 의 지체상금": 0.3,
            "지체일수 1일당 1.5%": 1.5,
            "지체일수 1일당 계약금액의 0.05%": 0.05,
        }.items():
            self.assertAlmostEqual(_rate_pct(text), expected, places=6, msg=text)


class PenaltyCapNegationTest(unittest.TestCase):
    """'상한을 두지 아니한다' 는 상한이 없다는 뜻이다."""

    def _has_cap(self, text: str) -> bool:
        return bool(_RX_PENALTY_CAP.search(text)) and not _RX_CAP_NEGATED.search(text)

    def test_negated_cap_is_not_a_cap(self) -> None:
        for text in (
            "지체상금에는 상한을 두지 아니한다.",
            "상한을 정하지 아니한다",
            "지체상금 누계액에는 상한을 두지 않는다.",
            "지체상금의 상한이 없다.",
            "배상액에 제한을 두지 아니한다",
            "무제한으로 누적된다",
            "The penalty is not capped.",
        ):
            self.assertFalse(self._has_cap(text), text)

    def test_real_cap_is_still_detected(self) -> None:
        for text in (
            "지체상금 누계액은 계약금액의 10%를 초과할 수 없다.",
            "지체상금의 상한은 계약금액의 10%로 한다.",
            "배상 한도는 대금의 15%로 한다",
            "shall not exceed 10% of the contract price",
            "up to a maximum of USD 100,000",
        ):
            self.assertTrue(self._has_cap(text), text)

    def test_uncapped_construction_penalty_is_high(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        clauses, _ = extract_clauses(text)
        out: list[dict] = []
        _apply_late_penalty_uncapped_check(
            out, text, clauses=clauses, our_party_aliases=["퍼시스", "발주자"],
        )
        self.assertEqual(len(out), 1, "지체상금 finding 이 생성되지 않았다")
        self.assertEqual(out[0]["clause_id"], "clr_late_penalty_rate_uncapped")
        self.assertEqual(
            str(out[0].get("risk_tier")).upper(), "HIGH",
            "상한 없는 지체상금이 HIGH 가 아니다",
        )


class ConstructionRevisionDownloadTest(unittest.TestCase):
    """앱의 '수정본 생성하기' 와 동일한 HTTP 경로를 그대로 호출한다."""

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
            entity="퍼시스",
            contract_type="",
            filename="건설공사도급계약서.docx",
            extraction={},
            text=FIXTURE.read_text(encoding="utf-8"),
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

    def test_download_docx_succeeds(self) -> None:
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"수정본(docx) 생성 실패 status={resp.status}: {body[:600]!r}")
        self.assertGreater(len(body), 1000, "docx 가 비어 있다")
        with zipfile.ZipFile(BytesIO(body)) as z:  # 유효한 .docx = zip
            self.assertIn("word/document.xml", z.namelist())

    def test_download_pdf_succeeds(self) -> None:
        resp, body = self._post(
            "/api/revision/download_pdf",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        if resp.status != 200:
            self.fail(f"수정본(pdf) 생성 실패 status={resp.status}: {body[:600]!r}")
        self.assertTrue(body.startswith(b"%PDF"), "PDF 헤더가 아니다")

    def test_meta_review_failed_is_disclosed_not_silently_dropped(self) -> None:
        """검토 파이프라인이 세운 REVIEW_FAILED 상태가 문서에 드러나는가.

        항목 13(Final Lawyer Self-Check)과 항목 1(Legal Map 완결성 게이트)은
        meta["review_status"] 에 사유를 세운다. 이 다운로드 경로가 그 상태를
        아예 읽지 않아 blocking 실패로 판정된 검토가 "정상" 문서로 나가던
        문제가 있었고(2026-09-09), 그래서 409 로 막게 했었다.

        2026-09-10 지시로 처리 방식이 다시 바뀐다 — 막으면 담당자는 아무것도
        받지 못한 채 원인도 알 수 없다("최종 수정본 생성이 또 실패했다").
        이제는 제거·중화할 수 있는 상태를 해소하고, 그 사실을 문서 말미의
        "자동 검증에서 보류·제외된 항목" 에 명시한 뒤 파일을 내보낸다.

        따라서 이 테스트가 고정하는 계약은 "차단"이 아니라 "**조용히 정상인
        척하지 않는 것**" 이다.
        """
        # 먼저 정상 결과를 만들어 세션에 저장시킨다.
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        self.assertEqual(resp.status, 200, body[:400])

        doc = load_session(self.session_id)
        meta = (doc.get("review_result") or {}).get("clause_meta")
        self.assertIsInstance(meta, dict, "저장된 clause_meta 가 없다")
        meta["review_status"] = "REVIEW_FAILED_LAWYER_SELF_CHECK"
        meta["review_status_detail"] = "자체 점검 실패(테스트 주입)"
        save_session(doc)
        try:
            for fmt in ("docx", "pdf"):
                with self.subTest(format=fmt):
                    resp, body = self._post(
                        f"/api/revision/download_{fmt}",
                        {"session_id": self.session_id},
                    )
                    self.assertEqual(
                        resp.status, 200,
                        f"{fmt}: 다운로드가 실패했다 — 제거·기록 후 전달되어야 한다: {body[:300]!r}",
                    )
                    text = _extract_document_text(fmt, body)
                    self.assertIn(
                        "자동 검증에서 보류·제외된 항목", text,
                        f"{fmt}: 검토 실패 상태가 문서에 드러나지 않았다",
                    )
                    self.assertIn(
                        "최종 자가점검에서 확인이 필요한 항목이 있음", text,
                        f"{fmt}: 어떤 사유로 보정됐는지가 문서에 없다",
                    )
        finally:
            doc = load_session(self.session_id)
            meta = (doc.get("review_result") or {}).get("clause_meta") or {}
            meta.pop("review_status", None)
            meta.pop("review_status_detail", None)
            save_session(doc)

    def test_no_global_reasoning_false_positive(self) -> None:
        """게이트가 오탐으로 다운로드를 막지 않는지 명시적으로 확인한다."""
        resp, body = self._post(
            "/api/revision/download_docx",
            {"session_id": self.session_id, "rebuild": True, "ai_mode": "off"},
        )
        self.assertNotIn(b"REVIEW_FAILED_GLOBAL_REASONING", body)
        self.assertNotIn(b"monetary_risk_unconfirmed", body)
        self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
