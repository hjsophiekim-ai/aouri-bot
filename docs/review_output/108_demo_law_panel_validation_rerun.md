# /demo 화면 법률 검색 패널 노출 재검증(108)

## 결론
- `/demo` 결과 화면까지 진행 가능.
- 결과 화면 “상세 보기”에서 `관련 법령/판례/해석례` 섹션이 노출됨.
- 현재 UI는 요약 카드가 아니라 `law_search` JSON 덤프 형태로 보여준다.

## 확인 항목별 결과
### 1) 계약 입력 후 결과 화면에 법령/판례 패널이 보이는지
- PASS
  - `관련 법령/판례/해석례` 섹션이 존재하고 `enabled=true` 및 `results`가 노출됨

### 2) 대표 3~5개 정도 요약 노출이 되는지
- PARTIAL
  - 대표 N개 제한은 적용(현재는 타겟별 최대 3개), 다만 UI가 “요약 리스트”가 아니라 JSON으로 노출

### 3) 링크/식별정보가 보이는지
- PASS(형태는 JSON)
  - `title`, `identifiers`, `drf_detail_url` 등이 포함되어 노출됨

### 4) UI가 너무 복잡하지 않은지
- PARTIAL
  - 결과/상세 흐름은 단순하지만, 상세에서 JSON이 그대로 보여 정보량이 많음

### 5) law_search가 빈 경우 fallback 문구가 있는지
- 확인 필요
  - 이번 케이스에서는 law_search가 비어있지 않았음

## 근거(관측)
- 네트워크 요청에서 다음 호출 확인
  - `POST /api/review/analyze`
  - `POST /api/revision/suggest_text`
- 결과 화면의 상세 보기에서 `관련 법령/판례/해석례` JSON 블록 확인
