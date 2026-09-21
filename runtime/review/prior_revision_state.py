"""사업부가 이미 고친 조항을 알아보고, 같은 지적을 되풀이하지 않는다.

2026-09-21 3차 지시 —
  "사업부가 1차로 수정한 부분에 대해서 무조건 검토하지 말고 맞는지 틀린지
   판단하고, 검토한 부분이 맞으면 또 똑같이 수정하지 않는 로직을 개발해줘."
  1항 "현재 문구가 이미 충분하면 반드시 KEEP 처리하고 추가 수정하지 마세요."
  3항 "같은 법률효과가 이미 다른 조항에서 충분히 규정돼 있으면 새 조항을
       만들지 마세요."

무엇을 근거로 "이미 고쳤다" 고 아는가
──────────────────────────────
수정본에는 **수정한 사람이 남긴 메모**가 있다. 워드 주석으로 달려 있고,
PDF 로 인쇄하면 오른쪽 여백의 말풍선이 된다(text_extract.
`split_margin_annotations()` 가 본문에서 떼어낸다). 실측(오킨 수정안):

    메모 포함[ILOOM3]: 일룸이 국내 개발·시험·인증 업체와 협업할 수 있도록
                       일반적인 제3자 활용은 허용하고, OKIN이 지정한
                       핵심기술만 사전 승인을 받도록 구분했습니다.

이 메모는 "제5조 제3항을 왜 그렇게 고쳤는지" 를 그대로 말해 준다. 검토
엔진이 같은 조항에 대해 "제3자 제공 범위가 불명확" 이라고 다시 지적하면,
담당자는 자기가 방금 고친 것을 또 고치라는 말을 듣는다.

**메모만으로 KEEP 하지 않는다.** 메모는 "고쳤다" 는 주장일 뿐이다. 그
조항이 실제로 그 쟁점을 규정하고 있는지 문언으로 확인한 뒤에만 KEEP 한다
— 판단을 건너뛰면 "무조건 검토하지 말라" 가 아니라 "무조건 통과시켜라" 가
된다.

KEEP 하지 않는 경우
─────────────────
· 강행법규 위반을 지적하는 항목 — 사업부가 고쳤더라도 위법은 위법이다.
· HIGH — 계약 체결 전 반드시 고쳐야 한다고 판단된 것은 메모로 덮지 않는다.
· 인용·조항번호가 틀렸다는 지적 — 그것은 검토 결과 자체의 결함이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: 사업부가 이미 반영한 것으로 확인돼 그대로 두는 항목.
KEEP_VERDICT = "KEEP"

#: 메모 한 건을 알아보는 표지.
_RX_ANNOTATION_HEAD = re.compile(
    r"(?:메모\s*포함|Commented|주석|Comment)\s*\[([^\]]{1,40})\]\s*[:：]?\s*",
    re.IGNORECASE,
)

#: 이 낱말이 지적에 있으면 메모로 덮지 않는다 — 검토 결과 자체의 결함이거나
#: 강행법규 문제다.
_RX_NEVER_KEEP = re.compile(
    r"강행(?:법규|규정)|무효|위법|법령\s*위반|불공정\s*약관|약관규제법"
    r"|존재하지\s*않는\s*조항|인용|조항\s*위치|날조"
)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


@dataclass(frozen=True)
class RevisionNote:
    """사업부가 남긴 수정 메모 한 건."""

    marker: str          # "ILOOM3"
    note: str            # "일룸이 국내 개발·시험·인증 업체와 협업할 수 있도록 …"

    @property
    def keywords(self) -> tuple[str, ...]:
        """메모가 말하는 쟁점의 낱말들 — 조항 문언과 대조하는 데 쓴다."""
        tokens = re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9·]{1,}", self.note)
        return tuple(t for t in tokens if len(t) >= 2)


@dataclass
class PriorRevisionState:
    """이 계약이 이미 한 차례 수정된 문서인가, 무엇을 고쳤는가."""

    notes: list[RevisionNote] = field(default_factory=list)
    #: 사용자가 수정본이라고 밝혔는가(검토요청 설명에서 읽는다).
    declared_revision: bool = False
    declared_basis: str = ""

    @property
    def is_revised_draft(self) -> bool:
        return bool(self.notes) or self.declared_revision

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_revised_draft": self.is_revised_draft,
            "declared_revision": self.declared_revision,
            "declared_basis": self.declared_basis,
            "note_count": len(self.notes),
            "notes": [{"marker": n.marker, "note": n.note} for n in self.notes],
        }


#: 검토요청 설명에서 "이미 우리가 고친 안" 이라고 밝히는 표현.
_RX_DECLARED_REVISION = re.compile(
    r"수정안|수정\s*버전|1차\s*수정|우리(?:가|측이)\s*수정|자체\s*수정"
    r"|반영하여\s*수정|초안을\s*바탕으로[^.\n]{0,20}수정"
    r"|검토(?:하여|해)\s*수정한"
)


def parse_revision_notes(annotations: list[str] | None) -> list[RevisionNote]:
    """여백에서 떼어낸 메모 덩어리를 개별 메모로 나눈다."""
    out: list[RevisionNote] = []
    for block in annotations or []:
        text = str(block or "")
        positions = [(m.start(), m.end(), m.group(1)) for m in _RX_ANNOTATION_HEAD.finditer(text)]
        for i, (_start, end, marker) in enumerate(positions):
            stop = positions[i + 1][0] if i + 1 < len(positions) else len(text)
            note = _norm(text[end:stop])
            if note:
                out.append(RevisionNote(marker=_norm(marker), note=note))
    return out


def build_prior_revision_state(
    *,
    margin_annotations: list[str] | None = None,
    user_description: str = "",
    filename: str = "",
) -> PriorRevisionState:
    """이 문서가 이미 수정된 안인지, 무엇을 고쳤는지 모은다."""
    notes = parse_revision_notes(margin_annotations)
    haystack = f"{user_description}\n{filename}"
    declared = bool(_RX_DECLARED_REVISION.search(haystack))
    basis = ""
    if declared:
        m = _RX_DECLARED_REVISION.search(haystack)
        basis = _norm(haystack[max(0, m.start() - 40): m.end() + 40]) if m else ""
    elif notes:
        basis = f"계약서에 수정 메모 {len(notes)}건이 달려 있습니다."
    return PriorRevisionState(
        notes=notes, declared_revision=declared, declared_basis=basis,
    )


def _finding_text(cr: dict[str, Any]) -> str:
    return " ".join(
        _norm(cr.get(k))
        for k in ("issue_title", "clause_title", "problem", "rewrite_reason")
    )


def matching_note(cr: dict[str, Any], state: PriorRevisionState) -> RevisionNote | None:
    """이 지적과 같은 쟁점을 말하는 수정 메모."""
    text = _finding_text(cr)
    if not text:
        return None
    best: RevisionNote | None = None
    best_hits = 0
    for note in state.notes:
        hits = sum(1 for kw in note.keywords if kw in text)
        if hits > best_hits:
            best, best_hits = note, hits
    # 낱말 두 개 이상이 겹쳐야 같은 쟁점으로 본다 — 하나면 우연일 수 있다.
    return best if best_hits >= 2 else None


@dataclass
class PriorRevisionReport:
    kept: list[dict[str, Any]] = field(default_factory=list)
    checked: int = 0

    @property
    def detail(self) -> str:
        if not self.kept:
            return ""
        names = ", ".join(
            f"{k['display_path'] or k['clause_id']}" for k in self.kept[:4]
        )
        return (
            f"사업부가 이미 수정하여 요청사항을 충족하는 항목 {len(self.kept)}건을 "
            f"KEEP 으로 정리했습니다 — {names}."
        )


def apply_prior_revision_keep(
    clause_results: list[dict[str, Any]],
    state: PriorRevisionState,
    *,
    clauses: list[Any] | None = None,
) -> PriorRevisionReport:
    """이미 고쳐진 조항에 대한 중복 지적을 KEEP 으로 돌린다.

    항목을 지우지 않는다 — 담당자는 "이 쟁점을 봤고, 현재 문구로 충분하다"
    는 판단을 받아야 한다. 등급만 참고로 내리고 수정문안을 거둔다.
    """
    report = PriorRevisionReport()
    if not state.is_revised_draft or not isinstance(clause_results, list):
        return report

    by_article: dict[str, str] = {}
    for c in clauses or []:
        art = str(getattr(c, "article_number", "") or "")
        if art:
            by_article[art] = by_article.get(art, "") + "\n" + str(getattr(c, "text", "") or "")

    for cr in clause_results:
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        tier = str(cr.get("risk_tier") or cr.get("severity") or "").upper()
        if tier not in ("MEDIUM",):
            # HIGH 는 메모로 덮지 않는다. LOW 는 이미 참고 항목이다.
            continue
        text = _finding_text(cr)
        if _RX_NEVER_KEEP.search(text):
            continue
        note = matching_note(cr, state)
        if note is None:
            continue
        report.checked += 1

        # 메모는 "고쳤다" 는 주장일 뿐이다. 그 조항 문언이 실제로 그 쟁점을
        # 담고 있는지 확인한 뒤에만 KEEP 한다.
        article = str(cr.get("article_number") or "")
        body = by_article.get(article, "")
        if body:
            overlap = sum(1 for kw in note.keywords if kw in body)
            if overlap < 2:
                continue

        cr["keep_as_is"] = True
        cr["risk_tier"] = "LOW"
        cr["severity"] = "LOW"
        cr["review_tier"] = "NOTE"
        cr["must_fix"] = False
        cr["approval_required"] = False
        cr["high_risk"] = False
        cr["scope_verdict"] = KEEP_VERDICT
        cr["prior_revision_keep"] = {
            "marker": note.marker,
            "note": note.note,
            "reason": (
                "사업부가 이 조항을 이미 수정했고, 현재 문언이 그 쟁점을 담고 "
                "있어 추가 수정이 필요하지 않습니다."
            ),
        }
        for field_name in ("suggested_rewrite", "proposed_revision", "recommendation_text"):
            if cr.get(field_name):
                cr[field_name] = ""
        report.kept.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            "marker": note.marker,
        })
    return report
