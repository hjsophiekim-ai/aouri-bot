"""핵심 위험 추적 — 어느 단계가 만들고·합치고·숨기고·강등했는지, 그리고 최종 출력 대조 (2026-10-30).

무엇이 문제였나
─────────────
천안 상가 임대차(2026-10-29 사용자 세션): 보증금 미회수 HIGH 는 Triage 낱말 점수로 DROP 되어 LOW 가 됐고,
다시 돌린 결과(2026-10-30)에서는 거래 판단이 세운 HIGH 두 건이 **사유 없이** dedup_suppressed 가 됐다.
dedup_suppressed 를 세우는 곳이 파이프라인에 20곳이 넘고 대부분 이유를 남기지 않는다. 결과만 보면
"핵심 위험이 없는 계약" 처럼 보인다.

어떻게 막나
─────────
1. 핵심 위험 finding 은 ``TracedFinding`` 으로 만든다. 위험도·노출 여부를 바꾸는 키(risk_tier, dedup_suppressed,
   keep_as_is, triage …)가 바뀔 때마다 **바꾼 함수(모듈·함수·줄)** 와 그 순간 남아 있던 사유 필드를 ``_trace`` 에
   쌓는다. 복사(dict(cr))돼도 ``_trace`` 항목은 따라간다.
2. ``reconcile`` 은 출력 직전 거래 판단과 최종 finding 을 대조한다. 핵심 위험이 사라졌거나 숨겨졌거나 강등됐으면
   되살리고, 무엇이 왜 그랬는지를 ``core_risk_trace`` 로 남긴다. 결론을 뒤집은 단계가 사유를 남기지 않았으면
   그 사실 자체를 기록한다("사유 미기록").
"""
from __future__ import annotations

import copy
import sys
from typing import Any

#: 위험도·노출을 바꾸는 키
TRACKED = frozenset({
    "risk_tier", "severity", "dedup_suppressed", "keep_as_is", "display_kind", "triage", "high_risk",
    "must_fix", "approval_required", "merged_into", "suppressed", "guardrail_block", "suggested_rewrite",
})
#: 바뀐 순간 함께 남길 사유 필드
_REASON_KEYS = ("triage_reason", "keep_reason", "accept_keep_reason", "merged_into", "dedup_reason",
                "suppressed_reason", "guardrail_block", "rewrite_reason")
_TIER_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "": 0}


def _caller() -> str:
    f = sys._getframe(2)
    # dict 메서드 래퍼(update/setdefault)를 거쳐 들어오면 한 칸 더 올라간다.
    while f is not None and f.f_code.co_filename == __file__:
        f = f.f_back
    if f is None:
        return "?"
    mod = f.f_globals.get("__name__", "?").rsplit(".", 1)[-1]
    return f"{mod}.{f.f_code.co_name}:{f.f_lineno}"


