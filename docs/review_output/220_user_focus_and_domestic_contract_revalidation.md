# 220. user_focus + 국내계약 + UI/Word 일관성 재검증

## 재검증 대상
- 입력 DOCX: `C:\Users\FURSYS\Downloads\☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀).docx`
- 사용자 중점 검토 이슈(review_focus):
  - “대리점법 불이익 제공, 경영간섭, 비용전가, 계약해지 남용”
- 질문 답변(테스트용 가정 값):
  - 상대방 양식 yes
  - 비용전가 yes
  - 정산 통제 yes
  - 해지/불이익 위험 yes
  - 불이익 제공/경영간섭 위험 yes

※ 요청에 포함된 `붙여넣은 텍스트 (1)(42).txt` 파일은 작업 디렉토리/Downloads에서 발견되지 않아, 본 문서에서는 DOCX 기반 재검증 결과를 우선 기록한다.

## 결과 요약(스크립트 실행)
- 실행 스크립트: [revalidate_220_user_focus_and_domestic_contract.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/scripts/revalidate_220_user_focus_and_domestic_contract.py)
- 실행 결과 JSON: `aouri-bot/runtime/data/revalidate_220_result.json`

### 1) 사용자 중점 검토 이슈 반영 여부
- final_review_context.user_focus_issues가 정상 생성됨(4개 objective)
- user_focus_hit 조항 수: 20개
- 최상단 노출 조항(top_clause_ids)에 `제8조` 포함(중점/답변 우선 표시 대상)

### 2) 국내 계약에서 해외 reasoning 제거
- jurisdiction.kind = `domestic_korea`
- dispute 조항 rewrite_reason에서 “해외/집행/다국가/cross-border” 키워드 탐지: 0건

### 3) UI/Word 결과 일치(일관성)
- clause_meta.changed_clause_ids vs clause_results.has_rewrite_change 기반 changed set:
  - expected_changed_count = 1
  - actual_changed_count = 1
  - mismatch = []
- DOCX 생성(build_revision_docx) 예외 없이 성공(동일 clause_id 집합 기반)

### 4) 제8조(change log / 이유 정합성)
- 제8조(제8조 제1항) 결과:
  - user_focus_hit = true
  - factual_hit = true
  - has_rewrite_change = false
  - change_record.change_type = unchanged
  - why_changed에는 “연결(중점/답변 반영)”만 표시(삭제/수정 사유 오표기 없음)

### 5) 질문 우선순위
- 생성된 질문 IDs(top 5):
  - Q-DL-001-form
  - Q-DL-006-unfair-interference
  - Q-DL-007-dispute-special
  - Q-DL-002-cost-shift
  - Q-DL-003-settlement

### 6) 속도(참고)
- 본 재검증은 AI/Law off 상태(스크립트)에서 clause-level 처리 0.064s 기록.

