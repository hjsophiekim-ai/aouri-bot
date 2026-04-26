# 런타임 환경변수/닷env 로딩 재검증(102)

## 원칙
- 실제 키 값은 절대 출력하지 않고, 존재 여부만 true/false로 기록한다.

## 1) .env 파일 존재 여부
- `.env`: `true`
- `.env.local`: `false`
- `docs/.env`: `false`
- `docs/.env.local`: `false`

## 2)~4) 프로세스 환경변수 존재 여부(로더 호출 전/후)
- 로더 호출 전
  - `OPENAI_API_KEY`: `false`
  - `LAW_API_KEY`: `false`
  - `LAW_API_ENABLED`: `null`
- 로더 호출 후(.env 로딩 적용 포함)
  - `OPENAI_API_KEY`: `false`
  - `LAW_API_KEY`: `true`
  - `LAW_API_ENABLED`: `"true"`

## 5) config 로더 인식
- `load_ai_config()` → provider=`mock`, api_key_present=`false`, model=`gpt-4.1-mini`
- `load_law_api_config()` → enabled=`true`, api_key_present=`true`, base_url=`https://www.law.go.kr/DRF`

