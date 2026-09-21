"""광고매체 집행형 계약의 사전질문 — 거래구조와 직접 관련된 것만 묻는다.

2026-09-15 지시 —
  "광고매체 집행형에서는 2차 활용 계획·매체 재사용·2차적저작물작성권·
   저작인격권 불행사를 **기본적으로 묻지 말 것.** 상대방이 콘텐츠를 제작하거나
   그 권리를 제공하는 구조가 실제로 있을 때만 물을 것."

실측(타운보드 광고 계약): 사용자가 "엘레베이터 내 미디어 광고 집행을 위탁" 이라고
적었는데도 `Q-EFF-ip-scope`("취득하는 지식재산을 어디까지 활용할 계획인가요?
매체·기간·지역·재가공 포함 여부")가 나갔다. 상대방은 아무것도 만들지 않으므로
취득하는 지식재산이 없다. 담당자는 계약과 무관한 질문에 답을 지어내야 했다.

대신 무엇을 묻는가
────────────────
지시가 명시한 11개 — 광고기간·매체 위치·수량, 송출 기준, 미송출 시 처리,
광고료, 중도해지, 매체사 사정, 심의, 제공 콘텐츠의 IP 책임 범위, 임의 수정,
민원, 실적 보고. 전부 "상대방이 송출만 한다" 는 전제에서 실제로 다투게 되는 것들이다.
"""
from __future__ import annotations

import re

from runtime.questions.model import Question

#: 이 질문군의 접두어. `question_scope` 의 범위 게이트와 충돌하지 않도록
#: 별도 접두어를 쓴다.
AD_MEDIA_PREFIX = "Q-ADM-"


def _q(qid: str, title: str, description: str) -> Question:
    return Question(
        question_id=qid,
        title=title,
        description=description,
        answer_type="text",
        required=False,
        options=[],
        tags=["ad_media_placement"],
        related_rule_ids=[],
    )


#: 지시가 열거한 우선 확인 항목. 순서가 곧 중요도다.
#: 지시가 열거한 우선순위 그대로의 질문 순서.
#:
#: [2026-09-16 지시 2항] 열거 순서 — 광고기간·위치·수량·노출 → 미송출·부분
#: 송출·장애 구제 → 실제 송출실적 증빙 → 중도해지·위약금 → 매체사 일방 중단·
#: 변경권 → 민원 → 제공 콘텐츠의 법적 책임 → 상대방의 임의 수정·편집 책임 →
#: 광고료·지급조건 → 면책·손해배상.
#:
#: id 는 v11 에서 매긴 번호를 그대로 둔다. 번호를 다시 매기면 이미 답변이
#: 저장된 세션의 답이 엉뚱한 질문에 붙는다. 순서는 이 표가 정한다.
QUESTION_PRIORITY: tuple[str, ...] = (
    "Q-ADM-001",  # 광고기간·매체 위치·수량
    "Q-ADM-002",  # 송출 횟수·시간·노출 기준
    "Q-ADM-003",  # 미송출·장애 시 연장/환불
    "Q-ADM-011",  # 실제 송출실적 증빙
    "Q-ADM-005",  # 중도해지·위약금
    "Q-ADM-006",  # 매체사 일방 중단·변경
    "Q-ADM-010",  # 민원 시 중단·교체·비용
    "Q-ADM-008",  # 우리가 제공한 콘텐츠의 법적 책임 범위
    "Q-ADM-009",  # 상대방의 임의 수정·편집·송출 책임
    "Q-ADM-004",  # 광고료·지급조건
    "Q-ADM-007",  # 심의·법령 위반 책임
)

