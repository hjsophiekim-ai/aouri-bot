"""수정본 생성(다운로드)을 막던 4가지 원인 회귀테스트 (2026-09-09).

사용자 보고: 건설(공사도급)계약을 검토하고 "수정본 생성하기"를 눌러도 계속
실패. 재현해 보니 게이트 하나가 아니라 **네 겹**이었고, 앞의 것을 고치면
다음 것이 드러났다. 네 가지 모두를 여기서 고정한다.

  1. 캐시가 코드 변경을 무시  (가장 치명적)
     `run_review_with_session()` 의 캐시 시그니처에 엔진 버전이 없어서,
     같은 문서·같은 세션이면 엔진을 고쳐도 **저장된 실패 결과를 그대로**
     돌려줬다. 사용자가 몇 번을 다시 눌러도 완전히 동일한 실패만 반복된다.
     → 시그니처에 runtime/review 소스 지문 + rules_sha256 포함,
       그리고 rebuild=true 는 force 로 캐시 우회.

  2. 계약 전반 권고가 REVIEW_FAILED_INCOMPLETE_REDLINE 을 유발
     대응 조항이 없는 finding(clr_conditional_funding_unclear)은
     original_text 가 자리표시자라 edit_location 이 영영 "위치 확인 필요"에
     머물렀다. → 신설(new_clause)로 정규화.

  3. 지체상금 표기를 못 잡아 REVIEW_FAILED_GLOBAL_REASONING
     "지체상금률(1/1000)을 계약금액에 곱하여" 형태(표준 공사도급계약 서식)를
     요율 정규식이 놓쳤다. → 해당 어순 추가.

  4. MEDIUM 10건 상한이 hard gate 가 요구하는 finding 을 잘라냄
     표시용 cap 이 clr_late_penalty_rate_uncapped 를 11번째로 밀어내자
     게이트가 "금전 리스크 미확인"으로 판단해 다운로드를 막았다.
     → 고노출(_HIGH_EXPOSURE_CLAUSE_IDS) finding 은 cap 면제.

교훈: 표시용 필터가 정합성 게이트가 요구하는 데이터를 지우면 안 된다.
"""
from __future__ import annotations

import unittest

