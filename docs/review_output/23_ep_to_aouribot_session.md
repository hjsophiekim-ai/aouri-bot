# 23. EP → AouriBot 세션 연결(입력값 자동 전달) MVP

## 1) 목표
- EP에서 입력한 법인/계약유형/상대방/목적/금액/기간/첨부파일 정보를
  - AouriBot review 세션 시작 시 자동으로 넘긴다.
  - 사용자가 동일 정보를 다시 입력하지 않게 한다.

## 2) Intake payload schema(MVP)
- 필드(모두 optional, 파일은 별도):
  - `ep_request_id`: EP 신청 식별자
  - `entity`: 법인
  - `contract_type`: 계약유형
  - `counterparty`: 상대방
  - `purpose`: 거래 목적
  - `amount`: 금액(문자열)
  - `term_start`: 기간 시작(문자열)
  - `term_end`: 기간 종료(문자열)
  - `attachment_names`: 첨부파일명 목록(list[str])
- 검증 코드:
  - `aouri-bot/runtime/ep/intake.py`

## 3) EP → session start API
- `POST /api/ep/session_start` (multipart/form-data)
  - fields:
    - `file`: 계약서 파일(필수, MVP: txt/docx만 추출)
    - `intake_json`: 위 schema JSON 문자열(필수)
  - response:
    - `question_session_id`
    - `questions[]`
    - `classification` (entity/contract_type + is_inferred 표시)
    - `intake` (서버 저장된 intake echo)

## 4) 세션 ID 반환
- `question_session_id`로 반환
- 이후 호출:
  - `POST /api/question_sessions/{id}/answers`
  - `POST /api/question_sessions/{id}/review`

## 5) 업로드 파일 연결
- session start 호출 시 파일을 함께 업로드하여 서버에서 텍스트 추출 및 세션 문서에 저장
- 세션 파일:
  - `aouri-bot/runtime/data/question_sessions/{session_id}.json`
  - `input.filename`, `extraction`, `text` 포함

## 6) 초기 상태 저장(MVP)
- 파일 기반:
  - 세션 JSON에 `source=ep`, `intake`, `questions`, `detected_rule_ids` 저장
- DB 기반(EP linkage):
  - `ep_intake_session`에 `session_id/ep_request_id/intake_json/status` 저장(초기 status=`new`)
  - `ep_request_link`에 ep_request_id ↔ session_id 매핑 저장
- review 실행 후:
  - review 결과 DB 저장 시 `request_id`가 발급되며, ep_request_link에 request_id를 연결하고 ep_intake_session status를 `reviewed`로 업데이트

