# 174) AI deep review 범위 확장(2단계 구조) 적용

## 문제(기존)
- `/api/review/analyze` 및 일부 경로에서 `max_ai_clauses=4`로 고정되어, 문서 전체를 충분히 deep review 하지 못함
- 업로드→세션 리뷰(`/api/question_sessions/{id}/review`) 경로는 AI/Law를 사용하지 않아 analyze 대비 품질 격차가 발생
- 응답에서 “어떤 조항이 AI deep review 되었는지”가 명확히 표시되지 않음

## 목표(적용)
- 1단계: deterministic/rule 기반으로 전 조항 스크리닝(위험도/우선순위 산정)
- 2단계: HIGH + MEDIUM + 핵심 조항(계약유형별 우선순위) 중심으로 AI deep review 수행
- `max_ai_clauses=4` 하드코딩 제거(동적 선택)
- 응답에 AI deep review 된 조항을 표시

## 구현 요약
### 1) max_ai_clauses 하드코딩 제거
- `/api/review/analyze`, `/api/revision/*`, `/api/revision/download_docx` 등에서 `max_ai_clauses=4/6` 전달 제거
- 실제 deep review 대상 수는 `clause_count` 및 `tier_counts` 기반으로 동적 산정

관련 코드:
- [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L621-L677)

### 2) 2단계 구조: 스크리닝 → deep review
- 스크리닝(전체 조항):
  - rules 기반 이슈/리스크 산정
  - 계약유형별 핵심 키워드(앱개발/장비구매·설치 등)로 우선순위 반영
- deep review(선택 조항):
  - HIGH/approval_required 우선 + MEDIUM 일부 + 핵심조항 일부
  - 출력 안정성을 위해 선택 조항을 chunk로 분할 호출(토큰 한계/JSON 파손 방지)

관련 코드:
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 3) “어떤 조항이 AI deep review 되었는지” 표시
- `clause_results[].ai_deep_reviewed: bool` 추가
- `clause_meta.ai.selected_clause_ids`, `selected_count`, `used/ok/usage` 추가
- `/api/review/analyze`의 `ai.used`는 `clause_meta.ai.used`와 일치하도록 계산 방식 수정

관련 코드:
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L337-L535)
- [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L669-L677)

### 4) 세션 리뷰 경로 품질 동기화(업로드→리뷰)
- 기존 `run_review_with_session()`이 AI/Law를 비활성화하고 있었던 구조를 개선
- 업로드→리뷰 경로에서도 analyze와 동일하게 AI deep review 및 law_search를 적용

관련 코드:
- [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py#L131-L181)

## 검증(모션베드 앱개발 계약서)
- AI deep review selected_count: `26`
- Word redline: 삭제 취소선(`<w:strike>`) 확인
- 조/항/호 구조 및 guidance 분리 확인

리포트:
- [172_motionbed_app_contract_redline_revalidation.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/172_motionbed_app_contract_redline_revalidation.md)

