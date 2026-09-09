"""실무 Redline 고도화 — 수정 위치·방식·완성문구를 mandatory 구조로
제공한다(2026-09-04 지시).

아우리봇은 "법무팀이 알아서 고쳐야 하는 검토의견"이 아니라 "계약검토
경험이 없는 사업팀도 그대로 복사해서 수정할 수 있는 수준의 실무
redline"을 제공해야 한다. 모든 HIGH/MEDIUM finding은 다음을 반드시
포함한다:

1. edit_location — 기존 조항 수정인지, 특정 항 말미 추가인지, 특정 조항
   뒤 신설인지, 별도 신설 조항인지.
2. edit_type — replace | insert_after | insert_before | delete | new_clause.
3. final_clause_text — placeholder 없이 그대로 계약서에 넣을 수 있는
   완성된 문장.
4. reason — 초보자도 이해할 수 있는 2~3문장.

조항번호는 계약마다 다르므로, "제2조" 같은 숫자를 하드코딩하지 않는다 —
`clause_extraction.py`가 만든 실제 canonical 구조(ClauseChunk의
article_number/paragraph_number/display_path)에서 매칭되는 조항을 찾아
그 실제 번호를 그대로 쓴다. 매칭되는 조항을 찾지 못하면 위치를 임의로
지어내지 않고 "위치 확인 필요"로 남겨 REVIEW_FAILED_INCOMPLETE_REDLINE
게이트가 걸러내게 한다.
"""
from __future__ import annotations

import re
from typing import Any

EDIT_TYPES = ("replace", "insert_after", "insert_before", "delete", "new_clause")

_CIRCLED_NUMS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def paragraph_marker(n: int) -> str:
    """항 번호를 계약 관용 표기로 변환 — 20 이하는 원문자, 그 이상은
    "제N항" 형태."""
    if 1 <= n <= len(_CIRCLED_NUMS):
        return _CIRCLED_NUMS[n - 1]
    return f"제{n}항"

# 미완성 redline으로 간주하는 신호 — 이 중 하나라도 최종 결과에 남아있으면
# REVIEW_FAILED_INCOMPLETE_REDLINE 대상이다(요청 6, HARD GATE).
_RX_INCOMPLETE_SIGNALS = re.compile(
    r"자동수정\s*보류|수정방향만|계약\s*전체에\s*추가"
    r"|\[실제\s*[^\]]{0,20}\]|\[확인\s*필요\]|\[당사자\]"
    r"|\[\s*[○Oㅇo]\s*\]\s*%?",
)

_LOCATION_UNCERTAIN = "위치 확인 필요 — 원문에서 해당 조항을 특정하지 못함"

#: 특정 조항이 아니라 **계약 전반**에 대한 권고일 때 쓰는 위치 문구.
#: 이런 finding 은 원문에 대응 조항이 없으므로 "교체" 가 아니라 "신설" 이며,
#: 위치는 계약 말미가 된다. 실행 가능한 지시이므로 게이트를 통과한다.
LOCATION_CONTRACT_WIDE_NEW = "본 계약 말미에 신설 (특정 조항 아님 — 계약 전반 사항)"

#: 규칙이 대응 조항을 찾지 못했을 때 original_text 자리에 넣는 자리표시자.
#: 예: "(조건부 자금 관련 조항 전반)", "(해당 조항 없음)". 실제 조문이
#: 아니므로 이것을 "교체 대상 원문" 으로 다루면 안 된다 — 교체할 원문이
#: 없는데 replace 로 만들어지면 edit_location 이 영영 특정되지 않아
#: REVIEW_FAILED_INCOMPLETE_REDLINE 으로 다운로드가 막힌다(2026-09-09 실측:
#: clr_conditional_funding_unclear).
_RX_PLACEHOLDER_ORIGINAL = re.compile(
    r"^\s*[（(][^)）]{0,40}(?:전반|전체|없음|미상|해당\s*조항)[^)）]{0,20}[)）]\s*$"
)


def is_placeholder_original(text: str | None) -> bool:
    """original_text 가 실제 조문이 아니라 자리표시자인지."""
    s = str(text or "").strip()
    if not s:
        return True
    return bool(_RX_PLACEHOLDER_ORIGINAL.match(s))


def strip_placeholder_prefix(text: str | None) -> str:
    """신설 조문에서 선두의 자리표시자 줄을 제거한다.

    수정문안이 "(조건부 자금 관련 조항 전반)\\n\\n[추가 권고]\\n…" 형태로
    자리표시자를 머리에 달고 오는 경우, 신설 조문에 그대로 넣으면 계약서에
    붙여넣을 수 없는 문장이 된다.
    """
    s = str(text or "").strip()
    if not s:
        return ""
    lines = s.split("\n")
    if lines and is_placeholder_original(lines[0]):
        s = "\n".join(lines[1:]).strip()
    return s


