# 198) 실제 변경된 조항만 redline 표시

## 목표

- `suggested_rewrite`가 없거나 원문과 동일한 경우에는
  - 필수수정/고위험 리스트에 포함하지 않기
  - Word 본문 redline에도 포함하지 않기

## 적용 현황

- Word 본문 redline은 이미 **diff 기반**으로 구현되어 있으며,
  `suggested_rewrite`가 없거나 원문과 동일하면 redline 대상에서 제외됨.
  - [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

- UI에서는 keep_as_is 조항을 **수정 필요 없음**으로 분리하고,
  dedup으로 인해 rewrite가 제거된 경우 “중복 취지 대표 반영”으로 구분됨.

## 추가 메모

- /demo 결과 카드도 동일한 기준으로 “실제 변경”이 있는 조항만 강조 표시되도록 유지 필요.

