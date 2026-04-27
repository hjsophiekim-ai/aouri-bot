# 158. Fix: `/api/review/analyze`에서 AI가 실제로 사용되지 않던 버그 수정

## 문제
- `/api/review/analyze`는 AI config를 로드하고 `ai_provider`를 생성하지만,
- 실제 clause-level 엔진 호출에서 `ai_provider=None`으로 넘겨 AI가 전혀 사용되지 않았다.
- 위치(수정 전 호출부): [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

## 수정 내용
- `/api/review/analyze`에서 `build_clause_level_result(...)` 호출 시 아래 파라미터를 revision 경로와 동일하게 전달하도록 수정했다.
  - `ai_provider`
  - `ai_model`
  - `ai_timeout_sec`
  - `ai_max_tokens`
  - `ai_temperature`
- AI 비활성(OPENAI_API_KEY 미설정 등)인 경우에만 `ai_provider=None`으로 fallback 한다.
- 응답의 `ai.enabled`가 실제 설정(OPENAI 활성)과 일치하도록 정리하고, `ai.used`로 clause-level 내부 사용(시도) 여부를 분리했다.

## 변경 파일
- [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

## 동작 기준(정합성)
- `/api/ai/health`
  - `enabled=false`이면: `/api/review/analyze`도 `ai.enabled=false`로 응답해야 함
- `/api/review/analyze`
  - `ai.enabled=true`이고 clause-level이 실제로 AI rewrite를 시도하면 `ai.used=true`(meta.ai 존재)로 표시
  - clause_results가 없거나 AI 적용 대상이 없으면 `ai.enabled=true`라도 `ai.used=false`가 될 수 있음(설정은 켜져 있으나 실행할 항목이 없음)
- `/api/revision/suggest_text`
  - 이미 `build_clause_level_result`에 ai 파라미터를 전달하고 있어, `/api/review/analyze`와 동일한 기준으로 정렬됨

## 추가 검증(로컬)
- `/api/ai/health` → enabled 확인
- `/api/review/analyze` → `ai.enabled/ai.used` 확인
- `/api/revision/suggest_text` → `meta.ai` 확인

