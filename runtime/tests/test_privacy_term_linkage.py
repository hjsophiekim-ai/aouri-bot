"""거래 흐름 우선 검토 · 개인정보 처리 흐름 · 검토서↔Word 반영 대조 회귀시험 (2026-11-12 지시).

시험 1 — 식권 플랫폼 계약(실제 업로드 원본): 우리 역할(서명란 공란 → 요청서로 고객회사), 중도해지 가능 여부와 위약금을 별개
         질문으로 답하고 자동갱신·해지·위약금·별지 요금·종료 정산을 연결, 제6~8조와 종료·홍보 조항을 엮은 개인정보 흐름,
         운영자료 없이 처리 관계를 단정하지 않음, 위약금 수정안이 실제 제15조에 들어감(Word 변경 수락본으로 확인).
시험 2 — 다른 계약: '개인정보' 낱말 없이 고객 명단·관리자 조회가 있는 상담 대행 계약은 검토가 시작되고, 개인 정보 처리가
         없는 원자재 납품 계약에는 개인정보·위탁 조항을 넣지 않는다.
시험 3 — 실패 주입: Word 생성에서 제안 문구를 일부러 빼면 탐지 → 재생성 → 재검사. 계속 빠지면 '제안만 있음·파일 미반영'
         표시와 최종본(클린본) 출력 차단.

코드에는 회사명·조항 번호가 없다 — 기대값만 이 시험에 있다.
"""
from __future__ import annotations

import base64
import copy
import json
import re
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from runtime.review import deal_flow as df
from runtime.review import privacy_flow as pf
from runtime.review import term_linkage as tl
from runtime.review.clause_extraction import extract_clauses

from runtime.tests._private_fixtures import private_fixture

FIX = Path(__file__).parent / "fixtures"


def meal_docx() -> Path:
    """식권 계약 원본(실데이터) — 저장소 밖 로컬 폴더에만 있다. 없으면 SkipTest."""
    return private_fixture("meal_voucher_contract.docx")


def meal_req() -> str:
    return private_fixture("meal_voucher_request.txt").read_text(encoding="utf-8")


MEAL_REQ_NUMBERED = ("일룸홀딩스 임직원 식대 지급을 위해 한결식권 식사관리 서비스를 도입하려 합니다. "
                     "1. 계약기간 중 중도해지가 가능한지 2. 해지 시 위약금이 얼마인지 검토 부탁드립니다.")
OUTSOURCE_TXT = FIX / "customer_support_outsourcing.txt"
SUPPLY_TXT = FIX / "office_furniture_supply_no_personal.txt"
GENERAL_REQ = "계약 검토 부탁드립니다. 퍼시스에 불리한 조항이 있는지 검토해 주세요."


def meal_text() -> str:
    from runtime.review.text_extract import extract_text_from_file

    return extract_text_from_file(meal_docx()).text


def clauses_of(text: str) -> list[dict]:
    return [c.__dict__ for c in extract_clauses(text)[0]]


def stage(text: str, request: str, entity: str, crs: list | None = None) -> tuple[dict, list]:
    crs = crs if crs is not None else []
    out = df.run_deal_flow_stage(text=text, clauses=clauses_of(text), clause_results=crs, request_text=request,
                                 answers_text="", entity=entity)
    return out, crs


# ── HTTP 경로(업로드 → 답변 → 검토 → 다운로드), AI 없이 결정적 ─────────────────────────

def _multipart(url: str, path: Path, fields: dict[str, str]) -> dict:
    boundary = "----t" + uuid.uuid4().hex
    ctype = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if path.suffix == ".docx"
             else "text/plain; charset=utf-8")
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n".encode() + v.encode("utf-8") + b"\r\n")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n".encode())
    parts.append(path.read_bytes() + b"\r\n" + f"--{boundary}--\r\n".encode())
    req = Request(url, data=b"".join(parts), method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urlopen(req, timeout=900).read().decode("utf-8"))


def _post(url: str, payload: dict, raw: bool = False) -> Any:
    req = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
                  headers={"Content-Type": "application/json; charset=utf-8"})
    body = urlopen(req, timeout=1800).read()
    return body if raw else json.loads(body.decode("utf-8"))


def docx_text(b: bytes) -> str:
    from runtime.review.text_extract import extract_text_from_file

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as fh:
        fh.write(b)
    p = Path(fh.name)
    try:
        return extract_text_from_file(p).text
    finally:
        p.unlink(missing_ok=True)


