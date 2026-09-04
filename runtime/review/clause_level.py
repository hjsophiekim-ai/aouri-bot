from __future__ import annotations

import difflib
import difflib as _difflib
import json
import logging
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

logger = logging.getLogger(__name__)

from runtime.ai.enhance import _try_json
from runtime.ai.http_openai_compatible_provider import build_messages
from runtime.ai.provider import AIProvider, AIRequest
from runtime.ai.safe import sanitize_error_message
from runtime.law.search_service import LawSearchService
from runtime.review.clause_extraction import ClauseChunk, extract_clauses
from runtime.review.party_role import infer_party_role, infer_review_posture
from runtime.review.revision import suggest_revisions
from runtime.review.contract_structure import detect_contract_structure, STRUCTURE_DIRECT_CUSTOMER
from runtime.review.dealer_direct_findings import generate_structure_diagnosis_section
from runtime.review.word_markers import contains_wordprocessingml_markers
from runtime.review.korean_polish import polish_korean_legal_style
from runtime.review.clause_topic import classify_clause_topic, infer_rewrite_topics, is_topic_compatible
from runtime.review.priority_map import infer_contract_profile
from runtime.review.final_review_context import build_final_review_context
from runtime.review.user_focus import objective_codes_to_clause_topics, get_objective_keywords
from runtime.services.query_service import ReviewInput, RuleQueryService
from runtime.review.risk_scenarios import detect_risk_scenarios
from runtime.review.strategic_inquiry import generate_strategic_inquiry
from runtime.review.clause_conflicts import detect_clause_conflicts
from runtime.review.executive_summary import generate_executive_summary
from runtime.review.legal_effect_taxonomy import LEGAL_EFFECT_TAGS, effects_overlap

# ─── [Phase 2] 지능형 법무검토 시스템 프롬프트 ──────────────────────────────────
CLAUSE_REVIEW_SYSTEM = (
    "당신은 대한민국 대형 로펌 출신의 기업법무 파트너 변호사입니다. "
    "Fursys Inc.(퍼시스) 법무팀의 내부 법률자문으로서, 퍼시스의 이익을 최우선으로 검토합니다.\n\n"
    "검토 원칙:\n"
    "1. 상대방 표준 계약서는 상대방에게 유리하게 설계되어 있다고 가정하고 시작하라.\n"
    "2. 실제 분쟁이 발생했을 때 퍼시스가 입을 수 있는 최악의 시나리오를 먼저 상정하라.\n"
    "3. 모든 위험은 금전적·운영적·평판적 영향으로 구체화하여 서술하라.\n"
    "4. 영문 계약서의 경우 영미법·독일법·오스트리아법·EU법의 맥락에서 해석하라.\n"
    "5. 수정 제안은 반드시 대체 문안(영문 또는 국문)을 제시하라.\n"
    "6. 근거 없는 위험을 과장하지 말고, 실재하는 위험만 정확히 지적하라.\n"
    "7. indemnify/면책 조항이 수동태('shall be indemnified'/'면책된다')로만 되어 있고 "
    "그 의무를 실제로 부담하는 당사자(주체)가 명시되어 있지 않다면, 퍼시스(우리 회사)가 그 의무를 "
    "부담한다고 임의로 단정하지 마라 — '누가 면책하는지 불명확하다' 자체를 문제로 지적하고, "
    "각 당사자가 자신의 귀책사유로 발생한 청구에 대해서만 책임지도록 명확화할 것을 제안하라.\n\n"
    "출력 형식: 반드시 첫 글자 '[' 로 시작하는 JSON 배열만 출력하라. "
    "각 원소 형식: clause_id / rewrite_reason / suggested_rewrite / changed_segments / "
    "risk_tier / must_fix / worst_case_scenario / negotiation_strategy\n"
    "- worst_case_scenario: 분쟁 발생 시 퍼시스가 직면할 최악의 구체적 상황 1~2문장 (null 허용)\n"
    "- negotiation_strategy: PDG 또는 상대방과의 구체적 협상 전략 (null 허용)\n"
    "risk_tier와 must_fix는 입력값을 그대로 유지하라. 코드펜스/설명 문장 절대 금지."
)

EN_NDA_CLAUSE_REVIEW_SYSTEM = (
    "You are a senior partner attorney from a major Korean law firm, acting as in-house counsel for Fursys Inc. "
    "You specialize in cross-border transactions, German law, Austrian law, and international arbitration.\n\n"
    "Review principles:\n"
    "1. The counterparty's standard NDA is drafted in their favor — assume the worst.\n"
    "2. Identify the worst-case scenario for Fursys if a dispute arises under foreign law.\n"
    "3. Quantify all risks: cost exposure, jurisdictional disadvantage, enforcement difficulty.\n"
    "4. Interpret under German/Austrian law and EU regulations where applicable.\n"
    "5. Always propose alternative contract language (in English).\n"
    "6. Flag exclusive foreign court jurisdiction as HIGH risk requiring legal approval.\n"
    "7. If an indemnify/hold-harmless clause is passive ('shall be indemnified') and does not name "
    "which party actually bears that obligation, do NOT assume Fursys bears it by default — flag the "
    "ambiguity of the obligor itself as the issue, and propose clarifying that each party is liable "
    "only for claims arising from its own fault.\n\n"
    "Output format: ONLY a JSON array starting with '['. Each element:\n"
    "clause_id / rewrite_reason / suggested_rewrite / changed_segments / "
    "risk_tier / must_fix / worst_case_scenario / negotiation_strategy\n"
    "- worst_case_scenario: 1-2 sentences on the concrete worst-case legal outcome for Fursys\n"
    "- negotiation_strategy: specific negotiation strategy with 2-3 alternative approaches\n"
    "Keep risk_tier and must_fix from input. No code fences, no explanation text."
)

TOP3_RISK_SYSTEM = (
    "당신은 기업법무 파트너 변호사입니다. "
    "아래 조항별 분석 결과를 바탕으로 퍼시스에게 가장 치명적인 리스크 Top 3~5를 선정하라. "
    "반드시 JSON만 출력하라."
)

TOP3_RISK_USER_TEMPLATE = """\
## 계약 전체 맥락
{meta_summary}

## 전체 조항 분석 결과 (요약)
{all_clause_summaries}

## 요청
퍼시스에게 가장 치명적인 리스크 3~5개를 중요도 순으로 선정하고 아래 JSON으로만 응답하라.
"치명적"의 기준: 분쟁 발생 시 금전적 손실, 사업 중단, 평판 손상, 법적 불이익 중 하나 이상이 실질적으로 발생할 가능성이 있는 것.

{{
  "top_risks": [
    {{
      "rank": 1,
      "clause_id": "조항 ID",
      "risk_title": "리스크 제목 (20자 이내)",
      "severity": "CRITICAL|HIGH",
      "one_line_summary": "경영진에게 보고하는 수준의 1문장 요약",
      "financial_impact": "예상 금전적 영향 또는 '정량화 불가'",
      "recommended_action": "서명 전 반드시 취해야 할 조치",
      "deadline": "즉시|서명 전|계약 기간 중"
    }}
  ],
  "overall_recommendation": "SIGN_AS_IS|SIGN_WITH_MINOR_CHANGES|NEGOTIATE_BEFORE_SIGNING|DO_NOT_SIGN",
  "recommendation_reason": "2~3문장 종합 의견"
}}
"""
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClauseLevelResult:
    review: dict[str, Any]
    revision: dict[str, Any]
    clauses: list[ClauseChunk]
    clause_results: list[dict[str, Any]]
    meta: dict[str, Any]


def _contains_wordprocessingml_markers(text: str) -> bool:
    return contains_wordprocessingml_markers(text)


_RX_ACTIVE_TERMINATION_RIGHT = re.compile(
    r"해지(?:할\s*수\s*있다|권)|해제(?:할\s*수\s*있다|권)|즉시\s*(?:해지|해제)|계약을\s*(?:해지|해제)",
    re.DOTALL,
)
_RX_DEDUP = re.compile(r"[\s\r\n\t]+")
_RX_DEDUP_PUNCT = re.compile(r"[^\w가-힣]+")


def _rewrite_dedup_topic(text: str) -> str | None:
    t = (text or "")
    if not t:
        return None
    if any(k in t for k in ("침해사고", "보안사고", "개인정보 유출", "유출사고")):
        return "security_incident"
    if any(k in t for k in ("통지", "지체 없이", "사고 발생 시", "유출 시")) and any(k in t for k in ("보안", "개인정보", "침해")):
        return "security_incident"
    if any(k in t for k in ("재위탁", "재수탁", "하도급", "재하도급")):
        return "subcontract"
    if any(k in t for k in ("데이터 반환", "데이터 삭제", "반환·삭제", "반환/삭제")):
        return "data_return_delete"
    return None


def _norm_dedup_key(s: str) -> str:
    x = (s or "").strip().lower()
    x = _RX_DEDUP.sub(" ", x)
    x = _RX_DEDUP_PUNCT.sub(" ", x)
    x = _RX_DEDUP.sub(" ", x).strip()
    return x[:800]


def _format_meta_summary(
    llm_meta: dict[str, Any],
    contract_type: str = "",
    entity: str = "",
) -> str:
    lines: list[str] = []
    if entity:
        lines.append(f"의뢰인: {entity}")
    if contract_type:
        lines.append(f"계약 유형: {contract_type}")
    pa = str(llm_meta.get("party_a") or llm_meta.get("party_a_name") or "").strip()
    pb = str(llm_meta.get("party_b") or llm_meta.get("party_b_name") or "").strip()
    if pa:
        lines.append(f"당사자 A: {pa}")
    if pb:
        lines.append(f"당사자 B: {pb}")
    pac = str(llm_meta.get("party_a_country") or "").strip()
    pbc = str(llm_meta.get("party_b_country") or "").strip()
    if pac or pbc:
        lines.append(f"국가: A={pac or '불명'} / B={pbc or '불명'}")
    gl = str(llm_meta.get("governing_law") or llm_meta.get("governing_law_country") or "").strip()
    if gl:
        lines.append(f"준거법: {gl}")
    jc = str(llm_meta.get("jurisdiction_city") or "").strip()
    if jc:
        lines.append(f"관할 도시: {jc}")
    if llm_meta.get("is_cross_border"):
        lines.append("크로스보더 계약: 예")
    if llm_meta.get("has_exclusive_jurisdiction"):
        lines.append("전속 관할 조항: 있음")
    return "\n".join(lines) if lines else "(계약 메타 정보 없음)"


