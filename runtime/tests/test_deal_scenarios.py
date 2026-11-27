"""계약 전체 상황별 검증(deal_scenarios) — 문구 포함 여부가 아니라 상황별 책임·권리·비용 결과로 본다(2026-11-03).

A 묶음: Norden 디자인 라이선스(회귀 사례) 문구 구조 — Customer(우리) / NDG(상대방).
B 묶음: 별도 사례 — 일룸 영문 독점 디자인 라이선스 구조(Licensee(우리) / Licensor(상대방), 다른 조 번호·다른 지역 제한).
같은 규칙이 조항 번호·당사자 이름과 무관하게 작동하는지 본다.
"""
from __future__ import annotations

import unittest

from runtime.review.deal_scenarios import (
    LIABLE, NOT_LIABLE, OUT_OF_SCOPE, Parties, agreement_records, evaluate, liability_table,
)

P = Parties(ours=["Customer"], theirs=["NDG"], aliases_ours=["Sidiz Inc."])
L = Parties(ours=["Licensee"], theirs=["Licensor"])


def codes(res: dict) -> set[str]:
    return {p["code"] for p in res["problems"] if p["severity"] in ("block", "fix")}


# ── A. 회귀 사례 구조 ──────────────────────────────────────────────────────────
A_ORIG = {
    "Article 4.1": ("For the usage of the reference “Design by Studio F. A. Norden” Customer shall pay to NDG a reimbursement of 7 % "
                    "of the dealer supply price of every sold unit. The reimbursement according to article 4.1 is due until the end of the contract period."),
    "Article 6.6": ("The design may be used, and the products marketed, and sold worldwide. An exception applies to Mainland China: the customer is "
                    "permitted to sell the product there, but without the reference to \"Design by Studio F. A. Norden\"."),
    "Article 9.9": ("Customer shall indemnify NDG against all claims by third parties to whom NDG is not liable internally in relation to Customer. "
                    "It is clarified that Customer shall indemnify, defend and hold harmless NDG, its affiliates, officers, directors, employees, agents "
                    "and customers from and against any and all losses, liabilities, costs, damages, expenses, including legal fees, arising out of or "
                    "relating to any third party claim: (a) a breach by Customer of any of the representations; or (b) Customer’s negligence, willful "
                    "misconduct or intentional misrepresentation. The customer is obliged to defend, indemnify and hold NDG harmless from all third-party "
                    "claims arising from, relating to or resulting from or in connection with the design product."),
    "Article 10.1": ("If any claim is made on NDG by a third party based on infringement of proprietary rights and if NDG has executed the order "
                     "complying with Customer’s standards, Customer shall be obliged to indemnify NDG against such claims."),
    "Article 13.1": ("This Agreement shall come into force upon signature by both parties and shall end after five years with the option to extend "
                     "for further five years, subject to the consent of both Parties."),
    "Article 13.3": ("As from the termination of this Agreement Customer shall refrain from using its rights according to clause 6 and from the "
                     "manufacture, sale and distribution of the Design Product, unless the parties agree upon otherwise in writing."),
}
# final5 실측 수정안(문제 있는 판)
A_BAD = dict(A_ORIG)
A_BAD["Article 9.9"] = (
    "Customer shall indemnify NDG only against third party claims to the extent such claims arise out of (a) a breach by Customer of any of "
    "the representations; or (b) Customer’s negligence, willful misconduct or intentional misrepresentation. For the avoidance of doubt, "
    "Customer shall not be liable to indemnify NDG for losses arising from (i) the acts or omissions of NDG, its affiliates, officers, "
    "employees or customers, (ii) any design, specification or intellectual property provided by NDG, or (iii) any third party claims relating "
    "to the Design Product except to the extent caused by Customer’s breach, negligence or willful misconduct. The conditions and the amount "
    "of insurance cover shall constitute the maximum limit of the Customer's obligation to indemnify NDG for product liability claims covered by such insurance.")
A_BAD["Article 10.1"] = (
    "If any claim is made on NDG by a third party based on infringement of proprietary rights, Customer shall, to the extent that such claim "
    "arises directly and solely from Customer’s specifications or instructions, indemnify NDG against such claims, including reasonable legal fees. "
    "The total liability of Customer under this Article 10.1 shall in no event exceed [●] per contract year.")
A_BAD["Article 13.1"] = (
    "This Agreement shall come into force upon signature by both parties and shall end after five years, provided that unless Customer is in "
    "material breach of this Agreement which remains uncured after written notice and a reasonable cure period, Customer shall have the option "
    "to extend this Agreement for a further five years by giving written notice to NDG at least [●] months prior to the expiration of the initial term.")
