# 213. final_review_context 생성/주입(질문답변+사용자입력 통합)

## 목표
- 질문 답변 + 사용자 자유입력(review_focus)을 합쳐 최종 컨텍스트(`final_review_context`)를 생성하고, clause 결과/AI 프롬프트/리라이트 엔진에 일관되게 주입한다.
- 결과 보고서(Word) 및 화면에서 “질문 답변 반영 요약”을 별도 섹션으로 제공한다.

## 핵심 변경
### 1) FinalReviewContext 확장
- `user_focus_issues`: 사용자 직접 입력 기반 objective
- `review_objectives`: 사용자 입력 + 질문답변에서 유도된 objective(합집합)
- `factual_answers`: 질문 답변 원본(dict)
- `party_role`, `is_counterparty_form`
- `jurisdiction(domestic_korea/cross_border/foreign_entity_involved)`
- `contract_profile`
- 구현:
  - [final_review_context.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/final_review_context.py)
  - [user_focus.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/user_focus.py)

### 2) 질문 답변 → objective 재반영
- 답변 값(yes/텍스트 존재 등)으로 `dealer_cost_shift`, `settlement_offset`, `termination_abuse` 등 objective를 유도해 `review_objectives`로 합산:
  - [user_focus.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/user_focus.py)

### 3) clause 결과에 컨텍스트 영향 표시
- clause_results에 다음 필드 추가/강화:
  - `user_focus_hit/user_focus_match_titles`
  - `factual_hit/factual_match_titles`
- 정렬 우선순위에 factual_hit를 반영해 “답변으로 확정된 사실관계/리스크”가 일반 룰보다 앞서 나오도록 조정:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 4) AI 프롬프트 주입
- AI deep review payload에 `final_review_context`, `answers`, `party_role`, `clause_topic` 등을 포함해 문맥 기반 조항 검토가 가능하도록 유지/강화:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 5) 결과 보고서(Word) 반영
- Word 상단에 다음 섹션 추가:
  - “2-1) 사용자 요청 핵심 이슈 반영 결과”
  - “2-2) 질문 답변 반영 요약”
- 구현:
  - [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

## 기대 효과
- 사용자 입력/질문 답변이 AI/룰/표시/Word 출력까지 하나의 컨텍스트로 연결되어 “검토가 얕게 느껴지는 문제”를 완화한다.

