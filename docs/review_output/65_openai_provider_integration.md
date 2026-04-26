# OpenAI Provider 연동(MVP, 키 없으면 mock)

## 목표
- `OPENAI_API_KEY`가 있으면 OpenAI API 호출
- 없으면 mock provider 유지(런타임이 깨지지 않음)
- 모델/timeout/max_tokens/temperature는 환경변수 기반
- 에러는 안전한 메시지로 반환(키/Authorization 노출 금지)

## 구현 요약
- 설정 로더는 **오직 환경변수 기반**으로 동작한다.
  - 키: `OPENAI_API_KEY`만 사용
  - 로컬 편의: `.env`를 읽어 `os.environ`에 주입(키를 “환경변수로”만 사용한다는 원칙 유지)
- factory는 키 존재 여부로 provider를 자동 선택한다.

## 구현 파일
- 설정: [config.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/config.py)
- .env 로더: [dotenv.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/dotenv.py)
- provider 선택: [factory.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/factory.py)
- OpenAI(HTTP) 호출: [http_openai_compatible_provider.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/http_openai_compatible_provider.py)
- 에러 마스킹: [safe.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/safe.py)

## 보안 원칙
- 코드/문서/테스트에 실제 키를 넣지 않는다.
- Authorization 헤더/키 문자열을 로그로 출력하지 않는다.
- 오류 메시지에 키가 섞일 가능성을 대비해 마스킹 처리한다.

