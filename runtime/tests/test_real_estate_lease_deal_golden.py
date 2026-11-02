"""상가 임대차(임차인) Golden — 거래 전체 판단 · 보호수단 실효성 · 핵심 위험 추적 (2026-10-30).

실측(천안 상가 임대차, 사용자 세션 2026-10-29): 요청 6건 전부 "조항을 찾지 못했습니다", 보증금 미회수 HIGH 는
Triage 낱말 점수로 DROP, 계약 성격 "렌탈"(대리점 필드·가구렌탈 법령), 요약 근거 대리점법·산업안전보건법.

여기서 고정하는 것 — 회사명·조번호가 아니라 거래 내용으로:
  · 부동산 임대차 분류, 제품 렌탈·대리점·공사·광고 규칙 미유입
  · 근저당·예금질권·상계·연대보증·주차장 사용권을 각각 평가(있다 ≠ 작동한다)
  · 핵심 위험은 손실 경로로 세우고, 이후 단계가 숨기면 되살리며 사유를 남긴다
  · 수정안 전부 반영 시 기존 보호(상계·대위변제·보증·주차장 승인)가 사라지지 않는다
  · 변형: 이름·조번호 변경 / 담보 충분 / 담보 부족 / 역할 반전
"""
from __future__ import annotations

import importlib.util
import logging
import re
import unittest
from pathlib import Path

_FIX = Path(__file__).resolve().parent / "fixtures"
TEXT = (_FIX / "real_estate_lease_tenant_contract.txt").read_text(encoding="utf-8")
FOCUS = (_FIX / "real_estate_lease_tenant_focus.txt").read_text(encoding="utf-8")
FOCUS_WITH_ANSWERS = FOCUS + (
    "\n[사용자 확인 답변]\n"
    "- 주차장 부지에 대해서도 담보설정을 요구하실 계획이신가요?: 주차장 부지에 대해서는 담보설정을 하지 않을 예정입니다.\n"
    "- 토지소유자의 연대보증 범위에 추가로 요구하시는 조건이 있으신가요?: 임대보증금 한도입니다.\n"
    "- 임차인 투자비(인테리어 등)에 대한 안전장치로 추가로 요구하시는 담보나 보증 방식이 있으신가요?: 특별히 없습니다.\n"
)


