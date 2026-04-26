# Runtime 앱 로컬 실행 점검(Repo 기준)

## 실행 위치/명령어
- 작업 디렉토리: `aouri-bot/`
- 실행 명령(권장):
  - `python -m runtime.app`
- 대체 실행:
  - `python runtime/app.py`

기본 바인딩:
- host: `127.0.0.1`
- port: `8787`

## 1) 앱 시작 성공 여부
- 결과: 성공
- 시작 로그(요약):
  - `[AouriBot MVP] rules API started: http://127.0.0.1:8787/admin`
  - `[AouriBot MVP] upload & review: http://127.0.0.1:8787/upload`

헬스체크:
- `GET http://127.0.0.1:8787/health`
  - 응답: `{"status": "ok"}`

## 2) review rules 로드 성공 여부
- 결과: 성공
- 확인 방법:
  - `GET http://127.0.0.1:8787/api/rules`
- 확인 결과:
  - `count = 31`

## 3) /admin 접근 가능 여부
- 결과: 가능
- 확인 방법:
  - `GET http://127.0.0.1:8787/admin`
- 확인 결과:
  - HTTP `200`

## 4) review API 엔드포인트 목록
Base URL: `http://127.0.0.1:8787`

- `POST /api/review/analyze`
  - body: `{ entity, contract_type, text, filename?, answers?, persist? }`
- `POST /api/upload`
  - `multipart/form-data`
  - field: `file`(필수), `entity`(선택), `contract_type`(선택)
- `GET /api/reviews?limit=&offset=&entity=&contract_type=&high_risk_only=&approval_required_only=`
- `GET /api/reviews/{request_id}`
- `GET /api/reviews/{request_id}/applied_rules`
- `GET /api/question_sessions/{session_id}` (text 제외 메타 조회)
- `POST /api/question_sessions/{session_id}/answers`
- `POST /api/question_sessions/{session_id}/review` (DB 저장 포함)
- `POST /api/revision/suggest` (session_id 기반 조항별 수정 제안)
- `GET /api/draft/templates`
- `POST /api/draft/generate`

참고(EP/결재/대기함):
- `GET /api/approval_queue?...`
- `GET /api/approval_queue/{request_id}`
- `POST /api/approval_queue/{request_id}/status`
- `POST /api/ep/session_start`
- `GET /api/ep/status?session_id=...` 또는 `?ep_request_id=...`
- `POST /api/ep/status/update`
- `POST /api/ep/handoff`

## 5) backlog 조회 엔드포인트 목록
- `GET /api/backlog`
  - 응답: `{ count, mode: "reference_only", items: [...] }`
- 확인 결과:
  - `count = 6`

## 6) 샘플 request를 보낼 수 있는 주소
### A) Review analyze 샘플
- URL: `POST http://127.0.0.1:8787/api/review/analyze`

PowerShell 예시:
```powershell
$base = 'http://127.0.0.1:8787'
$body = @{
  entity = 'all'
  contract_type = 'all'
  filename = 'demo.txt'
  text = 'This contract includes without limitation liability and indemnify obligations.'
  persist = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "$base/api/review/analyze" `
  -ContentType 'application/json; charset=utf-8' -Body $body
```

실행 확인(요약):
- `summary` 예시:
  - `applicable_rule_count = 19`
  - `matched_rule_count = 4`
  - `approval_required_match_count = 4`

### B) Rules / Backlog 샘플
- URL:
  - `GET http://127.0.0.1:8787/api/rules`
  - `GET http://127.0.0.1:8787/api/backlog`

