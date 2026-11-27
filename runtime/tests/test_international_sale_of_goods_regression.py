"""국제 물품매매 기준 계약 회귀 — 원단 수입 매매 및 품질·대금 정산 계약서(국·영 병기, 비식별 fixture).

fixture: fixtures/intl_sale_goods_fabric_anon.txt — 실제 계약을 아우리봇 추출기로 읽은 텍스트에서 회사명·사업자번호·VAT·
주소·IBAN·BIC·PI 번호·품목코드 접두어만 가상값으로 바꿨다. 조항 문언·공란(원본 공백 폭)·국영 불일치는 그대로다.

요청(사용자 원문, 비식별): 하도급사가 이탈리아 업체로부터 원단을 구입하는 계약 — 하자 조항 중점, 대금 지급, 수출입 세금.
사전 답변: 인도 조건 FOB(상대방 합의 전 제안값), 검수는 구매자 단독, FTA 원산지 협의 미완료, 불량은 반품·환불 희망.

MUST / MUST NOT 는 docs/review_output/156·157 의 표와 같다. 기대값은 실측 실패의 반대이며 완화하지 않는다.
"""
from __future__ import annotations

import logging
import re
import unittest
from pathlib import Path

from runtime.review.cross_border.blanks import CLASS_BUSINESS, CLASS_MUST, detect_blanks
from runtime.review.cross_border.engine import run_cross_border_review
from runtime.review.cross_border.evidence import verify_quote
from runtime.review.cross_border.signals import assess_cross_border, cisg_applies

FIX = Path(__file__).resolve().parent / "fixtures"
TEXT = (FIX / "intl_sale_goods_fabric_anon.txt").read_text(encoding="utf-8")
FOCUS = (
    "시디즈의 하도급사인 가나다가 이탈리안 원단업체로부터 원단을 구입하는 물품구매계약서, 원단 불량이나 하자에 대한 조항 중점 검토. "
    "대금지급조항, 수출입관련 세금관련 조항 검토.\n\n[사용자 확인 답변]\n"
    "- 실제 선적 및 인도 조건(Incoterms 2020)은 FCA, FOB, CIF 중 무엇으로 확정되었습니까?: FOB 입니다.\n"
    "- 한국 내 지정 창고 입고일 기준으로 실제 검수 및 불량 판정은 누가, 어떤 방식으로 진행합니까?: 가나다가 물건을 받은 다음 검수를 합니다.\n"
    "- 수입 통관 시 한-EU FTA 원산지증명서 확보가 실제로 가능한지, 상대방과 사전 협의가 완료되었습니까?: 아직 완료되지 않았습니다.\n"
    "- 불량 원단의 폐기 또는 반송 시 실제 처리는 어떻게 진행할 계획입니까?: 불량일때는 반품하고 환불처리 하고 싶습니다."
)


def _engine(answers_text: str = FOCUS) -> tuple[dict, list[dict]]:
    crs: list[dict] = []
    out = run_cross_border_review(text=TEXT, clause_results=crs, base_type_code="purchase_supply", answers_text=answers_text)
    return out, crs


def _by(crs: list[dict]) -> dict[str, dict]:
    return {c["clause_id"]: c for c in crs}


# ── 1. 엔진(결정론) ─────────────────────────────────────────────────────────────

class EngineMustTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.out, cls.crs = _engine()
        cls.f = _by(cls.crs)

    def test_detected_as_international_sale_with_buyer_perspective(self) -> None:
        self.assertTrue(self.out["active"])
        self.assertEqual(self.out["international_type"], "international_sale_of_goods")
        p = self.out["perspective"]
        self.assertTrue(p["confirmed"])
        self.assertEqual((p["our_role"], p["our_label"]), ("buyer", "갑"))

    def test_shipment_deadline_blank_disables_liquidated_damages(self) -> None:
        f = self.f["xb_shipment_deadline_blank"]
        self.assertEqual((f["risk_tier"], f["action_type"], f["display_path"]), ("HIGH", "체결 전 확인", "제3조 제1항"))
        self.assertIn("제3조 제3항", f["problem"])
        self.assertIn("지체상금", f["problem"])

    def test_incoterms_unselected_with_proposed_fob(self) -> None:
        f = self.f["xb_incoterms_unselected"]
        self.assertEqual((f["risk_tier"], f["action_type"], f["display_path"]), ("HIGH", "필수수정", "제3조 제2항"))
        self.assertIn("ASSEGNATO", f["problem"])
        self.assertRegex(f["problem"], r"F조건.*맞고.*C조건.*충돌")
        rec = f["recommendation"]
        for must in ("합의 전 제안값", "지정 선적항", "적하보험", "FCA", "컨테이너"):
            self.assertIn(must, rec)
        self.assertEqual(f["redline_instruction"]["replacement_text"], "FOB [지정 선적항], Incoterms 2020")
        self.assertEqual(self.f["xb_incoterms_unselected__en"]["redline_instruction"]["replacement_text"],
                         "FOB [named port of shipment], Incoterms 2020")
        self.assertTrue(any("적하보험" in c["what"] for c in f["brief_checks"]))

    def test_incoterms_without_proposed_value_recommends_fca(self) -> None:
        _out, crs = _engine(answers_text="원단 구매계약 검토")
        f = _by(crs)["xb_incoterms_unselected"]
        self.assertEqual(f["redline_instruction"]["replacement_text"], "FCA [지정 인도 장소], Incoterms 2020")

    def test_governing_law_mismatch(self) -> None:
        f = self.f["xb_governing_law_undetermined"]
        self.assertIn(f["risk_tier"], ("MEDIUM", "HIGH"))
        self.assertEqual(f["display_path"], "제6조 제2항")
        self.assertIn("중립국", f["problem"])
        self.assertIn("영문 우선", f["problem"])
        self.assertNotIn("중립국", f["redline_instruction"]["replacement_text"])

    def test_arbitration_institution_alternative_and_no_seat(self) -> None:
        f = self.f["xb_arbitration_pathological"]
        self.assertIn(f["risk_tier"], ("HIGH", "MEDIUM"))
        self.assertIn("SIAC 또는 KCAB", f["problem"])
        self.assertIn("중재지", f["problem"])
        new = f["redline_instruction"]["replacement_text"]
        self.assertIn("중재지", new)
        self.assertNotIn("또는", new)
        self.assertIn("seat of arbitration", self.f["xb_arbitration_pathological__en"]["redline_instruction"]["replacement_text"])

    def test_advance_refund_and_post_cap_remedy(self) -> None:
        f = self.f["xb_advance_and_delay_remedies"]
        self.assertEqual(f["risk_tier"], "MEDIUM")
        self.assertIn("50%", f["problem"])
        self.assertIn("상한", f["problem"])
        self.assertIn("선급금 전액을 반환", f["redline_instruction"]["replacement_text"])

    def test_balance_due_before_claim_period(self) -> None:
        f = self.f["xb_balance_claim_timing"]
        self.assertEqual(f["risk_tier"], "MEDIUM")
        for must in ("14일", "30일", "검수 완료"):
            self.assertIn(must, f["problem"])

    def test_latent_defects_excluded(self) -> None:
        f = self.f["xb_latent_defects_excluded"]
        self.assertEqual((f["risk_tier"], f["display_path"]), ("MEDIUM", "제4조 제2항"))
        self.assertEqual(f["redline_instruction"]["target_text"], "단, 원단을 재단·가공하기 전 상태에서 발견된 하자에 한한다.")
        self.assertIn("숨은 하자", f["redline_instruction"]["replacement_text"])

    def test_origin_duty_liability(self) -> None:
        f = self.f["xb_origin_duty_liability"]
        self.assertEqual(f["risk_tier"], "MEDIUM")
        self.assertIn("추징", f["problem"])

    def test_low_items(self) -> None:
        self.assertEqual(self.f["xb_quality_subjective"]["risk_tier"], "LOW")
        self.assertIn("심한 색상 편차", self.f["xb_quality_subjective"]["problem"])
        self.assertIn("허용 오차", self.f["xb_quality_subjective"]["problem"])
        self.assertEqual(self.f["xb_conformity_evidence"]["risk_tier"], "LOW")
        self.assertIn("PFC FREE", self.f["xb_conformity_evidence"]["clause_title"])
        self.assertEqual(self.f["xb_account_change_verification"]["risk_tier"], "LOW")

    def test_every_finding_quote_is_in_the_contract(self) -> None:
        self.assertEqual(self.out["dropped_unverified"], [])
        for c in self.crs:
            for q in c.get("evidence_quotes") or []:
                self.assertTrue(verify_quote(q, TEXT), (c["clause_id"], q))
            ri = c.get("redline_instruction") or {}
            if ri.get("edit_type") == "replace":
                self.assertTrue(verify_quote(ri["target_text"], TEXT), (c["clause_id"], ri["target_text"]))

    def test_revisions_come_in_both_languages(self) -> None:
        for c in self.crs:
            if c.get("brief_merge_into") or c["action_type"] not in ("필수수정", "권장수정"):
                continue
            if c["clause_id"] == "xb_governing_law_undetermined":
                # 영문(우선 언어)은 이미 '대한민국 법 + CISG' 로 확정돼 있다 — 고칠 것은 국문 선택 문구뿐이다
                self.assertNotIn("translation_ids", c)
                self.assertIn("영문 우선", c["problem"])
                continue
            ids = c.get("translation_ids") or []
            langs = {"en" if "__en" in i else "ko" for i in ids} | {"ko"}
            self.assertIn("en", langs, c["clause_id"])

    def test_defect_grounds_are_cisg_not_civil_code_works(self) -> None:
        self.assertTrue(cisg_applies(TEXT))
        for code in ("xb_latent_defects_excluded", "xb_remedies_deduction_only", "xb_balance_claim_timing"):
            cites = [s["citation"] for s in self.f[code]["legal_grounding"]["statutes"]]
            self.assertTrue(any(c.startswith("CISG") for c in cites), (code, cites))
            self.assertFalse(any("667" in c for c in cites), (code, cites))

    def test_good_clauses_are_kept_internally(self) -> None:
        kept = {c["clause_id"] for c in self.crs if c["action_type"] == "현행 유지"}
        for code in ("xb_good_deemed_acceptance", "xb_good_quantity_tolerance", "xb_good_precedence"):
            self.assertIn(code, kept)


