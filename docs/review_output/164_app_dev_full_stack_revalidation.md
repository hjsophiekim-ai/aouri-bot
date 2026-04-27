# 164. 앱 개발계약 Full Stack 재검증(/api end-to-end)

## 테스트 케이스
- entity: `일룸/데스커`
- contract_type: `앱개발/소프트웨어개발/SI/유지보수/SaaS`
- 텍스트 포함 키워드:
  - 산출물 귀속, 소스코드 인도, 유지보수, 개인정보 처리, 재위탁, 검수, SLA, 해지 시 인수인계/데이터 반환·삭제

## 호출한 엔드포인트
1) `GET /api/ai/health`  
2) `POST /api/review/analyze`  
3) `POST /api/questions/generate`  
4) `POST /api/revision/suggest_text`  
5) `POST /api/revision/download_docx` (session_id 기반)  
6) `GET /api/draft/suggest?contract_type=...`

## 결과 요약(필수 체크)
### 1) AI 적용 여부 정합성
- `/api/ai/health.enabled = true`
- `/api/review/analyze.ai.enabled = true`
- `/api/review/analyze.ai.used = true`
- `/api/review/analyze.ai.detail.ok = true` (JSON 파싱 실패 없이 AI rewrite 반영)

### 2) issues=0 방지(검토 결과가 비지 않음)
- `matched_rules_count = 10` (APP-xxx 포함)
- `clause_results_count = 9`
- `revision_items_count = 9`

### 3) law_search가 앱 개발계약에 맞는지
- `law_queries`에 아래가 포함됨:
  - 민법(도급/채무불이행/손해배상)
  - 저작권법(프로그램 저작권/양도)
  - 부정경쟁방지법(영업비밀/소스코드)
  - 개인정보보호법(유출/손해배상)
- 표시광고/모델계약/소비자보호 중심 쿼리는 포함되지 않음

### 4) questions가 clause-aware 인지(없는/애매 조항 중심)
- `questions_count = 5` (상한 준수)
- 생성된 question_id:
  - `Q-AD-001-ip-ownership`
  - `Q-AD-003-sow`
  - `Q-AD-004-acceptance`
  - `Q-AD-005-sla`
  - `Q-AD-002-oss`
- 모든 질문에 `reason_code:*` tag 포함 확인

### 5) DOCX 다운로드 가능 및 문서 내용(빈 문서 방지)
- `/api/revision/download_docx` 응답 바이트 크기: `4621 bytes`
- document.xml에 아래 섹션 포함 확인:
  - 핵심 쟁점 요약
  - 검토된 주요 조항
  - 수정 권고 조항
  - 관련 법령
  - 추가 확인 필요 질문

### 6) draft 템플릿 추천이 빈 배열로 끝나지 않는지
- `draft_suggested_template_ids`가 빈 배열이 아니며, app-dev fallback 조합(용역/개인정보/라이선스/NDA)이 포함됨

## 부가 관측
- summary: high_risk=true로 탐지되며(high_risk_match_count=8), app dev 핵심 이슈를 “수정 권고”로 연결할 수 있는 상태임

