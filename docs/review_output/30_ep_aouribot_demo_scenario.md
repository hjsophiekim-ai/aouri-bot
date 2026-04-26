# EP + AouriBot + 결재 전환(MVP) 데모 시나리오 & 검증 문서

## 1) 데모 준비사항
- Python 실행 환경(사내 표준 버전)
- 로컬에서 AouriBot MVP 서버 실행 가능
- 샘플 계약서 파일 1개(`.txt` 또는 `.docx`)
  - MVP는 `.txt`, `.docx` 텍스트 추출만 지원

권장: 서버 실행 후 브라우저로 접속
- EP Mock: `http://127.0.0.1:8787/ep/mock/legal_request`
- 업로드(테스트): `http://127.0.0.1:8787/upload`
- Admin:
  - `http://127.0.0.1:8787/admin`
  - `http://127.0.0.1:8787/admin/reviews`
  - `http://127.0.0.1:8787/admin/approval`

## 2) 샘플 법무검토신청 생성 방법
1. EP Mock 화면 접속: `/ep/mock/legal_request`
2. 좌측 “신청 정보(EP 입력값)”에 아래를 입력
   - EP 신청 ID(권장): 예) `EP-DEMO-0001`
   - 법인(entity): 예) `fursys`
   - 계약유형(contract_type): 예) `nda` 또는 `supply` (모르면 비워도 됨)
   - 상대방/거래목적/금액/기간(옵션)
3. 파일 선택(샘플 계약서)
4. “아우리봇 패널 열기” 클릭

## 3) 계약서 업로드
1. “아우리봇 검토” 탭에서 “검토 시작” 클릭
2. 동작 확인
   - session_id가 생성되어 표시됨
   - 질문이 자동 생성되어 화면에 출력됨
   - 상태가 `aouribot_in_progress`로 표시됨

검증 포인트(API)
- `POST /api/ep/session_start` 응답에 `question_session_id`, `questions` 포함
- `GET /api/ep/status?ep_request_id=EP-DEMO-0001`에서 `status=aouribot_in_progress` 확인

## 4) 아우리봇 질문 응답
1. 질문 목록에서 필수 질문 위주로 선택(예: 책임 제한 필요, 개인정보 여부 등)
2. (선택) 추천 질문 버튼을 눌러 자주 묻는 이슈를 확인

## 5) rule 기반 검토 결과 확인
1. “답변 저장 & 검토 실행” 클릭
2. 기대 동작
   - 결과 JSON이 표시됨(요약/매칭 룰/이슈)
   - 상태가 `aouribot_completed`로 전환됨
   - 필요 시 “Approval Queue”에 항목이 생성됨(approval_required 또는 high risk일 때)

검증 포인트(API/DB)
- `POST /api/question_sessions/{id}/review` 응답에 `request_id` 포함
- `GET /api/reviews/{request_id}`로 상세 조회 가능
- `GET /api/ep/status?ep_request_id=...`에서 `status=aouribot_completed` 확인

## 6) 계약서 초안 작성 탭 시연
1. 우측 패널 탭 “계약서 초안” 클릭
2. 템플릿 선택 → “초안 생성”
3. 결과 JSON 표시 확인
   - 템플릿 기반 텍스트 생성 결과가 포함됨

검증 포인트(API)
- `GET /api/draft/templates`로 템플릿 목록 조회
- `POST /api/draft/generate`로 초안 생성

## 7) 수정 제안 탭 시연
1. 탭 “수정 제안” 클릭
2. “수정 제안 불러오기” 클릭
3. 조항별로 아래 항목이 표시되는지 확인
   - 원문 조항
   - 검출 이슈
   - 적용 rule
   - 추천 수정 방향
   - 대체 문안
   - high risk / approval required 표시

검증 포인트(API)
- `POST /api/revision/suggest`가 `revision.items[]`를 반환

## 8) 결재 전환 시연
### 8-A) 자동 전환(권장 데모)
1. “다음단계: 자동” 선택
2. “다음 단계로 넘기기” 클릭
3. 기대 결과(조건별)
   - high_risk 또는 approval_required가 있으면: `approval_pending`
   - 그 외: `legal_review_pending`

검증 포인트(API/저장)
- `POST /api/ep/handoff`
  - 응답의 `decision.target_status` 확인
  - 응답의 `persistence.handoff_status` 확인
    - 결재로 실제 handoff된 경우: `sent`
    - 법무로 라우팅된 경우: `routed_to_legal`

### 8-B) 법무 확인 후 결재로 넘기기(low/medium 케이스)
1. 자동 라우팅 결과가 `legal_review_pending`이면, 법무 확인 완료 가정
2. “다음단계: 결재(법무확인 완료)” 선택
3. “다음 단계로 넘기기” 클릭
4. 기대 결과
   - `approval_pending` 전환 + `sent` 기록

## 9) 기대 결과(최종)
- 상태 전이 흐름이 자연스럽게 이어짐
  - `draft` → `aouribot_in_progress` → `aouribot_completed`
  - `legal_review_pending` 또는 `approval_pending`으로 라우팅
- 수정 제안 탭에서 조항 단위로 이슈/대체문안이 보임
- 초안 탭에서 템플릿 기반 초안 생성이 됨
- 결재 전환 시 payload가 생성되고(멱등키 포함), 전환 기록이 저장됨

## 10) 실패 시 점검 포인트(체크리스트)
- 업로드 실패
  - 파일이 `.txt` 또는 `.docx`인지 확인(MVP 범위)
- 상태가 갱신되지 않음
  - EP 신청 ID를 입력했는지 확인
  - “상태 새로고침”으로 `/api/ep/status` 응답 확인
- 결재 전환이 막힘
  - 현재 상태가 `aouribot_completed` 또는 `legal_review_pending`인지 확인
  - 법무 확인 후 결재 강제 전환은 `legal_review_pending`에서만 허용
- handoff 실패(HTTP mode)
  - `mode=http`일 때 `endpoint` 필드 누락 여부 확인
  - 외부 결재 시스템이 200 응답을 주는지 확인
  - 실패 시 `idempotency_key`로 재시도 가능(멱등)