class BlankDetectorTest(unittest.TestCase):
    def test_blanks_and_negotiable_values(self) -> None:
        blanks, values = detect_blanks(TEXT)
        by = {(b.path, b.category): b for b in blanks}
        self.assertEqual(by[("제3조 제1항", "delivery_time")].classification, CLASS_MUST)
        self.assertEqual([d["path"] for d in by[("제3조 제1항", "delivery_time")].dependencies], ["제3조 제3항"])
        self.assertEqual(by[("제3조 제2항", "delivery_terms")].options, ["FCA Milano", "FOB", "CIF"])
        exec_items = {b.label for b in blanks if b.classification == CLASS_BUSINESS}
        self.assertTrue({"대표자", "계약 체결일"} <= exec_items, exec_items)
        # [ 3 ] [ 30 ] 은 공란이 아니라 협상 가능한 확정값
        self.assertIn(("제2조 제2항", "3"), {(v.path, v.value) for v in values})
        self.assertIn(("제4조 제2항", "30"), {(v.path, v.value) for v in values})
        self.assertFalse([b for b in blanks if b.path.startswith("제6조") and b.classification == CLASS_MUST])
        for b in blanks:
            for q in b.quotes:
                self.assertTrue(verify_quote(q, TEXT), q)

    def test_blank_terms_has_no_phantom_counterparty_info(self) -> None:
        from runtime.review.clause_extraction import extract_clauses
        from runtime.review.redline_integrity import blank_terms

        cl = [{"display_path": c.display_path, "text": c.text} for c in extract_clauses(TEXT)[0]]
        rows = {r["label"]: r for r in blank_terms(TEXT, cl)}
        self.assertNotIn("상대방 법인 정보", rows)
        self.assertEqual(rows["선적 기한"]["path"], "제3조")
        self.assertEqual(rows["인도 조건(Incoterms)"]["path"], "제3조")
        self.assertEqual(rows["대표자 성명"]["classification"], "사업부 결정")
        self.assertEqual(rows["체결일"]["classification"], "사업부 결정")


# ── 2. 전체 파이프라인 + 사업팀 전달본(AI 없이) ───────────────────────────────────

class PipelineBriefTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from runtime.review.business_brief import brief_sections
        from runtime.review.clause_extraction import extract_clauses
        from runtime.review.clause_level import build_clause_level_result
        from runtime.review.delivery_docs import brief_from_meta
        from runtime.rules.loader import RuleLoader
        from runtime.services.query_service import RuleQueryService

        loader = RuleLoader()
        loader.load()
        logging.disable(logging.CRITICAL)
        try:
            b = build_clause_level_result(
                service=RuleQueryService(loader), entity="가나다", contract_type="", text=TEXT,
                filename="intl_sale_goods_fabric_anon.txt", answers={}, review_focus=FOCUS, law_service=None,
                ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
            )
        finally:
            logging.disable(logging.NOTSET)
        cls.meta, cls.crs = b.meta, b.clause_results
        cls.brief = brief_from_meta(clause_results=b.clause_results, meta=b.meta, clauses=extract_clauses(TEXT)[0],
                                    contract_text=TEXT, answers={})
        cls.sections = brief_sections(cls.brief)
        cls.text = "\n".join(t for _h, rows in cls.sections for _s, t in rows)

    def _section(self, prefix: str) -> list[str]:
        return [t for h, rows in self.sections if h.startswith(prefix) for _s, t in rows]

    def test_canonical_type_and_cross_border(self) -> None:
        self.assertEqual(self.meta["canonical_state"]["international_type"], "international_sale_of_goods")
        self.assertTrue(self.meta["canonical_state"]["cross_border"]["is_cross_border"])
        self.assertTrue(self.meta["cross_border"]["active"])

    def test_must_cards(self) -> None:
        cards = {c.title: c for c in self.brief.cards}
        def card(word: str):
            return next(c for t, c in cards.items() if word in t)
        self.assertEqual(card("선적 기한").risk, "HIGH")
        self.assertEqual(card("Incoterms").risk, "HIGH")
        self.assertIn(card("중재기관").risk, ("HIGH", "MEDIUM"))
        self.assertIn(card("준거법").risk, ("MEDIUM", "HIGH"))
        for word in ("선급금", "검수 완료", "숨은 하자", "원산지"):
            self.assertEqual(card(word).risk, "MEDIUM", word)
        for word in ("색상 편차", "PFC FREE", "계좌 변경"):
            self.assertEqual(card(word).risk, "LOW", word)
        decisions = " ".join(d.action for d in self.brief.decisions)
        self.assertIn("대표자 성명", decisions)
        self.assertIn("체결일", decisions)

    def test_request_mapping(self) -> None:
        reqs = {r.request: r for r in self.brief.requests}
        defect = next(r for q, r in reqs.items() if "하자" in q or "불량" in q)
        self.assertIn("제4조", defect.answer)
        self.assertIn("제5조", defect.answer)
        tax = next(r for q, r in reqs.items() if "세금" in q)
        self.assertIn("제3조 제2항", tax.answer)
        self.assertIn("Incoterms", tax.answer)
        self.assertIn("원산지", tax.answer)
        # 배경 설명(“…원단을 구입하는 물품구매계약서”)은 요청 답변이 아니다
        self.assertFalse([q for q in reqs if q.endswith("물품구매계약서")])

    def test_pre_signing_checks_present(self) -> None:
        s2 = self._section("2.")   # 체결 전 필수 확정 사항
        for word in ("Incoterms", "선적 기한", "대표자 성명", "체결일"):
            self.assertTrue(any(word in x for x in s2), word)
        s4 = self._section("4.")   # 계약 전 확인사항
        self.assertNotIn("위 필수 확정 사항 외에 계약 전에 따로 확인할 사항이 없습니다.", s4)
        self.assertTrue(any("적하보험" in x for x in s4))

    def test_must_not(self) -> None:
        for bad in ("소비자 대면", "배송·하자·환불", "진위", "렌탈", "딜러", "위탁판매", "개인정보", "하도급법",
                    "상대방 법인 정보", "확인 필요(추측하지 않음)", "계약에 없는 당사자 호칭", "다른 계약 유형의 문안",
                    "민법 제667조"):
            self.assertNotIn(bad, self.text, bad)
        self.assertNotIn("진행 가능(권장", self.brief.verdict)

    def test_language_quality(self) -> None:
        from runtime.review.language_quality_gate import orphan_separator_spans

        for _h, rows in self.sections:
            for st, t in rows:
                if st == "d":
                    continue
                self.assertFalse(orphan_separator_spans(t), t)
                self.assertNotRegex(t, r"(?:^|\s)·[가-힣]{1,10}법(?:상|의)")

    def test_every_live_finding_quote_exists(self) -> None:
        for c in self.crs:
            if c.get("is_cross_border_check"):
                for q in c.get("evidence_quotes") or []:
                    self.assertTrue(verify_quote(q, TEXT), (c["clause_id"], q))

    def test_verification_passes_with_confirmed_perspective(self) -> None:
        self.assertEqual(self.brief.verification.get("needs_confirmation"), [])
        self.assertFalse(self.brief.verification.get("failed"), self.brief.verification)


