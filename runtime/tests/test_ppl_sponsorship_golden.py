"""Golden — 프로그램 협찬(PPL) 계약, 광고주 관점 (2026-10-21).

fixture
    ppl_program_sponsorship_contract.txt   실제 계약 추출본(상대방명·주소·대표자·계좌 비식별)

수정 전(실측, reports_evidence/cjenm_ppl/before)
    계약유형 "지식재산권 실시허락(라이선스) 계약", 우리 지위 "구매자/발주자"
    업로드 분류 "라이선스/로열티" → "오픈소스 사용/라이선스 위반" HIGH 가 양도금지 조에, 수정 위치는 다른 조
    "보장·최소 개런티" 와 "예정·사전 협의로 변경" 의 충돌, 라이선스와 "별도 사전 서면 합의" 의 충돌 미지적
    제6조 제1항(제작사 귀속)에 "양도 조항에 권리를 명시" — 저작권 양도 요구 프레임
    MEDIUM 수정안이 라이선스 호 전체를 한 문장으로 교체(기존 이용권 삭제), 반영본에 "[추가 권고]" 표지
    YouTube 채널에 방송법 "직접 적용·높음", 초상권 낱말로 개인정보보호법 "일부 적용·수정 필요"

회사명·조번호·보호조건·당사자 역할을 바꾼 변형으로 같은 판단이 나오는지 함께 본다.
"""
from __future__ import annotations

import io
import json
import logging
import re
import unittest
import zipfile
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses

FIX = Path(__file__).resolve().parent / "fixtures"
TEXT = (FIX / "ppl_program_sponsorship_contract.txt").read_text(encoding="utf-8")
FOCUS = "광고주(우리 회사) 입장에서 첨부 협찬 계약서 전반의 법률상 이상 여부 및 보완 필요 사항 검토 요청"


def _renamed_shifted(text: str) -> str:
    t = text.replace("시디즈", "한빛가구").replace("가나미디어", "다온미디어").replace("알로소", "루미에")
    t = re.sub(r"제\s*(\d+)\s*조", lambda m: f"제 {int(m.group(1)) + 1} 조" if " " in m.group(0) else f"제{int(m.group(1)) + 1}조", t)
    head, sep, rest = t.partition("제 2 조 (계약의 목적)")
    return head + "제 1 조 (정의)\n본 계약에서 \"게시일\"이란 대상 프로그램이 최초로 공개된 날을 말한다.\n" + sep + rest


def _sufficient(text: str) -> str:
    t = text.replace("손해배상을 청구할 수 있다. ‘", "손해배상을 청구할 수 있다. 다만, 제1항 제1호 및 제4호의 보장·최소 수량은 예정 사항에 해당하지 아니하며 ‘을’은 ‘갑’의 사전 서면 동의 없이 이를 변경하거나 축소할 수 없다.")
    t = t.replace("본편 및 브랜디드 쇼츠는 게시일 기준 최소 3개월간 공개 상태를 유지한다",
                  "본편 및 브랜디드 쇼츠는 게시일 기준 최소 3개월간 공개 상태를 유지한다\n⑩ 제1항 제1호의 조회수는 유튜브 스튜디오 공식 "
                  "통계로 게시일부터 3개월간 집계하며, 보장 조회수에 미달하면 30일 이내에 추가 노출로 보완하고 보완되지 아니한 부분은 "
                  "오프닝 PPL 배분액 3천만원에 미달 비율을 곱한 금액을 반환한다.\n⑪ ‘을’은 협찬 콘텐츠에 ‘갑’과의 경제적 이해관계(유료광고 포함 "
                  "사실)를 표시한다.")
    t = t.replace("2026년 10월 29일자로", "대상 프로그램의 실제 게시일 이후에")
    t = t.replace("사전 협의된 기간 내에서 프로그램의 방송 일정을 조정 또는 연장할 수 있다.",
                  "사전 협의된 기간 내에서 프로그램의 방송 일정을 조정 또는 연장할 수 있다. 다만, 늦어도 2026년 12월 31일까지 게시하지 "
                  "아니한 사항은 제9조 제3항에 따라 정산·반환한다.")
    return t.replace("‘을’과 사전 서면 합의를 거쳐야 한다.",
                     "‘을’과 사전 서면 합의를 거쳐야 한다. 다만, 제3조 제1항 제3호의 마케팅 라이선스 범위 안의 활용에는 사전 서면 합의를 요하지 아니한다.")


def _missing_refunds(text: str) -> str:
    t = re.sub(r"(?m)^③ 본 계약이 ‘을’의 귀책사유로 해제 또는 해지 된 경우[^\n]*\n?", "", text)
    return re.sub(r"(?m)^① ‘을’이 본 계약의 협찬의 대가를 계약내용대로 이행하지 않았을 경우[^\n]*\n?", "", t)