def _format_clause_summaries(clause_results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    count = 0
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        rt = str(cr.get("risk_tier") or "").upper()
        if rt not in ("HIGH", "MEDIUM"):
            continue
        cid = str(cr.get("clause_id") or cr.get("display_path") or "")
        rr = str(cr.get("rewrite_reason") or "").strip()
        wcs = str(cr.get("worst_case_scenario") or "").strip()
        must_fix = bool(cr.get("must_fix")) or bool(cr.get("approval_required"))
        parts = [f"[{rt}] {cid}"]
        if must_fix:
            parts.append("필수 수정")
        if rr:
            parts.append(rr[:120])
        if wcs:
            parts.append(f"최악: {wcs[:80]}")
        lines.append(" | ".join(parts))
        count += 1
        if count >= 20:
            break
    return "\n".join(lines) if lines else "(분석된 HIGH/MEDIUM 조항 없음)"


def _norm_text_for_change(s: str) -> str:
    x = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    x = _RX_DEDUP.sub(" ", x)
    x = re.sub(r"\n{3,}", "\n\n", x)
    return x.strip()


def _word_tokens_for_diff(s: str) -> list[str]:
    t = _norm_text_for_change(s)
    if not t:
        return []
    return re.findall(r"[0-9A-Za-z가-힣]+|[^\s0-9A-Za-z가-힣]|\s+", t)


def _diff_segments_for_change_record(original: str, revised: str) -> dict[str, list[str]]:
    a = _word_tokens_for_diff(original or "")
    b = _word_tokens_for_diff(revised or "")
    sm = difflib.SequenceMatcher(a=a, b=b)
    unchanged: list[str] = []
    inserted: list[str] = []
    deleted: list[str] = []

    def _push(arr: list[str], s: str) -> None:
        s = (s or "").strip()
        if not s:
            return
        if arr and arr[-1] == s:
            return
        arr.append(s)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            _push(unchanged, "".join(a[i1:i2]))
        elif tag == "insert":
            _push(inserted, "".join(b[j1:j2]))
        elif tag == "delete":
            _push(deleted, "".join(a[i1:i2]))
        elif tag == "replace":
            _push(deleted, "".join(a[i1:i2]))
            _push(inserted, "".join(b[j1:j2]))

    return {
        "unchanged_segment": unchanged[:4],
        "inserted_segment": inserted[:6],
        "deleted_segment": deleted[:6],
        "moved_or_omitted_segment": [],
    }


def _is_keep_as_is_clause(*, title: str, text: str) -> bool:
    t = (title or "").strip()
    body = (text or "").strip()
    if not body:
        return False

    def compact(s: str) -> str:
        return re.sub(r"[\s\W_]+", "", (s or ""))

    tc = compact(t)
    bc = compact(body)
    if not bc:
        return False

    if any(k in bc for k in ("침해사고", "보안사고", "개인정보유출", "통지", "배상책임", "손해배상")):
        return False

    if any(k in tc for k in ("불공정", "금지", "불이익", "지위", "해지", "계약해지")):
        return False

    title_hint = any(k in tc for k in ("기본원칙", "일반원칙", "총칙", "법령준수", "준법"))
    if "준수" not in bc:
        return False

    compliance_phrase = any(
        p in bc
        for p in (
            "관련법령의규정을준수",
            "관계법령의규정을준수",
            "관련법령을준수",
            "관계법령을준수",
            "법령을준수",
            "법령의규정을준수",
        )
    )
    law_hint = any(
        k in bc
        for k in (
            "독점규제",
            "공정거래",
            "대리점거래",
            "대리점",
            "개인정보보호",
            "부정경쟁",
            "전자상거래",
        )
    )

    if (title_hint or compliance_phrase) and ("법령" in bc or "법률" in bc) and law_hint:
        return True
    if compliance_phrase and ("관련법령" in bc or "관계법령" in bc):
        return True
    return False


def _dedup_rewrite_suggestions(clause_results: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("keep_as_is")):
            continue
        sr = cr.get("suggested_rewrite")
        if not isinstance(sr, str) or not sr.strip():
            continue
        rr = cr.get("rewrite_reason")
        topic = _rewrite_dedup_topic(sr) or (_rewrite_dedup_topic(rr) if isinstance(rr, str) else None)
        if not topic:
            continue
        article = str(cr.get("article_number") or "").strip()
        if not article:
            continue
        nk = _norm_dedup_key(sr)
        if len(nk) < 24:
            continue
        cr["_dedup_norm"] = nk
        groups.setdefault((topic, article), []).append(cr)

    def score_anchor(cr: dict[str, Any], topic: str) -> int:
        s = 0
        if bool(cr.get("must_fix")) or bool(cr.get("approval_required")) or bool(cr.get("high_risk")):
            s += 20
        tier = str(cr.get("risk_tier") or "").upper()
        if tier == "HIGH":
            s += 10
        if tier == "MEDIUM":
            s += 4
        title = str(cr.get("clause_title") or "")
        txt = str(cr.get("original_text") or "")
        hay = title + " " + txt
        if topic == "security_incident" and any(k in hay for k in ("개인정보", "보안", "정보보호", "침해", "유출")):
            s += 12
        if topic == "security_incident" and any(k in title for k in ("보안", "개인정보", "정보보호")):
            s += 20
        if topic == "security_incident" and "목적" in title:
            s -= 6
        if topic == "subcontract" and any(k in hay for k in ("재위탁", "하도급", "수탁", "위탁")):
            s += 12
        if topic == "data_return_delete" and any(k in hay for k in ("반환", "삭제", "종료", "해지", "데이터")):
            s += 10
        dp = str(cr.get("display_path") or "")
        s += max(0, 3 - len(dp.split()))
        return s

    def allow_suppress_secondary(cr: dict[str, Any], topic: str) -> bool:
        if topic == "security_incident":
            title = str(cr.get("clause_title") or "")
            if any(k in title for k in ("보안", "개인정보", "정보보호")):
                return False
            return True
        return True

    def sim(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        import difflib

        return difflib.SequenceMatcher(a=a, b=b).ratio()

    for (topic, _article), items in groups.items():
        if len(items) < 2:
            continue
        remaining = sorted(items, key=lambda x: (-score_anchor(x, topic), str(x.get("clause_id") or "")))
        used: set[str] = set()
        for primary in remaining:
            pid = str(primary.get("clause_id") or "")
            if not pid or pid in used:
                continue
            pn = str(primary.get("paragraph_number") or "").strip()
            pn_i = int(pn) if pn.isdigit() else None
            primary_norm = str(primary.get("_dedup_norm") or "")
            primary_dp = str(primary.get("display_path") or pid or "").strip()
            primary["dedup_group"] = topic
            primary["dedup_primary_clause_id"] = pid
            used.add(pid)

            for cr in remaining:
                cid = str(cr.get("clause_id") or "")
                if not cid or cid in used or cid == pid:
                    continue
                if not allow_suppress_secondary(cr, topic):
                    continue
                pn2 = str(cr.get("paragraph_number") or "").strip()
                pn2_i = int(pn2) if pn2.isdigit() else None
                if pn_i is not None and pn2_i is not None and abs(pn_i - pn2_i) > 2:
                    continue
                if not (isinstance(cr.get("suggested_rewrite"), str) and cr.get("suggested_rewrite").strip()):
                    continue
                c_norm = str(cr.get("_dedup_norm") or "")
                if sim(primary_norm, c_norm) < 0.93:
                    continue

                cr["dedup_group"] = topic
                cr["dedup_primary_clause_id"] = pid
                cr["dedup_suppressed"] = True
                cr["changed_segments"] = []
                cr["suggested_rewrite"] = None
                old_reason = cr.get("rewrite_reason")
                suffix = f"동일 취지 중복으로 판단되어 {primary_dp} 조항에 대표 반영"
                if isinstance(old_reason, str) and old_reason.strip():
                    cr["rewrite_reason"] = (old_reason.strip() + " / " + suffix)[:900]
                else:
                    cr["rewrite_reason"] = suffix
                used.add(cid)

    return


def _key_terms_for_contract_type(contract_type: str) -> list[str]:
    ct = (contract_type or "").strip()
    if not ct:
        return []
    if any(k in ct for k in ("대리점", "유통", "위탁거래", "위탁판매", "판매대행", "dealer", "distributor", "consignment")):
        return [
            "기본원칙", "공정거래", "준수", "동반성장", "불공정", "불이익", "거래상", "지위", "경영", "간섭",
            "영업", "자율", "해지", "종료", "물량", "공급", "중단", "불이익조치", "비용", "비용부담",
            "판촉", "광고", "장려금", "반품", "원상회복", "정산", "상계", "공제", "증빙", "자료",
            "확인", "개인정보", "고객정보", "분쟁해결",
        ]
    if any(k in ct for k in ("운영대행", "위탁운영", "운영위탁", "공간운영", "매장운영", "서비스위탁", "관리용역", "운영용역")):
        return [
            "업무범위", "운영", "대행", "성과", "KPI", "보고", "자료제출", "검수", "점검", "인력",
            "배치", "교대", "교육", "책임자", "정산", "수수료", "용역비", "상계", "공제", "증빙",
            "하도급", "재위탁", "승인", "안전", "산업안전", "개인정보", "기밀", "해지", "인수인계",
        ]
    if any(k in ct for k in ("앱개발", "소프트웨어", "SI", "유지보수", "SaaS", "IT", "API")):
        return [
            "목적", "범위", "수행", "사양", "SOW", "검수", "간주검수", "지연", "지체", "지체상금",
            "마일스톤", "산출물", "소스코드", "저작권", "지식재산", "IP", "제3자", "오픈소스",
            "라이선스", "보안", "개인정보", "위탁", "국외이전", "하자", "유지보수", "SLA", "장애",
            "해지", "종료", "인수인계", "데이터", "분쟁", "관할",
        ]
    if any(k in ct for k in ("구매", "설치", "납품", "장비", "물품", "공급")):
        return [
            "검수", "하자", "보증", "지연", "지체", "지체상금", "안전", "책임제한", "손해배상",
            "해지", "분쟁", "관할",
        ]
    if any(k in ct for k in ("용역", "자문", "컨설팅", "advisory", "consulting", "연구", "교수", "위탁연구")):
        return [
            "업무범위", "수행", "결과물", "산출물", "보고", "보고서", "저작권", "지식재산", "IP",
            "귀속", "비밀유지", "기밀", "겸직", "이해충돌", "보수", "용역비", "대금", "지급",
            "해지", "계약해제", "손해배상", "분쟁", "관할",
        ]
    return []


# ---------------------------------------------------------------------------
# [반복 코멘트 생성 방지] 조(Article) 단위 통합 판단 + 중복 제거 + Article Review
# ---------------------------------------------------------------------------


def _sim_ratio(a: str, b: str) -> float:
    """두 문자열의 유사도(0~1)를 반환한다."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return _difflib.SequenceMatcher(None, a[:600], b[:600]).ratio()


def _norm_for_sim(s: str) -> str:
    """유사도 비교용 정규화."""
    x = re.sub(r"[\s\r\n\t]+", " ", (s or "").strip().lower())
    x = re.sub(r"[^\w가-힣]+", " ", x)
    return x.strip()[:600]


def _build_article_review_comment(
    article_number: str | None,
    article_title: str | None,
    risk_codes: list[str],
    risk_topics: list[str],
) -> str:
    """
    조(Article) 전체를 묶는 [Article Review] 통합 코멘트를 생성한다.
    포괄적 리스크(불공정행위 금지 등)는 개별 항마다 반복하지 않고 여기에 한 번만 기술한다.
    """
    art = f"제{article_number}조" if article_number else "해당 조"
    title_part = f" [{article_title}]" if article_title else ""
    codes_str = " / ".join(risk_codes[:5]) if risk_codes else ""
    topics_str = " / ".join(risk_topics[:4]) if risk_topics else ""

    lines = [f"[Article Review] {art}{title_part}"]
    if codes_str:
        lines.append(f"  · 적용 규칙: {codes_str}")
    if topics_str:
        lines.append(f"  · 리스크 범주: {topics_str}")
    lines.append(
        f"  · 본 조 내 여러 항에 동일한 리스크가 존재합니다. "
        f"대표 항의 수정안을 기준으로 통합 관리하십시오."
    )
    return "\n".join(lines)


def _apply_article_dedup_and_consolidation(clause_results: list[dict[str, Any]]) -> None:
    """
    [반복 코멘트 생성 방지] 4가지 지침을 clause_results에 적용한다.
    이미 dedup_suppressed=True인 항목은 재처리하지 않는다(멱등성 보장).

    지침 1. 조(Article) 단위 통합 판단
        - 같은 조(article_number) 내 여러 항이 동일 핵심 리스크를 가지면
          코멘트는 단 한 번(대표 항)만 생성한다.

    지침 2. 대표 항 지정
        - 리스크가 가장 잘 드러나는 항을 anchor로 지정하고,
          나머지 항에는 "위 제N항의 수정안과 동일한 리스크가 존재하므로 통합 관리 필요"
          메시지로 대체한다.

    지침 3. 중복 검사(De-duplication)
        - suggested_rewrite 문구가 이미 다른 조항에서 사용된 문구와 80% 이상 유사하면
          해당 문구를 다시 출력하지 않고 인라인 수정 방식만 사용한다.

    지침 4. 리스크 범주화
        - "불공정행위 금지"처럼 포괄적인 내용은 개별 항마다 언급하지 않고
          조 전체를 묶어 [Article Review] 섹션으로 통합하여 한 번에 기술한다.
    """
    if not clause_results:
        return

    # ── 지침 3: 전역 중복 검사 ──────────────────────────────────────────────
    # 이미 출력된 suggested_rewrite 목록을 추적하여 80% 이상 유사 시 인라인 수정으로 전환
    seen_rewrites: list[str] = []

    def _is_duplicate_rewrite(text: str) -> bool:
        norm = _norm_for_sim(text)
        for seen in seen_rewrites:
            if _sim_ratio(norm, seen) >= 0.80:
                return True
        return False

    def _to_inline_rewrite(original_text: str, suggested: str) -> str:
        """
        중복 판정된 경우 suggested_rewrite를 원문에 직접 녹여내는 인라인 수정으로 변환한다.
        원문에 없는 핵심 추가 문구만 괄호로 삽입한다.
        """
        orig_norm = _norm_for_sim(original_text)
        sug_norm = _norm_for_sim(suggested)
        # 추가된 핵심 단어 추출
        orig_words = set(re.findall(r"[가-힣A-Za-z0-9]+", orig_norm))
        sug_words = set(re.findall(r"[가-힣A-Za-z0-9]+", sug_norm))
        new_words = [w for w in sug_words - orig_words if len(w) >= 2][:6]
        if not new_words:
            return original_text
        inline_note = " (단, " + " · ".join(new_words[:4]) + " 조건 포함)"
        return (original_text.rstrip() + inline_note).strip()

    # ── 지침 1·2·4: 조 단위 그룹화 ─────────────────────────────────────────
    # article_number 기준으로 그룹화 (이미 suppressed된 항목은 제외)
    article_groups: dict[str, list[dict[str, Any]]] = {}
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        # 이미 1차 dedup에서 처리된 항목은 재처리하지 않음 (멱등성)
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("article_review_anchor")):
            sr_existing = cr.get("suggested_rewrite")
            if isinstance(sr_existing, str) and sr_existing.strip():
                seen_rewrites.append(_norm_for_sim(sr_existing))
            continue
        an = str(cr.get("article_number") or "").strip()
        if not an:
            continue
        article_groups.setdefault(an, []).append(cr)

    # 포괄적 리스크 범주 (개별 항마다 반복 금지 대상)
    _BROAD_RISK_TOPICS = {
        "dealer_unfair", "cost_burden", "payment_settlement",
        "termination", "personal_data", "safety",
    }
    _BROAD_RISK_CODES = {
        "RISK-006", "RISK-005", "RISK-002", "RISK-001", "DEALER-001", "C-001",
    }

    # 조 제목 기반 topic 추론 (항 본문 키워드가 없어도 조 제목으로 판단)
    _TITLE_TOPIC_MAP: list[tuple[list[str], str]] = [
        (["불공정행위", "불공정 행위", "각종 불공정", "불이익 제공", "거래상 지위", "경영간섭"], "dealer_unfair"),
        (["비용", "판촉비", "광고비", "반품비", "원상회복", "비용분담", "비용 부담"], "cost_burden"),
        (["정산", "상계", "공제", "대금", "지급"], "payment_settlement"),
        (["해지", "계약해지", "종료", "중도해지"], "termination"),
        (["개인정보", "정보보호", "처리위탁"], "personal_data"),
        (["안전", "산업안전", "중대재해"], "safety"),
    ]

    def _infer_topic_from_title(title: str) -> str | None:
        t = (title or "").strip()
        if not t:
            return None
        for keywords, topic in _TITLE_TOPIC_MAP:
            if any(k in t for k in keywords):
                return topic
        return None

    def _suppress_secondary(
        cr: dict[str, Any],
        anchor: dict[str, Any],
        an: str,
        anchor_pn: str,
        anchor_dp: str,
    ) -> None:
        """secondary 항목을 suppressed 처리하고 참조 메시지를 설정한다."""
        pn_ref = anchor_pn if anchor_pn else anchor_dp
        cr["suggested_rewrite"] = None
        old_reason = str(cr.get("rewrite_reason") or "").strip()
        ref_msg = (
            f"위 제{pn_ref}항의 수정안과 동일한 리스크가 존재하므로 통합 관리 필요. "
            f"(제{an}조 전체를 [Article Review] 기준으로 검토하십시오.)"
        )
        cr["rewrite_reason"] = (old_reason + " / " + ref_msg).strip(" / ") if old_reason else ref_msg
        cr["article_review_ref"] = anchor.get("clause_id") or anchor_dp
        cr["dedup_suppressed"] = True
        cr["changed_segments"] = []

    for an, group in article_groups.items():
        if not group:
            continue

        # ── 조 제목 기반 topic 통일 ──────────────────────────────────────────
        group_titles = [str(cr.get("clause_title") or "") for cr in group]
        dominant_title = group_titles[0] if group_titles else ""
        title_topic = _infer_topic_from_title(dominant_title)

        # ── 지침 1: 동일 조 내 리스크 동일성 판단 ──────────────────────────
        group_risk_codes: set[str] = set()
        group_topics: set[str] = set()
        for cr in group:
            for ar in (cr.get("applied_rules") or []):
                if isinstance(ar, dict) and isinstance(ar.get("rule_id"), str):
                    group_risk_codes.add(str(ar["rule_id"]))
            t = str(cr.get("clause_topic") or "")
            if t and t != "other":
                group_topics.add(t)
        if title_topic:
            group_topics.add(title_topic)

        has_broad_risk = bool(group_risk_codes & _BROAD_RISK_CODES) or bool(group_topics & _BROAD_RISK_TOPICS)

        # ── 단일 항: 중복 검사만 적용 ────────────────────────────────────────
        if len(group) < 2:
            cr = group[0]
            sr = cr.get("suggested_rewrite")
            if isinstance(sr, str) and sr.strip():
                if _is_duplicate_rewrite(sr):
                    ot = str(cr.get("original_text") or "")
                    cr["suggested_rewrite"] = _to_inline_rewrite(ot, sr)
                    cr["rewrite_reason"] = (
                        (str(cr.get("rewrite_reason") or "") + " [중복 수정안 → 인라인 수정으로 전환]").strip()
                    )
                    cr["dedup_inline"] = True
                else:
                    seen_rewrites.append(_norm_for_sim(sr))
            continue

        # ── 지침 2: 대표 항(anchor) 선정 ────────────────────────────────────
        def _anchor_score(cr: dict[str, Any]) -> int:
            s = 0
            if bool(cr.get("approval_required")):
                s += 100
            if bool(cr.get("high_risk")):
                s += 80
            if str(cr.get("risk_tier") or "").upper() == "HIGH":
                s += 60
            if bool(cr.get("must_fix")):
                s += 40
            if bool(cr.get("user_focus_hit")):
                s += 30
            sr = cr.get("suggested_rewrite")
            if isinstance(sr, str) and sr.strip():
                s += 20
            pn = str(cr.get("paragraph_number") or "")
            if pn.isdigit():
                s -= int(pn)
            return s

        sorted_group = sorted(group, key=lambda x: -_anchor_score(x))
        anchor = sorted_group[0]
        secondaries = sorted_group[1:]

        # anchor의 suggested_rewrite 중복 검사
        anchor_sr = anchor.get("suggested_rewrite")
        if isinstance(anchor_sr, str) and anchor_sr.strip():
            if _is_duplicate_rewrite(anchor_sr):
                ot = str(anchor.get("original_text") or "")
                anchor["suggested_rewrite"] = _to_inline_rewrite(ot, anchor_sr)
                anchor["rewrite_reason"] = (
                    (str(anchor.get("rewrite_reason") or "") + " [중복 수정안 → 인라인 수정으로 전환]").strip()
                )
                anchor["dedup_inline"] = True
            else:
                seen_rewrites.append(_norm_for_sim(anchor_sr))

        anchor["article_review_anchor"] = True
        anchor_pn = str(anchor.get("paragraph_number") or "")
        anchor_dp = str(anchor.get("display_path") or anchor.get("clause_id") or "")

        # ── 지침 4: [Article Review] 통합 코멘트 생성 ───────────────────────
        if has_broad_risk:
            article_title = str(anchor.get("clause_title") or "").strip()
            risk_codes_list = sorted(group_risk_codes & _BROAD_RISK_CODES)
            risk_topics_list = sorted(group_topics & _BROAD_RISK_TOPICS)
            article_review_comment = _build_article_review_comment(
                article_number=an,
                article_title=article_title,
                risk_codes=risk_codes_list,
                risk_topics=risk_topics_list,
            )
            anchor["article_review_comment"] = article_review_comment

        # ── 지침 2: 나머지 항(secondary) 처리 ──────────────────────────────
        anchor_sr_norm = _norm_for_sim(str(anchor.get("suggested_rewrite") or ""))
        anchor_rr_norm = _norm_for_sim(str(anchor.get("rewrite_reason") or ""))

        for cr in secondaries:
            cr_sr = cr.get("suggested_rewrite")
            cr_rr = str(cr.get("rewrite_reason") or "")

            # 케이스 A: suggested_rewrite가 있는 경우
            if isinstance(cr_sr, str) and cr_sr.strip():
                cr_norm = _norm_for_sim(cr_sr)
                sim_sr = _sim_ratio(anchor_sr_norm, cr_norm) if anchor_sr_norm else 0.0
                if sim_sr >= 0.80:
                    _suppress_secondary(cr, anchor, an, anchor_pn, anchor_dp)
                elif _is_duplicate_rewrite(cr_sr):
                    ot = str(cr.get("original_text") or "")
                    cr["suggested_rewrite"] = _to_inline_rewrite(ot, cr_sr)
                    cr["rewrite_reason"] = (
                        (str(cr.get("rewrite_reason") or "") + " [중복 수정안 → 인라인 수정으로 전환]").strip()
                    )
                    cr["dedup_inline"] = True
                else:
                    seen_rewrites.append(_norm_for_sim(cr_sr))

            # 케이스 B: suggested_rewrite 없지만 rewrite_reason이 anchor와 유사
            elif cr_rr.strip() and anchor_rr_norm:
                sim_rr = _sim_ratio(anchor_rr_norm, _norm_for_sim(cr_rr))
                if sim_rr >= 0.75:
                    _suppress_secondary(cr, anchor, an, anchor_pn, anchor_dp)

            # 케이스 C: 같은 조, broad_risk 범주, suggested_rewrite/reason 모두 없음
            # → 조 제목이 포괄적 리스크 범주이면 무조건 참조 메시지 추가
            elif has_broad_risk and title_topic:
                _suppress_secondary(cr, anchor, an, anchor_pn, anchor_dp)

def _article_int(v: Any) -> int | None:
    s = str(v or "").strip()
    if not s:
        return None
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _is_hard_block_clause(*, article_int: int | None, title: str, clause_topic: str | None = None) -> bool:
    if article_int in (1, 2, 3):
        return True
    t = str(title or "").strip()
    if not t:
        t = ""
    tc = re.sub(r"\s+", "", t)
    if "목적" in t:
        return True
    if "기본원칙" in t or "일반원칙" in t:
        return True
    if "용어정의" in tc:
        return True
    if ("용어" in t) and ("정의" in t):
        return True
    if article_int == 32:
        if (clause_topic or "") == "dispute":
            return True
        if any(k in t for k in ("분쟁", "관할", "재판", "준거법", "중재", "조정", "소송")):
            return True
    return False


def _article_int_from_cr(cr: dict[str, Any]) -> int | None:
    return (
        _article_int(cr.get("article_number"))
        or _article_int(cr.get("clause_id"))
        or _article_int(cr.get("display_path"))
        or _article_int(cr.get("clause_title"))
    )


def _dealer_issue_rank(cr: dict[str, Any]) -> int:
    a = _article_int_from_cr(cr)
    if a in (21,):
        return 0
    if a in (14, 18, 5):
        return 1
    if a in (23, 24):
        return 2
    if a in (11, 17):
        return 3
    if a in (8, 9, 10):
        return 4
    if a in (27,):
        return 7
    hay = (str(cr.get("clause_title") or "") + " " + str(cr.get("display_path") or "")).strip()
    if any(k in hay for k in ("불공정", "불이익", "거래상 지위", "지위 남용", "각종 불공정행위")):
        return 0
    if any(k in hay for k in ("인력", "채용", "관리", "교육", "운영기준")):
        return 1
    if any(k in hay for k in ("해지", "종료", "물량", "공급중단", "불이익")):
        return 2
    if any(k in hay for k in ("운영비용", "비용분담", "비용 부담", "판촉", "광고", "장려금", "반품", "원상회복")):
        return 3
    if any(k in hay for k in ("정산", "상계", "공제", "증빙")):
        return 4
    if any(k in hay for k in ("분쟁", "관할", "준거법", "중재")):
        return 7
    ct = str(cr.get("clause_topic") or "")
    if ct in ("privacy",):
        return 5
    if ct in ("dispute",):
        return 7
    return 6


def _score_for_ai_deep_review(
    *,
    cr: dict[str, Any],
    key_terms: list[str],
    is_dealer_contract: bool,
    jur_kind: str | None,
    cross_border: bool,
    wants_dispute: bool,
) -> int:
    tier = str(cr.get("risk_tier") or "").strip().upper()
    score = 0
    if bool(cr.get("user_focus_hit")):
        score += 60
    if bool(cr.get("factual_hit")):
        score += 25
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
    if is_dealer_contract:
        a0 = _article_int_from_cr(cr)
        if a0 in (21, 23, 14, 11, 17, 8, 9, 10):
            score += 120
        if a0 in (27,):
            if str(jur_kind or "") == "domestic_korea" and (not cross_border) and (not wants_dispute):
                score -= 140
        ct0 = str(cr.get("clause_topic") or "").strip()
        if ct0 in ("termination", "dealer_unfair", "cost_burden", "payment_settlement"):
            score += 45
        if ct0 == "dispute" and str(jur_kind or "") == "domestic_korea" and (not cross_border) and (not wants_dispute):
            score -= 60
    return score


_AI_SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _ai_quote_is_grounded(quote: Any, original_text: str) -> bool:
    """[Hybrid AI Review guardrail] The AI must ground any severity call in an
    actual excerpt of the clause it is reasoning about. Reject ungrounded
    severity changes rather than trust a bare label — this is what stops the
    AI from re-creating the exact "사용자 중점 이슈: X" bare-label problem,
    just via a different code path.
    """
    if not isinstance(quote, str):
        return False
    q = quote.strip()
    if len(q) < 8:
        return False
    hay = (original_text or "")
    if q in hay:
        return True
    # Loose fallback: require a meaningful contiguous run (first 12 chars) to
    # tolerate the AI lightly normalising whitespace/punctuation in the quote.
    probe = q[:12]
    return len(probe) >= 8 and probe in hay


# [Hybrid AI Review guardrail] Keyword clusters whose presence in AI-
# generated rewrite_reason/suggested_rewrite content is a strong signal of a
# hallucinated, off-topic response — UNLESS the clause's own original_text
# already discusses that same subject. A grounded quote only proves the
# AI's excerpt is real; it does not prove the AI's REASONING about that
# excerpt stayed on-topic. Confirmed against a real FITI 시험분석약정서 run
# where 제14조② (관할/분쟁 조항) repeatedly received AI content about
# personnel/HR management ("인력 채용·배치·평가·징계") — a subject that
# clause's own text never mentions. Each tuple is (foreign-topic markers,
# keywords that — if present in the clause's own original_text — mean this
# topic genuinely belongs here and the content should NOT be rejected).
_FOREIGN_TOPIC_MARKER_CLUSTERS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (
        frozenset({"인력 채용", "인력 운용", "인사관리", "인사권", "채용·배치", "채용ㆍ배치", "인력 배치", "인력에 대한 평가"}),
        frozenset({"채용", "인사", "징계", "근로", "고용", "인력", "직원"}),
    ),
)


def _sanitize_ai_severity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().upper()
    return v if v in _AI_SEVERITY_RANK else None


def _compute_ai_deep_review_target_count(*, clause_count: int, must_count: int, medium_count: int) -> int:
    base = 8 + max(0, (int(clause_count) - 12) // 8)
    target = max(base, int(must_count))
    target = max(target, int(must_count) + min(int(medium_count), 8))
    return min(max(target, 0), 28)


# =============================================================================
# [Advanced Review Logic] Hard-Coded Filter Functions
# requirement.md > [Advanced Review Logic] 참조
# =============================================================================

_RENTAL_KW = re.compile(r"렌탈|구독|임대차|Lease", re.IGNORECASE)
# "리스" 뒤에 부정형 lookahead를 두어 "리스크"(risk)/"리스트"(list)와 혼동되지
# 않게 한다 — "리스료"/"리스 계약" 등 실제 렌탈/리스(lease) 관련 표현은 계속 매칭.
_RENTAL_COMMENT_KW = re.compile(r"소유권|위약금|렌탈|임대|리스(?!크|트)|반납|반환.*계약|구독.*해지")

_EN_NDA_TRIGGER_PATTERNS = [
    re.compile(r"\bStuttgart\b|\bMunich\b|\bFrankfurt\b|\bHamburg\b|\bBerlin\b", re.IGNORECASE),
    re.compile(r"\bGerman\s+law\b|\blaws\s+of\s+Germany\b|\bGoverning\s+Law\b", re.IGNORECASE),
    re.compile(r"\bjurisdiction\b|\bReceiving\s+Party\b|\bConfidential\s+Information\b", re.IGNORECASE),
]


def _check_en_nda_rules(
    clause_title: str,
    clause_text: str,
    jur_kind: str | None,
    loaded_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return NDA-EN-* rules whose triggers match the clause title/text."""
    if jur_kind == "domestic_korea":
        return []
    haystack = ((clause_title or "") + " " + (clause_text or "")[:1000]).lower()
    matched: list[dict[str, Any]] = []
    for rule in loaded_rules:
        if not isinstance(rule, dict):
            continue
        rid = str(rule.get("rule_id") or "")
        if not rid.startswith("NDA-EN"):
            continue
        tags = rule.get("tags") if isinstance(rule.get("tags"), list) else []
        trigger_kws = [t[8:].lower() for t in tags if isinstance(t, str) and t.startswith("trigger:")]
        if any(kw in haystack for kw in trigger_kws):
            matched.append(rule)
    return matched


def _build_change_record(
    clause_id: str,
    original_text: str,
    suggested_rewrite: str | None,
    rewrite_reason: str | None,
    risk_tier: str,
    *,
    worst_case_scenario: str | None = None,
    negotiation_strategy: str | None = None,
) -> dict[str, Any]:
    """Build a structured change record for a single clause."""
    return {
        "clause_id": clause_id,
        "original_text": (original_text or "")[:400],
        "suggested_rewrite": suggested_rewrite,
        "rewrite_reason": rewrite_reason,
        "risk_tier": risk_tier,
        "has_change": bool(suggested_rewrite and suggested_rewrite.strip() and suggested_rewrite.strip() != (original_text or "").strip()),
        "worst_case_scenario": worst_case_scenario,
        "negotiation_strategy": negotiation_strategy,
    }


def _is_rental_contract(contract_type: str, text: str) -> bool:
    return bool(_RENTAL_KW.search((contract_type or "") + " " + (text or "")[:400]))


def _is_domestic_only(text: str, answers: dict[str, Any] | None) -> bool:
    ans = answers or {}
    jur_ans = str(ans.get("jurisdiction") or ans.get("governing_law") or "")
    if any(k in jur_ans for k in ("해외", "foreign", "international", "cross", "overseas")):
        return False
    foreign_markers = ("United States", "U.S.", "China", "Japan", "Singapore",
                       " LLC", " Inc.", " Ltd.", "Deutschland", "UK ", "法人")
    if any(m in (text or "") for m in foreign_markers):
        return False
    return True


def _apply_rental_filter(clause_results: list[dict[str, Any]], is_rental: bool) -> None:
    """[Rental Filter] 비렌탈 계약에서 렌탈 관련 코멘트를 Hard-Block한다."""
    if is_rental:
        return
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        combined = (cr.get("suggested_rewrite") or "") + " " + (cr.get("rewrite_reason") or "")
        if _RENTAL_COMMENT_KW.search(combined):
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["rewrite_reason"] = None
            cr["risk_tier"] = "LOW"
            cr["approval_required"] = False
            cr["high_risk"] = False
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"
            if not cr.get("guardrail_block"):
                cr["guardrail_block"] = {"filter": "rental_filter"}


_INTL_RISK_KW = re.compile(r"다국가|국제 관할|해외 집행|cross.border|준거법 중복|국외 이전|해외 법원", re.IGNORECASE)


def _apply_domestic_filter(
    clause_results: list[dict[str, Any]],
    is_domestic: bool,
    llm_meta: dict[str, Any] | None = None,
) -> None:
    """[Domestic Filter v2] 국내 전용 계약에서 dispute 조항의 국제 관할 리스크 코멘트를 차단한다.
    퍼시스가 한국 법인이더라도 상대방이 해외 법인이면 국제 거래로 처리 — 필터 미적용.
    """
    # LLM 메타데이터로 국제 거래 여부를 재확인 (domestic flag 오탐 방지)
    if llm_meta:
        if bool(llm_meta.get("is_cross_border")):
            return
        party_a_c = str(llm_meta.get("party_a_country") or "").lower()
        party_b_c = str(llm_meta.get("party_b_country") or "").lower()
        non_kr = [
            c for c in [party_a_c, party_b_c]
            if c and "korea" not in c and "한국" not in c and c not in ("", "kr")
        ]
        if non_kr:
            return
    if not is_domestic:
        return
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        ct = str(cr.get("clause_topic") or "")
        if ct != "dispute":
            continue
        combined = (cr.get("suggested_rewrite") or "") + " " + (cr.get("rewrite_reason") or "")
        if _INTL_RISK_KW.search(combined):
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"
            cr["approval_required"] = False
            cr["high_risk"] = False
            cr["rewrite_reason"] = None
            if not cr.get("guardrail_block"):
                cr["guardrail_block"] = {"filter": "domestic_filter"}


_INTEGRITY_RULES: list[tuple[str, list[str], list[str]]] = [
    ("personal_data", ["개인정보"], ["정산", "상계", "공제", "판촉비", "장려금"]),
    ("damage",        ["손해배상", "책임제한", "배상"], ["판촉비", "증빙", "광고비", "장려금"]),
]


def _apply_clause_integrity_filter(clause_results: list[dict[str, Any]]) -> None:
    """[Clause Integrity] 조항 토픽과 무관한 문구(크로스 토픽 오염)를 차단한다."""
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        ct = str(cr.get("clause_topic") or "")
        title = str(cr.get("clause_title") or "")
        sr = cr.get("suggested_rewrite") or ""
        for topic, title_hints, forbidden in _INTEGRITY_RULES:
            topic_match = (ct == topic) or any(h in title for h in title_hints)
            if not topic_match:
                continue
            blocked = [kw for kw in forbidden if kw in sr]
            if not blocked:
                continue
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["rewrite_reason"] = None
            cr["risk_tier"] = "LOW"
            cr["approval_required"] = False
            cr["high_risk"] = False
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"
            if not cr.get("guardrail_block"):
                cr["guardrail_block"] = {"filter": "clause_integrity", "blocked": blocked}


# 진짜 조항 표제("제12조(약정의 종료 및 해지)")만 매칭하고, 본문 중 정상적인
# 상호참조("제3조 제3항 또는 제4항을 위반하여")는 매칭하지 않도록 뒤에 "("가
# 오는 경우로 제한한다 — 상호참조는 계약서 어디서나 흔하고 정상적이다.
_RX_FOREIGN_ARTICLE_HEADING = re.compile(r"제\s*(\d{1,3})\s*조\s*\(")


def _apply_original_text_integrity_guard(clause_results: list[dict[str, Any]]) -> None:
    """[Original Text Integrity] 원문 인용이 다른 조항과 섞이지 않았는지 검증한다.

    복잡한 레이아웃의 PDF/DOCX에서 텍스트 추출 순서가 뒤섞이면, 한 조항의
    original_text 안에 다른 조번호의 "제N조" 표제가 그대로 섞여 들어올 수
    있다(예: 제8조 본문 뒤에 제12조 표제가 이어 붙는 경우). 이런 조항은
    "원문"으로 그대로 인용하면 실제로는 존재하지 않는 문장을 인용하는
    결과가 되므로, 다른 조번호 표제가 등장하는 지점에서 잘라내고
    extraction_integrity_risk 플래그를 남긴다. 잘라낸 결과 실질 내용이
    남지 않으면 해당 조항에 대한 자동 생성 수정안은 신뢰할 수 없으므로
    보류(guardrail_block) 처리한다.
    """
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        ot = cr.get("original_text")
        if not isinstance(ot, str) or not ot.strip():
            continue
        own_article = str(cr.get("article_number") or "").strip()
        matches = list(_RX_FOREIGN_ARTICLE_HEADING.finditer(ot))
        # Ignore a heading that appears only at the very start (that's this
        # clause's own heading, e.g. "제8조(비밀유지의무) ...").
        cut_at: int | None = None
        for m in matches:
            if m.start() <= 2:
                continue
            found_article = m.group(1)
            if own_article and found_article == own_article:
                continue
            cut_at = m.start()
            break
        if cut_at is None:
            continue
        truncated = ot[:cut_at].rstrip()
        # 원문 integrity가 낮으면(=다른 조항 표제가 섞여 들어온 경우) 그 조항에
        # 대해서는 수정안을 절대 생성하지 않는다 — 남은 텍스트 길이와 무관하게,
        # 표제가 섞였다는 사실 자체가 이 조항의 세그멘테이션을 신뢰할 수 없다는
        # 뜻이기 때문이다. UI/DOCX에는 "extraction_error"로 표시한다.
        cr["extraction_integrity_risk"] = True
        cr["extraction_error"] = True
        cr["original_text"] = (
            truncated if len(truncated) >= 15
            else (truncated or "[원문 자동추출 불확실 — 원본 문서 직접 확인 필요]")
        )
        cr["suggested_rewrite"] = None
        cr["changed_segments"] = []
        cr["risk_tier"] = "LOW"
        cr["must_fix"] = False
        cr["approval_required"] = False
        cr["high_risk"] = False
        cr["review_tier"] = "NOTE"
        cr["display_kind"] = "extraction_error"
        if not cr.get("guardrail_block"):
            cr["guardrail_block"] = {"filter": "original_text_integrity", "reason": "cross_article_contamination"}


_SIDIZ_NAMES = frozenset({"시디즈", "SIDIZ", "Sidiz", "sidiz"})


_CI_SI_CLASS_ALLOWLIST = frozenset({
    "content_production", "advertising_content_production",
    "content_production_service", "creative_agency_service",
})
_CI_SI_SIGNAL_KW = re.compile(r"CI|SI|브랜드|상표|디자인|외관|로고", re.IGNORECASE)


def _apply_sidiz_position_strategy(
    clause_results: list[dict[str, Any]],
    entity: str,
    party_role: dict[str, Any] | None,
    text: str,
    contract_class: str = "",
) -> None:
    """[Sidiz Position Strategy] 시디즈가 위탁자(갑)인 경우 전략적 조항을 주입한다."""
    if not any(s in (entity or "") for s in _SIDIZ_NAMES):
        return
    our_role = str((party_role or {}).get("our_role") or (party_role or {}).get("role") or "")
    text_head = (text or "")[:300]
    is_consignor = (
        our_role in ("supplier", "consignor", "licensor")
        or (any(s in text_head for s in _SIDIZ_NAMES) and "갑" in text_head)
    )
    if not is_consignor:
        return
    # HARD BLOCK: CI/SI 브랜드 위약벌 문구는 콘텐츠/광고/CI 제작 계약에서만 의미가
    # 있다. 이전에는 clause_topic이 "termination"이기만 하면(=계약과 무관하게 어떤
    # 해지 조항이든) 이 문구를 주입했는데, 이는 시험분석약정서 같은 계약에서
    # 원본과 전혀 무관한 CI/SI·위약벌 문구를 억지로 끼워넣는 원인이었다.
    _ci_si_class_ok = (not contract_class) or (contract_class in _CI_SI_CLASS_ALLOWLIST)

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        ct = str(cr.get("clause_topic") or "")
        title = str(cr.get("clause_title") or "")
        sr = cr.get("suggested_rewrite") or ""
        ot = str(cr.get("original_text") or "")
        base = (sr or ot).rstrip()

        # ① CI/SI 위반 → 즉시 해지권 + 위약벌
        # 계약유형이 CI/콘텐츠/광고 제작류이면서(class allow-list) 실제로 해당
        # 조항 자체가 CI/SI/브랜드/상표를 다루고 있을 때만(clause-level signal) 적용.
        _clause_is_ci_si = bool(_CI_SI_SIGNAL_KW.search(title)) or bool(_CI_SI_SIGNAL_KW.search(ot))
        if _ci_si_class_ok and _clause_is_ci_si:
            if "즉시 해지" not in base and "위약벌" not in base:
                add = (
                    "\n\n[시디즈 위탁자 보호]\n"
                    "수탁자가 CI/SI 가이드라인을 위반하거나 브랜드를 훼손한 경우, "
                    "갑(시디즈)은 사전 통지 없이 즉시 계약을 해지할 수 있으며, "
                    "수탁자는 계약금액의 [ ]%에 해당하는 위약벌을 갑에게 지급한다."
                )
                cr["suggested_rewrite"] = (base + add).strip()
                cr["suggested_direction"] = (cr.get("suggested_direction") or []) + [
                    "CI/SI 위반 즉시 해지권 확보", "브랜드 훼손 위약벌 명시",
                ]
                cr["risk_tier"] = "HIGH"
                cr["must_fix"] = True
                cr["review_tier"] = "MUST"
                cr["approval_required"] = True

        # ② 개인정보 유출 → 무제한 구상권
        elif ct == "personal_data" or "개인정보" in title:
            if "구상권" not in base:
                add = (
                    "\n\n[시디즈 위탁자 보호]\n"
                    "수탁자의 귀책으로 개인정보 유출이 발생하여 갑이 제3자·감독기관에 "
                    "배상금·과태료·과징금을 지출한 경우, 갑은 그 전액을 수탁자에게 구상할 수 있다(무제한 구상권)."
                )
                cr["suggested_rewrite"] = (base + add).strip()
                cr["suggested_direction"] = (cr.get("suggested_direction") or []) + ["개인정보 유출 무제한 구상권 확보"]
                cr["risk_tier"] = "HIGH"
                cr["must_fix"] = True
                cr["review_tier"] = "MUST"
                cr["approval_required"] = True

        # ③ 정산 이의제기 기간 → 7일
        elif ct == "payment_settlement" or any(k in title for k in ("정산", "상계", "공제", "대금")):
            if "7일" not in base:
                add = (
                    "\n\n[시디즈 위탁자 보호]\n"
                    "수탁자는 정산서 수령 후 7일 이내에 서면으로 이의를 제기하지 않으면 "
                    "해당 정산 내용에 동의한 것으로 간주하며, 이후 이의 제기는 인정하지 않는다."
                )
                cr["suggested_rewrite"] = (base + add).strip()
                cr["suggested_direction"] = (cr.get("suggested_direction") or []) + ["정산 이의제기 기간 7일로 단기 설정"]
                if cr.get("risk_tier") != "HIGH":
                    cr["risk_tier"] = "MEDIUM"
                    cr["review_tier"] = "SUGGEST"


_RX_SENT_SPLIT = re.compile(r"(?<=[다않겠다니다습니다])[.。]\s*|\n")


def _apply_global_sentence_dedup(clause_results: list[dict[str, Any]]) -> None:
    """[Global Deduplication] 동일 문장이 2회 이상 등장하면 '상기 제N조 참조'로 대체한다."""
    seen: dict[str, tuple[int, str]] = {}
    for idx, cr in enumerate(clause_results):
        if not isinstance(cr, dict):
            continue
        sr = cr.get("suggested_rewrite")
        if not isinstance(sr, str) or not sr.strip():
            continue
        sentences = [s.strip() for s in _RX_SENT_SPLIT.split(sr) if len(s.strip()) >= 20]
        new_sr = sr
        for sent in sentences:
            norm = re.sub(r"\s+", " ", sent.lower())
            if norm in seen:
                first_idx, first_art = seen[norm]
                ref = f"상기 제{first_art}조 참조" if first_art else "상기 조항 참조"
                new_sr = new_sr.replace(sent, ref, 1)
            else:
                art = str(clause_results[idx].get("article_number") or "")
                seen[norm] = (idx, art)
        if new_sr != sr:
            cr["suggested_rewrite"] = new_sr.strip()


# =============================================================================
# [Review Priority Engine] — requirement.md > Review Priority Engine
# =============================================================================

_LEVEL1_FINANCIAL_KW = re.compile(
    r"선급금|선금|착수금|선지급|결과물.{0,20}지급|지급.{0,20}결과물|"
    r"중도\s*해지|기성고|검수.{0,15}지급|지급.{0,15}검수|"
    r"미완성|환급|환수|반환.{0,10}대금|deliverable|산출물.{0,15}미제출|"
    r"납기\s*지연|일정\s*지연|지체상금|책임\s*제한.{0,15}총액|배상\s*한도",
    re.IGNORECASE,
)
# [STEP 3] LEVEL 1 추가 — 신체사고·PL·중대재해·리콜·생산중단·대규모클레임·제3자손해
_LEVEL1_PL_SAFETY_KW = re.compile(
    r"신체\s*사고|인명\s*피해|사망|부상|상해|제조물\s*책임|PL\s*보험|PL법|"
    r"중대재해|중대\s*산업사고|리콜|생산\s*중단|가동\s*중단|대규모\s*클레임|"
    r"제3자\s*손해|제3자\s*피해|소비자\s*피해|사용자\s*사고|제조물\s*결함",
    re.IGNORECASE,
)
_LEVEL2_RIGHTS_KW = re.compile(
    r"지식재산|저작권|특허|상표|IP\b|사용권|재사용|비밀유지|기밀|영업비밀",
    re.IGNORECASE,
)
_LEVEL1_TOPICS = frozenset({"payment_settlement", "termination", "cost_burden", "other"})
_LEVEL1_SAFETY_TOPICS = frozenset({"safety", "safety_compliance", "damage"})
_LEVEL2_TOPICS = frozenset({"confidentiality", "ip_ownership", "personal_data"})


def _classify_financial_risk_level(cr: dict[str, Any]) -> int:
    """[STEP 3] LEVEL 1=실제 회사 손실(신체사고·PL·중대재해 포함), 2=권리확보, 3=일반법률문구"""
    topic = str(cr.get("clause_topic") or "")
    combined = (str(cr.get("clause_title") or "") + " " + str(cr.get("original_text") or ""))[:800]
    # LEVEL 1: 신체사고·PL·중대재해·리콜·생산중단 등 실제 회사 손실
    if topic in _LEVEL1_SAFETY_TOPICS or _LEVEL1_PL_SAFETY_KW.search(combined):
        return 1
    if topic in _LEVEL1_TOPICS or _LEVEL1_FINANCIAL_KW.search(combined):
        return 1
    if topic in _LEVEL2_TOPICS or _LEVEL2_RIGHTS_KW.search(combined):
        return 2
    return 3


def _apply_review_priority_engine(clause_results: list[dict[str, Any]], max_high: int = 5) -> None:
    """requirement.md > Review Priority Engine.
    LEVEL 1 → HIGH 보장. LEVEL 3 실질 리스크 없음 → LOW 강등. HIGH 최대 max_high개.
    """
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        level = _classify_financial_risk_level(cr)
        cr["_priority_level"] = level
        tier = str(cr.get("risk_tier") or "").upper()
        # 실제로 매칭된 룰(detected_issue_list/related_rules)이 있는 조항은
        # "선언/일반 조항"이 아니라 이미 확인된 리스크다 — clause_topic이 비어
        # LEVEL 3으로 떨어지더라도(예: RuleQueryService의 KR-*/ACT-* 매칭 결과처럼
        # clause_topic을 세팅하지 않는 경로) 강제로 LOW 강등하면 false negative가 된다.
        _has_substantiated_match = bool(cr.get("detected_issue_list")) or bool(cr.get("related_rules"))
        # LEVEL 3 — 선언/일반 조항: 실질 리스크 없으면 NOTE로 강등. 단
        # common_legal_risk.py가 원문 regex로 직접 확인해 만든 finding
        # (is_common_legal_risk=True)은 제외한다 — 그 조항의 clause_topic이
        # 이 함수의 LEVEL1/2 키워드·토픽 목록에 없다는 이유만으로(예:
        # "sow_change") 실제로 확인된 리스크를 조용히 LOW 강등하면 안 된다.
        if (
            level == 3
            and tier != "HIGH"
            and not _has_substantiated_match
            and not bool(cr.get("must_fix"))
            and not bool(cr.get("user_focus_hit"))
            and not bool(cr.get("approval_required"))
            and not bool(cr.get("is_common_legal_risk"))
        ):
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"

    # HIGH 최대 max_high개: LEVEL 순 정렬 후 초과분 MEDIUM 강등
    # 체크리스트 항목(is_checklist_item=True)과 공통 법률리스크(common_legal_risk.py,
    # is_common_legal_risk=True)는 캡 계산에서 제외한다. 전자는 "없는 조항 신설"
    # 권고라 Priority 3(원칙적 제외)로 이미 별도 처리되고, 후자는 지체상금 무상한·
    # 위약벌 배수·귀책불문 해지 등 실제 존재하는 불리한 조항(Priority 1)을
    # regex로 직접 확인해 만든 고정밀 finding이므로, 임의의 개수 상한으로
    # 조용히 MEDIUM 강등하면 "실제 중요한 독소조항의 우선순위를 놓치는" 결과가
    # 된다(변호사형 전체계약 판단 지시, 2026-08-31).
    high_items = [
        cr for cr in clause_results
        if isinstance(cr, dict)
        and str(cr.get("risk_tier") or "").upper() == "HIGH"
        and not bool(cr.get("dedup_suppressed"))
        and not bool(cr.get("keep_as_is"))
        and not bool(cr.get("is_checklist_item"))
        and not bool(cr.get("is_common_legal_risk"))
    ]
    if len(high_items) > max_high:
        high_items.sort(key=lambda x: (int(x.get("_priority_level") or 3), -int(bool(x.get("must_fix"))), -int(bool(x.get("approval_required")))))
        for cr in high_items[max_high:]:
            cr["risk_tier"] = "MEDIUM"
            cr["must_fix"] = False
            cr["review_tier"] = "SUGGEST"


# =============================================================================
# [Service Contract Mandatory Checklist] — requirement.md > Service Contract Mandatory Checklist
# =============================================================================

_SVC_CHECKLIST_ITEMS: list[dict[str, Any]] = [
    {
        "id": "svc_prepayment_guarantee",
        "name": "선급금 보증 구조",
        "trigger": re.compile(r"선급금|선금|착수금", re.IGNORECASE),
        "present": re.compile(r"보증보험|이행보증|선급금\s*보증|보증증권|보증서", re.IGNORECASE),
        "risk": "HIGH",
        "rewrite": (
            "위탁자는 선급금 지급 전 수탁자로부터 선급금 상당액의 "
            "이행(선급금)보증보험증권을 제출받을 수 있다."
        ),
        "direction": "선급금 미회수 방지를 위한 보증보험증권 요구",
    },
    {
        "id": "svc_inspection_before_payment",
        "name": "검수 후 지급 구조",
        "trigger": re.compile(r"대금|용역비|자문료|보수", re.IGNORECASE),
        "present": re.compile(r"검수.{0,20}지급|검수.{0,20}완료.{0,20}후|승인.{0,20}후.{0,20}지급|완료.{0,20}확인.{0,20}지급", re.IGNORECASE),
        "risk": "HIGH",
        "rewrite": (
            "각 단계별 결과물 제출 및 위탁자의 검수·승인 완료 후 해당 단계 대금을 지급한다. "
            "위탁자는 결과물 수령일로부터 [○]영업일 이내에 검수 결과를 서면으로 통보한다."
        ),
        "direction": "검수 없는 대금 지급 구조 개선",
    },
    {
        "id": "svc_deliverable_definition",
        "name": "단계별 deliverable 정의",
        "trigger": re.compile(r"단계|phase|결과물|산출물", re.IGNORECASE),
        "present": re.compile(r"(단계|phase).{0,60}(결과물|산출물|보고서|PPT|문서).{0,30}(제출|납품|전달)", re.IGNORECASE),
        "risk": "HIGH",
        "rewrite": (
            "수탁자는 각 단계별로 다음의 결과물을 위탁자가 지정한 형태(예: 편집 가능한 파일 형식)로 "
            "제출하여야 한다. 각 단계의 결과물 명세는 [별지]에 따른다."
        ),
        "direction": "단계별 결과물 형태·범위 명시",
    },
    {
        "id": "svc_refund_on_incomplete",
        "name": "미완성 시 환수 조항",
        "trigger": re.compile(r"선급금|선금|착수금", re.IGNORECASE),
        "present": re.compile(r"미완성.{0,20}반환|환급|귀책.{0,30}반환|중도\s*해지.{0,30}정산", re.IGNORECASE),
        "risk": "HIGH",
        "rewrite": (
            "수탁자의 귀책으로 계약이 중도 종료되는 경우, 미완성 부분에 해당하는 선급금은 "
            "즉시 반환하여야 한다. 기성고 비율은 당사자 간 협의로 확정하되, "
            "합의되지 않는 경우 위탁자가 지정한 감정인의 평가에 따른다."
        ),
        "direction": "미완성·중도해지 시 선급금 환수 구조 확보",
    },
    {
        "id": "svc_delay_response",
        "name": "일정 지연 대응 조항",
        # 2026-09-04 지시(그림닷컴 판매지원 용역계약 실사례) — 기존 trigger의
        # "일정|기간" 단독 매치는 "계약 기간"처럼 사실상 모든 계약에 있는
        # 일반 문구에도 걸려, 납기 의무가 전혀 없는 계약(예: 판매수수료만
        # 정산하는 판매지원 계약)에서도 "일정 지연 대응 조항" 신설을
        # 오탐 권고했다. 이 체크리스트가 실제로 의도하는 것은 "산출물
        # 납기"이므로, 실제 이행기한을 가리키는 표현으로 좁힌다.
        "trigger": re.compile(r"납기|완료\s*일|제출\s*일|인도\s*일|이행\s*기한", re.IGNORECASE),
        "present": re.compile(r"지연.{0,20}(통보|통지|협의|연장|위약금|지체상금)|납기.{0,20}(변경|연장|위약)", re.IGNORECASE),
        "risk": "MEDIUM",
        "rewrite": (
            "수탁자가 약정 납기를 초과하는 경우, 즉시 그 사유와 예상 완료일을 위탁자에게 "
            "서면 통보하여야 한다. 수탁자 귀책의 지연에 대하여 위탁자는 지연일수에 비례한 "
            "지연손해금(일 용역비 총액의 [○]%)을 청구할 수 있다."
        ),
        "direction": "납기 지연 발생 시 통보 의무 및 패널티 구조 명시",
    },
    {
        "id": "svc_post_use_scope",
        "name": "용역 종료 후 결과물 활용 범위",
        "trigger": re.compile(r"결과물|산출물|저작물|보고서", re.IGNORECASE),
        "present": re.compile(r"종료.{0,30}(활용|이용|사용)|완료.{0,30}(활용|이용|재사용)|영구.{0,20}(사용|이용)", re.IGNORECASE),
        "risk": "MEDIUM",
        "rewrite": (
            "위탁자는 계약 종료 후에도 결과물을 사내 업무 목적으로 영구적으로 활용할 수 있으며, "
            "수탁자는 위탁자의 사전 서면 동의 없이 동일·유사 결과물을 제3자에게 제공하거나 "
            "공개적으로 발표할 수 없다."
        ),
        "direction": "계약 종료 후 결과물 활용 권리 및 수탁자 재사용 제한 명시",
    },
]


def _apply_service_contract_checklist(
    clause_results: list[dict[str, Any]],
    full_text: str,
    contract_class: str,
) -> None:
    """requirement.md > Service Contract Mandatory Checklist.
    advisory 계약에서 원문에 없는 구조를 탐지하고 추가 권고를 생성한다.
    원문에 이미 존재하는 항목은 생성하지 않는다.
    content_production 계약에서는 이 checklist를 실행하지 않는다.
    """
    if contract_class not in ("advisory",):
        return  # content_production, general 등은 이 체크리스트 실행 안 함
    text = str(full_text or "")
    existing_ids = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}

    for item in _SVC_CHECKLIST_ITEMS:
        # trigger가 원문에 없으면 해당 리스크 자체가 없음 — 생성 금지
        if not item["trigger"].search(text):
            continue
        # 이미 원문에 올바른 구조가 있으면 생성 금지
        if item["present"].search(text):
            continue
        # 이미 동일 id의 권고가 있으면 스킵
        if any(str(cr.get("clause_id") or "") == item["id"] for cr in clause_results if isinstance(cr, dict)):
            continue
        clause_results.append({
            "clause_id": item["id"],
            "article_number": None,
            "clause_title": f"[권고] {item['name']}",
            "original_text": "",
            "suggested_rewrite": None,
            "clause_topic": "payment_settlement" if "payment" in item["id"] or "prepayment" in item["id"] or "inspection" in item["id"] else "other",
            "risk_tier": item["risk"],
            "must_fix": item["risk"] == "HIGH",
            "review_tier": "MUST" if item["risk"] == "HIGH" else "SUGGEST",
            "high_risk": item["risk"] == "HIGH",
            "approval_required": item["risk"] == "HIGH",
            "rewrite_reason": item["direction"],
            "suggested_direction": [item["direction"]],
            "recommendation_text": item["rewrite"],
            "is_checklist_item": True,
            "display_kind": "guidance",
            "has_rewrite_change": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "dedup_suppressed": False,
            "keep_as_is": False,
            "_priority_level": 1 if item["risk"] == "HIGH" else 2,
        })


# =============================================================================
# [Project Installation Contract Mandatory Checklist]
# requirement.md > Project Installation Contract Architecture 참조
# =============================================================================

_PROJECT_INSTALL_SAFETY_ITEMS: list[dict[str, Any]] = [
    {
        "id": "pi_safety_responsibility",
        "name": "안전 책임 주체 명시",
        "present": re.compile(r"안전\s*책임|안전관리\s*주체|현장안전\s*책임", re.IGNORECASE),
        "direction": "시공·설치·시운전 전 과정에서 안전 책임 주체(을/수급인)를 명시하는 조항을 추가하세요.",
        "rewrite": "[추가 권고 — 안전 책임 주체]\n을(수급인)은 현장 설치·시운전 전 과정에서 산업안전보건법 및 중대재해처벌법상 안전 책임 주체임을 확인하며, 관련 의무를 성실히 이행한다.",
    },
    {
        "id": "pi_safety_manager",
        "name": "안전관리자 지정 의무",
        "present": re.compile(r"안전관리자\s*지정|안전담당자|안전관리\s*책임자", re.IGNORECASE),
        "direction": "현장 안전관리자를 지정하고 연락처를 계약서에 명시하도록 요구하세요.",
        "rewrite": "[추가 권고 — 안전관리자 지정]\n을은 현장 착공 전 안전관리자를 지정하고 성명·연락처를 갑에게 서면 통보한다. 안전관리자 교체 시 48시간 이내에 갑에게 통보한다.",
    },
    {
        "id": "pi_legal_compliance",
        "name": "산안법·중대재해처벌법 준수 의무",
        "present": re.compile(r"산업안전보건법|중대재해|산안법", re.IGNORECASE),
        "direction": "산업안전보건법 및 중대재해처벌법 준수 의무를 명시하는 조항을 추가하세요.",
        "rewrite": "[추가 권고 — 법령 준수]\n을은 산업안전보건법, 중대재해처벌법 및 관련 법령·고시를 준수하며, 위반으로 인한 모든 행정처분·손해배상 책임은 을이 부담한다.",
    },
    {
        "id": "pi_subcontractor_safety",
        "name": "하도급 안전관리 연대책임",
        "present": re.compile(r"하도급.{0,20}안전|하수급인.{0,20}안전|협력업체.{0,20}안전", re.IGNORECASE),
        "direction": "하도급·협력업체에 대한 안전관리 연대책임 조항을 추가하세요.",
        "rewrite": "[추가 권고 — 하도급 안전 연대책임]\n을은 하도급·협력업체의 안전관리에 대해 연대책임을 지며, 하도급업체가 산안법·중대재해처벌법을 위반하더라도 이는 을의 귀책사유로 본다.",
    },
    {
        "id": "pi_work_stop_right",
        "name": "긴급 작업 중지권",
        "present": re.compile(r"작업\s*중지|작업중지권|긴급\s*중지", re.IGNORECASE),
        "direction": "위험 상황 발생 시 을이 즉시 작업을 중지할 수 있는 권리를 보장하는 조항을 추가하세요.",
        "rewrite": "[추가 권고 — 긴급 작업 중지권]\n을은 중대한 위험이 발생하거나 발생할 우려가 있을 경우 즉시 작업을 중지하고 갑에게 통보할 수 있다. 정당한 작업 중지를 이유로 계약상 불이익을 부여할 수 없다.",
    },
    {
        "id": "pi_risk_assessment",
        "name": "위험성 평가 실시 의무",
        "present": re.compile(r"위험성\s*평가|리스크\s*평가|위험\s*평가", re.IGNORECASE),
        "direction": "착공 전 위험성 평가를 실시하고 그 결과를 갑에게 제출하도록 요구하는 조항을 추가하세요.",
        "rewrite": "[추가 권고 — 위험성 평가]\n을은 작업 착수 전 산업안전보건법 제36조에 따라 위험성 평가를 실시하고, 평가 결과 및 개선 계획을 갑에게 제출한다.",
    },
    {
        "id": "pi_accident_reporting",
        "name": "사고 발생 즉시 보고 의무",
        "present": re.compile(r"사고.{0,15}보고|재해.{0,15}통보|즉시.{0,10}보고", re.IGNORECASE),
        "direction": "현장 사고 발생 시 즉시 갑에게 보고하는 의무 조항을 추가하세요.",
        "rewrite": "[추가 권고 — 사고 보고 의무]\n을은 현장에서 산업재해 또는 안전사고가 발생한 경우 즉시(1시간 이내) 갑에게 구두 및 서면으로 통보하고, 재발 방지 대책을 48시간 이내에 제출한다.",
    },
    {
        "id": "pi_ppe_education",
        "name": "안전장비·교육 제공 의무",
        "present": re.compile(r"안전장비|보호구|안전교육|안전\s*훈련", re.IGNORECASE),
        "direction": "작업자에 대한 보호구 지급 및 안전교육 실시 의무를 명시하는 조항을 추가하세요.",
        "rewrite": "[추가 권고 — 보호구 및 안전교육]\n을은 현장 작업자에게 적합한 보호구를 지급하고, 작업 착수 전 안전교육을 실시한다. 교육 일시·참석자 명단을 갑에게 제출한다.",
    },
    {
        "id": "pi_access_control",
        "name": "현장 출입 통제 및 구역 관리",
        "present": re.compile(r"출입\s*통제|출입\s*관리|현장\s*출입|구역\s*관리|펜스|안전\s*구역", re.IGNORECASE),
        "direction": "현장 출입 통제 및 위험 구역 관리 방안을 계약서에 명시하세요.",
        "rewrite": "[추가 권고 — 현장 출입 통제]\n을은 작업 구역에 안전 펜스·표지판을 설치하고 비인가자의 출입을 통제한다. 갑의 사전 승인 없이 제3자의 현장 접근을 허용하지 않는다.",
    },
    {
        "id": "pi_commissioning_accident_liability",
        "name": "시운전 중 사고 책임 귀속",
        "present": re.compile(r"시운전.{0,20}사고|시운전.{0,20}책임|시운전.{0,20}손해", re.IGNORECASE),
        "direction": "시운전 중 발생하는 사고·손해에 대한 책임 귀속을 명확히 하는 조항을 추가하세요.",
        "rewrite": "[추가 권고 — 시운전 중 사고 책임]\n시운전 기간 중 을의 작업·설비로 인해 발생한 인적·물적 사고의 손해배상 책임은 을에게 귀속된다. 단, 갑의 지시 또는 제공 자재의 결함으로 인한 경우에는 갑이 책임을 분담한다.",
    },
]

_PROJECT_INSTALL_TRAINING_ITEMS: list[dict[str, Any]] = [
    {
        "id": "pi_train_user",
        "name": "사용자 교육 제공 의무",
        "risk": "HIGH",
        "present": re.compile(r"사용자\s*교육|운용자\s*교육|오퍼레이터\s*교육|user\s*training", re.IGNORECASE),
        "direction": "설치 완료 후 사용자(운용자)에 대한 교육 제공 의무를 명시하세요.",
        "rewrite": "[추가 권고 — 사용자 교육]\n을은 설비 인수인계 전 갑의 운용 담당자를 대상으로 사용자 교육을 실시하고 교육 확인서를 제출한다.",
    },
    {
        "id": "pi_train_admin",
        "name": "관리자 교육 제공 의무",
        "risk": "HIGH",
        "present": re.compile(r"관리자\s*교육|admin\s*training|시스템\s*관리\s*교육", re.IGNORECASE),
        "direction": "시스템 관리자 교육 제공 의무를 명시하세요.",
        "rewrite": "[추가 권고 — 관리자 교육]\n을은 시스템 관리자를 대상으로 설정·운영·장애 처리 방법에 대한 관리자 교육을 실시한다.",
    },
    {
        "id": "pi_train_maintenance",
        "name": "유지보수 담당자 교육 의무",
        "risk": "MEDIUM",
        "present": re.compile(r"유지보수\s*교육|정비\s*교육|maintenance\s*training", re.IGNORECASE),
        "direction": "유지보수 담당자를 위한 정비·점검 방법 교육 의무를 명시하세요.",
        "rewrite": "[추가 권고 — 유지보수 교육]\n을은 갑의 유지보수 담당자를 대상으로 일상 점검, 소모품 교체, 고장 진단 방법에 대한 교육을 제공한다.",
    },
    {
        "id": "pi_train_emergency",
        "name": "비상 대응 절차 교육 의무",
        "risk": "HIGH",
        "present": re.compile(r"비상\s*대응\s*교육|긴급\s*절차\s*교육|emergency\s*training|비상\s*정지", re.IGNORECASE),
        "direction": "비상 정지·긴급 대응 절차에 대한 교육 의무를 명시하세요.",
        "rewrite": "[추가 권고 — 비상 대응 교육]\n을은 설비 비상 정지, 화재·사고 시 긴급 대응 절차를 포함한 비상 대응 교육을 실시하고 교육 자료를 갑에게 제공한다.",
    },
    {
        "id": "pi_ops_manual",
        "name": "운용 매뉴얼 납품 의무",
        "risk": "HIGH",
        "present": re.compile(r"운용\s*매뉴얼|운영\s*매뉴얼|사용\s*설명서|operations\s*manual", re.IGNORECASE),
        "direction": "설비 운용 매뉴얼(운영 설명서)을 납품 의무로 계약에 명시하세요.",
        "rewrite": "[추가 권고 — 운용 매뉴얼 납품]\n을은 최종 인수인계 시 설비 운용 매뉴얼을 인쇄본 및 디지털 파일 형태로 갑에게 납품한다. 매뉴얼에는 정상 운전, 비상 정지, 유지보수 절차가 포함되어야 한다.",
    },
    {
        "id": "pi_korean_manual",
        "name": "한국어 매뉴얼 제공 의무",
        "risk": "MEDIUM",
        "present": re.compile(r"한국어\s*매뉴얼|한글\s*매뉴얼|국문\s*매뉴얼|Korean\s*manual", re.IGNORECASE),
        "direction": "모든 매뉴얼 및 교육 자료를 한국어로 제공하도록 요구하세요.",
        "rewrite": "[추가 권고 — 한국어 매뉴얼]\n을이 제공하는 모든 매뉴얼, 교육 자료, 도면은 한국어로 작성·제공되어야 한다. 외국어 원본이 있는 경우 한국어 번역본을 병기한다.",
    },
    {
        "id": "pi_retrain_support",
        "name": "재교육 지원 의무",
        "risk": "MEDIUM",
        "present": re.compile(r"재교육|추가\s*교육\s*지원|교육\s*재실시", re.IGNORECASE),
        "direction": "인수 후 일정 기간 내 재교육 지원 의무를 명시하세요.",
        "rewrite": "[추가 권고 — 재교육 지원]\n을은 인수인계 완료 후 6개월 이내에 갑이 요청할 경우 1회에 한하여 추가 교육을 무상으로 제공한다.",
    },
    {
        "id": "pi_sla",
        "name": "유지보수 SLA (서비스 수준 협약)",
        "risk": "MEDIUM",
        "present": re.compile(r"SLA|서비스\s*수준|응답\s*시간|장애\s*복구\s*시간|유지보수\s*기간", re.IGNORECASE),
        "direction": "고장 대응 시간, 복구 목표 시간 등 유지보수 SLA를 계약서에 명시하세요.",
        "rewrite": "[추가 권고 — 유지보수 SLA]\n을은 장애 발생 신고 후 4시간 이내 현장 도착(원격 지원은 1시간 이내 개시), 24시간 이내 복구를 목표로 한다. SLA 미달 시 지체상금에 준하는 배상 기준을 적용한다.",
    },
]


def _apply_project_installation_checklist(
    clause_results: list[dict[str, Any]],
    full_text: str,
    contract_class: str,
) -> None:
    """requirement.md > Project Installation Contract Architecture.
    project_installation 계약에서 안전·교육 항목 누락을 탐지하고 권고를 생성한다.
    """
    if contract_class != "project_installation":
        return
    text = str(full_text or "")

    for item in _PROJECT_INSTALL_SAFETY_ITEMS:
        if any(str(cr.get("clause_id") or "") == item["id"] for cr in clause_results if isinstance(cr, dict)):
            continue
        if item["present"].search(text):
            continue
        clause_results.append({
            "clause_id": item["id"],
            "article_number": None,
            "clause_title": f"[안전권고] {item['name']}",
            "original_text": "",
            "suggested_rewrite": None,
            "clause_topic": "safety_compliance",
            "risk_tier": "HIGH",
            "must_fix": True,
            "review_tier": "MUST",
            "high_risk": True,
            "approval_required": True,
            "rewrite_reason": item["direction"],
            "suggested_direction": [item["direction"]],
            "recommendation_text": item["rewrite"],
            "is_checklist_item": True,
            "display_kind": "guidance",
            "has_rewrite_change": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "dedup_suppressed": False,
            "keep_as_is": False,
            "_priority_level": 1,
        })

    for item in _PROJECT_INSTALL_TRAINING_ITEMS:
        if any(str(cr.get("clause_id") or "") == item["id"] for cr in clause_results if isinstance(cr, dict)):
            continue
        if item["present"].search(text):
            continue
        risk = item["risk"]
        clause_results.append({
            "clause_id": item["id"],
            "article_number": None,
            "clause_title": f"[교육권고] {item['name']}",
            "original_text": "",
            "suggested_rewrite": None,
            "clause_topic": "training_operations",
            "risk_tier": risk,
            "must_fix": risk == "HIGH",
            "review_tier": "MUST" if risk == "HIGH" else "SUGGEST",
            "high_risk": risk == "HIGH",
            "approval_required": risk == "HIGH",
            "rewrite_reason": item["direction"],
            "suggested_direction": [item["direction"]],
            "recommendation_text": item["rewrite"],
            "is_checklist_item": True,
            "display_kind": "guidance",
            "has_rewrite_change": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "dedup_suppressed": False,
            "keep_as_is": False,
            "_priority_level": 1 if risk == "HIGH" else 2,
        })


# =============================================================================
# [STEP 4] Industry-Specific Legal Reasoning — requirement.md > STEP 4
# 가구·설비·제조물 계약 12개 항목 자동 점검
# =============================================================================

_INDUSTRY_SPECIFIC_ITEMS: list[dict[str, Any]] = [
    {
        "id": "isr_pl_defect_liability",
        "name": "제조물 결함 책임 귀속",
        "present": re.compile(r"제조물\s*(결함|책임)|결함\s*책임|PL\s*책임", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "제조물 결함으로 인한 손해에 대한 책임 귀속 조항을 명시하세요.",
        "rewrite": (
            "[추가 권고 — 제조물 결함 책임]\n"
            "공급자는 제공한 물품의 제조상·설계상·표시상 결함으로 인한 손해에 대해 책임을 지며, "
            "제조물책임법 제3조에 따른 입증 책임은 피해자에게 있음을 명시한다."
        ),
    },
    {
        "id": "isr_installation_defect",
        "name": "설치 하자 책임 귀속",
        "present": re.compile(r"설치\s*하자|설치\s*결함|설치\s*불량|시공\s*하자", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "설치 하자로 인한 손해에 대한 책임 귀속 조항을 추가하세요.",
        "rewrite": (
            "[추가 권고 — 설치 하자 책임]\n"
            "설치 과정의 하자(오설치·부실 시공)로 발생한 손해는 공급자(설치자)가 책임지며, "
            "발주자의 지시나 제공 자재의 결함으로 인한 경우에는 발주자가 책임을 부담한다."
        ),
    },
    {
        "id": "isr_user_safety",
        "name": "사용자 안전 보호 조항",
        "present": re.compile(r"사용자\s*안전|안전\s*보호|이용자\s*안전|소비자\s*안전", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "사용자 안전 보호를 위한 조항을 추가하세요.",
        "rewrite": (
            "[추가 권고 — 사용자 안전 보호]\n"
            "공급자는 제품 사용 중 예상 가능한 위험에 대해 적절한 경고 표시 및 안전 조치를 제공하여야 하며, "
            "사용자의 안전을 위해 합리적인 주의 의무를 이행한다."
        ),
    },
    {
        "id": "isr_manual_warning",
        "name": "경고문구·사용자 매뉴얼 제공 의무",
        "present": re.compile(r"사용설명서|매뉴얼|경고문|안내서|취급설명|주의사항", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "경고문구 및 사용자 매뉴얼 제공 의무를 계약서에 명시하세요.",
        "rewrite": (
            "[추가 권고 — 경고문구·매뉴얼 제공]\n"
            "공급자는 납품 시 한국어로 작성된 사용설명서, 경고문구, 안전 주의사항을 제공하며, "
            "제조물책임법상 표시상 결함 방어를 위한 적절한 경고 표시를 부착한다."
        ),
    },
    {
        "id": "isr_safety_certification",
        "name": "안전 인증 완료 보증",
        "present": re.compile(r"안전\s*인증|KC\s*인증|CE\s*인증|UL\s*인증|형식\s*승인|안전\s*검사", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "관련 법령에 따른 안전 인증 완료 보증 조항을 추가하세요.",
        "rewrite": (
            "[추가 권고 — 안전 인증 보증]\n"
            "공급자는 납품 물품이 관련 법령에 따른 안전 인증(KC, CE 등)을 완료하였음을 보증하며, "
            "인증 관련 서류를 납품 시 제공한다."
        ),
    },
    {
        "id": "isr_recall_procedure",
        "name": "리콜 절차 및 비용 부담",
        "present": re.compile(r"리콜|결함\s*회수|제품\s*회수|자발적\s*회수", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "결함 발견 시 리콜 절차 및 비용 부담 기준을 계약서에 명시하세요.",
        "rewrite": (
            "[추가 권고 — 리콜 절차]\n"
            "공급자 귀책의 결함 발견 시, 공급자는 리콜 또는 교환·수리 조치를 취하며, "
            "관련 비용(회수·수리·재납품·고객 통지 비용)은 공급자가 부담한다."
        ),
    },
    {
        "id": "isr_pl_insurance",
        "name": "PL보험 가입 의무",
        "present": re.compile(r"PL\s*보험|제조물\s*책임\s*보험|배상\s*책임\s*보험|생산물\s*배상", re.IGNORECASE),
        "risk": "MEDIUM",
        "direction": "제조물 책임보험(PL보험) 가입 의무 및 최소 보상 한도를 명시하세요.",
        "rewrite": (
            "[추가 권고 — PL보험 가입]\n"
            "공급자는 계약 기간 중 제조물 책임보험(PL보험)을 유지하며, "
            "요청 시 보험증서를 제출한다."
        ),
    },
    {
        "id": "isr_third_party_damage",
        "name": "제3자 손해 배상 책임",
        "present": re.compile(r"제3자\s*손해|제3자\s*피해|제3자\s*배상|이용자\s*손해", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "공급 물품으로 인한 제3자 손해에 대한 배상 책임 조항을 추가하세요.",
        "rewrite": (
            "[추가 권고 — 제3자 손해 배상]\n"
            "공급자의 귀책으로 공급 물품이 제3자에게 신체적·재산적 손해를 야기한 경우, "
            "공급자는 해당 손해를 배상할 책임을 진다."
        ),
    },
    {
        "id": "isr_maintenance",
        "name": "유지보수 및 정기점검 의무",
        "present": re.compile(r"유지보수|정기\s*점검|A/S|AS\b|사후\s*관리|예방\s*정비", re.IGNORECASE),
        "risk": "MEDIUM",
        "direction": "납품 후 유지보수 및 정기 점검 의무를 계약서에 명시하세요.",
        "rewrite": (
            "[추가 권고 — 유지보수·정기점검]\n"
            "공급자는 납품 후 보증 기간 내 무상 유지보수를 제공하며, "
            "연 [○]회 이상의 정기 점검을 실시한다."
        ),
    },
    {
        "id": "isr_defect_sla",
        "name": "하자 대응 SLA",
        "present": re.compile(r"SLA|하자\s*대응\s*시간|응답\s*시간|복구\s*시간|장애\s*대응", re.IGNORECASE),
        "risk": "MEDIUM",
        "direction": "하자·장애 발생 시 응답 및 복구 목표 시간(SLA)을 계약서에 명시하세요.",
        "rewrite": (
            "[추가 권고 — 하자 대응 SLA]\n"
            "공급자는 하자 신고 후 [○]시간 이내 현장 도착 또는 원격 지원을 개시하고, "
            "[○]시간 이내 복구를 목표로 한다."
        ),
    },
    {
        "id": "isr_accident_reporting",
        "name": "사고 발생 즉시 보고 의무",
        "present": re.compile(r"사고.{0,15}보고|사고.{0,15}통보|즉시.{0,10}보고|즉시.{0,10}통지", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "제품 사용 중 사고 발생 시 즉시 보고 의무를 계약서에 명시하세요.",
        "rewrite": (
            "[추가 권고 — 사고 발생 보고 의무]\n"
            "공급자는 납품 물품과 관련한 사고 또는 결함 정보를 인지한 즉시 발주자에게 통보하고, "
            "재발 방지 계획을 [○]일 이내에 서면으로 제출한다."
        ),
    },
    {
        "id": "isr_defect_correction",
        "name": "결함 발견 시 시정 조치 의무",
        "present": re.compile(r"결함\s*시정|개선\s*조치|시정\s*명령|결함\s*조치|불량\s*시정", re.IGNORECASE),
        "risk": "HIGH",
        "direction": "결함 발견 시 시정 조치 의무 및 기한을 계약서에 명시하세요.",
        "rewrite": (
            "[추가 권고 — 결함 시정 의무]\n"
            "공급자는 결함 발견 시 발주자에게 즉시 통보하고, "
            "[○]일 이내에 교환·수리·개선 등 시정 조치를 완료하여야 한다."
        ),
    },
]


def _apply_checklist_item_priority_demotion(
    clause_results: list[dict[str, Any]],
    focus_topics: set[str] | None,
    derived_topics: set[str] | None,
) -> None:
    """requirement.md > 변호사형 전체계약 판단 (2026-08-31 지시).

    체크리스트 injector(서비스/프로젝트설치 안전·교육/제조물/공급자보호 +
    content_production 4~5곳)가 만드는 finding은 전부 "계약서에 없는 조항을
    신설하라"는 권고다 — 실제 존재하는 불리한 조항(Priority 1)보다 후순위인
    Priority 2이며, 사용자가 그 주제를 직접 요청하지 않았다면 원칙적으로
    결과에서 제외한다(Priority 3). PL보험 가입, 사고 즉시 보고, 사용자
    매뉴얼, 안전인증 보증처럼 우리 회사의 새 의무를 자진해서 추가하는 제안을
    기본 출력에 올리지 않기 위함 — "리스크를 줄이는 목적"과 정면으로
    충돌하기 때문. 사용자가 review_focus로 해당 주제를 직접 물어본 경우
    (user_focus_hit/factual_hit/clause_topic 일치) 또는 mandatory 항목인
    경우에만 원래 등급을 유지한다.
    """
    wanted_topics = set(focus_topics or ()) | set(derived_topics or ())
    for cr in clause_results:
        if not isinstance(cr, dict) or not bool(cr.get("is_checklist_item")):
            continue
        if bool(cr.get("user_focus_hit")) or bool(cr.get("factual_hit")) or bool(cr.get("is_mandatory")):
            continue
        topic = str(cr.get("clause_topic") or "")
        if topic and topic in wanted_topics:
            continue
        cr["risk_tier"] = "LOW"
        cr["severity"] = "LOW"
        cr["must_fix"] = False
        cr["high_risk"] = False
        cr["approval_required"] = False
        cr["review_tier"] = "NOTE"
        cr["_priority_level"] = 3
        cr["_checklist_demoted"] = True


def _has_tangible_goods_obligation_signal(
    legal_map: dict[str, Any] | None,
    contract_class: str,
    contract_nature: str,
    canonical_type_code: str = "",
) -> bool:
    """실제로 물품·제조물·설치 급부 의무가 있는 계약에서만 True를 반환한다.

    canonical_type_code == "nda_confidentiality"는 단순 이름 매칭이 아니라
    contract_classifier.py가 여러 구조 신호(제목/정의조항/반환폐기 등)로
    확정한 canonical 판정이다 — NDA는 구조상 물품공급·제조·설치 의무 자체가
    성립할 수 없으므로, AI 유무와 무관하게 항상 차단한다(원문 서두의
    프로젝트 설명에 "가구 구매 및 설치"가 언급되어 전체텍스트 스캔이
    오탐한 실사례, 2026-09-01).

    NDA 외의 다른 유형(자문/라이선스/임대차/투자계약 등)에 대해서는 이름을
    하드코딩하지 않는다 — 대신 Contract Legal Map이 실제 AI로 계약 전체를
    읽은 경우(_legal_map_source == "ai"), 그 primary_obligations/key_
    deliverables/contract_purpose 요약에 물품/설치 신호가 있는지를 기존
    전체텍스트 스캔 결과와 AND로 교차검증해, 전체텍스트 스캔만으로는 잡지
    못하는 다른 유형의 오탐도 걸러낸다. AI가 없으면(regex 축소판은
    부정확할 수 있어) 기존 전체텍스트 스캔 결과를 그대로 신뢰한다.
    """
    if canonical_type_code == "nda_confidentiality":
        return False
    text_scan_says_yes = contract_class == "project_installation" or contract_nature == "제조물공급"
    lm = legal_map or {}
    if lm.get("_legal_map_source") == "ai":
        lm_text = " ".join(str(lm.get(k) or "") for k in ("primary_obligations", "key_deliverables", "contract_purpose"))
        lm_says_yes = bool(_NATURE_PRODUCT_SUPPLY_KW.search(lm_text) or _SUBSTANCE_TANGIBLE_KW.search(lm_text))
        return text_scan_says_yes and lm_says_yes
    return text_scan_says_yes


def _apply_industry_specific_review(
    clause_results: list[dict[str, Any]],
    full_text: str,
    contract_class: str,
    contract_nature: str,
    contract_type_code: str = "",
    legal_map: dict[str, Any] | None = None,
) -> None:
    """[STEP 4] 가구·설비·제조물 계약 12개 항목 자동 점검.
    Contract Legal Map상 실제 물품·제조·설치 급부가 있는 계약에서만
    누락 항목을 탐지한다. dealer_rental_service_contract는 제조물/산업
    안전 항목이 구조상 불필요하므로 완전 스킵.
    """
    if contract_type_code == "dealer_rental_service_contract":
        return
    if not _has_tangible_goods_obligation_signal(legal_map, contract_class, contract_nature, contract_type_code):
        return
    text = str(full_text or "")

    for item in _INDUSTRY_SPECIFIC_ITEMS:
        if any(str(cr.get("clause_id") or "") == item["id"] for cr in clause_results if isinstance(cr, dict)):
            continue
        if item["present"].search(text):
            continue
        risk = item["risk"]
        clause_results.append({
            "clause_id": item["id"],
            "article_number": None,
            "clause_title": f"[제조물검토] {item['name']}",
            "original_text": "",
            "suggested_rewrite": None,
            "clause_topic": "damage" if risk == "HIGH" else "other",
            "risk_tier": risk,
            "must_fix": risk == "HIGH",
            "review_tier": "MUST" if risk == "HIGH" else "SUGGEST",
            "high_risk": risk == "HIGH",
            "approval_required": risk == "HIGH",
            "rewrite_reason": item["direction"],
            "suggested_direction": [item["direction"]],
            "recommendation_text": item["rewrite"],
            "is_checklist_item": True,
            "display_kind": "guidance",
            "has_rewrite_change": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "dedup_suppressed": False,
            "keep_as_is": False,
            "_priority_level": 1 if risk == "HIGH" else 2,
        })


# =============================================================================
# [No Inline Rewrite Policy] — requirement.md > Output Format Policy
# =============================================================================

def _apply_no_inline_rewrite_policy(
    clause_results: list[dict[str, Any]],
    is_advisory: bool,
) -> None:
    """requirement.md > Output Format Policy — No Inline Rewrite.
    advisory 계약: suggested_rewrite = 원문 보존 + [추가 권고] 블록 append.
    원문 삭제·치환 세그먼트(deleted_segment) 생성 금지.
    기존 [추가] 블록을 [추가 권고] 포맷으로 정규화.
    """
    if not is_advisory:
        return
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("is_checklist_item")):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        sr = cr.get("suggested_rewrite")
        ot = str(cr.get("original_text") or "").strip()
        if not isinstance(sr, str) or not sr.strip():
            continue
        # 기존 [추가] → [추가 권고] 정규화
        sr = re.sub(r"\[추가\]", "[추가 권고]", sr)
        # 원문과 다른 경우: 원문 보존 + [추가 권고] 블록 형태로 재구성
        sr_norm = re.sub(r"\s+", " ", sr.strip())
        ot_norm = re.sub(r"\s+", " ", ot)
        if ot_norm and sr_norm and not sr_norm.startswith(ot_norm[:min(60, len(ot_norm))]):
            # suggested_rewrite가 원문으로 시작하지 않음 → 원문 + 권고 형태로 재구성
            # 단, [추가 권고] 블록만 있는 경우는 그대로 유지
            if "[추가 권고]" not in sr and "[수정 제안" not in sr:
                cr["suggested_rewrite"] = ot + "\n\n[추가 권고]\n" + sr.strip()
        else:
            cr["suggested_rewrite"] = sr
        # change_record의 deleted_segment 제거 (원문 삭제 표시 금지)
        rec = cr.get("change_record")
        if isinstance(rec, dict):
            rec["deleted_segment"] = []
            rec["moved_or_omitted_segment"] = []


# =============================================================================
# [Expert Advisory Review Logic] — requirement.md > [Expert Advisory Review Logic] 참조
# =============================================================================

_ADVISORY_CONTRACT_KW2 = re.compile(
    r"자문|용역|개발|제작|Advisory|Service|교수|강의|집필|연구용역|컨설팅|Consulting|위임|Engagement"
    r"|디자인\s*용역|컨텐츠\s*제작|개발\s*용역",
    re.IGNORECASE,
)
_RENTAL_CONTRACT_KW2 = re.compile(r"렌탈|임대차|Lease|구독", re.IGNORECASE)
_CONSTRUCTION_CONTRACT_KW = re.compile(r"공사|인테리어|시공|건설|리모델링", re.IGNORECASE)
_PROJECT_INSTALL_KW = re.compile(
    r"설치|시운전|현장\s*작업|자동화\s*설비|생산\s*라인|공장|SmartFactory|Smart\s*Factory"
    r"|\bcommissioning\b|\bsetup\b|\bintegration\b",
    re.IGNORECASE,
)
_LARGE_PAYMENT_KW = re.compile(r"1억|1,0\d\d,0\d\d|100,000,000|일억|대가.{0,8}억|용역비.{0,8}억|자문료.{0,8}억", re.IGNORECASE)

_IP_CLAUSE_TITLES = ("지식재산권", "저작권", "성과물", "결과물", "산출물", "지재권", "IP", "소유권")
# IP 본문 탐지: 결과물/산출물 단독으로는 IP 조항으로 판단하지 않음
_IP_BODY_EXPLICIT_KW = re.compile(r"지식재산권|저작권|지재권|\bIP\b|특허|상표", re.IGNORECASE)
_IP_CONTRACTOR_KW = re.compile(
    r"수탁자에게\s*귀속|을에게\s*귀속|교수에게\s*귀속|저작권.{0,15}을이\s*보유|이용권만.{0,10}부여"
    r"|비독점.{0,10}이용|퍼시스.{0,10}이용권만|수탁자가\s*소유",
    re.IGNORECASE,
)
_IP_WARRANTY_KW = re.compile(
    r"제3자.{0,20}권리.{0,20}침해.{0,20}보증|제3자.{0,20}침해.{0,20}면책|침해.{0,20}수탁자.{0,20}책임",
    re.IGNORECASE,
)

_IP_FURSYS_REWRITE = (
    "\n\n[수정 제안 — IP 귀속]\n"
    "① 본 계약에 따라 수탁자가 작성·제작·개발한 모든 결과물(보고서, 데이터, 설계도, 저작물 등)의 "
    "저작권 및 지식재산권은 완성과 동시에 위탁자(퍼시스)에게 전적으로 귀속된다.\n"
    "② 수탁자는 위탁자의 서면 동의 없이 결과물을 제3자에게 공개·제공·이용허락하거나 "
    "자신의 명의로 등록·출원할 수 없다.\n"
    "③ 위탁자는 결과물을 상업적 목적을 포함하여 독점적·무제한으로 이용할 수 있다.\n"
)

_IP_WARRANTY_REWRITE = (
    "\n\n[수정 제안 — 제3자 권리 침해 보증]\n"
    "① 수탁자는 결과물이 제3자의 저작권·특허권·상표권 등 지식재산권을 침해하지 않음을 보증한다.\n"
    "② 제3자의 권리 침해로 인해 위탁자에게 분쟁·손해·비용이 발생한 경우, "
    "수탁자는 자신의 비용과 책임으로 위탁자를 면책하고 모든 손해를 배상한다.\n"
    "③ 수탁자는 외부 소재(오픈소스, 무료 이미지 등) 활용 시 라이선스 조건을 위탁자에게 사전 고지한다.\n"
)

# 배상 한도 탐지: 용역대금 총액·계약금액 등으로 제한하는 패턴
_LIABILITY_CAP_KW = re.compile(
    r"(용역|대가|계약금|자문료|보수).{0,25}(총액|한도|이내|초과하지|범위로|제한)",
    re.IGNORECASE,
)
# 배상 한도 예외 단서가 이미 있는지 확인
_LIABILITY_EXCEPTION_KW = re.compile(
    r"지재권\s*침해|지식재산권\s*침해|비밀유지.{0,10}위반|고의.{0,5}중과실",
    re.IGNORECASE,
)
_LIABILITY_CAP_EXCEPTION_REWRITE = (
    "\n\n[수정 제안 — 배상 한도 예외 단서]\n"
    "단, 아래 각 호의 경우에는 위 배상 한도의 제한을 받지 아니하며, "
    "수탁자는 실제 발생한 손해 전액을 배상한다.\n"
    "① 지식재산권(저작권·특허권·상표권 등) 침해로 인한 손해\n"
    "② 비밀유지의무 위반으로 인한 손해\n"
    "③ 수탁자의 고의 또는 중과실로 인한 손해\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# [STEP 1] Contract Type Reasoning Engine — requirement.md > STEP 1
# 경제적 실질 9개 질문 기반 계약 유형 확정 (키워드 단독 분류 금지)
# ─────────────────────────────────────────────────────────────────────────────

_SUBSTANCE_TANGIBLE_KW = re.compile(
    r"물품|제품|가구|설비|장비|기계|자재|부품|완제품|완성품|납품|공급", re.IGNORECASE
)
_SUBSTANCE_INSTALL_KW = re.compile(
    r"설치|시운전|시공|현장\s*작업|공장|생산\s*라인|commissioning|setup|installation", re.IGNORECASE
)
_SUBSTANCE_ACCIDENT_KW = re.compile(
    r"사고|손상|파손|고장|결함|폭발|화재|감전|낙하|끼임|안전|위험|PL|제조물", re.IGNORECASE
)
_SUBSTANCE_OPS_KW = re.compile(
    r"운영\s*인력|KPI|상시\s*업무|운영\s*대행|위탁\s*운영|매장\s*운영|운영\s*용역", re.IGNORECASE
)
_SUBSTANCE_CONTINUOUS_KW = re.compile(
    r"월\s*단위|월정\s*요금|구독|SaaS|지속적\s*서비스|상시\s*지원|운영\s*기간", re.IGNORECASE
)
_SUBSTANCE_PRODUCT_SYS_KW = re.compile(
    r"제조물|설비|시스템|자동화|생산\s*라인|Smart\s*Factory|SmartFactory", re.IGNORECASE
)
_SUBSTANCE_THIRD_PARTY_KW = re.compile(
    r"제3자|제3인|사용자\s*피해|고객\s*피해|이용자\s*피해|타인\s*손해", re.IGNORECASE
)

# 계약 실질(법적 성격) 분류 — 적용 법령 결정에 사용
_NATURE_PRODUCT_SUPPLY_KW = re.compile(
    r"제조물|물품\s*(공급|납품|판매)|설비\s*(공급|납품)|장비\s*(공급|납품)", re.IGNORECASE
)
_NATURE_CONSTRUCTION_KW = re.compile(
    r"도급|공사|건설|시공|인테리어|리모델링", re.IGNORECASE
)


def _classify_contract_nature(contract_type: str, text: str) -> str:
    """[Contextual Awareness] 계약의 법적 실질을 선언한다.
    Returns: "제조물공급" | "도급" | "매매"
    적용 지배 법령 결정에 사용.
    """
    haystack = (contract_type or "") + " " + (text or "")[:600]
    if _NATURE_PRODUCT_SUPPLY_KW.search(haystack) and (
        _SUBSTANCE_INSTALL_KW.search(haystack) or _SUBSTANCE_ACCIDENT_KW.search(haystack)
    ):
        return "제조물공급"
    if _NATURE_CONSTRUCTION_KW.search(haystack):
        return "도급"
    if _SUBSTANCE_TANGIBLE_KW.search(haystack):
        return "매매"
    return "도급"


_CONTENT_PRODUCTION_KW = re.compile(
    r"콘텐츠\s*제작|광고\s*콘텐츠|제품\s*광고|콘텐츠\s*제작\s*대행"
    r"|콘텐츠의\s*제출\s*및\s*검수|소유권의\s*귀속"
    r"|저작재산권|저작권.*이전|촬영|콘티|시안|제작\s*견적서"
    r"|유상.*폰트|이미지.*비용|초상권|모델",
    re.IGNORECASE,
)
_AI_SEARCH_SPECIFIC_KW = re.compile(
    r"AI\s*검색|검색\s*노출|검색\s*최적화|\bSEO\b|\bGEO\b|\bAEO\b|생성형\s*AI\s*검색"
    r"|검색\s*알고리즘|키워드\s*광고|LLM\s*기반\s*검색",
    re.IGNORECASE,
)


def _classify_contract_type_by_substance(
    contract_type: str,
    text: str,
    filename: str | None,
) -> str:
    """[STEP 1 + EMERGENCY PATCH 2] 4단계 계약 유형 확정 엔진.
    Stage 0: Content production detection (NEW — must run first)
    Stage 1: 계약 목적 (유형물/무형/인력/자문/시스템/설치공사/유지보수)
    Stage 2: 핵심 의무 (제조납품/설치/인력투입/자문제공/시스템개발)
    Stage 3: 대가 구조 (제품대금/운영비/인건비/프로젝트비/라이선스)
    Stage 4: 운영 개입 여부 (7개 조건 ALL 충족 시에만 ops_outsourcing)
    Returns: "content_production" | "advisory" | "rental" | "construction" | "project_installation" | "general"
    """
    haystack = (contract_type or "") + " " + (filename or "") + " " + (text or "")[:600]

    # ── Stage 0: Content production detection — MUST run before advisory check ─
    # Key: "광고" alone should NOT trigger ai_search_marketing; needs content production signals.
    has_content_production = bool(_CONTENT_PRODUCTION_KW.search(haystack))
    has_ai_search_specific = bool(_AI_SEARCH_SPECIFIC_KW.search(haystack))
    if has_content_production and not has_ai_search_specific:
        return "content_production"

    # ── Stage 1: 계약 목적 ───────────────────────────────────────────────────
    is_tangible = bool(_SUBSTANCE_TANGIBLE_KW.search(haystack))
    has_installation = bool(_SUBSTANCE_INSTALL_KW.search(haystack))
    accident_possible = bool(_SUBSTANCE_ACCIDENT_KW.search(haystack))
    is_product_system = bool(_SUBSTANCE_PRODUCT_SYS_KW.search(haystack))
    is_advisory_type = bool(_ADVISORY_CONTRACT_KW2.search(haystack))
    is_rental_type = bool(_RENTAL_CONTRACT_KW2.search(haystack))
    is_construction_type = bool(_CONSTRUCTION_CONTRACT_KW.search(haystack))

    # ── Stage 2: 핵심 의무 판단 ─────────────────────────────────────────────
    # 물품 + 설치 + 사고 가능 → 설치형 제조물 공급
    if (is_tangible or is_product_system) and has_installation and accident_possible:
        return "project_installation"
    # project_installation KW fallback
    if _PROJECT_INSTALL_KW.search(haystack):
        return "project_installation"

    # ── Stage 3: 대가 구조 판단 ─────────────────────────────────────────────
    # 월정 요금/구독/지속적 서비스: advisory 또는 rental 후보
    is_continuous = bool(_SUBSTANCE_CONTINUOUS_KW.search(haystack))

    # ── Stage 4: 운영 개입 여부 — ops_outsourcing은 7개 조건 ALL 필요 ──────────
    # [PATCH 2] 조건이 하나라도 빠지면 ops_outsourcing 분류 금지
    _OPS_COND_KW = [
        re.compile(r"상시\s*운영\s*인력|운영\s*인력\s*상시", re.IGNORECASE),
        re.compile(r"\bKPI\b|성과\s*지표", re.IGNORECASE),
        re.compile(r"\bSLA\b|서비스\s*수준\s*협약", re.IGNORECASE),
        re.compile(r"운영\s*센터|운영\s*본부", re.IGNORECASE),
        re.compile(r"지속적\s*운영|상시\s*운영|월\s*단위\s*운영", re.IGNORECASE),
        re.compile(r"고객\s*응대|고객\s*서비스\s*인력", re.IGNORECASE),
        re.compile(r"시설\s*운영|시설\s*관리|매장\s*운영", re.IGNORECASE),
    ]
    ops_cond_count = sum(1 for kw in _OPS_COND_KW if kw.search(haystack))
    is_ops_outsourcing = (ops_cond_count >= 5)  # 5개 이상 충족 시 ops 확정

    if is_ops_outsourcing:
        if is_advisory_type:
            return "advisory"
        return "general"  # ops_outsourcing → general 매핑 유지

    # 기존 분류 fallback
    if is_advisory_type:
        return "advisory"
    if is_rental_type:
        return "rental"
    if is_construction_type:
        return "construction"
    # 유형물이 있지만 설치나 사고가 없는 경우 → general (단순 납품)
    if is_tangible and not has_installation:
        return "general"
    return "general"


def _classify_contract_type(contract_type: str, text: str, filename: str | None) -> str:
    """계약 유형 확정 — 경제적 실질 우선, 키워드 fallback.
    Returns: "advisory" | "rental" | "construction" | "project_installation" | "general"
    """
    return _classify_contract_type_by_substance(contract_type, text, filename)


# ─────────────────────────────────────────────────────────────────────────────
# [Contextual Awareness] Logic Hard-Lock — requirement.md > Contextual Awareness
# 제조물공급 계약 확정 시 advisory/ops_outsourcing 로직을 완전 차단한다.
# ─────────────────────────────────────────────────────────────────────────────

def _apply_contract_nature_lock(
    clause_results: list[dict[str, Any]],
    contract_nature: str,
) -> None:
    """contract_nature == '제조물공급' 시 용역/인력 관련 수정문안을 Hard-Block한다."""
    if contract_nature != "제조물공급":
        return
    _ADVISORY_CONTAMINATION_KW = re.compile(
        r"용역비|자문료|수탁자|위탁자|산출물|deliverable|SOW|결과물\s*납품"
        r"|지식재산권\s*귀속|저작권\s*귀속|IP\s*귀속|인력\s*배치|KPI|운영\s*인력",
        re.IGNORECASE,
    )
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("is_checklist_item")):
            continue
        sr = str(cr.get("suggested_rewrite") or "")
        rr = str(cr.get("rewrite_reason") or "")
        if _ADVISORY_CONTAMINATION_KW.search(sr + " " + rr):
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["rewrite_reason"] = "제조물공급 계약 — 용역/인력 관련 로직 Hard-Block 적용"
            cr["guardrail_block"] = {"filter": "contract_nature_lock", "nature": contract_nature}
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["approval_required"] = False
            cr["high_risk"] = False
            cr["review_tier"] = "NOTE"


def _law_contract_type_for_search(contract_class: str, raw_contract_type: str) -> str:
    """법령 DB 검색에 사용할 계약 유형 문자열을 contract_class 기준으로 반환한다.
    유형별 법령 DB를 엄격히 분리하여 advisory 계약에 렌탈/물류 법령이 주입되는 것을 차단.
    - advisory → IP·저작권·민법(위임) 중심 검색 유도
    - rental   → 렌탈 전용 검색
    - construction → 인테리어·공사 전용 검색
    - general  → 원본 contract_type 그대로 사용
    """
    if contract_class == "advisory":
        return "자문용역_IP저작권"
    if contract_class == "rental":
        return "가구렌탈"
    if contract_class == "construction":
        return "인테리어공사"
    if contract_class == "project_installation":
        return "설치시운전_산업안전중대재해"
    return raw_contract_type


def _apply_advisory_ip_review(
    clause_results: list[dict[str, Any]],
    contract_type: str,
    text: str,
    entity: str,
    contract_class: str = "",
) -> None:
    """[Expert Advisory Review Logic — Phase 2: IP & Copyright Priority]
    자문/용역 계약에서 IP 귀속(CRITICAL)과 제3자 침해 보증을 점검한다.
    """
    # HARD BLOCK: testing_service (시험·검사·인증 용역) contracts are not IP/
    # development contracts, even though _is_service_advisory_contract's loose
    # "용역" keyword regex would otherwise match them (a testing-service
    # agreement is, technically, also a 용역 in the colloquial sense). This
    # previously caused IP/저작권/제3자 침해보증 boilerplate to be injected
    # into a testing-lab agreement that has no IP deliverable at all.
    if contract_class == "testing_service":
        return
    if not _is_service_advisory_contract(str(contract_type), str(text or "")):
        return

    is_large_payment = bool(_LARGE_PAYMENT_KW.search(str(text or "")))
    found_ip_clause = False
    first_non_meta_cr: dict[str, Any] | None = None

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        a_i = _article_int_from_cr(cr)
        if a_i is not None and a_i in (1, 2, 3):
            continue

        title = str(cr.get("clause_title") or "")
        ot = str(cr.get("original_text") or "")
        sr = cr.get("suggested_rewrite") or ""
        combined = title + " " + ot
        # is_ip_clause: 제목 기반 우선 탐지, 본문은 명시적 IP 키워드만 인정 (결과물/산출물 단독은 제외)
        is_ip_clause = (
            any(k in title for k in _IP_CLAUSE_TITLES)
            or bool(_IP_BODY_EXPLICIT_KW.search(ot))
        )
        has_warranty = bool(_IP_WARRANTY_KW.search(combined))

        if is_ip_clause:
            found_ip_clause = True

        if first_non_meta_cr is None:
            first_non_meta_cr = cr

        # Guard: dealer trademark/IP usage clauses (e.g. "사전 승인없이 상호·상표 사용 불가")
        # must NEVER receive development-deliverable IP warranty templates.
        # Setting found_ip_clause=True prevents ③ from injecting them into the first clause.
        if _is_dealer_trademark_ip_clause(title, ot):
            continue

        # ① IP가 수탁자에게 귀속 → CRITICAL
        if is_ip_clause and _IP_CONTRACTOR_KW.search(combined):
            base = (sr or ot).rstrip()
            cr["suggested_rewrite"] = (base + _IP_FURSYS_REWRITE).strip()
            cr["suggested_direction"] = (cr.get("suggested_direction") or []) + [
                "[CRITICAL] IP/저작권 → 퍼시스(위탁자) 전적 귀속으로 수정",
                "독점적·무제한 이용권 확보",
                "수탁자 제3자 제공·등록 금지 명시",
            ]
            cr["rewrite_reason"] = (
                "[CRITICAL] 수탁자 IP 귀속 조항은 퍼시스가 자신이 비용을 지급한 결과물을 "
                "자유롭게 활용하지 못하게 한다. 저작권법 제9조는 도급 계약에서 수탁자 귀속을 "
                "원칙으로 하므로 명시적 위탁자 귀속 규정이 필수다."
                + (" (1억 이상 고액 대가 계약으로 리스크 가중)" if is_large_payment else "")
            )
            cr["risk_tier"] = "HIGH"
            cr["must_fix"] = True
            cr["review_tier"] = "MUST"
            cr["approval_required"] = True
            cr["high_risk"] = True
            cr["ip_critical"] = True

        # ② IP 조항이 있으나 제3자 보증 누락 → 보증 삽입
        elif is_ip_clause and not has_warranty:
            base = (sr or ot).rstrip()
            cr["suggested_rewrite"] = (base + _IP_WARRANTY_REWRITE).strip()
            cr["suggested_direction"] = (cr.get("suggested_direction") or []) + [
                "제3자 권리 침해 보증 문구 삽입",
                "침해 시 수탁자 면책·배상 의무 명시",
            ]
            if not (isinstance(cr.get("rewrite_reason"), str) and cr.get("rewrite_reason")):
                cr["rewrite_reason"] = (
                    "제3자 침해 보증 미비 시 퍼시스가 공동 침해자로 노출될 위험. "
                    "저작권법 제125조 손해배상 리스크 차단을 위해 보증 조항 필수."
                )
            cr["risk_tier"] = "HIGH"
            cr["must_fix"] = True
            cr["review_tier"] = "MUST"

    # ③ IP 전용 조항 자체가 없으면 → 첫 실질 조항에 삽입
    if not found_ip_clause and first_non_meta_cr is not None:
        cr = first_non_meta_cr
        ot = str(cr.get("original_text") or "")
        sr = cr.get("suggested_rewrite") or ""
        base = (sr or ot).rstrip()
        cr["suggested_rewrite"] = (base + _IP_FURSYS_REWRITE + _IP_WARRANTY_REWRITE).strip()
        cr["suggested_direction"] = (cr.get("suggested_direction") or []) + [
            "[CRITICAL] IP 귀속 조항 누락 — 결과물 조항에 귀속·보증 조항 삽입 필수",
        ]
        cr["risk_tier"] = "HIGH"
        cr["must_fix"] = True
        cr["review_tier"] = "MUST"
        cr["approval_required"] = True
        cr["rewrite_reason"] = (
            "[CRITICAL] 지식재산권 귀속 조항 부재. 저작권법 제9조에 따라 도급 계약 수탁자 자동 귀속 위험."
        )

    # ④ 배상 한도 예외 단서 — Exclusive IP Review Engine Step 2.③
    # 용역대금 총액 등으로 배상을 제한하는 조항에 IP/비밀유지 위반 예외 단서를 추가한다.
    _LIABILITY_TITLE_HINTS = ("손해배상", "배상", "책임제한", "책임의 한계", "손해 배상")
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        a_i = _article_int_from_cr(cr)
        if a_i is not None and a_i in (1, 2, 3):
            continue
        title = str(cr.get("clause_title") or "")
        ot = str(cr.get("original_text") or "")
        if not any(h in title for h in _LIABILITY_TITLE_HINTS):
            continue
        # 배상 총액 제한 패턴 탐지
        if not _LIABILITY_CAP_KW.search(ot):
            continue
        # 이미 예외 단서가 있으면 스킵
        if _LIABILITY_EXCEPTION_KW.search(ot):
            continue
        sr = cr.get("suggested_rewrite") or ""
        base = (sr or ot).rstrip()
        cr["suggested_rewrite"] = (base + _LIABILITY_CAP_EXCEPTION_REWRITE).strip()
        cr["suggested_direction"] = (cr.get("suggested_direction") or []) + [
            "배상 한도 예외: 지재권 침해·비밀유지 위반·고의중과실은 총액 한도 적용 제외",
        ]
        if not (isinstance(cr.get("rewrite_reason"), str) and cr.get("rewrite_reason")):
            cr["rewrite_reason"] = (
                "배상 범위를 용역대금 총액으로 제한 시 지재권 침해·비밀유지 위반의 경우에도 "
                "배상이 제한되어 퍼시스의 실질적 피해 회복이 불가능해진다. "
                "IP 침해·NDA 위반·고의중과실에 대한 예외 단서가 필수다."
            )
        cr["risk_tier"] = "HIGH"
        cr["must_fix"] = True
        cr["review_tier"] = "MUST"


# =============================================================================
# [Zero-Hallucination Guardrail] — requirement.md > [Zero-Hallucination Guardrail] 참조
# =============================================================================

_SERVICE_ADVISORY_KW = re.compile(
    r"자문|용역|Service|Advisory|컨설팅|Consulting|위임|Engagement|집필|강의|연구", re.IGNORECASE
)

# 자문/용역/개발/제작 계약에서 절대 삽입 금지 키워드 (Exclusive IP Review Engine)
_FORBIDDEN_ADVISORY_KW = re.compile(
    r"렌탈|소유권은\s*퍼시스에|물류시설|물류\s*센터|물류\s*비용|구독\s*서비스|소유권\s*존속|채권추심"
    r"|부동산|위약금\s*10\s*%|위약금\s*10\s*퍼센트|임대차\s*보증금|보증금\s*반환",
    re.IGNORECASE,
)

# 자문/용역 계약과 무관한 법령 패턴
_FORBIDDEN_LAW_KW = re.compile(
    r"물류시설법|부동산\s*세법|화물자동차\s*운수사업법|주택\s*임대차|상가건물\s*임대차"
    r"|임대차보호법|전자상거래법|방문판매법|할부거래법",
    re.IGNORECASE,
)


def _is_service_advisory_contract(contract_type: str, text: str) -> bool:
    haystack = (contract_type or "") + " " + (text or "")[:400]
    return bool(_SERVICE_ADVISORY_KW.search(haystack))


# ─── Dealer trademark/IP usage guard ─────────────────────────────────────────
# Prevents development-deliverable IP templates from being applied to dealer
# trademark-usage restriction clauses (e.g. "사전 승인없이 상호·상표 사용 불가").

_DEALER_TRADEMARK_GUARD_KW = re.compile(
    r"사전\s*승인\s*없이.{0,100}(?:상호|상표|저작물|지식재산권)"
    r"|(?:간판|영업장|옥내.{0,5}외\s*간판).{0,60}(?:상호|상표|지식재산권)"
    r"|대리점.{0,40}(?:상표|로고|상호).{0,40}사용",
    re.IGNORECASE | re.DOTALL,
)
_DEALER_DEVELOPMENT_DELIVERABLE_KW = re.compile(
    r"산출물|소스\s*코드|개발.{0,20}결과물|수탁자는\s*결과물|개발.{0,20}저작물",
    re.IGNORECASE,
)


def _is_dealer_trademark_ip_clause(title: str, text: str) -> bool:
    """Return True when the clause restricts dealer use of supplier trademarks/IP.

    This is NOT a development-deliverable IP clause — the development IP warranty
    templates (수탁자는 결과물이 제3자의 저작권...) must never be applied here.
    """
    combined = (title or "") + " " + (text or "")
    if _DEALER_DEVELOPMENT_DELIVERABLE_KW.search(combined):
        return False
    return bool(_DEALER_TRADEMARK_GUARD_KW.search(combined))


def _apply_zero_hallucination_guardrail(
    clause_results: list[dict[str, Any]],
    contract_type: str,
    text: str,
) -> None:
    """[Zero-Hallucination Guardrail]
    1. 제1·2·3조 절대 보호 (모든 계약 유형)
    2. 자문/용역 계약: 렌탈·소유권·물류시설 등 금지 키워드 Hard-Block
    3. 자문/용역 계약: 무관 법령 인용 삭제
    requirement.md > [Zero-Hallucination Guardrail] 참조
    """
    is_advisory = _is_service_advisory_contract(str(contract_type), str(text or ""))

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue

        # ── 규칙 1: 제1·2·3조 절대 보호 (목적·원칙·정의 조항) ──────────────
        a_i = _article_int_from_cr(cr)
        if a_i is not None and a_i in (1, 2, 3):
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"
            cr["high_risk"] = False
            cr["approval_required"] = False
            cr["rewrite_reason"] = None
            if not cr.get("guardrail_block"):
                cr["guardrail_block"] = {"filter": "article_1_2_3_protection"}
            continue

        if not is_advisory:
            continue

        sr = cr.get("suggested_rewrite") or ""
        rr = cr.get("rewrite_reason") or ""
        combined = sr + " " + rr

        # ── 규칙 2: 자문/용역 — 금지 키워드 Hard-Block ─────────────────────
        if _FORBIDDEN_ADVISORY_KW.search(combined):
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["rewrite_reason"] = None
            cr["risk_tier"] = "LOW"
            cr["approval_required"] = False
            cr["high_risk"] = False
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"
            if not cr.get("guardrail_block"):
                cr["guardrail_block"] = {"filter": "advisory_forbidden_keywords"}
            continue

        # ── 규칙 3: 자문/용역 — 무관 법령 삭제 → 허용 법령으로 교체 ──────────
        if _FORBIDDEN_LAW_KW.search(combined):
            # related_laws 내 무관 법령 항목 삭제
            law = cr.get("related_laws")
            if isinstance(law, dict) and isinstance(law.get("results"), dict):
                for k in ("laws", "precedents", "interpretations"):
                    arr = law["results"].get(k)
                    if isinstance(arr, list):
                        law["results"][k] = [
                            it for it in arr
                            if isinstance(it, dict)
                            and not _FORBIDDEN_LAW_KW.search(str(it.get("title") or ""))
                        ]
            # suggested_rewrite에서 무관 법령 문장 제거 후 허용 법령 추가
            if _FORBIDDEN_LAW_KW.search(sr):
                cleaned = re.sub(
                    r"[^\n]*(?:물류시설법|부동산\s*세법|화물자동차\s*운수사업법"
                    r"|주택\s*임대차|상가건물\s*임대차|임대차보호법"
                    r"|전자상거래법|방문판매법|할부거래법)[^\n]*\n?",
                    "",
                    sr,
                ).strip()
                # 허용 법령 미포함 시 보충 (Exclusive IP Review Engine)
                allowed_laws = "저작권법, 부정경쟁방지법, 특허법"
                if not any(k in (cleaned or "") for k in ("저작권법", "부정경쟁방지법", "특허법")):
                    if cleaned:
                        cleaned = cleaned + f"\n[관련 법령] {allowed_laws}"
                    else:
                        cleaned = f"[관련 법령] {allowed_laws}"
                cr["suggested_rewrite"] = cleaned if cleaned else None
                if not cr.get("guardrail_block"):
                    cr["guardrail_block"] = {"filter": "advisory_forbidden_laws"}


# =============================================================================
# [FINAL GOVERNING RULE] Relevance Validation Gate
# requirement.md > Relevance Validation Gate 참조
# 5개 조건 중 3개 이상 충족해야 출력 유지 (2개 이상 불충족 시 제거)
# =============================================================================

_BOILERPLATE_DETECT_KW = re.compile(
    r"명확히\s*할\s*필요가\s*있(습니다|다)|검토가\s*필요(합니다|하다)|"
    r"추가적인\s*검토가\s*필요|관련\s*법령을?\s*(검토|확인)|"
    r"일반적으로|통상적으로|법적\s*검토가\s*필요|고려해\s*볼\s*필요|"
    r"적절한\s*조치를?\s*취할|주의가\s*필요합니다",
    re.IGNORECASE,
)

_TOPIC_CONTRACT_COMPAT: dict[str, frozenset[str]] = {
    "advisory": frozenset({
        "ip_ownership", "confidentiality", "payment_settlement",
        "termination", "dispute", "personal_data", "damage",
    }),
    "project_installation": frozenset({
        "safety", "safety_compliance", "damage", "payment_settlement",
        "termination", "personal_data", "cost_burden",
    }),
    "rental": frozenset({
        "payment_settlement", "termination", "personal_data", "damage",
        "cost_burden",
    }),
    "construction": frozenset({
        "payment_settlement", "safety", "termination", "damage",
        "cost_burden",
    }),
    "testing_service": frozenset({
        "confidentiality", "damage", "termination", "payment_settlement",
        "personal_data", "other",
    }),
    "general": frozenset({
        "payment_settlement", "termination", "damage", "cost_burden",
        "confidentiality", "ip_ownership", "personal_data", "safety",
        "safety_compliance", "dealer_unfair",
    }),
}


# rule_id -> out-of-scope for these contract_class values, regardless of how
# the rule entered `applicable` (base match, context_expanded_by_questions,
# or context_expanded_by_text). These ACT-*/RISK-* rules key off whole-document
# keyword search (query_service.TRIGGER_MAP), not clause-scoped extraction, so
# a single incidental mention (e.g. "안전한 상태로 제공" in a testing-service
# 시료 조항) can expand the rule set to include 안전/하도급/기술자료 checklist
# items that have nothing to do with the actual contract. HARD BLOCK them here
# so they can never reach suggest_revisions() for these contract classes.
_OUT_OF_SCOPE_RULE_IDS_BY_CONTRACT_CLASS: dict[str, frozenset[str]] = {
    "testing_service": frozenset({
        "ACT-007", "ACT-008", "ACT-010",
        "RISK-003", "RISK-004", "RISK-005",
    }),
}


def _hard_block_out_of_scope_rules(review: dict[str, Any], contract_class: str) -> None:
    """HARD BLOCK: strip contract-class-irrelevant ACT-*/RISK-* rules from the
    rule-engine output before they ever reach per-clause revision generation.
    Mutates `review` in place and recomputes summary counts so
    matched_rule_count/checklist_rule_count/approval_required/high_risk stay
    internally consistent with the filtered lists."""
    blocked = _OUT_OF_SCOPE_RULE_IDS_BY_CONTRACT_CLASS.get(contract_class)
    if not blocked or not isinstance(review, dict):
        return

    def _keep(r: Any) -> bool:
        return not (isinstance(r, dict) and str(r.get("rule_id") or "") in blocked)

    matched_rules = [r for r in review.get("matched_rules", []) if _keep(r)]
    checklist_rules = [r for r in review.get("checklist_rules", []) if _keep(r)]
    review["matched_rules"] = matched_rules
    review["checklist_rules"] = checklist_rules

    approval_required_matches = [
        r for r in matched_rules
        if isinstance(r, dict) and (r.get("rule_status") == "approval_required" or r.get("approval_required"))
    ]
    high_risk_matches = [
        r for r in matched_rules
        if isinstance(r, dict) and str(r.get("risk_level") or "").strip().lower() in ("high", "very_high", "critical")
    ]
    review["approval_required_matches"] = approval_required_matches

    summary = review.get("summary")
    if isinstance(summary, dict):
        summary["matched_rule_count"] = len(matched_rules)
        summary["checklist_rule_count"] = len(checklist_rules)
        summary["approval_required_match_count"] = len(approval_required_matches)
        summary["high_risk_match_count"] = len(high_risk_matches)
        summary["approval_required"] = len(approval_required_matches) > 0
        summary["high_risk"] = len(high_risk_matches) > 0


def _apply_relevance_validation_gate(
    clause_results: list[dict[str, Any]],
    contract_class: str,
    contract_nature: str,
) -> None:
    """[FINAL GOVERNING RULE] Relevance Validation Gate.
    5개 조건 중 3개 이상 충족 시 수정안 유지, 미달 시 제거.
    체크리스트·dedup_suppressed·keep_as_is 항목은 대상 제외.
    """
    compat = _TOPIC_CONTRACT_COMPAT.get(contract_class, frozenset())

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        if bool(cr.get("is_checklist_item")):
            continue
        # common_legal_risk.py의 Layer 1 rule은 "계약유형과 무관하게 모든 계약에서
        # 검토"하도록 의도적으로 설계됨(그 파일 자체의 docstring — HARD BLOCK도
        # 적용받지 않음). 이 relevance gate의 조건 1/3(계약유형별 topic 호환성)이
        # Layer 1 finding에도 그대로 적용되면 실제로 존재하는 불리한 조항
        # (지체상금 무상한·위약벌 배수·귀책불문 해지 등, clause_topic="other"/
        # "damage" 등)이 계약유형 미스매치로 오인되어 조용히 LOW 강등되므로 제외한다.
        if bool(cr.get("is_common_legal_risk")):
            continue

        sr = str(cr.get("suggested_rewrite") or "")
        if not sr.strip():
            continue

        rr = str(cr.get("rewrite_reason") or "")
        tier = str(cr.get("risk_tier") or "").upper()
        topic = str(cr.get("clause_topic") or "")
        score = 0

        # 조건 1: 이 리스크가 실제 이 계약에서 발생 가능한가?
        if not compat or topic in compat or tier == "HIGH" or bool(cr.get("user_focus_hit")):
            score += 1

        # 조건 2: 전문 변호사가 실제 수정 요구할 수준인가?
        if tier in ("HIGH", "MEDIUM") and bool(cr.get("has_rewrite_change")):
            score += 1
        elif bool(cr.get("approval_required")) or bool(cr.get("must_fix")):
            score += 1

        # 조건 3: 계약 유형과 논리적으로 일치하는가?
        if not compat or topic in compat or not topic:
            score += 1

        # 조건 4: 사용자가 중요하다고 한 이슈와 관련 있는가?
        if bool(cr.get("user_focus_hit")) or bool(cr.get("factual_hit")) or bool(cr.get("approval_required")):
            score += 1

        # 조건 5: generic boilerplate가 아닌가?
        if not _BOILERPLATE_DETECT_KW.search(sr + " " + rr):
            score += 1

        if score < 3:
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["risk_tier"] = "MEDIUM" if tier == "HIGH" else "LOW"
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"
            cr["approval_required"] = False
            cr["high_risk"] = False
            cr["has_rewrite_change"] = False
            if not cr.get("guardrail_block"):
                cr["guardrail_block"] = {
                    "filter": "relevance_validation_gate",
                    "score": score,
                    "topic": topic,
                    "tier": tier,
                }


# =============================================================================
# [CRITICAL FIX] Do Not Harm Our Side Gate — 당사 불이익 방지 최종 검증 게이트
# requirement.md > [FINAL VALIDATION GATE] Do Not Harm Our Side
# =============================================================================

# 공급자에게 과도한 의무를 부과하는 표현 감지 패턴
_SUPPLIER_OVERBURDEN_KW = re.compile(
    r"포괄적\s*(안전\s*)?보증|무제한\s*(리콜|하자|책임|배상|부담)"
    r"|즉시\s*(리콜|회수|배상|부담)"
    r"|전액\s*(부담|배상|비용)"
    r"|일방적으로|PL보험\s*(가입\s*)?(의무|필수)"
    r"|반드시\s*(보험|인증|리콜|배상)"
    r"|자동\s*(의무|부담|책임)",
    re.IGNORECASE,
)

# 공급자 방어 필수 문구가 없는 경우 감지 (귀책사유·법령범위·예외사유)
_SUPPLIER_GUARDRAIL_MISSING = re.compile(
    r"귀책\s*사유|법령상\s*(요구|범위|규정)|관련\s*법령|직접\s*손해|합리적\s*범위|면책",
    re.IGNORECASE,
)

# 자동 대체 쌍 (원래 표현 패턴 → 방어 문구)
_SUPPLIER_AUTO_REWRITE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"포괄적?\s*(안전\s*)?보증", re.IGNORECASE), "관련 법령상 요구되는 범위 내에서의 보증"),
    (re.compile(r"무제한\s*(리콜\s*)?(비용\s*)?부담", re.IGNORECASE), "법령상 요구되거나 중대한 결함이 확인된 경우의 리콜 비용 부담"),
    (re.compile(r"즉시\s*리콜", re.IGNORECASE), "법령상 요구되거나 중대한 결함이 확인된 경우의 리콜 조치"),
    (re.compile(r"전액\s*(부담|배상)", re.IGNORECASE), "합리적 범위의 직접손해에 한하여 부담"),
    (re.compile(r"무조건\s*(책임|배상)", re.IGNORECASE), "공급자의 귀책사유가 있는 경우에 한하여 책임"),
    (re.compile(r"PL보험\s*(가입\s*)?(의무|필수)", re.IGNORECASE), "PL보험 가입은 별도 협의 또는 요청 시 검토"),
    (re.compile(r"즉시\s*시정\s*조치를?\s*완료", re.IGNORECASE), "합리적인 기간 내 시정 조치 완료"),
    (re.compile(r"안전\s*인증\s*완료를?\s*(보증|확약)", re.IGNORECASE), "해당 법령에서 요구하는 인증을 취득한 범위 내에서 확인"),
]

# =============================================================================
# [STEP 2] Buyer-Favorable Manufacturing Template Blacklist
# requirement.md > [STEP 2] Delete Buyer-Favorable Manufacturing Templates
# =============================================================================
_BUYER_FAVORABLE_TEMPLATES: list[re.Pattern[str]] = [
    re.compile(r"안전\s*인증\s*완료를?\s*(보증|확약)", re.IGNORECASE),
    re.compile(r"공급자가?\s*(리콜|회수)\s*비용을?\s*(전액\s*)?부담", re.IGNORECASE),
    re.compile(r"공급자는?\s*PL\s*보험에?\s*(가입|체결)(하여야|해야|해야\s*한다)", re.IGNORECASE),
    re.compile(r"공급자는?\s*제3자\s*손해를?\s*(전부\s*)?배상(한다|하여야|해야)", re.IGNORECASE),
    re.compile(r"공급자는?\s*결함\s*발견\s*시\s*즉시\s*시정\s*조치를?\s*완료(하여야|해야|한다)", re.IGNORECASE),
]

# =============================================================================
# [STEP 3] Supplier-Protective Product Contract Checklist
# requirement.md > [STEP 3] Supplier-Protective Product Contract Logic
# 우리 회사 = 공급자이고 물품공급계약일 때 누락된 보호 조항 자동 탐지·주입
# =============================================================================
_SUPPLIER_HIGH_CHECKLIST: list[dict[str, Any]] = [
    {
        "id": "sppc_inspection_standard",
        "name": "검수 기준 및 검수 완료 간주",
        "present": re.compile(r"검수\s*기준|합격\s*판정|검수\s*완료\s*간주|검수\s*기간.{0,20}이내", re.IGNORECASE),
        "direction": "검수 기준·검수 기간·검수 완료 간주 조항을 계약서에 명시하여 무기한 검수 클레임을 차단하세요.",
        "rewrite": "구매자는 물품 수령 후 [ ]영업일 이내에 검수를 완료하여야 한다. 상기 기간 내에 서면으로 이의를 제기하지 아니한 경우, 검수가 완료된 것으로 간주한다.",
        "clause_topic": "payment_settlement",
    },
    {
        "id": "sppc_defect_notice",
        "name": "하자 통지 기한 및 절차",
        "present": re.compile(r"하자\s*(통지|신고).{0,30}(기한|기간|이내)|발견.{0,15}일\s*이내.{0,15}통지", re.IGNORECASE),
        "direction": "하자 통지 기한(발견일로부터 7일 이내 서면 통지)과 통지 해태 시 클레임 제한 조항을 추가하세요.",
        "rewrite": "구매자는 하자를 발견한 경우 발견일로부터 7일 이내에 구체적 내용을 기재하여 서면으로 공급자에게 통지하여야 한다. 이를 해태한 경우 해당 하자에 관한 클레임을 제기할 수 없다.",
        "clause_topic": "damage",
    },
    {
        "id": "sppc_return_limit",
        "name": "반품 제한 및 반품 조건",
        "present": re.compile(r"반품\s*(제한|불가|조건|요건)|주문제작.{0,20}반품", re.IGNORECASE),
        "direction": "주문제작·설치완료 제품의 반품을 제한하고, 반품 요건(검수 불합격 + 서면 통지 필수)을 명시하세요.",
        "rewrite": "주문제작 또는 설치가 완료된 물품은 원칙적으로 반품이 불가하다. 반품이 허용되는 경우, 구매자는 물품 수령일로부터 [ ]일 이내에 구체적 하자 내용을 기재한 서면 반품 요청서를 공급자에게 제출하여야 한다.",
        "clause_topic": "termination",
    },
    {
        "id": "sppc_payment_retention",
        "name": "대금 미지급 시 공급자 이행유보권",
        "present": re.compile(r"이행\s*유보|대금\s*(미지급|지연).{0,20}이행\s*정지|지급\s*정지.{0,20}이행|유치권", re.IGNORECASE),
        "direction": "대금 미지급 시 공급자가 이행을 유보할 수 있는 권리(이행유보권)를 계약서에 명시하세요.",
        "rewrite": "구매자가 기한 내에 대금을 지급하지 아니하는 경우, 공급자는 대금 완납 시까지 물품 인도 또는 추가 서비스 이행을 유보할 수 있으며, 이로 인한 지연은 공급자의 귀책으로 보지 않는다.",
        "clause_topic": "payment_settlement",
    },
    {
        "id": "sppc_damage_cap",
        "name": "손해배상 한도 및 간접손해 배제",
        "present": re.compile(r"손해배상\s*(한도|상한|총액)|간접\s*손해.{0,15}(배제|제외|책임지지)", re.IGNORECASE),
        "direction": "공급자의 손해배상책임을 공급대금 총액으로 한정하고, 간접손해·특별손해·일실이익을 배제하세요.",
        "rewrite": "공급자의 손해배상책임은 해당 클레임의 원인이 된 물품의 공급대금을 한도로 하며, 특별손해, 간접손해, 결과적 손해, 일실이익에 대해서는 책임을 부담하지 아니한다. 단, 공급자의 고의 또는 중대한 과실로 인한 손해는 예외로 한다.",
        "clause_topic": "damage",
    },
    {
        "id": "sppc_misuse_exemption",
        "name": "오사용/보관불량/임의개조 면책",
        "present": re.compile(r"오사용|임의\s*개조.{0,20}(제외|면책|책임\s*없)|보관\s*(불량|하자).{0,20}(제외|면책)", re.IGNORECASE),
        "direction": "구매자의 오사용·보관불량·임의개조·사용설명 위반으로 인한 하자·사고는 공급자 책임에서 명시적으로 제외하세요.",
        "rewrite": "다음 각 호의 사유로 인한 하자·손해에 대하여 공급자는 책임을 부담하지 아니한다: ① 구매자 또는 사용자의 오사용 또는 사용설명서 위반, ② 구매자의 임의 개조·수리, ③ 구매자의 보관 불량 또는 설치환경 부적합, ④ 구매자 제공 사양·도면·지시에 기인한 결함, ⑤ 제3자 제품과의 결합으로 인한 손해.",
        "clause_topic": "damage",
    },
    {
        "id": "sppc_custom_cancel_limit",
        "name": "주문제작·설치완료 제품 취소 제한",
        "present": re.compile(r"주문제작.{0,20}취소\s*(제한|불가)|설치\s*완료.{0,20}취소\s*(제한|불가)", re.IGNORECASE),
        "direction": "주문제작 또는 설치완료 단계 이후의 주문 취소를 제한하고, 취소 시 이미 발생한 비용 부담을 구매자에게 귀속하세요.",
        "rewrite": "주문제작 공정이 개시된 이후 또는 설치가 완료된 후에는 구매자가 일방적으로 계약을 취소할 수 없다. 부득이한 취소의 경우, 구매자는 공급자가 이미 투입한 재료비·인건비·제반 비용을 부담한다.",
        "clause_topic": "termination",
    },
    {
        "id": "sppc_as_exclusion",
        "name": "A/S 제외 사유",
        "present": re.compile(r"A/S.{0,20}(제외|불가|해당\s*없)|AS.{0,20}(제외|불가)|무상\s*수리.{0,20}(제외|불가)", re.IGNORECASE),
        "direction": "A/S 제외 사유(오사용·임의개조·보관불량·소모품 등)를 구체적으로 열거하여 무분별한 A/S 요청을 방어하세요.",
        "rewrite": "다음 각 호의 경우 무상 A/S 대상에서 제외한다: ① 사용설명서를 준수하지 아니하거나 오사용으로 인한 고장, ② 구매자 또는 제3자의 임의 개조·수리로 인한 손상, ③ 정상 마모·소모품 교체, ④ 구매자의 보관 불량 또는 설치환경 부적합으로 인한 손상, ⑤ 구매자의 부주의로 인한 파손.",
        "clause_topic": "damage",
    },
]

_SUPPLIER_MEDIUM_CHECKLIST: list[dict[str, Any]] = [
    {
        "id": "sppc_spec_liability",
        "name": "고객 제공 사양/도면 책임 귀속",
        "present": re.compile(r"사양.{0,20}(책임|귀책)|도면.{0,20}(책임|귀책)|고객\s*제공.{0,20}(책임|귀책)", re.IGNORECASE),
        "direction": "고객이 제공한 사양·도면·지시에 기인한 결함·손해는 공급자 책임에서 제외하는 조항을 명시하세요.",
        "rewrite": "구매자가 제공하는 사양, 도면, 설계서 또는 지시에 따라 제작된 물품에서 발생하는 결함·손해는 공급자의 귀책으로 보지 않으며, 해당 책임은 구매자에게 귀속된다.",
        "clause_topic": "damage",
    },
    {
        "id": "sppc_install_env",
        "name": "설치환경 미비 시 책임 제외",
        "present": re.compile(r"설치\s*환경.{0,20}(미비|부적합|미충족).{0,20}(책임|면책|제외)", re.IGNORECASE),
        "direction": "구매자가 설치 환경 요건을 충족하지 못하여 발생하는 손해는 공급자 책임에서 제외하는 조항을 추가하세요.",
        "rewrite": "구매자가 공급자가 사전에 고지한 설치 환경 요건(전원, 바닥 하중, 온도·습도 등)을 충족하지 아니하여 발생하는 설비 손상·사고·성능 저하에 대하여 공급자는 책임을 부담하지 아니한다.",
        "clause_topic": "damage",
    },
    {
        "id": "sppc_buyer_delay_extension",
        "name": "구매자 지연 시 납기 연장",
        "present": re.compile(r"구매자.{0,20}지연.{0,20}(납기\s*연장|기간\s*연장)|발주자.{0,20}지연.{0,20}연장", re.IGNORECASE),
        "direction": "구매자 귀책으로 인한 납기 지연 시 납기가 자동 연장되고 추가비용은 구매자가 부담하는 조항을 추가하세요.",
        "rewrite": "구매자의 귀책사유(자재 미공급, 설치환경 미준비, 승인 지연, 정보 미제공 등)로 인한 납기 지연의 경우, 납기는 그 지연 기간만큼 자동 연장되며, 이로 인한 추가 비용은 구매자가 부담한다.",
        "clause_topic": "cost_burden",
    },
    {
        "id": "sppc_risk_transfer",
        "name": "위험이전 시점 명확화",
        "present": re.compile(r"위험\s*(이전|부담).{0,20}(인도|검수|시점)|인도\s*완료.{0,20}위험", re.IGNORECASE),
        "direction": "물품 인도 완료(또는 검수 완료) 시점에 위험이 구매자에게 이전됨을 명시하세요.",
        "rewrite": "물품에 대한 위험은 공급자가 구매자 또는 구매자가 지정한 장소에 물품을 인도(또는 설치 완료)한 시점에 구매자에게 이전된다. 인도 이후의 멸실·훼손에 대하여 공급자는 책임을 부담하지 아니한다.",
        "clause_topic": "damage",
    },
    {
        "id": "sppc_setoff_limit",
        "name": "상계 제한 또는 상계 요건 명확화",
        "present": re.compile(r"상계\s*(제한|요건|합의|금지)|일방적\s*상계.{0,20}금지", re.IGNORECASE),
        "direction": "구매자의 일방적 상계를 제한하고, 상계 시 서면 합의 또는 확정 판결을 요건으로 명시하세요.",
        "rewrite": "구매자는 공급자의 사전 서면 동의 없이 공급대금 채무와 다른 채권을 일방적으로 상계할 수 없다. 상계는 법원의 확정 판결 또는 당사자 간 서면 합의에 의해서만 허용된다.",
        "clause_topic": "payment_settlement",
    },
]


def _apply_supplier_product_checklist(
    clause_results: list[dict[str, Any]],
    full_text: str,
    contract_class: str,
    our_role: str,
    review_posture: str,
) -> None:
    """[STEP 3] Supplier-Protective Product Contract Checklist.
    우리 회사 = 공급자이고 물품공급 계약일 때 누락된 보호 조항을 자동 탐지하여
    HIGH/MEDIUM 수정안을 주입한다.
    """
    _our_role = str(our_role or "").lower()
    _is_supplier = _our_role in ("supplier", "seller", "rental_provider", "contractor")
    if not _is_supplier:
        return
    if review_posture != "seller_favorable":
        return
    # HARD BLOCK: this checklist assumes a tangible-goods supply/installation
    # contract (검수/반품/A/S/위험이전/설치환경 등). It must NEVER fire for
    # service/advisory/testing/content/IP-type contracts just because
    # contract_class fell through to "general" — "general" means "unclear",
    # not "assume goods supply". Require an explicit allow-listed contract_class
    # AND an actual tangible-goods/installation signal in the contract text.
    _EXCLUDED_FOR_PRODUCT_SUPPLY = (
        "advisory", "ops_outsourcing", "content_production", "testing_service",
    )
    if contract_class in _EXCLUDED_FOR_PRODUCT_SUPPLY:
        return
    _ALLOWED_FOR_PRODUCT_SUPPLY = ("general", "project_installation")
    if contract_class not in _ALLOWED_FOR_PRODUCT_SUPPLY:
        return
    _text_head = str(full_text or "")
    is_product_supply = bool(
        _SUBSTANCE_TANGIBLE_KW.search(_text_head) or _SUBSTANCE_INSTALL_KW.search(_text_head)
    )

    if not is_product_supply:
        return

    text = str(full_text or "")

    def _add_item(item: dict[str, Any], risk: str) -> None:
        if item["present"].search(text):
            return
        if any(str(cr.get("clause_id") or "") == item["id"] for cr in clause_results if isinstance(cr, dict)):
            return
        clause_results.append({
            "clause_id": item["id"],
            "article_number": None,
            "clause_title": f"[공급자 보호] {item['name']}",
            "original_text": "",
            "suggested_rewrite": None,
            "clause_topic": item.get("clause_topic", "damage"),
            "risk_tier": risk,
            "must_fix": risk == "HIGH",
            "review_tier": "MUST" if risk == "HIGH" else "SUGGEST",
            "high_risk": risk == "HIGH",
            "approval_required": risk == "HIGH",
            "rewrite_reason": item["direction"],
            "suggested_direction": [item["direction"]],
            "recommendation_text": item["rewrite"],
            "is_checklist_item": True,
            "display_kind": "guidance",
            "has_rewrite_change": False,
            "user_focus_hit": False,
            "factual_hit": False,
            "dedup_suppressed": False,
            "keep_as_is": False,
            "_priority_level": 1 if risk == "HIGH" else 2,
        })

    for item in _SUPPLIER_HIGH_CHECKLIST:
        _add_item(item, "HIGH")
    for item in _SUPPLIER_MEDIUM_CHECKLIST:
        _add_item(item, "MEDIUM")


_SUPPLIER_DEFENSE_KW = re.compile(
    r"귀책|면책|한정|제외|예외|구상|방어|보호|한도|합리적\s*기간|서면\s*(통지|합의)|이의\s*제기",
    re.IGNORECASE,
)

_SUPPLIER_UNFAVORABLE_CONFIRM = re.compile(
    r"공급자는?\s*(보증|확약|책임진다|부담한다|이행하여야|이행해야|가입하여야|가입해야)",
    re.IGNORECASE,
)

_BUYER_FAVORABLE_KW = re.compile(
    r"구매자에게\s*(추가|새로운|더\s*많은)\s*(권리|보호|혜택)"
    r"|공급자.{0,30}(즉시|전액|무조건|포괄적)(으로)?\s*(이행|배상|보증|부담)",
    re.IGNORECASE,
)

# [요구 9] 우리에게 유리한 조항 보호 — 해지권/평가권/승인권처럼 우리 회사가
# 실제로 보유한 권리를, 실질적 불이익 근거 없이 "형식적 비대칭"이라는
# 비판만으로 약화시키지 않는다.
_RX_FAVORABLE_RIGHT_TOPIC = re.compile(r"해지권|평가권|승인권", re.IGNORECASE)
_RX_FORMAL_ASYMMETRY_ONLY_CRITIQUE = re.compile(
    r"일방적|편향|불균형|비대칭|형평성",
    re.IGNORECASE,
)


def _apply_do_not_harm_our_side_gate(
    clause_results: list[dict[str, Any]],
    our_role: str,
    review_posture: str,
) -> None:
    """[CRITICAL FIX + STEP 2 + FINAL VALIDATION] Do Not Harm Our Side Gate.
    우리 회사 = 공급자인 경우:
    - STEP 2: 구매자 유리 템플릿 블랙리스트 체크 후 즉시 폐기/대체
    - FINAL VALIDATION: 5개 항목 체크, 2개 이상 YES → 폐기 또는 방어 문구로 대체
    """
    _our_role = str(our_role or "").lower()
    _is_supplier = _our_role in ("supplier", "seller", "rental_provider", "contractor")
    if review_posture != "seller_favorable" and not _is_supplier:
        return

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        if bool(cr.get("is_checklist_item")):
            continue

        sr = str(cr.get("suggested_rewrite") or "")
        if not sr.strip():
            continue

        rr = str(cr.get("rewrite_reason") or "")

        # ── [요구 9] 우리에게 유리한 권리(해지권/평가권/승인권) 보호 ─────────
        # clause_topic이 termination이거나 제목/사유에 해지권·평가권·승인권이
        # 언급되는데, 비판 내용이 "일방적/불균형/비대칭"류 형식적 비판뿐이고
        # 실질적 불이익 근거(과중한 부담·구매자 추가권리 확인 등)가 전혀 없으면
        # 그 권리를 약화시키는 수정안 자체를 폐기한다.
        _is_favorable_right_topic = (
            str(cr.get("clause_topic") or "") == "termination"
            or bool(_RX_FAVORABLE_RIGHT_TOPIC.search(str(cr.get("clause_title") or "") + " " + rr))
        )
        if _is_favorable_right_topic and _RX_FORMAL_ASYMMETRY_ONLY_CRITIQUE.search(rr):
            _has_real_harm_evidence = bool(
                _SUPPLIER_OVERBURDEN_KW.search(rr)
                or _BUYER_FAVORABLE_KW.search(sr)
                or _SUPPLIER_UNFAVORABLE_CONFIRM.search(sr)
            )
            if not _has_real_harm_evidence:
                cr["suggested_rewrite"] = None
                cr["changed_segments"] = []
                cr["has_rewrite_change"] = False
                cr.setdefault("guardrail_block", {})["favorable_right_protection"] = "formal_asymmetry_only_discarded"
                continue

        # ── [STEP 2] 구매자 유리 템플릿 블랙리스트 즉시 차단 ─────────────────
        blacklisted = any(pat.search(sr) for pat in _BUYER_FAVORABLE_TEMPLATES)
        if blacklisted:
            patched = sr
            for pattern, replacement in _SUPPLIER_AUTO_REWRITE:
                patched = pattern.sub(replacement, patched)
            if patched != sr:
                cr["suggested_rewrite"] = patched
                cr.setdefault("guardrail_block", {})["step2_blacklist"] = "auto_rewrite"
            else:
                cr["suggested_rewrite"] = None
                cr["changed_segments"] = []
                cr["has_rewrite_change"] = False
                cr.setdefault("guardrail_block", {})["step2_blacklist"] = "discarded"
            continue

        # ── [FINAL VALIDATION] 5개 항목 체크 (YES = 문제) ───────────────────
        harm_score = 0

        # 1. 이 문구가 우리 회사의 책임을 새로 늘리는가?
        if _SUPPLIER_OVERBURDEN_KW.search(sr):
            harm_score += 1

        # 2. 이 문구가 법령상 필수 수준을 넘는가?
        if _SUPPLIER_OVERBURDEN_KW.search(sr) and not _SUPPLIER_GUARDRAIL_MISSING.search(sr):
            harm_score += 1

        # 3. 구매자에게 유리한 추가 권리를 부여하는가?
        if _BUYER_FAVORABLE_KW.search(sr) or _SUPPLIER_UNFAVORABLE_CONFIRM.search(sr):
            harm_score += 1

        # 4. 공급자 방어 문구 없이 의무만 추가하는가?
        if _SUPPLIER_OVERBURDEN_KW.search(sr) and not _SUPPLIER_DEFENSE_KW.search(sr):
            harm_score += 1

        # 5. 실제 협상에서 우리 법무팀이 거부할 가능성이 높은가?
        if not _SUPPLIER_DEFENSE_KW.search(sr) and _SUPPLIER_UNFAVORABLE_CONFIRM.search(sr):
            harm_score += 1

        if harm_score < 2:
            continue

        # 2개 이상 YES → 자동 대체 시도
        patched = sr
        for pattern, replacement in _SUPPLIER_AUTO_REWRITE:
            patched = pattern.sub(replacement, patched)

        if patched != sr:
            cr["suggested_rewrite"] = patched
            cr.setdefault("guardrail_block", {})["supplier_harm_gate"] = {
                "harm_score": harm_score,
                "action": "auto_rewrite",
            }
        else:
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["has_rewrite_change"] = False
            cr.setdefault("guardrail_block", {})["supplier_harm_gate"] = {
                "harm_score": harm_score,
                "action": "discarded",
            }


# =============================================================================
# [STEP 5B] Redline Safety Check — 문장 훼손 감지 및 guidance-only 전환
# requirement.md > [STEP 5] Redline 생성 수정
# =============================================================================

_REDLINE_CORRUPTION_KW = re.compile(
    r"\[원문\]\s*\[수정\]|\{before\}|\{after\}|<before>|<after>"
    r"|원문\s*:\s*.+\s*수정\s*:\s*.+"
    r"|\.\.\.\s*$|^\s*\.\.\.",
    re.IGNORECASE | re.DOTALL,
)

_REDLINE_TOKEN_MERGE_KW = re.compile(
    r"[가-힣]{1,3}\s+[a-zA-Z]{1,5}\s+[가-힣]{1,3}|"
    r"[^\s]{50,}",
)


def _apply_redline_safety_check(
    clause_results: list[dict[str, Any]],
    our_role: str,
    review_posture: str,
) -> None:
    """[STEP 5B] Redline Safety Check.
    문장 중간 삽입/문자열 병합/regex overwrite로 훼손된 redline을 감지하여
    해당 suggested_rewrite를 폐기하고 guidance-only 모드로 전환한다.
    공급자 모드 외에도 공통 적용한다.
    """
    import difflib as _dl

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
            continue
        if bool(cr.get("is_checklist_item")):
            continue

        sr = str(cr.get("suggested_rewrite") or "")
        if not sr.strip():
            continue

        original = str(cr.get("original_text") or "").strip()
        is_corrupted = False
        corruption_reason = ""

        # 감지 1: 명시적 훼손 마커
        if _REDLINE_CORRUPTION_KW.search(sr):
            is_corrupted = True
            corruption_reason = "explicit_corruption_marker"

        # 감지 2: 원문이 충분히 길 때, 수정안이 원문과 지나치게 유사하면서 매우 짧은 경우
        if not is_corrupted and original and len(original) > 150 and len(sr) < len(original) * 0.3:
            ratio = _dl.SequenceMatcher(None, original[:300], sr[:300]).ratio()
            if ratio > 0.75:
                is_corrupted = True
                corruption_reason = "truncated_fragment"

        # 감지 3: 수정안이 원문과 동일한 경우 (변경 없음)
        if not is_corrupted and original and sr.strip() == original.strip():
            is_corrupted = True
            corruption_reason = "identical_to_original"

        if is_corrupted:
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            cr["has_rewrite_change"] = False
            cr.setdefault("guardrail_block", {})["redline_safety"] = {
                "reason": corruption_reason,
                "action": "guidance_only",
            }


# =============================================================================
# [Dealer Rental Final Gate] dealer_rental_service_contract 전용 최종 차단 필터
# 11개 ID 완전 제거 + 조항-문안 hard gate (termination/assignment/confidentiality)
# =============================================================================

_DEALER_RENTAL_HARD_BLOCKED_IDS: frozenset = frozenset({
    # isr_* (industry-specific review — 제조물/설치 안전)
    "isr_accident_reporting", "isr_pl_defect_liability", "isr_installation_defect",
    "isr_user_safety", "isr_safety_certification", "isr_pl_insurance", "isr_defect_sla",
    "isr_defect_correction",
    # sppc_* (supplier product purchase checklist)
    "sppc_inspection_standard", "sppc_return_limit", "sppc_payment_retention",
    "sppc_custom_cancel_limit",
    # pi_* (project/installation/산업안전보건/중대재해)
    "pi_safety_responsibility", "pi_safety_manager", "pi_legal_compliance",
    "pi_subcontractor_safety", "pi_work_stop_right", "pi_risk_assessment",
    "pi_accident_reporting", "pi_ppe_education", "pi_access_control",
    "pi_commissioning_accident_liability",
})

# 프리픽스 기반 차단 (ID가 구체적으로 등록되지 않은 파생 항목 포함)
_DEALER_RENTAL_BLOCKED_PREFIXES: tuple = ("isr_", "sppc_", "pi_")

# clause_title 키워드 기반 차단
_DEALER_RENTAL_BLOCKED_TITLE_KEYWORDS: tuple = (
    "제조물검토", "안전권고", "산업안전보건법", "중대재해처벌법",
    "시공", "시운전", "착공", "하도급 안전", "보호구", "위험성 평가",
    "안전관리자",
)

# (clause_title 키워드 목록, forbidden 키워드 목록) 쌍
_DEALER_RENTAL_CLAUSE_TOPIC_GATE: list[tuple[list[str], list[str]]] = [
    (["해지", "종료", "해제"], ["소유권", "채권추심", "신용정보", "개인정보"]),
    (["양도", "지위 이전", "계약자 변경"], ["판촉비", "광고비", "반품비", "원상회복비", "비용분담"]),
    (["비밀", "기밀"], ["인력", "채용", "배치", "평가", "징계", "경영간섭"]),
]

_DEALER_RENTAL_MISMATCH_MSG = "자동수정 보류: 조항 주제와 수정문안 불일치"


def apply_dealer_rental_final_gate(
    clause_results: list[dict],
    contract_type_code: str,
) -> list[dict]:
    """dealer_rental_service_contract 전용 최종 차단 (Defense-in-depth Layer 2):
    1) isr_*/sppc_*/pi_* 프리픽스 또는 hard-blocked ID 완전 제거
    2) 차단된 clause_title 키워드 포함 항목 제거
    3) 조항 주제와 수정문안 불일치 시 suggested_rewrite 삭제
    """
    if contract_type_code != "dealer_rental_service_contract":
        return clause_results

    filtered: list[dict] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        cid = str(cr.get("clause_id") or "")
        # ID 기반 차단
        if cid in _DEALER_RENTAL_HARD_BLOCKED_IDS:
            continue
        # 프리픽스 기반 차단
        if any(cid.startswith(p) for p in _DEALER_RENTAL_BLOCKED_PREFIXES):
            continue
        # clause_title 키워드 기반 차단
        _ctitle = str(cr.get("clause_title") or "")
        if any(kw in _ctitle for kw in _DEALER_RENTAL_BLOCKED_TITLE_KEYWORDS):
            continue
        filtered.append(cr)

    for cr in filtered:
        if not isinstance(cr, dict):
            continue
        _ct = str(cr.get("clause_title") or "").lower()
        _sr = str(cr.get("suggested_rewrite") or "").strip()
        if not _sr or _sr == _DEALER_RENTAL_MISMATCH_MSG:
            continue
        for _title_kws, _forbidden_kws in _DEALER_RENTAL_CLAUSE_TOPIC_GATE:
            if any(k in _ct for k in _title_kws):
                if any(f in _sr for f in _forbidden_kws):
                    cr["suggested_rewrite"] = _DEALER_RENTAL_MISMATCH_MSG
                    cr["has_rewrite_change"] = False
                    cr["display_kind"] = "guidance"
                break

    return filtered


# =============================================================================


def build_clause_level_result(
    *,
    service: RuleQueryService,
    entity: str,
    contract_type: str,
    text: str,
    filename: str | None,
    answers: dict[str, Any] | None,
    review_focus: str | None = None,
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

    # ── [STEP 1 / Classification First] 계약 유형·실질 최우선 확정 ────────────
    # requirement.md > STEP 1 (경제적 실질 기반), Advanced Strategic Logic > Phase 1
    #
    # 계약유형 판단은 runtime.review.contract_classifier(단일 정본 분류기)를 우선
    # 참조한다. 특히 시험·검사·인증 용역처럼 이 파일의 로컬 6분류
    # (_classify_contract_type_by_substance)가 커버하지 않는 유형은 정본 분류
    # 결과를 그대로 신뢰하고, 그 외 유형은 기존 로컬 분류 결과를 유지해
    # 기존 advisory/rental/construction/project_installation 테스트를 깨지 않는다.
    # answers에 사용자가 직접 확인한 계약유형(Q-TYPE-001)이 있으면 그것을 최우선한다.
    from runtime.review.contract_classifier import classify_contract_detailed as _cc_canonical
    _canonical_profile = _cc_canonical(
        entity=str(entity), contract_type=str(contract_type), text=str(text or ""),
        filename=filename, answers=answers,
    )
    if _canonical_profile.contract_type == "testing_inspection_service":
        _contract_class = "testing_service"
    else:
        _contract_class = _classify_contract_type(str(contract_type), str(text or ""), filename)
    _contract_nature = _classify_contract_nature(str(contract_type), str(text or ""))
    _is_advisory_class = (_contract_class == "advisory")
    _is_rental_class = (_contract_class == "rental")
    _is_construction_class = (_contract_class == "construction")
    _is_project_install_class = (_contract_class == "project_installation")

    # [Layer 0 — Contract Legal Map] requirement.md 2026-08-28 / 변호사형
    # 전체계약 판단(2026-09-01): 개별 조항 검토를 시작하기 전에 계약 전체를
    # 한 번 읽고 당사자·거래구조·의무구조·해지구조·책임구조 등을 먼저
    # 구조화한다. AI가 있으면 실제 AI 호출로 채우고(계약당 1회), 없으면
    # 기존 regex 기반 4필드만으로 축소판을 반환한다 — 어느 쪽이든 이후
    # Layer 1(공통 법률효과)·Layer 2(유형별) 조항 검토가 이 결과를 공유
    # 컨텍스트로 사용한다.
    # party/역할 판정보다 먼저 실행해야 아래에서 그 결과로 override할 수 있다.
    clauses, clause_report = extract_clauses(text)
    from runtime.review.contract_legal_map import build_contract_legal_map
    _legal_map = build_contract_legal_map(
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_timeout_sec=ai_timeout_sec,
        ai_max_tokens=ai_max_tokens,
        ai_temperature=ai_temperature,
        entity=str(entity),
        contract_type=str(contract_type),
        contract_type_code=str(_canonical_profile.contract_type or ""),
        text=str(text or ""),
        clauses=clauses,
    )
    # [거래구조 확인 질문 답변 반영, 2026-09-04 지시] — AI 없이도(regex
    # fallback 경로 포함) 사용자가 Q-TXN-* 질문에 실제로 답변한 판매자·
    # 소유권·대금수령 등 사실관계를 Contract Legal Map에 채운다.
    from runtime.review.transaction_structure_answers import apply_transaction_structure_answers
    apply_transaction_structure_answers(_legal_map.fields, answers)
    from runtime.review.contract_overview import build_contract_overview
    _contract_overview = build_contract_overview(clauses=clauses, full_text=str(text or ""))
    _contract_overview_dict = {**_contract_overview.to_dict(), **_legal_map.to_dict()}

    # [Mandatory Legal Applicability Review] 2026-09-02 지시 — 사용자가
    # review_focus에서 특정 법률의 적용 여부를 직접 물었다면 rule hit
    # 개수와 무관하게 그 법률 각각에 대한 독립적인 분석을 반드시 산출한다.
    # 이어서(2026-09-02 후속 지시) 사용자가 법률을 하나도 지정하지 않아도,
    # AI가 사용 가능하면 build_mandatory_legal_applicability_review()가
    # 계약 구조를 스스로 읽고 문제될 만한 법률을 자체 판단해 추가한다
    # (사내변호사가 의뢰인이 안 물어본 법률도 먼저 짚어주는 것과 동일한
    # 원칙) — 그래서 _cited_statutes가 비어 있어도 이 함수는 항상 호출한다.
    from runtime.review.legal_applicability_review import (
        detect_user_cited_statutes,
        infer_additional_relevant_statutes,
        build_mandatory_legal_applicability_review,
    )
    _cited_statutes = detect_user_cited_statutes(review_focus)
    # 사용자가 특정 법률을 나열한 뒤 "그 외 법령"처럼 포괄적 검토를
    # 요청했다면, 실제 계약 구조상 문제될 만한 다른 법률도 놓치지 않는다
    # (2026-09-02 실사례: "하도급법, 건설산업기본법 그외 법령상 문제가
    # 없는지"라는 요청에서 공정거래법이 문언에 없다는 이유만으로 통째로
    # 누락됨).
    _cited_statutes = _cited_statutes + infer_additional_relevant_statutes(
        review_focus=review_focus, text=str(text or ""), already_cited=_cited_statutes,
    )
    _legal_applicability_results = build_mandatory_legal_applicability_review(
        statutes=_cited_statutes,
        contract_legal_map=_legal_map.to_dict(),
        text=str(text or ""),
        entity=str(entity),
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_timeout_sec=ai_timeout_sec,
        ai_max_tokens=ai_max_tokens,
        ai_temperature=ai_temperature,
    )

    # [REMOVED] 관련 법령 retrieval 영구 비활성화 — requirement.md > Section Removal Specs
    law_service = None

    # Phase 2: LLM-based contract metadata extraction (lightweight, ~512 tokens)
    # Augments answers with cross-border/governing_law signals for downstream pipeline
    _llm_meta: dict[str, Any] = {}
    if ai_provider is not None and ai_model:
        from runtime.review.meta_extractor import extract_contract_meta
        try:
            _llm_meta = extract_contract_meta(
                str(text or ""),
                ai_provider=ai_provider,
                model=str(ai_model),
                max_tokens=512,
                timeout_sec=min(30.0, float(ai_timeout_sec or 30.0)),
                temperature=0.1,
            )
        except Exception:
            _llm_meta = {}
    _answers_aug = dict(answers or {})
    if _llm_meta and not _answers_aug.get("jurisdiction"):
        if _llm_meta.get("is_cross_border"):
            _answers_aug["jurisdiction"] = "foreign"
        glaw = str(_llm_meta.get("governing_law") or "")
        if glaw and "korean" not in glaw.lower() and "korea" not in glaw.lower():
            _answers_aug["governing_law"] = glaw
    if _llm_meta:
        _answers_aug["_llm_meta"] = _llm_meta
    answers = _answers_aug

    party = infer_party_role(
        entity=str(entity), contract_type=str(contract_type), text=str(text), answers=answers,
        contract_type_code=_canonical_profile.contract_type,
    )
    # [Layer 0 우선 원칙] rule 기반 classifier/party_role이 처음 보는
    # 계약유형(라이선스·임대차 등)에서 당사자 방향(공급자/구매자)을 반대로
    # 판정하는 사례가 hold-out 검증에서 발견되어, Contract Legal Map이 AI로
    # 실행되었고 확신도가 high일 때만 이 축(provider/recipient)을 우선하는
    # source of truth로 삼는다. AI 미실행/저확신/판정불가 시 기존 rule 결과를
    # 그대로 유지 — 조용한 override가 아니라 meta.legal_map_role_override로
    # 항상 기록된다.
    from runtime.review.legal_map_role_override import apply_legal_map_role_override
    _canonical_profile, party, _role_override_audit = apply_legal_map_role_override(
        canonical_profile=_canonical_profile,
        party=party,
        legal_map_dict=_legal_map.to_dict(),
        legal_map_source=_legal_map.source,
    )
    review_posture = infer_review_posture(
        party=party, contract_type=str(contract_type), text=str(text),
        contract_type_code=str(_canonical_profile.contract_type or ""),
    )
    review = service.analyze(
        ReviewInput(
            entity=entity,
            contract_type=contract_type,
            text=text,
            filename=filename,
            answers=answers,
            review_focus=review_focus,
        )
    )
    _hard_block_out_of_scope_rules(review, _contract_class)
    derived = review.get("derived_context") if isinstance(review, dict) else None
    prof = infer_contract_profile(
        contract_type=str(contract_type), text=str(text or ""),
        canonical_type_code=str(_canonical_profile.contract_type or ""),
    )
    frc = build_final_review_context(
        entity=str(entity),
        contract_type=str(contract_type),
        text=str(text or ""),
        filename=filename,
        answers=answers,
        review_focus=review_focus,
        party_role=(party.to_dict() if party is not None else None),
    )
    # Detect dealer-direct contract structure for structure-aware review
    _struct = detect_contract_structure(
        text=str(text or ""),
        entity=str(entity or ""),
        contract_type=str(contract_type or ""),
    )
    contract_context = {
        "entity": str(entity),
        "contract_type": str(contract_type),
        "contract_text": str(text or ""),
        "jurisdiction": (derived.get("jurisdiction") if isinstance(derived, dict) else None),
        "contract_profile": prof.to_dict(),
        "final_review_context": frc.to_dict(),
        "contract_structure": _struct.contract_structure,
        "structure_result": _struct.to_dict(),
        "contract_overview": _contract_overview_dict,
    }
    revision = suggest_revisions(
        clauses,
        review.get("matched_rules", []),
        posture=review_posture,
        party=party,
        contract_context=contract_context,
    )

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
    focus_codes = [str(x.code) for x in (frc.user_focus_issues or []) if isinstance(getattr(x, "code", None), str)]
    review_obj_codes = [str(x.code) for x in (frc.review_objectives or []) if isinstance(getattr(x, "code", None), str)]
    focus_topics = objective_codes_to_clause_topics(focus_codes)
    focus_topics_by_code: dict[str, set[str]] = {c: objective_codes_to_clause_topics([c]) for c in focus_codes}
    derived_codes = [c for c in review_obj_codes if c not in set(focus_codes)]
    derived_topics = objective_codes_to_clause_topics(derived_codes)
    derived_topics_by_code: dict[str, set[str]] = {c: objective_codes_to_clause_topics([c]) for c in derived_codes}
    focus_title_by_code_obj: dict[str, str] = {str(x.code): str(x.title) for x in (frc.user_focus_issues or []) if isinstance(getattr(x, "code", None), str)}
    derived_title_by_code_obj: dict[str, str] = {str(x.code): str(x.title) for x in (frc.review_objectives or []) if isinstance(getattr(x, "code", None), str) and str(x.code) in set(derived_codes)}
    focus_keywords_by_code_obj: dict[str, list[str]] = {
        str(x.code): [str(k) for k in (x.keywords or []) if isinstance(k, str) and str(k).strip()]
        for x in (frc.user_focus_issues or [])
        if isinstance(getattr(x, "code", None), str)
    }
    dealer_focus_articles_by_code: dict[str, set[int]] = {}
    if prof.profile == "dealer_consignment":
        for c in focus_codes:
            if c == "dealer_unfair_disadvantage":
                # 제2조·제3조(선언적 조항)는 하드블록 대상이므로 제외, 실질 조항만 매핑
                dealer_focus_articles_by_code[c] = {21, 23}
            elif c == "dealer_management_interference":
                dealer_focus_articles_by_code[c] = {5, 14, 18}
            elif c == "termination_abuse":
                dealer_focus_articles_by_code[c] = {23, 24}
            elif c == "dealer_cost_shift":
                dealer_focus_articles_by_code[c] = {11, 17}
            elif c == "settlement_offset":
                dealer_focus_articles_by_code[c] = {8, 9, 10}
    for it in items:
        if not isinstance(it, dict):
            continue
        clause_id = str(it.get("clause_id") or "")
        chunk = chunk_by_id.get(clause_id)
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
                        "context_expanded_by_questions": bool(base.get("context_expanded_by_questions")),
                        "context_expanded_by_text": bool(base.get("context_expanded_by_text")),
                        "description": base.get("description"),
                        "review_action": base.get("review_action") if isinstance(base.get("review_action"), list) else [],
                        "worst_case_scenario": base.get("worst_case_scenario"),
                        "negotiation_strategy": base.get("negotiation_strategy"),
                        "tags": base.get("tags") if isinstance(base.get("tags"), list) else [],
                        "matched_keywords": ar.get("matched_keywords") if isinstance(ar.get("matched_keywords"), list) else [],
                    }
                )
            else:
                related_rules.append(dict(ar))

        question_context_hit = any(bool(r.get("context_expanded_by_questions")) for r in related_rules if isinstance(r, dict))
        recommended = it.get("recommended_rewrite")
        fallback_texts = it.get("fallback_text") if isinstance(it.get("fallback_text"), list) else []
        suggested_rewrite = recommended if isinstance(recommended, str) and recommended.strip() else (fallback_texts[0] if fallback_texts else None)
        clause_title = (str(chunk.title) if isinstance(chunk, ClauseChunk) and chunk.title is not None else None) or str(it.get("clause_title") or "")
        original_text = (str(chunk.text) if isinstance(chunk, ClauseChunk) and chunk.text is not None else None) or str(it.get("original_clause") or "")
        article_number = (chunk.article_number if isinstance(chunk, ClauseChunk) and chunk.article_number else it.get("article_number"))
        if not str(article_number or "").strip():
            article_number = str(_article_int(clause_id) or _article_int(it.get("display_path")) or _article_int(clause_title) or "") or None
        clause_topic = classify_clause_topic(title=clause_title, text=original_text)
        if prof.profile == "dealer_consignment":
            a0 = _article_int(article_number) or _article_int(clause_id) or _article_int(it.get("display_path")) or _article_int(clause_title)
            if a0 in (23, 24):
                clause_topic = "termination"
        focus_match_codes = [c for c, ts in focus_topics_by_code.items() if clause_topic in ts]
        hay_low = (clause_title + "\n" + original_text + "\n" + str(it.get("context_text") or "")).lower()
        for code, kws in focus_keywords_by_code_obj.items():
            if not code or code in focus_match_codes:
                continue
            if any((k.lower() in hay_low) for k in kws if k):
                focus_match_codes.append(code)
        if prof.profile == "dealer_consignment" and dealer_focus_articles_by_code:
            a0 = _article_int((chunk.article_number if isinstance(chunk, ClauseChunk) and chunk.article_number else it.get("article_number")))
            if a0 is None:
                a0 = _article_int(clause_id) or _article_int(it.get("display_path")) or _article_int(clause_title)
            if a0 is not None:
                for code, aset in dealer_focus_articles_by_code.items():
                    if code and code not in focus_match_codes and a0 in aset:
                        focus_match_codes.append(code)
        user_focus_hit = bool(focus_match_codes) or (clause_topic in focus_topics)
        factual_match_codes = [c for c, ts in derived_topics_by_code.items() if clause_topic in ts]
        factual_hit = bool(factual_match_codes) or (clause_topic in derived_topics)
        keep_as_is = _is_keep_as_is_clause(title=clause_title, text=original_text)
        any_medium = any(
            (isinstance(r, dict) and str(r.get("risk_level") or "").strip().upper() == "MEDIUM") for r in related_rules
        )
        any_low = any((isinstance(r, dict) and str(r.get("risk_level") or "").strip().upper() == "LOW") for r in related_rules)
        risk_tier = "HIGH" if (bool(it.get("approval_required")) or bool(it.get("high_risk"))) else ("MEDIUM" if any_medium else ("LOW" if any_low else "MEDIUM"))
        must_fix = bool(it.get("approval_required")) or bool(it.get("high_risk")) or risk_tier == "HIGH"
        review_tier = "MUST" if must_fix else ("SUGGEST" if risk_tier == "MEDIUM" else "NOTE")

        rewrite_reason = it.get("rewrite_reason")
        if keep_as_is:
            suggested_rewrite = None
            rewrite_reason = "법령 준수 일반원칙 문구는 현행 유지(수정 필요 없음)."
            risk_tier = "LOW"
            must_fix = False
            review_tier = "NOTE"

        a_i = _article_int(article_number) or _article_int(clause_id) or _article_int(it.get("display_path")) or _article_int(clause_title)
        ct_hb = clause_topic if isinstance(clause_topic, str) else None
        if _is_hard_block_clause(article_int=a_i, title=str(clause_title or ""), clause_topic=ct_hb):
            suggested_rewrite = None
            rewrite_reason = "원문 유지(하드 블록: 메타/분쟁 조항)."
            risk_tier = "LOW"
            must_fix = False
            review_tier = "NOTE"
            user_focus_hit = False
            factual_hit = False
            focus_match_codes = []
            factual_match_codes = []
            related_rules = []

        clause_results.append(
            {
                "clause_id": clause_id,
                "article_number": article_number,
                "paragraph_number": (chunk.paragraph_number if isinstance(chunk, ClauseChunk) and chunk.paragraph_number else it.get("paragraph_number")),
                "item_number": (chunk.item_number if isinstance(chunk, ClauseChunk) and chunk.item_number else it.get("item_number")),
                "subitem_number": (chunk.subitem_number if isinstance(chunk, ClauseChunk) and chunk.subitem_number else it.get("subitem_number")),
                "display_path": it.get("display_path") or (chunk_by_id.get(clause_id).display_path if chunk_by_id.get(clause_id) else None),
                "parent_clause_id": it.get("parent_clause_id") or (chunk_by_id.get(clause_id).parent_clause_id if chunk_by_id.get(clause_id) else None),
                "context_text": it.get("context_text") or (chunk_by_id.get(clause_id).context_text if chunk_by_id.get(clause_id) else None),
                "clause_title": clause_title,
                "original_text": original_text,
                "clause_topic": (clause_topic if clause_topic != "other" else None),
                "user_focus_matches": focus_match_codes,
                "user_focus_hit": bool(user_focus_hit),
                "user_focus_match_titles": [focus_title_by_code_obj.get(str(c), str(c)) for c in focus_match_codes if str(c)],
                "factual_matches": factual_match_codes,
                "factual_hit": bool(factual_hit),
                "factual_match_titles": [derived_title_by_code_obj.get(str(c), str(c)) for c in factual_match_codes if str(c)],
                "detected_issue_list": ([] if _is_hard_block_clause(article_int=a_i, title=str(clause_title or ""), clause_topic=ct_hb) else (it.get("detected_issues") if isinstance(it.get("detected_issues"), list) else [])),
                "related_rules": related_rules,
                "question_context_hit": bool(question_context_hit),
                "related_laws": None,
                "rewrite_reason": rewrite_reason,
                "suggested_direction": ([] if _is_hard_block_clause(article_int=a_i, title=str(clause_title or ""), clause_topic=ct_hb) else (it.get("suggested_direction") if isinstance(it.get("suggested_direction"), list) else [])),
                "suggested_rewrite": suggested_rewrite,
                "approval_required": bool(it.get("approval_required")) if not (keep_as_is or _is_hard_block_clause(article_int=a_i, title=str(clause_title or ""), clause_topic=ct_hb)) else False,
                "high_risk": bool(it.get("high_risk")) if not (keep_as_is or _is_hard_block_clause(article_int=a_i, title=str(clause_title or ""), clause_topic=ct_hb)) else False,
                "risk_tier": risk_tier,
                "must_fix": must_fix,
                "review_tier": review_tier,
                "unfavorable_to_us": bool(it.get("unfavorable_to_us")),
                "keep_as_is": bool(keep_as_is),
                "worst_case_scenario": next((r.get("worst_case_scenario") for r in related_rules if isinstance(r, dict) and r.get("worst_case_scenario")), None),
                "negotiation_strategy": next((r.get("negotiation_strategy") for r in related_rules if isinstance(r, dict) and r.get("negotiation_strategy")), None),
            }
        )

    existing_ids = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if prof.profile == "dealer_consignment":
        # 제1·2·3조(목적/기본원칙/용어정의) 제외 — 하드블록 선언적 조항
        must_articles = {8, 9, 10, 11, 14, 17, 21, 23, 27}
        for c in clauses:
            cid = str(c.clause_id or "")
            if not cid or cid in existing_ids:
                continue
            a = _article_int(c.article_number) or _article_int(cid) or _article_int(c.display_path) or _article_int(c.title)
            # 하드블록 조항은 dealer screening에서도 제외
            if _is_hard_block_clause(article_int=a, title=str(c.title or "")):
                continue
            hay_key = (str(c.display_path or "") + " " + str(c.title or "")).strip()
            is_key_by_title = any(
                k in hay_key
                for k in (
                    "공정거래",
                    "동반성장",
                    "불공정",
                    "불이익",
                    "각종 불공정행위",
                    "계약해지",
                    "해지",
                    "인력",
                    "채용",
                    "운영비용",
                    "비용분담",
                    "광고",
                    "판촉",
                    "정산",
                    "상계",
                    "공제",
                    "분쟁해결",
                    "재판관할",
                    "관할",
                )
            )
            if not ((a is not None and a in must_articles) or is_key_by_title):
                continue
            article_number = c.article_number
            if not str(article_number or "").strip():
                article_number = str(a) if a is not None else None
            ct = classify_clause_topic(title=str(c.title or ""), text=str(c.text or ""))
            focus_match_codes = [code for code, ts in focus_topics_by_code.items() if ct in ts]
            hay_low = (str(c.display_path or "") + "\n" + str(c.title or "") + "\n" + str(c.text or "") + "\n" + str(c.context_text or "")).lower()
            for code, kws in focus_keywords_by_code_obj.items():
                if not code or code in focus_match_codes:
                    continue
                if any((k.lower() in hay_low) for k in kws if k):
                    focus_match_codes.append(code)
            if dealer_focus_articles_by_code:
                for code, aset in dealer_focus_articles_by_code.items():
                    if code and code not in focus_match_codes and a in aset:
                        focus_match_codes.append(code)
            factual_match_codes = [code for code, ts in derived_topics_by_code.items() if ct in ts]
            clause_results.append(
                {
                    "clause_id": cid,
                    "article_number": article_number,
                    "paragraph_number": c.paragraph_number,
                    "item_number": c.item_number,
                    "subitem_number": c.subitem_number,
                    "display_path": c.display_path,
                    "parent_clause_id": c.parent_clause_id,
                    "context_text": c.context_text,
                    "clause_title": c.title,
                    "original_text": c.text,
                    "clause_topic": (ct if ct != "other" else None),
                    "user_focus_matches": focus_match_codes,
                    "user_focus_hit": bool(focus_match_codes) or (ct in focus_topics),
                    "user_focus_match_titles": [focus_title_by_code_obj.get(str(c0), str(c0)) for c0 in focus_match_codes if str(c0)],
                    "factual_matches": factual_match_codes,
                    "factual_hit": bool(factual_match_codes) or (ct in derived_topics),
                    "factual_match_titles": [derived_title_by_code_obj.get(str(c0), str(c0)) for c0 in factual_match_codes if str(c0)],
                    "detected_issue_list": [],
                    "related_rules": [],
                    "question_context_hit": False,
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
            existing_ids.add(cid)
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
            # 하드블록 조항(제1·2·3조 등 선언적)은 screening에서도 제외
            _a_screen = _article_int(c.article_number) or _article_int(str(c.clause_id or "")) or _article_int(c.display_path) or _article_int(c.title)
            if _is_hard_block_clause(article_int=_a_screen, title=str(c.title or "")):
                continue
            ct = classify_clause_topic(title=str(c.title or ""), text=str(c.text or ""))
            focus_match_codes = [code for code, ts in focus_topics_by_code.items() if ct in ts]
            article_number = c.article_number
            if not str(article_number or "").strip():
                article_number = str(_article_int(str(c.clause_id or "")) or _article_int(c.display_path) or _article_int(c.title) or "") or None
            hay_low = (str(c.display_path or "") + "\n" + str(c.title or "") + "\n" + str(c.text or "") + "\n" + str(c.context_text or "")).lower()
            for code, kws in focus_keywords_by_code_obj.items():
                if not code or code in focus_match_codes:
                    continue
                if any((k.lower() in hay_low) for k in kws if k):
                    focus_match_codes.append(code)
            if prof.profile == "dealer_consignment" and dealer_focus_articles_by_code:
                a0 = _article_int(c.article_number) or _article_int(str(c.clause_id or "")) or _article_int(c.display_path) or _article_int(c.title)
                if a0 is not None:
                    for code, aset in dealer_focus_articles_by_code.items():
                        if code and code not in focus_match_codes and a0 in aset:
                            focus_match_codes.append(code)
            factual_match_codes = [code for code, ts in derived_topics_by_code.items() if ct in ts]
            clause_results.append(
                {
                    "clause_id": str(c.clause_id),
                    "article_number": article_number,
                    "paragraph_number": c.paragraph_number,
                    "item_number": c.item_number,
                    "subitem_number": c.subitem_number,
                    "display_path": c.display_path,
                    "parent_clause_id": c.parent_clause_id,
                    "context_text": c.context_text,
                    "clause_title": c.title,
                    "original_text": c.text,
                    "clause_topic": (ct if ct != "other" else None),
                    "user_focus_matches": focus_match_codes,
                    "user_focus_hit": bool(focus_match_codes) or (ct in focus_topics),
                    "user_focus_match_titles": [focus_title_by_code_obj.get(str(c0), str(c0)) for c0 in focus_match_codes if str(c0)],
                    "factual_matches": factual_match_codes,
                    "factual_hit": bool(factual_match_codes) or (ct in derived_topics),
                    "factual_match_titles": [derived_title_by_code_obj.get(str(c0), str(c0)) for c0 in factual_match_codes if str(c0)],
                    "detected_issue_list": [],
                    "related_rules": [],
                    "question_context_hit": False,
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

    # ── Phase 3 helper: 재판매가격 유지행위(RPM) 패턴 감지 ──────────────────
    _RPM_PATTERNS = re.compile(
        r"(판매가격|가격)\s*.{0,20}?\s*(승인|사전\s*승인|승인을\s*받|사전\s*동의|통보|결정권|통제|지정|강제)",
        re.IGNORECASE,
    )

    def _has_price_approval_risk(text: str) -> bool:
        return bool(_RPM_PATTERNS.search(text or ""))

    # ── payment_settlement 내용 가드: 실제 정산/공제/상계 문구가 있을 때만 주입 ──
    _SETTLEMENT_GUARD = re.compile(r"(공제|상계|차감|정산|감액|환입|환수)")

    if prof.profile == "dealer_consignment":
        # 조(article) 단위로 첫 번째 항에만 rewrite를 생성한다.
        # 같은 조의 나머지 항은 dedup에서 처리하므로 여기서 중복 생성하지 않는다.
        _seen_articles_for_dealer: set[str] = set()
        for cr in clause_results:
            if not isinstance(cr, dict):
                continue
            if bool(cr.get("keep_as_is")) or bool(cr.get("dedup_suppressed")):
                continue
            sr = cr.get("suggested_rewrite")
            if isinstance(sr, str) and sr.strip():
                continue
            ot = str(cr.get("original_text") or "")
            title = str(cr.get("clause_title") or "")
            if not ot.strip():
                continue
            ct0 = str(cr.get("clause_topic") or "").strip()
            # 조 번호 추출 (같은 조의 두 번째 항부터는 건너뜀)
            _an = str(cr.get("article_number") or "").strip()
            # ── Phase 3: 가격 구속(RPM) 우선 탐지 — 조 번호보다 내용 우선 ──────
            if _has_price_approval_risk(ot):
                _key = f"rpm_{_an}"
                if _key in _seen_articles_for_dealer:
                    continue
                _seen_articles_for_dealer.add(_key)
                cr["suggested_rewrite"] = re.sub(
                    r"(판매가격|가격)\s*.{0,30}?\s*(승인|사전\s*승인|승인을\s*받|사전\s*동의|통제|지정|강제)[^。.]*",
                    lambda m: m.group(0).replace(
                        m.group(0),
                        m.group(1) + "은(는) 을이 시장 상황을 반영하여 자율적으로 결정하되, "
                        "갑은 참고용 가이드라인(권장가)을 제시할 수 있다. "
                        "갑은 을의 판매가격을 지정·승인·강제하거나 특정 가격 준수를 조건으로 불이익 조치를 취하여서는 아니 된다.",
                    ),
                    ot,
                    count=1,
                )
                cr["suggested_direction"] = [
                    "판매가격 결정권을 을(대리점)에게 귀속",
                    "'승인' → '권장가 가이드라인(참고용)'으로 수정",
                    "가격 강제·불이익 조치 명시적 금지",
                ]
                cr["rewrite_reason"] = (
                    "판매가격 사전 승인 문구는 공정거래법상 재판매가격 유지행위(법 제46조)에 해당하여 "
                    "공정위 과징금·시정명령 대상이 될 수 있다. "
                    "'승인' 구조를 '권장가 가이드라인 제시'로 전환하여 규제 리스크를 제거한다."
                )
                cr["why_this_is_core_issue"] = (
                    "재판매가격 유지행위는 공정거래법 위반으로 공정위 과징금(관련 매출액 최대 10%) 대상이며, "
                    "대리점법상 경영간섭(제18조)과도 중첩된다."
                )
                cr["risk_tier"] = "HIGH"
                cr["must_fix"] = True
                cr["review_tier"] = "MUST"
                cr["approval_required"] = True
                continue
            if ct0 == "payment_settlement":
                # 내용 가드: 실제 공제/상계/정산 문구가 없으면 주입 금지 (대금수금 조항 오염 방지)
                if not _SETTLEMENT_GUARD.search(ot):
                    continue
                _key = f"payment_{_an}"
                if _key in _seen_articles_for_dealer:
                    continue
                _seen_articles_for_dealer.add(_key)
                add = (
                    "\n\n[추가]\n"
                    "① 정산은 항목별 산식과 기준에 따라 이루어지며, 공제/상계는 계약 또는 사전 서면합의에 근거한 경우에 한한다.\n"
                    "② 갑은 정산서(항목별 내역) 및 합리적 범위의 증빙을 제공하고, 을은 일정 기간 내 이의제기할 수 있다.\n"
                )
                cr["suggested_rewrite"] = (ot.rstrip() + add).strip()
                cr["suggested_direction"] = [
                    "공제/상계 요건을 계약/서면합의로 제한",
                    "정산서·증빙 제공 및 이의제기 절차 명문화",
                ]
                cr["rewrite_reason"] = "정산/상계/공제 구조가 불명확하면 불이익 제공·거래상 지위 남용 논점으로 연결될 수 있어, 산식·증빙·이의 절차를 구체화한다."
                cr["risk_tier"] = "MEDIUM"
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
                continue
            a = _article_int_from_cr(cr)
            if a is None:
                continue
            if a in (23, 24):
                _key = f"termination_{_an}"
                if _key in _seen_articles_for_dealer:
                    continue
                _seen_articles_for_dealer.add(_key)
                add = (
                    "\n\n[추가]\n"
                    "① 갑은 을의 본 계약상 의무 위반이 객관적으로 중대하고 회복 곤란한 경우에 한하여 계약을 해지할 수 있다.\n"
                    "② 갑이 계약을 해지하려면 원칙적으로 위반 사항을 특정하여 서면으로 최고하고, 을에게 상당한 시정기간(예: 15일 이상)을 부여하여야 한다.\n"
                    "③ 다만, (i) 고의적·중대한 법령 위반, (ii) 대금 편취 등 신뢰관계를 본질적으로 훼손하는 행위, (iii) 반복 위반으로 시정이 기대되기 어려운 경우에는 즉시 해지를 허용할 수 있다.\n"
                    "④ 해지 시에는 정산/반품/자료 반환 등 후속 절차와 기준을 서면으로 명확히 한다.\n"
                )
                cr["suggested_rewrite"] = (ot.rstrip() + add).strip()
                cr["suggested_direction"] = [
                    "즉시 해지 사유를 객관적·중대한 위반으로 한정",
                    "원칙적으로 서면 최고 및 시정기간 부여",
                    "예외적 즉시 해지 사유를 좁게 열거",
                    "해지 시 정산/인수인계 절차 명확화",
                ]
                cr["rewrite_reason"] = "계약해지/물량축소 등 불이익 조치가 일방적으로 운용되면 대리점법상 불이익 제공 및 거래상 지위 남용으로 해석될 소지가 있어, 해지 요건·절차를 객관화/한정한다."
                cr["why_this_is_core_issue"] = "대리점 계약에서 해지/공급중단 등 불이익 조치는 거래상 지위 남용과 직접 연결되며, 즉시해지 남용은 분쟁·손실로 직결된다."
                cr["risk_tier"] = "HIGH"
                cr["must_fix"] = True
                cr["review_tier"] = "MUST"
            elif a == 21 or ("불공정" in title or "불이익" in title):
                _key = f"unfair_{_an}"
                if _key in _seen_articles_for_dealer:
                    continue
                _seen_articles_for_dealer.add(_key)
                add = (
                    "\n\n[추가]\n"
                    "① 갑은 을에게 거래상 지위를 이용하여 부당하게 불이익을 제공하거나, 부당한 비용을 전가하거나, 거래조건을 일방적으로 변경하여서는 아니 된다.\n"
                    "② 갑은 판매장려금/판촉비/광고비/반품비 등 비용 부담 또는 공제/상계가 발생하는 경우, 항목·산정기준·증빙·정산시기를 사전에 서면으로 합의하여야 한다.\n"
                    "③ 을은 정산의 적정성 확인을 위해 갑에게 관련 자료(정산내역/산정근거/증빙)의 제공을 요청할 수 있으며, 갑은 합리적 범위에서 이에 협조한다.\n"
                )
                cr["suggested_rewrite"] = (ot.rstrip() + add).strip()
                cr["suggested_direction"] = [
                    "불이익 제공/지위 남용 금지 문구를 명시",
                    "비용부담/공제는 사전 서면합의·기준·증빙을 요건화",
                    "정산자료 확인권(자료제공 협조)을 명문화",
                ]
                cr["rewrite_reason"] = "대리점법상 불이익 제공 및 거래상 지위 남용 리스크를 줄이기 위해, 불공정행위 금지의무를 구체화하고 비용전가·정산자료 통제에 대한 장치를 명시한다."
                cr["risk_tier"] = "HIGH"
                cr["must_fix"] = True
                cr["review_tier"] = "MUST"
            elif a == 14 or ("인력" in title or "채용" in title or "교육" in title):
                _key = f"staff_{_an}"
                if _key in _seen_articles_for_dealer:
                    continue
                _seen_articles_for_dealer.add(_key)
                add = (
                    "\n\n[추가]\n"
                    "① 을의 인력 채용·배치·평가·징계 등 인사관리는 을의 책임과 재량에 따른다.\n"
                    "② 갑이 운영기준/서비스 품질 기준을 제시하는 경우에도, 갑은 을의 인력 운용에 관하여 직접적·구체적으로 지시하거나 개별 인력에 대한 평가/교체를 강제하지 않는다.\n"
                )
                cr["suggested_rewrite"] = (ot.rstrip() + add).strip()
                cr["suggested_direction"] = [
                    "인사(채용/배치/평가) 자율성 보장",
                    "운영기준 제시는 허용하되 직접 지시/강제는 제한",
                ]
                cr["rewrite_reason"] = "수탁자 인력 채용·배치·평가에 대한 직접 통제는 경영간섭/영업자율 침해로 해석될 소지가 있어, 운영기준과 인사권의 경계를 명확히 한다."
                cr["risk_tier"] = "MEDIUM"
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
            elif a in (11, 17) or ("광고" in title or "판촉" in title or "비용" in title):
                _key = f"cost_{_an}"
                if _key in _seen_articles_for_dealer:
                    continue
                _seen_articles_for_dealer.add(_key)
                add = (
                    "\n\n[추가]\n"
                    "① 판촉비/광고비/반품비/원상회복 비용 등 을이 부담하는 비용 항목은 사전에 항목별로 서면 합의하며, 상한(캡) 및 산정 기준을 명확히 한다.\n"
                    "② 갑은 비용 정산 또는 공제/상계를 하려는 경우, 을에게 사전 통지하고 정산내역과 증빙을 제공하며, 을에게 이의제기 기간을 부여한다.\n"
                )
                cr["suggested_rewrite"] = (ot.rstrip() + add).strip()
                cr["suggested_direction"] = [
                    "비용부담 항목/기준을 사전 서면합의로 고정",
                    "상한(캡)·증빙·이의제기 절차를 포함",
                ]
                cr["rewrite_reason"] = "판촉비/광고비 분담이 사전 서면합의·항목별 기준 없이 운용되면 비용전가 분쟁이 발생할 수 있어, 기준·상한·증빙·이의 절차를 명확히 한다."
                cr["risk_tier"] = "MEDIUM"
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
            elif a in (8, 9, 10) or ("정산" in title or "상계" in title or "공제" in title):
                # 내용 가드: 조 번호가 8/9/10이라는 이유만으로 주입하지 않는다
                # — 실제 정산/공제/상계 문구가 있을 때만(payment_settlement
                # 분기와 동일 가드). 2026-09-01: dealer_consignment로 잘못
                # 분류된 문서에서 이 번호 매칭만으로 반환·양도금지 조항에
                # 무관한 "정산" 문구가 주입된 사고 재발 방지.
                if not _SETTLEMENT_GUARD.search(ot):
                    continue
                _key = f"settlement_{_an}"
                if _key in _seen_articles_for_dealer:
                    continue
                _seen_articles_for_dealer.add(_key)
                add = (
                    "\n\n[추가]\n"
                    "① 정산은 항목별 산식과 기준에 따라 이루어지며, 공제/상계는 계약 또는 사전 서면합의에 근거한 경우에 한한다.\n"
                    "② 갑은 정산서(항목별 내역) 및 합리적 범위의 증빙을 제공하고, 을은 일정 기간 내 이의제기할 수 있다.\n"
                )
                cr["suggested_rewrite"] = (ot.rstrip() + add).strip()
                cr["suggested_direction"] = [
                    "공제/상계 요건을 계약/서면합의로 제한",
                    "정산서·증빙 제공 및 이의제기 절차 명문화",
                ]
                cr["rewrite_reason"] = "정산/상계/공제 구조가 불명확하면 불이익 제공·거래상 지위 남용 논점으로 연결될 수 있어, 산식·증빙·이의 절차를 구체화한다."
                cr["risk_tier"] = "MEDIUM"
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"

    # 하드블록 조항(제1·2·3조 등)을 clause_results에서 완전히 제거
    clause_results = [
        cr for cr in clause_results
        if not _is_hard_block_clause(
            article_int=_article_int_from_cr(cr),
            title=str(cr.get("clause_title") or ""),
        )
    ]

    def _is_high_risk(x: dict) -> bool:
        tier = str(x.get("risk_tier") or "").upper()
        return tier == "HIGH" or bool(x.get("approval_required")) or bool(x.get("high_risk"))

    if prof.profile == "dealer_consignment":
        clause_results = sorted(
            clause_results,
            key=lambda x: (
                0 if _is_high_risk(x) else 1,
                0 if bool(x.get("must_fix")) else 1,
                0 if bool(x.get("user_focus_hit")) else 1,
                _dealer_issue_rank(x if isinstance(x, dict) else {}),
                0 if str(x.get("risk_tier") or "").upper() == "MEDIUM" else 1,
                0 if bool(x.get("factual_hit")) else 1,
                0 if bool(x.get("question_context_hit")) else 1,
                str(x.get("clause_id") or ""),
            ),
        )
    else:
        clause_results = sorted(
            clause_results,
            key=lambda x: (
                0 if _is_high_risk(x) else 1,
                0 if bool(x.get("must_fix")) else 1,
                0 if bool(x.get("user_focus_hit")) else 1,
                0 if str(x.get("risk_tier") or "").upper() == "MEDIUM" else 1,
                0 if bool(x.get("factual_hit")) else 1,
                0 if bool(x.get("question_context_hit")) else 1,
                str(x.get("clause_id") or ""),
            ),
        )
    clause_results = [cr for cr in clause_results if not _contains_wordprocessingml_markers(str(cr.get("original_text") or ""))]

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        sr = cr.get("suggested_rewrite")
        ot = cr.get("original_text")
        has_change = bool(isinstance(sr, str) and sr.strip() and _norm_text_for_change(sr) != _norm_text_for_change(str(ot or "")))
        cr["has_rewrite_change"] = bool(has_change)
        if bool(cr.get("keep_as_is")):
            change_type = "keep_as_is"
        elif bool(cr.get("dedup_suppressed")):
            change_type = "suppressed"
        elif has_change:
            change_type = "modified"
        else:
            change_type = "unchanged"
        cr["change_record"] = {
            "change_type": change_type,
            "changed_segments": cr.get("changed_segments") if isinstance(cr.get("changed_segments"), list) else [],
            "why_changed": cr.get("rewrite_reason"),
        }
        if bool(cr.get("dedup_suppressed")):
            cr["display_kind"] = "guidance"
        elif bool(cr.get("keep_as_is")):
            cr["display_kind"] = "keep"
        elif has_change and (bool(cr.get("must_fix")) or bool(cr.get("approval_required")) or bool(cr.get("high_risk"))):
            cr["display_kind"] = "redline"
        elif has_change:
            cr["display_kind"] = "guidance"
        elif bool(cr.get("user_focus_hit")) or bool(cr.get("must_fix")) or str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM"):
            cr["display_kind"] = "guidance"
        else:
            cr["display_kind"] = "note"

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

    # [Original Text Integrity] AI 선정보다 먼저 실행 — 기존 호출은 이 함수
    # 훨씬 아래(여러 룰체인 이후)에 있어, 그 시점까지는 AI가 이미 오염된
    # original_text를 넘겨받아 rewrite를 생성한 뒤였다. 여기서 한 번 더 실행해
    # 지금까지 채워진 clause_results의 오염을 AI 선정 전에 걸러내고, 이후
    # 새로 추가되는 룰체인의 오염은 기존 위치의 재호출이 마저 잡는다
    # (멱등 함수라 두 번 호출해도 안전함).
    _apply_original_text_integrity_guard(clause_results)

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

    frc0 = contract_context.get("final_review_context") if isinstance(contract_context, dict) else None
    jur0 = frc0.get("jurisdiction") if isinstance(frc0, dict) else None
    jur_kind0 = jur0.get("kind") if isinstance(jur0, dict) else None
    cross_border0 = bool(jur0.get("cross_border")) if isinstance(jur0, dict) else False
    wants_dispute0 = bool(isinstance(frc0, dict) and isinstance(frc0.get("user_focus_issues"), list) and any(isinstance(x, dict) and x.get("code") == "dispute" for x in frc0.get("user_focus_issues")))
    # prof(infer_contract_profile)가 이미 canonical_type_code를 우선 신뢰해
    # 계산된 단일 source of truth이므로, raw contract_type 부분 문자열
    # 매칭을 별도로 OR하지 않는다(2026-09-01 — stale 라벨이 이 값을
    # 덮어써 무관한 조항에 대리점 전용 채점 가중치가 붙는 사고 방지).
    is_dealer_contract0 = prof.profile == "dealer_consignment"

    scored_for_ai = sorted(
        clause_results,
        key=lambda cr: (
            -_score_for_ai_deep_review(
                cr=cr,
                key_terms=key_terms,
                is_dealer_contract=is_dealer_contract0,
                jur_kind=(str(jur_kind0) if isinstance(jur_kind0, str) else None),
                cross_border=cross_border0,
                wants_dispute=wants_dispute0,
            ),
            str(cr.get("clause_id") or ""),
        ),
    )
    shortlist_target = min(len(scored_for_ai), max(12, int(desired)))
    deep_review_shortlist = scored_for_ai[: max(0, shortlist_target)]
    deep_review_shortlist_ids = [str(cr.get("clause_id") or "") for cr in deep_review_shortlist if str(cr.get("clause_id") or "")]
    # -----------------------------------------------------------------------
    # [반복 코멘트 생성 방지] 1차 dedup: AI shortlist 구성 전에 미리 적용
    # → AI가 dedup_suppressed 항목에 새 rewrite를 생성하지 않도록 사전 차단
    # -----------------------------------------------------------------------
    _apply_article_dedup_and_consolidation(clause_results)

    selected = deep_review_shortlist[: max(0, desired)]
    # dedup_suppressed 항목은 AI 처리 대상에서 제외
    selected = [cr for cr in selected if not bool(cr.get("dedup_suppressed"))]
    # extraction_error(원문 integrity 낮음) 항목은 AI 검토·rewrite 대상에서 제외
    # — segmentation을 신뢰할 수 없는 조항에 대해 AI가 새 rewrite를 만들어내면
    # (integrity guard가 이미 suggested_rewrite=None으로 비워둔 것을) 다시
    # 채워 넣어버릴 수 있으므로, 애초에 AI에게 보내지 않는다.
    selected = [cr for cr in selected if not bool(cr.get("extraction_error"))]

    # ── [Hybrid AI Review] 룰 DB/키워드가 전혀 건드리지 않은 조항도 AI에게 보여준다.
    # 지금까지는 clause_results(이미 룰 매칭되었거나 review_focus에 걸린 조항)만
    # AI에게 보내, AI는 "이미 알려진 문제의 표현을 다듬는" 역할만 할 수 있었다.
    # 룰 DB에 없는 리스크를 AI가 스스로 발견하게 하려면, 문서 전체 조항 중
    # 아직 결과에 없는 조항도 최소한 한 번은 AI 검토 대상에 포함해야 한다.
    _EXPLORATION_CAP = 40
    exploration_items: list[dict[str, Any]] = []
    if ai_enabled:
        _existing_ids = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
        _room = max(0, _EXPLORATION_CAP - len(selected))
        for c in clauses:
            if _room <= 0:
                break
            cid = str(c.clause_id or "")
            if not cid or cid in _existing_ids:
                continue
            txt = str(c.text or "").strip()
            if len(txt) < 15:
                continue
            exploration_items.append({
                "clause_id": cid,
                "article_number": c.article_number,
                "display_path": c.display_path,
                "clause_title": str(c.title or ""),
                "clause_topic": None,
                "risk_tier": "LOW",
                "must_fix": False,
                "user_focus_hit": False,
                "original_text": txt,
                "context_text": c.context_text,
                "detected_issue_list": [],
                "related_rules": [],
                "related_laws": None,
                "suggested_rewrite": None,
                "is_exploration_only": True,
            })
            _existing_ids.add(cid)
            _room -= 1
    ai_review_items = list(selected) + exploration_items

    selected_ids = [str(cr.get("clause_id") or "") for cr in ai_review_items if str(cr.get("clause_id") or "")]
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
                # 계약 유형별 법령 DB 엄격 분리: advisory는 IP/저작권 중심 검색 유도
                _law_ct = _law_contract_type_for_search(_contract_class, str(contract_type))
                cr["related_laws"] = law_service.search_for_review(
                    entity=str(entity),
                    contract_type=_law_ct,
                    text=ctext,
                    matched_rules=rr,
                    scope="clause",
                    max_per_type=max_clause_law_items,
                    contract_type_code=str(_canonical_profile.contract_type or ""),
                    context={
                        "party_role": party.to_dict(),
                        "review_posture": review_posture,
                        "risk_tier": cr.get("risk_tier"),
                        "must_fix": bool(cr.get("must_fix")),
                        "contract_class": _contract_class,
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
        if bool(cr.get("keep_as_is")):
            continue
        parts: list[str] = []
        if bool(cr.get("user_focus_hit")):
            titles = cr.get("user_focus_match_titles") if isinstance(cr.get("user_focus_match_titles"), list) else []
            titles = [str(x) for x in titles if isinstance(x, str) and x.strip()]
            if titles:
                # A bare category label ("사용자 중점 이슈: 구상권/소송비용 전가")
                # is not a reason — it doesn't say WHY this specific clause is
                # a problem, and a lawyer reading the output cannot verify it
                # against the quoted 원문. Anchor it to the actual matched
                # keyword phrase found in this clause's own text so the label
                # and the quoted 원문 refer to the same, verifiable issue.
                _ot_for_match = str(cr.get("original_text") or "")
                _matched_codes = cr.get("user_focus_matches") if isinstance(cr.get("user_focus_matches"), list) else []
                _snippets: list[str] = []
                for _code in _matched_codes[:2]:
                    for _kw in get_objective_keywords(str(_code)):
                        if _kw and _kw in _ot_for_match:
                            _snippets.append(_kw)
                            break
                if _snippets:
                    parts.append(
                        "사용자 중점 이슈: " + ", ".join(titles[:2])
                        + " — 본 조항에 '" + "', '".join(_snippets) + "' 관련 문구 포함"
                    )
                else:
                    parts.append("사용자 중점 이슈: " + ", ".join(titles[:2]) + " (해당 조항 문언 재확인 필요)")
        if bool(cr.get("factual_hit")):
            titles = cr.get("factual_match_titles") if isinstance(cr.get("factual_match_titles"), list) else []
            titles = [str(x) for x in titles if isinstance(x, str) and x.strip()]
            if titles:
                parts.append("질문 답변 반영: " + ", ".join(titles[:2]))
        if issues:
            titles = [str(x.get("issue_title") or "").strip() for x in issues if isinstance(x, dict) and str(x.get("issue_title") or "").strip()]
            if titles:
                parts.append("검출 이슈: " + ", ".join(titles[:2]))
        if rules:
            rule_ids = [str(x.get("rule_id") or "").strip() for x in rules if isinstance(x, dict) and str(x.get("rule_id") or "").strip()]
            if rule_ids:
                parts.append("적용 규칙: " + ", ".join(rule_ids[:2]))
        if isinstance(law, dict) and isinstance(law.get("results"), dict):
            laws = []
            for k in ("laws", "precedents", "interpretations"):
                arr = law["results"].get(k)
                if isinstance(arr, list):
                    for it in arr[:2]:
                        if isinstance(it, dict) and isinstance(it.get("title"), str) and it.get("title").strip():
                            laws.append(it["title"].strip())
            if laws:
                parts.append("관련 법령/판례: " + ", ".join(laws[:2]))
        parts = [p for p in parts if p][:2]
        cr["rewrite_reason"] = " / ".join(parts) if parts else None

    # [Hybrid AI Review] 결과 상단에 표시할 검토 방식 배너 — API 키가 없어서
    # rule-based fallback으로 돌아간 경우를 "정상 AI 검토"처럼 보이게 하지 않는다.
    ai_state: dict[str, Any] = {
        "enabled": bool(ai_enabled),
        "used": False,
        "selected_clause_ids": selected_ids,
        "selected_count": len(selected_ids),
        "model": ai_model if ai_enabled else None,
        "ok": None,
        "error": None,
        "usage": None,
        "mode": "ai_legal_review" if ai_enabled else "rule_based_fallback",
        "banner": (
            f"AI 법률검토 활성화 (모델: {ai_model})"
            if ai_enabled
            else "AI 법률검토 비활성화 — Rule-based fallback (키워드/패턴 기반 룰 엔진 결과입니다. "
                 "OPENAI_API_KEY 또는 ANTHROPIC_API_KEY를 설정하면 AI 기반 조항별 법률검토가 활성화됩니다.)"
        ),
    }
    # [STEP 1 + STEP 4] 공급자 방어 원칙 — seller_favorable 시 AI 프롬프트에 추가
    _supplier_guardrail_addendum = ""
    if review_posture == "seller_favorable":
        _supplier_guardrail_addendum = (
            "\n\n## [STEP 1 — HARD LOCK] Supplier-Side Review Mode 활성화\n"
            "우리 회사 = 공급자. 아래 원칙을 모든 수정안에 절대적으로 적용한다:\n"
            "1. 우리 회사의 책임을 새로 늘리는 수정안 생성 금지\n"
            "2. 법령상 최소 준수 수준을 넘는 추가 확약 금지\n"
            "3. 상대방에게 유리하고 우리 회사에 불리한 신규 의무 자동 제안 금지\n"
            "4. 우리 회사의 면책·책임 제한·절차 통제 조항을 우선 검토할 것\n\n"
            "## [STEP 2 — BLACKLIST] 다음 문구는 절대 출력 금지\n"
            "- 안전 인증 완료를 보증한다\n"
            "- 공급자가 리콜 또는 회수 비용을 부담한다\n"
            "- 공급자는 PL보험에 가입하여야 한다\n"
            "- 공급자는 제3자 손해를 배상한다\n"
            "- 공급자는 결함 발견 시 즉시 시정 조치를 완료하여야 한다\n\n"
            "## [STEP 4 — 의무] 수정안 필수 7개 방어 요소\n"
            "모든 수정안에 아래 요소 중 해당되는 것을 반드시 포함한다:\n"
            "1. '공급자의 귀책사유가 있는 경우에 한하여'\n"
            "2. '관련 법령상 요구되는 범위 내에서'\n"
            "3. '직접손해에 한하여'\n"
            "4. '구매자의 오사용, 임의개조, 보관불량, 사용설명 위반, 제3자 제품과의 결합, 구매자 제공 사양 또는 지시에 기인한 경우 제외'\n"
            "5. '공급자에게 합리적인 시정 기회를 먼저 부여'\n"
            "6. '서면 통지 및 증빙 제출을 요건으로 함'\n"
            "7. '주문제작 또는 설치완료 제품은 반품 제한'\n\n"
            "## [STEP 4 — 좋은 예시]\n"
            "예시1: '구매자는 하자를 발견한 경우 발견일로부터 7일 이내에 구체적 내용을 기재하여 서면으로 통지하여야 하며, 이를 해태한 경우 해당 하자에 관한 클레임을 제기할 수 없다.'\n"
            "예시2: '공급자는 자신의 귀책사유로 인한 하자에 대하여 합리적인 기간 내 수리, 교환 또는 대금 환급 중 하나의 방법으로 우선 시정할 수 있다.'\n"
            "예시3: '공급자의 손해배상책임은 해당 클레임의 원인이 된 물품의 공급대금을 한도로 하며, 특별손해, 간접손해, 일실이익에 대해서는 책임지지 않는다.'\n\n"
            "## [FINAL VALIDATION] 수정안 출력 전 자가 검증\n"
            "다음 중 2개 이상 YES이면 수정안을 삭제하거나 방어 문구로 재작성할 것:\n"
            "1. 이 문구가 우리 회사의 책임을 새로 늘리는가?\n"
            "2. 이 문구가 법령상 필수 수준을 넘는가?\n"
            "3. 구매자에게 유리한 추가 권리를 부여하는가?\n"
            "4. 공급자 방어 문구 없이 의무만 추가하는가?\n"
            "5. 실제 협상에서 우리 법무팀이 거부할 가능성이 높은가?\n"
        )

    # ── [Hybrid AI Review] 계약유형별 "이 계약에서는 제안 금지" 카테고리 ─────
    # AI가 스스로 판단하기 전에, 룰 엔진이 이미 확정한 계약유형/스코프 정보를
    # 알려줘서 애초에 무관한 제안을 만들지 않게 한다. 그래도 만들어지면
    # hallucination_guard/self_check가 최종적으로 걸러낸다(2중 방어).
    _OUT_OF_SCOPE_BY_CLASS: dict[str, str] = {
        "testing_service": "물품공급/검수/반품/A/S/위험이전/설치환경/주문제작취소/이행유보권, CI/SI·브랜드 위약벌, 콘텐츠·IP 결과물 귀속/보증",
        "advisory": "물품공급/검수/반품/A/S/위험이전/설치환경, CI/SI·브랜드 위약벌, 대리점/유통 관련 조항",
        "content_production": "물품공급/검수/반품/A/S/위험이전/설치환경, 대리점/유통 관련 조항",
        "rental": "IP/저작권 귀속, 소프트웨어 개발 관련 조항, 대리점/유통 관련 조항",
        "construction": "IP/저작권 귀속, 소프트웨어 개발 관련 조항",
        "project_installation": "IP/저작권 귀속, 대리점/유통 관련 조항",
    }
    _out_of_scope_notice = _OUT_OF_SCOPE_BY_CLASS.get(_contract_class, "")
    _canonical_type_code = _canonical_profile.contract_type
    _our_role_bucket = _canonical_profile.our_role_bucket

    _HYBRID_SCHEMA_AND_SEVERITY_INSTRUCTIONS = (
        "\n\n## [핵심] 이 조항에 룰 엔진이 부여한 risk_tier/must_fix는 참고용 초기값일 뿐이다 — "
        "그대로 베끼지 말고, 아래 5단계에 따라 직접 재평가하라:\n"
        "1) 원문 의미: 이 조항이 실제로 규정하는 권리·의무가 무엇인가\n"
        "2) 당사자 권리·의무: 이 조항으로 각 당사자가 구체적으로 무엇을 하거나 하지 않아야 하는가\n"
        "3) 우리 회사 리스크: 이로 인해 우리 회사(제공된 party_role/our_role_bucket 기준)가 실제로 손해를 보거나 "
        "의무를 부담하게 되는 지점이 있는가\n"
        "4) 법적/실무적 이유: 왜 그것이 문제인가(법적 근거 또는 실무 리스크)\n"
        "5) 최소 수정안: 계약 구조·거래 취지를 최대한 유지하면서 그 리스크만 제거하는 최소한의 수정 문구\n\n"
        "이 5단계를 거친 뒤, 실제로 우리 회사에 불리한 리스크가 있다고 판단되면 룰 엔진의 초기값과 무관하게 "
        "risk_tier를 HIGH/MEDIUM/LOW 중 하나로 직접 산정하라(초기값이 LOW/무시상태였던 조항이라도, 실제로 "
        "중대한 리스크를 발견하면 HIGH로 상향하라 — 이것이 이 검토의 핵심 목적이다). "
        "반대로 초기값이 HIGH/MEDIUM인 조항을 낮추려면 rewrite_reason에 왜 실제로는 문제가 아닌지 반드시 명시하라. "
        f"is_exploration_only=true인 항목은 룰 엔진이 전혀 검토하지 않은 조항이다 — 실제 리스크가 없다고 "
        "판단되면 결과에서 제외해도 되고(items 배열에서 생략), 리스크가 있으면 반드시 포함하라.\n\n"
        + (f"## 이 계약유형({_contract_class})에서는 다음 카테고리의 제안을 절대 하지 말 것: {_out_of_scope_notice}\n\n" if _out_of_scope_notice else "")
        + "출력은 반드시 첫 글자 '[' 로 시작하는 JSON 배열만 출력하고, 코드펜스/설명 문장을 절대 포함하지 마라. "
        "각 원소 형식은 clause_id/original_text_quote/party_obligations/our_company_risk/rewrite_reason/"
        "suggested_rewrite/changed_segments/risk_tier/must_fix/original_effect_tags/rewrite_effect_tags 로 통일하라. "
        f"original_effect_tags, rewrite_effect_tags: 이 조항의 원문과 네가 제안하는 수정문안이 실제로 어떤 "
        f"법률효과를 발생시키는지, 아래 taxonomy 중 해당하는 값들의 배열로 분류하라(단어가 아니라 효과로 "
        f"판단할 것 — 예: '해지'라는 단어가 있어도 실제로는 반환·폐기 조항의 트리거 조건일 뿐이면 "
        f"termination_for_breach가 아니라 return_destruction으로 분류). taxonomy: "
        f"{', '.join(LEGAL_EFFECT_TAGS)}. 수정문안이 원문과 근본적으로 다른 법률효과로 바뀌면(예: 원문은 "
        f"양도조항의 연대책임인데 수정문안이 지급보증 문구가 되는 경우) rewrite_effect_tags가 원문과 겹치는 "
        f"태그를 최소 하나는 포함하도록 재작성하라 — 겹치지 않으면 자동으로 REVIEW_FAILED_SEMANTIC_MISMATCH로 "
        f"처리되어 그 finding이 버려진다. "
        "original_text_quote: 판단의 근거가 된 원문 조항에서 그대로(변형 없이) 발췌한 10자 이상의 문구 — "
        "원문에 실제로 없는 문구를 지어내지 마라. "
        "party_obligations: 이 조항이 규정하는 각 당사자의 권리·의무를 80자 이내 1문장으로. "
        "our_company_risk: 우리 회사가 부담하게 되는 구체적 리스크를 80자 이내 1문장으로(리스크가 없으면 빈 문자열). "
        "위 모든 필드를 합쳐도 조항당 출력이 지나치게 길어지지 않도록 간결하게 작성하라 — "
        "한 응답에 여러 조항을 함께 출력해야 하므로 장황한 설명은 금지한다."
        "changed_segments는 변경된 핵심 구간 최대 3개를 {before, after} 형태로 요약하라."
    )

    if ai_enabled and ai_review_items:
        if _is_advisory_class:
            # Advisory/자문/용역 계약 전용 AI 프롬프트 — Logic Isolation (Phase 2)
            # [FOUNDATIONAL SYSTEM CHANGE] Legal Scenario Reasoning Engine 적용
            system = (
                "너는 한국 대형 로펌의 시니어 파트너 변호사다. 현재 검토 대상은 자문·용역·개발 계약이다.\n\n"
                "## [필수] 5단계 Reasoning 순서 — 반드시 이 순서로 사고할 것\n"
                "STEP 1: 이 계약으로 실제 어떤 분쟁·손실이 발생하는가? (IP 귀속 분쟁, 결과물 활용 제한, 배상 한도 미비 등)\n"
                "STEP 2: 회사가 실제 어디서 돈을 잃는가? (IP 미귀속 → 재사용 불가, 배상 한도 초과, 비밀 유출 손해 등)\n"
                "STEP 3: 제3자 손해가 발생하는가? (수탁자 IP 침해 → 위탁자 연대 책임)\n"
                "STEP 4: 누가 책임을 부담하는가? (저작권법 제9조 수탁자 귀속 원칙 → 명시 규정 필수. "
                "indemnify/면책 조항이 수동태로만 되어 있고 의무 주체가 불명확하면 우리 회사가 부담한다고 "
                "단정하지 말고 그 불명확함 자체를 지적할 것)\n"
                "STEP 5: 실제 분쟁 가능성이 높은 경우에만 수정안 생성. boilerplate·일반론 금지.\n\n"
                "## 최우선 점검 3개 (위탁자 갑인 경우)\n"
                "① [IP 귀속 CRITICAL] 산출물의 저작권·지식재산권이 수탁자에게 귀속되거나 이용권만 부여되면 '위탁자(퍼시스) 전적 귀속'으로 수정하라. 근거: 저작권법 제9조.\n"
                "② [제3자 침해 보증 CRITICAL] IP 조항에 '수탁자는 제3자 권리를 침해하지 않음을 보증하며 침해 시 면책·배상' 문구 없으면 삽입하라.\n"
                "③ [배상 한도 예외 HIGH] 손해배상이 용역대금 총액으로 제한된 경우 IP침해·비밀유지위반·고의중과실은 한도 예외 단서를 삽입하라.\n\n"
                "## 수정안 필수 6개 요소 (모두 포함해야 함)\n"
                "주체 / 조건(발동 요건) / 절차 / 기한 / 비용부담 / 책임범위\n\n"
                "## 금지\n"
                "- 'XX를 명확히 할 필요가 있습니다' 같은 generic guidance\n"
                "- 추상적 법률 설명만 있고 실제 문구가 없는 출력\n"
                "- 렌탈·물류시설법·부동산세법·방문판매법·B2C 약관 관련 문구\n"
                "- 제1·2·3조(목적·원칙·정의) 등 선언적 조항에 실무 의무 삽입\n"
                "- 입력에 없는 사실·상황·의무를 새로 만드는 것\n\n"
                "review_focus에 사용자가 명시한 조항/쟁점이 있으면 해당 조항을 반드시 검토 대상에 포함하고, "
                "rewrite_reason에서 그 요청에 구체적으로 대응하는 근거를 제시하라. "
                "answers에 사용자가 제공한 사실관계(과거 사례, 계획, 빈도 등)가 있으면 이를 반영하여 리스크 평가와 수정안을 조정하라.\n"
                "rewrite_reason: 법률 근거 + 실제 손실 시나리오 중심으로 220자 이내.\n"
                "suggested_rewrite: 협상 테이블에 바로 올릴 수 있는 계약 문구, 900자 이내, 법무 문체."
            ) + _HYBRID_SCHEMA_AND_SEVERITY_INSTRUCTIONS + _supplier_guardrail_addendum
        elif cross_border0 and str(jur_kind0 or "") != "domestic_korea":
            # Cross-border / English NDA 전용 프롬프트 — 국제 법무 특화
            system = EN_NDA_CLAUSE_REVIEW_SYSTEM + _supplier_guardrail_addendum
        else:
            # [FOUNDATIONAL SYSTEM CHANGE] Legal Scenario Reasoning Engine 적용
            system = (
                "너는 한국 대형 로펌의 시니어 파트너 변호사다.\n\n"
                "## [필수] 조항 검토 전 계약 전체 이해\n"
                "입력의 contract_overview(계약 목적, 계약기간, 대금구조, 전체 조항 목차)와 "
                "final_review_context를 먼저 읽고 이 계약이 무엇에 관한 것인지, 당사자 지위와 "
                "거래구조가 무엇인지 파악한 뒤에 개별 조항(items)을 검토하라. 개별 조항만 보고 "
                "판단하지 말고, 이 계약 전체 맥락에서 실제로 문제되는지 판단하라.\n"
                "법령 조문 번호(제N조)는 네가 확실히 알고 있는 경우에만 표기하고, 확신이 없으면 "
                "법률명만 쓰거나 조문 번호 없이 서술하라. 조문 번호를 추정해서 만들어내지 말 것.\n\n"
                "## [필수] 5단계 Reasoning 순서 — 반드시 이 순서로 사고할 것\n"
                "STEP 1: 이 계약으로 실제 어떤 사고·분쟁이 발생하는가? (제품 사고, 설치 재해, 리콜, 하자 분쟁, 해지 분쟁 등 구체적 시나리오)\n"
                "STEP 2: 회사가 실제 어디서 돈을 잃는가? (대규모 손해배상, 생산중단, 리콜 비용, 계약해지 패널티 등)\n"
                "STEP 3: 제3자 손해가 발생하는가? (고객·사용자 피해, 하도급 사고 연대책임 등)\n"
                "STEP 4: 누가 책임을 부담하는가? (책임 공백·면책 과도·보험 미비 확인. indemnify/면책 조항이 "
                "수동태로만 되어 있고 의무 주체가 불명확하면 우리 회사가 부담한다고 단정하지 말고 그 "
                "불명확함 자체를 지적할 것)\n"
                "STEP 5: 실제 분쟁 가능성이 높은 경우에만 수정안 생성. generic boilerplate·일반론 금지.\n\n"
                "## 수정안 필수 6개 요소 (모두 포함해야 함)\n"
                "주체 / 조건(발동 요건) / 절차 / 기한 / 비용부담 / 책임범위\n\n"
                "## 예시\n"
                "나쁜 출력: '리콜 절차를 명확히 할 필요가 있습니다.'\n"
                "좋은 출력: '공급자는 결함 발견 시 즉시 수요자에게 통보하고, 수요자의 요청이 있는 경우 지체 없이 리콜·교환·수리 조치를 수행한다. 이 경우 회수·교체·재설치·고객 통지 비용은 공급자가 부담한다.'\n\n"
                "## 금지\n"
                "- 'XX가 필요합니다', 'XX를 검토하세요' 같은 generic guidance\n"
                "- 추상적 법률 설명만 있고 실제 계약 문구가 없는 출력\n"
                "- 조항 주제(clause_topic)와 무관한 문구 (분쟁조항에 비용전가/안전 문구 금지)\n"
                "- jurisdiction.kind가 domestic_korea이면 해외 집행/다국가 거래 reasoning 금지\n"
                "- 입력에 없는 사실·상황·의무를 새로 만드는 것\n"
                "- party_role과 review_posture에 반하는 방향으로 수정\n\n"
                "user_focus_issues가 있으면 해당 이슈 관련 조항을 최우선으로 검토하고, rewrite_reason에 연결을 명확히 표시하라.\n"
                "review_focus에 사용자가 명시한 조항/쟁점이 있으면 해당 조항을 반드시 검토 대상에 포함하고, "
                "rewrite_reason에서 그 요청에 구체적으로 대응하는 근거를 제시하라. "
                "answers에 사용자가 제공한 사실관계(과거 사례, 계획, 빈도 등)가 있으면 이를 반영하여 리스크 평가와 수정안을 조정하라.\n"
                "rewrite_reason: 실제 손실 시나리오 + 법률 근거 + 협상 논리, 220자 이내.\n"
                "suggested_rewrite: 협상 테이블에 바로 올릴 수 있는 계약 문구, 900자 이내, 법무 문체."
            ) + _HYBRID_SCHEMA_AND_SEVERITY_INSTRUCTIONS + _supplier_guardrail_addendum

        def chunked(xs: list[dict[str, Any]], n: int) -> list[list[dict[str, Any]]]:
            if n <= 0:
                return []
            out: list[list[dict[str, Any]]] = []
            for i in range(0, len(xs), n):
                out.append(xs[i : i + n])
            return out

        # 5-step reasoning + original_text_quote/party_obligations/our_company_risk를
        # 추가하면서 항목당 출력 분량이 늘었다 — 청크당 항목 수를 줄여 max_tokens
        # 초과로 인한 JSON 잘림(파싱 실패)을 방지한다.
        chunk_size = 5
        chunks = chunked(ai_review_items, chunk_size)
        errors: list[str] = []
        usages: list[dict[str, Any]] = []
        ok_all = True
        any_used = False
        exploration_by_id: dict[str, dict[str, Any]] = {
            str(it.get("clause_id")): it for it in exploration_items if it.get("clause_id")
        }
        ai_discovered_count = 0
        ai_grounding_rejected: list[str] = []
        for ch in chunks:
            user = json.dumps(
                {
                    "entity": entity,
                    "contract_type": contract_type,
                    "contract_type_code": _canonical_type_code,
                    "our_role_bucket": _our_role_bucket,
                    "out_of_scope_categories": _out_of_scope_notice or None,
                    "contract_overview": (contract_context.get("contract_overview") if isinstance(contract_context, dict) else None),
                    "final_review_context": (contract_context.get("final_review_context") if isinstance(contract_context, dict) else None),
                    "review_posture": review_posture,
                    "party_role": party.to_dict(),
                    "answers": answers if isinstance(answers, dict) else None,
                    "review_focus": review_focus if isinstance(review_focus, str) and review_focus.strip() else None,
                    "items": [
                        {
                            "clause_id": cr.get("clause_id"),
                            "risk_tier": cr.get("risk_tier"),
                            "must_fix": bool(cr.get("must_fix")),
                            "clause_title": cr.get("clause_title"),
                            "display_path": cr.get("display_path"),
                            "clause_topic": cr.get("clause_topic"),
                            "user_focus_hit": bool(cr.get("user_focus_hit")),
                            "original_text": str(cr.get("original_text") or "")[:1500],
                            "context_text": str(cr.get("context_text") or "")[:900] if isinstance(cr.get("context_text"), str) else None,
                            "detected_issue_list": cr.get("detected_issue_list"),
                            "related_rules": cr.get("related_rules"),
                            "related_laws": cr.get("related_laws"),
                            "fallback_rewrite": cr.get("suggested_rewrite"),
                            "is_exploration_only": bool(cr.get("is_exploration_only")),
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

                _FLOOR_PROTECTED_KEYS = ("is_common_legal_risk", "is_checklist_item", "is_mandatory")

                def _apply_ai_update(cr: dict[str, Any], upd: dict[str, Any], *, is_new: bool) -> None:
                    # Belt-and-suspenders: extraction_error clauses are already
                    # excluded from `selected` before the AI call, but refuse
                    # any AI-provided rewrite/reasoning here too in case one
                    # ever reaches this path (e.g. a future caller of
                    # _apply_ai_update that doesn't go through `selected`).
                    if bool(cr.get("extraction_error")):
                        return
                    quote = upd.get("original_text_quote")
                    original_text = str(cr.get("original_text") or "")
                    grounded = _ai_quote_is_grounded(quote, original_text)
                    if not grounded:
                        # An AI response that can't be grounded in an actual
                        # excerpt of THIS clause's own text means the AI has
                        # confused this clause with another (or invented
                        # content outright) — confirmed against a real FITI
                        # 시험분석약정서 run where 제14조(관할조항)'s finding
                        # carried "인력 채용·배치·평가·징계" reasoning that has
                        # nothing to do with jurisdiction. This used to gate
                        # only the severity update below, while rewrite_
                        # reason/suggested_rewrite/worst_case_scenario were
                        # still applied unconditionally above — exactly the
                        # fields that reach the Word output. Reject the ENTIRE
                        # update here, before any field is touched, so a
                        # hallucinated response can never overwrite this
                        # clause's (safe, rule-engine-provided) existing
                        # content.
                        ai_grounding_rejected.append(str(cr.get("clause_id") or ""))
                        return
                    rr = upd.get("rewrite_reason")
                    sr = upd.get("suggested_rewrite")
                    cs = upd.get("changed_segments")
                    wcs = upd.get("worst_case_scenario")
                    neg = upd.get("negotiation_strategy")
                    ai_sev = _sanitize_ai_severity(upd.get("risk_tier"))

                    # A quote can be genuinely grounded in this clause's own
                    # text while the AI's reasoning is still about a
                    # completely unrelated subject — grounding only proves
                    # the QUOTE is real, not that the REASONING is on-topic.
                    # Confirmed twice in the same real FITI run: 제14조②
                    # (관할/분쟁 조항, "본약정과관련된 분쟁은 서울중앙지방법원을
                    # 전속관할로 한다") repeatedly got AI-generated content
                    # about "인력 채용·배치·평가·징계" (personnel/HR
                    # management) — a subject this clause's own text never
                    # mentions at all. Reject any AI content that introduces
                    # a foreign-topic keyword cluster the clause's own
                    # original_text has no trace of.
                    _ai_text_combined = " ".join(x for x in (rr, sr) if isinstance(x, str))
                    for _markers, _allow_if_present in _FOREIGN_TOPIC_MARKER_CLUSTERS:
                        if any(m in _ai_text_combined for m in _markers) and not any(a in original_text for a in _allow_if_present):
                            ai_grounding_rejected.append(str(cr.get("clause_id") or ""))
                            return

                    # [Layer 3 — semantic consistency gate] AI가 스스로 분류한
                    # 원문/수정문안의 법률효과 태그가 전혀 겹치지 않으면(예: 원문=
                    # return_destruction인데 rewrite=termination_for_breach),
                    # 조용히 finding을 버리지 않고 REVIEW_FAILED_SEMANTIC_MISMATCH로
                    # 기록한다(변호사형 전체계약 판단 지시, 2026-09-01 — 항목 3).
                    _oet = upd.get("original_effect_tags")
                    _ret = upd.get("rewrite_effect_tags")
                    _oet = [str(x) for x in _oet if isinstance(x, str) and x in LEGAL_EFFECT_TAGS] if isinstance(_oet, list) else []
                    _ret = [str(x) for x in _ret if isinstance(x, str) and x in LEGAL_EFFECT_TAGS] if isinstance(_ret, list) else []
                    if _oet:
                        cr["original_effect_tags"] = _oet
                    if _ret:
                        cr["rewrite_effect_tags"] = _ret
                    if _oet and _ret and not effects_overlap(_oet, _ret) and isinstance(sr, str) and sr.strip():
                        cr["semantic_mismatch"] = {
                            "stage": "ai_rewrite_effect_consistency",
                            "status": "REVIEW_FAILED_SEMANTIC_MISMATCH",
                            "clause_id": str(cr.get("clause_id") or ""),
                            "original_effect_tags": _oet,
                            "rewrite_effect_tags": _ret,
                        }
                        logger.warning(
                            "REVIEW_FAILED_SEMANTIC_MISMATCH clause_id=%s original_effect_tags=%s rewrite_effect_tags=%s",
                            cr.get("clause_id"), _oet, _ret,
                        )
                        # 원문이 규정하는 법률효과와 완전히 다른 효과로 수정문안을
                        # 재작성한 셈이므로, 그 rewrite는 신뢰할 수 없다 — 적용하지
                        # 않고(finding 자체는 남겨 로그·추적 가능하게 유지) reason만
                        # mismatch 사유로 남긴다.
                        rr = f"[REVIEW_FAILED_SEMANTIC_MISMATCH] AI가 제안한 수정문안의 법률효과({_ret})가 원문의 법률효과({_oet})와 일치하지 않아 자동 적용을 보류함."
                        sr = None

                    if isinstance(rr, str) and rr.strip():
                        cr["rewrite_reason"] = polish_korean_legal_style(rr.strip())
                    if isinstance(sr, str) and sr.strip():
                        cr["suggested_rewrite"] = polish_korean_legal_style(sr.strip())
                    if isinstance(wcs, str) and wcs.strip():
                        cr["worst_case_scenario"] = wcs.strip()
                    if isinstance(neg, str) and neg.strip():
                        cr["negotiation_strategy"] = neg.strip()
                    po = upd.get("party_obligations")
                    if isinstance(po, str) and po.strip():
                        cr["party_obligations"] = po.strip()
                    ocr = upd.get("our_company_risk")
                    if isinstance(ocr, str) and ocr.strip():
                        cr["our_company_risk"] = ocr.strip()
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

                    # [Hybrid AI Review] severity: AI's own 5-step assessment.
                    # Groundedness was already checked above (gating this
                    # entire update); only need a valid severity value here.
                    if ai_sev is None:
                        return
                    cur_sev = str(cr.get("risk_tier") or "LOW").upper()
                    # 룰 엔진(Layer1/Layer2/mandatory)이 부여한 등급은 "최소 보장" —
                    # AI가 근거 없이 그 아래로 낮추지 못한다. 위로 올리는 것은 허용.
                    if any(bool(cr.get(k)) for k in _FLOOR_PROTECTED_KEYS):
                        if _AI_SEVERITY_RANK.get(ai_sev, 0) < _AI_SEVERITY_RANK.get(cur_sev, 0):
                            return
                    cr["risk_tier"] = ai_sev
                    cr["severity"] = ai_sev
                    cr["must_fix"] = bool(upd.get("must_fix")) or ai_sev == "HIGH"
                    cr["approval_required"] = cr["must_fix"] or bool(cr.get("approval_required"))
                    cr["high_risk"] = ai_sev == "HIGH"
                    cr["review_tier"] = "MUST" if cr["must_fix"] else ("SUGGEST" if ai_sev == "MEDIUM" else "NOTE")
                    cr["ai_severity_grounded"] = True
                    if is_new:
                        cr["is_ai_discovered"] = True

                for cr in clause_results:
                    cid = cr.get("clause_id")
                    upd = by_id.get(cid) if isinstance(cid, str) else None
                    if not upd:
                        continue
                    # dedup_suppressed 항목은 AI 수정안을 적용하지 않는다
                    if bool(cr.get("dedup_suppressed")):
                        continue
                    _apply_ai_update(cr, upd, is_new=False)
                    by_id.pop(cid, None)

                # 룰 엔진이 전혀 만들지 못했던 조항(exploration-only)에 대해 AI가
                # 실제로 뭔가를 발견해 반환한 경우, 새 clause_result로 추가한다.
                # 이것이 "룰 DB에 없는 리스크라도 AI가 발견하면 포함" 요구사항의
                # 실제 동작 경로다.
                for cid, upd in by_id.items():
                    src = exploration_by_id.get(cid)
                    if not src:
                        continue
                    new_cr: dict[str, Any] = {
                        "clause_id": cid,
                        "article_number": src.get("article_number"),
                        "clause_title": src.get("clause_title"),
                        "display_path": src.get("display_path"),
                        "clause_topic": src.get("clause_topic"),
                        "original_text": src.get("original_text"),
                        "context_text": src.get("context_text"),
                        "detected_issue_list": [],
                        "related_rules": [],
                        "related_laws": None,
                        "risk_tier": "LOW",
                        "severity": "LOW",
                        "must_fix": False,
                        "approval_required": False,
                        "high_risk": False,
                        "review_tier": "NOTE",
                        "suggested_rewrite": None,
                        "rewrite_reason": None,
                        "user_focus_hit": False,
                        "factual_hit": False,
                        "keep_as_is": False,
                        "dedup_suppressed": False,
                        "has_rewrite_change": False,
                        "ai_deep_reviewed": True,
                        "ai_discovered_from_exploration": True,
                    }
                    _apply_ai_update(new_cr, upd, is_new=True)
                    if new_cr.get("ai_severity_grounded"):
                        clause_results.append(new_cr)
                        ai_discovered_count += 1
            except Exception as exc:
                any_used = True
                ok_all = False
                errors.append(sanitize_error_message(str(exc)))

        ai_state["used"] = bool(any_used)
        ai_state["ok"] = bool(ok_all) if any_used else None
        ai_state["usage"] = usages[:8] if usages else None
        ai_state["exploration_candidate_count"] = len(exploration_items)
        ai_state["ai_discovered_count"] = ai_discovered_count
        ai_state["ai_grounding_rejected_count"] = len(ai_grounding_rejected)
        if errors:
            ai_state["error"] = errors[0]
        if any_used and not ok_all:
            # AI가 설정되어 호출을 시도했지만 전부/일부 실패했다 — 룰 엔진 결과가
            # 그대로 남아있다는 것을 배너에 명확히 반영한다(성공한 것처럼 보이지 않게).
            ai_state["mode"] = "ai_call_failed_rule_based_fallback"
            ai_state["banner"] = (
                f"AI 법률검토 호출 실패 — Rule-based fallback으로 표시됨 (오류: {errors[0] if errors else '알 수 없음'})"
            )

    jur_kind = None
    try:
        frc0 = contract_context.get("final_review_context") if isinstance(contract_context, dict) else None
        if isinstance(frc0, dict) and isinstance(frc0.get("jurisdiction"), dict):
            jur_kind = frc0.get("jurisdiction", {}).get("kind")
    except Exception:
        jur_kind = None

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        sr = cr.get("suggested_rewrite")
        if not (isinstance(sr, str) and sr.strip()):
            continue
        ct = cr.get("clause_topic")
        clause_topic = str(ct) if isinstance(ct, str) and ct.strip() else classify_clause_topic(title=str(cr.get("clause_title") or ""), text=str(cr.get("original_text") or ""))
        rc = cr.get("rewrite_reason_codes") if isinstance(cr.get("rewrite_reason_codes"), list) else []
        rt = infer_rewrite_topics(rewrite_text=sr, reason_codes=[str(x) for x in rc if isinstance(x, str)])
        low_sr = sr.lower()
        onsite_present = ("설치" in (text or "")) or ("시공" in (text or "")) or ("현장" in (text or "")) or ("공사" in (text or ""))
        # canonical-aware profile만 신뢰(raw contract_type 라벨 매칭 제거,
        # 2026-09-01) — stale 라벨이 이 게이트를 오염시키면 정당한 app-dev
        # 관련 rewrite가 "topic mismatch"로 조용히 폐기(None)되는 사고로
        # 이어진다.
        is_dealer_contract = prof.profile == "dealer_consignment"
        strong_app_dev = any(k in (text or "") for k in ("소스코드", "SOW", "Statement of Work", "오픈소스", "SBOM", "API 연동", "소프트웨어 개발", "앱 개발"))
        if str(jur_kind or "") == "domestic_korea" and clause_topic == "dispute":
            rr0 = cr.get("rewrite_reason")
            if isinstance(rr0, str) and any(x in rr0 for x in ("해외", "집행", "cross-border", "cross border", "다국가")):
                cr["rewrite_reason"] = "국내 계약 분쟁조항은 준거법 중복보다 관할(전속관할/합의관할/민사소송법상 관할) 구조를 중심으로 점검."
        if clause_topic == "dispute" and any(k in sr for k in ("판촉", "광고비", "반품", "판매장려금", "비용전가", "비용 전가", "정산식", "증빙", "산업안전", "중대재해", "작업중지")):
            rt = set()
        if clause_topic == "personal_data" and any(k in sr for k in ("산업안전", "중대재해", "작업중지", "보호구")):
            rt = set()
        if clause_topic == "personal_data" and (not onsite_present) and any(k in sr for k in ("현장", "시공", "설치", "공사")):
            rt = set()
        if is_dealer_contract and (not strong_app_dev) and any(k.lower() in low_sr for k in ("sow", "sbom", "open source", "opensource")):
            rt = set()
        if is_dealer_contract and (not strong_app_dev) and any(k in sr for k in ("오픈소스", "소스코드")):
            rt = set()
        if not is_topic_compatible(clause_topic=clause_topic, rewrite_topics=rt):
            cr["guardrail_block"] = {"clause_topic": clause_topic, "rewrite_topics": sorted(list(rt))[:8]}
            cr["suggested_rewrite"] = None
            cr["changed_segments"] = []
            if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                cr["rewrite_reason"] = "조항 주제와 무관한 수정문안은 제외(guardrail)."
            # [Layer 3 — semantic consistency gate] 어떤 단계(clause_topic
            # 기반 guardrail)에서 mismatch가 발생했는지 로그에 남긴다(변호사형
            # 전체계약 판단 지시, 2026-09-01 — 항목 3). 조용히 버리지 않는다.
            cr["semantic_mismatch"] = {
                "stage": "clause_topic_rewrite_consistency",
                "status": "REVIEW_FAILED_SEMANTIC_MISMATCH",
                "clause_id": str(cr.get("clause_id") or ""),
                "original_clause_topic": clause_topic,
                "rewrite_topics": sorted(list(rt))[:8],
            }
            logger.warning(
                "REVIEW_FAILED_SEMANTIC_MISMATCH clause_id=%s clause_topic=%s rewrite_topics=%s",
                cr.get("clause_id"), clause_topic, sorted(list(rt))[:8],
            )

    # ── [STEP 4] Industry-Specific Legal Reasoning (가구·설비·제조물 12개 항목) ──
    _apply_industry_specific_review(
        clause_results, str(text or ""), _contract_class, _contract_nature,
        contract_type_code=str(_canonical_profile.contract_type or ""),
        legal_map=_legal_map.to_dict(),
    )

    # ── [Contextual Awareness] Contract Nature Lock ────────────────────────
    _apply_contract_nature_lock(clause_results, _contract_nature)

    # ── [Severity Reclassifier] 위탁판매 대리점 계약 severity 재분류 ──────────
    # 대리점/위탁판매 구조에서 구조 불일치(세금계산서 주체, 수금 책임, 모든 책임 등)를
    # 자동으로 HIGH/MEDIUM으로 상향 조정한다.
    # raw contract_type 라벨 부분 문자열 매칭 제거(2026-09-01) — prof.profile
    # 이 이미 canonical_type_code를 우선 신뢰해 계산되고, _struct는 실제
    # 문서 구조 탐지 결과이므로 이 둘만으로 충분하다.
    _is_consignment_dealer = (
        prof.profile == "dealer_consignment"
        or _struct.contract_structure == "direct_customer_contract_with_dealer_service"
    )
    if _is_consignment_dealer:
        from runtime.review.severity_reclassifier import reclassify_for_consignment_dealer
        for _cr in clause_results:
            if not isinstance(_cr, dict):
                continue
            if bool(_cr.get("dedup_suppressed")) or bool(_cr.get("keep_as_is")) or bool(_cr.get("is_checklist_item")):
                continue
            _cur_sev = str(_cr.get("risk_tier") or "LOW").upper()
            _new_sev, _reasons = reclassify_for_consignment_dealer(
                severity=_cur_sev,
                clause_text=str(_cr.get("original_text") or ""),
                clause_title=str(_cr.get("clause_title") or ""),
            )
            if _new_sev != _cur_sev:
                _cr["risk_tier"] = _new_sev
                _cr["auto_severity_upgrade"] = _reasons
                if _new_sev == "HIGH":
                    _cr["high_risk"] = True
                    _cr["must_fix"] = True
                    _cr["review_tier"] = "MUST"
                elif _new_sev == "MEDIUM" and _cur_sev == "LOW":
                    _cr["review_tier"] = "SUGGEST"

    # ── [Severity Reclassifier] 대칭적 상호 해지권 HIGH 강등 (모든 계약유형) ──
    # 양 당사자에게 동일하게 부여된 통지기간부 해지권(예: "양 당사자는 상대방에게
    # 30일 전 서면으로 통지하여 계약을 해지할 수 있다")은 일방적 리스크가 아니라
    # 균형잡힌 상호 조항이므로, AI가 HIGH로 판단했더라도 실제 협상상 중요도가
    # 더 큰 일방적 경제 리스크(직접거래제한+위약벌, 최소구매약정 등) 위에 노출되지
    # 않도록 MEDIUM으로 강등한다.
    from runtime.review.severity_reclassifier import demote_symmetric_mutual_termination
    for _cr in clause_results:
        if not isinstance(_cr, dict):
            continue
        if bool(_cr.get("dedup_suppressed")) or bool(_cr.get("keep_as_is")) or bool(_cr.get("is_checklist_item")):
            continue
        if bool(_cr.get("is_common_legal_risk")):
            continue
        _cur_sev2 = str(_cr.get("risk_tier") or "LOW").upper()
        _new_sev2, _demoted = demote_symmetric_mutual_termination(
            severity=_cur_sev2,
            clause_text=str(_cr.get("original_text") or ""),
        )
        if _demoted and _new_sev2 != _cur_sev2:
            _cr["risk_tier"] = _new_sev2
            _cr["severity"] = _new_sev2
            _cr["high_risk"] = False
            _cr["approval_required"] = False
            _cr["must_fix"] = False
            _cr["auto_severity_downgrade"] = ["symmetric_mutual_termination"]
            if bool(_cr.get("has_rewrite_change")):
                _cr["display_kind"] = "guidance"
            else:
                _cr["display_kind"] = "note"

    # ── [Severity Reclassifier] 이미 완결된 준거법/분쟁해결 조항 HIGH 강등
    # (모든 계약유형) — GLOBAL_CROSS_CLAUSE_VALIDATION은 "다른 조항에 이미
    # 있다"만 처리하므로, "이 조항 자체가 이미 충분하다"는 별도 축을 여기서
    # 처리한다 (2026-09-03 지시, KOTRA Article 9.2 과대평가 사례).
    from runtime.review.severity_reclassifier import demote_adequate_governing_law_dispute_clause
    for _cr in clause_results:
        if not isinstance(_cr, dict):
            continue
        if bool(_cr.get("dedup_suppressed")) or bool(_cr.get("keep_as_is")) or bool(_cr.get("is_checklist_item")):
            continue
        if bool(_cr.get("is_common_legal_risk")):
            continue
        _cur_sev3 = str(_cr.get("risk_tier") or "LOW").upper()
        _new_sev3, _demoted3 = demote_adequate_governing_law_dispute_clause(
            severity=_cur_sev3,
            clause_text=str(_cr.get("original_text") or ""),
            clause_title=str(_cr.get("clause_title") or ""),
            rewrite_reason=str(_cr.get("rewrite_reason") or ""),
            legal_business_reason=str(_cr.get("legal_business_reason") or ""),
        )
        if _demoted3 and _new_sev3 != _cur_sev3:
            _cr["risk_tier"] = _new_sev3
            _cr["severity"] = _new_sev3
            _cr["high_risk"] = False
            _cr["approval_required"] = False
            _cr["must_fix"] = False
            _cr["keep_as_is"] = True
            _cr["review_tier"] = "NOTE"
            _cr["adequacy_downgrade_reason"] = "governing_law_dispute_resolution_already_adequate"
            _cr["auto_severity_downgrade"] = ["adequate_governing_law_dispute_clause"]
            _cr["display_kind"] = "note"

    # ── [GLOBAL_CROSS_CLAUSE_VALIDATION] 이미 다른 조항에서 해결된 "부재"
    # finding 제거 (모든 계약유형) ──────────────────────────────────────────
    # 조항 단위(또는 AI의 단일 clause 호출) 검토는 문서 전체를 보지 못하므로,
    # "이 조항에는 준거법/분쟁해결/책임상한 조항이 없다"는 finding이 실제로는
    # 계약서의 다른 조항에 이미 있는 내용을 다시 지적하는 오탐일 수 있다.
    from runtime.review.global_cross_clause_validation import apply_global_cross_clause_validation
    apply_global_cross_clause_validation(clause_results, str(text or ""))

    _dedup_rewrite_suggestions(clause_results)
    for cr in clause_results:
        if isinstance(cr, dict):
            cr.pop("_dedup_norm", None)

    # 키워드→템플릿 이어붙이기 루프: Advisory/Service 계약 Hard-Block (Logic Isolation)
    # _contract_class / _is_advisory_class 는 함수 최상단(Classification First)에서 이미 확정됨.
    for cr in clause_results:
        if _is_advisory_class:
            continue
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("keep_as_is")) or bool(cr.get("dedup_suppressed")):
            continue
        tier0 = str(cr.get("risk_tier") or "").strip().upper()
        if tier0 not in ("HIGH", "MEDIUM"):
            continue
        sr0 = cr.get("suggested_rewrite")
        if isinstance(sr0, str) and sr0.strip():
            continue
        ot0 = str(cr.get("original_text") or "")
        if not ot0.strip():
            continue
        cid0 = str(cr.get("clause_id") or "")
        ch0 = chunk_by_id.get(cid0)
        a0s = str(ch0.article_number or "").strip() if isinstance(ch0, object) else ""
        a0i = int(a0s) if a0s.isdigit() else None
        title0 = str(cr.get("clause_title") or "")
        ct0 = str(cr.get("clause_topic") or "").strip()
        if _is_hard_block_clause(article_int=a0i, title=title0, clause_topic=ct0):
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"
            cr["high_risk"] = False
            cr["approval_required"] = False
            cr["rewrite_reason"] = "원문 유지(하드 블록: 메타/분쟁 조항)."
            continue
        if ct0 == "payment_settlement":
            add = (
                "\n\n[추가]\n"
                "① 정산은 항목별 산식과 기준에 따라 이루어지며, 공제/상계는 당사자 간 사전 서면합의(사유·금액·산정 기준 포함)가 있는 경우에 한한다.\n"
                "② 공제/상계는 상대방에 대한 확정 채권(또는 이에 준하는 객관적 근거)이 있는 경우로 제한한다.\n"
                "③ 갑은 정산서(항목별 내역) 및 합리적 범위의 증빙을 제공하고, 을은 일정 기간 내 이의제기할 수 있다.\n"
            )
            cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
            if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                cr["suggested_direction"] = [
                    "공제/상계 요건을 확정 채권 및 사전 서면합의로 제한",
                    "정산서·증빙 제공 및 이의제기 절차 명문화",
                ]
            if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                cr["rewrite_reason"] = "정산/상계/공제 구조가 불명확하면 불이익 제공·거래상 지위 남용 논점으로 연결될 수 있어, 산식·증빙·이의 절차를 구체화한다."
            if tier0 == "MEDIUM":
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
            continue
        if ct0 == "cost_burden":
            add = (
                "\n\n[추가]\n"
                "① 비용(판촉비/광고비/반품비/원상회복 비용 등) 부담은 항목·산정기준·상한(캡)·증빙을 사전에 서면으로 합의한 경우에만 적용한다.\n"
                "② 갑이 비용 정산 또는 공제/상계를 하려는 경우, 을에게 사전 통지하고 정산내역과 증빙을 제공하며, 을에게 합리적인 이의제기 기간을 부여한다.\n"
            )
            cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
            if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                cr["suggested_direction"] = [
                    "비용부담 항목/기준을 사전 서면합의로 고정",
                    "상한(캡)·증빙·이의제기 절차를 포함",
                ]
            if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                cr["rewrite_reason"] = "비용 부담이 사전 서면합의·항목별 기준 없이 운용되면 비용전가 분쟁이 발생할 수 있어, 기준·상한·증빙·이의 절차를 명확히 한다."
            if tier0 == "MEDIUM":
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
            continue
        if ct0 == "termination" and not _RX_ACTIVE_TERMINATION_RIGHT.search(ot0):
            # clause_topic 분류가 "해지"/"종료"라는 단어가 조항 어딘가에
            # 있기만 하면(예: 비밀정보 반환 조항의 "계약이 해제·해지·종료
            # 되거나"라는 트리거 조건 문구) termination으로 분류하기 때문에,
            # 실제로 해지권을 행사/제한하는 조항이 아닌데도 "해지 요건 객관화"
            # 템플릿이 삽입되는 것을 방지한다(변호사형 전체계약 판단 지시,
            # 2026-09-01 — NDA 반환·폐기 조항 오염 사례). 실제 해지권
            # 조항인지는 "해지/해제할 수 있다"/"해지권"/"즉시 해지" 같은
            # 능동적 행사 문언으로 판별한다.
            pass
        elif ct0 == "termination":
            add = (
                "\n\n[추가]\n"
                "① 해지(또는 계약 종료)는 객관적으로 중대한 위반이 있는 경우로 한정한다.\n"
                "② 원칙적으로 위반 사항을 특정하여 서면 최고하고, 30일 이상의 시정기간 및 2회 이상 시정 기회를 부여한다.\n"
                "③ 예외적 즉시해지 사유는 신뢰관계를 본질적으로 훼손하는 고의·중대한 위반 등으로 좁게 열거한다.\n"
            )
            cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
            if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                cr["suggested_direction"] = [
                    "즉시 해지 사유를 객관적·중대한 위반으로 한정",
                    "원칙적으로 30일 이상 서면 최고 및 시정기간 부여",
                    "예외적 즉시 해지 사유를 좁게 열거",
                ]
            if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                cr["rewrite_reason"] = "해지 권한이 과도하면 계약해지 남용/불이익 제공 논점으로 확대될 수 있어, 요건·절차를 객관화한다."
            if tier0 == "MEDIUM":
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
            continue
        if ct0 == "dealer_unfair":
            add = (
                "\n\n[추가]\n"
                "① 갑은 거래상 지위를 이용하여 을에게 부당하게 불이익을 제공하거나 거래조건을 일방적으로 강요하여서는 아니 된다.\n"
                "② 갑은 을의 영업/인사/운영에 관하여 직접적·구체적으로 지시하거나, 개별 인력의 교체·평가를 강제하지 않는다(경영간섭 방지).\n"
            )
            cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
            if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                cr["suggested_direction"] = [
                    "불이익 제공/지위 남용 금지 문구를 구체화",
                    "경영간섭 방지(직접 지시/강제 제한) 명시",
                ]
            if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                cr["rewrite_reason"] = "대리점법/공정거래 관점에서 불공정·경영간섭 리스크를 줄이기 위해, 금지 의무와 한계를 명시한다."
            if tier0 == "MEDIUM":
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
            continue
        if ct0 == "safety":
            add = (
                "\n\n[추가]\n"
                "① 본 조의 “사고”는 공사 수행과 관련하여 발생한 안전사고 및 기타 중대한 사건을 의미하며, 수급인은 사고(또는 사고 징후)를 인지한 즉시 도급인에게 서면으로 통지한다.\n"
                "② 통지에는 발생 일시·장소·경위, 피해 범위(인명/재산/공정), 긴급 조치 및 재발방지 계획을 포함한다.\n"
                "③ 수급인의 귀책사유로 인한 사고에 대해서는 수급인이 관련 법령상 의무를 이행하고, 도급인의 손해를 합리적인 범위에서 배상한다.\n"
                "④ 다만, 발주자(도급인)가 제공한 자료/도면/지시의 하자, 발주자가 제공·관리하는 현장의 기존 하자(시설·전기·구조·누수 등), 현장 인도 지연 등 수급인의 귀책이 아닌 사유로 인한 경우에는 수급인의 책임을 면제 또는 감경한다.\n"
                "⑤ 안전관리는 일방 책임 전가가 아니라 상호 협력 원칙에 따라 수행하며, 도급인은 현장 인도·출입통제·기존 시설 안전 확보 등 도급인이 통제 가능한 영역의 안전 조치를 이행한다.\n"
            )
            cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
            if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                cr["suggested_direction"] = [
                    "사고 정의 및 통지 범위를 명확화",
                    "통지 내용(경위/피해/조치/재발방지) 구체화",
                    "발주자 귀책(제공자료/현장 하자 등) 면책·감경 및 상호 협력 구조 반영",
                ]
            if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                cr["rewrite_reason"] = "사고 통지 의무는 필요하지만, 사고 범위·통지 내용·책임 기준이 불명확하면 과도한 책임으로 확대될 수 있어, 정의/절차/귀책 기준을 명확히 한다."
            if tier0 == "MEDIUM":
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
            continue
        if ct0 == "personal_data":
            add = (
                "\n\n[추가]\n"
                "① 개인정보 처리 목적/범위/기간을 특정하고, 목적 달성 또는 계약 종료 시 지체 없이 파기(또는 반환)한다.\n"
                "② 접근통제/암호화 등 합리적 보안조치를 이행하고, 침해사고 발생 시 지체 없이 통지 및 재발방지 조치를 협의한다.\n"
            )
            cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
            if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                cr["suggested_direction"] = [
                    "처리 목적/범위/기간을 특정",
                    "보안조치 및 침해사고 통지·조치 절차 포함",
                ]
            if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                cr["rewrite_reason"] = "개인정보 처리위탁 조항은 목적/범위/보안/사고대응이 불명확하면 법령 리스크가 커, 최소 요건을 명시한다."
            if tier0 == "MEDIUM":
                cr["must_fix"] = False
                cr["review_tier"] = "SUGGEST"
            continue
        if ct0 == "other":
            hay0 = (str(cr.get("clause_title") or "") + "\n" + ot0).lower()
            if any(k in hay0 for k in ("손해배상", "책임", "면책", "간접손해", "특별손해")):
                add = (
                    "\n\n[추가]\n"
                    "① 당사자의 손해배상 책임은 고의 또는 중대한 과실이 있는 경우를 제외하고, 직접·통상손해에 한한다.\n"
                    "② 간접손해/특별손해/영업이익 상실 등은 배상 책임에서 제외한다(법령상 제한이 없는 범위).\n"
                    "③ 손해배상 총액의 상한(캡) 및 산정 기준은 별도로 합의한다.\n"
                )
                cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
                if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                    cr["suggested_direction"] = ["책임 범위를 직접·통상손해로 한정", "간접·특별손해 제외", "총액 상한(캡) 설정"]
                if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                    cr["rewrite_reason"] = "책임 범위/상한이 불명확하면 손해배상 분쟁이 확대될 수 있어, 배상 범위·예외·상한을 명확히 한다."
                if tier0 == "MEDIUM":
                    cr["must_fix"] = False
                    cr["review_tier"] = "SUGGEST"
                continue
            if any(k in hay0 for k in ("지체상금", "지연", "납기", "기한")):
                add = (
                    "\n\n[추가]\n"
                    "① 지체상금/지연손해금은 실제 손해를 합리적으로 반영하는 수준에서 산정하며, 총액 상한(캡)을 둔다.\n"
                    "② 지연 사유가 상대방 귀책 또는 불가항력인 경우에는 지체상금 부과 대상에서 제외한다.\n"
                )
                cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
                if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                    cr["suggested_direction"] = ["지체상금 총액 상한(캡) 설정", "불가항력/상대방 귀책 예외 명시"]
                if not (isinstance(cr.get("rewrite_reason"), str) and str(cr.get("rewrite_reason") or "").strip()):
                    cr["rewrite_reason"] = "지체상금이 과도하거나 예외가 없으면 과잉 제재로 운용될 수 있어, 상한 및 예외를 명시한다."
                if tier0 == "MEDIUM":
                    cr["must_fix"] = False
                    cr["review_tier"] = "SUGGEST"
                continue
        if tier0 == "MEDIUM" and not (
            bool(cr.get("approval_required"))
            or bool(cr.get("high_risk"))
            or bool(cr.get("user_focus_hit"))
            or bool(cr.get("is_common_legal_risk"))
            or bool(cr.get("is_checklist_item"))
            or bool(cr.get("is_mandatory"))
        ):
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"
    # ── Advisory 계약: 키워드 템플릿 루프 종료 (격리 블록 끝) ─────────────────

    # -----------------------------------------------------------------------
    # [반복 코멘트 생성 방지] 2차 dedup: AI 처리 후 재적용
    # → AI가 새로 생성한 rewrite 중 중복/유사 항목을 최종 정리
    # → 이미 suppressed된 항목은 멱등성 보장으로 재처리하지 않음
    # -----------------------------------------------------------------------
    _apply_article_dedup_and_consolidation(clause_results)

    # ── [Advanced Review Logic + Expert Advisory + Zero-Hallucination] Filters ─
    # requirement.md 참조: [Advanced Review Logic] / [Expert Advisory Review Logic]
    #                      / [Zero-Hallucination Guardrail]
    _is_rental = _is_rental_contract(str(contract_type), str(text or ""))
    # Phase 3: Use comprehensive jurisdiction profile (detects GmbH, AG, foreign law, etc.)
    # instead of the limited _is_domestic_only() marker list.
    _is_domestic = (jur_kind0 == "domestic_korea") if jur_kind0 is not None else _is_domestic_only(str(text or ""), answers)
    # 1순위: Zero-Hallucination Guardrail (제1·2·3조 보호 + Advisory 금지키워드)
    _apply_zero_hallucination_guardrail(clause_results, str(contract_type), str(text or ""))

    # ── [Hallucination Guard] 계약유형별 금지문구 차단 ───────────────────────
    # 대리점 계약에서 개발계약용 IP 문구(수탁자, 결과물, 오픈소스 등)를 차단한다.
    try:
        from runtime.review.hallucination_guard import check_revision_text as _hg_check
        # Reuse the single canonical profile computed at the top of this
        # function (_canonical_profile) instead of re-classifying — a second,
        # independently-computed classification could disagree with the
        # first and silently apply a different hallucination-guard allowlist
        # than the one the rest of the pipeline used.
        _detailed_profile = _canonical_profile
        for _cr in clause_results:
            if not isinstance(_cr, dict):
                continue
            if bool(_cr.get("dedup_suppressed")) or bool(_cr.get("keep_as_is")):
                continue
            # common_legal_risk.py의 결정론적 rule은 원문에 실제로 등장하는
            # 문구를 정규식으로 직접 확인해 만든 고정밀 finding이므로 이
            # 계약유형별 금지문구 차단 대상이 아니다(self_check.py 백스톱과
            # 동일한 예외 — 2026-09-04 지시 회귀조건).
            if bool(_cr.get("is_common_legal_risk")):
                continue
            _sr = _cr.get("suggested_rewrite")
            if not (isinstance(_sr, str) and _sr.strip()):
                continue
            _guard = _hg_check(_sr, contract_type_code=_detailed_profile.contract_type)
            if not _guard.is_clean:
                _cr["suggested_rewrite"] = None
                _cr["changed_segments"] = []
                if not _cr.get("guardrail_block"):
                    _cr["guardrail_block"] = {
                        "filter": "hallucination_guard_contract_type",
                        "violations": _guard.violations[:5],
                    }
    except Exception:
        _detailed_profile = None
    # 2순위: Advisory IP & Copyright (자문/용역 → IP 귀속·보증 CRITICAL 점검)
    _apply_advisory_ip_review(clause_results, str(contract_type), str(text or ""), str(entity), contract_class=_contract_class)
    # 3순위: 기존 필터 체인
    _apply_rental_filter(clause_results, _is_rental)
    _apply_domestic_filter(clause_results, _is_domestic, llm_meta=_llm_meta)
    _apply_clause_integrity_filter(clause_results)
    _apply_original_text_integrity_guard(clause_results)
    _apply_sidiz_position_strategy(
        clause_results,
        str(entity),
        party.to_dict() if party is not None else None,
        str(text or ""),
        contract_class=_contract_class,
    )
    _apply_global_sentence_dedup(clause_results)

    # ── [NEW ENGINES] requirement.md > Review Priority Engine / Checklist / Output Policy ─
    # 1. Service Contract 필수 체크리스트 (advisory 계약 전용 — content_production에서는 실행 안 함)
    _apply_service_contract_checklist(clause_results, str(text or ""), _contract_class)

    # 1-0. Content Production 전용 체크리스트 (제품 광고 콘텐츠 제작 계약)
    if _contract_class == "content_production":
        try:
            from runtime.review.checklists.content_production import run_content_production_checklist
            _cp_issues = run_content_production_checklist(
                text=str(text or ""),
                contract_type_code="advertising_content_production",
                entity=str(entity or ""),
                counterparty="",
            )
            # Remove svc_* items that might have slipped through
            _SVC_IDS = {
                "svc_prepayment_guarantee", "svc_inspection_before_payment",
                "svc_deliverable_definition", "svc_refund_on_incomplete",
                "svc_delay_response", "svc_post_use_scope",
            }
            clause_results[:] = [
                cr for cr in clause_results
                if not (isinstance(cr, dict) and str(cr.get("clause_id") or "") in _SVC_IDS)
            ]
            # Inject content production checklist items at the front
            for _cp_issue in reversed(_cp_issues):
                clause_results.insert(0, _cp_issue.to_issue_dict())
        except Exception:
            pass
    # 1-1. Project Installation 필수 안전·교육 체크리스트
    _apply_project_installation_checklist(clause_results, str(text or ""), _contract_class)
    # 1-2. [STEP 3] Supplier-Protective Product Contract 체크리스트
    _apply_supplier_product_checklist(clause_results, str(text or ""), _contract_class, party.our_role, review_posture)
    # 1-2b. [Priority 3 억제] 위 체크리스트들이 만든 "누락 조항 신설" 권고는
    # 사용자가 직접 요청한 주제가 아니면 기본 출력에서 제외한다 — 새로운
    # 의무를 자진해서 추가하지 않기 위함(변호사형 전체계약 판단 지시).
    _apply_checklist_item_priority_demotion(clause_results, focus_topics, derived_topics)
    # 1-3. [Layer 1 — 공통 법률리스크] 계약유형과 무관하게 모든 계약에서 검토.
    # HARD BLOCK(계약유형 게이트)은 아래 Layer 2(유형특화) 룰에만 적용하고,
    # 이 Layer 1은 절대 게이트하지 않는다 — 그래야 무관 룰 차단이 실제 존재하는
    # 공통 리스크(일방 면책·무제한 구상·외부약관 편입 등) 탐지까지 죽이지 않는다.
    from runtime.review.common_legal_risk import _apply_common_legal_risk_rules

    def _infer_english_defined_term_for_entity(_text: str, _entity: str) -> str | None:
        """entity 실명(예: "Fursys") 바로 옆에 붙는 영문 정의어(예: '("Company")')를
        찾는다 — 계약마다 우리 쪽 정의어가 "Company"/"Client"/"Buyer" 등으로
        달라지므로, "Company"를 고정 별칭으로 쓰지 않고 실제 계약문에서
        우리 실명과 짝지어진 정의어만 별칭으로 채택한다(범용, 계약별 하드코딩 아님)."""
        _entity = (_entity or "").strip()
        if len(_entity) < 2:
            return None
        _idx = _text.lower().find(_entity.lower())
        if _idx < 0:
            return None
        _window = _text[_idx: _idx + 300]
        _m = re.search(r'["“]\s*(?:the\s+)?([A-Za-z][A-Za-z ]{1,30}?)\s*["”]\s*\)', _window)
        return _m.group(1).strip() if _m else None

    _our_party_aliases = [
        a for a in {
            str(entity or "").strip(),
            str(getattr(party, "our_label", "") or "").strip(),
            "당사",
            _infer_english_defined_term_for_entity(str(text or ""), str(entity or "")) or "",
        }
        if a
    ]
    _apply_common_legal_risk_rules(clause_results, str(text or ""), clauses, our_party_aliases=_our_party_aliases)
    # 1-4. [Layer 2 — 시험·검사·인증 용역 특화] testing_service 계약에서만 실행.
    from runtime.review.testing_service_rules import _apply_testing_service_checklist
    _apply_testing_service_checklist(clause_results, str(text or ""), _contract_class, clauses)
    # 2. 리뷰 우선순위 엔진 (LEVEL 1~3 분류, HIGH 최대 5개 — 체크리스트 제외)
    _apply_review_priority_engine(clause_results, max_high=5)
    # 3. No Inline Rewrite 정책 (advisory: 원문 보존 + [추가 권고] 형태)
    _apply_no_inline_rewrite_policy(clause_results, _is_advisory_class)
    # 4. [FINAL GOVERNING RULE] Relevance Validation Gate — 관련성 검증 후 제거
    _apply_relevance_validation_gate(clause_results, _contract_class, _contract_nature)
    # 5. [STEP 2 + FINAL VALIDATION] Do Not Harm Our Side Gate — 당사 불이익 방지 최종 검증
    _apply_do_not_harm_our_side_gate(clause_results, party.our_role, review_posture)
    # 6. [STEP 5B] Redline Safety Check — 문장 훼손 감지 및 guidance-only 전환
    _apply_redline_safety_check(clause_results, party.our_role, review_posture)
    # ─────────────────────────────────────────────────────────────────────────

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        sr = cr.get("suggested_rewrite")
        ot = cr.get("original_text")
        has_change = bool(isinstance(sr, str) and sr.strip() and _norm_text_for_change(sr) != _norm_text_for_change(str(ot or "")))
        cr["has_rewrite_change"] = bool(has_change)

        # ── [STEP 3-2] Redline 위치 정보 주입 ────────────────────────────────
        _ot_raw = str(ot or "").strip()
        _sr_raw = str(sr or "").strip()
        _an = str(cr.get("article_number") or "").strip()
        _pn = str(cr.get("paragraph_number") or "").strip()
        _ADD_MARKER = "\n\n[추가]\n"
        if has_change and _ADD_MARKER in _sr_raw:
            _base_part, _add_part = _sr_raw.split(_ADD_MARKER, 1)
            _base_sim = _sim_ratio(
                re.sub(r"[\s\r\n\t]+", " ", _base_part.strip().lower()),
                re.sub(r"[\s\r\n\t]+", " ", _ot_raw.lower()),
            )
            if _base_sim >= 0.90:
                cr["has_rewrite_change"] = False
                cr["replace_text"] = None
            else:
                cr["replace_text"] = _ot_raw
            cr["has_addition"] = True
            cr["addition_text"] = "[추가]\n" + _add_part.strip()
            cr["insert_after"] = ((_an + "." + _pn) if _pn else _an) or None
        elif has_change:
            cr["replace_text"] = _ot_raw
            cr["has_addition"] = False
            cr["addition_text"] = None
            cr["insert_after"] = None
        else:
            cr["replace_text"] = None
            cr["has_addition"] = False
            cr["addition_text"] = None
            cr["insert_after"] = None
        # ─────────────────────────────────────────────────────────────────────

        if bool(cr.get("keep_as_is")):
            change_type = "keep_as_is"
        elif bool(cr.get("dedup_suppressed")):
            change_type = "suppressed"
        elif has_change:
            change_type = "modified"
        else:
            change_type = "unchanged"
        segs = _diff_segments_for_change_record(str(ot or ""), str(sr or "")) if has_change else {
            "unchanged_segment": [],
            "inserted_segment": [],
            "deleted_segment": [],
            "moved_or_omitted_segment": [],
        }
        why = cr.get("rewrite_reason")
        if not has_change and not bool(cr.get("keep_as_is")) and not bool(cr.get("dedup_suppressed")):
            why = None if not bool(cr.get("user_focus_hit")) and not bool(cr.get("factual_hit")) else why
        cr["change_record"] = {
            "change_type": change_type,
            "unchanged_segment": segs.get("unchanged_segment", []),
            "inserted_segment": segs.get("inserted_segment", []),
            "deleted_segment": segs.get("deleted_segment", []),
            "moved_or_omitted_segment": segs.get("moved_or_omitted_segment", []),
            "why_changed": why,
        }
        if has_change and not (isinstance(cr.get("changed_segments"), list) and cr.get("changed_segments")):
            before0 = " ".join([str(x) for x in (segs.get("deleted_segment") or []) if isinstance(x, str) and x.strip()][:2]).strip()
            after0 = " ".join([str(x) for x in (segs.get("inserted_segment") or []) if isinstance(x, str) and x.strip()][:2]).strip()
            if before0 or after0:
                cr["changed_segments"] = [{"before": before0[:140], "after": after0[:140]}]
        if bool(cr.get("dedup_suppressed")):
            cr["display_kind"] = "guidance"
        elif bool(cr.get("keep_as_is")):
            cr["display_kind"] = "keep"
        elif has_change and (bool(cr.get("must_fix")) or bool(cr.get("approval_required")) or bool(cr.get("high_risk"))):
            cr["display_kind"] = "redline"
        elif has_change:
            cr["display_kind"] = "guidance"
        elif bool(cr.get("user_focus_hit")) or bool(cr.get("factual_hit")) or bool(cr.get("must_fix")) or str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM"):
            cr["display_kind"] = "guidance"
        else:
            cr["display_kind"] = "note"

    # [Dealer Rental Final Gate] isr_*/sppc_* 제거 + 조항-문안 hard gate.
    # MUST run here — after has_rewrite_change/redline metadata are computed
    # above (so a mismatch-downgraded item's has_rewrite_change=False is not
    # clobbered by that loop) but before the Top 3 risk synthesis / Output
    # Filter / self-check blocks below build meta.final_findings, the single
    # source of truth the UI and DOCX both read. Previously this gate ran only
    # once, at the very end of the function, well after meta.final_findings
    # was already built from the pre-gate clause_results — so a stripped
    # item's count/clause_id could survive in meta.final_findings while being
    # absent from the clause_results actually returned to the caller
    # (final_findings_count(ui) != final_findings_count(docx) / dangling
    # clause_id).
    _dlr_type = (getattr(_detailed_profile, "contract_type", None) or str(contract_type or ""))
    clause_results = apply_dealer_rental_final_gate(clause_results, _dlr_type)

    # [Mandatory Review Targets] 사용자가 review_focus에 직접 인용한 조항번호
    # (예: "제5조 제2항 제1호")는 룰/AI 매칭 여부와 무관하게 최종 결과에서
    # 절대 누락되어서는 안 된다 — see mandatory_review_target.py.
    from runtime.review.mandatory_review_target import annotate_and_track_mandatory_targets
    _mandatory_target_status = annotate_and_track_mandatory_targets(
        clause_results=clause_results,
        clauses=clauses,
        review_focus=review_focus,
    )

    frc1 = contract_context.get("final_review_context") if isinstance(contract_context, dict) else None
    if isinstance(frc1, dict) and bool(frc1.get("expert_mode")):
        party1 = frc1.get("party_role") if isinstance(frc1.get("party_role"), dict) else {}
        our_role1 = str(party1.get("our_role") or "")
        # is_common_legal_risk(원문 regex로 직접 확인된 실존 독소조항)와
        # is_checklist_item(없는 조항 신설 권고 — 이미 Priority 3로 별도 억제됨)은
        # 이 top-5 재점수 캡에서도 제외한다. 그렇지 않으면 위의 _apply_review_
        # priority_engine에서 준 예외가 여기서 다시 무력화되어 실제 존재하는
        # 불리한 조항이 임의로 MEDIUM 강등된다(변호사형 전체계약 판단 지시).
        high_candidates = [
            cr
            for cr in clause_results
            if isinstance(cr, dict)
            and not bool(cr.get("keep_as_is"))
            and not bool(cr.get("dedup_suppressed"))
            and not bool(cr.get("is_common_legal_risk"))
            and not bool(cr.get("is_checklist_item"))
            and (str(cr.get("risk_tier") or "").upper() == "HIGH" or bool(cr.get("high_risk")) or bool(cr.get("approval_required")))
        ]
        if len(high_candidates) > 5:
            topic_weight_supplier = {
                "dealer_unfair": 40,
                "payment_settlement": 35,
                "termination": 32,
                "cost_burden": 28,
                "personal_data": 18,
                "dispute": 5,
            }
            topic_weight_contractor = {
                "payment_settlement": 40,
                "other": 34,
                "safety": 28,
                "termination": 22,
                "cost_burden": 18,
                "dispute": 6,
            }
            topic_weight_rental = {
                "payment_settlement": 40,
                "termination": 34,
                "personal_data": 28,
                "other": 20,
                "dispute": 6,
            }
            tw = (
                topic_weight_supplier
                if our_role1 == "supplier"
                else (topic_weight_contractor if our_role1 == "contractor" else (topic_weight_rental if our_role1 == "rental_provider" else {}))
            )

            def _score_high(cr: dict[str, Any]) -> int:
                s = 0
                if bool(cr.get("approval_required")):
                    s += 60
                if bool(cr.get("high_risk")):
                    s += 45
                if bool(cr.get("must_fix")):
                    s += 30
                if bool(cr.get("user_focus_hit")):
                    s += 20
                if str(cr.get("risk_tier") or "").upper() == "HIGH":
                    s += 10
                s += int(tw.get(str(cr.get("clause_topic") or ""), 0))
                return s

            keep = sorted(high_candidates, key=lambda cr: (-_score_high(cr), str(cr.get("clause_id") or "")))[:5]
            keep_ids = {str(cr.get("clause_id") or "") for cr in keep if str(cr.get("clause_id") or "")}
            for cr in high_candidates:
                cid = str(cr.get("clause_id") or "")
                if cid and cid not in keep_ids:
                    cr["expert_demoted_from_high"] = True
                    cr["risk_tier"] = "MEDIUM"
                    cr["high_risk"] = False
                    cr["approval_required"] = False
                    cr["must_fix"] = False
                    if bool(cr.get("has_rewrite_change")):
                        cr["display_kind"] = "guidance"
                    else:
                        cr["display_kind"] = "note"

    focus_mapping_debug: list[dict[str, Any]] = []
    if focus_codes:
        for code in focus_codes:
            mapped = [
                str(cr.get("clause_id") or "")
                for cr in clause_results
                if isinstance(cr, dict) and str(cr.get("clause_id") or "") and code in (cr.get("user_focus_matches") or [])
            ]
            mapped = [x for x in mapped if x]
            cand: list[str] = []
            note = ""
            aset = dealer_focus_articles_by_code.get(code) if isinstance(dealer_focus_articles_by_code, dict) else None
            if not mapped:
                if isinstance(aset, set) and aset:
                    for cr in clause_results:
                        if not isinstance(cr, dict):
                            continue
                        if str(cr.get("clause_id") or "") and (_article_int_from_cr(cr) in aset):
                            cand.append(str(cr.get("clause_id") or ""))
                        if len(cand) >= 8:
                            break
                    note = "키워드/토픽 히트가 약해 탐지되지 않았을 수 있어, 조문 번호 기반 후보를 함께 제시함."
                else:
                    note = "키워드/토픽 히트가 없어 탐지되지 않았을 수 있음."
            focus_mapping_debug.append(
                {
                    "objective_code": code,
                    "objective_title": focus_title_by_code_obj.get(code, code),
                    "mapped_clause_ids": mapped[:40],
                    "candidate_clause_ids": cand[:12],
                    "note": note,
                }
            )

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

    user_focus_mapping_table: list[dict[str, Any]] = []
    frc_obj = contract_context.get("final_review_context") if isinstance(contract_context, dict) else None
    focus_items0 = (frc_obj.get("user_focus_issues") if isinstance(frc_obj, dict) else None) if isinstance(frc_obj, dict) else None
    if isinstance(focus_items0, list) and focus_items0:
        for obj in focus_items0[:12]:
            if not isinstance(obj, dict):
                continue
            code0 = str(obj.get("code") or "").strip()
            title0 = str(obj.get("title") or obj.get("code") or "").strip()
            if not code0:
                continue
            aset0 = dealer_focus_articles_by_code.get(code0) if isinstance(dealer_focus_articles_by_code, dict) else None
            aset0 = aset0 if isinstance(aset0, set) else set()
            cands = [cr for cr in clause_results if isinstance(cr, dict) and code0 in (cr.get("user_focus_matches") or [])]
            cands = sorted(
                cands,
                key=lambda cr: (
                    0 if bool(cr.get("user_focus_hit")) else 1,
                    0 if (_article_int_from_cr(cr) in aset0) else 1,
                    _dealer_issue_rank(cr) if prof.profile == "dealer_consignment" else 9,
                    str(cr.get("clause_id") or ""),
                ),
            )
            seen_articles: set[int] = set()
            ids: list[str] = []
            labels: list[str] = []
            for cr in cands:
                a0 = _article_int_from_cr(cr) or -1
                if a0 in seen_articles:
                    continue
                seen_articles.add(a0)
                cid = str(cr.get("clause_id") or "")
                lab = str(cr.get("display_path") or cid)
                if cid:
                    ids.append(cid)
                    labels.append(lab)
                if len(ids) >= 12:
                    break
            user_focus_mapping_table.append(
                {
                    "objective_code": code0,
                    "objective_title": title0 or code0,
                    "matched_clause_ids": ids,
                    "matched_clause_labels": labels,
                }
            )

    # ── [Top 3 Risk Synthesis] LLM 기반 치명적 리스크 Top 3 생성 ────────────
    _top_risks_llm: list[dict[str, Any]] = []
    _overall_recommendation: str = ""
    _recommendation_reason: str = ""
    _high_med = [
        cr for cr in clause_results
        if isinstance(cr, dict) and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
    ]
    if ai_enabled and ai_provider and ai_model and _high_med:
        try:
            _meta_summary = _format_meta_summary(_llm_meta, str(contract_type or ""), str(entity or ""))
            _clause_summaries = _format_clause_summaries(clause_results)
            _top3_user = TOP3_RISK_USER_TEMPLATE.format(
                meta_summary=_meta_summary,
                all_clause_summaries=_clause_summaries,
            )
            _req3 = AIRequest(
                model=ai_model,
                messages=build_messages(TOP3_RISK_SYSTEM, _top3_user),
                temperature=float(ai_temperature),
                max_tokens=min(int(ai_max_tokens), 2000),
                timeout_sec=float(ai_timeout_sec),
            )
            _resp3 = ai_provider.complete(_req3)
            _obj3 = _try_json(_resp3.content) if _resp3 and _resp3.content else None
            if isinstance(_obj3, dict):
                if isinstance(_obj3.get("top_risks"), list):
                    _top_risks_llm = [r for r in _obj3["top_risks"] if isinstance(r, dict)][:5]
                if isinstance(_obj3.get("overall_recommendation"), str):
                    _overall_recommendation = _obj3["overall_recommendation"].strip()
                if isinstance(_obj3.get("recommendation_reason"), str):
                    _recommendation_reason = _obj3["recommendation_reason"].strip()
        except Exception:
            pass
    # ─────────────────────────────────────────────────────────────────────────

    # ── [Senior Counsel 판단] legal_risk와 negotiation_priority 분리 ────────
    # "법적으로 문제인가"(risk_tier/severity)와 "지금 협상 테이블에 올릴
    # 가치가 있는가"(negotiation_priority)를 별도 축으로 계산해 각 finding에
    # 부착한다(2026-09-04 지시). Output Filter가 이 값을 그대로 UI/DOCX로
    # 전달하도록, 그 이전에 계산해야 한다.
    try:
        from runtime.review.counterparty_role import classify_counterparty_role
        from runtime.review.exposure_classification import classify_exposure
        from runtime.review.negotiation_action import classify_negotiation_action
        _counterparty_role = classify_counterparty_role(str(text or ""))
        for cr in clause_results:
            if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
                continue
            # clr_late_penalty_rate_uncapped처럼 이미 자체적으로 exposure_
            # category를 계산해 부착한 rule도 있지만, 그 외 common_legal_risk
            # 룰(예: clr_third_party_debt_guarantee)은 아직 계산되어 있지
            # 않으므로 여기서 일괄 보강한다 — 개별 rule마다 중복 구현하지
            # 않고 한 곳에서 모든 finding에 동일하게 적용한다.
            if not cr.get("exposure_category"):
                cr["exposure_category"] = classify_exposure(
                    str(cr.get("original_text") or ""), _our_party_aliases,
                )
            cr.update(classify_negotiation_action(cr, counterparty_role=_counterparty_role))

        # [Risk Cascade 연동] (2026-09-04 지시, 요구 9/12) — 지체상금(예:
        # KOTRA Article 3.4)처럼 상대방 전용 리스크(counterparty_only)로
        # ACCEPT 처리된 finding이라도, 같은 계약에 우리 쪽 보증 finding
        # (clr_third_party_debt_guarantee)이 있으면 그 보증조항이 해결되기
        # 전까지는 조건부로 우리 리스크에 연결된다 — "4.3이 삭제/제한되면
        # 3.4는 협상우선순위를 낮출 수 있다"는 지시를 반영해, ACCEPT로
        # 확정하지 않고 조건부 NEGOTIATE_IF_POSSIBLE + 의존관계로 표시한다.
        _guarantee_cr = next(
            (cr for cr in clause_results if isinstance(cr, dict) and cr.get("clause_id") == "clr_third_party_debt_guarantee"
             and not bool(cr.get("dedup_suppressed"))),
            None,
        )
        if _guarantee_cr is not None:
            for cr in clause_results:
                if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
                    continue
                # 지체상금류(late_penalty)만 연동한다 — risk_cascade.py의
                # "delay_to_guarantee" 체인이 실제로 연결하는 finding이 이
                # 유형이며, 다른 counterparty_only finding까지 무차별
                # 연동하면 무관한 조항에도 잘못된 의존관계가 붙는다.
                if cr.get("clause_id") != "clr_late_penalty_rate_uncapped":
                    continue
                if cr.get("business_exposure") == "counterparty_only" and cr.get("negotiation_priority") == "ACCEPT":
                    cr["negotiation_priority"] = "NEGOTIATE_IF_POSSIBLE(조건부)"
                    cr["negotiation_priority_depends_on"] = str(_guarantee_cr.get("clause_id") or "")
    except Exception:
        pass

    # ── [Output Filter] HIGH/MEDIUM 필터 + Top 5 핵심 리스크 ─────────────────
    # build_final_findings() is the single canonical clause_results -> final-
    # issue-list conversion, shared with server.py's DOCX/PDF download
    # endpoint — so "what the reviewer sees here" and "what ends up in the
    # downloaded file" are computed by the same rule, not two independently
    # maintained filters that can silently diverge in count and content.
    _filtered_output: dict = {}
    try:
        from runtime.review.output_filter import (
            filter_issues as _fi,
            clause_results_to_review_issues as _cr_to_ri,
            count_low_issues_in_output as _cli,
        )
        _type_code = (_detailed_profile.contract_type if _detailed_profile is not None else "general")
        _review_issues_raw = _cr_to_ri(clause_results)
        _filtered_output = _fi(_review_issues_raw, contract_type_code=_type_code, include_low=False)
        _low_count_in_output = _cli({"clause_results": clause_results})
    except Exception:
        _filtered_output = {}
        _low_count_in_output = 0

    # ── [UI/DOCX 일치 강제] ───────────────────────────────────────────────
    # output_filter의 dedup(같은 조항 병합 + 같은 rule의 정적 issue_title
    # 충돌로 인한 병합)이 제거한 항목은 UI에서도 동일하게 숨긴다 — "UI에는
    # 나오는데 DOCX/PDF에는 없는" 조항이 남지 않도록, DOCX가 최종 채택한
    # HIGH/MEDIUM id 집합을 canonical 기준으로 삼아 그 밖의 HIGH/MEDIUM
    # clause_results를 dedup_suppressed로 되먹임한다. UI(internal_demo_
    # chat_ui.py 등)는 이미 dedup_suppressed를 항상 존중하므로 이 필드
    # 하나로 두 화면이 같은 최종 findings를 보게 된다(2026-09-02).
    if _filtered_output:
        _docx_visible_ids = {
            str(i.clause_id) for i in (_filtered_output.get("high", []) + _filtered_output.get("medium", []))
        }
        for cr in clause_results:
            if not isinstance(cr, dict):
                continue
            if bool(cr.get("dedup_suppressed")) or bool(cr.get("keep_as_is")):
                continue
            _ui_tier = str(cr.get("risk_tier") or "").upper()
            if _ui_tier in ("HIGH", "MEDIUM") and str(cr.get("clause_id") or "") not in _docx_visible_ids:
                cr["dedup_suppressed"] = True

    # ── [Final Self-Check] requirement.md > Self-Check gate ─────────────────
    # 결과를 반환하기 전 마지막으로 재검증한다: 계약유형/역할이 이 리뷰 전체에서
    # 일관되게 쓰였는지, 유형과 무관한 문구가 남아있지 않은지, 원문-문제점-수정안이
    # 같은 조항을 가리키는지, 놓친 우선순위 리스크가 있는지. 이 패스는 상위
    # 단계의 개별 게이트가 놓친 경우를 잡아내는 최종 안전망이다.
    _final_findings_clause_ids = {
        str(i.clause_id) for i in (_filtered_output.get("high", []) + _filtered_output.get("medium", []))
    } if _filtered_output else set()
    from runtime.review.self_check import run_self_check as _run_self_check
    _self_check_report = _run_self_check(
        clause_results=clause_results,
        contract_type_code=_canonical_profile.contract_type,
        contract_class=_contract_class,
        our_role_bucket=_canonical_profile.our_role_bucket,
        confidence=_canonical_profile.confidence,
        full_text=str(text or ""),
        final_findings_counts={
            "high_count": len(_filtered_output.get("high", [])) if _filtered_output else 0,
            "medium_count": len(_filtered_output.get("medium", [])) if _filtered_output else 0,
        },
        mandatory_review_targets=_mandatory_target_status,
        final_findings_clause_ids=_final_findings_clause_ids,
        legal_map_fields=_legal_map.fields,
        legal_applicability_results=[r.to_dict() for r in _legal_applicability_results],
    )

    # ── [Self-Check 이후 재계산] (2026-09-04 지시로 발견) ────────────────────
    # run_self_check()의 hallucination-guard 백스톱(예: 계약유형과 무관한
    # 문구가 섞인 AI rewrite)은 clause_results를 직접 mutate해 risk_tier를
    # LOW로 낮춘다. 하지만 그 시점은 이미 _filtered_output(= meta.final_
    # findings, UI/DOCX가 공유하는 "단일 원본")을 계산한 *이후*라, self_check가
    # 방금 강등한 finding이 계속 HIGH/MEDIUM으로 남아 최종 출력에 박제된다.
    # 실제로 KOTRA 3자 컨설팅계약 다운로드에서 이 순서 문제가 재현됐다 —
    # self_check가 지식재산권/IP 환각(hallucination) finding을 LOW로 낮췄지만
    # final_findings에는 이미 HIGH로 포함되어, 이후 별도로 재구성되는 DOCX
    # 경로(risk_tier를 다시 읽음)와 개수가 어긋나 REVIEW_FAILED_OUTPUT_
    # MISMATCH가 발생했다. self_check 이후 clause_results 기준으로 다시
    # 계산해 이 클래스의 불일치를 구조적으로 막는다.
    try:
        _review_issues_raw = _cr_to_ri(clause_results)
        _filtered_output = _fi(_review_issues_raw, contract_type_code=_type_code, include_low=False)
        _low_count_in_output = _cli({"clause_results": clause_results})
    except Exception:
        pass

    meta = {
        "self_check": _self_check_report,
        "mandatory_review_targets": _mandatory_target_status,
        "review_posture": review_posture,
        "party_role": party.to_dict(),
        "contract_profile": (contract_context.get("contract_profile") if isinstance(contract_context, dict) else None),
        "jurisdiction": (contract_context.get("jurisdiction") if isinstance(contract_context, dict) else None),
        "final_review_context": (contract_context.get("final_review_context") if isinstance(contract_context, dict) else None),
        "user_focus_mapping_debug": focus_mapping_debug[:12],
        "user_focus_clause_ids": [str(cr.get("clause_id") or "") for cr in clause_results if bool(cr.get("user_focus_hit"))][:40],
        "user_focus_mapping_table": user_focus_mapping_table,
        "changed_clause_ids": [str(cr.get("clause_id") or "") for cr in clause_results if bool(cr.get("has_rewrite_change"))][:200],
        "text_length": text_len,
        "text_sha256": sha256((text or "").encode("utf-8", errors="replace")).hexdigest() if text else None,
        "clause_count": clause_count,
        "issue_clause_count": len(clause_results),
        # tier_counts: filtered output 기반 (UI·DOCX 동일 소스 보장)
        # raw must_count/medium_count/low_count는 quality gate 없음 → DOCX와 불일치 원인
        "tier_counts": {
            "must": len(_filtered_output.get("high", [])) if _filtered_output else must_count,
            "medium": len(_filtered_output.get("medium", [])) if _filtered_output else medium_count,
            "low": _low_count_in_output if _filtered_output else low_count,
            # 원본 raw 카운트 보존 (디버깅용)
            "raw_must": must_count,
            "raw_medium": medium_count,
            "raw_low": low_count,
        },
        "headings_found": headings_found,
        "fallback_only": fallback_only,
        "warnings": warnings[:10],
        "docx_allowed": docx_allowed,
        "law_errors": law_errors[:5],
        "ai": ai_state,
        "deep_review_shortlist_clause_ids": deep_review_shortlist_ids[:60] if isinstance(deep_review_shortlist_ids, list) else [],
        "clause_extraction_report": clause_report.to_dict() if isinstance(clause_report, object) else None,
        "contract_nature": _contract_nature,
        "contract_class": _contract_class,
        "top_risks_llm": _top_risks_llm,
        "overall_recommendation": _overall_recommendation,
        "recommendation_reason": _recommendation_reason,
        "structure_diagnosis": generate_structure_diagnosis_section(_struct),
        "contract_structure": _struct.contract_structure,
        "structure_confidence": _struct.structure_confidence,
        "detailed_contract_profile": (_detailed_profile.to_dict() if _detailed_profile is not None else None),
        "top_risks_filtered": [i.to_dict() for i in _filtered_output.get("top_risks", [])] if _filtered_output else [],
        "high_issues_filtered": [i.to_dict() for i in _filtered_output.get("high", [])] if _filtered_output else [],
        "medium_issues_filtered": [i.to_dict() for i in _filtered_output.get("medium", [])] if _filtered_output else [],
        "low_count_in_output": _low_count_in_output,
        # final_findings: UI·DOCX·다운로드가 공유하는 단일 원본
        "final_findings": {
            "high_count": len(_filtered_output.get("high", [])) if _filtered_output else 0,
            "medium_count": len(_filtered_output.get("medium", [])) if _filtered_output else 0,
            "low_count": _low_count_in_output,
            "must_fix_count": sum(1 for i in (_filtered_output.get("high", []) if _filtered_output else []) if i.approval_required),
            "display_buckets": {
                "필수수정": len(_filtered_output.get("high", [])) if _filtered_output else 0,
                "권장수정": len(_filtered_output.get("medium", [])) if _filtered_output else 0,
                "참고": _low_count_in_output,
            },
            "top_risks": [i.to_dict() for i in _filtered_output.get("top_risks", [])] if _filtered_output else [],
            "high_issues": [i.to_dict() for i in _filtered_output.get("high", [])] if _filtered_output else [],
            "medium_issues": [i.to_dict() for i in _filtered_output.get("medium", [])] if _filtered_output else [],
        },
    }

    # ── [Risk Scenario Modeling] 가상 사고 시나리오 기반 리스크 추출 ────────
    risk_scenarios = detect_risk_scenarios(str(text or ""), _contract_nature)

    # ── [Risk Cascade] 계약 전체를 관통하는 리스크 연쇄(contract-level) ─────
    from runtime.review.risk_cascade import build_risk_cascades
    risk_cascades = build_risk_cascades(clause_results, _legal_map.fields)

    # ── [Strategic Inquiry] 계약 유형별 쟁점 질문 생성 ───────────────────────
    strategic_questions = generate_strategic_inquiry(
        contract_class=_contract_class,
        contract_nature=_contract_nature,
        existing_answers=answers if isinstance(answers, dict) else None,
        user_focus=review_focus,
        our_role=party.our_role,
    )

    # ── [Clause-Level Conflict Check] 조항 간 모순 감지 ─────────────────────
    clause_conflicts = detect_clause_conflicts(clause_results)

    # ── [Executive Summary] 변호사식 핵심 요약 생성 ─────────────────────────
    executive_summary = generate_executive_summary(clause_results, clause_conflicts)

    meta["contract_legal_map"] = _legal_map.to_dict()
    meta["legal_map_role_override"] = _role_override_audit
    meta["semantic_mismatches"] = [
        cr.get("semantic_mismatch")
        for cr in clause_results
        if isinstance(cr, dict) and cr.get("semantic_mismatch")
    ]
    meta["legal_applicability_review"] = [r.to_dict() for r in _legal_applicability_results]
    meta["user_cited_statutes"] = _cited_statutes
    # 사용자가 명시적으로 지정한 법률(_cited_statutes)만 "누락되면 실패"
    # 대상이다 — AI가 스스로 추가 판단한 법률(source="ai_self_identified")
    # 은 사용자가 요청한 것이 아니므로 빠져도 REVIEW_FAILED 사유가 아니다.
    _missing_statutes = [
        r.statute for r in _legal_applicability_results
        if r.statute in _cited_statutes and r.source != "ai"
    ]
    if _missing_statutes:
        meta["review_status"] = "REVIEW_FAILED_USER_LEGAL_SCOPE_MISSING"
        meta["review_status_detail"] = f"AI 분석 없이 확인 필요 상태로 남은 법률: {', '.join(_missing_statutes)}"

    return ClauseLevelResult(
        review={
            **review,
            "risk_scenarios": risk_scenarios,
            "risk_cascades": risk_cascades,
            "strategic_questions": strategic_questions,
            "clause_conflicts": clause_conflicts,
            "executive_summary": executive_summary,
        },
        revision=revision,
        clauses=clauses,
        clause_results=clause_results,
        meta=meta,
    )
