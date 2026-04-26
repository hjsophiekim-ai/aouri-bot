# 환경변수 로딩/재시작 재검증(118)

## 재시작 후 검증 대상
1. `/health`
2. `/api/ai/health`
3. `/api/debug/env-status`
4. `/api/review/analyze`
5. `/demo`

## 결과 요약(민감정보 미노출)
### 1) /health
- PASS: HTTP 200, `{"status":"ok"}` 확인

### 2) /api/ai/health
- PASS: enabled=`true`, provider=`openai`, ok=`true` 확인

### 3) /api/debug/env-status
- PASS
  - `cwd`와 `repo_root` 확인 가능
  - dotenv 후보/로드된 경로(`dotenv.candidates`, `dotenv.loaded`) 확인 가능
  - `OPENAI_API_KEY_present=true` 확인(값 미출력)

### 4) /api/review/analyze
- PASS: HTTP 200, 10초 내 응답, `law_search` 포함 확인

### 5) /demo
- PASS: 페이지 로딩 및 “검토 시작 → 질문 입력” 단계 진입 확인

## 핵심 체크 포인트
- `/api/ai/health` enabled=true: PASS
- provider가 mock이 아닌지: PASS(openai)
- `/api/debug/env-status` OPENAI_API_KEY_present=true: PASS
