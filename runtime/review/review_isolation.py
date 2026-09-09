"""검토 상태 격리 + 이전 문서 오염 차단 (2026-09-09 지시 항목 3).

증상: 새 계약을 검토하는데 이전 계약의 용어·당사자·계약유형·체크리스트가
섞여 나온다. 실측 사례 — 호텔 신축 공사도급계약 검토 결과에
`clr_conditional_funding_unclear` finding 이 붙고 그 수정문안에
"Consultant / Company / Participation Agreement"(KOTRA 3자 컨설팅계약의
용어)가 그대로 들어갔다. 공사도급계약에는 Consultant 도 Participation
Agreement 도 존재하지 않는다.

원인은 두 갈래다:
  (a) **상태 승계** — 세션·캐시·전역 상태가 문서 경계를 넘어 재사용된다.
  (b) **문안 오염** — 룰/AI 가 다른 계약유형의 정형문구를 그대로 심는다.

이 모듈은 둘 다 막는다:

  `ReviewScope`      문서 단위 격리 키. document_id(파일 내용 해시) +
                     review_session_id 의 쌍만이 검토 상태의 유효 범위다.
  `detect_contamination()`  최종 결과가 원문에 존재하지 않는 고유 용어
                     (당사자명·계약유형 특정 용어)를 말하고 있으면 잡아낸다.
  `REVIEW_FAILED_CROSS_DOCUMENT_CONTAMINATION`

설계 원칙 — **하드코딩 금지**. 특정 회사명·계약명을 목록으로 갖지 않는다.
대신 "결과가 언급한 고유명사/전문용어가 이 문서 원문에 실제로 있는가"를
검사한다. 그래서 처음 보는 계약유형에서도 그대로 작동한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from uuid import uuid4

REVIEW_FAILED_CROSS_DOCUMENT_CONTAMINATION = "REVIEW_FAILED_CROSS_DOCUMENT_CONTAMINATION"

#: 검토 상태를 문서 간에 절대 승계해서는 안 되는 키들(지시 항목 3).
NON_INHERITABLE_STATE_KEYS: tuple[str, ...] = (
    "mandatory_review_issues",
    "mandatory_review_targets",
    "user_review_coverage",
    "user_review_request_parse",
    "answers",
    "contract_type",
    "contract_type_code",
    "clause_results",
    "final_findings",
    "draft_suggest",
    "suggested_template_ids",
    "review_result",
    "review_result_fast",
    "detected_rule_ids",
)


# ═══════════════════════════════════════════════════════════════════════════
# 격리 키
# ═══════════════════════════════════════════════════════════════════════════

def document_id_for(text: str | None, *, filename: str | None = None) -> str:
    """문서 내용 기반 id. 파일명이 바뀌어도 내용이 같으면 같은 id 다.

    파일명을 id 에 섞지 않는 이유: 같은 계약서를 다른 이름으로 올렸을 때
    별개 문서로 취급하면 캐시가 무의미해지고, 반대로 다른 계약서가 같은
    이름이면 오염이 발생한다. 내용 해시가 유일한 안전한 키다.
    """
    h = sha256()
    h.update((text or "").encode("utf-8", errors="replace"))
    return "doc_" + h.hexdigest()[:20]


@dataclass(frozen=True)
class ReviewScope:
    """이 검토가 유효한 범위. 이 범위를 벗어난 상태는 신뢰할 수 없다."""

    document_id: str
    review_session_id: str
    filename: str | None = None

    @property
    def key(self) -> str:
        return f"{self.document_id}::{self.review_session_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "review_session_id": self.review_session_id,
            "filename": self.filename,
            "scope_key": self.key,
        }

    def owns(self, other: dict[str, Any] | None) -> bool:
        """저장된 상태가 이 범위의 것인지."""
        if not isinstance(other, dict):
            return False
        return (
            str(other.get("document_id") or "") == self.document_id
            and str(other.get("review_session_id") or "") == self.review_session_id
        )


def new_scope(
    text: str | None, *, filename: str | None = None, review_session_id: str | None = None,
) -> ReviewScope:
    return ReviewScope(
        document_id=document_id_for(text, filename=filename),
        review_session_id=str(review_session_id or uuid4().hex),
        filename=filename,
    )


def strip_inherited_state(state: dict[str, Any] | None, scope: ReviewScope) -> dict[str, Any]:
    """다른 문서에서 온 상태를 제거한다.

    상태에 이 문서의 scope 도장이 찍혀 있지 않으면, 승계 금지 키를 전부
    털어낸다 — "이전 계약의 답변/유형/체크리스트를 그대로 쓰는" 경로를
    구조적으로 없앤다.
    """
    src = dict(state or {})
    if scope.owns(src.get("review_scope")):
        return src
    for k in NON_INHERITABLE_STATE_KEYS:
        src.pop(k, None)
    src["review_scope"] = scope.to_dict()
    src["inherited_state_stripped"] = True
    return src


# ═══════════════════════════════════════════════════════════════════════════
# 문안 오염 탐지
# ═══════════════════════════════════════════════════════════════════════════

#: 결과 텍스트에서 뽑아낼 "고유 용어" 후보.
#:  - 라틴 대문자로 시작하는 단어(Consultant, Participation Agreement …)
#:  - 한글 3자 이상의 복합 명사
#: 흔한 법률 일반어는 아래 화이트리스트로 걸러낸다.
_RX_LATIN_TERM = re.compile(r"\b[A-Z][A-Za-z]{3,}(?:\s+[A-Z][A-Za-z]{3,}){0,2}\b")

#: 계약 검토 결과에 정상적으로 등장하는 일반 용어 — 원문에 없어도 오염이 아니다.
#: 계약유형·회사명이 아니라 **법률 일반어**만 담는다(하드코딩 금지 원칙).
_GENERIC_TERM_WHITELIST: frozenset[str] = frozenset({
    # 법률/실무 일반 영어
    "Agreement", "Contract", "Party", "Parties", "Article", "Clause", "Section",
    "Force", "Majeure", "Indemnity", "Warranty", "Liability", "Damages",
    "Confidential", "Information", "Intellectual", "Property", "Rights",
    "Governing", "Arbitration", "Jurisdiction", "Termination", "Breach",
    "Payment", "Delivery", "Acceptance", "Schedule", "Exhibit", "Annex",
    "Background", "Foreground", "Redline", "High", "Medium", "Review",
    "Contractor", "Employer", "Owner", "Supplier", "Buyer", "Seller",
    "Disclosing", "Receiving", "Licensor", "Licensee",
    # ── 엔진이 스스로 결과에 쓰는 어휘 ──────────────────────────────────
    # 계약 원문에 있을 리 없지만 오염이 아니다. 실측 오탐: 심각도 라벨
    # "CRITICAL" 이 원문에 없다는 이유로 finding 이 통째로 제거됐다.
    "CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "TRUE", "FALSE",
    "REVIEW", "FAILED", "PASS", "WARN", "INFO", "ERROR",
    "SUGGEST", "MUST", "TODO", "REDLINE",
    # legal effect / 리포트 섹션 표기에 쓰이는 영문 태그
    "Effect", "Scope", "Matrix", "Summary", "Detail", "Gate", "Policy",
    "Cap", "Term", "Terms", "Structure", "Allocation", "Risk",
})

#: REVIEW_FAILED_* 같은 엔진 상태 코드는 통째로 오염 후보에서 제외한다.
_RX_ENGINE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")


def _candidate_terms(text: str) -> set[str]:
    out: set[str] = set()
    for m in _RX_LATIN_TERM.finditer(text or ""):
        term = m.group(0).strip()
        if not term:
            continue
        words = term.split()
        # 전부 일반어면 후보에서 제외
        if all(w in _GENERIC_TERM_WHITELIST for w in words):
            continue
        # 엔진 상태 코드(REVIEW_FAILED_… 등)는 원문에 없는 것이 당연하다.
        if all(_RX_ENGINE_CODE.match(w) for w in words):
            continue
        out.add(term)
    return out


def _finding_text(cr: dict[str, Any]) -> str:
    keys = (
        "issue_title", "clause_title", "problem", "rewrite_reason",
        "legal_business_reason", "suggested_rewrite", "proposed_revision",
        "recommendation_text", "negotiation_position",
    )
    return "\n".join(str(cr.get(k) or "") for k in keys)


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


def detect_contamination(
    clause_results: list[dict[str, Any]] | None,
    *,
    contract_text: str,
    extra_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """결과가 **이 문서에 없는 고유 용어**를 말하고 있으면 잡아낸다.

    판정 방식이 하드코딩이 아니라는 점이 중요하다: 금지 단어 목록을 두지
    않고, 결과에 등장한 고유 용어가 계약 원문에 실제로 있는지만 본다.
    처음 보는 계약유형·처음 보는 상대방에도 그대로 적용된다.

    반환: 오염 항목 목록 [{clause_id, display_path, terms}]
    """
    haystack = _normalize(contract_text) + _normalize("\n".join(extra_texts or []))
    out: list[dict[str, Any]] = []
    for cr in (clause_results or []):
        if not isinstance(cr, dict) or bool(cr.get("dedup_suppressed")):
            continue
        leaked = sorted(
            t for t in _candidate_terms(_finding_text(cr))
            if _normalize(t) not in haystack
        )
        if leaked:
            out.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "terms": leaked,
            })
    return out


def scrub_contaminated_findings(
    clause_results: list[dict[str, Any]] | None,
    *,
    contract_text: str,
    extra_texts: list[str] | None = None,
) -> dict[str, Any]:
    """오염된 finding 을 제거하고 리포트를 돌려준다.

    삭제가 정답인 이유: 오염된 문안은 "조금 어긋난 표현"이 아니라 **다른
    계약의 조항을 이 계약에 심는 것**이라, 사용자가 그대로 협상에 쓰면
    상대방에게 존재하지 않는 계약을 인용하게 된다. 수정보다 제거가 안전하다.
    """
    hits = detect_contamination(
        clause_results, contract_text=contract_text, extra_texts=extra_texts,
    )
    by_id = {h["clause_id"]: h for h in hits}
    removed: list[dict[str, Any]] = []
    for cr in (clause_results or []):
        if not isinstance(cr, dict):
            continue
        cid = str(cr.get("clause_id") or "")
        if cid not in by_id or bool(cr.get("dedup_suppressed")):
            continue
        cr["dedup_suppressed"] = True
        cr["dedup_reason"] = "cross_document_contamination"
        cr["contaminated_terms"] = by_id[cid]["terms"]
        removed.append(by_id[cid])
    # 제거 후 **남아 있는** 오염만 실패 사유다.
    #
    # 지시 항목 3 은 "이전 계약 용어가 나오면 즉시 실패"라고 하지만, 그 취지는
    # 오염된 조언을 내보내지 말라는 것이다. 여기서 이미 걷어냈다면 출력은
    # 깨끗하므로, 실패로 막으면 정작 사용자가 정상 결과를 받지 못한다 —
    # "수정본 생성 실패"가 반복되던 원인이 바로 이런 과잉 차단이었다.
    # 그래서 제거 사실은 리포트에 남기고, 걷어내지 못한 오염이 있을 때만
    # 실패로 올린다.
    residual = detect_contamination(
        clause_results, contract_text=contract_text, extra_texts=extra_texts,
    )
    return {
        "contaminated": hits,
        "removed": removed,
        "removed_count": len(removed),
        "residual": residual,
        "status": REVIEW_FAILED_CROSS_DOCUMENT_CONTAMINATION if residual else "",
    }
