# 결재 전환(Handoff) MVP — 조건/페이로드/저장/복구/연동방식

## 목적
- EP에서 AouriBot 검토 완료 후, **결재 시스템으로 넘길 수 있는 전환 지점**을 MVP로 구현한다.
- 실제 결재 시스템이 없으면 stub/mock으로 동작하되, **연동 인터페이스(페이로드/저장/복구)**는 운영 확장 가능하게 정의한다.

## 1) 결재 전환 payload
결재 전환 payload는 `POST /api/ep/handoff`가 생성하며, 기본 구조는 [handoff.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ep/handoff.py)에서 만든다.

예시 필드(요약):
- `handoff_id`: handoff 1건의 식별자
- `idempotency_key`: 멱등 키(기본: `"{ep_request_id}:{aouribot_request_id}:{target_status}"`)
- `ep_request_id`: EP 신청 ID
- `aouribot_request_id`: AouriBot review request_id
- `entity`, `contract_type`
- `approval_required`: 승인 필요(룰 기반)
- `high_risk`: 고위험(룰 기반)
- `counts`: `high_risk_count`, `approval_required_count`, `issue_count`
- `issues`: 저장된 issue 목록(요약)

API 응답에는 payload와 함께 `decision`, `persistence`, `integration`, `recovery`를 같이 돌려준다.

## 2) 전환 조건
### 기본 라우팅(자동)
- 조건: `high_risk == true` 또는 `approval_required == true`
  - 다음 상태: `approval_pending` (결재 시스템으로 handoff 시도)
- 그 외
  - 다음 상태: `legal_review_pending` (법무 확인 단계로 라우팅; 결재 시스템 호출 없음)

### low/medium도 결재로 넘기기
- 법무 확인 후(`legal_review_pending`) 사용자가 **강제로 결재로 넘길 수 있게** `force_approval=true` 옵션을 제공한다.
- 제약: `force_approval=true`는 `legal_review_pending` 상태에서만 허용.

상태 전이 검증: [status.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ep/status.py), API 처리: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

## 3) 전환 시 저장할 데이터
결재 전환(또는 법무 라우팅) 시, 아래 데이터를 SQLite에 기록한다.

### `approval_handoff` 테이블(핵심)
- 생성 마이그레이션: [migrations.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/db/migrations.py)
- 주요 컬럼:
  - `ep_request_id`, `request_id`, `handoff_id`
  - `idempotency_key` (UNIQUE)
  - `target_status` (`legal_review_pending` 또는 `approval_pending`)
  - `mode` (`stub` 또는 `http`)
  - `payload_json` (생성 payload JSON)
  - `status` (`created` / `routed_to_legal` / `sent` / `failed`)
  - `attempt_count` (재시도 횟수)
  - `external_reference` (외부 결재 시스템의 접수 ID 등)
  - `error_message`
  - `created_at`, `updated_at`

저장/갱신 로직: [review_repository.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/db/review_repository.py)

## 4) 전환 실패 시 복구 방식
### 실패 정의
- `target_status=approval_pending`인 경우, 외부 시스템 호출이 실패하거나 예외가 발생하면 실패로 처리한다.

### 복구 원칙(MVP)
- 실패 시 **EP 상태는 진행시키지 않는다**(즉, `approval_pending`으로 변경하지 않음).
- 실패 기록은 `approval_handoff.status=failed` + `error_message`에 남긴다.
- 재시도는 같은 `idempotency_key`로 요청한다.
  - 이미 `sent` 또는 `routed_to_legal`이면 멱등 처리로 “기존 결과”를 돌려준다.

API는 실패 시 `502(BAD_GATEWAY)`로 응답한다.

## 5) mock/stub vs 실제 API 연결 방식
### A) Stub/mock (기본)
- 모드: `mode="stub"`(기본값)
- 동작: 결재 시스템 호출 대신 성공 처리 + `external_reference="STUB-{handoff_id}"` 반환
- 구현: [approval_client.py:StubApprovalClient](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ep/approval_client.py)

### B) 실제 API 연결(HTTP POST)
- 모드: `mode="http"`
- 추가 입력:
  - `endpoint` (필수): 외부 결재 시스템 handoff URL
  - `bearer_token` (선택): 인증 토큰
  - `timeout_sec` (선택): 기본 5초
- 구현: [approval_client.py:HttpApprovalClient](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ep/approval_client.py)
- 기대 응답:
  - JSON에 `approval_request_id` 또는 `external_reference`가 있으면 `external_reference`로 저장

## API 요약
- `POST /api/ep/handoff`
  - body:
    - `ep_request_id` (필수)
    - `force_approval` (선택, bool)
    - `mode` (선택: `stub`|`http`)
    - `endpoint`/`bearer_token`/`timeout_sec` (mode=http일 때)
    - `idempotency_key` (선택)

