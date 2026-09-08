"""Layer 2 — NDA(비밀유지계약) 전용 결정론적 검토 룰(2026-09-08 지시).

`nda_confidentiality`로 확정된 계약에서만 실행된다. 각 룰은 계약 원문에
실제로 존재하는 문언을 정규식으로 직접 확인해 finding을 만들며, 조항번호는
`clause_extraction.py`가 만든 canonical 구조에서 조회한 실제 번호만 사용한다
(항목 9 — 존재하지 않는 조항번호 생성 금지).

이 모듈이 담당하는 지시사항
---------------------------
* 항목 5 — Background IP(계약 전 보유·독자개발)와 Foreground IP(향후 개발
  결과)의 구분. Background IP는 각 당사자에게 유지되어야 하고, Foreground
  IP는 NDA에서 최종 귀속을 임의로 정하지 않고 후속 개발계약으로 유보한다.
  상대방 비밀정보를 참고했다는 이유만으로 수령자의 독자개발 결과 전체가
  제공자에게 귀속되는 조항은 HIGH.
* 항목 6 — AI Use Purpose 분리. 프로젝트 수행에 필요한 분석·추론·처리는
  허용하되, 상대방 동의 없는 범용 모델 학습·개선 및 타 프로젝트/타 고객
  활용은 제한되어야 한다.
* 항목 7 — 개인정보는 "NDA에 전부 넣기"가 아니라 계약 경계 판단. 실제 처리
  전 별도 서면계약이 필요하다는 유보조항을 **신설**할 뿐, 기존 비밀유지
  조항을 개인정보 조항으로 교체하지 않는다(edit_type은 항상 new_clause).
* 항목 8 — 외부 협력업체에 대한 정보제공 범위는 비밀정보 제공 조항에서
  다루고, 계약상 지위 양도금지 조항을 고쳐서 해결하지 않는다(양도금지
  조항에 매칭된 경우 룰이 발동하지 않도록 anchor를 검증한다).
* 항목 10 — 모든 finding이 수정 위치·방식·기존 문구·완성 수정문구·수정
  이유를 갖추도록 `redline_instruction`을 직접 만든다.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.review.clause_extraction import ClauseChunk
from runtime.review.redline_instruction import build_redline_instruction

NDA_TYPE_CODE = "nda_confidentiality"

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def _clause_field(c: Any, name: str) -> Any:
    if isinstance(c, dict):
        return c.get(name)
    return getattr(c, name, None)


def _paragraph_number_at(article_text: str, offset: int) -> str:
    """조 본문 안에서 `offset` 위치가 몇 번째 항인지 되돌려준다.

    segmentation이 조 단위까지만 나눈 계약(항이 "1." / "①"로 한 문단 안에
    이어지는 흔한 한국식 서식)에서도 finding이 "제8조 제3항"처럼 실제 항을
    가리킬 수 있게 한다. 항 표기를 찾지 못하면 빈 문자열(조 단위 지시).
    """
    head = article_text[:offset]
    found = ""
    for m in re.finditer(r"(?:^|\n)\s*(\d{1,2})\s*\.\s", head):
        found = m.group(1)
    for m in re.finditer(r"[" + _CIRCLED + r"]", head):
        found = str(_CIRCLED.index(m.group(0)) + 1)
    return found


class _Anchor:
    """룰이 실제로 매칭된 조항의 위치·원문."""

    def __init__(self, chunk: Any, match: re.Match[str]):
        self.article_number = str(_clause_field(chunk, "article_number") or "").strip()
        self.title = str(_clause_field(chunk, "title") or "").strip()
        self.text = str(_clause_field(chunk, "text") or "")
        self.display_path = str(_clause_field(chunk, "display_path") or "").strip()
        self.paragraph_number = _paragraph_number_at(self.text, match.start())
        start = max(0, match.start() - 30)
        end = min(len(self.text), match.end() + 160)
        self.excerpt = self.text[start:end].strip()
        self.matched = match.group(0)

    @property
    def label(self) -> str:
        base = self.display_path or (f"제{self.article_number}조" if self.article_number else "")
        if self.paragraph_number:
            return f"{base} 제{self.paragraph_number}항"
        return base


def _find_anchor(
    clauses: list[ClauseChunk] | None,
    pattern: re.Pattern[str],
    *,
    exclude_title: re.Pattern[str] | None = None,
    require_in_clause: re.Pattern[str] | None = None,
) -> _Anchor | None:
    """패턴이 매칭되는 첫 조항을 찾는다.

    `exclude_title`은 항목 8을 구조적으로 강제한다 — 예컨대 제3자 제공
    범위 룰이 "권리·의무의 양도 금지" 조항에 앵커되는 것을 원천 차단한다.
    """
    for c in (clauses or []):
        text = str(_clause_field(c, "text") or "")
        if not text:
            continue
        title = str(_clause_field(c, "title") or "")
        if exclude_title is not None and exclude_title.search(title):
            continue
        if require_in_clause is not None and not require_in_clause.search(text):
            continue
        m = pattern.search(text)
        if m:
            return _Anchor(c, m)
    return None


def _last_article_number(clauses: list[ClauseChunk] | None) -> int:
    best = 0
    for c in (clauses or []):
        raw = str(_clause_field(c, "article_number") or "").strip()
        if raw.isdigit():
            best = max(best, int(raw))
    return best


# ── 계약 전체 신호 ──────────────────────────────────────────────────────────
_RX_AI_CONTEXT = re.compile(r"AI\s*모델|인공지능|학습\s*데이터|알고리즘|머신러닝|딥러닝")
_RX_JOINT_DEVELOPMENT_CONTEXT = re.compile(r"공동\s*(?:개발|연구)|기획[∙·ㆍ\s]*개발|개발[∙·ㆍ\s]*상용화|추가\s*개발")
_RX_SENSITIVE_DATA_CONTEXT = re.compile(r"수면|음성|생체|건강|의료|심박|뇌파|바이오")

# 이미 충족되어 있으면 룰을 발동시키지 않는 "해소 문언"
_RX_FOREGROUND_RESERVED = re.compile(
    r"(?:공동\s*개발|추가\s*개발|개발\s*결과|개발\s*성과)[^.\n]{0,60}"
    r"(?:후속\s*계약|별도\s*계약|별도의\s*계약|별도로\s*정한다|따로\s*정한다)"
)
_RX_GENERAL_TRAINING_RESTRICTED = re.compile(
    r"(?:범용|일반)\s*(?:AI\s*)?모델[^.\n]{0,30}(?:학습|훈련|개선)"
    r"|타\s*(?:고객|프로젝트|사업)[^.\n]{0,30}(?:활용|사용)"
)
_RX_PERSONAL_DATA_DEFERRED = re.compile(
    r"개인정보[^.\n]{0,60}(?:별도(?:의)?\s*(?:서면\s*)?계약|처리위탁\s*계약|위수탁\s*계약|따로\s*정한다)"
)
_RX_BACKUP_EXCEPTION = re.compile(r"(?:자동\s*)?백업|법령상\s*보존|보존\s*의무")
_RX_INDEPENDENT_CARVEOUT = re.compile(r"독자적으로\s*개발|자체적으로\s*개발|기존에\s*보유|이미\s*보유")


def _mk(
    *,
    clause_id: str,
    anchor: _Anchor | None,
    severity: str,
    issue_title: str,
    original_text: str,
    problem: str,
    reason: str,
    rewrite: str,
    edit_type: str,
    edit_location: str,
    mandatory_issue_code: str,
    scope_verdict: str,
    clause_topic: str = "confidentiality",
    negotiation: str = "",
    target_text: str = "",
) -> dict[str, Any]:
    """clause_result 한 건을 만든다 — redline_instruction까지 완성해서 붙인다."""
    display_path = anchor.label if anchor else ""
    instruction = build_redline_instruction(
        clause_id=clause_id,
        severity=severity,
        edit_location=edit_location,
        edit_type=edit_type,
        target_text=target_text,
        replacement_text=rewrite,
        original_text=original_text if edit_type == "replace" else "",
        reason=reason,
    )
    return {
        "clause_id": clause_id,
        "article_number": (anchor.article_number if anchor else None) or None,
        "paragraph_number": (anchor.paragraph_number if anchor else "") or None,
        "item_number": None,
        "display_path": display_path,
        "clause_title": f"{display_path} [{issue_title}]" if display_path else f"[비밀유지계약] {issue_title}",
        "issue_title": issue_title,
        "clause_number_uncertain": not bool(display_path),
        "related_clauses": [],
        "clause_topic": clause_topic,
        "original_text": original_text,
        "risk_tier": severity,
        "severity": severity,
        "high_risk": severity == "HIGH",
        "must_fix": severity == "HIGH",
        "approval_required": severity == "HIGH",
        "review_tier": "MUST" if severity == "HIGH" else "SUGGEST",
        "suggested_rewrite": rewrite,
        "rewrite_reason": problem,
        "legal_business_reason": reason,
        "suggested_direction": [problem],
        "negotiation_position": negotiation or "계약 단계(비밀유지)에 맞는 범위 명확화 목적의 수정으로 제안 가능",
        "confidence": 0.9,
        # 계약 원문 문언을 직접 확인해 만든 결정론적 룰 — Layer 1 clr_* 룰과
        # 동일한 성격이므로 계약유형 hallucination guard/relevance gate/HIGH
        # 캡에서 동일하게 예외 처리되어야 한다.
        "is_common_legal_risk": True,
        "is_mandatory": True,
        "has_rewrite_change": True,
        "display_kind": "redline" if severity == "HIGH" else "guidance",
        "dedup_suppressed": False,
        "keep_as_is": False,
        "user_focus_hit": True,
        "factual_hit": True,
        "ai_deep_reviewed": False,
        "redline_instruction": instruction,
        "mandatory_issue_code": mandatory_issue_code,
        "scope_verdict": scope_verdict,
        "original_effect_tags": ["confidentiality"],
        "rewrite_effect_tags": ["confidentiality"],
    }


def apply_nda_scope_rules(
    clause_results: list[dict[str, Any]],
    full_text: str,
    clauses: list[ClauseChunk] | None,
    *,
    contract_type_code: str,
) -> None:
    """NDA 전용 룰을 clause_results에 주입한다(계약유형이 NDA가 아니면 no-op)."""
    if (contract_type_code or "").strip() != NDA_TYPE_CODE:
        return
    text = str(full_text or "")
    existing = {str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict)}
    out: list[dict[str, Any]] = []

    def add(item: dict[str, Any] | None) -> None:
        if item and item["clause_id"] not in existing:
            out.append(item)
            existing.add(item["clause_id"])

    add(_rule_derived_information_overbroad(clauses))
    add(_rule_improvement_ip_assigned_to_discloser(clauses))
    add(_rule_foreground_ip_not_reserved(text, clauses))
    add(_rule_general_model_training_unrestricted(text, clauses))
    add(_rule_personal_data_boundary_missing(text, clauses))
    add(_rule_third_party_recipient_scope(clauses))
    add(_rule_trade_secret_survival(clauses))
    add(_rule_return_destruction_backup(clauses))
    add(_rule_injunction_prerequisites_preadmitted(clauses))
    add(_rule_subsequent_agreement_priority(clauses))

    clause_results.extend(out)


# ── 개별 룰 ─────────────────────────────────────────────────────────────────

_RX_DERIVED_INFO = re.compile(r"기초로\s*창출한\s*일체의|이를\s*기초로\s*(?:하여\s*)?(?:창출|생성|파생)")


def _rule_derived_information_overbroad(clauses: list[ClauseChunk] | None) -> dict[str, Any] | None:
    """비밀정보 정의가 "이를 기초로 창출한 일체의 정보"까지 포섭해, 수령자의
    독자개발·자체 기획 산물까지 상대방 비밀정보가 되어버리는 구조(항목 5)."""
    anchor = _find_anchor(clauses, _RX_DERIVED_INFO)
    if anchor is None:
        return None
    if _RX_INDEPENDENT_CARVEOUT.search(anchor.text):
        return None
    rewrite = (
        "“비밀정보”는 “본 계약”의 일방 당사자가 “본 업무”를 수행하는 과정에서 타방 당사자, 그 임직원 또는 "
        "대리인으로부터 제공받는 등 지득하게 된 일체의 기술상 또는 경영상의 정보 및 해당 정보의 내용을 "
        "실질적으로 포함하여 창출한 정보를 말한다. 다만 다음 각 호의 정보는 “비밀정보”에 포함되지 아니한다. "
        "(1) “정보수령자”가 “정보제공자”의 “비밀정보”를 사용하지 아니하고 독자적으로 개발하거나 착안한 정보, "
        "(2) “정보수령자”가 “비밀정보”를 제공받기 이전부터 보유하고 있던 정보 및 그 개량·발전에 따른 정보, "
        "(3) “정보수령자”가 자체적으로 수립한 제품·서비스 기획, 사업 구상 및 그에 부수하는 자료."
    )
    return _mk(
        clause_id="nda_derived_information_overbroad",
        anchor=anchor,
        severity="HIGH",
        issue_title="파생정보 정의가 수령자의 독자개발·자체 기획까지 포섭",
        original_text=anchor.excerpt,
        problem=(
            "비밀정보의 정의에 “이를 기초로 창출한 일체의 정보”가 포함되어 있어, 상대방 정보를 조금이라도 "
            "참고한 정황만 있으면 당사가 자체적으로 개발하거나 기획한 내용까지 상대방의 비밀정보로 "
            "취급될 수 있다. 독자개발·기존보유 정보에 대한 예외를 정의 단계에서 명시해야 한다."
        ),
        reason=(
            "부정경쟁방지 및 영업비밀보호에 관한 법률상 영업비밀은 비밀관리성·경제적 유용성·비공지성을 "
            "갖춘 정보에 한정되나, 계약으로 “기초로 창출한 일체의 정보”라고 정의하면 그 범위가 법률상 "
            "영업비밀보다 훨씬 넓어진다. 특히 제5조 제1항 제3호가 독자개발 정보를 비밀유지의무의 예외로 "
            "두고 있음에도 정의 조항이 이를 다시 포섭해, 두 조항이 충돌한 상태로 남는다."
        ),
        rewrite=rewrite,
        edit_type="replace",
        edit_location=f"{anchor.label} 교체",
        target_text=anchor.excerpt,
        mandatory_issue_code="confidentiality_scope",
        scope_verdict="수정 필요",
        negotiation="상호 NDA이므로 양 당사자에게 동일하게 유리한 수정이라는 점을 들어 관철 가능성이 높음",
    )


_RX_IMPROVEMENT_IP = re.compile(
    r"개량[^.\n]{0,60}(?:새로운\s*)?지식재산권|개량\s*등의\s*창작\s*활동"
)


def _rule_improvement_ip_assigned_to_discloser(clauses: list[ClauseChunk] | None) -> dict[str, Any] | None:
    """수령자의 개량·독자개발 성과를 제공자의 사전 승인 대상으로 삼아
    Background IP와 Foreground IP를 뭉뚱그리는 조항(항목 5)."""
    anchor = _find_anchor(clauses, _RX_IMPROVEMENT_IP)
    if anchor is None:
        return None
    rewrite = (
        "“비밀정보” 자체에 관한 특허출원 등 지식재산출원을 할 권리는 “정보제공자”에게 있다. "
        "다만 “정보수령자”가 “본 계약” 체결 이전부터 보유하고 있던 기술·지식재산권 및 “정보제공자”의 "
        "“비밀정보”를 사용하지 아니하고 독자적으로 개발한 기술·지식재산권은 “정보수령자”에게 그대로 귀속되며, "
        "본 항은 이에 영향을 미치지 아니한다. “정보수령자”가 “정보제공자”의 “비밀정보”를 실질적으로 이용하여 "
        "개량 기술을 창출한 경우에 한하여 그 출원 전에 “정보제공자”에게 서면으로 통지하고 권리 귀속 및 "
        "실시 조건을 협의하며, 그 구체적 내용은 당사자 간 후속 계약에서 정한다."
    )
    return _mk(
        clause_id="nda_improvement_ip_assigned_to_discloser",
        anchor=anchor,
        severity="HIGH",
        issue_title="개량기술·독자개발 성과가 제공자 사전승인 대상으로 포섭됨(Background IP 침해)",
        original_text=anchor.excerpt,
        problem=(
            "“비밀정보”를 개량하여 새로운 지식재산권을 형성하는 모든 경우에 “정보제공자”의 사전 서면 승인을 "
            "받도록 하고 있어, 당사가 계약 이전부터 보유하던 기술(Background IP)이나 상대방 정보를 쓰지 않고 "
            "독자적으로 개발한 기술까지 상대방의 승인 없이는 출원할 수 없게 될 수 있다. Background IP는 각 "
            "당사자에게 유지된다는 점, 그리고 실제로 상대방 비밀정보를 이용한 개량기술에 한하여 협의 의무가 "
            "발생한다는 점을 분리해서 명시해야 한다."
        ),
        reason=(
            "비밀유지계약은 정보의 유출을 막기 위한 계약이지 권리의 귀속을 정하는 계약이 아니다. 개량기술의 "
            "귀속을 사전 승인 구조로 묶어두면, 후속 개발계약을 체결하지 못한 상태에서도 당사의 독자 연구개발이 "
            "사실상 봉쇄되고, 상대방 비밀정보를 참고했다는 주장만으로 당사 성과 전부에 대한 권리를 다투는 "
            "근거가 될 수 있다."
        ),
        rewrite=rewrite,
        edit_type="replace",
        edit_location=f"{anchor.label} 교체",
        target_text=anchor.excerpt,
        mandatory_issue_code="background_ip",
        scope_verdict="수정 필요",
        clause_topic="ip",
        negotiation="상호 계약이므로 상대방에게도 동일하게 적용되는 대칭 수정임을 근거로 협상",
    )


_RX_IP_ARTICLE = re.compile(r"지식재산권|소유권|권리의?\s*귀속")


def _rule_foreground_ip_not_reserved(
    text: str, clauses: list[ClauseChunk] | None,
) -> dict[str, Any] | None:
    """향후 공동·추가 개발결과(Foreground IP)의 귀속을 NDA가 임의로 정하지도,
    후속 계약으로 유보하지도 않은 상태(항목 5 후단)."""
    if not _RX_JOINT_DEVELOPMENT_CONTEXT.search(text):
        return None
    if _RX_FOREGROUND_RESERVED.search(text):
        return None
    anchor = _find_anchor(clauses, _RX_IP_ARTICLE)
    if anchor is None:
        return None
    art = anchor.article_number or ""
    new_article = f"제{art}조의2" if art else "신설 조항"
    rewrite = (
        f"{new_article} (향후 개발 결과의 취급)\n"
        "“본 계약”의 당사자들이 “본 업무”의 검토 과정에서 또는 그 이후 공동으로 또는 추가로 수행하는 개발의 "
        "성과 및 그로부터 발생하는 지식재산권의 귀속, 실시권의 범위, 대가 및 제3자 실시 허락 여부는 "
        "“본 계약”에서 정하지 아니하며, 당사자들이 별도로 체결하는 개발계약에서 정한다. 해당 개발계약이 "
        "체결되기 전까지 각 당사자가 “본 계약” 체결 이전부터 보유하거나 상대방의 “비밀정보”를 사용하지 "
        "아니하고 독자적으로 개발한 기술 및 지식재산권은 각 보유 당사자에게 그대로 귀속된다."
    )
    return _mk(
        clause_id="nda_foreground_ip_not_reserved",
        anchor=anchor,
        severity="MEDIUM",
        issue_title="향후 공동·추가 개발결과의 귀속이 후속 개발계약으로 유보되어 있지 않음",
        original_text=anchor.excerpt,
        problem=(
            "계약의 목적에 기획·개발·상용화 검토가 포함되어 있음에도, 그 과정에서 또는 그 이후 발생할 개발 "
            "성과(Foreground IP)의 귀속을 어디에서 정할지에 관한 조항이 없다. 비밀유지계약 단계에서 최종 "
            "귀속을 정하는 것은 부적절하므로, 후속 개발계약에서 정하도록 유보하는 조항을 신설해야 한다."
        ),
        reason=(
            "유보 조항이 없으면 제8조의 “비밀정보에 대한 권리” 조항이 개발 성과에까지 유추 적용된다는 주장이 "
            "가능해지고, 정작 개발비·역할분담·실시권 등 대가 구조는 정해지지 않은 상태에서 권리 귀속만 "
            "다투게 된다. 유보 조항은 당사자 어느 쪽에도 불리하지 않으면서 이후 협상 여지를 그대로 남긴다."
        ),
        rewrite=rewrite,
        edit_type="new_clause",
        edit_location=f"{anchor.display_path or ('제' + art + '조')} 뒤에 {new_article} 신설",
        mandatory_issue_code="future_development_results",
        scope_verdict="별도계약 필요",
        clause_topic="ip",
        negotiation="양 당사자 모두 후속 협상 여지를 남기는 중립 조항이므로 반발 가능성이 낮음",
    )


# 사용제한 조항을 찾는 두 패턴. 앞의 것은 조 제목("비밀정보의 사용 제한")이 아니라
# 실제 의무를 정하는 문장에만 매칭되도록 서술어까지 요구한다 — 제목에 매칭되면
# finding이 조 단위로만 지시되어 "제4조 제1항"이라는 정확한 위치를 잃는다.
_RX_USE_RESTRICTION_OPERATIVE = re.compile(
    r"목적이나?\s*용도로\s*사용할\s*수\s*없|다른\s*목적으로\s*사용하[지여]|학습\s*또는\s*분석"
)
_RX_USE_RESTRICTION = re.compile(r"목적이나?\s*용도로\s*사용|본\s*업무\s*외|사용\s*제한|학습\s*또는\s*분석")


def _rule_general_model_training_unrestricted(
    text: str, clauses: list[ClauseChunk] | None,
) -> dict[str, Any] | None:
    """AI 프로젝트인데도 "프로젝트 수행상 필요한 분석·추론"과 "범용 모델 학습·
    개선·타 고객 활용"이 구분되어 있지 않은 상태(항목 6)."""
    if not _RX_AI_CONTEXT.search(text):
        return None
    if _RX_GENERAL_TRAINING_RESTRICTED.search(text):
        return None
    anchor = _find_anchor(clauses, _RX_USE_RESTRICTION_OPERATIVE) or _find_anchor(clauses, _RX_USE_RESTRICTION)
    if anchor is None:
        return None
    rewrite = (
        "“정보수령자”는 “정보제공자”의 “비밀정보”를 “본 업무”의 수행에 필요한 범위 내에서 분석, 검증, 추론 및 "
        "처리하는 목적으로만 사용할 수 있다. “정보수령자”는 “정보제공자”의 사전 서면 승인 없이 "
        "“비밀정보”(그로부터 생성된 가공·요약·특징값 데이터를 포함한다)를 자신 또는 제3자의 범용 인공지능 "
        "모델의 학습, 사전학습, 미세조정, 성능 개선, 평가용 데이터셋 구축에 사용하거나, “본 업무” 외의 다른 "
        "프로젝트 또는 다른 고객을 위한 목적으로 사용할 수 없다. “정보수령자”는 “정보제공자”의 요청이 있는 "
        "경우 해당 “비밀정보”의 사용 목적 및 처리 이력을 서면으로 설명하여야 한다."
    )
    return _mk(
        clause_id="nda_general_model_training_unrestricted",
        anchor=anchor,
        severity="HIGH",
        issue_title="범용 AI 모델 학습·개선 및 타 프로젝트 활용 제한이 명시되어 있지 않음",
        original_text=anchor.excerpt,
        problem=(
            "계약이 “AI 모델, 학습 데이터, 알고리즘”을 비밀정보로 명시하고 있음에도, 사용 제한 조항은 "
            "“본 업무 외의 목적”이라는 일반적 표현에 그친다. 프로젝트 수행에 필요한 분석·추론과, 상대방 "
            "동의 없는 범용 모델 학습·미세조정·성능 개선 및 타 고객 활용은 법적 평가가 전혀 다르므로 "
            "조문에서 명시적으로 구분해야 한다."
        ),
        reason=(
            "학습에 사용된 데이터는 모델 가중치에 흡수되어 사후 반환·폐기가 사실상 불가능하다. “본 업무 외 "
            "사용 금지”라는 표현만으로는, 상대방이 “본 업무 수행 과정에서의 학습”이라고 주장하며 범용 모델을 "
            "개선한 경우 이를 위반으로 특정하기 어렵고, 제7조의 반환·폐기 의무로도 원상회복이 되지 않는다."
        ),
        rewrite=rewrite,
        edit_type="replace",
        edit_location=f"{anchor.label} 교체",
        target_text=anchor.excerpt,
        mandatory_issue_code="ai_training_data_reuse",
        scope_verdict="수정 필요",
        clause_topic="confidentiality",
        negotiation="양 당사자 모두 AI 기술을 보유한 구조이므로 대칭 조항으로 제안 시 수용 가능성이 높음",
    )


