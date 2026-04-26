# 24. 아우리봇 사전 질문(Pre-review Question) 플로우 (MVP)

## 1) 목표
- 계약 검토 전에 사용자가 추가 정보를 입력하도록 질문을 제시한다.
- 입력: `entity + contract_type + detected rules(본문 기반 탐지)`를 근거로 질문 세트를 생성한다.
- 답변을 저장하고, 최종 `review analyze` 실행 시 답변을 반영한다.
- LLM 의존 없이도 동작하도록 룰/휴리스틱 기반으로 구현한다.

## 2) 구현 범위(MVP)
- 질문 생성: rule 기반(탐지 rule_id + 계약유형 키워드)으로 질문 세트 구성
- 질문 답변 저장: 파일 기반 JSON 세션 저장
- 답변 반영: 답변이 `추가 계약유형 rule 확장`에 영향을 주는 형태로 반영
- 제외: OCR/PDF 스캔본, HWP/HWPX, legacy DOC 처리

## 3) 핵심 정책
- 판정에 사용하는 rule 범위: `confirmed_standard / confirmed_pattern / exception_possible / approval_required`
- `unconfirmed_backlog`는 참고용으로만 표시하며 판정에는 사용하지 않음

## 4) 처리 흐름(사용자 관점)
1. 업로드
2. 텍스트 확보(.txt/.docx)
3. entity / contract_type 입력 또는 자동추정
4. 본문 기반 1차 rule 탐지(pre-detect) → 질문 세트 생성
5. 사용자 답변 저장
6. 답변 반영하여 review analyze 실행
7. 결과 화면 표시

## 5) 엔드포인트/API
### 5.1 업로드 시작(세션 생성)
- `POST /api/upload` (multipart/form-data)
  - form fields:
    - `file`(필수)
    - `entity`(옵션)
    - `contract_type`(옵션)
  - response:
    - `question_session_id`
    - `questions[]`
    - `detected_rule_ids[]`
    - `classification`, `extraction`

### 5.2 답변 저장
- `POST /api/question_sessions/{session_id}/answers`
  - body:
    - `answers`: `{ "<question_id>": "<answer_value>" }`
  - response:
    - 세션 문서(텍스트 제외)

### 5.3 답변 반영 review 실행
- `POST /api/question_sessions/{session_id}/review`
  - response:
    - `review analyze` 결과(JSON)

### 5.4 세션 조회(읽기 전용)
- `GET /api/question_sessions/{session_id}`
  - response:
    - 세션 문서(텍스트 제외)

## 6) 질문 생성 로직
- 코드: `aouri-bot/runtime/questions/generator.py`
- 입력:
  - `entity`
  - `contract_type`
  - `detected_rule_ids` (본문 기반 pre-detect 결과)
- 출력:
  - `questions[]` (`question_id`, `title`, `description`, `options`, `related_rule_ids` 등)

### 6.1 기본 질문(항상/대부분 포함)
- 상대방 양식 vs 당사 양식
- 해외법인/해외거래 여부
- 개인정보 처리 여부
- 산출물 귀속/이전 필요 여부
- 하도급/단가감액 이슈 여부
- 대리점 비용전가 이슈 여부
- 현장 작업(안전/중대재해) 여부
- 광고/모델 계약 여부

### 6.2 rule 탐지 기반 질문 강화 예시
- `RISK-001/RISK-002` 탐지 시: 책임제한(상한) 필요 여부 질문 추가/필수화
- `RISK-004/ACT-007` 탐지 시: 기술자료 요구 여부 질문 추가/필수화
- `RISK-006/ACT-009` 탐지 시: 대리점 비용전가 질문 필수화
- `RISK-005/ACT-008` 탐지 시: 하도급/단가감액 질문 필수화

## 7) 질문/답변 저장 구조
- 저장 위치: `aouri-bot/runtime/data/question_sessions/{session_id}.json`
- 핵심 필드(요약):
  - `session_id`, `created_at`, `updated_at`
  - `rules_sha256` (룰 버전 식별)
  - `extraction`, `classification`
  - `detected_rule_ids`
  - `questions[]`
  - `answers` (question_id → value)
  - `review_result` (실행 후 저장)
  - `text` (서버 내부 저장, API 응답에서는 제외)

## 8) 답변 반영 방식(MVP)
- 코드: `aouri-bot/runtime/services/query_service.py`
- 방식:
  - 답변에 따라 `추가 contract_type rule 집합`을 포함하도록 확장 적용
  - 예:
    - `Q-003-personal-data=yes` → 개인정보/처리위탁 관련 rule을 추가로 포함
    - `Q-006-subcontract=yes` → 공사/도급/하도급 관련 rule을 추가로 포함
    - `Q-007-dealer=yes` → 대리점/위탁/유통 관련 rule을 추가로 포함
    - `Q-009-ad-model=yes` → 광고/마케팅/협찬 관련 rule을 추가로 포함
  - 해외거래(`Q-002-overseas=yes`)는 entity 매칭 범위를 넓혀 해외법인 관련 rule도 함께 적용

## 9) UI(테스트용)
- 화면: `GET /upload`
- 구성:
  - 1단계: 업로드 + entity/contract_type 입력(옵션)
  - 2단계: 질문 표시 + 답변 저장
  - 3단계: review 결과 JSON 표시

## 10) 로컬 실행
- `cd aouri-bot`
- `python -m runtime.app`
- 접속:
  - `http://127.0.0.1:8787/upload`

