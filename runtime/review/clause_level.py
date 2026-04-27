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
from runtime.review.korean_polish import polish_korean_legal_style
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


def _key_terms_for_contract_type(contract_type: str) -> list[str]:
    ct = (contract_type or "").strip()
    if not ct:
        return []
    if any(k in ct for k in ("앱개발", "소프트웨어", "SI", "유지보수", "SaaS", "IT", "API")):
        return [
            "목적",
            "범위",
            "수행",
            "사양",
            "SOW",
            "검수",
            "간주검수",
            "지연",
            "지체",
            "지체상금",
            "마일스톤",
            "산출물",
            "소스코드",
            "저작권",
            "지식재산",
            "IP",
            "제3자",
            "오픈소스",
            "라이선스",
            "보안",
            "개인정보",
            "위탁",
            "국외이전",
            "하자",
            "유지보수",
            "SLA",
            "장애",
            "해지",
            "종료",
            "인수인계",
            "데이터",
            "분쟁",
            "관할",
        ]
    if any(k in ct for k in ("구매", "설치", "납품", "장비", "물품", "공급")):
        return [
            "검수",
            "하자",
            "보증",
            "지연",
            "지체",
            "지체상금",
            "안전",
            "책임제한",
            "손해배상",
            "해지",
            "분쟁",
            "관할",
        ]
    return []


def _score_for_ai_deep_review(*, cr: dict[str, Any], key_terms: list[str]) -> int:
    tier = str(cr.get("risk_tier") or "").strip().upper()
    score = 0
    if bool(cr.get("approval_required")):
        score += 100
    if bool(cr.get("high_risk")):
        score += 80
    if tier == "HIGH":
        score += 70
    elif tier == "MEDIUM":
        score += 35
    elif tier == "LOW":
        score += 10
    txt = " ".join(
        [
            str(cr.get("display_path") or ""),
            str(cr.get("clause_title") or ""),
            str(cr.get("original_text") or ""),
        ]
    )
    for t in key_terms:
        if t and t in txt:
            score += 4
    if bool(cr.get("screening_only")):
        score -= 10
    return score