def find_article_for_pattern(
    clauses: list[Any] | None, pattern: re.Pattern[str],
) -> dict[str, Any] | None:
    """clauses(ClauseChunk 목록)에서 pattern에 매치되는 조항을 찾아 그
    조항의 article_number/title과, 그 조항 아래 이미 존재하는 항의
    최대 번호(다음 항을 신설할 때 쓸 번호)를 반환한다. 계약마다 조항
    번호가 다르므로 여기서 실제 구조를 조회한다 — 하드코딩하지 않는다."""
    matched_article: str | None = None
    matched_title: str = ""
    for c in (clauses or []):
        text = getattr(c, "text", "") or ""
        article = getattr(c, "article_number", None)
        if article and pattern.search(text):
            matched_article = str(article)
            matched_title = str(getattr(c, "title", "") or "")
            break
    if not matched_article:
        return None
    max_para = 0
    for c in (clauses or []):
        if str(getattr(c, "article_number", None) or "") != matched_article:
            continue
        pn = getattr(c, "paragraph_number", None)
        if pn is not None and str(pn).isdigit():
            max_para = max(max_para, int(str(pn)))
    return {
        "article_number": matched_article,
        "article_title": matched_title,
        "max_paragraph_number": max_para,
    }


def location_insert_after_last_paragraph(loc: dict[str, Any] | None) -> str:
    """해당 조항의 마지막 항 뒤에 새 항을 신설하는 위치 문구를 만든다."""
    if not loc:
        return _LOCATION_UNCERTAIN
    art, title, max_para = loc["article_number"], loc["article_title"], loc["max_paragraph_number"]
    label = f"제{art}조({title})" if title else f"제{art}조"
    if max_para:
        return f"{label} 제{max_para}항 뒤에 제{max_para + 1}항 신설"
    return f"{label} 뒤에 신설"


def location_new_article_after(loc: dict[str, Any] | None, new_article_suffix: str = "의2") -> str:
    """해당 조항 바로 뒤에 별도 신설 조항(예: 제5조의2)을 추가하는 위치
    문구를 만든다."""
    if not loc:
        return _LOCATION_UNCERTAIN
    art, title = loc["article_number"], loc["article_title"]
    label = f"제{art}조({title})" if title else f"제{art}조"
    return f"{label} 뒤에 제{art}조{new_article_suffix} 신설"


def location_replace_paragraph(loc: dict[str, Any] | None, paragraph_number: str | int | None = None) -> str:
    """해당 조항의 특정 항(모르면 조항 전체)을 교체하는 위치 문구."""
    if not loc:
        return _LOCATION_UNCERTAIN
    art, title = loc["article_number"], loc["article_title"]
    label = f"제{art}조({title})" if title else f"제{art}조"
    if paragraph_number:
        return f"{label} 제{paragraph_number}항 교체"
    return f"{label} 교체"


def compose_final_clause_text(
    *, edit_type: str, original_text: str = "", target_text: str = "", replacement_text: str = "",
) -> str:
    """edit_type에 따라 완성된 최종 조문 텍스트를 조합한다. placeholder
    없이 그대로 복사해 계약서에 반영할 수 있는 문장이어야 한다."""
    replacement_text = (replacement_text or "").strip()
    if edit_type == "delete":
        return ""
    if edit_type == "new_clause":
        return replacement_text
    if edit_type == "insert_after":
        original = (original_text or "").rstrip()
        return f"{original}\n{replacement_text}".strip() if original else replacement_text
    if edit_type == "insert_before":
        original = (original_text or "").lstrip()
        return f"{replacement_text}\n{original}".strip() if original else replacement_text
    # replace (기본값)
    if target_text and original_text and target_text in original_text:
        return original_text.replace(target_text, replacement_text, 1)
    return replacement_text


