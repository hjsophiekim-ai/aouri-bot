"""Visibility gate, report format, and clause-parser tests for dealer_rental_service_contract.

Failure conditions (any of these failing means the fix is incomplete):
  FC-1  UI와 DOCX는 동일한 final_findings 기반이어야 한다
  FC-2  dealer_rental 기본 검토에서 제조물/산업안전/중대재해 항목 노출 금지
  FC-3  DOCX에 "TOP 5 핵심 리스크" 섹션이 없어야 한다
  FC-4  DOCX 섹션은 계약구조/필수수정/권장수정/(LOW부록)/제외항목 순서만 허용
  FC-5  clause_no는 대리점계약서 본문 조항 기준이어야 한다
  FC-6  고객용 렌탈계약서 조항을 대리점계약서 본문 조항으로 오인 표시 금지
  FC-7  hidden finding은 UI 렌더링 데이터에 포함되어선 안 된다
  FC-8  dealer_rental whitelist — DLR-* 외 forbidden prefix 항목 전부 제거
"""
from __future__ import annotations

import unittest
from pathlib import Path


DEALER_FIXTURE = Path(__file__).parent / "fixtures" / "fursys_rental_dealer_contract.txt"
CONSIGNMENT_FIXTURE = Path(__file__).parent / "fixtures" / "fursys_consignment_dealer.txt"

# 기본 검토에서 절대 나오면 안 되는 문자열 (FC-9 실패 조건)
_FORBIDDEN_STRINGS = [
    "isr_", "sppc_", "pi_safety", "중대재해처벌법", "산업안전보건법",
    "안전관리자", "위험성 평가", "보호구", "시운전", "하도급 안전",
    "제조물검토", "안전권고",
]

_BLOCKED_PREFIXES = ("isr_", "sppc_", "pi_")


def _fixture_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return (
        "퍼시스와 대리점 간 렌탈 위탁판매 대리점 계약서입니다.\n"
        "공급업자와 대리점 사이의 용역수수료, 거래보증금, 케어운영 수수료 조항.\n"
        "제1조 (목적) 본 계약은 공급업자와 대리점 간의 위탁판매 대리점 계약이다.\n"
        "제6조 (대리점의 의무) 대리점은 공급업자로부터 위탁받은 범위 내에서 영업한다.\n"
        "제10조 (수수료 지급) 공급업자는 매월 말일 기준으로 수수료를 정산한다.\n"
        "제15조 (계약 해지) 일방은 30일 전 서면통보로 계약을 해지할 수 있다.\n"
        "제20조 (비밀유지) 계약 당사자는 상대방의 영업비밀을 보호한다.\n"
        "세금계산서는 퍼시스가 고객에게 직접 발행한다.\n"
    )


# ─────────────────────────────────────────────────────────────────────────────


class TestUIAndDocxUseSameFinalFindings(unittest.TestCase):
    """FC-1: UI와 DOCX는 동일한 final_findings 기반."""

    def test_ui_and_docx_use_same_final_findings(self) -> None:
        from runtime.review.review_orchestrator import build_dealer_rental_review
        text = _fixture_text(DEALER_FIXTURE)
        result = build_dealer_rental_review(text=text, entity="퍼시스")

        ff = result.get("final_findings") or {}
        cr = result.get("clause_results") or []

        # clause_results와 final_findings.high_issues/medium_issues가 동일 데이터여야 함
        ff_high = len(ff.get("high_issues") or [])
        ff_med = len(ff.get("medium_issues") or [])
        cr_high = sum(1 for x in cr if str(x.get("risk_level") or x.get("risk_tier") or "").upper() == "HIGH")
        cr_med = sum(1 for x in cr if str(x.get("risk_level") or x.get("risk_tier") or "").upper() == "MEDIUM")

        self.assertEqual(ff_high, cr_high,
            f"[FC-1] final_findings HIGH({ff_high}) ≠ clause_results HIGH({cr_high})")
        self.assertEqual(ff_med, cr_med,
            f"[FC-1] final_findings MEDIUM({ff_med}) ≠ clause_results MEDIUM({cr_med})")
        # count 필드도 일치해야 함
        self.assertEqual(ff.get("high_count", -1), ff_high,
            "[FC-1] final_findings.high_count ≠ len(high_issues)")
        self.assertEqual(ff.get("medium_count", -1), ff_med,
            "[FC-1] final_findings.medium_count ≠ len(medium_issues)")


