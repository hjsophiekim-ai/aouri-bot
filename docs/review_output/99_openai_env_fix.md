# OpenAI 환경변수(.env) 점검/교정(99)

## 결론
- 현재 프로젝트 루트의 `.env`에는 `OPENAI_API_KEY` 항목이 존재하지 않는다(키 값 미출력).
- 따라서 런타임에서 `load_ai_config()`는 provider를 `mock`으로 선택하고, `/api/ai/health`도 `enabled=false`로 나온다.
- 추가로, 기존 구현은 “환경변수가 존재하지만 빈 문자열”인 경우 `.env` 로딩을 건너뛰는 문제가 있을 수 있어, 빈 값도 “미설정”으로 취급해 `.env`를 로딩하도록 수정했다.

## 1) .env 로딩 경로 점검(프로젝트 루트 기준)
- OpenAI 로더가 시도하는 경로(루트 기준)
  - `.env`
  - `.env.local`
  - `docs/.env`
  - `docs/.env.local`
- 구현: [load_ai_config()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/ai/config.py#L41-L55)

## 2) 왜 OPENAI_API_KEY를 못 읽는가(정확 원인)
- `.env` 파일은 존재하지만, `OPENAI_API_KEY=...` 라인이 없음  
  - 존재 여부 재검증 결과: [102_env_runtime_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/102_env_runtime_validation_rerun.md)

## 3) 적용한 수정
- `.env` 로딩 트리거 조건 개선
  - 변경 전: `OPENAI_API_KEY`가 환경변수 “키로 존재”하면(값이 비어 있어도) `.env` 로딩을 건너뛸 수 있음
  - 변경 후: `OPENAI_API_KEY`가 없거나/비어 있으면 `.env` 로딩 수행
- 변경 코드: [load_ai_config()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/ai/config.py#L41-L55)

## 4) OpenAI 실제 provider 활성화를 위한 남은 작업
- 사용자가 `.env`에 `OPENAI_API_KEY`를 추가해야 한다(키 값은 저장소에 커밋하지 않도록 주의).
- 성공 기준: `/api/ai/health`에서 `enabled=true`, `provider=openai`로 표시됨.