def _variants():
    spec = importlib.util.spec_from_file_location(
        "make_lease_variants", Path(__file__).resolve().parents[2] / "scripts" / "make_lease_variants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _clauses(text: str):
    from runtime.review.clause_extraction import extract_clauses

    return extract_clauses(text)[0]


def _deal(text: str = TEXT, entity: str = "일룸", focus: str = FOCUS_WITH_ANSWERS):
    from runtime.review.deal_assessment import build_deal_assessment, build_request_answers, qa_pairs
    from runtime.review.user_request_answers import parse_numbered_requests_detailed

    da = build_deal_assessment(clauses=_clauses(text), contract_text=text, entity=entity,
                               review_focus=focus, qa=qa_pairs(focus, {}, None))
    da.request_answers = build_request_answers(da, parse_numbered_requests_detailed(focus))
    return da


def _run(text: str, entity: str = "일룸", focus: str = FOCUS_WITH_ANSWERS):
    from runtime.review.clause_level import build_clause_level_result
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService

    loader = RuleLoader()
    loader.load()
    logging.disable(logging.CRITICAL)
    try:
        return build_clause_level_result(
            service=RuleQueryService(loader), entity=entity, contract_type="임대차계약서",
            text=text, filename="lease.txt", answers={}, review_focus=focus, asked_questions=None, law_service=None,
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )
    finally:
        logging.disable(logging.NOTSET)


def _live(crs: list[dict]) -> list[dict]:
    return [c for c in crs if not c.get("dedup_suppressed") and not c.get("keep_as_is")
            and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]


# ── 단위: 거래 모델 ───────────────────────────────────────────────────────────

class DealModelUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.da = _deal()
        cls.p = {p.key: p for p in cls.da.protections}
        cls.r = {r.id: r for r in cls.da.core_risks}

    def test_nature_parties_and_money(self) -> None:
        self.assertEqual(self.da.nature, "real_estate_lease")
        self.assertEqual(self.da.our_label, "임차인")
        land = next(p for p in self.da.parties if p.label == "토지소유자")
        self.assertTrue(land.person)
        self.assertEqual(set(land.functions), {"물상보증인", "연대보증인"})
        kinds = {m.kind: m.amount for m in self.da.money_flows}
        self.assertEqual((kinds["deposit"], kinds["계약금"], kinds["잔금"], kinds["rent"]),
                         (500_000_000, 250_000_000, 250_000_000, 30_000_000))

    def test_each_protection_is_evaluated_not_just_listed(self) -> None:
        self.assertEqual(self.p["mortgage"].verdict, "partial")  # 선순위 + 사용자 수치 74% → 일부만
        self.assertIn("74%", self.p["mortgage"].assessment)
        self.assertEqual(self.p["deposit_pledge"].verdict, "effective")  # 승낙·확정일자·상계권 불행사 모두 원문
        self.assertTrue(any("재예치" in x for x in self.p["deposit_pledge"].limits))
        self.assertTrue(any("9개월" in x for x in self.p["setoff"].limits))  # 2.5억 / 월 3천만
        self.assertTrue(any("매각 후에는 상계할 임대료 자체가 없다" in x for x in self.p["setoff"].limits))
        self.assertEqual(self.p["joint_guarantee"].verdict, "weak")  # 손해배상 부분 최고액 미특정
        self.assertEqual(self.p["damages"].verdict, "weak")  # 배상 약정 ≠ 투자비 회수
        self.assertEqual(self.p["use_right_1"].verdict, "effective")  # 토지 사용 승낙은 승계 대상
        self.assertEqual(self.p["use_right_parking"].verdict, "weak")  # 주차장 승인은 승계 누락 + 지분 9.5%
        self.assertIn("parking_collateral", self.p)  # 담보가치와 사용권을 따로 본다

    def test_core_risks_by_loss_path(self) -> None:
        self.assertEqual(self.r["deal_guarantee_max_amount"].category, "필수수정")
        self.assertEqual(self.r["deal_deposit_mortgage_recovery"].tier, "HIGH")
        self.assertEqual(self.r["deal_deposit_mortgage_recovery"].category, "체결 전 확인")
        # "추가로 요구하는 담보가 있느냐" 에 "특별히 없습니다" 는 추가 요구가 없다는 답이지 투자비 무담보 위험을 받아들인다는
        # 결정이 아니다(2026-10-30 지시 4항) — 수용으로 넓혀 읽지 않고 사업부 결정사항으로 남긴다.
        self.assertEqual(self.r["deal_continuity_investment"].category, "체결 전 확인")
        self.assertTrue(any("수용 여부는 결정되지 않았다" in a for a in self.r["deal_continuity_investment"].action))
        for r in self.da.core_risks:
            self.assertTrue(r.event and r.failed_protection and r.loss, r.id)
        # 보증 최고액은 사용자 답("임대보증금 한도")으로 금액 특정 — 문장 단위 최소 보완
        old, new = self.r["deal_guarantee_max_amount"].edit
        self.assertIn("연대하여 보증한다", old)
        self.assertIn("최고액은 금오억원", new)

    def test_explicit_acceptance_only(self) -> None:
        da = _deal(focus=FOCUS_WITH_ANSWERS.replace("특별히 없습니다.", "투자비 위험은 사업부가 감수하기로 했습니다."))
        r = {x.id: x for x in da.core_risks}
        self.assertEqual(r["deal_continuity_investment"].category, "수용 가능한 위험")

    def test_unverified_facts_are_conditional(self) -> None:
        docs = " ".join(u["doc"] for u in self.da.unknowns)
        self.assertIn("등기사항전부증명서", docs)
        self.assertTrue(any("미확인" in f for f in self.da.user_facts))

    def test_request_answers_have_five_parts_and_no_substitution(self) -> None:
        a = {x.index: x for x in self.da.request_answers}
        self.assertEqual(sorted(a), [1, 2, 3, 4, 5, 6])
        for x in a.values():
            for k in ("judgment", "basis", "existing_protection", "residual_risk", "required_action"):
                self.assertTrue(str(getattr(x, k)).strip(), (x.index, k))
        self.assertRegex(a[2].existing_protection, "근저당")
        self.assertRegex(a[2].existing_protection, "질권")
        self.assertNotRegex(a[2].judgment, "인도\\s*지연|렌트\\s*프리")
        self.assertEqual(a[4].verdict, "KEEP")  # 계열사 전대 사전 동의가 이미 있다


class VariantUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.v = _variants()

    def test_sufficient_security_has_no_core_findings(self) -> None:
        focus = FOCUS.replace("감정평가 64억(선순위 근저당 44.5억+일룸 근저당 3억 포함시 43.7억 -> 74.1% 수준)",
                              "선순위 담보 없음(1순위 근저당)")
        da = _deal(self.v.sufficient(TEXT), focus=focus)
        self.assertFalse([r for r in da.core_risks if r.as_finding])

    def test_missing_security_keeps_deposit_risk(self) -> None:
        da = _deal(self.v.missing(TEXT))
        r = {x.id: x for x in da.core_risks}
        self.assertEqual(r["deal_deposit_unsecured"].tier, "HIGH")

    def test_role_reversed_is_not_our_deposit_risk(self) -> None:
        da = _deal(self.v.role_reversed(TEXT))
        self.assertEqual(da.our_label, "임대인")
        self.assertFalse(da.core_risks)
        self.assertFalse([p for p in da.protections if p.ours and p.key in ("mortgage", "deposit_pledge")])

    def test_renamed_shifted_same_judgment(self) -> None:
        da = _deal(self.v.renamed_shifted(TEXT), entity="시디즈", focus=self.v.FOCUS_V1)
        r = {x.id: x for x in da.core_risks}
        self.assertTrue(r["deal_deposit_mortgage_recovery"].path.startswith("제5조"))
        self.assertTrue(r["deal_guarantee_max_amount"].path.startswith("제15조"))


# ── 단위: 공통 장치 ───────────────────────────────────────────────────────────

class SharedMechanismUnitTest(unittest.TestCase):
    def test_numbered_requests_restart_at_header_and_keep_sub_bullets(self) -> None:
        from runtime.review.user_request_answers import parse_numbered_requests_detailed

        req = parse_numbered_requests_detailed(FOCUS)
        self.assertEqual(req[0][1], "임대차계약서 초안 검토")
        self.assertTrue(any("주차장" in d for d in req[1][2]))

    def test_trace_restores_hidden_core_risk_with_stage(self) -> None:
        from runtime.review.core_risk_trace import reconcile, traced

        f = traced([{"clause_id": "deal_x", "risk_tier": "HIGH", "issue_title": "t"}])[0]
        f["triage_reason"] = "점수 미달"
        f["dedup_suppressed"] = True
        f["risk_tier"] = "LOW"
        out = reconcile([f], [f], None)
        rec = out["risks"][0]
        self.assertTrue(rec["restored"])
        self.assertEqual(f["risk_tier"], "HIGH")
        self.assertFalse(f["dedup_suppressed"])
        self.assertTrue(any(e["change"] == "hidden" and "test_real_estate" in e["stage"] for e in rec["events"]))

    def test_whole_set_check_holds_protection_loss(self) -> None:
        from runtime.review.clause_index import build_clause_index
        from runtime.review.revision_set_check import check_revision_set

        clauses = _clauses(TEXT)
        art14 = next(c for c in clauses if str(getattr(c, "article_number", "")) == "14" and not getattr(c, "paragraph_number", ""))
        original = str(art14.text)
        cr = {"clause_id": "x", "risk_tier": "MEDIUM", "article_number": "14", "display_path": "제14조",
              "redline_instruction": {"edit_type": "replace", "edit_location": "제14조 교체", "target_text": original,
                                      "replacement_text": "임대차 목적물의 인도가 지연되는 경우 렌트프리 기간을 연장한다."}}
        rep = check_revision_set([cr], clause_index=build_clause_index(TEXT, clauses), contract_text=TEXT)
        self.assertTrue(cr["redline_instruction"]["held"])
        self.assertTrue(rep["protections_checked"]["preserved"])  # 보류 후 반영본은 보호를 그대로 가진다

    def test_clean_docx_replaces_only_the_sentence_inside_a_multi_item_paragraph(self) -> None:
        import io
        import zipfile

        from runtime.review.docx_redline import build_redline_docx

        items = ["(6) “토지소유자”는 다음 사항을 확약한다.", "2. 주차장 사용을 승인한다.",
                 "3. 토지를 양도하는 경우 사전 통지한다. 양도 시에는 양수인이 제 1호의 승낙을 승계하도록 한다.",
                 "4. 보증금 반환채무를 연대하여 보증한다."]
        run = "<w:br/>".join(f'<w:t xml:space="preserve">{t}</w:t>' for t in items)
        body = ('<w:p><w:r><w:t>제 14 조 (특약)</w:t></w:r></w:p>' f"<w:p><w:r>{run}</w:r></w:p>")
        xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
               f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", xml)
            z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        target = "양도 시에는 양수인이 제 1호의 승낙을 승계하도록 한다."
        repl = "양도 시에는 양수인이 제 1호의 승낙 및 제2호의 사용 승인을 승계하도록 한다."
        crs = [{"clause_id": "deal_use_right_succession", "article_number": "14", "risk_tier": "MEDIUM",
                "original_text": items[2], "suggested_rewrite": repl, "has_rewrite_change": True,
                "redline_instruction": {"edit_type": "replace", "target_text": target, "replacement_text": repl,
                                        "final_clause_text": items[2].replace(target, repl)}}]
        _, clean = build_redline_docx(docx_bytes=buf.getvalue(), original_clauses=[], clause_results=crs)
        text = re.sub(r"<[^>]+>", "", zipfile.ZipFile(io.BytesIO(clean)).read("word/document.xml").decode("utf-8"))
        self.assertIn("주차장 사용을 승인한다", text)
        self.assertIn("연대하여 보증한다", text)
        self.assertIn("제2호의 사용 승인을 승계", text)
        self.assertEqual(text.count("사전 통지한다"), 1)  # 단락 중복 없음

    def test_executive_summary_uses_finding_basis_not_topic_template(self) -> None:
        from runtime.review.executive_summary import generate_executive_summary

        es = generate_executive_summary([{"clause_id": "a", "risk_tier": "HIGH", "clause_topic": "termination",
                                          "rewrite_reason": "임대차 종료 시 보증금 반환 지연"}], [])
        self.assertNotIn("대리점법", es["items"][0]["legal_basis"])
        self.assertNotIn("과징금", es["items"][0]["expected_effect"])


# ── 파이프라인(AI 미사용) ─────────────────────────────────────────────────────

class PipelineGoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.res = _run(TEXT)
        cls.meta = cls.res.meta
        cls.live = {str(c["clause_id"]): c for c in _live(cls.res.clause_results)}

    def test_classification_and_no_foreign_rule_packs(self) -> None:
        self.assertEqual(self.meta["canonical_state"]["contract_type"], "real_estate_lease")
        roles = [p["role"] for p in self.meta["party_map"]["parties"]]
        self.assertNotIn("공급자", roles)
        self.assertNotIn("구매자", roles)
        decisions = {d["statute"]: d["conclusion"] for d in self.meta["statute_applicability_gate"]["decisions"]}
        for law in ("하도급법", "대리점법", "표시광고법", "산업안전보건법"):
            self.assertEqual(decisions.get(law), "비적용", law)
        blob = " ".join(str(c.get("rewrite_reason") or "") for c in self.live.values())
        self.assertNotRegex(blob, "대리점|산업안전|제조물|소비자")

    def test_core_risks_survive_to_final_output(self) -> None:
        for cid in ("deal_deposit_mortgage_recovery", "deal_guarantee_max_amount", "deal_use_right_succession",
                    "deal_pledge_redeposit_gap"):
            self.assertIn(cid, self.live)
            self.assertTrue(self.live[cid].get("loss_path", {}).get("loss"), cid)
        self.assertEqual(self.live["deal_deposit_mortgage_recovery"]["risk_tier"], "HIGH")
        trace = self.meta["core_risk_trace"]
        self.assertTrue(all(r["final_state"] in ("visible", "deal_section_only") or r["restored"] for r in trace["risks"]))

    def test_requests_answered_and_status(self) -> None:
        rows = [r for r in self.meta["user_review_coverage"] if r.get("source") == "deal_request"]
        self.assertEqual(len(rows), 6)
        self.assertTrue(self.meta["review_completion"]["complete"])
        self.assertFalse([r for r in self.meta["user_review_coverage"]
                          if r.get("source") == "explicit_user_request" and "주차장" in str(r.get("original_user_text"))])

    def test_all_revisions_together_preserve_protections(self) -> None:
        chk = self.meta["revision_set_check"]["protections_checked"]
        self.assertTrue(chk["preserved"], chk)
        for k in ("근저당", "질권", "상계", "보증", "사용 승인", "대위변제"):
            self.assertGreaterEqual(chk["after"][k], chk["before"][k], k)


if __name__ == "__main__":
    unittest.main()
