"""법률효과 기반 점검 2종 — 대리 권한 / 선택형 귀속 조항 미선택 (2026-10-01 지시).

계약유형 룰팩이 아니다(v8 원칙). 어느 계약에서든 같은 법률효과가 있으면 같은 판단을 한다.

1. 대리 권한 (지시 6항·14항 B)
   계약 상대방이 권리자 본인이 아니라 갤러리·에이전시·대리인이면, 그 대리인이 받은 권한
   범위 안의 행위만 권리자에게 효력이 있다(민법 제114조). 권한이 없으면 권리자가 추인하지
   않는 한 효력이 없다(제130조). 그래서 (a) 권한을 **증명하는 서면**과 (b) 권한 하자 시
   우리를 지키는 **면책·배상 범위**가 계약에 있어야 한다. "직접적인 손해" 로 한정하면
   판매중단·회수 비용이 빠진다.

2. 선택형 귀속 조항 미선택 (지시 14항 C)
   "□ 알로소 / □ 국립한글박물관 / □ 기타" 처럼 귀속 주체를 고르게 한 조항이 아무것도
   선택되지 않은 채 서명되면, 대금을 다 치르고도 실물을 누가 갖는지가 정해지지 않는다.
"""
from __future__ import annotations

import re
from typing import Any

_RX_AGENT_PARTY = re.compile(r"갤러리|에이전시|대리인|매니지먼트")
_RX_AGENT_SCENARIO = re.compile(r"본인이\s*아닌|대리인인\s*경우|권한을\s*위임|위임받")
_RX_AUTHORITY = re.compile(r"권한을?\s*위임|대리권|권한을?\s*(?:적법하게\s*)?확보|동의\s*또는\s*권한")
_RX_PROOF = re.compile(r"위임장|권한을?\s*증명|증빙\s*(?:서류|자료)?(?:을|를)?\s*제출|확인서(?:를)?\s*제출|권한\s*증빙")
_RX_INDEMNITY = re.compile(r"면책|방어(?:하여야|한다)|제3자[^.\n]{0,40}(?:청구|소송|이의)[^.\n]{0,60}(?:비용|책임)으로")
_RX_DIRECT_ONLY = re.compile(r"직접적인\s*손해|직접\s*손해")
_RX_PRINCIPAL = re.compile(r"참여\s*아티스트|아티스트|작가|저작자|권리자")

_RX_CHECKED = re.compile(r"[■☑☒✔✓▣]")
_RX_OPTION = re.compile(r"□\s*([^□/\n]+?)\s*(?=/|□|$)")
_RX_ALLOCATION = re.compile(r"귀속|소유권|권리자|주체")


_RX_AGENT_BLOCK_LABEL = re.compile(
    r"(?:갤러리|에이전시|대리인)[^\n]*\n(?:[^\n]*\n){0,6}?[^\n]*이하\s*[“\"']([^”\"']{1,12})[”\"']"
)


def _batchim(word: str) -> bool:
    last = word[-1:] if word else ""
    return "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0


def _p(word: str, with_b: str, without_b: str) -> str:
    return word + (with_b if _batchim(word) else without_b)


def _agent_label(text: str, agent: Any) -> str:
    if agent is not None and getattr(agent, "label", ""):
        return agent.label
    m = _RX_AGENT_BLOCK_LABEL.search(text[:3000])
    return m.group(1).strip() if m else "상대방"


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _finding(clause: Any, **kw: Any) -> dict[str, Any]:
    base = {
        "clause_id": f"{kw.pop('check_id')}__{_attr(clause, 'clause_id')}",
        "clause_title": _attr(clause, "title") or _attr(clause, "clause_title"),
        "display_path": _attr(clause, "display_path"),
        "article_number": _attr(clause, "article_number"),
        "paragraph_number": _attr(clause, "paragraph_number"),
        "original_text": _attr(clause, "text"),
        "risk_tier": "MEDIUM",
        "severity": "MEDIUM",
        "confidence": 0.85,
        "is_effect_baseline": True,
        # 원문 문언을 정규식으로 직접 확인한 결함이다 — 계약유형·주제 호환성으로
        # 강등하는 게이트(relevance_validation_gate 등)가 건드리지 않게 한다.
        # 법인명 정정 finding 과 같은 근거(실측: 둘 다 LOW 로 떨어지고 수정문이 지워짐).
        "is_common_legal_risk": True,
    }
    base.update(kw)
    base.setdefault("rewrite_reason", base.get("problem", ""))
    base.setdefault("recommendation_text", base.get("suggested_rewrite", ""))
    base.setdefault("negotiation_strategy", base.get("negotiation_position", ""))
    return base


