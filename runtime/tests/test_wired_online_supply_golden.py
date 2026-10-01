"""Golden Acceptance — 와이어드컴퍼니 온라인 판매·공급 계약 (2026-10-01 지시 17항).

fixture
    wired_online_supply_draft.txt           최초 초안(“메이커”/“회사”, 제7조 최저가·정산, 제18조 관할)
    wired_online_supply_legal_revision.txt  법무팀 수정본(“공급사”/“판매사”, 제3조·제5조·제13조)

요청사항(사용자 원문 — 초안 조 번호를 인용)
    ① 최저가 보장 관련 귀책 구분(제7조)  ② 버틀랩 정산 주체 문제(제7조 8항)
    ③ 관할법원(제18조)                   ④ 배상 상한 부재

실측(수정 전 아우리봇): 광고매체 집행 계약으로 분류, 상대방 = 구매자, 배상 상한 → 개인정보 조항,
제20조 표시광고 신설 HIGH, 이행유보권 HIGH, 상계 제한 MEDIUM, 상품등록 조항에 NDA 식 로그·백업
삭제 문구, 비밀유지·양도금지에 동의권자·10영업일·무응답 간주, "(단, 서면사전 · 권리 · 10영업일
· 동의한 조건 포함)" 같은 깨진 문구.
"""
from __future__ import annotations

import logging
import re
import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses
from runtime.review.commercial_request_review import review_commercial_requests, split_requests
from runtime.review.entity_resolution import resolve_entities
from runtime.review.existing_protection import find_existing_protections
from runtime.review.online_sales_model import resolve_online_sales_model
from runtime.review.senior_counsel_audit import run_senior_counsel_audit

FIX = Path(__file__).resolve().parent / "fixtures"
FOCUS = "① 최저가 보장 관련 귀책 구분(제7조)\n② 버틀랩 정산 주체 문제(제7조 8항)\n③ 관할법원(제18조)\n④ 배상 상한 부재"


