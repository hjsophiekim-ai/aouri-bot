# /api/review/analyze + law_search 재검증(105)

## case-1: 퍼시스 + 대리점/유통 관련 텍스트
- http ok=`true` status=`200` elapsed=`0.0176`
- matched_rule_ids: `["RISK-006", "ACT-009"]`
- law_search: present=`true`, enabled=`true`
- law_counts: `{"laws": 3, "precedents": 3, "interpretations": 3, "admin_rules": 0, "local_ordinances": 0}`

## case-2: 퍼시스 + 하도급/기술자료 관련 텍스트
- http ok=`true` status=`200` elapsed=`0.0024`
- matched_rule_ids: `["RISK-004", "RISK-005", "ACT-007", "ACT-008"]`
- law_search: present=`true`, enabled=`true`
- law_counts: `{"laws": 3, "precedents": 3, "interpretations": 3, "admin_rules": 0, "local_ordinances": 0}`

## case-3: 바로스 + 안전/물류센터 관련 텍스트
- http ok=`true` status=`200` elapsed=`0.0131`
- matched_rule_ids: `["ACT-010", "RISK-003"]`
- law_search: present=`true`, enabled=`true`
- law_counts: `{"laws": 3, "precedents": 3, "interpretations": 3, "admin_rules": 0, "local_ordinances": 0}`

