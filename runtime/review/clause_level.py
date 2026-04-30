from __future__ import annotations

import difflib
import difflib as _difflib
import json
import re
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
from runtime.review.clause_topic import classify_clause_topic, infer_rewrite_topics, is_topic_compatible
from runtime.review.priority_map import infer_contract_profile
from runtime.review.final_review_context import build_final_review_context
from runtime.review.user_focus import objective_codes_to_clause_topics
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
    return []

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
    # article_number 기준으로 그룹화
    article_groups: dict[str, list[dict[str, Any]]] = {}
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        an = str(cr.get("article_number") or "").strip()
        if not an:
            continue
        article_groups.setdefault(an, []).append(cr)

    # 포괄적 리스크 범주 (개별 항마다 반복 금지 대상)
    _BROAD_RISK_TOPICS = {
        "dealer_unfair",
        "cost_burden",
        "payment_settlement",
        "termination",
        "personal_data",
        "safety",
    }
    _BROAD_RISK_CODES = {
        "RISK-006", "RISK-005", "RISK-002", "RISK-001",
        "DEALER-001", "C-001",
    }

    for an, group in article_groups.items():
        if len(group) < 2:
            # 단일 항: 중복 검사만 적용
            cr = group[0]
            sr = cr.get("suggested_rewrite")
            if isinstance(sr, str) and sr.strip():
                if _is_duplicate_rewrite(sr):
                    # 인라인 수정으로 전환
                    ot = str(cr.get("original_text") or "")
                    cr["suggested_rewrite"] = _to_inline_rewrite(ot, sr)
                    cr["rewrite_reason"] = (
                        (str(cr.get("rewrite_reason") or "") + " [중복 수정안 → 인라인 수정으로 전환]").strip()
                    )
                    cr["dedup_inline"] = True
                else:
                    seen_rewrites.append(_norm_for_sim(sr))
            continue

        # ── 지침 1: 동일 조 내 리스크 동일성 판단 ──────────────────────────
        # 각 항의 risk_codes, clause_topic 수집
        group_risk_codes: set[str] = set()
        group_topics: set[str] = set()
        for cr in group:
            for ar in (cr.get("applied_rules") or []):
                if isinstance(ar, dict) and isinstance(ar.get("rule_id"), str):
                    group_risk_codes.add(str(ar["rule_id"]))
            t = str(cr.get("clause_topic") or "")
            if t:
                group_topics.add(t)

        has_broad_risk = bool(group_risk_codes & _BROAD_RISK_CODES) or bool(group_topics & _BROAD_RISK_TOPICS)

        # ── 지침 2: 대표 항(anchor) 선정 ────────────────────────────────────
        # 우선순위: approval_required > high_risk > risk_tier HIGH > must_fix > 첫 번째 항
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
                s -= int(pn)  # 낮은 항 번호 우선
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

        # anchor에 article_review_anchor 마킹
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
        for cr in secondaries:
            cr_sr = cr.get("suggested_rewrite")
            if not (isinstance(cr_sr, str) and cr_sr.strip()):
                continue

            # 중복 검사: anchor와 80% 이상 유사하면 참조 메시지로 대체
            anchor_norm = _norm_for_sim(str(anchor.get("suggested_rewrite") or ""))
            cr_norm = _norm_for_sim(cr_sr)
            sim = _sim_ratio(anchor_norm, cr_norm)

            if sim >= 0.80:
                # 지침 2: 참조 메시지로 대체
                pn_ref = anchor_pn if anchor_pn else anchor_dp
                cr["suggested_rewrite"] = None
                old_reason = str(cr.get("rewrite_reason") or "").strip()
                ref_msg = (
                    f"위 제{pn_ref}항의 수정안과 동일한 리스크가 존재하므로 통합 관리 필요. "
                    f"({an}조 전체를 [Article Review] 기준으로 검토하십시오.)"
                )
                cr["rewrite_reason"] = (old_reason + " / " + ref_msg).strip(" / ") if old_reason else ref_msg
                cr["article_review_ref"] = anchor.get("clause_id") or anchor_dp
                cr["dedup_suppressed"] = True
                cr["changed_segments"] = []
            else:
                # 유사도 낮음: 독립 수정안 유지하되 전역 중복 검사 적용
                if _is_duplicate_rewrite(cr_sr):
                    ot = str(cr.get("original_text") or "")
                    cr["suggested_rewrite"] = _to_inline_rewrite(ot, cr_sr)
                    cr["rewrite_reason"] = (
                        (str(cr.get("rewrite_reason") or "") + " [중복 수정안 → 인라인 수정으로 전환]").strip()
                    )
                    cr["dedup_inline"] = True
                else:
                    seen_rewrites.append(_norm_for_sim(cr_sr))
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


