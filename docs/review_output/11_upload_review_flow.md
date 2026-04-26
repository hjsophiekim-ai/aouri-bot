# 11. 업로드 → 텍스트 확보 → 검토 결과 표시 (MVP)

## 1) 개요
- 목적: 계약서 업로드 후 텍스트를 확보하고, 법인(entity)/계약유형(contract_type)을 입력 또는 추정한 뒤 **사전 질문(Pre-review Questions)**을 거쳐 `review analyze`를 실행하고 결과를 즉시 화면에 표시한다.
- MVP 범위:
  - 업로드 포맷 지원: `.txt`, `.docx`
  - 제외: `.pdf`(OCR/텍스트레이어 판별), `.hwp/.hwpx`, legacy `.doc` (이번 단계 backlog)
  - 판정 룰: `confirmed_standard/confirmed_pattern/exception_possible/approval_required`만 사용
  - backlog(`unconfirmed_backlog`)는 참고용으로만 표시

## 2) 구현 위치(레포 내)
- API 서버: `aouri-bot/runtime/api/server.py`
- 텍스트 추출: `aouri-bot/runtime/review/text_extract.py`
- 법인/유형 추정: `aouri-bot/runtime/review/classify.py`
- 업로드 화면(UI): `aouri-bot/runtime/admin/upload_ui.py`
- 기존 관리자 화면 링크: `aouri-bot/runtime/admin/ui.py`

## 3) 처리 순서(요구사항 1~6 매핑)
### 3.1 업로드
- 화면: `GET /upload`
  - 파일 선택 + `entity`/`contract_type` 입력(선택)
  - 입력을 비우면 자동추정(휴리스틱)
- 업로드 요청: `POST /api/upload` (multipart/form-data)
  - field:
    - `file` (필수)
    - `entity` (옵션)
    - `contract_type` (옵션)

### 3.2 텍스트 확보
- `.txt`: UTF-8 읽기(대체 디코딩 포함)
- `.docx`: zip 내부 `word/*.xml`에서 `<w:t>` 텍스트 추출(본문 + 헤더/푸터/각주/미주 포함 범위)
- 지원하지 않는 포맷은 `extraction.success=false`로 반환하고, review는 실행하지 않음

### 3.3 entity / contract_type 입력 또는 추정
- 사용자 입력이 있으면 우선 적용(`*_source=user_input`)
- 없으면 텍스트+파일명 기반 휴리스틱 추정(`*_source=heuristic`)
  - entity 룰: `퍼시스/시디즈/일룸/데스커/...` 키워드
  - contract_type 룰: `NDA/DPA/임대차/공급/대리점/용역/...` 키워드

### 3.4 review analyze API 호출
- 업로드 엔드포인트(`/api/upload`)는 즉시 분석을 하지 않고, **질문 세션을 생성**한다.
  - pre-detect(본문 기반 1차 탐지) 결과로 질문을 생성하여 반환
- 답변 저장 후, 세션 기반으로 `review analyze` 실행:
  - `POST /api/question_sessions/{id}/answers`
  - `POST /api/question_sessions/{id}/review`
- 기존 JSON API 직접 호출도 가능:
  - `POST /api/review/analyze` (entity/contract_type/text 직접 전달)

### 3.5 결과 반환
- `/api/upload` 응답(JSON):
  - `extraction`: 성공/실패, method, text_length(성공 시)
  - `classification`: entity/contract_type, source
  - `question_session_id`: 질문/답변/리뷰 상태를 묶는 세션 ID
  - `detected_rule_ids`: pre-detect로 탐지된 rule_id 목록
  - `questions`: 질문 목록
- `/api/question_sessions/{id}/review` 응답(JSON):
  - `review analyze` 결과(답변 반영 포함)

### 3.6 화면 표시
- `/upload` 페이지에서 응답 JSON을 그대로 프리뷰(운영자/테스트 목적)
- `/admin` 화면에서 `/upload` 링크 제공

## 4) 로컬 실행 방법
- 서버 실행:
  - `cd aouri-bot`
  - `python -m runtime.app`
- 접속:
  - `http://127.0.0.1:8787/upload`

## 5) 테스트(최소)
- API 업로드 테스트(텍스트 파일):
  - `aouri-bot/runtime/tests/test_api_server.py::test_upload_txt`
- 전체 테스트 실행:
  - `cd aouri-bot`
  - `python -m unittest discover -s runtime/tests -v`

## 6) 이번 단계에서 제외(backlog)
- PDF 텍스트 레이어/스캔 판별 + OCR 파이프라인
- HWP/HWPX 파서
- legacy DOC 변환(Office COM 등)