A_BAD["Article 4.1"] = A_ORIG["Article 4.1"].replace(
    "is due until the end of the contract period.",
    "is due until the end of the contract period, provided that for any Design Products sold or delivered, or parts supplied, pursuant to "
    "clause 13.4 after the termination or expiration of this Agreement, the reimbursement shall continue to be due.")
A_BAD["Article 13.4"] = (
    "Notwithstanding clause 13.3, the following exceptions shall apply after the termination or expiration of this Agreement: (a) Order "
    "Fulfillment: Customer shall be entitled to manufacture and deliver Design Products under purchase orders accepted prior to termination, "
    "provided that such orders are notified in writing to NDG within [●] days, and may use the reference 'Design by Studio F. A. Norden' "
    "solely to that extent. (b) Sell-off of Existing Inventory: Customer shall be entitled to sell off inventory for a period of [●] months "
    "and may use the reference 'Design by Studio F. A. Norden' solely for that sale, and shall report the quantities to NDG. (c) After-Sales "
    "Service Parts: Customer shall be entitled to manufacture, store and supply parts for Design Products sold prior to the termination or "
    "expiration of this Agreement, solely for warranty purposes, and may use the Design to that extent, for a period equal to the standard warranty "
    "period, but in no event longer than [●] years after the termination date.")

# 같은 사안을 바르게 고친 판
A_GOOD = dict(A_BAD)
A_GOOD["Article 9.9"] = (
    "Subject to Article 10.1, Customer shall indemnify, defend and hold harmless NDG, its affiliates, officers, directors and employees only "
    "against third party claims to the extent such claims arise out of (a) a breach by Customer of any of the representations; or "
    "(b) Customer’s negligence, gross negligence or willful misconduct. Customer shall not be liable to indemnify NDG for losses arising from "
    "(i) the acts or omissions of NDG, or (ii) any design or intellectual property provided by NDG. Customer's aggregate liability under this "
    "Article 9.9 and Article 10.1, including defence costs, legal fees, damages and indemnified amounts in respect of all indemnified parties, "
    "shall not exceed EUR [●] per claim and EUR [●] in the aggregate per contract year.")
A_GOOD["Article 10.1"] = (
    "If any claim is made on NDG by a third party based on infringement of proprietary rights, Customer shall, to the extent that such claim "
    "arises solely from Customer’s specifications or instructions, indemnify NDG against such claims, subject to the limits in Article 9.9.")
A_GOOD["Article 13.1"] = (
    "This Agreement shall come into force upon signature by both parties and shall end after five years. It shall automatically be extended "
    "for a further five years without any further consent of NDG, unless Customer gives notice of non-renewal or Customer is in material breach "
    "of this Agreement which has not been cured within [●] days after NDG's written notice specifying the breach.")
A_GOOD["Article 4.1"] = A_ORIG["Article 4.1"].replace(
    "is due until the end of the contract period.",
    "is due until the end of the contract period, provided that it shall also be due for Design Products sold during the periods under "
    "clause 13.4 (a) and (b). No reimbursement shall be payable for warranty repairs, replacement parts supplied free of charge or the storage of spare parts.")
A_GOOD["Article 13.3"] = A_ORIG["Article 13.3"].replace("As from the termination", "Subject to clause 13.4, as from the termination")
A_GOOD["Article 13.4"] = (
    "The following applies after expiration or termination of this Agreement for any reason, including termination for cause: "
    "(a) Order Fulfillment: Customer may manufacture and deliver Design Products under purchase orders accepted before the termination date "
    "within [●] months and may use the Design and the reference 'Design by Studio F. A. Norden' to that extent, subject to the restriction for "
    "Mainland China in Article 6.6; such sales shall be reported to NDG. (b) Sell-off: Customer may sell off its inventory for [●] months, "
    "may use the Design and the reference 'Design by Studio F. A. Norden' subject to Article 6.6 and shall report the quantities sold. "
    "(c) After-sales service: Customer may store and supply spare parts and perform warranty repairs for Design Products sold before or during "
    "the periods under (a) and (b), and may use the Design for that purpose until the expiry of the warranty period applicable to the last "
    "product sold.")

A_REQ = ("5. 제13.1조: 계약 위반이 없는 한 연장되는 형태로 보완 필요. 6. 제13.3조: wind-down. 3. 제6.6조: 노르덴 측이 이메일로 확인해 준 "
         "\"SIDIZ와 Studio F. A. Norden 간 협업에 관한 일반적인 기업 커뮤니케이션은 허용된다\"는 취지 — 법무팀 제안 문구: "
         "\"For the avoidance of doubt, this restriction shall not prevent SIDIZ from making general corporate communications regarding the cooperation.\"")
