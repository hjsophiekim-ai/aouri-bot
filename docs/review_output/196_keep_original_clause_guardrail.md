# 196) keep_as_is 가드레일(원문 유지 우선)

## 문제

- “기본원칙/법령준수” 조항이 중복제안 제거 로직에 잘못 걸려,
  - 원문이 적절한데도 “중복 취지로 판단…” 문구가 붙고
  - 사실상 수정 대상처럼 보이는 문제가 발생.

## 해결

- 조항이 아래 조건을 만족하면 `keep_as_is=True`로 판정
  - 제목에 `기본원칙/목적/총칙/일반/준수` 중 하나가 포함
  - 본문에 `법령`과 `준수/이행`이 포함
  - `공정거래법/대리점법/개인정보보호법` 등 법령명 포함
- keep_as_is 조항은:
  - `suggested_rewrite=None`
  - `rewrite_reason="법령 준수 일반원칙 문구는 현행 유지(수정 필요 없음)."`
  - **dedup 대상에서 제외**

## 구현 위치

- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - `_is_keep_as_is_clause()`
  - `clause_results` 생성 시 keep_as_is 적용
  - dedup 함수에서 keep_as_is 제외