def _rule_personal_data_boundary_missing(
    text: str, clauses: list[ClauseChunk] | None,
) -> dict[str, Any] | None:
    """실제 사용자 음성·수면·건강정보 처리가 예정되는데도, 처리 전 별도
    개인정보 계약이 필요하다는 경계 조항이 없는 상태(항목 7).

    기존 비밀유지 조항을 개인정보 조항으로 **교체하지 않는다** — 항상 신설.
    """
    if not (_RX_SENSITIVE_DATA_CONTEXT.search(text) or "개인정보" in text):
        return None
    if _RX_PERSONAL_DATA_DEFERRED.search(text):
        return None
    anchor = _find_anchor(clauses, _RX_USE_RESTRICTION)
    if anchor is None:
        return None
    art = anchor.article_number or ""
    new_article = f"제{art}조의2" if art else "신설 조항"
    rewrite = (
        f"{new_article} (개인정보의 취급 경계)\n"
        "“본 계약”은 “비밀정보”의 보호에 관한 사항만을 정하며, 「개인정보 보호법」상 개인정보(민감정보 및 "
        "생체정보를 포함한다)의 처리에 관한 권한을 부여하지 아니한다. 당사자들은 실제 이용자의 음성, 수면, "
        "건강 등 개인정보를 수집·이용·제공·처리하기 전에 처리 목적과 항목, 처리위탁·제3자 제공·공동처리 여부, "
        "민감정보 및 국외 이전 여부, 재위탁의 허용 범위, 보유기간과 파기 방법, 안전성 확보조치 및 사고 "
        "통지 절차를 정하는 별도의 서면계약을 체결하여야 한다. 해당 서면계약이 체결되기 전까지 어느 "
        "당사자도 상대방에게 실제 이용자의 개인정보를 제공하거나 상대방을 위하여 이를 처리하지 아니하며, "
        "“본 업무”의 검토는 가명·익명 처리되었거나 개인을 식별할 수 없는 데이터로 수행한다."
    )
    return _mk(
        clause_id="nda_personal_data_boundary_missing",
        anchor=anchor,
        severity="HIGH",
        issue_title="실제 이용자 개인정보 처리에 대한 별도 계약 유보 조항이 없음",
        original_text=anchor.excerpt,
        problem=(
            "수면·음성 등 개인의 생활·건강과 직결되는 데이터를 다루는 협력이 예정되어 있으나, 계약에는 "
            "개인정보 처리에 관한 경계가 전혀 정해져 있지 않다. 비밀유지 조항은 정보의 누설을 막을 뿐 "
            "개인정보를 처리할 법적 근거가 되지 못하므로, 실제 처리 전에 별도 계약이 필요하다는 유보 조항을 "
            "신설해야 한다."
        ),
        reason=(
            "「개인정보 보호법」상 처리위탁·제3자 제공·공동처리는 각각 요건과 책임 구조가 다르고, 수면·건강 "
            "정보는 민감정보에 해당할 수 있어 별도 동의와 강화된 안전조치가 요구된다. 근거 계약 없이 "
            "개인정보가 오가면 양 당사자 모두 과징금·과태료 및 정보주체에 대한 손해배상 위험을 부담한다. "
            "이 사항들을 비밀유지계약 본문에 끌어와 정하는 것은 계약 단계에 맞지 않으므로, 경계만 긋고 "
            "구체적 내용은 후속 개인정보 계약으로 넘긴다."
        ),
        rewrite=rewrite,
        edit_type="new_clause",
        edit_location=f"{anchor.display_path or ('제' + art + '조')} 뒤에 {new_article} 신설",
        mandatory_issue_code="personal_sensitive_data",
        scope_verdict="별도계약 필요",
        clause_topic="personal_data",
        negotiation="법령 준수를 위한 중립 조항으로, 양 당사자 모두의 제재 위험을 낮추므로 반발 가능성이 낮음",
    )