class TestNoIrrelevantProductSafetyItems(unittest.TestCase):
    """FC-2: dealer_rental 기본 검토에서 제조물/산업안전/중대재해 항목 금지."""

    def _apply_gate(self, items: list[dict], contract_type: str) -> list[dict]:
        from runtime.review.clause_level import apply_dealer_rental_final_gate
        return apply_dealer_rental_final_gate(items, contract_type)

    def test_no_irrelevant_product_safety_items_for_dealer_rental(self) -> None:
        """isr_*/sppc_*/pi_* 항목이 dealer_rental gate 후에 남아있으면 안 된다."""
        raw = [
            {"clause_id": "isr_defect_correction", "clause_title": "[제조물검토] 결함시정", "risk_tier": "HIGH"},
            {"clause_id": "pi_safety_responsibility", "clause_title": "[안전권고] 안전책임", "risk_tier": "HIGH"},
            {"clause_id": "pi_safety_manager", "clause_title": "안전관리자 선임", "risk_tier": "MEDIUM"},
            {"clause_id": "pi_legal_compliance", "clause_title": "산업안전보건법 준수", "risk_tier": "MEDIUM"},
            {"clause_id": "pi_work_stop_right", "clause_title": "위험 시 작업중지", "risk_tier": "HIGH"},
            {"clause_id": "pi_risk_assessment", "clause_title": "위험성 평가", "risk_tier": "MEDIUM"},
            {"clause_id": "DLR-001", "clause_title": "거래구조 명확화", "risk_tier": "HIGH"},
            {"clause_id": "DLR-004", "clause_title": "수수료 지급", "risk_tier": "HIGH"},
        ]
        filtered = self._apply_gate(raw, "dealer_rental_service_contract")
        filtered_ids = [x["clause_id"] for x in filtered]

        for bad in ("isr_defect_correction", "pi_safety_responsibility", "pi_safety_manager",
                    "pi_legal_compliance", "pi_work_stop_right", "pi_risk_assessment"):
            self.assertNotIn(bad, filtered_ids,
                f"[FC-2] {bad}가 dealer_rental 출력에 남아있습니다")
        self.assertIn("DLR-001", filtered_ids, "[FC-2] DLR-001이 잘못 제거되었습니다")
        self.assertIn("DLR-004", filtered_ids, "[FC-2] DLR-004가 잘못 제거되었습니다")

    def test_no_forbidden_strings_in_gate_output(self) -> None:
        """gate 통과 후 clause_title에 forbidden_strings가 없어야 한다."""
        raw = [
            {"clause_id": "isr_001", "clause_title": "중대재해처벌법 위반 리스크", "risk_tier": "HIGH"},
            {"clause_id": "sppc_001", "clause_title": "산업안전보건법 준수 조항", "risk_tier": "HIGH"},
            {"clause_id": "pi_acc", "clause_title": "안전관리자 선임 의무", "risk_tier": "MEDIUM"},
            {"clause_id": "DLR-002", "clause_title": "세금계산서 발행 주체", "risk_tier": "HIGH"},
        ]
        from runtime.review.clause_level import apply_dealer_rental_final_gate
        filtered = apply_dealer_rental_final_gate(raw, "dealer_rental_service_contract")
        for item in filtered:
            title = item.get("clause_title", "")
            cid = item.get("clause_id", "")
            for forbidden in _FORBIDDEN_STRINGS:
                self.assertNotIn(forbidden, title,
                    f"[FC-2] forbidden string '{forbidden}' in title '{title}' (clause_id={cid})")
                self.assertNotIn(forbidden, cid,
                    f"[FC-2] forbidden string '{forbidden}' in clause_id '{cid}'")


