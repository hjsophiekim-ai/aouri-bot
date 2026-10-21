"""Golden — 콘텐츠 제작 프리랜서 용역계약 (2026-10-21 원문·판단 일치 / 수정안 전부 반영 검증).

fixture
    content_editor_service_contract.txt   실제 계약 추출본(주소·대표자·사업자번호 비식별)
    content_editor_service_session.json   실제 세션의 검토요청문·답변

수정 전(실측, reports_evidence/freelancer_q4/before)
    요약 "산출물 지식재산권 귀속·검수 기준·대금 지급 조건: 미기재" (세 축 모두 원문 제4·5·8조에 있음)
    제8조 제1항(귀속)을 "양도가 아니라 이용허락" 으로 설명, "저작권법 제2항"(제45조가 잘림)
    보완 문장 두 건이 모두 "제12조 뒤에 제13조 신설", 새 조 안의 "제1항에 따라" — 어느 조인지 불명확
    "계약서 전반 검토" 요청이 제목·배경·요청 3줄로 쪼개져 각각 "적정 / 수정 불필요"
    원문 상호참조 오류(큐레이션형 뉴스레터를 '제5호' 로 지칭 — 실제 제3호) 미검토
    업로드 분류가 "산출물" 한 낱말로 앱개발 → SOW·소프트웨어 문구가 수정안에 혼입

회사명·조항번호에 기대지 않는지 보기 위해 같은 계약의 변형(당사자명 변경 + 앞에 조 하나를 끼워 모든 조번호가
하나씩 밀린 것), 보호가 이미 충분한 변형, 실제로 조항이 빠진 변형을 함께 돌린다.
"""
from __future__ import annotations

import json
import logging
import re
import unittest
from pathlib import Path

from runtime.review.clause_extraction import extract_clauses

FIX = Path(__file__).resolve().parent / "fixtures"
TEXT = (FIX / "content_editor_service_contract.txt").read_text(encoding="utf-8")
SESSION = json.loads((FIX / "content_editor_service_session.json").read_text(encoding="utf-8"))


def _renamed_and_shifted(text: str) -> str:
    """당사자명을 바꾸고, 제1조 앞에 정의 조를 끼워 모든 조번호(본문 참조 포함)를 하나씩 민다."""
    t = text.replace("주식회사 퍼시스", "주식회사 한빛가구").replace("퍼시스닷컴", "한빛닷컴") \
        .replace("퍼시스", "한빛").replace("스튜디오 하늘빛", "글마루 스튜디오")
    t = re.sub(r"제\s*(\d+)\s*조", lambda m: f"제{int(m.group(1)) + 1}조" if " " not in m.group(0)
               else f"제 {int(m.group(1)) + 1} 조", t)
    head, sep, rest = t.partition("제 2 조. [계약의 목적]")
    return head + "제 1 조. [정의]\n본 계약에서 \"성과물\"이란 \"을\"이 본 계약에 따라 작성하여 제출하는 원고를 말한다.\n" + sep + rest


def _with_sufficient_protection(text: str) -> str:
    """보호가 충분한 변형 — 상호참조를 바로잡고, 귀속 조항에 재가공·저작인격권·지급 전 이용을 넣는다."""
    t = text.replace("제2호 및 제5호", "제2호 및 제3호").replace("제2호·제5호", "제2호·제3호")
    return t.replace(
        "독점적, 배타적으로\n귀속된다.",
        "독점적, 배타적으로\n귀속된다. 이 권리에는 2차적저작물을 작성하여 이용할 권리가 포함되며, \"을\"은 \"갑\"의 편집·"
        "재구성 이용에 대하여 저작인격권을 행사하지 아니한다. 용역대금 지급 전이라도 \"갑\"은 검수 완료된 성과물을 "
        "게시·이용할 수 있다.",
    )


def _without_ip_clause(text: str) -> str:
    """실제로 IP 귀속이 빠진 변형 — 제8조 제1항을 지운다."""
    return re.sub(r"① 본 계약에 의한 최종 산출물에 대한 지식재산권은[^.]*\.\n", "", text)


def _focus() -> str:
    return SESSION["review_focus"]


def _run(text: str):
    from runtime.review.clause_level import build_clause_level_result
    from runtime.rules.loader import RuleLoader
    from runtime.services.query_service import RuleQueryService

    loader = RuleLoader()
    loader.load()
    logging.disable(logging.CRITICAL)
    try:
        return build_clause_level_result(
            service=RuleQueryService(loader), entity=SESSION["entity"], contract_type="용역/자문/SOW",
            text=text, filename=SESSION["filename"], answers={}, review_focus=_focus(),
            asked_questions=None, law_service=None, ai_provider=None, ai_model=None,
            ai_timeout_sec=None, ai_max_tokens=None, ai_temperature=None,
        )
    finally:
        logging.disable(logging.NOTSET)


