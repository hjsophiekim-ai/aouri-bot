# OpenAI 연동 검증 체크리스트(키 노출 금지)

## 주의
- 어떤 로그/문서/스크린샷에도 실제 키 값을 남기지 않는다.
- 이 문서는 성공/실패와 원인만 기록한다.

## 검증 결과(요약)
- 상태: HOLD(키 미설정으로 OpenAI 비활성)
- 원인: 현재 로컬에서 `OPENAI_API_KEY`가 감지되지 않음
  - `docs/.env` 파일은 존재하지 않는 것으로 확인됨(파일 내용을 읽거나 출력하지 않음)

## 1) OPENAI_API_KEY 환경변수 읽기 성공 여부
- 확인 방법:
  - `.env` 또는 `docs/.env`에 `OPENAI_API_KEY` 설정 후 서버 재시작
  - `/api/ai/health` 확인
- 성공 기준:
  - `enabled=true`
- 결과: FAIL
- 관측:
  - `/api/ai/health` → `enabled=false` (mock)

## 2) provider 초기화 성공 여부
- 성공 기준:
  - `/api/ai/health` 응답에 `provider=openai` 표시
- 결과: FAIL
- 관측:
  - `provider=mock`

## 3) /api/ai/health 정상 여부
- 성공 기준:
  - `ok=true`, `elapsed_sec` 존재
- 실패 시:
  - `ok=false`, `error`에 원인 요약(키/Authorization 노출 없음)
- 결과: PASS(비활성 정상)
- 관측:
  - 키 미설정 상태에서 `enabled=false`로 명확히 안내

## 4) /api/questions/generate 에서 AI 보강 동작 여부
- 확인 방법:
  - `POST /api/questions/generate`
  - 응답의 `ai`가 존재하고 `ok=true`인지 확인
- 실패 시:
  - `ai.error`만 기록(키/민감정보 금지)
- 결과: SKIP(키 미설정)
- 관측:
  - 응답에 `ai` 메타가 포함되지 않음

## 5) /api/revision/suggest_text 에서 AI 문구 보강 여부
- 확인 방법:
  - `POST /api/revision/suggest_text`
  - 응답의 `ai`가 존재하고 `ok=true`인지 확인
- 결과: SKIP(키 미설정)
- 관측:
  - 응답에 `ai` 메타가 포함되지 않음

## 6) 초안 생성 기능 동작 여부
- 확인 방법:
  - `POST /api/draft/generate`
  - 응답의 `ai`가 존재하고 `ok=true`인지 확인(활성화된 경우)
- 결과: PASS(rule/템플릿 기반 동작)
- 관측:
  - 키 미설정 상태에서도 템플릿 기반 초안 생성은 정상 동작
  - AI 메타는 포함되지 않음(비활성)

## 7) /demo 화면에서 실제 사용자 흐름이 동작하는지
- URL: `http://127.0.0.1:8787/demo`
- 확인:
  - 질문 1개씩 진행되는지
  - 마지막 질문 후 결과 화면으로 이동하는지
  - 결과가 대표 결론 1개 + 상세 accordion인지
- 결과: PASS(기본 흐름)

## 다음 액션(키 설정 후 재검증)
- `.env.example`을 `.env` 또는 `docs/.env`로 복사 후 `OPENAI_API_KEY`를 설정
- 서버 재시작 후 `/api/ai/health`에서 `enabled=true` 확인
- 이후 4~6 항목을 다시 실행해 `ai.ok=true` 확인(키/응답 민감정보 출력 금지)