class TestDocxHasNoTop5Section(unittest.TestCase):
    """FC-3: DOCX에 'TOP 5 핵심 리스크' 섹션이 없어야 한다."""

    def _build_docx_bytes(self) -> bytes:
        from runtime.review.legal_review_docx import build_legal_review_docx
        sample_cr = [
            {
                "clause_id": "DLR-001",
                "clause_title": "거래구조 및 대리권",
                "risk_tier": "HIGH",
                "approval_required": True,
                "original_text": "대리점이 고객과 직접 계약을 체결합니다.",
                "suggested_rewrite": "퍼시스가 고객과 직접 계약을 체결하고 대리점은 영업지원을 담당합니다.",
                "rewrite_reason": "거래구조 불명확",
                "legal_business_reason": "대리권 미명시 시 세금계산서 발행 분쟁 발생",
            },
            {
                "clause_id": "DLR-003",
                "clause_title": "고객 미수금 책임",
                "risk_tier": "MEDIUM",
                "approval_required": False,
                "original_text": "미수금 발생 시 대리점이 전액 책임진다.",
                "suggested_rewrite": "미수금 책임은 퍼시스와 대리점이 협의하여 결정한다.",
                "rewrite_reason": "미수금 전가 조항",
                "legal_business_reason": "대리점에 불리한 미수금 전가 조항",
            },
        ]
        return build_legal_review_docx(
            entity="퍼시스",
            contract_type="dealer_rental_service_contract",
            filename="test_dealer.docx",
            clause_results=sample_cr,
            contract_type_code="dealer_rental_service_contract",
        )

    def _extract_docx_text(self, docx_bytes: bytes) -> str:
        import zipfile, io
        from xml.etree import ElementTree as ET
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        texts = [e.text or "" for e in root.iter(f"{{{ns}}}t")]
        return "".join(texts)

    def test_docx_has_no_top5_section(self) -> None:
        docx_bytes = self._build_docx_bytes()
        text = self._extract_docx_text(docx_bytes)
        self.assertNotIn("TOP 5 핵심 리스크", text,
            "[FC-3] DOCX에 'TOP 5 핵심 리스크' 섹션이 남아있습니다 — 중복 섹션 제거 필요")

    def test_docx_has_only_high_and_medium_sections(self) -> None:
        docx_bytes = self._build_docx_bytes()
        text = self._extract_docx_text(docx_bytes)
        # dealer_rental: TOP 5 없으므로 번호가 2.필수수정, 3.권장수정
        self.assertIn("2. 필수수정 조항", text,
            "[FC-4] dealer_rental DOCX에 '2. 필수수정 조항' 섹션이 없습니다")
        self.assertIn("3. 권장수정 조항", text,
            "[FC-4] dealer_rental DOCX에 '3. 권장수정 조항' 섹션이 없습니다")
        # TOP 5 없음 재확인
        self.assertNotIn("2. TOP 5", text,
            "[FC-4] DOCX에 '2. TOP 5' 섹션 번호가 남아있습니다")
        self.assertNotIn("TOP 5 핵심 리스크", text,
            "[FC-4] dealer_rental DOCX에 TOP 5 섹션이 남아있습니다")


class TestClauseNumbersFromMainContract(unittest.TestCase):
    """FC-5/FC-6: clause_no는 대리점계약서 본문 기준, 고객용 렌탈계약서와 혼용 금지."""

    def test_clause_numbers_are_from_main_contract(self) -> None:
        """detect_source_section_type이 대리점계약서 본문을 main_contract로 인식한다."""
        from runtime.review.clause_parser import detect_source_section_type
        main_text = "공급업자와 대리점 사이에 체결된 위탁판매 대리점 계약. 용역수수료 및 거래보증금 조항."
        stype = detect_source_section_type(main_text)
        self.assertEqual(stype, "main_contract",
            f"[FC-5] 대리점계약서 본문을 '{stype}'으로 오인식 — 'main_contract' 예상")

    def test_customer_contract_form_not_mixed_with_dealer_contract(self) -> None:
        """고객용 렌탈계약서 텍스트를 customer_contract_form으로 분류한다."""
        from runtime.review.clause_parser import detect_source_section_type
        customer_text = "퍼시스와 고객 간 렌탈 계약서. 계약물품 및 금액, 렌탈료 산정 견적서, 설치장소."
        stype = detect_source_section_type(customer_text)
        self.assertEqual(stype, "customer_contract_form",
            f"[FC-6] 고객용 렌탈계약서를 '{stype}'으로 오인식 — 'customer_contract_form' 예상")

    def test_appendix_detected_correctly(self) -> None:
        """별첨/부속서가 appendix로 분류된다."""
        from runtime.review.clause_parser import detect_source_section_type
        appendix_text = "별첨 1. 렌탈 서비스 운영 지침서\n공급업자가 제공하는 운영 매뉴얼."
        stype = detect_source_section_type(appendix_text)
        self.assertEqual(stype, "appendix",
            f"[FC-6] 별첨 텍스트를 '{stype}'으로 오인식 — 'appendix' 예상")

    def test_parse_clauses_fills_clause_no_and_section_type(self) -> None:
        """parse_clauses(detect_section_types=True)가 clause_no와 source_section_type을 채운다."""
        from runtime.review.clause_parser import parse_clauses
        text = (
            "제1조 (목적) 본 계약은 공급업자와 대리점 간 위탁판매 대리점 계약이다.\n"
            "본문 내용: 용역수수료, 거래보증금 등을 규정한다.\n"
            "제6조 (대리점의 의무) 대리점은 공급업자로부터 위탁받은 범위 내에서 영업한다.\n"
        )
        clauses = parse_clauses(text, detect_section_types=True)
        self.assertGreater(len(clauses), 0, "[FC-5] parse_clauses 결과가 비어있습니다")
        c1 = next((c for c in clauses if c.number == "1"), None)
        self.assertIsNotNone(c1, "[FC-5] 제1조를 파싱하지 못했습니다")
        self.assertIn("제1조", c1.clause_no, f"[FC-5] clause_no='{c1.clause_no}' — '제1조' 미포함")
        self.assertEqual(c1.source_section_type, "main_contract",
            f"[FC-5] 제1조 source_section_type='{c1.source_section_type}' — 'main_contract' 예상")


