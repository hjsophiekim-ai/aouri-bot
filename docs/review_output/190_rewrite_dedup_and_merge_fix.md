# 190) 조항별 수정문안 반복(dedup) 억제

## 문제

- 동일한 “침해사고(보안사고/개인정보 유출) 발생 시…” 문구가 한 계약서 안에서 여러 조항에 반복 삽입되는 현상이 발생.
- 사용자는 “같은 취지의 주의형 문구는 1번만 나와도 충분”하다고 체감.

## 목표

- 동일/유사한 수정 문구는 **대표 조항 1회만 redline**로 남기고,
- 나머지 유사 조항은
  - “관련 조항에서 동일 취지 반영 필요” 안내로 전환하거나
  - guidance만 표시하도록 조정.

## 구현(현재 적용)

- `ClauseLevelResult` 생성 직전에, `clause_results`의 `suggested_rewrite`를 대상으로 **topic 기반 중복 억제**를 수행.
- 우선 적용 topic:
  - `security_incident` (침해사고/보안사고/개인정보 유출/유출사고)
  - `subcontract` (재위탁/하도급)
  - `data_return_delete` (데이터 반환/삭제/종료)

### 동작 요약

- 동일 topic + 거의 동일한 `suggested_rewrite`는 한 그룹으로 묶음
- 그룹 내 대표 조항(앵커)을 “must_fix/high_risk/HIGH + 키워드 적합도”로 선정
- 앵커가 아닌 조항은(단, HIGH/must_fix는 제외)
  - `suggested_rewrite=None`로 제거
  - `rewrite_reason`에 “중복 제안으로 판단되어 (대표 조항) 에 동일 취지 반영 권고” 문구를 추가
  - 메타 필드 추가:
    - `dedup_group`
    - `dedup_primary_clause_id`
    - `dedup_suppressed=true`

## 변경 파일

- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

## 비고

- “여러 번 모두 수정해야 하는 경우”(예: 서로 다른 의무/요건이 실제로 분산되어 있는 경우)는 HIGH/must_fix는 억제 대상에서 제외하여 안전하게 유지.
- 이후 고도화(요청 194)에 맞춰 topic별 “대표 위치(앵커) 선정 규칙”을 더 정교화 가능.

