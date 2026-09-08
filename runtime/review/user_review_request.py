"""User Review Request semantic parsing — 사용자의 자유서술 검토요청을
의미 단위의 법률쟁점으로 구조화한다(2026-09-08 지시).

핵심 원칙
---------
사용자의 검토요청은 **검색 키워드가 아니라 계약검토의 scope instruction**이다.
처음 보는 표현이거나 기존 rule/taxonomy에 없는 쟁점이라도, 의미를 이해해
mandatory issue로 구조화하고 최종 결과에서 반드시 답해야 한다.

`mandatory_review_issues.py`(계약유형별 기본 이슈맵)와의 관계
------------------------------------------------------------
그 모듈은 "이 계약유형이라면 아우리봇이 반드시 봐야 할 것"의 정본 목록이고,
이 모듈은 "사용자가 직접 봐달라고 한 것"을 추적한다. 우선순위는

    explicit user request > contract-type default > rule catalogue > AI-discovered

이며, 사용자 요청을 기존 taxonomy에 억지로 끼워 맞추지 않는다. 카탈로그
코드와 매칭되면 연결(`catalog_code`)하되, 매칭되지 않으면
`custom_user_issue`로 사용자의 표현 그대로 보존한다.

AI 불가 시(항목 6)
------------------
LLM 호출이 불가능하거나 실패하면 키워드/카탈로그 방식으로 fallback하되,
자유서술을 문장 단위로 쪼개 **카탈로그에 걸리지 않은 문장도 버리지 않고**
custom issue로 남긴다. 이때 `degraded=True`가 되고, UI/DOCX는 "사용자
자유서술 요청 일부를 의미 분석하지 못했습니다"를 명시한다 — 정상 완료로
위장하지 않는다.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from runtime.ai.enhance import _try_json
from runtime.ai.http_openai_compatible_provider import build_messages
from runtime.ai.provider import AIProvider, AIRequest
from runtime.review.senior_counsel_pass import (
    TOPIC_UNKNOWN,
    classify_topic,
    finding_topic,
    topics_compatible,
)
from runtime.review.mandatory_review_issues import (
    DEFAULT_ISSUE_MAP_BY_CONTRACT_TYPE,
    VERDICT_NEEDS_FIX,
    VERDICT_OK,
    VERDICT_SEPARATE_AGREEMENT,
)

logger = logging.getLogger(__name__)

# 항목 3 — 최종 검토에서 허용되는 답변. `mandatory_review_issues`의 3종에
# "사실관계 추가확인"이 더해진다: 사용자가 요청했지만 계약 문언만으로는
# 판단할 수 없어 사실관계 확인이 선행되어야 하는 쟁점을 "적정"으로 위장하지
# 않기 위한 값이다.
VERDICT_NEEDS_FACTS = "사실관계 추가확인"
USER_REQUEST_VERDICTS: tuple[str, ...] = (
    VERDICT_OK, VERDICT_NEEDS_FIX, VERDICT_SEPARATE_AGREEMENT, VERDICT_NEEDS_FACTS,
)

SOURCE_EXPLICIT = "explicit_user_request"
SOURCE_CONTRACT_DEFAULT = "contract_type_default"
SOURCE_RULE_CATALOGUE = "rule_catalogue"
SOURCE_AI_DISCOVERED = "ai_discovered"

# 우선순위 — 숫자가 작을수록 우선(항목 2).
_SOURCE_PRIORITY: dict[str, int] = {
    SOURCE_EXPLICIT: 0,
    SOURCE_CONTRACT_DEFAULT: 1,
    SOURCE_RULE_CATALOGUE: 2,
    SOURCE_AI_DISCOVERED: 3,
}

PARSE_STATUS_AI = "ai"
PARSE_STATUS_NO_AI = "no_ai_fallback_keyword"
PARSE_STATUS_AI_FAILED = "ai_call_failed_fallback_keyword"
PARSE_STATUS_EMPTY = "no_user_request"

DEGRADED_NOTICE = "사용자 자유서술 요청 일부를 의미 분석하지 못했습니다"

_RX_CLAUSE_CITATION = re.compile(
    r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?(?:\s*제\s*(\d+)\s*항)?(?:\s*제\s*(\d+)\s*호)?"
)
_RX_TOKEN = re.compile(r"[가-힣]{2,}|[A-Za-z]{3,}")
_STOPWORDS: frozenset[str] = frozenset({
    "계약", "조항", "내용", "경우", "관련", "대하여", "대해", "부분", "사항", "여부",
    "검토", "확인", "필요", "가능", "우리", "당사", "상대방", "그리고", "또는", "해서",
    "해주세요", "봐주세요", "주세요", "합니다", "습니다", "하는지", "있는지", "되는지",
    "충분한지", "이번", "다음", "전체", "모든", "특히", "정도", "때문", "위해", "통해",
    "the", "and", "for", "with", "that", "this", "please", "check", "review",
})


@dataclass
class UserReviewIssue:
    """사용자 검토요청에서 추출된 쟁점 하나."""

    issue_id: str
    source: str
    original_user_text: str
    normalized_issue: str
    # 기존 카탈로그(mandatory_review_issues)와 매칭된 코드. 매칭되지 않으면
    # 빈 문자열 — 억지로 끼워 맞추지 않고 custom_user_issue로 보존한다.
    catalog_code: str = ""
    expected_answer: bool = True
    cited_clause_paths: list[str] = field(default_factory=list)
    search_keywords: list[str] = field(default_factory=list)
    relevant_clause_ids: list[str] = field(default_factory=list)
    # clause_id -> 연결 강도. 같은 쟁점에 여러 조항이 걸렸을 때 어느 조항이
    # 더 확실한 근거인지 구분해, 결론을 그 조항의 finding으로 잡기 위한 값.
    clause_link_scores: dict[str, float] = field(default_factory=dict)
    # AI가 의미 단위로 정규화한 쟁점인지. keyword fallback으로 만든 쟁점은
    # search_keywords가 사용자 문장의 원시 토큰이라 finding 본문과의 어휘
    # 중첩만으로 "이 쟁점을 다룬 finding"이라고 단정할 수 없다 — 그런
    # 쟁점은 조항 연결로만 매칭하고, 근거가 없으면 "사실관계 추가확인"으로
    # 답한다(없는 근거로 "적정"/"수정 필요"를 만들어내지 않기 위함).
    semantic_parsed: bool = False

    @property
    def is_custom(self) -> bool:
        return not self.catalog_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "source": self.source,
            "original_user_text": self.original_user_text,
            "normalized_issue": self.normalized_issue,
            "catalog_code": self.catalog_code,
            "custom_user_issue": self.is_custom,
            "expected_answer": self.expected_answer,
            "cited_clause_paths": list(self.cited_clause_paths),
            "search_keywords": list(self.search_keywords),
            "relevant_clause_ids": list(self.relevant_clause_ids),
            "semantic_parsed": self.semantic_parsed,
        }


def issues_from_meta(parse_meta: dict[str, Any] | None) -> list[UserReviewIssue]:
    """meta["user_review_request_parse"]에 저장된 쟁점을 복원한다.

    DOCX/PDF 다운로드 경로는 clause_results를 독립적으로 재구성하므로 coverage를
    다시 계산해야 하지만, LLM을 다시 호출할 필요는 없다 — 최초 검토에서 이미
    구조화해 둔 쟁점을 그대로 복원해 새 clause_results에 대해 다시 답변한다.
    """
    out: list[UserReviewIssue] = []
    for raw in ((parse_meta or {}).get("issues") or []):
        if not isinstance(raw, dict):
            continue
        issue_id = str(raw.get("issue_id") or "").strip()
        if not issue_id:
            continue
        out.append(UserReviewIssue(
            issue_id=issue_id,
            source=str(raw.get("source") or SOURCE_EXPLICIT),
            original_user_text=str(raw.get("original_user_text") or ""),
            normalized_issue=str(raw.get("normalized_issue") or ""),
            catalog_code=str(raw.get("catalog_code") or ""),
            expected_answer=bool(raw.get("expected_answer", True)),
            cited_clause_paths=[str(x) for x in (raw.get("cited_clause_paths") or [])],
            search_keywords=[str(x) for x in (raw.get("search_keywords") or [])],
            relevant_clause_ids=[str(x) for x in (raw.get("relevant_clause_ids") or [])],
            semantic_parsed=bool(raw.get("semantic_parsed", False)),
        ))
    return out


@dataclass
class UserRequestParseResult:
    issues: list[UserReviewIssue]
    status: str
    degraded: bool
    unparsed_segments: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "degraded": self.degraded,
            "degraded_notice": DEGRADED_NOTICE if self.degraded else "",
            "unparsed_segments": list(self.unparsed_segments),
            "error": self.error,
            "issues": [i.to_dict() for i in self.issues],
        }


# ── AI 의미 파싱 ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """당신은 사내변호사의 계약검토 요청을 받아, 그 요청을 검토
가능한 법률쟁점 단위로 구조화하는 법무 어시스턴트입니다.

