"""Risk Package / Document Hierarchy / 누락 역검증 / Practical First 회귀테스트
(2026-09-09 2차 지시).

지시의 목표는 "조항별 키워드 탐지기"에서 벗어나는 것이었다. 그래서 이 테스트는
개별 패턴이 매칭되는지가 아니라, **구조적 판단이 맞는지**를 확인한다:

  · 문서 우선순위를 선언대로 복원하는가
  · 상위 문서가 하위 문서의 보호를 뒤집은 사실을 잡는가
  · 조항 하나하나는 흔한데 함께 걸리면 위험한 조합을 하나로 묶는가
  · 위험이 큰데 검토 의견이 없는 영역을 역으로 찾는가
  · 수정안이 위치·방식·문구·이유·우선순위를 갖추고, 물러설 선을 함께 주는가
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from runtime.project_paths import CODE_REPO_ROOT
from runtime.review.canonical_identity import (
    REVIEW_FAILED_CANONICAL_ROLE_CONFLICT,
    ROLE_PROVIDER,
    ROLE_RECIPIENT,
    normalize_role,
    resolve_canonical_identity,
)
from runtime.review.document_hierarchy import (
    DOC_GENERAL,
    DOC_MAIN,
    DOC_SPECIAL,
    declared_priority,
    detect_document_sections,
    find_priority_overrides,
    rank_of,
    resolve_priority,
)
from runtime.review.missing_risk_backcheck import backcheck_missing_risks
from runtime.review.practical_rewrite import (
    METHOD_ADD_PROVISO,
    METHOD_NEW_CLAUSE,
    METHOD_REPLACE,
    PRIORITY_MUST,
    build_practical_positions,
    infer_method,
)
from runtime.review.risk_allocation_matrix import (
    SIDE_OURS,
    SIDE_UNALLOCATED,
    build_risk_allocation_matrix,
)
from runtime.review.risk_package import (
    RISK_PACKAGES,
    attach_packages_to_findings,
    build_risk_packages,
)

_MODULES = (
    "canonical_identity.py",
    "document_hierarchy.py",
    "missing_risk_backcheck.py",
    "practical_rewrite.py",
    "risk_package.py",
)

#: 두 문서가 한 파일에 들어 있고 조문번호가 각각 제1조부터 다시 시작하는 구조.
#: 실무 계약의 표준 형태다(합성 텍스트 — 실제 계약서가 아니다).
_TWO_DOCS = """공사도급계약서
계약문서 상호간에 상이한 사항이 있을 경우 공사도급계약서 > 공사계약 특수조건 >
공사계약 일반조건 순위에 의해서 해석된다.

공사계약 일반조건
제 1 조 [목적]
이 조건은 도급인과 수급인의 권리와 의무를 정함을 목적으로 한다.
제 2 조 [공사기간의 연장]
1. 도급인의 책임 있는 사유 또는 천재지변으로 공사가 지연된 경우 수급인은
공사기간의 연장을 요청할 수 있고, 이에 따른 추가 비용은 도급인이 부담한다.
제 3 조 [지체상금]
1. 수급인은 준공기한 내에 공사를 완성하지 못한 때에는 매 지체일수마다
지체상금률을 계약금액에 곱하여 산출한 지체상금을 도급인에게 납부하여야 한다.
다만 지체상금은 계약금액의 10%까지로 한다.
2. 도급인의 책임 있는 사유로 준공이 지체된 경우에는 그 해당일수에 상당하는
지체상금을 부과하지 아니하고, 공기만회에 소요되는 비용은 도급인이 부담한다.

