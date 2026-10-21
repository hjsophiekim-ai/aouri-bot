"""현재 파일만이 근거다 — Cross-Case 오염 차단 · 키워드 grounding · 별첨 역할 정정 (2026-10-13 긴급 보정 2·3·9·11·12항).

실측(일룸 ↔ ㈜아트앤라이프 물품공급계약 + 프랜차이즈 별첨)
──────────────────────────────────────────────────
최종 보고서에 "광고기간·매체 위치·송출 횟수", "매체사가 송출을 즉시 중단", "제공 콘텐츠 책임" HIGH 3건이
실렸다. 계약서에는 매체사·송출·광고료·콘텐츠라는 낱말이 한 번도 없다. 직접 원인은 광고 거래모델 오분류였지만
(ad_transaction_model 에서 고쳤다), 어떤 경로로 들어왔든 **현재 문서에 없는 거래 개념을 말하는 finding 은
출력되면 안 된다** — 이 모듈은 출력 직전의 마지막 그물이다.

    1. 거래유형 표지어(광고기간·매체사·송출·광고료·콘텐츠·크리에이터·포트폴리오·SNS 게시·광고 소재 등)가
       finding 에 있는데 현재 계약 원문에도, 사용자가 이번에 쓴 요청문·답변 값에도 없으면
       CROSS_CASE_STATE_CONTAMINATION 으로 그 finding 을 내보내지 않고 기록한다(다른 계약의 흔적).
       사전질문 **문구**는 근거로 치지 않는다 — 오분류된 질문("광고기간, 매체 위치…?")이 근거가 되면 안 된다.
    2. 법률 적용성·요청 답변·요약 문장도 같은 기준으로 그 문장만 걷어낸다.
    3. 별첨의 가맹본부/가맹점사업자 역할을 뒤집은 서술("㈜일룸(가맹본부)")을 바로잡는다
       (REVIEW_FAILED_PARTY_ROLE_MISMATCH 정정 기록).
    4. 별첨이 가맹사업 실질을 담으면 가맹사업법 행을 **요건별 판단**으로 대체한다 — AI 행의 "적용이 확실합니다" 를
       그대로 두지 않는다.

출력 텍스트만 고친다. 원문 필드(original_text 등)는 계약서 자체이므로 건드리지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

STATUS_CROSS_CASE = "CROSS_CASE_STATE_CONTAMINATION"
STATUS_SOURCE_NOT_FOUND = "REVIEW_FAILED_SOURCE_NOT_FOUND"
STATUS_PARTY_ROLE = "REVIEW_FAILED_PARTY_ROLE_MISMATCH"

#: 특정 거래유형에서만 쓰는 표지어 — 거래 영역별로 묶는다. 그 **영역 자체**가 현재 문서·요청에 없을 때만
#: 오염이다. 같은 영역의 계약에서 "없는 것을 넣자"(예: 콘텐츠 제작계약에 2차적저작물작성권 명시)는 정상 권고이므로
#: 표지어 하나가 원문에 없다는 이유로 지우지 않는다.
DOMAINS: dict[str, tuple[str, tuple[str, ...]]] = {
    "광고·매체 집행": (r"광고주|매체사|송출|광고물|광고료|광고\s*매체|광고\s*대행",
                    ("광고기간", "광고 기간", "매체 위치", "매체위치", "송출", "노출시간", "노출 시간", "광고료", "매체사",
                     "광고 소재", "광고소재", "광고주", "광고물", "광고 집행 명세")),
    "콘텐츠 제작": (r"콘텐츠|컨텐츠|영상물|크리에이터|인플루언서|촬영|유튜브",
                ("콘텐츠", "컨텐츠", "크리에이터", "인플루언서", "포트폴리오", "SNS 게시", "협찬", "촬영 원본")),
    "산학 연구": (r"연구비|연구책임자|연구과제|연구개발", ("연구책임자", "연구보고서", "연구비")),
    "건설 공사": (r"공사\s*도급|도급인|수급인|시공|착공|준공|기성", ("기성금", "하수급인", "착공", "준공")),
}
CONTAMINATION_TERMS: tuple[str, ...] = tuple(t for _, terms in DOMAINS.values() for t in terms)

#: 출력 문장으로 보는 필드(원문 필드 제외).
_TEXT_FIELDS: tuple[str, ...] = (
    "issue_title", "problem", "rewrite_reason", "legal_business_reason", "suggested_rewrite",
    "recommendation_text", "proposed_revision", "negotiation_position", "negotiation_strategy",
    "worst_case_scenario", "our_company_risk", "location_instruction",
)
_ORIGINAL_KEYS = frozenset({
    "original_text", "clause_text", "context_text", "text", "exact_text", "evidence", "quoted_text",
    "unchanged_segment", "original_user_text", "raw_citation", "source_text", "clause_title", "request",
})

_ANSWER_MARKER = "[사용자 확인 답변]"


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def allowed_source(*, contract_text: str, review_focus: str = "", answers: Any = None) -> str:
    """근거로 인정하는 글 — 계약 원문 + 이번 요청문 + 답변 **값**(질문 문구 제외)."""
    request = str(review_focus or "").split(_ANSWER_MARKER, 1)[0]
    vals: list[str] = []
    if isinstance(answers, dict):
        vals = [str(v) for v in answers.values() if isinstance(v, (str, int, float))]
    elif isinstance(answers, list):
        for row in answers:
            if isinstance(row, dict):
                v = row.get("answer") or row.get("value") or row.get("text")
                if isinstance(v, (str, int, float)):
                    vals.append(str(v))
    return _norm("\n".join([str(contract_text or ""), request, *vals]))


def foreign_terms(blob: str, allowed_norm: str) -> list[str]:
    """blob 이 말하는 거래 영역 중 현재 문서·요청에 **영역째로** 없는 것의 표지어."""
    body = _norm(blob)
    out: list[str] = []
    seen: set[str] = set()
    for anchors, terms in DOMAINS.values():
        if re.search(anchors.replace(r"\s*", ""), allowed_norm):
            continue
        for term in terms:
            t = _norm(term)
            if t and t in body and t not in allowed_norm and t not in seen:
                seen.add(t)
                out.append(term)
    return out


def _finding_blob(cr: dict[str, Any]) -> str:
    return "\n".join(str(cr.get(k) or "") for k in _TEXT_FIELDS)


def _strip_sentences(text: str, allowed_norm: str) -> tuple[str, list[str]]:
    """오염 표지어가 든 문장만 걷어낸다."""
    value = str(text or "")
    if not value.strip():
        return value, []
    parts = re.split(r"(?<=[.。!?])\s+|\n", value)
    kept, hit = [], []
    for p in parts:
        terms = foreign_terms(p, allowed_norm)
        if terms:
            hit.extend(t for t in terms if t not in hit)
            continue
        kept.append(p)
    if not hit:
        return value, []
    return " ".join(x for x in kept if x.strip()).strip(), hit


def scrub_value(value: Any, allowed_norm: str, hits: list[str]) -> Any:
    if isinstance(value, str):
        new, h = _strip_sentences(value, allowed_norm)
        hits.extend(t for t in h if t not in hits)
        return new
    if isinstance(value, list):
        return [scrub_value(v, allowed_norm, hits) for v in value]
    if isinstance(value, dict):
        return {k: (v if k in _ORIGINAL_KEYS else scrub_value(v, allowed_norm, hits)) for k, v in value.items()}
    return value


def _fix_roles(value: Any, roles: Any, counter: list[int]) -> Any:
    from runtime.review.annex_conflict_review import corrected_role_text

    if isinstance(value, str):
        new, n = corrected_role_text(value, roles)
        counter[0] += n
        return new
    if isinstance(value, list):
        return [_fix_roles(v, roles, counter) for v in value]
    if isinstance(value, dict):
        return {k: (v if k in _ORIGINAL_KEYS else _fix_roles(v, roles, counter)) for k, v in value.items()}
    return value


def franchise_statute_row(annex_review: Any) -> dict[str, Any] | None:
    fa = getattr(annex_review, "franchise", None) or {}
    if not fa:
        return None
    reqs = "; ".join(f"{r['requirement']} — {r['status']}" + (f"({r['basis']})" if r.get("basis") else "")
                     for r in fa.get("requirements") or [])
    paths = list(dict.fromkeys(
        p for r in fa.get("requirements") or [] for p in re.findall(r"\[별첨\][^,;()]*?\)|\[별첨\] \d+\.", str(r.get("basis") or ""))
    )) or ["[별첨]"]
    return {
        "statute": str(fa.get("law") or "가맹사업거래의 공정화에 관한 법률"),
        "applicability": str(fa.get("likelihood") or "확인 필요"),
        "reasoning": f"[요건별 판단] {fa.get('conclusion') or ''}\n요건: {reqs}",
        "additional_facts_needed": list(fa.get("open_facts") or []),
        "related_clauses": paths,
        "risk_level": "확인 필요",
        "source": "annex_franchise_assessment",
        "canonical_status": "NEEDS_FACT_CHECK",
    }


def run_source_grounding_gate(
    *,
    contract_text: str,
    review_focus: str,
    answers: Any,
    clause_results: list[dict[str, Any]],
    meta: dict[str, Any],
    annex_review: Any = None,
) -> dict[str, Any]:
    allowed = allowed_source(contract_text=contract_text, review_focus=review_focus, answers=answers)
    report: dict[str, Any] = {
        "RESET_ALL_CONTRACT_CONTEXT": True, "status": "", "removed_findings": [], "scrubbed": [],
        "role_corrections": 0, "franchise_row": False,
    }

    # 1. finding — 현재 문서에 없는 거래 개념을 말하면 내보내지 않는다.
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
            continue
        terms = foreign_terms(_finding_blob(cr), allowed)
        if not terms:
            continue
        cr["dedup_suppressed"] = True
        cr["cross_case_contamination"] = terms
        cr["source_grounding_removed"] = STATUS_CROSS_CASE
        report["removed_findings"].append({
            "clause_id": str(cr.get("clause_id") or ""), "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90], "terms": terms, "code": STATUS_CROSS_CASE,
        })

    # 2. 법률 적용성·요청 답변·필수 검토항목 — 오염 문장만 걷어낸다.
    for key in ("legal_applicability_review", "legal_applicability", "user_review_coverage",
                "answer_intent_reviews", "user_request_answers"):
        if key in meta and meta.get(key):
            hits: list[str] = []
            meta[key] = scrub_value(meta[key], allowed, hits)
            if hits:
                report["scrubbed"].append({"section": key, "terms": hits})

    # 3. 별첨 역할 뒤집힘 — finding 은 내보내지 않고(수정문이 뒤집힌 역할 위에 쓰였다), 서술 행은 정정한다.
    roles = getattr(annex_review, "roles", None)
    if roles is not None and getattr(roles, "franchisor_name", ""):
        counter = [0]
        for cr in clause_results:
            if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
                continue
            probe = [0]
            _fix_roles({k: cr.get(k) for k in _TEXT_FIELDS}, roles, probe)
            if not probe[0]:
                continue
            cr["dedup_suppressed"] = True
            cr["source_grounding_removed"] = STATUS_PARTY_ROLE
            counter[0] += probe[0]
            report.setdefault("role_mismatch_findings", []).append(str(cr.get("clause_id") or ""))
        for key in ("legal_applicability_review", "legal_applicability", "user_review_coverage"):
            if meta.get(key):
                meta[key] = _fix_roles(meta[key], roles, counter)
        report["role_corrections"] = counter[0]
        if counter[0]:
            report["role_correction_code"] = STATUS_PARTY_ROLE

    # 3-2. 별첨에 대한 다른 지적(AI 조항 검토 등)은 축별 비교 finding 의 하위 쟁점이다 — 같은 별첨에 "우선순위
    #      불명확" 이 두 번 나가지 않게 한다(2026-10-13 AI 경로: AP-2 HIGH 가 따로 나왔다).
    owners = [cr for cr in clause_results if isinstance(cr, dict) and not cr.get("dedup_suppressed")
              and str(cr.get("clause_id") or "").startswith("ax_annex_precedence")]
    annex_path = str(getattr(annex_review, "annex_path", "") or "")
    if owners and annex_path:
        owner = owners[0]
        for cr in clause_results:
            if (not isinstance(cr, dict) or cr.get("dedup_suppressed")
                    or str(cr.get("clause_id") or "").startswith(("ax_", "uf_"))
                    or str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM")):
                continue
            # 별첨 자체, 그리고 별첨을 끌어오는 부칙 조항(우선순위 finding 의 앵커)에 붙은 지적.
            dp = str(cr.get("display_path") or "")
            if not (dp.startswith(annex_path.rstrip("]")) or dp.startswith("[부칙")):
                continue
            owner.setdefault("sub_issues", []).append({
                "clause_id": str(cr.get("clause_id") or ""), "display_path": str(cr.get("display_path") or ""),
                "title": str(cr.get("issue_title") or "")[:90], "problem": str(cr.get("problem") or "")[:240],
            })
            cr["dedup_suppressed"] = True
            cr["dedup_merged_into"] = str(owner.get("clause_id") or "")
            report.setdefault("absorbed_into_annex_review", []).append(str(cr.get("clause_id") or ""))

    # 4. 가맹사업법 — 요건별 판단 행으로 대체(AI 의 "적용 확실" 행 제거).
    row = franchise_statute_row(annex_review)
    if row is not None:
        for key in ("legal_applicability_review", "legal_applicability"):
            rows = [r for r in (meta.get(key) or []) if isinstance(r, dict)
                    and not re.search(r"가맹사업", str(r.get("statute") or ""))]
            rows.append(dict(row))
            meta[key] = rows
        report["franchise_row"] = True

    # 출력 직전 재확인 — 남아 있으면 그것이 상태다(지시 14항).
    residual = [str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)
                and not cr.get("dedup_suppressed") and foreign_terms(_finding_blob(cr), allowed)]
    if residual:
        report["status"] = STATUS_CROSS_CASE
        report["detail"] = "현재 계약서에 없는 거래 개념이 남은 finding: " + ", ".join(residual[:5])
    elif report["removed_findings"]:
        report["detail"] = (f"현재 계약서·요청에 없는 거래 개념을 말하는 finding {len(report['removed_findings'])}건을 "
                            "출력에서 제외했습니다(다른 계약의 흔적).")
    return report


def fix_roles_value(value: Any, annex_review: Any) -> Any:
    roles = getattr(annex_review, "roles", None)
    if roles is None or not getattr(roles, "franchisor_name", ""):
        return value
    return _fix_roles(value, roles, [0])


__all__ = [
    "fix_roles_value",
    "CONTAMINATION_TERMS", "STATUS_CROSS_CASE", "STATUS_PARTY_ROLE", "STATUS_SOURCE_NOT_FOUND",
    "allowed_source", "foreign_terms", "franchise_statute_row", "run_source_grounding_gate", "scrub_value",
]
