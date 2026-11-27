"""거래 전체 판단·요청 답변의 보고서 문장 — DOCX·PDF 가 같은 줄을 그린다 (2026-10-30).

DOCX 와 PDF 가 각자 문장을 만들면 한쪽만 고쳐지는 일이 반복됐다(report_header 가 생긴 이유와 같다).
여기서는 (종류, 문장, 색) 줄 목록만 만들고, 그리는 일은 각 렌더러가 한다.
    종류: heading · bold · text · bullet · note
    색:   high · medium · low · ""
"""
from __future__ import annotations

from typing import Any

Line = tuple[str, str, str]

SECTION_TITLE = "0-1. 거래 전체 판단 (조항 검토의 전제)"
_CAT_TONE = {"필수수정": "high", "체결 전 확인": "medium", "권장수정": "medium", "수용 가능한 위험": "low"}
_VERDICT_TONE = {"effective": "low", "conditional": "medium", "partial": "medium", "weak": "high"}
_CATEGORY_ORDER = ("필수수정", "체결 전 확인", "권장수정", "수용 가능한 위험")


def _s(v: Any) -> str:
    return str(v or "").strip()


def deal_section_lines(deal: dict[str, Any] | None) -> list[Line]:
    if not isinstance(deal, dict) or not deal.get("active"):
        return []
    out: list[Line] = [("heading", SECTION_TITLE, "")]
    basis = ", ".join(deal.get("nature_basis") or [])
    out.append(("bold", f"거래 성격: {_s(deal.get('nature_label'))}" + (f" — 근거: {basis}" if basis else ""), ""))
    out.append(("text", f"우리 측 지위: {_s(deal.get('our_role'))}", ""))
    for p in deal.get("purpose") or []:
        out.append(("text", f"사업 목적: {_s(p)}", ""))
    parties = []
    for p in deal.get("parties") or []:
        fn = "·".join(p.get("functions") or [])
        parties.append(f"{p.get('label')}={p.get('entity') or '?'}" + (" (개인)" if p.get("person") else "")
                       + (f" — {fn}" if fn else "") + (" [우리]" if p.get("is_us") else ""))
    if parties:
        out.append(("text", "당사자·제3자: " + " / ".join(parties), ""))
    flows = []
    for m in deal.get("money_flows") or []:
        if m.get("kind") in ("deposit", "rent") or m.get("amount"):
            amt = m.get("amount")
            flows.append(f"{m.get('label')} {_won(amt)}" + (" (반환 대상)" if m.get("returnable") else "")
                         + (f" — {m.get('due')}" if m.get("due") else ""))
    if flows:
        out.append(("text", "주고받는 돈: " + "; ".join(flows), ""))
    if deal.get("sequence"):
        out.append(("text", "이행 순서: " + " → ".join(deal.get("sequence") or []), ""))
    for e in deal.get("exposures") or []:
        prot = ", ".join(e.get("protected_by") or []) or "확인된 보호 없음"
        out.append(("bullet", f"잃을 수 있는 것: {e.get('label')} — 지키는 수단: {prot}", ""))
    if deal.get("user_facts"):
        out.append(("text", "검토요청서의 수치(미확인): " + "; ".join(deal.get("user_facts") or []), ""))

    out.append(("bold", "보호수단 실효성 평가 — '있다' 와 '작동한다' 를 구분", ""))
    for p in deal.get("protections") or []:
        if not p.get("ours"):
            continue
        tone = _VERDICT_TONE.get(_s(p.get("verdict")), "")
        out.append(("bold", f"■ {p.get('label')} ({p.get('path')}) — {p.get('verdict_label')}", tone))
        out.append(("bullet", f"평가: {_s(p.get('assessment'))}", ""))
        if p.get("against"):
            out.append(("bullet", f"누구에게: {_s(p.get('against'))} / 언제·절차: {_s(p.get('procedure'))}", ""))
        for x in (p.get("limits") or [])[:5]:
            out.append(("bullet", f"한계: {x}", ""))
        if p.get("insolvency"):
            out.append(("bullet", f"상대방 지급불능 시: {_s(p.get('insolvency'))}", ""))
        for x in p.get("conflicts") or []:
            out.append(("bullet", f"다른 조항과 함께 볼 점: {x}", ""))

    out.append(("bold", "핵심 위험 — 사건 → 작동하지 않는 보호 → 손실", ""))
    risks = list(deal.get("core_risks") or [])
    for cat in _CATEGORY_ORDER:
        for c in [r for r in risks if r.get("category") == cat]:
            out.append(("bold", f"[{cat} · {c.get('tier')}] {c.get('title')}", _CAT_TONE.get(cat, "")))
            out.append(("bullet", f"손실 경로: {_s(c.get('loss_path_text'))}", ""))
            if c.get("action"):
                out.append(("bullet", "필요 조치: " + " / ".join(c.get("action") or []), ""))
            if c.get("needed_docs"):
                out.append(("bullet", "필요 자료: " + ", ".join(c.get("needed_docs") or []), ""))
            if c.get("conditional"):
                out.append(("bullet", "판단 성격: 조건부 — 위 자료를 확인하기 전에는 회수 가능성·효력을 확정하지 않는다", ""))
    if not risks:
        out.append(("text", "원문에서 손실 경로가 확인된 핵심 위험이 없다(아래 미확인 사실 확인 전제).", ""))

    if deal.get("unknowns"):
        out.append(("bold", "확인되지 않은 사실 — 필요 자료와 결론에 미치는 영향", ""))
        for u in deal.get("unknowns") or []:
            out.append(("bullet", f"{u.get('fact')}: {u.get('doc')} → {u.get('impact')}", ""))
    if deal.get("closing_checklist"):
        out.append(("bold", "체결 전 확인 체크리스트", ""))
        for x in deal.get("closing_checklist") or []:
            out.append(("bullet", f"□ {x}", ""))
    out.append(("note", "※ 필수수정(HIGH) 건수는 문구를 고쳐야 할 조항의 수다. 계약이 안전하다는 판단이 아니다 — "
                        "체결 전 확인·수용 위험과 미확인 사실을 함께 본다.", ""))
    return out


