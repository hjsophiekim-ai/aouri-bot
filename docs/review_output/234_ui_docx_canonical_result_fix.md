# 234. UI/Word canonical result 단일 소스 강화(대리점 케이스 포함)

## 문제
- UI는 `/api/revision/suggest` 결과를 우선 사용하고, Word는 세션 기반 결과를 사용하면서
  - user_focus(review_focus)가 누락되거나
  - clause set이 달라져
  - “UI에는 있는데 Word에는 없음 / Word에는 있는데 UI에는 없음”이 발생할 수 있었다.

## 변경
### 1) `/api/revision/suggest`를 세션 canonical 결과로 통일
- `/api/revision/suggest`는 세션을 로드한 뒤 `run_review_with_session(...)` 결과를 반환하도록 변경
- 결과적으로 UI가 쓰는 clause_results와 Word(docx)가 쓰는 clause_results가 동일해짐
- 구현: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

### 2) integration 테스트 호환
- 기존 응답 스키마 호환을 위해 `revision.items`는 빈 배열로 유지(문서 구조 유지)
- 구현: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

### 3) focus 매핑 실패 시 UI 표시 개선
- focus hit가 0일 때도 `meta.user_focus_mapping_debug` 후보 조항을 UI 상단에 노출
- 구현: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

## 기대 효과
- UI clause cards, revision output, Word docx가 동일한 canonical clause_results를 사용
- user_focus 이슈 반영이 UI/Word 모두에서 일관되게 표시됨

