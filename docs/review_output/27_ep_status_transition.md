# EP 상태 전이(MVP) — AouriBot 연동

## 목적
- EP(법무검토신청) 화면에서 AouriBot 검토 흐름이 끝나면, **EP 신청 상태를 다음 단계(법무/결재)로 전환**할 수 있게 한다.
- MVP 범위에서는 EP 실코드가 없으므로, **EP Mock 화면 + AouriBot Runtime API + SQLite 저장**으로 “연동 지점/전환 규칙”을 검증한다.

## 상태 정의(필수)
- `draft`: EP 신청 작성 중(또는 AouriBot 연결 전)
- `aouribot_in_progress`: AouriBot 세션 생성 완료, 질문/답변 진행 중
- `aouribot_completed`: AouriBot 질문 완료 + review analyze 완료(저장까지 완료)
- `legal_review_pending`: 법무 확인 단계(결재 전 단계)
- `approval_pending`: 결재 시스템으로 handoff 완료(결재 대기)
- `completed`: 전체 완료(법무/결재 완료 후 마감)
- `error`: (MVP 내부용) 연동 실패/오류 표기. 일반 플로우에는 노출하지 않되, 장애 복구 시 `draft` 또는 `aouribot_in_progress`로 되돌릴 수 있다.

## 전이 규칙(허용)
- `draft` → `aouribot_in_progress`
- `aouribot_in_progress` → `aouribot_completed`
- `aouribot_completed` → `legal_review_pending` 또는 `approval_pending`
- `legal_review_pending` → `approval_pending` 또는 `completed`
- `approval_pending` → `completed`
- `*` → `error` (어느 상태에서든 오류 표기 가능)
- `error` → `draft` 또는 `aouribot_in_progress`

전이 검증 로직은 [status.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ep/status.py)에서 관리한다.

## 트리거(언제 상태가 바뀌는가)
### 1) EP → AouriBot 세션 시작
- 트리거: EP 화면에서 “아우리봇 검토 시작”
- API: `POST /api/ep/session_start`
- 결과:
  - 질문 세션 생성(`question_session_id` 반환)
  - `ep_intake_session.status = aouribot_in_progress`로 저장

### 2) 질문 답변 저장 및 review 실행(검토 완료)
- 트리거: “답변 저장 & 검토 실행”
- API:
  - `POST /api/question_sessions/{session_id}/answers`
  - `POST /api/question_sessions/{session_id}/review`
- 결과:
  - review 결과 DB 저장(`review_request`, `review_result`, `review_issue`, `review_applied_rule`)
  - EP 연동 세션 상태를 `aouribot_completed`로 업데이트

### 3) 다음 단계로 전환(법무/결재)
- 트리거: “다음 단계로 넘기기”(자동) 또는 “결재(법무확인 완료)”
- API: `POST /api/ep/handoff`
- 결과(조건에 따라):
  - 고위험 또는 승인 필요: `approval_pending`으로 이동(결재 시스템 handoff 수행)
  - 그 외: `legal_review_pending`으로 이동(법무 확인 단계로 라우팅)

## API 스펙(요약)
### 상태 조회
- `GET /api/ep/status?session_id=...`
  - 응답: `ep_intake_session` 기반 상태/인테이크
- `GET /api/ep/status?ep_request_id=...`
  - 응답: 링크(`ep_request_link`)를 통해 세션을 찾고, 상태를 반환

구현: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py), 저장: [review_repository.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/db/review_repository.py)

### 상태 변경(수동)
- `POST /api/ep/status/update`
  - body:
    - `ep_request_id` (필수)
    - `session_id` (선택)
    - `status` (필수)
    - `from_status` (선택, 낙관적 동시성 체크)
    - `note` (선택)
  - 동작:
    - `from_status`가 있으면 DB 현재 상태와 일치하는지 검사(불일치 시 `409`)
    - 현재 상태 기반으로 전이 허용 여부 검증
    - `ep_status_history`에 기록(감사/추적)

## DB 저장 구조(관련 테이블)
- `ep_intake_session`
  - EP 인테이크 + AouriBot 세션 상태를 session_id 단위로 보관
- `ep_request_link`
  - `ep_request_id` ↔ `session_id` ↔ `request_id(AouriBot review 저장 결과)` 링크
- `ep_status_history`
  - 상태 변경 히스토리(감사 로그 성격)

스키마 생성: [migrations.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/db/migrations.py)

## UI 연동(MVP: EP Mock)
- EP Mock 화면: [ep_legal_request_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/ep_legal_request_ui.py)
- 주요 UX:
  - 좌측: EP 신청 입력값 + 파일 업로드
  - 우측 패널: AouriBot 탭(검토/초안/수정제안) + 상태/이슈 요약 + 다음 단계 전환