_RX_THIRD_PARTY_DISCLOSURE = re.compile(r"제\s*3\s*자에게\s*제공")
_RX_ASSIGNMENT_TITLE = re.compile(r"양도|이전|지위")


def _rule_third_party_recipient_scope(clauses: list[ClauseChunk] | None) -> dict[str, Any] | None:
    """외부 협력업체·시험기관에 대한 정보제공 범위 명확화(항목 8).

    반드시 "비밀정보 제공" 조항에 앵커되어야 하며, "권리·의무의 양도 금지"
    조항을 수정해 해결하지 않는다.
    """
    anchor = _find_anchor(
        clauses,
        _RX_THIRD_PARTY_DISCLOSURE,
        exclude_title=_RX_ASSIGNMENT_TITLE,
        require_in_clause=re.compile(r"비밀정보"),
    )
    if anchor is None:
        return None
    rewrite = (
        "“정보수령자”가 “본 업무”의 수행을 위하여 “정보제공자”의 “비밀정보”를 제3자에게 제공하고자 할 경우, "
        "“정보수령자”는 그 제3자의 상호, 수행 업무의 범위 및 제공하려는 “비밀정보”의 항목을 특정하여 "
        "“정보제공자”로부터 사전 서면 승인을 받아야 하며, 그 제3자와 “본 계약”과 동등한 수준의 비밀유지계약을 "
        "체결한 이후에 이를 제공하여야 한다. 다만 “정보수령자”의 임직원 및 “정보수령자”와 이미 "
        "비밀유지계약을 체결하고 “본 업무”에 직접 관여하는 자문사·시험기관에 대하여는, “정보수령자”가 그 "
        "명단과 제공 범위를 사전에 “정보제공자”에게 서면으로 통지하는 것으로 승인에 갈음할 수 있다. "
        "다만 알고리즘, 모델 구조, 학습 데이터 등 핵심기술에 해당하는 “비밀정보”의 제공은 통지로 갈음할 수 "
        "없고 언제나 “정보제공자”의 사전 서면 승인을 받아야 한다. 어느 경우에도 “정보수령자”는 그 제3자의 "
        "행위에 대하여 자신의 행위와 동일한 책임을 진다."
    )
    return _mk(
        clause_id="nda_third_party_recipient_scope",
        anchor=anchor,
        severity="MEDIUM",
        issue_title="외부 협력업체에 대한 정보제공 범위와 핵심기술 사전승인 기준이 불명확",
        original_text=anchor.excerpt,
        problem=(
            "제3자 제공에 일률적으로 건별 사전 서면 승인을 요구하고 있어, 실제 개발 과정에서 반드시 관여하는 "
            "외부 개발사·시험기관에 대한 정보 제공이 매번 지연될 수 있다. 반대로 알고리즘·모델 구조 같은 "
            "핵심기술은 승인 기준이 따로 없어 일반 정보와 동일하게 취급된다. 통지로 갈음할 수 있는 범위와 "
            "언제나 사전 승인이 필요한 핵심기술을 조문에서 구분해야 한다."
        ),
        reason=(
            "이 쟁점은 “비밀정보를 누구에게 제공할 수 있는가”의 문제이므로 비밀정보 제공 조항에서 해결해야 "
            "하며, 계약상 지위의 양도를 금지하는 조항(권리·의무의 양도 금지)을 수정해 해결할 사항이 아니다. "
            "두 조항은 규율 대상이 서로 다르다."
        ),
        rewrite=rewrite,
        edit_type="replace",
        edit_location=f"{anchor.label} 교체",
        target_text=anchor.excerpt,
        mandatory_issue_code="permitted_recipients",
        scope_verdict="수정 필요",
        negotiation="양 당사자 모두 외부 협력업체를 사용하는 구조이므로 대칭 조항으로 제안",
    )


