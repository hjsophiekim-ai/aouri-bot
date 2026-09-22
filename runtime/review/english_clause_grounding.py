"""영문 계약에 실재하는 보호장치를 "없음" 으로 판단하지 않는다.

2026-09-21 5차 지시 9·10·18항 —
  "영문 계약에서 실제 조항이 있는데 '없음' 이면
   REVIEW_FAILED_ENGLISH_CLAUSE_GROUNDING."
  "Article 5.3 이 있는데 제3자 제공 조항 없음으로 판단 / Article 7.4·9.2 가
   있는데 Background IP 없음 / Article 9.3 이 있는데 Foreground IP 없음 /
   Article 12 가 있는데 비밀유지기간 미기재 / Article 14 가 있는데 개인정보
   처리경계 미기재 / Article 15 가 있는데 준거법·중재 없음 /
   Article 16.4~16.5 가 있는데 언어조항 없음 — 정상 완료 금지."

왜 영문만 따로 보는가
──────────────────
국문 계약의 부재 오판은 `absence_verification` 이 잡는다. 그 모듈의 개념
사전은 한국어 문형으로 되어 있어 영문 계약에는 걸리지 않는다. 영문은 애초에
**조항 구조 자체가 무너져** 있었다 — Article 5 의 제3항이 "Article 3" 으로
파싱돼 Article 5.3 이 색인에 없었다(clause_extraction 에서 고쳤다).

구조를 고치고 나면 남는 문제는 하나다: 조항이 색인에 있는데도 검토 결과가
"없음" 이라고 말하는 경우. 이 게이트는 지시 18항의 목록을 그대로 확인한다.

**지적을 지우지 않는다.** 실재하는 조항을 근거로 그 주장이 틀렸다고 기록하고
상태를 세운다 — 무엇이 어디에 있는지 담당자가 바로 볼 수 있어야 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REVIEW_FAILED_ENGLISH_CLAUSE_GROUNDING = "REVIEW_FAILED_ENGLISH_CLAUSE_GROUNDING"

#: 존재 상태 — 지시 10항.
STATUS_PRESENT = "PRESENT"
STATUS_PRESENT_NEEDS_REFINEMENT = "PRESENT_BUT_NEEDS_REFINEMENT"
STATUS_ABSENT = "ABSENT"


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass(frozen=True)
class ProtectionSpec:
    """지시 10·18항이 열거한 보호장치 하나."""

    key: str
    label: str
    #: 영문 계약 본문에서 이 보호장치를 찾는 문형.
    evidence_rx: re.Pattern[str]
    #: 검토 결과가 "이것이 없다" 고 말하는지 알아보는 문형(국문 리포트 기준).
    absence_rx: re.Pattern[str]


PROTECTIONS: tuple[ProtectionSpec, ...] = (
    ProtectionSpec(
        "mutual_nda", "상호 비밀유지 구조",
        _rx(r"mutual\s+confidentiality|obligations?\s+on\s+both\s+parties"
            r"|appl(?:y|ies)\s+to\s+both\s+Part(?:y|ies)"),
        _rx(r"일방(?:향)?\s*NDA|상호(?:성)?[^.\n]{0,20}(?:없|아니)"),
    ),
    ProtectionSpec(
        "third_party_disclosure", "제3자 제공 허용 범위",
        _rx(r"may\s+disclose[^.]{0,160}(?:third\s+part|contractor|affiliate|need-to-know)"
            r"|may\s+engage[^.]{0,120}third\s+part"),
        _rx(r"제3자[^.\n]{0,40}(?:제공|공개)[^.\n]{0,40}"
            r"(?:없|부재|규정되어 있지 않|불명확)"),
    ),
    ProtectionSpec(
        "background_ip", "Background IP 귀속",
        _rx(r"retains?\s+ownership[^.]{0,200}(?:before|prior|pre-existing|independently)"),
        _rx(r"(?:기존\s*보유|보유\s*기술|background)[^.\n]{0,60}"
            r"(?:없|부재|규정되어 있지 않|미기재)"),
    ),
    ProtectionSpec(
        "foreground_ip", "Foreground IP 후속계약 유보",
        _rx(r"(?:development\s+results|deliverables|improvements|modifications"
            r"|derivative\s+technology|interface\s+adaptation)[^.]{0,240}"
            r"(?:separate\s+development\s+agreement|separately|written\s+agreement)"),
        _rx(r"(?:개발\s*성과|개발성과|foreground)[^.\n]{0,60}"
            r"(?:없|부재|유보되어 있지 않|미기재)"),
    ),
    ProtectionSpec(
        "independent_development", "독자개발 자유",
        _rx(r"does\s+not\s+restrict[^.]{0,120}independent\s+development"
            r"|independent(?:ly)?\s+develop[^.]{0,200}(?:not\s+be\s+restricted|may)"
            r"|does\s+not\s+create\s+any[^.]{0,120}exclusive"),
        _rx(r"독자\s*개발[^.\n]{0,60}(?:없|부재|제한|보호되지)"),
    ),
    ProtectionSpec(
        "ai_training_restriction", "범용 AI 학습 제한",
        _rx(r"(?:general(?:-purpose)?\s+AI|AI\s+model)[^.]{0,160}"
            r"(?:training|improve)[^.]{0,160}(?:prior\s+written\s+consent|consent)"),
        _rx(r"AI[^.\n]{0,40}(?:학습|훈련)[^.\n]{0,40}(?:없|제한되지|규정되어 있지 않)"),
    ),
    ProtectionSpec(
        "return_destruction", "반환·폐기",
        _rx(r"return\s+or\s+destroy|destruction\s+(?:certificate|confirmation)"),
        _rx(r"반환[^.\n]{0,20}폐기[^.\n]{0,40}(?:없|부재|규정되어 있지 않)"),
    ),
    ProtectionSpec(
        "confidentiality_term", "비밀유지기간",
        _rx(r"confidentiality\s+obligations?[^.]{0,200}"
            r"(?:\(?\d+\)?\s*years?|trade[-\s]secret|remain\s+in\s+effect)"),
        _rx(r"비밀유지\s*기간[^.\n]{0,40}(?:없|부재|미기재|규정되어 있지 않)"),
    ),
    ProtectionSpec(
        "data_processing_boundary", "개인정보 처리경계",
        _rx(r"personal\s+(?:data|information)[^.]{0,200}"
            r"(?:comply|applicable\s+laws?|data\s+subject|separate)"
            r"|separate\s+written\s+(?:technical\s+agreement|data\s+processing)"),
        _rx(r"개인정보[^.\n]{0,60}(?:없|부재|미기재|경계가?\s*불명확)"),
    ),
    ProtectionSpec(
        "governing_law", "준거법",
        _rx(r"governed\s+by[^.]{0,120}laws?\s+of"),
        _rx(r"준거법[^.\n]{0,40}(?:없|부재|미기재)"),
    ),
    ProtectionSpec(
        "arbitration", "중재",
        _rx(r"arbitration[^.]{0,200}(?:KCAB|Korean\s+Commercial\s+Arbitration"
            r"|final\s+and\s+binding|Seoul)"),
        _rx(r"중재[^.\n]{0,40}(?:없|부재|미기재)"),
    ),
    ProtectionSpec(
        "language_precedence", "언어본 우선순위",
        _rx(r"(?:English|Chinese|Korean)[^.]{0,160}"
            r"(?:prevail|controlling|shall\s+govern|reference|interpret)"),
        _rx(r"(?:우선\s*언어|언어본)[^.\n]{0,40}(?:없|부재|미기재)"),
    ),
)


def _is_english_contract(clauses: list[Any] | None) -> bool:
    ids = [str(getattr(c, "clause_id", "") or "") for c in clauses or []]
    en = sum(1 for i in ids if i.startswith("EN-"))
    return bool(ids) and en >= max(3, len(ids) // 2)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


@dataclass
class EnglishGroundingReport:
    """보호장치별 존재 상태와, 그것을 부재로 말한 항목."""

    protections: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    applied: bool = False

    @property
    def status(self) -> str:
        return REVIEW_FAILED_ENGLISH_CLAUSE_GROUNDING if self.violations else ""

    @property
    def detail(self) -> str:
        if not self.violations:
            return ""
        names = ", ".join(
            f"{v['label']}({', '.join(v['supporting_clause_ids'][:2])})"
            for v in self.violations[:3]
        )
        return (
            f"영문 계약에 실재하는 보호조항을 '없음' 으로 판단한 항목 "
            f"{len(self.violations)}건을 확인했습니다 — {names}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "protections": list(self.protections),
            "violations": list(self.violations),
        }


def check_english_clause_grounding(
    clauses: list[Any] | None,
    clause_results: list[dict[str, Any]] | None = None,
    *,
    contract_text: str = "",
) -> EnglishGroundingReport:
    """영문 계약의 보호장치를 조항 단위로 확인하고, 부재 오판을 잡는다."""
    report = EnglishGroundingReport()
    if not _is_english_contract(clauses):
        return report
    report.applied = True

    for spec in PROTECTIONS:
        supporting: list[str] = []
        for c in clauses or []:
            body = re.sub(r"\s*\n\s*", " ", str(getattr(c, "text", "") or ""))
            if not body or not spec.evidence_rx.search(body):
                continue
            path = str(getattr(c, "display_path", "") or "")
            if path and path not in supporting:
                supporting.append(path)
        status = STATUS_PRESENT if supporting else STATUS_ABSENT
        report.protections.append({
            "key": spec.key,
            "label": spec.label,
            "status": status,
            # 지시 11항 — supporting_clause_ids 가 없으면 "적정" 이라고 하지 않는다.
            "supporting_clause_ids": supporting[:4],
        })
        if not supporting:
            continue
        for cr in clause_results or []:
            if not isinstance(cr, dict) or cr.get("dedup_suppressed"):
                continue
            blob = " ".join(
                _norm(cr.get(k))
                for k in ("issue_title", "clause_title", "problem", "rewrite_reason")
            )
            if not blob or not spec.absence_rx.search(blob):
                continue
            report.violations.append({
                "key": spec.key,
                "label": spec.label,
                "clause_id": str(cr.get("clause_id") or ""),
                "issue_title": _norm(cr.get("issue_title") or cr.get("clause_title"))[:90],
                "supporting_clause_ids": supporting[:4],
            })
            cr["english_grounding_contradiction"] = {
                "protection": spec.key,
                "supporting_clause_ids": supporting[:4],
                "reason": (
                    f"'{spec.label}' 는 {', '.join(supporting[:3])}에 실재합니다 — "
                    "부재로 판단할 수 없습니다."
                ),
            }
    return report
