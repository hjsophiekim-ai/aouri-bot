# /demo 결과 화면 CTA 정리

## 목표
- 버튼 수 최소화(업무용 EP 화면에 맞게)
- primary/secondary 구분 명확화

## 최종 버튼 구성(4개)
- 수정 제안 확정
- 초안 작성 확정
- 다시 질문 보기
- 처음으로 돌아가기

## 스타일 정책
- 대표 추천 액션에 해당하는 버튼만 primary(블루)로 표시
- 나머지 액션은 secondary(화이트/라이트 블루 테두리)
- 초안 추천 템플릿이 없으면 “초안 작성 확정”은 disabled 처리

## 관련 코드
- [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
  - `buildResult()`에서 추천 액션에 따라 버튼 class/disabled 처리

