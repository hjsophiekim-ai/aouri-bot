"""시니어 사내변호사 판단층 회귀테스트 (2026-09-09 지시 항목 1·4·7·8·10·11·12·13)."""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.project_paths import CODE_REPO_ROOT
from runtime.review.finding_integrity_gates import (
    REVIEW_FAILED_SEMANTIC_REWRITE_MISMATCH,
    STATUS_SEMANTIC_MISMATCH,
)
from runtime.review.legal_map_gate import (
    LEGAL_MAP_AXES,
    REVIEW_FAILED_LEGAL_MAP_INCOMPLETE,
    blocking_axes_for,
    evaluate_legal_map,
)
from runtime.review.risk_allocation_matrix import (
    RISK_AXES,
    SIDE_OURS,
    SIDE_UNALLOCATED,
    build_risk_allocation_matrix,
    concentrated_risk_axes,
)
from runtime.review.senior_counsel_judgment import (
    BUCKET_ACCEPTABLE,
    BUCKET_MUST_FIX,
    BUCKET_NEGOTIABLE,
    NATURE_CONTRACTUAL,
    NATURE_MIXED,
    NATURE_STATUTORY,
    REVIEW_FAILED_LAWYER_SELF_CHECK,
    annotate_liability_nature,
    assign_negotiation_buckets,
    classify_liability_nature,
    classify_negotiation_bucket,
    explain_statute_linkage,
    final_lawyer_self_check,
)
from runtime.review.senior_counsel_pass import apply_high_severity_policy

_MODULES = (
    "legal_map_gate.py",
    "risk_allocation_matrix.py",
    "senior_counsel_judgment.py",
)


# ═══════════════════════════════════════════════════════════════════════════
# 항목 1 — Legal Map 완결성 게이트
# ═══════════════════════════════════════════════════════════════════════════

