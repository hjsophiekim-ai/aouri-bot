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

_RX_CITE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*\d+)?(?:\s*제?\s*(\d+)\s*항)?(?:\s*제?\s*(\d+)\s*호)?")
_Q = "[“”\"]"
_TIER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


@dataclass
class FocusTarget:
    path: str
    article: str
    paragraph: str = ""
    item: str = ""
    request: str = ""

    def covers(self, article: str, paragraph: str = "", item: str = "") -> bool:
        if str(article) != self.article:
            return False
        if self.paragraph and str(paragraph or "") != self.paragraph:
            return False
        if self.item and str(item or "") != self.item:
            return False
        return True

    def covers_path(self, path: str) -> bool:
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
    return out


def _scope_clauses(t: FocusTarget, clauses: list[Any] | None) -> list[Any]:
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


_ANALYZERS = (_supplied_material_warranty, _non_exclusivity)


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
        if any(t.covers(art, par, item) for t in targets):
            cr["is_user_focus"] = True


# ── 최종 검증 ──────────────────────────────────────────────────────────────

def _live(crs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in crs if isinstance(c, dict) and not c.get("dedup_suppressed") and not c.get("keep_as_is")
            and str(c.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")]


def _covers(t: FocusTarget, cr: dict[str, Any]) -> tuple[bool, bool]:
    """(지정 조항을 다루는가, 지정 조항에 직접 붙었는가)."""
    direct = t.covers(str(cr.get("article_number") or ""), str(cr.get("paragraph_number") or ""),
                      str(cr.get("item_number") or ""))
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
    "FocusResult", "FocusTarget", "STATUS_FOCUS_DROPPED", "STATUS_RISK_CONFLICT",
    "extract_targets", "focus_findings", "risk_state_conflicts", "tag_focus", "verify_focus",
]
