# 240. Word 결과물에 조항별 구체 수정문안(제안 문안) 강제 포함

## 문제
- 앱 화면에는 조항별 “참고 문안/수정 제안”이 보이는데, Word(DOCX)에는 방향/사유 위주로만 나오거나 본문 redline이 비는 경우가 발생

## 목표
- Word 결과물에 조항별 구체 수정문안(제안 문안)을 반드시 포함
- guidance only가 아니라 아래 구조로 출력
  - 원문 핵심 표현
  - 제안 문안(구체 문장)
  - 수정 이유
  - 관련 법령/기준
- HIGH뿐 아니라 MEDIUM 조항도 “제안 문안”을 Word에 반드시 표시
- 본문 redline이 없어도 “조항별 구체적 수정안 부록”은 항상 생성
- Word에서 사유만 있고 문구(제안 문안)가 없으면 생성 실패 처리

## 적용 변경(코드)
- DOCX는 조항별로 guidance(8)와 부록(9)에 “원문 핵심/제안 문안/사유/법령” 구조를 출력
  - [docx_writer.py:guidance 섹션](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L662-L702)
  - [docx_writer.py:부록 표(원문 핵심/제안 문안/사유/법령)](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L704-L772)
- HIGH/MEDIUM 조항에서 `suggested_rewrite`가 비어 있으면 DOCX 생성 실패 처리(검증)
  - [docx_writer.py:missing suggested_rewrite validation](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L373-L382)
- show 대상 조항이 없더라도 부록이 비어 보이지 않도록 placeholder 행 추가
  - [docx_writer.py:appendix placeholder](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L724-L742)

