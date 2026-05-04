# 218. 조항별 정밀 change log + diff/이유 정합성

## 목표
- 각 조항별로 “무엇이 어떻게 바뀌었는지”를 구조화된 change_record로 남기고, UI/Word에서 동일하게 사용한다.
- diff가 없는데 삭제/수정 이유가 붙는 문제를 차단한다.
- 삭제가 있으면 Word 본문에도 취소선으로 남긴다.

## 구현
### 1) change_record 구조 도입
- clause_results에 `change_record`를 포함:
  - `change_type`: keep_as_is / suppressed / modified / unchanged
  - `unchanged_segment`
  - `inserted_segment`
  - `deleted_segment`
  - `moved_or_omitted_segment`(현재는 보수적으로 빈 배열)
  - `why_changed`
- 구현:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 2) diff 이후 재계산(일관성)
- guardrail/dedup 이후에 `has_rewrite_change`, `display_kind`, `change_record`를 재계산하여
  - UI와 Word가 동일한 “변경 여부”를 공유하도록 함

### 3) Word redline 정합성
- Word redline은 token-level diff 기반으로:
  - 추가(insert): 빨간색
  - 삭제(delete): 빨간색 + 취소선
- 구현:
  - [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

### 4) UI 표시 강화
- 조항 카드에 “중점/답변 우선”과 “유지/수정/중복생략” 배지를 함께 표시
- guidance 영역에 “중점 이슈 연결/답변 반영 쟁점” 라인을 추가
- 구현:
  - [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

## 기대 효과
- 제8조처럼 “앱 화면에서 삭제/수정처럼 보이는데 Word에는 없거나 이유가 부정확한” 불일치가 크게 감소한다.

