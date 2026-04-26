# /api/review/analyze + law_search 응답 포함 여부 검증

## 참고(필드명)
- 현재 `/api/review/analyze` 응답은 `issues/applied_rules` 대신 `matched_rules/checklist_rules` 구조를 사용한다.

## case-1: 퍼시스 + 대리점/유통 관련 텍스트
- 입력
  - entity: `퍼시스`
  - contract_type: `대리점/위탁/유통`
  - text: `대리점 계약입니다. 판촉비/광고비/반품 비용을 대리점이 부담합니다. 판매장려금 조건이 있습니다.`
- 호출 결과
  - ok: `true`
  - http_status: `200`
  - elapsed_client_sec: `6.2873`
- review 요약(summary)
  - {"applicable_rule_count": 24, "matched_rule_count": 2, "checklist_rule_count": 12, "approval_required_match_count": 2, "high_risk_match_count": 2, "approval_required": true, "high_risk": true, "backlog_reference_count": 6}
- matched_rules(rule_ids)
  - ["RISK-006", "ACT-009"]
- law_search
  - present: `true` / enabled: `true`
  - counts: `{"laws": 5, "precedents": 5, "interpretations": 5, "admin_rules": 5, "local_ordinances": 5}`
  - errors: `{}`

## case-2: 퍼시스 + 하도급/기술자료 관련 텍스트
- 입력
  - entity: `퍼시스`
  - contract_type: `공사/도급/하도급`
  - text: `하도급 거래로서 단가 인하(감액) 및 원가자료/기술자료 제출을 요구합니다. 재하도급 제한 조항이 있습니다.`
- 호출 결과
  - ok: `true`
  - http_status: `200`
  - elapsed_client_sec: `4.9036`
- review 요약(summary)
  - {"applicable_rule_count": 28, "matched_rule_count": 4, "checklist_rule_count": 14, "approval_required_match_count": 4, "high_risk_match_count": 4, "approval_required": true, "high_risk": true, "backlog_reference_count": 6}
- matched_rules(rule_ids)
  - ["RISK-004", "RISK-005", "ACT-007", "ACT-008"]
- law_search
  - present: `true` / enabled: `true`
  - counts: `{"laws": 5, "precedents": 5, "interpretations": 5, "admin_rules": 5, "local_ordinances": 5}`
  - errors: `{}`

## case-3: 바로스 + 안전/물류센터 관련 텍스트
- 입력
  - entity: `바로스`
  - contract_type: `바로스(물류/설치)`
  - text: `물류센터 현장 작업이 포함됩니다. 안전관리 책임, 산업안전보건, 중대재해 관련 조항이 있습니다.`
- 호출 결과
  - ok: `true`
  - http_status: `200`
  - elapsed_client_sec: `10.1958`
- review 요약(summary)
  - {"applicable_rule_count": 28, "matched_rule_count": 2, "checklist_rule_count": 14, "approval_required_match_count": 0, "high_risk_match_count": 1, "approval_required": false, "high_risk": true, "backlog_reference_count": 6}
- matched_rules(rule_ids)
  - ["ACT-010", "RISK-003"]
- law_search
  - present: `true` / enabled: `true`
  - counts: `{"laws": 5, "precedents": 5, "interpretations": 5, "admin_rules": 5, "local_ordinances": 5}`
  - errors: `{}`

## 결과 타당성(간단 판정 기준)
- 대리점/비용전가 키워드가 포함된 경우 `RISK-006/ACT-009` 계열이 matched_rules에 나타나는지 확인
- 하도급/기술자료 키워드가 포함된 경우 `RISK-005/ACT-008` 또는 `RISK-004/ACT-007` 계열이 나타나는지 확인
- 안전/중대재해 키워드가 포함된 경우 `RISK-003/ACT-010` 계열이 나타나는지 확인

