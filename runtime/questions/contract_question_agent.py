"""계약 본문을 실제로 읽고 그 계약에 맞는 사전 질문만 만드는 AI 에이전트.

2026-09-10 지시 항목 1 — 실사례: "콘텐츠 제작 대가로 가구를 공급하는
대물교환(바터) 계약"을 올렸는데, 사전 질문 5개가 전부 위탁매매 질문
(최종 판매자·재고 소유권·매출 귀속·POS 결제 명의·위탁판매자 여부)으로
나왔다. 이 계약에는 매매도, 고객도, 재고도, 판매수수료도 없다.

원인은 두 단계였다.

1. `transaction_structure_signals.detect_sales_transaction_ambiguity()` 가
   본문에 "판매"(제9조 제5항 "제3자에게 판매·양도·대여" 라는 **금지** 문언)와
   "소비자"("소비자가 기준 금액" 이라는 **가격 기준** 표현)가 각각 한 번씩
   나온 것만으로 True 를 돌려주었다. 두 단어 모두 이 계약의 거래구조와
   아무 관련이 없다.
2. 그렇게 주입된 위탁매매 질문 9개가 `max_questions`(5개)를 통째로 차지해,
   정작 이 계약에서 물어야 할 것(바터 등가성 산정 근거, 하도급법 적용 여부,
   출연자 동의 징구 주체 등)은 한 개도 나오지 못했다.

즉 질문 생성 전체가 "키워드가 보이면 미리 써둔 질문 묶음을 꺼낸다" 구조라,
AI 는 이미 만들어진 질문의 **문장만 다듬는**(`enhance.polish_questions`)
역할이었고 무엇을 물을지는 한 번도 판단하지 않았다.

이 모듈은 그 순서를 뒤집는다. 계약 전문을 AI 에게 그대로 읽히고,

  (a) 이 계약이 실제로 무슨 거래인지(거래구조·급부/반대급부·우리 지위),
  (b) 계약 문언만으로는 확정되지 않으면서 법률·세무·경제적 결론을 바꾸는
      사실이 무엇인지

를 먼저 판단하게 한 뒤, 그 판단에서 직접 질문을 만든다. 정적 질문 묶음은
이 판단이 허용한 주제(`applicable_topics`)에 한해서만 남는다.

AI 가 없거나(ai_mode=off, 키 미설정) 호출이 실패하면 이 모듈은 조용히
비어 있는 계획을 돌려주고, 호출자는 종전의 결정론적 경로를 그대로 탄다 —
다만 그 경로의 트리거는 `transaction_structure_signals` 쪽에서 함께
조인다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from runtime.ai.enhance import _build_request, _try_json
from runtime.ai.provider import AIProvider
from runtime.ai.safe import sanitize_error_message
from runtime.questions.model import Question, QuestionOption

logger = logging.getLogger(__name__)

#: 정적 질문 묶음이 다루는 주제. AI 가 이 계약에 해당한다고 판단한 것만
#: 남기고 나머지는 버린다. 값은 `Question.tags` 의 "topic:<...>" 와 맞춘다.
KNOWN_QUESTION_TOPICS: tuple[str, ...] = (
    "transaction_structure",     # 판매자·소유권·매출귀속 등 매매/위탁판매 구조
    "contract_type_confirmation",
    "party_role_confirmation",
    "user_focus",
    "ip_ownership",              # 저작권·산업재산권 귀속
    "personal_data",             # 개인정보·초상권
    "payment_settlement",        # 대금·정산·세금계산서
    "liability_indemnity",
    "termination",
    "subcontracting",            # 하도급법·재위탁
    "advertising_disclosure",    # 표시광고·협찬표시
)

_MAX_TEXT_CHARS = 24000
_QUESTION_ID_PREFIX = "Q-AI-"


@dataclass
class ContractQuestionPlan:
    """AI 가 계약을 읽고 세운 사전 질문 계획."""

    status: str = "skipped"          # "ai" | "skipped" | "error"
    deal_summary: str = ""
    contract_nature: str = ""
    our_side: str = ""
    counterparty: str = ""
    consideration_structure: str = ""
    applicable_topics: list[str] = field(default_factory=list)
    excluded_topics: list[str] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    error: str = ""

    @property
    def usable(self) -> bool:
        return self.status == "ai" and bool(self.questions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "deal_summary": self.deal_summary,
            "contract_nature": self.contract_nature,
            "our_side": self.our_side,
            "counterparty": self.counterparty,
            "consideration_structure": self.consideration_structure,
            "applicable_topics": list(self.applicable_topics),
            "excluded_topics": list(self.excluded_topics),
            "error": self.error,
            "question_ids": [q.question_id for q in self.questions],
        }


_SYSTEM = """당신은 한국 대기업의 사내변호사다. 계약서 초안을 받으면 검토를 시작하기 전에
"이 계약서만 읽어서는 알 수 없지만, 답에 따라 법률·세무·경제적 결론이 달라지는 사실"만
담당자에게 되묻는다.

