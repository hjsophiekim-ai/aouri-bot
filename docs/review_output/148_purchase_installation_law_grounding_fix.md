# 148) 구매+장비설치+시운전 계약 법령 grounding 정합성 개선

문제:
- LG 장비공급/설치 계약에도 대리점법이 반복적으로 붙는 등, 계약유형과 무관한 법령/키워드가 섞여 grounding 품질 저하

목표:
- 물품구매 + 장비설치 + 시운전 + 안전 + 품질 + 보증 + 책임제한 계약에 맞는 법령군만 우선 검색
- dealer/distributor law query 금지 또는 우선순위 하향
- clause issue별 법령 쿼리 템플릿 재정의
- 관련성 낮은 판례/행정해석 제거
- clause별 2~3개 제한 + reason_code 부여

---

## 1) 계약 프로파일 도입

- `contract_profile = purchase_installation`을 추론해, 해당 프로파일에서는 dealer/distributor 계열 토픽을 기본적으로 억제합니다.
- 구현: [search_service.py:_infer_contract_profile](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

---

## 2) purchase_installation 기본 쿼리 템플릿

contract scope(계약 전체 근거)에서 우선 쿼리를 다음처럼 설정합니다.

- 민법(매매/도급/하자담보/손해배상)
- 상법(상사매매 검사·통지)
- 산업안전보건법(설치/현장 작업 안전관리)
- 중대재해처벌법(안전보건 확보의무)
- 제조물책임법/품질보증(하자보수/보증)

구현: [search_service.py:_derive_queries](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

---

## 3) clause scope에서 노이즈 억제(판례/행정해석 제거)

조항 단위 grounding에서는:
- 법인 우선순위 토픽을 prepend하지 않음
- 판례(`prec`)는 기본 비활성(직접 연결이 강한 경우만 별도 룰로 확장)
- 제목 노이즈(조례안/입법예고/공고/보도자료 등)는 필터링

구현:
- [search_for_review(scope="clause")](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

---

## 4) reason_code 추가 및 상한 제한

- 응답에 `query_reasons`(query->reason_code)를 포함
- 각 결과 항목에도 `reason_code`와 `relevance_score`를 포함
- 조항당 최대 2~3개 제한은 기존 파라미터(`max_clause_law_items`)로 유지

---

## 5) 회귀 테스트

- LG 구매/설치 계약 프로파일에서 `민법` 포함, `대리점법` 미포함을 검증:
  - [test_buyer_favorable_regression.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_buyer_favorable_regression.py)
  - [test_buyer_favorable_regression_v2.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_buyer_favorable_regression_v2.py)

