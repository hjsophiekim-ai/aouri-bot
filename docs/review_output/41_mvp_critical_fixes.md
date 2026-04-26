# MVP 치명 이슈 안정화 수정(41)

## 목적
- 고도화보다 안정화를 우선하여, “검토 결과가 틀릴 가능성이 큰 구간”을 먼저 줄인다.
- 특히 (a) 계약유형 입력 실수로 인한 미탐, (b) high risk/approval_required 소비 측 혼선을 우선 해결한다.

## 수정 요약(실제 코드)
### 1) 계약유형(contract_type) 입력 실수로 인한 미탐 완화 (우선순위 1/2)
- 문제:
  - rule 적용은 `entity + contract_type` 스코프에 크게 의존한다.
  - 사용자가 contract_type을 “물품공급”으로 넣었지만 문구가 사실상 “대리점 비용전가”이면, 해당 대리점 전용 rule이 아예 적용 대상에서 제외되어 미탐이 발생할 수 있다.
  - 이는 실무에서 가장 흔한 실패 케이스(초기 분류/입력 흔들림)라 결과 신뢰도를 크게 깎는다.
- 수정:
  - 텍스트 자체에서 키워드를 보고 `additional_contract_types_by_text`를 자동 도출하여 적용 범위를 확장.
  - 예) “대리점/판촉비/반품비/광고비” 문구가 있으면 `대리점/위탁/유통` 규칙군을 추가로 적용.
- 변경 파일:
  - [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)
    - `_derive_contract_types_from_text()`
    - `derived_context.additional_contract_types_by_text`

검증(런타임 호출):
- 입력 contract_type을 일부러 틀리게(`물품공급/구매/매매`) 주더라도,
  - “대리점 판촉비/반품 비용/광고비 부담” 텍스트에서
  - `matched_rule_count=2`, `approval_required=True`, `high_risk=True`로 탐지됨

### 2) 안전(중대재해/산안) 관련 high risk 플래그 오판정 완화 (우선순위 2)
- 문제:
  - 안전 관련 문구가 있어도 “trigger rule”로 분류되지 않으면 `matched_rules`에 못 들어가 high_risk가 false로 나올 수 있다.
  - 결과적으로 안전 관련 리스크가 “체크리스트”로만 남아 상단 요약(라우팅)에서 누락될 수 있다.
- 수정:
  - `RISK-003`에 트리거 키워드를 부여하여 안전 관련 키워드가 있으면 `matched_rules`에 포함되도록 개선.
- 변경 파일:
  - [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py) (`TRIGGER_MAP["RISK-003"]` 추가)

주의:
- `RISK-003`는 rules 문서상 “부재 기반(오탐 가능)” 성격이므로, 향후에는 “현장작업 여부” 질문/판별과 결합해 승격(approval_required) 여부를 정교화하는 것이 바람직하다.

### 3) API 응답에서 high_risk / approval_required를 명시적으로 제공 (우선순위 3)
- 문제:
  - 기존엔 소비 측(UI/워크플로우)이 `matched_rules`를 다시 해석해 high_risk/approval_required를 계산해야 했다.
  - 구현체가 여러 곳으로 퍼지면 판정 기준이 흔들릴 수 있다.
- 수정:
  - `/api/review/analyze` 응답 `summary`에 아래 필드를 추가:
    - `high_risk_match_count`
    - `high_risk` (bool)
    - `approval_required` (bool)
- 변경 파일:
  - [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)

## 결과
- 계약유형 입력이 흔들려도 핵심 high risk/approval_required 문구(대리점 비용전가, 안전)를 놓칠 가능성을 낮췄다.
- 소비 측(UI/EP 라우팅)에서 요약 플래그를 그대로 써도 되도록 API 응답을 안정화했다.

## 추가 확인(테스트)
- `python -m unittest discover -s runtime/tests -p "test_*.py"` 통과