def check_agent_authority(
    *, text: str, clauses: list[Any] | None, entity_resolution: Any = None,
) -> list[dict[str, Any]]:
    body = str(text or "")
    if not (_RX_AGENT_PARTY.search(body) and _RX_AGENT_SCENARIO.search(body)):
        return []
    parties = list(getattr(entity_resolution, "parties", []) or [])
    our = getattr(entity_resolution, "our_company", None)
    agent = next((p for p in parties if _RX_AGENT_PARTY.search(p.role_in_contract or "")), None)
    if agent is not None and our is not None and agent is our:
        return []  # 우리가 대리인 쪽이면 이 점검의 보호 대상이 아니다
    auth = [c for c in clauses or [] if _RX_AUTHORITY.search(_attr(c, "text"))]
    if not auth:
        return []
    art = _attr(auth[0], "article_number")
    same = [c for c in clauses or [] if _attr(c, "article_number") == art]
    has_proof = bool(_RX_PROOF.search(body))
    has_indemnity = bool(_RX_INDEMNITY.search(body))
    liability = next((c for c in same if _RX_DIRECT_ONLY.search(_attr(c, "text"))), None)
    if has_proof and has_indemnity and liability is None:
        return []

    agent_label = _agent_label(body, agent)
    # [2026-10-01 Triage 지시 4·17항] 권한 확인·권리 보증·권한 하자 시 책임이 이미 같은
    # 조에 있으면 추가 보증조항은 실익이 낮다 — 팀원 판단("아티스트 권한보증 → 유지")과
    # 같게 KEEP 으로 명시 판정한다. 법률관계(대리)는 KEEP 판정에도 그대로 근거로 싣는다.
    from runtime.review.issue_triage import _RX_AUTH_CONFIRM, _RX_AUTH_LIABILITY, _RX_AUTH_WARRANT

    article_text = "\n".join(_attr(c, "text") for c in same)
    if (_RX_AUTH_CONFIRM.search(article_text) and _RX_AUTH_WARRANT.search(article_text)
            and _RX_AUTH_LIABILITY.search(article_text)):
        anchor = same[0]
        return [_finding(
            anchor,
            check_id="ac_agent_authority",
            problem=(f"{_p(agent_label, '이', '가')} 권리자 본인이 아닐 수 있는 3자 구조 — 작품의 제품화·판매·"
                     "이미지 이용 권한을 대리로 받는지 점검했다."),
            legal_business_reason=(
                "권한 위임 확인, 제품화·판매·전시·홍보·이미지 이용·독점성에 관한 권한 확보 보증, 권한 하자 시 "
                f"{agent_label}의 해결·손해 부담이 이미 규정되어 있어 현행 유지가 적정합니다."
            ),
            suggested_rewrite=None,
            keep_as_is=True,
            triage="KEEP",
            keep_reason=("권한 확인·권리 보증·권한 하자 시 책임이 이미 같은 조에 규정되어 있다 — "
                         "추가 보증조항을 신설할 실익이 낮다"),
            display_kind="keep",
            detected_issue_list=[{"issue_title": "갤러리·에이전시 대리 권한 및 권리 보증"}],
            related_clause_paths=[_attr(c, "display_path") for c in same
                                  if _RX_AUTHORITY.search(_attr(c, "text")) or _RX_DIRECT_ONLY.search(_attr(c, "text"))
                                  or _RX_AUTH_LIABILITY.search(_attr(c, "text"))],
        )]
    our_label = (our.label if our is not None and our.label else "당사")
    m_principal = _RX_PRINCIPAL.search(" ".join(_attr(c, "text") for c in same))
    principal = m_principal.group(0) if m_principal else "권리자"
    anchor = liability or same[-1]
    gaps = []
    if not has_proof:
        gaps.append(f"{principal}로부터 권한을 위임받았음을 증명하는 서면(위임장·확인서) 제출 의무가 없음")
    if liability is not None:
        gaps.append("권한 하자 시 배상 범위가 '직접적인 손해'로 한정돼 판매중단·제품 회수 비용이 빠질 수 있음")
    if not has_indemnity:
        gaps.append(f"제3자 이의·청구에 대해 {_p(agent_label, '이', '가')} 자기 비용으로 해결하고 {_p(our_label, '을', '를')} 면책할 의무가 없음")
    next_no = max([int(_attr(c, "paragraph_number")) for c in same if _attr(c, "paragraph_number").isdigit()] or [0]) + 1
    circled = "①②③④⑤⑥⑦⑧⑨⑩"
    rev_liability = (
        f"{agent_label}의 권한 부재 또는 권리관계의 하자로 제3자와 분쟁이 발생하거나 {our_label}에 이의가 "
        f"제기되는 경우, {_p(agent_label, '은', '는')} 자신의 비용과 책임으로 이를 해결하고 {_p(our_label, '을', '를')} 면책하며, 그로 "
        f"인하여 {our_label}에게 발생한 손해(제품 회수·판매 중단에 따른 비용을 포함한다)를 배상한다."
    )
    rev_proof = (
        f"{_p(agent_label, '은', '는')} 본 계약 체결 시 {principal}로부터 본 계약에서 정한 작품의 제작·제품화·판매·전시·"
        f"홍보·이미지 이용 및 독점성에 관한 권한을 위임받았음을 증명하는 서면(위임장 또는 {principal} "
        f"확인서)을 {our_label}에 제출한다."
    )
    parts = []
    if liability is not None or not has_indemnity:
        parts.append(rev_liability)
    if not has_proof:
        parts.append(f"{circled[next_no - 1] if 0 < next_no <= 10 else ''} {rev_proof}".strip())
    return [_finding(
        anchor,
        check_id="ac_agent_authority",
        problem=(f"{_p(agent_label, '이', '가')} {principal} 본인이 아닐 수 있는 구조인데 " + "; ".join(gaps) + "."),
        legal_business_reason=(
            f"{_p(principal, '이', '가')} 위임을 부인하면 제품화·판매·홍보 이용이 {principal}에게 효력이 없어 판매 중단과 "
            f"제3자 클레임이 {our_label}에 돌아오고, 현재 문언으로는 그 비용을 회복하기 어렵습니다."
        ),
        suggested_rewrite="\n".join(parts),
        location_instruction=(
            f"{_attr(anchor, 'display_path')}을 다음과 같이 수정"
            + (f"하고 제{art}조 제{next_no}항으로 추가" if not has_proof else "")
        ),
        negotiation_position=(
            f"권한 증빙과 면책은 {_p(agent_label, '이', '가')} 이미 {principal}로부터 받아 두었어야 하는 것이라 "
            "수용 부담이 작습니다. 증빙 제출을 먼저 요구하고, 배상 범위 확대는 제품 회수 비용에 한정해 제시합니다."
        ),
        detected_issue_list=[{"issue_title": "갤러리·에이전시 권한 증빙 및 권리하자 시 면책·배상 범위 미흡"}],
        related_clause_paths=[_attr(c, "display_path") for c in same if _RX_AUTHORITY.search(_attr(c, "text"))
                              or _RX_DIRECT_ONLY.search(_attr(c, "text"))],
    )]


