# 237. Dealer review priority map 하드닝(제27 후순위 고정)

## 목표
- 대리점 계약에서 제27조 분쟁해결 조항보다
  - 제21(불공정행위)
  - 제23(해지)
  - 제14(경영간섭/인력)
  - 제11/제17(비용전가/비용분담)
  - 제8~10(정산/상계)
  를 항상 우선 검토하도록 하드코딩 수준으로 강화

## 적용 변경
### 1) dealer 핵심 조항 강제 포함(룰 매칭 무관)
- dealer_consignment 프로파일이면 아래 조문 번호를 screening-only로라도 결과에 포함:
  - 2, 3, 8, 9, 10, 11, 14, 17, 21, 23, 27
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 2) dealer 전용 정렬 우선순위 하드 적용
- 조항 정렬은 user_focus_hit 다음으로 `_dealer_issue_rank()`를 사용:
  - 제21/제2~3(불이익/지위남용) → 제14/18/5(경영간섭) → 제23/24(해지) → 제11/17(비용) → 제8~10(정산) → 기타 → 제27(분쟁)
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 3) dealer priority topics 재정렬
- dealer_consignment 프로파일 우선 토픽을 “대리점 핵심 이슈 → 분쟁(후순위)”로 재정렬
- 구현: [priority_map.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/priority_map.py)

## 결과
- 제27조는 대리점 핵심 위험(불공정/경영간섭/해지/비용/정산)을 먼저 다 본 뒤 보조적으로만 노출됨