def _live(crs: list[dict]) -> list[dict]:
    return [c for c in crs if not c.get("dedup_suppressed") and not c.get("keep_as_is")
            and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]


# ── 단위: 새로 만든 판단들은 조항번호·회사명 없이 작동해야 한다 ─────────────────────────

class CrossReferenceUnitTest(unittest.TestCase):
    def _errors(self, text: str):
        from runtime.review.cross_reference_check import find_cross_reference_errors
        return find_cross_reference_errors(extract_clauses(text)[0])

    def test_wrong_item_number_is_found_with_correct_target(self) -> None:
        errs = self._errors(TEXT)
        self.assertEqual({(e.article, e.paragraph) for e in errs}, {("2", "2"), ("5", "3")})
        for e in errs:
            self.assertEqual((e.name, e.actual_items, e.wrong_items), ("큐레이션형 뉴스레터", ["3"], ["5"]))

    def test_found_after_renaming_and_renumbering(self) -> None:
        errs = self._errors(_renamed_and_shifted(TEXT))
        self.assertEqual({(e.article, e.paragraph) for e in errs}, {("3", "2"), ("6", "3")})

    def test_no_false_positive_when_references_are_right(self) -> None:
        self.assertEqual(self._errors(_with_sufficient_protection(TEXT)), [])

    def test_reference_to_missing_item(self) -> None:
        errs = self._errors(TEXT.replace("제2호 및 제5호", "제2호 및 제7호"))
        self.assertTrue(any(e.kind == "missing_target" for e in errs))

    def test_finding_rewrite_fixes_only_the_wrong_number(self) -> None:
        from runtime.review.cross_reference_check import build_findings, find_cross_reference_errors
        cl = extract_clauses(TEXT)[0]
        fs = build_findings(find_cross_reference_errors(cl), cl)
        self.assertEqual(len(fs), 1)  # 같은 오인용은 연계 수정으로 묶는다
        self.assertIn("제2호 및 제3호", fs[0]["suggested_rewrite"])
        self.assertIn("제2호·제3호", fs[0]["package_linked_edits"][0]["text"])
        self.assertIn("다만, 단순 오탈자", fs[0]["package_linked_edits"][0]["text"])  # 같은 항의 다른 문장 보존


class LegalEffectUnitTest(unittest.TestCase):
    def test_vesting_clause_is_assignment_not_license(self) -> None:
        from runtime.review.statute_grounding import detect_relations
        cr = {"issue_title": "콘텐츠 권리 이전 및 사용권 범위 보완 필요",
              "problem": "편집·재가공·2차적저작물 작성 권한이 없다.",
              "original_text": "최종 산출물에 대한 지식재산권은 용역대금 지급과 동시에 \"갑\"에게 독점적, 배타적으로 귀속된다."}
        rels = detect_relations(cr)
        self.assertIn("ip_assignment", rels)
        self.assertIn("assignment_derivative", rels)
        self.assertNotIn("ip_license", rels)

    def test_license_clause_stays_license(self) -> None:
        from runtime.review.statute_grounding import detect_relations
        cr = {"issue_title": "이미지 이용 범위 보완", "problem": "2차적 이용 범위가 없다",
              "original_text": "을은 갑에게 본 저작물의 이용을 허락한다."}
        self.assertIn("ip_license", detect_relations(cr))

    def test_verified_statute_citation_survives_polish(self) -> None:
        from runtime.review.korean_polish import _strip_unverified_law_article_numbers as strip
        self.assertEqual(strip("추정되므로(저작권법 제45조 제2항), 편집"), "추정되므로(저작권법 제45조 제2항), 편집")
        # 검증표에 없는 조문은 항까지 통째로 빠진다 — "하도급법 제1항" 같은 없는 인용을 남기지 않는다.
        self.assertEqual(strip("하도급법 제3조 제1항 위반"), "하도급법 위반")


