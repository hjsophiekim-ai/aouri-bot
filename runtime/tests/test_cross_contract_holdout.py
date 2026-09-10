"""계약유형 교차 hold-out 검증 (2026-09-10 아키텍처 지시).

왜 이 파일이 있는가
─────────────────
"NDA 를 고치면 콘텐츠 계약이 깨지고, 콘텐츠를 고치면 건설계약이 깨진다."
지금까지의 회귀테스트는 **한 계약유형 안에서** 한 가지 사고를 고정했다.
그래서 어떤 수정이 다른 유형을 망가뜨려도 스위트는 통과했다.

이 파일은 그 반대 방향을 검사한다 — 서로 다른 8개 계약유형을 **같은 기준**으로
한꺼번에 돌려, 유형별 패치가 다른 유형을 오염시키지 않는지 본다. 개별 사고
재현이 아니라 **아키텍처 불변식**을 고정하는 것이 목적이므로, 어느 한 계약의
정답 문구를 하드코딩하지 않는다.

검사하는 불변식 (지시의 성공 기준)
─────────────────────────────
  1. contract type 오류 0        — 유형이 기대 계열 안에 있는가
  2. party role 오류 0           — 우리 지위가 확정됐는가
  3. cross-contract contamination 0
                                 — 다른 계약유형 전용 어휘가 섞이지 않았는가
  4. user request fabrication 0  — 사용자가 하지 않은 말을 요청사항으로 적지 않았는가
  5. HIGH/MEDIUM incomplete rewrite 0
                                 — 모든 HIGH/MEDIUM 에 완성 문구가 있는가
  6. UI/DOCX mismatch 0          — 화면과 문서가 같은 결과 객체인가
  7. material risk miss 0        — 각 유형의 핵심 위험축에 검토의견이 있는가

AI 는 쓰지 않는다(`ai_provider=None`). 결정론적이어야 유형 간 비교가 의미를
갖고, conftest 가 테스트의 실제 과금 호출을 막고 있기 때문이다. AI 경로의
품질은 별도의 실사례 검증에서 본다.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.review.clause_level import build_clause_level_result
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass(frozen=True)
class HoldoutCase:
    """검토 대상 하나. 정답 문구가 아니라 **계열과 축**만 기대값으로 둔다."""

    key: str
    fixture: str
    entity: str
    #: 사용자가 UI 에 입력했다고 가정하는 계약유형 라벨(비워도 된다).
    contract_type: str = ""
    #: 허용되는 canonical contract_type 계열. 하나라도 맞으면 통과.
    expect_families: tuple[str, ...] = ()
    #: 이 계약에 **있어서는 안 되는** 다른 유형 전용 어휘.
    forbidden_terms: tuple[str, ...] = ()
    #: 이 유형에서 최소한 하나는 다뤄야 하는 위험축(clause_topic 또는 본문 키워드).
    expect_risk_terms: tuple[str, ...] = ()
    review_focus: str | None = None
    answers: dict[str, Any] | None = None


#: 다른 계약유형에서 흘러들어오면 곧바로 오염인 어휘. 유형별로 무엇이 금지인지
#: 나누어 둔다 — "지체상금" 은 건설에서는 정상이고 NDA 에서는 오염이다.
_DEALER_TERMS = ("판매장려금", "판촉비", "재판매가격", "위탁판매", "대리점 수수료")
_CONSTRUCTION_TERMS = ("지체상금", "기성고", "착공", "준공검사", "산업안전보건법", "중대재해")
_DEV_TERMS = ("소스코드", "오픈소스", "SLA", "형상관리")
_CONTENT_TERMS = ("숏폼", "채널 운영", "협찬 표시", "2차적저작물")
_PRIVACY_TERMS = ("개인정보 처리위탁", "수탁자 관리·감독", "정보주체")

CASES: tuple[HoldoutCase, ...] = (
    HoldoutCase(
        key="nda",
        fixture="nda_basic.txt",
        entity="퍼시스",
        contract_type="NDA/비밀유지",
        expect_families=("nda_confidentiality",),
        forbidden_terms=_DEALER_TERMS + _CONSTRUCTION_TERMS + _CONTENT_TERMS,
        expect_risk_terms=("비밀", "정보"),
    ),
    HoldoutCase(
        key="supply",
        fixture="supply_purchase.txt",
        entity="퍼시스",
        contract_type="물품공급/구매",
        expect_families=("supply_installation", "product_supply", "purchase_supply"),
        forbidden_terms=_DEALER_TERMS + _CONTENT_TERMS + _DEV_TERMS,
        expect_risk_terms=("대금", "지연", "납품", "하자"),
    ),
    HoldoutCase(
        key="service",
        fixture="services_consulting.txt",
        entity="퍼시스",
        contract_type="용역/자문",
        expect_families=("development_service", "advisory_service", "advisory"),
        forbidden_terms=_DEALER_TERMS + _CONSTRUCTION_TERMS,
        expect_risk_terms=("용역", "대금", "지급"),
    ),
    HoldoutCase(
        key="content",
        fixture="skai_cove_content_production.txt",
        entity="퍼시스",
        contract_type="콘텐츠 제작",
        expect_families=(
            "development_service", "advertising_content_production",
            "content_production_service",
        ),
        forbidden_terms=_DEALER_TERMS + _CONSTRUCTION_TERMS,
        expect_risk_terms=("저작권", "콘텐츠", "검수"),
    ),
    HoldoutCase(
        key="barter",
        fixture="barter_content_furniture.txt",
        entity="퍼시스",
        contract_type="콘텐츠 제작 바터거래 계약서",
        expect_families=(
            "development_service", "advertising_content_production",
            "content_production_service",
        ),
        forbidden_terms=_DEALER_TERMS + _CONSTRUCTION_TERMS + _DEV_TERMS,
        expect_risk_terms=("저작권", "초상", "교환"),
    ),
    HoldoutCase(
        key="construction",
        fixture="construction_works_contract.txt",
        entity="퍼시스",
        contract_type="공사도급",
        expect_families=("construction_contract", "construction"),
        forbidden_terms=_DEALER_TERMS + _CONTENT_TERMS + _DEV_TERMS,
        expect_risk_terms=("지체", "공사", "대금"),
    ),
    HoldoutCase(
        key="dealer",
        fixture="dealer_agency.txt",
        entity="퍼시스",
        contract_type="대리점/유통",
        expect_families=(
            "dealer_agency", "distribution_resale", "consignment_sales_agency",
            "dealer_distribution",
        ),
        forbidden_terms=_CONSTRUCTION_TERMS + _CONTENT_TERMS + _DEV_TERMS,
        expect_risk_terms=("판매", "가격", "해지"),
    ),
    HoldoutCase(
        key="license",
        fixture="_lm_license_1.txt",
        entity="퍼시스",
        contract_type="라이선스",
        expect_families=(
            "license_ip", "ip_license", "development_service", "nda_confidentiality",
        ),
        forbidden_terms=_DEALER_TERMS + _CONSTRUCTION_TERMS,
        expect_risk_terms=("license", "royalty", "라이선스", "사용료"),
    ),
)


@dataclass
class Violation:
    case: str
    check: str
    detail: str


@dataclass
class HoldoutResult:
    bundle: Any
    violations: list[Violation] = field(default_factory=list)


def _live_findings(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        cr for cr in clause_results
        if isinstance(cr, dict)
        and not bool(cr.get("dedup_suppressed"))
        and not bool(cr.get("keep_as_is"))
    ]


def _finding_text(cr: dict[str, Any]) -> str:
    parts = [
        str(cr.get(k) or "")
        for k in (
            "issue_title", "problem", "rewrite_reason", "legal_business_reason",
            "suggested_rewrite", "recommendation_text", "negotiation_strategy",
        )
    ]
    detected = cr.get("detected_issue_list")
    if isinstance(detected, list):
        parts += [str(d.get("issue_title") or "") for d in detected if isinstance(d, dict)]
    return "\n".join(parts)


class CrossContractHoldoutTest(unittest.TestCase):
    """8개 계약유형을 같은 기준으로 한꺼번에 검사한다."""

    maxDiff = None
    _cache: dict[str, HoldoutResult] = {}

    @classmethod
    def setUpClass(cls) -> None:
        loader = RuleLoader()
        loader.load()
        cls.service = RuleQueryService(loader)

    @classmethod
    def _run(cls, case: HoldoutCase) -> HoldoutResult:
        cached = cls._cache.get(case.key)
        if cached is not None:
            return cached
        text = (FIXTURES / case.fixture).read_text(encoding="utf-8")
        bundle = build_clause_level_result(
            service=cls.service,
            entity=case.entity,
            contract_type=case.contract_type,
            text=text,
            filename=case.fixture,
            answers=case.answers,
            review_focus=case.review_focus,
            law_service=None,
            ai_provider=None,
            ai_model=None,
            ai_timeout_sec=None,
            ai_max_tokens=None,
            ai_temperature=None,
        )
        result = HoldoutResult(bundle=bundle)
        cls._cache[case.key] = result
        return result

    # ── 1. contract type ────────────────────────────────────────────────
    def test_contract_type_is_resolved_into_the_expected_family(self) -> None:
        bad: list[str] = []
        for case in CASES:
            meta = self._run(case).bundle.meta
            state = meta.get("canonical_state") or {}
            code = str(state.get("contract_type") or "")
            family = str(state.get("contract_type_family") or "")
            if not code:
                bad.append(f"{case.key}: contract_type 미확정")
                continue
            if case.expect_families and not (
                code in case.expect_families or family in case.expect_families
            ):
                bad.append(f"{case.key}: {code}/{family} not in {case.expect_families}")
        self.assertEqual(bad, [], "계약유형 판정 오류")

    # ── 2. party role ───────────────────────────────────────────────────
    def test_our_role_is_resolved(self) -> None:
        bad: list[str] = []
        for case in CASES:
            state = self._run(case).bundle.meta.get("canonical_state") or {}
            if not str(state.get("party_role_direction") or "").strip():
                bad.append(f"{case.key}: our_role 미확정")
        self.assertEqual(bad, [], "당사자 지위 미확정")

    # ── 3. cross-contract contamination ─────────────────────────────────
    def test_no_other_contract_type_vocabulary_leaks_in(self) -> None:
        bad: list[str] = []
        for case in CASES:
            if not case.forbidden_terms:
                continue
            text = (FIXTURES / case.fixture).read_text(encoding="utf-8")
            for cr in _live_findings(self._run(case).bundle.clause_results):
                blob = _finding_text(cr)
                for term in case.forbidden_terms:
                    # 계약 원문이 그 단어를 쓰고 있으면 오염이 아니다.
                    if term in blob and term not in text:
                        bad.append(
                            f"{case.key}/{cr.get('clause_id')}: '{term}'"
                        )
        self.assertEqual(bad, [], "다른 계약유형 어휘 혼입")

    # ── 4. user request fabrication ─────────────────────────────────────
    def test_user_requests_are_never_fabricated(self) -> None:
        """사용자가 입력하지 않았는데 '사용자 요청사항'으로 기록하면 안 된다."""
        bad: list[str] = []
        for case in CASES:
            coverage = self._run(case).bundle.meta.get("user_review_coverage") or []
            if not isinstance(coverage, list):
                continue
            focus = str(case.review_focus or "")
            for row in coverage:
                if not isinstance(row, dict):
                    continue
                if str(row.get("source") or "") != "explicit_user_request":
                    continue
                quoted = str(row.get("original_user_text") or "").strip()
                if not focus:
                    bad.append(f"{case.key}: 입력이 없는데 explicit 요청 기록 — {quoted[:60]}")
                elif quoted and quoted not in focus:
                    bad.append(f"{case.key}: 사용자가 쓰지 않은 문장 — {quoted[:60]}")
        self.assertEqual(bad, [], "사용자 요청사항 날조")

    # ── 5. incomplete rewrite ───────────────────────────────────────────
    def test_every_high_medium_finding_has_a_complete_edit(self) -> None:
        from runtime.review.redline_instruction import is_incomplete_redline

        bad: list[str] = []
        for case in CASES:
            for cr in _live_findings(self._run(case).bundle.clause_results):
                if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
                    continue
                if str(cr.get("fact_confirmation_required") or "").strip():
                    continue  # 사실확인이 선행되어야 하는 항목은 별도 상태
                if is_incomplete_redline(cr.get("redline_instruction")):
                    bad.append(f"{case.key}/{cr.get('clause_id')}")
        self.assertEqual(bad, [], "HIGH/MEDIUM 인데 수정문안이 불완전")

    def test_no_placeholder_wording_in_output(self) -> None:
        """'[수정문안 보류]', '담당 변호사가 직접 확정' 같은 자리표시자는
        협상에 쓸 수 없다 — 사실확인이 필요하면 그 사실을 명시해야 한다."""
        banned = ("[수정문안 보류]", "담당 변호사가 직접 확정", "추후 협의", "TBD")
        bad: list[str] = []
        for case in CASES:
            for cr in _live_findings(self._run(case).bundle.clause_results):
                if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
                    continue
                blob = _finding_text(cr)
                for token in banned:
                    if token in blob:
                        bad.append(f"{case.key}/{cr.get('clause_id')}: {token}")
        self.assertEqual(bad, [], "자리표시자 문구가 최종 출력에 남았다")

    # ── 6. UI/DOCX 동일성 ────────────────────────────────────────────────
    def test_ui_and_docx_share_one_result_object(self) -> None:
        """meta.final_findings 는 UI 와 DOCX 가 공유하는 단일 원본이다.
        같은 clause_results 로 다시 계산해도 같은 집합이 나와야 한다."""
        from runtime.review.output_filter import build_final_findings

        bad: list[str] = []
        for case in CASES:
            meta = self._run(case).bundle.meta
            stored = meta.get("final_findings") or {}
            state = meta.get("canonical_state") or {}
            recomputed = build_final_findings(
                self._run(case).bundle.clause_results,
                contract_type_code=str(state.get("contract_type") or ""),
                include_low=False,
            )
            for key in ("high_count", "medium_count"):
                if int(stored.get(key) or 0) != int(recomputed.get(key) or 0):
                    bad.append(
                        f"{case.key}.{key}: stored={stored.get(key)} recomputed={recomputed.get(key)}"
                    )
        self.assertEqual(bad, [], "UI/DOCX 결과 객체 불일치")

    # ── 7. material risk miss ───────────────────────────────────────────
    def test_each_contract_type_gets_findings_on_its_core_risk_axis(self) -> None:
        bad: list[str] = []
        for case in CASES:
            if not case.expect_risk_terms:
                continue
            blob = "\n".join(
                _finding_text(cr) + " " + str(cr.get("clause_title") or "")
                for cr in _live_findings(self._run(case).bundle.clause_results)
            )
            if not any(t in blob for t in case.expect_risk_terms):
                bad.append(f"{case.key}: {case.expect_risk_terms} 중 어느 축도 다루지 않음")
        self.assertEqual(bad, [], "핵심 위험축 누락")

    # ── 8. Final Senior Counsel Gate (지시 항목 12) ──────────────────────
    def test_final_counsel_gate_runs_on_every_contract(self) -> None:
        """10개 항목 자가점검이 모든 유형에서 실행되고 결과를 남기는가."""
        bad: list[str] = []
        for case in CASES:
            gate = self._run(case).bundle.meta.get("final_counsel_gate")
            if not isinstance(gate, dict) or not gate.get("checks"):
                bad.append(f"{case.key}: 자가점검 결과 없음")
                continue
            if len(gate["checks"]) != 10:
                bad.append(f"{case.key}: 점검 항목 {len(gate['checks'])}개(10개여야 함)")
        self.assertEqual(bad, [], "Final Senior Counsel Gate 미실행")

    def test_final_counsel_gate_passes_on_every_contract(self) -> None:
        """유형별 패치가 다른 유형의 자가점검을 깨뜨리지 않는가.

        하나라도 실패하면 그 유형은 '정상 완료'가 아니다 — 어느 항목이 왜
        실패했는지까지 함께 보고해, 다음 수정의 출발점이 되게 한다.
        """
        failures: list[str] = []
        for case in CASES:
            gate = self._run(case).bundle.meta.get("final_counsel_gate") or {}
            for check in gate.get("checks") or []:
                if not isinstance(check, dict) or check.get("ok"):
                    continue
                failures.append(
                    f"{case.key}/{check.get('key')}: {str(check.get('detail') or '')[:110]}"
                )
        self.assertEqual(failures, [], "자가점검 실패 항목")

    def test_every_contract_produces_at_least_one_finding(self) -> None:
        bad = [
            case.key for case in CASES
            if not _live_findings(self._run(case).bundle.clause_results)
        ]
        self.assertEqual(bad, [], "검토의견이 0건인 계약")


if __name__ == "__main__":
    unittest.main()
