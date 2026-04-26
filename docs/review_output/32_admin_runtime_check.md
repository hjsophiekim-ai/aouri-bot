# /admin 런타임 검증 결과 (Runtime 앱 실행 중)

## 접속 주소
- Admin 화면: `http://127.0.0.1:8787/admin`

## 검증 방식
- 테스트 클라이언트(HTTP)로 `/admin` HTML 및 관련 API 호출을 수행해 동작을 확인했다.

## 1) admin 화면 접속 가능 여부
- 결과: 가능
- 확인:
  - `GET http://127.0.0.1:8787/admin` → HTTP `200`

## 2) rules version 표시 여부
- 결과: 표시됨
- Admin 화면에서 `rules_version` 메타를 `/api/rules/version`으로 조회해 표시한다.
- 확인:
  - `GET http://127.0.0.1:8787/api/rules/version`
  - 예시 응답(요약):
    - `rules_sha256 = f4d20829...3904512e`
    - `schema_version = 1.0`
    - `loaded_at = 2026-04-23T07:54:15+00:00`

## 3) entity / contract_type / clause_type 필터 존재 여부
- 결과: 존재
- 확인(HTML 요소 존재):
  - `entity` 입력
  - `contractType` 입력
  - `clauseType` 입력

추가로 Admin에는 다음 필터가 있다:
- `status`(confirmed 계열)
- `riskLevel`(high/medium/low)

## 4) high risk rule 조회 가능 여부
- 결과: 가능
- 확인(API):
  - `GET http://127.0.0.1:8787/api/rules?risk_level=high`
  - 응답: `count = 19`
  - 샘플: `STD-001` (`risk_level=HIGH`)

Admin UI에서도 `risk_level=high` 선택 후 조회가 가능하다.

## 5) backlog rule 분리 표시 여부
- 결과: 분리 표시됨
- Admin UI 상에 “Backlog 참고 조회” 섹션이 별도로 존재하며, `/api/backlog`를 호출해 목록을 렌더링한다.
- 확인(API):
  - `GET http://127.0.0.1:8787/api/backlog`
  - 응답: `count = 6` (참고용)

