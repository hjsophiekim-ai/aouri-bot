# 192) 계약유형별 rewrite pack 격리 강화(대리점 ↔ 앱개발 오염 방지)

## 문제

- 대리점 계약에서 `SOW`, `SBOM`, `오픈소스`, `소스코드` 등 **앱 개발계약 전용 문구**가 섞여 나오는 케이스가 있었다.
- 주된 원인은 다음 2가지였다.
  - 텍스트에 `license/라이선스` 같은 단어가 포함되면, 계약유형 컨텍스트가 앱개발 쪽으로 과확장되거나
  - 분류 단계에서 `라이선스/로열티`가 `대리점/위탁/유통`보다 우선 선택되어 APP-* 룰이 적용 후보에 들어오는 문제

## 변경 사항

### 1) contract_type 분류에서 대리점 우선순위 상향

- `대리점/위탁/유통`이 감지된 경우, `라이선스/로열티` 등보다 우선되도록 분류 우선순위를 올렸다.
- 위치: [classify.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/classify.py#L119-L140)

### 2) 텍스트 기반 contract_type “추가 확장”에서 app_dev 과확장 완화

- 기존: `license/라이선스` 등 **약한 힌트**만 있어도 `앱개발/...` 컨텍스트가 추가될 수 있었다.
- 변경: 아래 “강한 app_dev 증거”가 있을 때만 `앱개발/...` 컨텍스트를 추가한다.
  - 예: `소스코드`, `SOW`, `SBOM`, `오픈소스`, `API 연동`, `소프트웨어 개발` 등
- 또한 현재 contract_type 힌트 또는 본문에서 `대리점/유통/위탁`이 확인되면 app_dev 컨텍스트를 추가하지 않는다.
- 위치: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py#L63-L103)

### 3) 대리점 계약에서 APP-* 룰 매칭 결과를 최종 단계에서 차단(가드레일)

- 대리점 계약이고, 본문에 강한 app_dev 증거가 없으면:
  - `matched_rules`, `checklist_rules`에서 `APP-*` 룰을 제거한다.
- 이로써 조항별 rewrite 단계에 APP 룰이 흘러 들어가는 것을 방지한다.
- 위치: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py#L218-L270)

## 기대 효과

- 대리점 계약에서는 앱 개발계약 전용 rewrite(예: `SOW`, `SBOM`, `오픈소스` 관련 문구)가 섞여 나오지 않는다.
- 앱 개발계약(또는 명확한 app_dev 증거가 있는 계약)에서는 기존처럼 APP-* 룰이 정상 적용된다.

## 검증

- 단위 테스트 실행: `runtime.tests.test_query_service`, `runtime.tests.test_app_dev_contract_flow`, `runtime.tests.test_integration_flow` 통과.