MEDIA_PLACEMENT_QUESTIONS: tuple[Question, ...] = (
    _q(
        "Q-ADM-001",
        "광고기간, 매체 위치와 수량이 계약서(또는 별첨)에 확정되어 있나요?",
        "집행형 계약의 급부는 '어디에, 몇 대에, 얼마 동안' 이 전부입니다. "
        "이것이 비어 있으면 무엇을 받기로 했는지 특정되지 않아 미이행을 다툴 수 없습니다.",
    ),
    _q(
        "Q-ADM-002",
        "송출 횟수·시간대·1회 노출 길이 등 노출 기준이 정해져 있나요?",
        "같은 기간·같은 매체라도 노출 기준이 없으면 실제 집행량이 절반이어도 "
        "계약 위반을 주장하기 어렵습니다.",
    ),
    _q(
        "Q-ADM-003",
        "미송출·장애가 발생하면 기간 연장인가요, 환불인가요? 기준이 정해져 있나요?",
        "집행형에서 가장 자주 발생하는 분쟁입니다. 연장·환불 중 무엇인지와 "
        "산정 방법이 없으면 사실상 구제수단이 없습니다.",
    ),
    _q(
        "Q-ADM-004",
        "광고료 총액과 지급조건(청구 시기, 지급 기한, 분납 여부)은 어떻게 되나요?",
        "지급 지연 시 상대방이 즉시 송출을 중단할 수 있는 구조인지와 함께 봅니다.",
    ),
    _q(
        "Q-ADM-005",
        "중도해지가 가능한가요? 위약금이나 할인 반환 조건이 있나요?",
        "프로모션·패키지 할인 계약은 중도해지 시 표준가로 재산정해 차액을 "
        "청구하는 조항이 흔합니다. 실질 위약금이므로 규모를 먼저 확인해야 합니다.",
    ),
    _q(
        "Q-ADM-006",
        "매체사 사정(매체 철거·시스템 교체·임대차 종료 등)으로 송출이 불가능해지면 어떻게 처리하나요?",
        "우리 귀책이 아닌 중단인데 광고료를 그대로 부담하게 되는 구조인지 확인합니다.",
    ),
    _q(
        "Q-ADM-007",
        "광고 심의나 법령 위반(표시광고법 등) 책임은 누가 지나요?",
        "송출 매체가 심의 기준을 갖고 있는 경우, 심의 불통과로 인한 미집행의 "
        "책임 귀속이 달라집니다.",
    ),
    _q(
        "Q-ADM-008",
        "우리가 제공한 광고물의 지식재산권 침해 책임 범위는 어디까지인가요? "
        "매체사 귀책을 제외하는 문구가 있나요?",
        "집행형의 진짜 IP 논점은 '권리를 취득하는가' 가 아니라 '우리가 준 소재 "
        "때문에 생긴 문제를 우리가 어디까지 책임지는가' 입니다.",
    ),
    _q(
        "Q-ADM-009",
        "매체사가 광고물을 임의로 수정·편집하거나 다른 방식으로 송출할 수 있나요? "
        "그로 인한 문제의 책임은 누구에게 있나요?",
        "매체사가 크기·비율·재생 방식을 바꾼 결과 발생한 문제까지 광고주가 "
        "면책해야 하는 구조라면 carve-out 이 필요합니다.",
    ),
    _q(
        "Q-ADM-010",
        "민원이 발생하면 광고 교체·중단 절차가 어떻게 되나요? 그 비용은 누가 부담하나요?",
        "즉시 새 시안을 제작해 전달할 의무만 있고 기간 보전이 없으면, 민원 한 건에 "
        "집행 기간과 제작비를 모두 잃습니다.",
    ),
    _q(
        "Q-ADM-011",
        "송출 실적·광고 성과 보고를 받기로 되어 있나요? 어떤 형식으로 언제 받나요?",
        "실적 보고가 없으면 집행 여부를 우리가 검증할 방법이 없습니다.",
    ),
)


#: 상대방이 콘텐츠를 제작할 때만 성립하는 질문. 집행형에서는 묻지 않는다.
#:
#: 질문 id 로만 거르면 새 질문이 생길 때마다 표를 고쳐야 하므로, **질문 문구**
#: 로도 거른다 — 이 논점들은 표현이 정해져 있다.
_RX_PRODUCTION_ONLY_QUESTION = re.compile(
    r"2차\s*활용|2차적저작물|저작인격권|재가공|chain\s*of\s*title"
    r"|저작(?:재산)?권[^?\n]{0,20}(?:양도|이전|확보|귀속)"
    r"|창작자[^?\n]{0,20}(?:권리|확약|동의)"
    r"|취득하는\s*지식재산"
    r"|결과물[^?\n]{0,20}(?:권리|활용|저작권)"
    # [2026-09-16 지시 2항] "저작물을 어느 매체·기간·지역에서 쓸지" — 우리가
    # 만들지도, 넘겨받지도 않는 저작물의 이용범위를 묻는 질문이다. 집행형에서
    # 매체·기간은 **급부의 특정**(어디에 얼마나 싣는가)이지 저작물 이용범위가
    # 아니므로, 저작물 어휘와 함께 나올 때만 거른다.
    r"|(?:저작물|콘텐츠|산출물|제작물)[^?\n]{0,30}(?:매체|기간|지역)[^?\n]{0,15}"
    r"(?:범위|활용|사용|이용)"
    r"|(?:이용|활용|사용)\s*범위[^?\n]{0,15}\(?\s*매체[^?\n]{0,10}기간[^?\n]{0,10}지역"
    # 상대방이 소재를 조달해 만들 때만 성립하는 확인 항목.
    r"|(?:제3자|타인)\s*(?:소재|저작물)[^?\n]{0,25}(?:라이선스|이용허락|권리처리)"
    r"|(?:폰트|음원|스톡\s*이미지)[^?\n]{0,20}(?:라이선스|이용허락)"
    r"|초상권[^?\n]{0,20}(?:이용허락|동의서)"
    r"|시안[^?\n]{0,10}(?:검수|확정|승인)|수정\s*요청\s*횟수",
    re.IGNORECASE,
)

