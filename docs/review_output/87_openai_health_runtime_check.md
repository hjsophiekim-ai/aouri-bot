# OpenAI health 런타임 체크 (/api/ai/health)

## 확인 항목
- enabled 값
- mock인지 실제 provider인지
- model 이름
- 응답시간(서버 제공 elapsed_sec + 클라이언트 계측)
- 실패 시 원인

## 결과
- 요청: `http://127.0.0.1:8787/api/ai/health`
- HTTP: `200`
- 클라이언트 응답시간: `4.0821` sec
- enabled: `false`
- provider: `"mock"`
- model: `"gpt-4.1-mini"`
- elapsed_sec(서버): `null`
- ok(서버): `null`
- note: `"OPENAI_API_KEY not set; using mock provider"`

