# 215. Review Output single source of truth + UI/Word 불일치 방지

## 문제
- UI 화면과 Word 수정본이 서로 다른 결과 객체/조항 세트를 사용하면 “UI에는 있는데 Word에는 없음” 같은 불일치가 발생한다.
- 특히 suggested_rewrite가 guardrail/dedup로 제거된 뒤에도, 변경 여부 플래그가 갱신되지 않으면 Word redline에 누락처럼 보일 수 있다.

## 변경 요약
### 1) 세션에 original_clauses 저장(동일 조항 ID 기준)
- 세션 생성 시, build_clause_level_result가 사용한 clause extraction 결과를 `original_clauses`로 저장:
  - [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py)
- deep/fast 결과에도 `original_clauses`를 포함해, UI/Word가 동일한 조항 ID 집합을 공유하도록 함.

### 2) docx 다운로드에서 세션 결과 우선 사용
- `/api/revision/download_docx`(session_id 경로)에서:
  - 세션의 `review_result.clause_results` + `review_result.original_clauses`를 우선 사용
  - 원문 재추출(extract_clauses)로 인해 조항 ID가 달라지는 문제를 회피
- 구현:
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

### 3) consistency checker(실패 처리)
- docx 생성 전 다음 검증을 수행하고, 불일치 시 JSON 에러로 실패 처리:
  - clause_results의 clause_id가 original_clauses에 모두 존재하는지
  - UI meta의 changed_clause_ids와 실제 clause_results의 has_rewrite_change 기반 changed set이 일치하는지
- 구현:
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

### 4) 변경 여부/표시 kind 재계산(guardrail/dedup 이후)
- guardrail/dedup 적용 이후에 `has_rewrite_change`, `display_kind`, `change_record`를 재계산하여
  - “변경 없음인데 변경으로 표시”
  - “UI에는 redline인데 Word에는 diff 없음”
  같은 불일치를 줄임
- 구현:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - Word 측은 `has_rewrite_change`를 우선 사용:
    - [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

## 기대 효과
- UI/Word/다운로드 문서가 동일 clause_id 집합을 기준으로 동작한다.
- “UI에는 있는데 Word에는 없음”이 발생하면 docx 생성이 실패 처리되어 조용한 누락을 방지한다.