def build_redline_instruction(
    *,
    finding_id: str = "",
    clause_id: str = "",
    severity: str = "",
    edit_location: str,
    edit_type: str,
    target_text: str = "",
    replacement_text: str,
    reason: str,
    original_text: str = "",
) -> dict[str, Any]:
    """요청된 mandatory 구조를 그대로 만든다.

    대응 조항이 없는 **계약 전반 권고**는 여기서 신설(new_clause)로 정규화한다.
    그런 finding 은 original_text 가 자리표시자("(… 전반)")여서 replace 로
    만들어지는데, 교체할 원문이 없으니 edit_location 이 영영
    `_LOCATION_UNCERTAIN` 에 머물러 REVIEW_FAILED_INCOMPLETE_REDLINE 으로
    수정본 다운로드가 통째로 막혔다(2026-09-09 실측). "위치 미상 교체" 보다
    "계약 말미에 신설" 이 사실에도 맞고 실행도 가능하다.
    """
    _loc = str(edit_location or "").strip()
    if (
        (not _loc or _loc == _LOCATION_UNCERTAIN)
        and str(replacement_text or "").strip()
        and is_placeholder_original(original_text)
    ):
        edit_type = "new_clause"
        edit_location = LOCATION_CONTRACT_WIDE_NEW
        replacement_text = strip_placeholder_prefix(replacement_text)
        target_text = ""
        original_text = ""

    final_clause_text = compose_final_clause_text(
        edit_type=edit_type, original_text=original_text,
        target_text=target_text, replacement_text=replacement_text,
    )
    return {
        "finding_id": finding_id,
        "clause_id": clause_id,
        "severity": severity,
        "edit_location": edit_location,
        "edit_type": edit_type,
        "target_text": target_text,
        "replacement_text": replacement_text,
        "final_clause_text": final_clause_text,
        "reason": reason,
    }


def normalize_redline_instruction(instruction: dict[str, Any] | None) -> dict[str, Any] | None:
    """이미 만들어진 instruction 에도 계약 전반 권고 정규화를 적용한다.

    룰이 스스로 만든 instruction 은 그대로 보존되므로(다운로드 경로는 없는
    것만 채운다), `build_redline_instruction()` 안의 정규화만으로는 이미
    `_LOCATION_UNCERTAIN` 으로 저장된 것들을 구제하지 못한다. 게이트 검증
    **직전**에 이 함수를 통과시켜, 대응 조항이 없는 권고를 신설로 바꾼다.

    실제 조문이 있는데 위치만 못 찾은 경우는 손대지 않는다 — 그건 진짜
    미완성이고 게이트가 계속 잡아야 한다.
    """
    if not isinstance(instruction, dict):
        return instruction
    loc = str(instruction.get("edit_location") or "").strip()
    if loc and loc != _LOCATION_UNCERTAIN:
        return instruction
    replacement = str(instruction.get("replacement_text") or "").strip()
    if not replacement:
        return instruction
    original = instruction.get("original_text")
    if original is None:
        original = instruction.get("target_text")
    if not is_placeholder_original(original):
        return instruction

    out = dict(instruction)
    out["edit_type"] = "new_clause"
    out["edit_location"] = LOCATION_CONTRACT_WIDE_NEW
    out["target_text"] = ""
    out["replacement_text"] = strip_placeholder_prefix(replacement)
    out["final_clause_text"] = out["replacement_text"]
    out["normalized_as_contract_wide_new_clause"] = True
    return out


def is_incomplete_redline(instruction: dict[str, Any] | None) -> bool:
    """instruction이 없거나, 위치·문구가 비어있거나, 미완성 신호(자동수정
    보류/placeholder 등)를 포함하면 True — REVIEW_FAILED_INCOMPLETE_REDLINE
    게이트의 판정 기준."""
    if not isinstance(instruction, dict):
        return True
    edit_location = str(instruction.get("edit_location") or "").strip()
    edit_type = str(instruction.get("edit_type") or "").strip()
    final_clause_text = str(instruction.get("final_clause_text") or "").strip()
    replacement_text = str(instruction.get("replacement_text") or "").strip()
    if not edit_location or edit_location == _LOCATION_UNCERTAIN:
        return True
    if edit_type not in EDIT_TYPES:
        return True
    if edit_type != "delete" and not final_clause_text:
        return True
    combined = f"{edit_location} {replacement_text} {final_clause_text}"
    if _RX_INCOMPLETE_SIGNALS.search(combined):
        return True
    return False


def format_redline_display(instruction: dict[str, Any]) -> str:
    """UI/DOCX에 그대로 노출할 4줄 형태 — 요청된 표시 형식."""
    _EDIT_TYPE_LABELS = {
        "replace": "교체", "insert_after": "신설(뒤에 추가)",
        "insert_before": "신설(앞에 추가)", "delete": "삭제", "new_clause": "신설",
    }
    edit_type_label = _EDIT_TYPE_LABELS.get(str(instruction.get("edit_type") or ""), instruction.get("edit_type") or "")
    return (
        f"수정 위치: {instruction.get('edit_location') or ''}\n"
        f"수정 방식: {edit_type_label}\n"
        f"수정 문구: {instruction.get('final_clause_text') or ''}\n"
        f"수정 이유: {instruction.get('reason') or ''}"
    )
