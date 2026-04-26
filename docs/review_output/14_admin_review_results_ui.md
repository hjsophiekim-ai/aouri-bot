# 14. Admin UI - 저장된 Review 결과 조회 화면 (Read-only MVP)

## 1) 목표
- 관리자 UI에서 저장된 review 결과를 조회한다.
- 최소 기능:
  - 최근 검토 요청 목록
  - 법인(entity) 필터
  - 계약유형(contract_type) 필터
  - high risk만 보기
  - approval required만 보기
  - 단건 상세에서 applied rules / issues / raw(backlog 참고 포함) 보기

## 2) 구현 위치
- UI HTML: `aouri-bot/runtime/admin/review_results_ui.py`
- 라우트: `GET /admin/reviews` (`aouri-bot/runtime/api/server.py`)
- 데이터 API: `GET /api/reviews`, `GET /api/reviews/{id}`

## 3) 화면 구성
- 좌측: 최근 요청 목록 테이블
  - 행 클릭 시 우측 상세 패널 로드
- 우측: 단건 상세 패널
  - rules_sha256(앞 12자리) 표시
  - high_risk/approval 카운트 배지 표시
  - issues 테이블
  - applied rules 테이블
  - raw JSON 프리뷰

## 4) 접근 경로
- 메인 관리자 화면: `/admin`
- 결과 조회 화면: `/admin/reviews`
- 업로드 화면: `/upload`

## 5) 원칙 준수
- read-only: 생성/수정/삭제 UI 없음
- 한글 라벨 우선
- 표/상세 패널 중심의 단순 구성

