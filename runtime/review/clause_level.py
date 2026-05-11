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
_RENTAL_COMMENT_KW = re.compile(r"소유권|위약금|렌탈|임대|리스|반납|반환.*계약|구독.*해지")


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


def _apply_domestic_filter(clause_results: list[dict[str, Any]], is_domestic: bool) -> None:
    """[Domestic Filter] 국내 전용 계약에서 dispute 조항의 국제 관할 리스크 코멘트를 차단한다."""
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


_SIDIZ_NAMES = frozenset({"시디즈", "SIDIZ", "Sidiz", "sidiz"})


def _apply_sidiz_position_strategy(
    clause_results: list[dict[str, Any]],
    entity: str,
    party_role: dict[str, Any] | None,
    text: str,
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
        if ct == "termination" or any(k in title for k in ("CI", "SI", "브랜드", "상표", "디자인", "외관")):
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
_LEVEL2_RIGHTS_KW = re.compile(
    r"지식재산|저작권|특허|상표|IP\b|사용권|재사용|비밀유지|기밀|영업비밀",
    re.IGNORECASE,
)
_LEVEL1_TOPICS = frozenset({"payment_settlement", "termination", "cost_burden", "other"})
_LEVEL2_TOPICS = frozenset({"confidentiality", "ip_ownership", "personal_data"})


def _classify_financial_risk_level(cr: dict[str, Any]) -> int:
    """LEVEL 1=실제 금전손실, 2=권리확보, 3=일반법률문구"""
    topic = str(cr.get("clause_topic") or "")
    combined = (str(cr.get("clause_title") or "") + " " + str(cr.get("original_text") or ""))[:800]
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
        # LEVEL 3 — 선언/일반 조항: 실질 리스크 없으면 NOTE로 강등
        if level == 3 and tier != "HIGH" and not bool(cr.get("must_fix")) and not bool(cr.get("user_focus_hit")) and not bool(cr.get("approval_required")):
            cr["risk_tier"] = "LOW"
            cr["must_fix"] = False
            cr["review_tier"] = "NOTE"

    # HIGH 최대 max_high개: LEVEL 순 정렬 후 초과분 MEDIUM 강등
    # 체크리스트 항목(is_checklist_item=True)은 캡 계산에서 제외
    high_items = [
        cr for cr in clause_results
        if isinstance(cr, dict)
        and str(cr.get("risk_tier") or "").upper() == "HIGH"
        and not bool(cr.get("dedup_suppressed"))
        and not bool(cr.get("keep_as_is"))
        and not bool(cr.get("is_checklist_item"))
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
        "trigger": re.compile(r"납기|일정|기간|완료\s*일|제출\s*일", re.IGNORECASE),
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
    """
    if contract_class != "advisory":
        return
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


def _classify_contract_type(contract_type: str, text: str, filename: str | None) -> str:
    """계약서 제목·목적 기반 엄격한 유형 분류.
    Returns: "advisory" | "rental" | "construction" | "project_installation" | "general"
    """
    haystack = (contract_type or "") + " " + (filename or "") + " " + (text or "")[:300]
    if _PROJECT_INSTALL_KW.search(haystack):
        return "project_installation"
    if _ADVISORY_CONTRACT_KW2.search(haystack):
        return "advisory"
    if _RENTAL_CONTRACT_KW2.search(haystack):
        return "rental"
    if _CONSTRUCTION_CONTRACT_KW.search(haystack):
        return "construction"
    return "general"


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
) -> None:
    """[Expert Advisory Review Logic — Phase 2: IP & Copyright Priority]
    자문/용역 계약에서 IP 귀속(CRITICAL)과 제3자 침해 보증을 점검한다.
    """
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

    # ── [Classification First] 계약 유형 최우선 확정 ─────────────────────────
    # requirement.md > Advanced Strategic Logic > Phase 1 참조.
    _contract_class = _classify_contract_type(str(contract_type), str(text or ""), filename)
    _is_advisory_class = (_contract_class == "advisory")
    _is_rental_class = (_contract_class == "rental")
    _is_construction_class = (_contract_class == "construction")
    _is_project_install_class = (_contract_class == "project_installation")

    # [REMOVED] 관련 법령 retrieval 영구 비활성화 — requirement.md > Section Removal Specs
    law_service = None

    party = infer_party_role(entity=str(entity), contract_type=str(contract_type), text=str(text), answers=answers)
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
    # -----------------------------------------------------------------------
    # [반복 코멘트 생성 방지] 1차 dedup: AI shortlist 구성 전에 미리 적용
    # → AI가 dedup_suppressed 항목에 새 rewrite를 생성하지 않도록 사전 차단
    # -----------------------------------------------------------------------
    _apply_article_dedup_and_consolidation(clause_results)

    selected = deep_review_shortlist[: max(0, desired)]
    # dedup_suppressed 항목은 AI 처리 대상에서 제외
    selected = [cr for cr in selected if not bool(cr.get("dedup_suppressed"))]
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
                # 계약 유형별 법령 DB 엄격 분리: advisory는 IP/저작권 중심 검색 유도
                _law_ct = _law_contract_type_for_search(_contract_class, str(contract_type))
                cr["related_laws"] = law_service.search_for_review(
                    entity=str(entity),
                    contract_type=_law_ct,
                    text=ctext,
                    matched_rules=rr,
                    scope="clause",
                    max_per_type=max_clause_law_items,
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
        if _is_advisory_class:
            # Advisory/자문/용역 계약 전용 AI 프롬프트 — Logic Isolation (Phase 2)
            system = (
                "너는 한국 기업 법무팀의 시니어 계약검토 변호사다. 현재 검토 대상은 자문·용역·개발 계약이다. "
                "party_role과 review_posture를 강하게 반영하되, 퍼시스가 비용을 지급하는 위탁자(갑)인 경우 다음 3개를 최우선으로 점검하라. "
                "① [IP 귀속 CRITICAL] 산출물의 저작권·지식재산권이 수탁자에게 귀속되거나 이용권만 부여되면 반드시 '위탁자(퍼시스) 전적 귀속'으로 수정 제안하라. "
                "근거: 저작권법 제9조 — 도급 계약에서 원칙적으로 수탁자 귀속이므로 명시 규정이 없으면 분쟁 발생. "
                "② [제3자 침해 보증 CRITICAL] IP 조항에 '수탁자는 제3자 권리를 침해하지 않음을 보증하며 침해 시 면책·배상' 문구가 없으면 삽입 제안하라. "
                "③ [배상 한도 예외 HIGH] 손해배상이 용역대금 총액으로 제한된 경우 IP침해·비밀유지위반·고의중과실은 한도 예외로 처리하는 단서를 삽입하라. "
                "관련 법령은 저작권법·부정경쟁방지법·민법(위임/도급)만 인용하라. "
                "렌탈·물류시설법·부동산세법·방문판매법·B2C 약관 관련 문구는 절대 생성하지 마라. "
                "제1·2·3조(목적·원칙·정의) 등 선언적 조항에 실무 의무 문구를 삽입하지 마라. "
                "원문을 최대한 유지하면서 문제되는 표현만 최소 변경으로 수정하라. "
                "근거 없는 추정 금지: 입력에 없는 사실을 새로 만들지 마라. "
                "rewrite_reason은 법률 근거 + 실무 리스크 중심으로 220자 이내로 작성하라. "
                "suggested_rewrite는 900자 이내, 계약서 법무 문체로 작성하라. "
                "출력은 반드시 첫 글자 '[' 로 시작하는 JSON 배열만 출력하고, 코드펜스/설명 문장을 절대 포함하지 마라. "
                "각 원소 형식은 clause_id/rewrite_reason/suggested_rewrite/changed_segments/risk_tier/must_fix 로 통일하라. "
                "risk_tier와 must_fix는 입력값을 그대로 유지해 출력하라. "
                "changed_segments는 변경된 핵심 구간 최대 3개를 {before, after} 형태로 요약하라."
            )
        else:
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
                    # dedup_suppressed 항목은 AI 수정안을 적용하지 않는다
                    if bool(cr.get("dedup_suppressed")):
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
        if ct0 == "termination":
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
        if tier0 == "MEDIUM" and not (bool(cr.get("approval_required")) or bool(cr.get("high_risk"))):
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
    _is_domestic = _is_domestic_only(str(text or ""), answers)
    # 1순위: Zero-Hallucination Guardrail (제1·2·3조 보호 + Advisory 금지키워드)
    _apply_zero_hallucination_guardrail(clause_results, str(contract_type), str(text or ""))
    # 2순위: Advisory IP & Copyright (자문/용역 → IP 귀속·보증 CRITICAL 점검)
    _apply_advisory_ip_review(clause_results, str(contract_type), str(text or ""), str(entity))
    # 3순위: 기존 필터 체인
    _apply_rental_filter(clause_results, _is_rental)
    _apply_domestic_filter(clause_results, _is_domestic)
    _apply_clause_integrity_filter(clause_results)
    _apply_sidiz_position_strategy(
        clause_results,
        str(entity),
        party.to_dict() if party is not None else None,
        str(text or ""),
    )
    _apply_global_sentence_dedup(clause_results)

    # ── [NEW ENGINES] requirement.md > Review Priority Engine / Checklist / Output Policy ─
    # 1. Service Contract 필수 체크리스트 (advisory 계약 전용 누락 항목 탐지)
    _apply_service_contract_checklist(clause_results, str(text or ""), _contract_class)
    # 1-1. Project Installation 필수 안전·교육 체크리스트
    _apply_project_installation_checklist(clause_results, str(text or ""), _contract_class)
    # 2. 리뷰 우선순위 엔진 (LEVEL 1~3 분류, HIGH 최대 5개 — 체크리스트 제외)
    _apply_review_priority_engine(clause_results, max_high=5)
    # 3. No Inline Rewrite 정책 (advisory: 원문 보존 + [추가 권고] 형태)
    _apply_no_inline_rewrite_policy(clause_results, _is_advisory_class)
    # ─────────────────────────────────────────────────────────────────────────

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

    frc1 = contract_context.get("final_review_context") if isinstance(contract_context, dict) else None
    if isinstance(frc1, dict) and bool(frc1.get("expert_mode")):
        party1 = frc1.get("party_role") if isinstance(frc1.get("party_role"), dict) else {}
        our_role1 = str(party1.get("our_role") or "")
        high_candidates = [
            cr
            for cr in clause_results
            if isinstance(cr, dict)
            and not bool(cr.get("keep_as_is"))
            and not bool(cr.get("dedup_suppressed"))
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
