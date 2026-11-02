"""손실 경로 게이트 — 필수수정은 "사건 → 작동하지 않는 보호 → 손실" 이 있어야 한다 (2026-10-30).

실측(천안 상가 임대차, 실제 AI 경로): 조항별 AI 논점이 "연대책임 범위가 불명확하여 … 손해까지 부담할 우려",
"협조의무가 추상적이어서 … 책임소재 불분명" 을 이유로 HIGH·내부 승인 필요를 달았다(제10조는 법이 정한 책임을 넘지
않는 조항이다). 같은 실행에서 사내변호사 에이전트는 보증금 미회수를 HIGH 로 따로 냈고, 거래 판단의 핵심 위험과 겹쳐
같은 쟁점이 두 번 나왔다. 승인필요 표지만 단 MEDIUM 은 화면에서 필수수정, 보고서에서 권장수정으로 갈렸다.

규칙(생성형 AI 논점에만 — 규칙 자체가 HIGH·승인필요로 정한 판단은 바꾸지 않는다)
  1. 거래 판단의 핵심 위험과 같은 쟁점(같은 조 + 같은 주제어)이면 핵심 위험에 합친다(merged_into + 사유).
  2. 필수수정으로 보이는데(HIGH·승인필요·고위험) 근거가 모호성·가능성 표현이거나 손실이 서술되지 않았으면
     MEDIUM(권장수정)으로 내리고 승인필요 표지를 뗀다(사유 기록).
  3. 그 밖의 필수수정은 finding 자신의 서술에서 손실 경로를 세운다(derived=True 로 표시).
"""
from __future__ import annotations

import re
from typing import Any

_RX_HEDGED = re.compile(r"우려|모호|불명확|불분명|추상적|명확(?:화|하지)|가능성|소지|필요|미흡|불충분|여지|수\s*있(?:음|다)")
_RX_LOSS = re.compile(r"손실|손해|미회수|회수\s*불가|배상|지급|비용|대금|보증금|금액|원")
_TOPIC_WORDS = {
    "deposit": r"근저당|질권|보증금[^.]{0,20}(?:회수|반환|담보|보호)|담보",
    "guarantee": r"연대\s*보증|보증인|최고액|물상보증",
    "parking": r"주차장",
    "investment": r"투자비|시설비|인테리어|영업\s*손실",
}


#: 다른 조에 붙어도 같은 쟁점으로 볼 만큼 뚜렷한 주제.
_CROSS_ARTICLE_TOPICS = {"guarantee": r"연대\s*보증|보증인", "parking": r"주차장"}


def _rule_backed_high(cr: dict[str, Any]) -> bool:
    """규칙 자체가 HIGH·승인필요로 정한 판단인가 — 그때만 등급을 규칙 판단으로 본다."""
    return any(isinstance(r, dict) and (str(r.get("risk_level") or "").upper() == "HIGH" or r.get("approval_required"))
               for r in cr.get("related_rules") or [])


def _generated(cr: dict[str, Any]) -> bool:
    return bool(cr.get("is_counsel_agent") or cr.get("is_ai_discovered") or cr.get("ai_deep_reviewed")) \
        and not _rule_backed_high(cr) and not cr.get("is_deal_core_risk") and not cr.get("is_transaction_package")


def _must_fix_display(cr: dict[str, Any]) -> bool:
    """화면·보고서가 필수수정으로 보이는가(HIGH 또는 승인필요·고위험 표지)."""
    return str(cr.get("risk_tier") or "").upper() == "HIGH" or bool(cr.get("approval_required")) or bool(cr.get("high_risk"))


def _live(cr: dict[str, Any]) -> bool:
    return isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")


def _text(cr: dict[str, Any]) -> str:
    return " ".join(str(cr.get(k) or "") for k in ("issue_title", "problem", "rewrite_reason", "our_company_risk",
                                                   "legal_business_reason"))