_RX_SURVIVAL_YEARS = re.compile(r"비밀유지의무[^.\n]{0,80}?(\d+)\s*년")


def _rule_trade_secret_survival(clauses: list[ClauseChunk] | None) -> dict[str, Any] | None:
    """비밀유지기간이 확정 연수로만 정해져 있어, 그 기간 경과 후에는 영업비밀도
    자유롭게 사용될 수 있는 구조."""
    anchor = _find_anchor(clauses, _RX_SURVIVAL_YEARS)
    if anchor is None:
        return None
    if re.search(r"영업비밀", anchor.text):
        return None
    rewrite = (
        "“본 계약” 상의 비밀유지의무는 “본 계약”이 종료된 이후에도 존속하며 “본 계약”의 체결일부터 5년간 "
        "유효하다. 다만 「부정경쟁방지 및 영업비밀보호에 관한 법률」상 영업비밀에 해당하는 “비밀정보” 및 "
        "알고리즘, 모델 구조, 학습 데이터 등 핵심기술에 관한 “비밀정보”에 대하여는, 해당 정보가 "
        "“정보수령자”의 귀책사유 없이 공지의 사실이 될 때까지 비밀유지의무가 존속한다."
    )
    return _mk(
        clause_id="nda_trade_secret_survival_capped",
        anchor=anchor,
        severity="MEDIUM",
        issue_title="영업비밀·핵심기술까지 비밀유지기간이 확정 연수로 종료됨",
        original_text=anchor.excerpt,
        problem=(
            "비밀유지의무의 존속기간이 확정된 연수로만 정해져 있어, 그 기간이 지나면 알고리즘·모델 구조·"
            "학습 데이터와 같이 공개된 적이 없는 핵심기술까지 자유롭게 사용될 수 있다는 해석이 가능하다. "
            "영업비밀에 해당하는 정보는 공지될 때까지 존속하도록 예외를 두어야 한다."
        ),
        reason=(
            "영업비밀은 비공지 상태가 유지되는 한 기간 제한 없이 보호되는 것이 원칙이나, 계약으로 존속기간을 "
            "특정하면 그 기간이 당사자 사이의 합의된 보호기간으로 해석될 위험이 있다. 상호 계약이므로 이 "
            "예외는 양 당사자에게 동일하게 적용된다."
        ),
        rewrite=rewrite,
        edit_type="replace",
        edit_location=f"{anchor.label} 교체",
        target_text=anchor.excerpt,
        mandatory_issue_code="confidentiality_duration",
        scope_verdict="수정 필요",
        clause_topic="termination",
    )


