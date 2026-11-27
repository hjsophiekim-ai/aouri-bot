"""필수 검증 출력 통제 e2e — 검증 미통과면 변경추적본·클린본·검토의견서(앱·다운로드)가 같은 버전·같은 판정을 싣는다(2026-11-03).

검증 결과는 meta 에 저장되고, 출력 직전에 지금 수정안의 지문과 비교한다. 다르면 이전 결과를 버리고 다시 검증한다.
"""
from __future__ import annotations

import io
import re
import zipfile

from runtime.review import verification_gate as vg
from runtime.review.deal_scenarios import Parties
from runtime.review.delivery_docs import UNVERIFIED_MARK, build_tracked_docs, finalize_review_meta

P = Parties(ours=["Customer"], theirs=["NDG"])
C_99 = "NDG shall indemnify and hold Customer harmless from all claims arising from NDG's negligence."
C_13 = "Either party may terminate this Agreement by giving six months written notice."
TEXT = f"DESIGN AGREEMENT\nArticle 9 Indemnity\n9.9 {C_99}\nArticle 13 Term\n13.1 {C_13}\n"
CLAUSES = [
    {"clause_id": "EN-9.9", "display_path": "Article 9.9", "article_number": "9", "paragraph_number": "9", "text": C_99},
    {"clause_id": "EN-13.1", "display_path": "Article 13.1", "article_number": "13", "paragraph_number": "1", "text": C_13},
]
ROLE_SWAP = "Customer shall indemnify and hold NDG harmless from all claims arising from NDG's negligence."
GOOD = "NDG shall indemnify and hold Customer harmless from all claims, including reasonable legal fees, arising from NDG's negligence."


def _cr(repl: str) -> dict:
    return {"clause_id": "rq1_1_EN-9.9", "finding_id": "rq1", "display_path": "Article 9.9", "has_rewrite_change": True,
            "risk_tier": "HIGH", "original_text": C_99, "is_requested_clause_review": True, "issue_title": "제3자 청구 배상",
            "brief_action": "상대방 책임을 명시: NDG 귀책 손해는 NDG가 배상", "rewrite_reason": "NDG 귀책 손해는 NDG 부담",
            "suggested_rewrite": repl, "review_category": "필수수정",
            "redline_instruction": {"edit_type": "replace", "target_text": C_99, "replacement_text": repl, "final_clause_text": repl,
                                    "edit_location": "Article 9.9"}}


def _session(repl: str, *, remove: bool):
    crs = [_cr(repl)]
    res = vg.run_verification_gate(clause_results=crs, clauses=CLAUSES, parties=P, contract_text=TEXT, provider=None,
                                   remove_on_fail=remove)
    meta = {"verification_gate": vg.compact(res), "deal_scenarios": res["scenario_result"]}
    rr = {"clause_results": crs, "original_clauses": CLAUSES, "clause_meta": meta}
    session = {"text": TEXT, "input": {"filename": "agreement.txt"}, "review_result": rr}
    return session, rr, meta


def _docx_text(b: bytes) -> str:
    x = zipfile.ZipFile(io.BytesIO(b)).read("word/document.xml").decode("utf-8")
    x = re.sub(r"<w:delText[^>]*>.*?</w:delText>", "", x)
    return re.sub(r"<[^>]+>", "", x)


def test_failed_verification_restricts_every_output():
    session, rr, meta = _session(ROLE_SWAP, remove=False)
    assert meta["verification_gate"]["status"] == vg.STATUS_FAIL
    finalize_review_meta(session, rr)
    brief = meta["business_brief"]
    # 2026-11-27 지시: 검증 미통과는 결론(계약 리스크 판단)을 바꾸지 않는다 — 전달본을 사업팀에 내보내지 않고(전달 보류)
    # 법무에게만 미해결 사항을 알린다. 전달본 본문에는 도구 상태 문구를 싣지 않는다.
    assert not brief["verdict"].startswith(UNVERIFIED_MARK)
    assert brief["verification"]["failed"] and brief["verification"]["unresolved"]
    assert brief["delivery_blocked"] and any("필수 검증 미해결" in r for r in brief["delivery_block_reasons"])
    assert meta["business_brief_delivery"]["blocked"]
    flat = " ".join(r[1] for _h, rows in meta["business_brief_sections"] for r in rows)
    assert UNVERIFIED_MARK not in flat and "⚠ 미해결" not in flat
    assert not vg.RX_INTERNAL.search(flat), vg.RX_INTERNAL.findall(flat)
    docs = build_tracked_docs(session, rr)
    assert UNVERIFIED_MARK in _docx_text(docs["clean"]) and UNVERIFIED_MARK in _docx_text(docs["redline"])
    assert docs["change_set"]["verification"]["status"] == vg.STATUS_FAIL
    oc = meta["output_consistency"]
    assert oc["ok"], [c for c in oc["checks"] if not c["ok"]]


def test_removed_edit_never_reaches_tracked_or_clean_and_brief_shows_it():
    session, rr, meta = _session(ROLE_SWAP, remove=True)
    assert meta["verification_gate"]["status"] != vg.STATUS_FAIL
    finalize_review_meta(session, rr)
    docs = build_tracked_docs(session, rr)
    clean = _docx_text(docs["clean"])
    assert "Customer shall indemnify and hold NDG harmless" not in clean and C_99[:40] in clean
    assert UNVERIFIED_MARK not in clean
    flat = " ".join(r[1] for _h, rows in meta["business_brief_sections"] for r in rows)
    # 2026-11-27 지시: 검증 단계가 수정안을 뺀 기록은 도구 상태 — 법무 내부 기록(verification)에만, 전달본 본문에는 싣지 않는다
    assert "수정안을 빼고 원문을 유지함" not in flat
    assert meta["business_brief"]["verification"].get("removed")
    assert "Customer shall indemnify and hold NDG harmless" not in flat
    assert meta["output_consistency"]["ok"], meta["output_consistency"]


def test_passed_verification_has_no_unverified_mark():
    session, rr, meta = _session(GOOD, remove=True)
    assert meta["verification_gate"]["status"] == vg.STATUS_PASS
    finalize_review_meta(session, rr)
    docs = build_tracked_docs(session, rr)
    assert UNVERIFIED_MARK not in _docx_text(docs["clean"])
    assert not meta["business_brief"]["verdict"].startswith(UNVERIFIED_MARK)
    assert "legal fees" in _docx_text(docs["clean"])
    assert meta["output_consistency"]["ok"]


def test_edit_changed_after_verification_is_reverified_before_output():
    session, rr, meta = _session(GOOD, remove=True)
    assert meta["verification_gate"]["status"] == vg.STATUS_PASS
    old = meta["verification_gate"]["version"]
    # 검증 뒤 수정안이 바뀜(예: 화면 편집·후속 단계) — 출력은 이전 '통과' 를 쓰면 안 된다
    cr = rr["clause_results"][0]
    cr["suggested_rewrite"] = ROLE_SWAP
    cr["redline_instruction"].update(replacement_text=ROLE_SWAP, final_clause_text=ROLE_SWAP)
    docs = build_tracked_docs(session, rr)
    assert meta["verification_gate"]["version"] != old
    assert meta["verification_gate"]["status"] == vg.STATUS_FAIL
    assert UNVERIFIED_MARK in _docx_text(docs["clean"])
    assert "이전 검증 폐기" in meta["verification_gate"]["history"][-1]["step"]
