# 21. EP 연동 아키텍처(1차 MVP 기준)

## 1) EP 연동 목표
- EP 시스템에서 “법무검토신청”을 생성할 때, **결재/상신 전에 아우리봇(rule 기반) 검토를 선행**한다.
- 계약서 본문 기반으로 **사전 질문(Pre-review Questions)**을 제시하고 답변을 저장한다.
- 답변을 반영하여 **rule 기반 검토 결과**(승인필요/고위험 포함)를 생성한다.
- EP 화면 내에서 **계약서 초안 작성/수정 제안 탭**을 제공한다(LLM 없이 템플릿+룰 조합).
- 검토 완료 후, EP의 본격 결재 시스템(또는 승인 대기함)으로 넘어가기 위한 **상태 연결 포인트**를 마련한다.

## 2) EP 화면에서 필요한 입력값
필수(최소):
- 첨부 계약서 파일(업로드)
- 법인(entity)
- 계약유형(contract_type)

권장(운영 편의/질문 품질 향상):
- 상대방(counterparty)
- 거래 목적(purpose)
- 금액(amount)
- 기간(term_start, term_end)
- EP 신청 ID(ep_request_id)

## 3) 아우리봇 호출 흐름(EP 화면 관점)
1. EP에서 법무검토신청 폼 작성 + 계약서 첨부
2. “아우리봇 검토” 탭/버튼 클릭
3. EP → AouriBot: 세션 시작 호출(업로드 포함)
4. AouriBot → EP: 질문 세트/세션 ID 반환
5. EP에서 질문 답변 입력
6. EP → AouriBot: 답변 저장 후 review 실행
7. AouriBot → EP: 검토 결과 + request_id 반환
8. EP는 결과를 화면에 표시하고, 승인필요/고위험이면 “승인 대기(또는 결재 상신)”로 연결

## 4) review API 연결 방식
권장 방식(MVP):
- EP 화면에서 AouriBot API를 직접 호출(서버-서버 또는 브라우저-서버)
  - 장점: EP UI에 탭 형태로 쉽게 붙임
  - 주의: 인증/권한/내부망 접근 제어는 EP에서 선행 필요(현재 MVP에는 인증 없음)

MVP 제공 엔드포인트:
- `POST /api/ep/session_start` (multipart/form-data)
  - file + intake_json → 질문 세션 생성
- `POST /api/question_sessions/{session_id}/answers` (JSON)
  - answers 저장
- `POST /api/question_sessions/{session_id}/review` (POST)
  - 답변 반영 review 실행 + DB 저장 + request_id 반환
- 조회(EP에서 결과 재조회 필요 시):
  - `GET /api/reviews/{request_id}`
  - `GET /api/approval_queue?...`

## 5) 질문-답변 세션 구조
- 세션 ID: `question_session_id`
- 저장 위치(서버):
  - 파일: `aouri-bot/runtime/data/question_sessions/{session_id}.json`
  - DB(EP linkage): `ep_intake_session`, `ep_request_link` (SQLite)
- 핵심 필드:
  - `source`: `ep|upload`
  - `intake`: EP 입력값 스냅샷
  - `questions[]`: 질문 세트(rule 탐지 기반)
  - `answers{}`: 사용자 답변
  - `review_result`: 실행 결과(세션 파일에 저장)

## 6) 계약서 초안 작성/수정 제안 탭 구조(MVP)
탭 1) “계약서 초안 작성”
- 표준계약서 템플릿 선택
- 법인/계약유형/당사자 정보 입력(EP 입력값 자동 채움)
- 템플릿 텍스트 기반으로 초안 텍스트 생성

탭 2) “수정 제안”
- rule 기반으로 “자주 필요한 수정 제안”을 노출
  - 예: 책임상한 제안, 일방면책 상호주의 제안, 기술자료 범위 제한 등
- MVP에서는 LLM 없이 `rule_id → 제안문` 매핑으로 제공

관련 API:
- `GET /api/draft/templates`
- `POST /api/draft/generate`

## 7) 결재시스템 전환 시점(상태 연결)
- AouriBot review가 생성되고 `request_id`가 부여된 시점부터:
  - 승인필요/고위험이면 `approval_queue`에 자동 등록(초기 `new`)
  - EP는 “결재 상신” 버튼 활성화 조건을 `approval_required/high_risk` 등으로 결정 가능
- 향후 결재 연동 시:
  - EP 신청 ID(ep_request_id) ↔ AouriBot request_id 매핑(`ep_request_link`)을 기반으로 상태를 동기화

## 8) 필요한 API/DB/UI 변경 목록
### AouriBot(API)
- 추가됨:
  - `POST /api/ep/session_start`
  - `GET /api/draft/templates`
  - `POST /api/draft/generate`
- 기존 재사용:
  - 질문 저장/리뷰 실행: `/api/question_sessions/...`
  - 결과 조회: `/api/reviews/...`
  - 승인 대기함: `/api/approval_queue/...`

### AouriBot(DB)
- 추가됨(SQLite):
  - `ep_intake_session` (EP intake + 상태)
  - `ep_request_link` (EP 신청 ID ↔ session_id ↔ request_id)

### EP(UI)
- 이 레포에는 EP 실 UI 코드가 없음
- 실제 EP에는 다음 중 하나로 탭/패널을 추가:
  - (권장) EP 페이지 내 탭 → AouriBot API 호출 + 결과 렌더링
  - (대안) AouriBot UI를 iframe으로 임베드(인증/세션 처리 별도 필요)

## 9) MVP 범위와 후속 고도화 범위
MVP 범위(이번 단계):
- rule 기반 질문/검토/승인대기함
- 표준계약서 템플릿 기반 초안 생성(텍스트)
- EP 연동용 session_start API + linkage(EP 신청 ID 매핑)

후속 고도화:
- EP 인증/권한(SSO), 감사 로그
- OCR/PDF 스캔본/HWP/legacy DOC 지원
- 표준계약서 DOCX 템플릿에 placeholder 기반 자동 치환(정교한 서식 유지)
- LLM 기반 “초안 생성/수정 제안” (옵션 기능으로 분리)
- 결재 시스템과 상태 동기화(approved/rejected 등 자동 반영)

