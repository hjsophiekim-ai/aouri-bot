"""사내변호사형 AI 에이전트 — 계약의 본질을 먼저 이해하고, 회사에 실제로
법률·세무·경제적 리스크가 있는 논점만 골라내는 다단계 검토 패스.

2026-09-10 지시 항목 3 — "계약서 본질을 정확히 이해하고 사내변호사처럼 꼭
필요한 논점 위주, 회사에 세무적·법률적·경제적으로 리스크가 있는 내용 위주로
검토하도록 해줘. AI 에이전트를 이용해서."

무엇이 문제였나 (대물교환 계약 실측, session 2ae2a937…)
────────────────────────────────────────────────────────
종전 파이프라인은 조항을 하나씩 훑어 53건의 finding 을 만들었다. 그 결과는
사내변호사의 검토의견이 아니라 조항 목록에 가까웠다.

  · 제3조~제19조를 항 단위로 거의 전부 지적 (MEDIUM 남발)
  · 자가점검이 "검토 의견이 없는 축: **추가공사**, 불가항력, 계약해지" 라고
    적었다 — 이 계약에는 공사가 없다. 계약유형을 "물품 인도 + 설치 급부"로
    잘못 이해한 결과다.
  · 정작 담당자가 가장 먼저 물은 **하도급법상 대물변제 금지**(바터 구조의
    적법성 자체)에 대한 판단은 "해당 조항 없음 — 사실관계 확인 필요"로 끝났다.
  · **세무 논점은 한 건도 없었다.** 교환거래의 과세표준을 "소비자가"로 잡은
    제5조 제2항은 부가가치세법상 시가 기준과 어긋날 수 있고, 특수관계 여부에
    따라 부당행위계산부인까지 이어질 수 있는데 아무도 보지 않았다.

즉 "조항을 빠짐없이 본다"는 목표는 달성했지만 "이 계약에서 회사가 실제로 무엇을
잃을 수 있는가"라는 질문에는 답하지 못했다.

이 모듈이 하는 일
──────────────
사내변호사가 계약을 검토하는 순서를 그대로 3단계 에이전트 패스로 만든다.

  Pass 1 (이해)  계약 전문을 읽고 거래구조를 확정한다 — 급부/반대급부, 우리
                 지위, 대가의 형태와 가액 산정 근거, 계약의 경제적 실질,
                 적용 가능성이 있는 법령 후보. 이 단계에서 "이 계약이 무엇인지"를
                 틀리면 뒤가 전부 틀리므로 여기서만 판단하고 이후 재추론하지 않는다.

  Pass 2 (쟁점)  그 이해를 전제로 **법률·세무·경제** 세 축에서 회사에 실질
                 리스크가 있는 논점만 뽑는다. 각 논점은 반드시 계약 원문을
                 인용하거나(있는 조항), "계약서에 없다"고 명시해야 한다(누락).
                 담당자가 적어 보낸 검토요청은 최우선 논점으로 다룬다.

  Pass 3 (검증)  ① 인용문이 계약 원문에 실제로 존재하는지 **결정론적으로**
                 확인한다(AI 에게 되묻지 않는다). ② 남은 논점을 중요도 순으로
                 정렬하고, 사내변호사가 협상 테이블에서 실제로 꺼내지 않을
                 항목은 잘라낸다.

산출물은 기존 파이프라인의 `clause_results` 항목과 같은 모양이라, 이후의
중복제거·필터·게이트·DOCX 작성기를 그대로 통과한다.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from runtime.ai.enhance import _build_request, _try_json
from runtime.ai.provider import AIProvider
from runtime.ai.safe import sanitize_error_message

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 26000

#: 리스크 축. 사용자가 지시한 세 가지("세무적·법률적·경제적")를 그대로 쓴다.
RISK_AXES: tuple[str, ...] = ("legal", "tax", "economic")

AXIS_LABELS: dict[str, str] = {
    "legal": "법률",
    "tax": "세무",
    "economic": "경제",
}

#: 인용문 검증에서 무시할 문자(공백·따옴표·괄호류). 원문과 AI 인용문의
#: 사소한 표기 차이 때문에 정당한 논점이 떨어지지 않도록 한다.
_RX_NORMALIZE = re.compile(r"[\s\"'“”‘’`()（）\[\]【】·・,.:;]+")


@dataclass
class DealUnderstanding:
    """Pass 1 산출물 — 이 검토 전체가 전제로 삼는 계약의 실질."""

    transaction_summary: str = ""
    contract_nature: str = ""
    our_party: str = ""
    our_role: str = ""
    our_obligations: str = ""
    counterparty_obligations: str = ""
    consideration_structure: str = ""
    economic_substance: str = ""
    candidate_statutes: list[str] = field(default_factory=list)
    not_applicable_topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_summary": self.transaction_summary,
            "contract_nature": self.contract_nature,
            "our_party": self.our_party,
            "our_role": self.our_role,
            "our_obligations": self.our_obligations,
            "counterparty_obligations": self.counterparty_obligations,
            "consideration_structure": self.consideration_structure,
            "economic_substance": self.economic_substance,
            "candidate_statutes": list(self.candidate_statutes),
            "not_applicable_topics": list(self.not_applicable_topics),
        }

    def as_prompt_block(self) -> str:
        return (
            f"거래 요약: {self.transaction_summary}\n"
            f"법적 성질: {self.contract_nature}\n"
            f"우리 회사: {self.our_party} / 지위: {self.our_role}\n"
            f"우리 의무: {self.our_obligations}\n"
            f"상대방 의무: {self.counterparty_obligations}\n"
            f"대가 구조: {self.consideration_structure}\n"
            f"경제적 실질: {self.economic_substance}\n"
            f"적용 가능 법령 후보: {', '.join(self.candidate_statutes) or '(없음)'}\n"
            f"이 계약에 존재하지 않는 주제(지적 금지): {', '.join(self.not_applicable_topics) or '(없음)'}"
        )


@dataclass
class CounselIssue:
    """Pass 2 산출물 한 건."""

    axis: str
    title: str
    clause_path: str
    quote: str
    is_missing_clause: bool
    our_exposure: str
    legal_basis: str
    recommendation: str
    severity: str
    materiality_reason: str
    #: 상대방에게 그대로 건넬 수 있는 완성 조문 문안(지시 항목 7).
    proposed_clause_text: str = ""
    practical_position: str = ""
    #: 세무·회계 처리 자체의 판단 — 법무 결론과 분리한다(지시 항목 7).
    finance_confirmation: str = ""
    grounded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "title": self.title,
            "clause_path": self.clause_path,
            "quote": self.quote,
            "is_missing_clause": self.is_missing_clause,
            "our_exposure": self.our_exposure,
            "legal_basis": self.legal_basis,
            "recommendation": self.recommendation,
            "severity": self.severity,
            "materiality_reason": self.materiality_reason,
            "proposed_clause_text": self.proposed_clause_text,
            "practical_position": self.practical_position,
            "finance_confirmation": self.finance_confirmation,
            "grounded": self.grounded,
        }


@dataclass
class CounselReport:
    status: str = "skipped"        # "ai" | "skipped" | "error"
    understanding: DealUnderstanding = field(default_factory=DealUnderstanding)
    issues: list[CounselIssue] = field(default_factory=list)
    dropped_ungrounded: list[dict[str, Any]] = field(default_factory=list)
    dropped_immaterial: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "understanding": self.understanding.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "dropped_ungrounded": list(self.dropped_ungrounded),
            "dropped_immaterial": list(self.dropped_immaterial),
            "error": self.error,
        }


# ── Pass 1 ───────────────────────────────────────────────────────────────────

_UNDERSTAND_SYSTEM = """당신은 한국 대기업의 사내변호사다. 계약서를 받으면 조항을 훑기 전에
"이 계약이 실제로 무슨 거래인가"부터 확정한다. 계약서 제목이나 당사자가 붙인 이름이 아니라
급부와 반대급부의 실질로 판단한다.

