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

#: 조항번호가 실릴 수 있는 표시 필드.
_REFERENCE_FIELDS = ("issue_title", "clause_title", "display_path")
#: 본문 성격의 필드. 여기 있는 번호도 담당자에게는 지시로 읽힌다.
_BODY_FIELDS = ("problem", "rewrite_reason", "legal_business_reason",
                "suggested_rewrite", "proposed_revision", "recommendation_text",
                "negotiation_position")

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


def _text_of(cr: dict[str, Any], keys: tuple[str, ...]) -> str:
    return "\n".join(str(cr.get(k) or "") for k in keys)


def _contract_article_refs(value: str) -> list[str]:
    """계약 조항 참조만 추린다(법령 인용 제외)."""
    out: list[str] = []
    text = str(value or "")
    for m in _RX_ARTICLE_REF.finditer(text):
        before = text[max(0, m.start() - 20): m.start()]
        if _RX_STATUTE_BEFORE.search(before.rstrip()):
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
    for field in (*_REFERENCE_FIELDS, *_BODY_FIELDS):
        value = str(cr.get(field) or "")
        if not value:
            continue
        for m in _RX_ARTICLE_REF.finditer(value):
            before = value[max(0, m.start() - 20): m.start()]
            if _RX_STATUTE_BEFORE.search(before.rstrip()):
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


def _renumber_to_new_clause(
    cr: dict[str, Any], index: ClauseIndex, unknown: list[str], new_number: str,
) -> None:
    """존재하지 않는 번호 참조를 '신설 제N조' 형식으로 바꾼다(지시 항목 2·6)."""
    label = f"제{new_number}조"

    for field in _REFERENCE_FIELDS + _BODY_FIELDS:
        value = str(cr.get(field) or "")
        if value:
            cr[field] = _strip_bad_refs(value, unknown)

    title = _strip_bad_refs(str(cr.get("issue_title") or ""), unknown)
    cr["issue_title"] = f"[신설 {label}] {title}" if title else f"[신설 {label}] 조항 신설 필요"
    cr["clause_title"] = f"해당 조항 없음 — {label} 신설 필요"
    cr["display_path"] = f"{label} 신설"
    # 존재하지 않는 조항에는 원문이 없다. 지어낸 문장을 남겨두지 않는다.
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
