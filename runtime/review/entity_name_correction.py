"""계약 당사자 법인명 정정 — 브랜드·그룹명은 계약 당사자가 될 수 없다.

2026-09-29 지시
───────────────
  · 알로소는 주식회사 시디즈의 브랜드다. "주식회사 알로소" → "주식회사 시디즈".
  · 슬로우는 주식회사 일룸의 브랜드다. "주식회사 슬로우" → "주식회사 일룸".
  · 데스커도 주식회사 일룸의 브랜드다. "주식회사 데스커" → "주식회사 일룸".
  · 퍼시스그룹·FURSYS GROUP 은 법적 엔터티가 아니다. 당사자로 쓰였으면
    실제 계약 주체 법인("주식회사 퍼시스" 등)으로 고친다.

계약의 권리의무는 권리능력이 있는 법인에 귀속된다. 브랜드나 그룹 명칭을
당사자로 적으면 누가 채무를 지고 누가 청구하는지가 문언상 특정되지 않고,
분쟁 시 당사자 표시 정정부터 다투게 된다. 그래서 이 정정은 협상 사항이
아니라 **서명 전에 반드시 고칠 오기**로 다룬다.

무엇을 고치지 않는가
──────────────────
브랜드명 자체는 틀린 말이 아니다 — "알로소 매장", "슬로우 매트리스"처럼 상품·
매장을 가리키면 그대로 둔다. 법인격 표기(주식회사·㈜·Inc. 등)가 붙었거나
당사자 정의("(이하 ...)") 자리에 쓰였을 때만 고친다. 그룹명도 "퍼시스그룹
계열사"처럼 집단을 묘사하는 말은 그대로 둔다.

법인명·브랜드 목록은 `group_entities` 가 단일 출처다. 여기에는 **어떻게
찾아서 고치는가**만 둔다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from runtime.review.group_entities import (
    DEFAULT_GROUP_PARTY_KEY,
    GROUP_ENTITIES,
    GROUP_NAMES_EN,
    GROUP_NAMES_KO,
    GroupEntity,
    entity_by_key,
    resolve_entity,
)

_CORP_KO = r"(?:주식회사|㈜|\(\s*주\s*\))"
_CORP_EN = r"(?:,?\s*(?:Co\.?\s*,?\s*Ltd\.?|Inc\.?(?![A-Za-z])|Corp(?:oration)?\.?|Limited|Ltd\.?))"
#: 앞뒤가 이어진 낱말이면 다른 이름이다("슬로우베드"는 "슬로우"가 아니다).
_NO_WORD_BEFORE = r"(?<![가-힣A-Za-z0-9])"
_NO_WORD_AFTER = (
    r"(?=$|[^가-힣A-Za-z0-9]"
    # 조사는 이름의 일부가 아니다 — "주식회사 슬로우는" 도 잡는다.
    r"|(?:으로|에게|은|는|이|가|을|를|과|와|의|에|로|도)(?![가-힣]))"
)
#: 당사자 정의 자리 — `알로소(이하 "갑")`.
_PARTY_DEF = r"(?=\s*\(\s*이하)"
#: 그룹명이 집단을 묘사하는 경우 — 법인 자리가 아니므로 고치지 않는다.
_GROUP_DESCRIPTIVE = (
    r"(?!\s*(?:계열|소속|사|내|전체|차원|임직원|각\s*사|관계|의\s*계열|브랜드))"
)
_GROUP_DESCRIPTIVE_EN = (
    r"(?!\s+(?:affiliates?|companies|members?|entities|brands?)\b)"
)

#: AI 검토 프롬프트에 넣는 원칙. 결정적 정정(아래)과 같은 내용을 AI 에게도
#: 알려, AI 가 만든 수정문안이 틀린 법인명을 되살리지 않게 한다.
LEGAL_NAME_PROMPT_KO = (
    "당사자 법인명: 브랜드와 그룹명은 법인이 아니므로 계약 당사자가 될 수 없다. "
    "알로소는 주식회사 시디즈의 브랜드이고('주식회사 알로소'는 틀린 표현), 슬로우와 데스커는 "
    "주식회사 일룸의 브랜드다('주식회사 슬로우'·'주식회사 데스커'는 틀린 표현). "
    "퍼시스그룹·FURSYS GROUP 은 "
    "법적 엔터티가 아니므로 당사자로 쓰였으면 실제 계약 주체 법인(예: 주식회사 퍼시스)으로 "
    "고친다. 수정문안에는 항상 정확한 법인명을 쓴다."
)
LEGAL_NAME_PROMPT_EN = (
    "Party legal names: a brand or a group name is not a legal entity and cannot be a party. "
    "ALLOSO is a brand of Sidiz Inc.; SLOU and DESKER are brands of Iloom Inc.; 'FURSYS GROUP' is not a "
    "legal entity — replace it with the actual contracting company (e.g. Fursys Inc.). "
    "Always use the correct legal entity name in proposed language."
)

KIND_BRAND = "brand_as_company"
KIND_GROUP = "group_as_party"


@dataclass(frozen=True)
class NameCorrectionRule:
    kind: str
    wrong_label: str
    pattern: re.Pattern[str]
    #: 브랜드 규칙은 고정 법인, 그룹 규칙은 None(계약 주체를 문맥에서 정한다).
    entity_key: str | None
    english: bool = False


@dataclass(frozen=True)
class NameHit:
    rule: NameCorrectionRule
    start: int
    end: int
    wrong: str
    correct: str


def _alt(names: tuple[str, ...]) -> str:
    parts = sorted({re.escape(n).replace(r"\ ", r"\s*") for n in names if n}, key=len, reverse=True)
    return "(?:" + "|".join(parts) + ")"


def _build_rules() -> tuple[NameCorrectionRule, ...]:
    rules: list[NameCorrectionRule] = []
    for e in GROUP_ENTITIES:
        # 브랜드마다 규칙을 따로 둔다 — 메시지에 실제로 쓰인 브랜드를 적는다
        # (일룸은 슬로우·데스커 두 브랜드를 가진다).
        for brand in (e.brands if e.legal_name_ko else ()):
            b = _alt((brand,))
            rx = re.compile(
                rf"{_CORP_KO}\s*{b}{_NO_WORD_AFTER}"          # 주식회사 알로소
                rf"|{_NO_WORD_BEFORE}{b}\s*{_CORP_KO}"         # 알로소 주식회사
                rf"|{_NO_WORD_BEFORE}{b}{_NO_WORD_AFTER}{_PARTY_DEF}"  # 알로소(이하 "갑")
            )
            rules.append(NameCorrectionRule(KIND_BRAND, brand, rx, e.key))
        for brand in (e.brands_en if e.legal_name_en else ()):
            b = _alt((brand,))
            rx = re.compile(rf"\b{b}{_CORP_EN}", re.IGNORECASE)
            rules.append(NameCorrectionRule(KIND_BRAND, brand, rx, e.key, english=True))
    g = _alt(GROUP_NAMES_KO)
    rules.append(NameCorrectionRule(
        KIND_GROUP, GROUP_NAMES_KO[0],
        re.compile(
            rf"(?:{_CORP_KO}\s*)?{g}(?:\s*{_CORP_KO})?{_GROUP_DESCRIPTIVE}"
        ),
        None,
    ))
    ge = _alt(GROUP_NAMES_EN)
    rules.append(NameCorrectionRule(
        KIND_GROUP, GROUP_NAMES_EN[0],
        re.compile(rf"\b{ge}\b{_CORP_EN}?{_GROUP_DESCRIPTIVE_EN}", re.IGNORECASE),
        None, english=True,
    ))
    return tuple(rules)


RULES: tuple[NameCorrectionRule, ...] = _build_rules()


def group_party_entity(entity: str | None = None) -> GroupEntity:
    """그룹명이 당사자로 쓰였을 때 대신 적을 법인.

    검토 요청의 계열사가 법인명을 알고 있으면 그 법인, 아니면 기본값(퍼시스).
    """
    named = resolve_entity(entity)
    if named is not None and named.legal_name_ko:
        return named
    fallback = entity_by_key(DEFAULT_GROUP_PARTY_KEY)
    assert fallback is not None
    return fallback


def _correct_name(rule: NameCorrectionRule, entity: str | None) -> str:
    target = entity_by_key(rule.entity_key) if rule.entity_key else group_party_entity(entity)
    assert target is not None
    return target.legal_name_en if rule.english else target.legal_name_ko


def find_name_hits(text: str | None, *, entity: str | None = None) -> list[NameHit]:
    """본문에서 고쳐야 할 법인명 표기를 앞에서부터 겹치지 않게 찾는다."""
    body = str(text or "")
    hits: list[NameHit] = []
    for rule in RULES:
        for m in rule.pattern.finditer(body):
            wrong = m.group(0)
            if not wrong.strip():
                continue
            hits.append(NameHit(rule, m.start(), m.end(), wrong, _correct_name(rule, entity)))
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    out: list[NameHit] = []
    last_end = -1
    for h in hits:
        if h.start >= last_end:
            out.append(h)
            last_end = h.end
    return out


#: 받침 유무로 갈리는 조사 — (받침 있을 때, 없을 때). 긴 것부터 본다.
_PARTICLES: tuple[tuple[str, str], ...] = (
    ("으로", "로"), ("은", "는"), ("이", "가"), ("을", "를"), ("과", "와"),
)


def _has_batchim(word: str) -> bool | None:
    last = word.rstrip()[-1:] if word.strip() else ""
    if not ("가" <= last <= "힣"):
        return None
    return (ord(last) - 0xAC00) % 28 != 0


def _eun(word: str) -> str:
    """'은/는' — 영문 등 한글이 아니면 '는'."""
    return "은" if _has_batchim(word) else "는"


def _ro(word: str) -> str:
    """'로/으로' — 받침이 없거나 ㄹ 받침이면 '로'."""
    return "으로" if _has_batchim(word) and not _is_rieul_final(word) else "로"


def _is_rieul_final(word: str) -> bool:
    last = word.rstrip()[-1:]
    return "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 == 8


def _fix_particle(correct: str, following: str) -> tuple[str, int]:
    """바꾼 이름 뒤에 붙은 조사를 새 이름의 받침에 맞춘다.

    "퍼시스그룹과" → "주식회사 퍼시스와", "주식회사 슬로우는" → "주식회사 일룸은".
    돌려주는 값은 (새 조사, 원문에서 소비한 길이).
    """
    batchim = _has_batchim(correct)
    if batchim is None:
        return "", 0
    for with_b, without_b in _PARTICLES:
        for cand in (with_b, without_b):
            if not following.startswith(cand):
                continue
            nxt = following[len(cand):len(cand) + 1]
            # "이하"·"이 계약"처럼 조사가 아닌 낱말의 첫 글자는 건드리지 않는다.
            if cand == "이" and nxt and "가" <= nxt <= "힣":
                return "", 0
            if with_b == "으로":
                use = "로" if (not batchim or _is_rieul_final(correct)) else "으로"
            else:
                use = with_b if batchim else without_b
            return use, len(cand)
    return "", 0


def correct_entity_names(text: str | None, *, entity: str | None = None) -> str:
    """틀린 법인명 표기를 정확한 법적 당사자 명칭으로 바꾼 본문."""
    body = str(text or "")
    parts: list[str] = []
    pos = 0
    for h in find_name_hits(body, entity=entity):
        if h.start < pos:
            continue
        parts.append(body[pos:h.start])
        parts.append(h.correct)
        particle, used = _fix_particle(h.correct, body[h.end:h.end + 3])
        parts.append(particle)
        pos = h.end + used
    parts.append(body[pos:])
    return "".join(parts)


def _problem_for(hits: list[NameHit], entity: str | None) -> tuple[str, str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for h in hits:
        key = (re.sub(r"\s+", " ", h.wrong.strip()), h.correct)
        if key in seen:
            continue
        seen.add(key)
        if h.rule.kind == KIND_BRAND:
            owner = entity_by_key(h.rule.entity_key or "")
            owner_name = owner.legal_name_ko if owner else h.correct
            topic = h.rule.wrong_label + ("은" if _has_batchim(h.rule.wrong_label) else "는")
            lines.append(
                f"'{key[0]}'{_eun(key[0])} 틀린 표현입니다. {topic} {owner_name}의 "
                f"브랜드이며 법인이 아닙니다 → '{h.correct}'{_ro(h.correct)} 고칩니다."
            )
        else:
            lines.append(
                f"'{key[0]}'{_eun(key[0])} 법적 엔터티가 아닙니다. 계약 당사자는 실제 법인이어야 "
                f"하므로 '{h.correct}'{_ro(h.correct)} 고칩니다."
            )
    problem = " ".join(lines)
    reason = (
        "계약상 권리의무는 권리능력 있는 법인에 귀속됩니다. 브랜드나 그룹 명칭을 "
        "당사자로 적으면 채무자·청구권자가 문언상 특정되지 않아, 이행 청구·해지·"
        "소송 단계에서 당사자 표시 정정부터 다투게 됩니다. 서명 전에 등기상 "
        "법인명으로 바로잡아야 합니다."
    )
    if any(h.rule.kind == KIND_GROUP for h in hits):
        target = group_party_entity(entity)
        reason += (
            f" 그룹 명칭은 이 검토의 계약 주체({target.legal_name_ko}){_ro(target.legal_name_ko)} 바꾸었습니다. "
            "실제로 다른 계열사가 계약하는 경우 그 계열사의 법인명으로 바꾸십시오."
        )
    return problem, reason


def _letters(n: int) -> str:
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(ord("a") + r) + out
    return out


def _clause_attr(clause: Any, name: str) -> str:
    if isinstance(clause, dict):
        return str(clause.get(name) or "")
    return str(getattr(clause, name, "") or "")


def _finding(
    *, clause_id: str, title: str, display_path: str, article: str, paragraph: str,
    original: str, revised: str, hits: list[NameHit], entity: str | None,
) -> dict[str, Any]:
    problem, reason = _problem_for(hits, entity)
    # 위치를 제목에 넣는다 — output_filter 는 같은 issue_title 을 한 건으로
    # 병합하는데, 오기는 전문·서명란마다 따로 고쳐야 한다.
    title_label = f"계약 당사자 법인명 오기 — {display_path or title}"
    return {
        "clause_id": f"ENTITY_NAME__{clause_id}" if clause_id else "ENTITY_NAME",
        "clause_title": title,
        "display_path": display_path or title,
        "article_number": article,
        "paragraph_number": paragraph,
        "original_text": original,
        "risk_tier": "MEDIUM",
        "severity": "MEDIUM",
        "problem": problem,
        "rewrite_reason": problem,
        "legal_business_reason": reason,
        "suggested_rewrite": revised,
        "recommendation_text": revised,
        "negotiation_position": "서명 전 필수 정정(오기 수정 — 협상 대상 아님)",
        "negotiation_strategy": "상대방에게 오기 정정으로 통지하고 정정본으로 서명한다.",
        "confidence": 0.95,
        # 원문을 regex 로 직접 확인한 실존 오기다 — 계약유형·주제 호환성으로
        # 강등하는 게이트들이 이 finding 을 건드리지 않게 한다.
        "is_common_legal_risk": True,
        "is_entity_name_correction": True,
        "entity_name_corrections": [
            {"wrong": h.wrong.strip(), "correct": h.correct, "kind": h.rule.kind}
            for h in hits
        ],
        "detected_issue_list": [{"issue_title": title_label}],
    }


def build_name_correction_findings(
    clauses: list[Any] | None,
    *,
    full_text: str,
    entity: str | None = None,
) -> list[dict[str, Any]]:
    """법인명 오기가 있는 조항마다 정정 finding 을 하나씩 만든다.

    조항으로 잡히지 않는 전문(당사자 표시)·서명란도 빠뜨리지 않는다 — 법인명
    오기는 대개 거기에 있다. 조항 밖의 줄은 그 줄을 원문으로 삼는다.
    """
    body = str(full_text or "")
    if not find_name_hits(body, entity=entity):
        return []

    out: list[dict[str, Any]] = []
    covered_texts: list[str] = []
    for clause in (clauses or []):
        text = _clause_attr(clause, "text")
        if not text.strip():
            continue
        hits = find_name_hits(text, entity=entity)
        if not hits:
            covered_texts.append(text)
            continue
        covered_texts.append(text)
        title = _clause_attr(clause, "title") or _clause_attr(clause, "clause_title")
        out.append(_finding(
            clause_id=_clause_attr(clause, "clause_id"),
            title=title,
            display_path=_clause_attr(clause, "display_path"),
            article=_clause_attr(clause, "article_number"),
            paragraph=_clause_attr(clause, "paragraph_number"),
            original=text,
            revised=correct_entity_names(text, entity=entity),
            hits=hits,
            entity=entity,
        ))

    seen_lines: set[str] = set()
    party_block_no = 0
    first_article = re.search(r"^\s*제\s*1\s*조", body, re.MULTILINE)
    body_start = first_article.start() if first_article else len(body)
    place_count: dict[str, int] = {}
    offset = 0
    for raw_line in body.splitlines(keepends=True):
        line_pos = offset
        offset += len(raw_line)
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped in seen_lines:
            continue
        hits = find_name_hits(stripped, entity=entity)
        if not hits:
            continue
        if any(stripped in t for t in covered_texts):
            continue
        seen_lines.add(stripped)
        party_block_no += 1
        place = "전문(당사자 표시)" if line_pos < body_start else "서명란·말미"
        place_count[place] = place_count.get(place, 0) + 1
        if place_count[place] > 1:
            place = f"{place} {place_count[place]}"
        out.append(_finding(
            # 숫자를 넣지 않는다 — clause_id 의 숫자를 조문 번호로 읽는 게이트가
            # 있어 "line_3" 이 제3조로 오인됐다.
            clause_id=f"party_block_{_letters(party_block_no)}",
            title="당사자 표시",
            display_path=place,
            article="",
            paragraph="",
            original=stripped,
            revised=correct_entity_names(stripped, entity=entity),
            hits=hits,
            entity=entity,
        ))
    return out
