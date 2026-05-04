# 238. Dealer/distributor 우선순위 재정렬 + 국내 분쟁조항 보조화

## 문제
- 국내 대리점 계약임에도 분쟁해결/재판관할(제27조)이 핵심 이슈로 과대평가되어 상단에 노출됨
- 대리점법 핵심 조항(불공정/경영간섭/해지/비용/정산)이 상대적으로 후순위로 밀림

## 목표(강제 우선순위)
dealer/distributor 계약에서는 아래 순서를 강제한다.
1) 불이익 제공 / 거래상 지위 남용  
2) 경영간섭 / 영업자율 침해  
3) 계약해지 / 물량축소 / 공급중단 / 불이익 조치 남용  
4) 비용전가 / 판촉비 / 광고비 / 반품비 / 원상회복 비용분담  
5) 정산 / 상계 / 공제 / 증빙  
6) 개인정보 / 고객정보 / 교육 / 운영협의  
7) 분쟁해결 / 관할 / 준거법

또한 국내 대리점 계약에서는 제27조(분쟁/관할)를 “핵심 이슈”가 아니라 “보조 이슈”로만 처리한다(사용자 요청/크로스보더 정황 시 예외).

## 적용 변경(코드)
- dealer 조항 정렬 우선순위: [clause_level.py:_dealer_issue_rank](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L435-L467)
  - 제21/23/14/11/17/8~10을 상단으로, 제27을 후순위로 정렬
- 국내 대리점에서 ACT-004(분쟁조항) 보조화(요약 억제 + LOW 강등):
  - [query_service.py (ACT-004 suppression)](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py#L244-L260)
- DOCX “핵심 이슈 요약/쟁점”에서 보조 분쟁조항 제거(국내 dealer + user_focus_hit 없음):
  - [docx_writer.py (summary filter)](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L439-L477)

## 기대 효과
- “국내 계약 분쟁조항 점검”이 핵심 이슈 요약/상단 카드에 올라오지 않음
- 제21/23/14/11/17/8~10이 제27보다 항상 먼저 검토/노출됨