A_ANS = "연장: 자동연장이 필요합니다."


class LiabilityStructureTest(unittest.TestCase):
    def test_original_catch_all_makes_us_liable_for_counterparty_fault(self) -> None:
        t = liability_table(A_ORIG, P)["table"]
        self.assertEqual(t["Article 9.9"]["their_negligence"], LIABLE)   # NDG 일반 과실에도 우리가 면책
        self.assertEqual(t["Article 10.1"]["our_spec"], LIABLE)           # 조건절('complying with Customer's standards')도 원인

    def test_bad_revision_conflict_between_indemnity_and_ip_clause(self) -> None:
        res = evaluate(original=A_ORIG, revised=A_BAD, parties=P)
        conf = [p for p in res["problems"] if p["code"] == "LIABILITY_CONFLICT"]
        self.assertTrue(conf and conf[0]["scenario"] == "our_spec", res["problems"])
        self.assertIn("CAP_BASIS", codes(res))
        self.assertIn("CAP_COSTS", codes(res))

    def test_good_revision_situations(self) -> None:
        res = evaluate(original=A_ORIG, revised=A_GOOD, parties=P, request_text=A_REQ, answers_text=A_ANS)
        t = liability_table(A_GOOD, P)["table"]
        # NDG 일반 과실 → 우리 책임 없음, 우리 사양 → 10.1 로 책임(9.9 는 범위 밖), 우리 과실 → 책임
        self.assertEqual(t["Article 9.9"]["their_negligence"], NOT_LIABLE)
        self.assertEqual(t["Article 9.9"]["their_design"], NOT_LIABLE)
        self.assertEqual(t["Article 10.1"]["our_spec"], LIABLE)
        self.assertIn(t["Article 9.9"]["our_spec"], (OUT_OF_SCOPE,))
        self.assertEqual(t["Article 9.9"]["our_negligence"], LIABLE)
        self.assertFalse({"LIABILITY_CONFLICT", "CAP_BASIS", "CAP_COSTS", "CAP_PERSONS"} & codes(res), res["problems"])

    def test_direction_reversed_by_exception_is_blocked(self) -> None:
        rev = dict(A_ORIG)
        rev["Article 9.9"] = ("Customer shall indemnify NDG against all third party claims, except to the extent caused by Customer’s negligence.")
        res = evaluate(original=A_ORIG, revised=rev, parties=P,
                       descriptions={"Article 9.9": "면책 범위를 우리 귀책 있는 손해로 한정하고 NDG 귀책 손해는 제외한다."})
        mism = [p for p in res["problems"] if p["code"] == "DIRECTION_MISMATCH"]
        self.assertTrue(mism, res["problems"])
        self.assertEqual(mism[0]["severity"], "block")


class RenewalTest(unittest.TestCase):
    def test_consent_based_extension_is_not_reflected(self) -> None:
        rev = dict(A_ORIG)
        rev["Article 13.1"] = A_ORIG["Article 13.1"].replace(
            "subject to the consent of both Parties.", "subject to the consent of both Parties, such consent not to be unreasonably withheld.")
        res = evaluate(original=A_ORIG, revised=rev, parties=P, request_text=A_REQ, answers_text=A_ANS)
        self.assertIn("RENEWAL_CONSENT", codes(res))
        self.assertTrue(res["renewal"]["after_outcome"].startswith("상대방 동의"))

    def test_option_without_automatic_when_user_wanted_automatic(self) -> None:
        res = evaluate(original=A_ORIG, revised=A_BAD, parties=P, request_text=A_REQ, answers_text=A_ANS)
        self.assertIn("RENEWAL_NOT_AUTOMATIC", codes(res))
        self.assertIn("RENEWAL_FURTHER_CONSENT", codes(res))

    def test_good_extension(self) -> None:
        res = evaluate(original=A_ORIG, revised=A_GOOD, parties=P, request_text=A_REQ, answers_text=A_ANS)
        self.assertEqual(res["renewal"]["after_outcome"], "자동 연장(상대방 동의 불필요)")
        self.assertFalse({c for c in codes(res) if c.startswith("RENEWAL")}, res["problems"])


