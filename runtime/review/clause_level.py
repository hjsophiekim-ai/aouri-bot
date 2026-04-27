from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from runtime.ai.enhance import _try_json
from runtime.ai.http_openai_compatible_provider import build_messages
from runtime.ai.provider import AIProvider, AIRequest
from runtime.ai.safe import sanitize_error_message
from runtime.law.search_service import LawSearchService
from runtime.review.clause_extraction import ClauseChunk, extract_clauses
from runtime.review.party_role import infer_party_role, infer_review_posture
from runtime.review.revision import suggest_revisions
from runtime.review.word_markers import contains_wordprocessingml_markers
from runtime.services.query_service import ReviewInput, RuleQueryService


@dataclass(frozen=True)
class ClauseLevelResult:
    review: dict[str, Any]
    revision: dict[str, Any]
    clauses: list[ClauseChunk]
    clause_results: list[dict[str, Any]]
    meta: dict[str, Any]


def _contains_wordprocessingml_markers(text: str) -> bool:
    return contains_wordprocessingml_markers(text)


def build_clause_level_result(
    *,
    service: RuleQueryService,
    entity: str,
    contract_type: str,
    text: str,
    filename: str | None,
    answers: dict[str, Any] | None,
    law_service: LawSearchService | None,
    ai_provider: AIProvider | None,
    ai_model: str | None,
    ai_timeout_sec: float | None,
    ai_max_tokens: int | None,
    ai_temperature: float | None,
    max_clause_law_items: int = 2,
    max_ai_clauses: int = 6,
) -> ClauseLevelResult:
    if _contains_wordprocessingml_markers(text):
        meta = {
            "review_posture": "neutral",
            "text_length": len(text or ""),
            "text_sha256": sha256((text or "").encode("utf-8", errors="replace")).hexdigest() if text else None,
            "clause_count": 0,
            "issue_clause_count": 0,
            "headings_found": False,
            "fallback_only": False,
            "warnings": ["word_xml_markers_detected_block"],
            "docx_allowed": False,
            "law_errors": [],
            "ai": None,
        }
        return ClauseLevelResult(
            review={"summary": {"error": "WordprocessingML markers detected in contract text"}, "matched_rules": []},
            revision={"summary": {"issue_clause_count": 0}, "items": []},
            clauses=[],
            clause_results=[],
            meta=meta,
        )

    party = infer_party_role(contract_type=str(contract_type), text=str(text), answers=answers)
    review_posture = infer_review_posture(party=party, contract_type=str(contract_type), text=str(text))
    review = service.analyze(
        ReviewInput(
            entity=entity,
            contract_type=contract_type,
            text=text,
            filename=filename,
            answers=answers,
        )
    )
    clauses, clause_report = extract_clauses(text)
    revision = suggest_revisions(clauses, review.get("matched_rules", []), posture=review_posture, party=party)

    clause_title_by_id: dict[str, str] = {str(c.clause_id): str(c.title or "") for c in clauses}

    rule_by_id: dict[str, dict[str, Any]] = {}
    for r in review.get("matched_rules", []) if isinstance(review.get("matched_rules"), list) else []:
        if not isinstance(r, dict):
            continue
        rid = r.get("rule_id")
        if isinstance(rid, str) and rid:
            rule_by_id[rid] = r

    items = revision.get("items") if isinstance(revision.get("items"), list) else []
    clause_results: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        clause_id = str(it.get("clause_id") or "")
        applied = it.get("applied_rules") if isinstance(it.get("applied_rules"), list) else []
        related_rules: list[dict[str, Any]] = []
        for ar in applied:
            if not isinstance(ar, dict):
                continue
            rid = ar.get("rule_id")
            base = rule_by_id.get(rid) if isinstance(rid, str) else None
            if base:
                related_rules.append(
                    {
                        "rule_id": base.get("rule_id"),
                        "title": base.get("title"),
                        "rule_status": base.get("rule_status"),
                        "risk_level": base.get("risk_level"),
                        "approval_required": bool(base.get("approval_required")) or base.get("rule_status") == "approval_required",
                        "description": base.get("description"),
                        "review_action": base.get("review_action") if isinstance(base.get("review_action"), list) else [],
                        "tags": base.get("tags") if isinstance(base.get("tags"), list) else [],
                        "matched_keywords": ar.get("matched_keywords") if isinstance(ar.get("matched_keywords"), list) else [],
                    }
                )
            else:
                related_rules.append(dict(ar))

        recommended = it.get("recommended_rewrite")
        fallback_texts = it.get("fallback_text") if isinstance(it.get("fallback_text"), list) else []
        suggested_rewrite = recommended if isinstance(recommended, str) and recommended.strip() else (fallback_texts[0] if fallback_texts else None)

        clause_results.append(
            {
                "clause_id": clause_id,
                "article_number": it.get("article_number"),
                "clause_title": it.get("clause_title"),
                "original_text": it.get("original_clause"),
                "detected_issue_list": it.get("detected_issues") if isinstance(it.get("detected_issues"), list) else [],
                "related_rules": related_rules,
                "related_laws": None,
                "rewrite_reason": it.get("rewrite_reason"),
                "suggested_rewrite": suggested_rewrite,
                "approval_required": bool(it.get("approval_required")),
                "high_risk": bool(it.get("high_risk")),
                "unfavorable_to_us": bool(it.get("unfavorable_to_us")),
            }
        )

    clause_results = sorted(
        clause_results,
        key=lambda x: (
            0 if x.get("approval_required") else 1,
            0 if x.get("high_risk") else 1,
            str(x.get("clause_id") or ""),
        ),
    )
    clause_results = [cr for cr in clause_results if not _contains_wordprocessingml_markers(str(cr.get("original_text") or ""))]

    mismatches: list[dict[str, str]] = []
    for cr in clause_results:
        cid = str(cr.get("clause_id") or "")
        expected = clause_title_by_id.get(cid)
        actual = str(cr.get("clause_title") or "")
        if expected is None:
            continue
        if expected != actual:
            mismatches.append({"clause_id": cid, "expected": expected, "actual": actual})
    if mismatches:
        meta = {
            "review_posture": review_posture,
            "party_role": party.to_dict(),
            "text_length": len(text or ""),
            "text_sha256": sha256((text or "").encode("utf-8", errors="replace")).hexdigest() if text else None,
            "clause_count": len(clauses),
            "issue_clause_count": len(clause_results),
            "headings_found": any(not (c.clause_id or "").startswith("P-") for c in clauses),
            "fallback_only": bool(clauses) and all((c.clause_id or "").startswith("P-") for c in clauses),
            "warnings": ["clause_title_mismatch_block"],
            "docx_allowed": False,
            "law_errors": [],
            "ai": None,
            "clause_extraction_report": clause_report.to_dict(),
            "clause_identity_mismatches": mismatches[:10],
        }
        return ClauseLevelResult(
            review={"summary": {"error": "clause_title mismatch detected"}, "matched_rules": []},
            revision={"summary": {"issue_clause_count": 0}, "items": []},
            clauses=clauses,
            clause_results=[],
            meta=meta,
        )

    law_errors: list[str] = []
    if law_service is not None and clause_results:
        for cr in clause_results[: min(len(clause_results), 10)]:
            ctext = str(cr.get("original_text") or "")
            rr = cr.get("related_rules") if isinstance(cr.get("related_rules"), list) else []
            try:
                cr["related_laws"] = law_service.search_for_review(
                    entity=str(entity),
                    contract_type=str(contract_type),
                    text=ctext,
                    matched_rules=rr,
                    scope="clause",
                    max_per_type=max_clause_law_items,
                )
            except Exception as exc:
                law_errors.append(sanitize_error_message(str(exc)))
                cr["related_laws"] = {"enabled": False, "note": "law search failed", "error": sanitize_error_message(str(exc))}

    for cr in clause_results:
        issues = cr.get("detected_issue_list") if isinstance(cr.get("detected_issue_list"), list) else []
        rules = cr.get("related_rules") if isinstance(cr.get("related_rules"), list) else []
        law = cr.get("related_laws")
        existing_reason = cr.get("rewrite_reason")
        if isinstance(existing_reason, str) and existing_reason.strip():
            continue
        parts: list[str] = []
        if issues:
            parts.append("검출 이슈: " + ", ".join(str(x.get("issue_title") or "") for x in issues if isinstance(x, dict) and str(x.get("issue_title") or "").strip())[:6])
        if rules:
            parts.append("적용 규칙: " + ", ".join(str(x.get("rule_id") or "") for x in rules if isinstance(x, dict) and str(x.get("rule_id") or "").strip())[:8])
        if isinstance(law, dict) and isinstance(law.get("results"), dict):
            laws = []
            for k in ("laws", "precedents", "interpretations"):
                arr = law["results"].get(k)
                if isinstance(arr, list):
                    for it in arr[:2]:
                        if isinstance(it, dict) and isinstance(it.get("title"), str) and it.get("title").strip():
                            laws.append(it["title"].strip())
            if laws:
                parts.append("관련 법령/판례: " + ", ".join(laws[:6]))
        cr["rewrite_reason"] = " / ".join([p for p in parts if p]) if parts else None

    ai_meta: dict[str, Any] | None = None
    if (
        ai_provider is not None
        and ai_model
        and ai_timeout_sec is not None
        and ai_max_tokens is not None
        and ai_temperature is not None
        and clause_results
    ):
        to_rewrite = [cr for cr in clause_results if isinstance(cr.get("suggested_rewrite"), str) and str(cr.get("suggested_rewrite") or "").strip()]
        to_rewrite = to_rewrite[: max_ai_clauses]
        if to_rewrite:
            system = (
                "너는 계약서 조항별 수정문안 작성 엔진이다. "
                "판정은 이미 주어졌으며, 너는 원문/검출 이슈/관련 규칙/관련 법령·판례 정보만을 근거로 "
                "수정 이유(rewrite_reason)와 추천 수정문안(suggested_rewrite)을 작성한다. "
                "근거 없이 새로운 사실/의무/법적 결론을 추가하지 말고, 제공된 정보 밖으로 추정하지 마라. "
                "원문 조항에 이미 적절한 표현은 유지하고, 문제되는 표현만 최소 변경으로 수정하라. "
                "fallback_rewrite를 그대로 복사하거나 재진술하지 말고, 원문 문장 구조를 기반으로 실제 조항에 맞게 고쳐라. "
                "rewrite_reason은 250자 이내로, suggested_rewrite는 1200자 이내로 작성하라. "
                "출력은 JSON 배열만, 각 원소는 clause_id/rewrite_reason/suggested_rewrite만 포함하라."
            )
            user = json.dumps(
                {
                    "entity": entity,
                    "contract_type": contract_type,
                    "items": [
                        {
                            "clause_id": cr.get("clause_id"),
                            "clause_title": cr.get("clause_title"),
                            "original_text": str(cr.get("original_text") or "")[:1500],
                            "detected_issue_list": cr.get("detected_issue_list"),
                            "related_rules": cr.get("related_rules"),
                            "related_laws": cr.get("related_laws"),
                            "fallback_rewrite": cr.get("suggested_rewrite"),
                        }
                        for cr in to_rewrite
                    ],
                },
                ensure_ascii=False,
            )
            req = AIRequest(
                model=ai_model,
                messages=build_messages(system, user),
                temperature=float(ai_temperature),
                max_tokens=int(ai_max_tokens),
                timeout_sec=float(ai_timeout_sec),
            )
            try:
                resp = ai_provider.complete(req)
                obj = _try_json(resp.content)
                if isinstance(obj, dict) and isinstance(obj.get("items"), list):
                    obj = obj.get("items")
                if isinstance(obj, list):
                    by_id: dict[str, dict[str, Any]] = {}
                    for it in obj:
                        if not isinstance(it, dict):
                            continue
                        cid = it.get("clause_id")
                        if isinstance(cid, str) and cid:
                            by_id[cid] = it
                    for cr in clause_results:
                        cid = cr.get("clause_id")
                        upd = by_id.get(cid) if isinstance(cid, str) else None
                        if not upd:
                            continue
                        rr = upd.get("rewrite_reason")
                        sr = upd.get("suggested_rewrite")
                        if isinstance(rr, str) and rr.strip():
                            cr["rewrite_reason"] = rr.strip()
                        if isinstance(sr, str) and sr.strip():
                            cr["suggested_rewrite"] = sr.strip()
                    ai_meta = {"ok": True, "usage": (resp.usage.__dict__ if resp.usage else None)}
                else:
                    ai_meta = {"error": "invalid AI response (expected JSON array)"}
            except Exception as exc:
                ai_meta = {"error": sanitize_error_message(str(exc))}

    text_len = len(text or "")
    clause_count = len(clauses)
    headings_found = any(not (c.clause_id or "").startswith("P-") for c in clauses)
    fallback_only = bool(clauses) and all((c.clause_id or "").startswith("P-") for c in clauses)
    has_word_xml = any(_contains_wordprocessingml_markers(c.text) for c in clauses)
    warnings: list[str] = []
    if text_len < 250:
        warnings.append("contract_text_too_short_warning")
    if clause_count < 2:
        warnings.append("clause_count_too_low_warning")
    if fallback_only and clause_count >= 2:
        warnings.append("clause_extraction_fallback_warning")
    if clause_count == 0:
        warnings.append("clause_extraction_failed")
    if has_word_xml:
        warnings.append("word_xml_markers_detected_warning")

    docx_allowed = True
    if text_len < 120:
        docx_allowed = False
        warnings.append("contract_text_too_short_block")
    if clause_count < 1:
        docx_allowed = False
        warnings.append("no_clauses_block")
    if clause_count < 2 and text_len < 800:
        docx_allowed = False
        warnings.append("insufficient_contract_structure_block")
    if (not headings_found) and clause_count <= 2 and text_len < 600:
        docx_allowed = False
        warnings.append("summary_like_text_block")
    if has_word_xml:
        docx_allowed = False
        warnings.append("word_xml_markers_detected_block")

    meta = {
        "review_posture": review_posture,
        "party_role": party.to_dict(),
        "text_length": text_len,
        "text_sha256": sha256((text or "").encode("utf-8", errors="replace")).hexdigest() if text else None,
        "clause_count": clause_count,
        "issue_clause_count": len(clause_results),
        "headings_found": headings_found,
        "fallback_only": fallback_only,
        "warnings": warnings[:10],
        "docx_allowed": docx_allowed,
        "law_errors": law_errors[:5],
        "ai": ai_meta,
        "clause_extraction_report": clause_report.to_dict() if isinstance(clause_report, object) else None,
    }
    return ClauseLevelResult(
        review=review,
        revision=revision,
        clauses=clauses,
        clause_results=clause_results,
        meta=meta,
    )
