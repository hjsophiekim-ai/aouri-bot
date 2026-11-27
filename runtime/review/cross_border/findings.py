"""cross_border finding 공통 형식 — clause_results 와 같은 모양으로 만든다.

조치 유형(action_type)
- 필수수정       : 체결 전에 문구를 반드시 고쳐야 한다(HIGH)
- 체결 전 확인   : 공란·선택지를 상대방과 확정해야 한다
- 권장수정       : 협상에서 요청할 수정
- 사업부 결정    : 기재 사항·상업적 선택
- 현행 유지      : 잘 짜인 조항(법무 내부 분석본에만)

국·영 병기 계약의 수정은 국문 수정(본 finding)과 영문 수정(`__en` 짝 finding)으로 나눠 변경추적본 두 곳에 들어가게 하고,
사업팀 전달본에서는 짝 finding 을 본 항목 아래 수정 문구로만 싣는다(`brief_merge_into`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ACTION_MUST = "필수수정"
ACTION_CONFIRM = "체결 전 확인"
ACTION_SUGGEST = "권장수정"
ACTION_BUSINESS = "사업부 결정"
ACTION_KEEP = "현행 유지"


@dataclass
class Edit:
    location: str                    # "제3조 제1항"
    target: str                      # 원문 그대로(교체 대상). 신설이면 ""
    replacement: str                 # 완성 문구
    edit_type: str = "replace"       # replace / insert_after / new_clause
    lang: str = "ko"
    anchor_path: str = ""            # 신설 문안을 넣을 기준 항(국문 경로) — 비면 같은 finding 의 국문 신설 위치
    undecided: list[str] = field(default_factory=list)   # 문안 속 [  ] 의 항목 이름("선적 기한(주)")


@dataclass
class Finding:
    code: str
    title: str
    path: str
    risk: str                                  # HIGH / MEDIUM / LOW
    action: str
    topics: list[str]                          # defect / payment / tax / dispute / delivery / quality / origin / blank …
    quotes: list[str]
    problem: str                               # 현재 조건이 무엇이고 무엇이 비었는가
    risk_to_us: str                            # 우리에게 생길 위험
    loss_path: str                             # 사건 → 작동하지 않는 보호 → 손실
    action_text: str                           # 필요한 조치(한 문장)
    edits: list[Edit] = field(default_factory=list)
    statutes: list[dict[str, str]] = field(default_factory=list)
    checks: list[dict[str, str]] = field(default_factory=list)
    negotiation: str = ""
    fallback: str = ""
    recommendation: str = ""
    limits: str = ""
    family: str = "cross_border_common"

    def article(self) -> str:
        import re

        m = re.search(r"제\s*(\d+)\s*조", self.path)
        return m.group(1) if m else ""


_TIER = {"HIGH": "MUST", "MEDIUM": "SUGGEST", "LOW": "NOTE"}


def _loss_path_dict(text: str) -> dict[str, str]:
    """"사건 → 작동하지 않는 보호 → … → 손실" 문장을 표준 구조로."""
    parts = [p.strip() for p in str(text or "").split("→") if p.strip()]
    if not parts:
        return {}
    return {"event": parts[0], "failed_protection": " → ".join(parts[1:-1]) if len(parts) > 2 else "",
            "loss": parts[-1] if len(parts) > 1 else ""}


def _redline(f: Finding, e: Edit) -> dict[str, Any]:
    ko_insert = next((x for x in f.edits if x.lang == "ko" and x.edit_type != "replace"), None)
    anchor_path = e.anchor_path or (ko_insert.location if ko_insert else e.location)
    return {
        "lang": e.lang,
        "anchor_path": anchor_path if e.edit_type != "replace" else "",
        "undecided_labels": list(e.undecided),
        "finding_id": f"xb_{f.code}" + ("__en" if e.lang == "en" else ""),
        "clause_id": f"xb_{f.code}" + ("__en" if e.lang == "en" else ""),
        "severity": f.risk,
        "edit_location": f"{e.location} " + ("교체" if e.edit_type == "replace" else "뒤에 추가"),
        "edit_type": e.edit_type,
        "target_text": e.target,
        "replacement_text": e.replacement,
        "final_clause_text": e.replacement,
        "original_text": e.target,
        "reason": f.problem,
    }


def to_clause_results(f: Finding) -> list[dict[str, Any]]:
    """Finding → clause_results 항목(국문 본 항목 + 필요하면 영문 짝 항목)."""
    ko_edit = next((e for e in f.edits if e.lang == "ko"), None)
    en_edit = next((e for e in f.edits if e.lang == "en"), None)
    main_edit = ko_edit or en_edit
    cid = f"xb_{f.code}"
    suggested = main_edit.replacement if main_edit else ""
    replace = bool(main_edit and main_edit.edit_type == "replace")
    # 교체 수정은 원문 해당 문구를 지우고 바꾸는 것이 지적의 취지다 — 무결성 검사가 '이유 없는 원문 변경'으로 되돌리지 않게
    # 이유에 그 취지를 적는다. 원문(original_text)은 교체 대상 문구 그대로, 근거 인용은 evidence_quotes 에.
    reason = f.problem + (" 원문의 해당 문구를 삭제하고 아래 문구로 교체한다." if replace else "")
    base: dict[str, Any] = {
        "clause_id": cid,
        "finding_id": cid,
        "article_number": f.article() or None,
        "display_path": f.path,
        "clause_title": f.title,
        "clause_topic": f.topics[0] if f.topics else "other",
        "topic_tags": list(f.topics),
        "original_text": main_edit.target if replace else "\n".join(f.quotes),
        "evidence_quote": f.quotes[0] if f.quotes else "",
        "evidence_quotes": list(f.quotes),
        "risk_tier": f.risk,
        "severity": f.risk,
        "legal_risk": f.risk,
        "high_risk": f.risk == "HIGH",
        "must_fix": f.action == ACTION_MUST,
        "approval_required": False,
        "review_tier": _TIER.get(f.risk, "NOTE"),
        "review_category": f.action,
        "action_type": f.action,
        "rewrite_reason": reason,
        "problem": f.problem,
        "brief_current": f.problem,
        "brief_risk": f.risk_to_us,
        "brief_action": f.action_text,
        "legal_business_reason": f.risk_to_us,
        # 표준 구조(loss_path_gate·deal_assessment 와 같은 모양) — 요약 단계가 dict 로 읽는다(문자열이면 'str'.get 오류)
        "loss_path": _loss_path_dict(f.loss_path),
        "loss_path_text": f.loss_path,
        # 수정 문구 없이 확정·확인으로 끝나는 항목(공란 확정 등) — 최종 결과에 '체결 전 확인'으로 남게
        "action_only": not f.edits and f.action != ACTION_KEEP,
        "required_actions": [f.action_text],
        "suggested_rewrite": suggested or None,
        "has_rewrite_change": bool(main_edit and main_edit.edit_type == "replace"),
        "has_addition": bool(main_edit and main_edit.edit_type != "replace"),
        "addition_text": (main_edit.replacement if main_edit and main_edit.edit_type != "replace" else None),
        "redline_instruction": _redline(f, main_edit) if main_edit else {},
        "negotiation_position": f.negotiation,
        "fallback": f.fallback,
        "recommendation": f.recommendation,
        "legal_limits": f.limits,
        "brief_checks": list(f.checks),
        "legal_grounding": {"contract_clauses": [f.path] if f.path else [], "statutes": list(f.statutes),
                            "relations": [], "legal_reason": f.risk_to_us, "business_reason": f.loss_path},
        "is_cross_border_check": True,
        # 부재·전제 판단을 계약 전체 원문 정확 일치로 이미 했다 — 무결성 단계의 '부재 지적 재확인' 대상이 아니다
        "absence_verified": True,
        "rule_family": f.family,
        "keep_as_is": f.action == ACTION_KEEP,
        # 법무 내부 분석본의 '현행 유지(KEEP)' 절이 읽는 필드 — 유리한 조항을 근거와 함께 남긴다
        "triage": "KEEP" if f.action == ACTION_KEEP else "",
        "keep_reason": f.problem if f.action == ACTION_KEEP else "",
        "detected_issue_list": [{"issue_title": f.title}],
        "dedup_suppressed": False,
        "display_kind": "keep" if f.action == ACTION_KEEP else "guidance",
        "confidence": 0.8,
        "user_focus_hit": False,
        "factual_hit": True,
        "ai_deep_reviewed": False,
    }
    out = [base]
    # 본 항목의 수정 외 나머지 수정(영문, 같은 항의 다른 문단)은 짝 항목으로 — 변경추적본에는 각각 들어가고,
    # 사업팀 전달본에서는 본 항목 아래 수정 문구로만 싣는다.
    extra = [e for e in f.edits if e is not main_edit]
    ids: list[str] = []
    for i, e in enumerate(extra):
        suffix = "__en" if (e.lang == "en" and i == 0 and ko_edit is main_edit) else f"__{e.lang}{i + 2}"
        sid = cid + suffix
        sib = dict(base)
        sib.update({
            "clause_id": sid, "finding_id": sid,
            "clause_title": f.title + (" (영문)" if e.lang == "en" else " (추가 수정)"),
            "original_text": e.target if e.edit_type == "replace" else "\n".join(f.quotes),
            "rewrite_reason": f.problem + (" 원문의 해당 문구를 삭제하고 아래 문구로 교체한다." if e.edit_type == "replace" else ""),
            "suggested_rewrite": e.replacement,
            "has_rewrite_change": e.edit_type == "replace",
            "has_addition": e.edit_type != "replace",
            "addition_text": e.replacement if e.edit_type != "replace" else None,
            "redline_instruction": {**_redline(f, e), "finding_id": sid, "clause_id": sid},
            "brief_merge_into": cid,
            "translation_of": cid,
        })
        ids.append(sid)
        out.append(sib)
    if ids:
        base["translation_ids"] = ids
    return out
