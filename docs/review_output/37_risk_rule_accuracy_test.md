# 6대 위험 문구 룰 탐지 정확도 테스트

기준: 각 항목별 샘플 조항 2개를 넣고 `matched_rules`가 발생하며 high/approval이 잡히는지 확인

| 항목 | 샘플 | expected | actual | 통과 | 대표 rule_ids |
| --- | --- | --- | --- | --- | --- |
| 무제한 책임 | 1 | matched_rules>=1 and (high_risk or approval_required) | matched=2 high=True appr=True | PASS | RISK-001, ACT-005 |
| 무제한 책임 | 2 | matched_rules>=1 and (high_risk or approval_required) | matched=2 high=True appr=True | PASS | RISK-001, ACT-005 |
| 일방 면책 | 1 | matched_rules>=1 and (high_risk or approval_required) | matched=2 high=True appr=True | PASS | RISK-002, ACT-006 |
| 일방 면책 | 2 | matched_rules>=1 and (high_risk or approval_required) | matched=2 high=True appr=True | PASS | RISK-002, ACT-006 |
| 기술자료 요구 | 1 | matched_rules>=1 and (high_risk or approval_required) | matched=2 high=True appr=True | PASS | RISK-004, ACT-007 |
| 기술자료 요구 | 2 | matched_rules>=1 and (high_risk or approval_required) | matched=2 high=True appr=True | PASS | RISK-004, ACT-007 |
| 하도급 단가감액 | 1 | matched_rules>=1 and (high_risk or approval_required) | matched=2 high=True appr=True | PASS | RISK-005, ACT-008 |
| 하도급 단가감액 | 2 | matched_rules>=1 and (high_risk or approval_required) | matched=2 high=True appr=True | PASS | RISK-005, ACT-008 |
| 대리점 비용전가 | 1 | matched_rules>=1 and (high_risk or approval_required) | matched=0 high=False appr=False | FAIL | - |
| 대리점 비용전가 | 2 | matched_rules>=1 and (high_risk or approval_required) | matched=0 high=False appr=False | FAIL | - |
| 안전책임 공백 | 1 | matched_rules>=1 and (high_risk or approval_required) | matched=1 high=False appr=False | FAIL | ACT-010 |
| 안전책임 공백 | 2 | matched_rules>=1 and (high_risk or approval_required) | matched=1 high=False appr=False | FAIL | ACT-010 |


## 상세(요약 JSON)
```json
{
  "무제한 책임#1": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 2,
      "checklist_rule_count": 15,
      "approval_required_match_count": 2,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 2,
    "approval_required_match_count": 2,
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
        "rule_id": "ACT-005",
        "title": "무제한 책임 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "무제한 책임#2": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 2,
      "checklist_rule_count": 15,
      "approval_required_match_count": 2,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 2,
    "approval_required_match_count": 2,
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
        "rule_id": "ACT-005",
        "title": "무제한 책임 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "일방 면책#1": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 2,
      "checklist_rule_count": 15,
      "approval_required_match_count": 2,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 2,
    "approval_required_match_count": 2,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-002",
        "title": "일방 면책/일방 배상(후보) 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-006",
        "title": "일방 배상/면책 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "일방 면책#2": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 2,
      "checklist_rule_count": 15,
      "approval_required_match_count": 2,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 2,
    "approval_required_match_count": 2,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-002",
        "title": "일방 면책/일방 배상(후보) 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-006",
        "title": "일방 배상/면책 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "기술자료 요구#1": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 2,
      "checklist_rule_count": 15,
      "approval_required_match_count": 2,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 2,
    "approval_required_match_count": 2,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-004",
        "title": "기술자료/원가자료/도면/소스코드 요구 탐지",
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
  "기술자료 요구#2": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 2,
      "checklist_rule_count": 15,
      "approval_required_match_count": 2,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 2,
    "approval_required_match_count": 2,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-004",
        "title": "기술자료/원가자료/도면/소스코드 요구 탐지",
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
  "하도급 단가감액#1": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 2,
      "checklist_rule_count": 15,
      "approval_required_match_count": 2,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 2,
    "approval_required_match_count": 2,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-005",
        "title": "하도급 단가감액/인하(후보) 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-008",
        "title": "하도급 단가감액 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "하도급 단가감액#2": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 2,
      "checklist_rule_count": 15,
      "approval_required_match_count": 2,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 2,
    "approval_required_match_count": 2,
    "high_risk": true,
    "approval_required": true,
    "top_rules": [
      {
        "rule_id": "RISK-005",
        "title": "하도급 단가감액/인하(후보) 탐지",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      },
      {
        "rule_id": "ACT-008",
        "title": "하도급 단가감액 트리거(승인 필요)",
        "risk_level": "HIGH",
        "rule_status": "approval_required",
        "approval_required": true
      }
    ]
  },
  "대리점 비용전가#1": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 0,
      "checklist_rule_count": 15,
      "approval_required_match_count": 0,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 0,
    "approval_required_match_count": 0,
    "high_risk": false,
    "approval_required": false,
    "top_rules": []
  },
  "대리점 비용전가#2": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 0,
      "checklist_rule_count": 15,
      "approval_required_match_count": 0,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 0,
    "approval_required_match_count": 0,
    "high_risk": false,
    "approval_required": false,
    "top_rules": []
  },
  "안전책임 공백#1": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 1,
      "checklist_rule_count": 15,
      "approval_required_match_count": 0,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 1,
    "approval_required_match_count": 0,
    "high_risk": false,
    "approval_required": false,
    "top_rules": [
      {
        "rule_id": "ACT-010",
        "title": "안전조항 부재/약함 후보(최소 템플릿 삽입)",
        "risk_level": "MEDIUM",
        "rule_status": "exception_possible",
        "approval_required": false
      }
    ]
  },
  "안전책임 공백#2": {
    "summary": {
      "applicable_rule_count": 29,
      "matched_rule_count": 1,
      "checklist_rule_count": 15,
      "approval_required_match_count": 0,
      "backlog_reference_count": 6
    },
    "matched_rule_count": 1,
    "approval_required_match_count": 0,
    "high_risk": false,
    "approval_required": false,
    "top_rules": [
      {
        "rule_id": "ACT-010",
        "title": "안전조항 부재/약함 후보(최소 템플릿 삽입)",
        "risk_level": "MEDIUM",
        "rule_status": "exception_possible",
        "approval_required": false
      }
    ]
  }
}
```