def _t(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


DRAFT = "wired_online_supply_draft.txt"
REVISION = "wired_online_supply_legal_revision.txt"


class TransactionReconstructionTest(unittest.TestCase):
    def test_both_versions_are_online_sales_supply(self) -> None:
        for name, sup, sel, retained in ((DRAFT, "메이커", "회사", False), (REVISION, "공급사", "판매사", True)):
            m = resolve_online_sales_model(contract_text=_t(name), entity="일룸")
            self.assertTrue(m.confident, name)
            self.assertEqual((m.supplier_label, m.seller_label, m.our_side), (sup, sel, "supplier"), name)
            self.assertEqual(m.payment_agent, "버틀랩", name)
            self.assertEqual(m.payment_agent_retained, retained, name)
            self.assertEqual(set(m.payment_flows), {"supplier_collects", "seller_collects"}, name)
            for el in ("상품공급", "공동구매/프로모션", "판매수수료/정산", "제3자 셀러 활용", "제조물책임", "개인정보 처리"):
                self.assertIn(el, m.elements, name)

    def test_other_contracts_are_not_online_sales(self) -> None:
        for name in ("hangul_day_100th_alloso_3party_contract.txt", "interior_works_prime_contractor.txt"):
            self.assertFalse(resolve_online_sales_model(contract_text=_t(name)).confident, name)


class ExistingProtectionTest(unittest.TestCase):
    def test_legal_team_revision_already_solves_a_to_e(self) -> None:
        keys = {s.protection.key: s.display_path for s in find_existing_protections(extract_clauses(_t(REVISION))[0])}
        self.assertEqual(keys.get("lowest_price_controllable"), "제3조 제5항")       # A
        self.assertEqual(keys.get("third_party_seller_supervision"), "제2조 제7항")  # B
        self.assertEqual(keys.get("payment_agent_liability_retained"), "제5조 제7항")  # C
        self.assertTrue(keys.get("product_liability_boundary", "").startswith("제7조"))  # D
        self.assertTrue(keys.get("personal_data_controls", "").startswith("제8조"))      # E

    def test_draft_does_not_yet_have_a_to_e(self) -> None:
        keys = {s.protection.key for s in find_existing_protections(extract_clauses(_t(DRAFT))[0])}
        self.assertFalse(keys & {"lowest_price_controllable", "third_party_seller_supervision",
                                 "payment_agent_liability_retained", "product_liability_boundary"})


class UserRequestTest(unittest.TestCase):
    def _reviews(self, name: str) -> dict:
        t = _t(name)
        cl = extract_clauses(t)[0]
        rs = review_commercial_requests(review_focus=FOCUS, clauses=cl,
                                        model=resolve_online_sales_model(contract_text=t, entity="일룸"),
                                        protections=find_existing_protections(cl))
        return {r.topic: r for r in rs}

    def test_four_requests_are_split(self) -> None:
        self.assertEqual(len(split_requests(FOCUS)), 4)

    def test_revision_answers_map_by_content_not_by_cited_number(self) -> None:
        r = self._reviews(REVISION)
        self.assertEqual(set(r), {"lowest_price", "settlement_agent", "jurisdiction", "damages_cap"})
        self.assertEqual(r["lowest_price"].clauses, ["제3조 제4항", "제3조 제5항"])
        self.assertEqual(r["lowest_price"].verdict, "적정")
        self.assertIn("제조물책임", r["lowest_price"].cited_note)        # 요청의 "제7조"는 이 문서의 제조물책임 조항
        self.assertEqual(r["settlement_agent"].clauses, ["제5조 제7항"])
        self.assertEqual(r["settlement_agent"].verdict, "사실관계 추가확인")  # 결제창 Case A/B 정리 필요
        self.assertEqual(r["jurisdiction"].clauses, ["제13조 제2항"])
        self.assertEqual(r["jurisdiction"].verdict, "적정")

    def test_damages_cap_is_answered_and_never_mapped_to_personal_data(self) -> None:
        for name in (REVISION, DRAFT):
            cap = self._reviews(name)["damages_cap"]
            self.assertEqual(cap.verdict, "사업부 결정 필요", name)
            self.assertTrue(cap.proposed, name)
            self.assertIn("제조물책임, 개인정보 침해", cap.proposed[0])   # 상한에서 빼는 책임
            t = _t(name)
            titles = {c.display_path: c.title for c in extract_clauses(t)[0]}
            self.assertFalse([p for p in cap.clauses if "개인정보" in titles.get(p, "")], (name, cap.clauses))

    def test_draft_lowest_price_and_agent_need_fixes(self) -> None:
        r = self._reviews(DRAFT)
        self.assertEqual(r["lowest_price"].verdict, "수정 필요")
        self.assertIn("직접 판매하여서는 아니 된다", r["lowest_price"].proposed[0])
        self.assertIn("책임을 부담하지 아니한다", r["lowest_price"].proposed[0])
        self.assertEqual(r["settlement_agent"].verdict, "수정 필요")
        self.assertIn("지급의무 및 이 계약상 책임은 회사가 부담한다", r["settlement_agent"].proposed[0])


class OverreachGateTest(unittest.TestCase):
    """실측 아우리봇 출력의 과잉 finding 을 그대로 넣었을 때 내보내지 않는가."""

    def _audit(self, findings: list[dict], name: str = DRAFT) -> None:
        t = _t(name)
        run_senior_counsel_audit(findings, text=t, clauses=extract_clauses(t)[0],
                                 entity_resolution=resolve_entities(t, entity="일룸"), archetype="goods_supply")

    def _f(self, cid: str, tier: str, title: str, **kw) -> dict:
        d = {"clause_id": cid, "risk_tier": tier, "severity": tier, "problem": title,
             "detected_issue_list": [{"issue_title": title}]}
        d.update(kw)
        return d

    def test_retention_right_is_not_auto_high(self) -> None:
        f = self._f("sppc_payment_retention", "HIGH", "[공급자 보호] 대금 미지급 시 공급자 이행유보권",
                    display_path="제19조 뒤에 제20조 신설",
                    suggested_rewrite="구매자가 기한 내에 대금을 지급하지 아니하는 경우 공급자는 이행을 유보할 수 있다.")
        self._audit([f])
        self.assertTrue(f.get("dedup_suppressed") or str(f.get("risk_tier")).upper() != "HIGH")

    def test_setoff_limit_without_broad_setoff_right_is_dropped(self) -> None:
        f = self._f("sppc_setoff_limit", "MEDIUM", "[공급자 보호] 상계 제한 또는 상계 요건 명확화",
                    display_path="제19조 뒤에 제20조 신설",
                    suggested_rewrite="구매자는 공급자의 사전 서면 동의 없이 상계할 수 없다. 상계는 확정 판결에 의해서만 허용된다.")
        self._audit([f])
        self.assertTrue(f.get("dedup_suppressed"))

    def test_nda_log_backup_deletion_on_product_listing_is_contamination(self) -> None:
        f = self._f("KR-8", "MEDIUM", "데이터 이전/반환/삭제 및 로그/백업 처리 점검", display_path="제8조",
                    article_number="8", clause_title="【 상품등록 및 변경 】",
                    original_text="“메이커”의 상품 등록 시 개별 상품의 판매에 필요한 충분한 자료가 구비되지 아니한 경우",
                    suggested_rewrite="계약 종료 시 상대방은 당사의 데이터(백업/로그 포함)를 반환한 후 파기/삭제하고, 삭제 완료를 확인할 수 있는 증적을 제공한다.")
        self._audit([f])
        self.assertTrue(f.get("dedup_suppressed"))
        self.assertIn(f.get("senior_audit_removed"),
                      ("REVIEW_FAILED_CROSS_CONTRACT_CONTAMINATION", "REVIEW_FAILED_REDLINE_QUALITY"))

    def test_confidentiality_procedure_overedit_is_removed(self) -> None:
        f = self._f("KR-13", "MEDIUM", "사전 서면동의 조건 명확화", display_path="제13조", article_number="13",
                    original_text="상대방의 사전 서면동의 없이 제 3자에게 공개하지 못한다.",
                    suggested_rewrite="상대방의 대표이사 또는 그로부터 위임받은 담당자의 사전 서면 동의를 득하여야 하며, "
                                      "동의 요청일로부터 10영업일 이내에 통지하여야 한다. 기한 내 미통지 시 동의한 것으로 본다.")
        self._audit([f])
        self.assertTrue(f.get("dedup_suppressed") or f.get("keep_as_is"))

    def test_broken_assignment_redline_is_removed(self) -> None:
        f = self._f("KR-14", "MEDIUM", "동의권자, 동의 절차 및 응답 기한 명확화", display_path="제14조", article_number="14",
                    original_text="상대방의 사전 서면 동의 없이는 제 3자에게 양도할 수 없다.",
                    suggested_rewrite="상대방의 사전 서면 동의 없이는 제 3자에게 양도할 수 없다. (단, 서면사전 · 권리 · 10영업일 · 동의한 조건 포함)")
        self._audit([f])
        self.assertTrue(f.get("dedup_suppressed") or f.get("keep_as_is"))

    def test_admin_liability_exemption_redline_is_rejected(self) -> None:
        f = self._f("counsel_legal_01", "HIGH", "[법률] 표시광고법 위반 시 인플루언서(셀러) 책임 귀속 불명확",
                    is_counsel_agent=True, display_path="제20조 신설", original_text="(해당 조항 없음 — 계약서에 신설 필요)",
                    suggested_rewrite="인플루언서의 위반으로 인한 행정제재, 과태료, 손해배상 등 모든 책임은 회사가 부담하며, 메이커는 이에 대해 면책된다.")
        self._audit([f])
        self.assertTrue(f.get("dedup_suppressed"))

    def test_cap_and_tax_go_to_business_check_even_next_to_protections(self) -> None:
        # 실측(실제 AI): 제7조 제3항(제조물책임 경계)·제5조 제7항(정산 대행)에 붙은 배상 상한·세금계산서
        # 논점이 그 조의 보호장치 때문에 KEEP 으로 덮였다 — 지시 7·10항은 재경·사업부 확인이다.
        cap = self._f("counsel_legal_03", "HIGH", "[법률] 배상책임 상한 부재로 인한 무제한 손해배상 위험",
                      is_counsel_agent=True, display_path="제7조 제3항", article_number="7", paragraph_number="3",
                      original_text="제품의 결함으로 인한 분쟁의 처리 및 손해배상에 드는 비용은 공급사가 부담한다.",
                      suggested_rewrite="… 손해배상책임은 [○]개월간 지급된 금액을 한도로 한다.")
        tax = self._f("counsel_KR-5-p7", "MEDIUM", "[세무] 정산 주체(버틀랩)와 세금계산서 발행 명의 불일치 가능성",
                      is_counsel_agent=True, display_path="제5조 제7항", article_number="5", paragraph_number="7",
                      original_text="판매사는 정산금의 산정 및 지급 업무를 자신의 자회사인 버틀랩 주식회사에 대행하게 할 수 있다.",
                      suggested_rewrite="세금계산서는 … 명의로 발급한다.")
        self._audit([cap, tax], name=REVISION)
        self.assertEqual((cap.get("triage"), tax.get("triage")), ("FINANCE_CHECK", "FINANCE_CHECK"))
        self.assertFalse(cap.get("keep_as_is") or tax.get("keep_as_is"))

    def test_third_party_seller_issue_is_keep_when_revision_has_supervision(self) -> None:
        f = self._f("counsel_legal_02", "HIGH", "[법률] 표시광고법 위반 시 셀러 책임 귀속 불명확", is_counsel_agent=True,
                    display_path="제20조 신설", original_text="(해당 조항 없음 — 계약서에 신설 필요)",
                    suggested_rewrite="셀러는 표시·광고의 공정화에 관한 법률에 따른 경제적 이해관계를 표시하여야 한다.")
        self._audit([f], name=REVISION)
        self.assertTrue(f.get("keep_as_is"))
        self.assertEqual(f.get("kept_by_protection"), "third_party_seller_supervision")


class PipelineGoldenTest(unittest.TestCase):
    """AI 없이 전체 파이프라인 — 지시 17항 PASS 조건."""

    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.clause_level import build_clause_level_result
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        cls.out = {}
        logging.disable(logging.CRITICAL)
        try:
            for name in (DRAFT, REVISION):
                b = build_clause_level_result(
                    service=RuleQueryService(loader), entity="일룸", contract_type="", text=_t(name),
                    filename=name, answers={}, review_focus=FOCUS, law_service=None, ai_provider=None,
                    ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
                )
                cls.out[name] = (b.meta, b.clause_results)
        finally:
            logging.disable(logging.NOTSET)

    def test_type_and_roles(self) -> None:
        for name, (meta, _) in self.out.items():
            cs = meta["canonical_state"]
            self.assertEqual(cs["contract_type"], "online_sales_supply", name)
            self.assertNotIn("광고매체", cs["contract_type_label"], name)
            self.assertEqual(cs["party_role"], "supplier", name)
            self.assertEqual(cs["counterparty_role"], "seller", name)
            gt = cs["governing_transaction"]
            self.assertEqual(gt["online_sales_model"]["payment_agent"], "버틀랩", name)
            self.assertIn("판매사", gt["counterparty_role_label"])

    def test_no_ad_media_or_buyer_checklists(self) -> None:
        for name, (meta, crs) in self.out.items():
            live = [c for c in crs if not c.get("dedup_suppressed") and not c.get("keep_as_is")
                    and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]
            ids = [c["clause_id"] for c in live]
            self.assertFalse([i for i in ids if i.startswith("ADM-")], (name, ids))
            self.assertFalse([c for c in live if re.search(r"이행유보|상계\s*제한", str(c.get("detected_issue_list")))],
                             (name, ids))
            self.assertLessEqual(sum(1 for c in live if str(c["risk_tier"]).upper() == "HIGH"), 3, name)

    def test_revision_keeps_what_the_legal_team_fixed(self) -> None:
        meta, crs = self.out[REVISION]
        keep_titles = " | ".join(r["title"] for r in meta["senior_counsel_audit"]["triage"]["KEEP"])
        for needle in ("최저가", "제3자 판매", "정산 대행", "제조물책임"):
            self.assertIn(needle, keep_titles)
        self.assertFalse(meta.get("review_status"), meta.get("review_status_detail"))

    def test_payment_flow_split_is_should_fix_in_both(self) -> None:
        for name, (meta, crs) in self.out.items():
            f = [c for c in crs if str(c.get("clause_id", "")).startswith("ac_payment_flow_split")
                 and not c.get("dedup_suppressed") and not c.get("keep_as_is")]
            self.assertEqual(len(f), 1, name)
            self.assertEqual(str(f[0]["risk_tier"]).upper(), "MEDIUM", name)
            self.assertIn("결제창", f[0]["suggested_rewrite"])

    def test_draft_body_carries_the_lowest_price_fix(self) -> None:
        # 요청 답변이 "수정 필요"면 본문(A/B)에도 같은 최소수정문구가 있어야 한다.
        meta, crs = self.out[DRAFT]
        body = [c for c in crs if not c.get("dedup_suppressed") and not c.get("keep_as_is")
                and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")
                and "최저가" in str(c.get("detected_issue_list"))]
        self.assertEqual(len(body), 1)
        self.assertIn("직접 판매하여서는 아니 된다", body[0]["suggested_rewrite"])

    def test_report_coverage_answers_all_four(self) -> None:
        for name, (meta, _) in self.out.items():
            rows = {r.get("topic"): r for r in meta["user_review_coverage"] if r.get("topic")}
            self.assertEqual(set(rows), {"lowest_price", "settlement_agent", "jurisdiction", "damages_cap"}, name)
            for r in rows.values():
                self.assertTrue(r["relevant_clause_paths"], (name, r))
                self.assertTrue(r["current_text"], (name, r))
                self.assertFalse(str(r["conclusion"]).startswith("【"), (name, r))


if __name__ == "__main__":
    unittest.main()