_ROW_FIELDS = (("judgment", "판단"), ("basis", "근거"), ("existing_protection", "기존 보호"),
               ("residual_risk", "남은 위험"), ("required_action", "필요 조치"))


def request_row_lines(r: dict[str, Any]) -> list[Line]:
    """거래 판단이 답한 요청 한 건 — 판단/근거/기존 보호/남은 위험/필요 조치."""
    if r.get("answer_format") == "flow":
        # 거래 흐름 선검증의 답(2026-11-09): 근거 조항 → 원문상 결론 → 수정 또는 유지 이유 → 추가 확인사항
        from runtime.review.deal_flow import request_row_lines as _flow_lines

        return _flow_lines(r)
    text = _s(r.get("original_user_text"))
    head, *details = text.split("\n")
    tone = {"수정 필요": "high", "사실관계 추가확인": "medium", "적정": "low"}.get(_s(r.get("review_status")), "")
    out: list[Line] = [("bold", f"요청 {r.get('request_index')}. {head}", "")]
    for d in details:
        out.append(("bullet", d.lstrip("- ").strip(), ""))
    for key, label in _ROW_FIELDS:
        val = _s(r.get(key)) or "—"
        first, *rest = val.split("\n")
        out.append(("bold" if key == "judgment" else "text", f"{label}: {first}", tone if key == "judgment" else ""))
        for x in rest:
            out.append(("bullet", x, ""))
    if r.get("needed_documents"):
        out.append(("text", "필요 자료: " + ", ".join(r.get("needed_documents") or [])
                    + " — 자료 확인 전에는 결론을 조건부로 둔다", ""))
    if r.get("substantive") is False:
        out.append(("bold", "※ 이 요청에는 아직 실질적인 답이 없다 — 검토 미완료", "high"))
    return out


def issue_extra_lines(issue: Any) -> list[Line]:
    """핵심 위험 finding 의 분류·손실 경로·필요 조치(수정문구 대신)."""
    g = (lambda k: issue.get(k)) if isinstance(issue, dict) else (lambda k: getattr(issue, k, None))
    out: list[Line] = []
    if _s(g("review_category")):
        out.append(("text", f"분류: {_s(g('review_category'))}", ""))
    if _s(g("loss_path_text")):
        out.append(("text", f"손실 경로: {_s(g('loss_path_text'))}", ""))
    actions = [a for a in (g("required_actions") or []) if _s(a)]
    if actions and g("action_only"):
        out.append(("bold", "필요 조치(수정문구 대신 — 체결 전 확인·협상):", ""))
        for a in actions:
            out.append(("bullet", f"□ {a}", ""))
    return out


def requests_complete(coverage: list[dict[str, Any]] | None) -> bool:
    rows = [r for r in coverage or [] if isinstance(r, dict) and r.get("source") == "deal_request"]
    if not rows:
        return True
    def _done(r: dict[str, Any]) -> bool:
        if r.get("answer_format") == "flow":
            return all(_s(r.get(k)) for k in ("basis", "judgment", "required_action"))
        return bool(r.get("substantive", True)) and all(_s(r.get(k)) for k, _ in _ROW_FIELDS)

    return all(_done(r) for r in rows)


def _won(v: Any) -> str:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return ""
    if n >= 10 ** 8:
        return f"{n / 10 ** 8:g}억 원"
    if n >= 10 ** 4:
        return f"{n // 10 ** 4:,}만 원"
    return f"{n:,}원"


__all__ = ["SECTION_TITLE", "deal_section_lines", "issue_extra_lines", "request_row_lines", "requests_complete"]