이 단계에서 계약의 성격을 틀리면 이후 검토가 전부 틀린다. 그러므로 여기서는 판단만 하고,
계약에 없는 개념을 끌어오지 않는다.

출력은 JSON 하나만. 설명·마크다운·코드펜스 금지."""

_UNDERSTAND_USER = """[우리 회사] {entity}
[담당자 입력 계약유형] {contract_type}

[계약서 전문]
{text}

아래 JSON 스키마로만 답하라.

{{
  "transaction_summary": "이 계약이 실제로 무슨 거래인지 두 문장 이내",
  "contract_nature": "법적 성질 (예: 매매, 도급, 위임, 임대차, 라이선스, 대물교환(바터). 복합이면 복합 구조를 그대로 적는다)",
  "our_party": "이 계약에서 우리 회사에 해당하는 당사자 명칭",
  "our_role": "우리 회사의 실질 지위 (예: 물품 공급자 겸 콘텐츠 사용권 취득자)",
  "our_obligations": "우리가 지는 핵심 의무",
  "counterparty_obligations": "상대방이 지는 핵심 의무",
  "consideration_structure": "대가가 어떻게 오가는지. 금전 지급이 없으면 그 사실과 가액 산정 기준을 명시",
  "economic_substance": "회사가 이 거래로 실제로 얻는 것과 내주는 것, 그 경제적 크기",
  "candidate_statutes": ["이 거래에 적용될 가능성이 있는 법령을 구체적으로 (예: '부가가치세법 제29조(과세표준 - 시가)', '하도급거래 공정화에 관한 법률 제17조')"],
  "not_applicable_topics": ["이 계약에 존재하지 않아 지적하면 오류가 되는 주제 (예: '추가공사', '재고 소유권', '판매수수료')"]
}}"""


# ── Pass 2 ───────────────────────────────────────────────────────────────────

_ISSUE_SYSTEM = """당신은 한국 대기업의 사내변호사다. 계약 검토의견을 쓸 때
조항을 하나씩 나열하지 않는다. 회사가 이 거래로 **실제로 무엇을 잃을 수 있는가**만 쓴다.

