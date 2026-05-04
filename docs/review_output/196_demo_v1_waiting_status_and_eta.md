# 196) /demo-v1(legacy) 진행상태/ETA 표시

## 문제

- `/demo-v1` 화면에서는 검토 실행 시 안내 문구/ETA/경과시간이 없어 “멈춘 것처럼” 보일 수 있다.
- `/demo`(대화형)에는 진행 패널과 fast→deep 로딩을 적용했으나, `/demo-v1`에도 동일한 체감 개선이 필요하다.

## 적용

- 결과 패널 상단에 진행 표시 영역 추가
  - 진행 단계 텍스트
  - 경과시간(elapsed)
  - 대략적 남은 시간(ETA)
- 분석 호출을 fast→deep 2단계로 분리
  - `POST /api/review/analyze_fast`로 1차 결과를 먼저 표시
  - `POST /api/review/analyze_deep`를 백그라운드로 호출하여 정밀 결과로 갱신

## 구현 위치

- UI: [internal_demo_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_ui.py)

