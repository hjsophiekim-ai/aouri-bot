# 08. Admin Rules UI(읽기 전용) 구현 요약

## 구현 범위
- 최소 관리자 조회 화면(read-only) 구현
- 브라우저에서 rules/backlog 조회 + analyze 테스트 가능

## 생성/수정 파일
- `aouri-bot/runtime/admin/ui.py`
- `aouri-bot/runtime/api/server.py` (`GET /admin` 연결)

## 화면 기능
- Rules 조회
  - 필터: `status`, `entity`, `contract_type`
  - 데이터 소스: `GET /api/rules`
- Backlog 조회
  - 데이터 소스: `GET /api/backlog`
  - 화면에 “참고용”으로 표기
- Analyze 테스트
  - 데이터 소스: `POST /api/review/analyze`
  - 결과 JSON 프리뷰 표시

## 접근 URL
- `http://127.0.0.1:8787/admin`

## 정책 반영 여부
- 판정 대상 rules와 backlog를 화면에서 명확히 분리: 반영 완료
- write/edit 기능 없이 조회 전용(read-only): 반영 완료