class TestHiddenFindingsNotRenderedInUI(unittest.TestCase):
    """FC-7: hidden finding은 UI 렌더링 데이터에 포함되어선 안 된다."""

    def _gate(self, items: list[dict]) -> tuple[list[dict], list[str]]:
        """Python mirror of JS applyDealerRentalRenderGate."""
        HARD_BLOCKED = frozenset({
            "isr_accident_reporting", "isr_pl_defect_liability", "isr_installation_defect",
            "isr_user_safety", "isr_safety_certification", "isr_pl_insurance", "isr_defect_sla",
            "isr_defect_correction",
            "sppc_inspection_standard", "sppc_return_limit", "sppc_payment_retention",
            "sppc_custom_cancel_limit",
            "pi_safety_responsibility", "pi_safety_manager", "pi_legal_compliance",
            "pi_subcontractor_safety", "pi_work_stop_right", "pi_risk_assessment",
            "pi_accident_reporting", "pi_ppe_education", "pi_access_control",
            "pi_commissioning_accident_liability",
        })
        PREFIXES = ("isr_", "sppc_", "pi_")
        TITLE_KW = ("제조물검토", "안전권고", "산업안전보건법", "중대재해처벌법",
                    "시운전", "착공", "하도급 안전", "보호구", "위험성 평가", "안전관리자")
        filtered, hidden = [], []
        for it in items:
            cid = str(it.get("clause_id") or "")
            title = str(it.get("clause_title") or "")
            blocked = (
                cid in HARD_BLOCKED
                or any(cid.startswith(p) for p in PREFIXES)
                or any(k in title for k in TITLE_KW)
            )
            if blocked:
                hidden.append(cid or title)
            else:
                filtered.append(it)
        return filtered, hidden

    def test_hidden_findings_not_rendered_in_ui(self) -> None:
        raw = [
            {"clause_id": "isr_defect_correction", "clause_title": "[제조물검토] 결함 시정", "risk_tier": "HIGH"},
            {"clause_id": "pi_accident_reporting", "clause_title": "사고보고 의무", "risk_tier": "HIGH"},
            {"clause_id": "DLR-001", "clause_title": "거래구조", "risk_tier": "HIGH"},
        ]
        filtered, hidden = self._gate(raw)
        filtered_ids = {x["clause_id"] for x in filtered}
        self.assertNotIn("isr_defect_correction", filtered_ids,
            "[FC-7] isr_defect_correction이 UI 렌더링 데이터에 포함됩니다")
        self.assertNotIn("pi_accident_reporting", filtered_ids,
            "[FC-7] pi_accident_reporting이 UI 렌더링 데이터에 포함됩니다")
        self.assertIn("DLR-001", filtered_ids,
            "[FC-7] DLR-001이 잘못 hidden 처리되었습니다")
        self.assertIn("isr_defect_correction", hidden,
            "[FC-7] isr_defect_correction이 hidden 목록에 없습니다")

    def test_hidden_items_not_in_visible_count(self) -> None:
        raw = [
            {"clause_id": "pi_safety_manager", "clause_title": "안전관리자 선임", "risk_tier": "HIGH", "high_risk": True},
            {"clause_id": "DLR-005", "clause_title": "계약 해지", "risk_tier": "HIGH", "high_risk": True},
            {"clause_id": "DLR-006", "clause_title": "비용분담", "risk_tier": "MEDIUM", "high_risk": False},
        ]
        filtered, hidden = self._gate(raw)
        must_count = sum(1 for x in filtered if x.get("high_risk") or str(x.get("risk_tier", "")).upper() == "HIGH")
        # pi_safety_manager는 제거되므로 must_count=1 (DLR-005만)
        self.assertEqual(must_count, 1,
            f"[FC-7] 필수수정 count={must_count}이지만 1이어야 합니다 (pi_safety_manager 제거 후)")