def accepted(b: bytes) -> list[str]:
    from runtime.review.docx_redline import docx_paragraph_texts

    return [p for p in docx_paragraph_texts(b, mode="accept") if p.strip()]


def article_block(paras: list[str], no: str) -> list[str]:
    """수락본에서 '제 N 조' 머리글부터 다음 조 머리글 전까지(제N조의M 은 별도 조)."""
    rx_head = re.compile(r"^\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
    out: list[str] = []
    inside = False
    for p in paras:
        m = rx_head.match(p)
        if m and not re.match(r"^\s*제\s*\d+\s*조\s*(?:에|의\s*[^\d]|에\s*따라)", p):
            cur = m.group(1) + (f"의{m.group(2)}" if m.group(2) else "")
            inside = cur == no
            if inside:
                out.append(p)
            continue
        if inside:
            out.append(p)
    return out


class Server:
    def __init__(self) -> None:
        from runtime.api.server import build_httpd
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        self.httpd = build_httpd("127.0.0.1", 0, RuleQueryService(loader))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def run(self, path: Path, request: str, entity: str, answer: str = "없습니다.") -> dict[str, Any]:
        up = _multipart(self.base + "/api/upload", path, {"entity": entity, "contract_type": "", "review_focus": request})
        sid = up["question_session_id"]
        answers = {(q.get("question_id") or q.get("id")): answer for q in up.get("questions") or []}
        _post(f"{self.base}/api/question_sessions/{sid}/answers", {"answers": answers})
        review = _post(f"{self.base}/api/question_sessions/{sid}/review", {})["review"]
        out = {"sid": sid, "review": review, "meta": review["clause_meta"]}
        out["redline"] = _post(self.base + "/api/revision/download_redline", {"session_id": sid}, raw=True)
        out["clean"], out["clean_status"] = self.clean(sid)
        out["report"] = _post(self.base + "/api/revision/download_docx", {"session_id": sid}, raw=True)
        out["report_text"] = docx_text(out["report"])
        out["accepted"] = accepted(out["redline"])
        return out

    def clean(self, sid: str) -> tuple[bytes | dict, int]:
        try:
            return _post(self.base + "/api/revision/download_clean", {"session_id": sid}, raw=True), 200
        except HTTPError as exc:
            return json.loads(exc.read().decode("utf-8")), exc.code

    def close(self) -> None:
        self.httpd.shutdown()


def dropping_build(target_prefix: str, times: int):
    """Word 생성 단계에서 target 수정안을 빼고 만든다(times 회까지) — 반영 누락을 흉내 낸다."""
    from runtime.review.delivery_docs import build_tracked_docs

    calls = {"n": 0}

    def build(session: dict, review_result: dict, **kw: Any) -> Any:
        calls["n"] += 1
        if calls["n"] <= times:
            keep = [c for c in review_result.get("clause_results") or []
                    if not str(c.get("clause_id") or "").startswith(target_prefix)]
            return build_tracked_docs(session, {**review_result, "clause_results": keep}, **kw)
        return build_tracked_docs(session, review_result, **kw)

    build.calls = calls  # type: ignore[attr-defined]
    return build


# ── 시험 1: 식권 플랫폼 (단계 단위) ─────────────────────────────────────────────

class MealVoucherStageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = meal_text()
        cls.meal_req = meal_req()
        cls.out, cls.crs = stage(cls.text, cls.meal_req, "일룸홀딩스")

    def test_role_from_request_with_blank_signature(self) -> None:
        r = self.out["role"]
        self.assertTrue(r["confirmed"])
        self.assertEqual(r["our_label"], "고객회사")
        self.assertEqual(r["counterparty_label"], "운영회사")
        self.assertIn("요청서", r["basis_kind"])
        self.assertTrue(any("서명 전" in c and "법인명" in c for c in r["pre_sign_checks"]))

    def test_exit_and_penalty_are_separate_questions(self) -> None:
        rows = self.out["request_rows"]
        exit_row = next(r for r in rows if r["original_user_text"].endswith("중도해지 가능 여부"))
        cost_row = next(r for r in rows if r["original_user_text"].endswith("해지 시 위약금·비용"))
        self.assertIn("사유 없이 계약기간 중 해지할 수 있다는 조항은 없습니다", exit_row["judgment"])
        # 자동갱신·해지·위약금을 함께 읽는다
        for p in ("제13조", "제3조", "제15조"):
            self.assertIn(p, exit_row["relevant_clause_paths"])
        self.assertIn("갱신 거절", exit_row["judgment"])
        # 위약금: 별지 요금과 연결해 금액 계산, 정의 없는 기준·자동 연장·종료 정산
        self.assertIn("0원", cost_row["judgment"])
        self.assertIn("서비스 수수료", cost_row["judgment"])
        self.assertIn("자동 연장된 기간에도 적용", cost_row["judgment"])
        self.assertIn("제14조", cost_row["judgment"])

    def test_numbered_inline_request_is_split_without_repeat(self) -> None:
        out, _ = stage(self.text, MEAL_REQ_NUMBERED, "일룸홀딩스")
        texts = [r["original_user_text"] for r in out["request_rows"]]
        self.assertTrue(any(t.startswith("계약기간 중 중도해지가 가능한지") for t in texts))
        self.assertTrue(any(t.startswith("해지 시 위약금이 얼마인지") for t in texts))
        self.assertEqual(sum(1 for t in texts if "중도해지 가능 여부" in t or t.startswith("계약기간 중 중도해지")), 1)

    def test_privacy_flow_links_articles_6_to_8_and_promo(self) -> None:
        pr = self.out["privacy"]
        self.assertTrue(pr["active"])
        keys = {a["key"]: a for a in pr["activities"]}
        for k in ("roster", "signup", "history", "admin", "retain"):
            self.assertIn(k, keys)
        self.assertIn("제6조", keys["roster"]["basis"])
        self.assertIn("제7조", keys["retain"]["basis"])            # 보관 조항
        self.assertIn("제6조", keys["admin"]["basis"])             # 관리자 사이트
        self.assertEqual(pr["generic_only"], ["제8조"])            # '관련 법령 준수' 일반 조항만으로 충분하다고 보지 않는다
        self.assertEqual(pr["promo"]["path"], "제18조")
        self.assertTrue(pr["promo"]["personal"])                   # 회사 승인 ≠ 개인 정보 홍보 이용
        self.assertIn("반환·파기 없음", next(c["status"] for c in pr["checklist"] if c["key"] == "retention"))

    def test_privacy_relationship_not_asserted_without_operating_docs(self) -> None:
        pr = self.out["privacy"]
        for a in pr["activities"]:
            if len(a["relation_candidates"]) > 1:
                self.assertTrue(a["relation"].startswith("판단 보류"), a)
        self.assertTrue(any("운영약관" in d for d in pr["docs_missing"]))
        self.assertTrue(pr["pre_launch"])
        f = next(c for c in self.crs if c.get("linked_topic") == "privacy_flow")
        body = f["redline_instruction"]["replacement_text"]
        self.assertEqual(f["redline_instruction"]["edit_location"], "제8조의2 신설")
        # 위탁을 단정하지 않는다 — '위탁받아 처리하는 부분에 대하여는' 조건부로만
        self.assertIn("위탁받아 처리하는 부분에 대하여는", body)
        self.assertNotRegex(body, r"위탁한다|수탁자로\s*한다")
        self.assertNotRegex(body, r"다음\s*(?:문단|항)을\s*추가한다")

    def test_penalty_revision_targets_article_15(self) -> None:
        f = next(c for c in self.crs if c.get("linked_topic") == "penalty_scope")
        ri = f["redline_instruction"]
        self.assertEqual(ri["edit_location"], "제15조 ③ 신설")
        self.assertTrue(ri["replacement_text"].startswith("③ 본 조의 위약금 산정 기준 금액은 별지 1에 기재된 고객회사 서비스 이용료에 한하며"))
        self.assertIn("④ ", ri["replacement_text"])

    def test_edit_instruction_moves_to_memo(self) -> None:
        cr = {"clause_id": "counsel_x", "display_path": "제15조 제1항", "original_text": "원문", "risk_tier": "MEDIUM",
              "redline_instruction": {"edit_type": "replace", "edit_location": "제15조 제2항 뒤에 제3항 신설",
                                      "replacement_text": "③ 제15조(위약금) 중 다음 문단을 추가한다: '단, 별지1에 따라 서비스 이용료가 무료인 경우 위약금은 발생하지 아니한다.'"}}
        moved = df.split_edit_instruction(cr)
        self.assertIn("다음 문단을 추가한다", moved)
        self.assertEqual(cr["redline_instruction"]["replacement_text"], "③ 단, 별지1에 따라 서비스 이용료가 무료인 경우 위약금은 발생하지 아니한다.")
        self.assertEqual(cr["redline_instruction"]["edit_type"], "insert_after")
        self.assertIn("편집 지시(본문 아님)", cr["drafting_memo"])
        self.assertTrue(cr["has_rewrite_change"])

    def test_foreign_party_labels_are_held(self) -> None:
        bad = {"clause_id": "rule_x", "display_path": "제15조 제1항", "original_text": "원문", "risk_tier": "MEDIUM",
               "has_rewrite_change": False, "has_addition": True,
               "addition_text": "② 갑이 비용 정산 또는 공제/상계를 하려는 경우, 을에게 사전 통지한다.",
               "redline_instruction": {"edit_type": "replace", "replacement_text": "원문"}}
        _out, crs = stage(self.text, self.meal_req, "일룸홀딩스", crs=[bad])
        self.assertTrue(bad["redline_instruction"].get("held"))
        self.assertIn("갑", bad["redline_instruction"]["hold_reason"])


class SystemBannerTest(unittest.TestCase):
    def test_own_warning_banner_is_not_counted_as_contract_error(self) -> None:
        """2026-11-11 실측: '[검증 미통과 초안] …' 표지를 계약 본문 지침·메모 삽입으로 다시 집계했다."""
        from runtime.review.final_docx_check import check_docx

        orig = ["제1조 (목적)", "본 계약은 서비스 이용 조건을 정한다."]
        acc = ["[검증 미통과 초안] 이 수정안은 필수 검증을 통과하지 못했습니다(미해결 1건 — 검토의견서 1절 참고). 최종본이 아니며 서명용으로 쓰지 마십시오.",
               "[협상 초안 · 서명 전 확정 필요] 이 문서에는 아직 합의되지 않은 값([●] 등)이 남아 있습니다."] + orig
        self.assertEqual(check_docx(acc, orig, labels=["갑", "을"], live=[]), [])

    def test_edit_instruction_in_body_is_detected(self) -> None:
        from runtime.review.final_docx_check import check_docx

        orig = ["제1조 (목적)", "본 계약은 서비스 이용 조건을 정한다."]
        acc = orig + ["제1조(목적) 중 다음 문단을 추가한다: '단, 이용료는 무료로 한다.'"]
        self.assertIn("EDIT_INSTRUCTION_IN_BODY", [p["code"] for p in check_docx(acc, orig, labels=["갑", "을"], live=[])])

    def test_statute_citation_is_not_bad_reference(self) -> None:
        from runtime.review.final_docx_check import check_docx

        orig = ["제1조 (목적)", "본 계약은 서비스 이용 조건을 정한다."]
        acc = orig + ["(5) 을은 개인정보 보호법 제29조에 따른 안전성 확보에 필요한 조치를 하여야 한다."]
        self.assertNotIn("BAD_REF", [p["code"] for p in check_docx(acc, orig, labels=["갑", "을"], live=[])])


# ── 시험 2: 다른 계약 ───────────────────────────────────────────────────────────

class OtherContractsStageTest(unittest.TestCase):
    def test_customer_list_and_admin_view_start_privacy_review(self) -> None:
        text = OUTSOURCE_TXT.read_text(encoding="utf-8")
        self.assertNotIn("개인정보", text)
        out, crs = stage(text, GENERAL_REQ, "퍼시스")
        pr = out["privacy"]
        self.assertTrue(pr["active"])
        keys = {a["key"]: a for a in pr["activities"]}
        self.assertIn("성명, 연락처, 배송지 주소", keys["roster"]["items"])
        self.assertIn("admin", keys)
        # 원문이 '을이 갑의 업무를 대행' 이라 정하므로 위탁으로 읽는 근거가 원문에 있다(운영 자료 없이도)
        self.assertTrue(keys["roster"]["relation"].startswith("원문상 갑 업무의 처리위탁"))
        self.assertTrue(any(c.get("linked_topic") == "privacy_flow" for c in crs))

    def test_contract_without_personal_data_gets_no_privacy_clause(self) -> None:
        text = SUPPLY_TXT.read_text(encoding="utf-8")
        out, crs = stage(text, GENERAL_REQ, "퍼시스")
        self.assertFalse(out["privacy"]["active"])
        self.assertFalse([c for c in crs if str(c.get("linked_topic") or "").startswith("privacy")])
        for c in crs:
            self.assertNotIn("위탁", (c.get("redline_instruction") or {}).get("replacement_text", ""))

    def test_fixture_sweep_has_no_false_triggers(self) -> None:
        """기존 계약 fixture 가운데 개인 정보 흐름이 실제로 있는 것만 시작한다."""
        active = sorted(p.name for p in FIX.glob("*.txt")
                        if pf.analyze(p.read_text(encoding="utf-8", errors="ignore"), ours="갑", theirs="을").active)
        self.assertIn("customer_support_outsourcing.txt", active)
        self.assertNotIn("office_furniture_supply_no_personal.txt", active)
        for name in ("_lm_investment_1.txt", "employee_nda_kr_seoyakseo.txt", "interior_works_prime_contractor.txt",
                     "hangul_day_100th_alloso_3party_contract.txt"):
            self.assertNotIn(name, active)


# ── 실제 파일 생성까지(HTTP) + 실패 주입 ──────────────────────────────────────────

class EndToEndFilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.srv = Server()
        try:
            cls.meal = cls.srv.run(meal_docx(), meal_req(), "일룸홀딩스")
            cls.meal_skip = ""
        except unittest.SkipTest as e:   # 실데이터가 없어도 상담 대행·원자재 납품 시험은 돈다
            cls.meal, cls.meal_skip = None, str(e)
        cls.outs = cls.srv.run(OUTSOURCE_TXT, GENERAL_REQ, "퍼시스")
        cls.supply = cls.srv.run(SUPPLY_TXT, GENERAL_REQ, "퍼시스")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.srv.close()

    def _need_meal(self) -> None:
        if self.meal is None:
            self.skipTest(self.meal_skip)

    def test_meal_word_has_revisions_in_right_articles(self) -> None:
        self._need_meal()
        acc = self.meal["accepted"]
        a15 = " ".join(article_block(acc, "15"))
        self.assertIn("본 조의 위약금 산정 기준 금액은 별지 1에 기재된 고객회사 서비스 이용료에 한하며", a15)
        self.assertIn("손해배상액의 예정으로 보며", a15)
        self.assertIn("본 계약을 해지할 수 있다", " ".join(article_block(acc, "13")))
        a8_2 = article_block(acc, "8의2")
        self.assertTrue(a8_2 and "개인정보의 처리" in a8_2[0])
        self.assertIn("개인을 알아볼 수 있는 정보", " ".join(article_block(acc, "18")))
        # 편집 지시문·시스템 표지가 계약 본문에 없다
        self.assertFalse([p for p in acc if re.search(r"다음\s*(?:문단|문장|항)을\s*추가한다|다음과\s*같이\s*수정한다", p)])
        # 조 번호 중복 없음
        heads = [m.group(0).replace(" ", "") for p in acc for m in [re.match(r"^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?", p)] if m
                 and re.match(r"^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\s*\(", p)]
        self.assertEqual(len(heads), len(set(heads)), heads)

    def test_meal_records_and_consistency(self) -> None:
        self._need_meal()
        m = self.meal["meta"]
        self.assertEqual(m["final_docx_check"]["status"], "통과", m["final_docx_check"])
        self.assertFalse(m["final_docx_check"].get("final_blocked"))
        self.assertTrue(m["output_consistency"]["ok"], m["output_consistency"])
        self.assertEqual(self.meal["clean_status"], 200)
        applied = {r["clause_id"]: r["status"] for r in m["redline_apply_report"]}
        for k in ("link_penalty_scope", "link_convenience_termination", "privacy_privacy_flow"):
            self.assertEqual(next(v for c, v in applied.items() if c.startswith(k)), "applied")

    def test_meal_report_sections(self) -> None:
        self._need_meal()
        t = self.meal["report_text"]
        for s in ("0-0. 우리 역할과 실제 거래 흐름", "서명 전 확인", "계약에서 빠져나오는 길", "0-1. 개인정보 처리 흐름",
                  "데이터 제공·서비스 개시 전 충족할 조건", "중도해지 가능 여부", "해지 시 위약금·비용"):
            self.assertIn(s, t)

    def test_app_screen_shows_same_flow_sections(self) -> None:
        self._need_meal()
        heads = [s[0] for s in self.meal["meta"]["business_brief_sections"]]
        self.assertTrue(any(h.startswith("0-0.") for h in heads), heads)
        self.assertTrue(any(h.startswith("0-1. 개인정보 처리 흐름") for h in heads), heads)
        self.assertIn("0-1. 개인정보 처리 흐름", self.meal["report_text"])   # 같은 절이 검토의견서에도

    def test_outsourcing_word_gets_privacy_article(self) -> None:
        acc = self.outs["accepted"]
        blk = article_block(acc, "2의2")
        self.assertTrue(blk and "개인정보의 처리" in blk[0], acc[:30])
        self.assertEqual(self.outs["meta"]["final_docx_check"]["status"], "통과")

    def test_supply_word_has_no_privacy_or_entrustment_clause(self) -> None:
        acc = " ".join(self.supply["accepted"])
        self.assertNotIn("개인정보", acc)
        self.assertNotIn("위탁", acc)
        self.assertFalse((self.supply["meta"].get("deal_flow") or {}).get("privacy", {}).get("active"))
        # 대금을 내는 우리(갑)는 매수인 — 관형절 주어("을이 발행한")로 뒤집히지 않고, 공급자 관점 체크리스트 문구는 보류
        role = self.supply["meta"]["deal_flow"]["role"]
        self.assertEqual(role["our_role_kind"], "buyer")
        codes = {c["code"] for c in self.supply["meta"]["deal_flow"]["fact_corrections"]}
        self.assertIn("OPPOSITE_SIDE_CHECKLIST", codes)
        self.assertEqual(self.supply["clean_status"], 200)
        self.assertEqual(self.supply["meta"]["final_docx_check"]["status"], "통과")

    def test_injected_omission_is_regenerated(self) -> None:
        self._need_meal()
        from runtime.questions.storage import load_session
        from runtime.review.delivery_docs import finalize_review_meta

        doc = load_session(self.meal["sid"])
        rr = copy.deepcopy(doc["review_result"])
        b = dropping_build("link_penalty_scope", times=1)
        finalize_review_meta(doc, rr, build=b)
        fc = rr["clause_meta"]["final_docx_check"]
        self.assertGreaterEqual(len(fc["history"]), 2)
        self.assertTrue(any("NOT_IN_DOCX" in p for p in fc["history"][0]["problems"]))
        self.assertEqual(fc["status"], "통과")
        self.assertFalse(fc["final_blocked"])

    def test_persistent_omission_blocks_final(self) -> None:
        self._need_meal()
        from runtime.questions.storage import load_session, save_session
        from runtime.review.delivery_docs import finalize_review_meta

        doc = load_session(self.meal["sid"])
        rr = copy.deepcopy(doc["review_result"])
        finalize_review_meta(doc, rr, build=dropping_build("link_penalty_scope", times=99))
        meta = rr["clause_meta"]
        fc = meta["final_docx_check"]
        self.assertEqual(fc["status"], "미통과")
        self.assertTrue(fc["final_blocked"])
        self.assertTrue(any(x["clause_id"].startswith("link_penalty_scope") for x in fc["not_reflected"]))
        self.assertTrue(any(u["category"] == "제안만 있음·파일 미반영" for u in fc["unresolved"]))
        self.assertEqual(meta["verification_gate"]["status"], "검증 미통과 초안")
        self.assertTrue(meta["final_output_blocked"]["items"])
        brief = json.dumps(meta["business_brief"], ensure_ascii=False)
        self.assertIn("제안만 있음·파일 미반영", brief)
        # 저장된 세션으로 실제 다운로드 경로 확인 — 클린본(최종본) 거부, 변경추적본은 표지와 함께 제공
        doc2 = copy.deepcopy(doc)
        doc2["review_result"] = rr
        doc2["session_id"] = doc["session_id"] + "_blocked" if False else doc["session_id"]
        save_session(doc2)
        try:
            body, code = self.srv.clean(self.meal["sid"])
            self.assertEqual(code, 409)
            self.assertIn("최종본 출력 차단", body["error"])
            red = _post(self.srv.base + "/api/revision/download_redline", {"session_id": self.meal["sid"]}, raw=True)
            self.assertIn("검증 미통과 초안", accepted(red)[0])
        finally:
            save_session(doc)   # 원래 결과로 되돌린다


if __name__ == "__main__":
    unittest.main()
