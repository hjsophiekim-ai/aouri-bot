# 217. 변호사 스타일 문맥 기반 프롬프트 업그레이드(Structured output)

## 목표
- AI가 문장을 단순 보강하는 수준을 넘어, 계약 맥락을 입력으로 받아 조항별로 “최소 변경 + 조항 맞춤형 이유”를 출력하도록 한다.
- UI와 Word에 동일하게 적용 가능한 구조화 출력(JSON)만 생성한다.

## 입력 주입(필수 컨텍스트)
- 계약 유형(contract_type)
- 국내/해외 분류(jurisdiction.kind)
- 당사자 역할(party_role) 및 review_posture
- 사용자 중점 검토 이슈(user_focus_issues / review_objectives)
- 질문 답변(factual_answers, answers)
- clause topic, 관련 rule, 관련 법령/판례
- 원문 유지 원칙/추정 금지

## 구현
- AI system prompt에 다음 원칙을 명시:
  - user_focus_issues 우선
  - clause_topic 무관 문구 금지
  - domestic_korea일 때 해외 집행 reasoning 금지
  - 최소 변경/근거 없는 추정 금지
  - JSON 배열만 출력
- AI user payload에 final_review_context 및 조항별 입력을 포함:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

## 출력 구조(강제)
- AI 출력은 JSON 배열이며, 각 항목은 다음 키를 포함하도록 요구:
  - clause_id
  - rewrite_reason
  - suggested_rewrite
  - changed_segments({before, after} 최대 3개)
  - risk_tier / must_fix(입력값 유지)

## 후처리(품질 보정)
- 한국어 법무 문체 polish 적용:
  - [korean_polish.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/korean_polish.py)
- topic guardrail 및 국내/해외 reason 오염 방지:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

