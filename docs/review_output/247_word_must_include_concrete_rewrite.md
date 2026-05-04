# 247. Word(DOCX)에 구체 수정문구 필수 포함(중요/중간 포함)

## 목표
- MEDIUM 조항도 “조항 위치/원문/제안 문안/수정 이유/법령” 구조로 Word 부록에 반드시 포함한다.
- suggested_rewrite(또는 reference_rewrite)가 없으면 문서 생성 실패로 처리한다.
- “사유만 있고 문구 없음” 상태는 validation 실패로 처리한다.
- 본문 redline이 없더라도 “조항별 구체적 수정안 부록”은 항상 생성한다.

## 변경(코드)
- HIGH/MEDIUM 제안 문안 누락 시 실패 처리: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L373-L382)
- 부록 표(원문 핵심/제안 문안/사유/법령) + placeholder: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L704-L772)
- UI-visible 조항이 Word에서 누락되면 다운로드 실패(서버 검증): [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1337-L1420)

