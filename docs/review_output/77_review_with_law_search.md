# review analyze + 국가법령정보 검색 결합

변경 목표:
- 계약 텍스트, entity, contract_type, detected issues(rule 매칭)를 바탕으로
- 관련 법령/판례/해석례/행정규칙/자치법규를 자동 검색하고
- review 결과에 함께 포함

---

## 코드 변경

- `/api/review/analyze` 응답에 `law_search` 필드를 추가했습니다.
- 구현 위치: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
  - 기존 `RuleQueryService.analyze(...)` 실행 후
  - `LawSearchService.search_for_review(...)`로 자동 검색
  - 실패 시에도 rule 기반 결과는 유지하고 `law_search.enabled=false` + `error`만 반환

---

## 출력 형식 (law_search)

- `enabled`: bool
- `queries`: 검색에 사용한 토픽/키워드 목록
- `results`:
  - `laws`: 관련 법령(대표 3~5개)
  - `precedents`: 관련 판례(대표 3~5개)
  - `interpretations`: 해석례(대표 3~5개)
  - `admin_rules`: 행정규칙(대표 3~5개)
  - `local_ordinances`: 자치법규(대표 3~5개)
- 각 항목은 대략 다음을 포함:
  - `title`, `snippet`, `identifiers`, `drf_detail_url`, `source_query`

---

## 예시 연결 로직(요약)

현재 MVP에서는 rule id/계약유형/키워드 기반으로 다음을 우선 토픽에 포함합니다.
- 대리점/유통/위탁 → `대리점법`, `공정거래`
- 하도급/도급/공사 → `하도급법`, `공정거래`
- 개인정보 → `개인정보보호법`
- 안전/현장/공사 → `산업안전보건법`, `중대재해처벌법`

구현 위치: [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