class TestDealerRentalWhitelistOnly(unittest.TestCase):
    """FC-8: dealer_rental gate 후 isr_*/sppc_*/pi_* prefix 항목 전부 제거."""

    def test_dealer_rental_whitelist_only(self) -> None:
        """gate 후 남은 항목에 _BLOCKED_PREFIXES가 없어야 한다."""
        from runtime.review.clause_level import apply_dealer_rental_final_gate
        raw = [
            {"clause_id": "isr_new_unknown_01", "clause_title": "[제조물검토] 신규항목", "risk_tier": "HIGH"},
            {"clause_id": "sppc_new_item_99", "clause_title": "신규 검수 조항", "risk_tier": "HIGH"},
            {"clause_id": "pi_new_safety_99", "clause_title": "신규 안전 조항", "risk_tier": "MEDIUM"},
            {"clause_id": "DLR-001", "clause_title": "거래구조", "risk_tier": "HIGH"},
            {"clause_id": "DLR-009", "clause_title": "분쟁조정", "risk_tier": "MEDIUM"},
            {"clause_id": "rule_generic_001", "clause_title": "일반 검토 조항", "risk_tier": "LOW"},
        ]
        filtered = apply_dealer_rental_final_gate(raw, "dealer_rental_service_contract")
        for item in filtered:
            cid = str(item.get("clause_id") or "")
            for prefix in _BLOCKED_PREFIXES:
                self.assertFalse(cid.startswith(prefix),
                    f"[FC-8] '{cid}'이 dealer_rental gate를 통과했습니다 (prefix '{prefix}' 차단 실패)")

    def test_gate_passes_dlr_rules_unchanged(self) -> None:
        """DLR-001 ~ DLR-009는 gate 후에도 유지되어야 한다."""
        from runtime.review.clause_level import apply_dealer_rental_final_gate
        dlr_items = [
            {"clause_id": f"DLR-00{i}", "clause_title": f"DLR 룰 {i}", "risk_tier": "HIGH"}
            for i in range(1, 10)
        ]
        filtered = apply_dealer_rental_final_gate(dlr_items, "dealer_rental_service_contract")
        self.assertEqual(len(filtered), 9,
            f"[FC-8] DLR-001~009 중 일부가 잘못 제거되었습니다: {len(filtered)}/9 남음")

    def test_industry_specific_review_skipped_for_dealer_rental(self) -> None:
        """dealer_rental에서 _apply_industry_specific_review가 pi_* 항목을 주입하지 않는다."""
        from runtime.review.clause_level import _apply_industry_specific_review
        cr: list = []
        # project_installation이어도 dealer_rental이면 스킵해야 함
        _apply_industry_specific_review(
            cr, "제조물 공급 및 설치 계약", "project_installation", "제조물공급",
            "dealer_rental_service_contract",
        )
        injected_ids = [x.get("clause_id", "") for x in cr]
        for cid in injected_ids:
            self.assertFalse(cid.startswith("pi_"),
                f"[FC-8] dealer_rental에서 pi_* 항목 '{cid}'가 주입되었습니다")
        self.assertEqual(len(cr), 0,
            f"[FC-8] dealer_rental에서 industry_specific_review 항목 {len(cr)}개가 주입되었습니다")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
