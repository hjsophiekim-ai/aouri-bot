"""Contract Model 정합성 게이트 두 가지 — 질문·사용자요청 매핑.

2026-09-21 지시 3항 후단 / 12항.

  3항  "질문이 canonical contract model 과 불일치하면
        REVIEW_FAILED_QUESTION_MODEL_MISMATCH."
  12항 "사용자 질문 → 관련조항 → 결론의 의미 일치 강제. 검수 질문에 안전·산재
        finding 을 연결하는 식의 오매핑 금지.
        불일치 시 REVIEW_FAILED_USER_REQUEST_MAPPING_MISMATCH."

두 게이트 모두 **제거·기록 후 전달**이다. 어긋난 연결은 끊고 무엇이 왜
끊겼는지 남기되, 다운로드를 막지 않는다(2026-09-10 지시 2항).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REVIEW_FAILED_QUESTION_MODEL_MISMATCH = "REVIEW_FAILED_QUESTION_MODEL_MISMATCH"
REVIEW_FAILED_USER_REQUEST_MAPPING_MISMATCH = "REVIEW_FAILED_USER_REQUEST_MAPPING_MISMATCH"


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


# ══════════════════════════════════════════════════════════════════════════
# 1. 사전질문 ↔ canonical contract model
# ══════════════════════════════════════════════════════════════════════════

#: 계약유형별로 **성립하지 않는** 질문. 여기 적는 것은 "그 유형에서는 물어도
#: 답이 검토를 바꾸지 않는" 질문뿐이다 — 애매하면 적지 않는다.
INCOMPATIBLE_QUESTIONS_BY_TYPE: dict[str, tuple[str, ...]] = {
    # 공사도급에서 설계 결과물의 귀속은 부수 조항이다. 우리가 취득해서
    # 매체·기간·지역을 정해 활용할 지식재산이 아니다(지시 3항).
    "construction": ("Q-EFF-ip-scope", "Q-EFF-ip-ownership", "Q-EFF-license-scope"),
}

#: 그 유형이라면 **반드시** 물었어야 하는 질문의 접두사. 하나도 없으면 질문
#: 묶음 자체가 다른 계약의 것이다.
REQUIRED_QUESTION_PREFIX_BY_TYPE: dict[str, str] = {
    "construction": "Q-CONST-",
}


@dataclass
class QuestionModelReport:
    incompatible: list[dict[str, Any]] = field(default_factory=list)
    missing_pack: str = ""
    checked: int = 0

    @property
    def status(self) -> str:
        return (
            REVIEW_FAILED_QUESTION_MODEL_MISMATCH
            if (self.incompatible or self.missing_pack)
            else ""
        )

    @property
    def detail(self) -> str:
        parts: list[str] = []
        if self.incompatible:
            names = ", ".join(q["question_id"] for q in self.incompatible[:3])
            parts.append(
                f"이 계약유형에서 성립하지 않는 사전질문 {len(self.incompatible)}건이 "
                f"담당자에게 나갔습니다({names})."
            )
        if self.missing_pack:
            parts.append(self.missing_pack)
        return " ".join(parts)


def check_question_model_fit(
    questions: list[Any] | None,
    *,
    contract_type_code: str,
) -> QuestionModelReport:
    """담당자에게 실제로 나간 사전질문이 확정된 계약유형과 맞는가.

    질문 목록이 넘어오지 않으면 아무것도 판정하지 않는다 — 모르는 것을
    실패로 세지 않는다(2026-09-16 지시 9항과 같은 원칙).
    """
    report = QuestionModelReport()
    code = str(contract_type_code or "").strip()
    if not questions or not code:
        return report

    ids: list[str] = []
    for q in questions:
        if isinstance(q, dict):
            ids.append(str(q.get("question_id") or ""))
        else:
            ids.append(str(getattr(q, "question_id", "") or ""))
    ids = [i for i in ids if i]
    report.checked = len(ids)
    if not ids:
        return report

    for bad in INCOMPATIBLE_QUESTIONS_BY_TYPE.get(code, ()):
        if bad in ids:
            report.incompatible.append({
                "question_id": bad,
                "contract_type": code,
                "reason": (
                    "확정된 계약유형에서 이 질문은 판단을 바꾸지 않습니다 — "
                    "부수 조항을 주된 거래처럼 물었습니다."
                ),
            })

    prefix = REQUIRED_QUESTION_PREFIX_BY_TYPE.get(code, "")
    if prefix and not any(i.startswith(prefix) for i in ids):
        report.missing_pack = (
            f"확정된 계약유형({code})의 전용 사전질문이 하나도 나가지 않았습니다 — "
            "일반 질문만으로는 이 거래에서 무엇이 위험한지 확인하지 못합니다."
        )
    return report


# ══════════════════════════════════════════════════════════════════════════
# 2. 사용자 요청 ↔ 관련조항 ↔ 결론
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class UserRequestMappingReport:
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    checked: int = 0

    @property
    def status(self) -> str:
        return REVIEW_FAILED_USER_REQUEST_MAPPING_MISMATCH if self.mismatches else ""

    @property
    def detail(self) -> str:
        if not self.mismatches:
            return ""
        names = ", ".join(
            f"{m['issue_id']}→{m['relevant_clause']}" for m in self.mismatches[:3]
        )
        return (
            f"담당자 질문과 다른 법률효과의 조항을 연결한 항목 "
            f"{len(self.mismatches)}건의 연결을 해제했습니다 — {names}."
        )


_UNRESOLVED_LABEL = "조항 확인 필요"


def check_user_request_mapping(
    coverage: list[dict[str, Any]] | None,
    *,
    clauses: list[Any] | None,
) -> UserRequestMappingReport:
    """담당자 질문의 주제와, 거기 연결된 조항의 주제가 같은지 본다.

    같지 않으면 **연결만 끊는다**. 맞는 조항을 임의로 골라 갈아 끼우지
    않는다 — 그것은 추측이고, v10 이 금지한 행위다. 질문 자체는 남아
    "사실관계 확인" 으로 담당자에게 간다.
    """
    from runtime.review.clause_topic import (
        TOPIC_OTHER,
        classify_clause_topic,
        is_topic_compatible,
    )

    report = UserRequestMappingReport()
    if not isinstance(coverage, list) or not coverage:
        return report

    by_article: dict[str, Any] = {}
    for c in clauses or []:
        art = str(getattr(c, "article_number", "") or "")
        if art and art not in by_article:
            by_article[art] = c

    for row in coverage:
        if not isinstance(row, dict):
            continue
        paths = row.get("relevant_clause_paths")
        relevant = _norm(row.get("relevant_clause"))
        if not relevant or "없음" in relevant or _UNRESOLVED_LABEL in relevant:
            continue
        m = re.search(r"제\s*(\d+)\s*조", relevant)
        if not m:
            continue
        clause = by_article.get(m.group(1))
        if clause is None:
            continue
        report.checked += 1

        question_text = " ".join(
            _norm(row.get(k))
            for k in ("original_user_text", "normalized_issue", "objective_title")
        )
        question_topic = classify_clause_topic(title=None, text=question_text)
        clause_topic = classify_clause_topic(
            title=str(getattr(clause, "title", "") or ""),
            text=str(getattr(clause, "text", "") or ""),
        )
        if question_topic == TOPIC_OTHER or clause_topic == TOPIC_OTHER:
            continue
        if is_topic_compatible(clause_topic=clause_topic, rewrite_topics={question_topic}):
            continue

        report.mismatches.append({
            "issue_id": str(row.get("issue_id") or ""),
            "original_user_text": _norm(row.get("original_user_text"))[:120],
            "relevant_clause": relevant,
            "clause_topic": clause_topic,
            "question_topic": question_topic,
        })
        row["relevant_clause"] = _UNRESOLVED_LABEL
        row["relevant_clause_ids"] = []
        row["relevant_clause_paths"] = []
        row["answer_clause_paths"] = []
        row["review_status"] = "사실관계 추가확인"
        row["needs_revision"] = False
        row["direct_answer"] = (
            f"이 질문({question_topic})과 연결되어 있던 {relevant}는 다른 내용"
            f"({clause_topic})을 규정하고 있어 연결을 해제했습니다. 맞는 조항을 "
            "임의로 추정하지 않았으므로, 해당 쟁점을 다루는 조항을 확인한 뒤 "
            "적용하십시오."
        )
        row["conclusion"] = row["direct_answer"]
        if isinstance(paths, list):
            row["detached_clause_paths"] = list(paths)
    return report