class SummaryFactUnitTest(unittest.TestCase):
    def _facts(self, text: str) -> dict:
        from runtime.review.clause_index import build_clause_index
        from runtime.review.legal_map_grounding import resolve_summary_facts
        return resolve_summary_facts({}, clause_index=build_clause_index(text, extract_clauses(text)[0]),
                                     contract_text=text)

    def test_existing_terms_are_explicit_with_location(self) -> None:
        for text, arts in ((TEXT, {"deliverables_ip_owner": "8", "acceptance_criteria": "5", "payment_terms": "4"}),
                           (_renamed_and_shifted(TEXT),
                            {"deliverables_ip_owner": "9", "acceptance_criteria": "6", "payment_terms": "5"})):
            facts = self._facts(text)
            for key, art in arts.items():
                self.assertEqual((facts[key]["status"], facts[key]["article"]), ("explicit", art), key)
                self.assertNotIn("미기재", facts[key]["display"])

    def test_really_missing_vs_extraction_failure(self) -> None:
        facts = self._facts(_without_ip_clause(TEXT))
        self.assertNotEqual(facts["deliverables_ip_owner"]["status"], "explicit")
        tiny = self._facts("제 1 조. [목적]\n본 계약은 용역에 관한 것이다.")
        self.assertEqual(tiny["payment_terms"]["status"], "extraction_failed")


class RequestScopeUnitTest(unittest.TestCase):
    def test_form_headers_and_comprehensive_request(self) -> None:
        from runtime.review.user_review_request import COMPREHENSIVE_ISSUE_ID, parse_user_review_request
        r = parse_user_review_request(review_focus=_focus(), contract_type_code="content_production_service")
        self.assertEqual([i.issue_id for i in r.issues], [COMPREHENSIVE_ISSUE_ID])

    def test_mixed_request_keeps_the_specific_question(self) -> None:
        from runtime.review.user_review_request import COMPREHENSIVE_ISSUE_ID, parse_user_review_request
        r = parse_user_review_request(review_focus="계약 전반 검토 부탁드립니다. 특히 제5조 검수 기간이 짧은지 봐주세요.",
                                      contract_type_code="content_production_service")
        ids = [i.issue_id for i in r.issues]
        self.assertEqual(ids[0], COMPREHENSIVE_ISSUE_ID)
        self.assertTrue(any("제5조" in i.original_user_text for i in r.issues[1:]))

    def test_comprehensive_row_answers_with_the_whole_report(self) -> None:
        from runtime.review.user_review_request import (
            COMPREHENSIVE_ISSUE_ID, UserReviewIssue, build_user_request_coverage,
        )
        issue = UserReviewIssue(issue_id=COMPREHENSIVE_ISSUE_ID, source="explicit", original_user_text="전반 검토",
                                normalized_issue="계약서 전반 검토")
        rows = build_user_request_coverage([issue], clause_results=[
            {"clause_id": "a", "risk_tier": "HIGH", "display_path": "제8조"}])
        self.assertEqual((rows[0]["review_status"], rows[0]["needs_revision"]), ("수정 필요", True))
        rows = build_user_request_coverage([issue], clause_results=[])
        self.assertEqual(rows[0]["review_status"], "적정")
        self.assertIn("전체를 검토 범위", rows[0]["conclusion"])


class MonetaryPenaltyDirectionTest(unittest.TestCase):
    def test_only_penalties_we_bear_and_nobody_reviewed(self) -> None:
        from runtime.review.self_check import unreviewed_monetary_penalties as u
        self.assertEqual(u(TEXT, [], ("갑",)), [])                       # 상대방(을)이 부담 — 우리 리스크 아님
        self.assertEqual([x["article"] for x in u(TEXT, [], ("을",))], ["11"])  # 우리가 을이면 검토 필요
        self.assertEqual(u(TEXT, [{"article_number": "11"}], ("을",)), [])  # 그 조를 다룬 검토 결과가 있으면 끝


class IntakeClassificationTest(unittest.TestCase):
    def test_deliverable_and_acceptance_words_do_not_make_software_or_equipment(self) -> None:
        from runtime.review.classify import _classify_contract_type
        self.assertEqual(_classify_contract_type(TEXT, None), "용역/자문/SOW")
        self.assertEqual(_classify_contract_type(_renamed_and_shifted(TEXT), None), "용역/자문/SOW")

    def test_real_software_and_equipment_contracts_keep_their_type(self) -> None:
        from runtime.review.classify import _classify_contract_type
        app = (FIX / "app_dev_contract.txt").read_text(encoding="utf-8")
        equip = (FIX / "lg_purchase_installation.txt").read_text(encoding="utf-8")
        self.assertEqual(_classify_contract_type(app, None), "앱개발/소프트웨어개발/SI/유지보수/SaaS")
        self.assertEqual(_classify_contract_type(equip, None), "장비공급/설치/시운전")

    def test_inferred_cache_does_not_override_text(self) -> None:
        from runtime.review.infer import merge_inference
        inf = merge_inference(None, None, "퍼시스", "용역/자문/SOW", "__no_such_cached_file__.pdf", None)
        self.assertEqual(inf.contract_type, "용역/자문/SOW")