공사계약 특수조건
제 1 조 [목적]
이 특수조건은 공사계약 일반조건에 추가하여 계약의 특성상 필요하다고 인정되는
사항을 특별히 규정함을 목적으로 한다.
제 2 조 [공기 지연에 따른 조치]
1. 공기 지연에 따른 조치
① 도급인은 공사가 지연되고 있다고 판단될 경우 공기만회를 위한 조치를
수급인에게 요구할 수 있다. 이때 수급인은 지체 없이 구체적인 대책 방안을
강구하여 도급인에게 제시하여야 한다.
② 공기만회를 위한 돌관작업비 및 추가 투입에 발생하는 모든 비용은 수급인의
부담으로 한다.
제 3 조 [공정관리]
1. 수급인은 배부된 설계도서 및 시방서의 내용과 현장조건을 고려하여 전체
공사공정표를 작성하여 도급인에게 제출하여야 한다.
2. 수급인은 휴일, 장마, 혹서기, 동절기 등으로 공정에 영향을 끼칠 우발 상황을
고려하여 공정 계획을 수립하여야 한다.
"""


# ═══════════════════════════════════════════════════════════════════════════
# 1항 — Canonical Contract Type / Party Role
# ═══════════════════════════════════════════════════════════════════════════

class CanonicalIdentityTest(unittest.TestCase):
    def test_role_words_normalize_to_two_directions(self) -> None:
        for word in ("수급인", "시공사", "contractor", "supplier", "provider",
                     "rental_provider", "용역 제공"):
            with self.subTest(word=word):
                self.assertEqual(normalize_role(word), ROLE_PROVIDER)
        for word in ("도급인", "발주처", "buyer", "client", "employer", "임대인"):
            with self.subTest(word=word):
                self.assertEqual(normalize_role(word), ROLE_RECIPIENT)

    def test_unknown_role_is_not_guessed(self) -> None:
        for word in ("", "party", "unknown", "당사자"):
            with self.subTest(word=word):
                self.assertEqual(normalize_role(word), "")

    def test_rule_and_ai_role_conflict_blocks(self) -> None:
        """지위가 뒤집히면 위험배분이 좌우로 반대가 된다 — 그대로 낼 수 없다."""
        rep = resolve_canonical_identity(
            rule_type_code="construction_contract",
            rule_confidence=0.9, rule_uncertain=False,
            ai_role_text="도급인",          # AI: 우리가 발주자
            rule_role="contractor",         # rule: 우리가 시공사
        )
        self.assertEqual(rep["review_status"], REVIEW_FAILED_CANONICAL_ROLE_CONFLICT)
        self.assertEqual(rep["our_role_direction"], ROLE_PROVIDER,
                         "canonical 값은 구조를 채점한 rule classifier 쪽이어야 한다")
        self.assertTrue(rep["detail"])

    def test_agreeing_judgments_pass(self) -> None:
        rep = resolve_canonical_identity(
            rule_type_code="construction_contract",
            rule_confidence=0.9, rule_uncertain=False,
            ai_role_text="수급인(시공사)", rule_role="contractor",
        )
        self.assertEqual(rep["review_status"], "")
        self.assertEqual(rep["conflict_count"], 0)

    def test_canonical_is_single_source_of_truth(self) -> None:
        """AI 서술이 비어도 canonical 값은 확정돼야 한다."""
        rep = resolve_canonical_identity(
            rule_type_code="nda_confidentiality",
            rule_confidence=0.8, rule_uncertain=False,
            rule_role="supplier",
        )
        self.assertEqual(rep["contract_type_code"], "nda_confidentiality")
        self.assertEqual(rep["our_role_direction"], ROLE_PROVIDER)
        self.assertEqual(rep["source"], "rule_classifier")


# ═══════════════════════════════════════════════════════════════════════════
# 2·6항 — Document Hierarchy
# ═══════════════════════════════════════════════════════════════════════════

class DocumentHierarchyTest(unittest.TestCase):
    def test_sections_are_detected(self) -> None:
        secs = detect_document_sections(_TWO_DOCS)
        kinds = [s.kind for s in secs]
        self.assertIn(DOC_GENERAL, kinds)
        self.assertIn(DOC_SPECIAL, kinds)

    def test_declared_priority_is_parsed(self) -> None:
        order = declared_priority(_TWO_DOCS)
        self.assertEqual(order[:3], [DOC_MAIN, DOC_SPECIAL, DOC_GENERAL])

    def test_special_conditions_outrank_general(self) -> None:
        secs = detect_document_sections(_TWO_DOCS)
        pr = resolve_priority(_TWO_DOCS, secs)
        self.assertEqual(pr["source"], "declared")
        self.assertLess(rank_of(DOC_SPECIAL, pr["order"]),
                        rank_of(DOC_GENERAL, pr["order"]))

    def test_table_of_contents_is_not_a_document_section(self) -> None:
        """계약문서 첨부 목차를 구간으로 보면 몇 줄이 하나의 문서로 잡힌다."""
        toc = "\n".join([
            "붙임 계약문서",
            "1. 공사계약 일반조건 및 특수조건",
            "2. 입찰지침서 및 세부유의 사항",
            "3. 설계도서(입찰도면)",
        ]) + "\n" + "가" * 400
        secs = detect_document_sections(toc)
        self.assertEqual(
            [s.kind for s in secs], [],
            f"목차 줄이 문서 구간으로 잡혔다: {[s.heading for s in secs]}",
        )

    def test_upper_document_overriding_lower_protection_is_caught(self) -> None:
        """일반조건은 추가비용을 도급인 부담으로 두는데 특수조건이 뒤집는다."""
        rep = find_priority_overrides(_TWO_DOCS, our_role_direction="provider")
        self.assertTrue(rep["multi_document"])
        axes = {o["axis"] for o in rep["overrides"]}
        self.assertIn("schedule_delay", axes, rep["summary"])
        found = [o for o in rep["overrides"] if o["axis"] == "schedule_delay"][0]
        self.assertEqual(found["higher_document_kind"], DOC_SPECIAL)
        self.assertEqual(found["lower_document_kind"], DOC_GENERAL)
        self.assertIn("돌관", found["evidence_higher"])

    def test_single_document_produces_no_noise(self) -> None:
        """문서가 하나뿐인 계약에서 억지로 계층을 만들면 그게 오탐이다."""
        one = "\n".join([
            "제 1 조 [목적] 이 계약은 물품 공급을 목적으로 한다.",
            "제 2 조 [대금] 매수인은 대금을 지급한다.",
        ]) + "\n" + ("나" * 300)
        rep = find_priority_overrides(one, our_role_direction="provider")
        self.assertFalse(rep["multi_document"])
        self.assertEqual(rep["overrides"], [])


# ═══════════════════════════════════════════════════════════════════════════
# 4항 — Risk Package
# ═══════════════════════════════════════════════════════════════════════════

class RiskPackageTest(unittest.TestCase):
    _EXIT = """제 1 조 [계약해지]