_RX_RETURN_DESTRUCTION = re.compile(r"반환하거나?\s*폐기|반환\s*또는\s*폐기|폐기하여야")


def _rule_return_destruction_backup(clauses: list[ClauseChunk] | None) -> dict[str, Any] | None:
    """반환·폐기 의무에 자동백업·법령상 보존에 대한 예외가 없어 이행 자체가
    불가능해지는 구조."""
    anchor = _find_anchor(clauses, _RX_RETURN_DESTRUCTION)
    if anchor is None:
        return None
    if _RX_BACKUP_EXCEPTION.search(anchor.text):
        return None
    rewrite = (
        "제1문의 반환·폐기 의무에도 불구하고, “정보수령자”는 (1) 관계 법령 또는 감독기관의 요구에 따라 "
        "보존하여야 하는 “비밀정보”, (2) 통상적인 전산 백업·아카이빙 절차에 따라 자동으로 생성되어 개별 "
        "삭제가 기술적으로 곤란한 사본, (3) 분쟁의 대응을 위하여 필요한 최소한의 “비밀정보”를 보유할 수 있다. "
        "이 경우 “정보수령자”는 해당 “비밀정보”를 “본 업무” 외의 목적으로 사용하지 아니하고, 접근 권한을 "
        "제한하며, 보존 사유가 소멸하거나 백업 보존주기가 도래하는 때에 지체 없이 폐기하고, “본 계약” 상의 "
        "비밀유지의무는 그 보유 기간 동안 계속 존속한다."
    )
    return _mk(
        clause_id="nda_return_destruction_backup_exception",
        anchor=anchor,
        severity="MEDIUM",
        issue_title="반환·폐기 의무에 자동백업·법령상 보존 예외가 없음",
        original_text=anchor.excerpt,
        problem=(
            "반환 또는 폐기 후 확인서 제출까지 요구하면서, 통상적인 전산 백업본과 법령상 보존의무가 있는 "
            "자료에 대한 예외가 없다. 현실적으로 백업 사본의 개별 삭제는 불가능하므로, 예외 없이는 확인서 "
            "제출 시점부터 계약 위반 상태가 된다."
        ),
        reason=(
            "이행이 불가능한 의무를 그대로 두면 상대방이 언제든 계약 위반을 주장할 수 있는 근거가 되고, "
            "제11조의 손해배상 및 가처분 조항과 결합하면 실질적인 위험이 커진다. 예외를 두되 보유 기간 중 "
            "비밀유지의무가 존속하도록 하면 상대방의 보호 수준은 낮아지지 않는다."
        ),
        rewrite=rewrite,
        edit_type="insert_after",
        edit_location=f"{anchor.label} 말미에 단서 추가",
        mandatory_issue_code="return_destruction_backup",
        scope_verdict="수정 필요",
        clause_topic="return_destruction",
    )