사용자가 자유롭게 서술한 검토요청을 읽고, 그 안에 담긴 **개별 법률쟁점**을
빠짐없이 분리해 JSON 배열로 반환하십시오. 사용자의 요청은 검색 키워드가
아니라 이 검토의 범위 지시(scope instruction)입니다.

반드시 지킬 것:
1. 사용자가 실제로 우려하거나 확인해달라고 한 쟁점만 추출하십시오. 사용자가
   말하지 않은 일반적인 계약 검토항목을 임의로 추가하지 마십시오.
2. 하나의 문장에 서로 다른 쟁점이 섞여 있으면 각각 분리하십시오.
3. 처음 보는 쟁점(신규 사업모델 관련 특수 책임, 기존 고객데이터 이전, 공동
   브랜드 사용, 독특한 환수구조, 특정 기술 아키텍처 등)이라도 절대 버리지
   말고 그대로 하나의 쟁점으로 만드십시오. 알려진 분류에 억지로 끼워 맞추면
   안 됩니다.
4. `catalog_code`는 아래 제공된 카탈로그 코드 중 **의미가 실질적으로 동일한**
   것이 있을 때만 채우고, 애매하면 반드시 null로 두십시오. 억지 매칭 금지.
5. `original_user_text`에는 이 쟁점의 근거가 된 사용자 원문을 그대로(요약·
   변형 없이) 발췌해 넣으십시오.
