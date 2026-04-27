# 185) 검토 지연 최적화(AI/Law 호출 감소 + 캐시)

## 목표

- 60초 이상 걸리는 경로를 줄이고, 사용자가 기다리는 시간을 체감상 “짧게” 만든다.
- 핵심은 “정말 필요한 조항”에만 AI/Law를 붙이고, 동일 입력은 캐시로 재사용한다.

## 적용된 최적화

### 1) clause-level 법령검색 호출 수 제한

- clause-level 법령검색 대상 조항을 최대 6개로 제한
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- clause-level 질의 개수 제한(최대 4개)
  - [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

### 2) AI 요청 비용/속도 균형 조정

- deep mode에서 `ai_max_tokens` 상한을 2800으로 낮춰 응답 지연과 형식 오류 가능성을 줄임
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

### 3) 캐시 적극 사용(동일 입력 재검토 최적화)

- 텍스트 기반 fast/deep 결과를 메모리 캐시(TTL)로 재사용
  - fast: 10분 TTL
  - deep: 15분 TTL
- 세션 기반은 answers+text 시그니처가 같으면 저장된 결과를 즉시 반환
  - deep: `review_result_sig`
  - fast: `review_result_fast_sig`
  - [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py)

### 4) UI 레벨 병렬화

- draft 추천은 review 결과와 무관하면 병렬 호출(사용자 대기 감소)
  - [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

