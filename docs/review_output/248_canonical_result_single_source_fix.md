# 248. UI/Word canonical result single source fix

## 목표
- /api/review/analyze(텍스트 입력)에서 생성한 결과를 세션에 저장하고, UI/Word가 동일 session_id의 canonical 결과를 사용한다.
- DOCX 다운로드는 기본적으로 “재계산 없이” 세션의 review_result를 그대로 사용한다.
- 재생성은 rebuild=true일 때만 허용한다.

## 변경(코드)
- /api/questions/generate가 텍스트 입력에도 session_id를 발급:
  - [server.py:_handle_questions_generate](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1574-L1709)
  - [storage.py:create_text_session](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py#L147-L204)
- internal demo UI(텍스트 입력 플로우)도 session_id를 유지:
  - [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py#L672-L686)
- /api/review/analyze(deep/fast) 결과를 session_id에 저장:
  - [server.py:_handle_review_analyze_api](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L681-L816)
- /api/revision/download_docx는 기본적으로 세션 canonical 결과가 없으면 실패(rebuild=true 예외):
  - [server.py:_handle_revision_download_docx](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1273-L1286)