from runtime.review.output_filter import (
    _HIGH_EXPOSURE_CLAUSE_IDS,
    ReviewIssue,
    filter_issues,
)
from runtime.review.redline_instruction import (
    _LOCATION_UNCERTAIN,
    LOCATION_CONTRACT_WIDE_NEW,
    build_redline_instruction,
    is_incomplete_redline,
    is_placeholder_original,
    normalize_redline_instruction,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 캐시가 코드 변경을 반영하는가
# ═══════════════════════════════════════════════════════════════════════════

class ReviewCacheInvalidationTest(unittest.TestCase):
    def test_engine_fingerprint_is_stable_and_nonempty(self) -> None:
        from runtime.questions.storage import _review_engine_fingerprint

        fp = _review_engine_fingerprint()
        self.assertTrue(fp and len(fp) >= 8, fp)
        self.assertEqual(fp, _review_engine_fingerprint(), "같은 소스에서 값이 흔들린다")

    def test_fingerprint_changes_when_engine_source_changes(self) -> None:
        """엔진 소스가 바뀌면 지문이 달라져 캐시가 자동 무효화되어야 한다."""
        import runtime.questions.storage as storage

        original = storage._review_engine_fingerprint()
        storage._review_engine_fingerprint.cache_clear()
        try:
            # 임시 파일을 review 디렉터리에 추가해 소스 집합을 바꾼다.
            probe = storage._REVIEW_ENGINE_DIR / "_fingerprint_probe_tmp.py"
            probe.write_text("# temporary probe\n", encoding="utf-8")
            try:
                changed = storage._review_engine_fingerprint()
            finally:
                probe.unlink(missing_ok=True)
                storage._review_engine_fingerprint.cache_clear()
        except OSError:
            self.skipTest("review 디렉터리에 쓸 수 없음")
        self.assertNotEqual(original, changed, "소스가 바뀌었는데 지문이 그대로다")
        self.assertEqual(original, storage._review_engine_fingerprint())

    def test_review_runners_accept_force(self) -> None:
        import inspect

        from runtime.questions.storage import (
            run_review_with_session,
            run_review_with_session_fast,
        )

        for fn in (run_review_with_session, run_review_with_session_fast):
            params = inspect.signature(fn).parameters
            self.assertIn("force", params, f"{fn.__name__} 에 force 인자가 없다")
            self.assertIs(params["force"].default, False)

    def test_download_endpoint_forces_rebuild(self) -> None:
        """rebuild=true 인데 캐시를 돌려주면 '다시 눌러도 같은 실패'가 된다."""
        from pathlib import Path

        from runtime.project_paths import CODE_REPO_ROOT

        src = (CODE_REPO_ROOT / "runtime" / "api" / "server.py").read_text(encoding="utf-8")
        self.assertIn("run_review_with_session(service, session_id, force=True)", src)
        self.assertNotIn(
            "\n                    review_result = run_review_with_session(service, session_id)\n",
            src,
            "다운로드 경로에 force 없는 호출이 남아 있다",
        )
        self.assertTrue(Path(CODE_REPO_ROOT / "runtime" / "api" / "server.py").is_file())


# ═══════════════════════════════════════════════════════════════════════════
# 2. 계약 전반 권고 → 신설 정규화
# ═══════════════════════════════════════════════════════════════════════════

class ContractWideRedlineTest(unittest.TestCase):
    _PLACEHOLDER = "(조건부 자금 관련 조항 전반)"
    _BODY = "[추가 권고]\n지원금이 중단되는 경우 반환주체를 명확히 구분한다."

    def test_placeholder_detection(self) -> None:
        for t in (self._PLACEHOLDER, "(해당 조항 없음)", "(전체)", ""):
            self.assertTrue(is_placeholder_original(t), t)
        for t in ("제5조 지체상금은 …", "수급인은 준공기한 내에 공사를 완성하지 못한 경우"):
            self.assertFalse(is_placeholder_original(t), t)

    def test_builder_normalizes_to_new_clause(self) -> None:
        inst = build_redline_instruction(
            finding_id="f1", clause_id="clr_conditional_funding_unclear", severity="MEDIUM",
            edit_location=_LOCATION_UNCERTAIN, edit_type="replace",
            target_text=self._PLACEHOLDER,
            replacement_text=f"{self._PLACEHOLDER}\n\n{self._BODY}",
            reason="조건부 자금 구조 미비", original_text=self._PLACEHOLDER,
        )
        self.assertEqual(inst["edit_type"], "new_clause")
        self.assertEqual(inst["edit_location"], LOCATION_CONTRACT_WIDE_NEW)
        self.assertNotIn(self._PLACEHOLDER, inst["final_clause_text"])
        self.assertIn("반환주체", inst["final_clause_text"])
        self.assertFalse(is_incomplete_redline(inst))

    def test_normalizer_fixes_already_stored_instruction(self) -> None:
        """룰이 만든 instruction 은 보존되므로 게이트 직전 정규화가 필요하다."""
        stored = {
            "clause_id": "clr_conditional_funding_unclear",
            "edit_location": _LOCATION_UNCERTAIN,
            "edit_type": "replace",
            "target_text": self._PLACEHOLDER,
            "replacement_text": f"{self._PLACEHOLDER}\n\n{self._BODY}",
            "final_clause_text": f"{self._PLACEHOLDER}\n\n{self._BODY}",
        }
        self.assertTrue(is_incomplete_redline(stored))
        fixed = normalize_redline_instruction(stored)
        self.assertFalse(is_incomplete_redline(fixed))
        self.assertEqual(fixed["edit_type"], "new_clause")
        self.assertTrue(fixed["normalized_as_contract_wide_new_clause"])

    def test_real_clause_with_unknown_location_stays_incomplete(self) -> None:
        """실제 조문이 있는데 위치만 못 찾은 경우는 게이트가 계속 잡아야 한다."""
        stored = {
            "clause_id": "x",
            "edit_location": _LOCATION_UNCERTAIN,
            "edit_type": "replace",
            "target_text": "",
            "replacement_text": "새 문구",
            "final_clause_text": "새 문구",
            "original_text": "제7조 본 공사와 관련하여 발생하는 모든 사고의 책임은 수급인이 부담한다",
        }
        fixed = normalize_redline_instruction(stored)
        self.assertEqual(fixed["edit_type"], "replace")
        self.assertTrue(is_incomplete_redline(fixed))

    def test_normalizer_is_idempotent(self) -> None:
        stored = {
            "clause_id": "c", "edit_location": _LOCATION_UNCERTAIN, "edit_type": "replace",
            "target_text": self._PLACEHOLDER,
            "replacement_text": f"{self._PLACEHOLDER}\n\n{self._BODY}",
            "final_clause_text": f"{self._PLACEHOLDER}\n\n{self._BODY}",
        }
        once = normalize_redline_instruction(stored)
        twice = normalize_redline_instruction(once)
        self.assertEqual(once, twice)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 표준 공사도급계약 지체상금 표기
# ═══════════════════════════════════════════════════════════════════════════

class LatePenaltyStandardFormTest(unittest.TestCase):
    def test_rate_in_parentheses_after_label(self) -> None:
        from runtime.review.common_legal_risk import _RX_LATE_PENALTY_RATE as RX

        text = (
            "매 지체일수마다 계약서상의\n지체상금률(1/1000)을 계약금액에 곱하여 "
            "산출한 금액을 “도급인”에게 납부하여야 한다."
        )
        m = RX.search(text)
        self.assertIsNotNone(m, "표준 서식 지체상금률 표기를 못 잡는다")
        self.assertEqual(m.group(7), "1")
        self.assertEqual(m.group(8), "1000")
        self.assertAlmostEqual(float(m.group(7)) / float(m.group(8)) * 100, 0.1, places=6)

    def test_rule_emits_finding_for_standard_form(self) -> None:
        from runtime.review.clause_extraction import extract_clauses
        from runtime.review.common_legal_risk import _apply_late_penalty_uncapped_check

        text = (
            "제 30 조 [지체상금]\n"
            "1. “수급인”은 준공예정일까지 공사를 완료하여야 하며, 그러하지 못한 때에는 "
            "매 지체일수마다 계약서상의\n지체상금률(1/1000)을 계약금액에 곱하여 산출한 "
            "금액을 “도급인”에게 납부하여야 한다.\n"
            "5. 지체상금으로 발생할 수 있는 최대금액은 계약금액의 10% 까지로 한다.\n"
        )
        clauses, _ = extract_clauses(text)
        out: list[dict] = []
        _apply_late_penalty_uncapped_check(out, text, clauses=clauses, our_party_aliases=["수급인"])
        self.assertEqual(len(out), 1, "지체상금 finding 이 생성되지 않았다")
        self.assertEqual(out[0]["clause_id"], "clr_late_penalty_rate_uncapped")
        # 상한(10%)이 같은 조문에 있으므로 HIGH 가 아니라 MEDIUM 이어야 한다.
        self.assertEqual(str(out[0]["risk_tier"]).upper(), "MEDIUM")
        self.assertIn("%", str(out[0].get("legal_business_reason") or ""))


# ═══════════════════════════════════════════════════════════════════════════
# 4. 표시용 cap 이 hard gate 데이터를 지우면 안 된다
# ═══════════════════════════════════════════════════════════════════════════

_ART = [0]


def _issue(clause_id: str, *, severity="MEDIUM", mandatory=False) -> ReviewIssue:
    """유효성·dedup 을 통과하도록 조항을 서로 다르게 준다 —
    같은 조항이면 deduplicate_issues 가 합쳐서 cap 테스트가 무의미해진다."""
    _ART[0] += 1
    art = str(_ART[0])
    return ReviewIssue(
        clause_id=clause_id,
        clause_title=f"제{art}조 [{clause_id}]",
        severity=severity,
        approval_required=False,
        issue_title=f"이슈 {clause_id} 에 대한 구체적 지적 사항",
        original_text=f"제{art}조 원문 텍스트가 충분히 길어야 유효 판정을 통과한다. " * 2,
        problem=f"{clause_id} 문제점 설명이 충분히 길어야 유효 판정을 통과한다. " * 2,
        legal_business_reason=f"{clause_id} 법적 이유. 배상액이 10% 수준에 달한다. " * 2,
        proposed_revision=f"제{art}조 수정문안이 충분히 길어야 유효 판정을 통과한다. " * 2,
        negotiation_position="협상 포지션",
        confidence=0.8,
        is_mandatory=mandatory,
        article_number=art,
    )


class HighExposureExemptFromCapTest(unittest.TestCase):
    def test_high_exposure_ids_include_the_gated_findings(self) -> None:
        """hard gate 가 존재를 요구하는 finding 은 cap 면제 목록에 있어야 한다."""
        for cid in ("clr_late_penalty_rate_uncapped", "clr_third_party_debt_guarantee"):
            self.assertIn(cid, _HIGH_EXPOSURE_CLAUSE_IDS)

    def test_high_exposure_survives_medium_cap(self) -> None:
        """MEDIUM 이 cap 을 넘겨도 고노출 finding 은 살아남아야 한다."""
        filler = [_issue(f"filler_{n}") for n in range(14)]
        gated = _issue("clr_late_penalty_rate_uncapped")
        out = filter_issues(filler + [gated], max_medium=10)
        medium_ids = {i.clause_id for i in out["medium"]}
        self.assertIn(
            "clr_late_penalty_rate_uncapped", medium_ids,
            "표시용 cap 이 hard gate 가 요구하는 finding 을 잘라냈다",
        )

    def test_ordinary_medium_is_still_capped(self) -> None:
        """면제가 cap 자체를 무력화하면 안 된다."""
        filler = [_issue(f"filler_{n}") for n in range(14)]
        out = filter_issues(filler, max_medium=10)
        self.assertEqual(len(out["medium"]), 10)

    def test_mandatory_still_exempt(self) -> None:
        filler = [_issue(f"filler_{n}") for n in range(14)]
        cited = _issue("user_cited", mandatory=True)
        out = filter_issues(filler + [cited], max_medium=10)
        self.assertIn("user_cited", {i.clause_id for i in out["medium"]})


if __name__ == "__main__":
    unittest.main()
