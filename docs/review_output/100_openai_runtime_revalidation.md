# OpenAI 런타임 재검증(100)

## 확인 엔드포인트
- `/api/ai/health`

## 결과(키 값 미출력)
- 현재 상태: `enabled=false`, `provider=mock`
- 근거: [103_openai_health_runtime_check_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/103_openai_health_runtime_check_rerun.md)

## 실패(비활성) 원인
- `OPENAI_API_KEY`가 런타임에 설정되지 않음
  - `.env` 파일은 존재하나 `OPENAI_API_KEY` 항목이 없음(값 미출력): [99_openai_env_fix.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/99_openai_env_fix.md)

## 기대 동작(키 설정 후)
- `.env`에 `OPENAI_API_KEY`가 설정되면
  - `/api/ai/health` → `enabled=true`, `provider=openai`, `model` 표시
  - `/api/revision/suggest_text`, `/api/questions/generate`, `/api/draft/generate`에서 AI 보강이 활성화됨