class LegalMapGateTest(unittest.TestCase):
    def test_all_fifteen_axes_are_covered(self) -> None:
        """지시가 요구한 15축이 모두 있어야 한다."""
        self.assertEqual(len(LEGAL_MAP_AXES), 15)
        labels = {label for _, label in LEGAL_MAP_AXES}
        for required in ("검수/인도/준공 조건", "위험 이전 시점",
                         "지식재산/자료 귀속", "적용 가능 법률"):
            self.assertIn(required, labels, f"{required} 축이 없다")

    def test_new_fields_exist_in_the_legal_map(self) -> None:
        from runtime.review.contract_legal_map import UNIVERSAL_FIELDS

        for key in ("acceptance_and_completion", "risk_transfer_point",
                    "ip_and_data_ownership", "applicable_statutes"):
            self.assertIn(key, UNIVERSAL_FIELDS, f"{key} 필드가 없다")

    def test_blocking_axes_differ_by_family(self) -> None:
        """NDA 에 위험이전 시점을 요구하면 전부 오탐이다."""
        works = blocking_axes_for("construction_contract")
        nda = blocking_axes_for("nda_confidentiality")
        self.assertIn("risk_transfer_point", works)
        self.assertNotIn("risk_transfer_point", nda)
        self.assertNotIn("payment_flow", nda)
        # 어떤 유형이든 최소한 성격·지위·급부는 필요하다.
        for axes in (works, nda):
            for k in ("contract_purpose", "our_role_direction", "primary_obligations"):
                self.assertIn(k, axes)

    def test_empty_map_is_incomplete(self) -> None:
        rep = evaluate_legal_map({k: None for k, _ in LEGAL_MAP_AXES},
                                 contract_type_code="construction_contract")
        self.assertFalse(rep["complete"])
        self.assertEqual(rep["review_status"], REVIEW_FAILED_LEGAL_MAP_INCOMPLETE)
        self.assertIn("계약의 법적 성격", rep["missing_blocking"])

    def test_blocking_filled_is_complete_even_with_advisory_gaps(self) -> None:
        filled = {k: None for k, _ in LEGAL_MAP_AXES}
        filled.update({
            "contract_purpose": "숙박시설 신축공사 도급",
            "our_role_direction": "provider",
            "primary_obligations": "공사 완성 및 사용승인 취득",
            "payment_flow": "기성금 + 정산금",
            "acceptance_and_completion": "준공검사 합격",
            "risk_transfer_point": "준공검사 합격 시",
        })
        rep = evaluate_legal_map(filled, contract_type_code="construction_contract")
        self.assertTrue(rep["complete"])
        self.assertEqual(rep["review_status"], "")
        self.assertTrue(rep["missing_advisory"], "advisory 누락이 보고되지 않았다")

    def test_placeholder_values_do_not_count_as_filled(self) -> None:
        rep = evaluate_legal_map(
            {k: "미확인" for k, _ in LEGAL_MAP_AXES},
            contract_type_code="construction_contract",
        )
        self.assertFalse(rep["complete"], "'미확인'을 채워진 것으로 봤다")

    def test_ai_off_review_is_not_blocked_by_an_empty_map(self) -> None:
        """Map 은 AI 산출물이다 — AI 를 끈 검토에서 축이 비는 건 구조적 결과다.

        게이트를 무조건 적용하면 ai_mode=off 나 키 부재로 regex fallback 을 탄
        검토가 전부 차단되어, 사용자가 고른 오프라인 모드 자체가 불가능해진다
        (2026-09-09 실측: 수정본 다운로드가 전부 409). Map 을 실제로 만들 수
        있었는데 미완인 경우(source="ai")만 막는다.
        """
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        fixture = (
            CODE_REPO_ROOT / "runtime" / "tests" / "fixtures"
            / "construction_works_contract.txt"
        )
        bundle = build_clause_level_result(
            service=RuleQueryService(loader),
            entity="테스트법인",
            contract_type="",
            text=fixture.read_text(encoding="utf-8"),
            filename="공사도급계약서.docx",
            answers=None,
            review_focus=None,
            law_service=None,
            ai_provider=None,   # AI 없음 → regex fallback
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
            max_clause_law_items=0,
        )
        rep = bundle.meta.get("legal_map_completeness") or {}
        self.assertTrue(rep, "legal_map_completeness 가 보고되지 않았다")
        self.assertEqual(
            rep.get("review_status"), "",
            "AI 없는 검토를 Legal Map 미완으로 차단했다",
        )
        self.assertIn("legal_map_source=", str(rep.get("blocking_skipped_reason") or ""))
        self.assertNotEqual(
            str(bundle.meta.get("review_status") or ""),
            "REVIEW_FAILED_LEGAL_MAP_INCOMPLETE",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 항목 4 — Risk Allocation Matrix
# ═══════════════════════════════════════════════════════════════════════════

class RiskAllocationMatrixTest(unittest.TestCase):
    _WORKS = """제5조 지체상금
수급인이 준공기한을 지키지 못하면 지체상금을 도급인에게 지급한다.
제7조 산업안전
본 공사와 관련하여 발생하는 모든 인적·물적 사고에 대한 일체의 책임은
수급인이 부담한다.
제9조 제3자 손해
수급인은 제3자에게 손해를 가한 때에는 그 손해를 배상할 책임을 진다.
제20조 보증금
계약이 해지된 경우 계약이행보증금은 도급인에게 귀속한다.
"""

    def test_all_sixteen_axes_present(self) -> None:
        """지시가 나열한 16개 위험축이 모두 있어야 한다."""
        self.assertEqual(len(RISK_AXES), 16)
        keys = {a.key for a in RISK_AXES}
        for k in ("schedule_delay", "payment_default", "design_change", "extra_work",
                  "acceptance", "defects", "safety_accident", "force_majeure",
                  "third_party_damage", "subcontractor", "insurance", "termination",
                  "bond_forfeiture", "damages", "setoff", "ip_data"):
            self.assertIn(k, keys, f"{k} 축이 없다")

    def test_our_side_bearing_is_detected(self) -> None:
        m = build_risk_allocation_matrix(self._WORKS, our_role_direction="provider")
        rows = {r["key"]: r for r in m["rows"]}
        self.assertEqual(rows["safety_accident"]["side"], SIDE_OURS)
        self.assertEqual(rows["third_party_damage"]["side"], SIDE_OURS)

    def test_matrix_flips_with_our_role(self) -> None:
        """호칭을 하드코딩하지 않았다면 지위를 뒤집으면 결과도 뒤집힌다."""
        a = build_risk_allocation_matrix(self._WORKS, our_role_direction="provider")
        b = build_risk_allocation_matrix(self._WORKS, our_role_direction="recipient")
        self.assertNotEqual(a["ours_count"], b["ours_count"])
        self.assertEqual(a["ours_count"], b["counterparty_count"])

    def test_missing_axis_is_unallocated(self) -> None:
        m = build_risk_allocation_matrix("제1조 목적. 본 계약은 협력에 관한 것이다.")
        rows = {r["key"]: r for r in m["rows"]}
        self.assertEqual(rows["ip_data"]["side"], SIDE_UNALLOCATED)
        self.assertIn("ip_data", {r["key"] for r in m["rows"] if r["side"] == SIDE_UNALLOCATED})

    def test_definition_clause_is_not_an_allocation(self) -> None:
        """'수급인이라 함은 …' 은 위험배분이 아니다."""
        text = '"수급인"이라 함은 도급인으로부터 건설공사를 도급받는 건설업자를 말한다.'
        m = build_risk_allocation_matrix(text, our_role_direction="provider")
        rows = {r["key"]: r for r in m["rows"]}
        self.assertNotEqual(rows["subcontractor"]["side"], SIDE_OURS)

    def test_evidence_matches_the_verdict(self) -> None:
        m = build_risk_allocation_matrix(self._WORKS, our_role_direction="provider")
        rows = {r["key"]: r for r in m["rows"]}
        self.assertIn("제3자", rows["third_party_damage"]["evidence"])

    def test_concentration_warning_only_above_threshold(self) -> None:
        m = build_risk_allocation_matrix(self._WORKS, our_role_direction="provider")
        self.assertEqual(concentrated_risk_axes(m, threshold=99), [])
        self.assertTrue(concentrated_risk_axes(m, threshold=1))


# ═══════════════════════════════════════════════════════════════════════════
# 항목 7 — HIGH 기준
# ═══════════════════════════════════════════════════════════════════════════

class HighSeverityCriteriaTest(unittest.TestCase):
    def _cr(self, title: str, reason: str = "") -> dict:
        return {"clause_id": "x", "risk_tier": "HIGH", "severity": "HIGH",
                "issue_title": title, "rewrite_reason": reason}

    def test_item7_criteria_keep_high(self) -> None:
        cases = {
            "배상액이 계약금액의 50%에 달함": "large_monetary_exposure",
            "도급인은 필요하다고 인정하는 경우 언제든지 해지할 수 있다": "unilateral_termination_right",
            "보증금이 도급인에게 귀속되고 손해배상을 별도로 청구할 수 있다": "bond_forfeiture_plus_damages",
            "산업안전 사고에 대한 일체의 책임을 수급인이 부담": "safety_liability_fully_shifted",
            "설계도서에 관한 일체의 지식재산권이 도급인에게 귀속": "core_ip_loss",
            "수급인의 부도 또는 파산 시 해지": "insolvency_exposure",
        }
        for title, expect in cases.items():
            cr = self._cr(title)
            apply_high_severity_policy([cr])
            with self.subTest(title=title[:24]):
                # 등급 유지와 "근거가 기록되었는가"가 요건이다. 한 문언이
                # 여러 치명 근거에 동시에 해당할 수 있어(예: 안전책임 전가는
                # 포괄책임이기도 하다) 특정 패턴 이름을 고정하지 않는다.
                self.assertEqual(cr["risk_tier"], "HIGH", title)
                basis = str(cr.get("high_severity_basis") or "")
                self.assertTrue(basis, f"{title}: 치명 근거가 기록되지 않았다")
                self.assertTrue(basis.startswith(("pattern:", "effect:", "declared:")), basis)

    def test_mere_wording_improvement_is_not_high(self) -> None:
        cr = self._cr("문구 명확화 필요", "표현이 모호하다")
        apply_high_severity_policy([cr])
        self.assertEqual(cr["risk_tier"], "MEDIUM")


# ═══════════════════════════════════════════════════════════════════════════
# 항목 8 — 법률상 책임 vs 계약상 비용배분
# ═══════════════════════════════════════════════════════════════════════════

class StatutoryVsContractualTest(unittest.TestCase):
    def test_classification(self) -> None:
        cases = {
            "산업안전보건법상 사업주의 의무는 수급인이 전적으로 부담한다": NATURE_STATUTORY,
            "중대재해 발생 시 형사책임은 수급인이 진다": NATURE_STATUTORY,
            "사고로 발생한 비용은 수급인이 부담하고 도급인은 구상할 수 있다": NATURE_CONTRACTUAL,
            "산업안전보건법상 의무 위반으로 발생한 비용은 수급인이 부담한다": NATURE_MIXED,
        }
        for text, expect in cases.items():
            with self.subTest(text=text[:30]):
                self.assertEqual(classify_liability_nature(text), expect)

    def test_statutory_finding_gets_the_distinction_note(self) -> None:
        cr = {
            "clause_id": "safety", "risk_tier": "HIGH",
            "issue_title": "산업안전보건법상 책임을 수급인에게 전가",
            "legal_business_reason": "안전사고 책임이 전면 전가되었다.",
        }
        rep = annotate_liability_nature([cr])
        self.assertEqual(rep["annotated_count"], 1)
        self.assertEqual(cr["liability_nature"], NATURE_STATUTORY)
        self.assertIn("이전하거나 면제할 수 없습니다", cr["legal_business_reason"])
        self.assertIn("비용을 누가 부담하고", cr["legal_business_reason"])

    def test_pure_cost_allocation_is_not_annotated(self) -> None:
        cr = {"clause_id": "c", "risk_tier": "MEDIUM",
              "issue_title": "추가 비용 부담 주체 불명확",
              "legal_business_reason": "추가공사 비용의 부담 주체가 정해지지 않았다."}
        rep = annotate_liability_nature([cr])
        self.assertEqual(rep["annotated_count"], 0)
        self.assertEqual(cr["liability_nature"], NATURE_CONTRACTUAL)

    def test_annotation_is_idempotent(self) -> None:
        cr = {"clause_id": "s", "risk_tier": "HIGH",
              "issue_title": "중대재해처벌법상 책임 전가",
              "legal_business_reason": "기존 설명."}
        annotate_liability_nature([cr])
        first = cr["legal_business_reason"]
        annotate_liability_nature([cr])
        self.assertEqual(cr["legal_business_reason"], first)


# ═══════════════════════════════════════════════════════════════════════════
# 항목 10 — 수정안 semantic 불일치 명칭
# ═══════════════════════════════════════════════════════════════════════════

class SemanticRewriteMismatchAliasTest(unittest.TestCase):
    def test_requested_name_is_exported(self) -> None:
        self.assertEqual(REVIEW_FAILED_SEMANTIC_REWRITE_MISMATCH, STATUS_SEMANTIC_MISMATCH)
        self.assertTrue(REVIEW_FAILED_SEMANTIC_REWRITE_MISMATCH.startswith("REVIEW_FAILED_"))


# ═══════════════════════════════════════════════════════════════════════════
# 항목 11 — 협상 3단계
# ═══════════════════════════════════════════════════════════════════════════

class NegotiationBucketTest(unittest.TestCase):
    def test_three_buckets_by_tier(self) -> None:
        self.assertEqual(classify_negotiation_bucket({"risk_tier": "HIGH"}), BUCKET_MUST_FIX)
        self.assertEqual(classify_negotiation_bucket({"risk_tier": "MEDIUM"}), BUCKET_NEGOTIABLE)
        self.assertEqual(classify_negotiation_bucket({"risk_tier": "LOW"}), BUCKET_ACCEPTABLE)

    def test_counts_are_reported(self) -> None:
        crs = [{"clause_id": "a", "risk_tier": "HIGH"},
               {"clause_id": "b", "risk_tier": "MEDIUM"},
               {"clause_id": "c", "risk_tier": "LOW"}]
        rep = assign_negotiation_buckets(crs)
        self.assertEqual(rep["counts"][BUCKET_MUST_FIX], 1)
        self.assertEqual(rep["counts"][BUCKET_NEGOTIABLE], 1)
        self.assertEqual(rep["counts"][BUCKET_ACCEPTABLE], 1)
        self.assertEqual(crs[0]["negotiation_bucket"], BUCKET_MUST_FIX)

    def test_overreaching_rewrite_gets_minimum_fix_guidance(self) -> None:
        cr = {"clause_id": "x", "risk_tier": "HIGH",
              "suggested_rewrite": "상대방은 모든 손해를 무제한으로 배상한다."}
        rep = assign_negotiation_buckets([cr])
        self.assertEqual(rep["overreaching_count"], 1)
        self.assertTrue(cr["overreaching_rewrite"])
        self.assertIn("최소수정안", cr["negotiation_position"])

    def test_reasonable_rewrite_is_untouched(self) -> None:
        cr = {"clause_id": "y", "risk_tier": "MEDIUM",
              "suggested_rewrite": "배상 총액은 계약금액의 10%를 한도로 한다."}
        rep = assign_negotiation_buckets([cr])
        self.assertEqual(rep["overreaching_count"], 0)
        self.assertNotIn("overreaching_rewrite", cr)


# ═══════════════════════════════════════════════════════════════════════════
# 항목 12 — 적용법률을 거래구조와 연결
# ═══════════════════════════════════════════════════════════════════════════

class StatuteLinkageTest(unittest.TestCase):
    def test_explains_why_not_just_the_name(self) -> None:
        rows = explain_statute_linkage(
            "수급인은 산업안전보건법을 준수하여야 하며 안전관리자를 선임한다.")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["statute"], "산업안전보건법")
        self.assertTrue(r["why_applicable"])
        self.assertTrue(r["facts_to_confirm"])
        self.assertTrue(r["evidence"])

    def test_unrelated_statutes_are_not_injected(self) -> None:
        """계약유형과 무관한 법률 자동삽입 금지(항목 12)."""
        rows = explain_statute_linkage(
            "제5조 지체상금. 제7조 하자보수. 본 공사는 준공검사로 완료된다.")
        names = {r["statute"] for r in rows}
        self.assertNotIn("개인정보 보호법", names)
        self.assertNotIn("중대재해처벌법", names)

    def test_multiple_statutes_when_text_references_them(self) -> None:
        rows = explain_statute_linkage(
            "산업안전보건법 및 건설산업기본법을 준수하고, 하도급법상 대금지급 기일을 지킨다.")
        names = {r["statute"] for r in rows}
        self.assertIn("산업안전보건법", names)
        self.assertIn("건설산업기본법", names)


