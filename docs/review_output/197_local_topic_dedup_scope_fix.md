# 197) dedup 범위 제한(같은 조문군 내부만)

## 문제

- 개인정보/침해사고 topic의 dedup이 **제2조 기본원칙**까지 침범하는 등,
  서로 목적이 다른 조항을 과도하게 통합하는 문제가 발생.

## 해결

- dedup은 **같은 조문군(동일 `article_number`) 내부**에서만 수행.
- 다른 조(예: 제2조 vs 제20조)는 topic이 같아도 **통합 금지**.
- keep_as_is 조항은 dedup 대상에서 제외.

## 구현 위치

- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - dedup 그룹 키: `topic + article_number + rewrite_signature`
  - article_number 없는 조항은 dedup 제외

