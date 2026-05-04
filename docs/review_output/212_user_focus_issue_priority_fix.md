# 212. 사용자 중점 검토 이슈 우선순위 반영(수정)

## 문제
- 사용자가 입력한 “중점 검토 내용(review_focus)”이 조항 우선순위/표시/이유에 충분히 반영되지 않아, 일반 이슈(정산/안전/다국가 등)가 먼저 노출되는 현상이 있었다.

## 변경 요약
- 사용자 입력 review_focus를 세션/리뷰 파이프라인에 저장하고, 이를 구조화된 objective로 변환해 조항 결과에 연결했다.
- 화면 상단에 “사용자 요청 핵심 이슈 반영 결과” 섹션이 최종 결과 객체(meta.final_review_context)와 clause_results를 기반으로 표시되도록 유지/강화했다.
- 조항별 결과에 user_focus 연결 정보를 별도 필드로 포함해 UI/보고서에서 직접 표시 가능하게 했다.

## 구현 포인트
### 1) 입력 저장(Structured)
- 업로드/데모 UI에서 `review_focus`를 전송:
  - [upload_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/upload_ui.py)
  - [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
- 세션 생성 시 `input.review_focus`로 저장:
  - [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py)

### 2) review_focus → review objective 변환
- 키워드 기반 objective 파서:
  - [user_focus.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/user_focus.py)
  - 예: `dealer_unfair_disadvantage`, `dealer_management_interference`, `dealer_cost_shift`, `termination_abuse`

### 3) 우선순위 반영(표시/정렬)
- 조항별 topic 분류 후, objective→topic 매핑으로 `user_focus_hit/user_focus_matches` 산출
- 정렬 키에 user_focus_hit를 최상단으로 반영
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 4) 조항별 “이슈 연결 여부” 표시
- `user_focus_match_titles`를 clause_results에 포함:
  - UI에서 “중점 이슈 연결: …” 라인으로 표기
  - [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

## 기대 효과
- 사용자가 지정한 핵심 이슈가 조항 리스트 상단/이유 텍스트/요약 섹션에 직접 반영된다.
- “중점 이슈 관련 조항이 뒤로 밀리는 문제”를 구조적으로 방지한다. 