# ═══════════════════════════════════════════════════════════════════════════
# 항목 13 — Final Lawyer Self-Check
# ═══════════════════════════════════════════════════════════════════════════

class FinalLawyerSelfCheckTest(unittest.TestCase):
    def _good_meta(self) -> dict:
        return {
            "contract_type_resolution": {
                "contract_type_code": "construction_contract",
                "uncertain": False, "reason": "도급 구조",
            },
            "contract_legal_map": {"our_role_direction": "provider"},
            "commercial_terms": [{"label": "계약금액", "status": "확정"}],
            "risk_allocation_matrix": {"rows": [
                {"key": k} for k in ("termination", "damages", "bond_forfeiture", "setoff")
            ]},
            "senior_counsel_pass": {"contamination": {"residual": []}},
            "semantic_mismatches": [],
        }

    def test_all_check_questions_are_asked(self) -> None:
        """1차 지시의 9문항 + 2차 지시(Risk Package·Document Hierarchy)의 5문항."""
        rep = final_lawyer_self_check(meta=self._good_meta(), clause_results=[])
        self.assertEqual(rep["total_count"], 14)
        keys = {c["key"] for c in rep["checks"]}
        for required in ("contract_type", "our_role", "commercial_terms",
                         "high_justified", "cross_clause", "linked_axes",
                         "no_contamination", "semantic_fit", "negotiable",
                         "canonical_identity", "document_hierarchy",
                         "risk_package", "no_missing_risk", "practical_rewrite"):
            self.assertIn(required, keys, f"{required} 점검 항목이 없다")

    def test_clean_review_passes(self) -> None:
        rep = final_lawyer_self_check(meta=self._good_meta(), clause_results=[])
        self.assertTrue(rep["complete"], rep["detail"])
        self.assertEqual(rep["review_status"], "")

    def test_baseless_high_fails_the_review(self) -> None:
        crs = [{"clause_id": "x", "risk_tier": "HIGH"}]  # high_severity_basis 없음
        rep = final_lawyer_self_check(meta=self._good_meta(), clause_results=crs)
        self.assertFalse(rep["complete"])
        self.assertIn("high_justified", rep["blocking_failed"])
        self.assertEqual(rep["review_status"], REVIEW_FAILED_LAWYER_SELF_CHECK)

    def test_handled_semantic_mismatch_does_not_fail_the_review(self) -> None:
        """게이트가 제 일을 할수록 검토가 실패하는 역설이 되면 안 된다.

        의미 불일치를 잡은 두 지점 모두 그 자리에서 suggested_rewrite 를 버리고
        감사용 흔적(semantic_mismatch)만 남긴다. 그 흔적 수를 그대로 실패로
        세면, 나쁜 수정문안을 성공적으로 폐기한 검토가 blocking 실패가 된다
        (2026-09-09 실측: 실제 공사도급계약에서 5건 전부 폐기됐는데 차단).
        """
        meta = dict(self._good_meta(), semantic_mismatches=[
            {"clause_id": "KR-30", "status": "REVIEW_FAILED_SEMANTIC_MISMATCH"},
            {"clause_id": "KR-31", "status": "REVIEW_FAILED_SEMANTIC_MISMATCH"},
        ])
        crs = [
            {"clause_id": "KR-30", "semantic_mismatch": {"stage": "x"},
             "suggested_rewrite": None},
            {"clause_id": "KR-31", "semantic_mismatch": {"stage": "x"},
             "suggested_rewrite": ""},
        ]
        rep = final_lawyer_self_check(meta=meta, clause_results=crs)
        self.assertTrue(rep["complete"], rep["detail"])
        self.assertNotIn("semantic_fit", rep["failed"])

    def test_residual_semantic_mismatch_is_reported_but_advisory(self) -> None:
        """수정문안이 남아 있어도 다운로드를 막지 않는다 — 신호를 믿을 수 없다.

        실측(2026-09-09, 실제 공사도급계약): 남은 2건은 모두 topic 분류 오탐
        이었다. 현장대리인 배치 조항이 safety 로, 하자담보 조항이
        payment_settlement 로 분류돼 guardrail 이 걸렸고, 이후 단계가 복원한
        수정문안은 조항과 정확히 맞았다. 이 기록만으로 "처리됨 / 오탐 / 진짜
        문제"를 구분할 수 없으므로, 여기서 막으면 정상 계약의 수정본 생성이
        실패한다. 실제 차단은 탐지 지점의 integrity gate 가 이미 한다.
        """
        meta = dict(self._good_meta(), semantic_mismatches=[
            {"clause_id": "KR-30", "status": "REVIEW_FAILED_SEMANTIC_MISMATCH"},
        ])
        crs = [
            {"clause_id": "KR-30", "semantic_mismatch": {"stage": "x"},
             "suggested_rewrite": "제3자에게 즉시 통지하고 계약을 해지한다."},
        ]
        rep = final_lawyer_self_check(meta=meta, clause_results=crs)
        self.assertIn("semantic_fit", rep["advisory_failed"])
        self.assertNotIn("semantic_fit", rep["blocking_failed"])
        self.assertEqual(rep["review_status"], "", "advisory 인데 검토를 실패시켰다")

    def test_unsettled_terms_are_advisory_not_a_failure(self) -> None:
        """계약이 미비하다는 발견으로 결과를 막으면, 그 사실을 알려줄 수 없다."""
        meta = self._good_meta()
        meta["commercial_terms"] = [{"label": "계약금액", "status": "공란"}]
        rep = final_lawyer_self_check(meta=meta, clause_results=[])
        self.assertIn("commercial_terms", rep["advisory_failed"])
        self.assertTrue(rep["complete"], "계약 미비를 검토 실패로 처리했다")
        self.assertEqual(rep["review_status"], "")

    def test_contamination_residual_fails(self) -> None:
        meta = self._good_meta()
        meta["senior_counsel_pass"] = {"contamination": {"residual": [{"clause_id": "a"}]}}
        rep = final_lawyer_self_check(meta=meta, clause_results=[])
        self.assertIn("no_contamination", rep["blocking_failed"])

    def test_overreaching_rewrite_is_reported_but_advisory(self) -> None:
        """이미 최소수정안 지침이 붙은 뒤라 다시 막으면 오탐이다.

        `assign_negotiation_buckets` 가 과도한 수정안에 "최소수정안을 1차안으로
        제시하라"는 지침을 그 자리에서 붙인다. 여기서 검토를 실패시키면 44건 중
        1건이 공격적이라는 이유로 문서 전체가 나가지 못한다(2026-09-09 실측:
        실제 공사도급계약에서 KR-26 하나 때문에 다운로드가 409).
        """
        crs = [{"clause_id": "x", "risk_tier": "MEDIUM", "overreaching_rewrite": True}]
        rep = final_lawyer_self_check(meta=self._good_meta(), clause_results=crs)
        self.assertIn("negotiable", rep["advisory_failed"])
        self.assertNotIn("negotiable", rep["blocking_failed"])
        self.assertEqual(rep["review_status"], "")

    def test_uncertain_contract_type_fails(self) -> None:
        meta = self._good_meta()
        meta["contract_type_resolution"] = {"contract_type_code": "", "uncertain": True,
                                            "reason": "신호 없음"}
        rep = final_lawyer_self_check(meta=meta, clause_results=[])
        self.assertIn("contract_type", rep["blocking_failed"])