class KeepAndDeclarativeTest(unittest.TestCase):
    def test_scope_change_already_needs_written_agreement(self) -> None:
        from runtime.review.issue_triage import keep_reason
        cr = {"issue_title": "과업 범위/사양(SOW) 불명확 리스크 점검"}
        self.assertTrue(keep_reason(cr, "other", TEXT, ""))
        no_clause = re.sub(r"제 9 조\. \[계약내용의 변경\][^제]*", "", TEXT)
        self.assertEqual(keep_reason(cr, "other", no_clause, ""), "")

    def test_article_protection_follows_content_not_number(self) -> None:
        from runtime.review.clause_level import _article_text_for, _is_declarative_clause
        self.assertTrue(_is_declarative_clause(_article_text_for(TEXT, 1, {})))   # 목적 조항
        self.assertFalse(_is_declarative_clause(_article_text_for(TEXT, 2, {})))  # 업무 범위 — 실질 조항
        self.assertFalse(_is_declarative_clause(_article_text_for(TEXT, 3, {})))  # 계약기간


class RevisionSetUnitTest(unittest.TestCase):
    def _index(self):
        from runtime.review.clause_index import build_clause_index
        return build_clause_index(TEXT, extract_clauses(TEXT)[0])

    @staticmethod
    def _cr(cid, art, loc, et, text, target="", tier="MEDIUM"):
        return {"clause_id": cid, "article_number": art, "risk_tier": tier, "display_path": f"제{art}조",
                "practical_position": {"method": "replace_text", "location": cid},
                "redline_instruction": {"edit_location": loc, "edit_type": et, "replacement_text": text,
                                        "final_clause_text": text, "target_text": target}}

    def test_supplements_become_paragraphs_and_new_articles_get_distinct_numbers(self) -> None:
        from runtime.review.revision_set_check import check_revision_set
        crs = [
            self._cr("a", "8", "제12조 뒤에 제13조 신설", "new_clause", "제1항에 따라 귀속되는 권리에는 2차적저작물작성권이 포함된다."),
            self._cr("b", "10", "제12조 뒤에 제13조 신설", "new_clause", "을은 정산 대상 작업물을 갑에게 인도한다."),
            self._cr("c", "", "제12조 뒤에 제13조 신설", "new_clause", "을은 개인정보를 처리하는 경우 별도 위탁계약을 체결한다."),
            self._cr("d", "", "제12조 뒤에 제13조 신설", "new_clause", "을은 하도급 시 갑의 사전 서면 승인을 받는다."),
        ]
        rep = check_revision_set(crs, clause_index=self._index(), contract_text=TEXT)
        locs = [c["redline_instruction"]["edit_location"] for c in crs]
        self.assertEqual(locs[:2], ["제8조 제5항 뒤에 제6항 신설", "제10조 제3항 뒤에 제4항 신설"])
        self.assertEqual(locs[2:], ["제12조 뒤에 제13조 신설", "제13조 뒤에 제14조 신설"])
        self.assertTrue(crs[0]["redline_instruction"]["final_clause_text"].startswith("⑥"))
        self.assertEqual(crs[0]["practical_position"]["method"], "insert")
        self.assertEqual(rep["held"], [])

    def test_bare_paragraph_in_new_article_and_lost_protection_are_held(self) -> None:
        from runtime.review.revision_set_check import check_revision_set
        target = ("\"을\"은 \"갑\"의 사전 동의 없이 제1항의 비공개 자료를 외부 서비스 또는 제3자 시스템(생성형 AI\n"
                  "서비스를 포함한다)에 입력하거나 제공해서는 안 된다.")
        crs = [
            self._cr("x", "", "제12조 뒤에 제13조 신설", "new_clause", "제1항에 따라 을은 자료를 반환한다."),
            self._cr("y", "7", "제7조 제2항 교체", "replace", "을은 개인정보를 안전하게 처리한다.", target=target),
            self._cr("z", "7", "제7조 제2항 교체", "replace",
                     target.replace("안 된다.", "안 되며, 위반 시 손해를 배상한다."), target=target),
        ]
        rep = check_revision_set(crs, clause_index=self._index(), contract_text=TEXT)
        held = {h["clause_id"] for h in rep["held"]}
        self.assertEqual(held, {"x", "y"})          # z 는 기존 보호를 그대로 두고 덧붙인 교체
        self.assertTrue(crs[1]["redline_instruction"]["held"])
        self.assertIn("비공개", crs[1]["rewrite_hold_reason"])


