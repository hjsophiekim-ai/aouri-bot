"""Legal Map 의 "미기재" 판정을 계약 원문으로 확인한다.

2026-09-21 4차 지시 3항 —
  "비밀유지기간, 외부 협력업체, Background IP, Foreground IP, 개인정보
   처리경계가 실제 계약에 있으면 Legal Map 에서 절대 '미기재' 로 표시하지
   마세요. Legal Map 과 조항별 검토결과가 모순되면
   REVIEW_FAILED_LEGAL_MAP_CONTRADICTION."

왜 비어 있었나
────────────
Legal Map 은 AI 가 채운다. AI 를 쓰지 않거나 호출이 실패하면 정규식
fallback 이 도는데, 그것이 채우는 축은 사실상 `contract_purpose` 하나다.
그 상태로 완결성 게이트를 돌리면 계약에 **실재하는** 축까지 전부 미기재가
된다. 실측(상호 NDA 수정안, 2026-09-21):

    missing_blocking = 우리 회사의 지위, 핵심 급부, 대가 지급 구조,
                       검수/인도/준공 조건, 지식재산/자료 귀속

지식재산 귀속은 제9조에, 우리 지위는 canonical_state 에 이미 있다. 대가
지급·검수는 NDA 에 **없는 것이 정상**이다(그 축은 유형 게이트가 따로
걸러야 한다). 셋 다 성격이 다른데 한 줄로 "미기재" 가 됐다.

이 모듈이 하는 일
──────────────
Map 필드가 비어 있어도 (1) 이미 확정된 canonical 값이 있거나 (2) 계약
원문이 그 축을 규정하고 있으면 **채워진 것으로 본다**. 무엇을 근거로
채웠는지 함께 남긴다 — 조용히 채우면 나중에 그 값이 어디서 왔는지 알 수
없다.

새로 판단하지 않는다. 이미 있는 것을 못 본 것을 고칠 뿐이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REVIEW_FAILED_LEGAL_MAP_CONTRADICTION = "REVIEW_FAILED_LEGAL_MAP_CONTRADICTION"


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


#: 축 → 계약 원문에서 그 축이 규정되어 있음을 보여주는 문형.
#: 낱말 하나가 아니라 **규정하는 문장**을 찾는다 — "비밀"이라는 낱말이
#: 있다고 비밀유지 구조가 정해진 것은 아니다.
AXIS_TEXT_EVIDENCE: dict[str, re.Pattern[str]] = {
    "primary_obligations": _rx(
        r"비밀유지의무[^.\n]{0,60}(?:부담|적용|이행)"
        r"|비밀정보를[^.\n]{0,40}(?:사용|제공|공개)하[^.\n]{0,30}아니"
        r"|목적을?\s*위해서만[^.\n]{0,30}사용"
    ),
    "ip_and_data_ownership": _rx(
        r"(?:지식재산권?|권리)[^.\n]{0,60}귀속"
        r"|(?:체결\s*전부터|이전부터)\s*보유[^.\n]{0,80}귀속"
        r"|양도, 허락 또는 부여한 것으로 보지"
    ),
    "term": _rx(
        r"비밀유지의무는[^.\n]{0,60}(?:\d+\s*년|영업비밀)"
        r"|효력이\s*발생한다|계약\s*기간[^.\n]{0,40}(?:년|개월|까지)"
    ),
    "liability_structure": _rx(
        r"손해를?\s*배상|배상\s*범위[^.\n]{0,60}(?:직접손해|한정|제외)"
        r"|책임을\s*부담한다"
    ),
    "indemnity_structure": _rx(
        r"간접손해|특별손해|결과손해|일실이익|배상\s*범위"
    ),
    "termination_structure": _rx(
        r"(?:계약이?|협력이?)\s*(?:종료|해지|해제)[^.\n]{0,60}(?:경우|때)"
        r"|반환\s*또는\s*폐기"
    ),
    "third_party_liability": _rx(
        r"제3자[^.\n]{0,80}(?:제공|공개|참여)"
        r"|협력업체[^.\n]{0,60}(?:제공|부과)"
    ),
    "confidential_information_scope": _rx(
        r"[\"'“”]?비밀정보[\"'“”]?(?:란|이란)[^.\n]{0,80}의미한다"
        r"|비밀정보에는[^.\n]{0,80}포함"
    ),
    "return_destruction": _rx(
        r"반환\s*(?:또는|및)\s*폐기|폐기하여야|폐기\s*확인서"
    ),
    "confidentiality_survival": _rx(
        r"종료되더라도[^.\n]{0,60}(?:계속|존속)"
        r"|영업비밀성을\s*유지하는\s*동안"
    ),
    "applicable_statutes": _rx(
        r"준거법|대한민국\s*법률을\s*적용|관련\s*법령을\s*준수"
    ),
    "acceptance_and_completion": _rx(
        r"검수|준공|인수인계|합격[^.\n]{0,40}(?:본다|간주)"
    ),
    "payment_flow": _rx(
        r"대금[^.\n]{0,30}지급|기성|계약금액|지급기한|지급한다"
    ),
    "risk_transfer_point": _rx(r"위험(?:은|이)?\s*[^.\n]{0,30}이전|인도\s*시"),
}

#: 축 → canonical_state 에서 그 값을 들고 있는 속성.
AXIS_CANONICAL_SOURCE: dict[str, str] = {
    "our_role_direction": "party_role_direction",
    "counterparty": "counterparty_role",
    "contract_purpose": "contract_type_label",
}


@dataclass
class GroundingReport:
    """원문·확정값으로 채운 축과 그 근거."""

    grounded: dict[str, str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    #: Map 은 미기재라고 했는데 조항별 검토는 그 조항을 다루고 있는 축.
    contradictions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        return REVIEW_FAILED_LEGAL_MAP_CONTRADICTION if self.contradictions else ""

    @property
    def detail(self) -> str:
        if not self.contradictions:
            return ""
        names = ", ".join(c["label"] for c in self.contradictions[:4])
        return (
            f"Legal Map 이 '미기재' 로 둔 축을 계약 원문에서 확인해 채웠습니다 "
            f"— {names}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "grounded": dict(self.grounded),
            "sources": dict(self.sources),
            "contradictions": list(self.contradictions),
        }


def ground_legal_map(
    fields: dict[str, Any] | None,
    *,
    contract_text: str,
    canonical_state: Any = None,
    axis_labels: dict[str, str] | None = None,
) -> GroundingReport:
    """비어 있는 축을 확정값·원문으로 채운다. 제자리에서 `fields` 를 고친다."""
    from runtime.review.legal_map_gate import _is_filled

    report = GroundingReport()
    if fields is None:
        return report
    labels = axis_labels or {}
    body = str(contract_text or "")

    for axis, attr in AXIS_CANONICAL_SOURCE.items():
        if _is_filled(fields.get(axis)):
            continue
        value = str(getattr(canonical_state, attr, "") or "") if canonical_state else ""
        if not value:
            continue
        fields[axis] = value
        report.grounded[axis] = value
        report.sources[axis] = "canonical_state"
        report.contradictions.append({
            "axis": axis, "label": labels.get(axis, axis),
            "evidence": value, "source": "canonical_state",
        })

    for axis, pattern in AXIS_TEXT_EVIDENCE.items():
        if _is_filled(fields.get(axis)):
            continue
        m = pattern.search(body)
        if m is None:
            continue
        evidence = re.sub(r"\s+", " ", m.group(0)).strip()[:160]
        fields[axis] = f"[원문 확인] {evidence}"
        report.grounded[axis] = evidence
        report.sources[axis] = "contract_text"
        report.contradictions.append({
            "axis": axis, "label": labels.get(axis, axis),
            "evidence": evidence, "source": "contract_text",
        })
    return report


# ── 요약 헤더용 사실 확인 상태 (2026-10-21 지시 1항) ──────────────────────────
#
# 실측(프리랜서 콘텐츠 용역계약): 요약 헤더가 "산출물 지식재산권 귀속: 미기재 /
# 검수 기준: 미기재 / 대금 지급 조건: 미기재" 를 찍었다. 세 축 모두 원문
# 제4·5·8조에 있고 Legal Map(AI)도 채워 두었는데, 헤더는 detailed_contract_profile
# 이라는 **다른 저장소**를 읽었고 그 저장소에는 이 키를 채우는 단계가 없었다.
# 값이 비면 "미기재" 를 찍으니 "필드를 못 채움" 이 "계약에 조항 없음" 으로 나갔다.
#
# 여기서 축마다 확인 상태를 하나로 정하고, 헤더는 그 결과만 그린다.
#   explicit         — 원문 조항에서 규정을 찾음 (위치·원문 함께)
#   unclear          — 관련 낱말은 있으나 규정하는 문장으로 확인되지 않음
#   not_found        — 본문·첨부 전체를 찾아도 관련 규정이 없음
#   extraction_failed— 원문 추출이 불완전해 판단할 수 없음
# "일부 부족" 은 지적(finding)이 같은 조항에 걸렸을 때 렌더러가 덧붙인다 —
# 부족 여부는 조항별 검토의 판단이지 이 함수가 새로 판단할 일이 아니다.

FACT_EXPLICIT = "explicit"
FACT_UNCLEAR = "unclear"
FACT_NOT_FOUND = "not_found"
FACT_EXTRACTION_FAILED = "extraction_failed"

#: 요약 필드 → (Legal Map 축, 규정 문형, 관련 낱말, 조 제목 단서)
SUMMARY_FACT_AXES: dict[str, tuple[str, re.Pattern[str], re.Pattern[str], re.Pattern[str]]] = {
    "deliverables_ip_owner": (
        "ip_and_data_ownership",
        _rx(r"(?:지식재산권?|저작(?:재산)?권|권리|소유권)[^.\n]{0,60}(?:귀속|양도|이전)(?:된다|한다|하며|되며|받|하고|되고)"),
        _rx(r"지식재산|저작권|저작물|성과물의?\s*권리"),
        _rx(r"지식재산|저작권|성과물|권리\s*귀속|산출물"),
    ),
    "acceptance_criteria": (
        "acceptance_and_completion",
        _rx(r"검수[^.\n]{0,40}(?:이내|기한|결과|기준|절차|통지|완료된\s*것으로|합격)|재검수|간주\s*검수"),
        _rx(r"검수|인수|검사"),
        _rx(r"검수|납품|인수|검사"),
    ),
    "payment_terms": (
        "payment_flow",
        _rx(r"(?:대금|대가|보수|용역료|수수료|단가)[^.\n]{0,60}(?:지급한다|지급하여야|정산한다|이내에|원/건|원\s*\(|초과하지)"),
        _rx(r"대금|대가|보수|용역료|지급"),
        _rx(r"대금|대가|보수|지급|정산"),
    ),
}


def _sentence_around(body: str, m: re.Match[str]) -> str:
    """일치한 문형이 든 문장(항 번호·앞 문장 제외) — 요약에 낱말 조각이 아니라 규정 문장을 싣는다."""
    prev = body.rfind("다.", 0, m.start())
    start = prev + 2 if prev >= 0 else 0
    end = body.find("다.", max(m.start(), m.end() - 2))
    sent = body[start: end + 2 if end >= 0 else len(body)].strip()
    sent = re.sub(r"^(?:제\s*\d+\s*조\.?\s*(?:\[[^\]]*\])?\s*)?[①-⑳]?\s*", "", sent)
    return sent


def _article_hits(clause_index: Any, rule: re.Pattern[str], title_hint: re.Pattern[str]) -> list[tuple[int, Any, str]]:
    hits: list[tuple[int, Any, str]] = []
    for art in (getattr(clause_index, "articles", None) or {}).values():
        # PDF 줄바꿈은 문장 경계가 아니다 — 줄이 바뀐 "배타적으로 / 귀속된다" 를 놓치지 않게 공백을 편다.
        body = re.sub(r"\s+", " ", str(getattr(art, "exact_text", "") or ""))
        found = list(rule.finditer(body))
        if not found:
            continue
        score = len(found) + (3 if title_hint.search(str(getattr(art, "title", "") or "")) else 0)
        hits.append((score, art, _sentence_around(body, found[0])))
    hits.sort(key=lambda h: -h[0])
    return hits


def resolve_summary_facts(
    legal_map_fields: dict[str, Any] | None,
    *,
    clause_index: Any,
    contract_text: str,
) -> dict[str, dict[str, Any]]:
    """요약 필드별 확인 상태·근거. 값은 사람이 읽는 `display` 로도 준다."""
    from runtime.review.legal_map_gate import _is_filled

    fields = legal_map_fields or {}
    body = str(contract_text or "")
    extraction_ok = len(body.strip()) >= 200 and not getattr(clause_index, "structure_uncertain", False)
    out: dict[str, dict[str, Any]] = {}
    for key, (axis, rule, loose, title_hint) in SUMMARY_FACT_AXES.items():
        map_value = fields.get(axis)
        map_text = str(map_value).strip() if _is_filled(map_value) else ""
        map_text = re.sub(r"^\[원문 확인\]\s*", "", map_text)
        hits = _article_hits(clause_index, rule, title_hint)
        if hits:
            _, art, quote = hits[0]
            where = f"제{art.number}조" + (f"({art.title})" if getattr(art, "title", "") else "")
            # 요약은 원문 문장으로 쓴다 — AI 요약을 쓰면 원문과 다른 표현이 근거처럼 보인다.
            out[key] = {
                "status": FACT_EXPLICIT, "article": str(art.number), "quote": quote,
                "source": "contract_text", "legal_map": map_text,
                "display": f"규정 있음 — {where}: {quote[:90]}" + ("…" if len(quote) > 90 else ""),
            }
            continue
        flat = re.sub(r"\s+", " ", body)
        if rule.search(flat):
            # 조 구조 밖(첨부·별표)에 규정이 있는 경우
            m = rule.search(flat)
            quote = _sentence_around(flat, m) if m else ""
            out[key] = {
                "status": FACT_EXPLICIT, "article": "", "quote": quote,
                "source": "contract_text", "legal_map": map_text,
                "display": f"규정 있음 — 첨부·본문 기타 위치: {quote[:90]}",
            }
            continue
        if not extraction_ok:
            out[key] = {
                "status": FACT_EXTRACTION_FAILED, "article": "", "quote": "",
                "source": "", "legal_map": map_text,
                "display": "확인 불가 — 원문 추출이 불완전해 판단하지 못함(원본 확인 필요)",
            }
            continue
        if loose.search(body) or map_text:
            out[key] = {
                "status": FACT_UNCLEAR, "article": "", "quote": "",
                "source": "legal_map" if map_text else "contract_text", "legal_map": map_text,
                "display": "관련 문구는 있으나 규정 내용이 불명확 — 상세 검토 참조",
            }
            continue
        out[key] = {
            "status": FACT_NOT_FOUND, "article": "", "quote": "",
            "source": "contract_text", "legal_map": map_text,
            "display": "본문·첨부 전체에서 관련 규정을 찾지 못함 — 신설 검토 필요",
        }
    return out
