# 디버그용 환경변수 상태 엔드포인트(116)

## 추가 엔드포인트
- `GET /api/debug/env-status`

## 반환 항목(민감정보 미포함)
- `cwd`
- `dotenv.candidates`: dotenv 탐색 후보 경로(순서 유지)
- `dotenv.loaded`: 실제 로딩된 dotenv 파일 경로 목록
- `OPENAI_API_KEY_present`: true/false
- `LAW_API_KEY_present`: true/false
- `LAW_API_ENABLED`: 문자열 값 또는 null
- `selected_ai_provider`: `"openai"` 또는 `"mock"`
- `selected_ai_model`
- `selected_law_api_enabled`: true/false
- `selected_law_base_url`

## 보안 원칙
- 실제 키 값, Authorization 헤더 등 민감정보는 절대 반환하지 않는다.

## 구현 위치
- 엔드포인트: [server.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py#L260-L356)
- 상태 생성: [env_debug.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/env_debug.py)
