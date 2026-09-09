"""시니어 사내변호사형 검토 아키텍처 회귀테스트 (2026-09-09 지시).

이 파일은 아래 항목을 고정한다. 각 테스트는 실제 계약(호텔 신축 공사도급계약)
에서 관찰된 실패를 그대로 재현한다.

  항목 2  계약유형을 제목이 아니라 법률효과로 판정 + 불확실 시 게이트
  항목 3  이전 문서 오염 차단 + 문서 단위 상태 격리
  항목 5  교차조항 검토 — 다른 조항의 보호장치를 근거로 판단
  항목 6  원문 사실 검증 — "없다"는 주장이 사실인지 확인
  항목 9  핵심 상업조건(금액·기간·지급시기) 확정 여부

특정 계약서·회사명·조항번호를 하드코딩하지 않는지도 함께 검사한다.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.project_paths import CODE_REPO_ROOT
from runtime.review.commercial_terms_gate import (
    STATUS_BLANK,
    STATUS_EXTERNAL,
    STATUS_PRESENT,
    build_commercial_terms_findings,
    scan_commercial_terms,
)
from runtime.review.contract_type_resolution import (
    REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN,
    declared_type_code,
    declared_type_conflicts,
    resolve_contract_type,
)
from runtime.review.cross_clause_protection import (
    absence_claims,
    find_protections,
    reconcile_absence_claims,
)
from runtime.review.review_isolation import (
    NON_INHERITABLE_STATE_KEYS,
    REVIEW_FAILED_CROSS_DOCUMENT_CONTAMINATION,
    detect_contamination,
    document_id_for,
    new_scope,
    scrub_contaminated_findings,
    strip_inherited_state,
)

FIX = CODE_REPO_ROOT / "runtime" / "tests" / "fixtures"

#: 갑지가 비어 있는 공사도급계약(실측 구조를 합성으로 재현).
COVER_UNSETTLED = """공사도급계약서
1. 공 사 명 : 숙박시설 신축공사
3. 착 공 일 : 금융기표일
4. 준공 예정일 : 실착공일로부터 [ ] 개월
5. 계 약 금 액 : 일금       정 (\\        원. 부가가치세 별도)
6. 계약이행보증 : 계약금액의 10% 현금 또는 보증서
10. 정 산 금 : 준공검사 합격일로부터 14일 이내 지급
12. 하자담보책임 : 계약금액의 3% 보증서
제30조 [지체상금] 매 지체일수마다 지체상금률(1/1000)을 계약금액에 곱하여 산출한다.
"""

COVER_SETTLED = """공사도급계약서
1. 공 사 명 : 사옥 리모델링 공사
3. 착 공 일 : 2026. 10. 1.
4. 준공 예정일 : 2027. 3. 31.
5. 계 약 금 액 : 일금 이십억원정 (2,000,000,000원)
6. 계약이행보증 : 계약금액의 10% 보증서
10. 정 산 금 : 준공검사 합격일로부터 14일 이내 지급
12. 하자담보책임 : 계약금액의 3% 보증서
"""


# ═══════════════════════════════════════════════════════════════════════════
# 항목 2 — 계약유형은 제목이 아니라 법률효과로
# ═══════════════════════════════════════════════════════════════════════════

class ContractTypeByLegalEffectTest(unittest.TestCase):
    _EXPECT = {
        "construction_works_contract.txt": "construction_contract",
        "nda_basic.txt": "nda_confidentiality",
        "app_dev_contract.txt": "development_service",
        "webzen_equipment_purchase_install.txt": "supply_installation",
        "lg_purchase_installation.txt": "supply_installation",
        "fursys_rental_standard_contract.txt": "rental_lease",
        "fursys_consignment_dealer.txt": "sales_agency",
        "_lm_license_1.txt": "license",
    }

    def test_fixtures_resolve_to_the_right_family(self) -> None:
        missing = []
        for name, expect in self._EXPECT.items():
            p = FIX / name
            if not p.is_file():
                continue
            r = resolve_contract_type(p.read_text(encoding="utf-8"))
            with self.subTest(fixture=name):
                self.assertEqual(r.contract_type_code, expect,
                                 f"{name}: {r.reason[:120]}")
                missing.append(name)
        self.assertGreaterEqual(len(missing), 5, "검증할 fixture 가 너무 적다")

    def test_english_contract_is_not_korean_only(self) -> None:
        """범용이려면 언어에 종속되면 안 된다 — 영문 라이선스 계약."""
        p = FIX / "_lm_license_1.txt"
        if not p.is_file():
            self.skipTest("영문 라이선스 fixture 없음")
        r = resolve_contract_type(p.read_text(encoding="utf-8"))
        self.assertEqual(r.contract_type_code, "license")

    def test_nda_is_residual_not_primary(self) -> None:
        """비밀유지 '조항'이 있다고 NDA 로 분류하면 안 된다."""
        text = (
            "물품공급 및 설치계약서\n"
            "수급인은 장비를 납품하고 설치 및 시운전을 완료한다. "
            "검수 완료 후 소유권과 위험이 이전한다.\n"
            "제12조 (비밀유지) 양 당사자는 비밀정보를 제3자에게 누설하지 않으며, "
            "목적 외 사용을 금지하고 계약 종료 시 반환 또는 폐기한다."
        )
        r = resolve_contract_type(text)
        self.assertEqual(r.contract_type_code, "supply_installation")

    def test_uncertain_when_no_signal(self) -> None:
        r = resolve_contract_type("본 합의서는 당사자 간 협력에 관한 것이다.")
        self.assertTrue(r.uncertain)
        self.assertEqual(r.to_dict()["review_status"],
                         REVIEW_FAILED_CONTRACT_TYPE_UNCERTAIN)
        self.assertEqual(r.contract_type_code, "", "불확실인데 유형을 단정했다")

    def test_declared_type_conflict_is_reported(self) -> None:
        """실측: 공사도급계약이 '앱개발/SI/SaaS'로 선언되어 있었다."""
        r = resolve_contract_type(COVER_UNSETTLED + "수급인은 준공검사를 받는다. 기성금 지급.")
        msg = declared_type_conflicts(r, "앱개발/소프트웨어개발/SI/유지보수/SaaS")
        self.assertTrue(msg, "선언 유형 불일치를 보고하지 않았다")
        self.assertIn("공사도급계약", msg)
        self.assertIn("주입하지 않았습니다", msg)

    def test_declared_label_maps_to_code(self) -> None:
        self.assertEqual(declared_type_code("앱개발/소프트웨어개발/SI"), "development_service")
        self.assertEqual(declared_type_code("공사도급계약서(건축)"), "construction_contract")
        self.assertEqual(declared_type_code("알 수 없는 무언가"), "")


# ═══════════════════════════════════════════════════════════════════════════
# 항목 3 — 이전 문서 오염 차단
# ═══════════════════════════════════════════════════════════════════════════

class CrossDocumentIsolationTest(unittest.TestCase):
    def test_document_id_follows_content_not_filename(self) -> None:
        a = document_id_for("같은 내용", filename="a.pdf")
        b = document_id_for("같은 내용", filename="b.docx")
        c = document_id_for("다른 내용", filename="a.pdf")
        self.assertEqual(a, b, "파일명이 다르다고 다른 문서로 보면 캐시가 무의미해진다")
        self.assertNotEqual(a, c)

    def test_previous_document_state_is_not_inherited(self) -> None:
        scope = new_scope("새 계약 본문", filename="new.pdf")
        prev = {
            "contract_type": "nda_confidentiality",
            "mandatory_review_issues": [{"code": "x"}],
            "answers": {"jurisdiction": "foreign"},
            "clause_results": [{"clause_id": "old"}],
            "suggested_template_ids": ["nda_template"],
        }
        cleaned = strip_inherited_state(prev, scope)
        for k in NON_INHERITABLE_STATE_KEYS:
            self.assertIsNone(cleaned.get(k), f"{k} 가 승계됐다")
        self.assertTrue(cleaned["inherited_state_stripped"])
        self.assertTrue(scope.owns(cleaned["review_scope"]))

    def test_same_document_state_is_kept(self) -> None:
        scope = new_scope("본문", filename="a.pdf")
        state = {"contract_type": "construction_contract", "review_scope": scope.to_dict()}
        kept = strip_inherited_state(state, scope)
        self.assertEqual(kept["contract_type"], "construction_contract")

    def test_terms_from_another_contract_are_detected(self) -> None:
        """실측: 공사도급계약 결과에 KOTRA 컨설팅계약 용어가 섞였다."""
        text = "공사도급계약서\n수급인은 준공검사를 받는다."
        crs = [{
            "clause_id": "clr_conditional_funding_unclear",
            "display_path": "",
            "issue_title": "조건부 자금 반환주체 불명확",
            "suggested_rewrite": (
                "Consultant 의 귀책인지 Company 의 귀책인지 구분하고, "
                "관련 Participation Agreement 와의 관계를 명시한다."
            ),
        }]
        hits = detect_contamination(crs, contract_text=text)
        self.assertEqual(len(hits), 1)
        self.assertIn("Consultant", hits[0]["terms"])
        self.assertIn("Participation Agreement", hits[0]["terms"])

    def test_terms_actually_in_the_contract_are_not_flagged(self) -> None:
        text = "LICENSE AGREEMENT between Licensor and Teknion Limited."
        crs = [{
            "clause_id": "x", "issue_title": "Licensor 의 권리 범위",
            "suggested_rewrite": "Teknion Limited 의 실시 범위를 명시한다.",
        }]
        self.assertEqual(detect_contamination(crs, contract_text=text), [])

    def test_generic_legal_english_is_not_contamination(self) -> None:
        crs = [{
            "clause_id": "x", "issue_title": "Force Majeure 조항 미비",
            "suggested_rewrite": "Force Majeure 및 Indemnity 조항을 신설한다.",
        }]
        self.assertEqual(detect_contamination(crs, contract_text="공사도급계약서"), [])

    def test_scrub_removes_but_does_not_fail_the_review(self) -> None:
        """걷어냈으면 출력은 깨끗하다 — 실패로 막으면 정상 결과를 못 받는다."""
        crs = [{
            "clause_id": "a", "issue_title": "Participation Agreement 우선순위",
            "suggested_rewrite": "Participation Agreement 를 우선한다.",
        }]
        rep = scrub_contaminated_findings(crs, contract_text="공사도급계약서")
        self.assertEqual(rep["removed_count"], 1)
        self.assertTrue(crs[0]["dedup_suppressed"])
        self.assertEqual(rep["residual"], [], "제거 후에도 오염이 남았다")
        self.assertEqual(rep["status"], "", "제거에 성공했는데 실패로 처리했다")

    def test_residual_contamination_does_fail(self) -> None:
        """걷어낼 수 없는 오염이 남으면 실패다."""
        crs = [{
            "clause_id": "a", "dedup_suppressed": True,  # 이미 숨겨져 scrub 대상 아님
            "issue_title": "Participation Agreement",
        }]
        rep = scrub_contaminated_findings(crs, contract_text="공사도급계약서")
        self.assertEqual(rep["removed_count"], 0)
        self.assertEqual(rep["status"], "", "숨겨진 항목은 출력이 아니므로 실패가 아니다")

    def test_engine_vocabulary_is_not_contamination(self) -> None:
        """심각도 라벨·상태 코드는 원문에 없는 것이 당연하다."""
        crs = [{
            "clause_id": "a", "issue_title": "CRITICAL 등급 재검토",
            "problem": "REVIEW_FAILED_SEMANTIC_MISMATCH 상태였다.",
            "suggested_rewrite": "HIGH 에서 MEDIUM 으로 조정한다.",
        }]
        self.assertEqual(detect_contamination(crs, contract_text="공사도급계약서"), [])


# ═══════════════════════════════════════════════════════════════════════════
# 항목 5·6 — 교차조항 보호장치 확인 / 원문 사실 검증
# ═══════════════════════════════════════════════════════════════════════════

class CrossClauseProtectionTest(unittest.TestCase):
    _CAPPED = (
        "13. 지체 상금률 : 매 지체일수 마다 총계약금액 1/1,000(계약금액의 10%이내)\n"
        "제30조 [지체상금]\n"
        "1. 매 지체일수마다 지체상금률(1/1000)을 계약금액에 곱하여 산출한다.\n"
        "5. 지체상금으로 발생할 수 있는 최대금액은 계약금액의 10% 까지로 한다.\n"
    )
    _UNCAPPED = (
        "제5조 (지체상금) 지체일수 1일당 계약금액의 1천분의 3을 지급한다. "
        "지체상금에는 상한을 두지 아니한다.\n"
    )

    def _finding(self) -> dict:
        return {
            "clause_id": "clr_late_penalty_rate_uncapped",
            "display_path": "제30조", "risk_tier": "HIGH", "severity": "HIGH",
            "issue_title": "지체상금 누계 상한이 없음",
            "rewrite_reason": "지체상금에 누계 상한이 없어 무제한 누적된다.",
        }

    def test_protection_is_found_across_clauses(self) -> None:
        prot = find_protections(self._CAPPED)
        self.assertIn("late_penalty_cap", prot)
        self.assertGreaterEqual(len(prot["late_penalty_cap"]), 1)

    def test_absence_claim_is_detected(self) -> None:
        self.assertIn("late_penalty_cap", absence_claims(self._finding()))

    def test_false_absence_claim_is_corrected_not_deleted(self) -> None:
        """삭제하면 정합성 게이트가 '금전 리스크 미확인'으로 다운로드를 막는다."""
        cr = self._finding()
        rep = reconcile_absence_claims([cr], contract_text=self._CAPPED)
        self.assertEqual(rep["corrected_count"], 1)
        self.assertFalse(cr.get("dedup_suppressed"), "정정이어야 하는데 삭제했다")
        self.assertEqual(cr["risk_tier"], "MEDIUM", "등급이 내려가지 않았다")
        self.assertIn("교차조항 확인", cr["rewrite_reason"])
        self.assertTrue(cr["cross_clause_protection_evidence"])

    def test_true_absence_claim_is_untouched(self) -> None:
        cr = self._finding()
        rep = reconcile_absence_claims([cr], contract_text=self._UNCAPPED)
        self.assertEqual(rep["corrected_count"], 0)
        self.assertEqual(cr["risk_tier"], "HIGH")

    def test_reconcile_is_idempotent(self) -> None:
        cr = self._finding()
        reconcile_absence_claims([cr], contract_text=self._CAPPED)
        again = reconcile_absence_claims([cr], contract_text=self._CAPPED)
        self.assertEqual(again["corrected_count"], 0)
        self.assertEqual(cr["risk_tier"], "MEDIUM")

    def test_unrelated_topic_protection_does_not_excuse(self) -> None:
        """다른 주제의 상한이 있다고 이 주장이 틀린 것은 아니다."""
        cr = self._finding()
        other = "제11조 손해배상 총액은 계약금액의 20%를 한도로 한다.\n"
        rep = reconcile_absence_claims([cr], contract_text=other)
        self.assertEqual(rep["corrected_count"], 0)


# ═══════════════════════════════════════════════════════════════════════════
# 항목 9 — 핵심 상업조건
# ═══════════════════════════════════════════════════════════════════════════

class CommercialTermsTest(unittest.TestCase):
    def test_blank_amount_and_dates_are_detected(self) -> None:
        rows = {r["key"]: r for r in
                scan_commercial_terms(COVER_UNSETTLED, contract_type_code="construction_contract")}
        self.assertEqual(rows["contract_amount"]["status"], STATUS_BLANK)
        self.assertEqual(rows["completion_date"]["status"], STATUS_BLANK)
        self.assertEqual(rows["start_date"]["status"], STATUS_EXTERNAL)

    def test_reference_sentence_is_not_mistaken_for_a_value(self) -> None:
        """'계약이행보증 : 계약금액의 10%' 는 금액을 **참조**할 뿐이다."""
        rows = {r["key"]: r for r in
                scan_commercial_terms(COVER_UNSETTLED, contract_type_code="construction_contract")}
        self.assertEqual(rows["contract_amount"]["status"], STATUS_BLANK)
        self.assertEqual(rows["performance_bond"]["status"], STATUS_PRESENT)

    def test_blank_amount_is_high_and_explains_the_linkage(self) -> None:
        findings, _ = build_commercial_terms_findings(
            COVER_UNSETTLED, contract_type_code="construction_contract")
        amount = [f for f in findings if f["commercial_term_key"] == "contract_amount"]
        self.assertEqual(len(amount), 1)
        self.assertEqual(amount[0]["risk_tier"], "HIGH")
        self.assertIn("계약이행보증", amount[0]["rewrite_reason"])

    def test_bounded_period_after_an_event_is_settled(self) -> None:
        """'사용승인일로부터 14일 이내'는 확정된 지급조건이다."""
        rows = {r["key"]: r for r in
                scan_commercial_terms(COVER_UNSETTLED, contract_type_code="construction_contract")}
        self.assertEqual(rows["payment_schedule"]["status"], STATUS_PRESENT)

    def test_complete_cover_sheet_produces_nothing(self) -> None:
        findings, rows = build_commercial_terms_findings(
            COVER_SETTLED, contract_type_code="construction_contract")
        self.assertEqual(findings, [], [r for r in rows if r["status"] != STATUS_PRESENT])

    def test_nda_is_exempt(self) -> None:
        """NDA 에 계약금액이 없는 것은 정상 — 검사하면 전부 오탐이다."""
        self.assertEqual(
            scan_commercial_terms(COVER_UNSETTLED, contract_type_code="nda_confidentiality"), [])


# ═══════════════════════════════════════════════════════════════════════════
# 범용성 — 특정 계약서·회사명을 하드코딩하지 않았는가
# ═══════════════════════════════════════════════════════════════════════════

class NoHardcodingTest(unittest.TestCase):
    _MODULES = (
        "review_isolation.py",
        "commercial_terms_gate.py",
        "contract_type_resolution.py",
        "cross_clause_protection.py",
    )
    #: 실제 거래처·프로젝트를 가리키는 고유명사. 로직에 들어가면 범용이 아니다.
    _FORBIDDEN = ("역삼동", "에이슬립", "KOTRA", "퍼시스", "시디즈", "일룸",
                  "Teknion", "FURSYS", "WEBZEN")

    @staticmethod
    def _code_only(path: Path) -> str:
        """주석과 docstring 을 토큰 단위로 제거한 '실행되는 코드'만 남긴다.

        줄 단위로 `#`/`\"\"\"` 를 걸러내는 방식은 **여러 줄 docstring 의 본문**을
        코드로 오인한다 — 실측 사례를 기록한 모듈 docstring 때문에 이 테스트가
        스스로 오탐을 냈다. tokenize 로 COMMENT 와 삼중따옴표 STRING 을 지운다.
        """
        import io as _io
        import tokenize as _tok

        src = path.read_text(encoding="utf-8")
        kept: list[str] = []
        try:
            for tok in _tok.generate_tokens(_io.StringIO(src).readline):
                if tok.type == _tok.COMMENT:
                    continue
                if tok.type == _tok.STRING and tok.string.lstrip("rbufRBUF")[:3] in ('"""', "'''"):
                    continue  # docstring / 블록 주석용 문자열
                kept.append(tok.string)
        except _tok.TokenError:  # pragma: no cover
            return src
        return "\n".join(kept)

    def test_no_specific_party_or_project_in_logic(self) -> None:
        for name in self._MODULES:
            code = self._code_only(CODE_REPO_ROOT / "runtime" / "review" / name)
            for term in self._FORBIDDEN:
                with self.subTest(module=name, term=term):
                    self.assertNotIn(term, code, f"{name} 로직에 고유명사 {term} 가 있다")

    def test_no_article_number_hardcoding(self) -> None:
        import re as _re

        for name in self._MODULES:
            code = self._code_only(CODE_REPO_ROOT / "runtime" / "review" / name)
            hits = _re.findall(r"제\s*\d+\s*조", code)
            with self.subTest(module=name):
                self.assertEqual(hits, [], f"{name} 로직에 조항번호 하드코딩: {hits}")

    def test_the_stripper_itself_works(self) -> None:
        """이 검사가 무력하지 않은지 — 코드에 있는 고유명사는 반드시 잡아야 한다."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "probe.py"
            p.write_text(
                '"""문서 docstring 에 KOTRA 와 제30조 언급 — 허용되어야 한다."""\n'
                "# 주석에 역삼동 언급 — 허용되어야 한다\n"
                'BAD = "KOTRA"  # 코드 문자열 — 잡혀야 한다\n',
                encoding="utf-8",
            )
            code = self._code_only(p)
            self.assertIn("KOTRA", code, "코드 문자열의 고유명사를 놓쳤다")
            self.assertNotIn("역삼동", code, "주석을 제거하지 못했다")
            self.assertNotIn("제30조", code, "docstring 을 제거하지 못했다")


if __name__ == "__main__":
    unittest.main()
