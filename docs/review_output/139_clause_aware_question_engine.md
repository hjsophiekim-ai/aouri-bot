# 139) clause-aware 질문 엔진 개선

문제:
- 질문이 계약별로 달라지지 않고 “항상 비슷한 generic 질문”처럼 보이는 현상
- 이미 계약서에 충분히 명시된 항목도 반복해서 묻는 현상

목표:
- clause extraction 결과를 먼저 읽고
- detected issues / missing controls / ambiguous clauses를 기준으로 질문을 만든다
- 법인/계약유형은 가중치로만 사용
- 질문은 3~5개 이내, relevance 우선
- 질문별 reason_code 포함

---

## 1) 실제 입력 흐름

- `/api/questions/generate`에서:
  1) `service.analyze(...)`로 detected_rule_ids 확보
  2) `build_clause_level_result(... max_clause_law_items=0)`로 clause_results 확보
  3) `generate_questions(... contract_text, clause_results, detected_rule_ids ...)` 호출

코드:
- [server.py:_handle_questions_generate](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1224-L1318)
- [generator.py:generate_questions](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py#L44-L120)

---

## 2) 개선 포인트(이번 수정)

### 2.1 “이미 명시됨” 감지로 불필요 질문 제거

- 대리점/위탁 비용 질문은 `상한/정산/증빙/서면합의`가 계약서에 명시된 경우 생성하지 않습니다.
- 구현: [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)
  - `dealer_cost_details_present` 조건 추가

### 2.2 정황 기반 질문 트리거 강화(키워드만 있어도)

- `판촉비/판매장려금/반품/광고비` 같은 비용 키워드가 있으면 “대리점성 정황”으로 간주해 질문을 활성화합니다.

### 2.3 missing controls 질문 추가(개인정보)

- 개인정보 관련 키워드는 있으나 `재위탁/파기/보관기간/침해사고 통지/보안조치` 등 통제 키워드가 없으면,
  - 통제 조항 누락 가능성 질문을 생성합니다.
- 구현: `Q-CA-006-privacy-controls`

---

## 3) 회귀 테스트

- “명시된 비용 조건이 있으면 비용 질문 생략 / 부족하면 질문 생성” 테스트 추가:
  - [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py#L30-L60)

