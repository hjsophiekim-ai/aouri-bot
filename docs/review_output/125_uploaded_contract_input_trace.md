# 125. 업로드 계약서 입력 추적(Uploaded Contract Input Trace)

## 목표
- /demo에서 업로드한 파일의 **원문 텍스트 추출 결과**가 존재하는지 확인
- review/analyze에 전달되는 **실제 입력(payload)** 이 “요약문”이 아니라 **첨부 파일 본문**인지 확인
- 질문 답변(answers)이 원문을 덮어쓰지 않는지 확인

## 1) 업로드 후 텍스트 추출 결과 확인
### 업로드 처리 흐름
- `POST /api/upload`
  - 파일 저장(임시) → 텍스트 추출: [text_extract.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py)
  - 세션 생성(추출 텍스트를 `session.text`에 저장): [server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py), [storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py)

### 추출 텍스트 샘플(테스트 fixture 기반)
아래는 `runtime/tests/fixtures/demo_upload.txt` 업로드 시 서버가 반환하는 `extraction.preview`(앞부분 200자) 예시입니다.

```
제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.
제11조(면책) 상대방은 어떠한 경우에도 책임을 부담하지 아니한다.
제12조(기술자료) 당사는 상대방 요청 시 기술자료/원가자료/도면/소스코드를 제출한다.
제13조(해지) 상대방은 사전 통지 없이 즉시 해지할 수 있다.
```

또한 업로드 응답에는 다음이 포함됩니다.
- `extraction.text_length`: 추출 텍스트 길이
- `extraction.text_sha256`: 추출 텍스트 해시(본문이 실제로 존재함을 검증 용도)

## 2) review analyze에 전달되는 실제 payload 확인
### 기존 /demo(채팅형) 문제
- 업로드를 했더라도 `/api/review/analyze`를 직접 호출하면서 `text=''`로 보내는 로직이 있었습니다.
- 위치: [internal_demo_chat_ui.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

### 개선 후 동작(업로드 기반은 세션 기반으로 통일)
- `/demo` 업로드 경로는 이제 아래 순서로 실행됩니다.
  1) `POST /api/upload` → `question_session_id` 획득(여기서 추출 텍스트는 `session.text`로 저장됨)
  2) `POST /api/question_sessions/{id}/answers` (질문 답변 저장)
  3) `POST /api/question_sessions/{id}/review` (세션의 text로 분석 실행)
  4) `POST /api/revision/suggest` with `{ "session_id": "..." }` (조항별 수정안 생성)

즉, **payload에서 text를 따로 보내지 않아도** 서버가 세션에 저장된 “업로드 추출 텍스트”를 사용합니다.

## 3) payload가 요약문이 아니라 첨부 본문인지 확인
- 업로드 기반일 때는 `session.text`가 “계약서 본문”의 단일 소스입니다.
- `/api/question_sessions/{id}/review`에서 실제 분석 입력은 `session.text`를 사용합니다.
- 위치: [storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py) `run_review_with_session()`

## 4) 질문 답변이 원문을 덮어쓰는지 확인
- answers 저장은 `session.answers`만 업데이트하며, `session.text`를 수정하지 않습니다.
- 위치: [storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py) `save_answers()`

## 현재 shallow review의 직접 원인(요약)
- /demo(채팅형) 업로드 경로에서 `text=''`로 분석 호출 → “첨부 본문이 분석에 들어가지 않는” 현상이 발생
- 세션 리뷰 경로(`/api/question_sessions/{id}/review`)가 기존에는 조항별 결과를 포함하지 않아 “구체성”이 UI에 충분히 노출되지 않음