_RX_INJUNCTION_PREADMIT = re.compile(
    r"(?:피보전권리|보전의?\s*필요성)[^.\n]{0,60}(?:충족|인정)"
)


def _rule_injunction_prerequisites_preadmitted(clauses: list[ClauseChunk] | None) -> dict[str, Any] | None:
    """가처분의 실체적 요건을 계약으로 미리 인정해 방어권을 포기하는 조항."""
    anchor = _find_anchor(clauses, _RX_INJUNCTION_PREADMIT)
    if anchor is None:
        return None
    rewrite = (
        "“본 계약”의 당사자들은 “본 계약”의 위반이 상대방에게 금전적 손해배상만으로는 회복하기 어려운 손해를 "
        "발생시킬 수 있음을 확인한다. 다만 본 항은 가처분 등 보전처분의 피보전권리 및 보전의 필요성이 "
        "존재함을 미리 인정하는 것으로 해석되지 아니하며, 그 요건의 존부는 관계 법령에 따라 법원이 "
        "개별적으로 판단한다. 각 당사자는 보전처분 절차에서 자신의 주장과 증거를 제출할 권리를 포기하지 "
        "아니한다."
    )
    return _mk(
        clause_id="nda_injunction_prerequisites_preadmitted",
        anchor=anchor,
        severity="MEDIUM",
        issue_title="가처분의 피보전권리·보전의 필요성을 계약으로 사전 인정",
        original_text=anchor.excerpt,
        problem=(
            "보전처분의 실체적 요건인 피보전권리와 보전의 필요성이 충족됨을 당사자가 미리 인정하는 문언이다. "
            "실제 분쟁에서 당사가 이를 다툴 여지를 스스로 좁히는 결과가 되므로, 회복 곤란성에 관한 사실 "
            "확인에 그치도록 하고 요건 판단은 법원에 유보해야 한다."
        ),
        reason=(
            "가처분이 인용되면 본안 판단 전에 사업 활동이 중단될 수 있고, 특히 개발·상용화 단계에서는 그 "
            "손실이 크다. 요건 충족을 계약으로 미리 인정하는 조항은 상호 조항이라 하더라도 실제로는 먼저 "
            "신청하는 당사자에게 유리하게 작용한다."
        ),
        rewrite=rewrite,
        edit_type="replace",
        edit_location=f"{anchor.label} 교체",
        target_text=anchor.excerpt,
        mandatory_issue_code="damages_injunction",
        scope_verdict="수정 필요",
        clause_topic="damage",
    )


