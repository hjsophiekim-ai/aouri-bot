# /demo 시작 화면: 최소 입력 중심(EP용)

## 목표
- 첫 화면을 ChatGPT처럼 단순하게
- 사용자가 “지금 무엇을 해야 하는지” 바로 이해 가능
- 필수 요소만 남기고, 기술 설명/버튼을 최소화

## 반드시 남긴 요소
- 아우리봇 이미지(`docs/아우리봇.png` → `/static/aouribot.png`)
- 제목: “무슨 계약을 검토하고 싶으세요?”
- 입력:
  - 법인
  - 계약유형
  - 계약서 첨부
  - 계약 내용 입력
- CTA: “검토 시작”

## 제거/축소한 요소
- 초기에 보이는 복잡한 카드/세부 설명(최소화)
- “샘플 넣기” 등 보조 버튼 제거
- 내부 기술 정보성 텍스트 제거(업로드 포맷 안내 문구 등)

## 관련 코드
- UI: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
  - `stageStart` 영역 간소화