def check_unselected_allocation(
    *, clauses: list[Any] | None, entity_resolution: Any = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    our = getattr(entity_resolution, "our_company", None)
    our_names = [x for x in ((our.label, our.brand_name) if our is not None else ()) if x]
    for c in clauses or []:
        text = _attr(c, "text")
        if not _RX_ALLOCATION.search(text):
            continue
        for line in text.splitlines():
            if line.count("□") < 2 or _RX_CHECKED.search(line):
                continue
            options = [o.strip() for o in _RX_OPTION.findall(line) if o.strip()]
            ours = next((o for o in options if o in our_names), "")
            if not ours:
                continue  # 우리 안이 선택지에 없으면 기본안을 정할 근거가 없다
            subject = re.sub(r"[()（）]", "", _attr(c, "title") or "").strip() or "권리"
            if "다음 주체에게" in text:
                revised = text.replace(line, "").replace("다음 주체에게", f"{ours}에게")
                revised = re.sub(r"\n{2,}", "\n", revised).strip()
            else:
                revised = text.replace(line, line.replace(f"□ {ours}", f"■ {ours}", 1))
            out.append(_finding(
                c,
                check_id="ac_unselected_allocation",
                problem=(f"{subject} 귀속 주체 선택란({' / '.join(options)})이 하나도 선택되지 않아, "
                         "누구에게 귀속되는지 계약상 정해지지 않았다."),
                legal_business_reason=(
                    "선택란이 빈 채로 서명하면 계약금액을 다 지급한 뒤에도 귀속을 두고 다툼이 남고, 귀속을 전제로 한 "
                    "아카이브·전시 활용 조항의 근거도 흔들립니다. 서명 전에 한 곳을 선택해야 합니다."
                ),
                suggested_rewrite=revised,
                location_instruction=f"{_attr(c, 'display_path')}의 선택란을 다음과 같이 확정",
                negotiation_position=(
                    f"우리 회사 귀속({ours})을 기본안으로 제시합니다. 상위 지원사업 협약이 귀속 주체를 따로 정하고 "
                    "있으면 그 협약을 따릅니다."
                ),
                detected_issue_list=[{"issue_title": f"{subject} 귀속 주체가 선택되지 않음"}],
            ))
            break
    return out


_RX_UPPER_DOC = re.compile(r"상위\s*(?:지원사업\s*)?(?:사업\s*)?협약|사업\s*운영\s*(?:지침|기준)|운영\s*기준")
_RX_UPPER_PRIORITY = re.compile(r"우선\s*(?:반영|적용)|준수한다|따른다|따라\s*정한다")
_RX_UPPER_ATTACHED = re.compile(
    r"(?:별첨|첨부|사본)[^.\n]{0,25}(?:협약|운영)|(?:협약|운영\s*기준|운영\s*지침)[^.\n]{0,25}(?:별첨|첨부|사본|제공한다)"
)
_RX_RIGHTS_WORDS = re.compile(r"저작권|이용권|권리관계|지식재산")


def check_upper_agreement(
    *, text: str, clauses: list[Any] | None, entity_resolution: Any = None,
) -> list[dict[str, Any]]:
    """지시 17항 "지원사업 상위기준 → SHOULD FIX" — 계약 밖의 문서(상위 협약·운영기준)가
    권리관계·정산을 **우선**하는데 그 내용이 계약에 붙어 있지 않으면, 서명 뒤에 모르는 기준이
    이용권·정산을 바꿀 수 있다. 첨부·제공 장치가 있으면 만들지 않는다."""
    body = str(text or "")
    if not _RX_UPPER_DOC.search(body) or _RX_UPPER_ATTACHED.search(body):
        return []
    cands = [c for c in clauses or []
             if _RX_UPPER_DOC.search(_attr(c, "text")) and _RX_UPPER_PRIORITY.search(_attr(c, "text"))]
    if not cands:
        return []
    cands.sort(key=lambda c: -len(_RX_RIGHTS_WORDS.findall(_attr(c, "text"))))
    anchor = cands[0]
    our = getattr(entity_resolution, "our_company", None)
    our_label = (our.label if our is not None and our.label else "당사")
    addition = (
        "상위 지원사업 협약 및 운영기준 중 본 계약의 권리관계·정산에 적용되는 조건은 계약 체결 시 별첨으로 "
        f"첨부하며, 별첨에 없는 조건을 이유로 {our_label}의 이용권을 제한하려면 당사자가 사전에 서면으로 합의한다."
    )
    original = _attr(anchor, "text")
    return [_finding(
        anchor,
        check_id="ac_upper_agreement",
        problem=("상위 지원사업 협약·운영기준이 이 계약의 권리관계에 우선 적용되도록 되어 있으나, 그 기준의 "
                 "내용이 계약에 첨부·특정되어 있지 않다."),
        legal_business_reason=(
            "서명 시점에 확인하지 못한 외부 기준이 이용권·정산을 우선하므로, 제품화 이후에 이용 범위가 줄거나 "
            "정산 조건이 바뀌어도 계약만으로는 다툴 근거가 약합니다."
        ),
        suggested_rewrite=f"{original.rstrip()} {addition}",
        location_instruction=f"{_attr(anchor, 'display_path')} 말미에 다음 문구 추가",
        negotiation_position="상위 협약 사본의 첨부는 관계기관 자료라 상대방 부담이 거의 없습니다.",
        detected_issue_list=[{"issue_title": "상위 지원사업 협약·운영기준이 우선 적용되나 그 내용이 계약에 첨부되지 않음"}],
    )]


def run_authority_selection_checks(
    *, text: str, clauses: list[Any] | None, entity_resolution: Any = None,
) -> list[dict[str, Any]]:
    return (
        check_agent_authority(text=text, clauses=clauses, entity_resolution=entity_resolution)
        + check_unselected_allocation(clauses=clauses, entity_resolution=entity_resolution)
        + check_upper_agreement(text=text, clauses=clauses, entity_resolution=entity_resolution)
    )


__all__ = ["check_agent_authority", "check_unselected_allocation", "run_authority_selection_checks"]
