# 177) Context-aware 질문 엔진 고도화(3~7개 선별)

## 목표
- clause extraction/스크리닝 결과를 기준으로 “빠졌거나 애매한 조항”만 질문
- 계약서에 이미 명확히 있으면 되묻지 않기
- 질문 수를 3~7개 범위로 운영(기본 7 상한)
- 질문 우선순위는 계약유형/리스크/핵심쟁점 중심으로 강화
- AI는 질문 polish뿐 아니라 “우선순위 산정(prioritize)”에도 사용

## 구현 요약
- 질문 생성 상한을 7로 조정:
  - [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py#L91-L240)
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1388-L1433)
- clause_results의 risk tier를 반영해 “리스크가 높은 토픽” 질문 점수 가중:
  - `ip/oss/acceptance/sla/privacy/source…` 등 핵심 토픽별로 clause_results를 스캔해 HIGH/MEDIUM 힌트를 점수에 반영
  - [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py#L33-L70)
- AI 기반 질문 우선순위는 기존 `prioritize_questions()`를 그대로 사용(질문 선택 자체에 AI 활용):
  - [enhance.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/enhance.py#L130-L212)

## 동작 방식(요약)
- 1) 텍스트/조항을 스캔해 토픽 상태를 `missing/ambiguous/clear`로 분류
- 2) `missing/ambiguous` 토픽만 후보 질문으로 생성
- 3) clause_results에 HIGH/MEDIUM이 걸린 토픽이면 후보 점수 가중
- 4) (AI enabled 시) 후보 중 “진짜 필요한 질문”을 우선순위로 재정렬 후 3~7개로 축약

