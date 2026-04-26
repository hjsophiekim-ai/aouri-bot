# 127. Clause-Level Review Engine 적용

## 목표
- 문서 전체에 대해 “generic risk” 하나 띄우는 형태가 아니라, **각 조항마다** 이슈/근거/수정문안을 생성
- 조항별 결과를 API 응답/DB 저장/다운로드 산출물(.docx)로 연결

## 핵심 변경
### 1) 조항별 결과 구조(clause_results) 도입
- 구현: [clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- 입력: `entity`, `contract_type`, `text`, `answers`
- 처리:
  - 룰 기반 판정: `service.analyze()`
  - 조항 분해: `split_into_clauses()`
  - 조항별 이슈/룰 매칭 + fallback 수정문안: `suggest_revisions()`
  - 출력: `clause_results`(조항별 상세 결과 배열)

### 2) /api/review/analyze에 clause_results 포함
- 구현: [server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- 기존: `matched_rules` 중심 결과
- 변경: 기존 결과 + `clause_results`, `clause_meta` 추가

### 3) 업로드 세션 리뷰(`/api/question_sessions/{id}/review`)도 clause_results 포함
- 구현: [storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py) `run_review_with_session()`
- 변경: 세션의 `text`로 `build_clause_level_result()`를 호출하여 `clause_results`/`clause_meta`를 세션 결과에 저장 및 반환

### 4) DB에 clause 결과 저장
- 스키마: [migrations.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/db/migrations.py) (v6: `review_clause_result`)
- 저장: [review_repository.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/db/review_repository.py) `save_review()`

## 조항별 결과 구조(현재)
`clause_results[]` 각 원소는 아래 키를 포함합니다.
1. `clause_id`
2. `clause_title`
3. `original_text`
4. `detected_issue_list`
5. `related_rules`
6. `related_laws`
7. `rewrite_reason`
8. `suggested_rewrite`
9. `approval_required`

## 기대 효과
- 업로드 계약서 본문 기반으로 “조항별” 이슈/수정문안을 생성
- 이후 단계(법령 그라운딩/AI rewrite/Word 산출물)로 직접 연결 가능한 데이터 구조 확보
