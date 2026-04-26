# /api/questions/generate 재검증(106)

## 구조
- API는 `questions: []` 배열을 반환하므로 UI에서 1개씩 순차 표시가 가능하다.

## case-1: 대리점성 텍스트
- http ok=`true` status=`200` elapsed=`0.0167`
- count: `10` / has_q_law: `true` / law_topics_present: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-006-subcontract", "Q-007-dealer", "Q-LAW-001-dealer-consignment", "Q-LAW-002-dealer-promo", "Q-009-ad-model", "Q-LAW-003-subcontract-tech", "Q-LAW-004-subcontract-price"]`

## case-2: 하도급성 텍스트
- http ok=`true` status=`200` elapsed=`0.0141`
- count: `10` / has_q_law: `true` / law_topics_present: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-006-subcontract", "Q-LAW-001-dealer-consignment", "Q-LAW-002-dealer-promo", "Q-008-onsite-work", "Q-009-ad-model", "Q-LAW-003-subcontract-tech", "Q-LAW-004-subcontract-price"]`

## case-3: 개인정보 처리 위탁 텍스트
- http ok=`true` status=`200` elapsed=`0.0159`
- count: `10` / has_q_law: `true` / law_topics_present: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-006-subcontract", "Q-007-dealer", "Q-LAW-001-dealer-consignment", "Q-LAW-002-dealer-promo", "Q-009-ad-model", "Q-LAW-003-subcontract-tech", "Q-LAW-004-subcontract-price"]`

## case-4: 모델계약/광고 문구
- http ok=`true` status=`200` elapsed=`0.0155`
- count: `8` / has_q_law: `true` / law_topics_present: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-004-deliverable-ip", "Q-006-subcontract", "Q-LAW-001-dealer-consignment", "Q-LAW-002-dealer-promo", "Q-009-ad-model"]`

## case-5: 중대재해/현장작업 문구
- http ok=`true` status=`200` elapsed=`0.0154`
- count: `7` / has_q_law: `false` / law_topics_present: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-006-subcontract", "Q-007-dealer", "Q-008-onsite-work", "Q-009-ad-model"]`

