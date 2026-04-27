# 183) /demo 2단계(빠른 1차 + 정밀 2차) 로딩 파이프라인

## 목표

- 사용자가 “최종 결과가 다 끝날 때까지” 기다리지 않게, 결과 표시를 2단계로 분리한다.
- 1차 결과는 5~10초 내(목표)로 노출한다.
- 2차 결과(정밀 revision/law grounding/docx 준비)는 비동기 후속 로딩으로 갱신한다.
- draft 추천은 review 결과와 무관하면 병렬 호출한다.

## 변경 요약

- `/demo` `finishAndAnalyze()`를 “fast → deep 후속 로딩” 구조로 변경
  - fast 결과 수신 후 즉시 결과 화면(stageResult)을 보여주고 skeleton UI를 노출
  - deep 결과는 백그라운드 fetch로 받아서 clause cards / docx 상태를 후속 갱신
  - draft 추천은 `Promise`로 병렬 호출하여, 가능한 빨리 추천 템플릿 반영

## 사용자 흐름(UX)

1. 질문 종료 직후 “검토 시작” 및 소요 시간(20~60초) 안내 + 진행 패널 표시
2. fast 결과 도착 → 결과 화면에 summary/핵심 지표 우선 노출
3. “먼저 핵심 결과를 보여드리고, 조항별 수정안은 이어서 정리할게요.” 문구 표시
4. deep 결과 도착 → 조항별 수정안/법령 grounding/Docx 버튼 상태 자동 갱신

## 서버/엔드포인트

- fast
  - `/api/review/analyze_fast` (텍스트 기반)
  - `/api/question_sessions/{id}/review_fast` (세션 기반)
- deep
  - `/api/review/analyze_deep` (텍스트 기반)
  - `/api/question_sessions/{id}/review` (세션 기반; 기존 deep 유지)

## 구현 위치

- UI: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
  - `finishAndAnalyze()`에서 fast 호출 후 즉시 stageResult 노출
  - deep 호출은 비동기 후속 로딩으로 처리
  - draft 추천 호출 병렬화
- 서버: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
  - `/api/review/analyze_fast`, `/api/review/analyze_deep` 라우팅 추가
  - 세션 review_fast 엔드포인트 추가

