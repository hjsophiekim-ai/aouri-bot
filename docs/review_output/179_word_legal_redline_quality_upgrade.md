# 179) Word 법무 redline 품질 업그레이드

## 목표
- 삭제: 빨간 취소선
- 추가: 빨간색
- 변경 없는 텍스트: 원문 그대로
- 필수수정(HIGH)은 본문 redline, 권장/참고는 파란 guidance/부록
- 사용자가 “무엇을 고쳐야 하는지” 한눈에 보이도록 legend 제공

## 구현 요약
- Word 표지 영역에 legend 추가:
  - 필수수정(HIGH)=본문 redline
  - 권장수정(MEDIUM)=파란 guidance
  - 참고제안(LOW)=파란 guidance/부록(본문 미수정)
- 본문 redline은 기존 diff 기반 구조 유지(삭제 strike/추가 red)

관련 코드:
- legend 추가: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L321-L347)
- diff runs(삭제 strike/추가 red): [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L102-L136)