1. 도급인은 필요하다고 인정할 경우 계약을 해지할 수 있다.
제 2 조 [보증금]
1. 계약이 해지된 경우 계약이행보증금은 도급인에게 귀속된다.
제 3 조 [손해배상]
1. 도급인은 제2조의 보증금 귀속에 불구하고 그 손해가 보증금을 초과하는 경우
초과분에 대하여 손해배상을 청구할 수 있다.
제 4 조 [상계]
1. 도급인은 수급인에게 지급할 공사대금에서 위 금액을 상계할 수 있다.
"""

    def test_all_five_packages_are_defined(self) -> None:
        """지시가 예시로 든 다섯 조합이 모두 있어야 한다."""
        keys = {p.key for p in RISK_PACKAGES}
        for k in ("termination_exit", "delay_penalty", "defect_liability",
                  "no_fault_loss", "scope_change"):
            self.assertIn(k, keys, f"{k} 패키지가 없다")

    def test_stacked_exit_rights_are_one_high_exposure_package(self) -> None:
        """따로 보면 각각 흔한 조항이지만, 함께 걸리면 대금 회수가 0 이 된다."""
        pkgs = build_risk_packages(self._EXIT, our_role_direction="provider")
        exit_pkg = [p for p in pkgs if p["key"] == "termination_exit"]
        self.assertTrue(exit_pkg, "해지 패키지가 만들어지지 않았다")
        pkg = exit_pkg[0]
        self.assertGreaterEqual(pkg["components_present_count"], 3)
        self.assertIn(pkg["exposure"], ("high", "critical"), pkg["max_exposure_note"])

    def test_component_direction_is_verified(self) -> None:
        """방향이 반대인 조항을 우리 부담으로 보고하면 안 된다."""
        their_burden = """제 1 조 [비용]