class TracedFinding(dict):
    """dict 그대로 쓰되, 위험도·노출 키가 바뀌면 누가 바꿨는지 ``_trace`` 에 남긴다."""

    def _record(self, key: str, value: Any) -> None:
        old = dict.get(self, key)
        if key not in TRACKED or old == value or key == "_trace":
            return
        trail = dict.get(self, "_trace")
        if not isinstance(trail, list):
            trail = []
            dict.__setitem__(self, "_trace", trail)
        reasons = {k: str(dict.get(self, k))[:160] for k in _REASON_KEYS if dict.get(self, k) and k != key}
        trail.append({"stage": _caller(), "key": key, "from": _short(old), "to": _short(value), "reasons": reasons})

    def __setitem__(self, key: str, value: Any) -> None:
        self._record(key, value)
        dict.__setitem__(self, key, value)

    def update(self, *args: Any, **kw: Any) -> None:  # type: ignore[override]
        for k, v in dict(*args, **kw).items():
            self[k] = v

    def setdefault(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        if key not in self:
            self[key] = default
        return dict.__getitem__(self, key)

    def pop(self, key: str, *default: Any) -> Any:  # type: ignore[override]
        if key in self:
            self._record(key, None)
        return dict.pop(self, key, *default)

    def copy(self) -> "TracedFinding":  # type: ignore[override]
        return TracedFinding(self)

    def __copy__(self) -> "TracedFinding":
        return TracedFinding(self)

    def __deepcopy__(self, memo: dict) -> "TracedFinding":
        return TracedFinding({k: copy.deepcopy(v, memo) for k, v in self.items()})


def _short(v: Any) -> Any:
    if isinstance(v, str) and len(v) > 80:
        return v[:80] + "…"
    if isinstance(v, (dict, list)):
        return str(v)[:80]
    return v


def traced(findings: list[dict[str, Any]], *, stage: str = "deal_assessment") -> list[dict[str, Any]]:
    out = []
    for f in findings:
        t = TracedFinding(f)
        dict.__setitem__(t, "_trace", [{"stage": stage, "key": "created", "from": None,
                                        "to": t.get("risk_tier"), "reasons": {}}])
        dict.__setitem__(t, "_core_original_tier", t.get("risk_tier"))
        out.append(t)
    return out


def _hidden(cr: dict[str, Any]) -> bool:
    return bool(cr.get("dedup_suppressed") or cr.get("keep_as_is") or cr.get("suppressed")
                or str(cr.get("triage") or "") in ("DROP", "KEEP", "FINANCE_CHECK"))


def _changes(cr: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for e in cr.get("_trace") or []:
        if e.get("key") == "created":
            events.append({"stage": e["stage"], "change": "created", "reason": f"위험도 {e.get('to')}"})
            continue
        k, to, frm = e.get("key"), e.get("to"), e.get("from")
        change = ""
        if k in ("risk_tier", "severity") and _TIER_RANK.get(str(to or "").upper(), 0) < _TIER_RANK.get(str(frm or "").upper(), 0):
            change = "downgraded"
        elif k in ("dedup_suppressed", "keep_as_is", "suppressed") and to:
            change = "hidden"
        elif k == "merged_into" and to:
            change = "merged"
        elif k == "triage" and str(to) in ("DROP", "KEEP", "FINANCE_CHECK"):
            change = "hidden"
        if not change:
            continue
        reasons = e.get("reasons") or {}
        reason = next((reasons[r] for r in ("triage_reason", "keep_reason", "accept_keep_reason", "dedup_reason",
                                             "suppressed_reason", "merged_into") if reasons.get(r)), "")
        events.append({"stage": e["stage"], "change": change, "key": k, "from": frm, "to": to,
                       "reason": reason or "사유 미기록(이 단계가 이유를 남기지 않음)"})
    return events


def reconcile(clause_results: list[dict[str, Any]], core_findings: list[dict[str, Any]],
              deal: dict[str, Any] | None) -> dict[str, Any]:
    """최종 finding 을 거래 판단과 대조한다. 빠지거나 숨겨지거나 강등된 핵심 위험은 되살리고 기록한다."""
    by_id = {str(cr.get("clause_id")): cr for cr in clause_results if isinstance(cr, dict)}
    risks: list[dict[str, Any]] = []
    for orig in core_findings:
        cid = str(orig.get("clause_id"))
        cr = by_id.get(cid)
        rec: dict[str, Any] = {"id": cid, "title": orig.get("issue_title"), "category": orig.get("review_category"),
                               "expected_tier": orig.get("_core_original_tier") or orig.get("risk_tier")}
        if cr is None:
            # 목록에서 통째로 빠졌다 — 원본(추적 기록 포함)으로 되살린다.
            events = _changes(orig) + [{"stage": "(목록 재구성)", "change": "removed",
                                        "reason": "finding 목록을 다시 만드는 단계에서 빠짐 — 사유 미기록"}]
            restored = TracedFinding(orig)
            for k in ("dedup_suppressed", "keep_as_is", "suppressed"):
                dict.pop(restored, k, None)
            dict.__setitem__(restored, "risk_tier", rec["expected_tier"])
            clause_results.append(restored)
            rec.update({"events": events, "final_state": "missing", "restored": True})
            risks.append(rec)
            continue
        events = _changes(cr)
        state = "visible"
        expected = str(rec["expected_tier"] or "").upper()
        now = str(cr.get("risk_tier") or "").upper()
        fixed = []
        if _hidden(cr):
            state = "hidden"
            for k in ("dedup_suppressed", "keep_as_is", "suppressed"):
                if cr.get(k):
                    dict.__setitem__(cr, k, False)
                    fixed.append(k)
            if str(cr.get("triage") or "") in ("DROP", "KEEP", "FINANCE_CHECK"):
                dict.__setitem__(cr, "triage", "MUST_FIX" if expected == "HIGH" else "SHOULD_FIX")
                fixed.append("triage")
            if cr.get("display_kind") in ("keep", "hidden"):
                dict.__setitem__(cr, "display_kind", "")
        if _TIER_RANK.get(now, 0) < _TIER_RANK.get(expected, 0):
            state = "downgraded" if state == "visible" else state
            dict.__setitem__(cr, "risk_tier", expected)
            dict.__setitem__(cr, "severity", expected)
            fixed.append("risk_tier")
        rec.update({"events": events, "final_state": state, "restored": bool(fixed), "restored_keys": fixed})
        risks.append(rec)
    accepted = [{"id": c.get("id"), "title": c.get("title"), "category": c.get("category"),
                 "final_state": "deal_section_only", "events": [], "restored": False}
                for c in (deal or {}).get("core_risks") or [] if not c.get("as_finding")]
    return {
        "risks": risks + accepted,
        "restored_count": sum(1 for r in risks if r.get("restored")),
        "note": ("핵심 위험은 거래 판단에서 만들어지고, 이후 단계가 숨기거나 강등하면 출력 직전에 되살린다. "
                 "되살린 경우 그 단계와 사유(없으면 '사유 미기록')를 남긴다."),
    }


__all__ = ["TRACKED", "TracedFinding", "reconcile", "traced"]
