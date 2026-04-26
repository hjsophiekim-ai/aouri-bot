# 실제 계약서 5건 review analyze 결과

대상: `docs/review_output/02_extracted_texts` 내 텍스트 추출 성공 파일 중 5건(계약유형 비중복)

| 파일명 | 계약유형 출처 | 계약유형(추정/입력) | 검출 issue(=matched rule) 수 | high_risk | approval_required | 대표 rule 3개 | 간단 평가 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| extracted_nda_f786a2cf20.txt | 추정 | NDA/비밀유지 | 5 | Y | Y | ACT-002, ACT-003, ACT-004 | 키워드 기반이라 정밀도는 제한적이나, 주요 위험 문구가 있으면 탐지되는 편 |
| FURSYS_Vietnam_Dealer_Agreement_법무팀_b11ac793ef.txt | 입력 | 대리점/위탁/유통 | 6 | Y | Y | ACT-003, ACT-004, RISK-002 | 키워드 기반이라 정밀도는 제한적이나, 주요 위험 문구가 있으면 탐지되는 편 |
| Supply_Agreement_FURSYS_LXPANTOS_250710 법무팀검토본_수정_572f12ba1e.txt | 입력 | 물품공급/구매/매매 | 5 | Y | Y | ACT-001, ACT-003, ACT-004 | 키워드 기반이라 정밀도는 제한적이나, 주요 위험 문구가 있으면 탐지되는 편 |
| 2025 퍼시스 경영 자문 계약서_이종태(법무팀)_수정_22df7a0d13.txt | 입력 | 용역/자문 | 0 | N | N | - | 키워드 기반이라 정밀도는 제한적이나, 주요 위험 문구가 있으면 탐지되는 편 |
| ☆ 참고. 개인정보처리위탁 계약서 표준안 (법무팀)_0e33d01360.txt | 추정 | 개인정보/처리위탁 | 0 | N | N | - | 키워드 기반이라 정밀도는 제한적이나, 주요 위험 문구가 있으면 탐지되는 편 |


## 케이스별 상세(요약)

### extracted_nda_f786a2cf20.txt
- entity=all contract_type=NDA/비밀유지
- 응답시간=0.0113s

```json
{
  "summary": {
    "applicable_rule_count": 20,
    "matched_rule_count": 5,
    "checklist_rule_count": 11,
    "approval_required_match_count": 2,
    "backlog_reference_count": 6
  },
  "matched_rule_count": 5,
  "approval_required_match_count": 2,
  "high_risk": true,
  "approval_required": true,
  "top_rules": [
    {
      "rule_id": "ACT-002",
      "title": "사전 서면동의 조건 명확화",
      "risk_level": "MEDIUM",
      "rule_status": "confirmed_pattern",
      "approval_required": false
    },
    {
      "rule_id": "ACT-003",
      "title": "정산식·차감사유·증빙 필수화",
      "risk_level": "MEDIUM",
      "rule_status": "confirmed_pattern",
      "approval_required": false
    },
    {
      "rule_id": "ACT-004",
      "title": "다국가 거래 분쟁조항 점검",
      "risk_level": "HIGH",
      "rule_status": "confirmed_pattern",
      "approval_required": false
    },
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
}
```

### FURSYS_Vietnam_Dealer_Agreement_법무팀_b11ac793ef.txt
- entity=퍼시스 contract_type=대리점/위탁/유통
- 응답시간=0.0238s

```json
{
  "summary": {
    "applicable_rule_count": 24,
    "matched_rule_count": 6,
    "checklist_rule_count": 12,
    "approval_required_match_count": 4,
    "backlog_reference_count": 6
  },
  "matched_rule_count": 6,
  "approval_required_match_count": 4,
  "high_risk": true,
  "approval_required": true,
  "top_rules": [
    {
      "rule_id": "ACT-003",
      "title": "정산식·차감사유·증빙 필수화",
      "risk_level": "MEDIUM",
      "rule_status": "confirmed_pattern",
      "approval_required": false
    },
    {
      "rule_id": "ACT-004",
      "title": "다국가 거래 분쟁조항 점검",
      "risk_level": "HIGH",
      "rule_status": "confirmed_pattern",
      "approval_required": false
    },
    {
      "rule_id": "RISK-002",
      "title": "일방 면책/일방 배상(후보) 탐지",
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
      "rule_id": "ACT-006",
      "title": "일방 배상/면책 트리거(승인 필요)",
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
```

### Supply_Agreement_FURSYS_LXPANTOS_250710 법무팀검토본_수정_572f12ba1e.txt
- entity=퍼시스 contract_type=물품공급/구매/매매
- 응답시간=0.0080s

```json
{
  "summary": {
    "applicable_rule_count": 29,
    "matched_rule_count": 5,
    "checklist_rule_count": 15,
    "approval_required_match_count": 2,
    "backlog_reference_count": 6
  },
  "matched_rule_count": 5,
  "approval_required_match_count": 2,
  "high_risk": true,
  "approval_required": true,
  "top_rules": [
    {
      "rule_id": "ACT-001",
      "title": "상호협의/별도협의 문구 구체화",
      "risk_level": "MEDIUM",
      "rule_status": "confirmed_pattern",
      "approval_required": false
    },
    {
      "rule_id": "ACT-003",
      "title": "정산식·차감사유·증빙 필수화",
      "risk_level": "MEDIUM",
      "rule_status": "confirmed_pattern",
      "approval_required": false
    },
    {
      "rule_id": "ACT-004",
      "title": "다국가 거래 분쟁조항 점검",
      "risk_level": "HIGH",
      "rule_status": "confirmed_pattern",
      "approval_required": false
    },
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
}
```

### 2025 퍼시스 경영 자문 계약서_이종태(법무팀)_수정_22df7a0d13.txt
- entity=퍼시스 contract_type=용역/자문
- 응답시간=0.0034s

```json
{
  "summary": {
    "applicable_rule_count": 27,
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
}
```

### ☆ 참고. 개인정보처리위탁 계약서 표준안 (법무팀)_0e33d01360.txt
- entity=all contract_type=개인정보/처리위탁
- 응답시간=0.0042s

```json
{
  "summary": {
    "applicable_rule_count": 20,
    "matched_rule_count": 0,
    "checklist_rule_count": 11,
    "approval_required_match_count": 0,
    "backlog_reference_count": 6
  },
  "matched_rule_count": 0,
  "approval_required_match_count": 0,
  "high_risk": false,
  "approval_required": false,
  "top_rules": []
}
```