class WindDownTest(unittest.TestCase):
    def test_bad_wind_down_problems(self) -> None:
        res = evaluate(original=A_ORIG, revised=A_BAD, parties=P)
        c = codes(res)
        self.assertIn("ROYALTY_NONSALE", c)            # 4.1 에 'parts supplied' — 무상 A/S 부품에 로열티
        self.assertIn("ROYALTY_NONSALE_UNSTATED", c)
        self.assertIn("WD_SERVICE_SCOPE", c)           # 종료 후 판매분 A/S 누락
        self.assertIn("WD_SERVICE_CAP", c)             # 보증보다 짧을 수 있는 고정 상한
        self.assertIn("WD_RESTRICTION", c)             # 중국 표시 제한 누락

    def test_good_wind_down_passes(self) -> None:
        res = evaluate(original=A_ORIG, revised=A_GOOD, parties=P)
        self.assertFalse({x for x in codes(res) if x.startswith(("WD_", "ROYALTY"))}, res["problems"])
        acts = {a["activity"]: a for a in res["wind_down"]["activities"]}
        self.assertTrue(all(a["license"] and a["period"] for a in acts.values()), acts)


class AgreementRecordTest(unittest.TestCase):
    def test_email_agreement_tracked_against_original_and_revision(self) -> None:
        recs = agreement_records(A_REQ, A_ANS, " ".join(A_ORIG.values()),
                                 " ".join(A_ORIG.values()) + " For the avoidance of doubt, this restriction shall not prevent Customer from "
                                 "making general corporate communications regarding the cooperation.", parties=P)
        email = [r for r in recs if r["source"] == "이메일"]
        self.assertTrue(email, recs)
        self.assertEqual(email[0]["in_original"], "미반영")
        self.assertEqual(email[0]["in_revision"], "반영")
        # 계약 문구를 인용한 것("동의(subject to …)로만 규정")은 합의 기록이 아니다
        self.assertFalse(any("subject to the consent" in r["content"] for r in recs))


# ── B. 별도 사례: Licensor/Licensee 디자인 라이선스 ─────────────────────────────
B_ORIG = {
    "Section 1.3": "The license granted under this Agreement is limited to the Republic of Korea and Japan (the \"Territory\"). In Japan, the Licensee shall not use the name \"Nordlys Atelier Design\" on product packaging.",
    "Section 2.1": "This Agreement shall commence on the Effective Date and continue for a period of three (3) years and may be renewed for a further three (3) years upon mutual written agreement of the parties.",
    "Section 2.4": "Upon termination or expiration of this Agreement: (a) The Licensee shall immediately cease all use of the Design and Licensed Products. (b) The Licensee shall return or destroy all materials containing the Design.",
    "Section 3.2": "The Licensee shall pay the Licensor royalties equal to 5% of the net sales of the Licensed Products.",
    "Section 4.4": "In the event any claim is brought by a third party alleging that the Design infringes their intellectual property rights, the Licensor shall indemnify and hold harmless the Licensee from and against any and all damages, costs and expenses arising from such claims.",
    "Section 7.1": "The Licensee shall indemnify and hold the Licensor harmless from any claims, damages, or liabilities arising from the Licensee’s use of the Design, except to the extent caused by the Licensor’s breach of this Agreement.",
}
B_REQ = "1. 제2.1조: 메일로 협의한 대로 위반 사항이 없으면 자동 갱신되도록 해 주세요. 2. 제2.4조: 재고 판매와 A/S 가 가능해야 합니다."