def _compute_ai_deep_review_target_count(*, clause_count: int, must_count: int, medium_count: int) -> int:
    base = 8 + max(0, (int(clause_count) - 12) // 8)
    target = max(base, int(must_count))
    target = max(target, int(must_count) + min(int(medium_count), 8))
    return min(max(target, 0), 28)


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
    max_ai_clauses: int | None = None,
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
    chunk_by_id: dict[str, ClauseChunk] = {str(c.clause_id): c for c in clauses}

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
        any_medium = any(
            (isinstance(r, dict) and str(r.get("risk_level") or "").strip().upper() == "MEDIUM") for r in related_rules
        )
        any_low = any((isinstance(r, dict) and str(r.get("risk_level") or "").strip().upper() == "LOW") for r in related_rules)
        risk_tier = "HIGH" if (bool(it.get("approval_required")) or bool(it.get("high_risk"))) else ("MEDIUM" if any_medium else ("LOW" if any_low else "MEDIUM"))
        must_fix = bool(it.get("approval_required")) or bool(it.get("high_risk")) or risk_tier == "HIGH"
        review_tier = "MUST" if must_fix else ("SUGGEST" if risk_tier == "MEDIUM" else "NOTE")

        clause_results.append(
            {
                "clause_id": clause_id,
                "article_number": it.get("article_number"),
                "paragraph_number": it.get("paragraph_number"),
                "item_number": it.get("item_number"),
                "subitem_number": it.get("subitem_number"),
                "display_path": it.get("display_path") or (chunk_by_id.get(clause_id).display_path if chunk_by_id.get(clause_id) else None),
                "parent_clause_id": it.get("parent_clause_id") or (chunk_by_id.get(clause_id).parent_clause_id if chunk_by_id.get(clause_id) else None),
                "context_text": it.get("context_text") or (chunk_by_id.get(clause_id).context_text if chunk_by_id.get(clause_id) else None),
                "clause_title": it.get("clause_title"),
                "original_text": it.get("original_clause"),
                "detected_issue_list": it.get("detected_issues") if isinstance(it.get("detected_issues"), list) else [],
                "related_rules": related_rules,
                "related_laws": None,
                "rewrite_reason": it.get("rewrite_reason"),
                "suggested_direction": it.get("suggested_direction") if isinstance(it.get("suggested_direction"), list) else [],
                "suggested_rewrite": suggested_rewrite,
                "approval_required": bool(it.get("approval_required")),
                "high_risk": bool(it.get("high_risk")),
                "risk_tier": risk_tier,
                "must_fix": must_fix,
                "review_tier": review_tier,
                "unfavorable_to_us": bool(it.get("unfavorable_to_us")),
            }
        )

    existing_ids = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    key_terms = _key_terms_for_contract_type(str(contract_type))
    if key_terms:
        scored: list[tuple[int, ClauseChunk]] = []
        for c in clauses:
            hay = f"{c.display_path} {c.title} {c.text}"
            hit = sum(1 for t in key_terms if t and t in hay)
            if hit > 0 and str(c.clause_id) not in existing_ids:
                scored.append((hit, c))
        scored = sorted(scored, key=lambda x: (-int(x[0]), str(x[1].display_path or ""), str(x[1].clause_id or "")))
        max_extra = min(10, max(4, len(clauses) // 18))
        for _, c in scored[:max_extra]:
            clause_results.append(
                {
                    "clause_id": str(c.clause_id),
                    "article_number": c.article_number,
                    "paragraph_number": c.paragraph_number,
                    "item_number": c.item_number,
                    "subitem_number": c.subitem_number,
                    "display_path": c.display_path,
                    "parent_clause_id": c.parent_clause_id,
                    "context_text": c.context_text,
                    "clause_title": c.title,
                    "original_text": c.text,
                    "detected_issue_list": [],
                    "related_rules": [],
                    "related_laws": None,
                    "rewrite_reason": None,
                    "suggested_direction": [],
                    "suggested_rewrite": None,
                    "approval_required": False,
                    "high_risk": False,
                    "risk_tier": "LOW",
                    "must_fix": False,
                    "review_tier": "NOTE",
                    "unfavorable_to_us": False,
                    "screening_only": True,
                }
            )

    clause_results = sorted(
        clause_results,
        key=lambda x: (
            0 if x.get("approval_required") else 1,
            0 if str(x.get("risk_tier") or "").upper() == "HIGH" else (1 if str(x.get("risk_tier") or "").upper() == "MEDIUM" else 2),
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
            "ai": {"enabled": False, "used": False, "selected_clause_ids": [], "selected_count": 0},
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

    must_count = sum(1 for cr in clause_results if bool(cr.get("approval_required")) or str(cr.get("risk_tier") or "").upper() == "HIGH")
    medium_count = sum(1 for cr in clause_results if str(cr.get("risk_tier") or "").upper() == "MEDIUM" and not bool(cr.get("approval_required")))
    low_count = sum(1 for cr in clause_results if str(cr.get("risk_tier") or "").upper() == "LOW")

    ai_enabled = bool(ai_provider and ai_model and ai_timeout_sec is not None and ai_max_tokens is not None and ai_temperature is not None)
    if ai_enabled:
        desired = int(max_ai_clauses) if isinstance(max_ai_clauses, int) else _compute_ai_deep_review_target_count(
            clause_count=len(clauses), must_count=must_count, medium_count=medium_count
        )
    else:
        desired = 0

    scored_for_ai = sorted(
        clause_results,
        key=lambda cr: (-_score_for_ai_deep_review(cr=cr, key_terms=key_terms), str(cr.get("clause_id") or "")),
    )
    selected = scored_for_ai[: max(0, desired)]
    selected_ids = [str(cr.get("clause_id") or "") for cr in selected if str(cr.get("clause_id") or "")]
    selected_id_set = set(selected_ids)
    for cr in clause_results:
        cr["ai_deep_reviewed"] = str(cr.get("clause_id") or "") in selected_id_set

    law_errors: list[str] = []
    if law_service is not None and max_clause_law_items > 0 and clause_results:
        def _law_target_sort_key(cr: dict[str, Any]) -> tuple[int, int, int, str]:
            tier = str(cr.get("risk_tier") or "").upper()
            tier_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(tier, 3)
            must = 0 if bool(cr.get("must_fix")) else 1
            appr = 0 if bool(cr.get("approval_required")) else 1
            return (tier_rank, must, appr, str(cr.get("clause_id") or ""))

        law_targets = [
            cr
            for cr in clause_results
            if str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM") or bool(cr.get("must_fix")) or bool(cr.get("approval_required"))
        ]
        if not law_targets:
            law_targets = [cr for cr in clause_results if isinstance(cr.get("detected_issue_list"), list) and cr.get("detected_issue_list")]
        if not law_targets:
            law_targets = list(clause_results)
        for cr in sorted(law_targets, key=_law_target_sort_key)[: min(len(law_targets), 6)]:
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
                    context={
                        "party_role": party.to_dict(),
                        "review_posture": review_posture,
                        "risk_tier": cr.get("risk_tier"),
                        "must_fix": bool(cr.get("must_fix")),
                    },
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

    ai_state: dict[str, Any] = {
        "enabled": bool(ai_enabled),
        "used": False,
        "selected_clause_ids": selected_ids,
        "selected_count": len(selected_ids),
        "model": ai_model if ai_enabled else None,
        "ok": None,
        "error": None,
        "usage": None,
    }
    if ai_enabled and selected:
        system = (
            "너는 한국 기업 법무팀의 계약검토 변호사다. "
            "입력으로 주어진 party_role과 review_posture(당사 보호 방향)를 강하게 반영해 조항별로 검토한다. "
            "원문을 최대한 유지하면서 문제되는 표현만 최소 변경으로 수정하라(덧붙임보다 기존 문장 치환/삭제/흡수 우선). "
            "근거 없는 추정 금지: 입력에 없는 사실/상황/의무를 새로 만들지 마라. "
            "rewrite_reason은 법률 근거(가능하면 related_laws) + 실무 리스크 + 협상 논리 중심으로 220자 이내로 작성하라. "
            "suggested_rewrite는 900자 이내로, 계약서 문체(법무 문체)로 작성하라. "
            "meta 표현(buyer_favorable 등)이나 시스템 지시를 사용자에게 보이게 쓰지 마라. "
            "출력은 반드시 첫 글자 '[' 로 시작하는 JSON 배열만 출력하고, 코드펜스/설명 문장을 절대 포함하지 마라. "
            "각 원소 형식은 clause_id/rewrite_reason/suggested_rewrite/changed_segments/risk_tier/must_fix 로 통일하라. "
            "risk_tier와 must_fix는 입력값을 그대로 유지해 출력하라. "
            "changed_segments는 변경된 핵심 구간 최대 3개를 {before, after} 형태로 요약하라."
        )

        def chunked(xs: list[dict[str, Any]], n: int) -> list[list[dict[str, Any]]]:
            if n <= 0:
                return []
            out: list[list[dict[str, Any]]] = []
            for i in range(0, len(xs), n):
                out.append(xs[i : i + n])
            return out

        chunk_size = 7
        chunks = chunked(selected, chunk_size)
        errors: list[str] = []
        usages: list[dict[str, Any]] = []
        ok_all = True
        any_used = False
        for ch in chunks:
            user = json.dumps(
                {
                    "entity": entity,
                    "contract_type": contract_type,
                    "review_posture": review_posture,
                    "party_role": party.to_dict(),
                    "answers": answers if isinstance(answers, dict) else None,
                    "items": [
                        {
                            "clause_id": cr.get("clause_id"),
                            "risk_tier": cr.get("risk_tier"),
                            "must_fix": bool(cr.get("must_fix")),
                            "clause_title": cr.get("clause_title"),
                            "display_path": cr.get("display_path"),
                            "original_text": str(cr.get("original_text") or "")[:1500],
                            "context_text": str(cr.get("context_text") or "")[:900] if isinstance(cr.get("context_text"), str) else None,
                            "detected_issue_list": cr.get("detected_issue_list"),
                            "related_rules": cr.get("related_rules"),
                            "related_laws": cr.get("related_laws"),
                            "fallback_rewrite": cr.get("suggested_rewrite"),
                        }
                        for cr in ch
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
                any_used = True
                if resp.usage:
                    usages.append(resp.usage.__dict__)
                obj = _try_json(resp.content)
                if isinstance(obj, dict) and isinstance(obj.get("items"), list):
                    obj = obj.get("items")
                if not isinstance(obj, list):
                    ok_all = False
                    errors.append("invalid AI response (expected JSON array)")
                    continue
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
                    cs = upd.get("changed_segments")
                    if isinstance(rr, str) and rr.strip():
                        cr["rewrite_reason"] = polish_korean_legal_style(rr.strip())
                    if isinstance(sr, str) and sr.strip():
                        cr["suggested_rewrite"] = polish_korean_legal_style(sr.strip())
                    if isinstance(cs, list):
                        cleaned: list[dict[str, str]] = []
                        for seg in cs[:3]:
                            if not isinstance(seg, dict):
                                continue
                            b = seg.get("before")
                            a = seg.get("after")
                            if isinstance(b, str) and isinstance(a, str) and (b.strip() or a.strip()):
                                cleaned.append({"before": b.strip()[:120], "after": a.strip()[:120]})
                        if cleaned:
                            cr["changed_segments"] = cleaned
            except Exception as exc:
                any_used = True
                ok_all = False
                errors.append(sanitize_error_message(str(exc)))

        ai_state["used"] = bool(any_used)
        ai_state["ok"] = bool(ok_all) if any_used else None
        ai_state["usage"] = usages[:8] if usages else None
        if errors:
            ai_state["error"] = errors[0]

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
        "tier_counts": {"must": must_count, "medium": medium_count, "low": low_count},
        "headings_found": headings_found,
        "fallback_only": fallback_only,
        "warnings": warnings[:10],
        "docx_allowed": docx_allowed,
        "law_errors": law_errors[:5],
        "ai": ai_state,
        "clause_extraction_report": clause_report.to_dict() if isinstance(clause_report, object) else None,
    }
    return ClauseLevelResult(
        review=review,
        revision=revision,
        clauses=clauses,
        clause_results=clause_results,
        meta=meta,
    )