# ═══════════════════════════════════════════════════════════════════════════
# 범용성
# ═══════════════════════════════════════════════════════════════════════════

class NoHardcodingTest(unittest.TestCase):
    _FORBIDDEN = ("역삼동", "에이슬립", "KOTRA", "퍼시스", "시디즈", "일룸",
                  "Teknion", "FURSYS", "WEBZEN")

    @staticmethod
    def _code_only(path: Path) -> str:
        import io as _io
        import tokenize as _tok

        src = path.read_text(encoding="utf-8")
        kept: list[str] = []
        try:
            for tok in _tok.generate_tokens(_io.StringIO(src).readline):
                if tok.type == _tok.COMMENT:
                    continue
                if tok.type == _tok.STRING and tok.string.lstrip("rbufRBUF")[:3] in ('"""', "'''"):
                    continue
                kept.append(tok.string)
        except _tok.TokenError:  # pragma: no cover
            return src
        return "\n".join(kept)

    def test_no_party_names_or_article_numbers_in_logic(self) -> None:
        import re as _re

        for name in _MODULES:
            code = self._code_only(CODE_REPO_ROOT / "runtime" / "review" / name)
            for term in self._FORBIDDEN:
                with self.subTest(module=name, term=term):
                    self.assertNotIn(term, code)
            with self.subTest(module=name, check="article"):
                self.assertEqual(_re.findall(r"제\s*\d+\s*조", code), [])


if __name__ == "__main__":
    unittest.main()