class HoldoutLicenseTest(unittest.TestCase):
    def test_original_situations(self) -> None:
        t = liability_table(B_ORIG, L)["table"]
        # 우리(Licensee)는 '사용' 에서 생긴 모든 청구를 면책 — 상대방(Licensor) 디자인이 원인이어도 7.1 은 책임 있음
        self.assertEqual(t["Section 7.1"]["their_design"], LIABLE)
        res = evaluate(original=B_ORIG, revised=B_ORIG, parties=L, request_text=B_REQ)
        self.assertTrue(res["renewal"]["after_outcome"].startswith("상대방 동의"))
        self.assertIn("RENEWAL_CONSENT", codes(res))

    def test_bad_revision_same_rules_fire(self) -> None:
        rev = dict(B_ORIG)
        rev["Section 2.1"] = B_ORIG["Section 2.1"].replace("upon mutual written agreement of the parties",
                                                           "upon mutual written agreement, which the Licensor shall not unreasonably withhold")
        rev["Section 2.5"] = ("Notwithstanding Section 2.4, after expiration of this Agreement the Licensee may sell off its remaining inventory "
                              "of Licensed Products for six (6) months using the name \"Nordlys Atelier Design\" and may repair Licensed Products "
                              "sold before expiration for twelve (12) months. Royalties under Section 3.2 shall apply to all Licensed Products sold "
                              "and to all repairs performed during such periods.")
        res = evaluate(original=B_ORIG, revised=rev, parties=L, request_text=B_REQ)
        c = codes(res)
        self.assertIn("RENEWAL_CONSENT", c)
        self.assertIn("ROYALTY_NONSALE", c)        # 수리에 로열티
        self.assertIn("WD_SERVICE_SCOPE", c)       # 종료 후 판매분 A/S 누락
        self.assertIn("WD_RESTRICTION", c)         # 일본 포장 표시 제한 누락
        self.assertIn("WD_SCOPE", c)               # 중도해지 적용 범위 없음

    def test_good_revision_passes(self) -> None:
        rev = dict(B_ORIG)
        rev["Section 2.1"] = ("This Agreement shall commence on the Effective Date and continue for a period of three (3) years and shall "
                              "automatically be renewed for a further three (3) years without any further consent of the Licensor, unless the "
                              "Licensee is in material breach which remains uncured thirty (30) days after the Licensor's written notice.")
        rev["Section 2.4"] = "Subject to Section 2.5, upon termination or expiration of this Agreement: (a) The Licensee shall immediately cease all use of the Design and Licensed Products."
        rev["Section 2.5"] = ("After expiration or termination of this Agreement for any reason: (a) the Licensee may sell off its inventory for "
                              "six (6) months and may use the Design and the name \"Nordlys Atelier Design\" for that purpose, subject to the "
                              "restriction for Japan in Section 1.3, and shall report such sales; (b) the Licensee may perform warranty repairs and "
                              "supply spare parts for Licensed Products sold before or during the sell-off period and may use the Design for that "
                              "purpose until the expiry of the warranty period. No royalty shall be payable for warranty repairs or spare parts "
                              "supplied free of charge; royalties apply only to Licensed Products sold.")
        res = evaluate(original=B_ORIG, revised=rev, parties=L, request_text=B_REQ)
        self.assertFalse({x for x in codes(res) if x.startswith(("WD_", "ROYALTY", "RENEWAL"))}, res["problems"])
        self.assertEqual(res["renewal"]["after_outcome"], "자동 연장(상대방 동의 불필요)")


K = Parties(ours=["을"], theirs=["갑"])
K_ORIG = {
    "제3조": "본 계약의 기간은 체결일로부터 2년으로 하며, 갑과 을의 쌍방 합의로 1년씩 연장할 수 있다.",
    "제7조": "을은 제품과 관련하여 발생한 모든 제3자 청구에 대하여 갑을 면책하고 그 손해를 배상한다.",
    "제12조": "계약이 종료되면 을은 즉시 갑의 상표 사용과 제품의 생산·판매를 중단하여야 한다.",
}
K_REQ = "1. 제3조: 메일로 협의한 대로 계약 위반이 없으면 자동 연장되도록 해 주세요."


class KoreanContractTest(unittest.TestCase):
    def test_korean_rules(self) -> None:
        t = liability_table(K_ORIG, K)["table"]
        self.assertEqual(t["제7조"]["their_negligence"], LIABLE)   # '모든 제3자 청구' — 갑 과실에도 을이 배상
        res = evaluate(original=K_ORIG, revised=K_ORIG, parties=K, request_text=K_REQ)
        self.assertIn("RENEWAL_CONSENT", codes(res))
        rev = dict(K_ORIG)
        rev["제3조"] = ("본 계약의 기간은 체결일로부터 2년으로 하며, 을에게 중대한 위반이 있고 갑의 서면 시정 요구 후 30일 내에 시정되지 "
                       "않은 경우가 아니면 별도의 동의 없이 동일한 조건으로 1년씩 자동 연장된다.")
        rev["제7조"] = ("을은 을의 고의 또는 과실로 제3자에게 발생한 손해에 한하여 책임을 진다. 다만 갑의 귀책사유로 인한 손해에 대하여는 을은 책임을 지지 아니한다.")
        res2 = evaluate(original=K_ORIG, revised=rev, parties=K, request_text=K_REQ)
        t2 = liability_table(rev, K)["table"]
        self.assertEqual(t2["제7조"]["their_negligence"], NOT_LIABLE)
        self.assertEqual(t2["제7조"]["our_negligence"], LIABLE)
        self.assertEqual(res2["renewal"]["after_outcome"], "자동 연장(상대방 동의 불필요)")
        self.assertFalse({c for c in codes(res2) if c.startswith("RENEWAL")}, res2["problems"])


if __name__ == "__main__":
    unittest.main()
