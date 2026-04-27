# 188) /demo 대기 경험(Waiting UX) 검증

## 검증 범위

- 질문 종료 후 검토 시작 안내 문구 노출 여부
- 진행상태/ETA/경과시간 표시 여부
- fast(1차) 결과가 먼저 노출되는지
- 사용자가 무한 대기처럼 느끼지 않도록 화면이 갱신되는지
- deep 결과가 후속으로 자연스럽게 갱신되는지

## 확인 결과(코드/동작 기준)

### 1) 질문 종료 직후 “검토 시작” 안내 문구

- `finishAndAnalyze()` 시작 즉시 2개 메시지를 출력하도록 수정됨
  - “좋아요. 이제 검토를 시작해볼게요.”
  - “계약 길이와 조항 수에 따라 20~60초 정도 걸릴 수 있어요.”
- 구현: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

### 2) 진행상태/ETA/경과시간 표시

- stageChat에 진행 패널(`analyzePanel`) 추가
- fast 결과로 stageResult로 이동한 뒤에도 진행 패널(`resultAnalyzePanel`)이 유지되어 deep 로딩 중 상태가 보임
- 15초/30초/90초 지연 메시지 추가

### 3) fast 결과가 먼저 노출되는지(2단계 파이프라인)

- `/demo`는 먼저 fast 호출을 수행하고 즉시 stageResult를 열어 summary를 먼저 노출
  - 텍스트 입력: `POST /api/review/analyze_fast`
  - 세션(업로드): `POST /api/question_sessions/{id}/review_fast`
- 조항 카드 영역은 skeleton을 먼저 렌더링하고, deep 완료 후 실데이터로 갱신

### 4) deep 결과 후속 갱신

- deep 호출 완료 시 `reviewResult`/`revisionResult`를 업데이트하고 `buildResult()`를 다시 호출하여 clause cards / docx 상태를 갱신

## 성능(계측 결과 요약)

- 실제 계측 리포트: [187_review_latency_benchmark.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/187_review_latency_benchmark.md)
- 긴 계약서(app-dev) 기준, 개선 전(순차) 대비 “첫 결과(fast)”가 먼저 노출되어 체감 대기 시간이 감소함

## 남은 개선 포인트(관찰)

- deep 단계는 법령검색/AI 호출에 따라 변동폭이 크므로, 캐시 적중률 및 law/ai 모드 토글에 따른 체감 차이를 지속적으로 모니터링 필요