_RX_PRIOR_AGREEMENT_PRIORITY = re.compile(r"이전에\s*이루어진[^.\n]{0,80}우선한다|우선한다")


def _rule_subsequent_agreement_priority(clauses: list[ClauseChunk] | None) -> dict[str, Any] | None:
    """체결 이전의 합의에 대한 우선순위만 정하고, 이후 체결될 후속 계약과의
    우선순위는 정하지 않은 상태(항목 1·11)."""
    anchor = _find_anchor(clauses, _RX_PRIOR_AGREEMENT_PRIORITY)
    if anchor is None:
        return None
    if re.search(r"후속\s*계약|이후\s*체결", anchor.text):
        return None
    rewrite = (
        "“본 계약”의 당사자들이 “본 계약” 체결 이후 “본 업무”와 관련하여 개발계약, 공급계약, 개인정보 처리에 "
        "관한 계약 등 별도의 계약을 체결하는 경우, 그 계약에서 비밀유지에 관하여 “본 계약”과 다르게 정한 "
        "사항은 해당 계약이 정하는 범위에서 그 계약이 우선한다. 그 외의 사항에 대하여는 “본 계약”이 계속 "
        "적용되며, “본 계약”의 비밀유지의무는 해당 계약의 체결로 인하여 소멸하지 아니한다."
    )
    return _mk(
        clause_id="nda_subsequent_agreement_priority",
        anchor=anchor,
        severity="MEDIUM",
        issue_title="후속 계약과 본 계약의 우선순위가 정해져 있지 않음",
        original_text=anchor.excerpt,
        problem=(
            "계약의 효력 조항이 “체결 이전”의 양해·합의에 대한 우선순위만 정하고 있어, 이후 체결될 개발계약·"
            "개인정보 계약 등에서 비밀유지에 관하여 다르게 정한 경우 어느 계약이 우선하는지 알 수 없다. "
            "후속 계약과의 관계를 명시해야 한다."
        ),
        reason=(
            "후속 개발계약에서 비밀유지 범위나 기간을 새로 정하면, 두 계약이 병존하면서 서로 다른 의무가 "
            "동시에 적용되는 상태가 된다. 우선순위 조항을 두면 후속 계약 협상 시 비밀유지 조건만 따로 다시 "
            "합의하면 되고, 본 계약을 해지·변경할 필요가 없다."
        ),
        rewrite=rewrite,
        edit_type="insert_after",
        edit_location=f"{anchor.label} 말미에 항 추가",
        mandatory_issue_code="subsequent_agreement_priority",
        scope_verdict="수정 필요",
        clause_topic="other",
    )
