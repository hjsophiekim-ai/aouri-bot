# OpenAI API 키 환경변수(OPENAI_API_KEY) 기반 설정 정리

## 목표
- OpenAI API 키를 코드/문서/로그/테스트 어디에도 하드코딩하지 않음
- 키는 환경변수 `OPENAI_API_KEY`로만 읽음
- 키가 없으면 mock provider로 동작(또는 명확한 비활성 안내)

## 설정 키(환경변수)
- `OPENAI_API_KEY` (필수: 키가 있어야 OpenAI 호출 활성화)
- `OPENAI_MODEL` (기본값: `gpt-4.1-mini`)
- `OPENAI_TIMEOUT` (기본값: `60`)
- `OPENAI_MAX_TOKENS` (기본값: `1200`)
- `OPENAI_TEMPERATURE` (기본값: `0.2`)

## 동작 방식
- `OPENAI_API_KEY`가 **없으면**
  - provider는 자동으로 `mock`로 설정됨
  - `/api/ai/health`는 `enabled=false`로 응답
- `OPENAI_API_KEY`가 **있으면**
  - provider는 자동으로 `openai`로 설정됨
  - `/api/ai/health`에서 실제 1회 짧은 호출(ping)을 수행해 연결 여부를 확인 가능

## 구현 위치
- 설정 로더: [config.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/config.py)
- .env 로딩(로컬 편의): [dotenv.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/dotenv.py)
- provider factory: [factory.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/factory.py)