1. 공사 중지에 따른 추가 비용은 도급인이 부담한다.
"""
        pkgs = build_risk_packages(their_burden, our_role_direction="provider")
        scope = [p for p in pkgs if p["key"] == "scope_change"]
        if scope:
            keys = {c["key"] for c in scope[0]["components_present"]}
            self.assertNotIn("cost_on_us", keys,
                             "상대방이 부담하는 비용을 자기부담으로 보고했다")

    def test_absent_package_is_not_reported(self) -> None:
        pkgs = build_risk_packages(
            "제 1 조 [목적] 이 계약은 비밀유지를 목적으로 한다.",
            our_role_direction="provider",
        )
        self.assertEqual([p["key"] for p in pkgs], [])

    def test_findings_are_linked_not_deleted(self) -> None:
        """묶어서 보여주는 것이 목적이다 — 조항별 수정문안은 그대로 필요하다."""
        crs = [
            {"clause_id": "A", "title": "해지",
             "original_text": "도급인은 계약을 해지할 수 있다."},
            {"clause_id": "B", "title": "보증금",
             "original_text": "계약이행보증금은 도급인에게 귀속된다."},
            {"clause_id": "C", "title": "무관",
             "original_text": "당사자는 성실히 협력한다."},
        ]
        pkgs = build_risk_packages(self._EXIT, our_role_direction="provider")
        rep = attach_packages_to_findings(crs, pkgs)
        self.assertEqual(len(crs), 3, "finding 이 삭제됐다")
        self.assertTrue(rep["assignments"])
        self.assertIsNone(crs[2].get("risk_package"),
                          "무관한 finding 에 패키지가 붙었다")


# ═══════════════════════════════════════════════════════════════════════════
# 11항 — 누락 리스크 역검증
# ═══════════════════════════════════════════════════════════════════════════

class MissingRiskBackcheckTest(unittest.TestCase):
    def _matrix(self, ours: tuple[str, ...] = (), unalloc: tuple[str, ...] = ()):
        rows = []
        for key in ours:
            rows.append({"key": key, "label": key, "side": SIDE_OURS,
                         "side_label": "우리 회사 부담", "evidence": "…"})
        for key in unalloc:
            rows.append({"key": key, "label": key, "side": SIDE_UNALLOCATED,
                         "side_label": "미배분", "evidence": ""})
        return {"rows": rows}

    def test_axis_on_us_without_any_finding_is_a_gap(self) -> None:
        rep = backcheck_missing_risks(self._matrix(ours=("ip_data",)), [])
        self.assertEqual(rep["gap_count"], 1)
        self.assertEqual(rep["gaps"][0]["axis"], "ip_data")

    def test_axis_covered_by_a_finding_is_not_a_gap(self) -> None:
        crs = [{"clause_id": "X", "title": "기술자료 귀속",
                "issue": "기술자료가 포괄적으로 상대방에게 귀속된다"}]
        rep = backcheck_missing_risks(self._matrix(ours=("ip_data",)), crs)
        self.assertEqual(rep["gap_count"], 0, rep["summary"])

    def test_silence_on_a_risky_axis_is_also_a_gap(self) -> None:
        """계약이 아예 정하지 않은 위험은 지적 대상이 없어 그냥 빠진다."""
        rep = backcheck_missing_risks(self._matrix(unalloc=("extra_work",)), [])
        self.assertEqual(rep["gap_count"], 1)
        self.assertIn("다툼", rep["gaps"][0]["why"])

    def test_counterparty_axis_is_not_a_gap(self) -> None:
        rows = {"rows": [{"key": "insurance", "label": "보험",
                          "side": "counterparty", "side_label": "상대방 부담",
                          "evidence": "…"}]}
        rep = backcheck_missing_risks(rows, [])
        self.assertEqual(rep["gap_count"], 0)

    def test_no_findings_are_injected(self) -> None:
        """근거 없는 지적을 자동으로 만들어내면 안 된다."""
        crs: list[dict] = []
        backcheck_missing_risks(self._matrix(ours=("ip_data",)), crs)
        self.assertEqual(crs, [])


# ═══════════════════════════════════════════════════════════════════════════
# 10항 — Practical First
# ═══════════════════════════════════════════════════════════════════════════

class PracticalRewriteTest(unittest.TestCase):
    def test_method_is_inferred_from_the_finding_shape(self) -> None:
        self.assertEqual(
            infer_method({"original_text": "", "suggested_rewrite": "신설 문구"}),
            METHOD_NEW_CLAUSE)
        self.assertEqual(
            infer_method({"original_text": "수급인은 부담한다.",
                          "suggested_rewrite": "다만, 수급인의 귀책사유가 있는 경우로 한정한다."}),
            METHOD_ADD_PROVISO)
        self.assertEqual(
            infer_method({"original_text": "수급인은 부담한다.",
                          "suggested_rewrite": "수급인은 자신의 귀책사유가 있는 경우에 한하여 부담한다."}),
            METHOD_REPLACE)

    def test_five_fields_and_a_fallback_are_provided(self) -> None:
        crs = [{
            "clause_id": "KR-1", "article_no": "제5조",
            "risk_tier": "HIGH",
            "original_text": "수급인은 모든 손해를 배상한다.",
            "suggested_rewrite": "수급인은 자신의 귀책사유로 발생한 직접손해를 배상한다.",
            "rewrite_reason": "무제한 배상은 노출을 계산할 수 없다.",
        }]
        rep = build_practical_positions(crs)
        self.assertEqual(rep["annotated_count"], 1)
        pos = crs[0]["practical_position"]
        for field in ("location", "method", "text", "reason", "priority"):
            self.assertTrue(str(pos.get(field) or "").strip(), f"{field} 가 비었다")
        self.assertEqual(pos["priority"], PRIORITY_MUST)
        fb = crs[0]["fallback_position"]
        self.assertTrue(fb["position"])
        self.assertTrue(fb["hold"], "물러설 선에도 지켜야 할 것이 있어야 한다")

    def test_negotiation_bucket_drives_priority(self) -> None:
        crs = [{"clause_id": "A", "article_no": "제1조", "risk_tier": "HIGH",
                "negotiation_bucket": "acceptable",
                "original_text": "원문", "suggested_rewrite": "수정",
                "rewrite_reason": "이유"}]
        build_practical_positions(crs)
        self.assertEqual(crs[0]["practical_position"]["priority"], "acceptable")

    def test_findings_without_a_rewrite_are_left_alone(self) -> None:
        crs = [{"clause_id": "A", "original_text": "원문"}]
        rep = build_practical_positions(crs)
        self.assertEqual(rep["annotated_count"], 0)
        self.assertNotIn("practical_position", crs[0])


# ═══════════════════════════════════════════════════════════════════════════
# 통합 — 실제 계약 형태에서 매트릭스와 패키지가 어긋나지 않는가
# ═══════════════════════════════════════════════════════════════════════════

class ConsistencyTest(unittest.TestCase):
    def test_package_reuses_the_matrix_verdicts(self) -> None:
        """부담 주체를 두 곳에서 다르게 판정하면 리포트가 자기모순이 된다."""
        matrix = build_risk_allocation_matrix(
            _TWO_DOCS, our_role_direction="provider")
        pkgs = build_risk_packages(_TWO_DOCS, matrix, our_role_direction="provider")
        sides = {r["key"]: r["side"] for r in matrix["rows"]}
        for pkg in pkgs:
            for label in pkg["axes_on_us"]:
                keys = [k for k, _ in sides.items()
                        if any(r["key"] == k and r["label"] == label
                               for r in matrix["rows"])]
                for k in keys:
                    with self.subTest(package=pkg["key"], axis=k):
                        self.assertEqual(sides[k], SIDE_OURS)


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

    def test_stripper_has_teeth(self) -> None:
        """주석·독스트링만 지우고 코드는 남는지 — 이 테스트가 무의미해지지 않게."""
        probe = CODE_REPO_ROOT / "runtime" / "review" / "risk_package.py"
        code = self._code_only(probe)
        self.assertIn("RISK_PACKAGES", code)
        self.assertNotIn("시니어 사내변호사", code)

    def test_no_party_names_or_article_numbers_in_logic(self) -> None:
        for name in _MODULES:
            code = self._code_only(CODE_REPO_ROOT / "runtime" / "review" / name)
            for term in self._FORBIDDEN:
                with self.subTest(module=name, term=term):
                    self.assertNotIn(term, code)
            with self.subTest(module=name, check="article"):
                self.assertEqual(re.findall(r"제\s*\d+\s*조", code), [])


if __name__ == "__main__":
    unittest.main()
