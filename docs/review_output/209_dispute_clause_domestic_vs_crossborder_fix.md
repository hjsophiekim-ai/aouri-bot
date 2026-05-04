# 209) 분쟁해결/재판관할 조항: 국내 vs 해외 분리

## 목표

- 국내 계약에서 해외집행/다국가 분쟁 reasoning 금지
- 해외 정황이 있을 때만 cross-border 관점(집행/비용/기간)을 적용
- 분쟁조항 rewrite를 국내/해외 케이스로 분리

## 구현

### 1) 국내/해외 판별 레이어

- `domestic_korea / cross_border / foreign_entity_involved` 판정 및 evidence 반환
- 위치: [jurisdiction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/jurisdiction.py)

### 2) ACT-004(다국가 분쟁) 국내 완화

- 국내로 판정되면 ACT-004는:
  - 위험도를 HIGH로 취급하지 않고 MEDIUM으로 완화
  - 설명을 “국내 분쟁조항 점검(전속관할/관할 구조)” 중심으로 변경
- 위치: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)

### 3) 분쟁조항 rewrite: domestic vs cross-border

- 국내(`domestic_korea`)
  - 해외집행 reasoning 없이 `준거법(대한민국)` + `전속관할(서울중앙지방법원)` 중심으로 제안
- 해외 정황(`cross_border/foreign_entity_involved`)
  - 준거법과 관할/중재를 명시하도록 템플릿 형태로 제안
- 위치: [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py#L610-L642)

