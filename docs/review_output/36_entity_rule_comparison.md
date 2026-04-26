# 법인(entity)별 rule 결과 비교 테스트

동일 문구를 사용하고 entity만 변경하여 4회 실행했다.

## 입력 문구
```json
{
  "contract_type": "물품공급/구매/매매",
  "text": "본 계약은 물품 공급과 관련된다.\n상대방은 당사에 판촉비 등 비용 부담을 요구할 수 있다.\n당사는 without limitation 손해배상 책임을 부담한다.\n상대방이 요구하는 기술자료 및 원가자료를 제공한다."
}
```

## 비교 결과(요약)

| entity | matched_rules | high_risk | approval_required | 대표 rule_ids |
| --- | --- | --- | --- | --- |
| 퍼시스 | 4 | Y | Y | RISK-001, RISK-004, ACT-005, ACT-007 |
| 시디즈 | 4 | Y | Y | RISK-001, RISK-004, ACT-005, ACT-007 |
| 일룸 | 4 | Y | Y | RISK-001, RISK-004, ACT-005, ACT-007 |
| 바로스 | 4 | Y | Y | RISK-001, RISK-004, ACT-005, ACT-007 |


## 상세(요약 JSON)
```json
{
  "퍼시스": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 4,
      "checklist_rule_count": 15,
      "approval_required_match_count": 4,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 4,
    "approval_required_match_count": 4,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-001",
        "title": "무제한 책임(또는 사실상 무한대) 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "RISK-004",
        "title": "기술자료/원가자료/도면/소스코드 요구 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-005",
        "title": "무제한 책임 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-007",
        "title": "기술자료/자료제출 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "시디즈": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 4,
      "checklist_rule_count": 15,
      "approval_required_match_count": 4,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 4,
    "approval_required_match_count": 4,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-001",
        "title": "무제한 책임(또는 사실상 무한대) 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "RISK-004",
        "title": "기술자료/원가자료/도면/소스코드 요구 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-005",
        "title": "무제한 책임 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-007",
        "title": "기술자료/자료제출 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "일룸": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 4,
      "checklist_rule_count": 15,
      "approval_required_match_count": 4,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 4,
    "approval_required_match_count": 4,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-001",
        "title": "무제한 책임(또는 사실상 무한대) 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "RISK-004",
        "title": "기술자료/원가자료/도면/소스코드 요구 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-005",
        "title": "무제한 책임 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-007",
        "title": "기술자료/자료제출 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "바로스": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 4,
      "checklist_rule_count": 15,
      "approval_required_match_count": 4,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 4,
    "approval_required_match_count": 4,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-001",
        "title": "무제한 책임(또는 사실상 무한대) 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "RISK-004",
        "title": "기술자료/원가자료/도면/소스코드 요구 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-005",
        "title": "무제한 책임 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-007",
        "title": "기술자료/자료제출 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  }
}
```
