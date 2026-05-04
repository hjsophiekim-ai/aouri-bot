# 219. 대리점/위탁거래 계약 질문 우선순위 업그레이드

## 목표
- 대리점/위탁거래 계약에서 “진짜 크리티컬한 질문”이 먼저 나오도록 우선순위를 재정렬한다.
- 설치/현장/산업안전, 해외 거래 질문은 본문 정황이 있을 때만 우선 질문으로 허용한다.

## 우선 질문(상위)
1. 상대방 양식 여부 (`Q-DL-001-form`)
2. 판촉비/광고비/반품비/원상회복 비용 부담 (`Q-DL-002-cost-shift`)
3. 정산식/상계/공제/증빙 기준 (`Q-DL-003-settlement`)
4. 불이익 제공/경영간섭/해지·물량축소 위험 (`Q-DL-004-termination`, focus 시 `Q-DL-006-unfair-interference`)
5. 분쟁조정/관할/준거법 특이사항(focus 시 `Q-DL-007-dispute-special`)
6. 개인정보 처리/재위탁 정황(있는 경우만, `Q-DL-005-privacy`)

## 가드레일
- 해외 거래 질문은 jurisdiction이 domestic_korea가 아닐 때만 추가:
  - `Q-DL-006-crossborder`
- 개인정보 질문은 본문에 개인정보 정황이 있을 때만 추가

## 구현
- 질문 생성 엔진(계약 프로파일이 dealer_consignment인 경우 max 5로 제한 + 우선순위 점수 기반 컷):
  - [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)
- “대리점 비용 부담” 질문 ID 호환성 유지:
  - dealer_consignment 흐름에서도 `Q-CA-001-dealer-cost`를 조건부 포함(모호한 경우만)

