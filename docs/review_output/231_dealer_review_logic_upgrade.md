# 231. 대리점 계약 검토 로직 업그레이드(우선순위/핵심 조항 하드닝)

## 문제 요약
- 사용자 중점 이슈(불이익 제공/지위 남용/경영간섭/해지 남용)가 “탐지 없음”으로 처리됨
- 대리점 핵심 조항(제21/23/14/11/17/8~10)이 얕게 다뤄지고, 제27조 분쟁조항이 과도하게 상단에 노출됨
- UI와 Word 결과가 다른 경로를 사용해 신뢰성이 떨어짐

## 적용 변경
### 1) dealer/distributor 계약 우선순위 엔진 강화
- 대리점 계약에서 조항 정렬을 아래 순서로 하드 적용:
  1) 불이익 제공 / 거래상 지위 남용(제21, 제2~3 포함)
  2) 경영간섭 / 영업자율 침해(제14, 제18, 제5 등)
  3) 계약해지 / 물량축소 / 공급중단 / 불이익조치 남용(제23~24)
  4) 비용전가 / 판촉·광고·반품·원상회복 비용(제11, 제17)
  5) 정산 / 상계 / 공제 / 증빙(제8~10)
  6) 개인정보/고객정보/운영협의 등
  7) 분쟁조항/관할/준거법(제27) — 보조 이슈
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - dealer 전용 정렬키에 `_dealer_issue_rank()`를 추가
  - 제27조(dispute) 우선순위를 명시적으로 낮춤

### 2) dealer 핵심 조항 “항상 포함” 하드닝
- 룰 매칭이 없더라도 다음 조항은 screening-only로 반드시 결과에 포함:
  - 제21, 제23, 제14, 제11, 제17, 제8~10, 제27 (+ 제2~3)
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 3) dealer priority map 재정렬
- 계약 프로파일이 `dealer_consignment`일 때 우선 토픽 순서를 다음처럼 재정렬:
  - 불공정/지위남용 → 경영간섭 → 해지 → 비용전가/판촉 → 정산 → 개인정보 → 분쟁
- 구현: [priority_map.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/priority_map.py)

## 기대 효과
- 제21/23/14/11/17/8~10이 제27보다 항상 앞서 검토/표시됨
- “대리점법 핵심 조항”이 결과 상단에 안정적으로 노출되고, 후속 redline 생성 기반이 확보됨

