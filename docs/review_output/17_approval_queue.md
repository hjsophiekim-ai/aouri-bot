# 17. Approval Queue(승인 대기함) MVP 구현

## 1) 목표
- review 결과 중 `approval_required` 또는 `high risk`가 있는 건을 “별도 대기함”으로 관리한다.
- 상태값: `new / in_review / approved / rejected`
- 실제 결재 시스템 연동 없이, MVP 상태관리만 구현한다.

## 2) 저장 구조(DB)
- DB 파일: `aouri-bot/runtime/data/db/aouribot.db`
- 마이그레이션 버전: v2
- 테이블: `approval_queue`
  - `request_id` (PK, review_request FK)
  - `status` (`new|in_review|approved|rejected`)
  - `created_at`, `updated_at`

## 3) 생성 규칙(MVP)
- review 저장 시점에 아래 중 하나면 자동으로 approval_queue에 등록:
  - `high_risk_count > 0`
  - `approval_required_count > 0`
- 초기 상태: `new`

## 4) API
- 목록: `GET /api/approval_queue`
  - 필터:
    - `status`
    - `entity`
    - `contract_type`
    - `high_risk_only=true|false`
    - `approval_required_only=true|false`
- 상세: `GET /api/approval_queue/{request_id}`
  - issue/applied_rules/rules_version 포함
- 상태 변경: `POST /api/approval_queue/{request_id}/status`
  - body: `{ "status": "in_review" }`

## 5) 관리자 UI(read-only + 상태 변경 MVP)
- 화면: `GET /admin/approval`
- 기능:
  - pending approval 목록
  - 법인/계약유형/상태 필터
  - 상세에서 issue/applied rules 확인
  - 상태 변경(new/in_review/approved/rejected)

## 6) 구현 파일
- DB/Repo:
  - `aouri-bot/runtime/db/migrations.py`
  - `aouri-bot/runtime/db/review_repository.py`
- API:
  - `aouri-bot/runtime/api/server.py`
- UI:
  - `aouri-bot/runtime/admin/approval_queue_ui.py`
  - `aouri-bot/runtime/admin/ui.py` (링크 추가)

