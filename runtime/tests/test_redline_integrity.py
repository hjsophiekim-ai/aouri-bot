"""수정안 무결성 게이트 회귀 — 시디즈 영문 물품공급계약(2026-11-13) 실측 실패를 같은 입력으로 재현한다.

입력: (저장소 밖 실데이터 폴더) sidiz_supply_en/live_findings_before.json = 실제 라이브 검토(gpt-4.1) 출력 그대로(수정 전).
기대 결과는 실측 실패의 반대이며, 완화하지 않는다.
"""
from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from runtime.review import deal_flow as df
from runtime.review import redline_integrity as ri

from runtime.tests._private_fixtures import private_fixture


def _fx() -> dict:
    """실제 라이브 출력(실데이터) — 저장소 밖 로컬 폴더에만 있다. 없으면 SkipTest."""
    return json.loads(private_fixture("sidiz_supply_en/live_findings_before.json").read_text(encoding="utf-8"))


def _by_path(crs: list[dict], path: str) -> dict:
    return next(c for c in crs if c.get("display_path") == path)


def _active(c: dict) -> bool:
    return bool((c.get("has_rewrite_change") or c.get("has_addition"))
                and not (c.get("redline_instruction") or {}).get("held"))


def _run(fx: dict, crs: list[dict] | None = None, ours=("Supplier",), theirs=("Buyer",)) -> tuple[list[dict], dict]:
    crs = copy.deepcopy(fx["clause_results"] if crs is None else crs)
    rep = ri.run(clause_results=crs, clauses=fx["clauses"], contract_text=fx["text"], ours=list(ours), theirs=list(theirs),
                 request_text=fx["review_focus"], answers_text="")
    return crs, rep


