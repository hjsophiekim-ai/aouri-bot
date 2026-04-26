# review analyze API 품질 점검

## 1) 응답 속도

| case | sec | http_status |
| --- | --- | --- |
| empty | 0.0033 | 200 |
| too_short | 0.0230 | 200 |
| normal | 0.0155 | 200 |
| long | 0.0621 | 200 |


## 2) issue 구조 일관성

| case | issue_struct_ok |
| --- | --- |
| empty | OK |
| too_short | OK |
| normal | OK |
| long | OK |


## 3) applied rule 설명 가능성
- matched_rules에 rule_id/title/risk_level/rule_status/approval_required가 포함되어, UI에서 근거 표시가 가능

## 4) high risk / approval_required 판정 일관성
- matched_rules 기반으로 high/approval 여부를 일관되게 계산 가능(저장 계층에서도 동일 규칙 사용)

## 5) 빈 텍스트 입력 처리

```json
{
  "name": "empty",
  "http_status": 200,
  "elapsed_sec": 0.0033221000048797578,
  "ok": true,
  "issue_struct_ok": true,
  "backlog_mixed_in_matched": false,
  "summary": {
    "applicable_rule_count": 29,
    "matched_rule_count": 0,
    "checklist_rule_count": 15,
    "approval_required_match_count": 0,
    "backlog_reference_count": 6
  }
}
```

## 6) 너무 짧은 텍스트 입력 처리

```json
{
  "name": "too_short",
  "http_status": 200,
  "elapsed_sec": 0.023015699989628047,
  "ok": true,
  "issue_struct_ok": true,
  "backlog_mixed_in_matched": false,
  "summary": {
    "applicable_rule_count": 29,
    "matched_rule_count": 0,
    "checklist_rule_count": 15,
    "approval_required_match_count": 0,
    "backlog_reference_count": 6
  }
}
```

## 7) 긴 계약 텍스트 입력 처리

```json
{
  "name": "long",
  "http_status": 200,
  "elapsed_sec": 0.06209150000358932,
  "ok": true,
  "issue_struct_ok": true,
  "backlog_mixed_in_matched": false,
  "summary": {
    "applicable_rule_count": 29,
    "matched_rule_count": 7,
    "checklist_rule_count": 15,
    "approval_required_match_count": 6,
    "backlog_reference_count": 6
  }
}
```

## 8) backlog_rules가 판정에 섞이지 않는지

| case | backlog_mixed_in_matched |
| --- | --- |
| empty | N |
| too_short | N |
| normal | N |
| long | N |