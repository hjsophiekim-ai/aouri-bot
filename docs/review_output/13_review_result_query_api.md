# 13. 저장된 Review 결과 조회 API (MVP)

## 1) 목표
- 저장된 review 결과를 관리자 UI에서 바로 조회할 수 있도록, 응답 구조를 일관되게 제공한다.
- 기능:
  1. review request 목록 조회
  2. 단건 review 결과 조회
  3. applied rules 조회
  4. high risk / approval required 필터 조회
  5. rules version 표시

## 2) 구현 위치
- API 서버: `aouri-bot/runtime/api/server.py`
- 저장소: `aouri-bot/runtime/db/review_repository.py`

## 3) 엔드포인트
### 3.1 목록 조회
- `GET /api/reviews`
- Query params:
  - `limit` (default 50)
  - `offset` (default 0)
  - `entity` (부분 일치)
  - `contract_type` (부분 일치)
  - `high_risk_only=true|false`
  - `approval_required_only=true|false`
- Response:
  - `{ count, items[] }`
  - item 필드:
    - `request_id, created_at, entity, contract_type, filename, source, rules_sha256, high_risk_count, approval_required_count`

### 3.2 단건 상세 조회
- `GET /api/reviews/{request_id}`
- Response:
  - `request`: request 메타
  - `result`: summary/raw + 카운트
  - `applied_rules`: 매칭된 적용 룰 목록
  - `issues`: 고위험/승인필요 이슈 목록
  - `rules_version`: `rules_sha256`, `schema_version`, `loaded_at`, `source_path`

### 3.3 applied rules만 조회(옵션)
- `GET /api/reviews/{request_id}/applied_rules`
- Response:
  - `{ items: [...] }`

## 4) 응답 구조 일관성 원칙(MVP)
- 목록은 `count/items` 구조
- 상세는 `request/result/applied_rules/issues/rules_version` 고정 키
- raw 결과(JSON)는 `result.raw`에 그대로 포함(운영/디버깅 용)