class LiveFailuresSameInput(unittest.TestCase):
    """실제 라이브 출력(수정 전) → 게이트 통과 후."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = _fx()
        cls.crs, cls.rep = _run(cls.fx)

    def test_before_state_really_failed(self) -> None:
        # 입력이 실제로 실패 사례인지 먼저 확인한다(기대값을 맞추려고 입력을 바꾸지 않았다는 증거)
        raw = self.fx["clause_results"]
        self.assertIn("six percent (6%)", _by_path(raw, "Article 4.5")["suggested_rewrite"])
        self.assertNotIn("(b)", _by_path(raw, "Article 4.5")["suggested_rewrite"])
        self.assertNotIn("specifications", _by_path(raw, "Article 9.1")["suggested_rewrite"])
        self.assertNotIn("fraud", _by_path(raw, "Article 13.3")["suggested_rewrite"])
        self.assertRegex(_by_path(raw, "Article 13.4")["suggested_rewrite"], r"[가-힣]")

    def test_invented_interest_rate_not_inserted(self) -> None:
        c = _by_path(self.crs, "Article 4.5")
        self.assertFalse(_active(c) and "6%" in c.get("suggested_rewrite", ""))
        acts = [a["action"] for a in c.get("redline_integrity") or []]
        self.assertIn("invented_value_removed", acts)

    def test_existing_remedies_not_deleted(self) -> None:
        c = _by_path(self.crs, "Article 4.5")
        if _active(c):
            for m in ("(a)", "(b)", "(c)", "suspend any further shipment", "advance payment"):
                self.assertIn(m, c["suggested_rewrite"])

    def test_spec_warranty_kept_and_user_value_labelled(self) -> None:
        c = _by_path(self.crs, "Article 9.1")
        self.assertTrue(_active(c))
        self.assertIn("conform in all material respects to the agreed specifications", c["suggested_rewrite"])
        self.assertIn("twelve (12) months", c["suggested_rewrite"])
        self.assertTrue(c.get("user_answer_values"))

    def test_liability_cap_exceptions_not_lost(self) -> None:
        c = _by_path(self.crs, "Article 13.3")
        if _active(c):
            self.assertIn("fraud, willful misconduct", c["suggested_rewrite"])
            self.assertEqual(c["suggested_rewrite"].lower().count("cannot"), 1)   # 예외 중복 금지
        else:
            self.assertTrue((c.get("redline_instruction") or {}).get("held"))

    def test_mutual_indemnity_not_read_as_one_sided(self) -> None:
        c = _by_path(self.crs, "Article 13.4")
        self.assertFalse(_active(c))
        self.assertEqual(c["risk_tier"], "LOW")

    def test_no_korean_or_foreign_party_labels_inserted(self) -> None:
        for c in self.crs:
            if not _active(c):
                continue
            body = (c.get("suggested_rewrite") or "") + (c.get("addition_text") or "")
            self.assertNotRegex(body, r"[가-힣]", c.get("display_path"))
            self.assertNotRegex(body, r"\b(?:Consignee|Licensee|Contractor)\b")

    def test_custom_order_return_high_refuted(self) -> None:
        ids = {c.get("clause_id"): c for c in self.crs}
        for cid in ("sppc_return_limit", "sppc_custom_cancel_limit"):
            if cid in ids:
                self.assertNotEqual(ids[cid].get("risk_tier"), "HIGH")
                self.assertFalse(_active(ids[cid]))
        self.assertFalse([c for c in self.crs if c.get("risk_tier") == "HIGH" and _active(c)
                          and not c.get("worst_case_scenario")])

    def test_english_new_clause_numbering(self) -> None:
        locs = [(c.get("redline_instruction") or {}).get("edit_location") for c in self.crs if _active(c)]
        self.assertFalse([x for x in locs if x and re.search(r"제\s*\d+\s*조", x)], locs)
        en_new = [x for x in locs if x and re.search(r"Article\s+\d+\.\d+\s*신설", x)]
        self.assertEqual(len(en_new), len(set(en_new)), "같은 항 번호에 두 신설")

    def test_every_action_recorded(self) -> None:
        self.assertTrue(self.rep["actions"])
        for a in self.rep["actions"]:
            self.assertTrue(a["action"] and a["detail"])


class AbsenceClaimsRecheck(unittest.TestCase):
    """이미 있는 지급·FOB·취소·종료 조항을 없다고 지적 — 계약 전체 검색으로 철회."""

    def test_absence_refuted(self) -> None:
        fx = _fx()
        fake = []
        for title in ("대금 지급 조건 미규정", "인도 조건(FOB) 없음", "주문 취소 조항이 없음", "계약 해지 조항 누락"):
            fake.append({"clause_id": f"chk_{len(fake)}", "display_path": "", "clause_title": title,
                         "rewrite_reason": f"{title} — 명시하세요", "risk_tier": "HIGH", "severity": "HIGH",
                         "has_addition": True, "addition_text": "The Buyer shall pay within thirty (30) days.",
                         "original_text": "(해당 조항 없음)"})
        crs, rep = _run(fx, fake)
        crs = [c for c in crs if str(c.get("clause_id")).startswith("chk_")]
        for c in crs:
            self.assertEqual(c["risk_tier"], "LOW", c["clause_title"])
            self.assertFalse(_active(c))
            self.assertTrue(c.get("existing_protection_paths"), c["clause_title"])
        paths = {p for c in crs for p in c["existing_protection_paths"]}
        for p in ("Article 4.3", "Article 5.1", "Article 3.3", "Article 15.3"):
            self.assertIn(p, paths)


class SubItemAndNumbering(unittest.TestCase):
    def test_rewrite_dropping_sub_items_is_restored(self) -> None:
        orig = ("If the Buyer fails to make any payment when due, the Supplier may:\n(a) charge interest at the rate of [ ]% per annum;\n"
                "(b) suspend any further shipment; and/or\n(c) require advance payment for subsequent orders.")
        new = ("If the Buyer fails to make any payment when due, the Supplier may:\n(a) charge interest at the rate of [ ]% per annum, "
               "and the Buyer shall also reimburse reasonable collection costs;")
        fx = _fx()
        cr = {"clause_id": "x", "display_path": "Article 4.5", "original_text": orig, "suggested_rewrite": new,
              "has_rewrite_change": True, "risk_tier": "MEDIUM", "rewrite_reason": "회수 비용 보전"}
        crs, _ = _run(fx, [cr])
        out = crs[0]["suggested_rewrite"]
        for m in ("(a)", "(b) suspend", "(c) require", "collection costs"):
            self.assertIn(m, out)
        self.assertLess(out.index("(a)"), out.index("(b)"))
        self.assertLess(out.index("(b)"), out.index("(c)"))

    def test_noop_rewrite_removed(self) -> None:
        fx = _fx()
        cr = {"clause_id": "y", "display_path": "Article 16.3", "original_text": "courts of [ ], unless",
              "suggested_rewrite": "courts of [], unless", "has_rewrite_change": True, "risk_tier": "MEDIUM", "rewrite_reason": "명확화"}
        crs, _ = _run(fx, [cr])
        self.assertFalse(_active(crs[0]))


class OpinionMatchesEdit(unittest.TestCase):
    """검토 의견과 실제 수정문 불일치 — 의견이 말하지 않은 원문 변경은 반영하지 않는다."""

    def test_unrelated_rewording_held(self) -> None:
        fx = _fx()
        orig = "This Agreement shall be governed by the laws of the State of California, excluding its conflict-of-laws rules."
        new = "This Agreement shall be governed by the laws of the Republic of Korea."
        cr = {"clause_id": "z", "display_path": "Article 16.1", "original_text": orig, "suggested_rewrite": new,
              "has_rewrite_change": True, "risk_tier": "MEDIUM", "rewrite_reason": "관할 법원 공란을 확정한다"}
        crs, rep = _run(fx, [cr])
        self.assertFalse(_active(crs[0]))
        self.assertIn("rewrote_existing", [a["action"] for a in rep["actions"]])


class RoleSwitch(unittest.TestCase):
    """우리 회사가 공급자 ↔ 구매자로 바뀌면 판단도 바뀐다."""

    def setUp(self) -> None:
        self.text = _fx()["text"]

    def test_supplier(self) -> None:
        r = df.resolve_role(self.text, "시디즈가 미국 딜러에게 물품을 공급", "시디즈")
        self.assertEqual((r.status, r.our_label, r.our_role_kind, r.counterparty_label), (df.ROLE_CONFIRMED, "Supplier", "seller", "Buyer"))

    def test_buyer(self) -> None:
        sw = (self.text.replace("SIDIZ, INC., a corporation organized under the laws of the Republic of Korea",
                                "ACME TRADING LLC, a company organized under the laws of the State of Delaware")
              .replace("[ ], a company organized under the laws of [ ], having its principal office at [ ] (hereinafter\nreferred to as the \"Buyer\")",
                       "SIDIZ, INC., a corporation organized under the laws of the Republic of Korea (hereinafter\nreferred to as the \"Buyer\")")
              .replace("SUPPLIER\nSIDIZ, INC.", "SUPPLIER\nACME TRADING LLC").replace("BUYER\n[ ]", "BUYER\nSIDIZ, INC."))
        r = df.resolve_role(sw, "시디즈가 미국 업체로부터 물품을 구매", "시디즈")
        self.assertEqual((r.status, r.our_label, r.our_role_kind), (df.ROLE_CONFIRMED, "Buyer", "buyer"))
        fx = _fx()
        fx["text"] = sw
        # 우리가 독점권을 '받는' 쪽이면 최소 구매 의무 협상 권고를 만들지 않는다
        crs, rep = _run(fx, [], ours=("Buyer",), theirs=("Supplier",))
        self.assertFalse(rep["added_findings"])
        # 공급자 보호 조항(6.2 소유권 유보)은 구매자에게 '유리한 조항'이 아니다
        t62 = next(c["text"] for c in fx["clauses"] if c["display_path"] == "Article 6.2")
        self.assertEqual(ri.clause_posture(t62, ["Supplier"], ["Buyer"]), "favorable")
        self.assertNotEqual(ri.clause_posture(t62, ["Buyer"], ["Supplier"]), "favorable")

    def test_supplier_gets_exclusivity_check_only_when_exclusive(self) -> None:
        fx = _fx()
        _crs, rep = _run(fx, [])
        self.assertTrue(rep["added_findings"])           # 답변: 독점 부여
        fx2 = _fx()
        fx2["review_focus"] = fx2["review_focus"].replace("네 독점권을 부여합니다.", "아직 정하지 않았습니다.")
        _crs2, rep2 = _run(fx2, [])
        self.assertFalse(rep2["added_findings"])         # 선택지 공란 + 미확정 → 만들지 않는다


class CommercialBlanks(unittest.TestCase):
    def test_blanks_not_filled_and_user_values_marked(self) -> None:
        fx = _fx()
        _crs, rep = _run(fx, [])
        rows = {r["label"]: r for r in rep["commercial_terms"]}
        for lab in ("대금 지급기일", "연체이자율", "보증기간", "판매지역(Territory)", "관할 법원"):
            self.assertIn(lab, rows)
        self.assertEqual(rows["연체이자율"]["user_value"], "")
        self.assertIn("12", rows["보증기간"]["user_value"])
        self.assertEqual(rows["대금 지급기일"]["user_value"], "")      # '아직 확정되지 않았습니다' 는 값이 아니다

    def test_request_topics_each_answered(self) -> None:
        fx = _fx()
        _crs, rep = _run(fx)
        names = [r["normalized_issue"] for r in rep["request_rows"]]
        for n in ("대금 지급", "인도·선적 조건", "보증", "지식재산권", "관세·통관"):
            self.assertIn(n, names)
        for r in rep["request_rows"]:
            self.assertTrue(r["answer_clause_paths"], r["normalized_issue"])


if __name__ == "__main__":
    unittest.main()