def apply_loss_path_gate(clause_results: list[dict[str, Any]], deal: dict[str, Any] | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {"merged": [], "downgraded": [], "derived": []}
    core = [c for c in clause_results if isinstance(c, dict) and c.get("is_deal_core_risk")]
    topic_of = {str(r.get("id")): str(r.get("topic") or "") for r in (deal or {}).get("core_risks") or []}
    for cr in clause_results:
        if not _live(cr) or not _generated(cr):
            continue
        tier = str(cr.get("risk_tier") or "").upper()
        if tier not in ("HIGH", "MEDIUM"):
            continue
        blob = _text(cr)
        # 1. 거래 판단의 핵심 위험과 같은 쟁점이면 합친다.
        twin = next((c for c in core if str(c.get("article_number") or "") == str(cr.get("article_number") or "")
                     and re.search(_TOPIC_WORDS.get(topic_of.get(str(c.get("clause_id")), ""), r"(?!)"), blob)), None)
        if twin is None:
            # 보증·주차장처럼 쟁점이 뚜렷한 주제는 AI 가 다른 조에 붙여도 같은 쟁점이다(2026-10-30 실측: 제14조 연대보증 쟁점이
            # 제4조 AI 지적으로 또 나와, 우리가 받을 보증을 "투자비는 보증하지 않는다" 로 줄이는 반대 방향 문안까지 달렸다).
            head = " ".join((str(cr.get("issue_title") or ""), str(cr.get("problem") or "")[:160]))
            twin = next((c for c in core if topic_of.get(str(c.get("clause_id"))) in _CROSS_ARTICLE_TOPICS
                         and re.search(_CROSS_ARTICLE_TOPICS[topic_of[str(c.get("clause_id"))]], head)), None)
        if twin is not None:
            cr["dedup_reason"] = f"거래 판단 핵심 위험 '{twin.get('issue_title')}' 과 같은 쟁점 — 그 항목에 합침"
            cr["merged_into"] = str(twin.get("clause_id"))
            cr["dedup_suppressed"] = True
            report["merged"].append({"clause_id": cr.get("clause_id"), "into": twin.get("clause_id")})
            continue
        if not _must_fix_display(cr) or isinstance(cr.get("loss_path"), dict):
            continue
        risk = str(cr.get("our_company_risk") or cr.get("problem") or "")
        loss = str(cr.get("legal_business_reason") or "")
        if _RX_HEDGED.search(risk) or not _RX_LOSS.search(loss):
            reason = "손실 경로(사건 → 작동하지 않는 보호 → 손실) 미제시 — 모호성·가능성만으로 필수수정을 두지 않는다"
            cr["loss_path_gate_reason"] = reason
            cr["triage_reason"] = reason
            cr["risk_tier"] = "MEDIUM"
            cr["severity"] = "MEDIUM"
            # 뒤 단계의 "에이전트 등급 복원" 루프가 counsel_severity 로 되돌린다(2026-10-30 실측) — 함께 바꾼다.
            if cr.get("is_counsel_agent") or "counsel_severity" in cr:
                cr["counsel_severity"] = "MEDIUM"
            cr["high_risk"] = False
            cr["approval_required"] = False
            cr["must_fix"] = False
            report["downgraded"].append({"clause_id": cr.get("clause_id"), "reason": reason})
            continue
        cr["loss_path"] = {"event": risk[:200], "failed_protection": f"현행 {cr.get('display_path') or '조항'} 문언",
                           "loss": loss[:200], "derived": True}
        cr["loss_path_text"] = f"{risk[:200]} → 현행 {cr.get('display_path') or '조항'} 문언 → {loss[:200]}"
        report["derived"].append(str(cr.get("clause_id")))
    return report


def enforce_gate_decisions(clause_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """게이트가 내린 항목을 뒤 단계가 다시 올렸으면 게이트 판단으로 되돌리고 기록한다(출력 직전 멱등 점검)."""
    out = []
    for cr in clause_results:
        if not _live(cr) or not cr.get("loss_path_gate_reason") or not _must_fix_display(cr):
            continue
        out.append({"clause_id": str(cr.get("clause_id")), "was": str(cr.get("risk_tier")),
                    "note": "게이트 이후 단계가 다시 필수수정으로 올림 — 손실 경로가 없어 게이트 판단(MEDIUM)으로 되돌림"})
        cr["risk_tier"] = cr["severity"] = "MEDIUM"
        if "counsel_severity" in cr:
            cr["counsel_severity"] = "MEDIUM"
        cr["high_risk"] = cr["approval_required"] = cr["must_fix"] = False
    return out


__all__ = ["apply_loss_path_gate", "enforce_gate_decisions"]