6. `cited_clauses`에는 사용자가 그 쟁점과 함께 직접 언급한 조항번호만
   넣으십시오(예: "제8조 제3항"). 사용자가 조항번호를 말하지 않았으면 빈
   배열로 두고, 임의로 추정하지 마십시오.
7. `search_keywords`에는 계약 원문에서 이 쟁점과 관련된 조항을 찾을 때 쓸
   핵심 명사 3~8개를 넣으십시오(사용자가 쓴 표현뿐 아니라 계약서에서 통상
   쓰이는 법률 용어도 함께).

출력 형식(JSON 배열만, 설명 문장·코드펜스 금지):
[
  {
    "issue_id": "user_ai_secondary_use",
    "issue": "당사 제공정보 또는 프로젝트 데이터의 범용 AI 모델 학습 및 타 고객 목적 이용 제한",
    "original_user_text": "에이슬립이 우리 데이터를 자사 범용 AI 학습이나 다른 고객 서비스 개선에 쓰지 못하도록 충분한지 봐주세요.",
    "expected_answer": true,
    "catalog_code": "ai_training_data_reuse",
    "cited_clauses": [],
    "search_keywords": ["학습", "모델", "데이터", "타 고객", "사용 제한"]
  }
]

issue_id는 영문 소문자·숫자·밑줄로만 구성하고 "user_"로 시작하며, 쟁점의
내용을 알아볼 수 있게 지으십시오."""


def _slug(raw: str, fallback_index: int) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", str(raw or "").strip().lower()).strip("_")
    if not s:
        s = f"issue_{fallback_index}"
    if not s.startswith("user_"):
        s = f"user_{s}"
    return s[:60]


def _catalog_codes(contract_type_code: str) -> list[str]:
    seen: list[str] = []
    for issues in DEFAULT_ISSUE_MAP_BY_CONTRACT_TYPE.values():
        for i in issues:
            if i.code not in seen:
                seen.append(i.code)
    return seen


def _all_catalog_issues() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for issues in DEFAULT_ISSUE_MAP_BY_CONTRACT_TYPE.values():
        for i in issues:
            out[i.code] = i
    return out


def _split_segments(text: str) -> list[str]:
    """자유서술을 의미 단위 후보(문장/절)로 쪼갠다 — fallback 경로 전용."""
    raw = re.split(r"[\n\r]+|(?<=[.。?!])\s+|,\s*|;\s*|·\s*", str(text or ""))
    return [s.strip() for s in raw if len(s.strip()) >= 4]


def _keyword_fallback_issues(review_focus: str, contract_type_code: str) -> tuple[list[UserReviewIssue], list[str]]:
    """AI 없이 자유서술에서 쟁점을 뽑는다.

    카탈로그 키워드에 걸리는 문장은 해당 코드에 연결하고, **아무 것도 걸리지
    않은 문장도 버리지 않고** custom issue로 남긴다(항목 4). 다만 이 경로의
    normalized_issue는 사용자 원문 그대로이므로, 호출자는 degraded로 표시해야
    한다.
    """
    catalog = _all_catalog_issues()
    issues: list[UserReviewIssue] = []
    unparsed: list[str] = []
    seen_codes: set[str] = set()

    for idx, seg in enumerate(_split_segments(review_focus)):
        low = seg.lower()
        matched_code = ""
        for code, ci in catalog.items():
            if any(k.lower() in low for k in ci.focus_keywords if k):
                matched_code = code
                break
        cited = _extract_citations(seg)
        if matched_code:
            if matched_code in seen_codes:
                continue
            seen_codes.add(matched_code)
            issues.append(UserReviewIssue(
                issue_id=f"user_{matched_code}",
                source=SOURCE_EXPLICIT,
                original_user_text=seg,
                normalized_issue=catalog[matched_code].title,
                catalog_code=matched_code,
                cited_clause_paths=cited,
                search_keywords=list(catalog[matched_code].focus_keywords)[:8],
            ))
            continue
        # 카탈로그에 없는 문장 — 의미 정규화는 못 했지만 요청 자체는 유지한다.
        tokens = _tokens(seg)
        if not tokens:
            continue
        unparsed.append(seg)
        issues.append(UserReviewIssue(
            issue_id=_slug(f"free_{idx}", idx),
            source=SOURCE_EXPLICIT,
            original_user_text=seg,
            normalized_issue=seg,
            catalog_code="",
            cited_clause_paths=cited,
            search_keywords=sorted(tokens)[:8],
        ))
    return issues, unparsed


def _extract_citations(text: str) -> list[str]:
    out: list[str] = []
    for m in _RX_CLAUSE_CITATION.finditer(text or ""):
        article, sub, para, item = m.group(1), m.group(2), m.group(3), m.group(4)
        parts = [f"제{article}{('의' + sub) if sub else ''}조"]
        if para:
            parts.append(f"제{para}항")
        if item:
            parts.append(f"제{item}호")
        path = " ".join(parts)
        if path not in out:
            out.append(path)
    return out


def _tokens(text: str) -> set[str]:
    return {
        t for t in _RX_TOKEN.findall(str(text or "").lower())
        if t not in _STOPWORDS and len(t) >= 2
    }


def parse_user_review_request(
    *,
    review_focus: str | None,
    contract_type_code: str,
    ai_provider: AIProvider | None = None,
    ai_model: str | None = None,
    ai_timeout_sec: float | None = None,
    ai_max_tokens: int | None = None,
    ai_temperature: float | None = None,
) -> UserRequestParseResult:
    """자유서술 검토요청을 구조화된 쟁점 목록으로 변환한다."""
    focus = str(review_focus or "").strip()
    if not focus:
        return UserRequestParseResult(issues=[], status=PARSE_STATUS_EMPTY, degraded=False)

    ai_enabled = bool(
        ai_provider and ai_model and ai_timeout_sec is not None
        and ai_max_tokens is not None and ai_temperature is not None
    )
    if not ai_enabled:
        issues, unparsed = _keyword_fallback_issues(focus, contract_type_code)
        return UserRequestParseResult(
            issues=issues,
            status=PARSE_STATUS_NO_AI,
            # 자유서술이 있는데 AI 의미분석을 못 했다면, 카탈로그에 우연히
            # 전부 걸렸더라도 "의미를 이해했다"고 주장할 수 없다.
            degraded=True,
            unparsed_segments=unparsed,
        )

    payload = {
        "review_focus": focus,
        "contract_type_code": contract_type_code,
        "catalog_codes": _catalog_codes(contract_type_code),
    }
    req = AIRequest(
        model=str(ai_model),
        messages=build_messages(_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False)),
        temperature=float(ai_temperature),
        max_tokens=int(ai_max_tokens),
        timeout_sec=float(ai_timeout_sec),
    )
    try:
        resp = ai_provider.complete(req)
        parsed = _try_json(resp.content)
    except Exception as exc:  # noqa: BLE001 — provider 종류를 가리지 않고 fallback
        logger.warning("user_review_request AI parse failed, falling back to keywords: %s", exc)
        issues, unparsed = _keyword_fallback_issues(focus, contract_type_code)
        return UserRequestParseResult(
            issues=issues, status=PARSE_STATUS_AI_FAILED, degraded=True,
            unparsed_segments=unparsed, error=str(exc)[:200],
        )

    if not isinstance(parsed, list) or not parsed:
        logger.warning("user_review_request AI response was not a non-empty JSON array")
        issues, unparsed = _keyword_fallback_issues(focus, contract_type_code)
        return UserRequestParseResult(
            issues=issues, status=PARSE_STATUS_AI_FAILED, degraded=True,
            unparsed_segments=unparsed, error="AI response was not a JSON array",
        )

    known_codes = set(_catalog_codes(contract_type_code))
    issues: list[UserReviewIssue] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(parsed):
        if not isinstance(raw, dict):
            continue
        normalized = str(raw.get("issue") or "").strip()
        if not normalized:
            continue
        issue_id = _slug(str(raw.get("issue_id") or ""), idx)
        while issue_id in seen_ids:
            issue_id = f"{issue_id}_{idx}"
        seen_ids.add(issue_id)
        code = str(raw.get("catalog_code") or "").strip()
        if code not in known_codes:
            # 억지 매칭 금지 — 모르는 코드는 custom으로 둔다.
            code = ""
        cited = [str(c).strip() for c in (raw.get("cited_clauses") or []) if str(c).strip()]
        kws = [str(k).strip() for k in (raw.get("search_keywords") or []) if str(k).strip()]
        original = str(raw.get("original_user_text") or "").strip() or focus
        issues.append(UserReviewIssue(
            issue_id=issue_id,
            source=SOURCE_EXPLICIT,
            original_user_text=original,
            normalized_issue=normalized,
            catalog_code=code,
            expected_answer=bool(raw.get("expected_answer", True)),
            cited_clause_paths=cited or _extract_citations(original),
            search_keywords=kws or sorted(_tokens(normalized))[:8],
            semantic_parsed=True,
        ))

    if not issues:
        fb, unparsed = _keyword_fallback_issues(focus, contract_type_code)
        return UserRequestParseResult(
            issues=fb, status=PARSE_STATUS_AI_FAILED, degraded=True,
            unparsed_segments=unparsed, error="AI returned no usable issue",
        )
    return UserRequestParseResult(issues=issues, status=PARSE_STATUS_AI, degraded=False)


# ── 항목 5: 조항 연결 (조항번호가 없어도 추적) ──────────────────────────────

def _clause_attr(c: Any, name: str) -> Any:
    if isinstance(c, dict):
        return c.get(name)
    return getattr(c, name, None)


def _token_weight(document_frequency: int, clause_count: int) -> float:
    """계약 전체에 흔한 어휘일수록 가중치를 낮춘다.

    "정보", "사용", "권한", "당사자"처럼 계약서 거의 모든 조항에 등장하는
    단어는 어느 조항이 그 쟁점과 관련 있는지 전혀 구별해주지 못한다. 반대로
    "개량", "브랜드", "학습"처럼 한두 조항에만 등장하는 단어가 실제 연결
    근거다. 불용어 목록을 계속 늘리는 대신 계약별 빈도로 자동 판별한다.
    """
    if document_frequency <= 0:
        return 0.0
    if clause_count and document_frequency > max(2, clause_count // 2):
        return 0.0
    if document_frequency <= 2:
        return 1.0
    if document_frequency <= 4:
        return 0.5
    return 0.0


def link_clauses_to_issues(
    issues: list[UserReviewIssue],
    clauses: list[Any] | None,
    *,
    min_score: float = 1.0,
    max_links: int = 4,
) -> None:
    """각 쟁점에 관련 조항을 연결한다(in-place).

    사용자가 조항번호를 명시했으면 그 조항을 우선 anchor로 사용하고, 그렇지
    않으면 쟁점의 법률효과 키워드와 계약 원문의 어휘 중첩으로 관련 조항을
    찾는다 — 사용자가 조항번호를 몰라도 추적되어야 하기 때문이다(항목 5).

    계약이 전혀 다루지 않는 쟁점(예: 브랜드 사용권이 없는 NDA에서의 공동
    브랜드 문의)에는 아무 조항도 연결되지 않아야 한다. 그래야 그 쟁점이
    "적정"이 아니라 "사실관계 추가확인"으로 답변된다.
    """
    chunks = [c for c in (clauses or []) if str(_clause_attr(c, "text") or "")]
    bodies = [(str(_clause_attr(c, "clause_id") or ""), str(_clause_attr(c, "text") or "").lower()) for c in chunks]

    for issue in issues:
        linked: list[str] = []
        scores: dict[str, float] = {}

        if issue.cited_clause_paths:
            wanted = {p.replace(" ", "") for p in issue.cited_clause_paths}
            for c in chunks:
                dp = str(_clause_attr(c, "display_path") or "").replace(" ", "")
                if not dp:
                    continue
                if any(dp == w or dp.startswith(w) or w.startswith(dp) for w in wanted):
                    cid = str(_clause_attr(c, "clause_id") or "")
                    if cid and cid not in linked:
                        linked.append(cid)
                        scores[cid] = 10.0  # 사용자가 직접 지목한 조항이 최우선 anchor

        if not linked and bodies:
            # 검색어는 쟁점 문장 전체가 아니라 retrieval용으로 뽑힌
            # search_keywords를 우선 사용한다 — 정규화된 쟁점 문장에는
            # "제품", "출시", "범위"처럼 계약 주제와 무관하게 우연히 계약
            # 어딘가에 등장하는 일반어가 섞여 있어, 계약이 전혀 다루지 않는
            # 쟁점에도 조항이 연결되는 원인이 된다.
            probe = {t for k in issue.search_keywords for t in _tokens(k)}
            if not probe:
                probe = _tokens(issue.normalized_issue)
            probe -= _STOPWORDS
            weights = {
                t: _token_weight(sum(1 for _, b in bodies if t in b), len(bodies))
                for t in probe
            }
            scored: list[tuple[float, str]] = []
            for cid, body in bodies:
                if not cid:
                    continue
                score = sum(w for t, w in weights.items() if w > 0 and t in body)
                if score >= min_score:
                    scored.append((score, cid))
            scored.sort(key=lambda x: (-x[0], x[1]))
            for score, cid in scored[:max_links]:
                linked.append(cid)
                scores[cid] = score

        issue.relevant_clause_ids = linked
        issue.clause_link_scores = scores


# ── 항목 3: coverage tracking ───────────────────────────────────────────────

def _live_findings(clause_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        cr for cr in (clause_results or [])
        if isinstance(cr, dict) and not bool(cr.get("dedup_suppressed"))
    ]


def _finding_blob(cr: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "clause_title", "issue_title", "suggested_rewrite", "proposed_revision",
        "recommendation_text", "rewrite_reason", "legal_business_reason",
    ):
        v = cr.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    return "\n".join(parts).lower()


#: verdict 별 답변 서두. "수정 필요"만 던지지 않고, 사용자 질문에 대한
#: 직접적인 답(그래서 보호되는가 / 안 되는가)으로 시작한다(항목 1).
_ANSWER_LEAD = {
    VERDICT_NEEDS_FIX: "아니요 — 현재 문언으로는 충분하지 않아 수정이 필요합니다",
    VERDICT_SEPARATE_AGREEMENT: "본 계약만으로는 처리할 수 없고 별도 계약이 필요합니다",
    VERDICT_OK: "예 — 현재 문언으로 커버됩니다",
    VERDICT_NEEDS_FACTS: "계약 문언만으로는 판단할 수 없어 사실관계 확인이 필요합니다",
}


def _direct_answer(
    *,
    verdict: str,
    matched: list[dict[str, Any]],
    answer_paths: list[str],
) -> str:
    """사용자 질문에 대한 한 문장 직답.

    근거 finding이 있으면 그 finding이 지적한 내용만 인용한다 — 주제 게이트를
    통과한 finding만 들어오므로, 여기서 다른 쟁점이 섞일 수 없다.
    """
    lead = _ANSWER_LEAD.get(verdict, verdict or "미답변")
    if matched:
        top = matched[0]
        detail = str(
            top.get("issue_title")
            or top.get("rewrite_reason")
            or top.get("clause_title")
            or ""
        ).strip()
        where = answer_paths[0] if answer_paths else str(top.get("display_path") or "")
        if detail and where:
            return f"{lead}. {where}: {detail}"
        if detail:
            return f"{lead}. {detail}"
        if where:
            return f"{lead}. 근거 조항: {where}"
        return lead
    if verdict == VERDICT_OK and answer_paths:
        return f"{lead}. {', '.join(answer_paths[:3])}에서 이 쟁점을 다루고 있으며 별도 수정이 필요한 리스크는 발견되지 않았습니다"
    if verdict == VERDICT_NEEDS_FACTS:
        return f"{lead}. 이 쟁점을 직접 다루는 조항이 계약에 없어, 사실관계 확인 후 조항 신설 여부를 결정해야 합니다"
    return lead


def build_user_request_coverage(
    issues: list[UserReviewIssue],
    *,
    clause_results: list[dict[str, Any]],
    clauses: list[Any] | None = None,
    catalog_answers: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """각 사용자 요청 쟁점에 대해 최종 판단을 만든다.

    판단 우선순위:
      1. 그 쟁점을 다루는 HIGH/MEDIUM finding이 있으면 → 그 finding이 선언한
         `scope_verdict`(없으면 "수정 필요").
      2. 카탈로그 코드에 연결되어 있고 그 코드의 기본 이슈맵 답변이 있으면
         → 그 답변.
      3. 관련 조항을 찾았고 finding이 없으면 → "적정".
      4. 그 외(관련 조항도 finding도 없음) → "사실관계 추가확인".
         계약 문언에 근거가 없는 쟁점을 "적정"으로 답하지 않기 위함이다.
    """
    live = _live_findings(clause_results)
    by_catalog = {
        str(a.get("code") or ""): a for a in (catalog_answers or []) if isinstance(a, dict)
    }
    clause_display = {
        str(_clause_attr(c, "clause_id") or ""): str(_clause_attr(c, "display_path") or "")
        for c in (clauses or [])
    }

    out: list[dict[str, Any]] = []
    for issue in issues:
        linked_paths = {clause_display.get(cid, "") for cid in issue.relevant_clause_ids}
        linked_paths.discard("")
        # 사용자가 직접 인용한 조항이 있으면 그것이 가장 정확한 anchor다.
        cited_norm = {p.replace(" ", "") for p in issue.cited_clause_paths}
        linked_norm = {p.replace(" ", "") for p in linked_paths}
        probe = {k.lower() for k in issue.search_keywords if k}

        # display_path -> 그 조항의 연결 강도. 여러 조항이 연결됐을 때 더
        # 확실한 근거 조항의 finding이 결론이 되도록 한다.
        path_score: dict[str, float] = {}
        for cid, sc in issue.clause_link_scores.items():
            dp = clause_display.get(cid, "").replace(" ", "")
            if dp:
                path_score[dp] = max(path_score.get(dp, 0.0), float(sc))

        # ── 주제 게이트 (2026-09-08 지시 항목 1) ────────────────────────────
        # 같은 조문에 여러 쟁점의 finding이 붙어 있으면, 조항 연결만으로는
        # "AI 학습" 질문에 개인정보·외부협력업체 finding이 그대로 딸려와
        # 엉뚱한 결론이 나온다. 양쪽 주제가 모두 특정되고 서로 다르면
        # 연결하지 않는다. 한쪽이라도 주제를 특정할 수 없으면(TOPIC_UNKNOWN)
        # 기존 동작을 유지한다 — 과잉 차단으로 답변이 비는 것이 더 나쁘다.
        issue_topic = classify_topic(
            " ".join([issue.normalized_issue or "", issue.original_user_text or ""])
        )

        def _topic_conflict(cr: dict[str, Any]) -> bool:
            if issue_topic == TOPIC_UNKNOWN:
                return False
            return not topics_compatible(issue_topic, finding_topic(cr))

        def _match(cr: dict[str, Any]) -> tuple[int, float] | None:
            """(rank, 연결강도). rank 0=사용자 인용 조항, 1=연결된 조항, 2=키워드."""
            dp = str(cr.get("display_path") or "").replace(" ", "")
            cid = str(cr.get("clause_id") or "")
            # 사용자가 조항을 직접 인용했더라도, 그 조문에 걸린 다른 주제의
            # finding을 이 질문의 답으로 삼으면 안 된다.
            if _topic_conflict(cr):
                return None
            if dp and any(dp.startswith(w) or w.startswith(dp) for w in cited_norm):
                return (0, 10.0)
            if cid in issue.relevant_clause_ids:
                return (1, issue.clause_link_scores.get(cid, 1.0))
            if dp:
                for w, sc in path_score.items():
                    if dp.startswith(w) or w.startswith(dp):
                        return (1, sc)
                if any(dp.startswith(w) or w.startswith(dp) for w in linked_norm):
                    return (1, 1.0)
            # 키워드 매칭은 AI가 의미 정규화한 쟁점에서만 허용한다 — fallback
            # 경로의 원시 토큰으로 매칭하면 "공동 브랜드 사용" 요청이 "공동
            # 개발결과 귀속" finding에 걸리는 식의 오답이 나온다.
            if issue.semantic_parsed and probe:
                blob = _finding_blob(cr)
                if sum(1 for k in probe if k in blob) >= 3:
                    return (2, 0.0)
            # 주제 일치 fallback (2026-09-08 지시 항목 1).
            # 조항 연결이 엉뚱한 조문을 가리켜도, 같은 주제를 다루는 finding이
            # 계약 어딘가에 있으면 그것이 이 질문의 답이다. 실제 사례: "범용 AI
            # 학습이 충분히 제한되어 있는지" 질문이 제2조로 연결되어, 제4조
            # 제1항의 "범용 AI 모델 학습 제한 부재"(HIGH) finding을 놓치고
            # "적정"으로 답했다 — 계약서가 정반대를 말하고 있는데도.
            # 주제 어휘는 큐레이션된 목록이라 원시 키워드보다 훨씬 안전하므로
            # semantic_parsed 여부와 무관하게 허용한다.
            if issue_topic != TOPIC_UNKNOWN and finding_topic(cr) == issue_topic:
                return (3, 0.0)
            return None

        ranked: list[tuple[int, float, int, dict[str, Any]]] = []
        for cr in live:
            if str(cr.get("risk_tier") or cr.get("severity") or "").upper() not in ("HIGH", "MEDIUM"):
                continue
            hit = _match(cr)
            if hit is None:
                continue
            # 같은 rank·연결강도 안에서는 더 구체적인 조항 경로(제8조 제3항 >
            # 제8조)를 먼저 둔다 — 사용자가 특정 항을 지목했을 때 그 항의
            # finding이 결론이 되어야 한다.
            ranked.append((hit[0], -hit[1], -len(str(cr.get("display_path") or "")), cr))
        ranked.sort(key=lambda x: (x[0], x[1], x[2]))
        matched = [cr for _, _, _, cr in ranked]

        conclusion = ""
        if matched:
            declared = ""
            for cr in matched:
                d = str(cr.get("scope_verdict") or "").strip()
                if d in USER_REQUEST_VERDICTS:
                    declared = d
                    break
            verdict = declared or VERDICT_NEEDS_FIX
            titles = [
                str(cr.get("issue_title") or cr.get("clause_title") or cr.get("clause_id") or "")
                for cr in matched[:3]
            ]
            conclusion = " / ".join(t for t in titles if t)
        elif issue.catalog_code and issue.catalog_code in by_catalog:
            verdict = str(by_catalog[issue.catalog_code].get("verdict") or VERDICT_NEEDS_FACTS)
            if verdict not in USER_REQUEST_VERDICTS:
                verdict = VERDICT_NEEDS_FACTS
            conclusion = "계약유형 기본 검토항목 판단과 동일"
        elif issue.relevant_clause_ids:
            verdict = VERDICT_OK
            conclusion = (
                "관련 조항이 계약에 존재하며 이번 검토에서 별도 수정이 필요한 리스크는 발견되지 않음"
            )
        else:
            verdict = VERDICT_NEEDS_FACTS
            conclusion = (
                "계약 문언에서 이 쟁점을 직접 다루는 조항을 찾지 못했습니다 — "
                "사실관계(실제 거래 방식·데이터 흐름 등) 확인 후 별도 조항 신설 여부를 결정해야 합니다"
            )

        # 답변에 실제로 쓰인 조항만 노출한다. 주제 게이트를 통과한 finding의
        # 조항이 있으면 그것이 근거이고, 없으면 연결된 조항을 그대로 쓴다 —
        # 결론과 무관한 조항을 "관련 조항"으로 열거하지 않기 위함(항목 1).
        answer_paths = [
            str(cr.get("display_path") or "") for cr in matched[:3]
            if str(cr.get("display_path") or "").strip()
        ]
        if not answer_paths:
            answer_paths = sorted(p for p in linked_paths if p)

        out.append({
            "issue_id": issue.issue_id,
            "source": issue.source,
            # 항목 1이 요구한 구조: original_user_text → relevant_clause →
            # direct_answer. 세 필드는 항상 함께 채워진다.
            "original_user_text": issue.original_user_text,
            "relevant_clause": ", ".join(answer_paths) if answer_paths else "해당 조항 없음",
            "direct_answer": _direct_answer(
                verdict=verdict, matched=matched, answer_paths=answer_paths,
            ),
            "issue_topic": issue_topic,
            "normalized_issue": issue.normalized_issue,
            "catalog_code": issue.catalog_code,
            "custom_user_issue": issue.is_custom,
            "relevant_clause_ids": list(issue.relevant_clause_ids),
            "relevant_clause_paths": sorted(p for p in linked_paths if p),
            "answer_clause_paths": answer_paths,
            "review_status": verdict,
            "needs_revision": verdict in (VERDICT_NEEDS_FIX, VERDICT_SEPARATE_AGREEMENT),
            "conclusion": conclusion,
            "matched_finding_ids": [str(cr.get("clause_id") or "") for cr in matched[:5]],
        })

    out.sort(key=lambda r: _SOURCE_PRIORITY.get(str(r.get("source") or ""), 9))
    return out


def check_user_request_coverage(coverage: list[dict[str, Any]]) -> list[str]:
    """답변되지 않은(또는 허용되지 않은 값으로 답변된) 요청의 issue_id 목록."""
    return [
        str(r.get("issue_id") or "")
        for r in (coverage or [])
        if str(r.get("review_status") or "") not in USER_REQUEST_VERDICTS
    ]


def superseded_catalog_codes(issues: list[UserReviewIssue]) -> set[str]:
    """사용자가 직접 요청해 explicit로 승격된 카탈로그 코드 집합.

    호출자는 계약유형 기본 이슈맵에서 이 코드들을 중복 노출하지 않도록
    표시할 수 있다 — 같은 쟁점을 아우리봇의 문구와 사용자의 문구로 두 번
    보고하지 않기 위함이며, 우선순위상 사용자의 표현이 이긴다(항목 2).
    """
    return {i.catalog_code for i in issues if i.catalog_code and i.source == SOURCE_EXPLICIT}
