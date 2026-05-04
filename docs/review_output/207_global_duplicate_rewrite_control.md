# 207) 중복 수정문안 반복 삽입 제어(near-duplicate + 대표 1회)

## 목표

- 같은 취지/유사 문구가 조문군 내부에서 5~6번 반복 삽입되는 문제를 방지한다.
- 대표 조항 1회만 redline하고, 나머지는 guidance로만 남긴다.

## 정책

- 기본 원칙: **같은 토픽 + 같은 조문군(article_number) 내부에서만** dedup 수행
- 인접 조건: paragraph_number가 ±2 이내인 경우에만 suppression 허용
- exact duplicate 뿐 아니라 **near duplicate 유사도 기준**(SequenceMatcher ratio)으로도 통합

## 구현

- 토픽 추정: `security_incident / subcontract / data_return_delete`
- 대표 조항(anchor) 선택:
  - must_fix/high_risk/approval_required 우선
  - 토픽 적합성이 높은 제목(예: 개인정보/보안/정보보호) 우선
  - 일반/목적 조항은 감점
- near-duplicate 판정:
  - 정규화한 텍스트를 기준으로 ratio ≥ 0.93이면 동일 취지로 취급
- 억제된 조항 처리:
  - suggested_rewrite 제거(redline 금지)
  - rewrite_reason에 “대표 조항에 반영” 안내만 추가

## 변경 위치

- dedup 로직: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L116-L221)