def _reversed(text: str) -> str:
    return text.replace("시디즈", "@@").replace("가나미디어", "시디즈").replace("@@", "한빛전자")


def _run(text: str, entity: str = "시디즈"):
    from runtime.review.classify import _classify_contract_type
    from runtime.review.clause_level import build_clause_level_result
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService

    loader = RuleLoader()
    loader.load()
    logging.disable(logging.CRITICAL)
    try:
        return build_clause_level_result(
            service=RuleQueryService(loader), entity=entity, contract_type=_classify_contract_type(text, None),
            text=text, filename="ppl.txt", answers={}, review_focus=FOCUS, asked_questions=None, law_service=None,
            ai_provider=None, ai_model=None, ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )
    finally:
        logging.disable(logging.NOTSET)


def _live(crs: list[dict]) -> list[dict]:
    return [c for c in crs if not c.get("dedup_suppressed") and not c.get("keep_as_is")
            and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]


def _ids(crs: list[dict]) -> set[str]:
    return {str(c["clause_id"]).split("__")[0] for c in _live(crs)}


# ── 단위 ─────────────────────────────────────────────────────────────────────

class SponsorshipModelUnitTest(unittest.TestCase):
    def _m(self, text: str, entity: str):
        from runtime.review.sponsorship_model import resolve_sponsorship_model
        return resolve_sponsorship_model(contract_text=text, entity=entity)

    def test_roles_from_payment_sentence(self) -> None:
        m = self._m(TEXT, "시디즈")
        self.assertEqual((m.confident, m.sponsor_label, m.recipient_label, m.our_side), (True, "갑", "을", "sponsor"))
        self.assertTrue(m.online_channel)
        self.assertEqual(self._m(_reversed(TEXT), "시디즈").our_side, "recipient")
        self.assertEqual(self._m(_renamed_shifted(TEXT), "한빛가구").our_side, "sponsor")

    def test_other_sponsorship_forms(self) -> None:
        role_noun = ("스폰서십 계약\n주식회사 가나게임즈(이하 “주최자”)와 주식회사 시디즈(이하 “스폰서”)는 스폰서가 주최자가 주최하는 "
                     "행사를 후원하는 데 합의한다. 주최자는 다음 스폰서십 혜택을 스폰서에게 제공한다: 로고 노출, 부스. "
                     "스폰서는 스폰서십 비용 1천만원을 지급한다. 스폰서는 행사 후원사로서 제품을 협찬한다.")
        m = self._m(role_noun, "시디즈")
        self.assertEqual((m.confident, m.sponsor_label, m.our_side), (True, "스폰서", "sponsor"))
        adnominal = ("협찬 계약서\n주식회사 시디즈(이하 ‘시디즈’라 한다)와 주식회사 다라(이하 ‘다라’라 한다)는 협찬 계약을 체결한다. "
                     "시디즈가 다라가 주관하는 행사에 관련 물품을 제공하고, 다라는 홍보 업무를 진행한다. 다라는 행사에서 시디즈 로고를 노출한다. "
                     "협찬 물품은 제1조에 따른다.")
        m = self._m(adnominal, "시디즈")
        self.assertEqual((m.confident, m.sponsor_label), (True, "시디즈"))  # "다라가 주관하는" 은 관형절 주어

    def test_model_or_influencer_fee_contract_is_not_sponsorship(self) -> None:
        t = ("제품 협찬 계약서\n주식회사 일룸(이하 “갑”)과 모델 보호자(이하 “을”)는 촬영에 합의한다. 갑은 을에게 모델료 대신 제품을 "
             "무상 제공하고 을은 촬영 콘텐츠를 게시한다. 협찬 제품은 매트리스 1개다.")
        self.assertFalse(self._m(t, "일룸").confident)

    def test_upload_classification_follows_title(self) -> None:
        from runtime.review.classify import _classify_contract_type
        self.assertEqual(_classify_contract_type(TEXT, None), "광고/마케팅/협찬")


class StatuteCalibrationUnitTest(unittest.TestCase):
    def test_broadcasting_act_on_online_channel_is_unconfirmed(self) -> None:
        from runtime.review.statute_applicability_calibration import calibrate_broadcasting_act_applicability as cal
        r = {"statute": "방송법 및 동법 시행령", "applicability": "높음", "risk_level": "HIGH", "reasoning": "직접 적용됩니다."}
        out = cal(r, "방송채널 : YouTube 채널. 방송법 및 협찬고지에 관한 규칙을 위반하지 않는다.")
        self.assertEqual(out["applicability"], "확인 필요")
        self.assertNotIn("직접 적용됩니다", out["reasoning"])
        self.assertEqual(cal(r, "지상파 방송사업자가 편성하는 방송. YouTube 동시 게시.")["applicability"], "높음")

    def test_portrait_right_is_not_personal_data_processing(self) -> None:
        from runtime.review.statute_applicability_gate import CONCLUSION_NEEDS_FACTS, assess_privacy_act
        d = assess_privacy_act(text="출연자 초상권의 사용은 갑의 책임과 비용으로 처리한다.")
        self.assertEqual(d.conclusion, CONCLUSION_NEEDS_FACTS)


