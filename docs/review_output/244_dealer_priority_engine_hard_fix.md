# 244. Dealer/distributor priority engine hard fix

## 목표
- 대리점/유통/위탁(=dealer/distributor) 계약에서 핵심 이슈를 아래 순서로 강제한다.
  1) 불이익 제공/거래상 지위 남용
  2) 경영간섭/영업자율 침해
  3) 계약해지/물량축소/공급중단/불이익조치 남용
  4) 비용전가/판촉비/광고비/반품비/원상회복 비용분담
  5) 정산/상계/공제/증빙
  6) 개인정보/고객정보/교육/운영협의
  7) 분쟁해결/재판관할/준거법
- 국내 대리점계약에서는 제27조(분쟁/관할)를 보조 이슈로만 처리(사용자 요청/크로스보더 예외)

## 변경(코드)
- dealer 조항 정렬 우선순위: [clause_level.py:_dealer_issue_rank](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L435-L467)
- 국내 dealer에서 ACT-004 보조화: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py#L244-L260)
- AI deep review 대상 선정에서 dealer 핵심 조항 가중치 + 제27 감점: [clause_level.py:_score_for_ai_deep_review](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L470-L515)