절대 규칙:
1. 계약서를 처음부터 끝까지 읽고, 이 계약이 **실제로 어떤 거래인지** 먼저 확정한다.
   계약서 제목이 아니라 급부와 반대급부의 실질로 판단한다.
2. 계약서 본문에 이미 답이 적혀 있는 것은 절대 묻지 않는다.
3. 이 계약의 거래구조에 존재하지 않는 개념은 절대 묻지 않는다.
   (예: 매매·고객·재고가 없는 계약에서 "최종 판매자는 누구인가", "재고 소유권",
   "매출 귀속", "POS 결제 명의"를 묻는 것은 명백한 오류다.)
4. 질문은 답이 달라지면 검토 결론이 실제로 달라지는 것만 고른다.
   "참고로 알아두면 좋은" 질문은 만들지 않는다.
5. 각 질문에는 그 답이 어떤 법률·세무·경제 리스크 판단을 바꾸는지 반드시 적는다.

출력은 JSON 하나만. 설명·마크다운·코드펜스 금지."""

_USER_TEMPLATE = """[우리 회사] {entity}
[담당자가 입력한 계약 유형] {contract_type}
[담당자가 적은 검토 요청 사항]
{review_focus}

[계약서 전문]
{text}

위 계약서를 읽고 아래 JSON 스키마로만 답하라.

{{
  "deal_summary": "이 계약이 실제로 무슨 거래인지 한 문장 (급부와 반대급부를 명시)",
  "contract_nature": "거래의 법적 성질 (예: 대물교환(바터), 도급, 위임, 매매, 임대차, 라이선스 — 복합이면 복합이라고 적는다)",
  "our_side": "이 계약에서 우리 회사({entity} 측)가 누구이고 무엇을 제공/취득하는지",
  "counterparty": "상대방이 누구이고 무엇을 제공/취득하는지",
  "consideration_structure": "대가가 어떻게 오가는지 (금전 지급이 없으면 그 사실을 명시)",
  "applicable_topics": ["아래 주제 코드 중 이 계약에 실제로 존재하는 것만"],
  "excluded_topics": ["아래 주제 코드 중 이 계약에 존재하지 않아 물으면 안 되는 것"],
  "questions": [
    {{
      "title": "담당자에게 물을 질문 (한 문장, 물음표로 끝낸다)",
      "why": "이 답이 어떤 법률·세무·경제 리스크 판단을 바꾸는지",
      "risk_axis": "legal" | "tax" | "economic",
      "topic": "주제 코드 중 하나",
      "required": true | false,
      "options": ["선택지가 명확할 때만 2~5개, 아니면 빈 배열"]
    }}
  ]
}}

주제 코드: {topics}

