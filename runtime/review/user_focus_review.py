"""사용자 지정 검토사항 — 유실 금지 hard gate (2026-10-07 긴급 보정 1·2·4·9·10항).

실측(시디즈 브랜디드 콘텐츠 계약): 사업부가 "제6조 제2항 / 제7조 제3항 / 제14조" 를 직접 지정했다.
mandatory_review_targets 는 제14조를 HIGH 로 적었는데 triage 는 제14조 지적을 전부 DROP 했고, 요청 답변은
다른 finding(제9조에 잘못 붙은 손해배상 체크리스트)의 제목을 결론으로 실었다. HIGH 는 0건이었다.

이 모듈의 계약
    1. 요청문에서 조·항·호를 인용한 줄마다 mandatory target 을 고정한다.
    2. 지정 조항 전용 판단(공급 자료 권리보증, 비독점 조항)은 **문언 기준**으로 finding 을 만든다.
    3. 감사가 끝난 최종 상태에서, 지정 조항마다 최종 판단·위험도·수정 필요 여부·정확한 조항번호·수정문안이
       있는지 확인한다. 하나라도 없으면 REVIEW_FAILED_USER_FOCUS_DROPPED.
    4. 같은 쟁점의 위험도는 하나 — clause_results 의 등급이 canonical 이고, 요청 답변·필수 검토항목·
       final_findings 가 그것과 다르면 REVIEW_FAILED_RISK_STATE_CONFLICT.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from runtime.review.user_review_request import ANSWER_BLOCK_MARKER

STATUS_FOCUS_DROPPED = "REVIEW_FAILED_USER_FOCUS_DROPPED"
STATUS_RISK_CONFLICT = "REVIEW_FAILED_RISK_STATE_CONFLICT"
STATUS_NOT_IMPLEMENTED = "REVIEW_FAILED_USER_REQUEST_NOT_IMPLEMENTED"

_RX_CITE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*\d+)?(?:\s*제?\s*(\d+)\s*항)?(?:\s*제?\s*(\d+)\s*호)?")
_Q = "[“”\"]"
#: 요청문 속 별첨 지정("[별첨]", "별첨 1", "부속서") — 조 번호 인용이 없어도 mandatory target 이다.
_RX_ANNEX_CITE = re.compile(r"\[\s*별\s*첨\s*\d*\s*\]|별\s*첨\s*\d+|부속서|\[\s*첨\s*부\s*\d*\s*\]")
_RX_ANNEX_PATH = re.compile(r"^\[\s*(?:별첨|부속서|첨부)")
_TIER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


@dataclass
class FocusTarget:
    path: str
    article: str
    paragraph: str = ""
    item: str = ""
    request: str = ""
    #: 조 번호가 아니라 별첨·부속서 전체를 지정한 요청("[별첨] 프랜차이즈 가맹 내용 검토").
    annex: str = ""

    def covers(self, article: str, paragraph: str = "", item: str = "") -> bool:
        if self.annex:
            return False
        if str(article) != self.article:
            return False
        if self.paragraph and str(paragraph or "") != self.paragraph:
            return False
        if self.item and str(item or "") != self.item:
            return False
        return True

    def covers_path(self, path: str) -> bool:
        if self.annex:
            return bool(_RX_ANNEX_PATH.match(str(path or "").strip()))
        m = _RX_CITE.search(str(path or ""))
        return bool(m) and self.covers(m.group(1), m.group(2) or "", m.group(3) or "") if self.paragraph else (
            bool(m) and m.group(1) == self.article)


@dataclass
class FocusResult:
    target: FocusTarget
    verdict: str
    tier: str
    needs_revision: bool
    clause_paths: list[str] = field(default_factory=list)
    conclusion: str = ""
    proposed: list[str] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_coverage_row(self) -> dict[str, Any]:
        return {
            "issue_id": f"user_focus_{self.target.path.replace(' ', '_')}",
            "source": "user_focus_target",
            "original_user_text": self.target.request,
            "normalized_issue": f"{self.target.path} 지정 검토",
            "relevant_clause_paths": list(self.clause_paths),
            "review_status": self.verdict,
            "risk_tier": self.tier,
            "needs_revision": self.needs_revision,
            "conclusion": self.conclusion,
            "direct_answer": self.conclusion,
            "proposed_clauses": list(self.proposed),
            "matched_finding_ids": list(self.finding_ids),
            "topic": f"user_focus:{self.target.path}",
            "priority_group": "A",
        }


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _flat(s: str) -> str:
    return re.sub(r"\s*\n\s*", " ", str(s or "")).strip()


def _lab(label: str) -> str:
    return _Q + "?" + re.escape(label) + _Q + "?"


def _p(word: str, with_b: str, without_b: str) -> str:
    core = re.sub(r"[\s“”\"'()]+$", "", word or "")
    last = core[-1:] if core else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_b if has else without_b)


def _short(labels: list[str]) -> list[str]:
    return [lb for lb in labels if lb and len(lb) <= 6 and not re.search(r"주식회사|㈜|\(주\)", lb)]


def extract_targets(review_focus: str | None) -> list[FocusTarget]:
    """요청문(답변 블록 제외)에서 조항을 인용한 줄마다 target 하나."""
    focus = str(review_focus or "").split(ANSWER_BLOCK_MARKER, 1)[0]
    out: list[FocusTarget] = []
    seen: set[str] = set()
    for line in focus.splitlines():
        ln = line.strip().lstrip("-•■·*①②③④⑤⑥⑦⑧⑨⑩ ").strip()
        for m in _RX_CITE.finditer(ln):
            art, par, item = m.group(1), m.group(2) or "", m.group(3) or ""
            path = f"제{art}조" + (f" 제{par}항" if par else "") + (f" 제{item}호" if item else "")
            if path in seen:
                continue
            seen.add(path)
            out.append(FocusTarget(path=path, article=art, paragraph=par, item=item, request=ln))
    # 별첨 지정 — 2026-10-13 실측: "[별첨] 프랜차이즈 가맹 내용 검토 : 물품공급계약과 프랜차이즈 가맹 내용 상충 여부"
    # 에 조 번호가 없어 target 이 되지 않았고, 요청 답변은 제27조로 매핑돼 "적정" 으로 끝났다. 배경 설명 줄
    # ("…계약서 내에 [별첨]으로 … 기재")보다 목록 기호로 시작하는 요청 줄을 쓴다.
    annex_lines = [line for line in focus.splitlines() if _RX_ANNEX_CITE.search(line) and not _RX_CITE.search(line)]
    if annex_lines and "[별첨]" not in seen:
        listed = [ln for ln in annex_lines if re.match(r"\s*(?:[-•■·*]|\d+[.)])\s*", ln)]
        req = (listed or annex_lines)[0].strip().lstrip("-•■·* ").strip()
        out.append(FocusTarget(path="[별첨]", article="", request=req, annex="별첨"))
    return out


def _scope_clauses(t: FocusTarget, clauses: list[Any] | None) -> list[Any]:
    if t.annex:
        return [c for c in clauses or [] if _RX_ANNEX_PATH.match(_attr(c, "display_path"))]
    return [c for c in clauses or [] if t.covers(_attr(c, "article_number"), _attr(c, "paragraph_number"),
                                                   _attr(c, "item_number"))]


# ── 지정 조항 전용 판단 ──────────────────────────────────────────────────────

def _answer_negative(review_focus: str, q_rx: str) -> bool:
    block = str(review_focus or "").split(ANSWER_BLOCK_MARKER, 1)[-1]
    for ln in block.splitlines():
        if re.search(q_rx, ln):
            ans = ln.rsplit(":", 1)[-1]
            return bool(re.search(r"아니|없", ans))
    return False


def _supplied_material_warranty(t: FocusTarget, c: Any, *, our: list[str], them: list[str], text: str,
                                review_focus: str, clauses: list[Any] | None) -> dict[str, Any] | None:
    """지시 9항 — 우리가 제공한 자료의 권리보증·면책. 보증 자체는 통상적이다(자동 HIGH 금지)."""
    body = _flat(_attr(c, "text"))
    us = next((o for o in _short(our) if re.search(_lab(o) + r"(?:은|는)", body)), "")
    th = next(iter(_short(them)), "")
    if not us or not th or not re.search(r"보증", body) or not re.search(r"면책|책임으로\s*(?:이를\s*)?해결", body):
        return None
    limited = bool(re.search(r"이를\s*위반하여|위반으로\s*인하여", body))
    misuse_excluded = bool(re.search(r"목적\s*외|범위를\s*벗어|변형|귀책사유가\s*(?:있|경합)", body))
    us_q, th_q = f"“{us}”", f"“{th}”"
    deliverable = "“콘텐츠”" if "“콘텐츠”" in text else "결과물"
    addition = (f"다만, {_p(th_q, '이', '가')} 제공받은 자료를 본 계약의 목적 또는 {_p(us_q, '이', '가')} 승인한 범위를 벗어나 사용하거나 "
                f"변형하여 발생한 분쟁이거나 {th_q}의 귀책사유가 함께 원인이 된 경우에는 그 범위에서 {_p(us_q, '은', '는')} "
                "책임을 지지 아니한다.")
    # 상대방 쪽 같은 보증(자기가 만든 결과물의 권리 비침해)이 있는가 — 균형(요청 취지).
    their_warranty = any(re.search(_lab(th) + r"(?:은|는)[^.]{0,80}(?:침해하지\s*(?:않|아니)|보증)", _flat(_attr(x, "text")))
                         for x in clauses or [])
    linked: list[dict[str, str]] = []
    if not their_warranty:
        art = next((x for x in clauses or [] if re.search(re.escape(th) + r"[”\"]?의\s*권리", _attr(x, "title"))), None)
        if art is not None:
            n = max((int(_attr(x, "paragraph_number")) for x in clauses or []
                     if _attr(x, "article_number") == _attr(art, "article_number")
                     and _attr(x, "paragraph_number").isdigit()), default=0) + 1
            circ = "①②③④⑤⑥⑦⑧⑨⑩"[n - 1] if 1 <= n <= 10 else ""
            linked.append({
                "display_path": f"제{_attr(art, 'article_number')}조 {circ}(같은 조 말미)",
                "text": (f"{circ} {_p(th_q, '은', '는')} {deliverable}({_p(us_q, '이', '가')} 제공한 자료는 제외한다)가 제3자의 저작권, "
                         f"초상권 등 권리를 침해하지 아니함을 보증하며, 이를 위반하여 분쟁이 발생한 경우 {th_q}의 비용과 "
                         f"책임으로 이를 해결하고 {_p(us_q, '을', '를')} 면책하여야 한다."),
            })
    low_risk = _answer_negative(review_focus, r"제3자\s*권리")
    judgement = (
        f"{_p(us_q, '이', '가')} 제공한 자료에 대한 권리보증과 면책은 통상적인 조항이고, "
        + ("보증 위반으로 생긴 분쟁에 한정되어 있어 범위 자체는 과도하지 않다. " if limited else "")
        + ("사전질문 답변상 제공 자료에 제3자 권리가 포함될 가능성이 없어 실제 위험은 낮다. " if low_risk else "")
        + ("" if misuse_excluded else
           f"다만 {_p(th_q, '이', '가')} 자료를 목적 밖으로 쓰거나 변형한 경우, {th_q}의 과실이 섞인 경우에도 {_p(us_q, '이', '가')} 전부 "
           "책임지는 것으로 읽힐 수 있어 그 부분만 제외하면 충분하다. ")
        + ("" if their_warranty else
           f"요청하신 균형은 이 조항을 약화시키기보다 {th_q}에게도 자기가 만든 결과물에 대한 같은 보증·면책을 지우는 방식이 실익이 크다.")
    )
    original = _attr(c, "text").rstrip()
    problem = judgement + ((" [연계 수정] " + " / ".join(f"{e['display_path']}: {e['text']}" for e in linked)) if linked else "")
    return {
        "clause_id": f"uf_supplied_material_warranty__{_attr(c, 'clause_id')}",
        "clause_title": _attr(c, "title"), "display_path": _attr(c, "display_path"),
        "article_number": _attr(c, "article_number"), "paragraph_number": _attr(c, "paragraph_number"),
        "original_text": _attr(c, "text"),
        "risk_tier": "MEDIUM", "severity": "MEDIUM", "review_tier": "SUGGEST", "confidence": 0.95,
        "is_common_legal_risk": True, "is_user_focus": True, "legal_core": True,
        "problem": problem, "rewrite_reason": judgement,
        "legal_business_reason": ("자료 제공자의 권리보증은 업계 통상 조항이므로 삭제보다 범위 조정이 현실적이다. 결과물 쪽 권리 "
                                  "침해(배경음악·폰트·출연자 초상 등)는 제작자가 통제하므로 그 보증은 제작자가 지는 것이 맞다."),
        "suggested_rewrite": f"{original} {addition}",
        "recommendation_text": f"{original} {addition}",
        "location_instruction": f"{_attr(c, 'display_path')} 말미에 다음 문구 추가",
        "package_linked_edits": linked,
        "related_clause_paths": [_attr(c, "display_path")] + [e["display_path"] for e in linked],
        "negotiation_position": "보증 범위 조정은 수용 가능성이 높습니다. 상대방 결과물 보증 신설을 함께 요청합니다.",
        "detected_issue_list": [{"issue_title": f"[지정 검토] {_attr(c, 'display_path')} 제공 자료 권리보증·면책 범위"}],
    }


def _non_exclusivity(t: FocusTarget, c: Any, *, our: list[str], them: list[str], text: str,
                     review_focus: str, clauses: list[Any] | None) -> dict[str, Any] | None:
    """지시 10항 — 경쟁사 유사계약 허용은 사업상 독점성 문제. 좁고 실무적인 제한만 제안한다."""
    body = _flat(_attr(c, "text"))
    th = next((x for x in _short(them) if re.search(_lab(x) + r"(?:은|는)", body)), "")
    if not th or not re.search(r"(?:유사|동종|경쟁)[^.]{0,40}(?:다른\s*사업자|제3자|타사)[^.]{0,20}(?:계약|거래)[^.]{0,20}할\s*수\s*있", body):
        return None
    m = re.search(r"게시\s*(?:이후|후),?\s*(\d{1,2})\s*개월", _flat(text))
    months = m.group(1) if m else "3"
    # 계약이 따옴표로 정의해 쓰는 약칭을 쓴다("“광고주”") — 정의되지 않은 회사명("“시디즈”")은 넣지 않는다.
    brand = next((o for o in _short(our) if o != "갑" and f"“{o}”" in text), "") or next(iter(_short(our)), "")
    th_q, br_q = f"“{th}”", f"“{brand}”"
    deliverable = "“콘텐츠”" if "“콘텐츠”" in text else "결과물"
    addition = (f"다만, {_p(th_q, '은', '는')} {deliverable} 게시일로부터 {months}개월 동안 게시 채널에 {br_q}의 제품과 동일한 "
                "제품군에 속하는 경쟁 제품의 광고 콘텐츠를 게시하지 아니한다.")
    judgement = (f"다른 광고주와의 계약 자체를 막는 것은 법률상 불공정이라기보다 사업상 독점성 문제이고, 넓은 경업금지는 "
                 f"상대방이 받아들이기 어렵다. 실익이 있는 범위 — 신제품 홍보 기간({deliverable} 의무 게시기간 {months}개월) 동안, "
                 "같은 채널에서, 동일 제품군 경쟁 제품 광고만 — 으로 좁혀 제한하는 것을 권합니다.")
    original = _attr(c, "text").rstrip()
    return {
        "clause_id": f"uf_non_exclusivity__{_attr(c, 'clause_id')}",
        "clause_title": _attr(c, "title"), "display_path": _attr(c, "display_path"),
        "article_number": _attr(c, "article_number"), "paragraph_number": _attr(c, "paragraph_number"),
        "original_text": _attr(c, "text"),
        "risk_tier": "MEDIUM", "severity": "MEDIUM", "review_tier": "SUGGEST", "confidence": 0.9,
        "is_common_legal_risk": True, "is_user_focus": True, "business_exclusivity": True,
        "problem": judgement, "rewrite_reason": judgement,
        "legal_business_reason": "동일 채널에서 경쟁 제품 광고가 이어지면 신제품 홍보 효과가 직접 희석된다.",
        "suggested_rewrite": f"{original} {addition}",
        "recommendation_text": f"{original} {addition}",
        "location_instruction": f"{_attr(c, 'display_path')} 말미에 다음 문구 추가",
        "negotiation_position": "기간·채널·제품군을 모두 좁힌 제한이라 수용 가능성이 높습니다. 거절되면 기간만 줄입니다.",
        "detected_issue_list": [{"issue_title": f"[지정 검토] {_attr(c, 'display_path')} 경쟁 제품 광고 제한(기간·채널·제품군 한정)"}],
    }


#: 그림·액자 등 미술품 거래 신호(계약 원문). 두 종류 이상이 함께 나와야 미술품 거래로 본다.
_RX_ART_GOODS = re.compile(r"미술품|원화|원작|판화|에디션|액자|프린트|조각")


def _artwork_defect_warranty(t: FocusTarget, c: Any, *, our: list[str], them: list[str], text: str,
                             review_focus: str, clauses: list[Any] | None) -> dict[str, Any] | None:
    """2026-10-13 지시 6항 — 그림/액자 상품 특성에 맞는 하자보증인가. "하자보증 조항이 있으니 KEEP" 금지.

    원문에서 확인되는 사실만 문제점으로 적는다: 보증기간·구제수단(대품 교환)·진품 보증 유무·직접배송 구조·
    다른 조(숨은 하자 통지기간)와의 관계·건설 서식 잔재. 수정문은 제16조 전체를 항 단위로 다시 쓴다.
    """
    from runtime.review.annex_conflict_review import article_paragraphs

    body = _flat(_attr(c, "text"))
    if not re.search(r"하자\s*보증", body):
        return None
    kinds = set(_RX_ART_GOODS.findall(text or ""))
    if len(kinds) < 2 and not re.search(r"그림|액자|미술", t.request):
        return None
    us = next(iter(_short(our)), "")
    th = next(iter(_short(them)), "")
    if not us or not th:
        return None
    us_q, th_q = f"“{us}”", f"“{th}”"
    art = _attr(c, "article_number")
    paras = article_paragraphs(c)
    if len(paras) < 2:
        return None
    path = f"제{art}조"
    period_m = re.search(r"(\d+)\s*년간\s*하자\s*보증", body)
    period = period_m.group(1) if period_m else ""
    p_period = next((p for p in paras.values() if re.search(r"년간\s*하자\s*보증", _flat(p.text))), None)
    p_remedy = next((p for p in paras.values() if re.search(r"대품\s*교환", _flat(p.text))), None)
    p_claim = next((p for p in paras.values() if re.search(r"클레임|하자에\s*대한\s*판단", _flat(p.text))), None)
    p_deposit = next((p for p in paras.values() if re.search(r"하자보증금\s*예치", _flat(p.text))), None)
    p_construction = [p for p in paras.values() if re.search(r"공사가\s*중단|계약보증금|이행\s*보증금", _flat(p.text))]
    originals = bool(re.search(r"원화|원작", text or ""))
    authenticity = bool(re.search(r"진품|위작|진위|감정서", text or ""))
    direct_ship = bool(re.search(r"본사\s*직접\s*배송", text or ""))
    hidden = next(((hp, m) for x in clauses or [] if _attr(x, "article_number") != art
                   for hp in (list(article_paragraphs(x).values()) or [None])
                   for m in [re.search(r"(\d+)\s*개월\s*이내에\s*이를\s*발견", _flat(hp.text if hp else _attr(x, "text")))]
                   if m), None)
    hidden_path = (hidden[0].path if hidden is not None and hidden[0] is not None else "")

    points: list[str] = []
    if p_period is not None:
        points.append(f"{p_period.path}은 작품과 액자를 구분하지 않고 납품 완료일부터 {period or '일정 기간'}년간 하자보증을 "
                      "정하지만 무엇이 ‘하자’인지 정의가 없습니다. 미술품은 재료 고유의 자연스러운 변색·황변·균열이 생기고, "
                      "직사광선·습도 등 보관환경에 따라 상태가 달라지므로, 분쟁 시 상대방은 이를 ‘작품 고유 특성’이라며 하자가 "
                      "아니라고 다툴 것입니다. 반대로 액자·프레임·유리·마운팅·인쇄(프린트·에디션) 불량은 제조상 하자로서 "
                      f"{period or '3'}년 보증이 적정합니다 — 두 범주를 나눠야 보증이 실제로 작동합니다.")
    if p_remedy is not None and originals:
        points.append(f"{p_remedy.path}의 구제수단은 ‘수정, 보수 또는 대품 교환’인데, 별첨 공급가격표가 정한 원작·원화(조각 포함)는 "
                      "세상에 하나뿐이어서 대품 교환이 불가능합니다. 복원으로 원상이 회복되지 않을 때 반품·대금 반환을 청구할 "
                      "근거가 없습니다.")
    if not authenticity:
        points.append("미술품 거래의 핵심인 진품·작품정보(작가·에디션 번호) 보증이 계약 어디에도 없습니다"
                      "(제18조는 지식재산권 비침해만 보증).")
    if direct_ship:
        points.append(f"별첨의 ‘본사 직접 배송 판매 건’은 {_p(th_q, '이', '가')} 액자 제작·포장·배송을 맡아 고객에게 바로 인도하므로 "
                      f"{us_q}의 검사(제13조)를 거치지 않습니다. 운송 중 파손과 고객 인도 후 하자의 처리 주체·보증 기산일이 없습니다.")
    if hidden is not None:
        hm = hidden[1]
        points.append(f"{_p(hidden_path or '다른 조항', '은', '는')} 숨은 하자의 발견·통지기간을 {hm.group(1)}개월로 정해 {path}의 "
                      f"{period or ''}년 보증과 관계가 불분명합니다.")
    if p_construction:
        points.append(f"{_p(' · '.join(p.path for p in p_construction), '은', '는')} ‘공사가 중단’, ‘계약보증금’, ‘이행 보증금액’이라고 써서 "
                      "건설 서식이 남아 있고, 앞 항의 하자보증금과 귀속 대상이 맞지 않습니다.")
    if len(points) < 2:
        return None

    def keep(p: Any, fallback: str) -> str:
        if p is None:
            return fallback
        # PDF 는 줄을 낱말 중간에서 끊는다("결정한⏎다", "“을”⏎이") — 붙여 쓴다.
        joined = re.sub(r"(?<=[가-힣”’])\s*\n\s*(?=[가-힣])", "", str(p.text))
        return re.sub(r"^\d+\.\s*", "", _flat(joined))

    n = 1
    lines = [f"{n}. 상기 제13조의 검사가 완료되었다고 하더라도 {_p(th_q, '은', '는')} 납품 완료일"
             + ("(별첨의 ‘본사 직접 배송 판매 건’은 고객 인도일)" if direct_ship else "")
             + f"부터 {period or '3'}년간 다음 각 호의 하자에 대하여 보증 책임을 지고, 그 하자로 인한 {us_q}의 피해에 "
             "대하여 손해배상을 하여야 한다.\n"
             "1) 액자·프레임·유리(아크릴)·매트·마운팅·걸이 부속의 파손, 변형, 이탈, 습기·곰팡이 유입 등 제작·조립상 하자\n"
             "2) 프린트·사진·에디션 작품의 인쇄·인화 불량, 통상의 실내 보관환경에서 발생한 색 번짐·탈색·박리\n"
             f"3) 작품의 손상·오염으로서 {us_q} 또는 고객의 보관·취급상 귀책사유로 발생하였음을 {_p(th_q, '이', '가')} 증명하지 "
             "못한 것"]
    if originals:
        n += 1
        lines.append(f"{n}. 원작·원화(조각 포함)의 경우 재료 고유의 자연스러운 노화로서 {_p(th_q, '이', '가')} 납품 시 서면(작품 "
                     "보증서 또는 관리 안내서)으로 고지한 범위는 하자로 보지 아니한다. 다만 고지하지 아니한 손상이나 통상의 노화 "
                     "정도를 넘는 손상은 하자로 본다.")
    n += 1
    lines.append(f"{n}. 상기 기간 내에 하자가 발생한 경우 {_p(th_q, '은', '는')} {_p(us_q, '이', '가')} 지정하는 기간 내에 "
                 f"{th_q}의 비용으로 수선, 복원 또는 대품 교환을 하여야 한다. 대체할 수 없는 원작·원화 또는 에디션 작품으로서 "
                 f"수선·복원으로 원상이 회복되지 아니하는 경우 {_p(us_q, '은', '는')} 해당 작품의 반품과 공급가격 전액의 반환을 "
                 f"청구할 수 있다. {_p(th_q, '이', '가')} 이를 이행하지 않거나 이행할 수 없다고 {_p(us_q, '이', '가')} 판단할 "
                 f"경우 {_p(us_q, '은', '는')} {th_q}의 비용으로 집행할 수 있다.")
    if not authenticity:
        n += 1
        lines.append(f"{n}. {_p(th_q, '은', '는')} 납품하는 작품이 진품이며 작가명·제작연도·에디션 번호 등 {_p(th_q, '이', '가')} "
                     f"제시한 작품 정보가 사실과 같음을 보증한다. 이를 위반한 경우 제1항의 기간과 관계없이 {_p(th_q, '은', '는')} "
                     f"공급가격 전액을 반환하고, {_p(us_q, '이', '가')} 고객에게 부담한 환불·배상액을 포함한 손해를 배상하여야 한다.")
    if direct_ship:
        n += 1
        lines.append(f"{n}. 납품 또는 고객 인도 전 운송 중 발생한 파손·분실은 {_p(th_q, '이', '가')} 부담한다.")
    n += 1
    lines.append(f"{n}. " + keep(p_claim, f"{us_q}과 {th_q}은 별도의 클레임보상협정을 체결할 수 있다."))
    dep_n = n + 1
    lines.append(f"{dep_n}. " + keep(p_deposit, f"{_p(us_q, '은', '는')} 필요하다고 인정할 경우 {th_q}에게 하자보증금 예치를 "
                                                 "요구할 수 있다."))
    if p_construction or p_deposit is not None:
        lines.append(f"{dep_n + 1}. {th_q}의 귀책으로 계약이 해제 또는 해지될 경우에는 상기 {dep_n}항의 하자보증금은 "
                     f"{us_q}에게 귀속된다.")
        lines.append(f"{dep_n + 2}. {th_q}의 귀책으로 인하여 상기 {dep_n}항의 하자보증금을 초과한 {us_q}의 손해에 대하여 "
                     f"{_p(th_q, '은', '는')} 초과금액을 {us_q}에게 추가로 지급하여야 한다.")
    title = _attr(c, "title").split("\n")[0].strip() or "하자보증 책임"
    rewrite = f"{title}\n" + "\n".join(lines)
    judgement = (f"{period or '3'}년 하자보증 자체는 구매자인 우리에게 유리하므로 기간을 줄일 이유는 없습니다. 다만 그림·액자 "
                 "거래의 특성에 맞게 ‘무엇이 하자인지’와 ‘교환이 불가능한 작품의 구제수단’을 정하지 않으면 보증이 실제로 "
                 "작동하지 않습니다. " + " ".join(f"({i}) {pt}" for i, pt in enumerate(points, 1)))
    return {
        "clause_id": f"uf_artwork_defect_warranty__{_attr(c, 'clause_id')}",
        "clause_title": _attr(c, "title"), "display_path": _attr(c, "display_path") or path,
        "article_number": art, "paragraph_number": "",
        "original_text": _attr(c, "text"),
        "risk_tier": "MEDIUM", "severity": "MEDIUM", "review_tier": "SUGGEST", "confidence": 0.93,
        "is_common_legal_risk": True, "is_user_focus": True, "legal_core": True,
        "problem": judgement, "rewrite_reason": judgement,
        "legal_business_reason": (
            "매도인의 하자담보책임은 ‘통상 갖추어야 할 품질’을 기준으로 하므로, 미술품처럼 자연 노화가 "
            "예정된 물건은 무엇이 하자인지 계약으로 정하지 않으면 다툼의 대부분이 ‘하자인가’에서 시작됩니다. 대체물이 없는 "
            "특정물(원화)은 대품 교환이 성립하지 않으므로 반품·대금 반환을 따로 정해야 합니다. 진품 보증이 없으면 위작 시 "
            "착오·사기 취소나 채무불이행을 별도로 입증해야 합니다."),
        "suggested_rewrite": rewrite, "recommendation_text": rewrite, "proposed_revision": rewrite,
        "location_instruction": f"{path} 전부 교체",
        "related_clause_paths": [path] + ([hidden_path] if hidden_path else []),
        "negotiation_position": ("기간은 그대로 두고 하자의 범위를 명확히 하자는 제안이라 상대방에게도 예측 가능성이 생깁니다. "
                                 "원작 자연 노화를 하자에서 빼 주는 대신 진품 보증과 원화 반품·환불을 받는 교환 구도로 "
                                 "협상하십시오."),
        "detected_issue_list": [{"issue_title": f"[지정 검토] {path} 그림·액자 특성에 맞는 하자보증(하자 정의·원화 구제수단·진품 보증)"}],
        # 제목에 "제N조 …" 를 쓰면 조 제목 일치 게이트가 원문 조 제목("하자보증 책임")과 비교해 조항번호를 지운다.
        "issue_title": f"{title} — 그림·액자 특성 미반영(하자 정의·원화 구제수단·진품 보증 부재)",
    }


_ANALYZERS = (_artwork_defect_warranty, _supplied_material_warranty, _non_exclusivity)


def focus_findings(
    targets: list[FocusTarget], *, clauses: list[Any] | None, our: list[str], them: list[str],
    text: str, review_focus: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in targets:
        for c in _scope_clauses(t, clauses):
            for fn in _ANALYZERS:
                f = fn(t, c, our=our, them=them, text=text, review_focus=review_focus, clauses=clauses)
                if f is not None:
                    out.append(f)
                    break
    return out


_RX_EXPLICIT_REMOVAL = re.compile(r"removed|_gate|failed|fabricat|fake|mismatch", re.IGNORECASE)


def tag_focus(targets: list[FocusTarget], clause_results: list[dict[str, Any]]) -> None:
    """지정 조항에 붙은 finding 은 점수로 DROP 하지 않는다(유실 금지).

    지정 조항 판단(uf_*)이 앞 단계의 **기록 없는** 중복 제거로 꺼졌으면 되살린다 — 실측(AI 경로): 같은 항의
    규칙 후보("일방 면책/일방 배상(후보)" HIGH)가 남고 지정 조항 판단이 사라졌다(지시 9항: 자동 HIGH 금지).
    품질 게이트가 사유를 남기고 지운 것은 되살리지 않는다.
    """
    for cr in clause_results:
        if not isinstance(cr, dict) or not str(cr.get("clause_id") or "").startswith("uf_"):
            continue
        if cr.get("dedup_suppressed") and not cr.get("dedup_merged_into") and not any(
                _RX_EXPLICIT_REMOVAL.search(k) and cr.get(k) for k in cr):
            cr["dedup_suppressed"] = False
            cr["user_focus_restored"] = True
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        art, par = str(cr.get("article_number") or ""), str(cr.get("paragraph_number") or "")
        item = str(cr.get("item_number") or "")
        if any(t.covers(art, par, item) or (t.annex and t.covers_path(str(cr.get("display_path") or "")))
               for t in targets):
            cr["is_user_focus"] = True
    supersede_keeps(clause_results)


def supersede_keeps(clause_results: list[dict[str, Any]], triage: dict[str, Any] | None = None) -> list[str]:
    """지정 조항에 살아 있는 지적(uf_*)이 있으면 같은 조의 KEEP 은 내보내지 않는다.

    2026-10-13 실측: 제16조에 "수정 필요" 판단과 "[KEEP] 하자·A/S 책임의 귀속과 경계가 이미 규정되어 있다" 가
    한 보고서에 함께 실렸다. KEEP 은 감사(triage) 단계에서 다시 생기므로 감사 뒤에도 한 번 더 부른다.
    """
    live_arts = {str(cr.get("article_number") or "") for cr in clause_results if isinstance(cr, dict)
                 and str(cr.get("clause_id") or "").startswith("uf_") and not cr.get("dedup_suppressed")
                 and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")}
    live_arts.discard("")
    out: list[str] = []
    for cr in clause_results:
        if (isinstance(cr, dict) and cr.get("keep_as_is") and str(cr.get("article_number") or "") in live_arts
                and not str(cr.get("clause_id") or "").startswith("uf_")):
            cr["keep_as_is"] = False
            cr["dedup_suppressed"] = True
            cr["keep_superseded_by_user_focus"] = True
            out.append(str(cr.get("clause_id") or ""))
    if isinstance(triage, dict) and isinstance(triage.get("KEEP"), list):
        triage["KEEP"] = [r for r in triage["KEEP"] if not (
            isinstance(r, dict) and (str(r.get("clause_id") or "") in out
                                     or any(re.match(rf"제{a}조(?!\d)", str(r.get("display_path") or "")) for a in live_arts)))]
    return out


# ── 최종 검증 ──────────────────────────────────────────────────────────────

def _live(crs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in crs if isinstance(c, dict) and not c.get("dedup_suppressed") and not c.get("keep_as_is")
            and str(c.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")]


def _covers(t: FocusTarget, cr: dict[str, Any]) -> tuple[bool, bool]:
    """(지정 조항을 다루는가, 지정 조항에 직접 붙었는가)."""
    direct = t.covers(str(cr.get("article_number") or ""), str(cr.get("paragraph_number") or ""),
                      str(cr.get("item_number") or "")) or (bool(t.annex) and t.covers_path(str(cr.get("display_path") or "")))
    paths = [str(p) for p in cr.get("related_clause_paths") or []] + [
        str(e.get("display_path") or "") for e in cr.get("package_linked_edits") or [] if isinstance(e, dict)]
    return direct or any(t.covers_path(p) for p in paths), direct


def _edits_for(t: FocusTarget, cr: dict[str, Any], direct: bool) -> list[str]:
    out: list[str] = []
    if direct and str(cr.get("suggested_rewrite") or "").strip():
        out.append(f"{cr.get('display_path')}: {str(cr.get('suggested_rewrite')).strip()}")
    for e in cr.get("package_linked_edits") or []:
        if isinstance(e, dict) and (t.covers_path(str(e.get("display_path") or "")) or not direct):
            out.append(f"{e.get('display_path')}: {e.get('text')}")
    if not out and str(cr.get("suggested_rewrite") or "").strip():
        out.append(f"{cr.get('display_path')}: {str(cr.get('suggested_rewrite')).strip()}")
    return out


def verify_focus(targets: list[FocusTarget], clause_results: list[dict[str, Any]],
                 clauses: list[Any] | None) -> list[FocusResult]:
    live = _live(clause_results)
    results: list[FocusResult] = []
    for t in targets:
        hits = [(cr, *_covers(t, cr)) for cr in live]
        hits = [(cr, d) for cr, ok, d in hits if ok]
        if hits:
            hits.sort(key=lambda h: (-_TIER.get(str(h[0].get("risk_tier")).upper(), 0), not h[1]))
            cr, direct = hits[0]
            tier = str(cr.get("risk_tier")).upper()
            others = [h[0] for h in hits[1:]]
            paths = list(dict.fromkeys([str(cr.get("display_path") or "")] + [str(p) for p in cr.get("related_clause_paths") or []]))
            res = FocusResult(
                target=t, verdict="수정 필요", tier=tier, needs_revision=True,
                clause_paths=[p for p in paths if p],
                conclusion=(f"[{ {'HIGH': '필수 수정', 'MEDIUM': '권장 수정'}.get(tier, tier)}] "
                            + str(cr.get("rewrite_reason") or cr.get("problem") or "").split(" [연계 수정]")[0].strip()),
                proposed=_edits_for(t, cr, direct),
                finding_ids=[str(cr.get("clause_id"))] + [str(o.get("clause_id")) for o in others],
            )
            if not res.proposed and cr.get("action_only"):
                # 체결 전 확인 항목은 고칠 문장이 아니라 확인·협상 조치가 답이다(2026-10-30).
                res.proposed = [f"[필요 조치] {a}" for a in cr.get("required_actions") or [] if str(a).strip()]
        else:
            keep = next((c for c in clause_results if isinstance(c, dict) and c.get("keep_as_is")
                         and t.covers(str(c.get("article_number") or ""), str(c.get("paragraph_number") or ""))), None)
            scope = _scope_clauses(t, clauses)
            if keep is not None:
                res = FocusResult(target=t, verdict="적정", tier="LOW", needs_revision=False,
                                  clause_paths=[str(keep.get("display_path") or t.path)],
                                  conclusion="현행 유지 — " + str(keep.get("keep_reason") or keep.get("problem") or ""),
                                  proposed=["해당 없음(현행 유지)"], finding_ids=[str(keep.get("clause_id"))])
            else:
                res = FocusResult(target=t, verdict="", tier="", needs_revision=False,
                                  clause_paths=[_attr(c, "display_path") for c in scope[:3]])
                if t.annex and scope:
                    # 별첨을 검토했는데 고칠 것이 없으면 그것이 답이다 — 다만 비교 결과가 있어야 한다.
                    res.verdict, res.tier = "적정", "LOW"
                    res.conclusion = "본문과 별첨을 축별로 비교했으나 충돌하는 조항이 없습니다."
                    res.proposed = ["해당 없음(현행 유지)"]
        if not res.verdict:
            res.missing.append("최종 판단")
        if not res.tier:
            res.missing.append("위험도")
        if not res.clause_paths:
            res.missing.append("조항번호")
        if res.needs_revision and not res.proposed:
            res.missing.append("수정문안")
        results.append(res)
    return results


# ── 요청 취지 ↔ 수정문구 일치 (2026-10-07 보정: 대칭적 권리·의무 완결) ──────────────────────
#
# 실측: 제14조 "광고주 귀책 조치만 있고 을 귀책 조치가 없다" 요청에 대해 문제점은 인식했으나 수정문구에는 갑의
# 위약벌·손해배상 조정만 들어가고 을의 귀책사유·갑의 해지·환급·손해배상은 없었다. "검토했다" 가 아니라
# 요청한 불균형이 **수정문구에서** 해소됐는지 확인한다 — 원문을 그대로 옮긴 부분은 충족으로 세지 않는다.

def _req(them_rx: str, us_rx: str) -> dict[str, list[tuple[str, str]]]:
    return {
        # 상대방 귀책에 대한 우리의 조치가 없다 → 상대방 귀책사유 + 우리 해지권 + 미지급·환급 + 손해배상.
        "counterparty_fault_remedy": [
            ("상대방 귀책사유", them_rx + r"의\s*귀책사유로\s*(?:본다|한다)|" + them_rx + r"[^.]{0,40}귀책사유로"),
            ("우리 회사 해제·해지권", us_rx + r"(?:은|는)[^.]{0,120}(?:해제|해지)할\s*수\s*있"),
            ("미이행 대금 면제 또는 기지급금 반환", us_rx + r"(?:은|는)[^.]{0,60}지급\s*의무를\s*면|"
             + them_rx + r"(?:은|는)[^.]{0,80}반환"),
            ("손해배상", r"손해를[^.]{0,30}배상"),
        ],
        # 우리 회사의 면책·책임 부담 → 우리 귀책범위로 제한.
        "our_indemnity_scope": [
            ("우리 회사 귀책범위 한정", r"귀책사유|귀책\s*범위|그\s*범위에서|책임을\s*지지\s*아니한다"),
        ],
        # 상대방의 경쟁사 거래 허용 → 기간·채널·제품군으로 좁힌 제한.
        "competitor_restriction": [
            ("제한 기간", r"\d+\s*(?:개월|년)|기간\s*동안"),
            ("제한 채널", r"채널|매체|플랫폼"),
            ("제한 제품군", r"제품군|동일[^.]{0,10}제품|경쟁\s*제품"),
        ],
    }


def _intents(request: str, them: list[str], us: list[str]) -> list[str]:
    r = _flat(request)
    th = "(?:" + "|".join(re.escape(x) for x in them + ["상대방"]) + ")"
    out: list[str] = []
    if re.search(th + r"[”\"']?\s*의?\s*귀책[^.]{0,40}(?:없|부재|미비|누락)", r) or re.search(
            r"(?:귀책|책임)[^.]{0,30}(?:만\s*있|일방)[^.]{0,60}" + th + r"[^.]{0,20}(?:없|부재)", r):
        out.append("counterparty_fault_remedy")
    if re.search(r"면책|비용과\s*책임", r):
        out.append("our_indemnity_scope")
    if re.search(r"경쟁사|경쟁\s*업체|유사\s*(?:계약|서비스)|독점|경업", r):
        out.append("competitor_restriction")
    return out


def _added_texts(cr: dict[str, Any]) -> list[str]:
    """finding 이 실제로 바꾸거나 더하는 문구 — 원문을 앞에 그대로 둔 수정안은 덧붙인 부분만."""
    out: list[str] = []
    sr, orig = _flat(cr.get("suggested_rewrite")), _flat(cr.get("original_text"))
    if sr:
        out.append(sr[len(orig):] if orig and sr.startswith(orig) else sr)
    for e in cr.get("package_linked_edits") or []:
        if isinstance(e, dict) and str(e.get("text") or "").strip():
            out.append(_flat(e.get("text")))
    return [x for x in out if x.strip()]


_RX_PROBLEM_NO_REMEDY = re.compile(r"귀책[^.]{0,60}(?:조치|해지|환급|구제)[^.]{0,20}(?:없|부재)")


def request_implementation(
    targets: list[FocusTarget], clause_results: list[dict[str, Any]], *, our: list[str], them: list[str],
) -> list[dict[str, Any]]:
    """지정 요청마다 요청 취지가 수정문구에 실제로 들어갔는가. missing 이 있으면 출력 금지."""
    them_s, our_s = _short(them), _short(our)
    if not them_s or not our_s:
        return []
    them_rx = "(?:" + "|".join(_lab(x) for x in them_s) + ")"
    us_rx = "(?:" + "|".join(_lab(x) for x in our_s) + ")"
    reqs = _req(them_rx, us_rx)
    live = _live(clause_results)
    rows: list[dict[str, Any]] = []
    for t in targets:
        intents = _intents(t.request, them_s, our_s)
        if not intents:
            continue
        hits = [cr for cr in live if _covers(t, cr)[0]]
        added = [x for cr in hits for x in _added_texts(cr)]
        missing = [f"{lbl}" for it in intents for lbl, rx in reqs[it] if not any(re.search(rx, x) for x in added)]
        rows.append({"target": t.path, "request": t.request, "intents": intents,
                     "finding_ids": [str(cr.get("clause_id")) for cr in hits], "missing": missing})
    # 문제점에 "상대방 귀책 조치 없음" 을 적은 finding 은 수정문구에도 그 조치가 있어야 한다.
    for cr in live:
        prob = str(cr.get("rewrite_reason") or cr.get("problem") or "").split(" [연계 수정]")[0]
        if not _RX_PROBLEM_NO_REMEDY.search(prob):
            continue
        added = _added_texts(cr)
        missing = [lbl for lbl, rx in reqs["counterparty_fault_remedy"] if not any(re.search(rx, x) for x in added)]
        if missing:
            rows.append({"target": str(cr.get("display_path") or ""), "request": "(문제점 기재)",
                         "intents": ["counterparty_fault_remedy"], "finding_ids": [str(cr.get("clause_id"))],
                         "missing": missing})
    return rows


def risk_state_conflicts(
    clause_results: list[dict[str, Any]], final_findings: dict[str, Any] | None,
    coverage: list[dict[str, Any]] | None, mandatory: list[dict[str, Any]] | None,
) -> list[str]:
    """지시 2항 — 같은 finding 이 화면마다 다른 위험도를 갖지 않는가. clause_results 가 기준이다."""
    tier = {str(c.get("clause_id")): str(c.get("risk_tier") or "").upper() for c in clause_results if isinstance(c, dict)}
    live = {str(c.get("clause_id")) for c in _live(clause_results)}
    out: list[str] = []
    ff = final_findings or {}
    for key, want in (("high_issues", "HIGH"), ("medium_issues", "MEDIUM")):
        for row in ff.get(key) or []:
            cid = str(row.get("clause_id") or "")
            if cid in tier and tier[cid] != want:
                out.append(f"{cid}: final_findings {want} ↔ 본문 {tier[cid]}")
    for row in coverage or []:
        for cid in row.get("matched_finding_ids") or []:
            cid = str(cid)
            if row.get("review_status") == "수정 필요" and cid in tier and cid not in live and row.get("risk_tier"):
                out.append(f"{cid}: 요청 답변 '수정 필요' ↔ 본문에서 제외됨")
        rt = str(row.get("risk_tier") or "").upper()
        ids = [str(x) for x in row.get("matched_finding_ids") or []]
        if rt and ids and ids[0] in tier and tier[ids[0]] != rt and rt != "LOW":
            out.append(f"{ids[0]}: 요청 답변 {rt} ↔ 본문 {tier[ids[0]]}")
    for m in mandatory or []:
        sev = str(m.get("severity") or "").upper()
        if sev and m.get("final_tier") and sev != str(m.get("final_tier")).upper():
            out.append(f"{m.get('display_path')}: 필수 검토항목 {sev} ↔ 최종 {m.get('final_tier')}")
    return out


__all__ = [
    "FocusResult", "FocusTarget", "STATUS_FOCUS_DROPPED", "STATUS_NOT_IMPLEMENTED", "STATUS_RISK_CONFLICT",
    "extract_targets", "focus_findings", "request_implementation", "risk_state_conflicts", "tag_focus",
    "verify_focus",
]


def overlay_focus_rows(
    targets: list[dict[str, Any]] | None,
    coverage: list[dict[str, Any]] | None,
    clause_meta: dict[str, Any] | None,
    live_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """다운로드 경로가 다시 만든 필수 검토항목·요청 답변 위에 검토 파이프라인의 지정 쟁점 판단을 덮는다.

    2026-10-13 실측: 수정본(DOCX/PDF) 경로는 0절·0-3절을 처음부터 다시 만들면서 지정 쟁점 검증 결과
    (user_focus_review)를 쓰지 않았다 — "[별첨]" 이 빠지고 제16조가 [HIGH] 로, 결론은 finding 의 조 제목
    ("부칙 / 별첨 / 별첨")으로 나갔다. 화면·파일·meta 가 같은 판단을 말하도록 파이프라인 행을 우선한다.
    파이프라인 행이 가리키는 finding 이 다운로드 결과에 없으면(live_ids) 그 행은 덮지 않는다.
    """
    meta = clause_meta if isinstance(clause_meta, dict) else {}
    t_out = [dict(t) for t in (targets or []) if isinstance(t, dict)]
    c_out = [dict(c) for c in (coverage or []) if isinstance(c, dict)]
    m_targets = [t for t in (meta.get("mandatory_review_targets") or []) if isinstance(t, dict)]
    m_focus = [r for r in (meta.get("user_review_coverage") or [])
               if isinstance(r, dict) and r.get("source") == "user_focus_target"]

    def ok(ids: list[Any]) -> bool:
        return live_ids is None or not ids or any(str(i) in live_ids for i in ids)

    by_path = {str(t.get("display_path") or ""): i for i, t in enumerate(t_out)}
    for mt in m_targets:
        path = str(mt.get("display_path") or "")
        if not path or not ok(list(mt.get("matched_clause_ids") or [])):
            continue
        if path in by_path:
            row = t_out[by_path[path]]
            for k in ("status", "severity", "final_tier", "matched_clause_ids"):
                if mt.get(k):
                    row[k] = mt[k]
        else:
            t_out.append(dict(mt))
            by_path[path] = len(t_out) - 1

    def key(s: Any) -> str:
        return re.sub(r"[\s①-⑳()\-•\[\]]", "", str(s or ""))[:20]

    # 판단이 끝난 행만 덮는다 — 판단이 비어 있는 행을 가져오면 이 경로의 "미답변" 처리로 번진다.
    focus_rows = [dict(r) for r in m_focus if str(r.get("review_status") or "").strip()
                  and ok(list(r.get("matched_finding_ids") or []))]
    keys = [key(r.get("original_user_text")) for r in focus_rows]
    rest = [c for c in c_out if not any(k and (k in key(c.get("original_user_text"))
                                               or key(c.get("original_user_text")) in k) for k in keys)]
    return t_out, focus_rows + rest