# ── 파이프라인(AI 미사용): 원문·변형·충분·누락 4건 ─────────────────────────────────────

class PipelineGoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runs = {
            "original": _run(TEXT),
            "renamed_shifted": _run(_renamed_and_shifted(TEXT)),
            "sufficient": _run(_with_sufficient_protection(TEXT)),
            "ip_missing": _run(_without_ip_clause(TEXT)),
        }

    def test_summary_uses_the_same_facts_as_the_detail(self) -> None:
        for name in ("original", "renamed_shifted", "sufficient"):
            dp = self.runs[name].meta["detailed_contract_profile"]
            for key in ("deliverables_ip_owner", "acceptance_criteria", "payment_terms"):
                self.assertTrue(str(dp[key]).startswith("규정 있음"), (name, key, dp[key]))
        self.assertFalse(str(self.runs["ip_missing"].meta["detailed_contract_profile"]["deliverables_ip_owner"])
                         .startswith("규정 있음"))

    def test_no_license_framing_or_broken_citation(self) -> None:
        for name, b in self.runs.items():
            blob = json.dumps(_live(b.clause_results), ensure_ascii=False)
            self.assertNotIn("양도가 아니라 이용허락", blob, name)
            self.assertIsNone(re.search(r"저작권법\s*제\s*\d+\s*항", blob), name)

    def test_cross_reference_error_reported_only_when_present(self) -> None:
        for name, expect in (("original", True), ("renamed_shifted", True), ("sufficient", False)):
            xs = [c for c in _live(self.runs[name].clause_results) if c.get("is_cross_reference_error")]
            self.assertEqual(bool(xs), expect, name)

    def test_revision_set_has_no_number_collision_or_ambiguous_reference(self) -> None:
        for name, b in self.runs.items():
            new_arts = [c["redline_instruction"].get("new_article") for c in _live(b.clause_results)
                        if isinstance(c.get("redline_instruction"), dict) and c["redline_instruction"].get("new_article")]
            self.assertEqual(len(new_arts), len(set(new_arts)), name)
            for c in _live(b.clause_results):
                ri = c.get("redline_instruction") or {}
                if ri.get("new_article") and not ri.get("held"):
                    self.assertIsNone(re.search(r"(?<!조\s)(?<!조)제\s*\d+\s*항", str(ri.get("final_clause_text"))), name)

    def test_ip_gap_is_a_paragraph_of_the_ip_article(self) -> None:
        for name, art in (("original", "8"), ("renamed_shifted", "9")):
            ip = [c for c in _live(self.runs[name].clause_results)
                  if "2차적" in str(c.get("suggested_rewrite") or "")]
            self.assertTrue(ip, name)
            self.assertTrue(str(ip[0]["redline_instruction"]["edit_location"]).startswith(f"제{art}조 제"), name)

    def test_sufficient_protection_is_not_reproposed(self) -> None:
        live = _live(self.runs["sufficient"].clause_results)
        self.assertFalse([c for c in live if "2차적" in str(c.get("suggested_rewrite") or "")])

    def test_personal_data_unconfirmed_is_not_high(self) -> None:
        for name, b in self.runs.items():
            self.assertFalse([c for c in _live(b.clause_results)
                              if "개인정보" in str(c.get("issue_title") or "") and str(c.get("risk_tier")).upper() == "HIGH"],
                             name)

    def test_confidentiality_protection_not_dropped(self) -> None:
        for name, b in self.runs.items():
            for c in _live(b.clause_results):
                ri = c.get("redline_instruction") or {}
                if ri.get("edit_type") == "replace" and "비공개" in str(ri.get("target_text")) and not ri.get("held"):
                    for w in ("비공개", "생성형"):
                        self.assertIn(w, str(ri.get("final_clause_text")), name)

    def test_comprehensive_request_is_not_answered_as_adequate(self) -> None:
        cov = self.runs["original"].meta.get("user_review_coverage") or []
        rows = [r for r in cov if r.get("is_comprehensive_scope")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["review_status"], "수정 필요")
        self.assertFalse([r for r in cov if not r.get("is_comprehensive_scope") and r.get("review_status") == "적정"])


if __name__ == "__main__":
    unittest.main()
