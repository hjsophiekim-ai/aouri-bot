# 22. EP 법무검토신청 화면 - “아우리봇 검토” 탭/버튼 추가(MVP)

## 0) 전제(중요)
- 현재 aouribot 레포에는 EP 시스템의 실제 프론트/백엔드 코드가 포함되어 있지 않다.
- 따라서 이 레포에서는 **EP 연동을 검증하기 위한 Mock 화면**을 제공하고, EP 실 코드에는 동일한 방식으로 탭/버튼을 추가하는 것을 권장한다.

## 1) 이 레포에서 제공하는 Mock EP 화면
- 경로: `GET /ep/mock/legal_request`
- 구현 파일: `aouri-bot/runtime/admin/ep_legal_request_ui.py`
- 구성:
  - EP 신청 입력값 폼(법인/계약유형/상대방/목적/금액/기간/첨부파일)
  - “아우리봇 검토” 탭
    - 계약서 업로드 후 클릭 가능
    - 검토 시작 버튼 → EP → AouriBot 세션 시작 API 호출
    - 질문 표시 → 답변 저장 → 검토 실행
  - “계약서 초안 작성” 탭

## 2) EP 실 UI에 추가해야 하는 요소(MVP)
### 2.1 버튼/탭
- “아우리봇 검토” 버튼 또는 탭
  - 조건: 계약서 첨부 후 활성화
  - 동작: AouriBot 패널/탭 열기

### 2.2 전달할 신청 정보(최소)
- `entity`, `contract_type`, `counterparty`, `purpose`, `amount`, `term_start`, `term_end`, `ep_request_id`
- 첨부파일(계약서)

## 3) EP → AouriBot 호출 방식(권장)
- EP UI에서 AouriBot API 호출(동일 사내망/인증 전제)
  - `POST /api/ep/session_start` (multipart/form-data)
  - `POST /api/question_sessions/{id}/answers`
  - `POST /api/question_sessions/{id}/review`

## 4) 이 레포에서 실제 반영된 코드 변경(참고)
- API 라우트 추가:
  - `POST /api/ep/session_start`
- Mock UI 라우트 추가:
  - `GET /ep/mock/legal_request`
- 네비게이션 링크 추가:
  - `/admin`에서 EP Mock 링크 제공