class RevisionSafetyUnitTest(unittest.TestCase):
    def test_overlapping_and_destructive_replacements_are_held(self) -> None:
        from runtime.review.clause_index import build_clause_index
        from runtime.review.revision_set_check import check_revision_set
        idx = build_clause_index(TEXT, extract_clauses(TEXT)[0])
        lic = next(c for c in extract_clauses(TEXT)[0] if c.display_path == "제3조 제1항 3호")
        line = "활용 범위: 광고/홍보의 목적으로 활용가능한 광고주 보유+외부 플랫폼"

        def cr(cid, tier, target, repl):
            return {"clause_id": cid, "article_number": "3", "risk_tier": tier, "display_path": "제3조 제1항 3호",
                    "redline_instruction": {"edit_location": "제3조 제1항 3호 교체", "edit_type": "replace",
                                            "target_text": target, "replacement_text": repl, "final_clause_text": repl}}
        crs = [cr("a", "HIGH", lic.text, lic.text + " 라이선스 기간은 최초 게시일부터 기산한다."),
               cr("b", "MEDIUM", line, "‘외부 플랫폼’에는 국내외 플랫폼이 모두 포함된다.")]
        rep = check_revision_set(crs, clause_index=idx, contract_text=TEXT)
        self.assertEqual({h["clause_id"] for h in rep["held"]}, {"b"})

    def test_redline_follows_instruction_order_and_strips_display_markers(self) -> None:
        from runtime.review.docx_redline import build_redline_docx
        body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:p>' for t in (
            "제 3 조 (협찬의 대가)", "① 을은 다음을 제공한다.", "② 예정에 해당한다.", "제 4 조 (지급)", "① 갑은 지급한다."))
        xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
               f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", xml)
            z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')

        def ins(cid, n, text):
            return {"clause_id": cid, "article_number": "3", "risk_tier": "MEDIUM", "original_text": "① 을은 다음을 제공한다.",
                    "suggested_rewrite": text, "has_rewrite_change": True,
                    "redline_instruction": {"edit_type": "insert_after", "edit_location": f"제3조 제{n - 1}항 뒤에 제{n}항 신설",
                                            "final_clause_text": text, "replacement_text": text}}
        crs = [ins("later", 4, "④ 나중 항."), ins("first", 3, "③ 먼저 항. 미달분은 제4조 제1항에 따라 정산한다."),
               {"clause_id": "held", "article_number": "3", "risk_tier": "MEDIUM", "original_text": "② 예정에 해당한다.",
                "suggested_rewrite": "② 바뀐 문장.", "has_rewrite_change": True,
                "redline_instruction": {"edit_type": "replace", "held": True, "final_clause_text": "② 바뀐 문장."}},
               {"clause_id": "marker", "article_number": "4", "risk_tier": "MEDIUM", "original_text": "① 갑은 지급한다.",
                "suggested_rewrite": "① 갑은 지급한다.\n\n[추가 권고]\n다만, 게시 후 지급한다.", "has_rewrite_change": True}]
        _, clean = build_redline_docx(docx_bytes=buf.getvalue(), original_clauses=[], clause_results=crs)
        text = re.sub(r"<[^>]+>", "\n", zipfile.ZipFile(io.BytesIO(clean)).read("word/document.xml").decode("utf-8"))
        text = "\n".join(x for x in text.splitlines() if x.strip())
        self.assertLess(text.index("③ 먼저 항."), text.index("④ 나중 항."))
        self.assertLess(text.index("④ 나중 항."), text.index("제 4 조"))  # 본문 속 "제4조" 인용을 조 제목으로 보지 않는다
        self.assertIn("② 예정에 해당한다.", text)       # 자동 적용 보류는 반영하지 않는다
        self.assertNotIn("추가 권고", text)


# ── 파이프라인(AI 미사용): 원문·변형 4종 ─────────────────────────────────────────

class PipelineGoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runs = {
            "original": _run(TEXT),
            "renamed_shifted": _run(_renamed_shifted(TEXT), "한빛가구"),
            "sufficient": _run(_sufficient(TEXT)),
            "missing": _run(_missing_refunds(TEXT)),
            "reversed": _run(_reversed(TEXT)),
        }

    def test_transaction_structure(self) -> None:
        for name in ("original", "renamed_shifted", "sufficient", "missing"):
            cs = self.runs[name].meta["canonical_state"]
            self.assertEqual(cs["contract_type"], "advertising_sponsorship", name)
            self.assertIn("광고주", cs["party_label"], name)
        self.assertIn("협찬 수령", self.runs["reversed"].meta["canonical_state"]["party_label"])

    def test_core_findings_and_anchors(self) -> None:
        o = {str(c["clause_id"]).split("__")[0]: c for c in _live(self.runs["original"].clause_results)}
        self.assertEqual(o["sp_guarantee_vs_tentative"]["risk_tier"], "HIGH")
        self.assertEqual(o["sp_license_vs_approval"]["risk_tier"], "HIGH")
        for k in ("sp_performance_guarantee", "sp_schedule_deadline", "sp_payment_timing", "sp_disclosure"):
            self.assertIn(k, o)
        self.assertEqual(o["sp_performance_guarantee"]["risk_tier"], "MEDIUM")  # 기존 반환 조항이 있어 기준만 보완
        r = {str(c["clause_id"]).split("__")[0]: c for c in _live(self.runs["renamed_shifted"].clause_results)}
        self.assertEqual(r["sp_guarantee_vs_tentative"]["article_number"], "4")
        self.assertEqual(r["sp_license_vs_approval"]["article_number"], "7")

    def test_sufficient_protection_is_not_reproposed(self) -> None:
        core = {"sp_guarantee_vs_tentative", "sp_performance_guarantee", "sp_schedule_deadline",
                "sp_payment_timing", "sp_license_vs_approval", "sp_disclosure"}
        self.assertFalse(core & _ids(self.runs["sufficient"].clause_results))

    def test_really_missing_refunds(self) -> None:
        m = {str(c["clause_id"]).split("__")[0]: c for c in _live(self.runs["missing"].clause_results)}
        self.assertEqual(m["sp_performance_guarantee"]["risk_tier"], "HIGH")
        self.assertIn("sp_force_majeure_refund", m)
        self.assertNotIn("제9조 제3항", m["sp_performance_guarantee"]["redline_instruction"]["final_clause_text"])

    def test_reversed_roles_get_producer_side_review_only(self) -> None:
        ids = _ids(self.runs["reversed"].clause_results)
        self.assertIn("sp_recipient_guarantee_exposure", ids)
        self.assertFalse({i for i in ids if re.match(r"sp_(?:guarantee_vs|performance_guarantee|license|disclosure)", i)})

    def test_no_wrong_frames_or_foreign_text(self) -> None:
        for name, b in self.runs.items():
            blob = json.dumps(_live(b.clause_results), ensure_ascii=False)
            self.assertIsNone(re.search(r"양도s*조항에s*권리", blob), name)
            self.assertIsNone(re.search(r"오픈소스|소스\s*코드|제품화", blob), name)
            self.assertIsNone(re.search(r"업계\s*(?:표준|관행)|수용\s*가능성이\s*높", blob), name)

    def test_unconfirmed_privacy_and_broadcast_are_not_asserted(self) -> None:
        for name, b in self.runs.items():
            self.assertFalse([c for c in _live(b.clause_results) if "개인정보" in str(c.get("issue_title") or "")
                              and str(c.get("risk_tier")).upper() == "HIGH" and not c.get("business_check")], name)
            dec = {d["statute"]: d["conclusion"] for d in b.meta["statute_applicability_gate"]["decisions"]}
            self.assertNotEqual(dec.get("개인정보보호법"), "일부 적용", name)

    def test_business_checks_without_invented_numbers(self) -> None:
        crs = self.runs["original"].clause_results
        biz = [c for c in crs if c.get("business_check") and not c.get("dedup_suppressed")]
        self.assertEqual({str(c["clause_id"]).split("__")[0] for c in biz} >= {"sp_biz_shorts", "sp_biz_product", "sp_biz_talent"}, True)
        talent = next(c for c in biz if str(c["clause_id"]).startswith("sp_biz_talent"))
        self.assertIn("누락이 아니다", talent["problem"])  # 명시된 비용분담은 협상안으로

    def test_revision_set_numbers_and_preserves_existing_protection(self) -> None:
        for name, b in self.runs.items():
            live = _live(b.clause_results)
            new_paras = [c["redline_instruction"].get("new_paragraph") for c in live
                         if isinstance(c.get("redline_instruction"), dict) and c["redline_instruction"].get("new_paragraph")]
            self.assertEqual(len(new_paras), len(set(new_paras)), name)
            for c in live:
                ri = c.get("redline_instruction") or {}
                if ri.get("edit_type") == "replace" and not ri.get("held"):
                    self.assertIn(re.sub(r"\s+", "", str(ri.get("target_text")))[:30],
                                  re.sub(r"\s+", "", str(ri.get("final_clause_text"))), (name, c["clause_id"]))


if __name__ == "__main__":
    unittest.main()
