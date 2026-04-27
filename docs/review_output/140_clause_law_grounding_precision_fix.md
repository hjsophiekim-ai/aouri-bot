# 140) clause-aware 법령 grounding 정밀화

문제:
- 관련 법령/판례 결과에 조항과 직접 관련 없는 결과(조례안/광고/공고 등)가 섞여 grounding 신뢰도가 낮아짐

목표:
- 조항별 issue에 맞는 법령만 좁게 붙이기
- law_search를 전체 계약 공통 묶음이 아니라 clause-aware retrieval로 운영
- 관련성 점수 낮은 결과 제거 + 직접 관련 법령 우선
- 판례/해석례는 “조항과의 직접 연결”이 약하면 기본 비활성(노이즈 최소화)

---

## 1) 기존 흐름(조항 단위 검색은 있었지만, 쿼리가 넓어짐)

- clause-level에서 조항별 `related_laws`를 만들고 있었음:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L152-L168)
- 하지만 검색 토픽 생성에서 “법인 우선순위 토픽”이 조항 단위에도 섞이면,
  - 조항과 무관한 결과가 함께 섞일 수 있음

---

## 2) 개선 내용(이번 수정)

### 2.1 scope 도입: contract vs clause

- `search_for_review(... scope="contract")`
  - 계약 전체 근거: 법인 우선순위 토픽을 포함 가능
- `search_for_review(... scope="clause")`
  - 조항 근거: 법인 우선순위 토픽을 기본적으로 포함하지 않음(노이즈 최소화)
  - 판례(`prec`)는 기본 비활성(직접 연결되는 경우에만 추후 확장)

구현:
- [search_service.py:search_for_review](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L35-L66)
- clause-level 적용: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L152-L168)
- contract-level 적용: [server.py /api/review/analyze](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L644-L666)

### 2.2 결과 rerank/필터 강화

- 필터:
  - 제목에 `입법예고/조례안/광고/채용/공고/보도자료/안내`가 포함되면 제거
- 관련성 점수:
  - 조항 텍스트 + matched_rules의 키워드(및 rule_id)를 토큰화한 뒤,
  - title/snippet과의 overlap 기반으로 점수 계산
  - 낮은 점수는 제거

구현:
- [search_service.py:_rerank_and_filter_references](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L232-L250)

---

## 3) 회귀 테스트

- 노이즈 결과(조례안/채용 공고)가 필터링되고, 하도급법이 남는지 검사:
  - [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py#L62-L94)

