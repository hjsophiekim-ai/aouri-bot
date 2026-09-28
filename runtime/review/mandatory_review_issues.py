"""User Review Focus를 최상위 issue map으로 구조화한다(2026-09-08 지시 항목 2).

사용자가 검토사항을 구체적으로 제시하면 그것은 "참고 문구"가 아니라 반드시
답변해야 할 **mandatory_review_issues**다. 각 이슈는 최종 결과에서 다음 셋 중
하나로 반드시 답변되어야 한다.

    적정 / 수정 필요 / 별도계약 필요

하나라도 답변되지 않으면 `REVIEW_FAILED_USER_SCOPE_NOT_COVERED`.

`mandatory_review_target.py`와의 차이
------------------------------------
그 모듈은 사용자가 **조항번호**를 직접 인용한 경우("제5조 제2항")를 추적한다.
이 모듈은 사용자가 **쟁점**을 서술한 경우("background IP", "AI 학습 재사용")를
추적한다. 둘은 보완 관계이며 서로를 대체하지 않는다.

특정 계약(에이슬립 NDA)에 대한 하드코딩이 아니다 — 계약유형별 기본 이슈맵
표(`DEFAULT_ISSUE_MAP_BY_CONTRACT_TYPE`)와, review_focus 자유서술에서 이슈를
추출하는 키워드 매칭의 조합으로 동작한다. 표에 없는 계약유형은 사용자가
review_focus에 실제로 쓴 쟁점만 mandatory가 된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

VERDICT_OK = "적정"
VERDICT_NEEDS_FIX = "수정 필요"
VERDICT_SEPARATE_AGREEMENT = "별도계약 필요"
VERDICTS: tuple[str, ...] = (VERDICT_OK, VERDICT_NEEDS_FIX, VERDICT_SEPARATE_AGREEMENT)

REVIEW_FAILED_USER_SCOPE_NOT_COVERED = "REVIEW_FAILED_USER_SCOPE_NOT_COVERED"

SOURCE_CONTRACT_TYPE_DEFAULT = "contract_type_default"
SOURCE_USER_REQUEST = "user_request"
SOURCE_LABELS: dict[str, str] = {
    SOURCE_CONTRACT_TYPE_DEFAULT: "계약유형 기본 검토항목",
    SOURCE_USER_REQUEST: "사용자 요청",
}


@dataclass(frozen=True)
class MandatoryReviewIssue:
    """반드시 답변되어야 하는 검토 쟁점 하나."""

    code: str
    title: str
    # review_focus 자유서술에서 이 쟁점을 인식하기 위한 키워드(한/영).
    focus_keywords: tuple[str, ...] = ()
    # 계약 원문에 이 쟁점을 다루는 조항이 실제로 존재하는지 판정하는 패턴.
    # 매치되면(그리고 별도 finding이 없으면) "적정"으로 답변할 근거가 된다.
    clause_marker: re.Pattern[str] | None = None
    # 원문에 조항이 없을 때의 기본 답변. 계약 단계상 이 계약에서 정할 수
    # 없는 사항(개인정보 처리, 향후 개발결과 귀속 등)은 "별도계약 필요"가
    # 정답이고, 이 계약에서 정했어야 하는 사항은 "수정 필요"가 정답이다.
    verdict_when_absent: str = VERDICT_NEEDS_FIX
    # 이 쟁점이 **기본값으로** mandatory 가 되려면 계약이 갖춰야 할 성격.
    # "" 이면 그 계약유형 전체에 적용된다. 사용자가 review_focus 에 직접 쓴
    # 쟁점은 이 조건과 무관하게 mandatory 가 된다(2026-09-28 지시 — 기술협업
    # NDA 에서 사용자가 요청했던 "AI 학습 제한·음성·수면·건강 정보" 가 모든
    # NDA 의 '사용자 검토항목' 으로 나가던 오염의 원인).
    requires: str = ""
    # 이 쟁점이 왜 mandatory 가 되었는가 — "contract_type_default"(계약유형
    # 기본 이슈맵) / "user_request"(담당자가 review_focus 에 직접 적음).
    # 리포트는 이 값으로 두 출처를 구분해 보여준다. 기본 이슈맵 항목을
    # '사용자 검토항목' 이라고 부르면 담당자는 자기가 요청하지 않은 항목을
    # 자기 요청으로 읽는다.
    source: str = SOURCE_CONTRACT_TYPE_DEFAULT

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "title": self.title, "source": self.source}


# ── NDA(비밀유지계약) 기본 이슈맵 ────────────────────────────────────────────
NDA_MANDATORY_ISSUES: tuple[MandatoryReviewIssue, ...] = (
    MandatoryReviewIssue(
        code="confidentiality_scope",
        title="비밀정보의 정의·범위(파생정보 포함 여부)",
        focus_keywords=("비밀정보 범위", "비밀정보의 범위", "파생정보", "confidentiality scope", "비밀정보 정의"),
        clause_marker=re.compile(
            r"비밀정보[^.\n]{0,20}(말한다|정의|의미한다)"
            r"|[\"“]Confidential\s+Information[\"”]\s+(?:means|shall\s+mean|includes)",
            re.IGNORECASE,
        ),
    ),
    MandatoryReviewIssue(
        code="background_ip",
        title="Background IP(계약 전 보유·독자개발 기술)의 각 당사자 유지",
        focus_keywords=("background ip", "기존 보유 기술", "기존보유", "자사 기술", "배경지식재산"),
        clause_marker=re.compile(r"(소유권|지식재산권)[^.\n]{0,30}(제공한\s*당사자|각\s*당사자)[^.\n]{0,10}있"),
        requires="tech_collaboration",
    ),
    MandatoryReviewIssue(
        code="independently_developed_information",
        title="독자개발 정보의 비밀유지의무 예외",
        focus_keywords=("독자개발", "독자 개발", "independently developed", "independent development"),
        clause_marker=re.compile(r"독자적으로\s*개발한\s*정보|independently\s+developed", re.IGNORECASE),
    ),
    MandatoryReviewIssue(
        code="future_development_results",
        title="향후 공동·추가 개발결과(Foreground IP)의 귀속 유보",
        focus_keywords=("개발 결과", "개발결과", "공동개발", "공동 개발", "future development", "성과물 귀속"),
        clause_marker=re.compile(
            r"(공동\s*개발|추가\s*개발|개발\s*결과물?|개발\s*성과물?)[^.\n]{0,40}"
            r"(후속\s*계약|별도\s*계약|별도의\s*계약|별도로\s*정한다|따로\s*정한다)"
        ),
        verdict_when_absent=VERDICT_SEPARATE_AGREEMENT,
        requires="tech_collaboration",
    ),
    MandatoryReviewIssue(
        code="ai_training_data_reuse",
        title="범용 AI 모델 학습·개선 및 타 프로젝트 활용 제한",
        focus_keywords=("ai 학습", "모델 학습", "학습 데이터", "fine-tuning", "파인튜닝", "데이터 재사용", "ai training"),
        clause_marker=re.compile(
            r"(범용|일반)\s*(?:AI\s*)?모델[^.\n]{0,20}(학습|훈련)|타\s*(?:고객|프로젝트)[^.\n]{0,20}(활용|사용)\s*(?:하지|금지|제한)"
        ),
        requires="tech_collaboration",
    ),
    MandatoryReviewIssue(
        code="personal_sensitive_data",
        title="개인정보·민감정보 처리의 계약 경계",
        focus_keywords=("개인정보", "민감정보", "건강정보", "음성", "수면 데이터", "personal data", "sensitive data"),
        clause_marker=re.compile(r"개인정보[^.\n]{0,40}(별도(?:의)?\s*(?:서면\s*)?계약|처리위탁\s*계약|따로\s*정한다)"),
        verdict_when_absent=VERDICT_SEPARATE_AGREEMENT,
        requires="tech_collaboration",
    ),
    MandatoryReviewIssue(
        code="permitted_recipients",
        title="비밀정보 제공이 허용되는 수령자 범위(외부 협력업체 포함)",
        focus_keywords=("제3자 제공", "제삼자 제공", "협력업체", "외부 개발사", "시험기관", "permitted recipients", "수령자"),
        clause_marker=re.compile(r"제\s*3\s*자에게\s*제공[^.\n]{0,40}(사전\s*서면\s*승인|비밀유지계약)"),
    ),
    MandatoryReviewIssue(
        code="confidentiality_duration",
        title="비밀유지기간 및 영업비밀 존속(survival)",
        focus_keywords=("비밀유지기간", "비밀유지 기간", "존속", "survival", "계약기간", "duration"),
        clause_marker=re.compile(
            r"비밀유지의무[^.\n]{0,60}(존속|유효)"
            r"|(?:obligations?|agreement)[^.]{0,80}(?:survive|continue)[^.]{0,60}(?:after|following|termination|indefinitely)",
            re.IGNORECASE,
        ),
    ),
    MandatoryReviewIssue(
        code="return_destruction_backup",
        title="반환·폐기 및 자동백업 예외",
        focus_keywords=("반환", "폐기", "파기", "백업", "backup", "return/destruction", "destruction"),
        clause_marker=re.compile(r"(반환|폐기)[^.\n]{0,60}(백업|자동\s*보관|법령상\s*보존)"),
    ),
    MandatoryReviewIssue(
        code="damages_injunction",
        title="손해배상 및 가처분 등 보전처분",
        focus_keywords=("손해배상", "가처분", "보전처분", "injunction", "damages"),
        clause_marker=re.compile(
            r"(손해를?\s*배상|가처분|보전처분)|injunctive\s+(?:or\s+other\s+equitable\s+)?relief",
            re.IGNORECASE,
        ),
    ),
    MandatoryReviewIssue(
        code="subsequent_agreement_priority",
        title="후속 계약과 본 계약의 우선순위",
        focus_keywords=("후속 계약", "후속계약", "우선", "priority", "정식계약", "본계약 우선"),
        clause_marker=re.compile(r"(우선한다|우선하여\s*적용|본\s*계약이\s*우선)"),
        requires="tech_collaboration",
    ),
)

#: 기술협업·공동개발 성격의 NDA 인가 — 서로 다른 신호가 두 가지 이상일 때만.
#: 낱말 하나("개발")로 판단하지 않는다: 직원 비밀유지서약도 "independently
#: developed" 를 예외로 쓴다.
_TECH_COLLAB_SIGNALS: tuple[re.Pattern[str], ...] = (
    re.compile(r"공동\s*개발|협업\s*개발|기술\s*(?:협력|협업|검토|평가)|joint\s+development|collaborat", re.IGNORECASE),
    re.compile(r"알고리즘|소스\s*코드|source\s+code|프로토타입|prototype|시제품", re.IGNORECASE),
    re.compile(r"\bAI\b|인공지능|머신\s*러닝|machine\s+learning|(?:학습|훈련)\s*데이터|training\s+data", re.IGNORECASE),
    re.compile(r"특허|patent|발명|invention|기술\s*자료|technical\s+(?:data|information)", re.IGNORECASE),
    re.compile(r"개발\s*(?:결과|성과|계약)|후속\s*(?:계약|개발)|정식\s*계약|definitive\s+agreement", re.IGNORECASE),
    re.compile(r"개인정보|민감정보|건강|생체|biometric|health\s+data", re.IGNORECASE),
)


def contract_has_character(requires: str, contract_text: str | None) -> bool:
    """계약이 그 쟁점을 기본값으로 물을 성격을 갖췄는가.

    원문이 넘어오지 않으면(구 호출자) 종전처럼 전부 적용한다.
    """
    if not requires:
        return True
    if contract_text is None:
        return True
    if requires == "tech_collaboration":
        hits = sum(1 for rx in _TECH_COLLAB_SIGNALS if rx.search(contract_text))
        return hits >= 2
    return True

DEFAULT_ISSUE_MAP_BY_CONTRACT_TYPE: dict[str, tuple[MandatoryReviewIssue, ...]] = {
    "nda_confidentiality": NDA_MANDATORY_ISSUES,
}

_ALL_ISSUES_BY_CODE: dict[str, MandatoryReviewIssue] = {
    i.code: i for issues in DEFAULT_ISSUE_MAP_BY_CONTRACT_TYPE.values() for i in issues
}


def derive_mandatory_review_issues(
    *,
    contract_type_code: str,
    review_focus: str | None = None,
    contract_text: str | None = None,
    default_issues: tuple[MandatoryReviewIssue, ...] | None = None,
) -> list[MandatoryReviewIssue]:
    """이 검토에서 반드시 답변해야 할 쟁점 목록.

    계약유형 기본 이슈맵이 있으면 그 계약의 성격에 맞는 항목이 mandatory다
    (NDA에서 비밀정보 범위·존속기간을 "사용자가 안 물어봐서" 빼먹는 일이
    없도록). 여기에 review_focus에서 키워드로 인식된 쟁점을 합집합으로 더한다.

    `contract_text` 가 넘어오면 `requires` 조건을 원문으로 확인한다 — 기술협업
    NDA 전용 항목(AI 학습 제한·Foreground IP 등)이 모든 NDA 에 붙지 않게.
    `default_issues` 가 넘어오면 계약유형 표 대신 그것을 기본 이슈맵으로 쓴다
    (거래모델이 확정된 하위유형 — 예: 임직원 비밀유지계약).
    """
    from dataclasses import replace as _replace

    code = (contract_type_code or "").strip()
    defaults = (
        tuple(default_issues) if default_issues is not None
        else DEFAULT_ISSUE_MAP_BY_CONTRACT_TYPE.get(code, ())
    )
    low = (review_focus or "").lower()

    def _asked(issue: MandatoryReviewIssue) -> bool:
        return bool(low.strip()) and any(k.lower() in low for k in issue.focus_keywords if k)

    out: dict[str, MandatoryReviewIssue] = {}
    for issue in defaults:
        if _asked(issue):
            out[issue.code] = _replace(issue, source=SOURCE_USER_REQUEST)
        elif contract_has_character(issue.requires, contract_text):
            out[issue.code] = _replace(issue, source=SOURCE_CONTRACT_TYPE_DEFAULT)

    # 하위유형 이슈맵이 주어졌으면 다른 계약유형의 카탈로그에서 항목을 끌어오지
    # 않는다 — 직원 서약서의 "개인정보" 한 낱말로 기술협업 NDA 의 "민감정보
    # 처리 계약 경계(별도계약 필요)" 가 붙으면 그것이 곧 계약 간 오염이다.
    if low.strip() and default_issues is None:
        for issue in _ALL_ISSUES_BY_CODE.values():
            if issue.code in out:
                continue
            if _asked(issue):
                out[issue.code] = _replace(issue, source=SOURCE_USER_REQUEST)
    return list(out.values())


def _finding_blob(cr: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "clause_title", "issue_title", "suggested_rewrite", "proposed_revision",
        "recommendation_text", "rewrite_reason", "legal_business_reason", "problem",
    ):
        v = cr.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    return "\n".join(parts)


def answer_mandatory_review_issues(
    issues: list[MandatoryReviewIssue],
    *,
    clause_results: list[dict[str, Any]],
    full_text: str,
) -> list[dict[str, Any]]:
    """각 mandatory issue에 대해 적정/수정 필요/별도계약 필요 중 하나로 답변한다.

    답변 근거의 우선순위:
      1. 그 쟁점을 명시적으로 태깅한 finding(`mandatory_issue_code`)이 있으면
         그 finding이 스스로 선언한 `scope_verdict`(없으면 "수정 필요").
      2. 태깅은 없지만 쟁점 키워드가 걸리는 HIGH/MEDIUM finding이 있으면
         "수정 필요".
      3. finding이 없고 계약 원문에 그 쟁점을 다루는 조항이 실제로 있으면
         "적정".
      4. 그 외에는 쟁점별 기본값(`verdict_when_absent`).
    """
    text = str(full_text or "")
    live = [
        cr for cr in clause_results
        if isinstance(cr, dict) and not bool(cr.get("dedup_suppressed"))
    ]

    answers: list[dict[str, Any]] = []
    for issue in issues:
        verdict = ""
        evidence_clause_ids: list[str] = []
        basis = ""

        for cr in live:
            codes = cr.get("mandatory_issue_code") or cr.get("mandatory_issue_codes")
            codes = [codes] if isinstance(codes, str) else list(codes or [])
            if issue.code in codes:
                declared = str(cr.get("scope_verdict") or "").strip()
                verdict = declared if declared in VERDICTS else VERDICT_NEEDS_FIX
                evidence_clause_ids.append(str(cr.get("clause_id") or ""))
                basis = "tagged_finding"

        if not verdict:
            for cr in live:
                if str(cr.get("risk_tier") or cr.get("severity") or "").upper() not in ("HIGH", "MEDIUM"):
                    continue
                blob = _finding_blob(cr).lower()
                if any(k.lower() in blob for k in issue.focus_keywords if k):
                    verdict = VERDICT_NEEDS_FIX
                    evidence_clause_ids.append(str(cr.get("clause_id") or ""))
                    basis = "keyword_matched_finding"

        if not verdict and issue.clause_marker is not None and issue.clause_marker.search(text):
            verdict = VERDICT_OK
            basis = "clause_present_and_acceptable"

        if not verdict:
            verdict = issue.verdict_when_absent
            basis = "absent_from_contract"

        answers.append({
            "code": issue.code,
            "title": issue.title,
            "source": issue.source,
            "source_label": SOURCE_LABELS.get(issue.source, ""),
            "verdict": verdict,
            "basis": basis,
            "evidence_clause_ids": evidence_clause_ids[:5],
        })
    return answers


def check_all_issues_answered(answers: list[dict[str, Any]]) -> list[str]:
    """답변되지 않았거나 허용되지 않은 값으로 답변된 쟁점 code 목록."""
    return [
        str(a.get("code") or "")
        for a in answers or []
        if str(a.get("verdict") or "") not in VERDICTS
    ]