# ── 3. 범용 결함 ───────────────────────────────────────────────────────────────

class GenericDefectTest(unittest.TestCase):
    def test_pos_is_not_matched_inside_english_words(self) -> None:
        from runtime.review.transaction_structure_signals import detect_sales_transaction_ambiguity

        self.assertFalse(detect_sales_transaction_ambiguity(TEXT))
        self.assertTrue(detect_sales_transaction_ambiguity("판매점 POS 단말로 고객 결제를 받고 판매대금을 정산한다."))

    def test_cross_border_needs_two_signal_groups(self) -> None:
        domestic_siac = ("제1조 (목적) 주식회사 가나다(이하 갑)와 주식회사 라마바(이하 을)는 사무용 가구 납품에 관하여 계약을 체결한다.\n"
                         "제10조 (분쟁) 분쟁은 싱가포르국제중재센터(SIAC) 규칙에 따른 중재로 해결한다.")
        self.assertFalse(assess_cross_border(domestic_siac).is_cross_border)
        self.assertFalse(assess_cross_border("주식회사 가나다 주소: 서울시 중구. 협력사 Singapore 지사와 협의한다.").is_cross_border)
        a = assess_cross_border(TEXT)
        self.assertTrue(a.is_cross_border)
        self.assertGreaterEqual(len(a.groups), 2)

    def test_domestic_only_flag_uses_single_source(self) -> None:
        from runtime.review.clause_level import _is_domestic_only

        self.assertFalse(_is_domestic_only(TEXT, {}))
        # 중재기관 이름 속 국가명 하나로 국제계약이 되지 않는다
        self.assertTrue(_is_domestic_only("국내 계약. 분쟁은 싱가포르국제중재센터(SIAC) 중재로 해결한다.", {}))

    def test_law_name_not_truncated(self) -> None:
        from runtime.review.statute_grounding import strip_law_mentions

        out = strip_law_mentions("판매자로 오인되어 전자상거래법·소비자보호법상 책임을 떠안을 위험이 있다.")
        self.assertNotRegex(out, r"(?:^|\s)·")
        self.assertIn("책임을 떠안을 위험", out)

    def test_direction_gate_blocks_restricting_our_deduction(self) -> None:
        from runtime.review import direction_gate as dg

        ours, theirs = dg.expand_labels(["갑"], TEXT), dg.expand_labels(["을"], TEXT)
        add = ("① 공제/상계는 당사자 간 사전 서면합의(사유·금액 포함)가 있는 경우에 한한다.\n"
               "③ 갑은 정산서 및 증빙을 제공하고, 을은 일정 기간 내 이의제기할 수 있다.")
        kinds = [b["kind"] for b in dg.check_added_text(add, contract_text=TEXT, ours=ours, theirs=theirs)]
        self.assertEqual(kinds, ["우리 권리 축소", "우리 의무 확대"])
        # 상대방 시각(을=우리)에서는 같은 문안이 우리 권리를 줄이지 않는다
        self.assertEqual(dg.check_added_text(add, contract_text=TEXT, ours=theirs, theirs=ours), [])

    def test_statute_questions_need_contract_structure(self) -> None:
        from runtime.review.strategic_inquiry import generate_strategic_inquiry
        from runtime.review.user_focus import parse_user_focus_issues

        qs = generate_strategic_inquiry("goods_supply", "물품공급", None, FOCUS, "buyer", contract_text=TEXT)
        self.assertFalse([q for q in qs if str(q.get("question_id", "")).startswith("OV-SUB")])
        codes = {o.code for o in parse_user_focus_issues(FOCUS, contract_text=TEXT)}
        self.assertNotIn("unfair_unit_price_reduction", codes)

    def test_group_labels_only_when_group_is_party(self) -> None:
        from runtime.review.group_entities import our_side_labels

        self.assertEqual(our_side_labels(TEXT, entity="시디즈 하도급사 가나다"), ())

    def test_perspective_question_when_request_is_silent(self) -> None:
        from runtime.review.cross_border.perspective import QUESTION_ID, perspective_question

        q = perspective_question(text=TEXT, request_text="계약서 검토 부탁드립니다.")
        self.assertIsNotNone(q)
        self.assertEqual(q.question_id, QUESTION_ID)
        self.assertEqual({o.value for o in q.options}, {"buyer", "seller"})
        self.assertIsNone(perspective_question(text=TEXT, request_text=FOCUS))


if __name__ == "__main__":
    unittest.main()