#: id 로도 명시적으로 막아 두는 질문(문구가 바뀌어도 성격은 그대로다).
PRODUCTION_ONLY_QUESTION_IDS: frozenset[str] = frozenset({
    "Q-EFF-ip-scope",
})


def is_production_only_question(question: Question) -> bool:
    """상대방이 콘텐츠를 만들 때만 성립하는 질문인가."""
    if question.question_id in PRODUCTION_ONLY_QUESTION_IDS:
        return True
    blob = f"{question.title}\n{question.description}"
    return bool(_RX_PRODUCTION_ONLY_QUESTION.search(blob))


def apply_ad_media_question_policy(
    questions: list[Question],
    model,  # AdTransactionModel — 순환 import 를 피하려 타입을 느슨하게 둔다
    *,
    max_questions: int = 7,
) -> dict:
    """집행형이면 제작계약용 질문을 빼고 매체 집행 질문으로 채운다.

    **확신할 때만** 바꾼다(`model.confident`). 사용자 설명과 계약 원문이
    엇갈리면 아무것도 지우지 않는다 — 모르는 상태에서 질문을 지우는 것은
    엉뚱한 질문을 하는 것과 같은 실패다.

    돌려주는 dict: {"questions", "suppressed", "added", "applied"}.
    """
    report = {
        "questions": list(questions),
        "suppressed": [],
        "added": [],
        "applied": False,
    }
    if model is None or not getattr(model, "is_media_placement", False):
        return report
    if not getattr(model, "confident", False):
        return report

    survivors: list[Question] = []
    for q in questions:
        if is_production_only_question(q):
            report["suppressed"].append({"question_id": q.question_id, "title": q.title[:80]})
            continue
        survivors.append(q)

    # 순서가 곧 무엇을 묻게 되는가다 — 질문 수에는 상한(`max_questions`)이
    # 있으므로 뒤로 밀린 질문은 **나가지 않는다**.
    #
    # [2026-09-16 지시 2항] "대신 다음을 우선 질문·검토하세요" — 광고기간·
    # 위치·수량·노출, 미송출 구제, 실적 증빙, 중도해지·위약금, 매체사 일방
    # 중단권, 민원, 제공 콘텐츠 책임, 임의 수정 책임, 광고료·지급조건.
    #
    # 종전에는 일반 질문(대가 산정 근거·최대 손해 규모 등)을 먼저 채운 뒤
    # 남는 자리에만 집행형 질문을 넣었다. 실측: 11개 중 4개만 나가고 실적
    # 증빙·중도해지·일방 중단·민원·제공 콘텐츠 책임이 전부 잘렸다 —
    # 지시가 우선하라고 한 항목들이다.
    #
    # 담당자가 **직접 적은 검토 요청**(Q-FOCUS-…)은 그보다도 앞이다. 우리가
    # 고른 질문이 사용자가 물어본 것을 밀어낼 수는 없다.
    def _is_user_focus(q: Question) -> bool:
        return q.question_id.startswith("Q-FOCUS-")

    by_id = {q.question_id: q for q in MEDIA_PLACEMENT_QUESTIONS}
    prioritized = [by_id[qid] for qid in QUESTION_PRIORITY if qid in by_id]
    prioritized += [q for q in MEDIA_PLACEMENT_QUESTIONS if q.question_id not in QUESTION_PRIORITY]

    ordered: list[Question] = [q for q in survivors if _is_user_focus(q)]
    seen = {q.question_id for q in ordered}
    for q in prioritized:
        if q.question_id in seen:
            continue
        ordered.append(q)
        seen.add(q.question_id)
        report["added"].append(q.question_id)
    for q in survivors:
        if q.question_id in seen:
            continue
        ordered.append(q)
        seen.add(q.question_id)

    # 지시 2항은 열 가지를 **전부** 물으라고 했다. 일반 상한(7)을 그대로
    # 적용하면 실적 증빙·민원·제공 콘텐츠 책임·임의 수정 책임이 잘린다 —
    # 실측: 11개 중 4개만 나갔다. 이 거래구조에서는 이 질문들의 답이 곧
    # 검토의 입력이므로 집행형 질문에 한해 상한을 그만큼 넓힌다. 일반
    # 질문은 여전히 `max_questions` 뒤로 밀려 잘린다.
    _must_ask = sum(
        1 for q in ordered
        if _is_user_focus(q) or q.question_id.startswith(AD_MEDIA_PREFIX)
    )
    limit = max(int(max_questions), _must_ask)
    kept = ordered[:limit]
    _kept_ids = {q.question_id for q in kept}
    report["added"] = [qid for qid in report["added"] if qid in _kept_ids]
    report["dropped_for_limit"] = [
        q.question_id for q in ordered[max_questions:]
    ]
    report["questions"] = kept
    report["applied"] = True
    return report