반드시 지킬 것:
1. 법률·세무·경제 세 축을 모두 검토한다. 특히 **세무는 빠뜨리기 쉬우니 반드시 본다** —
   과세표준 산정 기준, 세금계산서 발행 시기·금액, 특수관계인 거래, 대가의 시가 적정성,
   손금·비용 인정 여부, 원천징수 의무 등.
   단, **세무·회계 리스크를 과장하지 않는다.** 계약서에 금액이 적혀 있지 않으면
   "수천만원", "수억원", "10~25%" 같은 손실·추징 규모를 **추정하지 마라**.
   금액을 쓸 수 있는 것은 계약서에 그 숫자가 적혀 있을 때뿐이다.
   그리고 세무 논점은 "법무가 계약 문구로 할 수 있는 것"과 "재경·세무팀이
   확인해야 하는 것"을 반드시 나누어 쓴다 — recommendation 에는 계약 문구만 쓰고,
   세무처리 자체의 판단은 finance_confirmation 에 적는다.
2. 각 논점은 반드시 계약 원문의 문장을 **그대로** 인용한다. 인용문을 지어내면 안 된다.
   조항 자체가 없어서 문제인 경우에만 quote를 빈 문자열로 두고 is_missing_clause를 true로 한다.
3. "일반적으로 ~하는 것이 바람직합니다" 같은 일반론은 쓰지 않는다.
   회사에 어떤 금액·어떤 상황의 손실이 발생하는지 구체적으로 쓴다.
4. 협상 테이블에서 실제로 요구하지 않을 사소한 항목은 아예 넣지 않는다.
   조항 수가 많다고 논점이 많은 것이 아니다.
5. 위 이해 단계가 "이 계약에 존재하지 않는다"고 적은 주제는 절대 지적하지 않는다.
6. **법률 적용요건 판단은 이미 끝났다.** 아래 "적용법률 선판단" 에서 비적용으로
   확정된 법률은 어떤 형태로도 논점에 올리지 마라 — 그 법률의 의무·금지·제재를
   언급하는 것 자체가 오류다. 법률명이 떠오른다는 이유로 적용하지 않는다.
7. 우리 회사에 유리한 조항이라도 **강행법규를 어기면 고쳐야 한다.**
   적용되는 하도급법·대리점법·대규모유통업법·공정거래법·약관규제법 등에 비추어
   우리 계약서가 거래상 지위를 남용하거나 상대방에게 부당한 불이익을 주고 있으면,
   그 조항을 법령 준수 방향으로 수정하는 논점을 반드시 올린다. 이때는 어떤 법의
   어느 조문에 어떻게 저촉되는지를 legal_basis 에 명시한다.
   반대로 유리하면서 적법한 조항은 건드리지 않는다 — 상대방 청구권을 굳이
   새로 열어주는 수정안은 만들지 않는다.

출력은 JSON 하나만. 설명·마크다운·코드펜스 금지."""

_ISSUE_USER = """[계약의 실질 — 이 판단을 전제로 검토하라]
{understanding}

[적용법률 선판단 — 이 결론을 뒤집지 말 것]
{statutes}

[담당자가 직접 적어 보낸 검토요청 — 최우선으로 답할 것]
{review_focus}

[계약서 전문]
{text}

아래 JSON 스키마로만 답하라.

