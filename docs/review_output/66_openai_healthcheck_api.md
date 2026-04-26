# OpenAI 연결 검증 API: /api/ai/health

## 목표
- `OPENAI_API_KEY` 존재 여부 확인
- provider 초기화 가능 여부 확인
- 아주 짧은 테스트 프롬프트 1회 실행(키가 있을 때만)
- 성공/실패/모델명/응답시간만 반환
- 키/Authorization/민감 응답 본문을 노출하지 않음

## 엔드포인트
- `GET http://127.0.0.1:8787/api/ai/health`

## 응답 예시(키 없음)
```json
{
  "enabled": false,
  "provider": "mock",
  "model": "gpt-4.1-mini",
  "note": "OPENAI_API_KEY not set; using mock provider"
}
```

## 응답 예시(키 있음 + 성공)
```json
{
  "enabled": true,
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "elapsed_sec": 0.4321,
  "ok": true
}
```

## 구현 위치
- 라우팅/처리: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

