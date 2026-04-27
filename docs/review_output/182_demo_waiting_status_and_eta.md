# 182) /demo 대기 안내 + 진행상태/ETA 표시

## 문제

- `/demo` 대화형 화면에서 질문 종료 후 검토를 시작할 때, 사용자가 “멈춘 것처럼” 느끼는 구간이 존재했다.
- `finishAndAnalyze()`가 안내 문구 1줄만 출력하고, 이후 API 호출이 끝날 때까지 화면에 진행 단계/예상 시간/경과 시간/재시도 안내가 없었다.

## 변경 요약

- 질문 종료 직후 챗봇 메시지 2줄을 즉시 출력
  - “좋아요. 이제 검토를 시작해볼게요.”
  - “계약 길이와 조항 수에 따라 20~60초 정도 걸릴 수 있어요.”
- 진행 상태 패널을 추가하고, 아래를 표시
  - 단계(5단계) + 1/5 형태 진행률
  - 경과 시간(elapsed)
  - 대략적 남은 시간(ETA)
  - 15초/30초/90초 지연 메시지
  - 취소/재시도 버튼 및 오류 시 안내

## 단계 정의(예시)

1. 업로드/텍스트 정리
2. 규칙 분석
3. 법령/판례 확인
4. AI 정밀 검토
5. 수정 제안 정리

## 구현 위치

- UI: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
  - `analyzePanel`(stageChat) / `resultAnalyzePanel`(stageResult) 추가
  - `startAnalyzeProgress()`, `setAnalyzeStage()`, `updateAnalyzeHeader()` 등 진행 UI 로직 추가
  - 15/30/90초 지연 메시지 출력
  - 오류 시 재시도 버튼 노출 및 안내 문구 처리

## 사용자 체감 개선 포인트

- “검토를 시작했다”는 신호가 즉시 표시되어, 무한 대기처럼 보이던 구간이 제거된다.
- deep 결과가 늦어도, 경과/ETA/단계가 계속 갱신되어 화면이 “살아있게” 유지된다.