{{
  "issues": [
    {{
      "axis": "legal" | "tax" | "economic",
      "title": "논점 제목 (한 줄)",
      "clause_path": "관련 조항 (예: '제5조 제2항'). 계약서에 없으면 빈 문자열",
      "quote": "계약 원문에서 그대로 옮긴 문장. 지어내지 말 것. 조항이 없으면 빈 문자열",
      "is_missing_clause": true | false,
      "our_exposure": "우리 회사에 발생하는 구체적 손실·부담 (금액 규모나 상황을 명시)",
      "legal_basis": "근거 법령·법리 (조문 번호까지)",
      "recommendation": "협상에서 요구할 수정 방향",
      "proposed_clause_text": "상대방에게 그대로 건넬 수 있는 **완성된 조문 문안**. 기존 조항을 고치는 경우에는 원문을 유지한 채 필요한 문장만 더하거나 바꾼 전체 문장을 쓴다. 조항 신설이면 신설 조문 전문을 쓴다. '추후 협의', 'TBD', 빈칸은 절대 쓰지 말 것",
      "practical_position": "협상 실무 포지션 — 상대방이 받아들일 가능성과 대안",
      "finance_confirmation": "세무·회계 축인 경우, 재경/세무팀이 확인해야 할 사항. 법무가 계약 문구로 해결할 수 없는 부분만. 해당 없으면 빈 문자열",
      "severity": "HIGH" | "MEDIUM",
      "materiality_reason": "왜 이것이 꼭 다뤄야 할 논점인지"
    }}
  ]
}}

논점은 최대 {max_issues}개. 중요한 것부터 적는다.
세무 축 논점이 하나도 없다면, 정말 세무 리스크가 없는지 다시 확인한 뒤 없을 때만 비운다."""


# ── Pass 3 (중요도 컷) ────────────────────────────────────────────────────────

_CULL_SYSTEM = """당신은 법무팀장이다. 후배 변호사가 올린 검토의견 초안에서
"협상 테이블에서 실제로 꺼낼 논점"만 남기고 나머지를 잘라낸다.

남길 기준: 이 항목을 그대로 두면 회사가 금전·권리·세무상 실제로 손해를 볼 수 있는가.
자르는 기준: 일반론, 계약 관행상 다툴 실익이 없는 것, 다른 항목과 사실상 같은 이야기.

출력은 JSON 하나만."""

_CULL_USER = """[계약의 실질]
{understanding}

[검토의견 초안]
{issues}

아래 JSON 스키마로만 답하라.

{{
  "keep_indexes": [남길 항목의 0-기반 인덱스],
  "drop_reasons": {{"인덱스": "자른 이유"}}
}}

