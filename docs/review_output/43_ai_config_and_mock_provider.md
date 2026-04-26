# AI 설정/Secret 구조 + Mock Provider (키 없이도 동작)

## 목표
- API 키가 아직 없어도 런타임이 깨지지 않도록 `mock provider`로 동작
- 나중에 키만 넣으면(설정만 주입하면) provider/model/timeout/max_tokens/temperature 등을 바꿔서 AI 호출이 가능하도록 “설정 계층”을 먼저 완성

## 구현 파일
- 설정 로더: [config.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/config.py)
- Provider 인터페이스: [provider.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/provider.py)
- Mock Provider: [mock_provider.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/mock_provider.py)
- Provider Factory: [factory.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/factory.py)
- (준비용) OpenAI 호환 HTTP Provider: [http_openai_compatible_provider.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/http_openai_compatible_provider.py)

## 설정 구조
### 1) ENV 기반(권장)
아래 환경변수로 설정 가능:
- `AOURIBOT_AI_PROVIDER`
  - 예: `mock`, `openai`, `openai_compatible`
- `AOURIBOT_AI_MODEL`
  - 예: `gpt-4.1-mini` (예시)
- `AOURIBOT_AI_API_KEY`
  - 실제 키(비밀)
- `AOURIBOT_AI_ENDPOINT`
  - OpenAI 호환 endpoint(기본값은 factory에서 `https://api.openai.com/v1/chat/completions`)
- `AOURIBOT_AI_TIMEOUT_SEC`
- `AOURIBOT_AI_MAX_TOKENS`
- `AOURIBOT_AI_TEMPERATURE`

### 2) Secret 파일(JSON) 기반(옵션)
환경변수 `AOURIBOT_AI_CONFIG_FILE`에 JSON 파일 경로를 지정하면 읽는다.
- 키 이름은 소문자로 저장:
  - `provider`, `model`, `api_key`, `endpoint`, `timeout_sec`, `max_tokens`, `temperature`
- ENV가 파일보다 우선한다(override).

예시(`ai_config.json`):
```json
{
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "api_key": "YOUR_KEY",
  "endpoint": "https://api.openai.com/v1/chat/completions",
  "timeout_sec": 15,
  "max_tokens": 800,
  "temperature": 0.2
}
```

## Mock 동작 원칙
- `AOURIBOT_AI_API_KEY`가 없거나, `AOURIBOT_AI_PROVIDER=mock`이면
  - Factory는 무조건 `MockAIProvider`를 반환한다.
- Mock은 실제 API 호출 없이, 입력 메시지를 요약해서 결정적으로 반환한다.

## “나중에 키만 넣으면 동작” 시나리오
1. 환경변수만 추가
   - `AOURIBOT_AI_PROVIDER=openai`
   - `AOURIBOT_AI_MODEL=...`
   - `AOURIBOT_AI_API_KEY=...`
2. (옵션) endpoint 변경이 필요하면 `AOURIBOT_AI_ENDPOINT` 지정
3. 애플리케이션에서 `create_ai_provider()`를 통해 provider를 생성한 후 `complete()`를 호출하면 된다.

주의:
- 현재 런타임 API 서버는 아직 AI 기능 엔드포인트를 노출하지 않는다.
- 이번 단계는 “설정/프로바이더 계층”만 준비한 상태다.

## 테스트
- 설정 로드 및 키 미존재 시 mock 선택 동작을 테스트로 검증했다:
  - [test_ai_config.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_ai_config.py)

