"""같은 법률효과를 다루는 finding 을 하나로 합친다.

2026-09-21 2차 지시 8항 —
  "유치권 포기 + 유치권의 부당특약 가능성 + Payment Risk Package 내 유치권이
   사실상 동일 이슈라면 하나의 HIGH finding 으로 통합하고, 필요 시 하위
   bullet 로 채권보전 상실 / 지급 선행조건 / 하수급인 징구 를 설명하세요.
   같은 조항·같은 손실 시나리오가 반복되면 중복 finding 으로 판정."

실측(인테리어 2차 본계약, 2026-09-21 15:45 검토):

    [HIGH] counsel_KR-16      | 제16조 | 유치권 포기각서 …
    [HIGH] counsel_KR-16      | 제16조 | 유치권 포기각서 …   ← **같은 id 가 두 번**
    [HIGH] CWC-LIEN-WAIVER    | 제15조 | 유치권 포기각서 제출이 선행조건

담당자는 같은 이야기를 세 번 읽고, 어느 문안을 계약서에 넣어야 하는지
알 수 없다.

무엇을 기준으로 같다고 보는가
──────────────────────────
조항번호가 같아야 한다고 보면 합쳐지지 않는다 — 유치권은 제15조(지급
선행조건)와 제16조(제출 의무)에 걸쳐 있다. 그래서 **법률효과(개념)** 를
기준으로 묶는다. 개념 어휘는 `absence_verification.CONCEPTS` 를 그대로 쓴다
— 같은 개념 목록을 두 곳에 두면 갈라진다.

무엇을 남기는가
─────────────
가장 완성도가 높은 항목 하나(등급이 높고, 그대로 넣을 수 있는 문안이 길고,
계약 원문 인용이 있는 것)를 남기고, 나머지는 그 항목의 하위 bullet 로
접는다. **지적 내용을 버리지 않는다** — 자리만 하나로 모은다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: 이 등급 이상만 통합 대상. LOW 는 화면에서도 접혀 있어 중복이 문제되지 않고,
#: 섣불리 합치면 참고 정보가 사라진다.
_MERGE_TIERS = ("HIGH", "CRITICAL", "MEDIUM")


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _tier(cr: dict[str, Any]) -> str:
    return str(cr.get("risk_tier") or cr.get("severity") or "").upper()


def _subject(cr: dict[str, Any]) -> str:
    return _norm(cr.get("issue_title") or cr.get("clause_title"))


def _concept_key(cr: dict[str, Any]) -> str:
    """이 finding 이 다루는 법률효과. 없으면 빈 문자열."""
    from runtime.review.absence_verification import CONCEPTS

    text = " ".join(
        _norm(cr.get(k))
        for k in ("issue_title", "clause_title", "problem", "rewrite_reason")
    ).lower()
    best, best_hits = "", 0
    for spec in CONCEPTS:
        hits = sum(1 for term in spec.claim_terms if term.lower() in text)
        if hits > best_hits:
            best, best_hits = spec.key, hits
    return best


def _remedy_kind(cr: dict[str, Any]) -> str:
    """이 지적이 요구하는 처방 — 신설인가, 기존 조항 수정인가."""
    from runtime.review.absence_verification import claims_absence

    if bool(cr.get("is_new_clause")) or "신설" in _norm(cr.get("display_path")):
        return "new_clause"
    return "new_clause" if claims_absence(cr) else "amend"


def _completeness(cr: dict[str, Any]) -> tuple[int, int, int, int]:
    """어느 항목을 대표로 남길지 정하는 점수(클수록 대표)."""
    tier_rank = {"CRITICAL": 3, "HIGH": 3, "MEDIUM": 2}.get(_tier(cr), 1)
    rewrite = max(
        len(_norm(cr.get(k)))
        for k in ("suggested_rewrite", "recommendation_text", "proposed_revision")
    )
    has_quote = 0 if "해당 조항 없음" in _norm(cr.get("original_text")) else 1
    anchored = 1 if str(cr.get("article_number") or "").strip() else 0
    return tier_rank, rewrite, has_quote, anchored


@dataclass
class ConsolidationReport:
    merged: list[dict[str, Any]] = field(default_factory=list)
    exact_duplicates: list[str] = field(default_factory=list)

    @property
    def detail(self) -> str:
        parts: list[str] = []
        if self.exact_duplicates:
            parts.append(f"같은 항목이 두 번 실린 것 {len(self.exact_duplicates)}건을 제거했습니다.")
        if self.merged:
            names = ", ".join(m["concept"] for m in self.merged[:3])
            parts.append(
                f"같은 법률효과를 다루는 항목 {len(self.merged)}묶음을 하나로 "
                f"통합했습니다({names})."
            )
        return " ".join(parts)


def consolidate_duplicate_findings(
    clause_results: list[dict[str, Any]],
) -> ConsolidationReport:
    """제자리에서 중복을 정리하고 보고서를 돌려준다."""
    report = ConsolidationReport()
    if not isinstance(clause_results, list) or len(clause_results) < 2:
        return report

    # 1. 완전히 같은 항목이 두 번 실린 경우 — id 와 지적 제목이 모두 같다.
    seen: set[tuple[str, str]] = set()
    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        key = (str(cr.get("clause_id") or ""), _subject(cr))
        if key[0] and key in seen:
            report.exact_duplicates.append(key[0])
            continue
        seen.add(key)
        kept.append(cr)
    if report.exact_duplicates:
        clause_results[:] = kept

    # 2. 같은 법률효과를 다루는 항목들 — 대표 하나만 남기고 나머지는 접는다.
    groups: dict[str, list[dict[str, Any]]] = {}
    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        if _tier(cr) not in _MERGE_TIERS:
            continue
        # 다른 문서(재하도급 계약서)에 들어갈 항목은 이 계약의 항목과 합치지
        # 않는다 — 들어갈 계약서가 다르다(지시 11항).
        if str(cr.get("target_contract") or "this") != "this":
            continue
        concept = _concept_key(cr)
        if not concept:
            continue
        # 같은 개념이라도 **처방이 다르면** 다른 지적이다. "조항이 없으니
        # 신설하라" 와 "있는 조항이 불리하니 고치라" 는 담당자가 해야 할 일이
        # 다르므로, 하나로 접으면 그중 하나가 사라진다. 실측: 개선 IP 귀속
        # 조항 지적(제8조 제3항 수정)에 Foreground IP 유보 신설 지적이
        # 접혀 골든 항목 하나가 결과에서 빠졌다.
        groups.setdefault(f"{concept}|{_remedy_kind(cr)}", []).append(cr)

    for concept, rows in groups.items():
        if len(rows) < 2:
            continue
        # HIGH 가 섞여 있으면 HIGH 끼리만 묶는다 — 등급이 다른 지적을 접으면
        # 낮은 쪽의 판단이 높은 쪽 이름 아래로 숨는다.
        high = [r for r in rows if _tier(r) in ("HIGH", "CRITICAL")]
        target = high if len(high) >= 2 else rows
        if len(target) < 2:
            continue
        target.sort(key=_completeness, reverse=True)
        primary, others = target[0], target[1:]

        bullets: list[str] = []
        for other in others:
            subject = _subject(other)
            where = _norm(other.get("display_path"))
            bullets.append(f"{subject}{f' ({where})' if where else ''}")
            other["dedup_suppressed"] = True
            other["dedup_primary_clause_id"] = str(primary.get("clause_id") or "")
            other["dedup_reason"] = (
                f"'{concept}' 축을 다루는 지적이 여러 건이라 "
                f"{_norm(primary.get('display_path')) or '대표 항목'}으로 통합했습니다."
            )
        existing = primary.get("consolidated_points")
        primary["consolidated_points"] = (
            list(existing) if isinstance(existing, list) else []
        ) + bullets
        primary["consolidated_from"] = [
            str(o.get("clause_id") or "") for o in others
        ]
        report.merged.append({
            "concept": concept.split("|")[0],
            "primary": str(primary.get("clause_id") or ""),
            "display_path": _norm(primary.get("display_path")),
            "folded": [str(o.get("clause_id") or "") for o in others],
            "points": bullets,
        })
    return report
