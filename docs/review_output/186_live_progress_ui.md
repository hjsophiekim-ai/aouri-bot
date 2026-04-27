# 186) /demo Live Progress UI(로딩 중 화면 “살아있게”)

## 목표(요구사항 반영)

- 로딩 스피너/점 애니메이션
- 단계 텍스트 갱신(계약서 읽는 중 → 규칙 검토 → 법령/판례 → AI → 결과 정리)
- elapsed time 표시
- ETA(rough estimate) 표시
- cancel/재시도(오류/지연 시 안내 포함)
- 90초 초과 시 “지연 중” 안내

## 구현

- 진행 패널을 stageChat + stageResult에 동시에 노출
  - 질문 종료 후: stageChat에서 진행 패널 표시
  - fast 결과 노출 이후: stageResult에서 동일 진행 패널이 유지되어 deep 로딩 중에도 상태가 보임
- 15초/30초/90초 지연 메시지를 챗봇 메시지로 추가 노출
- 취소 시 AbortController로 deep fetch를 중단하고 재시도 버튼을 노출

## 구현 위치

- UI: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
  - `startAnalyzeProgress()` / `setAnalyzeStage()` / `updateAnalyzeHeader()`
  - `cancelAnalyze()` / `retryAnalyze()`
  - `finishAndAnalyze()`의 fast/deep 2단계 로딩