def _article_int_from_cr(cr: dict[str, Any]) -> int | None:
    return (
        _article_int(cr.get("article_number"))
        or _article_int(cr.get("clause_id"))
        or _article_int(cr.get("display_path"))
        or _article_int(cr.get("clause_title"))
    )


def _dealer_issue_rank(cr: dict[str, Any]) -> int:
    a = _article_int_from_cr(cr)
    if a in (21, 2, 3):
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

    party = infer_party_role(contract_type=str(contract_type), text=str(text), answers=answers)
    review_posture = infer_review_posture(party=party, contract_type=str(contract_type), text=str(text))
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
    clauses, clause_report = extract_clauses(text)
    derived = review.get("derived_context") if isinstance(review, dict) else None
    prof = infer_contract_profile(contract_type=str(contract_type), text=str(text or ""))
    frc = build_final_review_context(
        entity=str(entity),
        contract_type=str(contract_type),
        text=str(text or ""),
        filename=filename,
        answers=answers,
        review_focus=review_focus,
        party_role=(party.to_dict() if party is not None else None),
    )
    contract_context = {
        "entity": str(entity),
        "contract_type": str(contract_type),
        "contract_text": str(text or ""),
        "jurisdiction": (derived.get("jurisdiction") if isinstance(derived, dict) else None),
        "contract_profile": prof.to_dict(),
        "final_review_context": frc.to_dict(),
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
                dealer_focus_articles_by_code[c] = {2, 3, 21, 23}
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
                "detected_issue_list": it.get("detected_issues") if isinstance(it.get("detected_issues"), list) else [],
                "related_rules": related_rules,
                "question_context_hit": bool(question_context_hit),
                "related_laws": None,
                "rewrite_reason": rewrite_reason,
                "suggested_direction": it.get("suggested_direction") if isinstance(it.get("suggested_direction"), list) else [],
                "suggested_rewrite": suggested_rewrite,
                "approval_required": bool(it.get("approval_required")) if not keep_as_is else False,
                "high_risk": bool(it.get("high_risk")) if not keep_as_is else False,
                "risk_tier": risk_tier,
                "must_fix": must_fix,
                "review_tier": review_tier,
                "unfavorable_to_us": bool(it.get("unfavorable_to_us")),
                "keep_as_is": bool(keep_as_is),
            }
        )

    existing_ids = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    if prof.profile == "dealer_consignment":
        must_articles = {2, 3, 8, 9, 10, 11, 14, 17, 21, 23, 27}
        for c in clauses:
            cid = str(c.clause_id or "")
            if not cid or cid in existing_ids:
                continue
            a = _article_int(c.article_number) or _article_int(cid) or _article_int(c.display_path) or _article_int(c.title)
            hay_key = (str(c.display_path or "") + " " + str(c.title or "")).strip()
            is_key_by_title = any(
                k in hay_key
                for k in (
                    "기본원칙",
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

    if prof.profile == "dealer_consignment":
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
            if ct0 == "payment_settlement":
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

    if prof.profile == "dealer_consignment":
        clause_results = sorted(
            clause_results,
            key=lambda x: (
                0 if bool(x.get("user_focus_hit")) else 1,
                _dealer_issue_rank(x if isinstance(x, dict) else {}),
                0 if bool(x.get("must_fix")) else 1,
                0 if x.get("approval_required") else 1,
                0 if str(x.get("risk_tier") or "").upper() == "HIGH" else (1 if str(x.get("risk_tier") or "").upper() == "MEDIUM" else 2),
                0 if bool(x.get("factual_hit")) else 1,
                0 if bool(x.get("question_context_hit")) else 1,
                str(x.get("clause_id") or ""),
            ),
        )
    else:
        clause_results = sorted(
            clause_results,
            key=lambda x: (
                0 if bool(x.get("user_focus_hit")) else 1,
                0 if x.get("approval_required") else 1,
                0 if str(x.get("risk_tier") or "").upper() == "HIGH" else (1 if str(x.get("risk_tier") or "").upper() == "MEDIUM" else 2),
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
    is_dealer_contract0 = (prof.profile == "dealer_consignment") or any(k in str(contract_type or "") for k in ("대리점", "유통", "위탁"))

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
    selected = deep_review_shortlist[: max(0, desired)]
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
        if bool(cr.get("keep_as_is")):
            continue
        parts: list[str] = []
        if bool(cr.get("user_focus_hit")):
            titles = cr.get("user_focus_match_titles") if isinstance(cr.get("user_focus_match_titles"), list) else []
            titles = [str(x) for x in titles if isinstance(x, str) and x.strip()]
            if titles:
                parts.append("사용자 중점 이슈: " + ", ".join(titles[:2]))
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
            "user_focus_issues(사용자 중점 검토 이슈)가 있으면 해당 이슈 관련 조항을 최우선으로 검토하고, rewrite_reason에 연결을 명확히 표시하라. "
            "조항 주제(clause_topic)와 무관한 문구를 제안하지 마라(분쟁조항에 비용전가/안전 문구 금지, 개인정보 조항에 산안법/현장 문구 금지). "
            "jurisdiction.kind가 domestic_korea이면 해외 집행/다국가 거래 reasoning을 절대 쓰지 마라. "
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
                    "final_review_context": (contract_context.get("final_review_context") if isinstance(contract_context, dict) else None),
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
                            "clause_topic": cr.get("clause_topic"),
                            "user_focus_hit": bool(cr.get("user_focus_hit")),
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
        is_dealer_contract = any(k in str(contract_type or "") for k in ("대리점", "위탁", "유통"))
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

    _dedup_rewrite_suggestions(clause_results)
    for cr in clause_results:
        if isinstance(cr, dict):
            cr.pop("_dedup_norm", None)

    for cr in clause_results:
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
        ct0 = str(cr.get("clause_topic") or "").strip()
        if ct0 == "payment_settlement":
            add = (
                "\n\n[추가]\n"
                "① 정산은 항목별 산식과 기준에 따라 이루어지며, 공제/상계는 계약 또는 사전 서면합의에 근거한 경우에 한한다.\n"
                "② 갑은 정산서(항목별 내역) 및 합리적 범위의 증빙을 제공하고, 을은 일정 기간 내 이의제기할 수 있다.\n"
            )
            cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
            if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                cr["suggested_direction"] = [
                    "공제/상계 요건을 계약/서면합의로 제한",
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
        if ct0 == "termination":
            add = (
                "\n\n[추가]\n"
                "① 해지(또는 계약 종료)는 객관적으로 중대한 위반이 있는 경우로 한정한다.\n"
                "② 원칙적으로 위반 사항을 특정하여 서면 최고하고, 상당한 시정기간을 부여한다.\n"
                "③ 예외적 즉시해지 사유는 신뢰관계를 본질적으로 훼손하는 고의·중대한 위반 등으로 좁게 열거한다.\n"
            )
            cr["suggested_rewrite"] = (ot0.rstrip() + add).strip()
            if not (isinstance(cr.get("suggested_direction"), list) and cr.get("suggested_direction")):
                cr["suggested_direction"] = [
                    "즉시 해지 사유를 객관적·중대한 위반으로 한정",
                    "원칙적으로 서면 최고 및 시정기간 부여",
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
        if tier0 == "MEDIUM" and not (bool(cr.get("approval_required")) or bool(cr.get("high_risk"))):
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"

    # -----------------------------------------------------------------------
    # [반복 코멘트 생성 방지] 4가지 지침 적용
    # 1. 조(Article) 단위 통합 판단
    # 2. 대표 항 지정 (나머지 항은 참조 메시지로 대체)
    # 3. 중복 검사(De-duplication): suggested_rewrite 80% 이상 유사 시 인라인 수정
    # 4. 리스크 범주화: 포괄적 내용은 [Article Review] 섹션으로 통합
    # -----------------------------------------------------------------------
    _apply_article_dedup_and_consolidation(clause_results)

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

    meta = {
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
        "tier_counts": {"must": must_count, "medium": medium_count, "low": low_count},
        "headings_found": headings_found,
        "fallback_only": fallback_only,
        "warnings": warnings[:10],
        "docx_allowed": docx_allowed,
        "law_errors": law_errors[:5],
        "ai": ai_state,
        "deep_review_shortlist_clause_ids": deep_review_shortlist_ids[:60] if isinstance(deep_review_shortlist_ids, list) else [],
        "clause_extraction_report": clause_report.to_dict() if isinstance(clause_report, object) else None,
    }
    return ClauseLevelResult(
        review=review,
        revision=revision,
        clauses=clauses,
        clause_results=clause_results,
        meta=meta,
    )
