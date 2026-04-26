# /api/questions/generate 법률 토픽 반영 검증

## 확인 항목
- 질문이 한 번에 1개씩 보여줄 수 있는 구조인지
- 법률적으로 의미 있는 질문이 나오는지
- 법인별 차이가 반영되는지(토픽 기반 Q-LAW 질문 포함 여부)

## 구조 판정
- API는 `questions: []` 배열로 질문을 반환하며, UI가 1개씩 순차 표시하는 방식에 적합하다.

## case-1: 대리점성 텍스트
- input: entity=`퍼시스`, contract_type=`대리점/위탁/유통`, text=`대리점 계약이며 판촉비/광고비/반품비를 대리점이 부담합니다.`
- http ok=`true` status=`200` elapsed=`8.2724`
- count: `10`
- has_q_law(Q-LAW-*): `true`
- law_topics_present: `true` / has_key_topics: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-006-subcontract", "Q-007-dealer", "Q-LAW-001-dealer-consignment", "Q-LAW-002-dealer-promo", "Q-009-ad-model", "Q-LAW-003-subcontract-tech", "Q-LAW-004-subcontract-price"]`

## case-2: 하도급성 텍스트
- input: entity=`퍼시스`, contract_type=`공사/도급/하도급`, text=`하도급 거래로 단가 인하 및 재작업 비용 부담이 있습니다.`
- http ok=`true` status=`200` elapsed=`7.7935`
- count: `10`
- has_q_law(Q-LAW-*): `true`
- law_topics_present: `true` / has_key_topics: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-006-subcontract", "Q-LAW-001-dealer-consignment", "Q-LAW-002-dealer-promo", "Q-008-onsite-work", "Q-009-ad-model", "Q-LAW-003-subcontract-tech", "Q-LAW-004-subcontract-price"]`

## case-3: 개인정보 처리 위탁 텍스트
- input: entity=`퍼시스`, contract_type=`개인정보/처리위탁`, text=`개인정보 처리위탁(DPA) 및 재위탁, 보관기간, 파기 조항이 필요합니다.`
- http ok=`true` status=`200` elapsed=`5.2756`
- count: `10`
- has_q_law(Q-LAW-*): `true`
- law_topics_present: `true` / has_key_topics: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-006-subcontract", "Q-007-dealer", "Q-LAW-001-dealer-consignment", "Q-LAW-002-dealer-promo", "Q-009-ad-model", "Q-LAW-003-subcontract-tech", "Q-LAW-004-subcontract-price"]`

## case-4: 모델계약/광고 문구
- input: entity=`일룸`, contract_type=`광고/마케팅/협찬`, text=`광고 캠페인 및 모델(초상권) 사용 범위가 포함됩니다.`
- http ok=`true` status=`200` elapsed=`3.1046`
- count: `8`
- has_q_law(Q-LAW-*): `true`
- law_topics_present: `true` / has_key_topics: `true`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-004-deliverable-ip", "Q-006-subcontract", "Q-LAW-001-dealer-consignment", "Q-LAW-002-dealer-promo", "Q-009-ad-model"]`

## case-5: 중대재해/현장작업 문구
- input: entity=`바로스`, contract_type=`바로스(물류/설치)`, text=`물류센터 현장 작업, 안전관리, 중대재해 대응이 포함됩니다.`
- http ok=`true` status=`200` elapsed=`4.0441`
- count: `7`
- has_q_law(Q-LAW-*): `false`
- law_topics_present: `true` / has_key_topics: `false`
- question_ids: `["Q-001-template-owner", "Q-002-overseas", "Q-003-personal-data", "Q-006-subcontract", "Q-007-dealer", "Q-008-onsite-work", "Q-009-ad-model"]`