최소 {min_keep}개는 남긴다. 담당자가 직접 요청한 쟁점에 답하는 항목은 반드시 남긴다."""


def _clip(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    s = str(text or "")
    if len(s) <= limit:
        return s
    head = s[: int(limit * 0.7)]
    tail = s[-int(limit * 0.25):]
    return f"{head}\n\n…(중략)…\n\n{tail}"


def _norm(s: str) -> str:
    return _RX_NORMALIZE.sub("", str(s or ""))


def _norm_with_map(s: str) -> tuple[str, list[int]]:
    """정규화 문자열과, 그 각 문자가 원문에서 몇 번째였는지의 대응표.

    정규화 후 찾은 위치를 원문 위치로 되돌려 **계약서에 실제로 적힌 문장**을
    인용문으로 되돌려주기 위해 필요하다.
    """
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(s or ""):
        if _RX_NORMALIZE.match(ch):
            continue
        out.append(ch)
        idx.append(i)
    return "".join(out), idx


def _sentence_around(text: str, start: int, end: int) -> str:
    """원문에서 [start, end) 를 포함하는 문장 하나를 잘라낸다."""
    left = max(
        text.rfind("\n", 0, start),
        text.rfind(". ", 0, start),
        text.rfind("다.", 0, start),
    )
    left = 0 if left < 0 else left + 1
    right = len(text)
    for marker in ("\n", "다.", ". "):
        j = text.find(marker, end)
        if j >= 0:
            right = min(right, j + len(marker))
    return text[left:right].strip()


def _call_json(
    provider: AIProvider,
    *,
    model: str,
    system: str,
    user: str,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
) -> Any | None:
    try:
        resp = provider.complete(
            _build_request(
                model=model, system=system, user=user,
                timeout_sec=timeout_sec, max_tokens=max_tokens, temperature=temperature,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("counsel_agent call failed: %s", sanitize_error_message(str(exc)))
        return None
    return _try_json(getattr(resp, "content", "") or "")


def understand_deal(
    provider: AIProvider,
    *,
    model: str,
    entity: str,
    contract_type: str,
    text: str,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
) -> DealUnderstanding | None:
    data = _call_json(
        provider,
        model=model,
        system=_UNDERSTAND_SYSTEM,
        user=_UNDERSTAND_USER.format(
            entity=str(entity or "(미상)"),
            contract_type=str(contract_type or "(미상)"),
            text=_clip(text),
        ),
        timeout_sec=timeout_sec,
        max_tokens=min(max_tokens, 1400),
        temperature=temperature,
    )
    if not isinstance(data, dict):
        return None
    return DealUnderstanding(
        transaction_summary=str(data.get("transaction_summary") or "").strip(),
        contract_nature=str(data.get("contract_nature") or "").strip(),
        our_party=str(data.get("our_party") or "").strip(),
        our_role=str(data.get("our_role") or "").strip(),
        our_obligations=str(data.get("our_obligations") or "").strip(),
        counterparty_obligations=str(data.get("counterparty_obligations") or "").strip(),
        consideration_structure=str(data.get("consideration_structure") or "").strip(),
        economic_substance=str(data.get("economic_substance") or "").strip(),
        candidate_statutes=[str(x).strip() for x in (data.get("candidate_statutes") or []) if str(x).strip()][:12],
        not_applicable_topics=[str(x).strip() for x in (data.get("not_applicable_topics") or []) if str(x).strip()][:12],
    )


def format_statute_decisions(decisions: list[dict[str, Any]] | None) -> str:
    """적용법률 선판단을 프롬프트 블록으로. 비적용은 이유까지 그대로 싣는다."""
    rows = [d for d in (decisions or []) if isinstance(d, dict)]
    if not rows:
        return "(선판단 없음 — 법률 적용요건을 스스로 확인하고, 확실하지 않으면 단정하지 마라)"
    out: list[str] = []
    for d in rows:
        out.append(
            f"· {d.get('statute')}: {d.get('conclusion')} — {d.get('reason')}"
        )
    return "\n".join(out)


def spot_issues(
    provider: AIProvider,
    *,
    model: str,
    understanding: DealUnderstanding,
    review_focus: str | None,
    text: str,
    max_issues: int,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
    statute_decisions: list[dict[str, Any]] | None = None,
) -> list[CounselIssue]:
    def _ask(limit: int) -> Any | None:
        return _call_json(
            provider,
            model=model,
            system=_ISSUE_SYSTEM,
            user=_ISSUE_USER.format(
                understanding=understanding.as_prompt_block(),
                statutes=format_statute_decisions(statute_decisions),
                review_focus=str(review_focus or "").strip() or "(없음)",
                text=_clip(text),
                max_issues=int(limit),
            ),
            timeout_sec=timeout_sec,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    data = _ask(max_issues)
    if not isinstance(data, dict):
        # 응답이 max_tokens 에서 잘리면 JSON 이 닫히지 않아 파싱이 실패하고,
        # 그 결과가 "논점 없음" 과 구분되지 않는다 — 실측: 같은 계약에서
        # 6~7건이 나오던 검토가 한 번은 0건으로 나와 세무 논점이 통째로
        # 사라졌다. 항목 수를 줄여 한 번 더 물어본다.
        logger.warning("counsel_agent: issue JSON unparseable, retrying with fewer issues")
        data = _ask(max(4, int(max_issues) // 2))
    if not isinstance(data, dict):
        return []
    out: list[CounselIssue] = []
    for raw in (data.get("issues") or []):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        axis = str(raw.get("axis") or "").strip().lower()
        axis = axis if axis in RISK_AXES else "legal"
        severity = str(raw.get("severity") or "").strip().upper()
        severity = severity if severity in ("HIGH", "MEDIUM") else "MEDIUM"
        out.append(
            CounselIssue(
                axis=axis,
                title=title,
                clause_path=str(raw.get("clause_path") or "").strip(),
                quote=str(raw.get("quote") or "").strip(),
                is_missing_clause=bool(raw.get("is_missing_clause")),
                our_exposure=str(raw.get("our_exposure") or "").strip(),
                legal_basis=str(raw.get("legal_basis") or "").strip(),
                recommendation=str(raw.get("recommendation") or "").strip(),
                severity=severity,
                materiality_reason=str(raw.get("materiality_reason") or "").strip(),
                proposed_clause_text=str(raw.get("proposed_clause_text") or "").strip(),
                practical_position=str(raw.get("practical_position") or "").strip(),
                finance_confirmation=str(raw.get("finance_confirmation") or "").strip(),
            )
        )
        if len(out) >= max_issues:
            break
    return out


def verify_grounding(
    issues: list[CounselIssue],
    contract_text: str,
) -> tuple[list[CounselIssue], list[dict[str, Any]]]:
    """인용문이 계약 원문에 실제로 존재하는지 **결정론적으로** 확인한다.

    AI 에게 "정말 있느냐"고 되묻지 않는다 — 지어낸 인용을 지어낸 근거로
    확인시키는 셈이기 때문이다. 원문을 정규화해 부분 문자열로 대조한다.

    조항 자체의 부재를 지적하는 항목(`is_missing_clause`)은 인용이 없는 것이
    정상이므로 통과시킨다.
    """
    haystack, index_map = _norm_with_map(contract_text)
    kept: list[CounselIssue] = []
    dropped: list[dict[str, Any]] = []
    #: 앵커 길이. 이만큼의 연속 문자가 원문에 그대로 있으면 그 논점이 실재하는
    #: 조항을 가리킨다고 본다 — 우연히 일치할 길이가 아니다.
    _ANCHOR = 30
    for issue in issues:
        if issue.is_missing_clause and not issue.quote:
            issue.grounded = True
            kept.append(issue)
            continue
        needle = _norm(issue.quote)
        if len(needle) < 12:
            # 인용이 지나치게 짧으면 "우연히 포함됨"으로 통과할 수 있어
            # 근거로 인정하지 않는다.
            dropped.append({"title": issue.title, "reason": "quote_too_short", "quote": issue.quote[:80]})
            continue
        if needle in haystack:
            issue.grounded = True
            kept.append(issue)
            continue

        # AI 는 긴 조항을 **축약해서** 인용하는 일이 잦다(각 호를 건너뛰거나
        # 말미를 자른다). 그때 전체 대조만 하면 실재하는 조항을 가리킨 정당한
        # 논점까지 버려진다 — 실측: 제9조 제3항(저작권 2차 활용)과 제5조 제4항
        # 이 그렇게 떨어져 담당자가 가장 중요하게 본 쟁점이 사라졌다.
        #
        # 그래서 인용문 앞부분의 연속 앵커가 원문에 실재하면 논점은 남기되,
        # **표시되는 인용문을 계약서의 실제 문장으로 교체**한다. 계약서에 없는
        # 문장이 결과에 노출되는 일은 여전히 없다.
        anchor = needle[:_ANCHOR]
        pos = haystack.find(anchor) if len(anchor) >= _ANCHOR else -1
        if pos >= 0:
            start = index_map[pos]
            end = index_map[min(pos + len(anchor), len(index_map)) - 1] + 1
            real = _sentence_around(contract_text, start, end)
            if real:
                issue.quote = real[:800]
                issue.grounded = True
                kept.append(issue)
                continue
        dropped.append({"title": issue.title, "reason": "quote_not_found_in_contract", "quote": issue.quote[:80]})
    return kept, dropped


def cull_immaterial(
    provider: AIProvider,
    *,
    model: str,
    understanding: DealUnderstanding,
    issues: list[CounselIssue],
    min_keep: int,
    timeout_sec: float,
    max_tokens: int,
    temperature: float,
) -> tuple[list[CounselIssue], list[str]]:
    """협상에서 실제로 꺼내지 않을 논점을 잘라낸다."""
    if len(issues) <= min_keep:
        return issues, []
    listing = json.dumps(
        [
            {
                "index": i,
                "axis": it.axis,
                "title": it.title,
                "clause_path": it.clause_path,
                "our_exposure": it.our_exposure[:300],
                "severity": it.severity,
            }
            for i, it in enumerate(issues)
        ],
        ensure_ascii=False,
    )
    data = _call_json(
        provider,
        model=model,
        system=_CULL_SYSTEM,
        user=_CULL_USER.format(
            understanding=understanding.as_prompt_block(),
            issues=listing,
            min_keep=int(min_keep),
        ),
        timeout_sec=timeout_sec,
        max_tokens=min(max_tokens, 900),
        temperature=temperature,
    )
    if not isinstance(data, dict) or not isinstance(data.get("keep_indexes"), list):
        return issues, []
    keep: list[int] = []
    for x in data["keep_indexes"]:
        try:
            i = int(x)
        except Exception:
            continue
        if 0 <= i < len(issues) and i not in keep:
            keep.append(i)
    if len(keep) < min_keep:
        # 팀장 패스가 과하게 잘라내면 원본을 신뢰한다 — 이 단계의 목적은
        # 정리이지 검토 결과를 비우는 것이 아니다.
        return issues, []
    kept = [issues[i] for i in sorted(keep)]
    reasons = [
        f"{issues[i].title}: {str((data.get('drop_reasons') or {}).get(str(i)) or '중요도 낮음')}"
        for i in range(len(issues))
        if i not in keep
    ]
    return kept, reasons


def run_counsel_agent(
    *,
    provider: AIProvider | None,
    model: str,
    entity: str,
    contract_type: str,
    text: str,
    review_focus: str | None = None,
    statute_decisions: list[dict[str, Any]] | None = None,
    max_issues: int = 12,
    min_keep: int = 5,
    timeout_sec: float = 120.0,
    max_tokens: int = 4000,
    temperature: float = 0.1,
) -> CounselReport:
    """3단계 에이전트 패스를 순서대로 실행한다."""
    if provider is None or not str(text or "").strip():
        return CounselReport(status="skipped")

    understanding = understand_deal(
        provider, model=model, entity=entity, contract_type=contract_type, text=text,
        timeout_sec=timeout_sec, max_tokens=max_tokens, temperature=temperature,
    )
    if understanding is None:
        return CounselReport(status="error", error="계약 실질 파악(Pass 1)에 실패했습니다.")

    issues = spot_issues(
        provider, model=model, understanding=understanding, review_focus=review_focus,
        text=text, max_issues=max_issues, statute_decisions=statute_decisions,
        timeout_sec=timeout_sec, max_tokens=max_tokens, temperature=temperature,
    )
    if not issues:
        return CounselReport(status="ai", understanding=understanding)

    issues, dropped_ungrounded = verify_grounding(issues, text)
    issues, dropped_immaterial = cull_immaterial(
        provider, model=model, understanding=understanding, issues=issues,
        min_keep=min(min_keep, len(issues)),
        timeout_sec=timeout_sec, max_tokens=max_tokens, temperature=temperature,
    )

    return CounselReport(
        status="ai",
        understanding=understanding,
        issues=issues,
        dropped_ungrounded=dropped_ungrounded,
        dropped_immaterial=dropped_immaterial,
    )


# ── clause_results 변환 ──────────────────────────────────────────────────────

def _match_clause(issue: CounselIssue, clauses: list[Any] | None) -> Any | None:
    """인용문이 실제로 들어있는 조항을 찾는다 — 조항 번호 표기가 달라도
    본문 대조로 붙이므로, 잘못된 조항 참조가 생기지 않는다."""
    if not clauses or not issue.quote:
        return None
    needle = _norm(issue.quote)
    if len(needle) < 12:
        return None
    probe = needle[: max(12, int(len(needle) * 0.6))]
    for c in clauses:
        body = c.get("text") if isinstance(c, dict) else getattr(c, "text", "")
        if probe in _norm(str(body or "")):
            return c
    return None


def _clause_field(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def counsel_issues_to_clause_results(
    report: CounselReport,
    clauses: list[Any] | None,
    *,
    last_article_number: int = 0,
) -> list[dict[str, Any]]:
    """에이전트 논점을 기존 파이프라인의 clause_results 항목으로 변환한다.

    · 인용문이 붙는 조항이 있으면 그 조항의 id/경로를 그대로 쓴다 —
      존재하지 않는 조항을 가리켜 조항참조 게이트에 걸리는 일이 없다.
    · 조항이 없는 논점(누락)은 신설 권고로 표시한다.
    """
    out: list[dict[str, Any]] = []
    for i, issue in enumerate(report.issues, start=1):
        matched = _match_clause(issue, clauses)
        axis_label = AXIS_LABELS.get(issue.axis, issue.axis)

        problem = issue.our_exposure or issue.materiality_reason or issue.title
        reason_parts = [p for p in (issue.legal_basis, issue.materiality_reason) if p]
        legal_reason = " / ".join(reason_parts) or problem

        cr: dict[str, Any] = {
            "clause_id": (
                _clause_field(matched, "clause_id") if matched is not None
                else f"counsel_{issue.axis}_{i:02d}"
            ),
            "clause_title": (
                _clause_field(matched, "title") or _clause_field(matched, "clause_title")
                if matched is not None else issue.title
            ),
            "display_path": (
                _clause_field(matched, "display_path") if matched is not None else ""
            ),
            "article_number": _clause_field(matched, "article_number") if matched is not None else "",
            "paragraph_number": _clause_field(matched, "paragraph_number") if matched is not None else "",
            "original_text": (
                issue.quote if issue.quote
                else "(해당 조항 없음 — 계약서에 신설 필요)"
            ),
            "risk_tier": issue.severity,
            "severity": issue.severity,
            "problem": problem,
            "rewrite_reason": f"[{axis_label} 리스크] {issue.title} — {problem}",
            "legal_business_reason": legal_reason,
            "recommendation_text": issue.proposed_clause_text or issue.recommendation,
            "suggested_rewrite": issue.proposed_clause_text or None,
            "negotiation_position": issue.practical_position or issue.recommendation,
            "negotiation_strategy": issue.practical_position or issue.recommendation,
            "confidence": 0.9,
            "is_checklist_item": bool(issue.is_missing_clause and matched is None),
            # 사내변호사 판단으로 올라온 논점은 출력 필터의 편집상 정리 대상이
            # 아니다 — 이 검토의 결론 그 자체이기 때문이다.
            "is_mandatory_review_target": True,
            "is_mandatory": True,
            "is_counsel_agent": True,
            # 파이프라인 후단의 여러 강등 루프(대부분 "suggested_rewrite 가
            # 없으면 가치가 낮다"는 전제)가 이 논점들을 LOW 까지 끌어내린다.
            # 에이전트가 매긴 등급을 따로 보관해 두었다가 출력 직전에 복원한다.
            "counsel_severity": issue.severity,
            # senior_counsel_judgment 의 "HIGH 가 정말 가장 큰 리스크인가"
            # 점검은 HIGH 마다 치명 근거(high_severity_basis)를 요구한다.
            # 에이전트는 그 근거를 이미 산출했으므로(우리 회사 노출 + 중요도
            # 판단) 그대로 기록한다 — 근거 없는 HIGH 를 만들지 않기 위한
            # 점검이지, 근거 있는 HIGH 를 막기 위한 점검이 아니다.
            "high_severity_basis": (
                f"counsel_agent[{issue.axis}]: {issue.our_exposure or issue.materiality_reason}"[:400]
                if issue.severity == "HIGH" else ""
            ),
            "counsel_axis": issue.axis,
            "counsel_axis_label": axis_label,
            "detected_issue_list": [{"issue_title": f"[{axis_label}] {issue.title}"[:120]}],
        }
        if issue.is_missing_clause and matched is None and last_article_number > 0:
            cr["display_path"] = f"제{last_article_number + 1}조 신설"

        # [완성 문구 보장, 2026-09-10 아키텍처 지시 항목 7] ─────────────────
        # HIGH/MEDIUM 은 예외 없이 "수정 위치 + edit type + 완성 문구 +
        # 수정 이유 + practical position" 을 갖춰야 한다. 에이전트가 조문
        # 문안을 쓰지 않았다면(또는 방향만 적었다면) 원문의 법률효과를 유지한
        # 최소수정안으로 채운다. 그것도 불가능하면 FACT_CONFIRMATION_REQUIRED
        # 로 표시하고 확인해야 할 사실을 명시한다.
        _attach_complete_edit(cr, issue)
        # 세무·회계 처리 판단은 법무 결론과 분리해 표시한다(지시 항목 7).
        if issue.finance_confirmation:
            from runtime.review.amount_claim_guard import split_finance_confirmation
            split_finance_confirmation(cr, issue.finance_confirmation)
        out.append(cr)
    return out


def _attach_complete_edit(cr: dict[str, Any], issue: CounselIssue) -> None:
    """finding 에 완성된 redline instruction 을 붙인다."""
    from runtime.review.minimal_edit import (
        apply_minimal_edit,
        mark_fact_confirmation_required,
    )
    from runtime.review.redline_instruction import build_redline_instruction

    display_path = str(cr.get("display_path") or "").strip()
    original = str(cr.get("original_text") or "").strip()
    proposed = str(issue.proposed_clause_text or "").strip()
    is_new_clause = bool(issue.is_missing_clause) or not original or original.startswith("(해당 조항 없음")

    if proposed:
        cr["redline_instruction"] = build_redline_instruction(
            finding_id=str(cr.get("finding_id") or ""),
            clause_id=str(cr.get("clause_id") or ""),
            severity=str(cr.get("risk_tier") or ""),
            edit_location=(
                f"{display_path} 신설" if is_new_clause and display_path
                else (f"{display_path} 교체" if display_path else "말미에 신설")
            ),
            edit_type="new_clause" if is_new_clause else "replace",
            target_text="" if is_new_clause else original,
            replacement_text=proposed,
            original_text="" if is_new_clause else original,
            reason=str(cr.get("rewrite_reason") or issue.materiality_reason or ""),
        )
        return

    if not is_new_clause and apply_minimal_edit(
        cr, reason="에이전트가 조문 문안을 제시하지 않아 최소수정안으로 보완했습니다.",
    ):
        return

    mark_fact_confirmation_required(
        cr,
        reason="이 쟁점은 계약 문언만으로 문구를 확정할 수 없습니다.",
        fact_needed=(
            issue.recommendation[:180] if issue.recommendation
            else "이 쟁점의 판단에 필요한 사실관계"
        ),
    )
