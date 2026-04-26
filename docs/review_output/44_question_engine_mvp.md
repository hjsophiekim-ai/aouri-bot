# 질문 엔진 MVP (Rule 기반, AI 없이 동작)

## 목표
- 계약 검토 전에 필요한 추가 질문을 생성
- 질문/답변을 저장
- 답변을 review analyze에 반영하여 적용 rule 범위를 확장

## 구현 위치(실제 코드)
- 질문 모델: [model.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/model.py)
- 질문 생성기(rule 기반): [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)
- 질문 세션 저장/조회/답변 저장: [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py)
- 답변 반영되는 검토 엔진: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)

## 동작 방식(MVP)
### 1) 세션 생성 시점(업로드/EP 세션 시작)
- 텍스트가 확보되면 `create_session()`이 pre-review를 1회 실행
  - 목적: 초기 `matched_rules`에서 `detected_rule_ids`를 만들고 질문 세트를 결정
- 질문은 “계약유형/법인 + detected_rule_ids” 기반으로 생성된다.

관련 코드:
- [create_session](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py#L60-L96)
- [generate_questions](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py#L13-L248)

### 2) 사용자 답변 저장
- API:
  - `POST /api/question_sessions/{session_id}/answers`
  - body: `{ "answers": { "Q-003-personal-data": "yes", ... } }`
- 저장:
  - `runtime/data/question_sessions/{session_id}.json` 파일에 `answers`로 저장

### 3) review analyze 반영
- `POST /api/question_sessions/{session_id}/review` 호출 시
  - 저장된 answers를 `RuleQueryService.analyze(..., answers=...)`에 전달
  - answers에 따라 `derived_context.additional_contract_types`가 확장되어 적용 rule이 달라질 수 있다.

예시(답변에 따른 확장):
- `Q-003-personal-data=yes` → `개인정보/처리위탁` 규칙군 추가 적용
- `Q-006-subcontract=yes` → `공사/도급/하도급` 규칙군 추가 적용
- `Q-007-dealer=yes` → `대리점/위탁/유통` 규칙군 추가 적용
- `Q-009-ad-model=yes` → `광고/마케팅/협찬` 규칙군 추가 적용

## 질문 예시(요구사항 매핑)
- 상대방 양식인지: `Q-001-template-owner`
- 개인정보 처리 여부: `Q-003-personal-data`
- 설치/현장 작업 여부: `Q-008-onsite-work`
- 산출물 귀속 필요 여부: `Q-004-deliverable-ip`
- 대리점/하도급 관련 여부: `Q-007-dealer`, `Q-006-subcontract`
- 해외법인 거래 여부: `Q-002-overseas`

## 보완 포인트(다음 단계 후보)
- 질문 응답의 유효성(필수 질문 미응답 시 경고/차단) 정책을 UI에서 강화
- 질문 결과를 계약서 본문(조항)과 연결해 “왜 이 질문이 필요한지” 근거 표시
- (AI 도입 시) 질문 자체는 rule 기반 유지, “계약서에서 답 근거 찾기”를 AI로 보강

