# 214. 국내 vs 해외(cross-border) 하드 분리(분쟁조항 reasoning 오염 방지)

## 문제
- 국내 계약임에도 분쟁조항 수정 이유가 “해외 거래 시 집행 가능성…” 등 cross-border 논리로 작성되는 문제가 있었다.
- 국내 계약에서 “대한민국 법률 준거”를 과도하게 반복 제안하거나, 분쟁조항에 무관 문구가 섞이는 사례가 있었다.

## 변경 요약
### 1) contract_jurisdiction_profile 선계산
- `domestic_korea / cross_border / foreign_entity_involved`를 휴리스틱으로 판정:
  - [jurisdiction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/jurisdiction.py)
- 최종 컨텍스트에 포함:
  - [final_review_context.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/final_review_context.py)

### 2) domestic_korea 정책(해외 집행 reasoning 금지)
- AI system prompt에 domestic_korea일 때 해외 집행/다국가 reasoning 금지를 명시
- 추가로, 국내+분쟁조항에서 rewrite_reason에 해외 키워드가 섞이면 강제로 국내형 reason으로 교정:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 3) 분쟁조항 rewrite 분기(국내/해외)
- `ACT-004` 분쟁조항 리라이트는 jurisdiction kind에 따라 분기:
  - domestic_korea:
    - “해외 집행” 논리 금지
    - 관할 구조(전속/합의/민사소송법상 관할) 중심으로 보완
    - “대한민국 준거법”을 중복 제안하지 않도록 기본값 취급
  - cross_border:
    - 준거법 + 관할/중재 + 집행 가능성 reasoning 허용
- 구현:
  - [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)

## 기대 효과
- 국내 계약 분쟁조항이 “해외 집행 가능성” 중심으로 오염되는 현상을 원천 차단한다.
- 국내 계약에서는 관할/분쟁해결 절차의 실무적 쟁점(전속관할/합의관할/관할법원)으로 reasoning이 수렴한다.

