# /api/questions/generate: AI 질문 문구 보강(선택)

## 목표
- 기본은 기존 rule 기반 질문 생성 유지
- `OPENAI_API_KEY`가 있으면 질문 표현(제목/설명)을 더 자연스럽게 다듬음
- 질문 구조(question_id/required/options)는 유지
- 결과는 UI에서 “한 번에 1개씩” 보여줄 수 있는 형태 유지

## 동작 방식
1) 기존 로직으로 질문 생성(rule 기반)
2) OpenAI가 활성화되어 있으면
   - 질문 의미를 바꾸지 않고 title/description만 다듬음
   - 실패 시 원본 질문 그대로 반환

## 구현 위치
- API 핸들러: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- AI 보강 로직: [enhance.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/enhance.py) (`polish_questions`)

## 응답 변화
- 응답에 `ai` 필드가 추가될 수 있음(성공/실패 메타만, 키/민감정보 없음)

