"""존재 검증 Hard Gate — 없는 조항·문구를 만들어내지 않는다.

2026-09-14 지시(Hallucination Zero) 항목 1·2·3·6·7 —
  "없는 조항·문구·사실을 하나라도 만들어내는 것보다, '확인 불가' 라고 말하는
   것이 항상 우선이다."

무엇을 막는가 (실측 — SNS마케팅 제휴계약(실사례))
──────────────────────────────────────────────────
계약은 제10조까지인데 결과에 이런 항목이 실렸다.

    CP-006  "제12조 제3항 — 해지 시 정산 및 산출물 인도 기준 보완 필요"
            원문: "[제12조] 계약의 해제 및 해지 관련 조항"

제12조는 없다. 저 "원문" 은 계약서에서 온 문장이 아니라 체크리스트가
표준계약서 양식의 번호로 조립한 **문자열**이다. 게다가 이 계약에는 해지
조항이 **제4조(계약의 해지 및 위약금)** 로 실재한다 — 번호를 지어내는 바람에
있는 조항을 못 보고 없는 조항을 고치라고 한 셈이다.

세 가지를 검사한다
─────────────────
  1. 조항 존재   — 가리키는 조 번호가 `ClauseIndex` 에 있는가
  2. 인용 진위   — `original_text` 가 계약 원문에 실제로 있는가(90% 기준)
  3. 수정 대상   — redline 이 가리키는 위치가 실재하는가

처리 방식 — 지우기 전에 **정정**한다
──────────────────────────────────
"해지 정산 기준이 없다" 는 지적 자체는 대개 옳다. 틀린 것은 거기 붙은
**번호**다. 그래서 존재하지 않는 조항을 가리키는 항목이 "이 내용이 없으니
넣자" 는 취지이면 **신설 조항 형식으로 바꾼다**(지시 항목 2·6).

    제12조 제3항 — 해지 시 정산 …   →   [신설 제11조] 해지 시 정산 …
    원문: "[제12조] …"              →   원문 없음(해당 조항 없음 — 신설 필요)

취지가 그것이 아니면(실재하는 조항을 고치라는 주장인데 그 조항이 없으면)
그 항목은 근거가 없으므로 **삭제**한다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.clause_index import ClauseIndex

STATUS_NONEXISTENT_CLAUSE = "REVIEW_FAILED_NONEXISTENT_CLAUSE"
STATUS_FAKE_QUOTE = "REVIEW_FAILED_FAKE_QUOTE"
STATUS_HALLUCINATED_REFERENCE = "REVIEW_FAILED_HALLUCINATED_REFERENCE"
#: 번호는 실재하지만 그 조항이 finding 과 다른 이야기를 하는 경우(2차 보정 2항).
STATUS_SEMANTIC_ANCHOR_MISMATCH = "SEMANTIC_ANCHOR_MISMATCH"

#: 조항번호가 실릴 수 있는 표시 필드.
_REFERENCE_FIELDS = ("issue_title", "clause_title", "display_path")
#: 본문 성격의 필드. 여기 있는 번호도 담당자에게는 지시로 읽힌다.
#: 협상포지션이 특히 중요하다 — 담당자가 협상 테이블에 그대로 들고 가는 줄이다.
_BODY_FIELDS = ("problem", "rewrite_reason", "legal_business_reason",
                "suggested_rewrite", "proposed_revision", "recommendation_text",
                "negotiation_position", "negotiation_strategy", "worst_case_scenario")

#: 조항번호가 **목록**으로 들어가는 필드(2차 보정 1항).
#: 실측: 표시 경로를 "제11조 신설" 로 정정하고도 `related_clauses` 에는
#: ["제12조 제3항"] 이 그대로 남아, UI·DOCX 의 "관련 조항" 칸에 존재하지 않는
#: 조항이 계속 노출됐다.
_LIST_REFERENCE_FIELDS = (
    "clause_ids", "related_clauses", "related_clause_ids", "merged_clause_ids",
    "also_amend_clause_ids", "user_focus_match_titles",
)

#: "이 내용이 없으니 넣자" 는 취지의 표지. 이러면 삭제가 아니라 신설로 고친다.
_RX_ABSENCE_INTENT = re.compile(
    r"없습니다|없음|누락|미규정|규정되지\s*(?:않|아니)|부재|신설|추가\s*필요|보완\s*필요"
    r"|명시(?:되어)?\s*있지\s*(?:않|아니)|포함되지\s*(?:않|아니)"
)

#: "제12조 제3항", "[제12조]" 같은 참조 토막.
_RX_ARTICLE_REF = re.compile(
    r"\[?\s*제\s*(\d{1,3})\s*조\s*\]?(?:\s*제\s*\d{1,3}\s*항)?(?:\s*제\s*\d{1,3}\s*호)?"
)
#: 법령 인용은 계약 조항 참조가 아니다.
#:
#: 구분자를 허용해야 한다 — 실측에서 "저작권법, 제46조" 와 "부가가치세법, 제29조"
#: 가 계약 조항으로 오인돼 정상 finding 2건(저작권 2차활용·부가세 세금계산서)이
#: 통째로 삭제됐다. 법률명 뒤에는 쉼표·가운뎃점·닫는 괄호가 흔히 붙는다.
_RX_STATUTE_BEFORE = re.compile(
    r"(?:법|법률|령|규칙|조례|약관|」|\))\s*[,、·:：]?\s*$"
)


#: 문장 안에서 법령을 가리키는 낱말. "…법", "…법률", "시행령", "시행규칙" 등.
_RX_STATUTE_WORD = re.compile(
    r"[가-힣A-Za-z]{2,20}(?:법률|법)(?:상|은|는|이|가|을|를|의|에|과|와)?\b"
    r"|시행령|시행규칙|「[^」]{2,30}」"
)

#: 문장 경계. 한국어 계약 서술은 마침표·줄바꿈으로 끊긴다.
_RX_SENTENCE_BREAK = re.compile(r"[.。\n]")


def _is_statute_citation(text: str, at: int, *, sentence_scope: bool) -> bool:
    """이 위치의 "제N조" 가 **법령** 인용인가.

    `sentence_scope=False` 면 바로 앞에 법률명이 붙은 경우만 인정한다(표시·목록
    필드용). True 면 같은 문장에서 그 앞쪽에 법률명이 나오면 인용으로 본다.
    """
    head = str(text or "")[:at]
    if _RX_STATUTE_BEFORE.search(head.rstrip()):
        return True
    if not sentence_scope:
        return False
    # 같은 문장의 앞부분만 본다 — 앞 문장의 법률명까지 끌어오면 너무 넓어진다.
    breaks = list(_RX_SENTENCE_BREAK.finditer(head))
    sentence_head = head[breaks[-1].end():] if breaks else head
    return bool(_RX_STATUTE_WORD.search(sentence_head))


def _text_of(cr: dict[str, Any], keys: tuple[str, ...]) -> str:
    return "\n".join(str(cr.get(k) or "") for k in keys)


def _contract_article_refs(value: str, *, sentence_scope: bool = False) -> list[str]:
    """계약 조항 참조만 추린다(법령 인용 제외)."""
    out: list[str] = []
    text = str(value or "")
    for m in _RX_ARTICLE_REF.finditer(text):
        if _is_statute_citation(text, m.start(), sentence_scope=sentence_scope):
            continue
        num = str(int(m.group(1)))
        if num not in out:
            out.append(num)
    return out


def _is_new_clause_context(value: str, at: int) -> bool:
    """그 참조가 '신설' 맥락인가 — 신설은 없는 번호를 가리키는 것이 정상이다."""
    window = str(value or "")[max(0, at - 30): at + 30]
    return "신설" in window


#: "제9조(소유권의 귀속)" 처럼 **제목을 명시적으로 주장**하는 형태만 대조 대상이다.
_RX_ASSERTED_TITLE = re.compile(
    r"제\s*(\d{1,3})\s*조\s*[(（]\s*([^)）\n]{1,40}?)\s*[)）]"
)


def asserted_titles(cr: dict[str, Any]) -> list[tuple[str, str]]:
    """이 finding 이 주장하는 (조 번호, 조 제목) 쌍.

    두 경로에서 모은다.
      · 표시 문자열 안의 "제9조(소유권의 귀속)" 형태
      · 체크리스트가 채우는 `clause_ids` / `clause_titles` 짝

    **표시 문자열 전체를 제목으로 보지 않는다.** 종전에는 issue_title 통째를
    제목으로 대조해서, "제4조 제2항 — 존속조항 부재" 처럼 제목을 주장하지도
    않은 정상 finding 이 전부 "제목 불일치" 로 걸렸다(실측 5건).
    """
    pairs: list[tuple[str, str]] = []
    for field in _REFERENCE_FIELDS:
        for m in _RX_ASSERTED_TITLE.finditer(str(cr.get(field) or "")):
            pairs.append((str(int(m.group(1))), m.group(2).strip()))

    ids = cr.get("clause_ids")
    titles = cr.get("clause_titles")
    if isinstance(ids, list) and isinstance(titles, list) and len(ids) == len(titles):
        for raw_id, raw_title in zip(ids, titles):
            nums = _contract_article_refs(str(raw_id or ""))
            title = str(raw_title or "").strip()
            if len(nums) == 1 and title:
                pairs.append((nums[0], title))
    return pairs


#: 지시 항목 6 이 요구한 표기. 없는 조항은 이렇게 적는다.
ABSENT_CLAUSE_MARKER = "해당 조항 없음 — 신설 필요"

#: 통째로 괄호에 싸인 값은 "이건 설명이다" 라고 스스로 밝힌 것이다.
_RX_LABEL_ONLY = re.compile(r"^\s*[(\[（【][^)\]）】]*[)\]）】]\s*$", re.S)


def _is_quote_claim(text: str) -> bool:
    """이 값이 '계약 원문을 그대로 옮긴 것' 이라고 주장하는가.

    결정론적 rule 중에는 원문 대신 구조 설명을 넣는 것이 있다 —
    예: "(계약 전체 구조 — 별도 계약이라는 형식과 실제 존속기간·해지 연동 조항)".
    괄호로 감싸 스스로 설명임을 밝힌 값을 가짜 인용으로 판정하면, 부재를
    지적하는 정상 rule 이 통째로 무력화된다(실측: 그림닷컴 판매지원 계약에서
    HIGH 2건 중 1건이 사라졌다).
    """
    value = str(text or "").strip()
    if not value:
        return False
    if value == ABSENT_CLAUSE_MARKER:
        return False
    return not bool(_RX_LABEL_ONLY.match(value))


def _absence_intent(cr: dict[str, Any]) -> bool:
    blob = _text_of(cr, ("issue_title", "problem", "rewrite_reason",
                         "legal_business_reason", "checklist_status"))
    if str(cr.get("checklist_status") or "") == "absent":
        return True
    return bool(_RX_ABSENCE_INTENT.search(blob))


# ── 검사 ────────────────────────────────────────────────────────────────────

def verify_finding(cr: dict[str, Any], index: ClauseIndex) -> list[dict[str, Any]]:
    """finding 하나의 존재 검증 위반 목록. 비어 있으면 통과."""
    violations: list[dict[str, Any]] = []
    if index.structure_uncertain:
        # 구조를 확신하지 못하면 존재/부재를 단정하지 않는다(지시 항목 9).
        return violations

    # (1) 조항 존재 — 신설 맥락이 아닌 참조만 본다.
    unknown: list[str] = []
    # (필드값, 문장범위로 법령을 인정할지) 짝으로 모은다.
    scan: list[tuple[str, bool]] = [
        (str(cr.get(f) or ""), False) for f in _REFERENCE_FIELDS
    ]
    scan += [(str(cr.get(f) or ""), True) for f in _BODY_FIELDS]
    for field in _LIST_REFERENCE_FIELDS:
        value = cr.get(field)
        if isinstance(value, list):
            scan.extend((str(x or ""), False) for x in value)
        elif isinstance(value, str):
            scan.append((value, False))
    ri_scan = cr.get("redline_instruction")
    if isinstance(ri_scan, dict):
        scan.extend(
            (str(ri_scan.get(k) or ""), True)
            for k in ("replacement_text", "final_clause_text", "reason")
        )
    for value, sentence_scope in scan:
        if not value:
            continue
        for m in _RX_ARTICLE_REF.finditer(value):
            if _is_statute_citation(value, m.start(), sentence_scope=sentence_scope):
                continue
            num = str(int(m.group(1)))
            if index.has_article(num) or _is_new_clause_context(value, m.start()):
                continue
            if num not in unknown:
                unknown.append(num)
    if unknown:
        violations.append({
            "code": STATUS_NONEXISTENT_CLAUSE,
            "detail": "계약에 존재하지 않는 조항을 기존 조항처럼 인용했습니다: "
                      + ", ".join(f"제{n}조" for n in unknown),
            "articles": unknown,
        })

    # (2) 인용 진위 — 원문 칸에 계약서에 없는 문장이 들어갔는가.
    #     사용자가 설명한 사실관계를 계약 문구처럼 옮겨 적은 경우도 여기서 잡힌다
    #     (지시 항목 5) — 계약 원문에 없으면 원문이 아니다.
    quote = str(cr.get("original_text") or "").strip()
    if quote and _is_quote_claim(quote) and not index.quote_exists(quote):
        violations.append({
            "code": STATUS_FAKE_QUOTE,
            "detail": "원문으로 표시된 문장이 계약서에 존재하지 않습니다 "
                      f"(일치율 {index.quote_similarity(quote):.0%}).",
            "quote": quote[:200],
        })

    # (3) 수정 대상 위치
    ri = cr.get("redline_instruction")
    if isinstance(ri, dict):
        location = str(ri.get("edit_location") or "")
        is_new = str(ri.get("edit_type") or "") == "new_clause" or "신설" in location
        if location and not is_new:
            bad = [n for n in _contract_article_refs(location) if not index.has_article(n)]
            if bad:
                violations.append({
                    "code": STATUS_NONEXISTENT_CLAUSE,
                    "detail": "수정하려는 위치가 계약에 없습니다: "
                              + ", ".join(f"제{n}조" for n in bad),
                    "articles": bad,
                })
    return violations


# ── 정정 ────────────────────────────────────────────────────────────────────

def _strip_bad_refs(value: str, unknown: list[str]) -> str:
    """존재하지 않는 조항 번호 참조를 문장에서 걷어낸다.

    번호를 다른 번호로 바꾸지 않는다 — 바꿔 적으면 그것도 지어낸 참조다.
    "[제12조] … 관련 조항" 처럼 번호만으로 조립된 라벨은 통째로 뺀다.
    """
    out = str(value or "")
    for bad in unknown:
        out = re.sub(rf"\[\s*제\s*0*{bad}\s*조[^\]]*\]\s*[^\n]{{0,20}}관련\s*조항", "", out)
        out = re.sub(rf"\[\s*제\s*0*{bad}\s*조[^\]]*\]", "", out)
        out = re.sub(
            rf"제\s*0*{bad}\s*조(?:\s*제\s*\d{{1,3}}\s*항)?(?:\s*제\s*\d{{1,3}}\s*호)?",
            "", out,
        )
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" —-–·|,").strip()


def prune_reference_lists(
    cr: dict[str, Any], unknown: list[str], *, replacement: str = "",
) -> list[str]:
    """목록형 참조에서 존재하지 않는 조항 항목을 걷어낸다(2차 보정 1항).

    `replacement` 가 주어지면(신설로 정정된 경우) 그 번호로 대체하고, 아니면
    항목을 제거한다. 걷어낸 원래 값을 돌려준다.
    """
    removed: list[str] = []
    for field in _LIST_REFERENCE_FIELDS:
        value = cr.get(field)
        if not isinstance(value, list) or not value:
            continue
        kept: list[Any] = []
        for entry in value:
            text = str(entry or "")
            refs = _contract_article_refs(text)
            if refs and any(r in unknown for r in refs):
                removed.append(text)
                if replacement:
                    kept.append(f"{replacement} 신설")
                continue
            kept.append(entry)
        # 중복 제거 — 같은 신설 번호가 여러 번 들어가지 않게.
        deduped: list[Any] = []
        for entry in kept:
            if entry not in deduped:
                deduped.append(entry)
        cr[field] = deduped
    if removed:
        cr["pruned_clause_references"] = sorted(set(removed))
    return removed


#: finding 이 어느 조항에 걸려 있는지 읽어낼 때 쓰는 표시 필드(우선순위 순).
_ANCHOR_FIELDS = ("article_number", "display_path", "clause_title", "clause_id")

_RX_ANCHOR_IN_ID = re.compile(r"KR-(\d{1,3})")


def anchored_article(cr: dict[str, Any]) -> str:
    """이 finding 이 '기존 조항' 으로 걸어 둔 조 번호. 없으면 빈 문자열."""
    raw = str(cr.get("article_number") or "").strip()
    if raw.isdigit():
        return str(int(raw))
    for field in ("display_path", "clause_title"):
        value = str(cr.get(field) or "")
        if "신설" in value:
            return ""
        refs = _contract_article_refs(value)
        if len(refs) == 1:
            return refs[0]
    m = _RX_ANCHOR_IN_ID.search(str(cr.get("clause_id") or ""))
    return m.group(1) if m else ""


def enforce_semantic_anchor(
    clause_results: list[dict[str, Any]],
    index: ClauseIndex,
) -> dict[str, Any]:
    """번호는 실재하지만 그 조항이 finding 과 다른 이야기를 하면 연결을 끊는다.

    2026-09-15 지시 2항 —
      "조항번호가 실제로 존재하더라도, 해당 조항의 legal effect 가 finding 과
       다르면 SEMANTIC_ANCHOR_MISMATCH 로 결과 생성 금지."
    3항 —
      "적절한 기존 조항이 없으면 억지로 아무 조항에 연결하지 말고 '해당 조항
       없음 — 신설 필요' 로만 처리."

    **다른 조항으로 갈아 끼우지 않는다.** 비슷한 제목·효과의 조항을 찾아
    옮겨 붙이는 것은 근거 없는 추측이고, 1차 지시 항목 9 가 금지한 행위다.
    연결만 끊고, 부재를 지적하는 항목이면 신설로 돌린다.

    과차단을 막는 안전장치 세 가지
      · 양쪽 모두 법률효과 태그가 **붙었을 때만** 비교한다(태그 없음 = 의견 없음).
      · finding 이 그 조항의 문언을 실제로 인용하고 있으면 연결이 옳은 것이므로
        태그가 어긋나도 건드리지 않는다.
      · 구조 미확정(`structure_uncertain`)이면 아무것도 판단하지 않는다.
    """
    from runtime.review.clause_topic import (
        TOPIC_OTHER,
        classify_clause_topic,
        is_topic_compatible,
    )
    from runtime.review.legal_effect_taxonomy import (
        effects_overlap,
        infer_legal_effects,
    )

    report: dict[str, Any] = {"status": "", "detail": "", "mismatches": []}
    if index.structure_uncertain:
        return report

    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        if bool(cr.get("is_new_clause")) or bool(cr.get("clause_reference_unresolved")):
            continue
        # 계약 원문을 직접 찾아 붙인 체크리스트·결정론적 rule 은 연결이
        # 구조적으로 옳다. 지적 내용과 조항의 법률효과가 다른 것이 정상인
        # 경우도 많다 — 예: 해지 비용 지적은 '광고료 납부' 조항에 붙는다.
        if bool(cr.get("is_ad_media_checklist")) or bool(cr.get("is_common_legal_risk")):
            continue
        # 건설 체크리스트도 같다 — 계약 원문의 **조 제목**으로 자리를 잡는다
        # (2026-09-21 지시 5항). 한 항목이 대금·공기·책임에 동시에 걸치므로
        # 단일 법률효과 태그로 대조하면 정당한 연결까지 끊긴다. 실측:
        # 보증·유보금 지적(CWC-10)이 제16조(보증)에 제대로 붙었는데도
        # "조항 위치 확인 필요" 로 나갔다.
        if bool(cr.get("is_construction_checklist")):
            continue
        number = anchored_article(cr)
        if not number or not index.has_article(number):
            continue
        article = index.articles[number]
        clause_effects = infer_legal_effects(article.exact_text)
        finding_text = "\n".join(
            str(cr.get(k) or "")
            for k in ("issue_title", "problem", "rewrite_reason", "suggested_rewrite")
        )
        finding_effects = infer_legal_effects(finding_text)

        if clause_effects and finding_effects:
            if effects_overlap(clause_effects, finding_effects):
                continue
            axis = "legal_effect"
        else:
            # 한쪽이라도 효과 태그가 비면 주제 축으로 본다. 조항 전문과 지적
            # 전문을 비교하는 것이므로 `classify_clause_topic` 의 본래 용도에
            # 맞는다. 둘 다 판정이 서고 서로 맞지 않을 때만 어긋난 것으로 본다.
            clause_topic = classify_clause_topic(
                title=article.title, text=article.exact_text,
            )
            finding_topic = classify_clause_topic(title=None, text=finding_text)
            if clause_topic == TOPIC_OTHER or finding_topic == TOPIC_OTHER:
                continue
            if is_topic_compatible(
                clause_topic=clause_topic, rewrite_topics={finding_topic},
            ):
                continue
            axis = "clause_topic"
            clause_effects = clause_effects or [clause_topic]
            finding_effects = finding_effects or [finding_topic]

        # 그 조항의 문언을 실제로 인용하고 있으면 연결은 옳다.
        quote = str(cr.get("original_text") or "").strip()
        if quote and _is_quote_claim(quote):
            from runtime.review.clause_index import _norm as _norm_quote
            if _norm_quote(quote) and _norm_quote(quote) in _norm_quote(article.exact_text):
                continue

        entry = {
            "clause_id": str(cr.get("clause_id") or ""),
            "anchored_article": f"제{number}조",
            "anchored_title": article.title,
            "clause_effects": clause_effects,
            "finding_effects": finding_effects,
            "axis": axis,
            "issue_title": str(cr.get("issue_title") or "")[:90],
        }
        report["mismatches"].append(entry)

        # **신설로 돌리지 않는다.** 여기서 확인된 사실은 "이 연결이 틀렸다" 뿐이다.
        # 그 내용을 규정한 조항이 계약 어딘가에 실재할 수 있고(이 계약의 조 번호는
        # 전부 실재한다), 그것을 확인하지 않은 채 새 조항을 만들라고 하면 있는
        # 조항을 두고 중복 조항을 넣으라는 지시가 된다. 실측: 영문 라이선스 계약의
        # 지연이자 지적이 Article 1(License)에 잘못 걸려 있었는데, 신설로 돌리자
        # 대금 조항이 실재하는데도 "제10조 신설" 을 권고하게 됐다.
        # 신설 처리는 **조항 자체가 없을 때**(존재 검증 게이트)의 몫이다.
        #
        # **표시 경로와 목록만** 손댄다. 본문(problem/이유/문안)은 건드리지 않는다 —
        # 그 번호는 실재하는 조항이므로 본문에서 언급하는 것 자체는 날조가 아니고,
        # 여기서 본문을 고치면 다른 게이트의 판단 근거가 흔들린다(실측: 본문을
        # 수정하자 "제안 문안이 원문 사본인가" 판정이 깨져 정상 finding 이
        # 정합성 게이트에서 삭제됐다). 제거해야 하는 것은 **연결**이다.
        for field in _REFERENCE_FIELDS:
            value = str(cr.get(field) or "")
            if value:
                cr[field] = _strip_bad_refs(value, [number])
        prune_reference_lists(cr, [number])
        cr["article_number"] = None
        cr["clause_title"] = "조항 위치 확인 필요"
        cr["display_path"] = "조항 위치 확인 필요"
        cr["clause_reference_unresolved"] = True
        cr["semantic_anchor_mismatch"] = entry
        cr["clause_reference_unresolved_reason"] = (
            f"이 지적이 걸려 있던 제{number}조({article.title})는 다른 내용을 규정하고 "
            f"있습니다(그 조항의 법률효과: {', '.join(clause_effects)} / 이 지적: "
            f"{', '.join(finding_effects)}). 맞는 조항을 임의로 추정하지 않고 연결만 "
            "해제했습니다 — 해당 내용을 규정한 조항을 확인한 뒤 적용하십시오."
        )
        entry["remediation"] = "anchor_detached"

    if report["mismatches"]:
        report["status"] = STATUS_SEMANTIC_ANCHOR_MISMATCH
        report["detail"] = (
            f"조항의 법률효과와 맞지 않는 연결 {len(report['mismatches'])}건을 해제했습니다: "
            + ", ".join(
                f"{m['clause_id']}({m['anchored_article']})"
                for m in report["mismatches"][:6]
            )
        )
    return report


def scrub_meta_references(meta: dict[str, Any], index: ClauseIndex) -> list[str]:
    """meta 의 조항 매핑 표에서도 존재하지 않는 조항을 걷어낸다(2차 보정 1항).

    사용자 요청 매핑·필수 검토 대상은 UI 가 그대로 표로 그리므로, 여기 남은
    번호는 화면에 '기존 조항' 처럼 보인다.
    """
    if index.structure_uncertain or not isinstance(meta, dict):
        return []
    removed: list[str] = []

    def _clean(value: Any) -> Any:
        if isinstance(value, str):
            bad = [n for n in _contract_article_refs(value) if not index.has_article(n)]
            if not bad:
                return value
            removed.append(value[:80])
            return _strip_bad_refs(value, bad)
        if isinstance(value, list):
            return [_clean(v) for v in value]
        if isinstance(value, dict):
            return {k: _clean(v) for k, v in value.items()}
        return value

    for key in (
        "user_focus_mapping_table", "user_focus_clause_ids", "user_focus_mapping_debug",
        "mandatory_review_targets",
    ):
        if key in meta:
            meta[key] = _clean(meta[key])
    return sorted(set(removed))


def _renumber_to_new_clause(
    cr: dict[str, Any], index: ClauseIndex, unknown: list[str], new_number: str,
) -> None:
    """존재하지 않는 번호 참조를 '신설 제N조' 형식으로 바꾼다(지시 항목 2·6)."""
    label = f"제{new_number}조"

    for field in _REFERENCE_FIELDS + _BODY_FIELDS:
        value = str(cr.get(field) or "")
        if value:
            cr[field] = _strip_bad_refs(value, unknown)
    prune_reference_lists(cr, unknown, replacement=label)

    title = _strip_bad_refs(str(cr.get("issue_title") or ""), unknown)
    cr["issue_title"] = f"[신설 {label}] {title}" if title else f"[신설 {label}] 조항 신설 필요"
    cr["clause_title"] = f"해당 조항 없음 — {label} 신설 필요"
    cr["display_path"] = f"{label} 신설"
    # 존재하지 않는 조항에는 원문이 없다. 지어낸 문장을 남겨두지 않는다.
    # 신설로 돌리기 전에, 권고 칸이 **원래 조항 원문의 메아리**면 함께 비운다.
    # 일부 경로는 recommendation_text 에 대상 조항 전문을 그대로 담는다. 연결을
    # 끊은 뒤에도 그 문장이 남아 있으면 이후 게이트가 그것을 "제안 문안" 으로
    # 읽고, 원문이 사라진 탓에 사본 판정도 못 해 정상 finding 을 지운다
    # (실측: 영문 라이선스 계약의 지연이자 지적이 이 경로로 삭제됐다).
    _prev_original = "".join(str(cr.get("original_text") or "").split())
    if len(_prev_original) >= 40:
        for _key in ("recommendation_text", "proposed_revision"):
            _val = "".join(str(cr.get(_key) or "").split())
            if len(_val) >= 40 and (_val in _prev_original or _prev_original in _val):
                cr[_key] = None
    cr["original_text"] = ABSENT_CLAUSE_MARKER
    cr["original_text_absent_reason"] = "계약에 해당 조항이 없어 인용할 원문이 없습니다."
    cr["is_new_clause"] = True
    cr["new_clause_number"] = new_number

    anchor = index.max_article()
    ri = cr.get("redline_instruction")
    if not isinstance(ri, dict):
        ri = {}
    ri["edit_type"] = "new_clause"
    ri["edit_location"] = (
        f"제{anchor}조 뒤에 {label} 신설" if anchor else f"{label} 신설"
    )
    ri["target_text"] = ""
    # 문안 자체에도 지어낸 번호가 들어 있다 — 실측: replacement_text 가
    # "[제12조] 계약의 해제 및 해지 관련 조항 …" 로 시작했다. 여기를 안 고치면
    # 화면에서는 신설로 보이는데 Word 파일에는 없는 번호가 그대로 들어간다.
    for key in ("replacement_text", "final_clause_text", "reason"):
        if isinstance(ri.get(key), str) and ri[key].strip():
            ri[key] = _strip_bad_refs(ri[key], unknown)
    cr["redline_instruction"] = ri


def enforce_existence_gate(
    clause_results: list[dict[str, Any]],
    index: ClauseIndex,
) -> dict[str, Any]:
    """존재하지 않는 조항·문구를 정정하거나 제거한다.

    돌려주는 리포트: {"status", "detail", "violations", "renumbered", "removed",
    "quotes_cleared"}.
    """
    report: dict[str, Any] = {
        "status": "",
        "detail": "",
        "violations": [],
        "renumbered": [],
        "removed": [],
        "quotes_cleared": [],
        "structure_uncertain": index.structure_uncertain,
    }
    if index.structure_uncertain:
        report["detail"] = "; ".join(index.uncertainty_reasons)
        return report

    # 신설 번호는 순서대로 나눠 준다 — 두 항목이 같은 번호를 주장하면 안 된다.
    next_number = index.max_article()

    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue

        violations = verify_finding(cr, index)
        if not violations:
            kept.append(cr)
            continue

        entry = {
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            "codes": [v["code"] for v in violations],
            "details": [v["detail"] for v in violations],
        }
        report["violations"].append(entry)

        # 가짜 인용만 문제라면 그 칸만 비운다 — 지적 자체는 살아 있다.
        fake_only = all(v["code"] == STATUS_FAKE_QUOTE for v in violations)
        if fake_only:
            # 부재를 지적하는 항목이면 빈칸이 아니라 "없다" 고 적는다(지시 항목 6).
            # 빈칸으로 두면 출력 필터가 항목 자체를 버려 지적이 사라진다.
            cr["original_text"] = ABSENT_CLAUSE_MARKER if _absence_intent(cr) else ""
            cr["original_text_absent_reason"] = (
                "표시된 원문이 계약서에서 확인되지 않아 제외했습니다."
            )
            cr["fake_quote_removed"] = True
            entry["remediation"] = "quote_cleared"
            report["quotes_cleared"].append(entry["clause_id"])
            kept.append(cr)
            continue

        unknown = sorted(
            {a for v in violations for a in v.get("articles", [])},
            key=lambda x: int(x),
        )
        if unknown and _absence_intent(cr):
            next_number += 1
            _renumber_to_new_clause(cr, index, unknown, str(next_number))
            entry["remediation"] = "converted_to_new_clause"
            entry["new_clause_number"] = str(next_number)
            report["renumbered"].append(entry)
            kept.append(cr)
            continue

        entry["remediation"] = "removed"
        report["removed"].append(entry)

    clause_results[:] = kept

    if report["violations"]:
        report["status"] = (
            STATUS_NONEXISTENT_CLAUSE if (report["renumbered"] or report["removed"])
            else STATUS_FAKE_QUOTE
        )
        report["detail"] = (
            f"존재 검증 위반 {len(report['violations'])}건 처리"
            f"(신설로 정정 {len(report['renumbered'])}건, 삭제 {len(report['removed'])}건, "
            f"가짜 인용 제거 {len(report['quotes_cleared'])}건): "
            + "; ".join(
                f"{v['clause_id']}({','.join(v['codes'])})" for v in report["violations"][:5]
            )
        )
    return report


# ── 최종 전수검증 (지시 항목 7) ─────────────────────────────────────────────

def audit_final_references(
    clause_results: list[dict[str, Any]],
    index: ClauseIndex,
) -> dict[str, Any]:
    """HIGH/MEDIUM 전부에 대해 네 가지를 다시 확인한다.

        referenced clause exists? / title matches? / quoted text exists? /
        edit target exists?

    여기서 걸리면 앞 단계가 놓쳤다는 뜻이므로 그 항목을 **제거**하고
    `REVIEW_FAILED_HALLUCINATED_REFERENCE` 로 기록한다. 지시는 "결과 생성 금지"
    라고 했는데, 제거가 곧 그 요구의 이행이다 — 지어낸 항목이 결과에 실리지
    않는다. 나머지 정상 항목까지 내주지 않으면 담당자는 아무것도 받지 못하고,
    그것은 이 엔진에서 이미 한 번 실패한 길이다.
    """
    report: dict[str, Any] = {"status": "", "detail": "", "failures": []}
    if index.structure_uncertain:
        return report

    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        tier = str(cr.get("risk_tier") or "").upper()
        if tier not in ("HIGH", "MEDIUM") or bool(cr.get("dedup_suppressed")):
            kept.append(cr)
            continue

        failures: list[str] = []
        if verify_finding(cr, index):
            failures.append("존재하지 않는 조항 또는 원문 인용")

        if not failures:
            kept.append(cr)
            continue

        report["failures"].append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "reasons": failures,
        })

    clause_results[:] = kept
    if report["failures"]:
        report["status"] = STATUS_HALLUCINATED_REFERENCE
        report["detail"] = (
            f"최종 전수검증에서 실재하지 않는 참조 {len(report['failures'])}건을 제거했습니다: "
            + ", ".join(f["clause_id"] for f in report["failures"][:6])
        )
    return report


def enforce_title_consistency(
    clause_results: list[dict[str, Any]],
    index: ClauseIndex,
) -> dict[str, Any]:
    """주장한 조 제목이 원문의 그 조 제목과 다르면 **번호를 떼어낸다**.

    번호는 있는데 그 조가 다른 내용인 경우다. 실측: 콘텐츠 체크리스트 CP-004 가
    "제9조(소유권의 귀속)" 를 가리키는데, 이 계약의 제9조는 "분쟁 해결 및 관할"
    이고 지식재산권은 제5조에 있다. 표준계약서 양식의 번호를 그대로 쓴 결과다.

    **다른 번호로 바꿔 적지 않는다.** 제목이 비슷한 조항을 찾아 갈아 끼우는 것은
    추측이고, 지시 항목 9 가 금지한 바로 그 행위다. 지적 자체는 유효하므로 남기되
    위치를 "확인 필요" 로 표시하고, 그 사실을 리포트에 남긴다.
    """
    report: dict[str, Any] = {"status": "", "detail": "", "unresolved": []}
    if index.structure_uncertain:
        return report

    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        if bool(cr.get("is_new_clause")):
            continue
        wrong: list[str] = []
        for num, title in asserted_titles(cr):
            if index.has_article(num) and not index.title_matches(num, title):
                if num not in wrong:
                    wrong.append(num)
        if not wrong:
            continue

        for field in _REFERENCE_FIELDS + _BODY_FIELDS:
            value = str(cr.get(field) or "")
            if value:
                cr[field] = _strip_bad_refs(value, wrong)
        # [2026-09-15 2차 보정 1항] 표시 경로만 고치면 UI·DOCX 의 "관련 조항" 칸에
        # 그 번호가 그대로 남는다(실측: CP-004 의 related_clauses=["제9조"]).
        prune_reference_lists(cr, wrong)
        cr["article_number"] = None
        cr["clause_title"] = "조항 위치 확인 필요"
        cr["display_path"] = "조항 위치 확인 필요"
        cr["clause_reference_unresolved"] = True
        cr["clause_reference_unresolved_reason"] = (
            "이 지적이 가리키던 조항번호("
            + ", ".join(f"제{n}조" for n in wrong)
            + ")는 이 계약에서 다른 내용을 담고 있습니다. 표준계약서 양식의 번호로 "
            "보이므로 번호를 제거했습니다 — 해당 내용을 규정한 조항을 확인한 뒤 "
            "적용하십시오."
        )
        report["unresolved"].append({
            "clause_id": str(cr.get("clause_id") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            "wrong_articles": [f"제{n}조" for n in wrong],
            "actual_titles": {f"제{n}조": index.title_of(n) for n in wrong},
        })

    if report["unresolved"]:
        report["status"] = STATUS_NONEXISTENT_CLAUSE
        report["detail"] = (
            f"조 제목이 원문과 달라 조항번호를 제거한 항목 {len(report['unresolved'])}건: "
            + ", ".join(u["clause_id"] for u in report["unresolved"][:6])
        )
    return report