질문은 최대 {max_questions}개. 중요도 순으로 정렬한다.
계약서만으로 이미 확정되는 사실은 질문에 넣지 마라."""


def _clip(text: str, limit: int = _MAX_TEXT_CHARS) -> str:
    s = str(text or "")
    if len(s) <= limit:
        return s
    # 앞부분(당사자·목적·대가 구조)과 뒷부분(해지·손해배상·특약)이 모두
    # 필요하므로 가운데를 자른다.
    head = s[: int(limit * 0.65)]
    tail = s[-int(limit * 0.3):]
    return f"{head}\n\n…(중략)…\n\n{tail}"


def _normalize_topic(value: Any) -> str:
    t = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return t if t in KNOWN_QUESTION_TOPICS else ""


def _to_question(raw: Any, index: int) -> Question | None:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    why = str(raw.get("why") or "").strip()
    axis = str(raw.get("risk_axis") or "").strip().lower()
    axis = axis if axis in ("legal", "tax", "economic") else "legal"
    topic = _normalize_topic(raw.get("topic")) or "user_focus"

    options: list[QuestionOption] = []
    raw_options = raw.get("options")
    if isinstance(raw_options, list):
        for opt in raw_options:
            label = str(opt or "").strip()
            if not label:
                continue
            options.append(QuestionOption(value=f"opt_{len(options) + 1}", label=label))
            if len(options) >= 5:
                break
    if len(options) < 2:
        options = []

    description = why or "이 답에 따라 검토 결론이 달라집니다."
    return Question(
        question_id=f"{_QUESTION_ID_PREFIX}{index:03d}-{topic}",
        title=title,
        description=description,
        answer_type="single_choice" if options else "text",
        required=bool(raw.get("required", True)),
        options=options,
        tags=[
            f"topic:{topic}",
            f"risk_axis:{axis}",
            "source:contract_question_agent",
            f"priority:{index}",
        ],
        related_rule_ids=[],
    )


def plan_questions(
    *,
    provider: AIProvider | None,
    model: str,
    entity: str,
    contract_type: str,
    contract_text: str,
    review_focus: str | None = None,
    max_questions: int = 5,
    timeout_sec: float = 90.0,
    max_tokens: int = 2000,
    temperature: float = 0.1,
) -> ContractQuestionPlan:
    """계약 전문을 AI 에게 읽히고 이 계약에 맞는 질문 계획을 세운다.

    AI 가 없거나 실패하면 `status != "ai"` 인 빈 계획을 돌려준다 — 호출자는
    그때만 종전의 결정론적 질문 생성 경로를 탄다.
    """
    text = str(contract_text or "").strip()
    if provider is None or not text:
        return ContractQuestionPlan(status="skipped")

    user = _USER_TEMPLATE.format(
        entity=str(entity or "").strip() or "(미상)",
        contract_type=str(contract_type or "").strip() or "(미상)",
        review_focus=str(review_focus or "").strip() or "(없음)",
        text=_clip(text),
        topics=", ".join(KNOWN_QUESTION_TOPICS),
        max_questions=int(max_questions),
    )
    try:
        resp = provider.complete(
            _build_request(
                model=model,
                system=_SYSTEM,
                user=user,
                timeout_sec=timeout_sec,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        )
    except Exception as exc:  # noqa: BLE001 - AI 실패는 검토를 막지 않는다
        logger.warning("contract_question_agent call failed: %s", sanitize_error_message(str(exc)))
        return ContractQuestionPlan(status="error", error=sanitize_error_message(str(exc)))

    data = _try_json(getattr(resp, "content", "") or "")
    if not isinstance(data, dict):
        return ContractQuestionPlan(status="error", error="AI 응답을 JSON으로 해석하지 못했습니다.")

    questions: list[Question] = []
    for i, raw in enumerate(data.get("questions") or [], start=1):
        q = _to_question(raw, i)
        if q is not None:
            questions.append(q)
        if len(questions) >= max_questions:
            break

    applicable = [t for t in (_normalize_topic(x) for x in (data.get("applicable_topics") or [])) if t]
    excluded = [t for t in (_normalize_topic(x) for x in (data.get("excluded_topics") or [])) if t]

    plan = ContractQuestionPlan(
        status="ai",
        deal_summary=str(data.get("deal_summary") or "").strip(),
        contract_nature=str(data.get("contract_nature") or "").strip(),
        our_side=str(data.get("our_side") or "").strip(),
        counterparty=str(data.get("counterparty") or "").strip(),
        consideration_structure=str(data.get("consideration_structure") or "").strip(),
        applicable_topics=applicable,
        excluded_topics=excluded,
        questions=questions,
    )
    if not questions:
        # 계약을 읽고도 물을 것이 없다고 판단한 경우와, 파싱이 실패한 경우를
        # 구분한다 — 전자는 정상이므로 정적 질문으로 되돌아가지 않는다.
        plan.status = "ai" if isinstance(data.get("questions"), list) else "error"
    return plan


def topic_of(question: Question) -> str:
    """`Question.tags` 에서 "topic:<code>" 를 뽑는다."""
    for tag in question.tags or []:
        s = str(tag or "")
        if s.startswith("topic:"):
            return _normalize_topic(s[len("topic:"):]) or s[len("topic:"):].strip()
    return ""


def filter_static_questions_by_plan(
    questions: list[Question],
    plan: ContractQuestionPlan,
) -> list[Question]:
    """AI 가 "이 계약에 없다"고 판단한 주제의 정적 질문을 제거한다.

    허용 목록(`applicable_topics`)만으로 걸러내지 않는다 — AI 가 주제 코드를
    빠뜨렸다고 해서 정상 질문까지 사라지면 안 되기 때문이다. 명시적으로
    배제된 주제(`excluded_topics`)만 제거한다.
    """
    if plan.status != "ai" or not plan.excluded_topics:
        return list(questions)
    excluded = set(plan.excluded_topics)
    return [q for q in questions if topic_of(q) not in excluded]
